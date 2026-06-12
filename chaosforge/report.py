"""Render experiment results as text, Markdown, or JSON."""

from __future__ import annotations

import json

from .experiment import ExperimentResult


def to_json(result: ExperimentResult, indent: int = 2) -> str:
    return json.dumps(result.to_dict(), indent=indent)


def to_markdown(result: ExperimentResult) -> str:
    verdict = "✅ PASSED" if result.passed else "❌ FAILED"
    lines = [
        f"# Chaos Experiment: {result.experiment}",
        "",
        f"**Verdict:** {verdict}",
        "",
        "| Window | Success rate | p50 (ms) | p95 (ms) | Samples |",
        "| --- | --- | --- | --- | --- |",
    ]
    for w in (result.baseline, result.fault, result.recovery):
        lines.append(
            f"| {w.label} | {w.success_rate:.0%} | {w.p50_ms:.0f} | "
            f"{w.p95_ms:.0f} | {w.samples} |"
        )
    lines.append("")
    if result.findings:
        lines.append("## Findings")
        for f in result.findings:
            lines.append(f"- {f}")
    else:
        lines.append("## Findings")
        lines.append("- No resilience gaps detected. System held its steady state.")
    lines.append("")
    return "\n".join(lines)


def to_console(result: ExperimentResult) -> str:
    """Plain, color-free console summary (safe for any terminal / CI log)."""
    verdict = "PASSED" if result.passed else "FAILED"
    out = [f"Experiment: {result.experiment}  ->  {verdict}", ""]
    header = f"{'window':<10}{'success':>10}{'p50 ms':>10}{'p95 ms':>10}"
    out.append(header)
    out.append("-" * len(header))
    for w in (result.baseline, result.fault, result.recovery):
        out.append(
            f"{w.label:<10}{w.success_rate * 100:>9.0f}%{w.p50_ms:>10.0f}{w.p95_ms:>10.0f}"
        )
    out.append("")
    if result.findings:
        out.append("Findings:")
        for f in result.findings:
            out.append(f"  - {f}")
    else:
        out.append("Findings: none — steady state held.")
    return "\n".join(out)
