# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Starting a session? Read `ISSUES.md` first.** It is the handoff document: what is in flight and
at which commit, what to do next and why, what every closed issue taught, and the PR/review
workflow. Its "Start here" section lists the first actions of a session — including re-triggering
any CodeRabbit review that a quota block stopped the day before. Update its "Start here" and
"In flight" sections before a session ends.

`scripts/cr-wait.sh <pr>` is the only reliable way to detect a CodeRabbit verdict: it submits no
formal review, so `gh api .../pulls/N/reviews` is always empty, and it edits comments in place —
deleting text as well as adding it. Do not improvise a poll; see `ISSUES.md` "Start here".

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

Nothing *mines* without live Twitch auth, but more is testable offline than it looks. Beyond
`python3 -m py_compile <changed files>`: login happens in `run()`, not `__init__`, so
`TwitchChannelPointsMiner(username="…", logger_settings=LoggerSettings(save=False,
console_level=logging.CRITICAL))` constructs offline — enough to exercise `end()`, the signal
handlers and anything in `utils.py` for real. `__slots__` blocks monkeypatching methods on it
(`AttributeError: … is read-only`), so drive it through real calls rather than stubs. Do this:
`py_compile` and a bare `import` both passed on an `end()` that crashed on the first line it
reached.

Dashboard JS is testable offline too — `node` and `npm` are on this host. `npm install jsdom
jquery@3.5.1` (match the version `charts.html` pins) in a scratch dir, load the real jQuery into
a jsdom document with `w.eval(jquerySource)`, and assert on the DOM. This gave a decisive
before/after on the #12 XSS fix: `.append(string)` created a live `<img onerror=…>`, the text-node
version created none. Caveat: jsdom does not fire `onerror`/`onload`, so assert on element
creation and attributes, not on handler execution.

Driving `script.js` itself needs stubs for `daysAgo`, an `ApexCharts` class, and
`Element.prototype.scrollIntoView`/`window.alert`, which jsdom does not implement. The trap:
**install any `setTimeout` stub *after* `w.eval(jquerySource)`** — jQuery schedules its own ready
callback through `setTimeout`, so stubbing first silently stops every `$(document).ready` handler
from running while unrelated assertions still pass. Assert that ready ran. Exceptions inside
`renderStreamers`'s Promise executor are swallowed into a rejection, surfacing only as an unhandled
rejection after the run.

A live run *is* available: `.venv` has every dependency
(Python 3.14), `run.py` is configured, and `cookies/roope242.pkl` skips the device-code step —
so `.venv/bin/python -u run.py` mines for real. Use `-u`; stdout is block-buffered otherwise
and you see nothing. Priming ~74 followers takes ~2 minutes before the main loop starts.
The minute watcher only watches the top 2 streamers by priority, so a newly added streamer is
usually subscribed but *not* watched — don't read that as a bug.

`example.py` is the canonical documentation of the public surface: every constructor option of
`TwitchChannelPointsMiner`, `LoggerSettings`, `StreamerSettings`, and `BetSettings` appears there
with a comment. **Any new user-facing option must be added to `example.py` and `README.md`** — that
is how the project documents itself.

Linting is via pre-commit, scoped to `TwitchChannelPointsMiner/` only (black, isort with the black
profile, flake8 `--max-line-length=88 --extend-ignore=E501`). It is not installed by default:

