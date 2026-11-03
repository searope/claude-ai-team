# Claude AI team

Ten Claude Code skills and three agent types that work together as a software team, the pipeline rules they
follow, and the tool that keeps each feature's state. A feature goes through ten stages: spec, copy, UI spec,
architecture, code, infra, tests, security review, second review and merge. Copy, UI spec and infra run when the
feature needs them, and the second review when the project turns it on.

## How the pieces fit

- A **skill** describes one role's work: what it produces and its quality bar. Its text names no other role, no
  stage and no file location. What it builds on, where it reports and which rules bind it reach it in its
  dispatch, so it runs only when the pipeline dispatches it. Two skills are exceptions. `product-manager`, which
  runs in your conversation, pre-approves in its `allowed-tools` the writes in its own folder and in the handoff
  folder; the skills that run isolated get their access from their agent type. And `second-reviewer` reads the
  audit protocol of `security-reviewer` from that skill's file, so that the two reviews audit alike.
- The nine specialist skills are hidden from the slash-command menu, with `user-invocable: false` in their
  frontmatter. `/team-lead` is the only command of the team that you type; it calls the others. The model can
  still call a hidden skill, and a call that carries no dispatch is refused: by the skill's agent type, or by
  the skill itself where it runs in the conversation. Where no stage is dispatched, the guard also lets no
  isolated agent of the team write in the project.
- An **agent type** is a tool profile for an isolated agent: file tools or not, a shell or not. It also carries
  the guard hook, and it makes the agent read the two files its dispatch names, the pipeline rules and the
  project file.
- The **guard**, `ai_team_guard.py`, is the hook that Claude Code runs before each read, file write and shell
  command of an agent of the team. When an isolated stage is dispatched, the tool writes down what that stage
  may write. The guard then lets the file tools write only those files, the stage's handoff and the agent's
  scratch folder. A shell command may write nowhere else, `git` and `gh` run only in their read-only forms, and
  no agent opens a file that holds secrets. Write Isolation in the rules lists what it blocks. The guard is not
  a sandbox, so the tool checks afterwards as well: before each isolated stage that writes, it takes a snapshot
  of every file the stage could change, those under `.ai-team/` and `.claude/` included. When the stage
  returns, a change outside its area stops the feature, and you choose whether it is put back. Discovery runs
  in your conversation, under your session's own permissions, and neither the guard nor a snapshot watches it.
- The **pipeline rules** bind every agent and name no skill: the write areas, the fields each artifact must
  carry, how tools are run, and how an agent is dispatched and reports. There is one copy of the rules, next to
  `team-lead`. Every project reads it from there, so no project can fall behind the installed rules. Only a
  session that is still open keeps the text it loaded, until `/team-lead` is typed in it again.
- **`team-lead`** is the orchestrator. It and its tool are the only place where the roles are tied together.
  The tool, `ai_team.py`, holds the state machine: it keeps the ledger, decides which stage runs next, builds
  each dispatch, writes the change record, checks what each stage changed, and holds the gates and the loop
  caps. Its table of stages gives for each stage the skill, the name of its handoff, the artifacts it builds on,
  the area it writes, the condition it runs under and its agent type. `team-lead` does what needs judgment:
  understanding the request, choosing its lane and its name, talking to you, presenting the gates, and carrying
  out the steps of the git workflow. No isolated agent reads the skill or the tool. An agent that is stuck
  names the area it is blocked on, and the tool routes that to the stage that writes the area.
- Agents do not talk to each other. A stage builds on **artifacts** whose required fields the rules define, and
  reports to `team-lead` in a **handoff**. No agent reads another agent's handoff unless its dispatch cites it.
  A note for later stages has a fixed heading in the handoff, and the tool names that handoff in the dispatches
  that follow. What only `team-lead` knows, such as a decision of yours that no artifact records, it adds to a
  notes file that the dispatches name as well. What two roles have to agree on, such as what makes a test count,
  is in the Artifact Contracts of the rules and in neither skill.
- A **project file**, `.claude/ai-team-project.md`, is all a project holds: its source, test and infra paths, its
  git workflow settings, how a page is rendered for a mock-up, its scans, whether the second review runs, its
  overrides of the rules, and a few lines that say when the pipeline applies.
- **Scans** are read-only checks, such as a dependency audit or a search for secrets, that the project file lists
  under `Scans`. Before each review the tool runs them itself, from the feature's folder, and gives the reviewers
  their report, so these checks rest on tools and not on an agent's word. A failed scan blocks the review,
  unless the review shows that the finding is a false positive or lies outside the change. The tool runs a list
  of scans only after you have approved it, and asks again when the list changes. Gates are the other kind of
  check: commands that a stage runs itself before it reports `DONE`, set under `Overrides for this project`.
