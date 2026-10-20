"""Disposable, sanitized probe for Teams-owned macOS power assertions."""

import re
import subprocess
import sys

_ASSERTION_PATTERN = re.compile(
    r"^\s*pid\s+\d+\((?P<owner>.+)\):.*?\b(?P<kind>[A-Za-z][A-Za-z0-9]+)\s+named:"
)


def parse_teams_assertions(output: str) -> list[tuple[str, str]]:
    """Return only Teams process names and assertion types, never assertion details."""
    assertions = set()
    for line in output.splitlines():
        match = _ASSERTION_PATTERN.match(line)
        if match is None:
            continue
        owner = match.group("owner")
        if "teams" in owner.casefold():
            assertions.add((owner, match.group("kind")))
    return sorted(assertions)


def format_report(assertions: list[tuple[str, str]]) -> str:
    if not assertions:
        return "No Teams-owned assertion entries found."
    return "\n".join(f"{owner}: {kind}" for owner, kind in assertions)


def main() -> int:
    if sys.platform != "darwin":
        print("This diagnostic can only run on macOS.", file=sys.stderr)
        return 2

    try:
        result = subprocess.run(
            ["pmset", "-g", "assertions"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        print("Unable to query macOS power assertions.", file=sys.stderr)
        return 1

    if result.returncode != 0:
        print("Unable to query macOS power assertions.", file=sys.stderr)
        return 1

    print(format_report(parse_teams_assertions(result.stdout)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
