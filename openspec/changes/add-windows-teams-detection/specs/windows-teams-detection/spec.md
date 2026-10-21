# Spec Delta

## Purpose

Detect whether the current Windows user has actually joined a Microsoft Teams call using validated evidence from the user's local Teams logs. The capability distinguishes confirmed call states from unavailable, ambiguous, unsupported, or stale log observations.

## ADDED Requirements

### Requirement: Read the current user's Teams logs without elevation
The Windows detector SHALL read the current user's local New Teams log directory using standard-user filesystem access and SHALL NOT require the Third-Party API, administrator privileges, or a remote service.

#### Scenario: Teams logs are readable
- **WHEN** the current user's Teams log directory is accessible
- **THEN** the detector reads supported log files from that directory without requiring elevation

#### Scenario: Teams logs are missing or inaccessible
- **WHEN** the log directory cannot be found or read
- **THEN** the detector reports an indeterminate or explicit detection error and not a not-joined state

### Requirement: Report only call states supported by validated log evidence
The Windows detector SHALL report joined or not joined only when a validated Teams log record establishes that state, and SHALL NOT infer participation from calendar, microphone, process, or window presence.

#### Scenario: Validated log evidence establishes a joined call
- **WHEN** a supported log record unambiguously indicates that the user joined a call
- **THEN** the detector reports joined

#### Scenario: Validated log evidence establishes no active call
- **WHEN** a supported log record unambiguously indicates that the user is not in a call
- **THEN** the detector reports not joined

#### Scenario: User remains in a call while muted
- **WHEN** supported log evidence continues to indicate an active call while microphone or camera state is off
- **THEN** the detector continues to report joined

#### Scenario: No validated state marker is present
- **WHEN** readable logs contain no recognized current call-state evidence
- **THEN** the detector reports indeterminate rather than not joined

### Requirement: Preserve uncertainty in log-based detection
The detector SHALL report indeterminate or an explicit detection error when log evidence is malformed, unsupported, stale, or insufficient to establish a current call state.

#### Scenario: Log format or marker is unknown
- **WHEN** a log entry cannot be safely interpreted using a validated format and state marker
- **THEN** the detector does not use that entry to report joined or not joined

#### Scenario: Log files rotate while monitoring
- **WHEN** Teams creates, renames, truncates, or rotates log files
- **THEN** the detector resumes reading supported current logs without treating a file transition as a not-joined state

#### Scenario: Evidence is stale
- **WHEN** the detector cannot establish that its last recognized state remains current within the observation validity interval
- **THEN** the result becomes indeterminate rather than retaining joined or changing to not joined

#### Scenario: User leaves a call
- **WHEN** a validated log record establishes that the user has left the call
- **THEN** the detector reports not joined

### Requirement: Protect privacy in log processing
The Windows detector SHALL expose only meeting state, observation time, and a bounded non-sensitive reason, and SHALL NOT retain or log meeting content read from Teams logs.

#### Scenario: Logs contain meeting details
- **WHEN** a log record includes meeting titles, participant identities, message content, or other meeting details
- **THEN** the detector discards those details and retains only the minimum validated state evidence

### Requirement: Select the Windows detector on Windows
The monitor SHALL compose the Windows Teams log detector when run on Windows and SHALL preserve explicit unsupported-platform behavior on platforms without a live detector.

#### Scenario: Monitor starts on Windows
- **WHEN** the monitor starts on Windows
- **THEN** monitoring uses the Windows Teams log detector

#### Scenario: Monitor starts on an unsupported platform
- **WHEN** the monitor starts on a platform without a supported live detector
- **THEN** detection remains explicitly unsupported or indeterminate and is not reported as not joined
