# Design

## Context

See proposal.md for motivation and macos-login-agent/spec.md for externally visible behavior. The CLI currently requires an explicit `--config` path and runs the monitor in a polling loop. It shuts down the publisher in a `finally` block after `KeyboardInterrupt`, but the default SIGTERM behavior exits without reaching that cleanup. The MQTT publisher already publishes retained offline availability during graceful shutdown.

The live detector is macOS-specific and runs as the normal logged-in user. The project keeps OS integration in adapters and composes it at the CLI boundary.

## Goals / Non-Goals

**Goals:**
- Install and remove a per-user LaunchAgent without requiring root or an interactive shell.
- Show a recognizable `ha-teams-status` process name instead of a generic Python interpreter process.
- Start the monitor immediately after installation, at subsequent logins, and after unexpected process exits.
- Shut down the monitor and publisher cleanly when launchd unloads the service.
- Keep credentials in the existing protected config file and report service-management failures clearly.

**Non-Goals:**
- Installing a system LaunchDaemon, running while the user is logged out, or supporting Windows/Linux startup services.
- Managing broker configuration, deleting retained Home Assistant MQTT discovery, or moving the user's config file.
- Keeping the installed executable synchronized with later application updates; the user must reinstall the agent to rebuild it.

## Decisions

### Use a per-user LaunchAgent

Write a plist in the current user's `~/Library/LaunchAgents` and manage it in that user's `gui/<uid>` launchd domain. Use `RunAtLoad` to start it at login and `KeepAlive` to restart an unexpected process exit. Uninstall must boot the job out before removing its plist so an intentional termination is not restarted.

This keeps detection in the same user session as Teams and avoids a privileged daemon. A system LaunchDaemon was rejected because it runs in a different security/session context. A shell login script was rejected because it depends on shell startup behavior and does not provide launchd lifecycle management.

### Build and install a named macOS executable

Activity Monitor derives the displayed process name from the executable, not the LaunchAgent `Label`; renaming only the label would not resolve the generic `python` name. Use PyInstaller as an optional `macos-service` extra to build a standalone console-mode executable named `ha-teams-status` during service installation. Store its one-directory runtime under `~/Library/Application Support/ha-teams-status` and point `ProgramArguments` at that executable plus `--config` with the selected config path resolved to an absolute path.

Build in a temporary directory before changing service state, then replace the per-user runtime and plist when installation succeeds. Invoke the executable directly rather than through a shell, `uv`, `mise`, or `PATH`; launchd does not inherit an interactive environment. Validate the config before changing service state. The plist contains only executable arguments and paths, never MQTT credentials. The config stays at its existing location with its existing user-only access controls. Reinstall after updating the application to rebuild the installed executable.

### Keep launchd operations in a macOS adapter

Add CLI service-management commands that delegate executable packaging, plist creation, and `launchctl` operations to a macOS-specific adapter. Keep launchd, plist serialization, process signals, and packaging tools out of domain code. Use the standard-library plist support and subprocess facilities; keep PyInstaller optional and limited to the installation/build path.

Make installation repeatable: build the new executable first, unload an existing registration before replacing its runtime and plist, then bootstrap it in the current user's GUI domain. Surface build, filesystem, and launchd failures instead of reporting success. Uninstall an already-absent registration idempotently, but report other errors; remove the generated runtime as well as the plist while retaining the config and logs.

### Handle SIGTERM through the normal shutdown path

Use a stop event in the monitoring loop and translate SIGTERM into a request to stop. Let `run_monitoring` leave the loop and call the existing publisher `stop()` path in `finally`; keep KeyboardInterrupt behavior. This allows a normal service stop to publish offline availability before disconnecting.

### Provide per-user diagnostics

Redirect the LaunchAgent's standard output and error to files under `~/Library/Logs/ha-teams-status`. Create the log directory as needed. Document launchctl status and manual control commands; the initial CLI surface is limited to installation and removal.

## Risks / Trade-offs

- [A changed config can become invalid after installation, causing launchd to restart the monitor repeatedly] -> Validate before installation, use launchd's restart throttling, and document the per-user error log.
- [The optional packaging tool may be missing or fail to build for the current machine] -> Report a clear installation error before changing service state and document the `macos-service` extra.
- [The bundled executable can become stale after an application update] -> Rebuild it on service reinstall and document that reinstall step.
- [A forced kill or crash cannot run graceful publisher shutdown] -> Retain the existing MQTT Last Will and availability expiry as fallback behavior.
- [Uninstall leaves retained MQTT discovery in Home Assistant] -> Stop gracefully so availability becomes offline, and document that uninstall does not remove the retained discovery entity or broker topics.

## Migration Plan

There is no existing service registration to migrate. The user first verifies the monitor with the foreground command, installs the optional `macos-service` build extra, then installs the LaunchAgent with the same config file. Installation builds the named executable into per-user Application Support. To roll back, uninstall the LaunchAgent; this stops the process and publishes offline availability when possible. The config, log files, and retained MQTT discovery are not deleted.
