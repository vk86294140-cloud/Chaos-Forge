"""CLI tests. Everything runs in-process so no subprocess or network is needed."""

from __future__ import annotations

import json

import pytest

from chaosforge.cli import main

FAST_SCHEDULE = "schedule:\n  baseline_s: 0\n  fault_s: 0\n  recovery_s: 0\n"


def _write_experiment(tmp_path, target: str, name: str = "cli-exp"):
    path = tmp_path / "exp.yaml"
    path.write_text(
        f"""
name: {name}
target: {target}
steady_state:
  url: /health
  samples: 4
  min_success_rate: 0.99
  max_p95_ms: 5000
fault:
  type: latency
  latency_ms: 5
{FAST_SCHEDULE}""",
        encoding="utf-8",
    )
    return path


def test_version_flag_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "chaos-forge" in capsys.readouterr().out


def test_list_faults_text_lists_every_catalog_entry(capsys):
    assert main(["list-faults"]) == 0

    out = capsys.readouterr().out
    for name in ("latency", "error", "blackhole", "cpu", "memory", "disk"):
        assert name in out


def test_list_faults_json_is_parseable(capsys):
    assert main(["list-faults", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["latency"].startswith("Add fixed latency")


def test_validate_accepts_a_good_file(tmp_path, capsys, target_server):
    path = _write_experiment(tmp_path, target_server, name="valid-exp")

    assert main(["validate", str(path)]) == 0
    assert "OK: 'valid-exp'" in capsys.readouterr().out


def test_validate_rejects_a_broken_file(tmp_path, capsys):
    path = tmp_path / "bad.yaml"
    path.write_text("name: missing-everything-else\n", encoding="utf-8")

    assert main(["validate", str(path)]) == 1
    assert "INVALID" in capsys.readouterr().err


def test_run_exits_zero_and_writes_markdown(tmp_path, capsys, target_server):
    path = _write_experiment(tmp_path, target_server)
    report = tmp_path / "report.md"

    assert main(["run", str(path), "--md", str(report)]) == 0

    assert "cli-exp" in capsys.readouterr().out
    assert "# Chaos Experiment: cli-exp" in report.read_text(encoding="utf-8")


def test_run_json_emits_a_parseable_document(tmp_path, capsys, target_server):
    path = _write_experiment(tmp_path, target_server)

    assert main(["run", str(path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["experiment"] == "cli-exp"
    assert payload["windows"]["baseline"]["success_rate"] == 1.0


def test_run_exits_nonzero_when_the_hypothesis_breaks(tmp_path, capsys):
    """A target that is already down fails its baseline, and the exit code has
    to reflect that so the command is usable as a CI gate."""
    path = tmp_path / "down.yaml"
    path.write_text(
        f"""
name: dead-target
target: http://127.0.0.1:1
steady_state:
  url: /health
  samples: 2
  min_success_rate: 0.99
fault:
  type: latency
  latency_ms: 1
{FAST_SCHEDULE}""",
        encoding="utf-8",
    )

    assert main(["run", str(path)]) == 1
    assert "Baseline already unhealthy" in capsys.readouterr().out
