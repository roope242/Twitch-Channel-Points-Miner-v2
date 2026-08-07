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

Two more, from review of the above:

- That broadened `except Exception` also swallowed real I/O errors (e.g. a
  cookies file that exists but isn't readable), reporting a perfectly good
  file as "corrupt" and throwing away good credentials in favor of a
  device-code login nobody can complete headlessly. `OSError` now propagates
  ahead of the broad catch.
- The expiry check ran before the status/access_token check, so a token
  arriving in the same round-trip as expiry was discarded. It now only fires
  on a non-200 response, so a 200 always gets its access_token/error handling
  first.
"""

import os
import pickle

import pytest
import requests

import TwitchChannelPointsMiner.classes.TwitchLogin as twitch_login_module
from TwitchChannelPointsMiner.classes.Exceptions import (
    BadCredentialsException,
    WrongCookiesException,
)
from TwitchChannelPointsMiner.classes.Twitch import Twitch
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


class _FakeNonJSONResponse:
    """Stand-in for a requests.Response whose body isn't JSON at all -- a
    proxy or CDN answering 200 with an HTML error page, say. `.json()`
    raises the way the real `requests.Response.json()` does (a
    JSONDecodeError, which subclasses ValueError), and `.text` carries the
    raw body for the fallback log message (#43).
    """

    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text

    def json(self):
        raise requests.exceptions.JSONDecodeError(
            "Expecting value: line 1 column 1 (char 0)", self.text, 0
        )


def make_login():
    return TwitchLogin("client-id", "device-id", "some-user", "agent")


def make_twitch(tmp_path, monkeypatch, username="some-user"):
    # Twitch.__init__ only creates a "cookies" directory under the current
    # working directory and constructs a TwitchLogin -- no network -- so it's
    # safe offline as long as cwd is a throwaway directory.
    monkeypatch.chdir(tmp_path)
    return Twitch(username, "agent")


def test_poll_loop_gives_up_after_max_device_code_attempts(monkeypatch):
    """Covers #39: the outer loop used to re-issue a device code forever once
    the inner poll loop broke out on expiry. Every device code here expires
    immediately, so a correct fix must stop requesting new ones once
    MAX_DEVICE_CODE_ATTEMPTS is reached instead of looping past it.
    """
    twitch_login = make_login()

    device_code_calls = 0
    token_poll_calls = 0
    second_device_request_body = None

    def fake_send_oauth_request(self, url, json_data):
        nonlocal device_code_calls, token_poll_calls, second_device_request_body
        if url.endswith("/device"):
            device_code_calls += 1
            # Pre-fix, this would run forever; fail the test loudly instead
            # of hanging if the bound is not honoured.
            assert (
                device_code_calls <= twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
            ), "login_flow requested a device code past the bound"
            if device_code_calls == 2:
                # This is the retry after the first code's expiry -- the one
                # a stale/aliased post_data would corrupt. Capture it for the
                # assertion below.
                second_device_request_body = json_data
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
        assert token_poll_calls < 20, "poll loop did not exit once the code expired"
        return _FakeResponse(400, {})

    monkeypatch.setattr(TwitchLogin, "send_oauth_request", fake_send_oauth_request)
    monkeypatch.setattr(twitch_login_module, "sleep", lambda _seconds: None)

    result = twitch_login.login_flow()

    assert result is False
    # One poll per expired code, none left over once the bound is hit.
    assert token_poll_calls == twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
    assert device_code_calls == twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
    # Regression for a bug the expiry fix exposed: the token payload built at
    # the top of the inner loop used to reuse the *same* `post_data` name as
    # the device-code payload, so this retry silently posted a scope-less
    # token body to the device endpoint instead of the original one.
    assert second_device_request_body is not None
    assert "scopes" in second_device_request_body


def test_successful_login_before_bound_is_not_treated_as_given_up(monkeypatch):
    """The bound must not interfere with an ordinary retry-then-succeed run:
    a first code expires, a second one is entered in time.
    """
    twitch_login = make_login()
    monkeypatch.setattr(TwitchLogin, "check_login", lambda self: True)

    device_code_calls = 0

    def fake_send_oauth_request(self, url, json_data):
        nonlocal device_code_calls
        if url.endswith("/device"):
            device_code_calls += 1
            assert device_code_calls <= 2
            return _FakeResponse(
                200,
                {
                    "user_code": "ABCD1234",
                    "device_code": "devcode",
                    "interval": 0,
                    # First code is already expired; second isn't.
                    "expires_in": -1 if device_code_calls == 1 else 1800,
                },
            )
        if device_code_calls == 1:
            return _FakeResponse(400, {})
        return _FakeResponse(200, {"access_token": "REAL-TOKEN"})

    monkeypatch.setattr(TwitchLogin, "send_oauth_request", fake_send_oauth_request)
    monkeypatch.setattr(twitch_login_module, "sleep", lambda _seconds: None)

    result = twitch_login.login_flow()

    assert result is True
    assert twitch_login.token == "REAL-TOKEN"
    # Well within MAX_DEVICE_CODE_ATTEMPTS -- the bound never fired.
    assert device_code_calls == 2


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


def test_unknown_poll_error_does_not_log_full_payload(monkeypatch, caplog):
    """Covers #40: the token-endpoint error body is the one response class
    that can plausibly carry a credential, and file_level defaults to DEBUG
    -- logs/<username>.log is what users attach to bug reports. PR #37
    deliberately switched this line from the bare `Response` repr to the
    parsed body so a real error code would be diagnosable; that must still
    work, but the body itself must not be logged verbatim -- only its shape
    (error_code/message fields, and the sorted key names).
    """
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
        return _FakeResponse(
            200,
            {"error_code": "invalid_grant", "secret_field": "super-secret-value"},
        )

    monkeypatch.setattr(TwitchLogin, "send_oauth_request", fake_send_oauth_request)
    monkeypatch.setattr(twitch_login_module, "sleep", lambda _seconds: None)

    with caplog.at_level("ERROR"):
        with pytest.raises(NotImplementedError, match="invalid_grant"):
            twitch_login.login_flow()

    # The diagnosis (error code, and that "secret_field" is a key present
    # in the body) must still reach the log...
    assert "invalid_grant" in caplog.text
    assert "secret_field" in caplog.text
    # ...but the value behind that key must not.
    assert "super-secret-value" not in caplog.text


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
    """A 200 device body missing "user_code" must sleep and retry.

    Pre-#42, this test ended the loop early by switching the second response
    to a bare 500, since a non-200 aborted login_flow() instantly. #42 made
    a non-200 retry-and-sleep like every other malformed-response case
    instead, so a 500 no longer ends the loop early -- the fake now returns
    the same malformed body on every call and the test lets the loop run out
    its full attempt bound through the give-up path.
    """
    twitch_login = make_login()

    calls = 0
    sleep_calls = []

    def fake_send_oauth_request(self, url, json_data):
        nonlocal calls
        calls += 1
        assert calls <= twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
        return _FakeResponse(200, {"unexpected": "body"})

    monkeypatch.setattr(TwitchLogin, "send_oauth_request", fake_send_oauth_request)
    monkeypatch.setattr(
        twitch_login_module, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    result = twitch_login.login_flow()

    assert result is False
    assert calls == twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
    assert sleep_calls == (
        [twitch_login_module.MALFORMED_RESPONSE_RETRY_SECONDS]
        * (twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS - 1)
    )


def test_missing_device_code_sleeps_before_retry(monkeypatch):
    """Covers #38: a 200 device body with `user_code` but no `device_code`
    used to be read with `login_response_json["device_code"]` and raise a
    bare KeyError out of login_flow() -- on the field the poll loop actually
    posts, so this is the one that matters most. Must retry like the other
    missing-field cases instead.

    Pre-#42, this test ended the loop early via a bare 500 on the second
    call; #42 made non-200 retry-and-sleep too, so the fake now repeats the
    same malformed body and the test runs the loop out to its give-up path.
    """
    twitch_login = make_login()

    calls = 0
    sleep_calls = []

    def fake_send_oauth_request(self, url, json_data):
        nonlocal calls
        calls += 1
        assert calls <= twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
        return _FakeResponse(
            200,
            {
                "user_code": "ABCD1234",
                "interval": 5,
                "expires_in": 1800,
                # "device_code" missing.
            },
        )

    monkeypatch.setattr(TwitchLogin, "send_oauth_request", fake_send_oauth_request)
    monkeypatch.setattr(
        twitch_login_module, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    result = twitch_login.login_flow()

    assert result is False
    assert calls == twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
    assert sleep_calls == (
        [twitch_login_module.MALFORMED_RESPONSE_RETRY_SECONDS]
        * (twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS - 1)
    )


def test_missing_interval_sleeps_before_retry(monkeypatch):
    """Covers #38: a 200 device body with `user_code` but no `interval` used
    to be read with `login_response_json["interval"]` and raise a bare
    KeyError out of login_flow(). It must be treated like the missing-
    user_code case instead: log, sleep, retry.

    Pre-#42, this test ended the loop early via a bare 500 on the second
    call; #42 made non-200 retry-and-sleep too, so the fake now repeats the
    same malformed body and the test runs the loop out to its give-up path.
    """
    twitch_login = make_login()

    calls = 0
    sleep_calls = []

    def fake_send_oauth_request(self, url, json_data):
        nonlocal calls
        calls += 1
        assert calls <= twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
        return _FakeResponse(
            200,
            {
                "user_code": "ABCD1234",
                "device_code": "devcode",
                "expires_in": 1800,
                # "interval" missing.
            },
        )

    monkeypatch.setattr(TwitchLogin, "send_oauth_request", fake_send_oauth_request)
    monkeypatch.setattr(
        twitch_login_module, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    result = twitch_login.login_flow()

    assert result is False
    assert calls == twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
    assert sleep_calls == (
        [twitch_login_module.MALFORMED_RESPONSE_RETRY_SECONDS]
        * (twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS - 1)
    )


def test_missing_expires_in_sleeps_before_retry(monkeypatch):
    """Same as above for the other field named in #38: `expires_in` missing
    used to raise out of `timedelta(seconds=login_response_json["expires_in"])`.

    Pre-#42, this test ended the loop early via a bare 500 on the second
    call; #42 made non-200 retry-and-sleep too, so the fake now repeats the
    same malformed body and the test runs the loop out to its give-up path.
    """
    twitch_login = make_login()

    calls = 0
    sleep_calls = []

    def fake_send_oauth_request(self, url, json_data):
        nonlocal calls
        calls += 1
        assert calls <= twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
        return _FakeResponse(
            200,
            {
                "user_code": "ABCD1234",
                "device_code": "devcode",
                "interval": 5,
                # "expires_in" missing.
            },
        )

    monkeypatch.setattr(TwitchLogin, "send_oauth_request", fake_send_oauth_request)
    monkeypatch.setattr(
        twitch_login_module, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    result = twitch_login.login_flow()

    assert result is False
    assert calls == twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
    assert sleep_calls == (
        [twitch_login_module.MALFORMED_RESPONSE_RETRY_SECONDS]
        * (twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS - 1)
    )


def test_malformed_device_responses_count_against_give_up_bound(monkeypatch):
    """A run of malformed device responses (the #38 retry path) must spend
    attempts from the same #39 bound rather than looping forever on its own.
    """
    twitch_login = make_login()

    calls = 0
    sleep_calls = []

    def fake_send_oauth_request(self, url, json_data):
        nonlocal calls
        calls += 1
        assert (
            calls <= twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
        ), "malformed-response retries were not bounded"
        # Missing "user_code" on every single response.
        return _FakeResponse(200, {"interval": 5, "expires_in": 1800})

    monkeypatch.setattr(TwitchLogin, "send_oauth_request", fake_send_oauth_request)
    monkeypatch.setattr(
        twitch_login_module, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    result = twitch_login.login_flow()

    assert result is False
    assert calls == twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
    # One wait *between* attempts, and none after the last -- waiting out the
    # retry interval when there is no attempt left only delays the exit.
    assert sleep_calls == (
        [twitch_login_module.MALFORMED_RESPONSE_RETRY_SECONDS]
        * (twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS - 1)
    )


def test_non_dict_device_response_retries_instead_of_raising(monkeypatch):
    """A 200 whose JSON body is not an object at all.

    The `.get()` reads that fixed #38 assume a mapping, where the membership
    test they replaced did not: `"user_code" in <list>` is merely False. So
    `null`, a list or a bare string turned a graceful retry into an
    AttributeError out of login_flow() -- the same failure #38 was filed to
    remove, one input shape over. `data: null` is a body Twitch is on record
    as returning (see post_gql_request in classes/Twitch.py).
    """
    for body in (None, ["error"], "rate limited"):
        twitch_login = make_login()
        calls = 0

        def fake_send_oauth_request(self, url, json_data, body=body):
            nonlocal calls
            calls += 1
            assert calls <= twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
            return _FakeResponse(200, body)

        monkeypatch.setattr(TwitchLogin, "send_oauth_request", fake_send_oauth_request)
        monkeypatch.setattr(twitch_login_module, "sleep", lambda _seconds: None)

        assert twitch_login.login_flow() is False
        assert calls == twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS


def test_non_200_device_response_retries_instead_of_aborting(monkeypatch):
    """Covers #42: a single non-200 from the device endpoint used to `break`
    out of the outer attempt loop immediately -- a user saw "attempt 1/3"
    and then only one attempt, and the while/else give-up log line was
    skipped entirely since `break` exits the loop without exhausting it. A
    503 blip during startup killed a headless miner outright. Non-200 must
    now spend an attempt and retry like the malformed-body case, exiting
    through the same while/else give-up path once the bound is reached.
    """
    twitch_login = make_login()

    calls = 0
    sleep_calls = []

    def fake_send_oauth_request(self, url, json_data):
        nonlocal calls
        calls += 1
        assert calls <= twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
        return _FakeResponse(503, {})

    monkeypatch.setattr(TwitchLogin, "send_oauth_request", fake_send_oauth_request)
    monkeypatch.setattr(
        twitch_login_module, "sleep", lambda seconds: sleep_calls.append(seconds)
    )

    result = twitch_login.login_flow()

    assert result is False
    # All 3 attempts spent, not just 1 -- the give-up path was reached
    # rather than an early `break` cutting the loop short.
    assert calls == twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
    assert sleep_calls == (
        [twitch_login_module.MALFORMED_RESPONSE_RETRY_SECONDS]
        * (twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS - 1)
    )


def test_non_200_device_response_recovers_on_retry(monkeypatch):
    """A transient non-200 must not prevent a later attempt from succeeding
    -- the #42 fix has to actually retry, not just avoid crashing/aborting.
    """
    twitch_login = make_login()
    monkeypatch.setattr(TwitchLogin, "check_login", lambda self: True)

    device_calls = 0

    def fake_send_oauth_request(self, url, json_data):
        nonlocal device_calls
        if url.endswith("/device"):
            device_calls += 1
            if device_calls == 1:
                return _FakeResponse(503, {})
            assert device_calls == 2
            return _FakeResponse(
                200,
                {
                    "user_code": "ABCD1234",
                    "device_code": "devcode",
                    "interval": 0,
                    "expires_in": 1800,
                },
            )
        return _FakeResponse(200, {"access_token": "REAL-TOKEN"})

    monkeypatch.setattr(TwitchLogin, "send_oauth_request", fake_send_oauth_request)
    monkeypatch.setattr(twitch_login_module, "sleep", lambda _seconds: None)

    result = twitch_login.login_flow()

    assert result is True
    assert twitch_login.token == "REAL-TOKEN"
    assert device_calls == 2


def test_non_json_device_response_retries_instead_of_raising(monkeypatch, caplog):
    """Covers #43: a 200 whose body isn't JSON at all -- a proxy or CDN
    answering `200 text/html`, say -- used to raise a bare JSONDecodeError
    straight out of `login_response.json()`, before ever reaching the
    `isinstance(..., dict)` guard #38/#39 added for a body that parses fine
    but to something unusable (`null`, a list, a bare string). That guard
    can't catch a body that never becomes a value at all. It must retry like
    those cases instead, and the raw response text -- which could be a whole
    HTML error page -- must be truncated before it reaches the log.
    """
    twitch_login = make_login()

    calls = 0
    html_body = "<html>" + ("x" * 5000) + "</html>"

    def fake_send_oauth_request(self, url, json_data):
        nonlocal calls
        calls += 1
        assert calls <= twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
        return _FakeNonJSONResponse(200, html_body)

    monkeypatch.setattr(TwitchLogin, "send_oauth_request", fake_send_oauth_request)
    monkeypatch.setattr(twitch_login_module, "sleep", lambda _seconds: None)

    with caplog.at_level("ERROR"):
        result = twitch_login.login_flow()

    assert result is False
    assert calls == twitch_login_module.MAX_DEVICE_CODE_ATTEMPTS
    # Some of the body reached the log (enough to diagnose), but not the
    # whole 5000-char page.
    assert "<html>" in caplog.text
    assert html_body not in caplog.text


def test_poll_success_at_expiry_still_returns_token(monkeypatch):
    twitch_login = make_login()
    # __set_user_id() would otherwise make a real HTTP request.
    monkeypatch.setattr(TwitchLogin, "check_login", lambda self: True)

    device_calls = 0

    def fake_send_oauth_request(self, url, json_data):
        nonlocal device_calls
        if url.endswith("/device"):
            device_calls += 1
            if device_calls > 1:
                # Bounds a pre-fix run -- which discards the token and asks
                # for a fresh code -- into a clean failure instead of a hang.
                # Unreached when the fix behaves correctly (device_calls
                # never exceeds 1), so #42 making a 500 retry-and-sleep
                # instead of aborting instantly doesn't affect this test --
                # sleep is mocked out below either way, and only `result`/
                # `token` are asserted, not device_calls.
                return _FakeResponse(500, {})
            return _FakeResponse(
                200,
                {
                    "user_code": "ABCD1234",
                    "device_code": "devcode",
                    "interval": 0,
                    "expires_in": 0,
                },
            )
        # A 200 carrying an access_token, landing exactly at expires_at.
        return _FakeResponse(200, {"access_token": "REAL-TOKEN"})

    monkeypatch.setattr(TwitchLogin, "send_oauth_request", fake_send_oauth_request)
    monkeypatch.setattr(twitch_login_module, "sleep", lambda _seconds: None)

    result = twitch_login.login_flow()

    assert result is True
    assert twitch_login.token == "REAL-TOKEN"


def test_login_recovers_from_corrupt_cookies_file(tmp_path, monkeypatch):
    twitch = make_twitch(tmp_path, monkeypatch)
    with open(twitch.cookies_file, "wb") as f:
        f.write(b"not a pickle")

    login_flow_called = False

    def fake_login_flow(self):
        nonlocal login_flow_called
        login_flow_called = True
        self.token = "fresh-token"
        return True

    monkeypatch.setattr(TwitchLogin, "login_flow", fake_login_flow)

    twitch.login()

    assert login_flow_called is True
    # The corrupt file was replaced with a loadable one carrying the fresh
    # session, not left corrupt and not silently skipped.
    reloaded = make_login()
    reloaded.load_cookies(twitch.cookies_file)
    assert reloaded.get_cookie_value("auth-token") == "fresh-token"


def test_login_loads_valid_cookies_without_login_flow(tmp_path, monkeypatch):
    twitch = make_twitch(tmp_path, monkeypatch)
    twitch.twitch_login.token = "saved-token"
    twitch.twitch_login.user_id = 99
    twitch.twitch_login.save_cookies(twitch.cookies_file)

    def fail_login_flow(self):
        raise AssertionError("login_flow must not run for a valid cookies file")

    monkeypatch.setattr(TwitchLogin, "login_flow", fail_login_flow)

    # A second instance, the way a real restart would create one.
    twitch_restarted = Twitch("some-user", "agent")
    twitch_restarted.login()

    assert twitch_restarted.twitch_login.token == "saved-token"


def test_login_propagates_permission_error_not_reported_as_corrupt(
    tmp_path, monkeypatch
):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root ignores file permission bits")

    twitch = make_twitch(tmp_path, monkeypatch)
    twitch.twitch_login.token = "saved-token"
    twitch.twitch_login.save_cookies(twitch.cookies_file)
    os.chmod(twitch.cookies_file, 0o000)

    # On the pre-fix source a PermissionError here is swallowed and reported
    # as "corrupt", falling through to a real, unpatched login_flow() -- a
    # live network call. Patch it so that path fails fast/offline instead of
    # hanging, while asserting it must never even be reached.
    def fail_login_flow(self):
        raise AssertionError(
            "login_flow must not run -- the PermissionError should propagate"
        )

    monkeypatch.setattr(TwitchLogin, "login_flow", fail_login_flow)

    try:
        with pytest.raises(PermissionError):
            twitch.login()
    finally:
        os.chmod(twitch.cookies_file, 0o600)


def test_login_raises_when_the_recovery_login_fails(tmp_path, monkeypatch):
    """A failed re-login after corrupt cookies must not return quietly.

    `login_flow()` gives up and returns False on a single non-200 from the
    device endpoint. Returning from `login()` there leaves the session with no
    Authorization header, and `run()` never checks -- the miner then reports
    "0 followers" and "streamer does not exist" for the rest of its life
    instead of a login failure, on every subsequent start.
    """
    twitch = make_twitch(tmp_path, monkeypatch)
    with open(twitch.cookies_file, "wb") as f:
        f.write(b"not a pickle")

    monkeypatch.setattr(TwitchLogin, "login_flow", lambda self: False)

    with pytest.raises(BadCredentialsException):
        twitch.login()

    assert twitch.twitch_login.token is None
    assert "Authorization" not in twitch.twitch_login.session.headers


def test_login_raises_when_the_first_login_fails(tmp_path, monkeypatch):
    """Same silent-continue, reached through the no-cookies-file branch."""
    twitch = make_twitch(tmp_path, monkeypatch)
    assert os.path.isfile(twitch.cookies_file) is False

    monkeypatch.setattr(TwitchLogin, "login_flow", lambda self: False)

    with pytest.raises(BadCredentialsException):
        twitch.login()
