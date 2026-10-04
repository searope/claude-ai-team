# AI Team Pipeline: <project name>

Feature work in this project runs through the AI team pipeline.

- Start a new feature or a behaviour-changing fix with
  `/team-lead <description>` or `/team-lead <issue number>`, and continue one
  with `/team-lead <feature-slug>`. Do not write code, tests or infrastructure
  for such work outside the pipeline.
- A change the user calls trivial (typo, comment, formatting, one-line fix,
  config value), and any request where the user says to skip the pipeline, is
  done directly.
- Questions, code reading, exploration and reviews that change no files are
  not gated.

The pipeline rules ship with the `team-lead` skill and are read from there.
This file holds only what is specific to this project. `team-lead` creates it
once and never overwrites it.

## Project Paths

Edit this block to match the project. Agents use it to tell write areas apart.

- **Source:** `src/`, `lib/`, `app/` (includes design-token, theme and locale
  files)
- **Tests:** `tests/`, plus colocated test files (`*_test.*`, `*.test.*`,
  `*.spec.*`)
- **Infra:** `Dockerfile*`, `docker-compose*`, `.github/`, other CI config,
  IaC, `migrations/`

## Git Workflow

- **Workflow:** <ask | worktree | in-place | worktree only | in-place only>
- **Worktree setup:** <what a worktree gets besides the files git tracks and
  how tools are run in it, or `none needed`, or `not decided`>

`Workflow` decides where a feature is developed when the command does not say
and the session is in the main folder. With `worktree`, each feature gets a
folder and a branch of its own and `team-lead` commits there. With `in-place`,
features run one at a time in this folder and you commit them. With `ask`,
`team-lead` asks each time. An `only` value forbids the other workflow.

`Worktree setup` is what the agents follow when a feature runs in a worktree,
which starts as a fresh checkout: which environment the tools use, what makes
the worktree's own code the code that runs, what a feature does when it needs
a new dependency, and what a tool there sees of your settings file.

## Overrides for this project

A rule written here wins over the matching default in the pipeline rules and
in the skills. The rules say what may be overridden: gates, stage notes, the
git workflow and the fast path.

- None.
