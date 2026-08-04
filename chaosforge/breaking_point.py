"""Search for the fault magnitude a service stops tolerating.

`chaosforge run` answers a yes/no question: did the system survive *this*
fault? That is the right question when you already know the number you care
about - a 200ms dependency slowdown, a 10% error rate from an upstream.

Often you don't. The useful output is the threshold itself: "checkout holds up
to 380ms of added latency and falls over at 420ms". That number is a budget.
It tells you how much headroom a dependency has before it takes you with it,
and it turns into a regression test - if next month the same search returns
150ms, something got more fragile.

This module binary-searches the fault magnitude for the largest value at which
the steady-state hypothesis still holds. Binary search rather than a linear
ramp because each trial costs a real observation window: a linear sweep over
0-1000ms in 50ms steps is 20 windows, while the search converges to the same
resolution in about 5.

The search assumes tolerance is monotonic - if a service survives 400ms it
would also survive 200ms. That is true of latency and error-rate faults in
practice, and where it isn't (a retry storm that only triggers in a narrow
band) the reported threshold is still a real failure point, just not
necessarily the lowest one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .experiment import Experiment, SteadyState
from .probes import ProbeResult, probe
from .proxy import FaultProxy
from .runner import _path_of

# Per-fault search bounds and units. `error` and `blackhole` are rates, so the
# ceiling is 1.0; latency is unbounded in principle but a service that tolerates
# two seconds of added delay is not what the search is for.
BOUNDS: dict[str, tuple[float, float, str]] = {
    "latency": (0.0, 2000.0, "ms"),
    "error": (0.0, 1.0, "error_rate"),
    "blackhole": (0.0, 1.0, "blackhole_rate"),
}

# Stop when the bracket is narrower than this - further precision is inside the
# noise of a short probe window anyway.
RESOLUTION: dict[str, float] = {"latency": 25.0, "error": 0.05, "blackhole": 0.05}


@dataclass
class Trial:
    magnitude: float
    held: bool
    success_rate: float
    p95_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "magnitude": round(self.magnitude, 4),
            "held": self.held,
            "success_rate": round(self.success_rate, 4),
            "p95_ms": round(self.p95_ms, 2),
        }


@dataclass
class BreakingPoint:
    experiment: str
    fault_type: str
    unit: str
    tolerated: float | None
    breaks_at: float | None
    trials: list[Trial] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return self.breaks_at is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment": self.experiment,
            "fault_type": self.fault_type,
            "unit": self.unit,
            "tolerated": self.tolerated,
            "breaks_at": self.breaks_at,
            "trials": [t.to_dict() for t in self.trials],
        }


def _holds(result: ProbeResult, steady_state: SteadyState, fault_type: str) -> bool:
    """Did the steady-state hypothesis survive this trial?"""
    if result.success_rate < steady_state.min_success_rate:
        return False
    # Latency faults are judged on the latency SLO too - a service that returns
    # 200s ten seconds late is not holding its steady state in any useful sense.
    return not (fault_type == "latency" and result.p95_ms > steady_state.max_p95_ms)


def _arm(proxy: FaultProxy, fault_type: str, magnitude: float) -> None:
    if fault_type == "latency":
        proxy.fault.arm(latency_ms=int(magnitude))
    elif fault_type == "error":
        proxy.fault.arm(error_rate=magnitude)
    elif fault_type == "blackhole":
        proxy.fault.arm(blackhole_rate=magnitude)
    else:  # pragma: no cover - guarded by find_breaking_point
        raise ValueError(f"unknown fault type: {fault_type!r}")


def find_breaking_point(
    experiment: Experiment,
    max_magnitude: float | None = None,
    max_trials: int = 8,
    window_s: float | None = None,
    on_trial: Callable[[Trial], None] | None = None,
) -> BreakingPoint:
    """Binary-search the largest fault magnitude the steady state survives.

    `tolerated` is the highest magnitude observed to hold, `breaks_at` the
    lowest observed to fail. Both are None-able on purpose: a service that
    fails at the smallest tested magnitude has no tolerance to report, and one
    that survives the ceiling has no breaking point *within the search range* -
    which is a real answer, not a failure of the search.
    """
    fault_type = experiment.fault.type
    if fault_type not in BOUNDS:
        raise ValueError(
            f"breaking-point search supports {sorted(BOUNDS)}; got {fault_type!r}. "
            f"Resource faults (cpu/memory/disk) are host-level, not proxy-injected."
        )

    low, ceiling, unit = BOUNDS[fault_type]
    high = float(max_magnitude) if max_magnitude is not None else ceiling
    resolution = RESOLUTION[fault_type]
    ss = experiment.steady_state
    observe_s = window_s if window_s is not None else experiment.schedule.fault_s

    result = BreakingPoint(
        experiment=experiment.name,
        fault_type=fault_type,
        unit=unit,
        tolerated=None,
        breaks_at=None,
    )

    with FaultProxy(target_base=experiment.target) as proxy:
        probe_url = proxy.base_url + _path_of(ss.url)

        def trial_at(magnitude: float) -> Trial:
            _arm(proxy, fault_type, magnitude)
            observed = probe(
                probe_url,
                samples=ss.samples,
                expect_status=ss.expect_status,
                window_s=observe_s,
            )
            proxy.fault.disarm()
            trial = Trial(
                magnitude=magnitude,
                held=_holds(observed, ss, fault_type),
                success_rate=observed.success_rate,
                p95_ms=observed.p95_ms,
            )
            result.trials.append(trial)
            if on_trial is not None:
                on_trial(trial)
            return trial

        # Probe the ceiling first. If the service survives the worst case there
        # is no threshold to bisect for, and the search is over in one window
        # instead of eight.
        if trial_at(high).held:
            result.tolerated = high
            return result

        result.breaks_at = high
        while len(result.trials) < max_trials and (high - low) > resolution:
            midpoint = (low + high) / 2
            if trial_at(midpoint).held:
                low = midpoint
                result.tolerated = midpoint
            else:
                high = midpoint
                result.breaks_at = midpoint

    return result
