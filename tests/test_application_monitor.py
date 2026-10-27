import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from ha_teams_status.application.monitor import (
    DetectionError,
    MonitorMeeting,
    ObserveMeeting,
)
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


@dataclass
class FakePublisher:
    observations: list[MeetingObservation]

    def publish(self, observation: MeetingObservation) -> None:
        self.observations.append(observation)


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


@pytest.mark.parametrize(
    "state",
    [ObservationState.JOINED, ObservationState.NOT_JOINED],
)
def test_monitor_publishes_confirmed_observation_states(state: ObservationState) -> None:
    observation = MeetingObservation(state=state, observed_at=NOW)
    publisher = FakePublisher(observations=[])
    monitor = MonitorMeeting(
        observe=ObserveMeeting(
            detector=FakeDetector(observation=observation),
            clock=lambda: NOW,
            max_age=timedelta(seconds=30),
        ),
        publisher=publisher,
        clock=lambda: NOW,
    )

    assert monitor.execute() is observation
    assert [item.state for item in publisher.observations] == [state]


def test_monitor_publishes_indeterminate_instead_of_not_joined() -> None:
    observation = MeetingObservation(
        state=ObservationState.INDETERMINATE,
        observed_at=NOW,
        reason=ObservationReason.SIGNAL_INCONCLUSIVE,
    )
    publisher = FakePublisher(observations=[])
    monitor = MonitorMeeting(
        observe=ObserveMeeting(
            detector=FakeDetector(observation=observation),
            clock=lambda: NOW,
            max_age=timedelta(seconds=30),
        ),
        publisher=publisher,
        clock=lambda: NOW,
    )

    result = monitor.execute()

    assert result.state is ObservationState.INDETERMINATE
    assert [item.state for item in publisher.observations] == [ObservationState.INDETERMINATE]


def test_monitor_publishes_stale_observation_as_indeterminate() -> None:
    stale_observation = MeetingObservation(
        state=ObservationState.NOT_JOINED,
        observed_at=NOW - timedelta(seconds=31),
    )
    publisher = FakePublisher(observations=[])
    monitor = MonitorMeeting(
        observe=ObserveMeeting(
            detector=FakeDetector(observation=stale_observation),
            clock=lambda: NOW,
            max_age=timedelta(seconds=30),
        ),
        publisher=publisher,
        clock=lambda: NOW,
    )

    result = monitor.execute()

    assert result.state is ObservationState.INDETERMINATE
    assert [item.state for item in publisher.observations] == [ObservationState.INDETERMINATE]


def test_monitor_publishes_detection_failure_as_indeterminate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="ha_teams_status.application.monitor")
    publisher = FakePublisher(observations=[])
    monitor = MonitorMeeting(
        observe=ObserveMeeting(
            detector=FakeDetector(error=DetectionError("private detector detail")),
            clock=lambda: NOW,
            max_age=timedelta(seconds=30),
        ),
        publisher=publisher,
        clock=lambda: NOW,
    )

    result = monitor.execute()

    assert result.state is ObservationState.INDETERMINATE
    assert result.reason is ObservationReason.SIGNAL_UNAVAILABLE
    assert [item.state for item in publisher.observations] == [ObservationState.INDETERMINATE]
    assert "DetectionError" in caplog.text
    assert "private detector detail" not in caplog.text


def test_monitor_logs_observation_state_transitions(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="ha_teams_status.application.monitor")
    detector = FakeDetector(observation=MeetingObservation(ObservationState.JOINED, NOW))
    monitor = MonitorMeeting(
        observe=ObserveMeeting(
            detector=detector,
            clock=lambda: NOW,
            max_age=timedelta(seconds=30),
        ),
        publisher=FakePublisher(observations=[]),
        clock=lambda: NOW,
    )

    monitor.execute()
    monitor.execute()
    detector.observation = MeetingObservation(ObservationState.NOT_JOINED, NOW)
    monitor.execute()

    transition_messages = [
        record.message for record in caplog.records if record.levelno == logging.INFO
    ]
    assert len(transition_messages) == 2
    assert "to_state=joined" in transition_messages[0]
    assert "to_state=not_joined" in transition_messages[1]
    assert "private" not in caplog.text


