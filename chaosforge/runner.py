"""Orchestrate an experiment: baseline -> inject fault -> recovery -> verdict."""

from __future__ import annotations

from .experiment import Experiment, ExperimentResult, WindowReport
from .probes import ProbeResult, probe
from .proxy import FaultProxy


def _arm_fault(proxy: FaultProxy, experiment: Experiment) -> None:
    f = experiment.fault
    if f.type == "latency":
        proxy.fault.arm(latency_ms=f.latency_ms)
    elif f.type == "error":
        proxy.fault.arm(error_rate=f.error_rate, error_status=f.error_status)
    elif f.type == "blackhole":
        proxy.fault.arm(blackhole_rate=f.blackhole_rate)
    else:
        raise ValueError(f"unknown fault type: {f.type!r}")


def _window(label: str, result: ProbeResult) -> WindowReport:
    return WindowReport(
        label=label,
        success_rate=result.success_rate,
        p50_ms=result.p50_ms,
        p95_ms=result.p95_ms,
        samples=result.samples,
    )


def run_experiment(experiment: Experiment) -> ExperimentResult:
    """Run the experiment against `experiment.target` through a fault proxy.

    Returns an ExperimentResult whose `passed` flag answers: did the system
    keep its steady-state hypothesis during the fault, and did it recover?
    """

    ss = experiment.steady_state
    with FaultProxy(target_base=experiment.target) as proxy:
        probe_url = proxy.base_url + _path_of(ss.url)

        baseline = probe(probe_url, samples=ss.samples, expect_status=ss.expect_status)

        _arm_fault(proxy, experiment)
        fault = probe(probe_url, samples=ss.samples, expect_status=ss.expect_status)
        proxy.fault.disarm()

        recovery = probe(probe_url, samples=ss.samples, expect_status=ss.expect_status)

    findings: list[str] = []

    if baseline.success_rate < ss.min_success_rate:
        findings.append(
            f"Baseline already unhealthy: success rate "
            f"{baseline.success_rate:.0%} < {ss.min_success_rate:.0%}. "
            f"Fix the system before trusting this experiment."
        )

    if recovery.success_rate < ss.min_success_rate:
        findings.append(
            f"System did NOT recover: post-fault success rate "
            f"{recovery.success_rate:.0%} < {ss.min_success_rate:.0%}. "
            f"This is a resilience gap — the fault left lasting damage."
        )

    if experiment.fault.type == "latency" and fault.p95_ms > ss.max_p95_ms:
        findings.append(
            f"Latency SLO breached under fault: p95 {fault.p95_ms:.0f}ms "
            f"> {ss.max_p95_ms:.0f}ms. Consider timeouts, retries with backoff, "
            f"or a circuit breaker."
        )

    if experiment.fault.type in ("error", "blackhole") and fault.success_rate < ss.min_success_rate:
        findings.append(
            f"No fault tolerance for {experiment.fault.type}: success dropped to "
            f"{fault.success_rate:.0%} under fault. A retry/fallback policy would help."
        )

    # Pass = the system was healthy before and recovered cleanly after.
    passed = (
        baseline.success_rate >= ss.min_success_rate
        and recovery.success_rate >= ss.min_success_rate
    )

    return ExperimentResult(
        experiment=experiment.name,
        passed=passed,
        baseline=_window("baseline", baseline),
        fault=_window("fault", fault),
        recovery=_window("recovery", recovery),
        findings=findings,
    )


def _path_of(url: str) -> str:
    """Extract the path (+query) from a steady-state URL or accept a bare path."""
    if url.startswith("http://") or url.startswith("https://"):
        from urllib.parse import urlsplit

        parts = urlsplit(url)
        return parts.path + (("?" + parts.query) if parts.query else "")
    return url if url.startswith("/") else "/" + url
