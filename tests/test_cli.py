import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import pytest

from ha_teams_status.__main__ import main, run_monitoring
from ha_teams_status.adapters.configuration import MonitorConfig, MonitorSettings, MqttSettings
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


def test_module_entrypoint() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ha_teams_status", "--version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert result.stdout.strip() == version("ha-teams-status")


def test_composition_publishes_unsupported_platform_as_indeterminate() -> None:
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
