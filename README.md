# Teams status for Home Assistant

Python foundation for detecting an actually joined Teams meeting or call locally
on macOS and Windows and publishing a binary sensor through MQTT.

**Foundation only:** there is no live detection, MQTT publishing, or startup
agent yet. Windows detection is an unresolved feasibility gate. Nothing in this
repository currently requires Microsoft tenant consent, a Home Assistant token,
or production broker credentials.

## Development in VS Code

Install Docker (or a compatible Dev Containers engine), VS Code, and the
Dev Containers extension. Open this folder and select **Dev Containers: Reopen
in Container**. Initial setup restores Python and OpenSpec dependencies from
their committed locks; it does not initialize OpenSpec again.

The container provides Python 3.12, uv 0.13.1, and Node 24.22.0 LTS.
Its Python environment lives outside the workspace. A named volume isolates
Linux Node dependencies from a native host installation.

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

Calling `ha-teams-status` without options deliberately exits with an error because
monitoring is not implemented. It never reports a fake Off state.

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
  adapters/       # Future macOS, Windows, MQTT/Home Assistant connectors
  __main__.py     # CLI and future composition root
tests/            # CLI smoke tests and import-boundary checks
openspec/         # Requirements and proposed changes
```

The domain depends on no other project layer. The application depends only on
the domain and its own modules. Adapters depend inward on ports and domain types.
Only the composition root chooses concrete connectors. Core code must not import
OS-specific libraries, MQTT clients, or Home Assistant payload formats.

The domain now defines OS-neutral meeting observations, and the application owns
the `MeetingDetector` port and observation use case. The CLI does not yet compose
the detector, and MQTT/Home Assistant publishing remains separate work.

The macOS Teams detector reads public IOKit power assertions. Its native matrix
was recorded on Teams build `26276.505.5234.9924` and macOS `27.0.1 (26A434)`:
idle, pre-join, ringing, and after leaving produced no Teams-owned assertions;
joined and muted calls produced `NoDisplaySleepAssertion` and
`NoIdleSleepAssertion`. The run used a non-root account (UID 501).

To repeat the API-backed check after a Teams or macOS update, run
`python3 scripts/macos_teams_api_diagnostic.py` as a standard user, without
`sudo` or Full Disk Access, in each of these states: idle, pre-join, ringing,
joined, muted, and after leaving. Record the exact build and assertion output.
The diagnostic prints only the Teams build and assertion type names. A complete
known assertion pair enables best-effort joined detection on a newer build; an
unknown build without the pair remains indeterminate until its matrix is
validated.

Future adapters:

- **Windows:** establish an accurate standard-user mechanism for current Teams.
  Do not assume classic Teams logs remain valid.
- **MQTT:** encode discovery, state, availability, expiry, and reconnect behavior;
  never depend on OS detector internals.

No calendar, Busy status, microphone-only signal, or running process is a
substitute for a proven joined-call signal. Detection failures must remain
distinct from Not in call. Monitoring will require heartbeat expiry in addition
to MQTT Last Will to avoid stale states after sleep or a hung detector.

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
