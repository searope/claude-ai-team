# AI Team Pipeline

**Pipeline Version:** 5.1

Feature work runs through a 9-stage pipeline operated by nine skills. This file
is the only place where the stages, the artifacts and the agents are tied
together. A skill describes one role's work and nothing about the other roles.

These rules ship with the `team-lead` skill and are read from there. They are
never copied into a project, so a change to them applies to every project at
once. A project holds only its own project file: its paths and its overrides
(A1).

- **Part A** binds every pipeline agent: where files live, who may write what,
  what each artifact must contain, and how an agent is dispatched and reports.
- **Part B** binds `team-lead` and the main conversation: when the pipeline
  applies, the order of the stages, the design gate, routing and the git
  workflow.

---

# Part A: Rules for Every Agent

## A1. The Project File

Each project has one file of its own, `.claude/ai-team-project.md`, imported
from the project `CLAUDE.md`. `team-lead` creates it on its first run in a
project and never overwrites it. Every dispatch names it (A5). It holds:

- **Project Paths:** which paths are `Source`, `Tests` and `Infra` in this
  project. Agents use them to tell write areas apart (A2).
- **Overrides for this project:** the project's own rules (A6).

**Older projects.** A project set up before version 5.0 has a full copy of an
older version of these rules at `.claude/ai-team-pipeline.md`. That file is
then its project file, and only two blocks of it count: `Project Paths` and
`Overrides for this project`. The rest of it is out of date; ignore it and
follow these rules.

---

## A2. Write Isolation

No agent may write outside its own area. The area names in this table are also
the names an agent uses to say what it is blocked on (A5).

| Area | Paths | Owner | Limit |
| :--- | :--- | :--- | :--- |
| `Spec` | `docs/specs/` | `product-manager` | |
| `Copy` | `docs/copy/` | `copywriter` | |
| `UI spec` | `docs/design/` | `ui-designer` | |
| `ADR` | `docs/adr/` | `system-architect` | |
| `Source` | Source paths of the project file | `software-engineer` | Files in the ADR's `Allowed Blast Radius (Source)` |
| `Tests` | Test paths of the project file | `test-engineer` | Never production code |
| `Infra` | Infra paths of the project file | `devops-engineer` | Files in the ADR's `Allowed Blast Radius (Infra)` |
| State | `.ai-team/state/`, the change record | `team-lead` | |
| Handoff | `.ai-team/scratchpad/<feature-slug>-<role>-context.md` | The agent with that role | Own file only |

- `security-reviewer` owns no area. It returns a report, and `team-lead` stores
  it as the `security` handoff.
- **What is enforced.** Every agent except `team-lead` and `product-manager`
  runs isolated, with tools fixed by its agent type. `copywriter`,
  `ui-designer` and `system-architect` have file tools and no shell.
  `security-reviewer` has neither a shell nor file-writing tools.
  `software-engineer`, `devops-engineer` and `test-engineer` have both. None of
  them can invoke a skill. The path limits in the table are rules the agents
  follow and `security-reviewer` audits; they are not technically enforced.
- An agent that finds a problem in another area does not fix it. It reports
  `ESCALATE` (A5).
- Only `team-lead` dispatches agents. Agents do not invoke pipeline skills.
- Only `team-lead` runs git commands that change the repository, and only
  those the git workflow gives it (B5). No other agent commits, pushes,
  merges, stashes or resets.
- Nothing is deleted or stashed except by `team-lead`, and only after the user
  has chosen how to stop a feature (B5). Generated files are the one
  exception: a file that a tool run created as a side effect (a cache,
  compiled or build output) and that git does not ignore. The agent whose run
  created it deletes it before it reports. One that is left behind is a defect
  in the area it lies in, and that area's owner deletes it.

---

## A3. Artifact Topology

All agents communicate through these paths. Do not invent new directories for
specs or state.

```text
.
+-- CLAUDE.md                                   # imports the project file
+-- .claude/
|   +-- ai-team-project.md                      # project file (A1)
+-- docs/
|   +-- specs/<feature-slug>.md                 # spec
|   +-- copy/<feature-slug>-copy.md             # copy: new text
|   +-- copy/<feature-slug>-copy-audit.md       # copy audit: old -> new rewrites
|   +-- design/<feature-slug>-ui-spec.md        # UI spec
|   +-- adr/<feature-slug>-adr.md               # ADR
+-- .ai-team/                                   # working files, ignored by git
    +-- state/<feature-slug>-pipeline.md        # ledger (team-lead)
    +-- scratchpad/
        +-- <feature-slug>-<role>-context.md    # one handoff per agent
        +-- <feature-slug>-changes.md           # change record (team-lead)
```

