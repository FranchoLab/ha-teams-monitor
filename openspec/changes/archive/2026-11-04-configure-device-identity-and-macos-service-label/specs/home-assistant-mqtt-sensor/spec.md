# Spec Delta

## MODIFIED Requirements

### Requirement: Isolate independently configured monitor instances
The monitor SHALL accept an optional MQTT instance ID and use it for the MQTT
client ID, Home Assistant discovery node, and entity unique ID prefix. The
optional `mqtt.device_identifier` SHALL identify the Home Assistant device and
default to the instance ID. Omission of the instance ID SHALL preserve the
existing `ha_teams_status` identity. Both identifiers SHALL contain 1-48
lowercase ASCII letters, digits, underscores, or hyphens and SHALL start with a
letter or digit.

#### Scenario: Two independently configured computers publish concurrently
- **WHEN** monitors have different instance IDs and topic prefixes and no explicit device identifiers
- **THEN** their client IDs, discovery topics, device identifiers, entity unique IDs, state topics, and availability topics differ

#### Scenario: Independent instances share a Home Assistant device
- **WHEN** monitors have different instance IDs and topic prefixes but the same explicitly configured device identifier
- **THEN** their client IDs, discovery topics, entity unique IDs, state topics, and availability topics differ while their discovery payloads use the same device identifier

#### Scenario: Device identifier is omitted
- **WHEN** the monitor loads a configuration without `mqtt.device_identifier`
- **THEN** it uses the configured instance ID as the Home Assistant device identifier

#### Scenario: Existing configuration omits the instance ID
- **WHEN** the monitor loads a configuration without `mqtt.instance_id`
- **THEN** its MQTT and discovery identities remain unchanged

#### Scenario: Invalid instance identity is supplied
- **WHEN** an instance ID is empty, too long, or contains unsupported characters
- **THEN** configuration loading fails without exposing its value or connecting

#### Scenario: Invalid device identifier is supplied
- **WHEN** a device identifier is empty, too long, or contains unsupported characters
- **THEN** configuration loading fails without exposing its value or connecting

## ADDED Requirements

### Requirement: Configure the Home Assistant device display name
The monitor SHALL accept an optional non-empty MQTT device name and publish it as the Home Assistant discovery device name without changing the sensor name.

#### Scenario: User configures a device name
- **WHEN** the configuration supplies a non-empty `mqtt.device_name`
- **THEN** Home Assistant discovery uses it as the device name while retaining the configured sensor name as the entity name

#### Scenario: Device name is omitted
- **WHEN** the configuration does not supply `mqtt.device_name`
- **THEN** Home Assistant discovery uses the existing device name `teams status`

#### Scenario: Device name is empty
- **WHEN** the configuration supplies an empty `mqtt.device_name`
- **THEN** configuration loading fails without connecting or publishing
