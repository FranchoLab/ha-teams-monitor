# Teams status for Home Assistant

Standalone monitor for publishing a Teams meeting binary sensor to Home
Assistant over MQTT. The monitor, configuration loader, and MQTT connector are
implemented. Live detection has been validated for the macOS Teams build and
state matrix documented below. A Windows connector for the New Teams
Third-Party API is implemented but has not yet been verified on a native
Windows host; do not treat Windows live detection as validated support until
its native state matrix passes. Linux is for development and portable tests
rather than live monitoring.

A per-user macOS login agent is available for automatic startup; it is
optional. Microsoft tenant consent, a Home Assistant API token, and production
broker credentials are not included or required.

## Development in VS Code

Install Docker (or a compatible Dev Containers engine), VS Code, and the
Dev Containers extension. Open this folder and select **Dev Containers: Reopen
in Container**. Initial setup restores Python and OpenSpec dependencies from
their committed locks; it does not initialize OpenSpec again.

The container provides Python 3.12, uv 0.13.1, and Node 24.22.0 LTS.
Its Python environment lives outside the workspace. A named volume isolates
Linux Node dependencies from a native host installation.

Python files are formatted by Ruff on save through the workspace settings.
The container installs the Ruff VS Code extension automatically; when working
natively, install the Ruff extension (`charliermarsh.ruff`) in VS Code.

The container runs Linux. Develop the core, test fixtures, and MQTT connector
there; run live Teams detectors and login agents **natively on macOS/Windows**.
There is no host-access bridge and no Docker socket mount. Rebuild the container
after changing its tooling versions.

## Native setup

Install uv 0.13.1 and Node 24.22.0 LTS using trusted platform installers or
mise. From the project root, these commands work in macOS shells and Windows
PowerShell:

```text
uv sync --frozen
uv run --frozen pre-commit install
npm ci --no-audit --no-fund
uv run --frozen ha-teams-status --help
uv run --frozen ha-teams-status --version
```

uv obtains Python 3.12 if it is not already available. No virtual-environment
activation is necessary. Native environments use `.venv`; do not reuse that
environment from a Linux container. Node/OpenSpec are development tools only.
On Windows, if PowerShell blocks `npm.ps1`, use `npm.cmd` rather than weakening
your execution policy.

Create a local `monitor.conf` and replace the placeholders with the settings for
your MQTT broker:

```ini
[mqtt]
host = mqtt.example.invalid
port = 8883
username = YOUR_MQTT_USERNAME
password = REPLACE_WITH_MQTT_PASSWORD
discovery_prefix = homeassistant
topic_prefix = ha_teams_status/teams
tls = true

[monitor]
poll_interval_seconds = 5
observation_max_age_seconds = 15
heartbeat_interval_seconds = 10
availability_expiry_seconds = 30
max_joined_duration_seconds = 28800

[sensor]
name = Teams meeting
```

The monitor limits a continuous joined state to eight hours by default. After
that limit it publishes `UNKNOWN`, not `OFF`, until detection confirms that the
call has ended. Set `max_joined_duration_seconds` under `[monitor]` to tune the
limit; it must be a positive integer.

The configured name also determines Home Assistant's initial entity ID. For
example, `name = Francho reunido` produces
`binary_sensor.teams_status_francho_reunido`. Home Assistant uses this default
when the entity is first created; changing the name later does not rename an
entity already in its entity registry, so rename that entity in Home Assistant
if needed.

Keep this file outside source control and readable only by the OS account that
runs the monitor. On macOS/Linux, use `chmod 600 monitor.conf`; on Windows,
restrict the file's Security permissions to that account. Start the monitor
with the explicit config path:

```text
uv run --frozen ha-teams-status --config ./monitor.conf
```

Monitoring requires a valid configuration. `--help` and `--version` remain
available without one. Detection failures and unsupported platforms are not
reported as Off.

The monitor writes state transitions and sanitized failure categories to
standard error; LaunchAgent runs capture these in
`~/Library/Logs/ha-teams-status/stderr.log`. For per-poll timing details when
running in the foreground, add `--debug`:

```text
uv run --frozen ha-teams-status --debug --config ./monitor.conf
```

Logs do not include credentials, meeting titles, participants, or raw assertion
output. For a suspected missed hangup, compare the sanitized macOS signal while
joined and after leaving:

