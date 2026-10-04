# Claude AI team

Nine Claude Code skills and three agent types that work together as a software team, and the pipeline rules they
follow. A feature goes through nine stages: spec, copy, UI spec, architecture, code, infra, tests, security review
and merge.

## How the pieces fit

- A **skill** describes one role's work: what it produces and its quality bar. Its text names no other role, no
  stage and no file location. What it builds on, where it reports and which rules bind it reach it in its
  dispatch, so it runs only when the pipeline dispatches it. The one path a skill still knows is in the
  `allowed-tools` of its frontmatter, which pre-approves writes in its own folder.
- The eight specialist skills are hidden from the slash-command menu, with `user-invocable: false` in their
  frontmatter. `/team-lead` is the only command of the team that you type; it calls the others.
- An **agent type** is a tool profile for an isolated agent: file tools or not, a shell or not. Its only other
  job is to make the agent read the two files its dispatch names, the pipeline rules and the project file.
- The **pipeline rules** are the only place where the roles are tied together, and the skills are named in one
  table there, the Routing Table. For each stage it gives the skill, the name of its handoff, the artifacts it
  builds on, the area it writes and the condition it runs under. Part A binds every agent: write areas, the
  fields each artifact must carry, and how an agent is dispatched and reports. Part B is the orchestration:
  stage order, the design gate, routing and the git workflow. There is one copy of the rules, next to
  `team-lead`. Every project reads it from there, so no project can fall behind the installed rules. Only a
  session that is still open keeps the text it loaded, until `/team-lead` is typed in it again.
- Agents do not talk to each other. A stage builds on **artifacts** whose required fields the rules define, and
  reports to `team-lead` in a **handoff**. No agent reads another agent's handoff unless its dispatch cites it.
  What two roles have to agree on, such as what makes a test count, is in the Artifact Contracts of the rules
  and in neither skill.
- A **project file**, `.claude/ai-team-project.md`, is all a project holds: its source, test and infra paths, its
  git workflow settings, its overrides of the rules, and a few lines that say when the pipeline applies.
- A feature runs in one of two **git workflows**, chosen when it starts. In a **worktree**, the feature has a
  folder and a branch of its own, `team-lead` commits there, and several features can run at once. **In place**,
  features run one at a time in the folder you are in, and you commit them.
- `team-lead` is the only skill that knows the whole picture. It carries out the rules and does not repeat them:
  it builds each dispatch from the stage's row in the Routing Table. An agent that is stuck names the area it is
  blocked on, and `team-lead` routes that to the stage that writes the area.

## What is here

- `skills/`: the nine skills. Each `SKILL.md` carries its own version.
  - `team-lead`: the orchestrator. It runs the stages, keeps the ledger and stops for your approval.
  - `product-manager`, `copywriter`, `ui-designer`, `system-architect`: write the spec, the copy, the UI spec and
    the ADR.
  - `software-engineer`, `devops-engineer`, `test-engineer`: write the code, the infra and the tests.
  - `security-reviewer`: audits the change record that `team-lead` takes from git. It is read-only.
- `skills/team-lead/ai-team-pipeline.md`: the pipeline rules. This is the only copy; nothing installs it into a
  project.
- `skills/team-lead/project-initiation.md` and `project-template.md`: what `team-lead` does and writes on its
  first run in a project. It asks how the project works with git. It also works out what a worktree gets besides
  the files git tracks: which environment its tools use, what makes the worktree's own code the code that runs,
  and what a tool there sees of the settings file.
- `skills/team-lead/git-workflow-worktree.md` and `git-workflow-in-place.md`: the procedures for the two git
  workflows. `team-lead` reads only the one a feature uses, and neither where a project replaces the workflow
  with its own.
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
copy of those files. Changes are made here, tested, and then installed there.

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

