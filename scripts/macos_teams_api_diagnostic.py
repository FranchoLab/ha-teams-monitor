"""Sanitized native diagnostic for the IOKit-backed Teams assertion source."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ha_teams_status.adapters.macos_power_assertions import (
    IOKitPowerAssertionSource,
    PowerAssertionReadError,
)


def main() -> int:
    if sys.platform != "darwin":
        print("This diagnostic can only run on macOS.", file=sys.stderr)
        return 2

    try:
        assertions = IOKitPowerAssertionSource().read()
    except PowerAssertionReadError as error:
        print(f"Unable to read macOS Teams power assertions: {error}", file=sys.stderr)
        return 1

    if not assertions.process_found:
        print("No MSTeams process found.")
        return 0

    print(f"MSTeams build: {assertions.version or 'unknown'}")
    if assertions.assertion_types:
        print(f"MSTeams assertions: {', '.join(sorted(assertions.assertion_types))}")
    else:
        print("MSTeams assertions: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
