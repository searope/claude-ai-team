<#
PreToolUse hook for Edit, Write and NotebookEdit.

Refuses a write under a skills or agents folder, in ~/.claude or in this
repository, unless the file belongs to a skill or agent type named in
team.json. Writes anywhere else are not this hook's concern and pass through.
#>
$ErrorActionPreference = 'Stop'

function Deny([string]$Reason) {
    @{
        hookSpecificOutput = @{
            hookEventName            = 'PreToolUse'
            permissionDecision       = 'deny'
            permissionDecisionReason = $Reason
        }
    } | ConvertTo-Json -Compress -Depth 3
    exit 0
}

try {
    $call = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $target = $call.tool_input.file_path ?? $call.tool_input.notebook_path
    if (-not $target) { exit 0 }
    $path = [IO.Path]::GetFullPath($target, ($call.cwd ?? (Get-Location).Path))

    $repo = Split-Path (Split-Path $PSScriptRoot)
    foreach ($root in (Join-Path $HOME '.claude'), $repo) {
        foreach ($kind in 'skills', 'agents') {
            $dir = (Join-Path $root $kind) + [IO.Path]::DirectorySeparatorChar
            if (-not $path.StartsWith($dir, [StringComparison]::OrdinalIgnoreCase)) { continue }

            $rel = $path.Substring($dir.Length)
            $team = Get-Content (Join-Path $repo 'team.json') -Raw | ConvertFrom-Json
            $inTeam = if ($kind -eq 'skills') { ($rel -split '[\\/]')[0] -in $team.skills }
                      else { $rel -in $team.agents }
            if ($inTeam) { exit 0 }
            Deny ("$path is not part of the AI team. Only the skills and agent types named in team.json " +
                  "may be written here. Adding one needs the user's explicit request; see 'Adding a role' " +
                  "in README.md.")
        }
    }
    exit 0
} catch {
    Deny "The team-scope hook failed, so the write was refused: $_"
}
