# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Twitch channel-points miner: it logs into Twitch as a user, keeps "watching" streams to accrue
points, claims bonuses/drops/moments, and optionally places predictions. It is a long-running
daemon driven by Twitch's private GraphQL API and PubSub WebSocket — there is no public API and no
official support for any of it.

Lineage: `Tkd-Alex/Twitch-Channel-Points-Miner-v2` (original) → `rdavydov/...` (the active
upstream this repo tracks). GPLv3.

## Running and developing

There is **no test suite** and no build step. The package is a library; users write their own
entry script:

```bash
cp example.py run.py          # run.py is gitignored — it holds the user's config and username
python run.py                 # first run prints a device code to activate at twitch.tv/activate
```

Nothing runs without live Twitch auth, so the only local check on a change is
`python3 -m py_compile <changed files>`. `flask` and `pandas` are not installed in the dev
environment — the analytics server cannot be exercised locally.

`example.py` is the canonical documentation of the public surface: every constructor option of
`TwitchChannelPointsMiner`, `LoggerSettings`, `StreamerSettings`, and `BetSettings` appears there
with a comment. **Any new user-facing option must be added to `example.py` and `README.md`** — that
is how the project documents itself.

Linting is via pre-commit, scoped to `TwitchChannelPointsMiner/` only (black, isort with the black
profile, flake8 `--max-line-length=88 --extend-ignore=E501`). It is not installed by default:

```bash
python3 -m venv .venv && .venv/bin/pip install pre-commit   # not installed in this environment
.venv/bin/pre-commit run --all-files
```

The repo is **not** uniformly black-formatted despite the hook — large parts of `Twitch.py`,
`AnalyticsServer.py`, and `TwitchChannelPointsMiner.py` predate it. Write new code black-clean, but
do not reformat whole files: it destroys diff reviewability for no benefit.

Docker: `Dockerfile` has `ENTRYPOINT ["python", "run.py"]` and expects `run.py` mounted as a volume.

## Architecture

### Entry point and lifecycle

`TwitchChannelPointsMiner.run()` (in `TwitchChannelPointsMiner/TwitchChannelPointsMiner.py`) is the
whole lifecycle in one method: login → resolve streamers → prime points/online state → spawn
threads → subscribe PubSub topics → supervise loop. `mine()` is a thin alias. Reading this one
method tells you most of what the program does.

### Concurrency model

State lives in one process across several threads, with **no locking** on the shared streamer list:

| Thread | Started by | Does |
|---|---|---|
| Main loop | `run()` | WebSocket liveness checks, periodic points-context refresh, followers refresh |
| Minute watcher | `run()` | Sends `minute-watched` events; picks up to 2 streamers by `priority` |
| WebSocket #N | `WebSocketsPool.__start` | PubSub receive → mutates streamers, claims bonuses, places bets |
| Sync campaigns | `run()`, if any streamer has `claim_drops` | Drops/inventory sync |
| Analytics (Flask) | `analytics()`, if `enable_analytics=True` | Dashboard + JSON endpoints |
| Chat (IRC) | per-streamer `ThreadChat` | Joined lazily when the streamer goes online |

The rule that keeps this safe: **mutate `self.streamers` only from the main thread.** Other threads
signal intent (e.g. the analytics server sets `refresh_followers_requested`, a `threading.Event`
the main loop consumes) rather than touching the list. Follow this pattern for anything new that
adds or removes streamers.

`self.streamers` is passed **by reference** into `WebSocketsPool`, which passes the same list object
into every `TwitchWebSocket`. Appending to it is visible everywhere; rebinding it would silently
break the WebSocket handlers.

`self.streamers` and `self.original_streamers` are **index-parallel** — `__print_report()` matches
them up by index to compute points gained. `__add_streamer_to_session()` is the single place that
appends to both; keep it that way.

### Twitch API layer

`classes/Twitch.py` (~1000 lines) is every GraphQL call, funnelled through `post_gql_request()`.
The persisted-query `sha256Hash` values live in `constants.GQLOperations`. **These hashes are the
main source of breakage**: Twitch rotates them and the queries start returning errors — much of the
recent commit history is exactly this kind of fix. When something suddenly stops working against
live Twitch, suspect a stale hash or a changed request field before suspecting the logic.