```bash
python3 -m venv .venv && .venv/bin/pip install pre-commit   # not installed in this environment
# black is already in .venv; isort is NOT -- install it or the import-ordering half silently no-ops
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

All worker threads are `daemon=True` (since #14) so a stuck one cannot block interpreter exit —
`sys.exit(0)` only raises on the main thread, and Python waits on non-daemon threads before the
process ends. `end()` bounds every join and the mutex wait with `SHUTDOWN_JOIN_TIMEOUT`, warns,
and continues; it guards re-entry on `shutting_down`, not `running`. New threads must follow
both. SIGSEGV is deliberately not handled.

`Streamer.leave_chat()` stops the current `ThreadChat` and **rebinds `streamer.irc_chat` to a
fresh, unstarted one**. Anything inspecting or joining the running chat thread must capture it
*before* that call — `is_alive()` on the replacement is always `False`.

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
Upstream's tracker confirms it fastest — a rotation produces a burst of `KeyError: 'data'` reports
there within days: `gh issue list --repo rdavydov/Twitch-Channel-Points-Miner-v2 --search KeyError`.

`post_gql_request()` returns `{}` both on request failure and — since `e708b20` — when Twitch
answers HTTP 200 with an error body (no `data`, or `data: null`), logging the operation name.
So `if response != {}` is now a real guard, and a rotated hash is visible in the log rather than
silent. Keep using that idiom for new callers.
**It can also return a list**: `__get_campaigns_details` posts a list of operations and gets a
list back, so the sanitization only applies to dict responses. Any change here must preserve that.

`update_client_version()` is called inline in `post_gql_request`'s headers, but since the fix for
issue #9 it caches behind a 30-minute TTL (`CLIENT_VERSION_TTL`) and its fetch has `timeout=20`.
Before that every GQL call first fetched and regexed the whole twitch.tv page, so each request was
really two. Measured on the same host, same 74 followers: 294 page fetches in a 13-minute run
before, 1 in a 3-minute run after. Only a *successful* fetch+match advances the timestamp, so a
failure retries on the next call rather than being cached; failures still serve the previous value.

Every live HTTP call passes `timeout=REQUESTS_TIMEOUT` (`constants.py`) since #6 — verify new
ones with an AST scan rather than grep, since multi-line calls hide from `grep`. Note `requests`
applies the timeout *per connection attempt*, so N DNS addresses means N × timeout: on a host
with blackholed IPv6, `raw.githubusercontent.com` (4 AAAA) takes ~40s even with `timeout=10`.
That is why the GitHub version check runs on a daemon thread rather than in `__init__`.

Guarded is not the same as loud: `get_followers()` returns `[]` and `get_channel_id()` raises
`StreamerDoesNotExistException` on *any* failure. A transient error during a followers refresh
therefore reads as "0 new streamers" or "that streamer does not exist", not as an error.

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

Those notifiers are called **synchronously inside the log formatter**, on the single
`QueueListener` thread draining every log record. One hung notification stops all logging,
console and file, while mining continues — issue #7, and probably upstream's #805.

### Analytics dashboard

`classes/AnalyticsServer.py` is a Flask app in a daemon thread, serving `assets/` (charts.html,
script.js, style.css…) with per-streamer JSON series read from `analytics/<username>/*.json`.

Assets have two locations and this trips people up. The **source** files live in
`TwitchChannelPointsMiner/assets/` and ship with the package; edit those. Flask serves the
**working-directory** `assets/`, which `check_assets()` populates on startup by copying the
packaged files in and overwriting any whose sha256 differs. So an asset edit reaches existing
installs on the next start — no README warning needed, and nothing is fetched over the network
(#4, PR #20). The three README screenshots stay in the repo-root `assets/`.

The server is unauthenticated and defaults to binding `127.0.0.1`. It now has one state-changing
route (`POST /refresh_followers`); keep that in mind before adding more.

`charts.html` pins its CDN includes with sha512 SRI. Regenerate with python `hashlib` — **`openssl`
is not installed here** — and cross-check against `api.cdnjs.com/libraries/<lib>/<ver>?fields=sri`
or `data.jsdelivr.com/v1/packages/npm/<pkg>` before committing.

## Conventions

- Explicit identity comparisons — `if x is True:` / `is False:` — throughout. Match it.
- `__slots__` on nearly every class, including the miner itself. **New instance attributes must be
  added to `__slots__`** or assignment raises `AttributeError` at runtime.
- Logging carries `extra={"emoji": ":rocket:", "event": Events.X}`; the emoji/colour handling lives
  in `logger.py`.
- Name-mangled `__private` methods for internals on the miner and pool classes.
- Runtime output directories (`cookies/`, `logs/`, `analytics/`) and `run.py` are all gitignored.
- **This fork's Python floor is 3.9**, upstream's is still 3.6. The only thing raising it is
  `str.removesuffix()` in `AnalyticsServer.json_all`, added here. Don't contort new code to keep
  EOL interpreters working: a fix cherry-picked upstream keeps `removesuffix` and bumps
  `python_requires` there too, called out explicitly in the PR. (`self.streamers:
  list[Streamer]` is annotation-only — never evaluated at runtime, verified on 3.8 — so it does
  *not* raise the floor.) Docker uses 3.10.

## Sending fixes upstream

`origin` is the `roope242` fork; its parent is `rdavydov/...`, whose parent is
`Tkd-Alex/...`. `CLAUDE.md`, `ISSUES.md` (fork-local triage and fix order) and
`.coderabbit.yaml` exist only on the fork — **never open an upstream PR from `master`**, it
would carry them along. Branch off `upstream/master`, cherry-pick the fix
commits, and open it cross-fork:

```bash
git remote add upstream https://github.com/rdavydov/Twitch-Channel-Points-Miner-v2.git  # once
git fetch upstream && git checkout -b <branch> upstream/master
git cherry-pick <sha>
gh pr create --repo rdavydov/Twitch-Channel-Points-Miner-v2 --base master --head roope242:<branch>
```

Fork PR bodies must state the code was written by an AI agent. **Upstream PR bodies must not raise
it** — omit, never misrepresent, since some maintainers reject AI-authored PRs on sight. The
`Co-Authored-By: Claude` commit trailers ride along on cherry-picks and are deliberately left.
