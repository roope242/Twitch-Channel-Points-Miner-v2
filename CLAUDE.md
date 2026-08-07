# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Starting a session? Read `ISSUES.md` first.** It is the handoff document: what is in flight and
at which commit, what to do next and why, what every closed issue taught, and the PR/review
workflow. Update its "Start here" and "In flight" sections before a session ends.

**Code review is a fresh-context agent, not a service.** After pushing a branch and opening the
PR, spawn the `pr-reviewer` agent on the pushed head. It lives in the global agent directory
(`~/.claude/agents/pr-reviewer.md`) and carries no project knowledge of its own — it reads *this*
file for the traps, so anything a reviewer needs to know about this repo belongs here rather than
in the agent. Every finding must come with a concrete failure scenario. Details and rationale:
`ISSUES.md` "Standing workflow".

CodeRabbit's automatic PR reviews are **off** (`.coderabbit.yaml`, 2026-08-01); the GitHub App
stays installed for `@coderabbitai review` on a PR big enough to earn a third opinion. Detect its
verdict only with `scripts/cr-wait.sh <pr>`, run **unpiped** (`| tail` masks the exit code that is
its whole API: 0 verdict, 2 quota, 3 timeout). It submits no formal review — `pulls/N/reviews` is
always empty — and edits comments in place, so a chatty "Review finished" can sit alongside an
older, edited-in-place "couldn't start this review". Trust the script, not a comment.

## What this is

A Twitch channel-points miner: it logs into Twitch as a user, keeps "watching" streams to accrue
points, claims bonuses/drops/moments, and optionally places predictions. It is a long-running
daemon driven by Twitch's private GraphQL API and PubSub WebSocket — there is no public API and no
official support for any of it.

Lineage: `Tkd-Alex/Twitch-Channel-Points-Miner-v2` (original) → `rdavydov/...` (the active
upstream this repo tracks). GPLv3.

## Running and developing

