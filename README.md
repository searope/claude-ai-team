# Claude AI team

Nine Claude Code skills and three agent types that work together as a software team, and the pipeline rules they
follow. A feature goes through nine stages: spec, copy, UI spec, architecture, code, infra, tests, security review
and merge.

## How the pieces fit

- A **skill** describes one role's work: what it produces and its quality bar. Its text names no other role, no
  stage and no file location. What it builds on, where it reports and which rules bind it reach it in its
  dispatch, so it runs only when the pipeline dispatches it. The only paths a skill still knows are in the
  `allowed-tools` of the four design skills, which pre-approve writes in their own folder and in the handoff
  folder.
- The eight specialist skills are hidden from the slash-command menu, with `user-invocable: false` in their
  frontmatter. `/team-lead` is the only command of the team that you type; it calls the others. The model can
  still call a hidden skill, and a call that carries no dispatch is refused: by the skill's agent type, or by
  the skill itself where it runs in the conversation.
- An **agent type** is a tool profile for an isolated agent: file tools or not, a shell or not. Besides that it
  makes the agent read the two files its dispatch names, the pipeline rules and the project file. The tools are
  the only thing that is technically enforced: the path limits of the write areas are rules the agents follow
  and the security review audits.
- The **pipeline rules** bind every agent and name no skill: the write areas, the fields each artifact must
  carry, how tools are run, and how an agent is dispatched and reports. There is one copy of the rules, next to
  `team-lead`. Every project reads it from there, so no project can fall behind the installed rules. Only a
  session that is still open keeps the text it loaded, until `/team-lead` is typed in it again.
- **`team-lead`** is the orchestrator, and the only place where the roles are tied together. Its Routing Table
  gives for each stage the skill, the name of its handoff, the artifacts it builds on, the area it writes and
  the condition it runs under. The stage order, the design gate, routing and the choice of git workflow are in
  its skill as well, and no isolated agent reads them. It builds each dispatch from the stage's row in the
  table. An agent that is stuck names the area it is blocked on, and `team-lead` routes that to the stage that
  writes the area.
- Agents do not talk to each other. A stage builds on **artifacts** whose required fields the rules define, and
  reports to `team-lead` in a **handoff**. No agent reads another agent's handoff unless its dispatch cites it.
  A note for later stages has a fixed heading in the handoff, and `team-lead` names that handoff in the
  dispatches that follow. What only `team-lead` knows, such as a decision the user made after the design was
  approved, it writes into a notes file that the dispatches name as well. What two roles have to agree on, such
  as what makes a test count, is in the Artifact Contracts of the rules and in neither skill.
- A **project file**, `.claude/ai-team-project.md`, is all a project holds: its source, test and infra paths, its
  git workflow settings, its overrides of the rules, and a few lines that say when the pipeline applies.
- A request takes one of three **lanes**: all the stages, a **fast path** that skips the stages a project
  names, or the **trivial lane**, in which the change is made directly with no stage and no review. `team-lead`
  chooses the lane when a request starts. "Lighter lanes" below says how.
- A feature runs in one of two **git workflows**, chosen when it starts. In a **worktree**, the feature has a
  folder and a branch of its own, `team-lead` commits there, and several features can run at once. **In place**,
  features run one at a time in the folder you are in, and you commit them.

## What is here

- `skills/`: the nine skills. Each `SKILL.md` carries its own version.
  - `team-lead`: the orchestrator. It runs the stages, keeps the ledger and stops for your approval.
  - `product-manager`, `copywriter`, `ui-designer`, `system-architect`: write the spec, the copy, the UI spec and
    the ADR.
  - `software-engineer`, `devops-engineer`, `test-engineer`: write the code, the infra and the tests.
  - `security-reviewer`: audits the change record that `team-lead` takes from git. It is read-only.
- `skills/team-lead/ai-team-pipeline.md`: the pipeline rules, which every agent reads. This is the only copy;
  nothing installs it into a project.
