"""Pure-function coverage for TwitchChannelPointsMiner/utils.py."""

from types import SimpleNamespace

from TwitchChannelPointsMiner.utils import (
    at_least_one_value_in_settings_is,
    create_chunks,
    float_round,
    get_streamer_index,
    percentage,
)


def streamer(channel_id):
    return SimpleNamespace(channel_id=channel_id)


def test_get_streamer_index_finds_by_string_or_int_channel_id():
    streamers = [streamer(111), streamer("222"), streamer(333)]

    assert get_streamer_index(streamers, 222) == 1
    assert get_streamer_index(streamers, "333") == 2


def test_get_streamer_index_missing_returns_minus_one():
    assert get_streamer_index([streamer(111)], 999) == -1
    assert get_streamer_index([], 111) == -1


def test_percentage():
    assert percentage(50, 200) == 25
    assert percentage(1, 3) == 33  # truncates, does not round


def test_percentage_zero_denominator_does_not_raise():
    assert percentage(10, 0) == 0


def test_float_round():
    assert float_round(1.23456) == 1.23
    assert float_round(1.23456, ndigits=4) == 1.2346
    assert float_round("2.5") == 2.5


def test_create_chunks():
    assert create_chunks([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    assert create_chunks([], 3) == []
    assert create_chunks([1, 2], 10) == [[1, 2]]


def test_at_least_one_value_in_settings_is_true():
    items = [
        SimpleNamespace(settings=SimpleNamespace(claim_drops=False)),
        SimpleNamespace(settings=SimpleNamespace(claim_drops=True)),
    ]
    assert at_least_one_value_in_settings_is(items, "claim_drops") is True


def test_at_least_one_value_in_settings_is_false():
    items = [
        SimpleNamespace(settings=SimpleNamespace(claim_drops=False)),
        SimpleNamespace(settings=SimpleNamespace(claim_drops=False)),
    ]
    assert at_least_one_value_in_settings_is(items, "claim_drops") is False


def test_at_least_one_value_in_settings_is_empty_list_is_false():
    assert at_least_one_value_in_settings_is([], "claim_drops") is False
