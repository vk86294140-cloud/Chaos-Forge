"""Tests for the fault-injecting proxy: pass-through, latency, errors."""

from __future__ import annotations

import time

from chaosforge.probes import probe
from chaosforge.proxy import FaultProxy


def test_proxy_passes_through_when_disarmed(target_server):
    with FaultProxy(target_base=target_server) as proxy:
        result = probe(proxy.base_url + "/health", samples=10)
    assert result.success_rate == 1.0


def test_latency_fault_adds_delay(target_server):
    with FaultProxy(target_base=target_server) as proxy:
        clean = probe(proxy.base_url + "/health", samples=5)
        proxy.fault.arm(latency_ms=150)
        slow = probe(proxy.base_url + "/health", samples=5)
        proxy.fault.disarm()
        recovered = probe(proxy.base_url + "/health", samples=5)

    assert slow.mean_ms >= clean.mean_ms + 100  # ~150ms injected
    assert recovered.mean_ms < slow.mean_ms      # delay removed on disarm


def test_error_fault_drops_success_rate(target_server):
    with FaultProxy(target_base=target_server) as proxy:
        proxy.fault.arm(error_rate=1.0, error_status=503)
        result = probe(proxy.base_url + "/health", samples=10, expect_status=200)
    assert result.success_rate == 0.0


def test_fault_config_disarm_resets(target_server):
    with FaultProxy(target_base=target_server) as proxy:
        proxy.fault.arm(latency_ms=50, error_rate=0.5)
        proxy.fault.disarm()
        snap = proxy.fault.snapshot()
    assert snap.latency_ms == 0
    assert snap.error_rate == 0.0
    assert snap.enabled is False
