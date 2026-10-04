# Claude AI team

Nine Claude Code skills and three agent types that work together as a software team, and the pipeline rules they
follow. A feature goes through nine stages: spec, copy, UI spec, architecture, code, infra, tests, security review
and merge.

## How the pieces fit

- A **skill** describes one role's work: what it reads, what it produces and its quality bar. It does not name the
  other roles or the order of the stages, and it cannot be used without the pipeline rules.
- An **agent type** fixes the tools of an isolated agent and tells it to read the two files its dispatch names:
  the pipeline rules and the project file.
- The **pipeline rules** are the only place where the roles are tied together. Part A binds every agent: write
  areas, the fields each artifact must carry, and how an agent is dispatched and reports. Part B is the
  orchestration: stage order, the design gate, routing and the git workflow. There is one copy of the rules, next
  to `team-lead`. Every project reads it from there, so the rules and the skills can never be at different
  versions.
- A **project file**, `.claude/ai-team-project.md`, is all a project holds: its source, test and infra paths, and
  its overrides of the rules.
- `team-lead` is the only skill that knows the whole picture. It carries out the rules and does not repeat them.
  An agent that is stuck names the area it is blocked on, and `team-lead` finds the owner.

## What is here

- `skills/`: the nine skills. Each `SKILL.md` carries its own version.
  - `team-lead`: the orchestrator. It runs the stages, keeps the ledger and stops for your approval.
  - `product-manager`, `copywriter`, `ui-designer`, `system-architect`: write the spec, the copy, the UI spec and
    the ADR.
  - `software-engineer`, `devops-engineer`, `test-engineer`: write the code, the infra and the tests.
  - `security-reviewer`: audits the change record that `team-lead` takes from git. It is read-only.
- `skills/team-lead/ai-team-pipeline.md`: the pipeline rules. This is the only copy; nothing installs it into a
  project.
- `skills/team-lead/project-template.md`: what `team-lead` writes into a new project as
  `.claude/ai-team-project.md`.
- `skills/team-lead/default-git-workflow.md`: the procedure for the default git workflow (start, deliver, stop,
  resume). `team-lead` reads it only where a project does not replace the workflow with its own.
- `agents/`: three agent types that fix which tools a skill gets. Every skill except `team-lead` and
  `product-manager` runs as one of them.
  - `ai-team-author`: file tools and no shell. Used by `copywriter`, `ui-designer` and `system-architect`.
  - `ai-team-builder`: file tools and a shell. Used by `software-engineer`, `devops-engineer` and `test-engineer`.
  - `ai-team-auditor`: read only, no shell and no file writing. Used by `security-reviewer`.
- `team.json`: the team roster. It names every skill and agent type that belongs to the team.
- `sync.ps1`: copies these files to and from Claude Code's own folders.
- `CLAUDE.md` and `.claude/`: the scope rules for Claude Code sessions in this repository, and the hook that
  enforces them.

## Where the live copy is

Claude Code reads skills from `~/.claude/skills/` and agent types from `~/.claude/agents/`. This repository holds a
copy of those files. Changes are made in `~/.claude` and then saved here.

`sync.ps1` touches only the skills and agent types named in `team.json`. It never reads or copies anything else in
`~/.claude`, such as other skills, credentials or transcripts.

## Scope

This repository covers the AI team and nothing else. Skills that are not in `team.json` stay out of it. That
includes `~/.claude/skills/synced`, which the desktop app downloads from your claude.ai account and owns.

In a Claude Code session opened here, `.claude/hooks/team-scope.ps1` refuses any write by the file tools under
`~/.claude/skills`, `~/.claude/agents`, or this repository's `skills/` and `agents/` unless the file belongs to
a skill or agent type in `team.json`. So a skill cannot be created or changed there by accident. The hook does
not see shell commands, and it does not run in sessions opened in other projects.

## Install on a machine

```
git clone https://github.com/searope/claude-ai-team.git
cd claude-ai-team
pwsh ./sync.ps1 install
```

Then, in any project, start a feature with `/team-lead <request>`. On its first run in a project `team-lead`
creates the project file, imports it from the project's `CLAUDE.md` and adds `.ai-team/` to `.gitignore`. The
project must be a git repository; `team-lead` creates one if needed.

`install` overwrites the team's files in `~/.claude` with the ones from this repository. It does not delete
anything: a file that is in `~/.claude` but not here is reported and left in place.

## Save a change

After a skill, an agent type or the rules change in `~/.claude`:

```
pwsh ./sync.ps1 check
pwsh ./sync.ps1 save
git status
```

`check` lists the files that differ and changes nothing. `save` copies them here, and removes from this repository
any team file that no longer exists in `~/.claude`. Then commit and push.

A change in `~/.claude` is live at once in every project, including for features that are in flight. Keep ledgers
and handoffs that already exist readable: when a format changes, say in the rules how the old form is read.

When the rules change, raise `Pipeline Version` in `ai-team-pipeline.md`. Each ledger records the version its
feature started under.

## Updating an older project

A project set up before version 5.0 holds a full copy of the old rules at `.claude/ai-team-pipeline.md`. It keeps
working as it is: `team-lead` uses that file as the project file, and only its `Project Paths` and
`Overrides for this project` count. To slim it down:

1. Create `.claude/ai-team-project.md` from `skills/team-lead/project-template.md`.
2. Move the project's `Project Paths` and `Overrides for this project` into it.
3. In `CLAUDE.md`, import the new file in place of the old one.
4. Delete `.claude/ai-team-pipeline.md`.

## Adding a role

A role is named in several places. Change them in this order:

1. `team.json`: add the skill folder name to `skills`, or the agent file name to `agents`. Until this is done the
   hook refuses to create the files.
2. `~/.claude/skills/<name>/SKILL.md`, or `~/.claude/agents/<name>.md`: write the skill or agent type. The skill
   describes only its own role and names one of the agent types in its `agent:` field.
3. `ai-team-pipeline.md`: add the role's area to Write Isolation, its artifact to the Artifact Topology and the
   Artifact Contracts, and its stage to the Routing Table. Raise `Pipeline Version`.
4. `team-lead/SKILL.md`, if the new stage needs its own dispatch or gate handling. No other skill should need a
   change; if one does, the new role is coupled to it and the contract belongs in the pipeline rules instead.
5. This README: the roster under "What is here" and the counts in the first paragraph.
6. `pwsh ./sync.ps1 save`, then commit.

To remove a role, delete its files from `~/.claude` and run `save`, which deletes them here too. Then take the
role out of `team.json` and the other places above.
