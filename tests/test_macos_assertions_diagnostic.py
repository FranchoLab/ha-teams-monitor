from collections.abc import Callable
from pathlib import Path
from runpy import run_path
from typing import cast

diagnostic = run_path(
    str(Path(__file__).resolve().parents[1] / "scripts" / "macos_assertions_diagnostic.py")
)
format_report = cast(Callable[[list[tuple[str, str]]], str], diagnostic["format_report"])
parse_teams_assertions = cast(
    Callable[[str], list[tuple[str, str]]], diagnostic["parse_teams_assertions"]
)


def test_parse_teams_assertions_discards_non_teams_and_assertion_details() -> None:
    output = "\n".join(
        [
            "Listed by owning process:",
            " pid 412(Microsoft Teams): [0x0000000100000001] 00:00:00 "
            'PreventUserIdleSystemSleep named: "Private meeting title"',
            " pid 413(Teams Helper (Renderer)): [0x0000000100000002] 00:00:00 "
            'UserIsActive named: "Participant details"',
            " pid 414(Safari): [0x0000000100000003] 00:00:00 "
            'PreventUserIdleSystemSleep named: "Web content"',
        ]
    )

    assertions = parse_teams_assertions(output)

    assert assertions == [
        ("Microsoft Teams", "PreventUserIdleSystemSleep"),
        ("Teams Helper (Renderer)", "UserIsActive"),
    ]
    report = format_report(assertions)
    assert "Private meeting title" not in report
    assert "Participant details" not in report
    assert "Web content" not in report


def test_format_report_does_not_claim_call_state_without_matching_assertions() -> None:
    assert format_report([]) == "No Teams-owned assertion entries found."
