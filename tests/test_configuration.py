import re
from pathlib import Path

import pytest

from ha_teams_status.adapters.configuration import ConfigurationError, load_config

CONFIG = """\
[mqtt]
host = broker.local
port = 1883
username = monitor
password = p%#;=word
discovery_prefix = homeassistant
topic_prefix = ha_teams_status/teams
tls = false

[monitor]
poll_interval_seconds = 5
observation_max_age_seconds = 15
heartbeat_interval_seconds = 10
availability_expiry_seconds = 30
"""


def test_load_config_preserves_literal_password_characters(tmp_path: Path) -> None:
    config_file = tmp_path / "monitor.conf"
    config_file.write_text(CONFIG, encoding="utf-8")

    config = load_config(config_file)

    assert config.mqtt.password == "p%#;=word"
    assert "p%#;=word" not in repr(config)
    assert config.mqtt.port == 1883
    assert config.monitor.poll_interval_seconds == 5
    assert config.monitor.max_joined_duration_seconds == 8 * 60 * 60
    assert config.sensor_name == "Teams meeting"


def test_load_config_reads_custom_maximum_joined_duration(tmp_path: Path) -> None:
    config_file = tmp_path / "monitor.conf"
    config_file.write_text(
        CONFIG + "max_joined_duration_seconds = 1200\n",
        encoding="utf-8",
    )

    assert load_config(config_file).monitor.max_joined_duration_seconds == 1200


@pytest.mark.parametrize("value", ["0", "-1"])
def test_load_config_rejects_nonpositive_maximum_joined_duration(
    tmp_path: Path,
    value: str,
) -> None:
    config_file = tmp_path / "monitor.conf"
    config_file.write_text(
        CONFIG + f"max_joined_duration_seconds = {value}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="must be positive"):
        load_config(config_file)


def test_load_config_rejects_noninteger_maximum_joined_duration(tmp_path: Path) -> None:
    config_file = tmp_path / "monitor.conf"
    config_file.write_text(
        CONFIG + "max_joined_duration_seconds = invalid\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="must be an integer"):
        load_config(config_file)


def test_load_config_reads_custom_sensor_name(tmp_path: Path) -> None:
    config_file = tmp_path / "monitor.conf"
    config_file.write_text(CONFIG + "\n[sensor]\nname = Calls at home\n", encoding="utf-8")

    assert load_config(config_file).sensor_name == "Calls at home"


def test_load_config_rejects_empty_sensor_name(tmp_path: Path) -> None:
    config_file = tmp_path / "monitor.conf"
    config_file.write_text(CONFIG + "\n[sensor]\nname =   \n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="sensor name must not be empty"):
        load_config(config_file)


@pytest.mark.parametrize(
    "contents",
    ["", "not an ini file", CONFIG.replace("port = 1883", "port = invalid")],
)
def test_load_config_rejects_invalid_files_without_values(
    tmp_path: Path,
    contents: str,
) -> None:
    config_file = tmp_path / "monitor.conf"
    config_file.write_text(contents, encoding="utf-8")

    with pytest.raises(ConfigurationError) as error:
        load_config(config_file)

    assert "p%#;=word" not in str(error.value)


def test_load_config_reports_missing_file_without_credentials(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="unreadable or invalid"):
        load_config(tmp_path / "missing.conf")


def test_load_config_reports_unreadable_path_without_details(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="unreadable or invalid"):
        load_config(tmp_path)


def test_load_config_rejects_invalid_intervals(tmp_path: Path) -> None:
    config_file = tmp_path / "monitor.conf"
    config_file.write_text(CONFIG.replace("poll_interval_seconds = 5", "poll_interval_seconds = 0"))

    with pytest.raises(ConfigurationError, match="must be positive"):
        load_config(config_file)


def test_readme_config_example_parses_and_uses_placeholders(tmp_path: Path) -> None:
    readme = Path(__file__).parents[1] / "README.md"
    match = re.search(r"```ini\n(.*?)\n```", readme.read_text(encoding="utf-8"), re.DOTALL)
    assert match is not None
    config_file = tmp_path / "documented.conf"
    config_file.write_text(match.group(1), encoding="utf-8")

    config = load_config(config_file)

    assert config.mqtt.host == "mqtt.example.invalid"
    assert config.mqtt.username == "YOUR_MQTT_USERNAME"
    assert config.mqtt.password == "REPLACE_WITH_MQTT_PASSWORD"
    assert config.sensor_name == "Teams meeting"
    assert config.monitor.max_joined_duration_seconds == 8 * 60 * 60


def test_readme_acl_matches_documented_config_topics(tmp_path: Path) -> None:
    readme = Path(__file__).parents[1] / "README.md"
    readme_text = readme.read_text(encoding="utf-8")
    match = re.search(r"```ini\n(.*?)\n```", readme_text, re.DOTALL)
    assert match is not None
    config_file = tmp_path / "documented.conf"
    config_file.write_text(match.group(1), encoding="utf-8")
    config = load_config(config_file)

    expected_topics = (
        f"{config.mqtt.discovery_prefix}/binary_sensor/ha_teams_status/meeting/config",
        f"{config.mqtt.topic_prefix}/state",
        f"{config.mqtt.topic_prefix}/availability",
    )
    for topic in expected_topics:
        assert f"topic write {topic}" in readme_text
    assert "YOUR_MQTT_USERNAME" in readme_text
    assert "Home Assistant API token" in readme_text
