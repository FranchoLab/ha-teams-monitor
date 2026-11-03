## Context

The adapter hardcodes the MQTT client, discovery, device, and entity identities.
Changing only the topic prefix cannot isolate installations. Existing users
must retain their registered entity and discovery topic.

## Goals / Non-Goals

- Support independently configured monitors and one visible Home Assistant sensor.
- Preserve uncertainty, freshness, and the existing single-monitor identity.
- Do not add monitor subscriptions, broker aggregation, or change detection.

## Decisions

- Add `[mqtt] instance_id`, defaulting to `ha_teams_status`. Use it as the client
  and device ID, discovery node ID, and prefix of the entity unique ID.
  Accept 1-48 lowercase ASCII letters, digits, underscores, and hyphens, starting
  with a letter or digit. Reject invalid values without echoing them.
- Continue using the configured topic prefix for state and availability. Users
  must assign different prefixes as well as different instance IDs.
- Keep names and initial entity IDs name-derived, independent of instance ID.
  Document distinct source names and verify actual registered IDs before using
  the combining template.
- Publish a discovery value template mapping `UNKNOWN` to the MQTT binary
  sensor's `None` payload. Otherwise Home Assistant ignores `UNKNOWN` and can
  retain an earlier ON/OFF value, invalidating aggregation.
- Supply a state-based Home Assistant template: any available ON wins; OFF is
  valid only when both sources are OFF; all other combinations are unavailable.
  A powered-off computer therefore cannot imply confirmed absence of a call.
- Test actual Jinja expressions across the full two-source state matrix, with
  Jinja2 as a development-only dependency.

## Risks / Trade-offs

- Explicit instance IDs can still collide if copied unchanged. Document the
  uniqueness requirement and separate exact broker ACLs.
- Changing an existing instance ID creates a new entity/device; keep the
  original ID on the first computer to avoid orphaning retained discovery.
- The example requires manual Home Assistant installation and source entity ID
  adjustment; portable tests do not establish live broker/HA compatibility.

## Migration Plan

Keep the first monitor's legacy identity and topics. Assign the second monitor
a distinct identity, topics, and name. Update both executables, verify two source
entities, add the template, then expose only the combined entity on dashboards.
Do not delete retained discovery or rewrite local credentials automatically.
