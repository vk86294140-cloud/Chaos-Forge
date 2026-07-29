"""Rendering tests for the three report formats."""

from __future__ import annotations

import json

from chaosforge.experiment import ExperimentResult, WindowReport
from chaosforge.report import to_console, to_json, to_markdown


def _result(passed: bool, findings: list[str] | None = None) -> ExperimentResult:
    def window(label: str, rate: float) -> WindowReport:
        return WindowReport(label=label, success_rate=rate, p50_ms=12.0, p95_ms=48.0, samples=10)

    return ExperimentResult(
        experiment="demo",
        passed=passed,
        baseline=window("baseline", 1.0),
        fault=window("fault", 0.4),
        recovery=window("recovery", 1.0),
        findings=findings or [],
    )


def test_json_round_trips_and_rounds_floats():
    payload = json.loads(to_json(_result(passed=True)))

    assert payload["experiment"] == "demo"
    assert payload["passed"] is True
    assert set(payload["windows"]) == {"baseline", "fault", "recovery"}
    assert payload["windows"]["fault"]["success_rate"] == 0.4
    assert payload["windows"]["baseline"]["p95_ms"] == 48.0


def test_markdown_has_a_row_per_window_and_lists_findings():
    md = to_markdown(_result(passed=False, findings=["System did NOT recover"]))

    assert "# Chaos Experiment: demo" in md
    assert "❌ FAILED" in md
    # Header, separator, and one row per window.
    assert md.count("\n| ") >= 3
    assert "| baseline |" in md and "| fault |" in md and "| recovery |" in md
    assert "- System did NOT recover" in md


def test_markdown_says_so_when_there_are_no_findings():
    md = to_markdown(_result(passed=True))

    assert "✅ PASSED" in md
    assert "No resilience gaps detected" in md


def test_console_output_is_ascii_only():
    """to_console promises output "safe for any terminal / CI log".

    A runner under the C/POSIX locale gets an ASCII stdout encoding, and
    printing a non-ASCII glyph there raises UnicodeEncodeError -- the report
    that says the experiment failed would itself fail to print. Both branches
    are checked because the no-findings path is the one that regressed.
    """
    with_findings = to_console(_result(passed=False, findings=["No fault tolerance"]))
    without_findings = to_console(_result(passed=True))

    for text in (with_findings, without_findings):
        text.encode("ascii")  # raises UnicodeEncodeError if a glyph sneaks in

    assert "FAILED" in with_findings
    assert "baseline" in with_findings and "recovery" in with_findings
    assert "  - No fault tolerance" in with_findings


def test_console_reports_a_clean_run():
    text = to_console(_result(passed=True))

    assert "PASSED" in text
    assert "steady state held" in text
