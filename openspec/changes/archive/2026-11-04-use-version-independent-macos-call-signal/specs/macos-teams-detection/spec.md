# Spec Delta

## MODIFIED Requirements

### Requirement: Report actual Teams call participation
The detector SHALL report a joined state only when supported evidence indicates the user has joined a Teams call, and SHALL report a not-joined state when supported evidence establishes that the user is not in a call.

#### Scenario: Teams is idle or the user is preparing to join
- **WHEN** Teams is idle, displaying a pre-join screen, or ringing without the user joining, and either no Teams process is detected or a validated build's supported evidence establishes no joined call
- **THEN** the detector reports not joined

#### Scenario: User joins a Teams call
- **WHEN** the user joins a Teams call and the complete known joined-call assertion signature is present for the Teams process
- **THEN** the detector reports joined regardless of whether the installed build has been validated

#### Scenario: User is muted during a call
- **WHEN** the user remains in a joined Teams call while microphone or camera is muted
- **THEN** the detector continues to report joined while the complete known joined-call assertion signature remains present

#### Scenario: User leaves a Teams call
- **WHEN** supported evidence for a validated Teams build establishes that the user has left the call
- **THEN** the detector reports not joined

### Requirement: Preserve indeterminate detection outcomes
The detector SHALL represent unsupported, unavailable, stale, or inconclusive observations as indeterminate or as an explicit detection error, never as not joined. For an unvalidated Teams build, the complete known joined-call assertion signature MAY establish joined, but an absent or incomplete signature SHALL remain indeterminate.

#### Scenario: New Teams build retains the known joined-call signature
- **WHEN** the installed Teams build is not yet validated and the complete known joined-call assertion signature is present
- **THEN** the result is joined

#### Scenario: New Teams build has no known call signature
- **WHEN** the installed Teams build is not yet validated and the known joined-call assertion signature is absent or incomplete
- **THEN** the result is indeterminate with an unsupported-client or inconclusive reason and is not reported as not joined

#### Scenario: Signal is not validated as discriminating for the installed build
- **WHEN** the installed Teams build is not yet validated and its assertion signal is absent or incomplete
- **THEN** the result is indeterminate and is not reported as joined or not joined

#### Scenario: macOS observation fails
- **WHEN** the detector cannot read or interpret the required macOS observation
- **THEN** it returns an explicit detection error or indeterminate result and does not report not joined

#### Scenario: Evidence becomes stale during a call
- **WHEN** the last call observation exceeds the detector's validity interval
- **THEN** the result becomes indeterminate rather than retaining joined or changing to not joined
