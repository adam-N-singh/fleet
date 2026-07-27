#!/usr/bin/env bash
# Fleet adapter: Factory Droid CLI (droid exec, headless mode).
# Notes:
# - droid exec -f <file> reads the prompt from a FILE — the brief passes
#   directly, no embedding or stdin needed (CMD_STDIN=no).
# - --output-format json returns one Claude-shaped result object
#   {type:"result", subtype, is_error, result, session_id, num_turns,
#   duration_ms} — parsed with the existing claude format.
# - Autonomy via --auto none|low|medium|high; medium (default here, override
#   with FLEET_DROID_AUTO) covers package installs, builds, and network —
#   note medium also permits git commits, so briefs' "do not commit"
#   instruction is the guard; never use high (deploy/push) for fleet work.
# - Resume supported: --session-id <id> continues a session; --fork <id>
#   branches one.
# - -r/--reasoning-effort maps the dispatcher's --effort straight through.
# - --cwd sets the working directory explicitly.
# - Auth: FACTORY_API_KEY env var (Factory platform account; usage-based).

ADAPTER_BIN="droid"
ADAPTER_EVENT_FORMAT="claude"
ADAPTER_SUPPORTS_RESUME="yes"
ADAPTER_RATE_PATTERNS='rate limit|rate_limit|rate-limit|429|too many requests|quota|usage limit|insufficient credits'
ADAPTER_AUTH_PATTERNS='401|unauthorized|unauthenticated|invalid api key|authentication failed|FACTORY_API_KEY|not logged in'

# adapter_build_cmd MODEL EFFORT WORKDIR RESUME BRIEF_PATH
adapter_build_cmd() {
  local model="$1" effort="$2" workdir="$3" resume="$4" brief="$5"
  CMD=(droid exec --output-format json --auto "${FLEET_DROID_AUTO:-medium}" --cwd "$workdir")
  [[ -n "$resume" ]] && CMD+=(--session-id "$resume")
  [[ -n "$model"  ]] && CMD+=(-m "$model")
  [[ -n "$effort" ]] && CMD+=(-r "$effort")
  CMD+=(-f "$brief")
  CMD_STDIN="no"
}
