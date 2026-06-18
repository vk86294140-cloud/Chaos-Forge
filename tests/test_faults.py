"""Tests for host-level resource faults — focus on the disk-fill injector.

These assert the cardinal rule: a fault must be fully reversible. The scratch
file disk_hog writes has to disappear on exit, including when the body raises.
"""

from pathlib import Path

import pytest

from chaosforge.faults import disk_hog


def test_disk_hog_creates_then_removes_file(tmp_path):
    seen: Path | None = None
    with disk_hog(megabytes=2, path=tmp_path) as scratch:
        seen = scratch
        assert scratch.exists()
        # File is at least the requested size (2 MiB).
        assert scratch.stat().st_size >= 2 * 1024 * 1024
        assert scratch.parent == tmp_path
    # Rolled back on exit.
    assert seen is not None and not seen.exists()


def test_disk_hog_cleans_up_on_exception(tmp_path):
    captured: Path | None = None
    with pytest.raises(RuntimeError):
        with disk_hog(megabytes=1, path=tmp_path) as scratch:
            captured = scratch
            assert scratch.exists()
            raise RuntimeError("boom")
    assert captured is not None and not captured.exists()


def test_disk_hog_leaves_no_residue(tmp_path):
    with disk_hog(megabytes=1, path=tmp_path):
        pass
    # The scratch directory holds nothing afterward.
    assert list(tmp_path.iterdir()) == []
