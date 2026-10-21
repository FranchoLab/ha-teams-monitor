# Tasks

## 1. Validate Windows log evidence

- [ ] 1.1 On the target Windows laptop, inspect the current user's Teams logs across idle, pre-join/ringing, joined, muted, and left states; identify candidate files and state markers without recording or sharing raw meeting data, and stop if joined/left cannot be distinguished reliably.
- [ ] 1.2 Establish record encoding/boundaries, state transition semantics, update cadence/freshness, and file rotation behavior; produce sanitized fixtures and a written parser contract, verifying each fixture maps to the observed state and contains no private meeting details.

## 2. Implement the log-backed detector

- [ ] 2.1 Replace the WebSocket source with a bounded read-only log reader rooted in the current user's `%LOCALAPPDATA%`; verify missing/inaccessible paths, appends, truncation, rotation, and restart behavior with fake filesystem tests.
- [ ] 2.2 Parse only the validated markers from the parser contract and map joined, not joined, stale, malformed, and unsupported evidence to the existing observation model; verify with the sanitized Windows log fixtures and ensure no unknown input becomes not joined.
- [ ] 2.3 Remove the WebSocket dependency from `pyproject.toml` and `uv.lock` if no longer used, and preserve Windows CLI detector selection and cleanup; verify with `uv lock --check` and CLI tests.

## 3. Document and validate

- [ ] 3.1 Update README.md with the log directory, read-only standard-user requirements, validated Teams build/format constraints, and fail-safe behavior; verify it no longer instructs enabling the Third-Party API or claims unvalidated Windows support.
- [ ] 3.2 Run Windows detector, CLI, macOS detector, MQTT tests, repository Ruff lint/format, and strict mypy; verify the Windows log parser tests are portable and existing macOS/MQTT behavior is unchanged.
- [ ] 3.3 On a native Windows host under a standard user account, validate idle, pre-join, ringing, joined, muted, left, log rotation/restart, and stale/unavailable behavior; record Teams/Windows builds and sanitized results, and do not claim validated support unless the complete matrix passes.
