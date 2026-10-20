# Design

## Context

See proposal.md for motivation. The repository currently has no observation model, detector port, runtime dependencies, or live monitoring composition. The domain and application layers must remain free of OS-specific imports; live detector feasibility must be validated natively on macOS.

## Goals / Non-Goals

**Goals:**
- Introduce an OS-neutral observation contract and an application-owned detector port.
- Isolate macOS Teams signal collection and state mapping in an adapter.
- Establish a repeatable native validation gate for supported Teams/macOS versions.

**Non-Goals:**
- Compose the detector into the CLI or publish status through MQTT/Home Assistant.
- Implement another platform or infer call state from calendar, microphone, process presence alone, or meeting UI content.

## Decisions

- **Represent certainty explicitly.** Define domain states for joined, not joined, and indeterminate, plus an explicit detection error boundary. Carry observation time and a non-sensitive reason where needed to diagnose unsupported or failed detection. This prevents an adapter failure from becoming a false not-in-call result; a boolean-only result was rejected for that reason.
- **Keep the port inward and the adapter narrow.** Put the detector protocol in the application layer, domain observation types in the domain layer, and macOS-specific collection/mapping in `adapters`. The composition root is not changed in this proposal. This follows the current architecture and keeps OS dependencies out of core modules.
- **Use Teams-specific macOS power-assertion evidence as the initial candidate.** Query evidence through a read-only macOS adapter, scoped to the supported Teams client identity. Do not use shell-output parsing as the production interface. A native feasibility check must prove the signal distinguishes pre-join/ringing from joined calls, remains present while muted, and clears after leaving, under standard-user permissions. If it fails any state, stop and revise the design rather than shipping a heuristic or silently substituting another signal.
- **Treat unsupported platform/client and old observations as indeterminate.** The adapter reports unsupported outside macOS or for an unvalidated Teams version. Bound freshness using the detector polling interval (an observation older than two polling intervals is stale); stale evidence cannot keep reporting joined or be converted to not joined.
- **Use public IOKit APIs through the standard library.** Read assertions grouped by PID with `IOPMCopyAssertionsByProcess` via `ctypes`, resolve the `MSTeams` process with `libproc`, and read its `CFBundleVersion` from the running app bundle. This avoids a runtime dependency and shell-output parsing. Recognize the complete validated assertion pair on any build so an update does not disable positive joined-call detection; only return not joined on a validated build with no assertions. For an unknown build without the complete pair, return indeterminate. The subprocess-based `pmset` parser remains a disposable diagnostic only.

## Risks / Trade-offs

- [A Teams update may change the meaning of a familiar assertion type or pair] -> Require the full known pair for best-effort positive detection on unvalidated builds, keep unknown-build absence indeterminate, and rerun the native state matrix after updates before treating negative results as supported.
- [macOS-only behavior cannot be proven in Linux CI] -> Keep fake-backed mapping tests portable and require a documented native macOS run with a real client and joined calls before release.
- [The IOKit binding or bundle-version lookup may differ from the diagnostic on macOS] -> Run the API-backed adapter on the tested native matrix and compare its process/version/assertion evidence before treating the connector as supported; keep OS imports in the adapter.
- [Polling introduces a window before changes become visible] -> Bound observation freshness and turn delayed or failed reads into indeterminate outcomes rather than retaining stale state.
- [Diagnostic output could expose meeting details] -> Retain only state, timestamp, and a bounded non-sensitive reason; do not persist raw assertion payloads or meeting content.

## Migration Plan

No persisted state or public runtime behavior exists to migrate. Add the model, port, and adapter behind tests; run the native feasibility and state-matrix checks before enabling or documenting a supported macOS client. Build updates retain best-effort joined detection only when the complete known assertion pair is present; until the updated build is validated, missing or partial evidence remains indeterminate.
