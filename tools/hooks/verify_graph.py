#!/usr/bin/env python3
"""Verify graphify-out/graph.json health: no vendored nodes, all node types present.

Used as the proof harness for the post-commit hook fix (and for debugging any
future graph pollution). Exit 0 = healthy, 1 = polluted/degraded, 2 = no graph.

    python3 tools/hooks/verify_graph.py [--wait-newer-than EPOCH] [--timeout SECONDS]

--wait-newer-than polls until graph.json's mtime is newer than EPOCH (use it
after a commit to wait for the async hook rebuild), then verifies.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

# Mirrors .graphifyignore — read it when present so the two never drift.
FALLBACK_PATTERNS = [
    "node_modules", ".next", ".venv", "site-packages", "__pycache__", "dist",
    "graphify-out", "site", "lunr", "*.min.js", "wordcut.js",
]
EXPECTED_FILE_TYPES = {"code", "document", "image"}  # rationale is optional


def _patterns(root: Path) -> list[str]:
    try:
        from graphify.detect import _load_graphifyignore

        return _load_graphifyignore(root) or FALLBACK_PATTERNS
    except Exception:
        return FALLBACK_PATTERNS


def _is_junk(rel: str, root: Path, patterns: list[str]) -> bool:
    try:
        from graphify.detect import _is_ignored

        return _is_ignored(root / rel, root, patterns)
    except Exception:
        return any(p.strip("*") in rel for p in patterns)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait-newer-than", type=float, default=None, metavar="EPOCH")
    ap.add_argument("--timeout", type=float, default=90.0)
    args = ap.parse_args()

    root = Path.cwd()
    graph_path = root / "graphify-out" / "graph.json"

    if args.wait_newer_than is not None:
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            if graph_path.exists() and graph_path.stat().st_mtime > args.wait_newer_than:
                break
            time.sleep(2)
        else:
            print(f"TIMEOUT: graph.json not rebuilt within {args.timeout}s")
            return 2

    if not graph_path.exists():
        print("NO GRAPH: graphify-out/graph.json missing")
        return 2

    nodes = json.loads(graph_path.read_text()).get("nodes", [])
    patterns = _patterns(root)
    junk = [n for n in nodes if _is_junk(str(n.get("source_file", "")), root, patterns)]
    ft = Counter(str(n.get("file_type")) for n in nodes)

    print(f"nodes: {len(nodes)} | file_types: {dict(ft)} | vendored: {len(junk)}")
    for n in junk[:5]:
        print(f"  JUNK: {n.get('source_file')}")

    missing = EXPECTED_FILE_TYPES - set(ft)
    if junk:
        print(f"FAIL: {len(junk)} vendored node(s) in the graph")
        return 1
    if missing:
        print(f"FAIL: node types missing from the graph: {sorted(missing)}")
        return 1
    print("OK: graph healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
