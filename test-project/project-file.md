# AI Team Pipeline: Orders board

Feature work in this project runs through the AI team pipeline.

- Start a new feature or a behaviour-changing fix with
  `/team-lead <description>`, and continue one with
  `/team-lead <feature-slug>`. Do not write code, tests or infrastructure
  for such work outside the pipeline.

The pipeline rules ship with the `team-lead` skill and are read from there.
This file holds only what is specific to this project.

## Project Paths

- **Source:** `src/`
- **Tests:** `tests/`
- **Infra:** `Dockerfile*`, `.github/`

`tools/` holds the project's own checks. It lies in no area, so no stage
changes it.

## Git Workflow

- **Workflow:** in-place only
- **Worktree setup:** none needed

## Mock-up

- **Mock-up:** none

## Scans

`ai_team.py` runs these once per round, before its first review, from the
feature's folder, and gives the reviewers their output. The first three are
the project's gates, so the tool runs them as well as the stages.

- `python -m compileall -q src`
- `python -m unittest discover -s tests -q`
- `python tools/check_infra.py`
- `python tools/secret_scan.py`

## Second Review

- **Second Review:** yes

## Overrides for this project

- **Gates:**
  - 5. Coding: `python -m compileall -q src`, `python -m unittest discover -s tests -q` pass.
  - 6. Infra: `python tools/check_infra.py` passes.
  - 7. Testing: `python -m unittest discover -s tests -q` passes.
- **Stage Notes:**
  - Every stage: Python's standard library only. A feature that needs a
    package stops and asks the owner.
  - 3. UI/UX: the board is one server-rendered page,
    `src/orders/templates/orders.html`, with one stylesheet,
    `src/orders/static/site.css`. Its design tokens are the `:root` rules
    there. Every word a visitor reads is in `src/orders/strings.json`.
  - 6. Infra: every setting in `src/orders/settings.py` is set in the
    `Dockerfile`; `python tools/check_infra.py` fails when one is missing.
