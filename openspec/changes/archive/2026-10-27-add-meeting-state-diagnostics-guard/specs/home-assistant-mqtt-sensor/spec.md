# Spec Delta

## ADDED Requirements

### Requirement: Emit privacy-safe monitor diagnostics
The monitor SHALL log meaningful observation and publishing failures without exposing credentials or meeting details.

#### Scenario: Observation outcome changes
- **WHEN** an observation changes state or becomes indeterminate
- **THEN** diagnostics identify the state, bounded reason when present, and observation time without logging meeting content, titles, or participant identities

#### Scenario: MQTT publishing fails
- **WHEN** the MQTT client rejects a state or availability publish
- **THEN** diagnostics identify the failure category and topic role without logging the payload, credentials, or raw sensitive error details

### Requirement: Bound continuous joined-state reporting
The monitor SHALL stop reporting a continuous joined state as current after its configured maximum duration and SHALL preserve the distinction between unknown and confirmed not joined.

#### Scenario: Joined-state duration exceeds its limit
- **WHEN** joined observations continue beyond the configured maximum duration since the last confirmed not-joined observation
- **THEN** the monitor publishes `UNKNOWN` instead of `ON` and does not publish `OFF` based only on elapsed time

#### Scenario: Detector reports uncertainty after the limit
- **WHEN** the joined-state duration limit has been reached and the detector remains joined or becomes indeterminate
- **THEN** the monitor keeps the sensor `UNKNOWN` until a confirmed not-joined observation is received

#### Scenario: Detector confirms the user is not joined
- **WHEN** the detector positively reports not joined
- **THEN** the monitor publishes `OFF` and resets the joined-state duration guard

#### Scenario: User has not configured a joined-state limit
- **WHEN** the monitor loads configuration without a maximum joined-state duration
- **THEN** it uses the documented default limit of eight hours