```text
mise exec -- uv run --frozen python scripts/macos_teams_api_diagnostic.py
```

It reports only the Teams build and assertion type names; do not collect or
share raw system assertion output, which may contain meeting details.

### Windows Teams detection (not yet natively validated)

The Windows connector targets the New Microsoft Teams client and its local
Third-Party API. Run the monitor as the same standard Windows user who runs
Teams, and enable the **Third-Party API** in Teams using the
[Microsoft setup guidance](https://support.microsoft.com/en-us/office/connect-to-third-party-devices-in-microsoft-teams-aabca9f2-47bb-407f-9f9b-81a104a883d6).
If Teams asks to authorize the monitor, approve it in Teams. The monitor
connects to the local WebSocket API; it does not use a cloud service or require
an API token in `monitor.conf`.

The connector currently uses protocol version 2.0.0 and reads only the
`isInMeeting` value from local meeting updates. An unavailable API, pending
authorization, malformed update, or lost connection is reported as unknown or
unavailable, never as not in a call.

This implementation has only portable fake-backed tests so far. No native
Windows state matrix has been run; Windows compatibility is therefore
unverified. Before relying on it, verify authorization and pre-join, ringing,
joined, muted, left, disconnect, and recovery behavior on Windows under a
standard user account. Record the Teams build and results before describing
Windows live detection as validated support.

### Optional macOS login agent

First verify the monitor in the foreground with the config you intend the
service to use:

```text
uv run --frozen ha-teams-status --config ./monitor.conf
```

Stop the foreground monitor with Ctrl-C. To install a per-user LaunchAgent that
starts immediately, starts at later logins, and restarts after unexpected
exits:

```text
uv sync --frozen --extra macos-service
uv run --frozen ha-teams-status service install --config ./monitor.conf
```

Install and uninstall run as the current standard user; do not use `sudo`. The
agent runs only in that user's logged-in macOS session. Its plist is
`~/Library/LaunchAgents/com.ha-teams-status.monitor.plist`. Installation builds
a standalone executable named `ha-teams-status` under
`~/Library/Application Support/ha-teams-status/runtime`; Activity Monitor and
process inspection can identify it by that name rather than as `python`. The
LaunchAgent invokes this executable with the absolute config path. Its plist
does not contain MQTT credentials. Keep the config at its existing location
and restrict access to the user account as described above.

Check or manually restart the registered job with:

```text
launchctl print gui/$(id -u)/com.ha-teams-status.monitor
launchctl kickstart -k gui/$(id -u)/com.ha-teams-status.monitor
```

The agent writes standard output and errors to
`~/Library/Logs/ha-teams-status/stdout.log` and
`~/Library/Logs/ha-teams-status/stderr.log`. To stop and remove the job:

```text
uv run --frozen ha-teams-status service uninstall
```

Uninstall removes the generated executable but keeps the config, logs, and
retained Home Assistant MQTT discovery. Reinstall the agent after updating the
application to rebuild the executable; its configuration path remains
absolute.

## Home Assistant MQTT setup

Enable Home Assistant's MQTT integration and connect it to the same broker
before starting the monitor. Create a dedicated broker user for this process;
it only needs permission to publish this sensor's discovery, state, and
availability messages. The monitor does not subscribe to broker topics and
does not require a Home Assistant API token.

For a Mosquitto ACL file, grant the example user only these write topics (the
discovery and topic prefixes must match `monitor.conf`):

```text
user YOUR_MQTT_USERNAME
topic write homeassistant/binary_sensor/ha_teams_status/meeting/config
topic write ha_teams_status/teams/state
topic write ha_teams_status/teams/availability
```

Do not grant read or wildcard access. If either prefix is changed, update the
ACL to the corresponding exact topics: `<discovery_prefix>/binary_sensor/ha_teams_status/meeting/config`,
`<topic_prefix>/state`, and `<topic_prefix>/availability`. Use TLS with
certificate validation when broker traffic crosses an untrusted network; do
not disable certificate verification.

## Checks

The installed Git hook runs Ruff lint and format checks, strict mypy, and the
full pytest suite before every commit.

```text
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy
uv run --frozen pytest
uv build --no-sources
npm run spec:validate
```

VS Code tasks expose the same checks. GitHub Actions checks the package on
Linux, macOS, and Windows. Automated CI does not prove real Teams detection;
that requires native tests with an actual client and joined calls.

To deliberately update dependencies, edit the relevant manifest and regenerate
the corresponding lock (`uv lock` or `npm install --package-lock-only`).
Do not replace frozen restores with implicit updates.

## Hexagonal architecture

```text
src/ha_teams_status/
  domain/         # Meeting concepts; no infrastructure imports
  application/    # Use cases and application-owned ports
  adapters/       # macOS/Windows detection, MQTT configuration and publisher
  __main__.py     # CLI and composition root
tests/            # CLI smoke tests and import-boundary checks
openspec/         # Requirements and proposed changes
```

The domain depends on no other project layer. The application depends only on
the domain and its own modules. Adapters depend inward on ports and domain types.
Only the composition root chooses concrete connectors. Core code must not import
OS-specific libraries, MQTT clients, or Home Assistant payload formats.

The domain defines OS-neutral meeting observations. The application owns the
detector and publisher ports; the CLI composes them with the macOS or Windows
detector and Home Assistant MQTT adapter. MQTT and Home Assistant payload
details stay in the adapter layer.

The macOS Teams detector reads public IOKit power assertions. Its native matrix
was recorded on Teams build `26276.505.5234.9924` and macOS `27.0.1 (26A434)`:
idle, pre-join, ringing, and after leaving produced no Teams-owned assertions;
joined and muted calls produced `NoDisplaySleepAssertion` and
`NoIdleSleepAssertion`. The run used a non-root account (UID 501).

The diagnostic matrix supplied for Teams build `26289.203.5259.2574` reported
no assertions while waiting to join, both assertions in a meeting, and no
assertions after leaving. The detector accepts these two builds based on their
observed state matrices; this does not establish compatibility for later
builds.

To repeat the check after a Teams or macOS update, run the
`mise exec -- uv run --frozen python scripts/macos_teams_api_diagnostic.py`
command as a standard user, without `sudo` or Full Disk Access, in each of
these states: idle, pre-join, ringing, joined, muted, and after leaving. Record
the exact build and assertion type names; the diagnostic prints only those
values. The detector reports joined only for builds whose signal has been
validated to distinguish an active call from idle, pre-join, and after-hangup
states. An unvalidated build reports UNKNOWN even when the complete assertion
pair is present. No version-independent, officially documented local macOS
call-state API was found, so a future Teams build may remain UNKNOWN during a
real call until its state matrix is validated.

Platform support and runtime behavior:

- **Windows:** the connector uses the New Teams local Third-Party API, but
  native validation is still outstanding. Do not assume classic Teams logs
  remain valid or claim live support from portable tests alone.
- **MQTT:** discovery, state, availability, retained Last Will, heartbeat, and
  reconnect handling are implemented; the adapter does not depend on detector
  internals.

No calendar, Busy status, microphone-only signal, or running process is a
substitute for a proven joined-call signal. Detection failures must remain
distinct from Not in call. Sensor state expiry complements the availability
heartbeat and MQTT Last Will so an old joined state is not shown as current.

## OpenSpec and Copilot

Use the pinned CLI, not a global `@latest` install:

```text
npm run openspec -- list
npm run openspec -- status --change bootstrap-foundation
npm run spec:validate
```

OpenSpec project context lives in `openspec/config.yaml`. Generated
`.github/prompts/` provide VS Code Copilot workflows such as `/opsx-propose`.
Generated `.github/skills/` provide the matching skills for Copilot, including
Copilot CLI. Run CLI from the project root and ask it to use the relevant
OpenSpec skill if a particular client does not expose the prompt command.
Reload VS Code or restart the CLI after adding generated integrations.

Root `AGENTS.md` contains shared project guidance. Keep OpenSpec-generated
workflows separate from these hand-maintained architectural rules.

For later features, propose and review the change before applying it. Start with
native detector feasibility; do not mark Windows support complete just because
the shared tests pass. The initial `bootstrap-foundation` change describes only
this scaffold and stays open while external validation is pending.

After intentionally changing the pinned OpenSpec version, run `npm ci` and
`npm run openspec -- update`, then review generated changes. Do not run
initialization or update automatically on every container startup.

## Secrets and scope

Do not commit tokens, meeting content, local runtime configuration, or real MQTT
credentials. No production connectivity is needed to use this foundation.
Future monitoring runs as a normal user; do not add elevated OS permissions,
Full Disk Access, or a privileged container to bypass policy.
