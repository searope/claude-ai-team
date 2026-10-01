# AI Team Pipeline

**Pipeline Version:** 3.3

Feature work in this project runs through a 9-stage pipeline operated by nine
skills. These rules bind the main conversation and every pipeline agent.

This file lives at `.claude/ai-team-pipeline.md` and is imported from the
project `CLAUDE.md`. Its master copy ships with the `team-lead` skill, which
installs it and reports when the project copy falls behind.

---

## 0. Scope & Prerequisites

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
  path above with its own, in section 8.

---

## 1. Project Paths

Edit this block to match the project. Agents use it to tell write areas apart.

- **Source:** `src/`, `lib/`, `app/` (includes design-token, theme and locale
  files)
- **Tests:** `tests/`, plus colocated test files (`*_test.*`, `*.test.*`,
  `*.spec.*`)
- **Infra:** `Dockerfile*`, `docker-compose*`, `.github/`, other CI config,
  IaC, `migrations/`

---

## 2. Write Isolation

No agent may write outside its own area.

| Area | Only writer | Limit |
| :--- | :--- | :--- |
| `docs/specs/` | `product-manager` | |
| `docs/copy/` | `copywriter` | |
| `docs/design/` | `ui-designer` | |
| `docs/adr/` | `system-architect` | |
| Source | `software-engineer` | Files in the ADR's `Allowed Blast Radius (Source)` |
| Tests | `test-engineer` | Never production code |
| Infra | `devops-engineer` | Files in the ADR's `Allowed Blast Radius (Infra)` |
| `.ai-team/state/` | `team-lead` | |
| `.ai-team/scratchpad/<feature-slug>-<role>-context.md` | The agent with that role | Own file only |
| Nothing | `security-reviewer` | Has no file-writing tools; `team-lead` stores its report |

- Tool limits are enforced for four agents: `copywriter`, `ui-designer` and
  `system-architect` have no shell, and `security-reviewer` has no file-writing
  tools. The path limits in this table are rules the agents follow and
  `security-reviewer` audits against `git`; they are not technically enforced.
- An agent that finds a problem in another agent's area does not fix it. It
  reports `ESCALATE` (section 6).
- Only `team-lead` dispatches agents. Agents do not invoke other pipeline
  skills.
- No agent commits, pushes or merges feature work. The user does that after
  `READY_FOR_MERGE`. The only commits an agent makes are `team-lead`'s setup
  commits on the first run (the baseline and the pipeline install) and a
  checkpoint commit the user agreed to before a feature starts.
- Nothing is deleted or stashed except by `team-lead`, and only after the user
  chooses how to stop a feature (section 7).

---

## 3. Artifact Topology

All agents communicate through these paths. Do not invent new directories for
specs or state.

```text
.
+-- CLAUDE.md                                   # imports the file below
+-- .claude/
|   +-- ai-team-pipeline.md                     # this file
+-- docs/
|   +-- specs/<feature-slug>.md                 # Stage 1: product spec
|   +-- copy/<feature-slug>-copy.md             # Stage 2: new text
|   +-- copy/<feature-slug>-copy-audit.md       # Stage 2: old -> new rewrites
|   +-- design/<feature-slug>-ui-spec.md        # Stage 3: UI spec
|   +-- adr/<feature-slug>-adr.md               # Stage 4: architecture
+-- .ai-team/
    +-- state/<feature-slug>-pipeline.md        # ledger (team-lead)
    +-- state/rejected-features.md              # shelved features (team-lead)
    +-- scratchpad/
        +-- <feature-slug>-<role>-context.md    # one handoff per agent
```

- `<feature-slug>` is kebab-case, fixed in Stage 1, and passed as the first
  argument to every skill.
- `<role>` is one of: `pm`, `copy`, `ui`, `arch`, `dev`, `devops`, `test`,
  `security`.
- Working files live in `.ai-team/`, not `.claude/`, because Claude Code asks
  for approval on every write under `.claude/`.

---

## 4. Routing Table

`team-lead` runs the stages in this order.

| Stage | Agent | Runs when | Inputs | Output |
| :--- | :--- | :--- | :--- | :--- |
| **1. Discovery** | `product-manager` | Always | User request | Spec |
| **2. Copy** | `copywriter` | Spec flag `User-Facing Text: yes` or `UI: yes` | Spec | Copy, Copy audit |
| **3. UI/UX** | `ui-designer` | Spec flag `UI: yes` | Spec, Copy | UI spec |
| **4. Architecture** | `system-architect` | Always | Spec, Copy audit, UI spec | ADR |
| **5. Coding** | `software-engineer` | Always | Spec, Copy, UI spec, ADR | Source changes |
| **6. Infra** | `devops-engineer` | ADR says `Infra Impact: yes` | ADR, source changes | Infra files |
| **7. Testing** | `test-engineer` | Always | Spec, UI spec, ADR, source and infra changes | Tests and results |
| **8. Security** | `security-reviewer` | Always | Everything above | `PASS` / `BLOCK` |
| **9. Merge** | `team-lead` | Security `PASS` in the current round | Ledger | `READY_FOR_MERGE` |

