#!/usr/bin/env bash
# fleet-status.sh — report the status of fleet background workers.
#
# Usage:
#   fleet-status.sh <task-id>                        one worker
#   fleet-status.sh --all                            every worker
#   fleet-status.sh --wait <task-id> [--timeout N]   block until terminal state
#
# Statuses:
#   RUNNING       worker alive, still working
#   DONE          exited cleanly with a result — VERIFY BEFORE ACCEPTING
#   FAILED        exited with an error (see ERRORS / STDERR_TAIL)
#   RATE_LIMITED  provider rate/usage limit — provider cooldown now active;
#                 re-dispatch on the next provider in the cascade
#   AUTH_ERROR    provider authentication problem — tell the user how to fix
#   INCOMPLETE    worker process gone without an exit code — treat as failed
#
# Environment overrides:
#   FLEET_RUNS_DIR (default .fleet-runs)   FLEET_COOLDOWN_SECONDS (default 900)
#   FLEET_POLL_INTERVAL for --wait (default 20)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Windows-friendly python resolution: Git Bash usually has `python`, not `python3`.
PY="${FLEET_PYTHON:-}"
if [[ -z "$PY" ]]; then
  if command -v python3 >/dev/null 2>&1; then PY="python3"; else PY="python"; fi
fi
RUNS_DIR="${FLEET_RUNS_DIR:-.fleet-runs}"
COOLDOWN_SECONDS="${FLEET_COOLDOWN_SECONDS:-900}"
POLL_INTERVAL="${FLEET_POLL_INTERVAL:-20}"

if [[ ! -d "$RUNS_DIR" ]]; then
  echo "STATUS UNKNOWN (no runs directory at $RUNS_DIR — nothing has been dispatched)"
  exit 0
fi
RUNS_DIR="$(cd "$RUNS_DIR" && pwd)"

meta() {  # meta <task_dir> <key>
  ${PY} -c "import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2],''))" \
    "$1/meta.json" "$2" 2>/dev/null || true
}

pe() {  # pe <events_file> <field> <format>
  ${PY} "$SCRIPT_DIR/parse_events.py" "$1" "$2" --format "$3" 2>/dev/null || true
}

report_task() {
  local task_dir="$1"
  local task_id provider fmt adapter_file
  task_id="$(basename "$task_dir")"
  echo "TASK $task_id"

  if [[ ! -d "$task_dir" ]]; then
    echo "STATUS UNKNOWN (no such task)"
    return 0
  fi

  provider="$(meta "$task_dir" provider)"
  fmt="$(meta "$task_dir" format)"
  local model
  model="$(meta "$task_dir" model)"
  echo "PROVIDER ${provider:-?} MODEL ${model:-(cli default)}"

  # Load the adapter's classification patterns
  local RATE_PATTERNS='429|rate limit|rate_limit|too many requests|quota'
  local AUTH_PATTERNS='401|unauthorized|invalid api key|not logged in'
  adapter_file="$SCRIPT_DIR/adapters/$(meta "$task_dir" adapter).sh"
  if [[ -f "$adapter_file" ]]; then
    # shellcheck source=/dev/null
    source "$adapter_file"
    RATE_PATTERNS="$ADAPTER_RATE_PATTERNS"
    AUTH_PATTERNS="$ADAPTER_AUTH_PATTERNS"
  fi

  local events="$task_dir/events.jsonl"
  local session
  session="$(pe "$events" session "$fmt")"
  [[ -n "$session" ]] && echo "SESSION $session"

  if [[ ! -f "$task_dir/exit-code" ]]; then
    local pid
    pid="$(cat "$task_dir/pid" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "STATUS RUNNING"
      local last
      last="$(pe "$events" last_event "$fmt")"
      [[ -n "$last" ]] && echo "LAST_EVENT $last"
    else
      echo "STATUS INCOMPLETE"
      echo "NOTE worker process gone without an exit code. Inspect the log and git diff, revert partial changes, treat as FAILED."
      echo "LOG $events"
    fi
    return 0
  fi

  local rc completed
  rc="$(cat "$task_dir/exit-code" 2>/dev/null || echo "?")"
  completed="$(pe "$events" completed "$fmt")"

  if [[ "$rc" == "0" && "$completed" == "yes" ]]; then
    echo "STATUS DONE"
    local usage
    usage="$(pe "$events" usage "$fmt")"
    [[ -n "$usage" ]] && echo "USAGE $usage"
    echo "FINAL_MESSAGE:"
    pe "$events" final "$fmt"
    echo "NEXT: review git diff, run the brief's acceptance commands, then record the outcome:"
    echo "  ${PY} $SCRIPT_DIR/ledger.py append --provider $provider --model '$model' --task-type <type> --outcome <accepted|remediated|absorbed|failed> --task-id $task_id"
    return 0
  fi

  if grep -qiE "$AUTH_PATTERNS" "$task_dir/stderr.log" "$events" 2>/dev/null; then
    echo "STATUS AUTH_ERROR"
    echo "NOTE $provider authentication failed. Tell the user to re-authenticate that CLI. Re-dispatch on the next provider in the cascade meanwhile."
    return 0
  fi

  if grep -qiE "$RATE_PATTERNS" "$task_dir/stderr.log" "$events" 2>/dev/null; then
    local until=$(( $(date +%s) + COOLDOWN_SECONDS ))
    echo "$until" > "$RUNS_DIR/cooldown-$provider"
    echo "STATUS RATE_LIMITED"
    echo "COOLDOWN_UNTIL $until (epoch, ${COOLDOWN_SECONDS}s, provider: $provider)"
    echo "NOTE $provider is blocked until the cooldown expires. Re-dispatch this brief on the next provider in the cascade; absorb only if none remain."
    return 0
  fi

  echo "STATUS FAILED"
  echo "EXIT $rc"
  echo "ERRORS:"
  pe "$events" errors "$fmt"
  if [[ -s "$task_dir/stderr.log" ]]; then
    echo "STDERR_TAIL:"
    tail -n 8 "$task_dir/stderr.log"
  fi
  echo "NOTE if the failure traces to an ambiguous brief, retry once with a corrected brief; otherwise try the next provider or absorb. Record the outcome in the ledger."
  return 0
}

