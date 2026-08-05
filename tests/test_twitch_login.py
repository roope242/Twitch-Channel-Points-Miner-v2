"""Regression coverage for issue #13: the device-code login flow.

Four defects, all in TwitchLogin.login_flow() and the cookie helpers, and how
each is pinned here:

- `now` was captured once, before the inner poll loop, and never reassigned,
  so `if now == expires_at:` was false forever -- a user who never enters the
  code made the miner poll id.twitch.tv forever, once every `interval`
  seconds. Pinned by an `expires_in: 0` device code: the fix must observe the
  wall clock catching up and break out after exactly one poll.
- `if "error_code" in login_response:` tested the raw `requests.Response`
  object, not the parsed JSON body, so `err_code` was never bound and the
  intended `NotImplementedError` was replaced by a `NameError`. `_FakeResponse`
  below has no `__contains__` that would ever find "error_code" on the
  response object itself, reproducing that exact miss.
- `save_cookies` wrote directly to the cookies file with no atomicity, and
  `load_cookies` had no exception handling, so a truncated/garbage pickle
  (e.g. from a process killed mid-write) crashed the next startup with a bare
  UnpicklingError/EOFError instead of the WrongCookiesException every other
  failure path already uses.
- A 200 response whose body had no `user_code` fell through the `if` with no
  `else`, immediately re-requesting a device code with no sleep -- a hot spin
  against id.twitch.tv on any malformed response.

Also covers a bug the expiry fix exposed: the inner loop's token-poll payload
reused the same `post_data` name as the outer device-code payload, so once
the expiry `break` actually became reachable, the retry it fell into posted
the scope-less token body to the device endpoint instead of the original one.
And `load_cookies`'s corruption catch is broadened from `(UnpicklingError,
EOFError)` to `Exception`, since a bad protocol byte raises `ValueError` and a
pickle referencing a missing class raises `AttributeError`/
`ModuleNotFoundError` -- the recovery is the same for all of them.
"""

import pickle

import pytest

import TwitchChannelPointsMiner.classes.TwitchLogin as twitch_login_module
from TwitchChannelPointsMiner.classes.Exceptions import WrongCookiesException
from TwitchChannelPointsMiner.classes.TwitchLogin import TwitchLogin


class _FakeResponse:
    """Stand-in for requests.Response: has .status_code and .json(), and --
    like the real thing when probed for a JSON key -- never contains
    "error_code" itself, only its parsed body might.
    """

    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data

    def __contains__(self, item):
        return False


def make_login():
    return TwitchLogin("client-id", "device-id", "some-user", "agent")


def test_poll_loop_exits_after_code_expires(monkeypatch):
    twitch_login = make_login()

    device_code_calls = 0
    token_poll_calls = 0
    second_device_request_body = None

    def fake_send_oauth_request(self, url, json_data):
        nonlocal device_code_calls, token_poll_calls, second_device_request_body
        if url.endswith("/device"):
            device_code_calls += 1
            if device_code_calls > 1:
                # This is the retry after expiry -- the one a stale/aliased
                # post_data would corrupt. Capture it for the assertion below
                # instead of asserting inline, so the outer loop still ends
                # the test cleanly on a non-200 either way.
                second_device_request_body = json_data
                return _FakeResponse(500, {})
            return _FakeResponse(
                200,
                {
                    "user_code": "ABCD1234",
                    "device_code": "devcode",
                    "interval": 0,
                    # Already expired by the time the poll loop starts, so a
                    # correct `>=` check trips on the very first iteration --
                    # and, since this differs from the `now` captured before
                    # the loop, the dead `now == expires_at` check can never
                    # match it by coincidence either.
                    "expires_in": -1,
                },
            )

        token_poll_calls += 1
        # Bounds the pre-fix infinite loop into a clean failure instead of a
        # hang: if the expiry check never fires, this trips well before it.
        assert token_poll_calls < 5, "poll loop did not exit once the code expired"
        return _FakeResponse(400, {})

    monkeypatch.setattr(TwitchLogin, "send_oauth_request", fake_send_oauth_request)
    monkeypatch.setattr(twitch_login_module, "sleep", lambda _seconds: None)

    result = twitch_login.login_flow()

    assert result is False
    assert token_poll_calls == 1
    # Regression for a bug the expiry fix exposed: the token payload built at
    # the top of the inner loop used to reuse the *same* `post_data` name as
    # the device-code payload, so this retry silently posted a scope-less
    # token body to the device endpoint instead of the original one.
    assert device_code_calls == 2
    assert second_device_request_body is not None
    assert "scopes" in second_device_request_body