`post_gql_request()` returns `{}` on any request failure, so callers must guard
`response["data"]` instead of indexing straight into it — several still don't.

`constants.py` also holds spoofed `CLIENT_ID`/`CLIENT_VERSION`/user-agent values (TV app client id
by default, with browser/mobile/Android alternatives commented out).

Auth is the OAuth **device-code flow** in `classes/TwitchLogin.py` (`login_flow()`, with
`login_flow_backup()` as a password fallback). Session cookies are pickled to
`cookies/<username>.pkl`; a stale one surfaces as `ERR_BADAUTH` on the WebSocket, and the fix is
deleting that file.

### PubSub

`WebSocketsPool` opens a new connection every 50 topics (Twitch's per-connection limit) and handles
reconnection by rebuilding the socket at the same array index and replaying `ws.topics`.
`TwitchWebSocket` implements `listen()` only — **there is no `UNLISTEN`**, so a topic subscribed
during a session cannot currently be dropped. This is the blocker for removing streamers mid-session.

`WebSocketsPool.on_message` is a large dispatch on `message.topic`; it resolves the streamer by
channel id via `get_streamer_index()` each time, so it tolerates the list growing.

The whole dispatch sits inside one `except Exception` that only logs. A typo or a call to a
method that doesn't exist surfaces as a single error line and nothing else — read this
handler skeptically and don't trust "no crash" as evidence a branch works.

### Settings

`classes/Settings.py` `Settings` is a namespace used as a global singleton — never instantiated,
attributes assigned directly on the class (`Settings.logger = ...`). Per-streamer settings cascade:
`StreamerSettings` defaults come from `Settings.streamer_settings` via `set_default_settings()`,
applied in `__setup_streamer()`.

The `Events` enum is the routing key for notifications: every `logger.info(..., extra={"event":
Events.X})` can be forwarded to Telegram/Discord/Webhook/Matrix/Pushover/Gotify depending on which
events the user listed in `LoggerSettings`. Adding a loggable event type means adding to `Events`.

### Analytics dashboard

`classes/AnalyticsServer.py` is a Flask app in a daemon thread, serving `assets/` (charts.html,
script.js, style.css…) with per-streamer JSON series read from `analytics/<username>/*.json`.

**Gotcha:** `check_assets()` only downloads asset files from GitHub `master` when they are
*missing*. Editing `assets/*` in this repo does not reach users who already have an `assets/`
folder — they must delete the stale files. Say so in the README when changing dashboard assets.

The server is unauthenticated and defaults to binding `127.0.0.1`. It now has one state-changing
route (`POST /refresh_followers`); keep that in mind before adding more.

## Conventions

- Explicit identity comparisons — `if x is True:` / `is False:` — throughout. Match it.
- `__slots__` on nearly every class, including the miner itself. **New instance attributes must be
  added to `__slots__`** or assignment raises `AttributeError` at runtime.
- Logging carries `extra={"emoji": ":rocket:", "event": Events.X}`; the emoji/colour handling lives
  in `logger.py`.
- Name-mangled `__private` methods for internals on the miner and pool classes.
- Runtime output directories (`cookies/`, `logs/`, `analytics/`) and `run.py` are all gitignored.
- **This fork's Python floor is 3.9**, upstream's is still 3.6. The only thing raising it is
  `str.removesuffix()` in `AnalyticsServer.json_all`, added here. So a fix cherry-picked upstream
  must either avoid `removesuffix` or bump `python_requires` there too. (`self.streamers:
  list[Streamer]` is annotation-only — never evaluated at runtime, verified on 3.8 — so it does
  *not* raise the floor.) Docker uses 3.10.

## Sending fixes upstream

`origin` is the `roope242` fork; its parent is `rdavydov/...`, whose parent is
`Tkd-Alex/...`. This `CLAUDE.md` exists only on the fork — **never open an upstream PR from
`master`**, it would carry the file along. Branch off `upstream/master`, cherry-pick the fix
commits, and open it cross-fork:

```bash
git remote add upstream https://github.com/rdavydov/Twitch-Channel-Points-Miner-v2.git  # once
git fetch upstream && git checkout -b <branch> upstream/master
git cherry-pick <sha>
gh pr create --repo rdavydov/Twitch-Channel-Points-Miner-v2 --base master --head roope242:<branch>
```
