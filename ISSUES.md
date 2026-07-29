# Open issues: triage and fix order

Fork-local planning document for `roope242/Twitch-Channel-Points-Miner-v2`. Not upstream's
tracker — see `CLAUDE.md` for the fork/upstream relationship and the rule about never opening an
upstream PR from `master`.

Last updated 2026-07-29, after closing #4.

## Effort/gain table

"Gain (config)" is measured against the current `run.py`: `make_predictions=False`,
`claim_drops=False`, `chat=ChatPresence.NEVER`, no notifiers, `enable_analytics=True`,
`file_level=DEBUG`, and an IPv4-only `getaddrinfo` monkeypatch. "Gain (general)" is for a typical
user with the defaults.

| # | Title | Effort | Gain (config) | Gain (general) | Status |
|---|---|---|---|---|---|
| ~~9~~ | Client version refetched per GQL request | S | High | High | **Closed** — fd55fe6 |
| ~~5~~ | Blanket `except Exception` hides PubSub bugs | XS | High | High | **Closed** — 5ca56fd |
| ~~15~~ | Assorted small correctness bugs | XS | Low | Low | **Closed** — 1691aff |
| ~~6~~ | No HTTP request timeouts | S–M | Med | High | **Closed** — see below |
| ~~14~~ | Shutdown hangs forever and re-enters itself | S–M | Med | Med | **Closed** — PR #17 |
| ~~4~~ | `check_assets()` never updates existing assets | S–M | Med | Med | **Closed** — PR #20 |
| 12 | Untrusted text reaches HTML and URL sinks | M | Med–High | Med | Open — next |
| 21 | Dashboard JS: log polling dies on one failed request | S | Low–Med | Med | Open |
| 13 | Device-code login: dead expiry check, no timeout | S | Low | Med | Open |
| 10 | PubSub reconnection blocks main loop, races itself | L | High | High | Open |
| 16 | Startup primes streamers in two sequential loops | M–L | Low | Low | Open |
| 7 | Notifiers run inside the log formatter | M | **Zero** | High | Open — upstream candidate |
| 11 | Bet sizing and filtering bugs | S–M | **Zero** | High | Open — upstream candidate |

