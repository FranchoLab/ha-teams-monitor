"""CLI entry point and future composition root."""

import argparse
import logging
import signal
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from threading import Event
from time import monotonic
from types import FrameType
from typing import Protocol

from .adapters.configuration import ConfigurationError, MonitorConfig, load_config
from .adapters.home_assistant_mqtt import create_publisher
from .adapters.macos_login_agent import (
    LaunchAgentError,
    MacOSLoginAgent,
    require_macos,
)
from .adapters.macos_teams import MacOSTeamsDetector
from .adapters.windows_teams import WindowsTeamsDetector
from .application.monitor import (
    MeetingDetector,
    MonitorMeeting,
    ObserveMeeting,
)
from .domain.observation import MeetingObservation

_LOGGER = logging.getLogger(__name__)


class MonitoringPublisher(Protocol):
    def start(self) -> None: ...

    def publish(self, observation: MeetingObservation) -> None: ...

    def stop(self) -> None: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _default_detector(clock: Callable[[], datetime]) -> MeetingDetector:
    if sys.platform == "win32":
        return WindowsTeamsDetector(clock=clock)
    return MacOSTeamsDetector(clock=clock)


def run_monitoring(
    config: MonitorConfig,
    *,
    detector: MeetingDetector | None = None,
    publisher: MonitoringPublisher | None = None,
    clock: Callable[[], datetime] = _utc_now,
    wait: Callable[[float], None] | None = None,
) -> None:
    selected_detector = detector if detector is not None else _default_detector(clock)
    selected_publisher = publisher or create_publisher(config)
    monitor = MonitorMeeting(
        observe=ObserveMeeting(
            detector=selected_detector,
            clock=clock,
            max_age=timedelta(seconds=config.monitor.observation_max_age_seconds),
        ),
        publisher=selected_publisher,
        clock=clock,
        max_joined_duration=timedelta(
            seconds=config.monitor.max_joined_duration_seconds,
        ),
    )
    stop_requested = Event()

    def request_shutdown(_signum: int, _frame: FrameType | None) -> None:
        stop_requested.set()

    previous_sigterm_handler = signal.signal(signal.SIGTERM, request_shutdown)
    try:
        selected_publisher.start()
        while not stop_requested.is_set():
            iteration_started = monotonic()
            try:
                monitor.execute()
            finally:
                iteration_duration = monotonic() - iteration_started
                if iteration_duration > config.monitor.poll_interval_seconds:
                    _LOGGER.warning(
                        "Monitoring iteration exceeded poll interval: %.3f seconds "
                        "for a %d second interval.",
                        iteration_duration,
                        config.monitor.poll_interval_seconds,
                    )
                else:
                    _LOGGER.debug(
                        "Monitoring iteration completed in %.3f seconds.",
                        iteration_duration,
                    )
            if wait is None:
                stop_requested.wait(config.monitor.poll_interval_seconds)
            else:
                wait(config.monitor.poll_interval_seconds)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            signal.signal(signal.SIGTERM, previous_sigterm_handler)
        finally:
            try:
                close_detector = getattr(selected_detector, "close", None)
                if callable(close_detector):
                    close_detector()
            finally:
                selected_publisher.stop()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ha-teams-status",
        description="Monitor Teams meeting state and publish it to Home Assistant over MQTT.",
    )
    parser.add_argument("--version", action="version", version=version("ha-teams-status"))
    parser.add_argument("--config", type=Path, help="path to the monitor .conf file")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable per-iteration monitoring diagnostics",
    )
    commands = parser.add_subparsers(dest="command")
    service_parser = commands.add_parser("service", help="manage the macOS login agent")
    service_commands = service_parser.add_subparsers(
        dest="service_action",
        required=True,
    )
    install_parser = service_commands.add_parser(
        "install",
        help="install and start the per-user macOS login agent",
    )
    install_parser.add_argument(
        "--config",
        type=Path,
        required=True,
        dest="service_config",
        help="path to the monitor .conf file",
    )
    service_commands.add_parser("uninstall", help="stop and remove the macOS login agent")
    args = parser.parse_args(argv)

    if args.command == "service":
        try:
            require_macos()
        except LaunchAgentError as error:
            parser.error(str(error))

        if args.service_action == "install":
            try:
                load_config(args.service_config)
            except ConfigurationError as error:
                parser.error(str(error))
            try:
                MacOSLoginAgent().install(args.service_config)
            except LaunchAgentError as error:
                parser.error(str(error))
            print("Installed and started the macOS login agent.")
        else:
            try:
                MacOSLoginAgent().uninstall()
            except LaunchAgentError as error:
                parser.error(str(error))
            print("Uninstalled the macOS login agent.")
        return 0

    if args.config is None:
        parser.error("the following arguments are required: --config")
    try:
        config = load_config(args.config)
    except ConfigurationError as error:
        parser.error(str(error))
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_monitoring(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
