# Design

## Context

See [proposal.md](./proposal.md) for motivation. MQTT discovery currently takes the MQTT instance ID as the MQTT client ID, discovery node, Home Assistant device identifier, and entity unique-ID prefix. The macOS adapter derives its plist path and `launchctl` target from one `LABEL` constant; installation and removal currently manage only that label.

## Goals / Non-Goals

**Goals:**
- Keep MQTT connection/discovery identity unique per monitor while allowing multiple entities to resolve to one Home Assistant device.
- Preserve current discovery identity and device name when new settings are omitted.
- Replace and clean up the old LaunchAgent label without affecting user configuration or logs.

**Non-Goals:**
- Automatically merge or delete pre-existing Home Assistant device/entity registry entries.
- Change state and availability topic ownership or combine multiple source states in the monitor.
- Rename the installed executable, runtime directory, or log directory.

## Decisions

- Add optional `device_identifier` and `device_name` fields to `MqttSettings`, loaded from `[mqtt]`. Default the identifier to the effective `instance_id` and the name to `teams status`. This keeps identity defaults stable and places settings next to other MQTT discovery configuration. Validate identifiers with the existing instance-ID character and length rules, and reject blank names. Separate `[device]` settings were considered but would add a new section without changing their MQTT-discovery scope.
- Use `device_identifier` only in Home Assistant discovery's `device.identifiers`; continue using `instance_id` for the MQTT client ID, discovery topic, and entity unique ID. Do not derive either MQTT topic from the device identifier. This preserves independent publishing and avoids discovery collisions while allowing Home Assistant's device registry to group the entities.
- Replace the single LaunchAgent label constant with the current label `francholab.ha-teams-status` and a legacy label `com.ha-teams-status.monitor`. Derive the current plist path and launchctl service target from the current label. During install and uninstall, check and unload the legacy launchctl service, then remove its plist; failures other than an absent service remain explicit errors. Uninstall also cleans the current label. This is preferred to leaving a compatibility alias, which could keep a duplicate monitor running.
- Keep the service's executable, runtime, log, and config paths unchanged. Only the LaunchAgent label and plist filename change, limiting migration to the service registration.
- Update README examples and launchctl commands with `[mqtt] device_identifier`, `[mqtt] device_name`, and the new label. Document that existing configurations retain their current device identity/name and that changing an explicit device identifier does not migrate Home Assistant registry records.

## Risks / Trade-offs

- [A changed or reused device identifier can associate unrelated entities with one Home Assistant device, or leave an old registry entry behind] → Keep the default equal to `instance_id`, document stable identifiers, and test that only the discovery device identifier is shared.
- [A failure while unloading or removing the old LaunchAgent can interrupt an upgrade] → Stage the new executable before migration, treat unexpected `launchctl` and filesystem errors as failures, and preserve the existing configuration and logs. Verify native install, upgrade, and uninstall behavior on macOS.
- [A Linux test run cannot establish `launchctl` behavior] → Use fake command runners for portable unit coverage and report live macOS verification separately.

## Migration Plan

1. Existing monitor configurations need no edits; their device identifier remains the current `instance_id` and their device name remains `teams status`.
2. To group sources, configure the same stable `device_identifier` and `device_name` on each computer while keeping each `instance_id` and topic prefix distinct.
3. On the first new macOS service install, stage the updated executable, unload any registered `com.ha-teams-status.monitor` service, remove its plist, and register `francholab.ha-teams-status`. Update documented status and restart commands to the new label.
4. Uninstall both the current and legacy registrations if present. Rollback consists of reinstalling the previous application version and its old LaunchAgent; the migration does not remove config or log files.
