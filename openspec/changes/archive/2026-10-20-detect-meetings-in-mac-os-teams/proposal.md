# Proposal

## Why

The project has no live detector, and macOS needs a reliable way to distinguish an actually joined Teams call from pre-join, ringing, or idle states. A validated macOS signal is the first platform-specific step toward monitoring without misreporting errors or uncertainty as Off.

## What Changes

- Add a macOS Teams detector that uses the validated Teams-specific assertion signature across build updates, while treating unknown builds without that signature as indeterminate.
- Represent unsupported, unavailable, or inconclusive detection separately from a known not-in-call result.
- Add portable tests with fakes and a native macOS validation procedure covering pre-join, ringing, joined, muted, and leaving states.
- Keep Windows detection, MQTT/Home Assistant publishing, startup-agent behavior, and production connectivity out of scope.

## Capabilities

### New Capabilities
- `macos-teams-detection`: Detect and report whether the current macOS user has actually joined a Microsoft Teams call, preserving uncertainty and errors as distinct outcomes.

### Modified Capabilities

## Impact

- Adds the first meeting observation domain/application contracts and a macOS adapter, following the existing inward-only dependency direction.
- Adds portable adapter tests and a native macOS validation gate; Linux CI alone cannot establish live detector compatibility.
- Uses only normal-user macOS access. No elevated permissions, Full Disk Access, calendar presence, microphone-only signal, or tenant/broker credentials are in scope.
- Leaves the CLI's live monitoring composition and MQTT/Home Assistant integration for separate changes.
