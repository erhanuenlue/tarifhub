"""Architectural guard: the value-serving path imports no LLM client.

Statically (AST) scans ``main.py`` and the ``storage`` package and asserts none of
them import anthropic / openai / cohere / langchain / llama_index. This encodes the
LOCKED rule that authoritative tariff values are served deterministically, with no AI
on the serving path.
"""

from __future__ import annotations

import ast
from pathlib import Path

import tarifhub_ingest

_FORBIDDEN = {"anthropic", "openai", "cohere", "langchain", "llama_index"}

_PKG_ROOT = Path(tarifhub_ingest.__file__).resolve().parent
_VALUE_PATH_FILES = (
    _PKG_ROOT / "main.py",
    _PKG_ROOT / "storage" / "db.py",
    _PKG_ROOT / "storage" / "tariff_repository.py",
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


def test_value_path_files_exist():
    for path in _VALUE_PATH_FILES:
        assert path.exists(), f"expected value-path file missing: {path}"


def test_value_path_imports_no_llm_client():
    offenders: dict[str, set[str]] = {}
    for path in _VALUE_PATH_FILES:
        bad = _imported_roots(path) & _FORBIDDEN
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"LLM client imported on the value path: {offenders}"
