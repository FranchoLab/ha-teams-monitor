"""Detect Teams meeting state through its local Third-Party WebSocket API."""

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlencode

import websocket

from ..application.monitor import DetectionError, MeetingDetector
from ..domain.observation import (
    MeetingObservation,
    ObservationReason,
    ObservationState,
)

_API_ENDPOINT = "ws://localhost:8124"
_API_PROTOCOL_VERSION = "2.0.0"
_PING_INTERVAL_SECONDS = 5
_PING_TIMEOUT_SECONDS = 3
_RECONNECT_DELAY_SECONDS = 2.0
_CLOSE_TIMEOUT_SECONDS = 5.0
_LOGGER = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class TeamsApiSnapshot:
    is_in_meeting: bool | None
    observed_at: datetime
    reason: ObservationReason | None


class TeamsApiSource(Protocol):
    def start(self) -> None: ...

    def read(self) -> TeamsApiSnapshot: ...

    def close(self) -> None: ...


class _WebSocketRunner(Protocol):
    def run_forever(
        self,
        *,
        ping_interval: float,
        ping_timeout: float,
        http_no_proxy: list[str],
        suppress_origin: bool,
    ) -> bool: ...

    def close(self) -> None: ...


WebSocketAppFactory = Callable[..., _WebSocketRunner]


