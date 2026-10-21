import importlib.machinery
import plistlib
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

import ha_teams_status.adapters.macos_login_agent as login_agent
from ha_teams_status.adapters.macos_login_agent import (
    EXECUTABLE_NAME,
    LABEL,
    LAUNCHCTL,
    LaunchAgentError,
    MacOSLoginAgent,
    build_launch_agent_plist,
    build_standalone_executable,
    launch_agent_paths,
)


class FakeCommandRunner:
    def __init__(self, results: list[subprocess.CompletedProcess[str]]) -> None:
        self.results = results
        self.calls: list[list[str]] = []

    def __call__(
        self,
        arguments: Sequence[str],
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(arguments))
        return self.results.pop(0)


def _result(
    returncode: int = 0,
    *,
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, "", stderr)


def _fake_bundle_builder(build_directory: Path) -> Path:
    bundle = build_directory / "dist" / EXECUTABLE_NAME
    bundle.mkdir(parents=True)
    executable = bundle / EXECUTABLE_NAME
    executable.write_text("test executable", encoding="utf-8")
    executable.chmod(0o700)
    return executable


def _mark_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")


def test_plist_uses_absolute_paths_and_contains_no_credentials(tmp_path: Path) -> None:
    config = tmp_path / "monitor.conf"
    config.write_text("[mqtt]\npassword = do-not-copy-this\n", encoding="utf-8")
    executable = tmp_path / "runtime" / EXECUTABLE_NAME
    paths = launch_agent_paths(tmp_path)

    plist = build_launch_agent_plist(
        config,
        executable=executable,
        home=tmp_path,
    )
    encoded = plistlib.dumps(plist)

    assert plist["Label"] == LABEL
    assert plist["ProgramArguments"] == [
        str(executable.absolute()),
        "--config",
        str(config.resolve()),
    ]
    assert Path(plist["ProgramArguments"][0]).name == EXECUTABLE_NAME
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] is True
    assert plist["StandardOutPath"] == str(paths.stdout)
    assert plist["StandardErrorPath"] == str(paths.stderr)
    assert b"do-not-copy-this" not in encoded


def test_build_standalone_executable_invokes_pyinstaller(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        arguments: Sequence[str],
    ) -> subprocess.CompletedProcess[str]:
        calls.append(list(arguments))
        dist = Path(arguments[arguments.index("--distpath") + 1])
        bundle = dist / EXECUTABLE_NAME
        bundle.mkdir(parents=True)
        executable = bundle / EXECUTABLE_NAME
        executable.touch()
        return _result()

    monkeypatch.setattr(
        login_agent,
        "find_spec",
        lambda _module: importlib.machinery.ModuleSpec("PyInstaller", loader=None),
    )

    executable = build_standalone_executable(tmp_path, command_runner=fake_run)

    assert executable == tmp_path / "dist" / EXECUTABLE_NAME / EXECUTABLE_NAME
    assert calls[0][1:4] == ["-m", "PyInstaller", "--noconfirm"]
    assert "--onedir" in calls[0]
    assert "--copy-metadata" in calls[0]


def test_build_standalone_executable_reports_build_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        login_agent,
        "find_spec",
        lambda _module: importlib.machinery.ModuleSpec("PyInstaller", loader=None),
    )

    with pytest.raises(LaunchAgentError, match="build failed"):
        build_standalone_executable(
            tmp_path,
            command_runner=lambda _arguments: _result(1, stderr="build failed"),
        )


def test_readme_login_agent_commands_and_paths_match_adapter() -> None:
    readme = Path(__file__).resolve().parents[1] / "README.md"
    documentation = readme.read_text(encoding="utf-8")
    normalized_documentation = " ".join(documentation.split())
    paths = launch_agent_paths(Path.home())

    assert "ha-teams-status service install --config ./monitor.conf" in documentation
    assert "ha-teams-status service uninstall" in documentation
    assert "uv sync --frozen --extra macos-service" in documentation
    assert "Activity Monitor" in documentation
    assert "after updating the application" in normalized_documentation
    assert f"~/{paths.plist.relative_to(Path.home())}" in documentation
    assert f"~/{paths.stdout.relative_to(Path.home())}" in documentation
    assert f"~/{paths.stderr.relative_to(Path.home())}" in documentation
    assert f"~/{paths.runtime.relative_to(Path.home())}" in documentation
    domain = f"gui/$(id -u)/{LABEL}"
    assert f"launchctl print {domain}" in documentation
    assert f"launchctl kickstart -k {domain}" in documentation


