"""The pilot suite needs the ingestion ``ai`` extra (the ``anthropic`` client) and poppler's
``pdftotext``. Without either, the run stops with this message instead of skipping tests."""

from __future__ import annotations

import importlib.util
import shutil

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Refuse the whole run when a dependency of the pilot's tests is missing."""
    missing = []
    if importlib.util.find_spec("anthropic") is None:
        missing.append("the anthropic client (sync services/ingestion with --extra ai --extra dev)")
    if shutil.which("pdftotext") is None:
        missing.append("poppler's pdftotext (brew install poppler, apt-get install poppler-utils)")
    if missing:
        raise pytest.UsageError("tools/commentary_rag tests need " + " and ".join(missing))
