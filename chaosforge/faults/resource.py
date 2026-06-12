"""Resource-exhaustion faults: CPU saturation and memory pressure.

Both are exposed as context managers so they are automatically rolled back,
which is the cardinal rule of chaos engineering: every blast radius must be
reversible.
"""

from __future__ import annotations

import contextlib
import threading
import time
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
