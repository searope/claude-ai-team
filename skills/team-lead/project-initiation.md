# Project Initiation

This is what `team-lead` does on its first run in a project, when the project
has no project file yet. It asks the user how the project works, writes the
project file, and commits what it set up.

---

## 1. Ask the user

Ask how features in this project should be developed (use `AskUserQuestion`
when it is available). If the user cannot be asked, write `ask`. There are
three choices:
- **Worktree** and **In place**, the two git workflows. Give each together
  with what it leads to: the rows of the table under `Start a new feature` in
  the skill, in plain sentences. For the worktree, add that it has only the
  files git tracks.
- **Ask each time:** `team-lead` asks this question whenever a feature starts
  from this folder.

Tell the user that the answer goes on the `Workflow` line of the project file
and can be changed there, and that a word in the command, `worktree` or
`in-place`, overrides it for one feature.

---

## 2. Work out the worktree setup

A worktree is a fresh checkout: it has only the files git tracks. What a
feature needs beyond them depends on the project, so work it out here and
write it on the `Worktree setup` line. Run `git status --porcelain --ignored`
to see what git ignores in this folder, and settle these four things.

**1. The environment the tools need,** such as a virtual environment or a
folder of installed packages. There are three ways. Take the first one unless
the project speaks against it:
- **Shared.** Tools in a worktree use this folder's environment, started by
  the full path of its interpreter or command. It costs nothing. It fits
  while the project's dependencies stay as they are: a feature that adds or
  changes one stops and asks the user, because installing it here would
  change the environment under every other feature and under this folder.
  For Node the line only has to say that the packages are shared: from a
  worktree inside this folder, Node finds this folder's `node_modules` by
  itself.
- **Thin.** Each worktree gets a small environment of its own that reuses
  this folder's packages. For Python that is an empty virtual environment
  made without pip, with one path file in its packages folder that holds the
  path of this folder's packages folder. It takes under a second and under a
  megabyte. A feature's new or changed dependency is installed there and
  stays in that worktree.
- **Its own.** The project's setup command builds a full environment in each
  worktree. Use it where the project's tools make that cheap, or where
  neither of the others works. Say what it costs in time and disk.

**2. How the worktree's own code comes first.** An environment in which the
project is installed from this folder runs this folder's code, whatever
folder a tool is started in, and reports no error. Find out how the project is
installed and where its source lies, and say what makes a tool pick up the
worktree's code. For Python, set `PYTHONPATH` to the worktree's source folder
(`.`, or `src` in a `src` layout) on every command. Starting modules from the
root is not enough: in a `src` layout that still imports this folder's code.

**3. Settings and secrets,** such as `.env`. They stay here, and no worktree
gets a copy. Look in the code for how the project loads them, because that
decides what a tool in a worktree sees:
- **Read from the working folder:** nothing. A step that needs a real value
  stops and asks the user.
- **Searched for in parent folders,** as python-dotenv does by default: this
  folder's file with its real keys, because worktrees lie inside this folder.
- **Taken from the process environment:** whatever is set there, in every
  folder.

If the project cannot start or run its tests without the file, tell the user,
and give the two ways out with what each leads to:
- A tracked file with values that are not secret gives tests their settings
  and puts no secret in any worktree. The project has to provide it.
- Listing the file in `.worktreeinclude` makes Claude Code copy it into each
  new worktree. Every worktree then holds the real keys, and the copies go
  stale when a key changes.

`team-lead` writes neither file.

**4. Local data and build output,** such as databases, downloaded data,
generated pages, caches and logs. A worktree starts without them, and what a
tool generates there stays there. If the project needs local data to run, say
which, and ask the user how a worktree is to get it.

Never link a folder of this folder into a worktree, and tell the user not to.
When the worktree is removed, git can delete what the link points to.

Put the result on the `Worktree setup` line, in a few sentences that an agent
can follow to the letter:
- which of the three environments, and the exact way a tool is started in a
  worktree;
- for a thin environment or one of its own, the commands that create it when
  it is missing;
- what makes the worktree's code come first;
- what a feature does when it needs a new dependency, and what a tool in a
  worktree sees of the settings file.

If this folder has nothing a worktree would lack, write `none needed`. If you
cannot tell how the tools are started, write `not decided` and ask the user.

Tell the user what you wrote and what it leads to, in plain words: what the
features share and what each has of its own, what happens when a feature
changes a dependency, and what a tool in a worktree can see of the secrets.
Say which of the three environments you took, and what the other two would
cost, so that the user can choose another.

---

## 3. Write the project file

- Work out the project's paths. Look at what the repository holds (`Glob`) and
  decide which of its paths are `Source`, `Tests` and `Infra`, as
  `Write Isolation` in the rules uses those names. Token, theme, style and
  locale files are `Source`; CI configuration, container files,
  infrastructure code and migrations are `Infra`. For an area you cannot
  place, keep the template's line.
- `Read` the template and `Write` it to `.claude/ai-team-project.md`, with the
  project's name in the title, those paths in `Project Paths`, the user's
  answer on the `Workflow` line and the result of step 2 on the
  `Worktree setup` line. Change nothing else in the template.
- Add the import. If `CLAUDE.md` exists in the project root, append the line
  `@.claude/ai-team-project.md` unless it is already there. If only
  `.claude/CLAUDE.md` exists, append `@ai-team-project.md` there. If neither
  exists, create a root `CLAUDE.md` holding a project heading and the import
  line.
- Make sure `.gitignore` lists `.ai-team/` and `.claude/worktrees/`, creating
  the file if it is missing. The first holds the pipeline's working files,
  and the second is where worktrees are made. If the `Worktree setup` has a
  worktree create an environment, make sure git ignores that folder too.

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
- The three lines of `Project Paths` as you wrote them. They decide what each
  build stage may write, so ask the user to check them. They can be corrected
  in the project file at any time.
- **The repository has a remote:** a worktree starts from the remote's base
  branch, so it has the project file only once this commit is there. Until
  the user pushes the commit, or merges it there, no feature can run in a
  worktree.
- **You are in a worktree yourself:** the project file is on this worktree's
  branch only. Other worktrees get it when that branch is merged.
