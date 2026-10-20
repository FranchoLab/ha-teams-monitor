"""Use case and port for obtaining a fresh meeting observation."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from ..domain.observation import (
    MeetingObservation,
    ObservationReason,
    ObservationState,
)


class DetectionError(Exception):
    """Raised when a detector cannot produce a trustworthy observation."""


class MeetingDetector(Protocol):
    def detect(self) -> MeetingObservation: ...


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
