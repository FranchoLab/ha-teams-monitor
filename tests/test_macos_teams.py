import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ha_teams_status.adapters.macos_power_assertions import (
    PowerAssertionReadError,
    TeamsPowerAssertions,
    _bundle_version,
)
from ha_teams_status.adapters.macos_teams import (
    VALIDATED_TEAMS_BUILDS,
    MacOSTeamsDetector,
)
from ha_teams_status.application.monitor import DetectionError, ObserveMeeting
from ha_teams_status.domain.observation import ObservationReason, ObservationState

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
SUPPORTED_BUILD = "26276.505.5234.9924"
OBSERVED_BUILD = "26289.203.5259.2574"
VALIDATED_BUILDS = (SUPPORTED_BUILD, OBSERVED_BUILD)
JOINED_ASSERTIONS = frozenset({"NoDisplaySleepAssertion", "NoIdleSleepAssertion"})


@dataclass
class FakeAssertionSource:
    snapshot: TeamsPowerAssertions | None = None
    error: PowerAssertionReadError | None = None

    def read(self) -> TeamsPowerAssertions:
        if self.error is not None:
            raise self.error
        assert self.snapshot is not None
        return self.snapshot


def make_detector(
    monkeypatch: pytest.MonkeyPatch, source: FakeAssertionSource
) -> MacOSTeamsDetector:
    monkeypatch.setattr("ha_teams_status.adapters.macos_teams.sys.platform", "darwin")
    return MacOSTeamsDetector(source=source, clock=lambda: NOW)


@pytest.mark.parametrize("version", VALIDATED_BUILDS)
@pytest.mark.parametrize(
    "assertion_types",
    [frozenset(), frozenset({"NoDisplaySleepAssertion"}), frozenset({"NoIdleSleepAssertion"})],
)
def test_detector_does_not_report_joined_without_both_assertions(
    monkeypatch: pytest.MonkeyPatch,
    version: str,
    assertion_types: frozenset[str],
) -> None:
    detector = make_detector(
        monkeypatch,
        FakeAssertionSource(snapshot=TeamsPowerAssertions(True, version, assertion_types)),
    )

    observation = detector.detect()

    if not assertion_types:
        assert observation.state is ObservationState.NOT_JOINED
        assert observation.reason is None
    else:
        assert observation.state is ObservationState.INDETERMINATE
        assert observation.reason is ObservationReason.SIGNAL_INCONCLUSIVE


@pytest.mark.parametrize("version", VALIDATED_BUILDS)
def test_detector_reports_joined_only_for_validated_assertion_pair(
    monkeypatch: pytest.MonkeyPatch,
    version: str,
) -> None:
    detector = make_detector(
        monkeypatch,
        FakeAssertionSource(snapshot=TeamsPowerAssertions(True, version, JOINED_ASSERTIONS)),
    )

    observation = detector.detect()

    assert observation.state is ObservationState.JOINED
    assert observation.observed_at == NOW


@pytest.mark.parametrize("version", [None, "unvalidated-build", "26300.0.0.0"])
def test_detector_reports_unvalidated_client_without_signature_as_indeterminate(
    monkeypatch: pytest.MonkeyPatch,
    version: str | None,
) -> None:
    detector = make_detector(
        monkeypatch,
        FakeAssertionSource(snapshot=TeamsPowerAssertions(True, version, frozenset())),
    )

    observation = detector.detect()

    assert observation.state is ObservationState.INDETERMINATE
    assert observation.reason is ObservationReason.UNSUPPORTED_CLIENT


@pytest.mark.parametrize(
    "version",
    [None, "unvalidated-build", "26300.0.0.0"],
)
def test_detector_reports_complete_signature_on_unvalidated_build_as_indeterminate(
    monkeypatch: pytest.MonkeyPatch,
    version: str | None,
) -> None:
    detector = make_detector(
        monkeypatch,
        FakeAssertionSource(snapshot=TeamsPowerAssertions(True, version, JOINED_ASSERTIONS)),
    )

    observation = detector.detect()

    assert observation.state is ObservationState.INDETERMINATE
    assert observation.reason is ObservationReason.UNSUPPORTED_CLIENT


def test_detector_reports_absent_teams_process_as_not_joined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detector = make_detector(
        monkeypatch,
        FakeAssertionSource(snapshot=TeamsPowerAssertions(False, None, frozenset())),
    )

    assert detector.detect().state is ObservationState.NOT_JOINED


def test_detector_preserves_signal_read_failure_as_detection_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="ha_teams_status.adapters.macos_teams")
    detector = make_detector(
        monkeypatch,
        FakeAssertionSource(error=PowerAssertionReadError("native query failed")),
    )

    with pytest.raises(DetectionError):
        detector.detect()
    assert "PowerAssertionReadError" in caplog.text
    assert "native query failed" not in caplog.text


def test_detector_is_indeterminate_off_macos_without_reading_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ha_teams_status.adapters.macos_teams.sys.platform", "linux")
    detector = MacOSTeamsDetector(
        source=FakeAssertionSource(error=PowerAssertionReadError("must not be read")),
        clock=lambda: NOW,
    )

    observation = detector.detect()

    assert observation.state is ObservationState.INDETERMINATE
    assert observation.reason is ObservationReason.UNSUPPORTED_PLATFORM


def test_stale_adapter_observation_is_indeterminate_not_not_joined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("ha_teams_status.adapters.macos_teams.sys.platform", "darwin")
    detector = MacOSTeamsDetector(
        source=FakeAssertionSource(
            snapshot=TeamsPowerAssertions(True, SUPPORTED_BUILD, JOINED_ASSERTIONS)
        ),
        clock=lambda: NOW - timedelta(seconds=31),
    )
    use_case = ObserveMeeting(
        detector=detector,
        clock=lambda: NOW,
        max_age=timedelta(seconds=30),
    )

    observation = use_case.execute()

    assert observation.state is ObservationState.INDETERMINATE
    assert observation.reason is ObservationReason.STALE


def test_observation_contains_no_assertion_or_meeting_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detector = make_detector(
        monkeypatch,
        FakeAssertionSource(
            snapshot=TeamsPowerAssertions(True, SUPPORTED_BUILD, JOINED_ASSERTIONS)
        ),
    )

    observation = detector.detect()

    assert set(observation.__dataclass_fields__) == {"state", "observed_at", "reason"}
    assert not any(assertion in repr(observation) for assertion in JOINED_ASSERTIONS)
    assert "MSTeams" not in repr(observation)


def test_bundle_version_reads_only_application_version(tmp_path: Path) -> None:
    import plistlib

    bundle = tmp_path / "Microsoft Teams.app"
    info_path = bundle / "Contents" / "Info.plist"
    info_path.parent.mkdir(parents=True)
    with info_path.open("wb") as info_file:
        plistlib.dump(
            {"CFBundleVersion": SUPPORTED_BUILD, "CFBundleName": "Microsoft Teams"},
            info_file,
        )

    assert set(VALIDATED_BUILDS) == VALIDATED_TEAMS_BUILDS
    assert _bundle_version(str(bundle / "Contents" / "MacOS" / "MSTeams")) == SUPPORTED_BUILD
