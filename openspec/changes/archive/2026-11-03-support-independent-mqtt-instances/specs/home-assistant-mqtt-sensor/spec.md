## ADDED Requirements

### Requirement: Isolate independently configured monitor instances
The monitor SHALL accept an optional MQTT instance ID and use it for the MQTT
client ID, Home Assistant discovery node, device identifier, and entity unique ID
prefix. Omission SHALL preserve the existing `ha_teams_status` identity.
Instance IDs SHALL contain 1-48 lowercase ASCII letters, digits, underscores,
or hyphens and SHALL start with a letter or digit.

#### Scenario: Two independently configured computers publish concurrently
- **WHEN** monitors have different instance IDs and topic prefixes
- **THEN** their client IDs, discovery topics, device identifiers, entity unique IDs, state topics, and availability topics differ

#### Scenario: Existing configuration omits the instance ID
- **WHEN** the monitor loads a configuration without `mqtt.instance_id`
- **THEN** its MQTT and discovery identities remain unchanged

#### Scenario: Invalid instance identity is supplied
- **WHEN** an instance ID is empty, too long, or contains unsupported characters
- **THEN** configuration loading fails without exposing its value or connecting

### Requirement: Document a safe Home Assistant combined sensor
The project SHALL provide a Home Assistant template combining two independent
source entities without publishing competing updates to a shared state topic.

#### Scenario: At least one available source confirms a joined meeting
- **WHEN** either source entity is on
- **THEN** the combined sensor is available and on regardless of the other source

#### Scenario: Both sources confirm no joined meeting
- **WHEN** both source entities are off
- **THEN** the combined sensor is available and off

#### Scenario: No source confirms joined and information is incomplete
- **WHEN** neither source is on and either source is unknown, unavailable, or missing
- **THEN** the combined sensor is unavailable rather than off

## MODIFIED Requirements

### Requirement: Preserve uncertainty and sensor availability
The monitor SHALL keep indeterminate, stale, failed, or unavailable observations
distinct from a confirmed not-joined state in Home Assistant.

#### Scenario: Meeting observation is indeterminate
- **WHEN** the detector returns an indeterminate observation
- **THEN** discovery maps the published `UNKNOWN` payload to Home Assistant's unknown binary sensor state, replacing any earlier on or off state

#### Scenario: Detector fails or observations become stale
- **WHEN** detection fails or no fresh observation is published within the configured validity interval
- **THEN** Home Assistant does not continue to present the last joined state as current and does not present the user as not joined

#### Scenario: MQTT connection is lost
- **WHEN** the monitor loses its MQTT connection or stops refreshing its availability
- **THEN** Home Assistant marks the sensor unavailable rather than treating the last state as current
