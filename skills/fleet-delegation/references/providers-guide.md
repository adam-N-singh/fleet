# Provider Registry & Adapter Contract

## Registry (`providers.json`)

Resolution order: `$FLEET_PROVIDERS` → `./.fleet/providers.json` →
`~/.fleet/providers.json`. Project-level wins, so different projects can run
different fleets. Start from `config/providers.example.json` or run
`/fleet-init`.

Per-provider fields:

| Field | Meaning |
|---|---|
| `enabled` | Only enabled providers are dispatchable. |
| `adapter` | `codex`, `antigravity`, `gemini` (retired for non-enterprise accounts 2026-06-18), `opencode`, `claude`, `grok`, `cursor`, `copilot`, `qwen`, `droid`, or `amp` — which launch mechanism to use. |
| `access` | `subscription`, `api`, `local`, or `free`. Informs the cost cascade. |
| `default_model` | Model when `--model` isn't passed. **Required for opencode** (`provider/model` form, e.g. `deepseek/deepseek-chat`); empty elsewhere means the CLI's own default. |
| `max_workers` | Per-provider concurrency cap (default 2). |
| `cost` | `{"mode": "flat"|"per_token"|"free", ...}`. For `per_token`, include `input_per_mtok` / `output_per_mtok` so the supervisor can compute ledger costs from token usage. |
| `strengths` / `weaknesses` | Short, honest, and **yours** — these steer routing. Update them as the ledger teaches you. |
| `context_window` | Tokens. Used by the capability filter. |
| `trust` | `standard` or `restricted`. Restricted providers (e.g. small local models) only get small, low-blast-radius tasks. |
| `soft_weekly_cap` | Optional `{"tasks": N}` and/or `{"tokens": N}`. A self-imposed pacing proxy for invisible subscription limits: `ledger.py usage` reports delegated usage against it, and the supervisor deprioritizes (not blocks) providers approaching it, preserving flat-rate quota for late-week work. Counts *delegated* usage only — the supervisor's own session usage is not in the ledger. |
| `review_after` | Optional ISO date. Set when a provider's access terms are scheduled to change (plan changes, promo access ending, a model moving to usage credits). `registry.py list` flags REVIEW_DUE once passed. |
| `notes` | Anything the supervisor should know (auth quirks, silent model fallbacks, etc.). |

`routing.prefer_order` is the cheapest-first cascade consulted after capability
filtering. The one dimension the registry cannot capture is remaining
subscription quota — no provider exposes it — so subscription budgeting is
reactive by design: hit the limit, cool down, cascade.

### One adapter, many providers

The `opencode` adapter is deliberately reusable: create one registry entry per
provider you want routable (deepseek, qwen, kimi, a local LM Studio model...),
each with its own `default_model`, cost, and trust level. They share the
launch mechanism but route independently. Provider credentials and local
endpoints are configured in OpenCode itself (`opencode auth login`,
`opencode.json`), not in this registry.

## Adapter contract (extending the fleet)

An adapter is a bash file at `scripts/adapters/<name>.sh` defining:

```bash
ADAPTER_BIN="..."              # binary checked at preflight
ADAPTER_EVENT_FORMAT="..."     # parse_events.py format key
ADAPTER_SUPPORTS_RESUME="yes|no"
ADAPTER_RATE_PATTERNS='...'    # case-insensitive extended-grep, rate/usage limits
ADAPTER_AUTH_PATTERNS='...'    # same, auth failures

# Must set global array CMD and CMD_STDIN=yes|no.
# If CMD_STDIN=yes, the dispatcher pipes the brief file on stdin;
# if no, embed the brief in CMD yourself (read "$5").
adapter_build_cmd() {  # MODEL EFFORT WORKDIR RESUME BRIEF_PATH
  ...
}
```

Requirements for a well-behaved adapter: the launched command must run fully
unattended (no interactive prompts), write parseable output to stdout, exit
non-zero on failure, and never commit. If the new CLI's output format isn't
shaped like an existing format (`codex`, `opencode`, `gemini`, `claude`,
`ndjson`, `grok`, `text`), add a format function to
`parse_events.py` implementing the six fields (`session`, `final`, `usage`,
`last_event`, `errors`, `completed`) — tolerant parsing, empty-on-missing.

Then add a registry entry with `"adapter": "<name>"`. The dispatcher, status
classification, cooldowns, concurrency, and ledger all work unchanged.
