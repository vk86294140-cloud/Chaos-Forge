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
