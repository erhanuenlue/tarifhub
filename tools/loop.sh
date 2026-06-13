#!/usr/bin/env bash
# loop.sh · closed-loop prompt runner for the remaining /ship sessions.
#
# Runs the remaining prompts back-to-back, headless (claude -p). Between prompts it
# verifies the completion contract and HALTS TO THE OWNER with a reason if anything
# misses. The gate-01 plan approval is pre-approved inside each prompt file (owner,
# 13 Jun); everything else (freeze line, green-contract, ratchet) still applies.
#
# Usage:
#   bash tools/loop.sh                 # runs 06 then 07 (05 is the manual dress rehearsal)
#   bash tools/loop.sh 05 06 07       # override the prompt list
#   LOOP_CMD='true' bash tools/loop.sh 06   # DRY RUN: replace claude with any command
#
# Contract between prompts (all must hold, else halt):
#   1. zero CAS ratchet regressions          (tools/cas_check.py --ci)
#   2. CAS floor non-decreasing              (totals.passed vs start of step)
#   3. clean working tree                    (the session merged its own PR)
#   4. no secret leak                        (gitleaks, or key-shaped grep fallback)
#   5. latest CI run on main = success       (gh run list)
#
# Log: .shipboard/loop.log (also tail -f friendly while the board runs).

set -u
cd "$(git rev-parse --show-toplevel 2>/dev/null || dirname "$0")/." || exit 1

PROMPTS_DEFAULT=(06 07)   # 05 runs manually per NEXT_STEPS; pass numbers to override
PROMPTS=("${@:-${PROMPTS_DEFAULT[@]}}")
LOG=".shipboard/loop.log"
mkdir -p .shipboard
# Quality before cost (owner law, 13 Jun): headless sessions run the same orchestrator
# as manual ones. Resolution: LOOP_MODEL env > .claude/settings.json "model" (ADR-018,
# switch with tools/switch_model.sh) > fallback.
SETTINGS_MODEL=$(python3 -c 'import json;print(json.load(open(".claude/settings.json")).get("model",""))' 2>/dev/null || true)
LOOP_MODEL="${LOOP_MODEL:-${SETTINGS_MODEL:-claude-opus-4-8}}"
QUALITY_PREFIX="Owner standing order (quality before cost): run at ultracode effort throughout, maximum reasoning, do not down-shift to save tokens. This is a long unattended run: your context auto-compacts, so do not stop early for token-budget reasons, and checkpoint progress and state to .shipboard/loop-checkpoint.md before continuing."
CLAUDE_CMD="${LOOP_CMD:-claude -p --model $LOOP_MODEL --permission-mode bypassPermissions --max-turns 400}"

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
    # live-state files the loop/board/hooks generate never count as dirt:
    # .shipboard/ (gitignored), the ratchet baseline (board writes it asynchronously when
    # the floor grows; the growth itself is validated above), and vault/00-index.md (the
    # brain_sync hook regenerates it at session end, including a minute-resolution
    # timestamp, so it can land uncommitted after the session's own commits; the vault
    # autocommit hook carries it on the next session end).
    local dirt; dirt=$(git --no-optional-locks status --porcelain 2>/dev/null \
        | grep -v -e ' \.shipboard/' -e ' tools/cas_baseline\.json$' -e ' vault/00-index\.md$' || true)
    [ -z "$why" ] && [ -n "$dirt" ] && why="working tree not clean (session did not finish its merge): $(echo "$dirt" | head -3 | tr '\n' ' ')"
    # Local secret gate (public-repo safety): catch a leak immediately, before it can
    # ride a fast loop into a public repo, independent of CI timing. gitleaks if present,
    # else a key-shaped grep over tracked files. CI's gitleaks job is the backstop.
    if [ -z "$why" ]; then
        if command -v gitleaks >/dev/null 2>&1; then
            gitleaks detect --no-banner -r /tmp/.gl.json >/dev/null 2>&1 || why="gitleaks found a secret (see /tmp/.gl.json) — do not push public"
        else
            local hit; hit=$(git --no-optional-locks grep -nIE \
                "sk-ant-[A-Za-z0-9]|sk-[A-Za-z0-9]{20}|ghp_[A-Za-z0-9]{36}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----" \
                -- ':!*.example' ':!prompts/*' ':!tools/loop.sh' 2>/dev/null | head -1 || true)
            [ -n "$hit" ] && why="possible secret in tracked file: ${hit%%:*} — do not push public"
        fi
    fi
    if [ -z "$why" ] && command -v gh >/dev/null 2>&1; then
        local ci; ci=$(gh run list --branch main -L 1 --json conclusion -q '.[0].conclusion' 2>/dev/null || echo "")
        [ -n "$ci" ] && [ "$ci" != "success" ] && why="latest CI on main is '$ci', not success"
    fi
    [ -z "$why" ] && return 0
    say "HALT: $why"
    say "→ fix it (or ask the orchestrator why), then rerun: bash tools/loop.sh ${REMAINING[*]:-}"
    return 1
}

