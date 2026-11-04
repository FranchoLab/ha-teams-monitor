# Proposal

## Why

Teams releases frequently change the exact build number, so an exact-version allowlist makes detection fall back to `UNKNOWN` after routine updates even when the known joined-call signal still works. The current build produced the complete assertion pair during a live call, but the detector rejected it solely because the build number was new.

## What Changes

- Treat the complete known Teams joined-call assertion pair as positive evidence regardless of the installed build number.
- Keep unknown or incomplete signals on unvalidated builds indeterminate rather than reporting not joined.
- Preserve `NOT_JOINED` for a missing Teams process and for validated builds with no Teams-owned assertions.
- Update detection requirements, tests, and operator documentation to state the version-independent policy and its false-positive trade-off.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `macos-teams-detection`: accept a complete known call signature on any detected Teams build while keeping incomplete evidence indeterminate.

## Impact

The macOS detector, its portable tests, the macOS detection specification, and the README's Teams-build validation guidance are affected. No new dependencies, permissions, or MQTT behavior are required.
