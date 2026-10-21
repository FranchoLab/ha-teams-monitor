# Project guidance

## Change workflow

- Before architecture changes, read [README.md](README.md) for project context
  and [openspec/config.yaml](openspec/config.yaml) for proposal constraints.
- For behavior changes, use the pinned OpenSpec workflow. Distinguish proposed
  functionality from implemented, verified capabilities.
- Write short Conventional Commit messages: `type: description`, no scope or body.

## Tooling

- Use [mise.toml](mise.toml) as the version authority for Python, Node.js, and uv.
  Provision with `mise install`; run commands through `mise exec -- <command>`
  rather than global tools.
- Restore dependencies with `mise exec -- uv sync --frozen` and
  `mise exec -- npm ci`. Change locks and tool versions only intentionally.

## Architecture

- Follow hexagonal dependencies: domain <- application <- adapters.
  Compose dependencies in the CLI, without a DI framework or plugin system.
- Keep OS APIs, MQTT libraries, and Home Assistant serialization in adapters,
  outside the core.

## Detection and safety

- Validate macOS and Windows connectors separately. Linux supports development
  and tests only, not live monitoring.
- Preserve errors, stale observations, and unsupported detection as distinct
  from Off. Detect actual joined calls; calendar presence and microphone usage
  are not substitutes.
- Use fixtures and fake ports for portable tests. Report native/live checks
  separately; Linux tests do not establish Windows compatibility.
- Keep secrets and meeting details out of source, logs, fixtures, and specs.
  Bootstrap without broad OS permissions or production broker access.

## Foundation validation

For foundation changes, run all checks below. Use pytest, Ruff, and strict mypy.

```sh
mise exec -- uv run --frozen ruff check .
mise exec -- uv run --frozen ruff format --check .
mise exec -- uv run --frozen mypy
mise exec -- uv run --frozen pytest
mise exec -- uv build --no-sources
mise exec -- npm run spec:validate
```