class LocalTeamsApiSource:
    """Maintain a local Teams event stream and retain only its meeting boolean."""

    def __init__(
        self,
        *,
        app_factory: WebSocketAppFactory | None = None,
        clock: Callable[[], datetime] = _utc_now,
        reconnect_delay: float = _RECONNECT_DELAY_SECONDS,
    ) -> None:
        if reconnect_delay < 0:
            raise ValueError("reconnect_delay must not be negative")
        self._app_factory = app_factory or websocket.WebSocketApp
        self._clock = clock
        self._reconnect_delay = reconnect_delay
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._app: _WebSocketRunner | None = None
        self._closed = False
        self._connected = False
        self._api_token: str | None = None
        self._snapshot = TeamsApiSnapshot(
            None,
            self._clock(),
            ObservationReason.SIGNAL_UNAVAILABLE,
        )

    def start(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("The Teams API source has been closed.")
            if self._thread is not None:
                return
            self._thread = threading.Thread(
                target=self._run,
                name="teams-local-api",
                daemon=True,
            )
            self._thread.start()

    def read(self) -> TeamsApiSnapshot:
        with self._lock:
            return self._snapshot

    def close(self) -> None:
        with self._lock:
            self._closed = True
            app = self._app
            thread = self._thread
        self._stop.set()
        if app is not None:
            app.close()
        if thread is not None:
            thread.join(timeout=_CLOSE_TIMEOUT_SECONDS)
            if thread.is_alive():
                raise RuntimeError("The Teams API reader did not stop in time.")

    def _url(self) -> str:
        query = {
            "protocol-version": _API_PROTOCOL_VERSION,
            "manufacturer": "ha-teams-status",
            "device": "HomeAssistant",
            "app": "ha-teams-status",
            "app-version": "1.0",
        }
        with self._lock:
            token = self._api_token
        if token is not None:
            query["token"] = token
        return f"{_API_ENDPOINT}?{urlencode(query)}"

    def _run(self) -> None:
        while not self._stop.is_set():
            app: _WebSocketRunner | None = None
            error_type: str | None = None
            try:
                app = self._app_factory(
                    self._url(),
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_pong=self._on_pong,
                )
                with self._lock:
                    if self._stop.is_set():
                        break
                    self._app = app
                app.run_forever(
                    ping_interval=_PING_INTERVAL_SECONDS,
                    ping_timeout=_PING_TIMEOUT_SECONDS,
                    http_no_proxy=["localhost", "127.0.0.1", "::1"],
                    suppress_origin=True,
                )
            except (websocket.WebSocketException, OSError) as error:
                error_type = type(error).__name__
            finally:
                with self._lock:
                    if self._app is app:
                        self._app = None
                    self._connected = False
                    self._snapshot = TeamsApiSnapshot(
                        None,
                        self._clock(),
                        ObservationReason.SIGNAL_UNAVAILABLE,
                    )
            if self._stop.is_set():
                break
            if error_type is None:
                _LOGGER.warning("Teams local API connection ended; retrying.")
            else:
                _LOGGER.warning(
                    "Teams local API connection failed (%s); retrying.",
                    error_type,
                )
            self._stop.wait(self._reconnect_delay)

    def _on_open(self, _app: object) -> None:
        with self._lock:
            self._connected = True
            self._snapshot = TeamsApiSnapshot(
                None,
                self._clock(),
                ObservationReason.SIGNAL_INCONCLUSIVE,
            )

    def _on_message(self, _app: object, message: object) -> None:
        if not isinstance(message, (str, bytes)):
            self._invalidate()
            return
        try:
            payload = json.loads(message)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._invalidate()
            return
        if not isinstance(payload, dict):
            self._invalidate()
            return

        if "tokenRefresh" in payload:
            token = payload["tokenRefresh"]
            if not isinstance(token, str) or not token:
                self._invalidate()
                return
            with self._lock:
                self._api_token = token

        if not set(payload).issubset({"meetingUpdate", "tokenRefresh"}):
            self._invalidate()
            return
        if "meetingUpdate" not in payload:
            if "tokenRefresh" not in payload:
                self._invalidate()
            return

        meeting_update = payload["meetingUpdate"]
        if not isinstance(meeting_update, dict):
            self._invalidate()
            return
        meeting_state = meeting_update.get("meetingState")
        if not isinstance(meeting_state, dict):
            self._invalidate()
            return
        is_in_meeting = meeting_state.get("isInMeeting")
        if not isinstance(is_in_meeting, bool):
            self._invalidate()
            return
        with self._lock:
            self._snapshot = TeamsApiSnapshot(is_in_meeting, self._clock(), None)

    def _on_error(self, _app: object, _error: object) -> None:
        self._invalidate(ObservationReason.SIGNAL_UNAVAILABLE)

    def _on_close(self, _app: object, _status_code: object, _message: object) -> None:
        self._invalidate(ObservationReason.SIGNAL_UNAVAILABLE)

    def _on_pong(self, _app: object, _message: object) -> None:
        with self._lock:
            if self._connected and self._snapshot.is_in_meeting is not None:
                self._snapshot = TeamsApiSnapshot(
                    self._snapshot.is_in_meeting,
                    self._clock(),
                    None,
                )

    def _invalidate(
        self,
        reason: ObservationReason = ObservationReason.SIGNAL_INCONCLUSIVE,
    ) -> None:
        with self._lock:
            self._snapshot = TeamsApiSnapshot(None, self._clock(), reason)


class WindowsTeamsDetector(MeetingDetector):
    def __init__(
        self,
        source: TeamsApiSource | None = None,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._source = source or LocalTeamsApiSource(clock=clock)
        self._clock = clock
        self._started = False
        self._closed = False

    def detect(self) -> MeetingObservation:
        if self._closed:
            raise DetectionError("The Windows Teams detector has been closed.")
        try:
            if not self._started:
                self._source.start()
                self._started = True
            snapshot = self._source.read()
        except DetectionError:
            raise
        except (OSError, RuntimeError) as error:
            raise DetectionError("Unable to obtain Windows Teams API state.") from error
        if snapshot.is_in_meeting is None:
            return MeetingObservation(
                ObservationState.INDETERMINATE,
                self._clock(),
                snapshot.reason or ObservationReason.SIGNAL_INCONCLUSIVE,
            )
        if snapshot.reason is not None:
            return MeetingObservation(
                ObservationState.INDETERMINATE,
                self._clock(),
                snapshot.reason,
            )
        return MeetingObservation(
            ObservationState.JOINED if snapshot.is_in_meeting else ObservationState.NOT_JOINED,
            snapshot.observed_at,
        )

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._source.close()
