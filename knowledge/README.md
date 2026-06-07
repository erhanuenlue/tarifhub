# knowledge/ — the TarifHub Obsidian vault

This folder is an **Obsidian vault** and the founder's second brain. It holds the
human-curated knowledge that does not belong in source code: architecture/dev decisions,
research, the AI-tooling journal, and daily logs. Open it by pointing Obsidian at this
`knowledge/` directory ("Open folder as vault").

Start at **[[00-index]]**.

## Two brains, two jobs

- **graphify = the structural brain of the codebase.** It answers *"what is in this monorepo
  and how is it wired"* — which ingestion adapter feeds which serving endpoint, what links the
  MCP server to the frozen-records store, where a concept lives across `services/ingestion`
  (Python), `services/serving` (Quarkus), `services/intelligence` (Python) and `apps/*`
  (Next.js). It extracts code locally via tree-sitter, commits its graph, and serves it over
  MCP (`query_graph`, `get_node`, `shortest_path`) — see the `graphify` server in `.mcp.json`.
- **Obsidian (this vault) = the human brain.** It answers *"why did we decide this"* — the
  durable record of decisions, research, and rationale.

## graphify → Obsidian export

graphify can export its code/doc knowledge graph **into this vault** as linked Markdown, so
your human notes can wikilink directly to code nodes (a function, a module, an endpoint):

```bash
# from the repo root, after the graph is built (graphify . , or the post-commit hook):
graphify --obsidian knowledge
```

This writes graph nodes/edges as notes under this vault (typically a `graph/` subfolder),
which you can then link to from `decisions/`, `research/`, and `daily/` notes. Re-run after
significant changes, or rely on graphify's **post-commit git hook** (installed by
`scripts/setup-claude-code.sh` via `graphify init`) to keep the graph fresh automatically.

The exported `graph/` notes are *generated* — treat them as read-only and regenerate rather
than hand-edit. Your authored notes (`decisions/`, `research/`, `daily/`, `ai-workflow.md`)
are the durable, hand-curated layer.

## Layout

```
knowledge/
├─ 00-index.md     map of content (start here)
├─ README.md       this file
├─ ai-workflow.md  AI-tooling journal + Vibe/Spec/Agentic decision matrix
├─ decisions/      ADR-style notes (NNNN-kebab-title.md)
├─ research/       verified research + tool/market/regulatory notes
└─ daily/          dated working logs (YYYY-MM-DD.md)
```
