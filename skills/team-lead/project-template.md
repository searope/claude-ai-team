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

Edit this block to match the project. Agents use it to tell write areas apart,
and the pipeline's guard holds each stage to its area by it. Only the paths in
backticks count, matched like lines of `.gitignore`: `src/` is a folder named
`src` at any depth, `/src/` only the one at the root, `*.test.*` a file name
anywhere. A path in more than one area is `Tests` first, then `Infra`, then
`Source`.

- **Source:** `src/`, `lib/`, `app/` (includes design-token, theme and locale
  files)
- **Tests:** `tests/`, plus colocated test files (`*_test.*`, `*.test.*`,
  `*.spec.*`)
- **Infra:** `Dockerfile*`, `docker-compose*`, `.github/`, other CI config,
  IaC, `migrations/`

## Git Workflow

- **Workflow:** worktree only
- **Worktree setup:** <what a worktree gets besides the files git tracks and
  how tools are run in it, or `none needed`, or `not decided`>

`Workflow` says where a feature is developed: `worktree only` (the default: a
worktree of its own, and a command asking for in-place is refused),
`worktree`, `in-place`, `in-place only`, or `ask` each time. `Worktree setup` is what the agents follow
in a worktree, which starts as a fresh checkout.

## Mock-up

- **Mock-up:** <`none`, or: the commands that build and serve the product in
  the folder of a feature; the command that takes a screenshot of a page at
  a width and writes it to a file; which pages may be opened; the widths>

For a feature that changes a screen, the UI stage builds the product, takes a
screenshot of the real page, makes a mock-up page from it and takes a
screenshot of that. `team-lead` shows both and waits for the user's approval
of the look before the next stage runs. The stage runs only the commands written here and opens only the pages
allowed here. With `none` it still makes the mock-up page, from the project's
files, but takes no screenshots and cannot check how the page renders.

## Scans

`ai_team.py` runs these before every review, from the feature's folder, and
gives the reviewers their output. A scan fails on a non-zero exit code, or when
its output matches the pattern after `fails when`. Each is a list item with the
command in backticks. `ai_team.py propose-gates` suggests them for the stack.
The user approves a list once, and again whenever it changes.

- None.

## Second Review

- **Second Review:** no

`yes` adds stage 9: a second read-only review of the same change on another
model (the `second-reviewer` skill), after Security. It costs one more review
per round.

## Overrides for this project

A rule written here wins over the matching default in the pipeline rules and
in the skills. The rules say what may be overridden: gates, stage notes, the
git workflow, the fast path and the trivial lane. Gates and stage notes name
their stage by its number, as in `7. Testing`.

- None.
