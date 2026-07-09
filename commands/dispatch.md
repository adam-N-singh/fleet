---
description: Explicitly dispatch a coding task to a fleet worker (skips the should-I-delegate rubric; provider optional)
argument-hint: <task description> [on <provider>]
---

The user has explicitly chosen to delegate this task to the fleet, so skip the
delegation decision rubric — the user decided. Follow the `fleet-delegation`
skill at `${CLAUDE_PLUGIN_ROOT}/skills/fleet-delegation/SKILL.md` for
everything else (routing, brief writing, dispatch, supervision, verification,
ledger).

Task from the user: $ARGUMENTS

Steps:

1. If the user named a provider (e.g. "... on gemini"), use it. Otherwise run
   the skill's routing rubric (registry list + ledger summary + cost cascade)
   and state your choice in one line.
2. Turn the task plus current project context into a fully self-contained
   brief per `${CLAUDE_PLUGIN_ROOT}/skills/fleet-delegation/references/brief-template.md`,
   saved under `.fleet-runs/briefs/`. If the task is too vague for concrete
   acceptance criteria, ask the minimum clarifying question first.
3. Dispatch with
   `bash ${CLAUDE_PLUGIN_ROOT}/skills/fleet-delegation/scripts/fleet-dispatch.sh --provider <name> --brief <file>`.
4. Report the TASK_ID, then continue with other work, supervising per the skill.

If dispatch reports PROVIDER_UNAVAILABLE or BUSY, cascade to the next capable
provider and tell the user; absorb the task yourself only if none remain.
