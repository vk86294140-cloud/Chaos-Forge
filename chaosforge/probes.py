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


@dataclass
class ProbeResult:
    samples: int
    successes: int
    errors: int
    latencies_ms: list[float]
    # Attempts that never produced an HTTP response (timeout, connection reset,
    # blackholed socket). Counted separately because they are the signature of
    # a hard failure rather than a slow-but-alive service.
    transport_errors: int = 0

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
    window_s: float = 0.0,
) -> ProbeResult:
    """Call `url` `samples` times and collect availability/latency stats.

    Every attempt contributes a latency sample, including ones that never came
    back with an HTTP response. A request that burns the full `timeout_s` and
    then raises is a 5000ms experience for the caller; dropping it would make
    the percentiles describe only the survivors.

    `window_s` spreads the samples evenly over that many seconds instead of
    firing them back to back. Each sample gets a slot of `window_s / samples`
    and the probe sleeps out the unused remainder, so a slow response eats its
    own slack rather than pushing the whole window long. A burst and a paced
    stream are different workloads, and steady-state hypotheses are written
    about the paced one.
    """

    successes = 0
    errors = 0
    transport_errors = 0
    latencies: list[float] = []

    slot_s = (window_s / samples) if (window_s and samples) else 0.0
    window_start = time.perf_counter()

    for index in range(samples):
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=timeout_s) as resp:
                status = resp.status
                resp.read()
            latencies.append((time.perf_counter() - start) * 1000.0)
            if status == expect_status:
                successes += 1
            else:
                errors += 1
        except urllib.error.HTTPError as exc:
            # An HTTP error is still a response, and can be the expected one
            # (e.g. an experiment asserting a 503 fallback path).
            latencies.append((time.perf_counter() - start) * 1000.0)
            if exc.code == expect_status:
                successes += 1
            else:
                errors += 1
        except Exception:
            latencies.append((time.perf_counter() - start) * 1000.0)
            errors += 1
            transport_errors += 1

        if slot_s:
            next_slot_at = window_start + slot_s * (index + 1)
            remaining = next_slot_at - time.perf_counter()
            if remaining > 0:
                time.sleep(remaining)
        elif interval_s:
            time.sleep(interval_s)

    return ProbeResult(
        samples=samples,
        successes=successes,
        errors=errors,
        latencies_ms=latencies,
        transport_errors=transport_errors,
    )
