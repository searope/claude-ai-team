# Default Git Workflow: Procedure

This is how `team-lead` carries out `Git Workflow` in the pipeline rules when
the project does not replace it. It has four parts: `Start`, `Deliver`, `Stop`
and `Resume`. Skip every part that the project's `Git Workflow` override
replaces, and do what the override says instead.

---

## Start

**Setup commits.** When setup created or changed files, commit them:
- **You created the repository:** `git add -A` and commit with the message
  `Baseline before AI team pipeline`. Look at what would be added first. If it
  includes likely secrets (`.env`, key or credential files) or dependency and
  build directories (`node_modules/`, virtual environments, `dist/`, `build/`)
  that no `.gitignore` covers, stop and ask the user before committing.
- **The repository existed and its working tree was clean before setup:**
  commit exactly the files you created or changed, with the message
  `Install AI team pipeline`.
- **It was not clean:** leave them uncommitted.
- If git refuses to commit because no user name or email is configured, stop
  and tell the user to set them.

**Clean start.** Before the first stage of a new feature, and before a resume,
run `git status --porcelain`. If the working tree is not clean, list the
uncommitted paths and do one of these:
- **Another feature is still in development** (its ledger is `IN_PROGRESS`,
  `AWAITING_USER` or `BLOCKED`): do not offer a commit. Tell the user to
  finish, roll back or shelve that feature first, and stop.
- **Otherwise, offer a checkpoint commit.** Ask the user whether you should
  commit the listed paths so the feature has a clean starting state (use
  `AskUserQuestion` when it is available), and wait. If some paths belong to a
  feature that is `READY_FOR_MERGE`, say so: committing them accepts that
  feature. Flag likely secrets (`.env`, key or credential files) and
  dependency or build directories that no `.gitignore` covers, and recommend
  leaving those out.
- **On yes:** stage the paths you listed, less any the user left out, commit
  with the message `Checkpoint before AI team feature`, and continue.
- **On no:** stop. The feature does not start on a dirty tree.

The feature's `Start Point` is `git rev-parse HEAD` once the tree is clean.
Keep it for the ledger.

---

## Deliver

Set `READY_FOR_MERGE`, tell the user which files to review and commit, and
remind them that the next feature can start only after that commit.

---

## Stop

Present the two options of the rules together with the rollback list, and wait
for the answer (use `AskUserQuestion` when it is available). Build the list
from git, not from handoffs, so that the partial work of an interrupted stage
is included:
- `git status --porcelain`: every modified, deleted or untracked path.
- `git log <Start Point>..HEAD`: commits made since the feature started. You
  cannot undo those; name them and leave them to the user.
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
3. Delete the feature's handoffs and change record, then its ledger.
4. Run `git status --porcelain` and confirm that nothing of the feature is
   left. Report what you removed and what you left for the user.

For a feature that is already shelved, its work is in the stash: show
`git stash show --include-untracked --name-only <stash>`, and on confirmation
drop that stash and delete the feature's files under `.ai-team/`.

**Shelve:**
1. Run `git stash push --include-untracked -m "ai-team/<feature-slug>"`. It
   stores the work and returns the working tree to the last commit. The files
   under `.ai-team/` are ignored by git and stay where they are.
2. In the ledger set `Gate Status` to `REJECTED`, `Design Gate` to `PENDING`
   and `Shelved Stash` to `ai-team/<feature-slug>`. Add a `History` line with
   the stage the feature stopped at and the reason.
3. Tell the user the work is kept in that stash, and that `git stash drop` or
   `git stash clear` would destroy it.

---

## Resume

1. Carry out the clean start above.
2. Find the stash by its message in `git stash list` and restore it with
   `git stash pop <stash ref>`. If it does not apply cleanly, do not leave a
   half-applied state. Git keeps the stash in that case, so put the working
   tree back to the last commit: `git restore --staged --worktree -- .`, then
   delete the untracked files `git status --porcelain` still lists (the tree
   was clean before the pop, so they all came from it). Leave the feature
   shelved, tell the user which commit and file conflict, and stop.
3. In the ledger set `Shelved Stash` to `none`, `Start Point` to the current
   `git rev-parse HEAD` and `Gate Status` to `IN_PROGRESS`. `Design Gate`
   stays `PENDING`.
