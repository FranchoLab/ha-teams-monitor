"""Home Assistant MQTT discovery and meeting-state publisher."""

import json
import re
import ssl
import unicodedata
from collections.abc import Callable
from threading import Event, Thread
from typing import Any, Protocol

import paho.mqtt.client as mqtt_client
from paho.mqtt.enums import CallbackAPIVersion

from ..domain.observation import MeetingObservation, ObservationState
from .configuration import MonitorConfig, MonitorSettings, MqttSettings


class MqttClient(Protocol):
    on_connect: Callable[..., Any] | None

    def username_pw_set(self, username: str, password: str) -> None: ...

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
    ) -> None: ...

    def will_set(self, topic: str, payload: str, *, qos: int, retain: bool) -> None: ...

    def reconnect_delay_set(self, min_delay: int, max_delay: int) -> None: ...

    def connect_async(self, host: str, port: int, *, keepalive: int) -> None: ...

    def loop_start(self) -> object: ...

    def loop_stop(self) -> object: ...

    def disconnect(self) -> object: ...

    def is_connected(self) -> bool: ...

    def publish(
        self,
        topic: str,
        payload: str,
        *,
        qos: int,
        retain: bool,
    ) -> object: ...


class MqttConnectionError(Exception):
    """Raised when the broker connection cannot be started safely."""


class HomeAssistantMqttPublisher:
    def __init__(
        self,
        client: MqttClient,
        mqtt: MqttSettings,
        monitor: MonitorSettings,
        sensor_name: str = "Teams meeting",
    ) -> None:
        self._client = client
        self._mqtt = mqtt
        self._monitor = monitor
        self._sensor_name = sensor_name
        self._heartbeat_stop = Event()
        self._heartbeat_thread: Thread | None = None
        self._started = False
        self._client.username_pw_set(mqtt.username, mqtt.password)
        self._client.will_set(self.availability_topic, "offline", qos=1, retain=True)
        self._client.reconnect_delay_set(min_delay=1, max_delay=60)
        self._client.on_connect = self._on_connect
        if mqtt.tls_enabled:
            self._client.tls_set(
                ca_certs=str(mqtt.tls_ca_file) if mqtt.tls_ca_file is not None else None,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )

    @property
    def discovery_topic(self) -> str:
        return f"{self._mqtt.discovery_prefix}/binary_sensor/ha_teams_status/meeting/config"

    @property
    def state_topic(self) -> str:
        return f"{self._mqtt.topic_prefix}/state"

    @property
    def availability_topic(self) -> str:
        return f"{self._mqtt.topic_prefix}/availability"

    @property
    def default_entity_id(self) -> str:
        normalized_name = unicodedata.normalize("NFKD", self._sensor_name)
        ascii_name = normalized_name.encode("ascii", "ignore").decode("ascii")
        object_id = re.sub(r"[^a-z0-9]+", "_", ascii_name.casefold()).strip("_")
        return f"binary_sensor.teams_status_{object_id or 'sensor'}"

    def publish_discovery(self) -> None:
        payload = {
            "availability": [
                {
                    "topic": self.availability_topic,
                    "payload_available": "online",
                    "payload_not_available": "offline",
                }
            ],
            "device": {
                "identifiers": ["ha_teams_status"],
                "manufacturer": "Local monitor",
                "model": "Teams MQTT sensor",
                "name": "teams status",
            },
            "device_class": "running",
            "expire_after": self._monitor.availability_expiry_seconds,
            "default_entity_id": self.default_entity_id,
            "name": self._sensor_name,
            "payload_off": "OFF",
            "payload_on": "ON",
            "state_topic": self.state_topic,
            "unique_id": "ha_teams_status_teams_meeting",
        }
        self._publish(self.discovery_topic, json.dumps(payload, sort_keys=True))

    def start(self) -> None:
        if self._started:
            return
        try:
            self._client.connect_async(
                self._mqtt.host,
                self._mqtt.port,
                keepalive=max(60, self._monitor.heartbeat_interval_seconds * 2),
            )
            self._client.loop_start()
        except Exception:
            raise MqttConnectionError("unable to start MQTT connection") from None
        self._started = True
        self._heartbeat_stop.clear()
        self._heartbeat_thread = Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def stop(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join()
            self._heartbeat_thread = None
        if not self._started:
            return
        try:
            receipt = self._client.publish(
                self.availability_topic,
                "offline",
                qos=1,
                retain=True,
            )
            wait_for_publish = getattr(receipt, "wait_for_publish", None)
            if callable(wait_for_publish):
                wait_for_publish(timeout=5)
        finally:
            self._client.disconnect()
            self._client.loop_stop()
            self._started = False

    def publish(self, observation: MeetingObservation) -> None:
        payload = {
            ObservationState.JOINED: "ON",
            ObservationState.NOT_JOINED: "OFF",
            ObservationState.INDETERMINATE: "UNKNOWN",
        }[observation.state]
        self._publish(self.state_topic, payload)

    def heartbeat(self) -> None:
        if self._client.is_connected():
            self._publish(self.availability_topic, "online")

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(self._monitor.heartbeat_interval_seconds):
            try:
                self.heartbeat()
            except Exception:
                continue

    def _on_connect(
        self,
        client: object,
        userdata: object,
        flags: object,
        reason_code: object,
        properties: object,
    ) -> None:
        if getattr(reason_code, "is_failure", False):
            return
        self.publish_discovery()
        self._publish(self.availability_topic, "online")
        self._publish(self.state_topic, "UNKNOWN")

    def _publish(self, topic: str, payload: str) -> None:
        self._client.publish(topic, payload, qos=1, retain=True)


def create_publisher(config: MonitorConfig) -> HomeAssistantMqttPublisher:
    client = mqtt_client.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id="ha_teams_status",
    )
    return HomeAssistantMqttPublisher(
        client,
        config.mqtt,
        config.monitor,
        sensor_name=config.sensor_name,
    )
