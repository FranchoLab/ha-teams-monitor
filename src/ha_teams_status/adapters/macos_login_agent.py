"""Install and remove the current user's macOS LaunchAgent."""

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

LABEL = "com.ha-teams-status.monitor"
LAUNCHCTL = "/bin/launchctl"
EXECUTABLE_NAME = "ha-teams-status"


class LaunchAgentError(Exception):
    """Raised when a LaunchAgent cannot be installed or removed safely."""


CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True, slots=True)
class LaunchAgentPaths:
    plist: Path
    stdout: Path
    stderr: Path
    runtime: Path
    executable: Path


def require_macos() -> None:
    if sys.platform != "darwin":
        raise LaunchAgentError("the login agent is supported only on macOS")


def launch_agent_paths(home: Path | None = None) -> LaunchAgentPaths:
    user_home = (home or Path.home()).expanduser().resolve()
    return LaunchAgentPaths(
        plist=user_home / "Library" / "LaunchAgents" / f"{LABEL}.plist",
        stdout=user_home / "Library" / "Logs" / "ha-teams-status" / "stdout.log",
        stderr=user_home / "Library" / "Logs" / "ha-teams-status" / "stderr.log",
        runtime=user_home / "Library" / "Application Support" / "ha-teams-status" / "runtime",
        executable=user_home
        / "Library"
        / "Application Support"
        / "ha-teams-status"
        / "runtime"
        / EXECUTABLE_NAME,
    )


def build_launch_agent_plist(
    config_path: Path,
    *,
    executable: Path,
    home: Path | None = None,
) -> dict[str, object]:
    paths = launch_agent_paths(home)
    try:
        program = executable.expanduser().absolute()
        config = config_path.expanduser().resolve(strict=True)
    except OSError as error:
        raise LaunchAgentError(f"unable to resolve login agent paths: {error}") from None
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(program),
            "--config",
            str(config),
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(paths.stdout),
        "StandardErrorPath": str(paths.stderr),
    }


ExecutableBuilder = Callable[[Path], Path]
BuildCommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _run_build_command(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, capture_output=True, text=True, check=False)


def build_standalone_executable(
    build_directory: Path,
    *,
    command_runner: BuildCommandRunner | None = None,
) -> Path:
    if find_spec("PyInstaller") is None:
        raise LaunchAgentError(
            "PyInstaller is required to build the macOS service executable; "
            "install it with `uv sync --frozen --extra macos-service`"
        )

    output_directory = build_directory / "dist"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        EXECUTABLE_NAME,
        "--distpath",
        str(output_directory),
        "--workpath",
        str(build_directory / "work"),
        "--specpath",
        str(build_directory / "spec"),
        "--copy-metadata",
        "ha-teams-status",
        str(Path(__file__).resolve().parents[1] / "_macos_bundle_entry.py"),
    ]
    try:
        result = (command_runner or _run_build_command)(command)
    except OSError as error:
        raise LaunchAgentError(f"unable to run PyInstaller: {error}") from None
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        message = "PyInstaller failed to build the macOS service executable"
        if detail:
            message = f"{message}: {detail}"
        raise LaunchAgentError(message)

    executable = output_directory / EXECUTABLE_NAME / EXECUTABLE_NAME
    if not executable.is_file():
        raise LaunchAgentError("PyInstaller completed without producing the named executable")
    return executable


def _run_command(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, capture_output=True, text=True, check=False)


