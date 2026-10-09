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

`Workflow` says where a feature is developed when the command does not: in a
worktree of its own, in place in this folder, or `ask` each time. An `only`
value forbids the other workflow. `Worktree setup` is what the agents follow
in a worktree, which starts as a fresh checkout.

## Mock-up

- **Mock-up:** <`none`, or: the commands that build and serve the product in
  the folder of a feature; the command that takes a screenshot of a page at
  a width and writes it to a file; which pages may be opened; the widths>

For a feature that changes a screen, the UI stage builds the product, takes a
screenshot of the real page, makes a mock-up page from it and takes a
screenshot of that. `team-lead` shows both when it asks for approval of the
design. The stage runs only the commands written here and opens only the pages
allowed here. With `none` it draws a sketch in the UI spec instead.

## Overrides for this project

A rule written here wins over the matching default in the pipeline rules and
in the skills. The rules say what may be overridden: gates, stage notes, the
git workflow, the fast path and the trivial lane.

- None.
