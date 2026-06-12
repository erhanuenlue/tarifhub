#!/bin/bash
# Re-apply the repo-local graphify hook fixes.
# Run after a fresh clone or after any `graphify hook install` (which would
# overwrite the hooks with the upstream full-rescan versions). Idempotent.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
cp tools/hooks/post-commit-graphify .git/hooks/post-commit-graphify
cp tools/hooks/post-checkout .git/hooks/post-checkout
chmod +x .git/hooks/post-commit-graphify .git/hooks/post-checkout
# The async wrapper is created by `graphify hook install`; recreate it if absent
# so a bare clone gets the full chain.
if [ ! -f .git/hooks/post-commit ]; then
    cat > .git/hooks/post-commit <<'EOF'
#!/bin/bash
# async wrapper — graph rebuild runs in the background, git returns instantly
nohup .git/hooks/post-commit-graphify >/dev/null 2>&1 &
exit 0
EOF
    chmod +x .git/hooks/post-commit
fi
echo "graphify hooks installed (incremental, .graphifyignore-driven, async)"
