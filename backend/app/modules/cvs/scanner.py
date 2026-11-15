"""Scan uploads through clamd INSTREAM before any extraction."""

import socket
import struct
from time import monotonic

from app.core.config import settings

SCAN_TIMEOUT = 12


class UnsafeCV(Exception):
    """The scanner detected a threat."""


class ScannerUnavailable(Exception):
    """The scanner could not return a definitive verdict."""


def scan_cv(data: bytes) -> None:
    deadline = monotonic() + SCAN_TIMEOUT
    try:
        with socket.create_connection(
            (settings.cv_scanner_host, settings.cv_scanner_port),
            timeout=SCAN_TIMEOUT,
        ) as connection:
            connection.sendall(b"zINSTREAM\0")
            for offset in range(0, len(data), 65_536):
                connection.settimeout(max(0.001, deadline - monotonic()))
                chunk = data[offset : offset + 65_536]
                connection.sendall(struct.pack("!I", len(chunk)) + chunk)
            connection.sendall(b"\0" * 4)
            response = bytearray()
            while len(response) < 1024 and b"\0" not in response:
                connection.settimeout(max(0.001, deadline - monotonic()))
                chunk = connection.recv(256)
                if not chunk:
                    break
                response.extend(chunk)
    except OSError:
        raise ScannerUnavailable from None
    verdict, delimiter, trailing = bytes(response).partition(b"\0")
    if not delimiter or trailing:
        raise ScannerUnavailable
    if verdict.endswith(b" FOUND"):
        raise UnsafeCV
    if verdict != b"stream: OK":
        raise ScannerUnavailable