Then, in any project, start a feature with `/team-lead <description>` or `/team-lead <issue number>`. On its first
run in a project `team-lead` asks how the project works with git, creates the project file, imports it from the
project's `CLAUDE.md` and adds `.ai-team/` and `.claude/worktrees/` to `.gitignore`. The project must be a git
repository; `team-lead` creates one if needed.

`install` overwrites the team's files in `~/.claude` with the ones from this repository. It does not delete
anything: a file that is in `~/.claude` but not here is reported and left in place.

## Change the team

A file in `~/.claude` is live at once in every project, including for features that are in flight. So a change is
made and tested here first, and installed last:

1. Make a branch in this repository and edit the files here.
2. Test without installing. Copy the team into a scratch project under other names: each skill folder as
   `.claude/skills/<name>-next/` and each agent type as `.claude/agents/<name>-next.md`, with every team name
   changed to its `-next` form in all of those files. Run it there with `claude -p`, starting from
   `/team-lead-next`, with the shell commands the build stages need allowed (`--allowedTools`). A project-level
   skill or agent type is seen only by that project, and the renamed Routing Table dispatches the renamed
   skills, so the live team takes no part in the test.
3. Run `pwsh ./sync.ps1 check` to see what `install` would change, then `pwsh ./sync.ps1 install`.
4. Commit, merge and push.

Keep ledgers and handoffs that already exist readable: when a format changes, say in the rules how the old form
is read. When the rules change, raise `Pipeline Version` in `ai-team-pipeline.md`. Each ledger records the version
its feature started under.

`pwsh ./sync.ps1 save` copies the other way, from `~/.claude` into this repository, and removes here any team file
that no longer exists there. Use it only to pick up an edit that was made directly in `~/.claude`. On a branch
with changes that are not installed yet it would overwrite them.

## Updating an older project

A project set up before version 5.0 holds a full copy of the old rules at `.claude/ai-team-pipeline.md`. It keeps
working as it is: `team-lead` uses that file as the project file, and only its `Project Paths` and
`Overrides for this project` count. To slim it down:

1. Create `.claude/ai-team-project.md` from `skills/team-lead/project-template.md`.
2. Move the project's `Project Paths` and `Overrides for this project` into it.
3. In `CLAUDE.md`, import the new file in place of the old one.
4. Delete `.claude/ai-team-pipeline.md`.

## Adding a role

A role is a skill, a row in the Routing Table and, if it writes something new, an area and an artifact. Work in
this repository, on a branch, as "Change the team" says:

1. `team.json`: add the skill folder name to `skills`, or the agent file name to `agents`. Until this is done the
   hook refuses to create the files.
2. `skills/<name>/SKILL.md`, or `agents/<name>.md`: write the skill or agent type. A skill describes only its own
   role: no other role, no stage, no path. It names one of the agent types in its `agent:` field. A new specialist
   skill also carries the line `user-invocable: false`, so that only `team-lead` can call it.
3. `ai-team-pipeline.md`: add the stage's row to the Routing Table, with its handoff name, its inputs, the area
   it writes and when it runs. If the area or the artifact is new, add it to Write Isolation, to the Artifact
   Topology and to the Artifact Contracts. Raise `Pipeline Version`.
4. No skill should need a change. `team-lead` works from the tables, and a skill that has to learn about the new
   role is coupled to it: put what the two share into the Artifact Contracts instead. Two things outside the
   skills can need one. An area that depends on the project's own paths also needs a line in
   `project-template.md` and in each project file. A stage before the design gate moves the gate, which the
   rules place by stage name.
5. Give the new stage a number that leaves the others as they are. Projects key their gates and notes to stage
   numbers, and ledgers in flight list the stages by number.
6. This README: the roster under "What is here" and the counts in the first paragraph.
7. Test, install, commit.

To remove a role, take it out of the Routing Table, `team.json` and this repository. `install` never deletes, so
remove its folder under `~/.claude/skills` or its file under `~/.claude/agents` by hand.
