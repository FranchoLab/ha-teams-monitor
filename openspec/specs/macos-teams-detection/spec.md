# macOS Teams Detection Specification

## Purpose

Detect whether the current macOS user has actually joined a Microsoft Teams call. The capability reports uncertainty separately from a confirmed absence so downstream monitoring cannot turn detector failures into a false Off state.

## Requirements

### Requirement: Report actual Teams call participation
The detector SHALL report a joined state only when supported evidence indicates the user has joined a Teams call, and SHALL report a not-joined state when supported evidence establishes that the user is not in a call.

#### Scenario: Teams is idle or the user is preparing to join
- **WHEN** Teams is idle, displaying a pre-join screen, or ringing without the user joining
- **THEN** the detector reports not joined

#### Scenario: User joins a Teams call
- **WHEN** the user joins a Teams call and the detector has positive joined-call evidence
- **THEN** the detector reports joined

#### Scenario: User is muted during a call
- **WHEN** the user remains in a joined Teams call while microphone or camera is muted
- **THEN** the detector continues to report joined

#### Scenario: User leaves a Teams call
- **WHEN** supported evidence establishes that the user has left the call
- **THEN** the detector reports not joined

### Requirement: Preserve indeterminate detection outcomes
The detector SHALL represent unsupported, unavailable, stale, or inconclusive observations as indeterminate or as an explicit detection error, never as not joined.

#### Scenario: New Teams build retains the known joined-call signature
- **WHEN** the installed Teams build is not yet validated but the complete known joined-call assertion signature is present
- **THEN** the result is indeterminate with an unsupported-client or inconclusive reason; the signature alone is not sufficient to report joined

#### Scenario: New Teams build has no known call signature
- **WHEN** the installed Teams build is not yet validated and the known joined-call assertion signature is absent or incomplete
- **THEN** the result is indeterminate with an unsupported-client or inconclusive reason and is not reported as not joined

#### Scenario: Signal is not validated as discriminating for the installed build
- **WHEN** the signal has not been validated to distinguish an active call from idle, pre-join, or post-call states for the installed Teams build
- **THEN** the result is indeterminate and is not reported as joined or not joined

#### Scenario: macOS observation fails
- **WHEN** the detector cannot read or interpret the required macOS observation
- **THEN** it returns an explicit detection error or indeterminate result and does not report not joined

#### Scenario: Evidence becomes stale during a call
- **WHEN** the last call observation exceeds the detector's validity interval
- **THEN** the result becomes indeterminate rather than retaining joined or changing to not joined

### Requirement: Detect with least privilege and protect meeting privacy
The detector SHALL operate as the normal logged-in user without requiring elevated privileges or broad OS permissions, and SHALL not expose meeting titles, participant identities, or meeting content in its result.

#### Scenario: Detector runs with standard user access
- **WHEN** the detector is started by a standard macOS user
- **THEN** it performs supported detection without requiring administrator privileges or Full Disk Access

#### Scenario: Observation contains meeting details
- **WHEN** the underlying macOS or Teams observation includes meeting-specific content
- **THEN** the detector result excludes titles, participant identities, and meeting content

### Requirement: Emit privacy-safe detector diagnostics
The detector SHALL emit diagnostics for outcome changes and signal-read failures without exposing meeting details or credentials.

#### Scenario: Detector outcome changes
- **WHEN** a fresh observation changes between joined, not joined, or indeterminate
- **THEN** diagnostics identify the observation state, bounded reason when present, and observation time without logging meeting content, titles, or participant identities

#### Scenario: Signal read fails
- **WHEN** the detector cannot read the macOS signal
- **THEN** diagnostics record a sanitized failure category without raw operating-system output or meeting details
