"""Use case and port for obtaining a fresh meeting observation."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from time import monotonic
from typing import Protocol

from ..domain.observation import (
    MeetingObservation,
    ObservationReason,
    ObservationState,
)

_LOGGER = logging.getLogger(__name__)


class DetectionError(Exception):
    """Raised when a detector cannot produce a trustworthy observation."""


class MeetingDetector(Protocol):
    def detect(self) -> MeetingObservation: ...


class MeetingObservationPublisher(Protocol):
    def publish(self, observation: MeetingObservation) -> None: ...


@dataclass(frozen=True, slots=True)
class ObserveMeeting:
    detector: MeetingDetector
    clock: Callable[[], datetime]
    max_age: timedelta

    def __post_init__(self) -> None:
        if self.max_age <= timedelta(0):
            raise ValueError("max_age must be positive")

    def execute(self) -> MeetingObservation:
        observation = self.detector.detect()
        now = self.clock()
        if observation.is_stale(as_of=now, max_age=self.max_age):
            return MeetingObservation(
                state=ObservationState.INDETERMINATE,
                observed_at=now,
                reason=ObservationReason.STALE,
            )
        return observation


@dataclass(slots=True)
class MonitorMeeting:
    observe: ObserveMeeting
    publisher: MeetingObservationPublisher
    clock: Callable[[], datetime]
    max_joined_duration: timedelta = timedelta(hours=8)
    monotonic_clock: Callable[[], float] = monotonic
    _joined_since: float | None = field(default=None, init=False)
    _joined_duration_exceeded: bool = field(default=False, init=False)
    _last_logged_outcome: tuple[ObservationState, ObservationReason | None] | None = field(
        default=None,
        init=False,
    )

    def __post_init__(self) -> None:
        if self.max_joined_duration <= timedelta(0):
            raise ValueError("max_joined_duration must be positive")

    def execute(self) -> MeetingObservation:
        try:
            observation = self.observe.execute()
        except DetectionError as error:
            cause = error.__cause__
            failure_type = type(cause).__name__ if cause is not None else type(error).__name__
            _LOGGER.warning("Meeting detection failed (%s).", failure_type)
            observation = MeetingObservation(
                state=ObservationState.INDETERMINATE,
                observed_at=self.clock(),
                reason=ObservationReason.SIGNAL_UNAVAILABLE,
            )
        observation = self._apply_joined_duration_guard(observation)
        self._log_observation_transition(observation)
        self.publisher.publish(observation)
        return observation

    def _log_observation_transition(self, observation: MeetingObservation) -> None:
        outcome = (observation.state, observation.reason)
        if outcome == self._last_logged_outcome:
            return
        previous_state, previous_reason = self._last_logged_outcome or (None, None)
        _LOGGER.info(
            "Meeting observation changed: from_state=%s from_reason=%s to_state=%s "
            "to_reason=%s observed_at=%s",
            previous_state.value if previous_state is not None else "none",
            previous_reason.value if previous_reason is not None else "none",
            observation.state.value,
            observation.reason.value if observation.reason is not None else "none",
            observation.observed_at.isoformat(),
        )
        self._last_logged_outcome = outcome

    def _apply_joined_duration_guard(
        self,
        observation: MeetingObservation,
    ) -> MeetingObservation:
        if observation.state is ObservationState.NOT_JOINED:
            self._joined_since = None
            self._joined_duration_exceeded = False
            return observation

        if self._joined_duration_exceeded:
            return self._joined_duration_indeterminate(observation)

        now = self.monotonic_clock()
        if observation.state is ObservationState.JOINED and self._joined_since is None:
            self._joined_since = now

        if (
            self._joined_since is not None
            and now - self._joined_since >= self.max_joined_duration.total_seconds()
        ):
            self._joined_duration_exceeded = True
            _LOGGER.warning(
                "Joined-state safety limit exceeded after %.0f seconds; publishing UNKNOWN.",
                self.max_joined_duration.total_seconds(),
            )
            return self._joined_duration_indeterminate(observation)
        return observation

    @staticmethod
    def _joined_duration_indeterminate(
        observation: MeetingObservation,
    ) -> MeetingObservation:
        return MeetingObservation(
            state=ObservationState.INDETERMINATE,
            observed_at=observation.observed_at,
            reason=ObservationReason.JOINED_DURATION_EXCEEDED,
        )
