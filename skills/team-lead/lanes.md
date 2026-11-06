# Lanes

This is how `team-lead` chooses the lane of a new request, and how a request
leaves its lane. A request takes one of three lanes:

- **Trivial:** the change is made directly in the conversation. It has no
  stage, no ledger, no handoff and no review.
- **Fast path:** a feature that skips the stages the project names, and with
  them the spec, the ADR and the design gate.
- **Full:** a feature that runs through every stage.

The two lighter lanes are the project's own. Each exists only where the
project file defines it, as a `Trivial Lane` or a `Fast Path` override, and
its conditions are the project's rule: you apply them, and only the user
changes them. Without a `Trivial Lane` override, the first lines of the
project file say what becomes of a change that the user calls trivial: as a
rule, that it is done directly. That is the trivial lane with one condition,
the user's word.

---

## Choose

Choose the lane before anything is created for the request: no slug, no
branch and no ledger.

1. **Another session.** If the project's `Git Workflow` override has a new
   request handed to another session before any work, hand it over and
   choose nothing. The lane is chosen where the change will be made.
2. **The files.** Where the project defines a lighter lane, find the files
   in `Source` and `Infra` that the change would touch, with `Read`, `Glob`
   and `Grep`, and name each one. Name no test file: tests are written in
   their own area. On a fast path these files stand in for the Allowed Blast
   Radius. A request whose files you cannot name runs in full, and so does
   one that touches a file in `Infra`: a fast path does not run Infra, which
   builds only from an ADR, and `ai_team` refuses such a file.
3. **The lightest lane that fits.** Hold the request and its files against
   the conditions of the trivial lane, then against those of the fast path.
   The request takes the first lane whose conditions all hold, and runs in
   full when neither does. Judge a condition about the size of the change by
   what the change needs. A guess that proves wrong is put right later
   (`Leave`).
4. **The user's word for trivial.** A trivial change gets no review, so no
   request takes that lane on your judgement alone. Whatever the project's
   rule says, the user must have called the change trivial or asked for that
   lane, in the request or in an answer to you. When every other condition
   holds and only this word is missing, ask for it. Give the two choices
   with what each leads to: the trivial lane, with what it leaves out and
   what the project's rule still asks of the change, and the next lane that
   fits.
5. **A lane the request names.** A request that asks for a lighter lane than
   the conditions allow does not take it, and it starts on no heavier lane
   unasked. Tell the user which condition stands against it, and ask how to
   go on: in the lane that fits, or not at all. Add that the rule is theirs
   to change in the project file. You move such a change to another lane
   without asking only where the project's rule orders that move in so many
   words, as "say so and move it to the fast path" does, and where that
   lane's own conditions hold; say that you did. A sentence that only names
   the lane of all other changes, as "anything else takes the fast path"
   does, is no such order. A request that asks for a heavier lane than it
   needs gets it.
6. **Say it.** Tell the user the lane and the condition that decided it:
   when the first stage starts, or in your next report if you did not. For a
   feature, give the same to `ai_team new` as `--lane-reason`, which writes it
   into `History`. On a fast path, `ai_team new` also takes `--lane fast`, the
   files of step 2 as `--files`, and the stages the project's rule skips
   besides the design stages and Infra as `--skip-stages`.

A feature, on the fast path or in full, goes on with the next step of
`Start a new feature`.

---

## The trivial lane

The trivial lane ends your part as the orchestrator. Create no ledger and no
dispatch, and no slug unless the project's rule for the lane needs one.

- **A feature in development here.** If `ai_team status` lists an `active`
  feature in this folder, the change would land among that feature's changes. Do not make it: tell the user that it has to wait
  for that feature, or be made in another folder.
- **Make it.** Tell the user that the change takes the trivial lane, why,
  and what the project's rule asks of it. Then make the change in the same
  turn, as the session and no longer as the orchestrator: the way the
  project's `Trivial Lane` rule says, or directly where the project has no
  such rule. Apart from `Leave` below, nothing else in the skill applies to
  it.

---

## Leave

A request leaves its lane only for a heavier one.

**A trivial change that is not trivial.** When a condition of the trivial
lane proves false while the change is made, as when it needs a second file,
stop making it, and undo your own edits for it and nothing else. From there
it is a request that asked for a lighter lane than the conditions allow: go
on as `Choose`, step 5, says.

**A fast path that meets its edge.** A stage on a fast path can be blocked on
the area of a stage that the fast path skips. There is no stage to route
that to: `ai_team` sets `BLOCKED`, notes the edge in `History`, and its action
is `ask_user` with the kind `fast_path_edge`. Then:
- **One more file.** The stage needs a file that `Files` does not name. Hold
  the request against the conditions again, with that file added; a file in
  `Infra` never fits. If they all hold, run `ai_team fast-path <slug> add-file --path <file> --dispatch`
  without asking: it adds the file, closes the item, and runs the blocked
  stage again (`Round` goes up, no other stage is reset, nothing counts
  toward a cap).
- **Anything else,** such as a file that breaks a condition, or a request
  that leaves open what a design stage would have settled: ask the user,
  with what each way leads to. The answer can also come in a later run.
  - *All the stages:* `ai_team fast-path <slug> to-full --dispatch`. Every
    stage the fast path skipped is `PENDING` again, the design gate is
    `PENDING`, your notes say that the feature began on the fast path and
    which files its stages changed, and the feature goes back to the first
    stage, counting toward no cap. An item that was blocked on a skipped
    stage stays open for that stage, which finds it in its dispatch. What was
    built stays in the folder, and the stages that built it run again, now on
    the spec and the ADR.
  - *Stay on the fast path:* the user answers what was open, narrows the
    change, or changes the rule in the project file. Check the conditions
    once more. If they hold, run `ai_team fast-path <slug> stay --direction
    "<the answer>" [--files <the files, when they changed>] --dispatch`.
  - *Stop the feature:* `Stop` of the feature's git workflow.
