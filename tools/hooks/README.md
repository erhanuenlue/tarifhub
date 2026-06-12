# Repo-local git hooks (tracked copies)

`.git/hooks/` is not version-controlled — the canonical copies live here.
Re-apply after a fresh clone or after any `graphify hook install`:

```bash
tools/hooks/install.sh
```

## Why these replace the graphify-installed hooks

Upstream `graphify.watch._rebuild_code` (used by both generated hooks) has two
defects, observed live on 2026-06-12:

1. It walks the **whole tree** with only minimal exclusions — `node_modules/`
   and mkdocs `site/` assets entered the graph (~77k junk nodes).
2. It rebuilds `graph.json` **from scratch, code-only** — every semantically
   extracted doc/image node is dropped on each commit.

The upstream post-checkout hook additionally ran the rebuild **synchronously**,
so a slow full-tree walk blocked `git checkout` itself (observed: a wedged
`checkout -b`).

## The tracked versions

- `post-commit-graphify` — extracts ONLY the committed code files
  (`git diff FROM TO`, defaults `HEAD~1 HEAD`), ghost-prunes those files'
  stale nodes, merges into the existing graph, applies the exclusions from
  `.graphifyignore` (loaded via `graphify.detect._load_graphifyignore` —
  single source of truth), prunes isolates, rewrites graph + report.
- `post-checkout` — thin async wrapper: on real branch switches it runs the
  same script with `PREV_HEAD NEW_HEAD` as the diff range, via `nohup … &`
  so git returns instantly.
- `verify_graph.py` — health checker: vendored-node count must be 0 and all
  node types present. `--wait-newer-than EPOCH` polls for the async rebuild
  after a commit. Used as the proof harness for this fix.
- The async wrapper `.git/hooks/post-commit` (from `graphify hook install`)
  is intentionally left as-is; `install.sh` recreates it only if absent.

Doc/markdown changes are intentionally NOT handled by the hooks — run
`/graphify --update` after doc-heavy sessions (also restores curated community
labels in `GRAPH_REPORT.md`; the hooks write generic ones).
