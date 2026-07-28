#!/usr/bin/env bash
# Fleet adapter: Cursor CLI (cursor-agent, print mode).
# Notes:
# - Headless mode is cursor-agent -p "<prompt>" (print mode); the prompt
#   is an ARGUMENT (CMD_STDIN=no).
# - --output-format stream-json emits Claude-style NDJSON events
#   (type/session_id/...; final {"type":"result",...}); parsed by the
#   ndjson-stream format. VERIFY event shapes on your installed version.
# - --force (alias --yolo) is required in non-interactive mode or the
#   agent stalls on approval prompts; pair with --trust in CI if needed.
# - Resume supported: --resume <session-id>.
# - Auth: `cursor-agent login` (browser) or CURSOR_API_KEY env var for
#   headless boxes. Access is via Cursor plans (subscription) or API key.
# - KNOWN QUIRK (verify on your version): in headless mode the agent has
#   been reported to fabricate "Questions skipped by the user" answers
#   instead of failing when it wants input (tiann/hapi#784) — briefs must
#   be fully self-contained so the question never arises.
# - No --cwd flag documented; the dispatcher launches the worker with the
#   workdir as process cwd, which cursor-agent uses.

ADAPTER_BIN="cursor-agent"
ADAPTER_EVENT_FORMAT="ndjson"
ADAPTER_SUPPORTS_RESUME="yes"
ADAPTER_RATE_PATTERNS='rate limit|rate_limit|rate-limit|(^|[^0-9])429([^0-9]|$)|too many requests|quota|usage limit'
ADAPTER_AUTH_PATTERNS='(^|[^0-9])401([^0-9]|$)|unauthorized|not logged in|login required|invalid api key|authentication failed|unauthenticated'

# adapter_build_cmd MODEL EFFORT WORKDIR RESUME BRIEF_PATH
adapter_build_cmd() {
  local model="$1" effort="$2" workdir="$3" resume="$4" brief="$5"
  local brief_text
  brief_text="$(cat "$brief")"
  # effort: no cursor-agent equivalent; ignored.
  CMD=(cursor-agent --output-format stream-json --force)
  [[ -n "$resume" ]] && CMD+=(--resume "$resume")
  [[ -n "$model"  ]] && CMD+=(-m "$model")
  CMD+=(-p "$brief_text")
  CMD_STDIN="no"
}
