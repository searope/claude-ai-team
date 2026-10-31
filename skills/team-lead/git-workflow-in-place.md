# Git Workflow: In Place

This is how `team-lead` carries out the in-place workflow. The feature is
developed in the folder the session is in, on the branch checked out there,
and the user commits it. Skip every part that the project's `Git Workflow`
override replaces, and do what the override says instead.

---

## Start

First run `ai_team status`. If it lists an `active` feature, another feature is
in development here, whether or not it has changed a file yet: tell the user to
finish, roll back or shelve that feature first, and stop.

Then run `git status --porcelain --untracked-files=all`, which lists every new
file and not only its folder. Leave `.claude/worktrees/` out of this check and
never stage it: it holds the worktrees of other features. If the working tree
is not clean, list the uncommitted paths and do this:
- **Offer a checkpoint commit.** Ask the user whether you should
  commit the listed paths so the feature has a clean starting state (use
  `AskUserQuestion` when it is available), and wait. If some paths belong to a
  feature that is `READY_FOR_MERGE`, say so: committing them accepts that
  feature. Flag likely secrets (`.env`, key or credential files) and
  dependency or build directories that no `.gitignore` covers, and recommend
  leaving those out.
- **On yes:** stage the paths you listed, less any the user left out, and
  commit with the message `Checkpoint before AI team feature`. Then run the
  status again. A path that it still lists keeps the feature from starting:
  it has to be ignored by git, or the user deals with it. Name those paths,
  and stop.
- **On no:** stop. The feature does not start on a dirty tree.

The feature's `Start Point` is `git rev-parse HEAD` once the tree is clean.
Give it to `ai_team new` with `--workflow in-place`.

---

## Deliver

1. Run `ai_team verify-delivery <slug>`. If `unchanged` is false, something
   changed after the review (`changed_paths`): run
   `ai_team review-again <slug> --dispatch`, a backward route to Security that
   counts toward no cap. The second time in a row it sets `BLOCKED` and names
   the paths that keep changing.
2. Run `ai_team delivered <slug>`: the feature is `READY_FOR_MERGE`. Tell the
   user which files to review and commit (the change record lists them), and
   remind them that the next feature can start only after that commit.

---

## Stop

Present the two options, a rollback or shelving, together with the rollback
list, and wait for the answer (use `AskUserQuestion` when it is available).
Build the list with `ai_team stop-list <slug>`, which takes it from git, not
from handoffs, so that the partial work of an interrupted stage is included:
- `uncommitted`: every modified, deleted or untracked path.
- `commits`: commits made since the feature started (`<Start Point>..HEAD`).
  You cannot undo those; name them and leave them to the user.
- `working_files`: the feature's files under `.ai-team/`, which git ignores:
  its ledger, handoffs, mock-up, change record, notes and snapshots.
- Warn that a rollback deletes uncommitted work for good, and that the list
  may hold edits the user made by hand since the feature started. Those go too
  unless the user saves them first.

Touch nothing that was not on the list you showed. If the user asks for a
rollback directly, without having seen the list, show the list and get a
confirmation first.

**Roll back:**
1. Restore every modified or deleted tracked path on the list with
   `git restore --staged --worktree -- <paths>`.
2. Delete every untracked path on the list.
3. Run `ai_team purge <slug> --confirm`: it deletes the feature's working
   files under `.ai-team/`, its ledger last.
4. Run `git status --porcelain` and confirm that nothing of the feature is
   left. Report what you removed and what you left for the user.

For a feature that is already shelved, its work is in the stash: show
`git stash show --include-untracked --name-only <stash>`, and on confirmation
drop that stash and run `ai_team purge <slug> --confirm`.

**Shelve:**
1. Run `git stash push --include-untracked -m "ai-team/<feature-slug>"`. It
   stores the work and returns the working tree to the last commit. The files
   under `.ai-team/` are ignored by git and stay where they are.
2. Run `ai_team set <slug> --gate-status REJECTED --design-gate-pending
   --shelved-stash "ai-team/<feature-slug>" --history "Shelved at <stage>:
   <reason>"`.
3. Tell the user the work is kept in that stash, and that `git stash drop` or
   `git stash clear` would destroy it.

---

## Resume

1. Carry out `Start`.
2. Find the stash by its message in `git stash list` and restore it with
   `git stash pop <stash ref>`. If it does not apply cleanly, do not leave a
   half-applied state. Git keeps the stash in that case, so put the working
   tree back to the last commit: `git restore --staged --worktree -- .`, then
   delete the untracked files that the pop brought: the ones that
   `git status --porcelain --untracked-files=all` lists now and did not list
   in `Start`. Delete nothing under `.claude/worktrees/`. Leave the feature
   shelved, tell the user which commit and file conflict, and stop.
3. Run `ai_team set <slug> --shelved-stash none --start-point <the hash git
   rev-parse HEAD prints> --gate-status IN_PROGRESS --history "Resumed"`.
   `Design Gate` stays `PENDING`, and a new round starts. Go on with the action
   it returns, as section 3 of the skill says.
