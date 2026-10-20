"""Platform-independent meeting observations."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class ObservationState(StrEnum):
    JOINED = "joined"
    NOT_JOINED = "not_joined"
    INDETERMINATE = "indeterminate"


class ObservationReason(StrEnum):
    UNSUPPORTED_PLATFORM = "unsupported_platform"
    UNSUPPORTED_CLIENT = "unsupported_client"
    SIGNAL_UNAVAILABLE = "signal_unavailable"
    SIGNAL_INCONCLUSIVE = "signal_inconclusive"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class MeetingObservation:
    state: ObservationState
    observed_at: datetime
    reason: ObservationReason | None = None

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.state is ObservationState.INDETERMINATE and self.reason is None:
            raise ValueError("indeterminate observations require a reason")
        if self.state is not ObservationState.INDETERMINATE and self.reason is not None:
            raise ValueError("only indeterminate observations may have a reason")

    def is_stale(self, *, as_of: datetime, max_age: timedelta) -> bool:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        if max_age <= timedelta(0):
            raise ValueError("max_age must be positive")
        return as_of - self.observed_at > max_age
