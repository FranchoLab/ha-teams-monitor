"""CLI entry point and future composition root."""

import argparse
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from time import sleep
from typing import Protocol

from .adapters.configuration import ConfigurationError, MonitorConfig, load_config
from .adapters.home_assistant_mqtt import create_publisher
from .adapters.macos_teams import MacOSTeamsDetector
from .application.monitor import (
    MeetingDetector,
    MonitorMeeting,
    ObserveMeeting,
)
from .domain.observation import MeetingObservation


class MonitoringPublisher(Protocol):
    def start(self) -> None: ...

    def publish(self, observation: MeetingObservation) -> None: ...

    def stop(self) -> None: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


def run_monitoring(
    config: MonitorConfig,
    *,
    detector: MeetingDetector | None = None,
    publisher: MonitoringPublisher | None = None,
    clock: Callable[[], datetime] = _utc_now,
    wait: Callable[[float], None] = sleep,
) -> None:
    selected_detector = detector or MacOSTeamsDetector(clock=clock)
    selected_publisher = publisher or create_publisher(config)
    monitor = MonitorMeeting(
        observe=ObserveMeeting(
            detector=selected_detector,
            clock=clock,
            max_age=timedelta(seconds=config.monitor.observation_max_age_seconds),
        ),
        publisher=selected_publisher,
        clock=clock,
    )
    selected_publisher.start()
    try:
        while True:
            monitor.execute()
            wait(config.monitor.poll_interval_seconds)
    except KeyboardInterrupt:
        pass
    finally:
        selected_publisher.stop()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ha-teams-status",
        description="Monitor Teams meeting state and publish it to Home Assistant over MQTT.",
    )
    parser.add_argument("--version", action="version", version=version("ha-teams-status"))
    parser.add_argument("--config", type=Path, required=True, help="path to the monitor .conf file")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigurationError as error:
        parser.error(str(error))
    run_monitoring(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
