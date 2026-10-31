# Git Workflow: Worktree

This is how `team-lead` carries out the worktree workflow. The feature is
developed in a worktree, a separate folder with a branch of its own, and you
commit its work there. A worktree that you make lies under
`.claude/worktrees/`. Skip every part that the project's `Git Workflow`
override replaces, and do what the override says instead.

Two facts are used throughout:
- **Am I in a worktree?** `git rev-parse --git-dir` and
  `git rev-parse --git-common-dir` print different paths in a worktree, and
  the same path in the project's main folder.
- **The base branch** is the branch a feature starts from and is merged back
  into. The project's `Git Workflow` override may name it. Otherwise, in a
  repository with a remote named `origin`, it is what
  `git symbolic-ref --short refs/remotes/origin/HEAD` prints; run
  `git fetch origin` before you use it. Without a remote, or when that
  command fails, it is the branch checked out in the main folder, which
  `git worktree list` names first. Tell the user which branch you took.

---

## Start

1. **Get into a worktree.**
   - **The session is in the main folder:** first check that the base branch
     has the project file: `git rev-parse --verify --quiet <base>:<its path>`
     prints a hash when it does. If it prints nothing, stop before you make a
     worktree, and tell the user that the commit that set the project up has
     to reach the base branch first. Then move the session into a new worktree
     with the `EnterWorktree` tool, giving the feature's slug as `name`. The
     user or the project file asked for a worktree, which is what that tool
     requires. Claude Code may show the user a window to confirm; wait for it.
   - **The session is already in a worktree:** use it, if
     `git status --porcelain` prints nothing and `ai_team status` lists no
     `active` feature there. Otherwise stop: tell the
     user that this worktree is taken and by what, and to start the feature
     from the main folder or from a new session.
   - **The session cannot be moved** (the tool is missing, it fails, or the
     user declines): stop. Tell the user the two ways on: open a session in a
     worktree and give the same command there, or run the feature in place
     with `/team-lead in-place <request>`. Leave the second one out when the
     project file says `worktree only`.
2. **Check the project file is there.** If the worktree has no project file,
   the commit that installed it is not on the base branch yet. Stop and tell
   the user to get that commit onto the base branch first. If its
   `Worktree setup` line says `not decided`, stop as well: no stage can run a
   tool in a worktree without it. Tell the user what the line has to say, and
   that they write it into the project file.
3. **Start from the current base.** `git rev-list --count <base>..HEAD` prints
   how many commits this worktree's branch has that the base lacks. If it is
   not `0`, the feature would be built on top of them and its review would not
   see them: show them with `git log --oneline <base>..HEAD`, ask the user
   whether to build on them, and stop on no. Then
   `git rev-list --count HEAD..<base>` prints how many base commits the
   worktree lacks. If it is not `0`, run `git merge <base>`.
4. **Make the feature's branch:** `git switch -c agent/<feature-slug>`, unless
   `git branch --show-current` already prints that name.
5. The feature's `Start Point` is `git rev-parse HEAD` now. Give it to
   `ai_team new` with `--workflow worktree --base <base>`.

---

## Commit

You commit on the feature's branch, and nowhere else.

To commit, run `git status --porcelain --untracked-files=all`, which lists
every new file and not only its folder. Stage every path it lists by name with
`git add -- <paths>`, and commit. Never use `git add -A` or `git add .`.

Before you stage, look at the list. If a path looks like a secret (`.env`, a
key or a credential file) or like a dependency or build folder
(`node_modules/`, a virtual environment, `dist/`, `build/`), do not stage
anything: stop and tell the user. Such a path has to be ignored by git, never
committed.

The messages are:
- before an update: `<feature-slug>: work in progress`
- at delivery: `<feature-slug>: <the title of the spec>`, or on a fast path
  the request in short
- when shelving: `<feature-slug>: shelved work in progress`

---

## Update

Do this before each run of Testing (the action `update` says when), on
`sync`, and at the start of a resume. Add `--dispatch` to the `ai_team`
commands below only when the action `update` sent you here; on `sync` and on a
resume, step 7 comes first, and then `ai_team next <slug> --dispatch`.

If a merge is already in progress, do not start again:
`git rev-parse --verify --quiet MERGE_HEAD` prints a hash then. The conflicts
are with the stages they were routed to until each of those has reported
`DONE`. Then the merge is yours to complete: go to the end of step 6.

1. In a repository with a remote, run `git fetch origin`.
2. Run `git rev-list --count HEAD..<base>`. If it prints `0`, the branch is up
   to date: run `ai_team updated <slug>`, and you are done.
