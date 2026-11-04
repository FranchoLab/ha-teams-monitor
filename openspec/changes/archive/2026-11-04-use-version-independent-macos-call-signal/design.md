# Design

## Context

See `proposal.md` for the motivation and `specs/macos-teams-detection/spec.md` for the behavior contract. The macOS detector currently rejects an unvalidated build before checking whether the complete known assertion signature is present. The assertion source already scopes observations to the Teams process, and the build allowlist is also used to interpret missing assertions as evidence of not being in a call.

## Goals / Non-Goals

**Goals:**
- Use the complete known assertion signature as positive evidence without requiring an exact build match.
- Preserve the allowlist's conservative role when interpreting absent signals.
- Keep unavailable, stale, and incomplete evidence distinct from a confirmed not-joined state.

**Non-Goals:**
- Discover a new call signal or change the native macOS assertion reader.
- Expand detection to calendar, microphone, window-title, or meeting-content signals.
- Change MQTT state mapping, configuration, permissions, or service behavior.

## Decisions

1. **Check the complete assertion signature before rejecting an unknown build.** After confirming that the Teams process exists, the detector reports joined when the complete known pair is present. This reuses the already observed signal and removes build number as a prerequisite for positive evidence. The alternative—continuing to gate positives on the exact build allowlist—would keep routine Teams updates from working without manual revalidation.
2. **Retain build validation for negative evidence.** If the Teams process exists but the complete pair is absent, an unvalidated build remains indeterminate. A validated build with no assertions may still be reported not joined; a validated build with a partial signal remains indeterminate. This avoids turning a new build's unknown signal behavior into a false `OFF`. The alternative—treating missing signals as not joined on every build—would assume that the signal is emitted consistently across versions.
3. **Keep the signal exact and process-scoped.** Positive evidence remains the complete `NoDisplaySleepAssertion` and `NoIdleSleepAssertion` pair read for the Teams process. Unrelated assertion types do not satisfy the signature.

## Risks / Trade-offs

- [A future Teams build may emit the complete pair while the user is not in a call] → This false-positive risk is accepted to avoid revalidating every build. Requiring the exact complete pair from the Teams process limits, but does not eliminate, the risk.
- [A new build may emit no pair after the user leaves a call] → The detector reports indeterminate rather than not joined until that build is validated, so the state may not return to `OFF` automatically on that build.

## Migration Plan

No configuration or data migration is required. Deploy the updated monitor and restart its existing service. Rolling back to the prior version restores the previous behavior, in which an unvalidated build reports indeterminate even when the complete pair is present.
