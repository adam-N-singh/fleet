#!/usr/bin/env bash
# Fleet adapter: xAI Grok Build CLI (grok, headless mode).
# Notes:
# - Headless mode is grok -p "<prompt>"; the prompt is an ARGUMENT, not
#   stdin, so the brief is embedded in the command (CMD_STDIN=no).
# - --output-format json returns one JSON object at the end of the run.
#   xAI does not publish the field schema, so parse_events.py uses the
#   tolerant generic-object format (recursive key search) — VERIFY the
#   session/usage extraction on your installed version before trusting
#   (one `grok -p "Say ok" --output-format json` run shows the shape).
# - --always-approve (alias --yolo) auto-approves tool executions; without
#   it headless runs stall on approval prompts. Default permission mode
#   is "ask".
# - Resume IS supported: -r <session-id>, sessions in ~/.grok/sessions.
#   Session id discovery depends on the JSON output surfacing it — if it
#   doesn't on your version, follow-ups need fresh briefs.
# - --effort maps straight through (same concept as codex).
# - Auth is subscription-gated: `grok login` needs SuperGrok or X
#   Premium+ (device flow: grok login --device-auth). As of 2026-07 full
#   Grok 4.5 access is confirmed only on SuperGrok Heavy; lower tiers are
#   getting it in stages.
# - --no-auto-update suppresses background update checks in scripts.
# - Optional turn cap: FLEET_GROK_MAX_TURNS adds --max-turns.

ADAPTER_BIN="grok"
ADAPTER_EVENT_FORMAT="grok"
ADAPTER_SUPPORTS_RESUME="yes"
ADAPTER_RATE_PATTERNS='rate limit|rate_limit|rate-limit|429|too many requests|quota|usage limit|resource_exhausted'
ADAPTER_AUTH_PATTERNS='401|unauthorized|not logged in|login required|subscription required|authentication failed|invalid api key'

# adapter_build_cmd MODEL EFFORT WORKDIR RESUME BRIEF_PATH
adapter_build_cmd() {
  local model="$1" effort="$2" workdir="$3" resume="$4" brief="$5"
  local brief_text
  brief_text="$(cat "$brief")"
  CMD=(grok --no-auto-update --output-format json --always-approve --cwd "$workdir")
  [[ -n "$resume" ]] && CMD+=(-r "$resume")
  [[ -n "$model"  ]] && CMD+=(-m "$model")
  [[ -n "$effort" ]] && CMD+=(--effort "$effort")
  [[ -n "${FLEET_GROK_MAX_TURNS:-}" ]] && CMD+=(--max-turns "$FLEET_GROK_MAX_TURNS")
  CMD+=(-p "$brief_text")
  CMD_STDIN="no"
}
