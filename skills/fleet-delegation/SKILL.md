---
name: fleet-delegation
description: Supervise a fleet of AI coding workers from many providers (OpenAI Codex, Google Antigravity CLI, xAI Grok Build, Cursor CLI, GitHub Copilot CLI, Qwen Code, Factory Droid, Amp, Claude Code headless, plus 75+ providers via OpenCode including DeepSeek, Kimi, GLM, and local models on LM Studio or Ollama) as background subagents. Decide which coding tasks to delegate, pick the best provider and model via the registry, cost cascade, and outcome ledger, dispatch workers in parallel, monitor progress, verify results before accepting them, and cascade to the next provider or do the work yourself when one is rate-limited or unavailable. Works from any Agent Skills-compatible supervisor. Use proactively in any multi-task build whenever an independent, well-specified task could run in parallel with your own work, not only when the user says "delegate" or names a provider or model. Also use when the user mentions background coding workers, multi-model orchestration, or running tasks on a cheaper model.
---

# Fleet Delegation

You are the supervisor: planner, architect, router, and reviewer. The fleet is a
set of AI coding workers on other providers that you dispatch well-specified
implementation work to, so it runs in the background while you do what you are
best suited for. Workers share **none** of your conversation context — every
dispatch carries a fully self-contained brief.

This skill is supervisor-agnostic: whichever agent is reading it (Claude Code,
Codex, Gemini CLI, or another Agent Skills-compatible tool) plays the
supervisor. **Self-dispatch caution:** if a registry provider uses the same CLI
and account you are running as, dispatching to it buys parallelism but spends
your own quota — the cost advantage of the fleet comes from the *other*
providers, so weight your routing accordingly.

All scripts live in this skill's `scripts/` directory; resolve them relative to
this SKILL.md file. `<scripts>` below means that directory. On Windows, run
them through Git Bash; if `python3` isn't on PATH, substitute `python` in the
commands below (the shell scripts already fall back on their own).

## Session start (once)

1. Read the fleet: `python3 <scripts>/registry.py list`
   This is your knowledge of the fleet — which providers the user has enabled,
   their access mode and cost, their strengths/weaknesses as *the user* recorded
   them, concurrency caps, and the routing preference order. If it errors with
   no registry found, offer to set the registry up (Claude Code: `/fleet-init`;
   any other supervisor: follow `references/providers-guide.md` and draft it
   interactively) and do all work yourself until then. Never dispatch to a
   provider that isn't enabled.
2. Read the track record: `python3 <scripts>/ledger.py summary`
   Observed outcomes per provider/model/task-type. This outranks both the
   registry's strengths notes and your own priors, because it reflects what
   actually happened in this user's projects.
   Also check pacing: `python3 <scripts>/ledger.py usage` — delegated volume
   per provider against any `soft_weekly_cap` in the registry. If the registry
   flags a provider REVIEW_DUE, tell the user its access terms may have
   changed and suggest refreshing that entry (Claude Code: `/fleet-init`;
   other supervisors: re-verify access/pricing and update the registry).
3. Confirm `.fleet-runs/` is in `.gitignore`; add it on first dispatch.

## Step 1 — Should this task be delegated at all?

Delegate ONLY when all four are true:

1. **Self-containable.** You can write a brief that fully specifies the task
   without conversation context. If the brief would take more than a few
   minutes to write, keep the task.
2. **Substantial.** Roughly 20+ minutes of focused implementation. Dispatch
   overhead (brief, polling, diff review, verification) makes small
   delegations cost more than they save.
3. **Objectively verifiable.** Tests, build, lint, or crisp acceptance
   criteria you can run.
4. **Independent.** Touches no files you are editing now and none listed in
   another in-flight brief.

**Where the savings actually are:** output tokens cost ~5x input tokens, so
delegation savings concentrate in **output-heavy** work — bulk implementation,
test generation, migrations, boilerplate. Planning-style tasks (large context
in, a short decision out) are input-heavy and output-light: cheap to do
yourself and rarely worth a dispatch round-trip even when they technically
pass the four criteria. Weight output volume when judging "substantial".

**Keep for yourself:** architecture and design decisions; planning; UI/UX
design (implementing a finalized design is delegable); anything ambiguous;
security-sensitive code (auth, payments, secrets, migrations) unless the user
explicitly directs otherwise; final integration; and — always — the review of
a worker's output. Never delegate reviewing worker A's output to worker B as a
substitute for your own verification.

**Tie-break: when in doubt, do it yourself.** If the user explicitly assigns a
task to the fleet or a named provider, skip this rubric — the user decided.

## Step 2 — Route: which provider and model?