- The **second review**, stage 9, runs only where the project file says `Second Review: yes`. `second-reviewer`
  audits the same change as Security, on another model, and reads neither the first review's report nor its
  handoff: the guard refuses it that file. It costs one more review in each round.
- A feature that changes a screen gets a **mock-up**: `ui-designer` builds the product, takes a screenshot of the
  real page, makes a mock-up page from it and checks its own render. `team-lead` then shows you the two
  screenshots side by side and waits for your approval of the look, before the architecture stage runs. The
  project file's `Mock-up` line gives the build and screenshot commands, the pages that may be opened and the
  widths; with `none` there, the designer still makes the mock-up page, without screenshots, and never ASCII
  art. The mock-up lives in `.ai-team/mockups/<feature-slug>/` and is not committed: the later stages build from
  the UI spec alone.
- A request takes one of three **lanes**: all the stages, a **fast path** that skips the stages a project
  names, or the **trivial lane**, in which the change is made directly with no stage and no review. `team-lead`
  chooses the lane when a request starts. "Lighter lanes" below says how.
- A feature runs in one of two **git workflows**, chosen when it starts. In a **worktree**, the feature has a
  folder and a branch of its own, `team-lead` commits there, and several features can run at once. **In place**,
  features run one at a time in the folder you are in, and you commit them. A new project file says
  `worktree only`; its `Workflow` line is yours to change.

## What is here

- `skills/`: the ten skills. Each `SKILL.md` carries its own version.
  - `team-lead`: the orchestrator. It runs the tool, dispatches the stages and stops for your decisions.
  - `product-manager`, `copywriter`, `ui-designer`, `system-architect`: write the spec, the copy, the UI spec and
    the ADR.
  - `software-engineer`, `devops-engineer`, `test-engineer`: write the code, the infra and the tests.
  - `security-reviewer`: audits the change record that the tool takes from git, and the scan report. It is
    read-only.
  - `second-reviewer`: the optional second review, on another model, by the audit protocol of
    `security-reviewer`. It is read-only.
- `skills/team-lead/ai-team-pipeline.md`: the pipeline rules, which every agent reads. This is the only copy;
  nothing installs it into a project.
- `skills/team-lead/scripts/`: the tool and the guard, in Python. They are files of the `team-lead` skill and
  are installed with it.
  - `ai_team.py`: the tool. `team-lead` runs it for every step that changes a feature's state. Each command
    prints one JSON object, and `python ai_team.py --help` lists them. `doctor` checks an installation and a
    project, `guard-test` checks the guard's decisions, and `cost` counts the tokens of each stage from Claude
    Code's session logs.
  - `aiteam/`: the tool's modules. `model.py` holds the table of stages, the areas and the paths, and is the
    only one that names a skill. `engine.py` holds the state machine, and `guard.py` what the guard allows.
  - `ai_team_guard.py`: the guard hook that the agent types run.
  - `tests/test_pipeline.py`: tests of the tool from end to end, on throwaway git repositories.
- `skills/team-lead/project-initiation.md` and `project-template.md`: what `team-lead` does and writes on its
  first run in a project. It puts every feature in a worktree of its own (`worktree only`) and works out what a
  worktree gets besides the files git tracks: which environment its tools use, what makes the worktree's own
  code the code that runs, and what a tool there sees of the settings file. It proposes a fast path, gates,
  scans and the second review, and writes what you accept.
- `skills/team-lead/git-workflow-worktree.md` and `git-workflow-in-place.md`: the procedures for the two git
  workflows. `team-lead` reads only the one a feature uses, and neither where a project replaces the workflow
  with its own.
- `skills/team-lead/lanes.md`: how `team-lead` chooses the lane of a new request, and how a request leaves a
  lane that proves too light. It is read only in a project that defines a lighter lane, and for a request that
  asks for one or calls itself trivial.
- `agents/`: three agent types that fix which tools a skill gets, each with the guard hook in its frontmatter.
  Every skill except `team-lead` and `product-manager` runs as one of them.
  - `ai-team-author`: file tools and no shell. Used by `copywriter` and `system-architect`.
  - `ai-team-builder`: file tools and a shell. Used by `ui-designer`, `software-engineer`, `devops-engineer` and
    `test-engineer`. The designer's shell is for the project's build and screenshot commands only. It keeps its
    prompt cache for an hour, because a test command can outlast the default five minutes.
  - `ai-team-auditor`: read only, no shell and no file writing. Used by `security-reviewer` and
    `second-reviewer`.
