"""Resource-exhaustion faults: CPU saturation, memory pressure, and disk fill.

All are exposed as context managers so they are automatically rolled back,
which is the cardinal rule of chaos engineering: every blast radius must be
reversible.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Iterator


@contextlib.contextmanager
def cpu_hog(workers: int = 1, duration_s: float | None = None) -> Iterator[None]:
    """Saturate `workers` CPU cores with busy loops until the context exits."""

    stop = threading.Event()

    def _burn() -> None:
        x = 0.0001
        while not stop.is_set():
            x = (x * x + 0.12345) % 7.0  # pointless FP work to keep a core hot

    threads = [threading.Thread(target=_burn, daemon=True) for _ in range(workers)]
    for t in threads:
        t.start()
    try:
        if duration_s is not None:
            time.sleep(duration_s)
        yield
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=2)


@contextlib.contextmanager
def memory_hog(megabytes: int = 256, duration_s: float | None = None) -> Iterator[None]:
    """Allocate and touch `megabytes` of memory until the context exits."""

    block = None
    try:
        # Allocate then write to every page so the pages are actually resident.
        block = bytearray(megabytes * 1024 * 1024)
        for i in range(0, len(block), 4096):
            block[i] = 1
        if duration_s is not None:
            time.sleep(duration_s)
        yield
    finally:
        del block


@contextlib.contextmanager
def disk_hog(
    megabytes: int = 256,
    duration_s: float | None = None,
    path: str | os.PathLike | None = None,
) -> Iterator[Path]:
    """Consume `megabytes` of disk by writing a scratch file until the context
    exits, then delete it. Simulates a full or filling disk (log spew, runaway
    cache) so you can verify a service degrades gracefully instead of crashing.

    Yields the scratch file path. The file is always removed on exit, even if
    the body raises — disk pressure must be as reversible as any other fault.
    `path` chooses the target filesystem (defaults to the system temp dir).
    """
    directory = Path(path) if path is not None else Path(tempfile.gettempdir())
    directory.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="chaosforge-disk-", dir=directory)
    scratch = Path(name)
    try:
        chunk = b"\0" * (1024 * 1024)  # 1 MiB
        with os.fdopen(fd, "wb") as fh:
            for _ in range(max(0, megabytes)):
                fh.write(chunk)
            fh.flush()
            os.fsync(fh.fileno())
        if duration_s is not None:
            time.sleep(duration_s)
        yield scratch
    finally:
        scratch.unlink(missing_ok=True)
