#!/usr/bin/env bash
# Integration tests for the provider-agnostic core: registry resolution,
# dispatch preflight, background execution, status classification,
# per-provider cooldown isolation, concurrency caps, and cascade signaling —
# exercised against stub CLIs (tests/stubs/) that mimic each real CLI's
# documented output. No network, no real providers, hermetic HOME.
#
# Run: bash tests/test_dispatch.sh          (from the repo root or anywhere)
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/skills/fleet-delegation/scripts"
STUBS="$ROOT/tests/stubs"

# ---------- tiny assertion harness ------------------------------------------

PASS=0; FAIL=0
pass() { PASS=$((PASS + 1)); echo "  ok  - $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL  - $1"; [ -n "${2:-}" ] && printf '%s\n' "$2" | sed 's/^/        | /'; }

expect_contains() {  # OUTPUT NEEDLE NAME
  if printf '%s' "$1" | grep -qF -- "$2"; then pass "$3"; else fail "$3 (missing: $2)" "$1"; fi
}
expect_not_contains() {
  if printf '%s' "$1" | grep -qF -- "$2"; then fail "$3 (unexpected: $2)" "$1"; else pass "$3"; fi
}
expect_rc() {  # ACTUAL EXPECTED NAME
  if [ "$1" = "$2" ]; then pass "$3"; else fail "$3 (exit $1, wanted $2)"; fi
}

# ---------- hermetic environment --------------------------------------------

# A python that actually works (Windows ships broken store aliases for
# python/python3, so probe by executing, not by command -v).
if [ -z "${FLEET_PYTHON:-}" ]; then
  for cand in python3 python py; do
    if "$cand" -c "pass" >/dev/null 2>&1; then export FLEET_PYTHON="$cand"; break; fi
  done
fi
[ -n "${FLEET_PYTHON:-}" ] || { echo "no working python found"; exit 1; }

WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT

