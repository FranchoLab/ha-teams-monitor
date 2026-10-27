from __future__ import annotations

import json
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ha_teams_status.adapters.configuration import MonitorSettings, MqttSettings
from ha_teams_status.adapters.home_assistant_mqtt import (
    HomeAssistantMqttPublisher,
    MqttConnectionError,
    MqttPublishError,
)
from ha_teams_status.domain.observation import (
    MeetingObservation,
    ObservationReason,
    ObservationState,
)


@dataclass(frozen=True)
class PublishedMessage:
    topic: str
    payload: str
    qos: int
    retain: bool


@dataclass
class FakeMqttClient:
    messages: list[PublishedMessage]
    credentials: tuple[str, str] | None = None
    will: PublishedMessage | None = None
    reconnect_delays: tuple[int, int] | None = None
    connect_arguments: tuple[str, int, int] | None = None
    connection_error: Exception | None = None
    publish_result: int = 0
    publish_error: Exception | None = None
    tls_options: tuple[str | None, ssl.VerifyMode | None, int | None] | None = None
    events: list[str] | None = None
    receipts: list[FakePublishReceipt] | None = None
    on_connect: Callable[..., object] | None = None
    connected: bool = False

    def __post_init__(self) -> None:
        self.events = []
        self.receipts = []

    def username_pw_set(self, username: str, password: str) -> None:
        self.credentials = (username, password)

    def tls_set(
        self,
        ca_certs: str | None = None,
        certfile: str | None = None,
        keyfile: str | None = None,
        cert_reqs: ssl.VerifyMode | None = None,
        tls_version: int | None = None,
        ciphers: str | None = None,
        keyfile_password: str | None = None,
        alpn_protocols: list[str] | None = None,
    ) -> None:
        self.tls_options = (ca_certs, cert_reqs, tls_version)

    def will_set(self, topic: str, payload: str, *, qos: int, retain: bool) -> None:
        self.will = PublishedMessage(topic, payload, qos, retain)

    def reconnect_delay_set(self, min_delay: int, max_delay: int) -> None:
        self.reconnect_delays = (min_delay, max_delay)

    def connect_async(self, host: str, port: int, *, keepalive: int) -> None:
        if self.connection_error is not None:
            raise self.connection_error
        self.connect_arguments = (host, port, keepalive)

    def loop_start(self) -> int:
        assert self.events is not None
        self.events.append("loop_start")
        return 0

    def loop_stop(self) -> int:
        assert self.events is not None
        self.events.append("loop_stop")
        return 0

    def disconnect(self) -> int:
        assert self.events is not None
        self.events.append("disconnect")
        self.connected = False
        return 0

    def is_connected(self) -> bool:
        return self.connected

    def publish(self, topic: str, payload: str, *, qos: int, retain: bool) -> FakePublishReceipt:
        if self.publish_error is not None:
            raise self.publish_error
        self.messages.append(PublishedMessage(topic, payload, qos, retain))
        receipt = FakePublishReceipt(self.events, self.publish_result)
        assert self.receipts is not None
        self.receipts.append(receipt)
        return receipt

    def simulate_connect(self, *, failed: bool = False) -> None:
        assert self.on_connect is not None
        self.connected = not failed
        self.on_connect(self, None, None, FakeReasonCode(failed), None)

    def simulate_connection_loss(self) -> None:
        self.connected = False
        assert self.will is not None
        self.messages.append(self.will)


@dataclass
class FakePublishReceipt:
    events: list[str] | None
    rc: int = 0

    def wait_for_publish(self, timeout: float | None = None) -> None:
        assert self.events is not None
        self.events.append(f"wait:{timeout}")


@dataclass(frozen=True)
class FakeReasonCode:
    is_failure: bool


@pytest.fixture
def mqtt_settings() -> MqttSettings:
    return MqttSettings(
        host="broker.invalid",
        port=1883,
        username="placeholder",
        password="placeholder",
        discovery_prefix="ha/discovery",
        topic_prefix="monitor/teams",
        tls_enabled=False,
        tls_ca_file=None,
    )


@pytest.fixture
def monitor_settings() -> MonitorSettings:
    return MonitorSettings(
        poll_interval_seconds=5,
        observation_max_age_seconds=15,
        heartbeat_interval_seconds=10,
        availability_expiry_seconds=30,
    )


