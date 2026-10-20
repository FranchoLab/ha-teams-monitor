# Home Assistant MQTT Sensor Specification

## Purpose

Provide a standalone, locally run bridge that publishes Teams meeting observations to Home Assistant through its MQTT integration, without granting the app direct Home Assistant API access.

## Requirements

### Requirement: Load standalone monitor configuration explicitly
The monitor SHALL load its MQTT and publishing configuration from the file supplied by the user with an explicit command-line option, and SHALL report invalid or unreadable configuration without attempting to publish.

#### Scenario: User supplies a valid configuration file
- **WHEN** the user starts monitoring with a readable, valid configuration file
- **THEN** the monitor uses those settings to connect to the configured MQTT broker

#### Scenario: Configuration is missing or invalid
- **WHEN** the supplied configuration file cannot be read or lacks required values
- **THEN** the monitor reports a configuration error and does not connect or publish a sensor state

#### Scenario: Configuration contains credentials
- **WHEN** the monitor reports startup or runtime errors
- **THEN** it does not include configured passwords or other credential values in logs or user-facing error messages

### Requirement: Publish a discoverable Home Assistant meeting sensor
The monitor SHALL publish MQTT discovery information and meeting state so Home Assistant can create a binary sensor without manual entity configuration.

#### Scenario: Home Assistant receives sensor discovery
- **WHEN** the monitor connects to the broker with valid configuration
- **THEN** it publishes discovery information identifying a Teams meeting binary sensor and its state and availability topics

#### Scenario: User configures the sensor display name
- **WHEN** the configuration file supplies a non-empty sensor name
- **THEN** Home Assistant discovery uses that value as the display name and derives `default_entity_id` using the `binary_sensor.teams_status_` prefix and a sanitized name suffix, without changing its stable unique ID or MQTT topics

#### Scenario: Sensor display name is omitted
- **WHEN** the configuration file does not supply a sensor name
- **THEN** Home Assistant discovery uses `Teams meeting` as the display name and `binary_sensor.teams_status_teams_meeting` as the default entity ID

#### Scenario: Name is sanitized for the entity ID
- **WHEN** the configured sensor name contains spaces, punctuation, or accented characters
- **THEN** the entity ID suffix is lowercase ASCII with word separators replaced by underscores

#### Scenario: Meeting observation is joined or not joined
- **WHEN** a fresh observation confirms that the user is joined or not joined
- **THEN** the published sensor state represents the corresponding joined or not-joined value

### Requirement: Preserve uncertainty and sensor availability
The monitor SHALL keep indeterminate, stale, failed, or unavailable observations distinct from a confirmed not-joined state in Home Assistant.

#### Scenario: Meeting observation is indeterminate
- **WHEN** the detector returns an indeterminate observation
- **THEN** the sensor is unknown or unavailable and is not reported as not joined

#### Scenario: Detector fails or observations become stale
- **WHEN** detection fails or no fresh observation is published within the configured validity interval
- **THEN** Home Assistant does not continue to present the last joined state as current and does not present the user as not joined

#### Scenario: MQTT connection is lost
- **WHEN** the monitor loses its MQTT connection or stops refreshing its availability
- **THEN** Home Assistant marks the sensor unavailable rather than treating the last state as current

### Requirement: Use least-privilege MQTT credentials
The monitor SHALL authenticate to the MQTT broker with configured broker credentials and SHALL operate without a Home Assistant API token or elevated operating-system privileges.

#### Scenario: Dedicated broker account has topic-scoped permissions
- **WHEN** the broker account is limited to publishing the monitor's discovery, state, and availability topics
- **THEN** the monitor can publish its sensor without requiring broader broker permissions

#### Scenario: No Home Assistant API token is configured
- **WHEN** the user configures MQTT broker access but no Home Assistant API token
- **THEN** the monitor can publish the Home Assistant MQTT sensor
