#!/usr/bin/env bash
# Fleet adapter: GitHub Copilot CLI (copilot, programmatic mode).
# Notes:
# - Programmatic mode is copilot -p "<prompt>"; prompt is an ARGUMENT
#   (CMD_STDIN=no). -s suppresses stats/decoration so stdout is just the
#   agent's response — plain text, no JSON output mode exists, so
#   LAST_EVENT and USAGE are unavailable (parsed as plain text).
# - --allow-all-tools is required for unattended runs (the fleet's
#   equivalent of yolo); --no-ask-user stops the agent pausing for input.
#   GitHub's own docs recommend containers for --allow-all-tools — the
#   fleet's git-repo-only + review-diff discipline is the mitigation here.
# - No documented programmatic session resume — follow-ups are fresh
#   briefs (interactive /resume exists but isn't scriptable).
# - Auth: `copilot` login flow, or COPILOT_GITHUB_TOKEN / GH_TOKEN /
#   GITHUB_TOKEN env vars (that precedence). Requires a Copilot
#   subscription; model choice affects premium-request multipliers.
# - Model via --model (e.g. gpt-5.2, claude-sonnet-4.6).

ADAPTER_BIN="copilot"
ADAPTER_EVENT_FORMAT="text"
ADAPTER_SUPPORTS_RESUME="no"
ADAPTER_RATE_PATTERNS='rate limit|rate_limit|rate-limit|(^|[^0-9])429([^0-9]|$)|too many requests|quota|usage limit|premium request'
ADAPTER_AUTH_PATTERNS='(^|[^0-9])401([^0-9]|$)|unauthorized|not logged in|login required|authentication failed|no copilot subscription|invalid token|token expired'

# adapter_build_cmd MODEL EFFORT WORKDIR RESUME BRIEF_PATH
adapter_build_cmd() {
  local model="$1" effort="$2" workdir="$3" resume="$4" brief="$5"
  local brief_text
  brief_text="$(cat "$brief")"
  # effort: no copilot equivalent; ignored. resume: unsupported, ignored.
  # workdir: copilot operates in the process cwd; the dispatcher cd's there.
  CMD=(copilot -s --allow-all-tools --no-ask-user)
  [[ -n "$model" ]] && CMD+=(--model "$model")
  CMD+=(-p "$brief_text")
  CMD_STDIN="no"
}
