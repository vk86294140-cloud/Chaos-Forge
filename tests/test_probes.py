"""Unit tests for probe statistics (no network needed)."""

from __future__ import annotations

from chaosforge.probes import ProbeResult, probe


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


def test_transport_failures_still_produce_latency_samples():
    """A refused connection is a real user-visible latency, not a missing sample.

    Regression test: percentiles used to be computed only from attempts that
    came back with an HTTP response, so a fully blackholed target reported
    p95 = 0.0 — better-looking than a healthy baseline.
    """
    # Port 1 on loopback: nothing listens, so every attempt fails in transport.
    r = probe("http://127.0.0.1:1/health", samples=5, timeout_s=1.0)

    assert r.samples == 5
    assert r.successes == 0
    assert r.errors == 5
    assert r.transport_errors == 5
    assert len(r.latencies_ms) == 5, "every attempt must contribute a sample"
    assert r.p95_ms > 0.0


def test_timeouts_inflate_the_percentiles_instead_of_vanishing(target_server):
    """End-to-end version of the same bug, through the fault proxy.

    A latency fault longer than the probe timeout makes every request time out.
    Those attempts used to be dropped from `latencies_ms` entirely, leaving an
    empty list and a reported p95 of 0.0 — a fully stalled service scoring
    better on latency than a healthy one.
    """
    from chaosforge.proxy import FaultProxy

    with FaultProxy(target_base=target_server) as proxy:
        url = proxy.base_url + "/health"

        baseline = probe(url, samples=3, timeout_s=1.0)
        proxy.fault.arm(latency_ms=2000)
        stalled = probe(url, samples=3, timeout_s=0.5)

    assert baseline.success_rate == 1.0
    assert stalled.success_rate == 0.0
    assert stalled.transport_errors == 3
    assert len(stalled.latencies_ms) == 3
    # Each attempt burned the full 0.5s timeout, so the tail must reflect that.
    assert stalled.p95_ms >= 400.0
    assert stalled.p95_ms > baseline.p95_ms
