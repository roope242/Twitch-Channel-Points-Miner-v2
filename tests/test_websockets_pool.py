"""Regression coverage for issue #10: PubSub reconnection.

Everything here is offline. No socket is ever connected: `WebSocketApp.__init__`
only stores the URL, `run_forever` is reached exclusively through
`WebSocketsPool.__start`, which these tests replace, and `time.sleep` /
`internet_connection_available` are swapped out so the reconnect path runs at
full speed.

The four defects, and how each is pinned here:

- `handle_reconnection` used to sleep ~60s on its caller's thread, so one stale
  socket parked the miner's whole main loop. Proved structurally, not by the
  clock: the test holds the wait open and observes it still pending after the
  call has returned.
- The `is_reconnecting` guard was a check-then-act reached from four threads.
  `RacingSocket` forces the interleaving the lock has to survive - without it
  the window is a few bytecodes wide and a plain race would almost never lose.
- Duplicate-message state lived on the individual socket, which is the one place
  it cannot work: a duplicate arrives on a *different* connection. It is a
  bounded window on the pool now, not the single previous message - with two
  connections the other one's traffic interleaves, and a single slot has been
  overwritten by the time the copy shows up.
- `PubsubTopic` had no `__eq__`, so `topic not in ws.topics` was an identity
  check and a re-added streamer got its topic listened to twice.
"""

import json
import threading
import time as real_time
from types import SimpleNamespace

import pytest

import TwitchChannelPointsMiner.classes.WebSocketsPool as pool_module
from TwitchChannelPointsMiner.classes.entities.PubsubTopic import PubsubTopic
from TwitchChannelPointsMiner.classes.TwitchWebSocket import TwitchWebSocket
from TwitchChannelPointsMiner.classes.WebSocketsPool import WebSocketsPool
from TwitchChannelPointsMiner.constants import WEBSOCKET


def make_streamer(channel_id):
    return SimpleNamespace(channel_id=channel_id)


def join_reconnect_threads(timeout=5):
    """Wait for anything the pool spawned, found by the naming convention."""
    for thread in threading.enumerate():
        if thread is threading.current_thread():
            continue
        if thread.name.startswith("WebSocket #"):
            thread.join(timeout=timeout)


class SleepGate:
    """A time.sleep the test can hold open and watch.

    The wait is bounded so the *unfixed* code, which sleeps on the caller's
    thread, fails an assertion instead of hanging the suite.
    """

    def __init__(self):
        self.entered = threading.Event()
        self.released = threading.Event()

    def sleep(self, seconds):
        self.entered.set()
        self.released.wait(timeout=5)


class RacingSocket(TwitchWebSocket):
    """Parks the first reader of is_reconnecting until a second one arrives.

    Both callers then observe False together, which is exactly the interleaving
    the unlocked check-then-act loses. Under the lock the second reader never
    gets there, so the rendezvous times out and the socket behaves normally.
    """

    def __init__(self, *args, **kwargs):
        self._is_reconnecting = False
        self._rendezvous = threading.Barrier(2)
        super().__init__(*args, **kwargs)

    @property
    def is_reconnecting(self):
        # Sample first, rendezvous second: the two callers must come away with
        # the value each saw *before* the other could set it, which is what a
        # simultaneous read is. Returning it after the barrier would instead
        # hand the second caller the flag the first had already claimed.
        sampled = self._is_reconnecting
        try:
            self._rendezvous.wait(timeout=0.5)
        except threading.BrokenBarrierError:
            pass
        return sampled

    @is_reconnecting.setter
    def is_reconnecting(self, value):
        self._is_reconnecting = value


def fake_time(sleep):
    return SimpleNamespace(sleep=sleep, time=real_time.time)


@pytest.fixture
def reconnect_env(monkeypatch):
    """A pool whose rebuild is counted and whose waits are instant."""
    calls = {"new": 0, "start": 0}

    def fake_new(self, index):
        calls["new"] += 1
        return SimpleNamespace(index=index, topics=[], forced_close=False)

    def fake_start(self, index):
        calls["start"] += 1

    def fake_submit(self, index, topic):
        calls["submit"] += 1

    calls["submit"] = 0
    monkeypatch.setattr(WebSocketsPool, "_WebSocketsPool__new", fake_new)
    monkeypatch.setattr(WebSocketsPool, "_WebSocketsPool__start", fake_start)
    monkeypatch.setattr(WebSocketsPool, "_WebSocketsPool__submit", fake_submit)
    monkeypatch.setattr(pool_module, "internet_connection_available", lambda: True)
    monkeypatch.setattr(pool_module, "time", fake_time(lambda seconds: None))

    pool = WebSocketsPool(twitch=None, streamers=[], events_predictions={})
    yield pool, calls
    join_reconnect_threads()


