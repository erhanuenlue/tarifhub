"""The pilot's offline suite blocks the network: ``conftest.py`` turns pytest-socket on around
each test, so creating a Python socket other than a Unix socket fails with
``SocketBlockedError`` before anything is sent."""

from __future__ import annotations

import socket

import pytest
from pytest_socket import SocketBlockedError


def test_an_internet_socket_cannot_be_created() -> None:
    with pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()


def test_a_connection_attempt_is_blocked() -> None:
    with pytest.raises(SocketBlockedError):
        socket.create_connection(("127.0.0.1", 9)).close()


def test_a_unix_socket_stays_available() -> None:
    # Allowed on purpose (allow_unix_socket=True): an event loop's self-pipe is a Unix socket pair.
    socket.socket(socket.AF_UNIX, socket.SOCK_STREAM).close()
