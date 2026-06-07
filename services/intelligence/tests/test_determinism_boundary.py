"""Architectural guard: the rule-evaluation path imports no LLM client.

Statically (AST) scans the value path — ``main.py`` and the ``rules``, ``crosswalk``,
``validators`` and ``store`` modules — and asserts none of them import anthropic / openai
/ cohere / langchain / llama_index, anywhere (module level OR inside a function). This
encodes the LOCKED rule that TarifIQ *evaluates* rules deterministically; AI only
*suggests* rules pre-freeze, and the ``ai_rule_suggest`` seam is a placeholder that wires
no model into this skeleton.
"""

from __future__ import annotations

import ast
from pathlib import Path

import tarifiq

_FORBIDDEN = {"anthropic", "openai", "cohere", "langchain", "llama_index"}

_PKG_ROOT = Path(tarifiq.__file__).resolve().parent
_VALUE_PATH_FILES = (
    _PKG_ROOT / "main.py",
    _PKG_ROOT / "rules" / "combinability.py",
    _PKG_ROOT / "crosswalk" / "tarmed_tardoc.py",
    _PKG_ROOT / "validators" / "rule_validator.py",
    _PKG_ROOT / "store" / "frozen_client.py",
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
