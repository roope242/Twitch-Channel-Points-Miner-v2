# Work log and roadmap

Fork-local planning document for `roope242/Twitch-Channel-Points-Miner-v2`. Not upstream's
tracker — see `CLAUDE.md` for the fork/upstream relationship and the rule about never opening an
upstream PR from `master`.

This file is the session handoff. It is written so a session that starts cold, knowing nothing but
this file and `CLAUDE.md`, can pick up exactly where the last one stopped. Keep it that way:
update the **Start here** and **In flight** sections at the end of every working session, before
the context runs out.

**Last updated:** 2026-07-31, mid-session.

---

## Start here

Do these in order at the beginning of a session, before starting anything new.

1. **Re-read real git state.** The snapshot below goes stale the moment another session commits.

   ```bash
   git fetch origin && git log --oneline -3 origin/master && git status -sb
   gh pr list --repo roope242/Twitch-Channel-Points-Miner-v2 --state open
   ```

2. **Re-trigger any CodeRabbit review that was blocked by the quota.** When a session ends because
   CodeRabbit hit its review limit, the next session's *first* action is to ask for the review
   again — the rolling window has usually cleared overnight:

   ```bash
   gh pr comment <N> --repo roope242/Twitch-Channel-Points-Miner-v2 --body "@coderabbitai review"
   ```

   Then confirm a real review landed, rather than trusting the bot's chat reply. **Do not use
   `gh api .../pulls/<N>/reviews` for this — it stays empty even after a completed review.**
   CodeRabbit does not submit a formal GitHub review; it **edits its existing summary comment in
   place**. Watch `updated_at` on that comment:

   ```bash
   gh api repos/roope242/Twitch-Channel-Points-Miner-v2/issues/<N>/comments \
     --jq '.[] | "id=\(.id) \(.user.login) created=\(.created_at) updated=\(.updated_at)"'
   gh api repos/roope242/Twitch-Channel-Points-Miner-v2/issues/comments/<id> --jq .body
   ```

   A bumped `updated_at` on the bot's comment is the signal the run finished — polling for a *new*
   comment misses it entirely. Inline findings, when there are any, appear separately in
   `gh api .../pulls/<N>/comments`. Read the body's "Recent review info" block for the commit range
   and compare it against the branch head: CodeRabbit is incremental and will not re-examine commits
   it has already seen, so the commits that fix its own findings are exactly the ones most likely to
   go unreviewed.

   If the comment still says the limit is reached, stop — re-posting burns quota and pushes the
   window out. **Record the absolute reset time before ending the session.** The notice only gives a
   relative "next review available in N minutes", which is worthless read a day later; convert it to
   a wall-clock timestamp and put it in the "In flight" table, so the next session knows whether the
   window has actually cleared instead of guessing.

   **Currently blocked:** nothing.

3. **Pick up the task named in "Next up"** below.

---

## In flight

| What | Where | State |
|---|---|---|
| `master` | `12074c8` | Clean, pushed. |
| **PR #22** — issue #12, untrusted-text sinks | branch `fix/untrusted-text-sinks`, head `07e94d1` | Open. Code complete and verified. **Reviewed clean 2026-07-31** — "no actionable comments", range `34c1181..07e94d1`, which is the branch head. Ready to merge. |

Nothing else is in progress. Stale local branches from merged PRs (`fix/shutdown-hang`,
`fix/stale-dashboard-assets`, `chore/coderabbit-config`, `docs/claude-md-session-learnings`) can be
deleted when convenient — ask first, branch deletion is destructive.

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

**When PR #22 merges, do #21.** Same file as #12 (`assets/script.js`), so it needs a rebase if it
starts first — and #12 is the more important of the two.

The only user-visible defect in #21 is the log polling. `setTimeout(getLog, 1000)` sits *inside*
the `$.get` success callback, so one failed request permanently ends log auto-refresh until the
user toggles the checkbox by hand. `getStreamerData`'s 5-minute refresh has the same shape, and
`getStreamers` failing leaves the dashboard silently empty. The refresh-followers button at
`script.js:114` already uses `.done()/.fail()/.always()` correctly — copy that pattern, moving the
re-schedule into `.always()`.

The other three in #21 are cosmetic: duplicate `#annotations`/`#dark-mode` bindings (`:187`/`:194`
inside `$(document).ready` and again at `:388`/`:391` top level), an implicit-global `displayname`
at `:325`, and missing SRI on four CDN includes in `charts.html:13-16`.

Deliberately *not* in #21: `getAllStreamersData()` at `:290` is uncalled but is the only client of
the live `/json_all` route (`AnalyticsServer.py:157`, registered at `:311`). Deleting it orphans a
working endpoint. Leave it until someone decides whether the multi-streamer chart view is wanted.

**#23 is worth doing before #21, not after.** It is an XS config-only change that shrinks every
subsequent review comment, so landing it first makes each later review cheaper to read. It is not a
code fix, so it needs no PR.

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
| 12 | Untrusted text reaches HTML and URL sinks | M | Med–High | Med | **PR #22 open** — reviewed clean, ready to merge |
| 23 | `.coderabbit.yaml` output is mostly packaging | XS | n/a — tooling | n/a | Open |
| 21 | Dashboard JS: log polling dies on one failed request | S | Low–Med | Med | Open — next |
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

- **Every code fix goes through a PR.** Branch off `master`, commit, push, `gh pr create` against
  `roope242/master`. Wait for CodeRabbit, act on the substantive findings, then merge without
  waiting for sign-off. Judgment still applies — CodeRabbit's findings are claims to verify against
  the code, and pushing back in the thread is the right response when it is wrong.
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
  **Open question, decide before the first upstream PR:** every commit here carries
  `Co-Authored-By: Claude …` and `Claude-Session: …` trailers, and `git cherry-pick` brings them
  along, so a cherry-picked upstream branch announces it in the commit metadata regardless of what
  the body says. Either strip the trailers while rebuilding the branch or accept that they show.
- **A chat reply is not a review — and neither is an empty `pulls/N/reviews`.** CodeRabbit submits
  no formal review at all; it edits its summary comment in place, so that endpoint stays empty
  forever and proves nothing either way. Check the comment's `updated_at` and its "Recent review
  info" commit range against the branch head — see "Start here" step 2 for the commands.
- **"Review limit reached" means stop.** Do not re-trigger while blocked. Convert the notice's
  relative "next review available in N minutes" into an absolute time, record it in "In flight",
  end the session, and re-trigger first thing the next one — see "Start here" step 2.
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
