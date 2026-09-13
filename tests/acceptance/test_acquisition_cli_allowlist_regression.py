"""Regressions for the acquisition CLI boundary.

These tests protect two failures found during review of the first Acquisition UI/API
integration: the refresh route uses the read-only `coverage` verb, and an absent
CLI configuration must never render a bogus `None` executable path.
"""

from pathlib import Path

import pytest
from continuum_storage import AcquisitionCliError, AcquisitionStore


def test_coverage_refresh_is_allowlisted_but_apply_is_not(tmp_path: Path) -> None:
    data_dir = tmp_path / "acquisition"
    data_dir.mkdir()
    cli = tmp_path / "acquisition_orchestrator.py"
    cli.write_text("print('ok')\n", encoding="utf-8")

    store = AcquisitionStore(str(data_dir), cli_path=str(cli))

    command = store.build_command("coverage")
    assert command[-1] == "coverage"

    with pytest.raises(AcquisitionCliError, match="--apply"):
        store.build_command("coverage", "--apply")


def test_missing_cli_path_does_not_build_a_fake_none_command(tmp_path: Path) -> None:
    data_dir = tmp_path / "acquisition"
    data_dir.mkdir()
    store = AcquisitionStore(str(data_dir))

    with pytest.raises(AcquisitionCliError, match="CLI path"):
        store.build_command("coverage")
