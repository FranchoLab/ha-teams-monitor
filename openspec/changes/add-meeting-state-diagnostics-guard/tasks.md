# Tasks

## 1. Bound continuous joined state

- [x] 1.1 Add optional `max_joined_duration_seconds` configuration with an
  eight-hour default and positive-value validation; verify omitted, valid, and
  invalid values in configuration tests.
- [x] 1.2 Add a monotonic-time joined-state guard and a bounded
  `joined_duration_exceeded` reason; verify the timeout publishes UNKNOWN,
  indeterminate samples do not reset it, and only confirmed NOT_JOINED resets
  it without synthesizing OFF.
- [x] 1.3 Document the setting, default, and UNKNOWN behavior in the README;
  verify the configuration example remains valid and existing configurations
  still load unchanged.

## 2. Add privacy-safe diagnostics

- [x] 2.1 Configure CLI logging and emit monitor state/reason transitions,
  detector failure categories, guard activation, and delayed-loop warnings;
  verify logs identify the failure path without exposing exception messages or
  meeting details.
- [x] 2.2 Log local MQTT publish rejections by safe failure category and topic
  role without including payloads or credentials; verify success and failure
  paths with fake-client logging tests.
- [x] 2.3 Document where foreground and LaunchAgent logs are written and how to
  use the sanitized macOS assertion diagnostic in joined and after-hangup
  states; verify the documented command and privacy constraints.

## 3. Verify integrated behavior

- [x] 3.1 Run targeted monitor, configuration, macOS detector, MQTT, and CLI
  tests with `mise exec -- uv run --frozen pytest
  tests/test_application_monitor.py tests/test_configuration.py
  tests/test_macos_teams.py tests/test_home_assistant_mqtt.py tests/test_cli.py`
  and run `mise exec -- npm run spec:validate`; resolve any failures.
- [ ] 3.2 On macOS as a standard user, run
  `mise exec -- uv run --frozen python scripts/macos_teams_api_diagnostic.py`
  while joined and after hangup; verify the sanitized reports distinguish the
  states or record that the signal remains unchanged without capturing meeting
  details or claiming native behavior from portable tests.
