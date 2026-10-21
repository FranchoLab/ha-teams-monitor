import json
import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from ha_teams_status.adapters.windows_teams import (
    LocalTeamsApiSource,
    TeamsApiSnapshot,
    WindowsTeamsDetector,
)
from ha_teams_status.application.monitor import DetectionError, ObserveMeeting
from ha_teams_status.domain.observation import ObservationReason, ObservationState

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


class FakeWebSocketApp:
    def __init__(self, url: str, callbacks: dict[str, object]) -> None:
        self.url = url
        self._callbacks = callbacks
        self.opened = threading.Event()
        self.finished = threading.Event()
        self.closed = False

    def run_forever(
        self,
        *,
        ping_interval: float,
        ping_timeout: float,
        http_no_proxy: list[str],
        suppress_origin: bool,
    ) -> bool:
        assert ping_interval > ping_timeout
        assert "localhost" in http_no_proxy
        assert suppress_origin
        self.emit("on_open")
        self.opened.set()
        self.finished.wait()
        return True

    def close(self) -> None:
        self.closed = True
        self.emit("on_close", 1000, "closed")
        self.finished.set()

    def disconnect_from_server(self) -> None:
        self.emit("on_close", 1006, "connection lost")
        self.finished.set()

    def emit(self, name: str, *args: object) -> None:
        callback = self._callbacks[name]
        assert callable(callback)
        callback(self, *args)

    def send_json(self, payload: object) -> None:
        self.emit("on_message", json.dumps(payload))


class FakeSource:
    def __init__(self, snapshot: TeamsApiSnapshot) -> None:
        self.snapshot = snapshot
        self.started = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def read(self) -> TeamsApiSnapshot:
        return self.snapshot

    def close(self) -> None:
        self.closed = True


class FailingSource(FakeSource):
    def start(self) -> None:
        raise OSError("private connection failure")


