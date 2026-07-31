#!/usr/bin/env bash
# Wait for CodeRabbit to reach a verdict on a PR, then print it.
#
# Why this exists: CodeRabbit submits no formal GitHub review, so
# `gh api repos/OWNER/REPO/pulls/N/reviews` returns [] forever and polling it
# never fires. It edits its *existing* summary comment in place, so polling for
# a new comment also misses. The only reliable signal is a terminal marker in
# the body of one of its comments.
#
# Usage:
#   scripts/cr-wait.sh <pr-number>
#
# Environment:
#   REPO      owner/name           (default: roope242/Twitch-Channel-Points-Miner-v2)
#   INTERVAL  seconds between polls (default: 20)
#   TIMEOUT   seconds before giving up (default: 1800)
#   SINCE     epoch seconds; only comments updated at or after this count.
#             Defaults to start time, so a stale verdict from an earlier run is
#             ignored. Trigger the review first, then run this. SINCE=0 reports
#             whatever state already exists.
#
# Exit codes: 0 verdict reached, 2 quota-blocked, 3 timed out.
set -uo pipefail

PR=${1:?usage: cr-wait.sh <pr-number>}
REPO=${REPO:-roope242/Twitch-Channel-Points-Miner-v2}
INTERVAL=${INTERVAL:-20}
TIMEOUT=${TIMEOUT:-1800}
SINCE=${SINCE:-$(date -u +%s)}

started=$(date -u +%s)
deadline=$((started + TIMEOUT))

while :; do
    # Every bot comment, newest first, that changed at or after SINCE. The
    # verdict can land in the original summary comment (edited in place) or in a
    # later one, so all of them are examined rather than just the newest.
    payload=$(gh api "repos/$REPO/issues/$PR/comments" --paginate \
        --jq '[.[] | select(.user.login == "coderabbitai[bot]")
               | {id, updated: .updated_at, body}] | reverse')

    inline=$(gh api "repos/$REPO/pulls/$PR/comments" --jq 'length')

    verdict=$(SINCE="$SINCE" INLINE="$inline" python3 - "$payload" <<'PY'
import json, sys, os, datetime, re

comments = json.loads(sys.argv[1] or "[]")
since = int(os.environ["SINCE"])
inline = int(os.environ["INLINE"])

def epoch(ts):
    return int(datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
               .replace(tzinfo=datetime.timezone.utc).timestamp())

# Marker choice matters. "No actionable comments were generated" is NOT durable:
# CodeRabbit re-edited PR #22's comment after the merge and dropped that line,
# leaving only the walkthrough. So a structural marker is checked too -- a
# walkthrough is only ever produced by a review that actually ran.
for c in comments:
    if epoch(c["updated"]) < since:
        continue
    body = c["body"] or ""

    # The HTML marker is the reliable one; the prose is localised and edited.
    if "rate limited by coderabbit.ai" in body or "Review limit reached" in body:
        mins = re.search(r"Next review available in:\*{0,2}\s*\*{0,2}(\d+)\s*minute", body)
        reset = ""
        if mins:
            when = datetime.datetime.fromtimestamp(
                epoch(c["updated"]) + int(mins.group(1)) * 60,
                datetime.timezone.utc)
            reset = when.strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"BLOCKED\t{c['id']}\t{reset}")
        break

    ran = ("walkthrough_start" in body
           or "No actionable comments" in body
           or "Actionable comments posted:" in body)
    if not ran:
        continue

    m = re.search(r"Actionable comments posted:\s*(\d+)", body)
    count = int(m.group(1)) if m else inline
    print(f"{'FINDINGS' if count else 'CLEAN'}\t{c['id']}\t{count}")
    break
else:
    print("PENDING\t\t")
PY
    )

    state=$(cut -f1 <<<"$verdict")
    cid=$(cut -f2 <<<"$verdict")
    detail=$(cut -f3 <<<"$verdict")
    now=$(date -u +%s)
    elapsed=$((now - started))

    case "$state" in
    CLEAN | FINDINGS)
        body=$(gh api "repos/$REPO/issues/comments/$cid" --jq .body)
        echo "VERDICT: $state after ${elapsed}s"
        echo "  comment $cid: $(wc -c <<<"$body") bytes, $(wc -l <<<"$body") lines"
        echo "  actionable comments posted: ${detail:-0}"
        echo "  inline review comments:     $inline"
        # The range it actually covered -- compare against the branch head, since
        # CodeRabbit is incremental and skips commits it has already seen.
        grep -o 'between [0-9a-f]\{40\} and [0-9a-f]\{40\}' <<<"$body" | tail -1
        exit 0
        ;;
    BLOCKED)
        echo "BLOCKED: quota, review never started (after ${elapsed}s)"
        echo "  next review available: ${detail:-unknown}"
        echo "  Record that absolute time in ISSUES.md; do not re-trigger before it."
        exit 2
        ;;
    esac

    if ((now >= deadline)); then
        echo "TIMEOUT: no verdict after ${elapsed}s (still PENDING)"
        exit 3
    fi
    sleep "$INTERVAL"
done