def test_install_writes_private_plist_and_bootstraps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mark_macos(monkeypatch)
    config = tmp_path / "monitor.conf"
    config.touch()
    runner = FakeCommandRunner(
        [
            _result(113, stderr="Could not find service"),
            _result(),
        ]
    )
    agent = MacOSLoginAgent(
        home=tmp_path,
        uid=501,
        command_runner=runner,
        executable_builder=_fake_bundle_builder,
    )

    agent.install(config)

    plist_path = agent.paths.plist
    with plist_path.open("rb") as plist_file:
        plist = plistlib.load(plist_file)
    assert plist["ProgramArguments"] == [
        str(agent.paths.executable),
        "--config",
        str(config.resolve()),
    ]
    assert agent.paths.executable.is_file()
    assert plist_path.stat().st_mode & 0o777 == 0o600
    assert runner.calls == [
        [LAUNCHCTL, "print", f"gui/501/{LABEL}"],
        [LAUNCHCTL, "bootstrap", "gui/501", str(plist_path)],
    ]


def test_install_replaces_an_existing_definition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mark_macos(monkeypatch)
    old_config = tmp_path / "old.conf"
    new_config = tmp_path / "new.conf"
    old_config.touch()
    new_config.touch()
    runner = FakeCommandRunner([_result(), _result(), _result()])
    agent = MacOSLoginAgent(
        home=tmp_path,
        uid=501,
        command_runner=runner,
        executable_builder=_fake_bundle_builder,
    )
    agent.paths.plist.parent.mkdir(parents=True)
    agent.paths.plist.write_text("old definition", encoding="utf-8")
    agent.paths.runtime.mkdir(parents=True)
    stale_file = agent.paths.runtime / "stale-runtime-file"
    stale_file.touch()

    agent.install(new_config)

    with agent.paths.plist.open("rb") as plist_file:
        plist = plistlib.load(plist_file)
    assert plist["ProgramArguments"][-1] == str(new_config.resolve())
    assert agent.paths.executable.is_file()
    assert not stale_file.exists()
    assert not agent.paths.runtime.with_name(".runtime-backup").exists()
    assert [call[1] for call in runner.calls] == ["print", "bootout", "bootstrap"]


def test_uninstall_is_idempotent_when_registration_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mark_macos(monkeypatch)
    runner = FakeCommandRunner(
        [
            _result(113, stderr="Could not find service"),
            _result(113, stderr="Could not find service"),
        ]
    )
    agent = MacOSLoginAgent(home=tmp_path, uid=501, command_runner=runner)
    agent.paths.plist.parent.mkdir(parents=True)
    agent.paths.plist.touch()
    agent.paths.runtime.mkdir(parents=True)
    (agent.paths.runtime / EXECUTABLE_NAME).touch()

    agent.uninstall()
    agent.uninstall()

    assert not agent.paths.plist.exists()
    assert not agent.paths.runtime.exists()
    assert len(runner.calls) == 2


def test_launchctl_errors_are_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mark_macos(monkeypatch)
    config = tmp_path / "monitor.conf"
    config.touch()
    runner = FakeCommandRunner(
        [
            _result(113, stderr="Could not find service"),
            _result(5, stderr="Bootstrap failed"),
        ]
    )
    agent = MacOSLoginAgent(
        home=tmp_path,
        uid=501,
        command_runner=runner,
        executable_builder=_fake_bundle_builder,
    )

    with pytest.raises(LaunchAgentError, match="Bootstrap failed"):
        agent.install(config)


def test_build_failure_does_not_change_service_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mark_macos(monkeypatch)
    config = tmp_path / "monitor.conf"
    config.touch()
    runner = FakeCommandRunner([])

    def fail_builder(_build_directory: Path) -> Path:
        raise LaunchAgentError("build failed")

    agent = MacOSLoginAgent(
        home=tmp_path,
        uid=501,
        command_runner=runner,
        executable_builder=fail_builder,
    )

    with pytest.raises(LaunchAgentError, match="build failed"):
        agent.install(config)

    assert runner.calls == []
    assert not agent.paths.plist.exists()
