#!/usr/bin/env bash
# fleet-dispatch.sh — launch a background worker on any configured provider.
#
# Usage:
#   fleet-dispatch.sh --provider <name> --brief <file>
#                     [--model <override>] [--effort <level>] [--cwd <dir>]
#                     [--resume <session_id>]
#
# Output (machine-readable, one field per line):
#   DISPATCHED + TASK_ID/PROVIDER/MODEL/SESSION/LOG/CHECK   worker running
#   PROVIDER_UNAVAILABLE <provider>: <reason>   binary missing / cooldown / disabled
#   BUSY <provider>: <reason>                   concurrency cap reached
#   ERROR: <reason>                             bad input
#   (a terminal STATUS block)                   worker finished within ~10s
#
# On PROVIDER_UNAVAILABLE or BUSY, the supervisor should try the next
# provider in the routing cascade, and only absorb the task when no
# providers remain.
#
# Environment overrides:
#   FLEET_RUNS_DIR (default .fleet-runs)   FLEET_MAX_WORKERS_TOTAL (default 4)
#   FLEET_PROVIDERS (registry path)        FLEET_CODEX_SANDBOX (default workspace-write)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Windows-friendly python resolution: Git Bash usually has `python`, not `python3`.
PY="${FLEET_PYTHON:-}"
if [[ -z "$PY" ]]; then
  if command -v python3 >/dev/null 2>&1; then PY="python3"; else PY="python"; fi
fi
RUNS_DIR="${FLEET_RUNS_DIR:-.fleet-runs}"
MAX_TOTAL="${FLEET_MAX_WORKERS_TOTAL:-4}"

PROVIDER="" BRIEF="" MODEL="" EFFORT="" WORKDIR="$(pwd)" RESUME=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider) PROVIDER="$2"; shift 2 ;;
    --brief)    BRIEF="$2";    shift 2 ;;
    --model)    MODEL="$2";    shift 2 ;;
    --effort)   EFFORT="$2";   shift 2 ;;
    --cwd)      WORKDIR="$2";  shift 2 ;;
    --resume)   RESUME="$2";   shift 2 ;;
    -h|--help)  grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
  esac
done

REG="${PY} $SCRIPT_DIR/registry.py"

# ---------- preflight --------------------------------------------------------

[[ -n "$PROVIDER" ]] || { echo "ERROR: --provider <name> is required (see: ${PY} $SCRIPT_DIR/registry.py list)" >&2; exit 2; }
if [[ -z "$BRIEF" || ! -s "$BRIEF" ]]; then
  echo "ERROR: --brief <file> is required and must be a non-empty file" >&2; exit 2
fi
[[ -d "$WORKDIR" ]] || { echo "ERROR: --cwd $WORKDIR is not a directory" >&2; exit 2; }
if ! git -C "$WORKDIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: $WORKDIR is not inside a git repository (required so worker changes stay reviewable)" >&2
  exit 2
fi

$REG path >/dev/null || exit 1

ENABLED="$($REG get "$PROVIDER" enabled false)"
if [[ "$ENABLED" != "true" ]]; then
  echo "PROVIDER_UNAVAILABLE $PROVIDER: disabled or not in registry. Try the next provider in the cascade."
  exit 3
fi

ADAPTER="$($REG get "$PROVIDER" adapter "")"
ADAPTER_FILE="$SCRIPT_DIR/adapters/$ADAPTER.sh"
if [[ ! -f "$ADAPTER_FILE" ]]; then
  echo "ERROR: adapter '$ADAPTER' for provider '$PROVIDER' not found at $ADAPTER_FILE" >&2
  exit 2
fi
# shellcheck source=/dev/null
source "$ADAPTER_FILE"

if ! command -v "$ADAPTER_BIN" >/dev/null 2>&1; then
  echo "PROVIDER_UNAVAILABLE $PROVIDER: '$ADAPTER_BIN' CLI is not installed or not on PATH. Try the next provider in the cascade."
  exit 3
fi

if [[ -n "$RESUME" && "$ADAPTER_SUPPORTS_RESUME" != "yes" ]]; then
  echo "ERROR: provider '$PROVIDER' does not support resume. Dispatch a fresh brief that summarizes the prior round." >&2
  exit 2
fi

[[ -n "$MODEL" ]] || MODEL="$($REG get "$PROVIDER" default_model "")"

mkdir -p "$RUNS_DIR"
RUNS_DIR="$(cd "$RUNS_DIR" && pwd)"

# Per-provider rate-limit cooldown
COOLDOWN_FILE="$RUNS_DIR/cooldown-$PROVIDER"
if [[ -f "$COOLDOWN_FILE" ]]; then
  NOW="$(date +%s)"
  UNTIL="$(cat "$COOLDOWN_FILE" 2>/dev/null || echo 0)"
  if [[ "$UNTIL" =~ ^[0-9]+$ ]] && (( NOW < UNTIL )); then
    echo "PROVIDER_UNAVAILABLE $PROVIDER: rate_limited (cooldown active, $(( UNTIL - NOW ))s remaining). Try the next provider in the cascade."
    exit 4
  fi
