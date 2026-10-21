# Tasks

## 1. Graceful monitor shutdown

- [x] 1.1 Make the monitor loop respond to SIGTERM through its existing cleanup path while preserving KeyboardInterrupt behavior; verify focused CLI tests assert polling stops and the publisher is stopped.

## 2. LaunchAgent integration

- [x] 2.1 Implement a macOS LaunchAgent plist builder using absolute named-executable and config paths, per-user log paths, RunAtLoad, and KeepAlive; verify plist tests assert required keys and that credentials are absent.
- [x] 2.2 Implement idempotent per-user launchctl install/uninstall operations with explicit filesystem and launchctl errors; verify unit tests cover bootstrap, bootout, replacement, and already-absent uninstall behavior using a fake command runner.

## 3. CLI and setup documentation

- [x] 3.1 Add macOS-only service install/uninstall CLI commands that validate the config before changing service state; verify CLI tests cover valid installation, invalid config, and unsupported-platform errors without service-file changes.
- [x] 3.2 Document foreground validation, install/uninstall commands, launchctl status and manual control, log locations, config protection, and reinstallation after application updates; verify each documented command and path matches the CLI and named executable.

## 4. Native macOS validation

- [x] 4.1 Validate as a standard user that installation starts the monitor immediately and at login, unexpected exit restarts it, launchctl stop/uninstall terminates cleanly, and logs contain no credentials; record any native-only limitations separately from portable test results.

## Validation record

- Portable: Ruff, format, strict mypy, all 88 pytest tests, package build, and strict OpenSpec validation passed. The npm script could not find a local `openspec` binary; the pinned OpenSpec 1.14.3 CLI passed when invoked with `npm exec`.
- Native macOS as a standard user: a temporary LaunchAgent started immediately, restarted with a new PID after forced process termination, stopped via `launchctl stop`, and unloaded on uninstall. A test-only credential was absent from its stdout and stderr logs.
- Native limitation: no logout/login cycle was performed. The generated plist's `RunAtLoad` key and immediate launchd bootstrap were verified; startup during a later login was not directly observed.

## 5. Identifiable macOS process

- [x] 5.1 Add the optional `macos-service` PyInstaller extra and a build entry point; produce a named standalone executable in a temporary build directory and report build failures before changing service state.
- [x] 5.2 Install the generated runtime under per-user Application Support, point the LaunchAgent at the named executable, rebuild it on reinstall, and remove it on uninstall; cover replacement and failure paths with portable tests.
- [x] 5.3 Update setup documentation with the optional build extra, recognizable process name, runtime location, and reinstall/update behavior; verify documented paths and commands against the implementation.
- [x] 5.4 Validate natively that Activity Monitor/process inspection identifies the monitor as `ha-teams-status` and that install, restart, stop, and uninstall still work with the bundled executable.
