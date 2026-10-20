from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from ha_teams_status.application.monitor import DetectionError, ObserveMeeting
from ha_teams_status.domain.observation import (
    MeetingObservation,
    ObservationReason,
    ObservationState,
)

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


@dataclass
class FakeDetector:
    observation: MeetingObservation | None = None
    error: DetectionError | None = None

    def detect(self) -> MeetingObservation:
        if self.error is not None:
            raise self.error
        assert self.observation is not None
        return self.observation


def test_use_case_returns_fresh_observation_unchanged() -> None:
    observation = MeetingObservation(
        state=ObservationState.JOINED,
        observed_at=NOW - timedelta(seconds=5),
    )
    use_case = ObserveMeeting(
        detector=FakeDetector(observation=observation),
        clock=lambda: NOW,
        max_age=timedelta(seconds=30),
    )

    assert use_case.execute() is observation


@pytest.mark.parametrize(
    "state",
    [ObservationState.JOINED, ObservationState.NOT_JOINED],
)
def test_use_case_converts_stale_state_to_indeterminate(state: ObservationState) -> None:
    observation = MeetingObservation(
        state=state,
        observed_at=NOW - timedelta(seconds=31),
    )
    use_case = ObserveMeeting(
        detector=FakeDetector(observation=observation),
        clock=lambda: NOW,
        max_age=timedelta(seconds=30),
    )

    result = use_case.execute()

    assert result.state is ObservationState.INDETERMINATE
    assert result.reason is ObservationReason.STALE
    assert result.observed_at == NOW


def test_use_case_preserves_detection_error() -> None:
    error = DetectionError("signal unavailable")
    use_case = ObserveMeeting(
        detector=FakeDetector(error=error),
        clock=lambda: NOW,
        max_age=timedelta(seconds=30),
    )

    with pytest.raises(DetectionError) as captured:
        use_case.execute()

    assert captured.value is error


def test_use_case_requires_positive_max_age() -> None:
    with pytest.raises(ValueError, match="max_age must be positive"):
        ObserveMeeting(
            detector=FakeDetector(),
            clock=lambda: NOW,
            max_age=timedelta(0),
        )
