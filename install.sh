#!/usr/bin/env bash
# install.sh — install the fleet-delegation skill for any Agent Skills-
# compatible coding agent (the SKILL.md open standard, agentskills.io).
#
# Usage:
#   ./install.sh claude        -> ~/.claude/skills/fleet-delegation
#   ./install.sh codex         -> ~/.codex/skills/fleet-delegation
#   ./install.sh gemini        -> ~/.gemini/skills/fleet-delegation
#   ./install.sh antigravity   -> ~/.gemini/antigravity/skills/fleet-delegation
#   ./install.sh --dir <path>  -> <path>/fleet-delegation (any other agent)
#   Add --project to install into the current repo's skills dir instead of
#   the user-level dir (claude: .claude/skills, codex/others: .agents/skills).
#
# Claude Code users: prefer the plugin install (README) — it adds the
# /dispatch, /fleet-status, and /fleet-init commands. This script installs
# the skill alone, which is fully functional everywhere.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/skills/fleet-delegation"
[[ -d "$SRC" ]] || { echo "ERROR: skill source not found at $SRC" >&2; exit 1; }

TARGET="" PROJECT="no"
while [[ $# -gt 0 ]]; do
  case "$1" in
    claude|codex|gemini|antigravity) TARGET="$1"; shift ;;
    --dir) DEST_BASE="$2"; TARGET="dir"; shift 2 ;;
    --project) PROJECT="yes"; shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$TARGET" ]] || { echo "ERROR: specify a target: claude | codex | gemini | antigravity | --dir <path>" >&2; exit 2; }

if [[ "$TARGET" != "dir" ]]; then
  if [[ "$PROJECT" == "yes" ]]; then
    case "$TARGET" in
      claude) DEST_BASE=".claude/skills" ;;
      *)      DEST_BASE=".agents/skills" ;;
    esac
  else
    case "$TARGET" in
      claude)      DEST_BASE="$HOME/.claude/skills" ;;
      codex)       DEST_BASE="$HOME/.codex/skills" ;;
      gemini)      DEST_BASE="$HOME/.gemini/skills" ;;
      antigravity) DEST_BASE="$HOME/.gemini/antigravity/skills" ;;
    esac
  fi
fi

DEST="$DEST_BASE/fleet-delegation"
mkdir -p "$DEST_BASE"
rm -rf "$DEST"
cp -R "$SRC" "$DEST"
chmod +x "$DEST"/scripts/*.sh "$DEST"/scripts/*.py "$DEST"/scripts/adapters/*.sh 2>/dev/null || true

echo "INSTALLED $DEST"
echo ""
echo "Next steps:"
echo "  1. Create your provider registry: copy $DEST/config/providers.example.json"
echo "     to ~/.fleet/providers.json (or ./.fleet/providers.json) and edit it,"
echo "     or ask your agent to set it up per $DEST/references/providers-guide.md."
echo "  2. Validate: python3 $DEST/scripts/registry.py validate"
echo "  3. Skill directory paths vary by agent and version — if your agent"
echo "     doesn't discover the skill, check its docs for the skills location"
echo "     and rerun with --dir <that-path>."
