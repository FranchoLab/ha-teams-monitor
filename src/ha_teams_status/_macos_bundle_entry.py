"""PyInstaller entry point for the identifiable macOS service executable."""

from ha_teams_status.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