- `skills/team-lead/project-initiation.md` and `project-template.md`: what `team-lead` does and writes on its
  first run in a project. It asks how the project works with git. It also works out what a worktree gets besides
  the files git tracks: which environment its tools use, what makes the worktree's own code the code that runs,
  and what a tool there sees of the settings file.
- `skills/team-lead/git-workflow-worktree.md` and `git-workflow-in-place.md`: the procedures for the two git
  workflows. `team-lead` reads only the one a feature uses, and neither where a project replaces the workflow
  with its own.
- `skills/team-lead/lanes.md`: how `team-lead` chooses the lane of a new request, and how a request leaves a
  lane that proves too light. It is read only in a project that defines a lighter lane, and for a request that
  calls itself trivial.
- `agents/`: three agent types that fix which tools a skill gets. Every skill except `team-lead` and
  `product-manager` runs as one of them.
  - `ai-team-author`: file tools and no shell. Used by `copywriter`, `ui-designer` and `system-architect`.
  - `ai-team-builder`: file tools and a shell. Used by `software-engineer`, `devops-engineer` and `test-engineer`.
  - `ai-team-auditor`: read only, no shell and no file writing. Used by `security-reviewer`.
- `team.json`: the team roster. It names every skill and agent type that belongs to the team.
- `sync.ps1`: copies these files to and from Claude Code's own folders.
- `CLAUDE.md` and `.claude/`: the scope rules for Claude Code sessions in this repository, and the hook and
  the deny rules that enforce them.

## Where the live copy is

Claude Code reads skills from `~/.claude/skills/` and agent types from `~/.claude/agents/`. This repository holds a
copy of those files. Changes are made here, tested, and then installed there.

`sync.ps1` touches only the skills and agent types named in `team.json`. It never reads or copies anything else in
`~/.claude`, such as other skills, credentials or transcripts.

## Scope

This repository covers the AI team and nothing else. Skills that are not in `team.json` stay out of it. That
includes `~/.claude/skills/synced`, which the desktop app downloads from your claude.ai account and owns.

In a Claude Code session opened here, two things guard the file tools. The deny rules in
`.claude/settings.json` refuse every write under `~/.claude/skills` and `~/.claude/agents`: a live file changes
only through `sync.ps1 install`. And `.claude/hooks/team-scope.ps1` refuses a write under this repository's
`skills/` and `agents/` unless the file belongs to a skill or agent type in `team.json`. So a skill cannot be
created or changed by accident. Neither sees shell commands, and neither applies in sessions opened in other
projects.

## Install on a machine

```
git clone https://github.com/searope/claude-ai-team.git
cd claude-ai-team
pwsh ./sync.ps1 install
```

Then, in any project, start a feature with `/team-lead <description>` or `/team-lead <issue number>`. On its first
run in a project `team-lead` asks how the project works with git, creates the project file, imports it from the
project's `CLAUDE.md` and adds `.ai-team/` and `.claude/worktrees/` to `.gitignore`. It commits what it set up
when the working tree was clean. The project must be a git repository; `team-lead` creates one if needed.

`install` overwrites the team's files in `~/.claude` with the ones from this repository. It does not delete
anything: a file that is in `~/.claude` but not here is reported and left in place. `sync.ps1` stops before it
copies anything when `team.json` is malformed or names a skill or agent type that the source lacks.

## Lighter lanes

A request that reaches `team-lead` runs through all the stages, unless you call it trivial: the first lines of
the project file send such a change past the pipeline. A project sets its own lanes under `Overrides for this
project` in its project file:

- **Fast Path:** which stages a small change skips, and the conditions it must meet. For example: a change of
  text or style skips stages 1 to 4 and 6, when it touches at most three files and none of them is a schema or
  a deploy file.
- **Trivial Lane:** which changes are made directly, and what is still asked of such a change. For example: a
  change of at most ten lines in one stylesheet, after which the tests are run once.

`team-lead` takes the lightest lane whose conditions hold, and says which condition decided it. Three things it
does not do on its own:

- **Take the trivial lane.** That lane has no review, so it takes your word: you call the change trivial, or
  you agree when `team-lead` asks.