Two entries have zero gain under the current config because they sit on disabled code paths
(`make_predictions=False` for #11, no notifiers configured for #7). They are still real bugs for
other users, which is what makes them the two best upstream candidates rather than the two best
things to fix here.

## Recommended path

### Phase 1 — cheap, and makes everything else observable

**#15 — assorted small correctness bugs.** Three independent one-liners: `percentage(a, 0)`
raises `ZeroDivisionError` because the short-circuit guards the numerator; `GQLOperations.
PersonalSections` is a 1-tuple from a stray trailing comma; a `pop` without a default. Each is
self-contained with no design decision attached. Do them directly, no delegation — they are
exempt as trivial edits.

Note the honest caveat already in the issue: the `percentage` path runs through `Drop.py`, and
drops are disabled in this config, so reachability there is unconfirmed.

**#6 — HTTP request timeouts.** Done: `REQUESTS_TIMEOUT = 10` applied at all 19 live call sites,
and the GitHub version check moved to a fire-and-forget daemon thread.

The measured behaviour is worth recording, because the timeout alone is genuinely not a fix.
`requests` applies the timeout *per connection attempt*, so on this host — where IPv6 egress is
blackholed — `check_versions()` takes **40.3s** (4 AAAA records x 10s) before falling back to
IPv4 and succeeding. That is why part 2 mattered more than part 1: the version check is now on a
daemon thread, so its 40s worst case delays nothing.

Which hosts this actually affects, measured rather than assumed:

| host | AAAA records | latency with blackholed IPv6 |
|---|---|---|
| `raw.githubusercontent.com` | 4 | ~40s |
| `gql.twitch.tv` | 1 | 0.3s |
| `www.twitch.tv` | 1 | 0.1s |

So the Twitch hosts are unaffected and only the GitHub-hosted calls are slow — `check_versions`
(now backgrounded) and `download_file` (only runs when assets are missing, on the analytics
daemon thread). On that evidence the IPv4-only `getaddrinfo` monkeypatch at the top of `run.py`
looks removable, but **this has not been confirmed with a live run** — verify before deleting it.

### Phase 2 — user-visible correctness

**#14 — shutdown.** Done in PR #17. Bounded joins, a dedicated `shutting_down` re-entrancy guard,
and SIGSEGV dropped from the handled signals.

Two things review caught that the issue itself missed, both worth remembering:

- **Bounded joins alone did not fix it.** The worker threads were non-daemon, and `sys.exit(0)`
  only raises `SystemExit` on the main thread — Python then waits on every non-daemon thread at
  interpreter shutdown. A stuck worker produced the new warning and hung anyway. Measured with a
  deliberately stuck thread: non-daemon had to be killed externally, daemon exits 0. All three
  workers are now `daemon=True`.
- **The issue's finding 1 was wrong about chat.** `leave_chat()` rebinds `streamer.irc_chat` to a
  fresh, never-started thread, so the chat join was always operating on something whose
  `is_alive()` is `False`. That branch could never have hung, before or after. The minute-watcher
  and sync-campaigns joins it named were real.

Still unverified: the join-timeout warning branches themselves. Forcing a genuinely stuck worker
needs a live session, so they are read-correct but have not been observed firing.

**#4 — dashboard assets never refresh.** Done in PR #20. The assets now live in
`TwitchChannelPointsMiner/assets/` and ship with the package; `check_assets()` copies them into
the working-directory `assets/` and overwrites on a sha256 mismatch. `download_assets()` and
`utils.download_file()` are gone — nothing fetches assets over the network anymore.

The download source turned out to be the deeper problem, not just the trigger. `GITHUB_url` points
at upstream `rdavydov/master`, so a naive refresh-on-mismatch would have *overwritten* fork-local
asset changes — the refresh-followers button among them — with upstream's version on every start.

Still unverified: that `MANIFEST.in` actually places the assets in a built sdist. `setuptools` and
`build` are not installed in `.venv`, so no distribution was built. The runtime path is proven —
`check_assets()` resolves the packaged folder via `os.path.dirname(__file__)/../assets`, which
works from a checkout regardless of packaging.

**#12 — untrusted text in HTML and URL sinks.** Fix at the **sink**, not the producers:
`.text(...)` instead of `.append(...)` in `assets/script.js:136`. The amendment on the issue
explains why escaping producers is the wrong layer — the untrusted text arrives as raw GQL
response bodies logged at DEBUG (`Twitch.py:297`), not through any formatted message, so a
producer-side fix would have missed it entirely. Note this depends on #4 shipping first, or the
fix will not reach anyone with existing assets.

Separately worth deciding on its own merits: whether logging entire response bodies at DEBUG is
wanted at all, given it also writes auth-adjacent payloads to disk in plaintext.

**#21 — dashboard JS defects.** Same file as #12, so whichever lands second needs a rebase; do #12
first, it matters more. Surfaced by CodeRabbit reviewing #20: the move made `script.js` and
`charts.html` read as newly added, so a reviewer looked at them for the first time. All four are
pre-existing and were verified against the code before filing.

Only one is user-visible: `setTimeout(getLog, 1000)` sits *inside* the `$.get` success callback, so
a single failed request permanently ends log auto-refresh until the user toggles the checkbox by
hand. `getStreamerData`'s 5-minute refresh has the same shape. The refresh-followers button already
uses `.done()/.fail()/.always()` correctly and is the pattern to copy.

The rest are cosmetic: duplicate `#annotations`/`#dark-mode` bindings, an implicit-global
`displayname`, and missing SRI on four CDN includes.

Worth recording as a review pattern: **a pure `git mv` makes a reviewer read the moved file as new
code.** Expect findings that predate the change. Keeping the move at 100% similarity is what lets
the next reader confirm it was faithful without diffing contents — so file the findings rather than
folding them in, and say so in the PR. CodeRabbit withdrew all five on that argument.

### Phase 3 — larger

**#10 — PubSub reconnection.** Highest absolute value left, and the largest. Two distinct
problems: reconnection runs synchronously on the main loop and parks the whole daemon, and the
`is_reconnecting` guard is a non-atomic check-then-act reached from four threads. Delegate with
care and read the threading rules in `CLAUDE.md` first — `self.streamers` is mutated only from
the main thread, `self.streamers`/`self.original_streamers` are index-parallel, and the list is
passed by reference into every `TwitchWebSocket` so it must never be rebound.

**#13 — device-code login.** Small, but low value here since valid cookies mean this path is
rarely touched. Reasonable to batch with an upstream submission rather than do standalone.

**#16 — startup sequencing.** Deliberately last. It saves ~60–90s once per start on a process
that runs for days, and it is the change most likely to introduce a threading bug for that
payoff. Both the effort and the risk are real; the gain is not.

### Not for this fork

**#7 and #11** are the two strongest upstream candidates: real bugs, reproducible, on code paths
upstream's users actually run, and both fail in a direction that costs the user something. Per
the upstream-contribution rules they should go out as focused PRs branched from
`upstream/master`, not carried here indefinitely. #7 additionally looks like the cause of
upstream's open #805, which is worth saying in the PR.

## Verification reality

There is no test suite and nothing runs without live Twitch auth. `python3 -m py_compile` is the
only offline check. A live run is available (`.venv/bin/python -u run.py`, use `-u`) and is the
only way to confirm anything end to end — priming ~74 followers takes ~2 minutes before the main
loop starts.

Because of the PubSub catch-all — narrowed but not removed in #5 — "no crash" is still not
evidence that a branch works. Anything touching `on_message` must be verified by observing the
intended side effect.
