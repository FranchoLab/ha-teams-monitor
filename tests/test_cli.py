import subprocess
import sys
from importlib.metadata import version

import pytest

from ha_teams_status.__main__ import main


def test_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as result:
        main(["--help"])
    assert result.value.code == 0
    assert "Live monitoring is not implemented" in capsys.readouterr().out


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as result:
        main(["--version"])
    assert result.value.code == 0
    assert capsys.readouterr().out.strip() == version("ha-teams-status")


def test_no_monitoring_fallback(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as result:
        main([])
    assert result.value.code == 2
    assert "Live monitoring is not implemented" in capsys.readouterr().err


def test_module_entrypoint() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ha_teams_status", "--version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert result.stdout.strip() == version("ha-teams-status")
