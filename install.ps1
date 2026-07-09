# install.ps1 — install the fleet-delegation skill on Windows (PowerShell).
#
# Usage:
#   .\install.ps1 claude          -> $HOME\.claude\skills\fleet-delegation
#   .\install.ps1 codex           -> $HOME\.codex\skills\fleet-delegation
#   .\install.ps1 gemini          -> $HOME\.gemini\skills\fleet-delegation
#   .\install.ps1 antigravity     -> $HOME\.gemini\antigravity\skills\fleet-delegation
#   .\install.ps1 -Dir <path>     -> <path>\fleet-delegation (any other agent)
#   Add -Project to install into the current repo's skills dir instead
#   (claude: .claude\skills, codex/others: .agents\skills).
#
# Claude Code users: prefer the plugin install (README) — it adds the
# /dispatch, /fleet-status, and /fleet-init commands.
#
# Runtime note: the skill's scripts run under bash (Git Bash, which Git for
# Windows provides) and need Python on PATH. `python` is enough — the scripts
# fall back automatically when `python3` doesn't exist.

param(
    [Parameter(Position = 0)]
    [ValidateSet("claude", "codex", "gemini", "antigravity")]
    [string]$Target,
    [string]$Dir,
    [switch]$Project
)

$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Src = Join-Path $Here "skills\fleet-delegation"
if (-not (Test-Path $Src)) { Write-Error "skill source not found at $Src"; exit 1 }

if ($Dir) {
    $DestBase = $Dir
} elseif ($Target) {
    if ($Project) {
        $DestBase = if ($Target -eq "claude") { ".claude\skills" } else { ".agents\skills" }
    } else {
        $DestBase = switch ($Target) {
            "claude"      { Join-Path $HOME ".claude\skills" }
            "codex"       { Join-Path $HOME ".codex\skills" }
            "gemini"      { Join-Path $HOME ".gemini\skills" }
            "antigravity" { Join-Path $HOME ".gemini\antigravity\skills" }
        }
    }
} else {
    Write-Error "specify a target: claude | codex | gemini | antigravity | -Dir <path>"
    exit 2
}

$Dest = Join-Path $DestBase "fleet-delegation"
New-Item -ItemType Directory -Force -Path $DestBase | Out-Null
if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
Copy-Item -Recurse -Force $Src $Dest

Write-Host "INSTALLED $Dest"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Create your provider registry: copy $Dest\config\providers.example.json"
Write-Host "     to $HOME\.fleet\providers.json (or .\.fleet\providers.json in a project)"
Write-Host "     and edit it, or ask your agent to set it up per the providers-guide."
Write-Host "  2. Validate: python $Dest\scripts\registry.py validate"
Write-Host "  3. Ensure Git for Windows (for Git Bash) and Python are installed —"
Write-Host "     the skill's scripts run under bash at dispatch time."
Write-Host "  4. If your agent doesn't discover the skill, check its docs for the"
Write-Host "     skills location and rerun with -Dir <that-path>."
