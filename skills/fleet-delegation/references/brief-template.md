# Dispatch Brief Template

Every brief must be fully self-contained. The worker has zero access to your
conversation, your plan, or your reasoning — the brief is the only context transfer.
Write it the way you would hand work to a competent contractor who has never seen
this conversation: everything needed, nothing assumed.

Copy the structure below into `.codex-runs/briefs/<slug>.md` and fill every section.
If you cannot fill a section, that is a signal the task is not ready to delegate.

---

# Task: <one-line title>

## Objective

What must exist when this task is done, in 2–4 sentences. State the outcome, not
the activity.

## Context

- **Stack:** language, framework, package manager, runtime version if relevant.
- **Entry points:** where in the codebase this work lives. Exact relative paths.
- **Relevant files:** every file the worker needs to read or modify, with a phrase
  on why each matters. Exact paths — never "the utils file".
- **Conventions:** naming, error-handling, testing patterns to match. Point at an
  existing file to imitate where possible ("follow the pattern in `src/api/users.ts`").

## Requirements

Numbered, specific, testable. Each requirement should be checkable by reading the
diff or running a command.

1. ...
2. ...

## Constraints

- Do NOT modify: <exact paths of files/directories that are off-limits>.
- Do NOT add new dependencies unless listed here: <allowed deps or "none">.
- Do NOT commit. Leave all changes uncommitted in the working tree.
- Match existing code style; no drive-by refactors outside the listed files.

## Acceptance criteria

Exact commands that must pass, and any manual checks:

```bash
<test command>
<build command>
<lint command>
```

## Out of scope

Explicitly list adjacent work the worker must NOT do, especially anything you are
handling yourself in parallel (this prevents file collisions).

## Final report

End your final message with: a list of every file you created or modified, the
output of the acceptance commands you ran, and anything you were unable to
complete or had to assume.