say "loop start · prompts: ${PROMPTS[*]} · model: $LOOP_MODEL · cmd: ${CLAUDE_CMD%% *}"
bash tools/curate.sh >>"$LOG" 2>&1 && say "catch-up: latest journal draft curated" || say "note: catch-up curation skipped (see $LOG)"
for i in "${!PROMPTS[@]}"; do
    n="${PROMPTS[$i]}"
    REMAINING=("${PROMPTS[@]:$i}")
    f=$(ls prompts/${n}_*.md 2>/dev/null | head -1)
    [ -z "$f" ] && { say "HALT: no prompt file for '$n'"; exit 1; }
    before=$(floor_passed)
    say "── prompt $n: $f (floor $before)"
    : > .shipboard/events.jsonl 2>/dev/null || true   # fresh pipeline rail per prompt
                                                       # (emits are also session-gated in the board)
    if [ -n "${LOOP_CMD:-}" ]; then
        $CLAUDE_CMD || { say "HALT: prompt $n command failed (exit $?)"; exit 1; }
    else
        claude -p "$QUALITY_PREFIX

$(cat "$f")" --model "$LOOP_MODEL" --permission-mode bypassPermissions --max-turns 400 2>&1 | tee -a "$LOG"
        rc=${PIPESTATUS[0]}
        [ "$rc" -ne 0 ] && { say "HALT: prompt $n session exited $rc"; exit 1; }
    fi
    contract "$before" || exit 1
    bash tools/curate.sh >>"$LOG" 2>&1 || say "note: journal curation skipped (see $LOG)"
    say "✓ prompt $n complete · contract green · floor $(floor_passed)"
done
AUDIT_PROMPT="Run the cas-audit skill exactly as defined in .claude/skills/cas-audit/SKILL.md: dispatch the grade-auditor agent, have it write vault/cas-audit/<today>.md and <today>.json (today's real date), then stop."
say "post-loop: running /cas-audit (grade estimate → CAS tab)"
if [ -n "${LOOP_CMD:-}" ]; then
    $CLAUDE_CMD || say "note: audit step failed (dry mode)"
else
    claude -p "$AUDIT_PROMPT" --model "$LOOP_MODEL" --permission-mode bypassPermissions --max-turns 120 2>&1 | tee -a "$LOG" || say "note: audit session failed, run /cas-audit in any session instead"
fi
# Independent second opinion on the grade estimate (owner decision 13 Jun): gpt-5.5
# reads the Opus auditor's report + the criterion map and flags disagreements/missed gaps.
if command -v codex >/dev/null 2>&1; then
    AUD=$(ls vault/cas-audit/2*.md 2>/dev/null | sort | tail -1)
    if [ -n "$AUD" ] && [ -f docs/criterion-map.md ]; then
        say "post-loop: codex second opinion on the grade estimate"
        SO=$(codex exec "Independent second opinion on a CAS grade estimate. Below are (1) the auditor's estimate and (2) the criterion map of the project. Do not re-estimate everything: flag only DISAGREEMENTS (criteria you would score differently, with the reason) and MISSED GAPS (risks the auditor did not list). Be specific, cite criteria numbers. If you agree fully, say so in one line.

=== AUDITOR ESTIMATE ===
$(cat "$AUD")

=== CRITERION MAP ===
$(cat docs/criterion-map.md)" 2>/dev/null)
        if [ -n "$SO" ]; then
            printf '%s
' "$SO" | tail -n +2 > "vault/cas-audit/codex-second-opinion-$(date +%F).md"
            git add vault/cas-audit/ 2>/dev/null
            git commit -q -m "vault: codex second opinion on grade estimate [skip ci]" -- vault/cas-audit/ 2>/dev/null && git push -q 2>/dev/null
            say "second opinion written: vault/cas-audit/codex-second-opinion-$(date +%F).md"
        fi
    fi
fi
bash tools/curate.sh >>"$LOG" 2>&1 || true
say "loop done · all prompts green · journal curated · audit estimate on the CAS tab."
say "the only thing left that is yours: the Eigenständigkeitserklärung (NEXT_STEPS step 5)."
