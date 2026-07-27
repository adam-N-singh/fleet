#!/usr/bin/env bash
# Fleet adapter: Claude Code headless (claude -p).
# Makes Claude a dispatchable WORKER. Two uses:
#   1. When another agent (e.g. Codex) is the fleet supervisor, this is how
#      it dispatches Claude workers.
#   2. A Claude supervisor can dispatch cheaper Claude models (e.g. haiku)
#      for mechanical work — set default_model accordingly in the registry.
# If the supervisor IS Claude Code on the same account, dispatching here
# spends that same account's quota — legitimate for parallelism, but the
# cross-provider value of the fleet comes from the other adapters.
#
# Notes:
# - --output-format json returns ONE result object at the end:
#   {type:"result", subtype:"success", result, session_id, total_cost_usd,
#    usage, num_turns} — cost feeds the ledger directly.
# - Resume: claude -p --resume <session_id>, which is directory-scoped —
#   the dispatcher already cd's to the task's workdir, satisfying that.
# - Unattended runs need --permission-mode bypassPermissions (default here;
#   override with FLEET_CLAUDE_PERMISSIONS). Optional safety caps via
#   FLEET_CLAUDE_MAX_TURNS and FLEET_CLAUDE_MAX_BUDGET_USD.

ADAPTER_BIN="claude"
ADAPTER_EVENT_FORMAT="claude"
ADAPTER_SUPPORTS_RESUME="yes"
ADAPTER_RATE_PATTERNS='429|rate limit|rate_limit|too many requests|usage limit|usage_limit|quota|overloaded|error_budget'
ADAPTER_AUTH_PATTERNS='401|unauthorized|authentication|invalid api key|not logged in|credential|please run /login'

# adapter_build_cmd MODEL EFFORT WORKDIR RESUME BRIEF_PATH
adapter_build_cmd() {
  local model="$1" effort="$2" workdir="$3" resume="$4" brief="$5"
  # effort: no claude-cli equivalent; ignored. workdir: dispatcher cd's there.
  CMD=(claude -p "You are an autonomous coding worker. Complete the task brief provided on stdin exactly as specified. Follow its constraints and acceptance criteria. Do not commit."
       --output-format json
       --permission-mode "${FLEET_CLAUDE_PERMISSIONS:-bypassPermissions}")
  [[ -n "$model"  ]] && CMD+=(--model "$model")
  [[ -n "$resume" ]] && CMD+=(--resume "$resume")
  [[ -n "${FLEET_CLAUDE_MAX_TURNS:-}"      ]] && CMD+=(--max-turns "$FLEET_CLAUDE_MAX_TURNS")
  [[ -n "${FLEET_CLAUDE_MAX_BUDGET_USD:-}" ]] && CMD+=(--max-budget-usd "$FLEET_CLAUDE_MAX_BUDGET_USD")
  CMD_STDIN="yes"
}