def _wait_for(predicate: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 2
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert predicate()


def _make_source(
    *,
    clock: Callable[[], datetime] = lambda: NOW,
    reconnect_delay: float = 0.01,
) -> tuple[LocalTeamsApiSource, list[FakeWebSocketApp]]:
    apps: list[FakeWebSocketApp] = []

    def factory(url: str, **callbacks: object) -> FakeWebSocketApp:
        app = FakeWebSocketApp(url, callbacks)
        apps.append(app)
        return app

    return (
        LocalTeamsApiSource(
            app_factory=factory,
            clock=clock,
            reconnect_delay=reconnect_delay,
        ),
        apps,
    )


def test_event_source_connects_to_local_api_and_keeps_only_meeting_state() -> None:
    source, apps = _make_source()
    source.start()
    try:
        _wait_for(lambda: bool(apps) and apps[0].opened.is_set())

        query = parse_qs(urlparse(apps[0].url).query)
        assert apps[0].url.startswith("ws://localhost:8124?")
        assert query["protocol-version"] == ["2.0.0"]
        assert "token" not in query

        apps[0].send_json(
            {
                "meetingUpdate": {
                    "meetingState": {
                        "isInMeeting": True,
                        "meetingTitle": "private meeting",
                        "participant": "private person",
                    }
                }
            }
        )

        snapshot = source.read()

        assert snapshot.is_in_meeting is True
        assert snapshot.observed_at == NOW
        assert snapshot.reason is None
        assert "private meeting" not in repr(snapshot)
        assert "private person" not in repr(snapshot)
    finally:
        source.close()

    assert apps[0].closed


@pytest.mark.parametrize(
    "payload",
    [
        {"meetingUpdate": {"meetingState": {}}},
        {"meetingUpdate": {"meetingState": {"isInMeeting": 1}}},
        {"meetingUpdate": {"meetingState": {"isInMeeting": "true"}}},
        {"unsupportedMessage": {}},
    ],
)
def test_event_source_marks_malformed_or_unsupported_state_inconclusive(
    payload: object,
) -> None:
    source, apps = _make_source()
    source.start()
    try:
        _wait_for(lambda: bool(apps) and apps[0].opened.is_set())
        apps[0].send_json({"meetingUpdate": {"meetingState": {"isInMeeting": True}}})
        assert source.read().is_in_meeting is True

        apps[0].send_json(payload)

        snapshot = source.read()
        assert snapshot.is_in_meeting is None
        assert snapshot.reason is ObservationReason.SIGNAL_INCONCLUSIVE
    finally:
        source.close()


def test_event_source_marks_invalid_json_inconclusive() -> None:
    source, apps = _make_source()
    source.start()
    try:
        _wait_for(lambda: bool(apps) and apps[0].opened.is_set())
        apps[0].emit("on_message", "not-json")
        snapshot = source.read()
        assert snapshot.is_in_meeting is None
        assert snapshot.reason is ObservationReason.SIGNAL_INCONCLUSIVE
    finally:
        source.close()


def test_api_error_is_unavailable_without_logging_error_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    source, apps = _make_source()
    secret_error = "authorization failed with sensitive-api-token"
    source.start()
    try:
        _wait_for(lambda: bool(apps) and apps[0].opened.is_set())
        apps[0].emit("on_error", RuntimeError(secret_error))

        snapshot = source.read()

        assert snapshot.is_in_meeting is None
        assert snapshot.reason is ObservationReason.SIGNAL_UNAVAILABLE
        assert secret_error not in caplog.text
        assert "sensitive-api-token" not in caplog.text
    finally:
        source.close()


def test_event_source_marks_disconnect_unavailable_and_recovers() -> None:
    source, apps = _make_source()
    source.start()
    try:
        _wait_for(lambda: len(apps) == 1 and apps[0].opened.is_set())
        apps[0].send_json({"meetingUpdate": {"meetingState": {"isInMeeting": True}}})

        apps[0].disconnect_from_server()

        snapshot = source.read()
        assert snapshot.is_in_meeting is None
        assert snapshot.reason is ObservationReason.SIGNAL_UNAVAILABLE

        _wait_for(lambda: len(apps) == 2 and apps[1].opened.is_set())
        apps[1].send_json({"meetingUpdate": {"meetingState": {"isInMeeting": False}}})
        assert source.read().is_in_meeting is False
    finally:
        source.close()


def test_event_source_refreshes_freshness_on_pong() -> None:
    current_time = [NOW]
    source, apps = _make_source(clock=lambda: current_time[0])
    source.start()
    try:
        _wait_for(lambda: bool(apps) and apps[0].opened.is_set())
        apps[0].send_json({"meetingUpdate": {"meetingState": {"isInMeeting": True}}})
        current_time[0] = NOW + timedelta(seconds=10)
        apps[0].emit("on_pong", "")

        assert source.read().observed_at == current_time[0]
        assert source.read().is_in_meeting is True
    finally:
        source.close()


def test_token_refresh_is_memory_only_and_used_for_reconnect(
    caplog: pytest.LogCaptureFixture,
) -> None:
    token = "sensitive-api-token"
    source, apps = _make_source()
    caplog.set_level(logging.WARNING)
    source.start()
    try:
        _wait_for(lambda: len(apps) == 1 and apps[0].opened.is_set())
        apps[0].send_json({"tokenRefresh": token})
        apps[0].disconnect_from_server()

        _wait_for(lambda: len(apps) == 2 and apps[1].opened.is_set())

        assert parse_qs(urlparse(apps[1].url).query)["token"] == [token]
        assert token not in caplog.text
    finally:
        source.close()


def test_detector_maps_api_states_and_closes_source() -> None:
    source = FakeSource(TeamsApiSnapshot(True, NOW, None))
    detector = WindowsTeamsDetector(source=source, clock=lambda: NOW)

    observation = detector.detect()
    detector.close()

    assert source.started
    assert source.closed
    assert observation.state is ObservationState.JOINED
    assert observation.observed_at == NOW


@pytest.mark.parametrize(
    ("snapshot", "expected_reason"),
    [
        (
            TeamsApiSnapshot(None, NOW, ObservationReason.SIGNAL_UNAVAILABLE),
            ObservationReason.SIGNAL_UNAVAILABLE,
        ),
        (
            TeamsApiSnapshot(None, NOW, ObservationReason.SIGNAL_INCONCLUSIVE),
            ObservationReason.SIGNAL_INCONCLUSIVE,
        ),
    ],
)
def test_detector_keeps_missing_api_state_indeterminate(
    snapshot: TeamsApiSnapshot,
    expected_reason: ObservationReason,
) -> None:
    detector = WindowsTeamsDetector(source=FakeSource(snapshot), clock=lambda: NOW)

    observation = detector.detect()

    assert observation.state is ObservationState.INDETERMINATE
    assert observation.reason is expected_reason


def test_detector_returns_confirmed_not_joined_state() -> None:
    detector = WindowsTeamsDetector(
        source=FakeSource(TeamsApiSnapshot(False, NOW, None)),
        clock=lambda: NOW,
    )

    assert detector.detect().state is ObservationState.NOT_JOINED


def test_detector_wraps_source_errors_without_leaking_details() -> None:
    detector = WindowsTeamsDetector(
        source=FailingSource(TeamsApiSnapshot(None, NOW, ObservationReason.SIGNAL_UNAVAILABLE)),
        clock=lambda: NOW,
    )

    with pytest.raises(DetectionError, match="Unable to obtain Windows Teams API state"):
        detector.detect()


def test_detector_observation_can_become_stale() -> None:
    source = FakeSource(TeamsApiSnapshot(True, NOW - timedelta(seconds=31), None))
    detector = WindowsTeamsDetector(source=source, clock=lambda: NOW)
    observe = ObserveMeeting(
        detector=detector,
        clock=lambda: NOW,
        max_age=timedelta(seconds=30),
    )

    observation = observe.execute()

    assert observation.state is ObservationState.INDETERMINATE
    assert observation.reason is ObservationReason.STALE


def test_detector_refuses_detection_after_close() -> None:
    detector = WindowsTeamsDetector(
        source=FakeSource(TeamsApiSnapshot(False, NOW, None)),
        clock=lambda: NOW,
    )
    detector.close()

    with pytest.raises(DetectionError):
        detector.detect()
