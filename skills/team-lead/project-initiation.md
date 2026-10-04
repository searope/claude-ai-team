# Project Initiation

This is what `team-lead` does on its first run in a project, when the project
has no project file yet. It asks the user how the project works, writes the
project file, and commits what it set up.

---

## 1. Ask the user

Ask this question (use `AskUserQuestion` when it is available). Give each
choice together with what it leads to, in the words below. If the user cannot
be asked, write `ask`.

**How should features in this project be developed?**
- **Worktree.** Each feature gets a folder and a branch of its own, so several
  features can run at once. `team-lead` commits each feature on its branch and
  merges the base branch into it before testing. The user merges the branch
  when it is ready. A worktree has only the files git tracks.
- **In place.** Features run one at a time in this folder, on the branch that
  is checked out. `team-lead` makes no commits. The user reviews and commits
  each feature, and the next one can start only after that commit.
- **Ask each time.** `team-lead` asks this question whenever a feature starts
  from this folder.

Tell the user that the answer goes on the `Workflow` line of the project file
and can be changed there, and that a word in the command, `worktree` or
`in-place`, overrides it for one feature.

---

## 2. Work out the worktree setup

Nothing is copied into a worktree. It has only the files git tracks, and tools
use the environment of this folder, the project's main folder. Find out what
that means here: run `git status --porcelain --ignored` and look at what git
ignores.
- **An environment the tools need,** such as a Python virtual environment:
  note how a tool is started from it, by the full path of its interpreter or
  command.
- **Secret files,** such as `.env`: they stay here. No worktree gets one.
- **Everything else,** such as build output, caches, logs and editor folders,
  is not needed.

Put the result on the `Worktree setup` line, in one or two sentences:
- how a tool is started in a worktree, and
- that it is started from the worktree's own root, so that the worktree's code
  is the code that runs. For Python this means running modules
  (`python -m ...`); a script that is run as a file has to put the worktree's
  root first on its import path itself.

If this folder has nothing a worktree would lack, write `none needed`. If you
cannot tell how the tools are started, write `not decided` and ask the user.

Tell the user what you wrote and what it leads to:
- All features share this folder's environment. A feature that adds or
  upgrades a dependency changes it for every other feature and for this
  folder, and it has to be installed here.
- No worktree holds secrets. A step that needs a real one stops and asks the
  user, so tests have to run without them.
- A project that needs more in its worktrees can list ignored files in a
  `.worktreeinclude` file in this folder: Claude Code then copies them into
  each new worktree. `team-lead` does not write that file.

---

## 3. Write the project file

- `Read` the template and `Write` it to `.claude/ai-team-project.md`, with the
  project's name in the title, the user's answer on the `Workflow` line and
  the result of step 2 on the `Worktree setup` line. Change nothing else in
  the template.
- Add the import. If `CLAUDE.md` exists in the project root, append the line
  `@.claude/ai-team-project.md` unless it is already there. If only
  `.claude/CLAUDE.md` exists, append `@ai-team-project.md` there. If neither
  exists, create a root `CLAUDE.md` holding a project heading and the import
  line.
- Make sure `.gitignore` lists `.ai-team/` and `.claude/worktrees/`, creating
  the file if it is missing. The first holds the pipeline's working files,
  and the second is where worktrees are made.

---

## 4. Commit what you set up

- **You created the repository:** `git add -A` and commit with the message
  `Baseline before AI team pipeline`. Look at what would be added first. If it
  includes likely secrets (`.env`, key or credential files) or dependency and
  build directories (`node_modules/`, virtual environments, `dist/`, `build/`)
  that no `.gitignore` covers, stop and ask the user before committing.
- **The repository existed and its working tree was clean before you began:**
  commit exactly the files you created or changed, with the message
  `Install AI team pipeline`.
- **It was not clean:** leave them uncommitted, and say so.
- If git refuses to commit because no user name or email is configured, stop
  and tell the user to set them.

---

## 5. Tell the user

- What you created and what you committed.
- That they should adjust `Project Paths` in the project file.
- **The repository has a remote:** a worktree starts from the remote's base
  branch, so it has the project file only once this commit is there. Until
  the user pushes the commit, or merges it there, no feature can run in a
  worktree.
- **You are in a worktree yourself:** the project file is on this worktree's
  branch only. Other worktrees get it when that branch is merged.
