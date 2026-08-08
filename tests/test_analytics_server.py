"""Tests for the analytics dashboard's JSON route.

`AnalyticsServer.__init__` calls `check_assets()`, which copies the packaged
dashboard files into the *working directory*, so every test here runs from a
tmp_path rather than the repo root.
"""

import json

import pytest

from TwitchChannelPointsMiner.classes.AnalyticsServer import AnalyticsServer
from TwitchChannelPointsMiner.classes.Settings import Settings

# Two points a day apart, so a date filter can select one of them.
SERIES = [
    {"x": 1785170438000, "y": 473072, "z": "Watch"},
    {"x": 1785256838000, "y": 473082, "z": "Claim"},
]
ANNOTATIONS = [{"x": 1785170438000, "y": 0, "z": "Started"}]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    analytics_path = tmp_path / "analytics"
    analytics_path.mkdir()
    monkeypatch.setattr(Settings, "analytics_path", str(analytics_path), raising=False)

    server = AnalyticsServer(username="tester")
    server.app.config["TESTING"] = True

    def write(name, payload):
        (analytics_path / f"{name}.json").write_text(json.dumps(payload))

    test_client = server.app.test_client()
    test_client.write_analytics = write
    return test_client


def test_empty_series_renders_instead_of_500(client):
    client.write_analytics("streamer", {"series": [], "annotations": ANNOTATIONS})

    response = client.get("/json/streamer")

    assert response.status_code == 200
    assert json.loads(response.data)["series"] == []


def test_empty_annotations_renders_instead_of_500(client):
    client.write_analytics("streamer", {"series": SERIES, "annotations": []})

    response = client.get("/json/streamer")

    assert response.status_code == 200
    assert json.loads(response.data)["annotations"] == []


def test_both_lists_empty_renders_instead_of_500(client):
    client.write_analytics("streamer", {"series": [], "annotations": []})

    response = client.get("/json/streamer")

    assert response.status_code == 200
    body = json.loads(response.data)
    assert body["series"] == []
    assert body["annotations"] == []


def test_missing_keys_still_produce_empty_lists(client):
    """The path an empty list is being routed into -- it must keep working."""
    client.write_analytics("streamer", {})

    response = client.get("/json/streamer")

    assert response.status_code == 200
    assert json.loads(response.data) == {"series": [], "annotations": []}


def test_populated_file_is_unchanged(client):
    client.write_analytics("streamer", {"series": SERIES, "annotations": ANNOTATIONS})

    response = client.get("/json/streamer")

    assert response.status_code == 200
    body = json.loads(response.data)
    assert body["series"] == SERIES
    assert body["annotations"] == ANNOTATIONS


def test_null_lists_are_treated_as_empty(client):
    """`{"series": null}` is a plausible hand-edit and reaches `len()` unguarded."""
    client.write_analytics("streamer", {"series": None, "annotations": None})

    response = client.get("/json/streamer")

    assert response.status_code == 200
    assert json.loads(response.data) == {"series": [], "annotations": []}


def test_streamers_list_survives_an_empty_series(client):
    """`/streamers` reads the same files through `get_challenge_points`."""
    client.write_analytics("healthy", {"series": SERIES, "annotations": ANNOTATIONS})
    client.write_analytics("emptied", {"series": [], "annotations": []})

    response = client.get("/streamers")

    assert response.status_code == 200
    listed = {entry["name"]: entry for entry in json.loads(response.data)}
    assert listed["emptied.json"]["points"] == 0
    assert listed["healthy.json"]["points"] == 473082


def test_json_all_survives_an_empty_series(client):
    client.write_analytics("healthy", {"series": SERIES, "annotations": ANNOTATIONS})
    client.write_analytics("emptied", {"series": [], "annotations": []})

    response = client.get("/json_all")

    assert response.status_code == 200
    bundled = {entry["name"]: entry["data"] for entry in json.loads(response.data)}
    assert bundled["emptied"]["series"] == []
    assert bundled["healthy"]["series"] == SERIES


def test_no_stream_fallback_still_fires(client):
    """A date window past the last data point yields the straight-line filler.

    This is the one behaviour a truthiness guard could plausibly break, since it
    keys off `len(datas["series"]) == 0` after filtering.
    """
    client.write_analytics("streamer", {"series": SERIES, "annotations": ANNOTATIONS})

    response = client.get("/json/streamer?startDate=2026-08-01&endDate=2026-08-02")

    assert response.status_code == 200
    series = json.loads(response.data)["series"]
    assert [point["z"] for point in series] == ["No Stream", "No Stream"]
    assert {point["y"] for point in series} == {473082}