def test_monitor_guard_publishes_unknown_after_maximum_joined_duration(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="ha_teams_status.application.monitor")
    detector = FakeDetector(observation=MeetingObservation(ObservationState.JOINED, NOW))
    publisher = FakePublisher(observations=[])
    monotonic_now = [100.0]
    monitor = MonitorMeeting(
        observe=ObserveMeeting(
            detector=detector,
            clock=lambda: NOW,
            max_age=timedelta(seconds=30),
        ),
        publisher=publisher,
        clock=lambda: NOW,
        max_joined_duration=timedelta(seconds=10),
        monotonic_clock=lambda: monotonic_now[0],
    )

    assert monitor.execute().state is ObservationState.JOINED
    monotonic_now[0] += 10
    result = monitor.execute()

    assert result.state is ObservationState.INDETERMINATE
    assert result.reason is ObservationReason.JOINED_DURATION_EXCEEDED
    assert [item.state for item in publisher.observations] == [
        ObservationState.JOINED,
        ObservationState.INDETERMINATE,
    ]
    assert "safety limit exceeded" in caplog.text


def test_monitor_guard_does_not_reset_on_indeterminate_observations() -> None:
    detector = FakeDetector(observation=MeetingObservation(ObservationState.JOINED, NOW))
    publisher = FakePublisher(observations=[])
    monotonic_now = [100.0]
    monitor = MonitorMeeting(
        observe=ObserveMeeting(
            detector=detector,
            clock=lambda: NOW,
            max_age=timedelta(seconds=30),
        ),
        publisher=publisher,
        clock=lambda: NOW,
        max_joined_duration=timedelta(seconds=10),
        monotonic_clock=lambda: monotonic_now[0],
    )

    monitor.execute()
    monotonic_now[0] += 7
    detector.observation = MeetingObservation(
        ObservationState.INDETERMINATE,
        NOW,
        ObservationReason.SIGNAL_INCONCLUSIVE,
    )
    assert monitor.execute().reason is ObservationReason.SIGNAL_INCONCLUSIVE

    monotonic_now[0] += 3
    detector.observation = MeetingObservation(ObservationState.JOINED, NOW)
    result = monitor.execute()

    assert result.state is ObservationState.INDETERMINATE
    assert result.reason is ObservationReason.JOINED_DURATION_EXCEEDED


def test_monitor_guard_remains_unknown_until_confirmed_not_joined() -> None:
    detector = FakeDetector(observation=MeetingObservation(ObservationState.JOINED, NOW))
    publisher = FakePublisher(observations=[])
    monotonic_now = [100.0]
    monitor = MonitorMeeting(
        observe=ObserveMeeting(
            detector=detector,
            clock=lambda: NOW,
            max_age=timedelta(seconds=30),
        ),
        publisher=publisher,
        clock=lambda: NOW,
        max_joined_duration=timedelta(seconds=10),
        monotonic_clock=lambda: monotonic_now[0],
    )

    monitor.execute()
    monotonic_now[0] += 10
    assert monitor.execute().reason is ObservationReason.JOINED_DURATION_EXCEEDED

    detector.observation = MeetingObservation(
        ObservationState.INDETERMINATE,
        NOW,
        ObservationReason.SIGNAL_UNAVAILABLE,
    )
    assert monitor.execute().reason is ObservationReason.JOINED_DURATION_EXCEEDED

    detector.observation = MeetingObservation(ObservationState.NOT_JOINED, NOW)
    assert monitor.execute().state is ObservationState.NOT_JOINED
    detector.observation = MeetingObservation(ObservationState.JOINED, NOW)
    assert monitor.execute().state is ObservationState.JOINED
