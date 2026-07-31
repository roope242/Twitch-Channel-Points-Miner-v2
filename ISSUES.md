# Work log and roadmap

Fork-local planning document for `roope242/Twitch-Channel-Points-Miner-v2`. Not upstream's
tracker — see `CLAUDE.md` for the fork/upstream relationship and the rule about never opening an
upstream PR from `master`.

This file is the session handoff. It is written so a session that starts cold, knowing nothing but
this file and `CLAUDE.md`, can pick up exactly where the last one stopped. Keep it that way:
update the **Start here** and **In flight** sections at the end of every working session, before
the context runs out.

**Last updated:** 2026-08-01 — #21 and #27 landed; review runs on a local fresh-context agent.

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
| `master` | `b6736a0` | Clean, pushed. CI green. |
| **PR #28** — issue #27, tests + CI | merge commit `b6736a0` | **Merged 2026-08-01.** Two review rounds; CI green on 3.9, 3.13 and node. |
| **PR #25** — issue #21, dashboard JS | merge commit `51591fc` | **Merged 2026-08-01.** Two review rounds, 20/20 jsdom assertions. |
| **#26** — polling chains accumulate, log chains duplicate | filed 2026-08-01 | Open. Both pre-existing, both observed in jsdom by the `pr-reviewer` agent on PR #25. Not scheduled. |

| **PR #22** — issue #12, untrusted-text sinks | merge commit `74eb9a8` | **Merged 2026-07-31.** Reviewed clean — "no actionable comments", range `34c1181..07e94d1`, the branch head. |

Nothing is in flight. **#10 is next** — see "Next up".

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

Nothing else is in progress. Stale local branches from merged PRs (`fix/shutdown-hang`,
`fix/stale-dashboard-assets`, `chore/coderabbit-config`, `docs/claude-md-session-learnings`,
`fix/untrusted-text-sinks`) can be deleted when convenient — ask first, branch deletion is
destructive.

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

**Start #10 (PubSub reconnection).** #21 and #27 both landed on 2026-08-01; nothing is open.
There is now a suite and a CI gate, so a delegated concurrency rewrite has something to fail against.

Deliberately *not* in #21: `getAllStreamersData()` is uncalled but is the only
client of the live `/json_all` route (`AnalyticsServer.py:157`, registered at `:311`). Deleting it
orphans a working endpoint. Leave it until someone decides whether the multi-streamer chart view is
wanted.

**#24 (black-format the whole package) is filed but deliberately unscheduled.** It conflicts with
any branch in flight and it contradicts the current `CLAUDE.md` guidance, which must be updated in
the same commit. Do it when nothing else is open — the issue carries the measurements (18 of 31
files, 564 diff lines) and the `.git-blame-ignore-revs` mitigation.

After #21, the order is **#10 → #13 → #16**, with **#7 and #11** going upstream rather than being
fixed here. Reasoning for each is under "Remaining work" below.

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
| 10 | PubSub reconnection blocks main loop, races itself | L | High | High | Open |
| 13 | Device-code login: dead expiry check, no timeout | S | Low | Med | Open |
| 16 | Startup primes streamers in two sequential loops | M–L | Low | Low | Open |
| 7 | Notifiers run inside the log formatter | M | **Zero** | High | Open — upstream candidate |
| 11 | Bet sizing and filtering bugs | S–M | **Zero** | High | Open — upstream candidate |

Two entries have zero gain under the current config because they sit on disabled code paths
(`make_predictions=False` for #11, no notifiers configured for #7). They are still real bugs for
other users, which is what makes them the two best upstream candidates rather than the two best
things to fix here.

---

## Remaining work

### #10 — PubSub reconnection

Highest absolute value left, and the largest. Two distinct problems: reconnection runs
synchronously on the main loop and parks the whole daemon, and the `is_reconnecting` guard is a
non-atomic check-then-act reached from four threads.

This is the one item that clearly warrants delegating the implementation and reviewing the diff —
multi-file, concurrency-critical, more than one defensible design. Read the threading rules in
`CLAUDE.md` first and put them in the task prompt: `self.streamers` is mutated only from the main
thread, `self.streamers`/`self.original_streamers` are index-parallel, and the list is passed by
reference into every `TwitchWebSocket` so it must never be rebound.

Related constraint from `CLAUDE.md`: `TwitchWebSocket` implements `listen()` only — there is no
`UNLISTEN` — so a topic subscribed during a session cannot be dropped. That is the blocker for
removing streamers mid-session and it bounds what #10 can achieve.

### #13 — device-code login

Small, but low value here: valid cookies in `cookies/roope242.pkl` mean this path is rarely
touched. Reasonable to batch with an upstream submission rather than do standalone.

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

- **Every code fix goes through a PR, and the review is a fresh-context agent.** Branch off
  `master`, commit, push, `gh pr create` against `roope242/master`. Then spawn the `pr-reviewer`
  agent (`.claude/agents/pr-reviewer.md`, flagship model, read-only) on the pushed head. Verify its
  findings against the code — they are claims, like any reviewer's — fix what is real, re-review,
  then merge without waiting for sign-off.

  **Tell it the base and head, and nothing else.** Not why the change is correct, not what was
  already verified, not what the last review said. The empty context is the entire mechanism; a
  reviewer primed with the author's reasoning re-derives the author's blind spot. The agent
  definition says the task prompt is not evidence — do not undercut that from the prompt side.

  Adding or editing `.claude/agents/*.md` does **not** register it in the running session:
  `subagent_type: pr-reviewer` fails with "Agent type not found" until Claude Code reloads. Until
  then, spawn the generic agent and point it at the file as its operating instructions — same
  model, same result.

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

There is no test suite. `python3 -m py_compile` is the floor, not the bar — see the #14 entry
above for why it proves nothing.

What actually works, in rough order of strength:

- **Live run.** `.venv/bin/python -u run.py` mines for real; `cookies/roope242.pkl` skips the
  device-code step. Use `-u` or stdout block-buffers and you see nothing. Priming ~74 followers
  takes ~2 minutes before the main loop starts. The minute watcher only watches the top 2 streamers
  by priority, so a newly added streamer is usually subscribed but *not* watched — not a bug.
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
