"""Regression coverage for issue #12: notifiers must not let a viewer-controlled
chat message escape its encoding.

Webhook.send() builds its URL by hand and must percent-encode both event name
and message with safe="" (no query-string injection, no unescaped "/").
Discord.send() must post its payload with json=, not data=: form encoding
flattens the nested allowed_mentions object to "allowed_mentions=parse", which
Discord silently ignores, so a bare @everyone in the message would actually
ping the channel. json= is what keeps allowed_mentions a real nested object.
"""

from urllib.parse import parse_qs, urlparse

from TwitchChannelPointsMiner.classes.Discord import Discord
from TwitchChannelPointsMiner.classes.Settings import Events
from TwitchChannelPointsMiner.classes.Webhook import Webhook

MALICIOUS_MESSAGE = "hello&event_name=BET_WIN&injected=1 / @everyone"


def test_webhook_get_percent_encodes_message_and_event(monkeypatch):
    captured = {}

    def fake_get(url, timeout=None):
        captured["url"] = url
        captured["timeout"] = timeout

    monkeypatch.setattr(
        "TwitchChannelPointsMiner.classes.Webhook.requests.get", fake_get
    )

    webhook = Webhook(
        endpoint="http://example.test/hook",
        method="GET",
        events=[Events.CHAT_MENTION],
    )
    webhook.send(MALICIOUS_MESSAGE, Events.CHAT_MENTION)

    assert "url" in captured, "no request was sent"
    parsed = urlparse(captured["url"])
    assert parsed.scheme == "http"
    assert parsed.netloc == "example.test"
    assert parsed.path == "/hook"

    # The injected "&event_name=" must decode back to a single literal value,
    # not create a second query parameter.
    query = parse_qs(parsed.query)
    assert query["event_name"] == ["CHAT_MENTION"]
    assert query["message"] == [MALICIOUS_MESSAGE]
    assert "injected" not in query

    # ...and specifically safe="": quote()'s default safe="/" passes "/" through
    # untouched, and parse_qs decodes %2F back to "/" either way, so the
    # assertions above hold under both. Only the raw query string tells them
    # apart. Without this, dropping safe="" would leave the suite green.
    assert "%2F" in parsed.query
    assert "/" not in parsed.query


def test_webhook_post_uses_post_method(monkeypatch):
    captured = {}

    def fake_post(url, timeout=None):
        captured["url"] = url

    def fail(*args, **kwargs):
        raise AssertionError("GET was called for a POST-configured webhook")

    monkeypatch.setattr(
        "TwitchChannelPointsMiner.classes.Webhook.requests.post", fake_post
    )
    monkeypatch.setattr("TwitchChannelPointsMiner.classes.Webhook.requests.get", fail)

    webhook = Webhook(
        endpoint="http://example.test/hook",
        method="POST",
        events=[Events.CHAT_MENTION],
    )
    webhook.send("hi", Events.CHAT_MENTION)

    assert "url" in captured


def test_webhook_does_not_send_for_unlisted_event(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("no request should be sent for an unlisted event")

    monkeypatch.setattr("TwitchChannelPointsMiner.classes.Webhook.requests.get", fail)
    monkeypatch.setattr("TwitchChannelPointsMiner.classes.Webhook.requests.post", fail)

    webhook = Webhook(
        endpoint="http://example.test/hook", method="GET", events=[Events.BET_WIN]
    )
    webhook.send("hi", Events.CHAT_MENTION)


def test_discord_sends_json_with_nested_allowed_mentions(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs

    monkeypatch.setattr(
        "TwitchChannelPointsMiner.classes.Discord.requests.post", fake_post
    )

    discord = Discord(
        webhook_api="http://example.test/discord-hook", events=[Events.CHAT_MENTION]
    )
    discord.send(MALICIOUS_MESSAGE, Events.CHAT_MENTION)

    # The actual #12 bug: a data= call form-encodes the payload, which
    # flattens the nested allowed_mentions object to a scalar Discord ignores.
    # json= is what keeps it a real nested object; assert the call shape, not
    # just that some serialization of the key showed up.
    assert "data" not in captured["kwargs"], "must be sent as json=, not data="
    assert "json" in captured["kwargs"]
    body = captured["kwargs"]["json"]
    assert body["content"] == MALICIOUS_MESSAGE
    assert isinstance(body["allowed_mentions"], dict)
    assert body["allowed_mentions"] == {"parse": []}


def test_discord_does_not_send_for_unlisted_event(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("no request should be sent for an unlisted event")

    monkeypatch.setattr("TwitchChannelPointsMiner.classes.Discord.requests.post", fail)

    discord = Discord(webhook_api="http://example.test/discord-hook", events=[])
    discord.send("hi", Events.CHAT_MENTION)
