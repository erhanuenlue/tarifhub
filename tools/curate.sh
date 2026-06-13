#!/usr/bin/env bash
# curate.sh · journal + fazit-notes curation via Codex (gpt-5.5).
# Owner decision 13 Jun: journal and fazit-note drafting is fully delegated to AI;
# the owner edits whatever he wants before submission, at his discretion.
#
# Usage: bash tools/curate.sh [YYYY-MM-DD]    (default: today)
# Called automatically by tools/loop.sh: at loop start (catch-up for the latest
# draft, e.g. the manual prompt-05 session), after every green prompt, and after
# the closing audit. Default date = the newest vault/daily/ file.
#
# Codex runs sandbox read-only: it only generates text; this script does the writing.

set -u
cd "$(git rev-parse --show-toplevel 2>/dev/null || dirname "$0")/." || exit 1

D="${1:-}"
if [ -z "$D" ]; then
    LATEST=$(ls vault/daily/*.md 2>/dev/null | sort | tail -1)
    if [ -n "$LATEST" ]; then D=$(basename "$LATEST" .md); else D=$(date +%F); fi
fi
J="vault/daily/$D.md"
N="vault/fazit-notes.md"

[ -f "$J" ] || { echo "curate: no journal draft at $J, nothing to do"; exit 0; }
command -v codex >/dev/null 2>&1 || { echo "curate: codex CLI not found"; exit 1; }

FACTS=$(git --no-optional-locks log --since "$D 00:00" --until "$D 23:59" --oneline 2>/dev/null | head -40)

BRIEF="You curate a developer journal for a graded CAS project (AI-assisted software engineering, FFHS).
Rules: facts only, never invent anything not present in the material below; first person;
keep the draft's language; keep every commit ref and diff pointer; explicitly mark where AI
suggestions were accepted, corrected or rejected; no em-dashes; no praise, no filler.
Task 1: rewrite the journal draft into a clean entry.
Task 2: propose up to 2 one-line Fazit notes (veto moments, surprises, corrections),
grounded only in the material; output zero notes rather than a generic one.
Answer in exactly this format and nothing after END:
JOURNAL-START
(full new content of the journal file)
NOTES-START
(0 to 2 lines, each starting with '- ')
CURATE-END

Today's commits:
$FACTS

Journal draft:
$(cat "$J")"

OUT=$(codex exec "$BRIEF" 2>/dev/null) || { echo "curate: codex failed, draft untouched"; exit 1; }

# codex echoes the prompt (which contains the markers) before the answer:
# always cut at the LAST occurrence of each marker.
TAIL=${OUT##*JOURNAL-START}
NEW=${TAIL%%NOTES-START*}
REST=${TAIL##*NOTES-START}
NOTES=$(printf '%s' "${REST%%CURATE-END*}" | grep '^- ' || true)
# trim leading/trailing blank lines
NEW=$(printf '%s' "$NEW" | sed -e '/./,$!d' | sed -e ':a' -e '/^\s*$/{$d;N;ba' -e '}')

if [ "${#NEW}" -lt 120 ]; then
    echo "curate: extracted content too short (${#NEW} chars), draft untouched"
    exit 1
fi
printf '%s\n' "$NEW" > "$J"

if [ -n "$NOTES" ]; then
    { echo ""; echo "## $D"; printf '%s\n' "$NOTES"; } >> "$N"
fi
# Commit + push the two vault files only ([skip ci], same pattern as vault_autocommit),
# so the next loop iteration's clean-tree contract and phase-09 auto-merge are unaffected.
if [ -n "$(git --no-optional-locks status --porcelain -- "$J" "$N" 2>/dev/null)" ]; then
    git add -- "$J" "$N" 2>/dev/null
    if git commit -q -m "vault: curate journal $D via gpt-5.5 [skip ci]" -- "$J" "$N" 2>/dev/null; then
        git push -q 2>/dev/null || echo "curate: committed; push failed, the next session's autocommit will push"
    else
        echo "curate: nothing committed, check git identity/state"
    fi
fi
echo "curate: $J rewritten$( [ -n "$NOTES" ] && echo "; fazit notes appended" )"