def add_socket(pool, socket_class=TwitchWebSocket, index=0):
    ws = socket_class(index=index, parent_pool=pool, url=WEBSOCKET)
    pool.ws.append(ws)
    return ws


def test_two_callers_rebuild_the_socket_only_once(reconnect_env):
    pool, calls = reconnect_env
    ws = add_socket(pool, socket_class=RacingSocket)

    callers = [
        threading.Thread(target=WebSocketsPool.handle_reconnection, args=(ws,))
        for _ in range(2)
    ]
    for caller in callers:
        caller.start()
    for caller in callers:
        caller.join(timeout=5)
        assert caller.is_alive() is False

    join_reconnect_threads()

    # The loser has to return having done nothing: a second rebuild orphans a
    # live connection that is still subscribed to every topic it carried.
    assert calls["new"] == 1
    assert calls["start"] == 1
    assert len(pool.ws) == 1
    assert pool.ws[0] is not ws


def test_handle_reconnection_does_not_block_its_caller(reconnect_env, monkeypatch):
    pool, calls = reconnect_env
    ws = add_socket(pool)
    gate = SleepGate()
    monkeypatch.setattr(pool_module, "time", fake_time(gate.sleep))

    WebSocketsPool.handle_reconnection(ws)

    # Control is back here while the reconnect wait is still parked in the gate
    # - that pending wait is the proof, rather than any wall-clock threshold.
    assert gate.entered.wait(timeout=5) is True
    assert gate.released.is_set() is False
    assert calls["new"] == 0
    assert pool.ws[0] is ws

    gate.released.set()
    join_reconnect_threads()

    assert calls["new"] == 1
    assert pool.ws[0] is not ws


def test_forced_close_during_the_wait_cancels_the_rebuild(reconnect_env, monkeypatch):
    pool, calls = reconnect_env
    ws = add_socket(pool)
    gate = SleepGate()
    monkeypatch.setattr(pool_module, "time", fake_time(gate.sleep))

    def shutdown_once_waiting():
        gate.entered.wait(timeout=5)
        ws.forced_close = True  # what WebSocketsPool.end() does
        gate.released.set()

    canceller = threading.Thread(target=shutdown_once_waiting)
    canceller.start()

    WebSocketsPool.handle_reconnection(ws)

    canceller.join(timeout=5)
    join_reconnect_threads()

    assert calls["new"] == 0
    assert calls["start"] == 0
    assert pool.ws[0] is ws


def test_shutdown_after_the_rebind_stops_the_topic_replay(reconnect_env, monkeypatch):
    # end() sets forced_close on whatever is in self.ws, so once the rebind has
    # happened it marks the *replacement*. Reading the retired socket's flag
    # would miss the shutdown and replay every topic into a closed connection.
    pool, calls = reconnect_env
    ws = add_socket(pool)
    ws.topics.append(PubsubTopic("video-playback-by-id", streamer=make_streamer(123)))

    sleeps = {"count": 0}

    def sleep_then_shut_down(seconds):
        sleeps["count"] += 1
        if sleeps["count"] == 2:  # the wait after the socket was rebuilt
            pool.ws[0].forced_close = True  # what WebSocketsPool.end() does now

    monkeypatch.setattr(pool_module, "time", fake_time(sleep_then_shut_down))

    WebSocketsPool.handle_reconnection(ws)
    join_reconnect_threads()

    assert calls["new"] == 1
    assert calls["submit"] == 0


def claim_available_message(channel_id="123", timestamp="2026-08-01T12:00:00Z"):
    payload = {
        "type": "claim-available",
        "data": {
            "timestamp": timestamp,
            "claim": {"id": f"claim-{timestamp}", "channel_id": channel_id},
        },
    }
    return json.dumps(
        {
            "type": "MESSAGE",
            "data": {
                "topic": f"community-points-user-v1.{channel_id}",
                "message": json.dumps(payload),
            },
        }
    )


def test_duplicate_message_on_a_second_socket_is_dispatched_once():
    claimed = []
    pool = WebSocketsPool(
        twitch=SimpleNamespace(
            claim_bonus=lambda streamer, claim_id: claimed.append(claim_id)
        ),
        streamers=[SimpleNamespace(channel_id="123")],
        events_predictions={},
    )
    first = TwitchWebSocket(index=0, parent_pool=pool, url=WEBSOCKET)
    second = TwitchWebSocket(index=1, parent_pool=pool, url=WEBSOCKET)

    message = claim_available_message()
    WebSocketsPool.on_message(first, message)
    assert claimed == [
        "claim-2026-08-01T12:00:00Z"
    ], "first delivery was not dispatched"

    # Same message, other connection: Twitch sends it on both.
    WebSocketsPool.on_message(second, message)
    assert len(claimed) == 1

    # A genuinely different message on that same second connection must still
    # get through - the guard is only about the immediately preceding message.
    WebSocketsPool.on_message(
        second, claim_available_message(timestamp="2026-08-01T12:05:00Z")
    )
    assert claimed == ["claim-2026-08-01T12:00:00Z", "claim-2026-08-01T12:05:00Z"]


