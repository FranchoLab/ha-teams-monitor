# Tasks

## 1. Configuration and CLI

- [x] 1.1 Add a validated INI `.conf` loader for broker settings and monitor intervals; verify tests cover missing/unreadable files, invalid values, literal password characters, and sanitized errors.
- [x] 1.2 Add the explicit `--config <path>` monitoring option while preserving `--help` and `--version`; verify CLI tests show monitoring fails before connecting when configuration is absent or invalid.
- [x] 1.3 Document a placeholder-only `.conf` example, file-permission guidance, and the exact startup command in README; verify the documented example parses and contains no usable credentials.
- [x] 1.4 Add optional `[sensor] name` configuration with the `Teams meeting` default; use it in Home Assistant discovery and verify custom/default names without changing the stable unique ID or topics.
- [x] 1.5 Derive Home Assistant `default_entity_id` from `[sensor] name` with the `teams_status` prefix; test normalization (including `Francho reunido`) and document that existing registry entities may need a one-time rename.

## 2. Application Publishing Flow

- [x] 2.1 Add an application-owned publisher port and monitoring use case; verify fake-port tests map joined/not-joined to distinct states and indeterminate, stale, or failed detection never publishes not-joined.

## 3. MQTT Adapter and Home Assistant Setup

- [x] 3.1 Add the MQTT client dependency and implement retained Home Assistant discovery and state publishing with stable identity and configured topics; verify adapter tests assert payloads, topics, QoS, and retained flags.
- [x] 3.2 Implement availability, Last Will, heartbeat/expiry, reconnect behavior, and certificate-validated TLS support; verify tests cover startup, graceful shutdown, broker loss, recovery, stale evidence, and credential redaction.
- [x] 3.3 Document Home Assistant MQTT prerequisites, dedicated broker user setup, exact topic-scoped publish ACLs, and the absence of any HA API token requirement in README; verify documented ACL topics match the adapter configuration and examples use placeholders only.

## 4. Composition and Verification

- [x] 4.1 Compose configuration, the supported detector, observation use case, and MQTT publisher in the CLI; verify integration tests use fake detector/broker ports and unsupported platforms or detector errors do not become Off.
- [x] 4.2 Run `uv run --frozen ruff check .`, `uv run --frozen ruff format --check .`, `uv run --frozen mypy`, `uv run --frozen pytest`, `uv build --no-sources`, and `npm run spec:validate`; report native macOS and live broker/Home Assistant checks separately from portable test results.
