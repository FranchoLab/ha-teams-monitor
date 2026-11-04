# Spec Delta

## ADDED Requirements

### Requirement: Use and migrate the macOS login-agent label
The monitor SHALL register its macOS LaunchAgent as `francholab.ha-teams-status` and SHALL remove any prior registration under `com.ha-teams-status.monitor` when installing or uninstalling the service.

#### Scenario: User installs the login agent
- **WHEN** a user installs the macOS login agent
- **THEN** its LaunchAgent label and plist filename are `francholab.ha-teams-status`

#### Scenario: User upgrades an existing login agent
- **WHEN** the previous `com.ha-teams-status.monitor` agent is installed and the user installs the new version
- **THEN** the old agent is unloaded and its plist is removed before the new agent is registered, without deleting the user's configuration or logs

#### Scenario: User uninstalls an existing login agent
- **WHEN** the user uninstalls the service while the previous `com.ha-teams-status.monitor` agent is installed
- **THEN** the previous agent is unloaded and its plist is removed along with the current service, without deleting the user's configuration or logs