- **Move a request to a heavier lane.** A request that asks for a lighter lane than the conditions allow does
  not start. `team-lead` names the condition and asks, unless the project's rule orders the move.
- **Widen a fast path.** A stage that needs one more file gets it while the conditions still hold. Otherwise
  the feature stops and you choose: all the stages, the fast path with your answer or a narrower change, or
  stopping. A feature that moves to all the stages keeps what was built.

## Change the team

A file in `~/.claude` is live at once in every project, including for features that are in flight. So a change is
made and tested here first, and installed last:

1. Make a branch in this repository and edit the files here.
2. Test without installing. Copy the team into a scratch project under other names: each skill folder as
   `.claude/skills/<name>-next/` and each agent type as `.claude/agents/<name>-next.md`, with every team name
   changed to its `-next` form in all of those files. Run it there with `claude -p`, starting from
   `/team-lead-next`, with file edits accepted and with the git commands and the shell commands of the build
   stages allowed (`--allowedTools`). A headless run cannot write under `.claude/`, so put the project file
   into the scratch project by hand. The first stage is a dialogue: answer it in continued turns
   (`--continue`). A project-level skill or agent type is seen only by that project, and the renamed Routing
   Table dispatches the renamed skills, so the live team takes no part in the test.
3. Run `pwsh ./sync.ps1 check` to see what `install` would change, then `pwsh ./sync.ps1 install`.
4. Commit, merge and push.

Keep ledgers and handoffs that already exist readable: when a format changes, say how the old form is read, in
the rules for what an agent reads and in `team-lead` for what it reads itself. Take that sentence out again once
no feature in flight was started under the old form. When the rules change, raise
`Pipeline Version` in `ai-team-pipeline.md`, and the same number in step 1 of `Setup` in `team-lead`, which
names the version it is written for. Each ledger records the version its feature started under.

`pwsh ./sync.ps1 save` copies the other way, from `~/.claude` into this repository, and removes here any team file
that no longer exists there. Use it only to pick up an edit that was made directly in `~/.claude`. On a branch
with changes that are not installed yet it would overwrite them.

## Adding a role

A role is a skill, a row in the Routing Table and, if it writes something new, an area and an artifact. Work in
this repository, on a branch, as "Change the team" says:

1. `team.json`: add the skill folder name to `skills`, or the agent file name to `agents`. Until this is done the
   hook refuses to create the files.
2. `skills/<name>/SKILL.md`, or `agents/<name>.md`: write the skill or agent type. A skill describes only its own
   role: no other role, no stage, no path. A skill that runs isolated carries `context: fork` and names one of
   the agent types in its `agent:` field; without the first line the second does nothing. A new specialist
   skill also carries the line `user-invocable: false`, which keeps it out of the slash-command menu.
3. `skills/team-lead/SKILL.md`: add the stage's row to the Routing Table, with its skill, its handoff name, its
   inputs, the area it writes and when it runs, and raise the skill's version. This is the only file that names
   the new skill.
4. `ai-team-pipeline.md`, only if the area or the artifact is new: add it to Write Isolation and to the Artifact
   Contracts, and raise `Pipeline Version`.
5. No other skill should need a change. A skill that has to learn about the new role is coupled to it: put what
   the two share into the Artifact Contracts instead. Two things outside the skills can need a change. An area
   that depends on the project's own paths also needs a line in `project-template.md` and in each project file.
   A stage placed before the design gate, before Testing or before Security also touches the places that name
   those stages: the notes under the Routing Table, `Dispatch` in `team-lead`, and the worktree procedure.
6. Give the new stage a number that leaves the others as they are. Projects key their gates and notes to stage
   numbers, and ledgers in flight list the stages by number.
7. This README: the roster under "What is here" and every count of skills.
8. Test, install, commit.

To remove a role, take it out of the Routing Table, `team.json` and this repository. `install` never deletes, so
remove its folder under `~/.claude/skills` or its file under `~/.claude/agents` by hand.