def test_discovery_uses_stable_identity_and_configured_topics(
    mqtt_settings: MqttSettings,
    monitor_settings: MonitorSettings,
) -> None:
    client = FakeMqttClient(messages=[])
    publisher = HomeAssistantMqttPublisher(client, mqtt_settings, monitor_settings)

    publisher.publish_discovery()

    message = client.messages[0]
    payload = json.loads(message.payload)
    assert message.topic == "ha/discovery/binary_sensor/ha_teams_status/meeting/config"
    assert message.qos == 1
    assert message.retain
    assert payload["unique_id"] == "ha_teams_status_teams_meeting"
    assert payload["name"] == "Teams meeting"
    assert payload["default_entity_id"] == "binary_sensor.teams_status_teams_meeting"
    assert payload["state_topic"] == "monitor/teams/state"
    assert payload["availability"][0]["topic"] == "monitor/teams/availability"
    assert payload["payload_on"] == "ON"
    assert payload["payload_off"] == "OFF"
    assert payload["expire_after"] == 30


def test_discovery_uses_custom_name_without_changing_identity_or_topics(
    mqtt_settings: MqttSettings,
    monitor_settings: MonitorSettings,
) -> None:
    client = FakeMqttClient(messages=[])
    publisher = HomeAssistantMqttPublisher(
        client,
        mqtt_settings,
        monitor_settings,
        sensor_name="Francho reunido",
    )

    publisher.publish_discovery()

    payload = json.loads(client.messages[0].payload)
    assert payload["name"] == "Francho reunido"
    assert payload["default_entity_id"] == "binary_sensor.teams_status_francho_reunido"
    assert payload["unique_id"] == "ha_teams_status_teams_meeting"
    assert payload["state_topic"] == "monitor/teams/state"
    assert payload["availability"][0]["topic"] == "monitor/teams/availability"


def test_default_entity_id_sanitizes_accents_and_punctuation(
    mqtt_settings: MqttSettings,
    monitor_settings: MonitorSettings,
) -> None:
    client = FakeMqttClient(messages=[])
    publisher = HomeAssistantMqttPublisher(
        client,
        mqtt_settings,
        monitor_settings,
        sensor_name="Café, Team!",
    )

    assert publisher.default_entity_id == "binary_sensor.teams_status_cafe_team"


@pytest.mark.parametrize(
    ("state", "payload"),
    [
        (ObservationState.JOINED, "ON"),
        (ObservationState.NOT_JOINED, "OFF"),
        (ObservationState.INDETERMINATE, "UNKNOWN"),
    ],
)
def test_observation_state_is_retained_at_configured_topic(
    mqtt_settings: MqttSettings,
    monitor_settings: MonitorSettings,
    state: ObservationState,
    payload: str,
) -> None:
    client = FakeMqttClient(messages=[])
    publisher = HomeAssistantMqttPublisher(client, mqtt_settings, monitor_settings)
    observation = MeetingObservation(
        state=state,
        observed_at=datetime(2026, 10, 20, 12, 0, tzinfo=UTC),
        reason=(
            ObservationReason.SIGNAL_UNAVAILABLE
            if state is ObservationState.INDETERMINATE
            else None
        ),
    )

    publisher.publish(observation)

    assert client.messages == [PublishedMessage("monitor/teams/state", payload, 1, True)]


