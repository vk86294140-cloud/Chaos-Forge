"""End-to-end experiment runner tests against a real in-process target."""

from __future__ import annotations

from chaosforge.experiment import Experiment
from chaosforge.runner import run_experiment


def _make_experiment(target: str, fault: dict) -> Experiment:
    return Experiment.from_dict(
        {
            "name": "test-exp",
            "target": target,
            "steady_state": {
                "url": "/health",
                "samples": 10,
                "min_success_rate": 0.99,
                "max_p95_ms": 50,
            },
            "fault": fault,
            "schedule": {"baseline_s": 0, "fault_s": 0, "recovery_s": 0},
        }
    )


def test_healthy_service_passes_and_recovers(target_server):
    exp = _make_experiment(target_server, {"type": "latency", "latency_ms": 120})
    result = run_experiment(exp)
    # Service is healthy before and after, so the experiment passes overall...
    assert result.passed is True
    assert result.recovery.success_rate == 1.0
    # ...but the latency SLO breach during the fault is reported as a finding.
    assert any("Latency SLO breached" in f for f in result.findings)


def test_error_fault_reports_no_tolerance(target_server):
    exp = _make_experiment(target_server, {"type": "error", "error_rate": 1.0})
    result = run_experiment(exp)
    assert result.fault.success_rate == 0.0
    assert result.recovery.success_rate == 1.0
    assert any("No fault tolerance" in f for f in result.findings)


def test_schedule_controls_how_long_each_window_runs(target_server):
    """The schedule block used to be parsed and then ignored entirely.

    Windows were paced only by how fast the probes returned, so `baseline_s`,
    `fault_s` and `recovery_s` had no effect on the run and the recovery window
    started the instant the fault was disarmed.
    """
    import time

    exp = _make_experiment(target_server, {"type": "latency", "latency_ms": 5})
    exp.steady_state.samples = 4
    exp.schedule.baseline_s = 1.0
    exp.schedule.fault_s = 1.0
    exp.schedule.recovery_s = 1.0

    start = time.perf_counter()
    run_experiment(exp)
    elapsed = time.perf_counter() - start

    # Three one-second windows cannot complete in appreciably less than 3s.
    assert elapsed >= 2.7, f"windows finished too fast ({elapsed:.2f}s)"


def test_experiment_from_yaml(tmp_path, target_server):
    yaml_text = f"""
name: yaml-exp
target: {target_server}
steady_state:
  url: /health
  samples: 8
  min_success_rate: 0.99
  max_p95_ms: 100
fault:
  type: latency
  latency_ms: 30
"""
    path = tmp_path / "exp.yaml"
    path.write_text(yaml_text)
    exp = Experiment.load(path)
    assert exp.name == "yaml-exp"
    result = run_experiment(exp)
    assert result.experiment == "yaml-exp"
