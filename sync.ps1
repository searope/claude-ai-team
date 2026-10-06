<#
Copies the AI team between this repository and Claude Code's own folders.

  ./sync.ps1 check     list the files that differ; changes nothing
  ./sync.ps1 save      Claude Code's folders -> this repository
  ./sync.ps1 install   this repository -> Claude Code's folders

Only the skills and agent types named in team.json are touched. Nothing else
in ~/.claude (other skills, credentials, transcripts) is read or copied.
#>
param(
    [Parameter(Mandatory)][ValidateSet('check', 'save', 'install')][string]$Mode,
    [string]$ClaudeDir = (Join-Path $HOME '.claude')
)

$ErrorActionPreference = 'Stop'

# The team roster. The write guard in .claude/hooks/team-scope.ps1 reads the same file.
$Team = Get-Content (Join-Path $PSScriptRoot 'team.json') -Raw | ConvertFrom-Json
$Skills = @($Team.skills)
$Agents = @($Team.agents)

# A malformed roster stops the script: an empty name would make it walk every skill there is.
foreach ($name in $Skills + $Agents) {
    if ($name -isnot [string] -or $name -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') {
        throw "team.json holds '$name', which is not the name of a skill folder or an agent file. Nothing was done."
    }
}
if (-not $Skills -or -not $Agents) { throw 'team.json names no skills or no agent types. Nothing was done.' }

# The roster entries that have no file under a root.
function Get-MissingEntries([string]$Root) {
    foreach ($skill in $Skills) {
        if (-not (Test-Path (Join-Path $Root "skills/$skill/SKILL.md"))) { "skills/$skill" }
    }
    foreach ($agent in $Agents) {
        if (-not (Test-Path (Join-Path $Root "agents/$agent"))) { "agents/$agent" }
    }
}

# The team's files under a root, as relative paths like "skills/team-lead/SKILL.md".
function Get-TeamFiles([string]$Root) {
    if (-not (Test-Path $Root)) { return @() }
    $full = (Resolve-Path $Root).Path.TrimEnd('\', '/')
    $files = @()
    foreach ($skill in $Skills) {
        $dir = Join-Path $full "skills/$skill"
        if (Test-Path $dir) {
            $files += Get-ChildItem $dir -Recurse -File -Force |
                ForEach-Object { $_.FullName.Substring($full.Length + 1).Replace('\', '/') }
        }
    }
    foreach ($agent in $Agents) {
        if (Test-Path (Join-Path $full "agents/$agent")) { $files += "agents/$agent" }
    }
    return $files
}

function Get-ContentHash([string]$Path) {
    if (Test-Path $Path) { return (Get-FileHash $Path -Algorithm SHA256).Hash }
    return $null
}

# One line for each file that is not the same in the repository and in Claude Code's folders.
function Compare-Team([string]$Repo, [string]$Live) {
    $all = @(Get-TeamFiles $Repo) + @(Get-TeamFiles $Live) | Sort-Object -Unique
    foreach ($rel in $all) {
        $inRepo = Get-ContentHash (Join-Path $Repo $rel)
        $inLive = Get-ContentHash (Join-Path $Live $rel)
        if ($inRepo -eq $inLive) { continue }
        if (-not $inRepo) { "only in ${Live}: $rel" }
        elseif (-not $inLive) { "only in the repository: $rel" }
        else { "differs: $rel" }
    }
}

# Copies the team's files from one root to the other. A file that exists only in
# the destination is removed when $RemoveExtra is set, and reported otherwise.
function Copy-Team([string]$From, [string]$To, [bool]$RemoveExtra) {
    $source = @(Get-TeamFiles $From)
    if (-not $source) { throw "No AI team files found in $From. Nothing was copied." }
    $missing = @(Get-MissingEntries $From)
    if ($missing) { throw "$From lacks $($missing -join ', '), named in team.json. Nothing was copied." }
    foreach ($rel in $source) {
        $dest = Join-Path $To $rel
        New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
        Copy-Item (Join-Path $From $rel) $dest -Force
    }
    foreach ($rel in @(Get-TeamFiles $To)) {
        if ($rel -in $source) { continue }
        if ($RemoveExtra) {
            Remove-Item (Join-Path $To $rel) -Force
            "removed, no longer in ${From}: $rel"
        } else {
            "left in place, not in the repository: $rel"
        }
    }
}

$Repo = $PSScriptRoot

switch ($Mode) {
    'check' {
        $diff = @(Get-MissingEntries $Repo | ForEach-Object { "named in team.json, missing in the repository: $_" })
        $diff += @(Compare-Team $Repo $ClaudeDir)
        if ($diff) { $diff; exit 1 }
        "The repository and $ClaudeDir match."
    }
    'save' {
        Copy-Team $ClaudeDir $Repo $true
        "Saved from $ClaudeDir. Review with 'git status', then commit and push."
    }
    'install' {
        Copy-Team $Repo $ClaudeDir $false
        "Installed into $ClaudeDir."
    }
}
