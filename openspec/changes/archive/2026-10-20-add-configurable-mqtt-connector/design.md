# Design

## Context

See proposal.md for motivation and spec.md for externally visible requirements. The application already exposes a detector port and a use case that validates observation age. The CLI is not yet a composition root for monitoring, and no MQTT dependency or Home Assistant publisher exists. The macOS detector has native evidence for one Teams build; Windows detection remains unvalidated, and Linux is a development/test platform rather than a supported live monitor.

## Goals / Non-Goals

**Goals:**
- Compose the available detector, observation use case, and MQTT publisher in the CLI.
- Make broker and monitor settings explicit, validated, and reproducible from a user-supplied INI `.conf` file.
- Publish an automatically discovered Home Assistant binary sensor while preserving freshness and uncertainty.
- Permit a dedicated, publish-only broker identity scoped to the configured discovery, state, and availability topics.

**Non-Goals:**
- Home Assistant API/REST/WebSocket access, an API token, a Supervisor add-on, or a native Home Assistant integration.
- Installing or managing an OS startup service.
- Claiming live Windows or Linux monitoring support, or expanding macOS detector support beyond its validated evidence.

## Decisions

### Configuration and startup

- Add `--config <path>` to the monitoring CLI. Require it when starting monitoring; keep `--help` and `--version` independent of a config file.
- Parse INI syntax with Python's standard-library `configparser`, with interpolation disabled so passwords containing `%` are handled literally. Validate required settings and numeric intervals before opening the broker connection.
- Keep `.conf` as the only supported file format in this change. Do not auto-load `.env`, environment variables, or a default per-user path; explicit selection avoids ambiguity between service and interactive launches.
- The config contains broker host/port, credentials, discovery/topic prefixes, and monitor polling/freshness intervals. Document a placeholder-only example. Never log configuration values or include credentials in exceptions.
- The optional `[sensor] name` setting controls the Home Assistant discovery display name and the default entity ID. Default it to `Teams meeting` when omitted, reject an explicitly empty value, and derive `default_entity_id` as `binary_sensor.teams_status_<sanitized-name>` using lowercase ASCII and underscores between words. Preserve the discovery unique ID and MQTT topics. Home Assistant only applies the default entity ID when first creating an entity with a unique ID, so changing the configured name does not rename an entity already in its registry.
- Users own file access controls: recommend a file readable only by the monitor's OS account. Support certificate-validated TLS where configured; never provide an option that disables certificate verification. Plaintext broker connections remain a deployment risk and must be called out in setup guidance.

### Ports and composition

- Add an application-owned publishing port for meeting observations and an application use case that coordinates observation, state publication, and availability lifecycle.
- Keep Paho MQTT, Home Assistant discovery payloads, configuration parsing, and OS selection in adapters/composition. The domain and existing detector port remain MQTT- and Home-Assistant-agnostic.
- Compose the macOS detector on supported macOS runs. Unsupported platforms and detector failures produce unknown/unavailable outcomes, never a fabricated not-joined state. Do not claim Windows support based on fakes or Linux CI.

### MQTT and Home Assistant behavior

- Use the established Paho MQTT client behind the publishing port. Publish retained Home Assistant MQTT discovery configuration, state, and availability messages at QoS 1 so broker or HA restarts can recover the current sensor definition and state.
- Use stable sensor identity and configurable discovery and topic prefixes. The broker account needs publish access only to this sensor's discovery configuration, state, and availability topics; it does not need subscriptions or Home Assistant API access.
- Map joined and not-joined observations to the sensor's configured on/off payloads. Map indeterminate observations and `DetectionError` to an explicit unknown state. Do not publish errors as off.
- Keep sensor state separate from process/broker availability. Publish online availability while monitoring; configure an offline Last Will and an availability expiry/heartbeat so a disconnected or stopped process cannot leave a stale joined value visible indefinitely. On graceful shutdown, publish offline availability.
- Retry temporary broker connection failures with bounded backoff. While disconnected, do not claim not joined; Home Assistant availability must become unavailable through the Last Will or expiry behavior.

### Secret and privacy handling

- The dedicated MQTT username/password live only in the user-provided config file and are never included in logs, exceptions, discovery metadata, fixtures, or checked-in examples.
- Publish only sensor state, static device metadata, and availability. Do not publish meeting titles, participant identities, content, OS paths, or raw detector errors.

## Risks / Trade-offs

- [A `.conf` file contains a broker password] -> Keep it outside source control, recommend user-only file permissions/ACLs, and redact values from all diagnostics.
- [Plaintext MQTT can expose credentials on the network] -> Support certificate-validated TLS and document TLS for any broker connection that crosses an untrusted network; never disable certificate validation.
- [Discovery/topic changes can orphan a Home Assistant entity] -> Keep identity stable, make prefixes explicit, and document retained discovery cleanup before changing identity.
- [The macOS detector may encounter unvalidated Teams builds] -> Preserve indeterminate state and never map missing or partial evidence to off.
- [A process can stop refreshing while a retained state remains] -> Use MQTT Last Will, availability expiry, and freshness-aware observation rather than relying on retained state alone.

## Migration Plan

There are no existing live publishers or persisted configuration formats to migrate. Deploy by creating a dedicated MQTT broker user and scoped ACL, writing a protected `.conf`, and starting the monitor with `--config`. Roll back by stopping the monitor and removing its retained discovery configuration and sensor topics; do not remove shared Home Assistant broker configuration.