- `<feature-slug>` is kebab-case. It is fixed no later than when the spec is
  first written, and it never changes.
- `<role>` is one of: `pm`, `copy`, `ui`, `arch`, `dev`, `devops`, `test`,
  `security`.
- The ledger is `team-lead`'s own record. No other agent reads it: what an
  agent needs from it arrives in the dispatch (A5).
- `.ai-team/` holds working files and is listed in `.gitignore`. The design
  artifacts under `docs/` are part of the feature and are committed with it.

---

## A4. Artifact Contracts

These are the parts of each artifact that another stage depends on. The owner
must write them exactly as named; everyone else may rely on them. What else an
artifact contains is its owner's business.

**Spec**
- `- **Revision:** <n>` directly under the title: `1` for a new spec, one
  higher on every rewrite.
- Acceptance Criteria numbered `AC-1`..`AC-N`, each testable and deterministic.
- A `## Topology Flags` section with exactly these two lines. `UI: yes` is
  only valid together with `User-Facing Text: yes`.

```markdown
## Topology Flags
- **User-Facing Text:** <yes | no>
- **UI:** <yes | no>
```

**Copy**
- Every string has a stable key (for example `settings.save.error`). Other
  artifacts and the code refer to a string by its key and use its text exactly
  as written.

**Copy audit**
- One row per rewrite of existing text: `File | Location | Old text | New text`.
  The rewrites are applied in `Source`, so the ADR's blast radius lists every
  file the audit names.

**UI spec**
- Every interactive component is defined in the six UI states: Empty, Loading,
  Ideal, Overflow, Degraded, Error.
- Strings appear only as copy keys.
- Design tokens are specified in the UI spec. Token, theme and style files are
  `Source`.

**ADR**
- `- **Revision:** <n>` directly under the title, as for the spec.
- `Allowed Blast Radius (Source)`: the complete list of files that may be
  created or modified in `Source`. It never lists test files.
- `Allowed Blast Radius (Infra)`: the same for `Infra`.
- `Infra Impact: yes` or `Infra Impact: no` on one line, followed by what
  changes.
- Invariants numbered `INV-1`..`INV-N`.
- Implementation Tasks numbered `T-1`..`T-N`, ordered and atomic.
- Every new dependency is named.

**Change record**
- The output of `git status --porcelain` followed by `git diff <Start Point>`,
  written by `team-lead` before the security review. Every path in it is part
  of the feature. New files appear only in the status list, not in the diff.

---

## A5. Dispatch and Handoff

**Dispatch.** `team-lead` starts an agent with these arguments:

```text
<feature-slug> [direction]
Stage: <number and name of the stage in the Routing Table>
Round: <n>
Rules: <path of this file>
Project: <path of the project file>
Defects:
- <area>: <one line> (<handoff file that describes it>)
Fast Path: <the request>
Files: <paths that may change>
```

- `team-lead` always sends the first five lines. An agent whose dispatch lacks
  one of them does not stop; it falls back. No `Round` line means round 0. No
  `Stage` line means the agent's own stage in the Routing Table (B2). No
  `Rules` or `Project` line means that file's usual place.
- The slug is the first word, except in the dispatch that starts a new feature
  whose slug is not fixed yet: there the first line is the user's request.
- `direction` is what the user or `team-lead` asks for in this run. On a re-run
  after another area changed, it says what changed and where that is
  described.
- `Stage` says which stage the agent is running. Where the project file gives
  a gate or a note for a numbered stage, this is how the agent knows which
  ones are its own.
- `Defects` appears on defect work. Fix those defects and change nothing else.
- `Fast Path` and `Files` appear only on a project fast path (A6), where there
  is no spec or ADR. The request stands in for the Acceptance Criteria, and
  `Files` for the Allowed Blast Radius.

**Escalation.** An agent that cannot finish correctly does not guess and does
not touch another area. It reports `ESCALATE` and names, in `Blocked On`, the
area that has to change:
- An artifact is ambiguous, contradictory or missing something: the area of
  that artifact. An Acceptance Criterion that cannot be tested is `Spec`, a
  string missing from the copy is `Copy`, an invariant that cannot be tested
  is `ADR`.
- The work needs a file outside the Allowed Blast Radius: `ADR`. Leave the
  file untouched.
- The fault is in another area's files: that area.
- Only the user can decide or fix it: `user`.

**Handoff.** Every agent ends by writing its handoff file (A3), starting with
this block, and returns the same block as its final message, followed by
whatever its skill adds.

