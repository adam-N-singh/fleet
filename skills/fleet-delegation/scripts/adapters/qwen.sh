#!/usr/bin/env bash
# Fleet adapter: Qwen Code CLI (qwen, headless mode).
# Notes:
# - Fork of Gemini CLI, but its structured output is Claude-style, not
#   Gemini-style: --output-format stream-json emits NDJSON events with
#   type/session_id/... and a final {"type":"result",...} object —
#   parsed by the ndjson-stream format.
# - Like its parent, -p works with the brief piped on stdin as context
#   (CMD_STDIN=yes keeps huge briefs off the argv limit).
# - --approval-mode yolo (or --yolo) auto-approves all tool calls.
#   There is NO sandbox by default — same blast radius as the other
#   adapters; the git-repo-only + review-diff discipline applies.
# - Resume supported: --resume <session-id> (project-scoped sessions in
#   ~/.qwen/projects/<cwd>/chats).
# - Useful caps: distinct exit codes for limits (53 = turn limit,
#   55 = wall-time/tool budget). FLEET_QWEN_MAX_WALL_TIME (e.g. "45m")
#   and FLEET_QWEN_MAX_TURNS add --max-wall-time / --max-session-turns.
# - Auth: the old Qwen OAuth free tier (~2000 req/day) was discontinued —
#   VERIFY current access: API key env or a Qwen Coding Plan.

ADAPTER_BIN="qwen"
ADAPTER_EVENT_FORMAT="ndjson"
ADAPTER_SUPPORTS_RESUME="yes"
ADAPTER_RATE_PATTERNS='rate limit|rate_limit|rate-limit|(^|[^0-9])429([^0-9]|$)|too many requests|quota|resource_exhausted|daily limit'
ADAPTER_AUTH_PATTERNS='(^|[^0-9])401([^0-9]|$)|unauthorized|unauthenticated|not logged in|login required|invalid api key|authentication failed'

# adapter_build_cmd MODEL EFFORT WORKDIR RESUME BRIEF_PATH
adapter_build_cmd() {
  local model="$1" effort="$2" workdir="$3" resume="$4" brief="$5"
  # effort: no qwen equivalent; ignored.
  # workdir: qwen operates in the process cwd; the dispatcher cd's there.
  CMD=(qwen --output-format stream-json --approval-mode yolo)
  [[ -n "$resume" ]] && CMD+=(--resume "$resume")
  [[ -n "$model"  ]] && CMD+=(--model "$model")
  [[ -n "${FLEET_QWEN_MAX_WALL_TIME:-}" ]] && CMD+=(--max-wall-time "$FLEET_QWEN_MAX_WALL_TIME")
  [[ -n "${FLEET_QWEN_MAX_TURNS:-}" ]] && CMD+=(--max-session-turns "$FLEET_QWEN_MAX_TURNS")
  CMD+=(-p "Complete the task brief provided on stdin exactly as specified. Follow its constraints and acceptance criteria. Do not commit.")
  CMD_STDIN="yes"
}
