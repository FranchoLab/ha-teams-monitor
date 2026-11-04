# Tasks

## 1. Version-independent positive detection

- [x] 1.1 Update macOS detector classification so a missing Teams process remains not joined, the complete known assertion pair reports joined regardless of build, and an unvalidated build with absent or incomplete assertions stays indeterminate; verify with focused regression tests for known and unknown builds, absent and partial signals, and unknown versions.

## 2. Documentation and verification

- [x] 2.1 Update README detection guidance to explain the version-independent positive signature, conservative unknown-build fallback, and accepted false-positive trade-off; verify the documentation matches the spec and contains no claim that every build must be allowlisted for joined detection.
- [x] 2.2 On macOS, validate that the running monitor reports joined during a call when the complete signature is present on an unvalidated build; verify no meeting details are exposed in diagnostics.
- [x] 2.3 Run `mise exec -- openspec validate use-version-independent-macos-call-signal --strict`, `mise exec -- uv run --frozen ruff check .`, `mise exec -- uv run --frozen ruff format --check .`, `mise exec -- uv run --frozen mypy`, and `mise exec -- uv run --frozen pytest`; verify all commands pass.