```markdown
# Handoff: <role> / <feature-slug>
- **Status:** <see below>
- **Round:** <the round from the dispatch>
- **Blocked On:** <an area from A2, or `user`; omit for DONE and PASS>
- **Reason:** <one line; omit for DONE and PASS>
- **Files Touched:** <paths>
```

| Status | Used by | Meaning |
| :--- | :--- | :--- |
| `DONE` | All but `security-reviewer` | Stage complete |
| `ESCALATE` | All but `security-reviewer` | Cannot complete until `Blocked On` changes |
| `DEFECTS` | `test-engineer` | Failing tests expose defects in `Source` or `Infra` |
| `PASS` / `BLOCK` | `security-reviewer` | Gate verdict; each blocker names its own area |

- `security-reviewer` cannot write files. It returns its report, and
  `team-lead` stores it unchanged as the `security` handoff.
- An agent with nothing to change on a re-run reports `DONE`.

---

## A6. Project Overrides

A project replaces defaults with its own rules in the
`Overrides for this project` block of its project file. A rule written there
wins over the matching default in these rules and in the skills. Everything it
does not mention stays as written.

Overrides may cover:
- **Gates** (every agent): the commands that must pass before a stage may
  report `DONE`.
- **Stage Notes** (every agent): project facts a stage must respect.
- **Git Workflow** (`team-lead`): any part of B5: where a feature is developed,
  who commits, how a finished feature is delivered, and how one is rolled
  back, shelved and resumed.
- **Fast Path** (`team-lead`): which changes may skip stages, and which stages
  they skip. On a fast path there is no spec or ADR. `team-lead` records the
  request and the files that may change in the ledger and passes them in every
  dispatch (A5).

Overrides may not relax Write Isolation (A2), the design gate for a feature
that runs the Architecture stage (B3), the handoff block (A5), or the rule
that the user chooses how a feature is stopped and confirms before anything is
deleted (B5).

---

# Part B: Orchestration

## B1. Scope and Prerequisites

- **In scope:** new features and behaviour-changing fixes. Start them with
  `/team-lead <feature idea or feature-slug>`. Do not write code, tests or
  infrastructure for in-scope work outside the pipeline.
- **Fast path:** a change the user calls trivial (typo, comment, formatting,
  one-line fix, config value), or any request where the user says to skip the
  pipeline, is done directly in the main conversation.
- **Not gated:** questions, code reading, exploration and reviews that change
  no files.
- **Git is required.** The project must be a git repository; `team-lead`
  creates one on its first run if needed. Every feature has a `Start Point`,
  the commit it started from, and the security review audits what changed
  since then.
- **Project overrides:** a project may replace the fast path and the git
  workflow with its own (A6).

---

## B2. Routing Table

`team-lead` runs the stages in this order.

| Stage | Agent | Runs when | Inputs | Output |
| :--- | :--- | :--- | :--- | :--- |
| **1. Discovery** | `product-manager` | Always | User request | Spec |
| **2. Copy** | `copywriter` | Spec flag `User-Facing Text: yes` | Spec | Copy, Copy audit |
| **3. UI/UX** | `ui-designer` | Spec flag `UI: yes` | Spec, Copy | UI spec |
| **4. Architecture** | `system-architect` | Always | Spec, Copy audit, UI spec | ADR |
| **5. Coding** | `software-engineer` | Always | Spec, Copy, Copy audit, UI spec, ADR | Source changes |
| **6. Infra** | `devops-engineer` | ADR says `Infra Impact: yes` | ADR, source changes | Infra files |
| **7. Testing** | `test-engineer` | Always | Spec, Copy, UI spec, ADR, source and infra changes | Tests and results |
| **8. Security** | `security-reviewer` | Always | Everything above, change record | `PASS` / `BLOCK` |
| **9. Merge** | `team-lead` | Security `PASS` in the current round | Ledger | `READY_FOR_MERGE` |

- A stage that does not run is recorded as `SKIPPED` in the ledger. `team-lead`
  decides this from the `Runs when` column, and decides again whenever the
  artifact that column reads is rewritten.
- **Discovery runs in the main conversation**, because it is a dialogue with
  the user. When its handoff reports `DONE`, `team-lead` continues the feature
  in the same turn. If it does not, run `/team-lead <feature-slug>`. Every
  other agent stage runs isolated.
