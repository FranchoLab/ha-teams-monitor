# Design

## Context

The macOS detector reads Teams power assertions on each poll. The current
classification can accept the joined assertion signature before rejecting an
unsupported Teams build, so an unvalidated build can be reported as joined.
`MonitorMeeting` publishes every observation, converts `DetectionError` to
indeterminate, and the MQTT adapter publishes retained state with Home
Assistant state expiry and availability. See `proposal.md` and the delta specs
for motivation and required behavior.

## Goals / Non-Goals

**Goals:**

- Distinguish detector outcomes, monitor delay, MQTT publish failure, and
  timeout-guard activation in runtime diagnostics.
- Bound a continuous joined state and preserve uncertainty rather than
  synthesizing a call end.
- Report joined only for a Teams build and signal mapping validated to
  discriminate an active call from non-call states.
- Keep logs free of credentials, meeting details, and raw OS output.

**Non-Goals:**

- Infer that a user left a call when the detector has not established that.
- Depend on an undocumented or deprecated local Teams API as a call-state
  source.
- Replace Home Assistant MQTT expiry or availability handling.

## Decisions

1. **Require validated build-specific joined evidence.** Check that the
   installed Teams build has a validated mapping for the joined-call signal
   before classifying its assertion signature. A complete signature from an
   unsupported or unvalidated build remains indeterminate; it does not become
   joined based on the signature alone. The user's diagnostics for build
   `26289.203.5259.2574` are useful evidence, but do not establish a stable
   contract for later Teams builds. This conservative fallback can make a new
   build report UNKNOWN during a real call until its evidence is validated; no
   version-independent official local call-state source was found.

   The local third-party device socket was considered. Microsoft documents
   pairing third-party devices to interact with Teams controls, but no public
   contract was found for external clients to observe joined/left call state.
   The community client documentation reports that Teams is removing the
   socket and describes a configuration workaround. Do not make this
   undocumented interface a detector dependency.

2. **Track joined duration in the application monitor using monotonic time.**
   Start timing on the first joined observation after confirmed not-joined;
   reset only on confirmed not-joined. Indeterminate observations do not reset
   the timer. A monotonic clock avoids system-time adjustments affecting the
   limit. Once the limit is reached, latch the output to indeterminate with a
   dedicated bounded reason such as `joined_duration_exceeded` until confirmed
   not-joined. This is safer than forcing OFF and avoids treating an unchanged
   power assertion as proof of an active call.

3. **Make `max_joined_duration_seconds` optional in configuration with an
   eight-hour default.** Existing configurations continue to load unchanged.
   The default bounds indefinitely retained joined reports while limiting
   impact on ordinary long meetings; installations can lower or raise it. A
   lower fixed default might classify a legitimate long meeting as uncertain
   sooner.

4. **Log transitions and failures at the layer that can explain them.**
   The monitor logs state/reason transitions and guard activation; the macOS
   detector logs sanitized signal-read failure categories; the MQTT adapter
   logs publish failures without payloads or credentials. Emit routine
   per-observation timing and state detail only at debug level to avoid noisy
   logs; warn when one monitoring iteration exceeds its configured poll
   interval. Configure the standard logger in the CLI composition root so
   foreground and LaunchAgent stderr capture can use the same diagnostics.

5. **Keep diagnostics bounded and privacy-safe.**
   Include observation time, state, bounded reason, elapsed duration, and safe
   failure category only. Do not log exception messages, raw assertion output,
   meeting titles, participant identities, MQTT payloads, or credentials.
   Alternatives that dump source output were rejected because they risk
   exposing meeting information and do not improve the state-level diagnosis.

## Risks / Trade-offs

- [A legitimate meeting exceeds the default limit] -> Publish UNKNOWN rather
  than OFF, document the setting, and allow users to tune the limit.
- [A legitimate call uses an unvalidated Teams build] -> Publish UNKNOWN
  rather than risk a false JOINED state; document that this requires signal
  validation and does not provide automatic compatibility for future builds.
- [A detector signal stays joined after hangup] -> Diagnostics show repeated
  joined evidence; the guard eventually bounds the ON state but cannot
  distinguish that signal from a genuinely long call before its limit.
- [Diagnostics are too noisy or contain sensitive data] -> Log transitions at
  normal verbosity, reserve per-cycle detail for debug, and test that logs
  exclude payloads, exception messages, and meeting details.
- [MQTT publication is asynchronous] -> Report local publish rejection or
  failure status without claiming broker receipt when the client cannot
  confirm delivery.

## Migration Plan

No migration is needed. The new setting is optional and existing configuration
files use the eight-hour default. Rollback consists of reverting the monitor
version; no retained topic or discovery schema migration is required.
