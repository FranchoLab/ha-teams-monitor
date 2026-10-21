# Proposal

## Why

When Teams detects a meeting start but misses the hangup, Home Assistant can
continue to show the retained `ON` state without enough runtime diagnostics to
identify whether the detector is still reporting joined or the state is not
being updated. The monitor should make these cases observable and bound how
long an unverified joined state can remain presented as current, without
mistaking a safety timeout for a confirmed call end.

## What Changes

- Add privacy-safe runtime diagnostics for observation transitions, detector
  uncertainty and failures, monitoring-loop delays, and MQTT publication
  failures. Do not log credentials, meeting details, or raw operating-system
  assertion output.
- Add a configurable maximum continuous joined-state duration. Once exceeded,
  publish `UNKNOWN` until detection positively establishes a new state; never
  synthesize `OFF` from elapsed time alone. Use an initial default of eight
  hours to limit impact on long legitimate meetings.
- Document the diagnostic workflow and the guard's behavior and configuration.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `macos-teams-detection`: add privacy-safe diagnostic expectations for
  detector outcomes and signal-read failures.
- `home-assistant-mqtt-sensor`: bound a persistent joined state with an
  indeterminate MQTT state, preserving the distinction between unknown and
  confirmed not joined; add privacy-safe monitoring and MQTT publish diagnostics.

## Impact

- Affected code: application monitoring, macOS Teams detection, MQTT publishing,
  monitor configuration, and CLI composition.
- Affected tests and documentation: monitoring and detector tests, MQTT state
  tests, configuration tests, and the README diagnostic guidance.
- No new dependencies or Home Assistant API access. The guard introduces a
  configurable runtime setting; its timeout must not produce an `OFF` state.
