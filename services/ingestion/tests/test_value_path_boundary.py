"""Architectural guard: the ingestion value path imports no LLM client (whole-package scan).

The frozen ``test_determinism_boundary.py`` pins a hard-coded trio of value-path files
(``main.py`` plus the ``storage`` package). A hard-coded list cannot catch a NEW value-path
module added later, so this sibling hardens the boundary exactly the way
``services/serving/tests/test_serving_boundary.py`` does for serving: it AST-scans EVERY
module under ``tarifhub_ingest`` and asserts none imports anthropic / openai / cohere /
langchain / llama_index — anywhere, module level OR inside a function.

Ingestion differs from serving in one principled way: it legitimately hosts the ONE
pre-freeze AI seam (``ai_map`` in ``mappers/tariff_mapper.py``). That single module is the
explicit, auditable allowlist below; every other module — including any new one — is held to
the no-LLM rule. A value-path module that slips an LLM import past the frozen trio is caught
here even though the trio does not name it.

Named distinctly (not ``test_determinism_boundary.py``, whose basename the ``guard_frozen``
hook freezes in ANY directory) and purely additive: the frozen original stays untouched.
This is the freeze-respecting realisation of "rglob the whole package like serving".
"""

from __future__ import annotations

import ast
from pathlib import Path

import tarifhub_ingest

_FORBIDDEN = {"anthropic", "openai", "cohere", "langchain", "llama_index"}

_PKG_ROOT = Path(tarifhub_ingest.__file__).resolve().parent
_PKG_FILES = sorted(_PKG_ROOT.rglob("*.py"))

# The ONLY modules permitted to import an LLM client: the pre-freeze ai_map seam. Paths are
# relative to the package root. Everything else is on the deterministic side of the freeze.
_AI_ALLOWED = {Path("mappers/tariff_mapper.py")}


def _imported_roots(path: Path) -> set[str]:
    """Root module of every import in a file (module level AND inside functions)."""

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


def test_package_has_modules():
    assert _PKG_FILES, f"no python modules found under {_PKG_ROOT}"


def test_ai_allowlist_paths_exist():
    """The allowlisted AI seam must exist, so the carve-out cannot silently rot."""

    for rel in _AI_ALLOWED:
        assert (_PKG_ROOT / rel).exists(), f"allowlisted AI module missing: {rel}"


def test_value_path_imports_no_llm_client_anywhere():
    """No module outside the sanctioned ai_map seam may import an LLM client."""

    offenders: dict[str, set[str]] = {}
    for path in _PKG_FILES:
        rel = path.relative_to(_PKG_ROOT)
        if rel in _AI_ALLOWED:
            continue  # the sanctioned pre-freeze ai_map seam
        bad = _imported_roots(path) & _FORBIDDEN
        if bad:
            offenders[str(rel)] = bad
    assert not offenders, (
        "LLM client imported off the pre-freeze AI seam (a new value-path module?): "
        f"{offenders}"
    )