def test_unknown_poll_error_raises_not_implemented_with_code(monkeypatch):
    twitch_login = make_login()

    def fake_send_oauth_request(self, url, json_data):
        if url.endswith("/device"):
            return _FakeResponse(
                200,
                {
                    "user_code": "ABCD1234",
                    "device_code": "devcode",
                    "interval": 0,
                    "expires_in": 1800,
                },
            )
        return _FakeResponse(200, {"error_code": "invalid_grant"})

    monkeypatch.setattr(TwitchLogin, "send_oauth_request", fake_send_oauth_request)
    monkeypatch.setattr(twitch_login_module, "sleep", lambda _seconds: None)

    with pytest.raises(NotImplementedError, match="invalid_grant"):
        twitch_login.login_flow()


def test_load_cookies_corrupt_file_raises_wrong_cookies_exception(tmp_path):
    # Truncation/garbage bytes: raises UnpicklingError or EOFError.
    truncated_file = tmp_path / "truncated.pkl"
    truncated_file.write_bytes(b"not a pickle")

    twitch_login = make_login()

    with pytest.raises(WrongCookiesException):
        twitch_login.load_cookies(str(truncated_file))

    # A bad protocol byte: pickle.load raises ValueError, a different shape
    # than the UnpicklingError/EOFError above -- both must recover the same
    # way rather than only the truncation case being caught.
    bad_protocol_file = tmp_path / "bad-protocol.pkl"
    bad_protocol_file.write_bytes(b"\x80\x06garbage")

    with pytest.raises(WrongCookiesException):
        twitch_login.load_cookies(str(bad_protocol_file))


def test_save_cookies_round_trip_and_survives_a_failed_write(tmp_path, monkeypatch):
    cookies_file = tmp_path / "some-user.pkl"
    twitch_login = make_login()
    twitch_login.token = "atoken123"
    twitch_login.user_id = 42

    twitch_login.save_cookies(str(cookies_file))
    assert list(tmp_path.iterdir()) == [cookies_file]

    reloaded = make_login()
    reloaded.load_cookies(str(cookies_file))
    assert reloaded.get_cookie_value("auth-token") == "atoken123"

    # Now simulate a process killed mid-write: pickle.dump writes a few bytes
    # and then never returns.
    def failing_dump(obj, fileobj, *args, **kwargs):
        fileobj.write(b"\x80\x04")
        raise RuntimeError("simulated crash mid-write")

    monkeypatch.setattr(pickle, "dump", failing_dump)
    twitch_login.token = "should-never-be-saved"

    with pytest.raises(RuntimeError):
        twitch_login.save_cookies(str(cookies_file))

    # The previous, valid cookies file must survive a failed write untouched
    # -- not truncated by the doomed attempt -- with no partial temp file
    # left behind in the directory either.
    assert list(tmp_path.iterdir()) == [cookies_file]
    reloaded_again = make_login()
    reloaded_again.load_cookies(str(cookies_file))
    assert reloaded_again.get_cookie_value("auth-token") == "atoken123"


def test_missing_user_code_sleeps_before_retry(monkeypatch):
    twitch_login = make_login()

    calls = 0
    sleep_calls = []

    def fake_send_oauth_request(self, url, json_data):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _FakeResponse(200, {"unexpected": "body"})
        # End the loop on the second request so the test terminates.
        return _FakeResponse(500, {})

    monkeypatch.setattr(TwitchLogin, "send_oauth_request", fake_send_oauth_request)
    monkeypatch.setattr(
        twitch_login_module, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    result = twitch_login.login_flow()

    assert result is False
    assert calls == 2
    assert sleep_calls == [5]
