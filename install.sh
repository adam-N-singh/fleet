#!/usr/bin/env bash
# install.sh — install the fleet-delegation skill for any Agent Skills-
# compatible coding agent (the SKILL.md open standard, agentskills.io).
#
# One-liner (no checkout needed — auto-detects your installed agents):
#   curl -fsSL https://raw.githubusercontent.com/adam-N-singh/fleet/main/install.sh | bash
#
# Usage:
#   ./install.sh               -> auto-detect installed agents, install for each
#   ./install.sh claude        -> ~/.claude/skills/fleet-delegation
#   ./install.sh codex         -> ~/.codex/skills/fleet-delegation
#   ./install.sh gemini        -> ~/.gemini/skills/fleet-delegation
#   ./install.sh antigravity   -> ~/.gemini/antigravity/skills/fleet-delegation
#   ./install.sh --dir <path>  -> <path>/fleet-delegation (any other agent)
#   Add --project to install into the current repo's skills dir instead of
#   the user-level dir (claude: .claude/skills, codex/others: .agents/skills).
#
# Auto-detect prefers the full Claude Code plugin (adds /dispatch,
# /fleet-status, /fleet-init) when the claude CLI is available, falling back
# to a plain skill copy. Explicit `./install.sh claude` copies the skill only.
set -euo pipefail

REPO="${FLEET_REPO:-https://github.com/adam-N-singh/fleet.git}"

# Piped from curl, or run outside a checkout? Clone to a temp dir and rerun.
SELF="${BASH_SOURCE[0]:-}"
HERE=""
[[ -n "$SELF" && -f "$SELF" ]] && HERE="$(cd "$(dirname "$SELF")" && pwd)"
if [[ -z "$HERE" || ! -d "$HERE/skills/fleet-delegation" ]]; then
  command -v git >/dev/null 2>&1 || { echo "ERROR: git is required for the one-line install" >&2; exit 1; }
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  echo "Fetching fleet from $REPO ..."
  git clone --quiet --depth 1 "$REPO" "$TMP/fleet"
  bash "$TMP/fleet/install.sh" "$@"
  exit
fi
SRC="$HERE/skills/fleet-delegation"

TARGETS=() PROJECT="no" DEST_BASE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    claude|codex|gemini|antigravity) TARGETS+=("$1"); shift ;;
    --dir) DEST_BASE="$2"; TARGETS+=("dir"); shift 2 ;;
    --project) PROJECT="yes"; shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
  esac
done

install_to() {  # $1 = destination skills dir
  local dest="$1/fleet-delegation"
  mkdir -p "$1"
  rm -rf "$dest"
  cp -R "$SRC" "$dest"
  chmod +x "$dest"/scripts/*.sh "$dest"/scripts/*.py "$dest"/scripts/adapters/*.sh 2>/dev/null || true
  echo "INSTALLED $dest"
}

install_claude_plugin() {
  if claude plugin list 2>/dev/null | grep -q 'fleet@fleet-marketplace'; then
    echo "Claude Code: fleet plugin already installed"
    return 0
  fi
  echo "Claude Code: installing the fleet plugin (adds /dispatch, /fleet-status, /fleet-init) ..."
  claude plugin marketplace list 2>/dev/null | grep -q 'fleet-marketplace' \
    || claude plugin marketplace add "$REPO"
  if claude plugin install fleet@fleet-marketplace; then
    echo "INSTALLED fleet plugin for Claude Code (restart Claude Code to load it)"
  else
    echo "WARN: plugin install failed; falling back to a plain skill copy" >&2
    install_to "$HOME/.claude/skills"
  fi
}

# Auto-detect when no target was given.
AUTO="no"
if [[ ${#TARGETS[@]} -eq 0 ]]; then
  AUTO="yes"
  command -v claude >/dev/null 2>&1 && TARGETS+=("claude")
  { command -v codex >/dev/null 2>&1 || [[ -d "$HOME/.codex" ]]; } && TARGETS+=("codex")
  command -v gemini >/dev/null 2>&1 && TARGETS+=("gemini")
  [[ -d "$HOME/.gemini/antigravity" ]] && TARGETS+=("antigravity")
  if [[ ${#TARGETS[@]} -eq 0 ]]; then
    echo "ERROR: no supported agent detected; specify one: claude | codex | gemini | antigravity | --dir <path>" >&2
    exit 2
  fi
  echo "Detected agents: ${TARGETS[*]}"
fi

for TARGET in "${TARGETS[@]}"; do
  case "$TARGET" in
    dir) install_to "$DEST_BASE" ;;
    claude)
      if [[ "$AUTO" == "yes" && "$PROJECT" == "no" ]] && command -v claude >/dev/null 2>&1; then
        install_claude_plugin
      elif [[ "$PROJECT" == "yes" ]]; then
        install_to ".claude/skills"
      else
        install_to "$HOME/.claude/skills"
      fi ;;
    codex|gemini|antigravity)
      if [[ "$PROJECT" == "yes" ]]; then
        install_to ".agents/skills"
      else
        case "$TARGET" in
          codex)       install_to "$HOME/.codex/skills" ;;
          gemini)      install_to "$HOME/.gemini/skills" ;;
          antigravity) install_to "$HOME/.gemini/antigravity/skills" ;;
        esac
      fi ;;
  esac
done

echo ""
echo "Next steps:"
echo "  1. Create your provider registry: ask your agent to set it up per the"
echo "     skill's references/providers-guide.md (Claude Code: /fleet-init), or"
echo "     copy the skill's config/providers.example.json to ~/.fleet/providers.json"
echo "     and edit it."
echo "  2. Validate: python3 <skills-dir>/fleet-delegation/scripts/registry.py validate"
echo "  3. Skill directory paths vary by agent and version — if your agent"
echo "     doesn't discover the skill, check its docs for the skills location"
echo "     and rerun with --dir <that-path>."
