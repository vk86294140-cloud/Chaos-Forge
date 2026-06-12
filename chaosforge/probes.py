"""Steady-state probes.

A probe repeatedly calls an endpoint and measures the two signals that matter
for a resilience hypothesis: availability (success rate) and latency (p50/p95).
"""

from __future__ import annotations

import statistics
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List


@dataclass
class ProbeResult:
    samples: int
    successes: int
    errors: int
    latencies_ms: List[float]

    @property
    def success_rate(self) -> float:
        return self.successes / self.samples if self.samples else 0.0

    @property
    def p50_ms(self) -> float:
        return self._pct(50)

    @property
    def p95_ms(self) -> float:
        return self._pct(95)

    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0

    def _pct(self, pct: float) -> float:
        if not self.latencies_ms:
            return 0.0
        data = sorted(self.latencies_ms)
        k = (len(data) - 1) * (pct / 100.0)
        lo = int(k)
        hi = min(lo + 1, len(data) - 1)
        return data[lo] + (data[hi] - data[lo]) * (k - lo)


def probe(
    url: str,
    samples: int = 20,
    timeout_s: float = 5.0,
    expect_status: int = 200,
    interval_s: float = 0.0,
) -> ProbeResult:
    """Call `url` `samples` times and collect availability/latency stats."""

    successes = 0
    errors = 0
    latencies: List[float] = []

    for _ in range(samples):
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=timeout_s) as resp:
                status = resp.status
                resp.read()
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            latencies.append(elapsed_ms)
            if status == expect_status:
                successes += 1
            else:
                errors += 1
        except urllib.error.HTTPError as exc:
            latencies.append((time.perf_counter() - start) * 1000.0)
            errors += 1
            if exc.code == expect_status:
                successes += 1
                errors -= 1
        except Exception:
            errors += 1
        if interval_s:
            time.sleep(interval_s)

    return ProbeResult(
        samples=samples, successes=successes, errors=errors, latencies_ms=latencies
    )
