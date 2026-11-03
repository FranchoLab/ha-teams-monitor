## Why

Two monitors currently share a fixed MQTT client ID and Home Assistant discovery
identity. Concurrent installations disconnect each other and overwrite the same
entity even when their state topics differ.

## What Changes

- Add an optional MQTT instance ID, preserving the existing single-installation identity.
- Isolate MQTT clients, discovery topics, entity unique IDs, and device IDs.
- Document separate source topics and a Home Assistant template combining them
  into one visible sensor without allowing an idle source to override a joined source.
- Map indeterminate MQTT observations to Home Assistant's unknown state.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `home-assistant-mqtt-sensor`: Independent source identities and safe combined-state guidance.

## Impact

Configuration, MQTT adapter, portable tests, and Home Assistant setup documentation.
No new runtime dependencies or broker subscriptions.