3. Commit the work so far (see Commit), if there is any.
4. Merge the base branch into the feature's branch. In the desktop app, in a
   worktree the app made, use the app's own tool for bringing a branch up to
   date with its base. Otherwise run `git merge <base>`. Never rebase.
5. **The merge is clean:** run `ai_team updated <slug> --start-point <hash>`,
   with the hash `git rev-parse <base>` prints: the base commit you merged
   becomes the `Start Point`, so that the change record still shows only the
   feature's own changes.
6. **The merge stops on a conflict:** do not resolve it yourself, and do not
   abort it. Run `ai_team route-conflicts <slug> --base <base> --dispatch`. It
   routes each conflicting file to the stage that writes its area, with the
   direction `Resolve the merge conflict with <base> in <files>`, as a
   backward route that counts toward no cap, and blocks on the user for a file
   that lies in no area. When an action is `complete_merge`, and before any
   other stage runs, complete the merge: stage the resolved files by name,
   check that `git diff --name-only --diff-filter=U` prints nothing, run
   `git commit --no-edit`, then `ai_team merged <slug> --dispatch`: the base
   commit that was merged becomes the `Start Point`.
7. **On `sync` or on a resume, when Testing has already run:** if the merge
   brought changes in, run `ai_team route-back <slug> --stage 7 --reason "the
   base branch brought changes in" --dispatch`: a backward route to Testing
   that counts toward no cap. If it brought nothing, say so and change nothing.

---

## Deliver

1. Run `ai_team verify-delivery <slug>`. It compares the change record the
   reviewer passed with one taken now. If `unchanged` is false, something
   changed after the review (`changed_paths`): do not commit. Run
   `ai_team review-again <slug> --dispatch`: a backward route to Security that
   counts toward no cap, with a new change record. The second time in a row it
   sets `BLOCKED` and names the paths that keep changing.
2. Commit the paths that `git status --porcelain --untracked-files=all` lists
   (see Commit). That commit is the delivered commit.
3. Check the base once more with steps 1 and 2 of Update, without running
   `ai_team updated`. If the base has commits the branch lacks, do not merge
   them. Say in your report how many there are, and that
   `/team-lead <feature-slug> sync` brings them in and runs Testing and
   Security again.
4. Run `ai_team delivered <slug> --commit <the delivered commit>`: the feature
   is `READY_FOR_MERGE`. Tell the user the name of the branch and what is left
   to them: merge it into the base branch, or push it and open a pull
   request, and remove the worktree afterwards.

---

## Stop

Present the two options, a rollback or shelving, together with what would be
lost, and wait for the answer (use `AskUserQuestion` when it is available).
Build the list with `ai_team stop-list <slug>`, which takes it from git, not
from handoffs:
- `uncommitted`: every uncommitted path, the partial work of an interrupted
  stage included.
- `commits`: the commits on the feature's branch (`<base>..HEAD`).
- `working_files`: the feature's files under `.ai-team/`, which git ignores:
  its ledger, handoffs, mock-up, change record, notes and snapshots.
- Warn that a rollback deletes all of these for good, and that the list may
  hold edits the user made by hand. A shelved feature keeps everything.

If the user asks for a rollback directly, without having seen the list, show
the list and get a confirmation first.

**Roll back:**
1. If a merge is in progress, run `git merge --abort`.
2. Restore every modified or deleted tracked path on the list with
   `git restore --staged --worktree -- <paths>`, and delete every untracked
   path on the list.
3. Leave the feature's branch and delete it: `git switch --detach <base>`,
   then `git branch -D agent/<feature-slug>`.
4. Run `ai_team purge <slug> --confirm`: it deletes the feature's working
   files under `.ai-team/`, its ledger last.
5. Run `git status --porcelain` and confirm that nothing of the feature is
   left. Tell the user the worktree folder is still there and can be removed.

**Shelve:**
1. If a merge is in progress, run `git merge --abort`: the base is merged
   again when the feature is resumed. Then commit the work so far (see
   Commit), if there is any.
2. Run `ai_team set <slug> --gate-status REJECTED --design-gate-pending
   --history "Shelved at <stage>: <reason>"`.
3. Tell the user three things: the work is committed on
   `agent/<feature-slug>`; the ledger and the handoffs are only in this
   worktree's `.ai-team/`, so removing the folder loses them; and the feature
   is resumed from this worktree.

---

## Resume

1. Run `ai_team set <slug> --gate-status IN_PROGRESS --history "Resumed"`.
   `Design Gate` stays `PENDING`, and a new round starts.
2. Carry out Update, then `ai_team next <slug> --dispatch`, and go on with what
   it returns.
