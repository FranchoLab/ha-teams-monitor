# Proposal

## Why

The Windows Teams Third-Party API is disabled by company policy, so the existing connector approach cannot provide meeting state on this user's managed laptop. The user can read the current Teams log directory as a standard account; a log-based detector may provide a policy-compatible local source if its records contain reliable, testable joined and left signals.

## What Changes

- Replace the proposed local Third-Party WebSocket API integration with a read-only reader for the current user's New Teams log files.
- First identify and validate log evidence for joined, not joined, and left states; do not guess undocumented markers or interpret missing evidence as not joined.
- Preserve `UNKNOWN` for inaccessible logs, unrecognized or malformed records, stale observations, and any state the log format cannot establish reliably.
- Keep Windows CLI selection, portable parser tests, privacy protections, and separate native Windows validation.

## Capabilities

### New Capabilities

- `windows-teams-detection`: Detect actual Teams call participation on Windows using validated local Teams log evidence.

### Modified Capabilities

None. The existing observation and sensor contracts already distinguish joined, not joined, and indeterminate states.

## Impact

- Replace the current Windows WebSocket adapter with a log-reader adapter and remove the WebSocket-only dependency if no other code uses it.
- Read the current user's Teams logs under `%LOCALAPPDATA%\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\Logs`; no administrator permission, Third-Party API setting, API token, or remote service is in scope.
- Update portable tests and README setup guidance. The log directory's accessibility is known, but the message format and reliable state markers have not yet been validated.
- Do not report Windows live detection as supported until a real Windows state matrix validates the log evidence.
