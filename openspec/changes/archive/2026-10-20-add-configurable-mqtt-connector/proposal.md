# Proposal

## Why

The project can detect a joined Teams call on macOS, but it cannot yet run as a configured monitor or publish a Home Assistant sensor. A standalone MQTT connector provides a small, locally operated path to Home Assistant without requiring a Home Assistant API token.

## What Changes

- Add an explicit `--config <path>` option for an INI-style `.conf` file containing monitor and MQTT settings.
- Allow the Home Assistant sensor display name to be configured in the `.conf` file, derive its default entity ID from the name using the `teams_status` prefix, and retain defaults for existing configurations.
- Compose the available meeting detector with an MQTT publisher that supports Home Assistant MQTT discovery and binary sensor state, availability, and expiry.
- Authenticate to the broker with a dedicated MQTT account whose publish permissions are limited to this sensor's discovery, state, and availability topics.
- Document Home Assistant MQTT prerequisites, the dedicated broker account and topic-scoped permissions, and safe `.conf` setup without real credentials in the README.
- Keep credentials out of source control, logs, and diagnostic output; preserve indeterminate and failed detection as unavailable or unknown rather than reporting Off.
- Keep Home Assistant API access, add-on packaging, and a native Home Assistant integration out of scope.

## Capabilities

### New Capabilities
- `home-assistant-mqtt-sensor`: Configure a standalone monitor and publish its meeting state to Home Assistant through MQTT discovery.

### Modified Capabilities

## Impact

- CLI and composition root for required configuration-path parsing and runtime startup.
- New application-facing publisher contract and MQTT/Home Assistant adapter, isolated from domain logic.
- Python dependencies for INI configuration and MQTT transport; tests using fake detector and broker ports.
- Home Assistant MQTT broker setup and topic-scoped broker ACLs. Live MQTT and native detector checks remain separate from portable Linux tests.
