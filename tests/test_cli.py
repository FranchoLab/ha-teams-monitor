import logging
import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import pytest

import ha_teams_status.__main__ as cli
from ha_teams_status.__main__ import main, run_monitoring
from ha_teams_status.adapters.configuration import MonitorConfig, MonitorSettings, MqttSettings
from ha_teams_status.adapters.windows_teams import WindowsTeamsDetector
from ha_teams_status.application.monitor import DetectionError
from ha_teams_status.domain.observation import (
    MeetingObservation,
    ObservationReason,
    ObservationState,
)

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


@dataclass
class FakeDetector:
    observation: MeetingObservation | None = None
    error: DetectionError | None = None

    def detect(self) -> MeetingObservation:
        if self.error is not None:
            raise self.error
        assert self.observation is not None
        return self.observation


@dataclass
class CloseableFakeDetector(FakeDetector):
    closed: bool = False

    def close(self) -> None:
        self.closed = True


@dataclass
class FakePublisher:
    observations: list[MeetingObservation] = field(default_factory=list)
    started: bool = False
    stopped: bool = False

    def start(self) -> None:
        self.started = True

    def publish(self, observation: MeetingObservation) -> None:
        self.observations.append(observation)

    def stop(self) -> None:
        self.stopped = True


def _stop_after_poll(seconds: float) -> None:
    assert seconds == 5
    raise KeyboardInterrupt


def _config() -> MonitorConfig:
    return MonitorConfig(
        mqtt=MqttSettings(
            host="broker.invalid",
            port=1883,
            username="placeholder",
            password="placeholder",
            discovery_prefix="homeassistant",
            topic_prefix="ha_teams_status/teams",
            tls_enabled=False,
            tls_ca_file=None,
        ),
        monitor=MonitorSettings(
            poll_interval_seconds=5,
            observation_max_age_seconds=15,
            heartbeat_interval_seconds=10,
            availability_expiry_seconds=30,
        ),
    )


def _write_valid_config(path: Path) -> None:
    path.write_text(
        "[mqtt]\nhost=localhost\nport=1883\nusername=user\npassword=placeholder\n"
        "discovery_prefix=homeassistant\ntopic_prefix=ha_teams_status/teams\ntls=false\n"
        "[monitor]\npoll_interval_seconds=5\nobservation_max_age_seconds=15\n"
        "heartbeat_interval_seconds=10\navailability_expiry_seconds=30\n",
        encoding="utf-8",
    )


def test_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as result:
        main(["--help"])
    assert result.value.code == 0
    assert "--config CONFIG" in capsys.readouterr().out


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as result:
        main(["--version"])
    assert result.value.code == 0
    assert capsys.readouterr().out.strip() == version("ha-teams-status")


