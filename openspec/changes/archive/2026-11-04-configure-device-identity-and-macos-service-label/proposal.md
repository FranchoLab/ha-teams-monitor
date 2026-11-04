# Proposal

## Why

Monitor instances currently use `instance_id` as their Home Assistant device identifier, so independent computers cannot contribute entities to one device without sharing identities that must remain unique for MQTT and discovery. The device name is fixed, and the macOS LaunchAgent uses a generic reverse-domain label that the user wants to replace.

## What Changes

- Add a configurable Home Assistant device identifier independent of `instance_id`, defaulting to the current instance ID so existing installations keep their current device identity.
- Add a configurable Home Assistant device display name, defaulting to the current `teams status` name.
- Change the macOS LaunchAgent label to `francholab.ha-teams-status` and safely migrate or remove the previous `com.ha-teams-status.monitor` registration and plist.
- Update configuration examples, service instructions, and focused tests.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `home-assistant-mqtt-sensor`: allow multiple independent MQTT instances to share a Home Assistant device identity and configure its display name while preserving defaults.
- `macos-login-agent`: use the new LaunchAgent label and handle installations created with the previous label.

## Impact

The MQTT configuration loader and Home Assistant discovery payload will gain device settings; the macOS LaunchAgent adapter, its tests, and documented install/status commands will use the new label. Existing configurations retain their current Home Assistant device identity and name. No new dependencies or Home Assistant API access are required.
