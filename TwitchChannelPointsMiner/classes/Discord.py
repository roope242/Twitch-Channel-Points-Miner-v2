from textwrap import dedent

import requests

from TwitchChannelPointsMiner.classes.Settings import Events
from TwitchChannelPointsMiner.constants import REQUESTS_TIMEOUT


class Discord(object):
    __slots__ = ["webhook_api", "events"]

    def __init__(self, webhook_api: str, events: list):
        self.webhook_api = webhook_api
        self.events = [str(e) for e in events]

    def send(self, message: str, event: Events) -> None:
        if str(event) in self.events:
            # json=, not data=: form encoding flattens the nested allowed_mentions
            # object to "allowed_mentions=parse", which Discord ignores.
            requests.post(
                url=self.webhook_api,
                json={
                    "content": dedent(message),
                    "username": "Twitch Channel Points Miner",
                    "avatar_url": "https://i.imgur.com/X9fEkhT.png",
                    # message can be a chat line written by any viewer, so a bare
                    # @everyone in it must not fire a real mention.
                    "allowed_mentions": {"parse": []},
                },
                timeout=REQUESTS_TIMEOUT,
            )
