# Project guidance

- Read `README.md` and `openspec/config.yaml` before changing architecture.
- Use the pinned OpenSpec workflow for proposed behavior changes. Keep proposed
  functionality distinct from implemented, verified capabilities.
- Python 3.12, uv, pytest, Ruff, strict mypy. Restore with `uv sync --frozen`
  and `npm ci`; update locks only intentionally.
- Hexagonal dependency direction: domain <- application <- adapters.
  The CLI composes dependencies. Keep OS APIs, MQTT libraries, and Home Assistant
  serialization out of the core; do not add a DI framework or plugin system.
- macOS and Windows need separately validated detection connectors. Linux is a
  development/test environment, not a supported live monitoring platform.
- Never equate errors, stale observations, or unsupported detection with Off.
  Never substitute calendar presence or microphone usage for actual joined calls.
- Use fixtures/fake ports for portable tests; report native/live checks separately.
  Do not claim Windows compatibility from tests run only inside Linux.
- Keep secrets and meeting details out of source, logs, fixtures, and specs.
  Do not add broad OS permissions or production broker access to bootstrap.
- Run `uv run --frozen ruff check .`, `uv run --frozen ruff format --check .`,
  `uv run --frozen mypy`, `uv run --frozen pytest`, `uv build --no-sources`,
  and `npm run spec:validate` for a foundation change.