There is a test suite (since #27) but no build step, and the suite covers a deliberately narrow
slice — everything provable without live Twitch auth. Run it before calling anything done:

```bash
.venv/bin/python -m pytest tests/ -q       # 51 tests (root conftest.py makes bare `pytest` work too)
scripts/test-container.sh                  # same suite in the image that ships: 50 + 1 skipped (#33)
(cd tests/js && npm ci && node --test)     # 21 jsdom assertions against the real script.js
```

(The jsdom line is parenthesised so the `cd` does not survive it — the block is meant to be
pasted whole from the repo root.)

All three run in CI on every PR and every push to `master` (`.github/workflows/tests.yml`, Python
3.9, 3.10 and 3.13, plus the container and jsdom legs). **Add to these rather than rebuilding a
throwaway harness** — the jsdom suite was rewritten from scratch three times before it was
committed, each time re-learning the same traps.

CI runs `python -m pytest tests/ -v`, module form, deliberately: the suite once passed locally
while CI collected nothing, because the `pytest` console script omits the repo root from
`sys.path`. For the teeth check, the jsdom suite scores 9/21 against pre-#21 `script.js`.

`scripts/test-container.sh` builds the `Dockerfile`'s **`test` stage** — the runtime image's exact
base and resolved `requirements.txt`, plus pytest — and runs the suite in it, so 3.10 is covered by
the environment that actually ships rather than only by a matrix entry. It picks podman or docker,
takes pytest arguments (`scripts/test-container.sh tests/test_utils.py -q`), and exits with
pytest's status. Two things about it that are load-bearing:

- **The `test` stage is deliberately not the last stage.** The last stage is what a bare
  `docker build .` produces and what `deploy-docker.yml` publishes, so it has to stay `runtime`.
  A CI step asserts the default target's entrypoint is still `python run.py` and that pytest is
  absent from it — reordering the stages would otherwise silently publish an image carrying the
  test suite.
- **`.dockerignore` excludes `tests/` and `conftest.py` and then re-admits them at the bottom**,
  since the last matching pattern wins. They reach the builder but not the published image, which
  is still 324 MB and contains only `TwitchChannelPointsMiner/` and `requirements.txt`.

One test skips in the container and not on the host: `test_login_propagates_permission_error_…`
chmods a file to `000`, and the image runs as root (no `USER` directive), which ignores permission
bits. The test's own guard handles it. That is correct fidelity, not a coverage hole — the
scenario cannot occur in the shipped environment.

The package is a library; users write their own entry script:

```bash
cp example.py run.py          # run.py is gitignored — it holds the user's config and username
python run.py                 # first run prints a device code to activate at twitch.tv/activate
```

Nothing *mines* without live Twitch auth, but more is testable offline than it looks. Beyond
`python3 -m py_compile <changed files>`: login happens in `run()`, not `__init__`, so
`TwitchChannelPointsMiner(username="…", logger_settings=LoggerSettings(save=False,
console_level=logging.CRITICAL))` constructs without authenticating — enough to exercise `end()`,
the signal handlers and anything in `utils.py` for real. **It is not offline, though:** `__init__`
loops `while not is_connected()` on `socket.gethostbyname("twitch.tv")` forever, 5s at a time, so
with no DNS it never returns. Patch the resolver — see the `offline_construction` fixture in
`tests/test_miner_lifecycle.py`. `__slots__` blocks monkeypatching methods on it
(`AttributeError: … is read-only`), so drive it through real calls rather than stubs —
`py_compile` and a bare `import` both passed on an `end()` that crashed on the first line it
reached.

Dashboard JS is testable offline too, and `tests/js/script.test.js` already does it — extend that
file rather than starting over. It loads the real `assets/script.js` into jsdom with the same
jQuery 3.5.1 that `charts.html` pins, and it is regression-sensitive: pointed at the pre-#21
script it reports 9 pass / 12 fail rather than passing vacuously. The technique, if you need it
elsewhere: load real jQuery into a jsdom document with `w.eval(jquerySource)` and assert on the
DOM. This gave a decisive before/after on the #12 XSS fix: `.append(string)` created a live
`<img onerror=…>`, the text-node
version created none. Caveat: jsdom does not fire `onerror`/`onload`, so assert on element
creation and attributes, not on handler execution.

Driving `script.js` itself needs stubs for `daysAgo`, an `ApexCharts` class, and
`Element.prototype.scrollIntoView`/`window.alert`, which jsdom does not implement. The trap:
**install any `setTimeout` stub *after* `w.eval(jquerySource)`** — jQuery schedules its own ready
callback through `setTimeout`, so stubbing first silently stops every `$(document).ready` handler
from running while unrelated assertions still pass. Assert that ready ran. Exceptions inside
`renderStreamers`'s Promise executor are swallowed into a rejection, surfacing only as an unhandled
rejection after the run.
`renderStreamers` also calls `changeStreamer` from a Promise `.then`, so its AJAX call lands at the
next `await` — inside whatever case is running by then. Await a tick after calling it, or requests
bleed across test cases.

**A live run is the strongest verification available, and it is usually available. Use it.**
Check for the cookie file first — `ls cookies/*.pkl` — and if one exists, finish any change that
touches the running flow (login, PubSub, the main loop, GQL calls, the dashboard server) with a
real run rather than stopping at the offline suite. State in the PR body whether the change was
exercised live.

**Run it in the container, not the host venv** — that is what ships and what the user runs.
`run.py` is configured and `cookies/roope242.pkl` skips the device-code step:

```bash
podman build --platform linux/amd64 -t tcpm:mine .
timeout 420 podman run --rm -v ./run.py:/usr/src/app/run.py:ro,Z \
  -v ./cookies:/usr/src/app/cookies:Z tcpm:mine
```

(`tcpm:mine`, not `tcpm:test` — `scripts/test-container.sh` owns that tag for the `test` stage, and
mining from an image carrying pytest is not what ships.)

**`--platform linux/amd64` is not optional.** `podman build` reuses a locally-stored base image
of the *wrong* architecture if one is tagged `python:3.10-slim-bookworm` — an arm64 base left by
an earlier emulated build gave a qemu run 2.5× slower that never reached the WebSocket phase in
5 minutes. Check with `podman image inspect <tag> --format '{{.Architecture}}'`.

Priming ~74 followers takes ~2.5 minutes in the container; budget **7 minutes** before reading
the output as steady state. `ENV PYTHONUNBUFFERED=1` is in the Dockerfile, so no `-u` needed.
Two WebSocket connections opening (`#0`, `#1`) means `submit()`'s capacity path ran for real.
The minute watcher only watches the top 2 streamers by priority, so a newly added streamer is
usually subscribed but *not* watched — don't read that as a bug.

A live run is real mining on the user's real account: it claims bonuses and, if `run.py` ever
enables them, places bets. Keep runs short and don't leave one going after the check is done.

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
That is why `__init__` starts the GitHub version check on a daemon thread rather than calling it
inline — it fires during construction, which is why tests patch `check_versions`.

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

`__submit` re-resolves `self.ws[index]` on every call rather than closing over a socket object,
so an index stays valid across a rebind — `self.ws` is only appended to or index-assigned, never
rebound or shrunk. That is what lets `__reconnect` repair the pool by index after publishing a
replacement.

The whole dispatch sits inside one `except Exception` that only logs. A typo or a call to a
method that doesn't exist surfaces as a single error line and nothing else.

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
- `TwitchChannelPointsMiner/__init__.py` re-exports the class under the submodule's own name, so
  `import TwitchChannelPointsMiner.TwitchChannelPointsMiner as m` binds the **class**, not the
  module. Use `importlib.import_module(...)` when patching module-level names like `check_versions`.
- Runtime output directories (`cookies/`, `logs/`, `analytics/`) and `run.py` are all gitignored.
- **This fork's Python floor is 3.9**, upstream's is still 3.6. The only thing raising it is
  `str.removesuffix()` in `AnalyticsServer.json_all`, added here. Don't contort new code to keep
  EOL interpreters working: a fix cherry-picked upstream keeps `removesuffix` and bumps
  `python_requires` there too, called out explicitly in the PR. (`self.streamers:
  list[Streamer]` is annotation-only — never evaluated at runtime, verified on 3.8 — so it does
  *not* raise the floor.) Docker uses 3.10.

## Sending fixes upstream

`origin` is the `roope242` fork; its parent is `rdavydov/...`, whose parent is
`Tkd-Alex/...`. `CLAUDE.md`, `ISSUES.md` (fork-local triage and fix order), `.coderabbit.yaml`,
`.claude/`, `scripts/cr-wait.sh`, and the whole test setup (`tests/`, `conftest.py`,
`requirements-dev.txt`, `.github/workflows/tests.yml`) exist only on the fork — **never open an
upstream PR from `master`**, it would carry them along. Branch off `upstream/master`, cherry-pick the fix
commits, and open it cross-fork:

```bash
git remote add upstream https://github.com/rdavydov/Twitch-Channel-Points-Miner-v2.git  # once
git fetch upstream && git checkout -b <branch> upstream/master
git cherry-pick <sha>
gh pr create --repo rdavydov/Twitch-Channel-Points-Miner-v2 --base master --head roope242:<branch>
```

Bare `gh` resolves to the fork since `gh repo set-default roope242/Twitch-Channel-Points-Miner-v2`
was run (2026-08-05, `remote.origin.gh-resolved = base` in `.git/config` — local to the clone, not
committed). Without it, `upstream` being a remote made `gh pr view`/`gh pr list` resolve *there*
and report a fork PR as nonexistent. A fresh clone needs the command again, or `--repo` on every
call. **Anything aimed at upstream still needs `--repo rdavydov/...` explicitly** — the default no
longer falls through to the parent by accident, which is the safer direction.

Fork PR bodies must state the code was written by an AI agent. **Upstream PR bodies must not raise
it** — omit, never misrepresent, since some maintainers reject AI-authored PRs on sight. The
`Co-Authored-By: Claude` commit trailers ride along on cherry-picks and are deliberately left.
