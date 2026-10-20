from datetime import UTC, datetime, timedelta

import pytest

from ha_teams_status.domain.observation import (
    MeetingObservation,
    ObservationReason,
    ObservationState,
)

OBSERVED_AT = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "state",
    [ObservationState.JOINED, ObservationState.NOT_JOINED],
)
def test_known_observation_states_have_timestamp_and_no_reason(
    state: ObservationState,
) -> None:
    observation = MeetingObservation(state=state, observed_at=OBSERVED_AT)

    assert observation.state is state
    assert observation.observed_at == OBSERVED_AT
    assert observation.reason is None


def test_indeterminate_observation_requires_bounded_reason_code() -> None:
    observation = MeetingObservation(
        state=ObservationState.INDETERMINATE,
        observed_at=OBSERVED_AT,
        reason=ObservationReason.SIGNAL_UNAVAILABLE,
    )

    assert observation.reason is ObservationReason.SIGNAL_UNAVAILABLE


@pytest.mark.parametrize(
    ("state", "reason"),
    [
        (ObservationState.JOINED, ObservationReason.SIGNAL_UNAVAILABLE),
        (ObservationState.NOT_JOINED, ObservationReason.SIGNAL_INCONCLUSIVE),
        (ObservationState.INDETERMINATE, None),
    ],
)
def test_observation_rejects_inconsistent_state_and_reason(
    state: ObservationState,
    reason: ObservationReason | None,
) -> None:
    with pytest.raises(ValueError):
        MeetingObservation(state=state, observed_at=OBSERVED_AT, reason=reason)


def test_observation_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        MeetingObservation(
            state=ObservationState.NOT_JOINED,
            observed_at=datetime(2026, 10, 19, 12, 0),
        )


def test_staleness_uses_strict_maximum_age_boundary() -> None:
    observation = MeetingObservation(
        state=ObservationState.JOINED,
        observed_at=OBSERVED_AT,
    )

    assert not observation.is_stale(
        as_of=OBSERVED_AT + timedelta(seconds=30),
        max_age=timedelta(seconds=30),
    )
    assert observation.is_stale(
        as_of=OBSERVED_AT + timedelta(seconds=31),
        max_age=timedelta(seconds=30),
    )


def test_staleness_requires_positive_age_and_timezone_aware_now() -> None:
    observation = MeetingObservation(
        state=ObservationState.NOT_JOINED,
        observed_at=OBSERVED_AT,
    )

    with pytest.raises(ValueError, match="max_age must be positive"):
        observation.is_stale(as_of=OBSERVED_AT, max_age=timedelta(0))
    with pytest.raises(ValueError, match="as_of must be timezone-aware"):
        observation.is_stale(
            as_of=datetime(2026, 10, 19, 12, 0),
            max_age=timedelta(seconds=30),
        )
