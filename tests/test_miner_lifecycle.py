"""Offline construction and shutdown of TwitchChannelPointsMiner.

Login happens in run(), not __init__, so the miner can be built and torn down
without authenticating. See issue #14: a bare `import` and `py_compile` both
passed on an end() that crashed on its first line, so exercising end() for real
is the point here.

__init__ is *not* offline-safe on its own, which is why every test here uses the
offline_construction fixture. Two things reach the network:

- `while not is_connected()` (TwitchChannelPointsMiner.py:124) loops forever,
  five seconds at a time, until `socket.gethostbyname("twitch.tv")` succeeds. On
  a runner with blocked DNS this never returns.
- `check_versions` is spawned on a daemon thread and fetches from
  raw.githubusercontent.com. Harmless to construction, but it outlives the test
  and would otherwise still be running while later modules patch `requests`.
"""

import importlib
import logging
import socket

import pytest

from TwitchChannelPointsMiner import TwitchChannelPointsMiner
from TwitchChannelPointsMiner.logger import LoggerSettings

# The package's __init__ re-exports the class under the module's own name, so
# `TwitchChannelPointsMiner.TwitchChannelPointsMiner` resolves to the class and
# `import ... as` would hand back that instead of the module. Go via sys.modules.
miner_module = importlib.import_module(
    "TwitchChannelPointsMiner.TwitchChannelPointsMiner"
)


@pytest.fixture
def offline_construction(monkeypatch, tmp_path):
    """Make __init__ reach nothing outside the process."""
    monkeypatch.setattr(socket, "gethostbyname", lambda host: "127.0.0.1")
    monkeypatch.setattr(miner_module, "check_versions", lambda *a, **kw: None)
    # Nothing here enables analytics, so nothing should touch the cwd — but chdir
    # into a throwaway directory anyway in case that ever changes.
    monkeypatch.chdir(tmp_path)


def make_miner(username="ci-test"):
    return TwitchChannelPointsMiner(
        username=username,
        logger_settings=LoggerSettings(save=False, console_level=logging.CRITICAL),
    )


def test_constructs_offline(offline_construction):
    miner = make_miner()

    assert miner.username == "ci-test"
    assert miner.running is False
    assert miner.shutting_down is False
    assert miner.streamers == []


def test_end_shuts_down_cleanly(offline_construction):
    miner = make_miner()

    with pytest.raises(SystemExit) as excinfo:
        miner.end(None, None)

    assert excinfo.value.code == 0
    assert miner.shutting_down is True


def test_end_is_reentrant_safe(offline_construction):
    # end() guards on shutting_down, not running, so a second call (e.g. a
    # repeated signal) must not re-run teardown or raise.
    miner = make_miner()

    with pytest.raises(SystemExit):
        miner.end(None, None)

    miner.end(None, None)  # second call: must return quietly, not raise/exit
    assert miner.shutting_down is True