def test_rejected_publish_logs_topic_role_without_payload_or_credentials(
    mqtt_settings: MqttSettings,
    monitor_settings: MonitorSettings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("WARNING", logger="ha_teams_status.adapters.home_assistant_mqtt")
    client = FakeMqttClient(messages=[], publish_result=4)
    publisher = HomeAssistantMqttPublisher(client, mqtt_settings, monitor_settings)
    observation = MeetingObservation(
        state=ObservationState.JOINED,
        observed_at=datetime(2026, 10, 20, 12, 0, tzinfo=UTC),
    )

    publisher.publish(observation)

    assert "rejected for state topic" in caplog.text
    assert "result_code=4" in caplog.text
    assert "ON" not in caplog.text
    assert "placeholder" not in caplog.text


def test_publish_exception_is_logged_safely_and_raised(
    mqtt_settings: MqttSettings,
    monitor_settings: MonitorSettings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("ERROR", logger="ha_teams_status.adapters.home_assistant_mqtt")
    client = FakeMqttClient(
        messages=[],
        publish_error=RuntimeError("private mqtt payload detail"),
    )
    publisher = HomeAssistantMqttPublisher(client, mqtt_settings, monitor_settings)
    observation = MeetingObservation(
        state=ObservationState.JOINED,
        observed_at=datetime(2026, 10, 20, 12, 0, tzinfo=UTC),
    )

    with pytest.raises(MqttPublishError, match="could not be queued"):
        publisher.publish(observation)

    assert "RuntimeError" in caplog.text
    assert "private mqtt payload detail" not in caplog.text


def test_start_and_stop_publish_availability_with_last_will(
    mqtt_settings: MqttSettings,
    monitor_settings: MonitorSettings,
) -> None:
    client = FakeMqttClient(messages=[])
    publisher = HomeAssistantMqttPublisher(client, mqtt_settings, monitor_settings)

    publisher.start()
    client.simulate_connect()
    publisher.stop()

    assert client.credentials == ("placeholder", "placeholder")
    assert client.will == PublishedMessage("monitor/teams/availability", "offline", 1, True)
    assert client.reconnect_delays == (1, 60)
    assert client.connect_arguments == ("broker.invalid", 1883, 60)
    assert [message.payload for message in client.messages[1:]] == ["online", "UNKNOWN", "offline"]
    assert client.events == ["loop_start", "wait:5", "disconnect", "loop_stop"]


def test_heartbeat_refreshes_availability_only_while_connected(
    mqtt_settings: MqttSettings,
    monitor_settings: MonitorSettings,
) -> None:
    client = FakeMqttClient(messages=[])
    publisher = HomeAssistantMqttPublisher(client, mqtt_settings, monitor_settings)

    publisher.heartbeat()
    client.connected = True
    publisher.heartbeat()

    assert client.messages == [PublishedMessage("monitor/teams/availability", "online", 1, True)]


def test_reconnect_rediscovery_resets_retained_state_to_unknown(
    mqtt_settings: MqttSettings,
    monitor_settings: MonitorSettings,
) -> None:
    client = FakeMqttClient(messages=[])
    publisher = HomeAssistantMqttPublisher(client, mqtt_settings, monitor_settings)
    publisher.start()
    client.simulate_connect()
    publisher.publish(
        MeetingObservation(
            state=ObservationState.JOINED,
            observed_at=datetime(2026, 10, 20, 12, 0, tzinfo=UTC),
        )
    )

    client.simulate_connection_loss()
    client.simulate_connect()

    assert client.messages[-4] == PublishedMessage("monitor/teams/availability", "offline", 1, True)
    assert client.messages[-3].topic.endswith("/config")
    assert client.messages[-2] == PublishedMessage("monitor/teams/availability", "online", 1, True)
    assert client.messages[-1] == PublishedMessage("monitor/teams/state", "UNKNOWN", 1, True)
    publisher.stop()


def test_failed_connection_callback_does_not_publish_online(
    mqtt_settings: MqttSettings,
    monitor_settings: MonitorSettings,
) -> None:
    client = FakeMqttClient(messages=[])
    HomeAssistantMqttPublisher(client, mqtt_settings, monitor_settings)

    client.simulate_connect(failed=True)

    assert client.messages == []


def test_tls_requires_certificate_validation(
    mqtt_settings: MqttSettings,
    monitor_settings: MonitorSettings,
) -> None:
    settings = MqttSettings(
        host=mqtt_settings.host,
        port=8883,
        username=mqtt_settings.username,
        password=mqtt_settings.password,
        discovery_prefix=mqtt_settings.discovery_prefix,
        topic_prefix=mqtt_settings.topic_prefix,
        tls_enabled=True,
        tls_ca_file=Path("/etc/ssl/certs/ca-certificates.crt"),
    )
    client = FakeMqttClient(messages=[])

    HomeAssistantMqttPublisher(client, settings, monitor_settings)

    assert client.tls_options == (
        "/etc/ssl/certs/ca-certificates.crt",
        ssl.CERT_REQUIRED,
        ssl.PROTOCOL_TLS_CLIENT,
    )


def test_connection_errors_do_not_expose_credentials(
    mqtt_settings: MqttSettings,
    monitor_settings: MonitorSettings,
) -> None:
    settings = MqttSettings(
        host=mqtt_settings.host,
        port=mqtt_settings.port,
        username="private-user",
        password="private-password",
        discovery_prefix=mqtt_settings.discovery_prefix,
        topic_prefix=mqtt_settings.topic_prefix,
        tls_enabled=False,
        tls_ca_file=None,
    )
    client = FakeMqttClient(messages=[], connection_error=RuntimeError("private-password"))
    publisher = HomeAssistantMqttPublisher(client, settings, monitor_settings)

    with pytest.raises(MqttConnectionError) as error:
        publisher.start()

    assert "private-password" not in str(error.value)
