#!/usr/bin/env bash
# loop.sh · closed-loop prompt runner for the remaining /ship sessions.
#
# Runs the remaining prompts back-to-back, headless (claude -p). Between prompts it
# verifies the completion contract and HALTS TO THE OWNER with a reason if anything
# misses. The gate-01 plan approval is pre-approved inside each prompt file (owner,
# 13 Jun); everything else (freeze line, green-contract, ratchet) still applies.
#
# Usage:
#   bash tools/loop.sh                 # run all prompts that are not yet done
#   bash tools/loop.sh 06 07          # run only these
#   LOOP_CMD='true' bash tools/loop.sh 06   # DRY RUN: replace claude with any command
#
# Contract between prompts (all must hold, else halt):
#   1. zero CAS ratchet regressions          (tools/cas_check.py --ci)
#   2. CAS floor non-decreasing              (totals.passed vs start of step)
#   3. clean working tree                    (the session merged its own PR)
#   4. latest CI run on main = success       (gh run list)
#
# Log: .shipboard/loop.log (also tail -f friendly while the board runs).

set -u
cd "$(git rev-parse --show-toplevel 2>/dev/null || dirname "$0")/." || exit 1

PROMPTS_DEFAULT=(05 06 07)
PROMPTS=("${@:-${PROMPTS_DEFAULT[@]}}")
LOG=".shipboard/loop.log"
mkdir -p .shipboard
CLAUDE_CMD="${LOOP_CMD:-claude -p --permission-mode acceptEdits --max-turns 400}"

say() { printf '%s %s\n' "$(date '+%H:%M:%S')" "$*" | tee -a "$LOG"; }

floor_passed() {
    python3 tools/cas_check.py --json 2>/dev/null \
      | python3 -c 'import json,sys;print(json.load(sys.stdin)["totals"]["passed"])' 2>/dev/null \
      || echo 0
}

contract() {
    local before="$1" why=""
    python3 tools/cas_check.py --ci >/dev/null 2>&1 || why="CAS ratchet regression (tools/cas_check.py --ci failed)"
    local after; after=$(floor_passed)
    [ -z "$why" ] && [ "$after" -lt "$before" ] && why="CAS floor decreased ($before → $after)"
    # live-state files the loop/board write themselves never count as dirt:
    # .shipboard/ (gitignored in the repo) and the ratchet baseline (board writes it
    # asynchronously when the floor grows; the growth itself is validated above).
    local dirt; dirt=$(git --no-optional-locks status --porcelain 2>/dev/null \
        | grep -v -e ' \.shipboard/' -e ' tools/cas_baseline\.json$' || true)
    [ -z "$why" ] && [ -n "$dirt" ] && why="working tree not clean (session did not finish its merge): $(echo "$dirt" | head -3 | tr '\n' ' ')"
    if [ -z "$why" ] && command -v gh >/dev/null 2>&1; then
        local ci; ci=$(gh run list --branch main -L 1 --json conclusion -q '.[0].conclusion' 2>/dev/null || echo "")
        [ -n "$ci" ] && [ "$ci" != "success" ] && why="latest CI on main is '$ci', not success"
    fi
    [ -z "$why" ] && return 0
    say "HALT: $why"
    say "→ fix it (or ask Fable why), then rerun: bash tools/loop.sh ${REMAINING[*]:-}"
    return 1
}

say "loop start · prompts: ${PROMPTS[*]} · cmd: ${CLAUDE_CMD%% *}"
for i in "${!PROMPTS[@]}"; do
    n="${PROMPTS[$i]}"
    REMAINING=("${PROMPTS[@]:$i}")
    f=$(ls prompts/${n}_*.md 2>/dev/null | head -1)
    [ -z "$f" ] && { say "HALT: no prompt file for '$n'"; exit 1; }
    before=$(floor_passed)
    say "── prompt $n: $f (floor $before)"
    if [ -n "${LOOP_CMD:-}" ]; then
        $CLAUDE_CMD || { say "HALT: prompt $n command failed (exit $?)"; exit 1; }
    else
        claude -p "$(cat "$f")" --permission-mode acceptEdits --max-turns 400 2>&1 | tee -a "$LOG"
        rc=${PIPESTATUS[0]}
        [ "$rc" -ne 0 ] && { say "HALT: prompt $n session exited $rc"; exit 1; }
    fi
    contract "$before" || exit 1
    say "✓ prompt $n complete · contract green · floor $(floor_passed)"
done
say "loop done · all prompts green. Curate today's journal (vault/daily/), then /cas-audit."
