"""Unit tests for probe statistics (no network needed)."""

from __future__ import annotations

from chaosforge.probes import ProbeResult


def test_percentiles_and_rates():
    r = ProbeResult(
        samples=10,
        successes=9,
        errors=1,
        latencies_ms=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
    )
    assert r.success_rate == 0.9
    assert r.p50_ms == 55.0
    assert 90 <= r.p95_ms <= 100
    assert r.mean_ms == 55.0


def test_empty_probe_is_safe():
    r = ProbeResult(samples=0, successes=0, errors=0, latencies_ms=[])
    assert r.success_rate == 0.0
    assert r.p95_ms == 0.0
    assert r.mean_ms == 0.0
