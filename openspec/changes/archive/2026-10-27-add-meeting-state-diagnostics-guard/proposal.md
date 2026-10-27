# Proposal

## Why

When an unvalidated Teams build reports the known power-assertion signature,
the detector can classify the user as joined even when the evidence has not
been verified to distinguish an active call from other states. This can leave
Home Assistant showing `ON`; diagnostics and a duration guard do not prevent
this immediate false positive, and no stable, documented local macOS call-state
API was found as a version-independent replacement.

## What Changes

- Add privacy-safe runtime diagnostics for observation transitions, detector
  uncertainty and failures, monitoring-loop delays, and MQTT publication
  failures. Do not log credentials, meeting details, or raw operating-system
  assertion output.
- Report `JOINED` only when the Teams build and its joined-call evidence have
  been validated as discriminating. Treat unsupported builds or ambiguous
  evidence as indeterminate, even when the complete assertion signature is
  present.
- Add a configurable maximum continuous joined-state duration. Once exceeded,
  publish `UNKNOWN` until detection positively establishes a new state; never
  synthesize `OFF` from elapsed time alone. Use an initial default of eight
  hours to limit impact on long legitimate meetings.
- Document the diagnostic workflow, the guard, and the limitations for
  unsupported Teams builds. Do not integrate the local third-party device
  socket as a call-state source because its state contract is not officially
  documented and community documentation reports that the socket is being
  removed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `macos-teams-detection`: add privacy-safe diagnostic expectations for
  detector outcomes and signal-read failures, and require validated,
  discriminating evidence before reporting joined.
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