- `team.json`: the team roster. It names every skill and agent type that belongs to the team.
- `sync.ps1`: copies these files to and from Claude Code's own folders.
- `CLAUDE.md` and `.claude/`: the scope rules for Claude Code sessions in this repository, and the hook and
  the deny rules that enforce them.
- `tools/compare-sessions.py`: compares two sessions that built the same feature, one with the team and one
  without: the time and tokens of each, and the material for a blind judgement of the two changes. It is not
  part of the team and is not installed.
- `trials/`: reports of trial runs of the team.

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

Besides Claude Code and git, a machine needs `pwsh` for `sync.ps1`, and Python 3.9 or later that starts as
`python` from the PATH. `team-lead` runs its tool as `python "${CLAUDE_SKILL_DIR}/scripts/ai_team.py"`, and each
agent type runs the guard as `python "$HOME/.claude/skills/team-lead/scripts/ai_team_guard.py"`. The hook finds
its script under `$HOME/.claude`, so the team has to be installed there, which is where `sync.ps1` puts it. When
`python` is missing or the path is wrong, the hook cannot start, and Claude Code blocks every call it guards.

```
git clone https://github.com/searope/claude-ai-team.git
cd claude-ai-team
pwsh ./sync.ps1 install
```

Then see the guard work once, as "Live check" says.

In any project, start a feature with `/team-lead <description>` or `/team-lead <issue number>`; an issue is read
with `gh`. On its first run in a project `team-lead` sets the project up:

- It creates the project file with `worktree only` on its `Workflow` line, so every feature gets a worktree of
  its own, and works out what a worktree needs besides the files git tracks.
- It proposes a fast path, and gates and scans for the project's stack, and asks whether the second review
  should run. You take each as proposed, changed, or not at all.
- It imports the project file from the project's `CLAUDE.md` and adds `.ai-team/` and `.claude/worktrees/` to
  `.gitignore`.

It commits what it set up when the working tree was clean. The project must be a git repository; `team-lead`
creates one if needed. In a repository with a remote, push that commit before the first feature: a worktree
starts from the remote's base branch, and no feature starts in a worktree that lacks the project file.

`install` overwrites the team's files in `~/.claude` with the ones from this repository. It does not delete
anything: a file that is in `~/.claude` but not here is reported and left in place. `sync.ps1` stops before it
copies anything when `team.json` is malformed or names a skill or agent type that the source lacks.

## Live check

The guard works only where Claude Code runs its hook, and where it does not, nothing says so: the calls go
through. `ai_team.py guard-test` checks the guard's decisions on a set of made-up calls, and
`ai_team.py doctor` checks that each agent type names the hook. Neither shows that the hook runs. So see the
guard refuse a call once on each machine, and again after an install that changes a hook:

1. Make a scratch folder that is a git repository, and put a file `.env.probe` in it that holds one harmless
   line. The guard refuses every agent of the team a file whose name marks it as holding secrets, whether or not
   a stage is dispatched.
2. In that folder, have Claude Code send the installed `ai-team-auditor` to read the file:

   ```
   claude -p "Have the ai-team-auditor agent read the file .env.probe in this folder and quote exactly what its Read tool returned. Do not read the file yourself."
   ```

3. The hook runs when the answer quotes `Blocked by the AI team guard`, with the file's path and the words
   `holds secrets`. Claude Code calls even this refusal a hook error. When the answer quotes the line from the
   file, the guard refused nothing: Claude Code did not run the hook, or let the call through when the hook
   could not start. When the answer quotes a hook that `failed`, the hook could not start: check that `python`
   starts from a shell and that the guard's script is where the agent type names it.

## Lighter lanes

A request that reaches `team-lead` runs through all the stages, unless you call it trivial: the first lines of
the project file send such a change past the pipeline. A project sets its own lanes under
`Overrides for this project` in its project file. `team-lead` proposes a fast path on its first run in a
project.

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
   changed to its `-next` form in all of those files, the tool's `model.py` included. Run it there with
   `claude -p`, starting from `/team-lead-next`, with file edits accepted and with the git commands and the shell
   commands of the build stages and of the project's `Mock-up` line allowed (`--allowedTools`). A headless run
   cannot write under `.claude/`, so put the project file into the scratch project by hand. The first stage is a
   dialogue: answer it in continued turns (`--continue`). A project-level skill or agent type is seen only by
   that project, and the renamed table of stages dispatches the renamed skills, so the live team takes no part
   in the test. `claude -p` skips the frontmatter hooks of an agent file in a project folder that is not
   trusted, so the guard does not run in such a test. A test of the guard needs the agent types passed with
   `--agents <file.json>` instead: one entry for each, with its `description`, `prompt`, `tools` and `hooks`,
   and each hook command pointed at the scratch project's copy of `ai_team_guard.py`.
