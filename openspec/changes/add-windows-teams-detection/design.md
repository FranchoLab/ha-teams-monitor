# Design

## Context

See proposal.md for motivation and the Windows detection spec for behavior. The CLI already selects a Windows detector and closes it during shutdown. The current committed WIP adapter instead connects to the local Third-Party WebSocket API, which is unavailable under the user's company policy. The user has verified that their standard account can list files in `%LOCALAPPDATA%\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\Logs`; the log schema and state markers remain unknown.

## Goals / Non-Goals

**Goals:**
- Replace the unavailable API source with read-only access to the current user's Teams logs.
- Validate the actual log format and call-state markers before implementing state interpretation.
- Preserve the existing observation model, CLI selection, sensor behavior, and least-privilege boundaries.
- Make parsing testable with sanitized fixtures and explicitly keep unsupported evidence indeterminate.

**Non-Goals:**
- Enable or circumvent the disabled Teams Third-Party API or company policy.
- Infer call state from process presence, window titles, microphone use, calendar, or generic Teams presence.
- Collect, retain, upload, or log raw Teams logs, meeting titles, participant information, or message content.

## Decisions

- **Use the user's local log directory as the only Windows evidence source.** Resolve the root from `LOCALAPPDATA` and the package-relative path `Packages/MSTeams_8wekyb3d8bbwe/LocalCache/Microsoft/MSTeams/Logs`. Read files with the current user's permissions only. Missing or inaccessible files are unavailable evidence, not confirmation of no call.
- **Make log-format discovery a prerequisite, not an assumed implementation detail.** The supplied PowerShell check establishes directory/file access but does not show file contents or prove any call-state signature. On a Windows host, compare sanitized log structure and state markers across idle, pre-join/ringing, joined, muted, and left cases. Identify the actual files, encoding, record boundaries, event types, and any state-transition/liveness behavior. If no unambiguous joined and ended evidence can be validated, stop: do not ship a heuristic detector.
- **Parse only validated state fields.** The eventual adapter may recognize only documented-by-evidence record patterns and must extract the minimum required state and timestamp. Unknown versions, malformed records, and records containing no validated state marker cannot produce joined or not joined. Use sanitized, minimal fixtures; never check in raw user logs or private meeting details.
- **Handle append, rotation, and restart without treating them as state transitions.** The reader must detect newly appended data and files created, renamed, truncated, or rotated. Deduplicate already-consumed records where necessary. File discovery/rotation must not itself imply not joined.
- **Define state freshness from observed log behavior.** During discovery, establish whether the log emits periodic state/liveness evidence or only transition records. Choose a conservative validity rule consistent with that evidence and the configured observation age. If freshness cannot be established after a quiet period or reader failure, publish indeterminate rather than keeping a possibly stale joined state or assuming not joined.
- **Remove WebSocket-specific runtime plumbing.** Replace the current WebSocket source and remove `websocket-client` from the dependency and lockfile if it is unused elsewhere. Keep Windows selection and detector shutdown in the CLI composition root; do not change domain or MQTT contracts.
- **Gate live support on Windows evidence.** Portable parser tests verify fixtures, invalid/unknown records, rotation, freshness, and privacy. A native Windows run must verify the full call-state matrix on the actual Teams build and standard-user account. Linux/macOS tests do not validate Windows log paths or schemas.

## Risks / Trade-offs

- [Teams logs may not contain reliable joined/left events or may change by release] → Discover and validate against real state transitions first; if evidence is insufficient, leave detection unsupported/unknown.
- [Logs may contain sensitive meeting or account data] → Inspect locally, never log or commit raw records, sanitize fixtures, and retain only the validated state and timestamp.
- [Log writes may be sparse, delayed, or split across files] → Establish cadence and transition semantics during the state matrix; when current state cannot be proven, use indeterminate.
- [Rotation, truncation, or restart can cause missed or replayed entries] → Test file lifecycle behavior and deduplicate records without interpreting file changes as call-state events.
- [The current Windows API implementation is already committed] → The next apply must replace its source, remove its dependency if unused, and update README claims; this artifact-only update does not itself change the code.
- [No representative Windows log samples are available in this environment] → Keep discovery as the first implementation task; do not invent signatures or mark Windows detection validated until native evidence is supplied.

## Migration Plan

No user configuration change is expected. In the next apply, first validate the log format and state semantics on Windows. If validation succeeds, replace the WebSocket adapter and dependency with the log reader, preserve CLI platform routing and the existing sensor contract, and update README setup guidance. Run portable tests using sanitized fixtures and project checks, then complete the native state matrix. If the log source cannot reliably distinguish joined, left, and unknown, stop and retain fail-safe unknown behavior rather than deploying a guessed parser.
