"""Tests for the breaking-point search, against a real in-process target."""

from __future__ import annotations

import pytest

from chaosforge.breaking_point import BOUNDS, find_breaking_point
from chaosforge.experiment import Experiment, Fault, Schedule, SteadyState
from chaosforge.report import breaking_point_to_console, breaking_point_to_json


def _experiment(target: str, fault: Fault, **steady: object) -> Experiment:
    defaults: dict[str, object] = {
        "url": "/health",
        "samples": 6,
        "expect_status": 200,
        "min_success_rate": 0.99,
        "max_p95_ms": 150.0,
    }
    defaults.update(steady)
    return Experiment(
        name="breaking-point",
        target=target,
        steady_state=SteadyState(**defaults),  # type: ignore[arg-type]
        fault=fault,
        schedule=Schedule(baseline_s=0.2, fault_s=0.2, recovery_s=0.2),
    )


def test_latency_search_reports_a_threshold_around_the_slo(target_server):
    # The target answers instantly, so added latency is essentially the whole
    # p95: the service should tolerate roughly up to the 150ms SLO and break
    # above it. Asserting a bracket rather than an exact number keeps this
    # honest on a loaded CI runner.
    exp = _experiment(target_server, Fault(type="latency", latency_ms=0))
    result = find_breaking_point(exp, max_magnitude=800, max_trials=6, window_s=0.2)

    assert result.found
    assert result.tolerated is not None
    assert result.tolerated < result.breaks_at
    assert result.tolerated <= 200
    assert result.breaks_at <= 800


def test_error_rate_search_finds_the_point_availability_drops(target_server):
    exp = _experiment(target_server, Fault(type="error", error_rate=0.0), samples=20)
    result = find_breaking_point(exp, max_trials=4, window_s=0.2)

    assert result.unit == "error_rate"
    assert result.found
    # Any real error rate breaks a 99% success hypothesis, so tolerance should
    # be at or near zero rather than somewhere mid-range.
    assert (result.tolerated or 0.0) <= 0.25


def test_a_service_that_survives_the_ceiling_reports_no_breaking_point(target_server):
    # An SLO this loose cannot be violated by latency injection within range.
    exp = _experiment(
        target_server,
        Fault(type="latency", latency_ms=0),
        max_p95_ms=10_000.0,
        min_success_rate=0.0,
    )
    result = find_breaking_point(exp, max_magnitude=50, max_trials=4, window_s=0.2)

    assert not result.found
    assert result.breaks_at is None
    assert result.tolerated == 50
    assert len(result.trials) == 1, "the ceiling probe should short-circuit the search"


def test_search_respects_the_trial_budget(target_server):
    exp = _experiment(target_server, Fault(type="latency", latency_ms=0))
    result = find_breaking_point(exp, max_magnitude=1000, max_trials=3, window_s=0.2)
    assert len(result.trials) <= 3


def test_resource_faults_are_rejected_with_a_useful_message(target_server):
    exp = _experiment(target_server, Fault(type="cpu_hog"))
    with pytest.raises(ValueError, match="host-level"):
        find_breaking_point(exp)


def test_every_supported_fault_declares_bounds_and_a_unit():
    for fault_type, (low, high, unit) in BOUNDS.items():
        assert low < high and unit, fault_type


def test_reports_render_for_both_outcomes(target_server):
    exp = _experiment(target_server, Fault(type="latency", latency_ms=0))
    result = find_breaking_point(exp, max_magnitude=600, max_trials=4, window_s=0.2)

    console = breaking_point_to_console(result)
    assert "Breaking point" in console
    assert ("Tolerates up to" in console) or ("No breaking point" in console)
    assert '"trials"' in breaking_point_to_json(result)
