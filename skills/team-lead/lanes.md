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
   Radius. A request whose files you cannot name runs in full.
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
   feature, write the same into `History` when you create the ledger.

A feature, on the fast path or in full, goes on with the next step of
`Start a new feature`. Where this procedure has you ask, the user's answer
needs no new command: take it from the conversation, and go on from the step
that asked.

---

## The trivial lane

The trivial lane ends your part as the orchestrator. Create no ledger and no
dispatch, and no slug unless the project's rule for the lane needs one.

- **A feature in development here.** If a ledger in this folder is
  `IN_PROGRESS`, `AWAITING_USER` or `BLOCKED`, the change would land among
  that feature's changes. Do not make it: tell the user that it has to wait
  for that feature, or be made in another folder.
- **Make it.** Tell the user that the change takes the trivial lane, why,
  and what the project's rule asks of it. Then make the change in the same
  turn, as the session and no longer as the orchestrator: the way the
  project's `Trivial Lane` rule says, or directly where the project has no
  such rule. Nothing else in the skill applies to it.

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
that to. Instead:
- **One more file.** The stage needs a file that `Files` does not name. Hold
  the request against the conditions again, with that file added. If they
  all hold, add the file to the ledger's `Fast Path` section, note it in
  `History`, and remove the item from `Active Defects`. Then run the blocked
  stage again, the way `Route` does after an answer of the user: `Round`
  goes up, no other stage is reset, and nothing counts toward a cap.
- **Anything else,** such as a file that breaks a condition, or a request
  that leaves open what a design stage would have settled: set `BLOCKED`,
  note in `History` that the feature is at the edge of its fast path, and
  ask the user, with what each way leads to. The answer can also come in a
  later run, after `continue`.
  - *All the stages:* the feature moves to the full lane, as below.
  - *Stay on the fast path:* the user answers what was open, narrows the
    change, or changes the rule in the project file. Check the conditions
    once more. If they hold, bring the ledger's `Fast Path` section in line
    with the answer, and run the blocked stage again with the answer as its
    direction, as above.
  - *Stop the feature.*

**Moving a feature to the full lane.**
1. In the ledger, set every stage that the fast path skipped to `PENDING`,
   set `Design Gate` to `PENDING`, and take out the `Fast Path` section.
2. Write into your notes for the stages that the feature began on the fast
   path, with its request and the files that its stages have changed so far.
3. This is a backward route to the first stage, and it counts toward no cap.
   An item that was blocked on a skipped stage stays open for that stage,
   which finds it in its dispatch.
4. From here the feature is like any other. What was built stays in the
   folder, and the stages that built it run again, now on the spec and the
   ADR.
