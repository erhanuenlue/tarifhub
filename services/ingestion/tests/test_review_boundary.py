"""Architectural guard: the human-in-the-loop review write-back imports no LLM client.

The intelligence on the review write-back path is the HUMAN, never an LLM. This AST-scans
the ``review`` module, the ``review_service`` orchestration it feeds (the extracted
load -> validate -> freeze -> store -> audit path) and ``main.py``, which hosts the
endpoints, and asserts none of them import anthropic / openai / cohere / langchain /
llama_index.

It extends the determinism boundary to the review surface. The original
``test_determinism_boundary.py`` is frozen by the ``guard_frozen`` hook and cannot be
edited in place, so this sibling test carries the additional scope — exactly as
``services/serving/tests/test_serving_boundary.py`` does for the serving package.
"""

from __future__ import annotations

import ast
from pathlib import Path

import tarifhub_ingest

_FORBIDDEN = {"anthropic", "openai", "cohere", "langchain", "llama_index"}

_PKG_ROOT = Path(tarifhub_ingest.__file__).resolve().parent
_REVIEW_PATH_FILES = (
    _PKG_ROOT / "review.py",
    _PKG_ROOT / "review_service.py",
    _PKG_ROOT / "main.py",
)


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_review_path_files_exist():
    for path in _REVIEW_PATH_FILES:
        assert path.exists(), f"expected review-path file missing: {path}"


def test_review_path_imports_no_llm_client():
    offenders: dict[str, set[str]] = {}
    for path in _REVIEW_PATH_FILES:
        bad = _imported_roots(path) & _FORBIDDEN
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"LLM client imported on the review write-back path: {offenders}"
