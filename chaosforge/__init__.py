"""chaos-forge: a lightweight chaos-engineering toolkit for HTTP services.

Inject controlled faults (latency, errors, connection drops, resource
exhaustion) in front of a target service, validate a steady-state hypothesis
before/during/after the fault, and produce a pass/fail resilience report.
"""

__version__ = "0.1.0"

from .experiment import Experiment, ExperimentResult
from .runner import run_experiment

__all__ = ["Experiment", "ExperimentResult", "run_experiment", "__version__"]
