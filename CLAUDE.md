# Claude AI team

This repository is the saved copy of the AI team: the skills and agent types named in `team.json`, the pipeline
rules and the project-file template in `skills/team-lead/`, and `sync.ps1`. Sessions here exist to maintain the
team and to explore ways to improve and extend it.

## Scope

- Work only on the team's skills and agent types, the pipeline rules, `sync.ps1`, and this repository's own files.
- Change nothing else under `~/.claude/skills` or `~/.claude/agents`. `~/.claude/skills/synced` belongs to the
  desktop app. Its skills may be read and called by name, such as `anthropic-skills:skill-creator`, but never
  edited or copied into this repository.
- `.claude/hooks/team-scope.ps1` enforces this for the file tools. Do not work around it with shell commands.

## Improving and extending the team

- Proposing is welcome: new roles, new agent types, changed stages, merged or split skills. Present them as
  proposals, with the reason and the cost.
- Creating is by explicit request only. Add a skill, role or agent type, or edit `team.json`, only after the user
  asks for that specific addition. Then follow "Adding a role" in `README.md`.

## Where edits go

The live copies are in `~/.claude/skills` and `~/.claude/agents`. A file there takes effect at once in every
project that uses the team, including features in flight, and projects hold no copy of the rules. So do not edit
the live copies. The deny rules in `.claude/settings.json` refuse that to the file tools, and `sync.ps1 install` is
the only thing that writes there. Follow "Change the team" in `README.md`:

1. Edit the files in this repository, on a branch.
2. Test them in a scratch project as project-level skills and agent types under other names, with headless
   `claude -p` runs.
3. Install with `pwsh ./sync.ps1 install` only when the user has agreed to go live.
4. Never run `pwsh ./sync.ps1 save` on a branch with changes that are not installed: it overwrites them.

When the pipeline rules change, raise `Pipeline Version`, and the same number in step 1 of `Setup` in `team-lead`.
When a skill changes, raise its `metadata.version`. Keep existing ledgers and handoffs readable.