First classify the task by **uncertainty, not apparent size** — uncertainty,
more than length, predicts which workers can survive it:

- **Clear:** the solution and finish line are already known (boilerplate,
  mechanical edits, tests against settled behavior). Any capable provider —
  route purely by cost.
- **Judgment-heavy:** tractable implementation with tradeoffs or failure
  modes to think through. Frontier-harness providers with a good ledger
  record; raise `--effort` where supported rather than jumping cost tiers.
- **Open-ended:** the problem or safe path must be discovered first. Do not
  delegate discovery — do the thinking yourself, then dispatch the settled
  plan as Clear/Judgment-heavy pieces.

Then apply these filters **in order**:

1. **Capability filter.** Eliminate providers that can't do the task:
   context window too small for the required files; `trust: restricted`
   providers for anything beyond small, low-blast-radius tasks; agentic
   multi-step work on providers whose ledger shows they can't sustain it.
2. **Cost cascade.** Among capable providers, prefer cheapest first using the
   registry's `routing.prefer_order` (typically: local free → subscription/
   free-tier flat → cheap API → expensive API). Flat-rate access is
   effectively free at the margin — burn it before per-token API spend.
3. **Availability and pacing.** Skip providers in cooldown or at their
   concurrency cap (the dispatch script enforces both and tells you). Also
   apply soft-cap pacing from `ledger.py usage`: a provider approaching its
   `soft_weekly_cap` (~70%+) gets deprioritized in the cascade; one over 100%
   is treated as a soft cooldown — route elsewhere unless no capable
   alternative exists. This deliberately preserves flat-rate quota for
   late-period tasks that genuinely need that provider, instead of burning it
   early and slamming into the hard limit.
4. **Track record.** Consult the ledger summary for this task type. A provider
   with repeated `absorbed`/`failed` outcomes on this task type gets skipped
   even if cheaper — failed delegations cost more than expensive successes.
   A cheap provider with a strong record beats a pricier default.