def test_pubsub_topic_equality_is_by_value():
    streamer_topic = PubsubTopic("video-playback-by-id", streamer=make_streamer(123))
    same_streamer_topic = PubsubTopic(
        "video-playback-by-id", streamer=make_streamer(123)
    )
    other_topic = PubsubTopic("raid", streamer=make_streamer(123))
    other_streamer = PubsubTopic("video-playback-by-id", streamer=make_streamer(456))

    assert streamer_topic == same_streamer_topic
    assert hash(streamer_topic) == hash(same_streamer_topic)
    assert streamer_topic in [other_topic, same_streamer_topic]
    assert streamer_topic != other_topic
    assert streamer_topic != other_streamer
    assert streamer_topic != str(streamer_topic)

    user_topic = PubsubTopic("community-points-user-v1", user_id=42)
    assert user_topic == PubsubTopic("community-points-user-v1", user_id=42)
    assert user_topic != PubsubTopic("community-points-user-v1", user_id=43)


def test_interleaved_duplicate_is_still_caught(monkeypatch):
    # The reason the pool remembers a window and not just the previous message:
    # with two connections, the other one's traffic lands between a message and
    # its copy. A single-slot check has been evicted by then and lets the copy
    # through, double-claiming the bonus.
    claimed = []
    pool = WebSocketsPool(
        twitch=SimpleNamespace(
            claim_bonus=lambda streamer, claim_id: claimed.append(claim_id)
        ),
        streamers=[
            SimpleNamespace(channel_id="123"),
            SimpleNamespace(channel_id="456"),
        ],
        events_predictions={},
    )
    first = TwitchWebSocket(index=0, parent_pool=pool, url=WEBSOCKET)
    second = TwitchWebSocket(index=1, parent_pool=pool, url=WEBSOCKET)

    message = claim_available_message(channel_id="123")
    WebSocketsPool.on_message(first, message)
    # Another connection's message for a different channel, in between.
    WebSocketsPool.on_message(
        second,
        claim_available_message(channel_id="456", timestamp="2026-08-01T12:00:01Z"),
    )
    WebSocketsPool.on_message(second, message)

    assert claimed == ["claim-2026-08-01T12:00:00Z", "claim-2026-08-01T12:00:01Z"]


def test_the_duplicate_window_is_bounded():
    # It has to forget eventually, or a long-running miner grows a list per
    # message for the life of the process.
    pool = WebSocketsPool(twitch=None, streamers=[], events_predictions={})
    ws = TwitchWebSocket(index=0, parent_pool=pool, url=WEBSOCKET)

    for minute in range(pool_module.RECENT_MESSAGES_WINDOW * 3):
        WebSocketsPool.on_message(
            ws, claim_available_message(timestamp=f"2026-08-01T12:{minute:02d}:00Z")
        )

    assert len(pool.recent_messages) == pool_module.RECENT_MESSAGES_WINDOW


def test_resubmitting_an_equal_topic_does_not_listen_twice():
    # The case that made this matter: a followers refresh builds a brand new
    # PubsubTopic for a streamer the connection is already subscribed to.
    # Recording it once is not enough - the second LISTEN must not be sent.
    sent = []
    pool = WebSocketsPool(
        twitch=SimpleNamespace(
            twitch_login=SimpleNamespace(get_auth_token=lambda: "token")
        ),
        streamers=[],
        events_predictions={},
    )
    ws = TwitchWebSocket(index=0, parent_pool=pool, url=WEBSOCKET)
    ws.is_opened = True
    ws.send = lambda request: sent.append(request)
    pool.ws.append(ws)

    pool._WebSocketsPool__submit(
        0, PubsubTopic("video-playback-by-id", streamer=make_streamer(123))
    )
    pool._WebSocketsPool__submit(
        0, PubsubTopic("video-playback-by-id", streamer=make_streamer(123))
    )

    assert len(ws.topics) == 1
    assert len(sent) == 1

    # A socket that has not opened yet queues instead of sending; the duplicate
    # must not reach that queue either.
    pending_ws = TwitchWebSocket(index=1, parent_pool=pool, url=WEBSOCKET)
    pool.ws.append(pending_ws)
    for _ in range(2):
        pool._WebSocketsPool__submit(
            1, PubsubTopic("video-playback-by-id", streamer=make_streamer(999))
        )

    assert len(pending_ws.pending_topics) == 1
