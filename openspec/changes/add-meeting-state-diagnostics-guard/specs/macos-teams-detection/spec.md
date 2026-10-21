# Spec Delta

## ADDED Requirements

### Requirement: Emit privacy-safe detector diagnostics
The detector SHALL emit diagnostics for outcome changes and signal-read failures without exposing meeting details or credentials.

#### Scenario: Detector outcome changes
- **WHEN** a fresh observation changes between joined, not joined, or indeterminate
- **THEN** diagnostics identify the observation state, bounded reason when present, and observation time without logging meeting content, titles, or participant identities

#### Scenario: Signal read fails
- **WHEN** the detector cannot read the macOS signal
- **THEN** diagnostics record a sanitized failure category without raw operating-system output or meeting details
