# Changelog

This file tracks releases of the fleet plugin, which turns coding agents into supervisors of multi-provider AI coding worker fleets.

## [v0.7.0] - 2026-08-03

- Measure the supervisor's own token usage instead of assuming it
- State the savings valuation basis in the ledger output
- Report realized savings from researched rates instead of guesses
- Add demo section with a real recorded session in README
- Match release asset filename in README

## [v0.6.3] - 2026-07-29

- Surface existing configuration before acting on it
- Note failure-path verification and the v0.6.2 phantom-status fix in the live-verified callout

## [v0.6.2] - 2026-07-28

- Fix bare 401/429 responses in adapter patterns that misclassify failures as auth/rate errors
- Drop duplicate version from marketplace listing, making plugin.json the single source of truth
- Pin marketplace listing version to 0.6.1
- Improves classification of HTTP response codes for better error handling

## [v0.6.1] - 2026-07-28

- Note live-verified adapters including codex, copilot, claude, and opencode

## [v0.6.0] - 2026-07-28

- Initial public release of the fleet multi-provider AI coding worker supervisor