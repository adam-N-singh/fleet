#!/usr/bin/env bash
# Fleet adapter: Amp CLI (ampcode.com, execute mode).
# Notes:
# - Execute mode is amp -x "<prompt>"; the prompt is an ARGUMENT
#   (CMD_STDIN=no). Output is the final response as plain text (its
#   --stream-json mode exists but the event schema is unpublished), so
#   LAST_EVENT and USAGE are unavailable — parsed as plain text.
# - --dangerously-allow-all auto-approves tool execution. Amp's own
#   recommended alternative is command allowlisting in its settings.json;
#   configure that and drop the flag via FLEET_AMP_ALLOW_ALL=0 if you
#   prefer a tighter sandbox.
# - Threads persist and sync to ampcode.com (`amp threads continue <id>`),
#   but execute mode doesn't surface the thread id on current versions —
#   resume is off; follow-ups are fresh briefs. VERIFY on your version.
# - No model flag: Amp routes models itself; registry default_model stays
#   empty.
# - Auth: `amp login` or AMP_API_KEY env var. Billing is usage-based
#   (credits), so treat access mode as "api" — the ledger can't compute
#   cost from tokens (none reported); check the Amp dashboard.
# - npm package renamed @sourcegraph/amp -> @ampcode/cli (2026).

ADAPTER_BIN="amp"
ADAPTER_EVENT_FORMAT="text"
ADAPTER_SUPPORTS_RESUME="no"
ADAPTER_RATE_PATTERNS='rate limit|rate_limit|rate-limit|429|too many requests|quota|out of credits|insufficient credits'
ADAPTER_AUTH_PATTERNS='401|unauthorized|unauthenticated|not logged in|login required|invalid api key|AMP_API_KEY'

# adapter_build_cmd MODEL EFFORT WORKDIR RESUME BRIEF_PATH
adapter_build_cmd() {
  local model="$1" effort="$2" workdir="$3" resume="$4" brief="$5"
  local brief_text
  brief_text="$(cat "$brief")"
  # model/effort: no amp equivalents; ignored. resume: unsupported, ignored.
  # workdir: amp operates in the process cwd; the dispatcher cd's there.
  CMD=(amp -x "$brief_text")
  [[ "${FLEET_AMP_ALLOW_ALL:-1}" == "1" ]] && CMD+=(--dangerously-allow-all)
  CMD_STDIN="no"
}