3. Run `pwsh ./sync.ps1 check` to see what `install` would change, then `pwsh ./sync.ps1 install`. After a change
   to a hook, see it work on the live agent type ("Live check").
4. Commit, merge and push.

The tool and the guard are part of `team-lead`: a change to either is a change of that skill, and raises its
`metadata.version`. Run the tool's tests and the guard's self-test before the scratch project, from
`skills/team-lead/scripts`:

```
python -m unittest discover -s tests -v
python ai_team.py guard-test
```

Keep ledgers and handoffs that already exist readable: when a format changes, say how the old form is read, in
the rules for what an agent reads, in the tool for the ledger and what it parses, and in `team-lead` for what it
reads itself. A ledger records the format it is written in and the `Pipeline Version` its feature started
under; the markdown ledger of pipeline 7.x is converted by `ai_team.py import-md`. Take such a reading out again
once no feature in flight was started under the old form. When the rules change, raise `Pipeline Version` in
`ai-team-pipeline.md`, the same number in step 1 of `Setup` in `team-lead`, which names the version it is
written for, and `PIPELINE_VERSION` in the tool's `model.py`. `ai_team.py doctor` warns when the rules file and
the tool disagree.

`pwsh ./sync.ps1 save` copies the other way, from `~/.claude` into this repository, and removes here any team file
that no longer exists there. Use it only to pick up an edit that was made directly in `~/.claude`. On a branch
with changes that are not installed yet it would overwrite them.

## Adding a role

A role is a skill, a row in the tool's table of stages and, if it writes something new, an area and an artifact.
Work in this repository, on a branch, as "Change the team" says:

1. `team.json`: add the skill folder name to `skills`, or the agent file name to `agents`. Until this is done the
   hook refuses to create the files.
2. `skills/<name>/SKILL.md`, or `agents/<name>.md`: write the skill or agent type. A skill describes only its own
   role: no other role, no stage, no path. A skill that runs isolated carries `context: fork`,
   `background: false`, and one of the agent types in its `agent:` field; without `context: fork` the `agent:`
   field does nothing. A new specialist skill also carries the line `user-invocable: false`, which keeps it out
   of the slash-command menu. A new agent type carries the guard hook as the others do, and its name goes into
   `PIPELINE_AGENTS` in `model.py`: the guard leaves alone an agent type that is not listed there.
3. The tool, in `skills/team-lead/scripts/aiteam/`: add the stage's row to `STAGES` in `model.py`, with its
   skill, its handoff name, its inputs, the area it writes, when it runs and its agent type. Then look through
   the tool for the numbers of the stages: some decisions are tied to them, such as what a stage may write
   (`stage_allowlist` in `guard.py`), what the user is told when a stage starts (`STAGE_SAYS` in `engine.py`),
   which stages are reviews (`REVIEW_STAGES`), and when a stage runs only on a condition (`CONDITIONAL_STAGES`
   and `_condition`). Add tests for the new stage to `tests/test_pipeline.py`.
4. `skills/team-lead/SKILL.md`: add the stage's row to the table under "The stages", and raise the skill's
   version. This file, `model.py`, `team.json` and this README are the only files that name the new skill.
5. `ai-team-pipeline.md`, only if the area or the artifact is new: add it to Write Isolation and to the Artifact
   Contracts, and raise `Pipeline Version` in the three places that "Change the team" names.
6. No other skill should need a change. A skill that has to learn about the new role is coupled to it: put what
   the two share into the Artifact Contracts instead. Two things outside the skills can need a change. An area
   that depends on the project's own paths also needs a line in `project-template.md` and in each project file.
   A stage placed before the design gate, before Testing or before Security also touches the places that name
   those stages: the lines under the table in "The stages" and "Run the feature" in `team-lead`, the worktree
   procedure, and the tool.
7. Give the new stage a number that leaves the others as they are. Projects key their gates and notes to stage
   numbers, and ledgers in flight list the stages by number. Where a number has to move, as Merge moved from 9
   to 10 when the second review came in, the tool must read the old number in the ledgers in flight, as
   `LEGACY_LABELS` in `model.py` does for the ledgers of pipeline 7.x.
8. This README: the roster under "What is here" and every count of skills and stages.
9. Test, install, commit.

To remove a role, take it out of the tool's table of stages and the places that use its number, the table in
`team-lead`, `team.json` and this repository. `install` never deletes, so remove its folder under
`~/.claude/skills` or its file under `~/.claude/agents` by hand.