fi

# Concurrency: per-provider cap from registry, plus a global cap
MAX_PROVIDER="$($REG get "$PROVIDER" max_workers 2)"
LIVE_TOTAL=0
LIVE_PROVIDER=0
for d in "$RUNS_DIR"/*/; do
  [[ -d "$d" && -f "$d/pid" && ! -f "$d/exit-code" ]] || continue
  WPID="$(cat "$d/pid" 2>/dev/null || true)"
  if [[ -n "$WPID" ]] && kill -0 "$WPID" 2>/dev/null; then
    LIVE_TOTAL=$(( LIVE_TOTAL + 1 ))
    TP="$(${PY} -c "import json,sys;print(json.load(open(sys.argv[1])).get('provider',''))" "$d/meta.json" 2>/dev/null || true)"
    [[ "$TP" == "$PROVIDER" ]] && LIVE_PROVIDER=$(( LIVE_PROVIDER + 1 ))
  fi
done
if (( LIVE_PROVIDER >= MAX_PROVIDER )); then
  echo "BUSY $PROVIDER: $LIVE_PROVIDER workers running (provider max $MAX_PROVIDER). Try another provider or wait."
  exit 5
fi
if (( LIVE_TOTAL >= MAX_TOTAL )); then
  echo "BUSY fleet: $LIVE_TOTAL workers running across all providers (max $MAX_TOTAL). Wait for one to finish."
  exit 5
fi

# ---------- dispatch ---------------------------------------------------------

TASK_ID="$(date +%Y%m%d-%H%M%S)-$PROVIDER-$$"
TASK_DIR="$RUNS_DIR/$TASK_ID"
mkdir -p "$TASK_DIR"
cp "$BRIEF" "$TASK_DIR/brief.md"

# Snapshot the workspace state BEFORE the worker starts, so diff review can
# distinguish the worker's changes from anything that was already dirty.
{
  echo "revision $(git -C "$WORKDIR" rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "branch $(git -C "$WORKDIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  git -C "$WORKDIR" status --porcelain 2>/dev/null
} > "$TASK_DIR/pre-state" || true

CMD=()
CMD_STDIN="yes"
adapter_build_cmd "$MODEL" "$EFFORT" "$WORKDIR" "$RESUME" "$TASK_DIR/brief.md"

${PY} - "$TASK_DIR/meta.json" "$TASK_ID" "$PROVIDER" "$ADAPTER" "$MODEL" "$ADAPTER_EVENT_FORMAT" <<'PYEOF'
import json, sys, time
_, path, task_id, provider, adapter, model, fmt = sys.argv
json.dump({"task_id": task_id, "provider": provider, "adapter": adapter,
           "model": model, "format": fmt, "started": int(time.time())},
          open(path, "w"))
PYEOF
printf '%s\n' "${CMD[*]}" > "$TASK_DIR/command"

if [[ "$CMD_STDIN" == "yes" ]]; then
  (
    set +e
    cd "$WORKDIR"
    "${CMD[@]}" < "$TASK_DIR/brief.md" > "$TASK_DIR/events.jsonl" 2> "$TASK_DIR/stderr.log"
    echo "$?" > "$TASK_DIR/exit-code"
  ) >/dev/null 2>&1 &
else
  (
    set +e
    cd "$WORKDIR"
    "${CMD[@]}" > "$TASK_DIR/events.jsonl" 2> "$TASK_DIR/stderr.log"
    echo "$?" > "$TASK_DIR/exit-code"
  ) >/dev/null 2>&1 &
fi
WORKER_PID=$!
disown "$WORKER_PID" 2>/dev/null || true
echo "$WORKER_PID" > "$TASK_DIR/pid"

# Wait briefly for a session id, or catch an immediate failure.
SESSION=""
for _ in $(seq 1 20); do
  [[ -f "$TASK_DIR/exit-code" ]] && break
  if [[ -s "$TASK_DIR/events.jsonl" ]]; then
    SESSION="$(${PY} "$SCRIPT_DIR/parse_events.py" "$TASK_DIR/events.jsonl" session --format "$ADAPTER_EVENT_FORMAT" 2>/dev/null || true)"
    [[ -n "$SESSION" ]] && break
  fi
  sleep 0.5
done

if [[ -f "$TASK_DIR/exit-code" ]]; then
  # Invoked via `bash` rather than directly: plugin installs, zip extraction,
  # and Windows checkouts routinely drop the executable bit, and a failed exec
  # here would swallow the terminal status of every fast-failing worker.
  exec bash "$SCRIPT_DIR/fleet-status.sh" "$TASK_ID"
fi

echo "DISPATCHED"
echo "TASK_ID $TASK_ID"
echo "PROVIDER $PROVIDER"
echo "MODEL ${MODEL:-(cli default)}"
echo "SESSION ${SESSION:-pending}"
echo "LOG $TASK_DIR/events.jsonl"
echo "CHECK bash $SCRIPT_DIR/fleet-status.sh $TASK_ID"
