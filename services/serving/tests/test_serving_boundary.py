"""Architectural guard: the serving package imports no LLM client.

Statically (AST) scans the ENTIRE ``tarifhub_serving`` package and asserts:

  (a) none of its modules import anthropic / openai / cohere / langchain /
      llama_index — the LOCKED rule that authoritative tariff values are served
      deterministically, with no AI on the serving value path; and
  (b) the only ``tarifhub_ingest`` submodules imported anywhere in the package are
      ``models`` and ``embeddings`` — never mappers or anything that could transitively
      pull an LLM client.

Modelled on ``services/ingestion/tests/test_determinism_boundary.py``. Named
``test_serving_boundary`` (not ``test_determinism_boundary``) because the latter
filename is frozen by the ``guard_frozen`` hook; the assertions here are the
serving-package equivalent.
"""

from __future__ import annotations

import ast
from pathlib import Path

import tarifhub_serving

_FORBIDDEN = {"anthropic", "openai", "cohere", "langchain", "llama_index"}
_ALLOWED_INGEST_SUBMODULES = {"models", "embeddings"}

_PKG_ROOT = Path(tarifhub_serving.__file__).resolve().parent
_PKG_FILES = sorted(_PKG_ROOT.rglob("*.py"))


def _import_targets(path: Path) -> list[tuple[str, str | None]]:
    """Return (root_module, second_segment) for every import in a file."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                targets.append((parts[0], parts[1] if len(parts) > 1 else None))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                parts = node.module.split(".")
                targets.append((parts[0], parts[1] if len(parts) > 1 else None))
    return targets


def test_package_has_modules():
    assert _PKG_FILES, f"no python modules found under {_PKG_ROOT}"


def test_no_llm_client_imported_anywhere():
    offenders: dict[str, set[str]] = {}
    for path in _PKG_FILES:
        bad = {root for root, _ in _import_targets(path)} & _FORBIDDEN
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"LLM client imported in the serving package: {offenders}"


def test_only_models_and_embeddings_imported_from_ingestion():
    offenders: dict[str, set[str]] = {}
    for path in _PKG_FILES:
        bad = {
            sub
            for root, sub in _import_targets(path)
            if root == "tarifhub_ingest"
            and sub is not None
            and sub not in _ALLOWED_INGEST_SUBMODULES
        }
        if bad:
            offenders[path.name] = bad
    assert not offenders, (
        "serving must import only models/embeddings from tarifhub_ingest; "
        f"found: {offenders}"
    )
