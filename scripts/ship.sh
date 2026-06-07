#!/usr/bin/env bash
#
# ship.sh — the autonomous branch -> commit -> push -> PR -> Codex-review (-> merge) flow.
#
# RUN THIS ON YOUR MACHINE (or via Claude Code's /ship on your machine). The GitHub CLI
# (`gh`) must be installed AND authenticated (`gh auth login`); gh is NOT in the build
# sandbox or CI. The Codex review step uses the Codex CLI (`codex exec`) if installed; if
# not, it leaves a note and you run /review-codex inside Claude Code instead. The user never
# runs git by hand — this script (driven by Claude) does all of it. See docs/START_GUIDE.md.
#
# Usage:
#   scripts/ship.sh "feat(intelligence): add cumulation rule"   # branch, commit, push, PR, review
#   scripts/ship.sh --merge                                     # squash-merge the current PR

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BASE_BRANCH="${BASE_BRANCH:-main}"
REVIEW_FILE="$ROOT/.codex-review.md"

require_gh() {
  command -v gh >/dev/null 2>&1 || { echo "ERROR: gh not found. Install it + 'gh auth login'." >&2; exit 1; }
  gh auth status >/dev/null 2>&1 || { echo "ERROR: gh not authenticated. Run 'gh auth login'." >&2; exit 1; }
}

# --- merge mode -----------------------------------------------------------------------
if [ "${1:-}" = "--merge" ]; then
  require_gh
  echo "Merging the current branch's PR (squash, delete branch) ..."
  # Prefer auto-merge (waits for required checks); fall back to an immediate squash merge.
  gh pr merge --squash --delete-branch --auto \
    || gh pr merge --squash --delete-branch
  git switch "$BASE_BRANCH" 2>/dev/null || true
  git pull --ff-only origin "$BASE_BRANCH" 2>/dev/null || true
  echo "Merged."
  exit 0
fi

# --- ship mode ------------------------------------------------------------------------
MSG="${1:-}"
[ -z "$MSG" ] && {
  echo "usage: ship.sh \"<conventional commit subject>\"   |   ship.sh --merge" >&2
  exit 1
}
require_gh

# Enforce Conventional Commits so history stays releasable.
if ! printf '%s' "$MSG" | grep -Eq '^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9_-]+\))?!?: .+'; then
  echo "ERROR: commit subject must follow Conventional Commits, e.g." >&2
  echo "       feat(intelligence): add cumulation rule" >&2
  exit 1
fi

# Fast determinism guard BEFORE anything remote — never ship across a broken freeze line.
echo "Running determinism-boundary tests ..."
( cd services/ingestion  && pytest -q tests/test_determinism_boundary.py )
( cd services/intelligence && pytest -q tests/test_determinism_boundary.py )

# Derive a branch name from the commit subject (type/slug), unless already on a feature branch.
TYPE="$(printf '%s' "$MSG" | sed -E 's/^([a-z]+).*/\1/')"
SLUG="$(printf '%s' "$MSG" \
  | sed -E 's/^[a-z]+(\([^)]*\))?!?: //' \
  | tr '[:upper:]' '[:lower:]' \
  | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//' \
  | cut -c1-50)"
BRANCH="${TYPE:-chore}/${SLUG:-change}"

CURRENT="$(git rev-parse --abbrev-ref HEAD)"
if [ "$CURRENT" = "$BASE_BRANCH" ]; then
  echo "Creating branch '$BRANCH' ..."
  git switch -c "$BRANCH"
else
  BRANCH="$CURRENT"
  echo "Already on feature branch '$BRANCH'; committing here."
fi

echo "Committing ..."
git add -A
git commit -m "$MSG"

echo "Pushing ..."
git push -u origin "$BRANCH"

echo "Opening PR against '$BASE_BRANCH' ..."
gh pr create --base "$BASE_BRANCH" --head "$BRANCH" --title "$MSG" \
  --body "Automated PR opened by scripts/ship.sh. Codex reviews before merge (see .codex-review.md / run /review-codex). Determinism + security audits run in the /ship loop." \
  || echo "NOTE: PR may already exist for this branch."
PR_URL="$(gh pr view --json url -q .url 2>/dev/null || echo '(unknown)')"

# --- trigger the independent Codex review (best effort from the CLI) ------------------
echo "Requesting Codex review ..."
git fetch origin "$BASE_BRANCH" --quiet || true
BASE_REF="$(git merge-base HEAD "origin/$BASE_BRANCH" 2>/dev/null || echo HEAD~1)"
PROMPT="You are an independent code reviewer. Review this diff for correctness, security, and TarifHub's determinism rules (no LLM client on a value path; no AI computes/mutates a billing value; versioning/, audit/, services/intelligence/**/crosswalk/ and rules_frozen* unchanged; the apps/*/lib/deident.ts de-identification boundary; no renamed fields/columns/routes). Report findings as: SEVERITY (blocker|major|minor|nit) - file:line - problem - suggested fix. End with 'CODEX VERDICT: ...'."
if command -v codex >/dev/null 2>&1; then
  git diff "$BASE_REF"...HEAD | codex exec "$PROMPT" >"$REVIEW_FILE" 2>&1 \
    || echo "Codex review returned non-zero; see $REVIEW_FILE."
  echo "Codex findings written to $REVIEW_FILE"
else
  {
    echo "# Codex review"
    echo
    echo "Codex CLI not found. Run \`/review-codex\` inside Claude Code (it uses the"
    echo "codex-plugin-cc plugin), or install Codex via scripts/setup-claude-code.sh."
  } >"$REVIEW_FILE"
  echo "Codex CLI not installed — wrote instructions to $REVIEW_FILE"
fi

echo
echo "PR:    $PR_URL"
echo "Review: $REVIEW_FILE"
echo "Next:  address blockers/majors, commit + push the fixes, then: scripts/ship.sh --merge"
