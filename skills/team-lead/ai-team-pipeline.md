# AI Team Pipeline

**Pipeline Version:** 4.0

Feature work in this project runs through a 9-stage pipeline operated by nine
skills. This file is the only place where the stages, the artifacts and the
agents are tied together. A skill describes one role's work and nothing about
the other roles.

- **Part A** binds every pipeline agent: where files live, who may write what,
  what each artifact must contain, and how an agent is dispatched and reports.
- **Part B** binds `team-lead` and the main conversation: when the pipeline
  applies, the order of the stages, the design gate, routing and stopping.

This file lives at `.claude/ai-team-pipeline.md` and is imported from the
project `CLAUDE.md`. Its master copy ships with the `team-lead` skill, which
installs it and reports when the project copy falls behind.

---

# Part A: Rules for Every Agent

## A1. Project Paths

Edit this block to match the project. Agents use it to tell write areas apart.

- **Source:** `src/`, `lib/`, `app/` (includes design-token, theme and locale
  files)
- **Tests:** `tests/`, plus colocated test files (`*_test.*`, `*.test.*`,
  `*.spec.*`)
- **Infra:** `Dockerfile*`, `docker-compose*`, `.github/`, other CI config,
  IaC, `migrations/`

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
| `Source` | Source paths (A1) | `software-engineer` | Files in the ADR's `Allowed Blast Radius (Source)` |
| `Tests` | Test paths (A1) | `test-engineer` | Never production code |
| `Infra` | Infra paths (A1) | `devops-engineer` | Files in the ADR's `Allowed Blast Radius (Infra)` |
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
- No agent commits, pushes or merges feature work. The user does that after
  `READY_FOR_MERGE`. The only commits an agent makes are `team-lead`'s setup
  commits on the first run (the baseline and the pipeline install) and a
  checkpoint commit the user agreed to before a feature starts.
- Nothing is deleted or stashed except by `team-lead`, and only after the user
  chooses how to stop a feature (B5).

---

## A3. Artifact Topology

All agents communicate through these paths. Do not invent new directories for
specs or state.

```text
.
+-- CLAUDE.md                                   # imports the file below
+-- .claude/
|   +-- ai-team-pipeline.md                     # this file
+-- docs/
|   +-- specs/<feature-slug>.md                 # spec
|   +-- copy/<feature-slug>-copy.md             # copy: new text
|   +-- copy/<feature-slug>-copy-audit.md       # copy audit: old -> new rewrites
|   +-- design/<feature-slug>-ui-spec.md        # UI spec
|   +-- adr/<feature-slug>-adr.md               # ADR
+-- .ai-team/
    +-- state/<feature-slug>-pipeline.md        # ledger (team-lead)
    +-- state/rejected-features.md              # shelved features (team-lead)
    +-- scratchpad/
        +-- <feature-slug>-<role>-context.md    # one handoff per agent
        +-- <feature-slug>-changes.md           # change record (team-lead)
```

- `<feature-slug>` is kebab-case and fixed when the spec is first written. It
  is the first word of every dispatch.
- `<role>` is one of: `pm`, `copy`, `ui`, `arch`, `dev`, `devops`, `test`,
  `security`.
- The ledger is `team-lead`'s own record. No other agent reads it: what an
  agent needs from it arrives in the dispatch (A5).
- Working files live in `.ai-team/`, not `.claude/`, because Claude Code asks
  for approval on every write under `.claude/`.

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
  written by `team-lead` before the security review. A feature starts from a
  clean working tree, so every path in it is part of the feature. New files
  appear only in the status list, not in the diff.

---

## A5. Dispatch and Handoff

**Dispatch.** `team-lead` starts an agent with these arguments:

```text
<feature-slug> [direction]
Round: <n>
Defects:
- <area>: <one line> (<handoff file that describes it>)
Fast Path: <the request>
Files: <paths that may change>
```

- Only the slug is always present. With no `Round` line the round is 0.
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

This section is empty in the master copy. A project fills it in, in its own
copy, to replace defaults with its own rules. A rule written here wins over the
matching default in this file and in the skills. Everything it does not
mention stays as written.

Overrides may cover:
- **Gates** (every agent): the commands that must pass before a stage may
  report `DONE`.
- **Stage Notes** (every agent): project facts a stage must respect.
- **Git Workflow** (`team-lead`): where a feature is developed, who commits,
  and how a finished feature is delivered. It replaces the clean-start rule,
  the rule that `team-lead` makes no feature commits, Stage 9, and the
  mechanics of rollback, shelve and resume.
- **Fast Path** (`team-lead`): which changes may skip stages, and which stages
  they skip. On a fast path there is no spec or ADR. `team-lead` records the
  request and the files that may change in the ledger and passes them in every
  dispatch (A5).

Overrides may not relax Write Isolation (A2), the design gate for a feature
that runs Stage 4 (B3), the handoff block (A5), or the rule that the user
chooses how a feature is stopped and confirms before anything is deleted (B5).

### Overrides for this project
- None.

---

# Part B: Orchestration

