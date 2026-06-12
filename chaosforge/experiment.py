"""Experiment definition and result model.

An experiment is a declarative YAML document with three parts:

  steady_state: the hypothesis the system must satisfy (success rate, latency)
  fault:        the turbulent condition to inject
  schedule:     how long to observe baseline / fault / recovery windows

See examples/ for complete files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass
class SteadyState:
    url: str
    samples: int = 20
    expect_status: int = 200
    min_success_rate: float = 0.99
    max_p95_ms: float = 500.0


@dataclass
class Fault:
    type: str  # latency | error | blackhole
    latency_ms: int = 0
    error_rate: float = 0.0
    error_status: int = 503
    blackhole_rate: float = 0.0


@dataclass
class Schedule:
    baseline_s: float = 3.0
    fault_s: float = 5.0
    recovery_s: float = 3.0


@dataclass
class Experiment:
    name: str
    target: str  # base URL of the real service the proxy forwards to
    steady_state: SteadyState
    fault: Fault
    schedule: Schedule = field(default_factory=Schedule)
    description: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Experiment":
        ss = data["steady_state"]
        fault = data["fault"]
        sched = data.get("schedule", {})
        return cls(
            name=data["name"],
            target=data["target"],
            description=data.get("description", ""),
            steady_state=SteadyState(**ss),
            fault=Fault(**fault),
            schedule=Schedule(**sched),
        )

    @classmethod
    def load(cls, path: str | Path) -> "Experiment":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(yaml.safe_load(fh))


@dataclass
class WindowReport:
    label: str
    success_rate: float
    p50_ms: float
    p95_ms: float
    samples: int


@dataclass
class ExperimentResult:
    experiment: str
    passed: bool
    baseline: WindowReport
    fault: WindowReport
    recovery: WindowReport
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment": self.experiment,
            "passed": self.passed,
            "windows": {
                w.label: {
                    "success_rate": round(w.success_rate, 4),
                    "p50_ms": round(w.p50_ms, 2),
                    "p95_ms": round(w.p95_ms, 2),
                    "samples": w.samples,
                }
                for w in (self.baseline, self.fault, self.recovery)
            },
            "findings": self.findings,
        }
