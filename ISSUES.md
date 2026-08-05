# Work log and roadmap

Fork-local planning document for `roope242/Twitch-Channel-Points-Miner-v2`. Not upstream's
tracker — see `CLAUDE.md` for the fork/upstream relationship and the rule about never opening an
upstream PR from `master`.

This file is the session handoff. It is written so a session that starts cold, knowing nothing but
this file and `CLAUDE.md`, can pick up exactly where the last one stopped. Keep it that way:
update the **Start here** and **In flight** sections at the end of every working session, before
the context runs out.

**Last updated:** 2026-08-05 — **#13 closed** (PR #37, merge commit `65662aa`). Four defects in the
device-code login flow, plus a fifth the first fix exposed and a sixth the review found. Three
review passes; the last one caught a regression *this branch* introduced, so it ran to four
iterations under the breaking-bug exception. Three findings were filed rather than patched —
**#38, #39, #40** — under a new standing rule: hitting the iteration cap ends the patching, not the
finding. Also confirmed today: no scheduled workflow has run since the two 2026-08-01 failures, so
#29's daily failure mail really did stop. Nothing in flight; see "Next up".

Previously, 2026-08-04 — docs only, no code touched (`57763af`, straight to `master` at the
user's call). `.github/ISSUE_TEMPLATE/agent_task.yml` turns the shape these issues had converged on
by hand into a GitHub form: code pointers as `path:line`, a concrete failure scenario, an Evidence
dropdown, and a **required** "Not verified". Field labels render as `###` headings, so an agent
reading the issue and nothing else gets a fixed, parseable structure. The two inherited templates
stay for users reporting the miner broken. **#36 filed** under the new scheme — the dashboard
sidebar is a directory listing, not session state.

Previously, 2026-08-02 (`1f2480c`, also straight to `master`). Second half of the CLAUDE.md split: the `pr-reviewer` agent left this repo for
`~/.claude/agents/`, rewritten to be generic, and the global instructions now require a
fresh-context review on **every** PR in any repo rather than only this one. The agent had been
carrying fork knowledge — an offline construction recipe for this miner, a stale jsdom
`node_modules` path, and a "there is no test suite here" line false since #27 — so it discovers
the repo's docs and test tooling now instead of hardcoding them. **Project knowledge belongs in
`CLAUDE.md`, not in the agent.** Nothing in flight; **#13 is still next**.

Earlier the same day (`3264c6d`), rules that were general rather than fork-specific moved from
`CLAUDE.md` to the user's global instructions: static checks are not verification, a new test must
be shown failing against the pre-fix revision, invoke tests the way CI does, never imply coverage a
change did not get, and give a reviewer the base and head with none of the implementing session's
reasoning. `CLAUDE.md` keeps the evidence for each.

Previously, 2026-08-01, end of session — **#34 closed**: the image is **324 MB**, down from
1.57 GB (`python:3.10-slim-bookworm`, no toolchain, no `apt`). Earlier the same day **#30 and #29
closed** (`ddff42e`, `90797a3`) and the fork started publishing its own Docker image,
`roopeli/twitch-channel-points-miner-v2`; #10 landed (PR #31) and #32, #33 were filed. **#32 then
closed too** (PR #35, `888c375`) — the last open correctness bug affecting a running miner.
Nothing in flight; **#13 is next** — see "Next up".

`6f5cad8` went in without a PR; `pr-reviewer` was run on it after the fact and found two real
things, both fixed in `d9f2bad` (also straight to `master`, at the user's call): the README
promised an `arm/v7` build the toolchain-free Dockerfile can no longer do (no `armv7l` wheels for
`numpy`/`pandas`, no compiler to fall back on — `arm64` does still build, verified under
emulation), and `setup.py` had never listed `validators` despite `classes/Twitch.py:15` importing
it at module scope. **Reviewing after the fact works, but it is the wrong order** — the fixes
landed on `master` unreviewed themselves.

---

## Start here

Do these in order at the beginning of a session, before starting anything new.

1. **Re-read real git state.** The snapshot below goes stale the moment another session commits.

   ```bash
   git fetch origin && git log --oneline -3 origin/master && git status -sb
   gh pr list --repo roope242/Twitch-Channel-Points-Miner-v2 --state open
   ```

2. **Nothing to re-trigger.** Reviews no longer run on a third-party service, so a session can no
   longer start blocked. Since 2026-08-01 the reviewer is a fresh-context agent spawned locally —
   see "Standing workflow" below. If a PR is open with unreviewed commits, spawn `pr-reviewer` on
   it; there is no queue and no quota window to wait for.

3. **Pick up the task named in "Next up"** below.

---

## In flight

| What | Where | State |
|---|---|---|
| `master` | `65662aa` | Clean, pushed. |
| **PR #37** — issue #13, device-code login | merge commit `65662aa` | **Merged 2026-08-05.** Three review passes, four iterations; CI green on 3.9/3.13/node; live-verified in the container. |
| **#38, #39, #40** | filed 2026-08-05 | Open, unscheduled. All three split out of PR #37's second review rather than widened into it. |
| **Merged branches** | — | Deleted 2026-08-05 with `git branch -d` (all three were contained in `master`) plus `git push origin --delete fix-13-device-code-login`. `master` is the only branch again, local and remote. Note `git branch -a` lists stale remote refs until `git fetch --prune`: two of the three had no remote at all. |
| **#36** — dashboard shows disk state, not session state | filed 2026-08-04 | Open, unscheduled. First issue written to the `agent_task.yml` template. Reasoned from the code; the dashboard was never run for it. |
| **#29** — inherited badge workflows | `90797a3` | **Closed 2026-08-01.** Both deleted; `deploy-docker.yml` kept and retargeted. |
| **#30** — README retargeted for the fork | `ddff42e` | **Closed 2026-08-01.** Docs-only, no PR. Option 1 (minimal) from the issue. |
| **PR #31** — issue #10, PubSub reconnection | merge commit `6d98a16` | **Merged 2026-08-01.** Two review rounds; CI green; live-verified. |
| **Docker image** | `b02bef0` pushed 2026-08-01 (1.57 GB); rebuilt at 324 MB, **not pushed** | `roopeli/twitch-channel-points-miner-v2:latest` + `:b02bef0` on Docker Hub are still the 1.57 GB build. The slim rebuild exists locally only. |
| **#34** — image was 1.57 GB for 652 kB of code | this session | **Closed 2026-08-01.** 324 MB, 79% smaller. Publishing it and moving builds to CI are still open. |
| **PR #35** — issue #32, `submit()` capacity race | merge commit `888c375` | **Merged 2026-08-01.** Four review rounds; CI green; live-verified in the container. The reconnect path itself was never exercised against a live socket — see below. |
| **#33** | filed 2026-08-01 | Open, unscheduled. Container testing. |
| **`6f5cad8` review debt** | `d9f2bad` | **Paid 2026-08-01.** Post-hoc `pr-reviewer` run on a commit that skipped review; 2 findings, both fixed. |
| **PR #28** — issue #27, tests + CI | merge commit `b6736a0` | **Merged 2026-08-01.** Two review rounds; CI green on 3.9, 3.13 and node. |
| **PR #25** — issue #21, dashboard JS | merge commit `51591fc` | **Merged 2026-08-01.** Two review rounds, 20/20 jsdom assertions. |
| **#26** — polling chains accumulate, log chains duplicate | filed 2026-08-01 | Open. Both pre-existing, both observed in jsdom by the `pr-reviewer` agent on PR #25. Not scheduled. |
| **PR #22** — issue #12, untrusted-text sinks | merge commit `74eb9a8` | **Merged 2026-07-31.** Reviewed clean — "no actionable comments", range `34c1181..07e94d1`, the branch head. |

**#39 + #38 are in flight** on `fix-39-login-give-up` — see "Next up". `master` is the only other
branch, local and remote, as of 2026-08-05.

### PR #37's three review passes, and the regression the last one caught

Kept because the shape is the one this file keeps warning about — **a fix that makes a latent bug
reachable** — and it happened twice in the same branch.

1. **Session review of the delegate's diff.** `login_flow()` assigned the token payload over
   `post_data`, the same name the outer loop posts to the *device* endpoint. Harmless only because
   the inner loop had no reachable exit; fixing the dead expiry check made it reachable, and the
   retry after an expiry then posted a scope-less token body to `/oauth2/device`. Observed by
   driving the real `login_flow()` with `send_oauth_request` patched and printing each request.
2. **Fresh-context `pr-reviewer`.** Two real findings. The broad `except Exception` around
   `pickle.load` — which *this session had asked for* the round before — swallowed
   `PermissionError`, so a valid-but-unreadable cookies file reported "is corrupt" and dropped into
   a device-code login, discarding good credentials for a worse diagnosis than the crash it
   replaced. And the expiry check ran ahead of the success check, so a token arriving in the final
   round-trip was thrown away: `200 {"access_token": "REAL-TOKEN"}` at `expires_in: 0` produced
   `Code expired. Try again` and a fresh device code.
3. **Second `pr-reviewer` pass, on the fixed head.** Caught the one that mattered most: routing
   corrupt cookies into `login_flow()` exposed a silent-continue the no-cookies branch already had.
   `login_flow()` returns `False` on a single non-200 from the device endpoint, both call sites
   ignored it, and `login()` returned normally with no token. Reproduced: `token` `None`, no
   `Authorization` header, corrupt file still on disk — after which the miner reports "0 followers"
   and "streamer does not exist" forever rather than a login problem. **For corrupt cookies that was
   a regression**: before the branch, the same input crashed loudly on `UnpicklingError`. Both paths
   raise `BadCredentialsException` now.

**This ran to four iterations, past the three-cycle cap**, on the breaking-bug exception: a defect
in code the branch itself added, turning a loud failure into a silent one. Cosmetic findings would
not have earned it.

The second pass also caught an **overstated verification claim in the PR body** — "every new
assertion was confirmed failing against the pre-fix source", when 2 of 9 pass at base (one is a
characterisation test; the other passes only because pre-fix `load_cookies` had no `try` at all).
Corrected to name the revision each test has teeth against. Worth remembering that the session
wrote that sentence about its own work and believed it.

### PR #35's four review rounds, and the shape they had

Each round found something real and strictly narrower than the last, all in the same eight lines of
`__reconnect`. Worth keeping because the pattern — a fix that closes the window it names and opens
its mirror image — is the thing to watch for in this file.

1. **Publish-then-seed.** The replacement went into `self.ws[ws.index]` and was seeded on the next
   two lines. `submit()` takes no lock, so in that gap it read 0 topics; the seeding then *rebound*
   both lists, discarding what `__submit` had appended. Silently unsubscribed for the session.
2. **Seed-then-publish left the mirror.** Until the store, `submit()` still resolved to the
   *retired* socket, so a topic appended to `ws.topics` after the snapshot was in neither list. No
   ordering fixes this — the sweep after publishing does, because past the store every `submit()`
   reaches the replacement.
3. **Two snapshots could disagree.** `topics` and `pending_topics` were each seeded from their own
   `list(ws.topics)`; a topic landing between the reads was in `pending_topics` only, so the sweep
   (which checks `topics`) re-appended it and `on_open` sent the LISTEN twice. One snapshot, copied.
4. Clean.

**Do not read "reviewed clean" as "exercised".** Every test and every review harness stubs
`__start`, so no rebuilt socket has ever connected and no LISTEN from one has been seen leaving the
process — which matters because this PR deleted the delayed replay, making `on_open` draining
`pending_topics` the only route by which a rebuilt connection resubscribes. The live container run
covers startup and steady state, not reconnection. Forcing a real reconnect needs a genuinely stale
connection; a run long enough to get one is the outstanding verification here.

Also on the record: `f1a59b6` deleted `test_shutdown_after_the_rebind_stops_the_topic_replay`
without replacement, since the replay it guarded no longer exists. That is a net −1 on shutdown
coverage of `__reconnect`, and the pre-existing orphan-replacement race (`end()` marks the retired
socket, `__reconnect` then publishes and starts a replacement nobody closes) stays unguarded —
harmless while every thread is a daemon and `end()` reaches `sys.exit(0)`.

### PR #25's two review rounds, and what the second caught

Worth keeping because the two rounds came from different reviewers and the second one caught the
first one's suggestion misfiring.

**Round 2 (`7ce88e4`, fresh-context agent) — the guard below was too broad.** Dropping the stored
selection whenever it was absent from the list also fired when the list was legitimately empty:
`Settings.analytics_path` is cwd-relative and always `mkdir`'d
(`TwitchChannelPointsMiner.py:134-137`), and `streamers_available()` lists `.json` files in it, so
a first start from another working directory — a systemd unit, a Docker mount — serves a 200 with
`[]`. The user's chosen streamer was then erased permanently. `7ce88e4` adds
`streamersList.length > 0 &&`. Observed in jsdom: the value survives an empty response, and the
assertion fails on `abcc030` exactly. Harness now 20/20.

The lesson generalises past this PR: **a reviewer's suggested fix is a claim like any other
finding.** CodeRabbit proposed the guard, it was verified against the *missing-streamer* case only,
and the empty-list case was never asked about. Check the suggestion's own edges, not just the bug
it names.

### Round 1's finding — fixed in `abcc030`

`script.js:331`, in the `getStreamers` success path. `selectedStreamer` was restored from
`localStorage` without checking it still exists. If that streamer is gone, `./json/<name>` returns
404 forever.

**This is pre-existing code that PR #25 makes worse, which is why it is worth fixing here rather
than filing separately.** Before the change a 404 killed the refresh loop, so the stale entry cost
one failed request. After it, `.always()` re-schedules unconditionally — so a permanently missing
streamer is now polled every five minutes for the life of the page. The resilience fix is correct;
this is the one case where "retry forever" is the wrong answer. `abcc030` clears the stale value
and falls through to the existing first-streamer default, rather than duplicating that default in
a second branch as CodeRabbit's snippet did — `renderStreamers` keys off
`localStorage.getItem("selectedStreamer") === null` at `script.js:365`, so removing the entry is
what keeps the list highlight consistent with `currentStreamer`.

Verified in jsdom, four new assertions (harness now 19 checks): with `selectedStreamer=ghost.json`
stored and a list holding only `real.json`, no request is issued for the ghost, the stored value
becomes `real.json`, `currentStreamer` falls back, and firing the one pending 300000ms timer polls
`./json/real.json`. All four fail on `c53274a`, pass on `abcc030`. `master` scores 8/19.

**Harness trap found while writing them:** `renderStreamers` calls `changeStreamer` from a Promise
`.then`, so its request lands in whatever test case happens to be running at the next `await` —
test 6's stray request was being counted against test 7. Await a tick after any `renderStreamers()`
call. One internal iteration spent of the three.

### What PR #22 contains, if the review needs defending

Three sinks that interpreted third-party text. All three fixes verified with real assertions, not
compile checks:

- **`assets/script.js:136`** — `.append(data)` became `.append(document.createTextNode(data))`.
  Note the issue text suggested `.text(...)`; that is **wrong**, it would replace the log on every
  poll instead of appending. Proven in jsdom with jQuery 3.5.1 (the version `charts.html` pins):
  before, a live `<img onerror="window.PWNED=1">` attaches to the DOM; after, zero elements and the
  text renders intact. The old code was also silently *swallowing* any log line containing markup.
- **`Webhook.py`** — both interpolated values now go through `quote(..., safe="")`. `parse_qs`
  confirms `@Bot x&event_name=STREAMER_ONLINE` no longer injects a second parameter.
- **`Discord.py`** — `allowed_mentions: {"parse": []}`, **plus** `data=` changed to `json=`. The
  issue called this a one-line fix; it is not. Form encoding flattens the nested object to
  `allowed_mentions=parse` and Discord ignores it, so the one-liner alone is a no-op.

Honest limits already stated in the PR body: jsdom does not fire `onerror`/`onload`, so element
creation and the live handler attribute are the evidence, not observed execution. Nothing was sent
to a real Discord webhook.

---

## Next up

**#13 is closed** (PR #37, `65662aa`). It turned out to be worth more than the effort table said:
the four defects were as filed, but fixing them exposed two more, and the login path is the one a
user hits before anything else works.

**#39 is the strongest of what #13 left behind** — `login_flow()` still re-issues device codes
forever, so a headless deployment that loses its cookies looks like a hang rather than a login
failure. #38 (a `KeyError` on a device response missing `interval`) is the same size and sits in
the same method, so the two are naturally one branch. #40 is smaller and rests on a response shape
nobody has seen; it can wait.

After those, the order is unchanged: **#33** (container testing), then **#36**, **#26**, **#16**,
with **#7 and #11** going upstream rather than being fixed here.

**#13 was a candidate for batching with an upstream submission** and no longer is, cleanly: the fix
grew a `BadCredentialsException` on failed login and a restructured `Twitch.login()`, which is a
behaviour change upstream would have to want on its own terms rather than a bug fix to wave
through. Send it only if someone asks.

**Two things left over from #34, both needing a decision rather than code:** the Docker Hub tags
still point at the 1.57 GB build, because republishing `latest` was not done unilaterally; and
`deploy-docker.yml` stays inert until `DOCKER_USERNAME` and `DOCKER_TOKEN` are set as repository
secrets, which only the repo owner can do. Until one of those happens, `latest` is a hand-built
image from a laptop.

**#29's fix is confirmed, four days on.** `gh run list --event schedule` on 2026-08-05 returns the
two 2026-08-01 failures and nothing newer, so deleting the scheduled workflows really did stop the
daily failure mail. Nothing further to check here.

#30 was done on 2026-08-01 as `ddff42e`, taking option 1 (minimal) from the issue: Python floor,
both clone URLs, a "This fork" section, the test-suite pointer, and the Docker section. Badges
other than Docker, plus credits and donation links, deliberately still point upstream, so an
upstream README merge stays clean. Both documented test commands were run as written.

Deliberately *not* in #21: `getAllStreamersData()` is uncalled but is the only
client of the live `/json_all` route (`AnalyticsServer.py:157`, registered at `:311`). Deleting it
orphans a working endpoint. Leave it until someone decides whether the multi-streamer chart view is
wanted.

**#24 (black-format the whole package) is filed but deliberately unscheduled.** It conflicts with
any branch in flight and it contradicts the current `CLAUDE.md` guidance, which must be updated in
the same commit. Do it when nothing else is open — the issue carries the measurements (18 of 31
files, 564 diff lines) and the `.git-blame-ignore-revs` mitigation.

Reasoning for each remaining item is under "Remaining work" below.

---

## Effort/gain table

"Gain (config)" is measured against the current `run.py`: `make_predictions=False`,
`claim_drops=False`, `chat=ChatPresence.NEVER`, no notifiers, `enable_analytics=True`,
`file_level=DEBUG`, and an IPv4-only `getaddrinfo` monkeypatch. "Gain (general)" is for a typical
user with the defaults.

| # | Title | Effort | Gain (config) | Gain (general) | Status |
|---|---|---|---|---|---|
| ~~9~~ | Client version refetched per GQL request | S | High | High | **Closed** — `fd55fe6` |
| ~~5~~ | Blanket `except Exception` hides PubSub bugs | XS | High | High | **Closed** — `5ca56fd` |
| ~~15~~ | Assorted small correctness bugs | XS | Low | Low | **Closed** — `1691aff` |
| ~~6~~ | No HTTP request timeouts | S–M | Med | High | **Closed** |
| ~~14~~ | Shutdown hangs forever and re-enters itself | S–M | Med | Med | **Closed** — PR #17 |
| ~~4~~ | `check_assets()` never updates existing assets | S–M | Med | Med | **Closed** — PR #20 |
| ~~12~~ | Untrusted text reaches HTML and URL sinks | M | Med–High | Med | **Closed** — PR #22, `74eb9a8` |
| ~~21~~ | Dashboard JS: log polling dies on one failed request | S | Low–Med | Med | **Closed** — PR #25, `51591fc` |
| 26 | Polling chains accumulate; log chains duplicate | S | Low | Low–Med | Open — unscheduled |
| ~~27~~ | No test suite; verification harnesses are thrown away | S–M | n/a — tooling | n/a | **Closed** — PR #28, `b6736a0` |
| ~~23~~ | `.coderabbit.yaml` output is mostly packaging | XS | n/a — tooling | n/a | **Closed** — `f257f02` |
| 24 | Package is not uniformly black-formatted | S | **Zero** | **Zero** | Open — unscheduled |
| ~~10~~ | PubSub reconnection blocks main loop, races itself | L | High | High | **Closed** — PR #31, `6d98a16` |
| ~~32~~ | `submit()` overfills a connection during a reconnect | S–M | Low–Med | Med | **Closed** — PR #35, `888c375` |
| ~~29~~ | Inherited badge workflows fail every day | XS | n/a — tooling | n/a | **Closed** — `90797a3` |
| ~~30~~ | README is upstream's, unreviewed for this fork | S | n/a — docs | Med | **Closed** — `ddff42e` |
| 33 | Tests do not run in a container, so nothing tests 3.10 | M | n/a — tooling | n/a | Open |
| ~~34~~ | Docker image was 1.57 GB for 652 kB of code | M | n/a — packaging | Med | **Closed** — 324 MB |
| ~~13~~ | Device-code login: dead expiry check, no timeout | S | Low | Med | **Closed** — PR #37, `65662aa` |
| 38 | Device response missing `interval` kills the process | XS | Low | Low–Med | Open — split from PR #37's review |
| 39 | `login_flow()` re-issues device codes forever | S | Low | Med | Open — split from PR #37's review |
| 40 | Token-endpoint error body logged verbatim | XS | Low | Low | Open — split from PR #37's review |
| 16 | Startup primes streamers in two sequential loops | M–L | Low | Low | Open |
| 7 | Notifiers run inside the log formatter | M | **Zero** | High | Open — upstream candidate |
| 11 | Bet sizing and filtering bugs | S–M | **Zero** | High | Open — upstream candidate |

Two entries have zero gain under the current config because they sit on disabled code paths
(`make_predictions=False` for #11, no notifiers configured for #7). They are still real bugs for
other users, which is what makes them the two best upstream candidates rather than the two best
things to fix here.

---

## Remaining work

### #32 — `submit()` overfills a connection during a reconnect

Fell out of #31's review. `submit()` sizes the last connection from `len(self.ws[-1].topics)`, but
`__reconnect` rebinds that index to an empty socket and only replays the topics 30 seconds later,
so a followers refresh landing in that window piles new topics onto a connection that is about to
get its original ~50 back. Excess `LISTEN`s are rejected and never retried, so those streamers go
dark for the session. Mostly pre-existing — unparking the main loop in #10 removed one of the two
things that were accidentally hiding it.

Note the standing constraint: `TwitchWebSocket` implements `listen()` only — there is no
`UNLISTEN` — so a topic subscribed during a session still cannot be dropped. That remains the
blocker for removing streamers mid-session.

### #34 — the Docker image (closed 2026-08-01)

**1.57 GB → 324 MB, a 4.85× reduction, measured on `podman images`.** The hypothesis that no
compiler toolchain was needed held: every requirement resolves to a manylinux/py3 wheel, `millify`
being the only sdist and pure-Python. The final `Dockerfile` is 14 lines with no `apt-get` at all.
What went: the fat `python:3.10-bullseye` base (→ `slim-bookworm`), `apt-get upgrade -y` (297 MB),
the orphan `apt-get update` layer (18.4 MB), `pip install --upgrade pip` (15.5 MB), the entire
`cryptography`/Rust apparatus for a package that was never installed, the apt-installed
`python3.9*` interpreters, and `pre-commit` (now in `requirements-dev.txt`, and out of `setup.py`'s
`install_requires`).

**The remaining 324 MB is mostly floor:** 132 MB base, then `pandas` 64 MB + `numpy` 67 MB = 131 MB
of the 191 MB dependency layer. Dropping below ~200 MB means replacing the single
`import pandas as pd` at `AnalyticsServer.py:10`. Not attempted; still the open question the issue
raised.

Verified in the built container: `__version__` is `2.0.7`; `pandas`, `flask`, `irc` and `PIL`
import; the five packaged dashboard assets are present *and* `check_assets()` copies all five out
at runtime; `pip list` shows none of `pre-commit`/`virtualenv`/`nodeenv`/`cfgv`. The entrypoint was
run with `run.py` bind-mounted and no cookies: it reached the Twitch device-code prompt, so it dies
at auth, not on an import. Not verified: a full live mining run from the container, and the image
was **not** pushed.

Credentials for the push live in `~/.config/containers/auth.json` with
`REGISTRY_AUTH_FILE` exported from `~/.bashrc.d/podman.sh` — podman's default store is
`$XDG_RUNTIME_DIR/containers/auth.json` on tmpfs and does not survive a reboot. That drop-in is
**not** read by systemd user units; those need `~/.config/environment.d/`.

`.dockerignore` (`5365fc3`) exists because the build context was 293 MB and included `cookies/` and
`run.py`. Nothing reached the image, but a future `COPY . .` would have leaked the session.

### #33 — inherited from upstream, never reviewed for this fork

Same shape as #29, #30 and #34: material that came over from `rdavydov/...` and was never read as
*this* repo's. Nothing currently tests Python 3.10, which is what the published Docker image runs.

**#29 closed 2026-08-01 (`90797a3`).** Both badge workflows deleted, with `CLONE.md` and
`TRAFFIC.md`. They failed daily because `SECRET_TOKEN` is unset here, so `gh auth login
--with-token` got an empty token and fell into the interactive device-code flow — 15 minutes of a
runner waiting for a code nobody can type. They also curl'd and executed a third party's script on
a runner holding a PAT. No scheduled workflow remains.

`deploy-docker.yml` was kept rather than deleted, because the fork now publishes an image: it
points at `roopeli/...`, builds `linux/amd64` only, and the QEMU step went with the ARM legs. It is
inert until `DOCKER_USERNAME` and `DOCKER_TOKEN` are set on the repository. It tags `latest`
unconditionally, so a `workflow_dispatch` from any branch would republish `latest` — inherited
behaviour, deliberately left.

### #38, #39, #40 — what #13 left behind

All three split out of PR #37's second review. #39 is the one with teeth: `login_flow()`'s outer
`while True` re-requests a device code after every expiry, so it never gives up and a headless
deployment that loses its cookies presents as a hang rather than a login failure. #38 is a bare
`KeyError` on a device response missing `interval` — the same shape of bug PR #37 fixed for a
missing `user_code`, one field over, in the same method, which makes it a natural companion branch.
#40 is a logging-hygiene fix resting on a response shape nobody has observed; the issue says so.

The estimate for #13 in the table below said "S / Low" and was wrong in an instructive way: the
four filed defects were all real and all small, but two more fell out of fixing them, and the
second-order work — a restructured `Twitch.login()`, a new exception on failed login, eleven tests
— was most of the branch. **A fix in a path nothing else guards tends to cost more than its
diff.**

### #16 — startup sequencing

Deliberately last. It saves ~60–90s once per start on a process that runs for days, and it is the
change most likely to introduce a threading bug for that payoff. Both the effort and the risk are
real; the gain is not.

### Not for this fork — #7 and #11

The two strongest upstream candidates: real bugs, reproducible, on code paths upstream's users
actually run, and both fail in a direction that costs the user something. Per the
upstream-contribution rules they should go out as focused PRs branched from `upstream/master`, not
carried here indefinitely. #7 additionally looks like the cause of upstream's open #805, which is
worth saying in the PR.

---

## Done, and what each one taught

### #13 — device-code login (PR #37, `65662aa`)

The four filed defects, plus the aliased `post_data` the expiry fix made reachable and the silent
token-less `login()` the corrupt-cookie recovery routed into. Eleven tests in
`tests/test_twitch_login.py`; live-verified in the container (7m01s, both WebSockets, `+10` on a
real WATCH). The three review passes are written up under "In flight" above. Four things worth
carrying forward:

- **A broad `except` is a decision about what you are willing to misdiagnose.** This session asked
  for `except Exception` around `pickle.load` to cover every corruption shape; it also swallowed
  `PermissionError`, so a *valid* cookies file with the wrong mode was announced as corrupt and
  traded for a device-code login nobody could complete headlessly. The fix is `except OSError:
  raise` ahead of the broad catch — but the lesson is that the instruction to broaden came from
  the reviewer's side of the desk, and no one checked it against the cases it would newly capture.
- **Removing a crash is not the same as handling a failure.** Replacing an uncaught
  `UnpicklingError` with a recovery path looked like strict improvement, and was worse: the
  recovery could finish with no token, and `run()` does not check, so the miner mined nothing while
  reporting "0 followers" — forever, on every start. A loud crash beats a quiet wrong state.
- **`logger.error` is not an exit.** Both `login()` branches logged and carried on. The log line
  makes it *look* handled while the process continues in a state that cannot work.
- **The session's own PR body overstated its verification** — "every new assertion was confirmed
  failing against the pre-fix source", when two of nine pass at base. Nobody was lying; the claim
  was written once, early, and stayed true-sounding after the test set grew. Re-check the
  verification sentence against the final test list, not the one it described when written.

### #10 — PubSub reconnection (PR #31, `6d98a16`)

The wait and rebuild moved to a daemon thread so `handle_reconnection` returns immediately; the
`is_reconnecting` claim is atomic under a pool-level lock that also covers the `self.ws[index]`
rebind; duplicate detection moved to a bounded window on the pool; `PubsubTopic` compares by value
and `__submit` returns early rather than re-`LISTEN`-ing.

Delegated to a subagent and reviewed twice by `pr-reviewer`. Four things worth carrying forward:

- **Moving shared state "up" a level can make it strictly weaker.** Hoisting the duplicate-message
  slot from the socket to the pool fixed the cross-connection case the comment described — and
  broke the same-connection case the code could actually catch, because with two connections the
  other one's traffic overwrites the slot between a message and its copy. A single slot was the
  wrong shape at either level; it is a 20-entry deque now. The reviewer *observed* it
  (`counter: 2, amount: 20` vs `counter: 1`) rather than arguing it.
- **A guard that records is not a guard that prevents.** `PubsubTopic.__eq__` was credited with
  stopping a duplicate `LISTEN`, but `if topic not in topics:` only gated the append — `listen()`
  ran underneath it regardless. `topics: 1, LISTENs: 2`. Check what the guard actually guards.
- **Rebinding an object into a shared array orphans every reference to the old one.**
  `__reconnect`'s post-rebind `forced_close` check read the retired socket, which `end()` can no
  longer reach, so a shutdown in that 30s window replayed topics into a just-closed connection.
- **`git add -A` after a live run is a trap in this repo.** `check_assets()` copies five packaged
  dashboard files into the working-directory `assets/` on every start, and they went into the
  commit. `.gitignore` names them now. The live run that made this repo's verification stronger is
  the same run that dirtied the tree.

Live verification is what proved the `__submit` early return safe: 75 topics, each `LISTEN`-ed
exactly once, in `logs/roope242.log`. Not verified: no live reconnection or live duplicate message
occurred in either run, so those paths are proven against stubs.

### #27 — a test suite and CI (PR #28, `b6736a0`)

`tests/js/script.test.js` (21 jsdom cases against the real `assets/script.js`) and three pytest
modules, gated by `.github/workflows/tests.yml` on `pull_request`, `push: [master]` and manual
dispatch, across Python 3.9 and 3.13.

**Run them as `python -m pytest tests/ -q` and `cd tests/js && npm ci && node --test`.** A root
`conftest.py` exists solely so the bare `pytest` also works — the package is not pip-installed, and
only the module form puts the repo root on `sys.path`.

Three things worth carrying forward:

- **A suite that passes is not a suite with teeth.** The measurement that mattered was pointing the
  JS suite at the pre-#21 `script.js`: 9 pass / 12 fail, each broken behaviour named. Do that to any
  new test before trusting it. It also caught a porting slip — a dropped `if (refresh.length)` guard
  made a regression abort the whole file with a `TypeError` instead of failing 12 cases cleanly.
- **CI ran zero Python tests on the first attempt and looked fine locally.** The workflow said
  `pytest tests/ -v`; the console script does not put the repo root on `sys.path`, so all three
  modules died at collection. It passed locally only because the local command was `python -m
  pytest`. Real CI confirmed it: run 30667879498 failed with `ModuleNotFoundError` on both legs.
  **Run the exact command CI runs, not your habitual one.**
- **`__init__` is not offline-safe**, despite login living in `run()`. It loops
  `while not is_connected()` on `socket.gethostbyname("twitch.tv")` forever, five seconds at a
  time. Tests patch the resolver via the `offline_construction` fixture, and both CI jobs now set
  `timeout-minutes` so a DNS stall cannot burn the 360-minute default.

**Known coverage gap, deliberately left:** every lifecycle test builds a miner with no streamers,
no `ws_pool` and no worker threads, so `end()` short-circuits and everything below its first log
line (`TwitchChannelPointsMiner.py:515-541`) is guarded off. Injecting `AttributeError`s into those
branches leaves the suite green. Only a crash at the very top of `end()` is caught — which is
narrower than issue #14's own failure mode. Closing it needs a miner with populated session state.

### #21 — dashboard JS resilience (PR #25, `51591fc`)

The re-schedule moved into `.always()` for all three polling chains, duplicate
`#annotations`/`#dark-mode` bindings removed, `displayname` de-globalised, SRI added to four CDN
includes. Verified observationally, not by reading: a simulated outage kills all four 5-minute
timers on `master` and none on the branch, and the duplicate handlers ran twice before and once
after.

Two rounds, two reviewers, and the second caught the first's suggestion misfiring — the full story
is under "PR #25's two review rounds" above. The transferable part: **a reviewer's proposed fix is
a claim with edges its finding never mentioned.** Verify the suggestion against the cases it did
*not* name.

### #23 — CodeRabbit output was mostly packaging (`f257f02`)

Presentation knobs off, findings untouched. Every key was validated against the published schema
before committing — `"off"` is quoted deliberately, since bare `off` is a YAML boolean and would
have been silently rejected as a mode.

**Measured on PR #25, the first review under the new config:**

| | comment size |
|---|---|
| PR #22, old config, verdict "no actionable comments" | 6104 bytes / 129 lines |
| PR #25, new config, verdict "1 actionable comment" | 3298 bytes / 61 lines |

Roughly half, and the smaller comment is the one with *more* to report — #22 had nothing to say and
still spent twice the bytes saying it. Not a controlled comparison (different PRs, different
content), but the direction is unambiguous and the packaging blocks are visibly gone.

Two settings were kept on against the general direction of the change: `review_status`, which is
what carries the "review skipped" and quota notices — losing those would hide exactly the failure
this session kept hitting — and `enable_prompt_for_ai_agents`, which is signal here rather than
noise.

### #12 — untrusted text in HTML and URL sinks (PR #22, `74eb9a8`)

Three sinks: the dashboard log viewer's `.append(data)`, the webhook query string, and Discord's
missing `allowed_mentions`. Details of each are in the PR body. Two things worth carrying forward:

- **Two of the issue's three suggested fixes were wrong or incomplete**, which is now a pattern
  across #15, #14 and this one. `.text(...)` on the log viewer would have replaced the log on every
  poll instead of appending, and the Discord one-liner was a *no-op* until `data=` also became
  `json=` — form encoding flattens `allowed_mentions` to `allowed_mentions=parse` and Discord
  ignores it. Driving the real `send()` with `requests` patched is what caught the second; reading
  the diff would not have.
- **Fixing at the sink, not the producer, was the deliberate choice.** `post_gql_request` logs
  `response.text` at DEBUG and `file_level` defaults to DEBUG, so the untrusted bytes reach the log
  as a raw API body rather than through a formatted message — escaping producers would have missed
  the widest path in the default configuration.

The review of this PR also taught the CodeRabbit detection fix now recorded in "Start here":
`pulls/N/reviews` returned `[]` *after* a completed review, because the bot edits its summary
comment in place instead of submitting one.

### #9 — client version refetched per GQL request (`fd55fe6`)

Cached behind a 30-minute TTL. Measured on the same host with the same 74 followers: **294 page
fetches in a 13-minute run before, 1 in a 3-minute run after**; startup to first result went 98s →
65s. Honestly smaller than the issue claimed, and recorded as such.

### #5 — blanket `except Exception` hid PubSub bugs (`5ca56fd`)

`AttributeError` and `NameError` now log `critical` with a traceback before the catch-all. Those
two mean a bug in the miner itself, not a Twitch or network problem. The catch-all is narrowed, not
removed, so "no crash" is still not evidence a branch works.

### #15 — assorted small correctness bugs (`1691aff`)

Three one-liners. Worth remembering that **one of the issue's own suggestions was wrong**: for the
dead timezone branch in `logger.py`, changing the comparison to `is None` would have made `tz = ""`
reachable and `datetime.now("")` raises `TypeError`. The branch was deleted instead. Verify issue
text against the code; a written-down finding is still a claim.

### #6 — no HTTP request timeouts

`REQUESTS_TIMEOUT = 10` applied at all 19 live call sites, and the GitHub version check moved to a
fire-and-forget daemon thread.

The timeout alone is genuinely not a fix. `requests` applies the timeout *per connection attempt*,
so on this host — where IPv6 egress is blackholed — `check_versions()` takes **40.3s** (4 AAAA
records × 10s) before falling back to IPv4 and succeeding. Part 2 mattered more than part 1.

Measured rather than assumed:

| host | AAAA records | latency with blackholed IPv6 |
|---|---|---|
| `raw.githubusercontent.com` | 4 | ~40s |
| `gql.twitch.tv` | 1 | 0.3s |
| `www.twitch.tv` | 1 | 0.1s |

Twitch hosts are unaffected; only GitHub-hosted calls are slow. On that evidence the IPv4-only
`getaddrinfo` monkeypatch at the top of `run.py` looks removable, but **this has not been confirmed
with a live run** — verify before deleting it.

### #14 — shutdown hang and re-entry (PR #17)

Bounded joins, a dedicated `shutting_down` re-entrancy guard, SIGSEGV dropped from the handled
signals. Three things worth carrying forward:

- **Bounded joins alone did not fix it.** The worker threads were non-daemon, and `sys.exit(0)`
  only raises `SystemExit` on the main thread — Python then waits on every non-daemon thread at
  interpreter shutdown. A stuck worker produced the new warning and hung anyway. Measured with a
  deliberately stuck thread: non-daemon had to be killed externally (exit 124), daemon exits 0. All
  three workers are now `daemon=True`.
- **The issue's finding 1 was wrong about chat.** `leave_chat()` rebinds `streamer.irc_chat` to a
  fresh, never-started thread, so the chat join was always operating on something whose
  `is_alive()` is `False`. That branch could never have hung. The minute-watcher and sync-campaigns
  joins it named were real.
- **`py_compile` and a bare `import` both passed on an `end()` that crashed on its first line.**
  This is why the verification bar is "exercise it", not "it compiles".

Still unverified: the join-timeout warning branches themselves. Forcing a genuinely stuck worker
needs a live session, so they are read-correct but have not been observed firing.

### #4 — dashboard assets never refreshed (PR #20)

Assets now live in `TwitchChannelPointsMiner/assets/` and ship with the package; `check_assets()`
copies them into the working-directory `assets/` and overwrites on a sha256 mismatch.
`download_assets()` and `utils.download_file()` are gone — nothing fetches assets over the network.

The download *source* was the deeper problem, not just the trigger. `GITHUB_url` points at upstream
`rdavydov/master`, so a naive refresh-on-mismatch would have *overwritten* fork-local asset changes
— the refresh-followers button among them — with upstream's version on every start.

**Review pattern worth reusing:** a pure `git mv` makes a reviewer read the moved file as new code,
so expect findings that predate the change. CodeRabbit raised five on the moved `script.js` and
`charts.html`; all five were real and all five were pre-existing. Keeping the move at 100%
similarity is what lets the next reader confirm it was faithful without diffing contents — so file
the findings separately (they became #21) and say so in the PR. CodeRabbit withdrew all five on
that argument.

Still unverified: that `MANIFEST.in` actually places the assets in a built sdist. `setuptools` and
`build` are not installed in `.venv`, so no distribution was built. The runtime path is proven —
`check_assets()` resolves the packaged folder via `os.path.dirname(__file__)/../assets`, which
works from a checkout regardless of packaging.

---

## Standing workflow

- **New issues follow `.github/ISSUE_TEMPLATE/agent_task.yml`.** `gh issue create` bypasses the
  form — GitHub only applies it in the web UI — so write the body with the same `###` headings by
  hand. The one that gets skipped and shouldn't is **Not verified**: an issue that quietly implies
  it was reproduced sends the next session hunting for a repro that never existed. #36 is the
  worked example.

  **Always pass `--label`.** `gh issue create` applies none by default and the template's Kind
  dropdown is body text, not a label, so an agent-filed issue lands unlabelled and invisible to
  every filter. Map Kind onto the repo's labels: *Defect* → `bug`, *Feature* → `enhancement`,
  *Documentation* → `documentation`, and the rest → `enhancement` unless a better one exists
  (`gh label list`). Asked for on 2026-08-05, after #38–#40 were filed bare and relabelled by hand.

- **A finding the iteration cap leaves unfixed gets evaluated for its own issue, not dropped.**
  Reaching the limit ends the patching, not the finding. For each one, decide out loud: file it, or
  say why it is not worth filing. The same goes for anything a review parked as "info" or
  "follow-up". #38, #39 and #40 came out of PR #37 this way — all three were real, none justified a
  fifth iteration on that branch.

- **Every code fix goes through a PR, and the review is a fresh-context agent.** Branch off
  `master`, commit, push, `gh pr create` against `roope242/master`. Then spawn the `pr-reviewer`
  agent (`~/.claude/agents/pr-reviewer.md`, flagship model, read-only) on the pushed head. Verify its
  findings against the code — they are claims, like any reviewer's — fix what is real, re-review,
  then merge without waiting for sign-off.

  **Tell it the base and head, and nothing else.** Not why the change is correct, not what was
  already verified, not what the last review said. The empty context is the entire mechanism; a
  reviewer primed with the author's reasoning re-derives the author's blind spot. The agent
  definition says the task prompt is not evidence — do not undercut that from the prompt side.

  The agent moved out of this repo to `~/.claude/agents/` on 2026-08-02 — it is now generic (finds
  the diff from a base/head, a PR number or a working tree; discovers the repo's docs and test
  tooling instead of hardcoding this project's) and applies to every PR in every repo. **Project
  knowledge lives in `CLAUDE.md`, not in the agent** — that is the split; do not push repo-specific
  verification tricks back into the agent file.

  Adding or editing an agent under `.claude/agents/` or `~/.claude/agents/` does **not** register it
  in the running session: `subagent_type: pr-reviewer` fails with "Agent type not found" until
  Claude Code reloads. Until then, spawn the generic agent and point it at the file as its
  operating instructions — same model, same result.

- **Why this replaced CodeRabbit (2026-08-01).** It runs on the Claude subscription instead of a
  third-party quota, so a session can no longer be blocked mid-flight — which is exactly what
  stopped the 2026-07-31 session with a fix pushed and unreviewed. It also re-reads the *whole*
  diff every run, where CodeRabbit is incremental and skips commits it has already seen; that gap
  is what left `abcc030` unreviewed while the bot cheerfully affirmed it by name.

  **Calibration, measured on the same diff.** PR #25 at `abcc030`: CodeRabbit's CLI returned
  **0 findings**; the fresh-context agent returned **3** — one warning and two info — and all three
  were reproduced in jsdom rather than argued. One was a genuine regression the CodeRabbit PR bot
  had asked for two rounds earlier: its own suggested guard wiped the user's saved streamer
  whenever `/streamers` legitimately returned `[]`. The other two were pre-existing and correctly
  labelled as such; they became #26. One sample, not a controlled comparison — but the direction
  was not close.

- **CodeRabbit is off by default and kept for the big cases.** `.coderabbit.yaml` sets
  `reviews.auto_review.enabled: false` (verified against the published schema: there is no
  `reviews.enabled` key, and `description_keyword` stays empty so no PR body can silently
  re-enable it). The GitHub App is still installed, so `@coderabbitai review` works on demand —
  use it as a third opinion on a PR large enough to be worth the cost, not as the default gate.
  `scripts/cr-wait.sh <N>` is still the only reliable way to detect its verdict when you do.
- **Documentation-only changes skip the PR.** `CLAUDE.md`, `ISSUES.md`, `README.md`, repo config —
  commit straight to `master`. There is nothing for a code reviewer to review and the ceremony just
  burns review quota.
- **Fork PR bodies must say the code was written by an AI agent.** The commits, the analysis and
  the verification transcripts are the agent's work; `@roope242` directs, reviews and merges, and is
  a co-author rather than the author. State that plainly in the description of every PR opened
  against `roope242/master`.
- **Upstream PR bodies must not raise it.** Some maintainers reject an AI-authored PR on sight,
  fundamentally correct or not, and a fix that is worth their review should stand on its
  reproduction and its evidence. So omit the subject upstream — *omit*, not misrepresent: never
  write or imply that a human wrote the code, and answer honestly if a maintainer asks.
  Every commit here carries `Co-Authored-By: Claude …` and `Claude-Session: …` trailers and
  `git cherry-pick` brings them along, so an upstream branch shows them in its commit metadata
  whatever the body says. **Decided 2026-07-31: leave them.** Do not rewrite commits to strip
  them — the rule is to not *raise* the subject in the description, not to hide it.
- **An approval is a claim too, and it is the one you want to believe.** This survived the move off
  CodeRabbit unchanged — only the failure mode is new. A bot that is merely talkative used to fake
  a verdict (PR #25: "Review finished", while no review had started); an agent that is merely
  agreeable can do the same. The defence is the same in both cases: a CLEAN verdict counts only if
  the report says *what was actually checked*, specifically enough to be false. "Verified the JS"
  is not a review. "Ran the jsdom harness, 19/19, ready confirmed to fire" is.

  If the report cannot show its teeth, treat it as no review and spawn again.
- **Iteration budget:** three internal review→fix cycles, six for verified external review
  findings. Cosmetic comments do not count against either. Past that, stop and report rather than
  patching again.

---

## Verification reality

There is a test suite since #27 (`python -m pytest tests/ -q`, `cd tests/js && node --test`), and
it is where new verification belongs. `python3 -m py_compile` is the floor, not the bar — see the
#14 entry above for why it proves nothing.

What actually works, in rough order of strength:

- **Live run — check for it and use it.** `ls cookies/*.pkl`; if a cookie file is there, a change
  touching the running flow gets a real run before it is called done, and the PR body says whether
  it got one. `.venv/bin/python -u run.py` mines for real; `cookies/roope242.pkl` skips the
  device-code step. Use `-u` or stdout block-buffers and you see nothing. Priming ~74 followers
  takes ~2 minutes before the main loop starts. The minute watcher only watches the top 2 streamers
  by priority, so a newly added streamer is usually subscribed but *not* watched — not a bug.
  It is the user's real account: keep the run short and stop it when the check is done.
- **Offline construction.** Login happens in `run()`, not `__init__`, so the miner constructs
  offline with `logger_settings=LoggerSettings(save=False, console_level=logging.CRITICAL)` —
  enough to exercise `end()`, the signal handlers, and anything in `utils.py` for real. `__slots__`
  blocks monkeypatching methods, so drive it through real calls rather than stubs.
- **Driving real methods with `requests` patched.** How the #12 webhook and Discord fixes were
  verified: call `send()` for real, capture the prepared request, assert on the URL with
  `parse_qs` and on the JSON body. Catches things reading the diff does not — the Discord fix was a
  no-op until `data=` became `json=`.
- **Dashboard JS in jsdom.** `node` and `npm` are on this host. `npm install jsdom jquery@3.5.1`
  (match the version `charts.html` pins) in a scratch dir, load real jQuery into a jsdom document
  with `w.eval(jquerySource)`, assert on the DOM. Caveat: jsdom does not fire `onerror`/`onload`,
  so assert on element creation and attributes, not handler execution.
- **Formatting.** `black` is installed in `.venv` (not in any requirements file). A `PostToolUse`
  hook formats `.py` files on save; it silently did nothing until black was installed, so do not
  assume a Python file was formatted just because the hook exists.

Because of the PubSub catch-all — narrowed but not removed in #5 — "no crash" is still not evidence
that a branch works. Anything touching `on_message` must be verified by observing the intended side
effect.
