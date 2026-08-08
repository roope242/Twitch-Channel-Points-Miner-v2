"""Tests for the analytics dashboard's JSON route.

`AnalyticsServer.__init__` calls `check_assets()`, which copies the packaged
dashboard files into the *working directory*, so every test here runs from a
tmp_path rather than the repo root.
"""

import json
import time

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


def test_point_with_no_x_reports_error_instead_of_500(client):
    """A hand-trimmed series can leave a point with no `x` -- `df.x` raises AttributeError."""
    client.write_analytics("streamer", {"series": [{"y": 4000}], "annotations": []})

    response = client.get("/json/streamer")

    assert response.status_code == 500
    body = json.loads(response.data)
    assert "streamer.json" in body["error"]


def test_series_as_dict_reports_error_instead_of_500(client):
    """`series` as a dict makes `pd.DataFrame` raise ValueError, not build columns."""
    client.write_analytics("streamer", {"series": {"a": 1, "b": 2}, "annotations": []})

    response = client.get("/json/streamer")

    assert response.status_code == 500
    body = json.loads(response.data)
    assert "streamer.json" in body["error"]


def test_series_as_number_reports_error_instead_of_500(client):
    client.write_analytics("streamer", {"series": 5, "annotations": []})

    response = client.get("/json/streamer")

    assert response.status_code == 500
    body = json.loads(response.data)
    assert "streamer.json" in body["error"]


def test_top_level_array_reports_error_instead_of_500(client):
    """A bare JSON array at the top level has no `.get`, unlike the expected dict."""
    client.write_analytics("streamer", [{"series": []}])

    response = client.get("/json/streamer")

    assert response.status_code == 500
    body = json.loads(response.data)
    assert "streamer.json" in body["error"]


def test_annotation_with_no_x_reports_error_instead_of_500(client):
    client.write_analytics("streamer", {"series": SERIES, "annotations": [{"y": 0}]})

    response = client.get("/json/streamer")

    assert response.status_code == 500
    body = json.loads(response.data)
    assert "streamer.json" in body["error"]


def test_point_with_no_y_reports_error_instead_of_500(client):
    """A point missing `y` makes `sort_values(by=["x", "y"])` raise KeyError."""
    client.write_analytics(
        "streamer",
        {"series": [{"x": 1785170438000, "z": "Watch"}], "annotations": []},
    )

    response = client.get("/json/streamer")

    assert response.status_code == 500
    body = json.loads(response.data)
    assert "streamer.json" in body["error"]


def test_point_with_string_x_reports_error_instead_of_500(client):
    """A timestamp left as a string makes `df.x // 1000` raise TypeError."""
    client.write_analytics(
        "streamer",
        {"series": [{"x": "abc", "y": 1, "z": "W"}], "annotations": []},
    )

    response = client.get("/json/streamer")

    assert response.status_code == 500
    body = json.loads(response.data)
    assert "streamer.json" in body["error"]


def test_bad_date_param_is_not_reported_as_a_malformed_file(client):
    """A bad `?startDate=` must not be misdiagnosed as a corrupt analytics file.

    `filter_datas` parses startDate/endDate before touching the file data, so this
    is a different failure than the malformed-shape cases above. It must not be
    caught by the "Error processing analytics data in file ..." guard -- Flask's
    TESTING mode propagates unhandled exceptions rather than turning them into a
    response, which is exactly the pre-existing (unchanged) behaviour this test
    pins: a plain, unguarded `ValueError`, not our file-naming error branch.
    """
    client.write_analytics("streamer", {"series": SERIES, "annotations": ANNOTATIONS})

    with pytest.raises(ValueError):
        client.get("/json/streamer?startDate=notadate")


@pytest.fixture
def east_of_utc(monkeypatch):
    """Pin a positive UTC offset so the date-overflow cases are reproducible.

    Whether `9999-12-31` overflows `.timestamp()` depends on the host's offset: it
    does east of UTC and does not in UTC itself, so these tests pass on a developer
    machine in Helsinki and fail in the container, which runs UTC. Pinning the zone
    is what makes them mean the same thing in both places.
    """
    monkeypatch.setenv("TZ", "Europe/Helsinki")
    time.tzset()
    yield
    # monkeypatch restores TZ, but tzset must be re-run for it to take effect.
    monkeypatch.undo()
    time.tzset()


@pytest.mark.parametrize("query", ["endDate=9999-12-31", "startDate=0001-01-01"])
def test_out_of_range_date_is_not_reported_as_a_malformed_file(
    client, east_of_utc, query
):
    """A date that parses but overflows `.timestamp()` is still a date problem.

    `9999-12-31` becomes year 10000 once `filter_datas` pushes it to end-of-day and
    converts to a local timestamp; `0001-01-01` underflows the same way. Checking
    only the format lets both through to the malformed-data guard, which then names
    a perfectly healthy file as the culprit.
    """
    client.write_analytics("streamer", {"series": SERIES, "annotations": ANNOTATIONS})

    with pytest.raises(ValueError):
        client.get(f"/json/streamer?{query}")


@pytest.mark.parametrize("query", ["endDate=9999-12-31", "startDate=0001-01-01"])
def test_out_of_range_date_does_not_silently_zero_the_streamers_list(
    client, east_of_utc, query
):
    """The worse half of the same bug: `/streamers` would answer 200 with zeros.

    A healthy streamer reported as `points: 0` is a wrong number presented as a
    right one, which is worse than the failure it replaced.
    """
    client.write_analytics("streamer", {"series": SERIES, "annotations": ANNOTATIONS})

    with pytest.raises(ValueError):
        client.get(f"/streamers?{query}")


def test_streamers_list_survives_a_malformed_file(client):
    client.write_analytics("healthy", {"series": SERIES, "annotations": ANNOTATIONS})
    client.write_analytics("broken", {"series": [{"y": 4000}], "annotations": []})

    response = client.get("/streamers")

    assert response.status_code == 200
    listed = {entry["name"]: entry for entry in json.loads(response.data)}
    assert listed["broken.json"]["points"] == 0
    assert listed["healthy.json"]["points"] == 473082


def test_json_all_survives_a_malformed_file(client):
    client.write_analytics("healthy", {"series": SERIES, "annotations": ANNOTATIONS})
    client.write_analytics("broken", {"series": [{"y": 4000}], "annotations": []})

    response = client.get("/json_all")

    assert response.status_code == 200
    bundled = {entry["name"]: entry["data"] for entry in json.loads(response.data)}
    assert "error" in bundled["broken"]
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
