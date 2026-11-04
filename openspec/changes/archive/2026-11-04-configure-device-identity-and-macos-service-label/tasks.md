# Tasks

## 1. Configurable Home Assistant device identity

- [x] 1.1 Add optional `[mqtt] device_identifier` and `[mqtt] device_name` settings with compatible defaults and validation; verify omitted, valid, and invalid values in `tests/test_configuration.py`.
- [x] 1.2 Publish the configured device identifier and name without changing per-instance MQTT/discovery/entity identities; cover independent and shared device cases in `tests/test_home_assistant_mqtt.py` and update README configuration examples with instructions for two sources sharing one device.

## 2. macOS LaunchAgent label migration

- [x] 2.1 Switch the LaunchAgent to `francholab.ha-teams-status` and safely unload/remove the legacy label and plist during install and uninstall; extend `tests/test_macos_login_agent.py` for new paths, migration ordering, absent legacy service, and explicit failures.
- [x] 2.2 Update README plist paths and `launchctl` commands; verify documented labels match the adapter and existing config, logs, and runtime paths remain unchanged.

## 3. Integrated validation

- [x] 3.1 Run `mise exec -- uv run --frozen pytest tests/test_configuration.py tests/test_home_assistant_mqtt.py tests/test_macos_login_agent.py` and `mise exec -- npm run spec:validate`; resolve any regressions in the touched behavior.
- [x] 3.2 On a controlled macOS user account, verify install, upgrade from the legacy label, status/restart using the new label, and uninstall; report native service verification separately from portable test results.
