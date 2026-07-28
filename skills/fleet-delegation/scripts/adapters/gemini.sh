#!/usr/bin/env bash
# Fleet adapter: Google Gemini CLI (headless mode).
#
# RETIRED (2026-06-18): Google stopped serving Gemini CLI requests for
# free-tier, AI Pro, and AI Ultra accounts and replaced it with the
# Antigravity CLI — see adapters/antigravity.sh. This adapter still works
# ONLY for enterprise Gemini Code Assist licenses, which retain access.
# Everyone else: disable the gemini registry entry and enable antigravity.
# https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/
#
# Notes:
# - Headless mode triggers with -p; the brief is piped on stdin as context.
# - --output-format json returns ONE JSON object {response, stats, error?}
#   at the end of the run (not a stream), so LAST_EVENT is unavailable
#   while running.
# - No resumable session id in headless mode: follow-ups must be dispatched
#   as fresh runs whose brief includes a summary of the prior round.
# - --approval-mode yolo auto-approves tool calls, which unattended runs
#   require. Gemini may enable its own sandbox with yolo by default; if a
#   worker fails with sandbox/docker errors, see the README.

ADAPTER_BIN="gemini"
ADAPTER_EVENT_FORMAT="gemini"
ADAPTER_SUPPORTS_RESUME="no"
ADAPTER_RATE_PATTERNS='(^|[^0-9])429([^0-9]|$)|resource_exhausted|rate limit|rate_limit|too many requests|quota|daily limit'
ADAPTER_AUTH_PATTERNS='(^|[^0-9])401([^0-9]|$)|unauthenticated|permission_denied|invalid api key|not logged in|credential'

# adapter_build_cmd MODEL EFFORT WORKDIR RESUME BRIEF_PATH
adapter_build_cmd() {
  local model="$1" effort="$2" workdir="$3" resume="$4" brief="$5"
  # effort: no gemini equivalent; ignored.
  # workdir: gemini operates in the process cwd; the dispatcher cd's there.
  CMD=(gemini --output-format json --approval-mode yolo
       -p "You are an autonomous coding worker. Complete the task brief provided on stdin exactly as specified. Follow its constraints and acceptance criteria. Do not commit.")
  [[ -n "$model" ]] && CMD+=(-m "$model")
  CMD_STDIN="yes"
}