def test_no_monitoring_fallback(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as result:
        main([])
    assert result.value.code == 2
    assert "--config" in capsys.readouterr().err


def test_invalid_config_fails_before_monitor_startup(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_file = tmp_path / "monitor.conf"
    config_file.write_text(
        "[mqtt]\nhost=localhost\nport=invalid\nusername=user\n"
        "password=private-secret\ndiscovery_prefix=ha\ntopic_prefix=teams\ntls=false\n"
        "[monitor]\npoll_interval_seconds=5\nobservation_max_age_seconds=15\n"
        "heartbeat_interval_seconds=10\navailability_expiry_seconds=30\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as result:
        main(["--config", str(config_file)])

    assert result.value.code == 2
    error = capsys.readouterr().err
    assert "[mqtt] port" in error
    assert "private-secret" not in error


def test_service_install_validates_config_and_installs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_file = tmp_path / "monitor.conf"
    _write_valid_config(config_file)
    calls: list[tuple[str, Path | None]] = []

    class FakeLoginAgent:
        def install(self, config_path: Path) -> None:
            calls.append(("install", config_path))

        def uninstall(self) -> None:
            calls.append(("uninstall", None))

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(cli, "MacOSLoginAgent", FakeLoginAgent)

    assert main(["service", "install", "--config", str(config_file)]) == 0

    assert calls == [("install", config_file)]
    assert "Installed and started" in capsys.readouterr().out


def test_service_install_rejects_invalid_config_before_service_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_file = tmp_path / "monitor.conf"
    config_file.write_text("invalid", encoding="utf-8")
    calls: list[str] = []

    class FakeLoginAgent:
        def __init__(self) -> None:
            calls.append("constructed")

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(cli, "MacOSLoginAgent", FakeLoginAgent)

    with pytest.raises(SystemExit) as result:
        main(["service", "install", "--config", str(config_file)])

    assert result.value.code == 2
    assert "unreadable or invalid" in capsys.readouterr().err
    assert calls == []


@pytest.mark.parametrize(
    ("arguments", "config_file"),
    [
        (["service", "install", "--config", "monitor.conf"], "monitor.conf"),
        (["service", "uninstall"], None),
    ],
)
def test_service_commands_reject_unsupported_platform_without_service_changes(
    arguments: list[str],
    config_file: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []

    class FakeLoginAgent:
        def __init__(self) -> None:
            calls.append("constructed")

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(cli, "MacOSLoginAgent", FakeLoginAgent)
    command = list(arguments)
    if config_file is not None:
        valid_config = tmp_path / config_file
        _write_valid_config(valid_config)
        command[-1] = str(valid_config)

    with pytest.raises(SystemExit) as result:
        main(command)

    assert result.value.code == 2
    assert "only on macOS" in capsys.readouterr().err
    assert calls == []
    assert not (tmp_path / "Library").exists()


def test_module_entrypoint() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ha_teams_status", "--version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert result.stdout.strip() == version("ha-teams-status")


def test_composition_publishes_unsupported_platform_as_indeterminate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Exercise the unsupported-platform path consistently on native CI hosts.
    monkeypatch.setattr(sys, "platform", "linux")
    publisher = FakePublisher()

    run_monitoring(
        _config(),
        publisher=publisher,
        clock=lambda: NOW,
        wait=_stop_after_poll,
    )

    assert publisher.started
    assert publisher.stopped
    assert len(publisher.observations) == 1
    assert publisher.observations[0].state is ObservationState.INDETERMINATE
    assert publisher.observations[0].reason is ObservationReason.UNSUPPORTED_PLATFORM


def test_default_detector_selects_windows_connector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    detector = cli._default_detector(clock=lambda: NOW)

    assert isinstance(detector, WindowsTeamsDetector)
    detector.close()


def test_monitoring_closes_managed_detector_and_stops_publisher() -> None:
    detector = CloseableFakeDetector(
        observation=MeetingObservation(ObservationState.NOT_JOINED, NOW)
    )
    publisher = FakePublisher()

    run_monitoring(
        _config(),
        detector=detector,
        publisher=publisher,
        clock=lambda: NOW,
        wait=_stop_after_poll,
    )

    assert detector.closed
    assert publisher.stopped


def test_sigterm_stops_polling_and_stops_publisher() -> None:
    publisher = FakePublisher()

    def send_sigterm(_seconds: float) -> None:
        os.kill(os.getpid(), signal.SIGTERM)

    run_monitoring(
        _config(),
        publisher=publisher,
        clock=lambda: NOW,
        wait=send_sigterm,
    )

    assert publisher.started
    assert publisher.stopped
    assert len(publisher.observations) == 1


def test_composition_publishes_detector_failure_as_indeterminate() -> None:
    publisher = FakePublisher()

    run_monitoring(
        _config(),
        detector=FakeDetector(error=DetectionError("private native error")),
        publisher=publisher,
        clock=lambda: NOW,
        wait=_stop_after_poll,
    )

    assert publisher.observations[0].state is ObservationState.INDETERMINATE
    assert publisher.observations[0].reason is ObservationReason.SIGNAL_UNAVAILABLE


def test_slow_monitor_iteration_is_logged(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monotonic_values = iter([100.0, 106.0])
    monkeypatch.setattr(cli, "monotonic", lambda: next(monotonic_values))
    caplog.set_level(logging.WARNING, logger="ha_teams_status.__main__")
    publisher = FakePublisher()

    run_monitoring(
        _config(),
        detector=FakeDetector(observation=MeetingObservation(ObservationState.NOT_JOINED, NOW)),
        publisher=publisher,
        clock=lambda: NOW,
        wait=_stop_after_poll,
    )

    assert "Monitoring iteration exceeded poll interval" in caplog.text
    assert "6.000 seconds" in caplog.text


def test_debug_option_configures_verbose_logging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = tmp_path / "monitor.conf"
    _write_valid_config(config_file)
    logging_options: list[dict[str, object]] = []
    monkeypatch.setattr(
        logging,
        "basicConfig",
        lambda **kwargs: logging_options.append(kwargs),
    )
    monkeypatch.setattr(cli, "run_monitoring", lambda _config: None)

    assert main(["--debug", "--config", str(config_file)]) == 0
    assert logging_options[0]["level"] == logging.DEBUG
