# fleet

An **agent-portable skill** (plus a Claude Code plugin wrapper) that turns your
coding agent into the supervisor of a **multi-provider fleet** of AI coding
workers. The supervisor stays the planner, architect, router, and reviewer;
well-specified implementation work runs in the background on whichever worker
is best suited and cheapest — OpenAI Codex, Google Gemini CLI, Claude Code
headless, or any of 75+ providers via OpenCode, including DeepSeek, Qwen, Kimi,
GLM, and local models served by LM Studio or Ollama.

The skill follows the [Agent Skills open standard](https://agentskills.io)
(SKILL.md), so the **same skill folder works under Claude Code, Codex CLI,
Gemini CLI, Cursor, and other compatible agents** — any of them can be the
supervisor, and thanks to the `claude` adapter, Claude Code is also a
dispatchable worker. Claude Code additionally gets a plugin wrapper with
`/dispatch`, `/fleet-status`, and `/fleet-init` commands.

> ## ⚠️ Read this before installing
>
> This plugin runs **autonomous background agents in your repository — from
> multiple providers, in parallel.** When Claude delegates a task, it launches
> a worker CLI headlessly with auto-approved tool execution: Codex with
> `--sandbox workspace-write`, Gemini with `--approval-mode yolo`, OpenCode
> per your permissions config. Concretely, workers can **edit files and run
> commands inside your project directory without asking you first**, while
> Claude works on other things. With API-billed providers enabled, delegation
> also **spends real money**.
>
> Mitigations built in: workers only run inside git repositories so every
> change is reviewable via `git diff` before commit; workers are briefed never
> to commit (Claude reviews and commits); sandboxes/permissions are never
> escalated by Claude; every dispatch is announced with provider, model, and
> reasoning; per-provider `trust` levels restrict what smaller models may
> touch; costs are surfaced per task via the ledger; and Claude must verify
> results against the brief's acceptance criteria before accepting them.
>
> Even so: **only use this in repositories you trust**, don't point it at
> repos containing untrusted code, review diffs before committing, and only
> enable providers whose billing you understand. If you are not comfortable
> with unattended agents modifying your working tree, do not install this.

## What it does

- **Registry-driven fleet knowledge.** A user-owned `providers.json` describes
  what you actually have access to: adapter, access mode (subscription / API /
  free tier / local), models, costs, strengths and weaknesses, concurrency
  caps, trust levels. `/fleet-init` interviews you and web-researches current
  models and pricing to draft it — fleet knowledge is never fossilized in a
  prompt.
- **Intelligent routing.** For each delegable task Claude filters by
  capability, then walks a cheapest-first cost cascade (local free →
  subscription flat → cheap API → expensive API), then checks availability,
  then consults the **outcome ledger** — observed success rates per
  provider/model/task-type from your actual usage. Routing gets smarter every
  week you use it.
- **Parallel execution and supervision.** Workers launch as background
  processes with per-provider and global concurrency caps. Claude dispatches,
  keeps working, checks in between its own tasks, and classifies each worker
  as RUNNING / DONE / FAILED / RATE_LIMITED / AUTH_ERROR / INCOMPLETE.
- **Quota pacing and true-cost visibility.** Optional per-provider
  `soft_weekly_cap` values let the supervisor deprioritize a flat-rate
  provider *before* it hits invisible subscription limits (`ledger.py usage`),
  preserving frontier quota for the work that needs it. `ledger.py dashboard`
  shows spend by provider by day, and the ledger books wasted spend from
  misroutes (plus redo costs) so cheap-but-flaky providers surface at their
  true cost-to-merge, not their sticker price. A `review_after` date field
  flags providers whose access terms are scheduled to change.
- **Cascade fallback.** A rate-limited provider gets an automatic cooldown and
  the brief re-routes to the next capable provider; Claude absorbs the task
  itself only when no provider remains. No provider outage blocks the build.
- **Verification-gated acceptance.** "DONE" is a claim, not evidence: git diff
  review + the brief's acceptance commands (+ the `verification-gate` skill if
  installed) before anything is accepted. Remediation resumes the same worker
  session where supported (Codex, OpenCode).

