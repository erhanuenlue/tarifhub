"""The pilot suite needs the ingestion ``ai`` extra (the ``anthropic`` client), the ``dev``
extra's ``pytest-socket`` and poppler's ``pdftotext``. Without one of them, the run stops with
this message instead of skipping tests. Each test runs with pytest-socket's block on: creating a
Python socket other than a Unix socket raises ``SocketBlockedError``, so a test that tries to
reach the network fails instead of connecting."""

from __future__ import annotations

import importlib.util
import shutil
from collections.abc import Iterator

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Refuse the whole run when a dependency of the pilot's tests is missing."""
    missing = []
    if importlib.util.find_spec("anthropic") is None:
        missing.append("the anthropic client (sync services/ingestion with --extra ai --extra dev)")
    if importlib.util.find_spec("pytest_socket") is None:
        missing.append("pytest-socket (sync services/ingestion with --extra ai --extra dev)")
    if shutil.which("pdftotext") is None:
        missing.append("poppler's pdftotext (brew install poppler, apt-get install poppler-utils)")
    if missing:
        raise pytest.UsageError("tools/commentary_rag tests need " + " and ".join(missing))


@pytest.fixture(autouse=True)
def _block_network() -> Iterator[None]:
    """Block new Python sockets, Unix sockets excepted, for one test and lift the block after it.

    pytest-socket is imported here, not at the top, so that a missing package reaches the
    refusal above instead of failing the import of this file.
    """
    import pytest_socket  # noqa: PLC0415

    pytest_socket.disable_socket(allow_unix_socket=True)
    yield
    pytest_socket.enable_socket()
