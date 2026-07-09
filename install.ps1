# install.ps1 - install the fleet-delegation skill on Windows (PowerShell).
#
# One-liner (no checkout needed - auto-detects your installed agents):
#   irm https://raw.githubusercontent.com/adam-N-singh/fleet/main/install.ps1 | iex
#
# Usage:
#   .\install.ps1                 -> auto-detect installed agents, install for each
#   .\install.ps1 claude          -> $HOME\.claude\skills\fleet-delegation
#   .\install.ps1 codex           -> $HOME\.codex\skills\fleet-delegation
#   .\install.ps1 gemini          -> $HOME\.gemini\skills\fleet-delegation
#   .\install.ps1 antigravity     -> $HOME\.gemini\antigravity\skills\fleet-delegation
#   .\install.ps1 -Dir <path>     -> <path>\fleet-delegation (any other agent)
#   Add -Project to install into the current repo's skills dir instead
#   (claude: .claude\skills, codex/others: .agents\skills).
#
# Auto-detect prefers the full Claude Code plugin (adds /dispatch,
# /fleet-status, /fleet-init) when the claude CLI is available, falling back
# to a plain skill copy. Explicit ".\install.ps1 claude" copies the skill only.
#
# Runtime note: the skill's scripts run under bash (Git Bash, which Git for
# Windows provides) and need Python on PATH. "python" is enough - the scripts
# fall back automatically when "python3" doesn't exist.
#
# NOTE for contributors: keep this file ASCII-only. Windows PowerShell 5.1
# reads BOM-less files as ANSI, and multi-byte punctuation (em dashes, curly
# quotes) decodes into characters that break string parsing.

param(
    [Parameter(Position = 0)]
    [string]$Target,
    [string]$Dir,
    [switch]$Project
)

$ErrorActionPreference = "Stop"

# Validated manually (not via [ValidateSet]) so the script also runs when
# piped through Invoke-Expression by the one-liner above.
if ($Target -and $Target -notin @("claude", "codex", "gemini", "antigravity")) {
    Write-Error "unknown target '$Target'; use: claude | codex | gemini | antigravity | -Dir <path>"
}

$Repo = "https://github.com/adam-N-singh/fleet.git"
if ($env:FLEET_REPO) { $Repo = $env:FLEET_REPO }

# Piped through iex, or run outside a checkout? Clone to a temp dir and rerun.
$Here = $null
if ($PSCommandPath) { $Here = Split-Path -Parent $PSCommandPath }
if (-not $Here -or -not (Test-Path (Join-Path $Here "skills\fleet-delegation"))) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Error "git is required for the one-line install (install Git for Windows first)"
    }
    $Tmp = Join-Path $env:TEMP ("fleet-install-" + [System.Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
    try {
        Write-Host "Fetching fleet from $Repo ..."
        git clone --quiet --depth 1 $Repo (Join-Path $Tmp "fleet")
        if ($LASTEXITCODE -ne 0) { Write-Error "git clone failed" }
        & (Join-Path $Tmp "fleet\install.ps1") @PSBoundParameters
    } finally {
        Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
    }
    return
}
$Src = Join-Path $Here "skills\fleet-delegation"

function Install-Skill([string]$DestBase) {
    $Dest = Join-Path $DestBase "fleet-delegation"
    New-Item -ItemType Directory -Force -Path $DestBase | Out-Null
    if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
    Copy-Item -Recurse -Force $Src $Dest
    Write-Host "INSTALLED $Dest"
}

function Install-ClaudePlugin {
    $listed = ""
    try { $listed = (claude plugin list) -join "`n" } catch {}
    if ($listed -match "fleet@fleet-marketplace") {
        Write-Host "Claude Code: fleet plugin already installed"
        return
    }
    Write-Host "Claude Code: installing the fleet plugin (adds /dispatch, /fleet-status, /fleet-init) ..."
    $markets = ""
    try { $markets = (claude plugin marketplace list) -join "`n" } catch {}
    if ($markets -notmatch "fleet-marketplace") {
        claude plugin marketplace add $Repo
    }
    claude plugin install fleet@fleet-marketplace
    if ($LASTEXITCODE -eq 0) {
        Write-Host "INSTALLED fleet plugin for Claude Code (restart Claude Code to load it)"
    } else {
        Write-Warning "plugin install failed; falling back to a plain skill copy"
        Install-Skill (Join-Path $HOME ".claude\skills")
    }
}

# Auto-detect when no target was given.
$Targets = @()
$Auto = $false
if ($Dir) {
    $Targets += "dir"
} elseif ($Target) {
    $Targets += $Target
} else {
    $Auto = $true
    if (Get-Command claude -ErrorAction SilentlyContinue) { $Targets += "claude" }
    if ((Get-Command codex -ErrorAction SilentlyContinue) -or (Test-Path (Join-Path $HOME ".codex"))) { $Targets += "codex" }
    if (Get-Command gemini -ErrorAction SilentlyContinue) { $Targets += "gemini" }
    if (Test-Path (Join-Path $HOME ".gemini\antigravity")) { $Targets += "antigravity" }
    if ($Targets.Count -eq 0) {
        Write-Error "no supported agent detected; specify one: claude | codex | gemini | antigravity | -Dir <path>"
    }
    Write-Host ("Detected agents: " + ($Targets -join ", "))
}

foreach ($T in $Targets) {
    switch ($T) {
        "dir" { Install-Skill $Dir }
        "claude" {
            if ($Auto -and -not $Project -and (Get-Command claude -ErrorAction SilentlyContinue)) {
                Install-ClaudePlugin
            } elseif ($Project) {
                Install-Skill ".claude\skills"
            } else {
                Install-Skill (Join-Path $HOME ".claude\skills")
            }
        }
        default {
            if ($Project) {
                Install-Skill ".agents\skills"
            } else {
                $Base = switch ($T) {
                    "codex"       { Join-Path $HOME ".codex\skills" }
                    "gemini"      { Join-Path $HOME ".gemini\skills" }
                    "antigravity" { Join-Path $HOME ".gemini\antigravity\skills" }
                }
                Install-Skill $Base
            }
        }
    }
}

Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Create your provider registry: ask your agent to set it up per the"
Write-Host "     skill's references/providers-guide.md (Claude Code: /fleet-init), or"
Write-Host "     copy the skill's config\providers.example.json to $HOME\.fleet\providers.json"
Write-Host "     and edit it."
Write-Host "  2. Validate: python <skills-dir>\fleet-delegation\scripts\registry.py validate"
Write-Host "  3. Ensure Git for Windows (for Git Bash) and Python are installed -"
Write-Host "     the skill's scripts run under bash at dispatch time."
Write-Host "  4. If your agent doesn't discover the skill, check its docs for the"
Write-Host "     skills location and rerun with -Dir <that-path>."
