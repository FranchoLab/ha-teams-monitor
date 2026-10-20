# Tasks

## 1. Validate macOS Signal

- [x] 1.1 Create a disposable native macOS diagnostic for the Teams-specific power-assertion candidate; verify it reads only the minimum assertion metadata needed and emits no meeting details.
- [x] 1.2 Run and record the native state matrix for each proposed supported Teams/macOS version: idle, pre-join, ringing, joined, muted, and leaving, using standard-user access; verify each state is distinguishable and revise this design before adapter implementation if any state fails.

	Native observations (2026-10-19; Teams 26276.505.5234.9924; macOS Version 27.0.1 (26A434); user `fjoven`, UID 501, non-root):
	Idle returned `No Teams-owned assertion entries found.`
	Pre-join returned `No Teams-owned assertion entries found.`
	Ringing returned `No Teams-owned assertion entries found.`
	In a meeting, the diagnostic returned `MSTeams: NoDisplaySleepAssertion` and `MSTeams: NoIdleSleepAssertion`.
	Muted while in a meeting, the diagnostic returned the same two assertions.
	After leaving, the diagnostic returned `No Teams-owned assertion entries found.`
	API-backed diagnostic in idle returned build `26276.505.5234.9924` and `MSTeams assertions: none`.
	API-backed diagnostic during an active meeting returned build `26276.505.5234.9924` and `MSTeams assertions: NoDisplaySleepAssertion, NoIdleSleepAssertion`, matching the joined/muted matrix.

## 2. Add OS-Neutral Contracts

- [x] 2.1 Add domain observation states, timestamp/freshness, and non-sensitive outcome details; verify unit tests cover joined, not joined, indeterminate, and stale observations.
- [x] 2.2 Add the application-owned detector port and observation use case; verify tests preserve detection errors and the architecture test rejects OS dependencies in core layers.

## 3. Implement macOS Adapter

- [x] 3.1 Implement the macOS IOKit signal source and Teams state mapping using only the native-validated signal; verify fake-backed tests cover idle/pre-join/ringing, joined, muted, leaving, unknown builds with and without the complete signature, read failures, and inconclusive evidence, and compare API-backed observations with the recorded native matrix.
- [x] 3.2 Verify adapter behavior outside macOS and on stale evidence is indeterminate, never not joined; run the adapter tests and confirm the result omits meeting titles, participant identities, and content.
- [x] 3.3 Document native validation steps and the exact supported Teams/macOS versions in README; verify the instructions can be followed on a native macOS user account without elevated access.

## 4. Verify Change

- [x] 4.1 Run `uv run --frozen ruff check .`, `uv run --frozen ruff format --check .`, `uv run --frozen mypy`, `uv run --frozen pytest`, `uv build --no-sources`, and `npm run spec:validate`; verify all checks pass and keep native detector evidence distinct from Linux CI results.
