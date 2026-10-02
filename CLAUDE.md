# Claude AI team

This repository is the saved copy of the AI team: the skills and agent types named in `team.json`, the pipeline
rules in `skills/team-lead/ai-team-pipeline.md`, and `sync.ps1`. Sessions here exist to maintain the team and to
explore ways to improve and extend it.

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

The live copies are in `~/.claude/skills` and `~/.claude/agents`. Edit them there, then run `pwsh ./sync.ps1 save`
and commit. When the pipeline rules change, raise `Pipeline Version`. When a skill changes, raise its
`metadata.version`.
