---
description: Check on fleet background workers across all providers
argument-hint: [task-id]
---

Run the status script from the `fleet-delegation` skill:

- With a task id in `$ARGUMENTS`:
  `bash ${CLAUDE_PLUGIN_ROOT}/skills/fleet-delegation/scripts/fleet-status.sh $ARGUMENTS`
- Otherwise:
  `bash ${CLAUDE_PLUGIN_ROOT}/skills/fleet-delegation/scripts/fleet-status.sh --all`

Summarize each worker's state for the user in plain language, including
provider, model, and any active provider cooldowns. Then act per the skill at
`${CLAUDE_PLUGIN_ROOT}/skills/fleet-delegation/SKILL.md`:

- DONE workers: run the acceptance protocol (git diff review, acceptance
  commands, verification-gate if available) before declaring anything
  complete, then record the outcome with ledger.py.
- RATE_LIMITED / AUTH_ERROR / FAILED / INCOMPLETE: follow the skill's failure
  handling — cascade to the next provider where appropriate, and ledger the
  outcome.