- **Before Security** `team-lead` writes the change record (A4).
- **Merge** is `team-lead` carrying out `Deliver` of the git workflow (B5).
- **Rounds.** `Round` starts at 0. It increases by 1 on every backward route,
  and when the user unblocks a stage (B4). A `PENDING` stage is completed only
  by a handoff whose `Round` equals the ledger's current `Round`; older
  handoffs are stale. A stage that is `DONE` in the ledger stays `DONE` until
  a backward route resets it.

---

## B3. Design Gate

The design gate sits after Architecture. The stages before it are the design
stages; the stages after it are the build stages. When the design stages are
done, `team-lead` summarises the spec, copy, UI spec and ADR and waits for the
user's approval. No build stage starts without it. The user answers with an
approval, a change request, or a stop (B5).

- **Approval is tied to a design.** `team-lead` records the spec and ADR
  `Revision` numbers the approval was given for. Any backward route to a design
  stage sets the gate back to `PENDING`. The user approves again, seeing what
  changed, before a build stage runs.
- **Change requests:** only while the gate is open. The user asks with
  `/team-lead <feature-slug> <change>`. It is a backward route to the owner of
  the affected artifact and does not count toward the loop cap (B4).
- **After approval there are no change requests.** The feature runs to
  `READY_FOR_MERGE` unless the user stops it (B5).

---

## B4. Defect Routing and Escalation

1. **Owner.** `team-lead` routes each `Blocked On` area to the owner of that
   area in the Write Isolation table (A2).
2. **Test failure:** `test-engineer` reports `DEFECTS` blocked on `Source` or
   `Infra`. Tests are never weakened to pass.
3. **Security block:** each blocker goes to the owner of the area it names. A
   vacuous test (one that cannot fail whatever the code does) and an AC or INV
   with no test are blockers on `Tests`, never observations.
4. **Re-run rule:** on every backward route `team-lead` increments `Round`. The
   stage routed to, and every later stage that is not `SKIPPED`, returns to
   `PENDING` and runs again in order. A route to a design stage also re-opens
   the design gate (B3), and `team-lead` decides the conditional stages again
   from the revised spec and ADR.
5. **Loop cap:** a feature gets at most 3 backward routes for test defects, 3
   for security blocks, and 5 for other escalations raised by agents. Changes
   the user requests at the design gate do not count. On the next counted
   route `team-lead` sets `BLOCKED` and asks the user. If the user says to
   continue, that counter starts again at 0.
6. **Blocked on the user:** when a handoff or a blocker is blocked on `user`,
   `team-lead` sets `BLOCKED` and asks. When the user has answered, blockers
   on other areas are routed as above. If none remain, `team-lead` increments
   `Round`, which makes the blocked handoff stale, and runs the blocked stage
   again with the user's answer. That is not a backward route: no other stage
   is reset, and it counts toward no cap.

---

## B5. Git Workflow

This is the default. A project may replace any part of it (A6). `team-lead`
carries it out; no other agent runs git commands that change the repository.

**Start.** One feature is in development at a time, in the project's working
tree. A feature starts only from a clean working tree, and the commit it
starts from is its `Start Point`. If the tree is not clean, `team-lead` lists
the uncommitted paths and offers to commit them as a checkpoint; the feature
starts only after that commit, or after the user has cleaned up. On its first
run in a project `team-lead` also commits what it sets up: a baseline, if it
had to create the repository, and the files it installs.

**Deliver.** `team-lead` never commits the work of a feature. `READY_FOR_MERGE`
means the security review passed and the work is in the working tree for the
user to review and commit. The next feature can start only after that commit.

**Stop.** The user can stop a feature at any point: at the design gate, at any
other stop, or after interrupting a stage that is still running. The command
is `/team-lead <feature-slug> stop`. `team-lead` never chooses for the user.
It lists everything that differs from the feature's `Start Point`, taken from
git, and asks:

1. **Roll back:** all work done on the feature is deleted. Modified files go
   back to their last commit, and new files, the handoffs and the ledger are
   removed.
2. **Shelve:** the work is kept in a git stash named `ai-team/<feature-slug>`,
   the working tree goes back to the last commit, and the ledger is set to
   `REJECTED`.

- Both return the project to the state it was in when the feature started.
- The list is built from git, so it includes the partial work of an
  interrupted stage and any edits the user made by hand since the feature
  started. A rollback discards those too.
- Commits made after the `Start Point` are never undone by `team-lead`. It
  names them and leaves them to the user.
- `git stash drop` or `git stash clear` destroys shelved work.

**Resume.** `/team-lead <feature-slug> resume` needs a clean working tree and
restores the stash. The design gate is `PENDING` again: no build stage runs
without a new approval. A shelved feature is ignored when `team-lead` looks
for work to continue.