## Requirements

- Any Agent Skills-compatible supervisor: Claude Code, Codex CLI, Gemini CLI,
  Cursor, OpenCode, and others; `git`, `bash`, `python3`
- At least one worker CLI installed and authenticated:
  - **Codex CLI** (`codex login`) — OpenAI, subscription or API
  - **Gemini CLI** (Google login for the free tier, or `GEMINI_API_KEY`)
  - **Claude Code** (`claude /login`) — as a worker, on any account/model
  - **OpenCode** (`opencode auth login` per provider) — everything else,
    including local models

## Install

**Claude Code (richest experience — adds the slash commands):**

```
/plugin marketplace add <your-username>/fleet
/plugin install fleet@fleet-marketplace
```

**Codex CLI / Gemini CLI / Antigravity / anything else** — the skill alone is
fully functional; supervisors without the commands are simply *asked* ("set up
my fleet registry", "dispatch the test suite to gemini", "check on the fleet"):

```bash
git clone <this-repo> && cd fleet
./install.sh codex          # -> ~/.codex/skills/fleet-delegation
./install.sh gemini         # -> ~/.gemini/skills/fleet-delegation
./install.sh antigravity    # -> ~/.gemini/antigravity/skills/fleet-delegation
./install.sh --dir <path>   # any other agent's skills directory
./install.sh <target> --project   # project-level instead of user-level
```

**Windows:** PowerShell doesn't execute `.sh` files (it opens them in your
editor). Either run the bash installer through Git Bash — `bash ./install.sh
codex` — or use the native PowerShell installer: `.\install.ps1 codex`
(same targets, `-Dir <path>`, `-Project`). Claude Code users can skip
installers entirely: `/plugin marketplace add <path-or-repo>` works with a
local folder path. Runtime requirements on Windows: Git for Windows (the
skill's scripts run under Git Bash at dispatch time) and Python on PATH —
plain `python` is fine, the scripts fall back automatically when `python3`
doesn't exist (override with `FLEET_PYTHON`).

Skill directory locations vary by agent version — if the agent doesn't
discover it, check that agent's skills docs and rerun with `--dir`. Then have
the supervisor create your provider registry (Claude Code: `/fleet-init`;
others: "read the fleet-delegation skill's providers-guide and set up my
registry"). Add `.fleet-runs/` to your project's `.gitignore` (the skill also
does this on first dispatch).

## Usage

The `fleet-delegation` skill triggers on its own during multi-task builds;
the supervisor announces every dispatch with provider, model, and reasoning.
Claude Code manual controls (other agents: just ask in natural language):

- `/dispatch <task> [on <provider>]` — explicitly delegate (skips the rubric)
- `/fleet-status [task-id]` — check workers across all providers
- `/fleet-init` — create or refresh the provider registry

## Configuration

Registry: `$FLEET_PROVIDERS` → `./.fleet/providers.json` →
`~/.fleet/providers.json`. Schema in
`skills/fleet-delegation/references/providers-guide.md`; starter in
`skills/fleet-delegation/config/providers.example.json`.

| Env var | Default | Meaning |
|---|---|---|
| `FLEET_RUNS_DIR` | `.fleet-runs` | Bookkeeping (briefs, logs, pids, ledger) |
| `FLEET_MAX_WORKERS_TOTAL` | `4` | Global concurrency cap (per-provider caps live in the registry) |
| `FLEET_COOLDOWN_SECONDS` | `900` | Per-provider cooldown after a rate limit |
| `FLEET_CODEX_SANDBOX` | `workspace-write` | Codex sandbox mode |
| `FLEET_LEDGER` | `.fleet-runs/ledger.jsonl` | Outcome ledger path |
| `FLEET_PROVIDERS` | (search order above) | Explicit registry path |

## Per-provider setup notes

- **Codex:** works out of the box once `codex login` is done. Resume supported.
- **Gemini:** headless mode returns one JSON object at the end (no live
  progress events) and has **no resumable session** — follow-ups are fresh
  briefs. YOLO approval mode may enable Gemini's own sandbox by default, which
  wants Docker; if workers fail with sandbox errors, disable sandboxing in
  Gemini's settings.json or install Docker. Free tier silently falls back
  between models near quota.
- **Claude (as worker):** headless `claude -p` with `--permission-mode
  bypassPermissions` (override via `FLEET_CLAUDE_PERMISSIONS`; optional caps
  `FLEET_CLAUDE_MAX_TURNS` / `FLEET_CLAUDE_MAX_BUDGET_USD`). Resume is
  directory-scoped, which the dispatcher satisfies. If the supervisor is
  Claude Code on the same account, this adapter buys parallelism, not savings.
- **OpenCode:** set each registry entry's `default_model` to an exact
  `provider/model` string (check `opencode models`). Unattended tool execution
  is governed by OpenCode's own permissions config — set edit/bash permissions
  to allow for the project or workers will stall waiting for approval that
  never comes. Local models: run LM Studio's server (or Ollama), configure it
  as an OpenAI-compatible provider in `opencode.json`, then reference it in
  the registry.

## Verify before trusting (first-run checklist)

The provider-agnostic core (registry resolution, routing inputs, dispatch,
background execution, per-provider cooldown isolation, status classification,
cascade signaling, ledger) is tested against stubs that mimic each CLI's
documented output. What depends on your installed CLI versions — verify once
per provider on a throwaway repo:

1. **Codex** (carried from v1): stdin prompt via `codex exec ... -`; `resume`
   flag placement; JSONL field names; your plan's rate-limit message strings.
2. **Gemini:** that `--output-format json` emits the `{response, stats}`
   object on your version (this shipped mid-2025; very old versions lack it);
   that `--approval-mode yolo` runs unattended in your environment (sandbox/
   Docker interaction); quota-exhaustion message strings against
   `ADAPTER_RATE_PATTERNS` in `adapters/gemini.sh`.
3. **OpenCode:** exact event shapes from `--format json` (the parser is
   tolerant, but confirm `final`/`usage` extraction on your version); that a
   session id is discoverable in the event stream for `--resume` (if not,
   `opencode session list` is the fallback — adjust `parse_events.py`);
   permissions config actually allows unattended edit/bash.
4. **Claude worker:** that `claude -p --output-format json` emits the result
   object with `session_id`/`total_cost_usd` on your version, and that
   `--permission-mode bypassPermissions` runs unattended in your environment.
5. **Registry pricing:** the example file's per-token prices are placeholders —
   `/fleet-init` researches real ones; verify before enabling API providers.

## Layout

```
fleet/
├── .claude-plugin/{plugin.json, marketplace.json}
├── commands/{dispatch.md, fleet-status.md, fleet-init.md}
└── skills/fleet-delegation/
    ├── SKILL.md                     rubric, routing, supervision, ledger protocol
    ├── references/{brief-template.md, providers-guide.md}
    ├── config/providers.example.json
    └── scripts/
        ├── fleet-dispatch.sh        provider-agnostic dispatcher
        ├── fleet-status.sh          provider-aware classification
        ├── registry.py              providers.json reader
        ├── parse_events.py          codex | opencode | gemini parsing
        ├── ledger.py                outcome tracking + summaries
        └── adapters/{codex.sh, gemini.sh, opencode.sh, claude.sh}
```

Plus `install.sh` at the repo root for non-Claude-Code agents. The
`.claude-plugin/` and `commands/` directories are the Claude Code wrapper;
everything under `skills/` is the portable core.

Extending to a new provider CLI = one adapter file + registry entry (contract
in `references/providers-guide.md`).
