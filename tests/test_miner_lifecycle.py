"""Offline construction and shutdown of TwitchChannelPointsMiner.

Login happens in run(), not __init__, so the miner can be built and torn down
without authenticating. __init__ does fire off check_versions() on a daemon
thread (raw.githubusercontent.com), but it is fire-and-forget: it neither
blocks construction nor fails the test when the network is unavailable.

See issue #14: a bare `import` and `py_compile` both passed on an end() that
crashed on its first line, so exercising end() for real is the point here.
"""

import logging

import pytest

from TwitchChannelPointsMiner import TwitchChannelPointsMiner
from TwitchChannelPointsMiner.logger import LoggerSettings


def make_miner(username="ci-test"):
    return TwitchChannelPointsMiner(
        username=username,
        logger_settings=LoggerSettings(save=False, console_level=logging.CRITICAL),
    )


def test_constructs_offline(monkeypatch, tmp_path):
    # enable_analytics defaults to False, so nothing here should touch the cwd,
    # but chdir into a throwaway directory anyway in case that ever changes.
    monkeypatch.chdir(tmp_path)

    miner = make_miner()

    assert miner.username == "ci-test"
    assert miner.running is False
    assert miner.shutting_down is False
    assert miner.streamers == []


def test_end_shuts_down_cleanly(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    miner = make_miner()

    with pytest.raises(SystemExit) as excinfo:
        miner.end(None, None)

    assert excinfo.value.code == 0
    assert miner.shutting_down is True


def test_end_is_reentrant_safe(monkeypatch, tmp_path):
    # end() guards on shutting_down, not running, so a second call (e.g. a
    # repeated signal) must not re-run teardown or raise.
    monkeypatch.chdir(tmp_path)
    miner = make_miner()

    with pytest.raises(SystemExit):
        miner.end(None, None)

    miner.end(None, None)  # second call: must return quietly, not raise/exit
    assert miner.shutting_down is True
