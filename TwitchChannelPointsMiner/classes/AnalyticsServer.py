import hashlib
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from threading import Thread

import pandas as pd
from flask import Flask, Response, cli, render_template, request

from TwitchChannelPointsMiner.classes.Settings import Settings

cli.show_server_banner = lambda *_: None
logger = logging.getLogger(__name__)


def streamers_available():
    path = Settings.analytics_path
    return [
        f
        for f in os.listdir(path)
        if os.path.isfile(os.path.join(path, f)) and f.endswith(".json")
    ]


def aggregate(df, freq="30Min"):
    df_base_events = df[(df.z == "Watch") | (df.z == "Claim")]
    df_other_events = df[(df.z != "Watch") & (df.z != "Claim")]

    be = df_base_events.groupby(
        [pd.Grouper(freq=freq, key="datetime"), "z"]).max()
    be = be.reset_index()

    oe = df_other_events.groupby(
        [pd.Grouper(freq=freq, key="datetime"), "z"]).max()
    oe = oe.reset_index()

    result = pd.concat([be, oe])
    return result


def filter_datas(start_date, end_date, datas):
    # Note: https://stackoverflow.com/questions/4676195/why-do-i-need-to-multiply-unix-timestamps-by-1000-in-javascript
    start_date = (
        datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000
        if start_date is not None
        else 0
    )
    end_date = (
        datetime.strptime(end_date, "%Y-%m-%d")
        if end_date is not None
        else datetime.now()
    ).replace(hour=23, minute=59, second=59).timestamp() * 1000

    # `or []` rather than a default: the key can be present and null, which the
    # two-argument form passes straight through to `len()` below.
    original_series = datas.get("series") or []

    # Truthiness, not membership: an empty list builds a column-less DataFrame,
    # so `df.x` below raises AttributeError and the route 500s.
    if datas.get("series"):
        df = pd.DataFrame(datas["series"])
        df["datetime"] = pd.to_datetime(df.x // 1000, unit="s")

        df = df[(df.x >= start_date) & (df.x <= end_date)]

        datas["series"] = (
            df.drop(columns="datetime")
            .sort_values(by=["x", "y"], ascending=True)
            .to_dict("records")
        )
    else:
        datas["series"] = []

    # If no data is found within the timeframe, that usually means the streamer hasn't streamed within that timeframe
    # We create a series that shows up as a straight line on the dashboard, with 'No Stream' as labels
    if len(datas["series"]) == 0 and len(original_series) > 0:
        new_end_date = start_date
        new_start_date = 0
        df = pd.DataFrame(original_series)
        df["datetime"] = pd.to_datetime(df.x // 1000, unit="s")

        # Attempt to get the last known balance from before the provided timeframe
        df = df[(df.x >= new_start_date) & (df.x <= new_end_date)]
        records = df.drop(columns="datetime").sort_values(
            by=["x", "y"], ascending=True).to_dict("records")

        if records:
            last_balance = records[-1]['y']
            datas["series"] = [{'x': start_date, 'y': last_balance, 'z': 'No Stream'}, {
                'x': end_date, 'y': last_balance, 'z': 'No Stream'}]

    if datas.get("annotations"):
        df = pd.DataFrame(datas["annotations"])
        df["datetime"] = pd.to_datetime(df.x // 1000, unit="s")

        df = df[(df.x >= start_date) & (df.x <= end_date)]

        datas["annotations"] = (
            df.drop(columns="datetime")
            .sort_values(by="x", ascending=True)
            .to_dict("records")
        )
    else:
        datas["annotations"] = []

    return datas


def read_json(streamer, return_response=True):
    start_date = request.args.get("startDate", type=str)
    end_date = request.args.get("endDate", type=str)

    path = Settings.analytics_path
    streamer = streamer if streamer.endswith(".json") else f"{streamer}.json"

    # Check if the file exists before attempting to read it
    if not os.path.exists(os.path.join(path, streamer)):
        error_message = f"File '{streamer}' not found."
        logger.error(error_message)
        if return_response:
            return Response(json.dumps({"error": error_message}), status=404, mimetype="application/json")
        else:
            return {"error": error_message}

    try:
        with open(os.path.join(path, streamer), 'r') as file:
            data = json.load(file)
    except json.JSONDecodeError as e:
        error_message = f"Error decoding JSON in file '{streamer}': {str(e)}"
        logger.error(error_message)
        if return_response:
            return Response(json.dumps({"error": error_message}), status=500, mimetype="application/json")
        else:
            return {"error": error_message}

    # Handle filtering data, if applicable
    filtered_data = filter_datas(start_date, end_date, data)
    if return_response:
        return Response(json.dumps(filtered_data), status=200, mimetype="application/json")
    else:
        return filtered_data


def get_challenge_points(streamer):
    datas = read_json(streamer, return_response=False)
    if "series" in datas and datas["series"]:
        return datas["series"][-1]["y"]
    return 0  # Default value when 'series' key is not found or empty


def get_last_activity(streamer):
    datas = read_json(streamer, return_response=False)
    if "series" in datas and datas["series"]:
        return datas["series"][-1]["x"]
    return 0  # Default value when 'series' key is not found or empty


def json_all():
    return Response(
        json.dumps(
            [
                {
                    "name": streamer.removesuffix(".json"),
                    "data": read_json(streamer, return_response=False),
                }
                for streamer in streamers_available()
            ]
        ),
        status=200,
        mimetype="application/json",
    )


def index(refresh=5, days_ago=7):
    return render_template(
        "charts.html",
        refresh=(refresh * 60 * 1000),
        daysAgo=days_ago,
    )


def streamers():
    return Response(
        json.dumps(
            [
                {"name": s, "points": get_challenge_points(
                    s), "last_activity": get_last_activity(s)}
                for s in sorted(streamers_available())
            ]
        ),
        status=200,
        mimetype="application/json",
    )


def _sha256(fpath):
    with open(fpath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_assets():
    required_files = [
        "banner.png",
        "charts.html",
        "script.js",
        "style.css",
        "dark-theme.css",
    ]
    # Packaged assets ship inside the package so they stay in sync with this
    # install, instead of being fetched from upstream's GitHub (which would
    # overwrite fork-local changes such as the refresh-followers button).
    packaged_folder = os.path.join(os.path.dirname(__file__), "..", "assets")
    assets_folder = os.path.join(Path().absolute(), "assets")
    Path(assets_folder).mkdir(parents=True, exist_ok=True)

    for f in required_files:
        src = os.path.join(packaged_folder, f)
        dst = os.path.join(assets_folder, f)

        if os.path.isfile(dst) is False:
            shutil.copyfile(src, dst)
            logger.info(f"Installed {f} in {assets_folder}")
        elif _sha256(src) != _sha256(dst):
            shutil.copyfile(src, dst)
            logger.warning(
                f"{f} in {assets_folder} differed from the packaged version "
                "and was replaced. If you customised it, your changes were overwritten."
            )

last_sent_log_index = 0

class AnalyticsServer(Thread):
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5000,
        refresh: int = 5,
        days_ago: int = 7,
        username: str = None,
        refresh_followers=None,
    ):
        super(AnalyticsServer, self).__init__()

        check_assets()

        self.host = host
        self.port = port
        self.refresh = refresh
        self.days_ago = days_ago
        self.username = username

        def trigger_followers_refresh():
            if refresh_followers is None:
                return Response(
                    json.dumps({"error": "Followers refresh is not available."}),
                    status=503,
                    mimetype="application/json",
                )

            success, message = refresh_followers()
            if success is True:
                return Response(
                    json.dumps({"status": message}),
                    status=202,
                    mimetype="application/json",
                )
            else:
                return Response(
                    json.dumps({"error": message}),
                    status=409,
                    mimetype="application/json",
                )

        def generate_log():
            global last_sent_log_index  # Use the global variable

            # Get the last received log index from the client request parameters
            last_received_index = int(request.args.get("lastIndex", last_sent_log_index))

            logs_path = os.path.join(Path().absolute(), "logs")
            log_file_path = os.path.join(logs_path, f"{username}.log")
            try:
                with open(log_file_path, "r", encoding="utf-8") as log_file:
                    log_content = log_file.read()

                # Extract new log entries since the last received index
                new_log_entries = log_content[last_received_index:]
                last_sent_log_index = len(log_content)  # Update the last sent index

                return Response(new_log_entries, status=200, mimetype="text/plain")

            except FileNotFoundError:
                return Response("Log file not found.", status=404, mimetype="text/plain")

        self.app = Flask(
            __name__,
            template_folder=os.path.join(Path().absolute(), "assets"),
            static_folder=os.path.join(Path().absolute(), "assets"),
        )
        self.app.add_url_rule(
            "/",
            "index",
            index,
            defaults={"refresh": refresh, "days_ago": days_ago},
            methods=["GET"],
        )
        self.app.add_url_rule("/streamers", "streamers",
                              streamers, methods=["GET"])
        self.app.add_url_rule(
            "/json/<string:streamer>", "json", read_json, methods=["GET"]
        )
        self.app.add_url_rule("/json_all", "json_all",
                              json_all, methods=["GET"])
        self.app.add_url_rule(
            "/log", "log", generate_log, methods=["GET"])
        self.app.add_url_rule(
            "/refresh_followers",
            "refresh_followers",
            trigger_followers_refresh,
            methods=["POST"],
        )

    def run(self):
        logger.info(
            f"Analytics running on http://{self.host}:{self.port}/",
            extra={"emoji": ":globe_with_meridians:"},
        )
        self.app.run(host=self.host, port=self.port,
                     threaded=True, debug=False)
