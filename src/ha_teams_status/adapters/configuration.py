"""Load and validate local monitor configuration."""

import configparser
from dataclasses import dataclass, field
from pathlib import Path


class ConfigurationError(Exception):
    """Raised when monitor configuration cannot be loaded safely."""


_DEFAULT_MAX_JOINED_DURATION_SECONDS = 8 * 60 * 60


@dataclass(frozen=True, slots=True)
class MqttSettings:
    host: str
    port: int
    username: str
    password: str = field(repr=False)
    discovery_prefix: str
    topic_prefix: str
    tls_enabled: bool
    tls_ca_file: Path | None


@dataclass(frozen=True, slots=True)
class MonitorSettings:
    poll_interval_seconds: int
    observation_max_age_seconds: int
    heartbeat_interval_seconds: int
    availability_expiry_seconds: int
    max_joined_duration_seconds: int = _DEFAULT_MAX_JOINED_DURATION_SECONDS


@dataclass(frozen=True, slots=True)
class MonitorConfig:
    mqtt: MqttSettings
    monitor: MonitorSettings
    sensor_name: str = "Teams meeting"


def load_config(path: str | Path) -> MonitorConfig:
    """Load a monitor INI file without exposing its values in errors."""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with Path(path).open(encoding="utf-8") as config_file:
            parser.read_file(config_file)
    except (OSError, UnicodeError, configparser.Error):
        raise ConfigurationError("configuration file is unreadable or invalid") from None

    mqtt = MqttSettings(
        host=_required(parser, "mqtt", "host"),
        port=_integer(parser, "mqtt", "port"),
        username=_required(parser, "mqtt", "username"),
        password=_required(parser, "mqtt", "password"),
        discovery_prefix=_required(parser, "mqtt", "discovery_prefix"),
        topic_prefix=_required(parser, "mqtt", "topic_prefix"),
        tls_enabled=_boolean(parser, "mqtt", "tls"),
        tls_ca_file=_optional_path(parser, "mqtt", "tls_ca_file"),
    )
    monitor = MonitorSettings(
        poll_interval_seconds=_integer(parser, "monitor", "poll_interval_seconds"),
        observation_max_age_seconds=_integer(parser, "monitor", "observation_max_age_seconds"),
        heartbeat_interval_seconds=_integer(parser, "monitor", "heartbeat_interval_seconds"),
        availability_expiry_seconds=_integer(parser, "monitor", "availability_expiry_seconds"),
        max_joined_duration_seconds=(
            _integer(parser, "monitor", "max_joined_duration_seconds")
            if parser.has_option("monitor", "max_joined_duration_seconds")
            else _DEFAULT_MAX_JOINED_DURATION_SECONDS
        ),
    )
    sensor_name = parser.get("sensor", "name", fallback="Teams meeting").strip()
    if not sensor_name:
        raise ConfigurationError("sensor name must not be empty")

    if not mqtt.host.strip() or not mqtt.username.strip() or not mqtt.password.strip():
        raise ConfigurationError("mqtt host, username, and password must not be empty")
    if not 1 <= mqtt.port <= 65535:
        raise ConfigurationError("mqtt port must be between 1 and 65535")
    if not mqtt.discovery_prefix.strip() or not mqtt.topic_prefix.strip():
        raise ConfigurationError("mqtt topic prefixes must not be empty")
    if any(
        interval <= 0
        for interval in (
            monitor.poll_interval_seconds,
            monitor.observation_max_age_seconds,
            monitor.heartbeat_interval_seconds,
            monitor.availability_expiry_seconds,
            monitor.max_joined_duration_seconds,
        )
    ):
        raise ConfigurationError("monitor intervals must be positive integers")
    if monitor.observation_max_age_seconds < monitor.poll_interval_seconds:
        raise ConfigurationError(
            "observation_max_age_seconds must be at least poll_interval_seconds"
        )
    if monitor.availability_expiry_seconds <= monitor.heartbeat_interval_seconds:
        raise ConfigurationError(
            "availability_expiry_seconds must exceed heartbeat_interval_seconds"
        )
    if mqtt.tls_ca_file is not None and not mqtt.tls_enabled:
        raise ConfigurationError("mqtt tls_ca_file requires tls = true")
    return MonitorConfig(mqtt=mqtt, monitor=monitor, sensor_name=sensor_name)


def _required(parser: configparser.ConfigParser, section: str, option: str) -> str:
    if not parser.has_option(section, option):
        raise ConfigurationError(f"missing required setting: [{section}] {option}")
    value = parser.get(section, option)
    if not value.strip():
        raise ConfigurationError(f"required setting must not be empty: [{section}] {option}")
    return value


def _integer(parser: configparser.ConfigParser, section: str, option: str) -> int:
    value = _required(parser, section, option)
    try:
        return int(value)
    except ValueError:
        raise ConfigurationError(f"setting must be an integer: [{section}] {option}") from None


def _boolean(parser: configparser.ConfigParser, section: str, option: str) -> bool:
    if not parser.has_option(section, option):
        raise ConfigurationError(f"missing required setting: [{section}] {option}")
    try:
        return parser.getboolean(section, option)
    except ValueError:
        raise ConfigurationError(f"setting must be true or false: [{section}] {option}") from None


def _optional_path(parser: configparser.ConfigParser, section: str, option: str) -> Path | None:
    value = parser.get(section, option, fallback="").strip()
    return Path(value) if value else None