export HOME="$WORK/home"
export USERPROFILE="$HOME"
mkdir -p "$HOME"
export PATH="$STUBS:$PATH"
chmod +x "$STUBS"/* 2>/dev/null || true

REPO="$WORK/repo"
mkdir -p "$REPO"
git -C "$REPO" init -q
echo hello > "$REPO/README.md"
git -C "$REPO" -c user.email=t@t -c user.name=t add -A
git -C "$REPO" -c user.email=t@t -c user.name=t commit -qm init

REG="$WORK/providers.json"
cat > "$REG" <<'EOF'
{
  "providers": {
    "codex":   {"enabled": true,  "adapter": "codex",   "access": "subscription",
                "default_model": "", "max_workers": 1},
    "copilot": {"enabled": true,  "adapter": "copilot", "access": "subscription",
                "default_model": ""},
    "parked":  {"enabled": false, "adapter": "codex",   "access": "subscription"},
    "ghost":   {"enabled": true,  "adapter": "amp",     "access": "api",
                "default_model": ""}
  },
  "routing": {"prefer_order": ["codex", "copilot"]}
}
EOF
export FLEET_PROVIDERS="$REG"

BRIEF="$WORK/brief.md"
echo "# Task: do the stub thing" > "$BRIEF"

dispatch() { bash "$SCRIPTS/fleet-dispatch.sh" "$@" 2>&1; }
status()   { bash "$SCRIPTS/fleet-status.sh" "$@" 2>&1; }
task_id_of() { printf '%s\n' "$1" | sed -n 's/^TASK_ID //p'; }

wait_exit_code() {  # TASK_ID [SECONDS]
  local i deadline="${2:-20}"
  for i in $(seq 1 $((deadline * 2))); do
    [ -f "$REPO/.fleet-runs/$1/exit-code" ] && return 0
    sleep 0.5
  done
  return 1
}

cd "$REPO"

# ---------- preflight failures ----------------------------------------------

OUT="$(FLEET_PROVIDERS="$WORK/nowhere.json" dispatch --provider codex --brief "$BRIEF")"; RC=$?
expect_rc "$RC" 1 "no registry anywhere -> exit 1"

OUT="$(dispatch --provider codex --brief "$WORK/does-not-exist.md")"; RC=$?
expect_rc "$RC" 2 "missing brief -> exit 2"

NONGIT="$WORK/plain"; mkdir -p "$NONGIT"
OUT="$(dispatch --provider codex --brief "$BRIEF" --cwd "$NONGIT")"; RC=$?
expect_rc "$RC" 2 "non-git workdir refused"
expect_contains "$OUT" "not inside a git repository" "non-git error names the reason"

OUT="$(dispatch --provider parked --brief "$BRIEF")"; RC=$?
expect_rc "$RC" 3 "disabled provider -> exit 3"
expect_contains "$OUT" "PROVIDER_UNAVAILABLE" "disabled provider signals cascade"

OUT="$(dispatch --provider ghost --brief "$BRIEF")"; RC=$?
expect_rc "$RC" 3 "missing CLI binary -> exit 3"
expect_contains "$OUT" "not installed" "missing binary names the reason"

OUT="$(dispatch --provider copilot --brief "$BRIEF" --resume some-session)"; RC=$?
expect_rc "$RC" 2 "resume on non-resumable adapter refused"
expect_contains "$OUT" "does not support resume" "resume refusal explains itself"

# ---------- happy path: dispatch, background execution, DONE ----------------

OUT="$(dispatch --provider codex --brief "$BRIEF")"
expect_contains "$OUT" "DISPATCHED" "codex dispatch launches"
expect_contains "$OUT" "SESSION th_stub1" "session id extracted while running"
TID="$(task_id_of "$OUT")"

for f in brief.md meta.json pid command pre-state; do
  [ -f "$REPO/.fleet-runs/$TID/$f" ] && pass "task dir has $f" || fail "task dir has $f"
done

OUT="$(status "$TID")"
expect_contains "$OUT" "STATUS RUNNING" "worker classified RUNNING while alive"

wait_exit_code "$TID" || fail "worker never finished"
OUT="$(status "$TID")"
expect_contains "$OUT" "STATUS DONE" "clean exit + completed -> DONE"
expect_contains "$OUT" "stub codex finished the task" "final message surfaced"
expect_contains "$OUT" "input_tokens" "usage surfaced for the ledger"
expect_contains "$OUT" "ledger.py append" "DONE prompts an outcome record"

# text-format provider end to end (also proves argv-brief CMD_STDIN=no path)
OUT="$(dispatch --provider copilot --brief "$BRIEF")"
expect_contains "$OUT" "STATUS DONE" "copilot (text format) completes"
expect_contains "$OUT" "stub copilot did the thing" "text final message surfaced"

# ---------- failure classification ------------------------------------------

OUT="$(STUB_MODE=fail dispatch --provider codex --brief "$BRIEF")"
expect_contains "$OUT" "STATUS FAILED" "generic failure -> FAILED"
expect_contains "$OUT" "boom" "stderr surfaced on failure"

OUT="$(STUB_MODE=auth dispatch --provider codex --brief "$BRIEF")"
expect_contains "$OUT" "STATUS AUTH_ERROR" "auth pattern -> AUTH_ERROR"
[ ! -f "$REPO/.fleet-runs/cooldown-codex" ] \
  && pass "auth error sets no cooldown" || fail "auth error sets no cooldown"

# ---------- concurrency caps -------------------------------------------------

OUT="$(STUB_MODE=hang dispatch --provider codex --brief "$BRIEF")"
HANG_TID="$(task_id_of "$OUT")"
expect_contains "$OUT" "DISPATCHED" "hang worker launches"

OUT="$(dispatch --provider codex --brief "$BRIEF")"; RC=$?
expect_rc "$RC" 5 "per-provider cap -> BUSY exit 5"
expect_contains "$OUT" "BUSY codex" "BUSY names the provider"

OUT="$(FLEET_MAX_WORKERS_TOTAL=1 dispatch --provider copilot --brief "$BRIEF")"; RC=$?
expect_rc "$RC" 5 "global cap -> BUSY exit 5"
expect_contains "$OUT" "BUSY fleet" "global BUSY names the fleet"

# INCOMPLETE: worker process killed without writing an exit code
HANG_PID="$(cat "$REPO/.fleet-runs/$HANG_TID/pid")"
kill "$HANG_PID" 2>/dev/null; sleep 1
OUT="$(status "$HANG_TID")"
expect_contains "$OUT" "STATUS INCOMPLETE" "dead worker without exit code -> INCOMPLETE"

# ---------- rate limits, cooldown, cascade isolation ------------------------

OUT="$(STUB_MODE=rate dispatch --provider codex --brief "$BRIEF")"
expect_contains "$OUT" "STATUS RATE_LIMITED" "rate pattern -> RATE_LIMITED"
expect_contains "$OUT" "COOLDOWN_UNTIL" "cooldown announced"
[ -f "$REPO/.fleet-runs/cooldown-codex" ] \
  && pass "cooldown file written" || fail "cooldown file written"

OUT="$(dispatch --provider codex --brief "$BRIEF")"; RC=$?
expect_rc "$RC" 4 "cooldown blocks re-dispatch (exit 4)"
expect_contains "$OUT" "rate_limited" "cooldown block signals cascade"

OUT="$(dispatch --provider copilot --brief "$BRIEF")"
expect_contains "$OUT" "STATUS DONE" "cooldown is per-provider: copilot unaffected"

OUT="$(status --all)"
expect_contains "$OUT" "COOLDOWN_ACTIVE codex" "--all reports active cooldowns"

# ---------- summary ----------------------------------------------------------

echo ""
echo "$PASS passed, $FAIL failed"
[ "$FAIL" = "0" ]
