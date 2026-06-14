"""Command-line interface for chaos-forge.

    chaosforge run experiment.yaml [--json] [--md report.md]
    chaosforge validate experiment.yaml
    chaosforge proxy --target http://localhost:8000 --port 9000 \
        [--latency-ms 200] [--error-rate 0.3]
"""

from __future__ import annotations

import argparse
import sys
import time

from . import __version__
from .experiment import Experiment
from .proxy import FaultProxy
from .report import to_console, to_json, to_markdown
from .runner import run_experiment


def _cmd_run(args: argparse.Namespace) -> int:
    experiment = Experiment.load(args.file)
    result = run_experiment(experiment)

    if args.json:
        print(to_json(result))
    else:
        print(to_console(result))

    if args.md:
        with open(args.md, "w", encoding="utf-8") as fh:
            fh.write(to_markdown(result))
        print(f"\nMarkdown report written to {args.md}", file=sys.stderr)

    return 0 if result.passed else 1


def _cmd_validate(args: argparse.Namespace) -> int:
    try:
        exp = Experiment.load(args.file)
    except Exception as exc:  # noqa: BLE001 - surface any parse error to the user
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    print(f"OK: '{exp.name}' targets {exp.target}, fault={exp.fault.type}")
    return 0


def _cmd_proxy(args: argparse.Namespace) -> int:
    proxy = FaultProxy(target_base=args.target, port=args.port).start()
    proxy.fault.arm(
        latency_ms=args.latency_ms,
        error_rate=args.error_rate,
        blackhole_rate=args.blackhole_rate,
    )
    print(f"chaos-forge proxy on {proxy.base_url} -> {args.target}")
    print(
        f"  latency={args.latency_ms}ms error_rate={args.error_rate} "
        f"blackhole_rate={args.blackhole_rate}"
    )
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nstopping proxy...")
    finally:
        proxy.stop()
    return 0


FAULT_CATALOG = {
    "latency": "Add fixed latency (ms) to every proxied request (--latency-ms).",
    "error": "Return HTTP 500 for a fraction of requests (--error-rate).",
    "blackhole": "Drop a fraction of connections with no reply (--blackhole-rate).",
    "cpu": "Saturate CPU cores for a duration (host fault: cpu_hog).",
    "memory": "Allocate and hold memory to create pressure (host fault: memory_hog).",
}


def _cmd_list_faults(args: argparse.Namespace) -> int:
    """List the fault types Chaos-Forge can inject."""
    if getattr(args, "json", False):
        import json
        print(json.dumps(FAULT_CATALOG, indent=2))
    else:
        for name, desc in FAULT_CATALOG.items():
            print(f"{name:10} {desc}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chaosforge", description=__doc__)
    parser.add_argument("--version", action="version", version=f"chaos-forge {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run an experiment file")
    run.add_argument("file")
    run.add_argument("--json", action="store_true", help="emit JSON instead of text")
    run.add_argument("--md", metavar="PATH", help="also write a Markdown report")
    run.set_defaults(func=_cmd_run)

    val = sub.add_parser("validate", help="validate an experiment file")
    val.add_argument("file")
    val.set_defaults(func=_cmd_validate)

    px = sub.add_parser("proxy", help="run a standalone fault-injecting proxy")
    px.add_argument("--target", required=True)
    px.add_argument("--port", type=int, default=9000)
    px.add_argument("--latency-ms", type=int, default=0)
    px.add_argument("--error-rate", type=float, default=0.0)
    px.add_argument("--blackhole-rate", type=float, default=0.0)
    px.set_defaults(func=_cmd_proxy)

    lf = sub.add_parser("list-faults", help="list the fault types that can be injected")
    lf.add_argument("--json", action="store_true", help="emit JSON instead of text")
    lf.set_defaults(func=_cmd_list_faults)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
