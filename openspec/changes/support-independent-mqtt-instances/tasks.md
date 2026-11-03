## 1. Independent source identities

- [x] 1.1 Load and validate optional MQTT instance IDs with legacy defaults.
- [x] 1.2 Wire client, discovery, device, and entity identities and map unknown payloads.
- [x] 1.3 Test isolation, identity stability, and invalid configuration.

## 2. Home Assistant aggregation

- [x] 2.1 Supply a combined sensor template and document source setup, ACLs, migration, and dashboard visibility.
- [x] 2.2 Render actual templates across all source-state combinations and test unknown payload mapping.

## 3. Verification

- [x] 3.1 Run targeted tests, lint, formatting, strict typing, package build, and OpenSpec validation.
- [x] 3.2 Report portable verification separately from pending live broker/Home Assistant checks.

## Verification results

- Portable checks: 75 focused tests and all 174 tests passed on macOS;
  Ruff lint/format, strict mypy, source/wheel build, and all five OpenSpec
  validations passed.
- The actual Jinja expressions cover all 25 two-source combinations of on,
  off, unknown, unavailable, and missing entities. MQTT identity isolation
  uses fake clients; no production broker or credentials were accessed.
- Documentation, fixtures, and examples use generic desktop/laptop settings.
- Pending deployment checks: two simultaneous live MQTT connections, Home
  Assistant discovery, template installation, state changes, disconnect/expiry,
  and recovery. No live macOS or Windows detector validation was performed.
