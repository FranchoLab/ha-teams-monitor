# Proposal

## Why

The monitor currently has to be started manually in a terminal, so it does not reliably resume at login. A per-user macOS LaunchAgent can start it in the same logged-in session as Teams without requiring root or broad OS permissions.

## What Changes

- Add macOS-specific CLI commands to install and uninstall a per-user LaunchAgent that starts monitoring at login and restarts after unexpected exits.
- Build a named standalone macOS executable during installation and register it with an explicit configuration file using absolute paths, so the process is identifiable instead of appearing as generic Python.
- Handle normal termination signals so stopping or uninstalling the agent can shut down the MQTT publisher cleanly.
- Document setup, status and manual service control, configuration and log paths, the recognizable process name, and the need to reinstall after application updates.

## Capabilities

### New Capabilities
- `macos-login-agent`: Install and manage a per-user macOS login agent for the Teams status monitor.

### Modified Capabilities

## Impact

- CLI service-management commands, optional macOS executable packaging, and a macOS-specific LaunchAgent adapter, composed at the CLI boundary.
- Application shutdown behavior and tests for graceful termination, generated plist contents, and service-management commands.
- README setup instructions and native macOS validation for login, restart, stop, and uninstall behavior.
- No new monitor runtime dependency, privileged daemon, Windows/Linux startup integration, or changes to the meeting-detection and MQTT sensor contracts. PyInstaller is an optional build extra used only to create the named macOS executable.
