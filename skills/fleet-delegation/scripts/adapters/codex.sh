#!/usr/bin/env bash
# Fleet adapter: OpenAI Codex CLI (codex exec).
# Contract: define ADAPTER_* vars and adapter_build_cmd(), which must set the
# global CMD array and CMD_STDIN=yes|no (whether the brief is piped on stdin).

ADAPTER_BIN="codex"
ADAPTER_EVENT_FORMAT="codex"
ADAPTER_SUPPORTS_RESUME="yes"
ADAPTER_RATE_PATTERNS='rate limit|rate_limit|rate-limit|429|too many requests|usage limit|usage_limit|quota'
ADAPTER_AUTH_PATTERNS='401|unauthorized|not logged in|login required|invalid api key|authentication failed'

# adapter_build_cmd MODEL EFFORT WORKDIR RESUME BRIEF_PATH
adapter_build_cmd() {
  local model="$1" effort="$2" workdir="$3" resume="$4" brief="$5"
  CMD=(codex exec)
  if [[ -n "$resume" ]]; then
    CMD+=(resume "$resume")
  fi
  CMD+=(--json --sandbox "${FLEET_CODEX_SANDBOX:-workspace-write}")
  if [[ -z "$resume" ]]; then
    CMD+=(--cd "$workdir")
  fi
  [[ -n "$model"  ]] && CMD+=(--model "$model")
  [[ -n "$effort" ]] && CMD+=(-c "model_reasoning_effort=$effort")
  CMD+=(-)  # read the brief from stdin
  CMD_STDIN="yes"
}
