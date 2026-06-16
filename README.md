# chaos-forge

[![CI](https://github.com/vk86294140-cloud/chaos-forge/actions/workflows/ci.yml/badge.svg)](https://github.com/vk86294140-cloud/chaos-forge/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A lightweight **chaos-engineering toolkit** for HTTP services. Inject controlled
faults in front of any service, validate a steady-state hypothesis across a
baseline → fault → recovery cycle, and get a pass/fail resilience report with
concrete findings.

Built around the core discipline of chaos engineering: a **measurable steady
state**, a **single turbulent variable**, a **bounded blast radius**, and an
**automatic rollback** so nothing is left broken.

> I built this after running fault-injection experiments (latency, instance and
> dependency failures, network faults) against multi-region AWS services and
> wanting a small, dependency-light tool that encodes the same loop —
> hypothesis, inject, observe, roll back, report — and runs anywhere, including
> in CI.

## Why it's different

- **Zero infra to attack a service.** A built-in fault-injecting reverse proxy
  sits in front of any HTTP target — no agents, no sidecars, no kernel tricks.
- **Standard-library core.** The proxy, probes, and runner use only the Python
  stdlib (`pyyaml` is the single runtime dependency), so it drops into any
  environment and any container.
- **Hypothesis-driven.** Experiments are declarative YAML with explicit SLOs
  (success rate, p95 latency). The exit code is CI-friendly: non-zero when the
  hypothesis fails.
- **Always reversible.** Faults are armed and disarmed at runtime; resource
  faults are context managers that always clean up.

## Faults supported

| Fault | What it does | Use it to test |
| --- | --- | --- |
| `latency` | Adds N ms to every proxied request | timeouts, retries, p95 SLOs |
| `error` | Returns 5xx for a fraction of requests | retry/fallback policies, circuit breakers |
| `blackhole` | Drops a fraction of connections silently | client timeouts, hung-connection handling |
| `cpu_hog` | Saturates N cores (context manager) | autoscaling, CPU-bound degradation |
| `memory_hog` | Allocates and touches N MB | OOM behaviour, memory headroom |
| `disk_hog` | Fills N MB of disk with a scratch file | log spew, full-disk handling, cache eviction |

## Install

```bash
git clone https://github.com/vk86294140-cloud/chaos-forge.git
cd chaos-forge
pip install -e ".[dev]"
```

## Quickstart (60 seconds)

```bash
# 1. Start a demo service to attack (stdlib only, listens on :8000)
python examples/demo_target.py

# 2. In another terminal, run an experiment
chaosforge run examples/latency_experiment.yaml
```

Example output:

```
Experiment: latency-injection-health-endpoint  ->  PASSED

window      success    p50 ms    p95 ms
----------------------------------------
baseline       100%         1         2
fault          100%       201       205
recovery       100%         1         2

Findings:
  - Latency SLO breached under fault: p95 205ms > 150ms. Consider timeouts,
    retries with backoff, or a circuit breaker.
```

The service stayed available (passed) but the run **surfaced a latency SLO
breach** — exactly the kind of finding a chaos experiment exists to produce.

## Writing an experiment

```yaml
name: latency-injection-health-endpoint
target: http://localhost:8000        # the real service to forward to

steady_state:
  url: /health                       # endpoint to probe
  samples: 30
  expect_status: 200
  min_success_rate: 0.99             # availability SLO
  max_p95_ms: 150                    # latency SLO

fault:
  type: latency                      # latency | error | blackhole
  latency_ms: 200

schedule:
  baseline_s: 2
  fault_s: 4
  recovery_s: 2
```

Validate before running:

```bash
chaosforge validate examples/latency_experiment.yaml
```

## Use the proxy standalone

Put a degraded version of any service in front of your client for manual or
load testing:

```bash
chaosforge proxy --target http://localhost:8000 --port 9000 \
  --latency-ms 300 --error-rate 0.2
# now hit http://localhost:9000 instead of :8000
```

## Run in CI

`chaosforge run` exits non-zero when the steady-state hypothesis fails, so a
resilience regression breaks the build:

```yaml
- name: Resilience check
  run: |
    python examples/demo_target.py &
    sleep 1
    chaosforge run examples/latency_experiment.yaml --md chaos-report.md
```

## Run with Docker

```bash
docker build -t chaos-forge .
docker run --rm --network host chaos-forge run examples/latency_experiment.yaml
```

## Project layout

```
chaosforge/
  proxy.py        fault-injecting reverse proxy (stdlib)
  probes.py       steady-state probe + p50/p95 statistics
  experiment.py   YAML experiment + result models
  runner.py       baseline -> fault -> recovery orchestration + verdict
  report.py       text / Markdown / JSON reporters
  cli.py          chaosforge run | validate | proxy
  faults/         host-level faults (cpu_hog, memory_hog)
examples/         demo target + ready-to-run experiments
tests/            pytest suite (real in-process target, no mocks)
```

## Testing

```bash
pytest -v
```

The suite spins up a real in-process HTTP target and asserts that latency is
actually injected, errors actually drop the success rate, and faults are fully
rolled back on disarm.

## License

MIT — see [LICENSE](LICENSE).
