from urllib.parse import quote

import requests

from TwitchChannelPointsMiner.classes.Settings import Events
from TwitchChannelPointsMiner.constants import REQUESTS_TIMEOUT


class Webhook(object):
    __slots__ = ["endpoint", "method", "events"]

    def __init__(self, endpoint: str, method: str, events: list):
        self.endpoint = endpoint
        self.method = method
        self.events = [str(e) for e in events]

    def send(self, message: str, event: Events) -> None:

        if str(event) in self.events:
            # message can be a chat line written by any viewer, so it must not be
            # able to add or terminate query parameters. safe="" also encodes "/".
            url = (
                self.endpoint
                + f"?event_name={quote(str(event), safe='')}"
                + f"&message={quote(message, safe='')}"
            )

            if self.method.lower() == "get":
                requests.get(url=url, timeout=REQUESTS_TIMEOUT)
            elif self.method.lower() == "post":
                requests.post(url=url, timeout=REQUESTS_TIMEOUT)
            else:
                raise ValueError("Invalid method, use POST or GET")
