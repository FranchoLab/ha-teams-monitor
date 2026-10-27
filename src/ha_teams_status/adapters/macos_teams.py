"""Microsoft Teams meeting detector for macOS."""

import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ..application.monitor import DetectionError, MeetingDetector
from ..domain.observation import (
    MeetingObservation,
    ObservationReason,
    ObservationState,
)
from .macos_power_assertions import (
    IOKitPowerAssertionSource,
    PowerAssertionReadError,
    TeamsPowerAssertions,
)

VALIDATED_TEAMS_BUILDS = frozenset(
    {
        "26276.505.5234.9924",
        "26289.203.5259.2574",
    }
)
_JOINED_ASSERTIONS = frozenset({"NoDisplaySleepAssertion", "NoIdleSleepAssertion"})
_LOGGER = logging.getLogger(__name__)


class PowerAssertionSource(Protocol):
    def read(self) -> TeamsPowerAssertions: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class MacOSTeamsDetector(MeetingDetector):
    source: PowerAssertionSource | None = None
    clock: Callable[[], datetime] = _utc_now

    def detect(self) -> MeetingObservation:
        observed_at = self.clock()
        if sys.platform != "darwin":
            return self._indeterminate(observed_at, ObservationReason.UNSUPPORTED_PLATFORM)

        source = self.source or IOKitPowerAssertionSource()
        try:
            assertions = source.read()
        except PowerAssertionReadError as error:
            _LOGGER.warning(
                "Unable to read macOS Teams power assertions (%s).",
                type(error).__name__,
            )
            raise DetectionError("Unable to read macOS Teams power assertions.") from error

        if not assertions.process_found:
            return MeetingObservation(ObservationState.NOT_JOINED, observed_at)
        if assertions.version not in VALIDATED_TEAMS_BUILDS:
            return self._indeterminate(observed_at, ObservationReason.UNSUPPORTED_CLIENT)
        if _JOINED_ASSERTIONS.issubset(assertions.assertion_types):
            return MeetingObservation(ObservationState.JOINED, observed_at)
        if not assertions.assertion_types:
            return MeetingObservation(ObservationState.NOT_JOINED, observed_at)
        return self._indeterminate(observed_at, ObservationReason.SIGNAL_INCONCLUSIVE)

    @staticmethod
    def _indeterminate(
        observed_at: datetime,
        reason: ObservationReason,
    ) -> MeetingObservation:
        return MeetingObservation(
            state=ObservationState.INDETERMINATE,
            observed_at=observed_at,
            reason=reason,
        )