State your routing choice in one line to the user when you dispatch ("sending
the test suite to antigravity: free tier, large context, 5/5 on test tasks").
If the user named a provider, use it. Model override: pass `--model` only when
the user asked or the registry notes call for it; otherwise the provider's
default model applies. Never invent model names.

## Step 3 — Dispatch

1. Write the brief to `.fleet-runs/briefs/<slug>.md` per
   `references/brief-template.md` (read it the first time each session). The
   brief is the entire context transfer — objective, stack, exact paths,
   requirements, constraints, runnable acceptance commands, out-of-scope.
2. Dispatch:
   ```bash
   bash <scripts>/fleet-dispatch.sh --provider <name> --brief .fleet-runs/briefs/<slug>.md
   ```
   Optional: `--model`, `--effort` (codex only), `--cwd`, `--resume <session>`.
3. The script returns immediately with TASK_ID, provider, model, session, and
   log path — record the TASK_ID in your todo list and tell the user in one
   line what you delegated, where, and why. Never dispatch silently.

**Multi-task builds: show the plan.** When delegating two or more tasks,
present a dispatch plan before the first dispatch and keep it updated:

```markdown
| Task | Provider | Model/effort | Depends on | Gate (acceptance) | Status |
```

**Dependency gating:** never dispatch a brief whose inputs depend on another
in-flight task — wait for the upstream artifact to exist and verify it first.
When chaining, the downstream brief references the actual artifact (diff,
file paths, test output), never your summary of it.

If dispatch prints `PROVIDER_UNAVAILABLE` or `BUSY`: move to the **next
provider in your routing order and re-dispatch the same brief.** Absorb the
task yourself only when no capable provider remains. A provider being down
must never block the build.

## Step 4 — Supervise

Go do your own tasks — that is the point. Between them:

```bash
bash <scripts>/fleet-status.sh <TASK_ID>    # or --all
```

Out of your own work? Block efficiently:
`bash <scripts>/fleet-status.sh --wait <TASK_ID> --timeout 900`

**Collision discipline:** never edit files listed in an in-flight brief. Need
one? Wait, or take the task back and treat partial changes as untrusted.

## Step 5 — Verify, then accept (mandatory)

`STATUS DONE` means the worker exited cleanly — a claim, not evidence. Before
accepting: read `git status` and `git diff` (check nothing outside the brief's
scope changed) against the pre-dispatch snapshot in
`.fleet-runs/<TASK_ID>/pre-state` (revision, branch, and files that were
already dirty — anything listed there is not the worker's doing), run the
brief's acceptance commands, and run the
`verification-gate` skill if available. Only then report completion.

If verification fails:
- **Small fix:** do it yourself — faster than a round trip.
- **Substantive rework, provider supports resume** (codex, opencode, claude,
  grok, cursor, qwen, droid): write a
  short follow-up brief stating exactly what's wrong, then
  `--resume <SESSION_ID>`. Max 2 rounds, then take over. Keep follow-up briefs
  additive — state what to change without restating or rewriting the original
  brief, so the worker-side prompt cache of the session prefix stays warm
  (cache hits are the cheapest tokens there are).
- **Substantive rework, no resume** (antigravity, gemini, copilot, amp):
  dispatch a fresh brief that
  includes a summary of the prior round's diff and what to change.

## Step 6 — Record the outcome (mandatory, every task)

After the final outcome of every delegated task — accepted, remediated,
absorbed, or failed — append to the ledger:

```bash
python3 <scripts>/ledger.py append --provider <p> --model "<m>" \
  --task-type <implement|tests|refactor|migration|lint-fix|docs|boilerplate|review|other> \
  --outcome <accepted|remediated|absorbed|failed> --task-id <id> \
  [--cost-usd X] [--tokens N] [--wall-seconds S] [--notes "..."]
```

Pull cost/tokens from the status output's USAGE line when present (opencode
and claude report cost directly; codex, gemini, cursor, qwen, and grok report
tokens — compute cost
from the registry's per-token prices for API providers; omit for flat-rate).
Plain-text providers (antigravity, copilot, amp) and droid report no usage at
all — ledger the outcome without cost/tokens, or add `--wall-seconds` only;
for usage-billed ones (amp, droid) check the provider dashboard when true-cost
accounting matters.

**True-cost accounting:** log `--cost-usd` for `absorbed` and `failed`
outcomes too — the invoice doesn't refund a misroute, so wasted spend must
count against that provider's record. When a failed delegation gets redone
and the redo cost is known (e.g. a replacement worker's reported cost), add
`--redo-cost-usd`. The summary's WASTED and true_cost figures exist so that a
cheap provider that fails often looks as expensive as it really is — sticker
price is not the routing signal; cost-to-merge is. This step is what makes
routing smarter every week — skipping it freezes the system at launch-day
intelligence.

## Failure handling

- **RATE_LIMITED** — a per-provider cooldown is written automatically; that
  provider refuses dispatch until it expires. Re-route the brief down the
  cascade. Mention the fallback to the user in one line.
- **AUTH_ERROR** — tell the user which CLI to re-authenticate (`codex login`, `claude /login`,
  `agy` Google login or `GEMINI_API_KEY`/`ANTIGRAVITY_API_KEY`, `grok login`,
  `cursor-agent login` / `CURSOR_API_KEY`, `copilot` login / `GH_TOKEN`,
  qwen API key, `FACTORY_API_KEY`, `amp login` / `AMP_API_KEY`,
  `opencode auth login`). Re-route meanwhile.
- **FAILED** — read ERRORS and stderr, then pick the rung that matches the
  failure. Transient error or a brief that lacked concrete evidence → one
  retry, same provider, corrected brief. Failure that reveals a capability
  gap → **escalate, never sidestep**: raise `--effort` where supported, or
  re-route to a *stronger* provider (per ledger record / registry strengths) —
  never retry a capability failure on a weaker or equal-cheaper worker just
  because the cascade lists it next. No stronger option → absorb. Never retry
  more than once per provider.
- **INCOMPLETE** — worker died mid-run. Inspect the diff, revert partial
  changes, treat as FAILED.
- Ledger every one of these.

## Concurrency, safety, and hygiene

- Caps: per-provider from the registry; 4 total across the fleet (env
  overrides exist; raise only if the user asks).
- Workers run unattended with file-edit and command execution inside the
  workspace. Only dispatch inside git repos (enforced). You commit — workers
  are briefed never to commit. Review every diff.
- Respect `trust: restricted` — small tasks, narrow file lists, nothing
  touching config or CI.
- Never escalate a worker's sandbox or permissions to unblock a failure;
  escalate to the user instead.
- No secrets in briefs; briefs are written to disk under `.fleet-runs/`.

## Reporting

Keep the user oriented: one line per dispatch (what, where, why), status
changes when you check in, and on acceptance a summary of what was built, what
you verified, and what it cost (USAGE / ledger figures). Cost visibility is a
core promise of this system — surface it, don't bury it.

**Report the route actually run, never the planned one.** If a task cascaded
to a different provider, was remediated, or was absorbed, the final summary
names the provider/model that actually produced the accepted result and what
the detour cost. If a capability the plan relied on turned out to be
unavailable (a missing effort flag, a failed resume), say so — do not present
the fallback as if it were the plan.