## B1. Scope and Prerequisites

- **Git is required.** The project must be a git repository. On its first run
  `team-lead` creates one if needed and commits a baseline, so that every
  feature has a known starting state to return to.
- **One feature at a time.** A feature starts only from a clean working tree
  (paths under `.ai-team/` are ignored). `team-lead` records the commit it
  started from as the feature's `Start Point`. Commit a finished feature before
  starting the next one. If the tree is not clean, `team-lead` lists the
  uncommitted paths and offers to commit them as a checkpoint; it starts the
  feature only after that commit, or after the user has cleaned up.
- **In scope:** new features and behaviour-changing fixes. Start them with
  `/team-lead <feature idea or feature-slug>`. Do not write code, tests or
  infrastructure for in-scope work outside the pipeline.
- **Fast path:** a change the user calls trivial (typo, comment, formatting,
  one-line fix, config value), or any request where the user says to skip the
  pipeline, is done directly in the main conversation.
- **Not gated:** questions, code reading, exploration and reviews that change
  no files.
- **Project overrides:** a project may replace the git rules and the fast
  path above with its own (A6).

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

- A stage that does not run is recorded as `SKIPPED` in the ledger.
- **Stage 1 runs in the main conversation**, because it is a dialogue with the
  user. When the `pm` handoff reports `DONE`, `team-lead` continues the feature
  in the same turn. If it does not, run `/team-lead <feature-slug>`.
- **Before Stage 8** `team-lead` writes the change record (A4).
- **Rounds.** `Round` starts at 0 and increases by 1 on every backward route.
  A `PENDING` stage is completed only by a handoff whose `Round` equals the
  ledger's current `Round`; older handoffs are stale. A stage that is `DONE` in
  the ledger stays `DONE` until a backward route resets it.

---

## B3. Design Gate

After Stage 4, `team-lead` summarises the spec, copy, UI spec and ADR and waits
for the user's approval before Stage 5 starts. The user answers with an
approval, a change request, or a stop (B5).

- **Approval is tied to a design.** `team-lead` records the spec and ADR
  `Revision` numbers the approval was given for. Any backward route to Stages
  1-4 sets the gate back to `PENDING`. The user approves again, seeing what
  changed, before Stage 5 resumes.
- **Change requests:** only while the gate is open. The user asks with
  `/team-lead <feature-slug> <change>`. It is a backward route to the owner of
  the affected artifact and does not count toward the loop cap (B4).
- **After approval there are no change requests.** The feature runs to
  `READY_FOR_MERGE` unless the user stops it (B5).

---

## B4. Defect Routing and Escalation

1. **Owner.** `team-lead` routes each `Blocked On` area to the owner of that
   area in the Write Isolation table (A2).
2. **Test failure (Stage 7 -> 5 or 6):** `test-engineer` reports `DEFECTS`
   blocked on `Source` or `Infra`. Tests are never weakened to pass.
3. **Security block (Stage 8 -> owners):** each blocker goes to the owner of
   the area it names. A vacuous test (one that cannot fail whatever the code
   does) and an AC or INV with no test are blockers on `Tests`, never
   observations.
4. **Re-run rule:** on every backward route `team-lead` increments `Round`. The
   stage routed to, and every later stage that is not `SKIPPED`, returns to
   `PENDING` and runs again in order. A route to Stages 1-4 also re-opens the
   design gate, and `team-lead` decides the conditional stages (2, 3, 6) again
   from the revised spec and ADR.
5. **Loop cap:** a feature gets at most 3 backward routes for test defects, 3
   for security blocks, and 5 for other escalations raised by agents. Changes
   the user requests at the design gate do not count. On the next counted
   route, or when a handoff or blocker is blocked on `user`, `team-lead` sets
   `BLOCKED` and asks the user. If the user says to continue, that counter
   starts again at 0.

---

## B5. Stopping a Feature

The user can stop a feature at any point: at the design gate, at any other
stop, or after interrupting a stage that is still running. The command is
`/team-lead <feature-slug> stop`. Both ways of stopping return the project to
the state it was in when the feature started. `team-lead` never chooses for
the user. It lists everything that differs from the feature's `Start Point`,
taken from git, and asks:

1. **Roll back:** all work done on the feature is deleted. Modified files go
   back to their last commit, and new files, the handoffs and the ledger are
   removed.
2. **Shelve:** the work is kept in a git stash named `ai-team/<feature-slug>`
   and the working tree goes back to the last commit. The ledger is set to
   `REJECTED` and the feature gets a line in
   `.ai-team/state/rejected-features.md`.

- The list is built from git, so it includes the partial work of an
  interrupted stage and any edits the user made by hand since the feature
  started. A rollback discards those too.
- Commits made after the `Start Point` are never undone by `team-lead`. It
  names them and leaves them to the user.
- A shelved feature is ignored when `team-lead` looks for work to continue.
  `/team-lead <feature-slug> resume` needs a clean working tree, restores the
  stash, and re-opens the design gate. It never continues without a new
  approval.
- `git stash drop` or `git stash clear` destroys shelved work.