class MacOSLoginAgent:
    def __init__(
        self,
        *,
        home: Path | None = None,
        uid: int | None = None,
        command_runner: CommandRunner | None = None,
        executable_builder: ExecutableBuilder | None = None,
    ) -> None:
        self._home = home
        self._uid = os.getuid() if uid is None else uid
        self._command_runner = command_runner or _run_command
        self._executable_builder = executable_builder or build_standalone_executable

    @property
    def paths(self) -> LaunchAgentPaths:
        return launch_agent_paths(self._home)

    @property
    def domain(self) -> str:
        return f"gui/{self._uid}"

    def install(self, config_path: Path) -> None:
        require_macos()
        try:
            config = config_path.expanduser().resolve(strict=True)
        except OSError as error:
            raise LaunchAgentError(f"unable to resolve configuration path: {error}") from None

        with tempfile.TemporaryDirectory(prefix="ha-teams-status-build-") as build_directory:
            executable = self._executable_builder(Path(build_directory))
            if not executable.is_file() or executable.name != EXECUTABLE_NAME:
                raise LaunchAgentError(
                    "the build did not produce a named ha-teams-status executable"
                )
            definition = build_launch_agent_plist(
                config,
                executable=self.paths.executable,
                home=self._home,
            )
            serialized = plistlib.dumps(definition, sort_keys=True)
            staging_parent = self._prepare_directories_and_stage(executable.parent)
            try:
                self._bootout_if_registered()
                backup = self._replace_runtime(staging_parent / "runtime")
                self._write_plist(serialized)
                self._launchctl("bootstrap", str(self.paths.plist))
                if backup is not None:
                    self._remove_runtime(backup)
            finally:
                try:
                    shutil.rmtree(staging_parent)
                except OSError as error:
                    raise LaunchAgentError(
                        f"unable to clean temporary login agent files: {error}"
                    ) from None

    def uninstall(self) -> None:
        require_macos()
        self._bootout_if_registered()
        try:
            self.paths.plist.unlink(missing_ok=True)
        except OSError as error:
            raise LaunchAgentError(f"unable to remove login agent definition: {error}") from None
        self._remove_runtime(self.paths.runtime)

    def _prepare_directories_and_stage(self, built_bundle: Path) -> Path:
        staging_parent: Path | None = None
        try:
            self.paths.plist.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.paths.stdout.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.paths.runtime.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            staging_parent = Path(
                tempfile.mkdtemp(
                    prefix=".ha-teams-status-stage-",
                    dir=self.paths.runtime.parent,
                )
            )
            shutil.copytree(built_bundle, staging_parent / "runtime")
            return staging_parent
        except OSError as error:
            if staging_parent is not None:
                try:
                    shutil.rmtree(staging_parent)
                except OSError as cleanup_error:
                    raise LaunchAgentError(
                        "unable to stage the login agent executable "
                        f"and clean up temporary files: {cleanup_error}"
                    ) from None
            raise LaunchAgentError(f"unable to stage the login agent executable: {error}") from None

    def _replace_runtime(self, staged_runtime: Path) -> Path | None:
        backup = self.paths.runtime.with_name(".runtime-backup")
        try:
            if backup.exists():
                shutil.rmtree(backup)
            if self.paths.runtime.exists():
                self.paths.runtime.replace(backup)
            staged_runtime.replace(self.paths.runtime)
        except OSError as error:
            if backup.exists() and not self.paths.runtime.exists():
                try:
                    backup.replace(self.paths.runtime)
                except OSError as restore_error:
                    raise LaunchAgentError(
                        "unable to replace the login agent runtime and restore the previous "
                        f"runtime: {restore_error}"
                    ) from None
            raise LaunchAgentError(f"unable to replace the login agent runtime: {error}") from None
        return backup if backup.exists() else None

    def _remove_runtime(self, runtime: Path) -> None:
        try:
            shutil.rmtree(runtime)
        except FileNotFoundError:
            return
        except OSError as error:
            raise LaunchAgentError(f"unable to remove login agent runtime: {error}") from None

    def _bootout_if_registered(self) -> None:
        service = f"{self.domain}/{LABEL}"
        try:
            status = self._command_runner([LAUNCHCTL, "print", service])
        except OSError as error:
            raise LaunchAgentError(f"unable to check login agent status: {error}") from None
        if status.returncode != 0:
            if self._is_absent(status):
                return
            self._raise_command_error("check login agent status", status)

        try:
            result = self._command_runner(
                [LAUNCHCTL, "bootout", self.domain, str(self.paths.plist)]
            )
        except OSError as error:
            raise LaunchAgentError(f"unable to run launchctl bootout: {error}") from None
        if result.returncode != 0:
            self._raise_command_error("boot out login agent", result)

    def _launchctl(self, operation: str, service_definition: str) -> None:
        try:
            result = self._command_runner([LAUNCHCTL, operation, self.domain, service_definition])
        except OSError as error:
            raise LaunchAgentError(f"unable to run launchctl {operation}: {error}") from None
        if result.returncode != 0:
            self._raise_command_error(f"{operation} login agent", result)

    @staticmethod
    def _is_absent(result: subprocess.CompletedProcess[str]) -> bool:
        output = f"{result.stdout}\n{result.stderr}".casefold()
        return any(
            message in output
            for message in (
                "could not find service",
                "could not find specified service",
                "service not found",
                "no such process",
            )
        )

    @staticmethod
    def _raise_command_error(
        operation: str,
        result: subprocess.CompletedProcess[str],
    ) -> None:
        detail = (result.stderr or result.stdout).strip()
        message = f"unable to {operation}"
        if detail:
            message = f"{message}: {detail}"
        raise LaunchAgentError(message)

    def _write_plist(self, serialized: bytes) -> None:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.paths.plist.parent,
                prefix=f".{LABEL}.",
                delete=False,
            ) as plist_file:
                temporary_path = Path(plist_file.name)
                plist_file.write(serialized)
                plist_file.flush()
                os.fsync(plist_file.fileno())
            temporary_path.chmod(0o600)
            temporary_path.replace(self.paths.plist)
        except OSError as error:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError as cleanup_error:
                    raise LaunchAgentError(
                        "unable to write login agent definition "
                        f"and could not clean up its temporary file: {cleanup_error}"
                    ) from None
            raise LaunchAgentError(f"unable to write login agent definition: {error}") from None
