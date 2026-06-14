"""Tests for the list-faults CLI command."""
from chaosforge.cli import main, FAULT_CATALOG


def test_list_faults_text(capsys):
    assert main(["list-faults"]) == 0
    out = capsys.readouterr().out
    assert "latency" in out and "blackhole" in out


def test_list_faults_json(capsys):
    import json
    assert main(["list-faults", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert set(data) == set(FAULT_CATALOG)
