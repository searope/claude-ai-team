# Claude AI team

Nine Claude Code skills and two agent types that work together as a software team, and the pipeline rules they
follow. A feature goes through nine stages: spec, copy, UI spec, architecture, code, infra, tests, security review
and merge.

## What is here

- `skills/`: the nine skills. Each `SKILL.md` carries its own version.
  - `team-lead`: the orchestrator. It runs the stages, keeps the ledger and stops for your approval.
  - `product-manager`, `copywriter`, `ui-designer`, `system-architect`: write the spec, the copy, the UI spec and
    the ADR.
  - `software-engineer`, `devops-engineer`, `test-engineer`: write the code, the infra and the tests.
  - `security-reviewer`: audits the real diff. It is read-only.
- `skills/team-lead/ai-team-pipeline.md`: the master copy of the pipeline rules. `team-lead` installs a copy into
  each project as `.claude/ai-team-pipeline.md`, where the project sets its own paths and overrides.
- `agents/`: two agent types that limit which tools a skill gets.
  - `ai-team-author`: file tools and no shell. Used by `copywriter`, `ui-designer` and `system-architect`.
  - `ai-team-auditor`: read and shell, no file writing. Used by `security-reviewer`.
- `sync.ps1`: copies these files to and from Claude Code's own folders.

## Where the live copy is

Claude Code reads skills from `~/.claude/skills/` and agent types from `~/.claude/agents/`. This repository holds a
copy of those files. Changes are made in `~/.claude` and then saved here.

`sync.ps1` touches only the nine skills and two agent types it names. It never reads or copies anything else in
`~/.claude`, such as other skills, credentials or transcripts.

## Install on a machine

```
git clone https://github.com/searope/claude-ai-team.git
cd claude-ai-team
pwsh ./sync.ps1 install
```

Then, in any project, start a feature with `/team-lead <request>`. On its first run in a project `team-lead`
installs the pipeline rules and adds the import line to the project's `CLAUDE.md`. The project must be a git
repository; `team-lead` creates one if needed.

`install` overwrites the team's files in `~/.claude` with the ones from this repository. It does not delete
anything: a file that is in `~/.claude` but not here is reported and left in place.

## Save a change

After a skill, an agent type or the master rules change in `~/.claude`:

```
pwsh ./sync.ps1 check
pwsh ./sync.ps1 save
git status
```

`check` lists the files that differ and changes nothing. `save` copies them here, and removes from this repository
any team file that no longer exists in `~/.claude`. Then commit and push.

When the master rules change, raise `Pipeline Version` in `ai-team-pipeline.md`. `team-lead` compares it with each
project's copy and reports a mismatch.
