# Project Initiation

This is what `team-lead` does on its first run in a project, when the project
has no project file yet. It asks the user how the project works, writes the
project file, and commits what it set up.

---

## 1. Ask the user

Ask both questions together (use `AskUserQuestion` when it is available). Give
each choice together with what it leads to, in the words below. If the user
cannot be asked, write `ask` and `not decided`.

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

**What should every new worktree get from this folder?** A worktree has only
the files git tracks. Ask this only when this folder has more than that. Run
`git status --porcelain --ignored` and sort what git ignores into two lists:
- **Needed** to build, run or test the project: local configuration such as
  `.env`, dependency folders such as `.venv` or `node_modules`, and local data
  files the code reads.
- **Not needed:** build output, caches, logs, editor folders, and the
  pipeline's own `.ai-team/`.

Show the user both lists, and say which of the needed entries are secret files
and which are folders that may be large. If nothing is needed, do not ask, and
write `none needed`. Offer the first choice as the recommended one.
- **Copy what is needed.** Claude Code copies the needed files and folders
  into every new worktree when it creates one. This leads to four things.
  Every worktree holds a copy of the secret files, and any agent working there
  can read them until the folder is removed. A dependency folder is copied
  whole each time, which costs time and disk space. A copied environment in
  which the project itself is installed in editable mode still points at this
  folder's code, so tools must be run from the worktree's own folder. And a
  later change in this folder does not reach worktrees that already exist.
- **Copy the files, share the environment.** Only single files such as `.env`
  are copied. Tools run from this folder's environment; the user says how, for
  example the path of its interpreter. There is no copy time. All features
  share one environment, so a feature that adds or upgrades a dependency
  changes it for every other feature and for this folder.
- **Copy nothing.** A worktree has only the files git tracks. A step that
  needs anything else stops and asks the user. Features in place are not
  affected.

---

## 2. Write the project file

- `Read` the template and `Write` it to `.claude/ai-team-project.md`, with the
  project's name in the title and the user's answers on the `Workflow` and
  `Worktree setup` lines. On the `Worktree setup` line say what a worktree
  gets and how tools are to be run there. Change nothing else in the template.
- **If anything is to be copied,** `Write` `.worktreeinclude` in the project
  root: one line for each path to copy, a folder with a trailing `/`. Claude
  Code reads that file when it creates a worktree and copies only what is
  listed there and ignored by git. Copy nothing yourself.
- Add the import. If `CLAUDE.md` exists in the project root, append the line
  `@.claude/ai-team-project.md` unless it is already there. If only
  `.claude/CLAUDE.md` exists, append `@ai-team-project.md` there. If neither
  exists, create a root `CLAUDE.md` holding a project heading and the import
  line.
- Make sure `.gitignore` lists `.ai-team/` and `.claude/worktrees/`, creating
  the file if it is missing. The first holds the pipeline's working files,
  and the second is where worktrees are made.

---

## 3. Commit what you set up

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

## 4. Tell the user

- What you created and what you committed.
- That they should adjust `Project Paths` in the project file.
- What every new worktree will get, and that `.worktreeinclude` is the place
  to change it. Worktrees that already exist are not updated.
- **The repository has a remote:** a worktree starts from the remote's base
  branch, so it has the project file only once this commit is there. Until
  the user pushes the commit, or merges it there, no feature can run in a
  worktree.
- **You are in a worktree yourself:** the project file is on this worktree's
  branch only. Other worktrees get it when that branch is merged.
