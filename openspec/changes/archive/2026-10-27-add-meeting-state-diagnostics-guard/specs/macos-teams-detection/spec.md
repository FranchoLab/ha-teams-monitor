# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Emit privacy-safe detector diagnostics
The detector SHALL emit diagnostics for outcome changes and signal-read failures without exposing meeting details or credentials.

#### Scenario: Detector outcome changes
- **WHEN** a fresh observation changes between joined, not joined, or indeterminate
- **THEN** diagnostics identify the observation state, bounded reason when present, and observation time without logging meeting content, titles, or participant identities

#### Scenario: Signal read fails
- **WHEN** the detector cannot read the macOS signal
- **THEN** diagnostics record a sanitized failure category without raw operating-system output or meeting details
