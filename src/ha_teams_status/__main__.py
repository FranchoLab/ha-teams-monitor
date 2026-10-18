"""CLI entry point and future composition root."""

import argparse
from collections.abc import Sequence
from importlib.metadata import version


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ha-teams-status",
        description="Teams meeting sensor foundation. Live monitoring is not implemented.",
    )
    parser.add_argument("--version", action="version", version=version("ha-teams-status"))
    parser.parse_args(argv)
    parser.error("Live monitoring is not implemented. Use --help or --version.")


if __name__ == "__main__":
    raise SystemExit(main())