# ---------- argument handling ------------------------------------------------

MODE="single"; TARGET=""; TIMEOUT=900

if [[ $# -eq 0 ]]; then
  MODE="all"
else
  case "$1" in
    --all) MODE="all" ;;
    --wait)
      MODE="wait"; TARGET="${2:-}"
      [[ -n "$TARGET" ]] || { echo "ERROR: --wait requires a task id" >&2; exit 2; }
      shift 2
      while [[ $# -gt 0 ]]; do
        case "$1" in
          --timeout) TIMEOUT="$2"; shift 2 ;;
          *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
        esac
      done
      ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) TARGET="$1" ;;
  esac
fi

case "$MODE" in
  all)
    NOW="$(date +%s)"
    for cf in "$RUNS_DIR"/cooldown-*; do
      [[ -f "$cf" ]] || continue
      UNTIL="$(cat "$cf" 2>/dev/null || echo 0)"
      if [[ "$UNTIL" =~ ^[0-9]+$ ]] && (( NOW < UNTIL )); then
        echo "COOLDOWN_ACTIVE $(basename "$cf" | sed 's/^cooldown-//') $(( UNTIL - NOW ))s remaining"
      fi
    done
    FOUND=0
    for d in "$RUNS_DIR"/*/; do
      [[ -d "$d" && -f "$d/pid" ]] || continue
      FOUND=1
      report_task "$d"
      echo ""
    done
    [[ "$FOUND" == "1" ]] || echo "STATUS NONE (no workers have been dispatched)"
    ;;
  single)
    report_task "$RUNS_DIR/$TARGET"
    ;;
  wait)
    DEADLINE=$(( $(date +%s) + TIMEOUT ))
    while true; do
      OUT="$(report_task "$RUNS_DIR/$TARGET")"
      if ! grep -q "STATUS RUNNING" <<< "$OUT"; then
        printf '%s\n' "$OUT"; exit 0
      fi
      if (( $(date +%s) >= DEADLINE )); then
        printf '%s\n' "$OUT"
        echo "WAIT_TIMEOUT after ${TIMEOUT}s — worker still running. Check again later or keep doing your own work."
        exit 0
      fi
      sleep "$POLL_INTERVAL"
    done
    ;;
esac
