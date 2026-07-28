#!/usr/bin/env bash
# Fleet adapter: Google Antigravity CLI (agy, headless print mode).
# Successor to Gemini CLI, which Google retired for free/AI Pro/Ultra
# accounts on 2026-06-18. Requires agy >= 1.1.1: earlier versions read
# stdin even with -p (hangs in subprocesses) and could exit 0 with empty
# output on server-side failures; 1.0.0 also dropped stdout entirely under
# a non-TTY (github.com/google-antigravity/antigravity-cli issue #76).
# Notes:
# - Headless mode is agy -p "<prompt>": ONE plain-text response on stdout
#   at the end of the run. There is NO structured/JSON output flag
#   (--output-format is rejected as undefined), so LAST_EVENT and USAGE
#   are unavailable; parse_events.py treats the output as plain text.
# - agy >= 1.1.1 ignores stdin when -p is given, so the brief cannot be
#   piped: it is embedded in the prompt argument (CMD_STDIN=no).
# - No headless resume: -p runs never surface their conversation id
#   (issue #7), and -c/--continue resumes the most recent conversation
#   GLOBALLY — unsafe with concurrent workers. Follow-ups must be fresh
#   briefs summarizing the prior round.
# - --dangerously-skip-permissions auto-approves tool calls (the
#   --approval-mode yolo equivalent), which unattended runs require.
#   Optional: FLEET_ANTIGRAVITY_SANDBOX=1 adds --sandbox (terminal
#   restrictions; may block acceptance commands — see README).
# - --print-timeout defaults to 5m, far too short for coding tasks;
#   raised here (override with FLEET_ANTIGRAVITY_PRINT_TIMEOUT).
# - Free tier is ~20 requests/day; one agentic task can burn several,
#   so keep max_workers low and expect daily-quota rate limits.

ADAPTER_BIN="agy"
ADAPTER_EVENT_FORMAT="antigravity"
ADAPTER_SUPPORTS_RESUME="no"
ADAPTER_RATE_PATTERNS='(^|[^0-9])429([^0-9]|$)|resource_exhausted|rate limit|rate_limit|too many requests|quota|daily limit|requests per day'
ADAPTER_AUTH_PATTERNS='(^|[^0-9])401([^0-9]|$)|unauthenticated|unauthorized|permission_denied|invalid api key|not signed in|not logged in|credential'

# adapter_build_cmd MODEL EFFORT WORKDIR RESUME BRIEF_PATH
adapter_build_cmd() {
  local model="$1" effort="$2" workdir="$3" resume="$4" brief="$5"
  # effort: no agy equivalent; ignored.
  # workdir: agy operates in the process cwd; the dispatcher cd's there.
  local brief_text
  brief_text="$(cat "$brief")"
  CMD=(agy -p "You are an autonomous coding worker. Complete the task brief below exactly as specified. Follow its constraints and acceptance criteria. Do not commit.

--- TASK BRIEF ---
$brief_text"
       --dangerously-skip-permissions
       --print-timeout "${FLEET_ANTIGRAVITY_PRINT_TIMEOUT:-45m}")
  [[ -n "$model" ]] && CMD+=(--model "$model")
  [[ "${FLEET_ANTIGRAVITY_SANDBOX:-}" == "1" ]] && CMD+=(--sandbox)
  CMD_STDIN="no"
}
