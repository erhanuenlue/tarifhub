#!/usr/bin/env bash
#
# bootstrap-github.sh — create the private GitHub repo, push, and protect `main`.
#
# RUN THIS ON YOUR MACHINE. The GitHub CLI (`gh`) must be installed AND authenticated
# (`gh auth login`) with a token that can create repositories. gh is NOT available in the
# build sandbox or in CI — the remote create + push happens locally, performed by you (or by
# Claude Code running on your machine). See docs/START_GUIDE.md.
#
# Idempotent: safe to re-run. Override defaults with REPO_NAME / DEFAULT_BRANCH env vars.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REPO_NAME="${REPO_NAME:-tarifhub}"
DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"

command -v gh >/dev/null 2>&1 || {
  echo "ERROR: gh (GitHub CLI) not found. Install it, then run 'gh auth login'." >&2
  exit 1
}
gh auth status >/dev/null 2>&1 || {
  echo "ERROR: gh is not authenticated. Run 'gh auth login' first." >&2
  exit 1
}

# Ensure a git repo exists with at least one commit on the default branch.
if [ ! -d .git ]; then
  echo "Initializing git repository (branch: $DEFAULT_BRANCH) ..."
  git init -b "$DEFAULT_BRANCH"
fi
if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  echo "Creating initial commit ..."
  git add -A
  git commit -m "chore: initial tarifhub commit"
fi
git branch -M "$DEFAULT_BRANCH"

# Create the private repo from this directory, wire origin, and push.
if gh repo view "$REPO_NAME" >/dev/null 2>&1; then
  echo "Repo '$REPO_NAME' already exists on your account; skipping create + push."
else
  echo "Creating private repo '$REPO_NAME' and pushing ..."
  gh repo create "$REPO_NAME" --private --source=. --remote=origin --push
fi

# Branch protection on main. Codex is the in-loop reviewer (via /ship), so we do NOT require
# human PR approvals (a solo founder cannot approve their own PRs); we DO require the CI gate
# to pass and a clean, linear history. The single required context "devsecops gates" is the
# aggregate CI job that `needs:` all the per-service jobs (see .github/workflows/ci.yml), so
# requiring it transitively requires the whole suite to be green.
OWNER="$(gh repo view "$REPO_NAME" --json owner -q .owner.login)"
echo "Applying branch protection to $OWNER/$REPO_NAME@$DEFAULT_BRANCH ..."
gh api -X PUT "repos/$OWNER/$REPO_NAME/branches/$DEFAULT_BRANCH/protection" \
  -H "Accept: application/vnd.github+json" \
  --input - <<'JSON' || echo "WARNING: branch protection not applied. Check token scope / repo plan, and that the 'devsecops gates' check name matches .github/workflows/ci.yml."
{
  "required_status_checks": { "strict": true, "contexts": ["devsecops gates"] },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
JSON

# Allow squash auto-merge so `scripts/ship.sh --merge` can merge automatically once CI is green.
gh api -X PATCH "repos/$OWNER/$REPO_NAME" \
  -f allow_auto_merge=true -f allow_squash_merge=true -f delete_branch_on_merge=true \
  >/dev/null 2>&1 || echo "NOTE: could not toggle auto-merge/squash settings; set them in repo Settings if needed."

echo "Done. Remote: $(gh repo view "$REPO_NAME" --json url -q .url)"
echo "Next: develop on a branch, then run scripts/ship.sh \"<commit>\" (or /ship in Claude Code)."
