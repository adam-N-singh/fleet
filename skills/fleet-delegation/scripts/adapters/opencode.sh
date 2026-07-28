#!/usr/bin/env bash
# Fleet adapter: OpenCode (opencode run) — the universal harness.
# One adapter covers every provider OpenCode supports (75+ via Models.dev),
# including DeepSeek, Qwen, Kimi, GLM, Mistral, and local models served by
# LM Studio or Ollama through OpenAI-compatible endpoints.
#
# Notes:
# - The registry's default_model MUST be in provider/model form
#   (e.g. deepseek/deepseek-chat, lmstudio/qwen2.5-coder-32b).
# - --format json emits an NDJSON event stream; step_finish events carry
#   cost and token counts, which feed the ledger.
# - Unattended tool execution is governed by OpenCode's own permissions
#   config (opencode.json). Configure edit/bash permissions to "allow" for
#   the project, or workers will stall — see the README.
# - Resume: opencode run supports continuing a session via -s <session-id>.

ADAPTER_BIN="opencode"
ADAPTER_EVENT_FORMAT="opencode"
ADAPTER_SUPPORTS_RESUME="yes"
ADAPTER_RATE_PATTERNS='(^|[^0-9])429([^0-9]|$)|rate limit|rate_limit|too many requests|quota|overloaded|resource_exhausted'
ADAPTER_AUTH_PATTERNS='(^|[^0-9])401([^0-9]|$)|unauthorized|invalid api key|authentication|no credentials|not logged in'

# adapter_build_cmd MODEL EFFORT WORKDIR RESUME BRIEF_PATH
adapter_build_cmd() {
  local model="$1" effort="$2" workdir="$3" resume="$4" brief="$5"
  # effort: no opencode equivalent; ignored.
  # workdir: opencode operates in the process cwd; the dispatcher cd's there.
  CMD=(opencode run --format json)
  [[ -n "$model"  ]] && CMD+=(--model "$model")
  [[ -n "$resume" ]] && CMD+=(--session "$resume")
  CMD+=("$(cat "$brief")")   # brief as the run message
  CMD_STDIN="no"
}
