# Spec Delta

## Purpose

Lets a macOS user install a least-privilege login agent that starts the Teams status monitor automatically and keeps it available during the user's login session.

## ADDED Requirements

### Requirement: Install and start a per-user login agent
The monitor SHALL provide a macOS login agent that starts monitoring when the current user logs in and restarts after an unexpected process exit.

#### Scenario: User installs the login agent
- **WHEN** the user installs the agent with a valid configuration and executable
- **THEN** the agent is registered in the current user's login session and starts monitoring immediately and at subsequent logins

#### Scenario: Agent exits unexpectedly
- **WHEN** the monitoring process exits unexpectedly while the agent remains installed
- **THEN** the operating system restarts the monitoring process

#### Scenario: Agent is installed for another operating system
- **WHEN** the user requests login-agent installation on an unsupported operating system
- **THEN** the command reports that this service is macOS-only and does not create or modify service files

### Requirement: Run the login agent with the user's privileges
The login agent SHALL run as the logged-in user and SHALL NOT require administrator privileges or elevated operating-system permissions.

#### Scenario: User installs without administrator privileges
- **WHEN** a standard macOS user installs the login agent
- **THEN** installation and monitoring run in that user's login session without requesting elevation

### Requirement: Preserve configuration and credential boundaries
The login agent SHALL launch the installed monitor with the selected configuration file and SHALL NOT copy credentials into its service definition.

#### Scenario: Agent is registered with a configuration path
- **WHEN** installation succeeds
- **THEN** the service definition contains absolute paths to the executable and configuration file and leaves the configuration file at its existing location

#### Scenario: Configuration contains broker credentials
- **WHEN** the login agent is installed
- **THEN** broker credentials remain only in the user-protected configuration file and are not embedded in the service definition

### Requirement: Present an identifiable macOS process
The login agent SHALL run a standalone executable named `ha-teams-status` instead of launching the Python interpreter directly, so the monitor process has a recognizable name in macOS process tools.

#### Scenario: User inspects the installed monitor process
- **WHEN** the login agent is running
- **THEN** the process is identified as `ha-teams-status` rather than `python`

#### Scenario: User reinstalls after updating the application
- **WHEN** the user reinstalls the login agent from an updated application environment
- **THEN** the installed executable is rebuilt and the LaunchAgent uses the refreshed executable

### Requirement: Stop and remove the login agent cleanly
The monitor SHALL support removing its login agent and SHALL gracefully stop monitoring when the operating system requests process termination.

#### Scenario: User uninstalls a running login agent
- **WHEN** the user uninstalls the login agent
- **THEN** the agent is unloaded, the monitoring process stops cleanly, and the service definition and generated executable are removed without deleting the configuration file

#### Scenario: Operating system terminates the monitor
- **WHEN** the operating system sends a normal termination signal to the monitoring process
- **THEN** the monitor stops its polling loop and invokes publisher shutdown before exiting