- A stage that does not run is recorded as `SKIPPED` in the ledger.
- **Design gate:** after Stage 4, `team-lead` summarises the spec, copy, UI spec
  and ADR and waits for the user's approval before Stage 5 starts. The user
  answers with an approval, a change request, or a stop (section 7).
  - **Approval is tied to a design:** the spec and the ADR each carry a
    `Revision` number that their owner raises on every rewrite, and
    `team-lead` records the revisions the approval was given for. Any backward
    route to Stages 1-4 sets the gate back to `PENDING`. The user approves
    again, seeing what changed, before Stage 5 resumes.
  - **Change requests:** only while the gate is open. The user asks with
    `/team-lead <feature-slug> <change>`. It is a backward route to the agent
    that owns the affected artifact and does not count toward the loop cap
    (section 6).
  - **After approval there are no change requests.** The feature runs to
    `READY_FOR_MERGE` unless the user stops it (section 7).

---

## 5. Handoff Protocol

Every agent ends by writing its handoff file (section 3), starting with this
block, and returns the same block as its final message.

```markdown
# Handoff: <role> / <feature-slug>
- **Status:** <see below>
- **Round:** <`Round` from the ledger, or 0 if there is no ledger>
- **Route To:** <skill name, or `user`; omit for DONE and PASS>
- **Reason:** <one line; omit for DONE and PASS>
- **Files Touched:** <paths>
```

| Status | Used by | Meaning |
| :--- | :--- | :--- |
| `DONE` | All but `security-reviewer` | Stage complete |
| `ESCALATE` | All | Cannot complete until `Route To` changes something |
| `DEFECTS` | `test-engineer` | Failing tests expose production defects |
| `PASS` / `BLOCK` | `security-reviewer` | Gate verdict; each blocker names its owner |

`Round` starts at 0 and increases by 1 on every backward route. A `PENDING`
stage is completed only by a handoff whose `Round` equals the ledger's current
`Round`; older handoffs are stale. A stage that is `DONE` in the ledger stays
`DONE` until a backward route resets it.

---

## 6. Defect Routing & Escalation

1. **Test failure (Stage 7 -> 5 or 6):** `test-engineer` reports `DEFECTS` and
   `team-lead` routes to `software-engineer` (or `devops-engineer` for infra
   defects). Tests are never weakened to pass.
2. **Security block (Stage 8 -> owner):** `team-lead` routes each blocker to the
   owner the reviewer named. A vacuous test (one that cannot fail whatever the
   code does) and an AC or INV with no test are blockers owned by
   `test-engineer`, never observations.
3. **Blast-radius breach (Stage 5 or 6 -> 4):** an agent that must touch a file
   outside its Allowed Blast Radius stops and escalates to `system-architect`.
4. **Upstream flaw (any stage -> owner):** an ambiguous, contradictory or
   missing item in the spec, copy, UI spec or ADR is escalated to the agent
   that owns that artifact. A UI string missing from the copy goes to
   `copywriter`.
5. **Re-run rule:** on every backward route `team-lead` increments `Round`. The
   stage routed to, and every later stage that is not `SKIPPED`, returns to
   `PENDING` and runs again in order. An agent that finds nothing to change
   reports `DONE`. A route to Stages 1-4 also re-opens the design gate, and
   `team-lead` decides the conditional stages (2, 3, 6) again from the revised
   spec and ADR.
6. **Loop cap:** a feature gets at most 3 backward routes for test defects, 3
   for security blocks, and 5 for other escalations raised by agents. Changes
   the user requests at the design gate do not count. On the next counted
   route, or when a handoff or blocker names `user` as its owner, `team-lead`
   sets `BLOCKED` and asks the user. If the user says to continue, that
   counter starts again at 0.

---

## 7. Stopping a Feature

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

---

## 8. Project Overrides

This section is empty in the master copy. A project fills it in, in its own
copy, to replace defaults with its own rules. A rule written here wins over the
matching default in this file and in the skills. Everything it does not
mention stays as written.

Overrides may cover:
- **Git Workflow:** where a feature is developed, who commits, and how a
  finished feature is delivered. It replaces the clean-start rule, the rule
  that `team-lead` makes no feature commits, Stage 9, and the mechanics of
  rollback, shelve and resume.
- **Fast Path:** which changes may skip stages, and which stages they skip.
- **Gates:** the commands that must pass before a stage may report `DONE`.
- **Stage Notes:** project facts a stage must respect.

Overrides may not relax Write Isolation (section 2), the design gate for a
feature that runs Stage 4, the Handoff Protocol (section 5), or the rule that
the user chooses how a feature is stopped and confirms before anything is
deleted (section 7).

On a fast path there is no spec or ADR. `team-lead` records the request and
the files that may change in the ledger's `Fast Path` section, and that section
stands in for the spec and the Allowed Blast Radius.

### Overrides for this project
- None.
