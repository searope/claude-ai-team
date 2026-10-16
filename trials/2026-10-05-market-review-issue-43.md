# Trial of pipeline 7.0 and team-lead 10.0: Market Review, issue 43

Written by Claude on 2026-10-05, in the Market Review session that ran the feature, at the owner's request. It
records how the 7.0 rules behaved on one small issue: what went as written, and every point that did not.
Section names such as "rules section 5" refer to `skills/team-lead/ai-team-pipeline.md`; "skill section 7"
refers to `skills/team-lead/SKILL.md`.

## The run

- **Project:** Market Review (`searope-org/market-review`).
- **Request:** issue 43, "Sample MR page": "The logo and Market review at the top have a different style".
- **Feature:** `43-mr-header-logo`. Result: `READY_FOR_MERGE`, pull request 86.
- **Installed:** Pipeline Version 7.0. `team-lead` 10.0; `product-manager`, `software-engineer` and
  `test-engineer` 8.0; `copywriter`, `ui-designer`, `system-architect`, `devops-engineer` and
  `security-reviewer` 6.0. This repository was on `ioc-streamline` at `f450855`.
- **Project file:** the older form, a full copy of the 3.3 rules at `.claude/ai-team-pipeline.md`. There was no
  `.claude/ai-team-project.md`. That was intended for the trial.
- **Workflow:** worktree, set by the project's `Git Workflow` override. The session was already in a worktree
  that the desktop app had made.
- **Path:** the full pipeline, not the project's fast path. Stage 6 was skipped. `Round` stayed 0: no backward
  route, counters 0/3, 0/3 and 0/5. One forward route (Stage 5 `DEFECTS`, blocked on `Tests`).
- **Size of the result:** spec with 25 Acceptance Criteria; copy with 2 keys and an audit of 10 rows; a UI spec;
  an ADR with 16 Invariants, 10 tasks and 8 files in its blast radius; 49 new tests. The commit has 17 files,
  3,016 lines added and 45 removed. The production change is eight files.

| Time (PDT) | What happened |
|---|---|
| 05:21 | Request read. Setup, slug, branch, issue label, ledger |
| 05:28 | Stage 1 asks two questions and stops |
| 05:32 | Stage 1 asks two more, with a scope list to confirm, and stops |
| 05:40 | Two last answers by click. Spec written |
| 05:40 to 06:10 | Stages 2, 3 and 4 |
| 06:10 to 06:13 | Design gate opened and approved by click |
| 06:13 to 07:19 | Stages 5 and 7, then `team-lead`'s browser check. The unit tests ran twice: 1,018 s and 1,093 s |
| 07:19 to 07:22 | A question to the owner about a finding, answered by click |
| 07:22 to 07:30 | Stage 8, commit, push, pull request |

The times are from the system clock at each stop. The boundaries between stages inside a row were not timed.

## What went as the rules say

- **The older project file worked.** `team-lead` read it as the project file, ran no initiation and wrote
  nothing to it. Only `Project Paths` and `Overrides for this project` were used.
- **No agent fell back to 3.3.** The project's `CLAUDE.md` imports the 3.3 copy, so its text was in every
  agent's context. All five isolated stages still wrote the 7.0 handoff block (no `Route To`), with the 7.0
  title and at the path their dispatch gave.
- **Conditional stages.** The spec's flags (`User-Facing Text: yes`, `UI: yes`) ran Stages 2 and 3.
  `Infra Impact: no` skipped Stage 6.
- **The design gate.** No build stage ran before the approval, and the approval was recorded for spec r1 and
  ADR r1.
- **The forward route.** Stage 5 reported `DEFECTS`, blocked on `Tests`, for two existing tests that pinned what
  the feature changes on purpose. Stage 5 counted as complete, no round was added, and Stage 7 got both items
  in its dispatch. The architect had predicted this in its handoff.
- **Write isolation.** The engineer changed exactly the eight files of the blast radius. The tester wrote only
  under `tests/`. The reviewer wrote nothing. Each design stage wrote its own artifact.
- **Whose code ran.** The project has one environment, in the main checkout. Both builders ran their tools from
  the worktree root and reported that the project's package was loaded from the worktree (rules section 3).
- **The base branch.** `Update` before Testing and the check at delivery both found the base unchanged.
- **The review.** It worked from the change record and from reading the files, and ran nothing. It has no
  file tools, so `team-lead` wrote its handoff file from its message.
- **Delivery.** The paths `git status` listed were the 17 of the change record, and those were committed.
- **Honest limits.** The UI designer, the architect and the engineer each said plainly what they had not seen
  or run.

## What did not go as the rules say

Each point says what happened, where the rules or the skill say otherwise or say nothing, and what was done.

### Setup and start

1. **The worktree was not fresh.** The desktop app gave the session a folder that an earlier feature had used.
   Its `.ai-team/` still held that feature's ledger (`READY_FOR_MERGE`), eight handoffs and a change record.
   Worktree `Start`, step 1, allows a start when no ledger there is `IN_PROGRESS`, `AWAITING_USER` or
   `BLOCKED`, so the feature started. The files were left in place. Rules section 1 calls a worktree "a fresh
   checkout"; here git's tracked files were fresh and the ignored ones were not.
2. **A project override needs commands the skill does not name.** Guardrail 3 allows only the `git` and `gh`
   commands named in the skill and in the git workflow file. The project's override asks for a label on the
   issue (`gh issue edit --add-label`) and for delivery by pull request (`git push`, `gh pr create`). All three
   were run on the override's authority. `team-lead` also ran two commands of its own choice:
   `git branch --list "agent/43-*"` with a wildcard, and `gh pr view 80` to match the form of an earlier pull
   request.
3. **No way is named to find the feature of an issue.** The skill says an issue whose feature already exists
   continues that feature. At that point the slug is not known. `team-lead` looked with `Glob` on ledgers and
   specs and with the wildcard branch list above.
4. **The fast-path check has no fixed place and no method.** Skill section 2, step 5, creates the ledger with
   every stage `PENDING`. Skill section 7 then describes the fast-path ledger, with stages `SKIPPED`. The check
   was made before the ledger was created. The project's condition is "at most 3 files"; the skill does not
   say how `team-lead` finds the files. It read the templates and stylesheets with `Read` and `Grep`, found
   the same block in three templates and one stylesheet, and ran the full pipeline.
5. **The slug is fixed before anyone knows what the feature is.** Skill section 2, step 2, fixes the slug
   before Stage 1 and says it never changes. The issue's own words ("Sample MR page") were ambiguous, so
   `team-lead` chose a slug that did not presume the answer.

### Stage 1, Discovery

6. **Discovery could not look at the page.** The issue is about how a page looks. The product-manager skill
   names no shell command, and rules section 3 limits the shell to what a skill names, so the site could not
   be built. The stage worked from source files only.
7. **"No agent reads the ledger" cannot hold for a stage in the conversation.** Rules section 2 says no agent
   reads the orchestrator's ledger. Stage 1 runs in the conversation, in the session that wrote the ledger.
8. **Owner's feedback: questions should be clickable.** The first four questions and the scope list were asked
   as text, and the owner typed answers such as "Q1 - A; Q2 - A". The owner then asked for them "the same way,
   as the questions of team-lead in the beginning of a session, so I could just click". The product-manager
   skill does not mention `AskUserQuestion`; `team-lead` does. From then on every question in the run was
   asked with that tool.
9. **One or two questions per turn made three stops.** Six decisions took two text stops and one call with two
   clicks. The scope list was confirmed in the same turn as the second pair of questions.
10. **Two answers were nearly assumed.** The first draft of the spec held two points that "follow from the
    answers and were not asked one by one", marked for the design gate. That is against the skill's guardrail
    2 (no assumed answers). They were asked by click before the handoff was written, and the spec was
    corrected.

### Stages 2 to 4 and the design gate

11. **The owner approved a look that nobody had seen.** The agent type of the UI designer and the architect
    has no shell and no browser. The UI spec says its widths are hand estimates "good to about 10%" and its
    contrasts are hand calculations. The feature's one new visual, a light-theme logo, existed only as hex
    values. `team-lead` drew a preview from the UI spec's values with the app's widget tool; the skill does
    not ask for that.
12. **One estimate missed.** The UI spec judged that the issue picker's date would still fit beside the wider
    logo "with about 3px spare". The picker's text is the date and the word "(latest)". The date fits; the
    word is cut. This was presented at the gate as a small risk and was found only in Stage 7 and in
    `team-lead`'s browser check.
13. **Final messages were not the handoff files.** Rules section 5 says an agent "returns the same text as
    its final message". In Stages 2, 3 and 5 the handoff block matched, and the text below it differed: bullets
    reworded, a table in place of a sentence, absolute paths in place of relative ones, one sentence present
    only in the message. Stage 3 also listed its own handoff file under `Files Touched`. Routing was not
    affected.
14. **Words in wireframes.** The UI spec's contract says strings appear only as copy keys (rules section 4).
    Its wireframes print the words "Market Review". Everywhere else it uses the keys. Not routed.
15. **Notes for later stages sit where later stages cannot read them.** The handoffs of Stages 1 to 4 each
    have a part addressed to later stages. No agent reads another's handoff unless its dispatch cites it. So
    the architect's dispatch cited three handoff files, and the tester's and the reviewer's dispatches carried
    the owner's decisions and two more handoff paths. The "one line" direction became three to four lines.
16. **The gate did not stop.** Skill section 8 says to ask and stop. The gate was asked with `AskUserQuestion`,
    as the owner had asked, so the turn waited and then went on to Stage 5. The summary and the report were
    printed before the question.

### Stages 5 to 8 and delivery

17. **The engineer edited by script.** It applied five of its edits with a Python script that it wrote to the
    system temp folder, and said so in its handoff. Rules section 3 allows the shell only for what the skill
    names, the gates, worktree setup, a dependency the ADR names and clean-up. The script is also a file
    written outside the engineer's area. The result was inside the blast radius, with LF line endings.
18. **`Defects` on a first run.** The forward route put `Defects` into Stage 7's first dispatch. Rules section
    5 says of a dispatch with `Defects`: "fix those defects and change nothing else". Read literally, the first
    run of Testing would write no tests for the feature. The direction line said that it was the first run and
    that both were wanted, and the tester did both.
19. **No status for "done, and the owner must decide something".** The tester found the cut word in the
    picker. Its gates passed and no criterion failed, so it reported `DONE` with a note for the owner.
    `ESCALATE` means the stage cannot be completed, which was not the case. Skill section 8 takes no change
    request after approval: the feature runs on or is stopped. `team-lead` asked the owner between Stages 7 and
    8, which is a stop the skill does not define, and offered a fix inside the feature only as "an escalation
    on the spec". The owner chose to run on and accept it.
20. **`team-lead`'s own browser check needed things the skill does not give it.** The project's override has
    `team-lead` check keyboard, focus and motion in a browser before it delivers a UI change. That needs a
    preview server, so `team-lead` added a temporary entry to `.claude/launch.json`, a tracked file that is
    not among what the skill says it writes. The entry came out before the change record was written, so that
    the review and the commit would not hold it. The check could not emulate reduced motion. `ipconfig` was
    not run, because guardrail 3 keeps the shell for git, so the owner got an unchecked network address.
21. **The reviewer thought that check was still open.** It had been done before Stage 8. Only the ledger said
    so, no agent reads the ledger, and the dispatch did not mention it.
22. **The tester's widths missed a range.** It opened the pages at 375, 420, 421 and 1440px and reported the
    cut word from 421px. `team-lead`'s check found a second range, 481 to 495px, where a label returns to the
    bar. No test opens that range.
23. **Tests that only run on the feature's branch.** The tester's `ChangeScope` class compares files with the
    Start Point and runs only on the feature's branch, as earlier features in this project did. The reviewer
    noted that these seven tests are the only cover for parts of two Invariants and one Acceptance Criterion,
    and that they are skipped after the merge.
24. **Two forms of title.** The worktree procedure gives the commit message
    `<feature-slug>: <the title of the spec>`. The project's earlier commits and pull requests use their own
    form ("Picker: ... (#64)"). The commit follows the procedure and the pull request title follows the
    project.

### Risks seen, where nothing went wrong

25. **The project's own pipeline document describes 3.3.** The project's `Stage Notes` send every stage to
    `.claude/PIPELINE.md` section 3. That text still says, for example, that `team-lead` creates the worktree
    and moves the session into it, and that the reviewer "audits the real `git diff`". In 7.0 the reviewer has
    no shell and reads the change record. No stage acted on the old text.
26. **Two sets of rules in every context.** The 3.3 copy is imported by the project's `CLAUDE.md`, so each
    agent holds it next to the 7.0 rules its dispatch names. Rules section 1 tells agents to ignore all but
    two blocks of it, and they did.

### Cost

27. **Time.** About 2 hours 10 minutes for a one-line issue. Stages 5 and 7 and the browser check took 66
    minutes of it; the unit tests ran twice inside those stages, for 35 minutes together.
28. **Silence.** An isolated stage shows nothing in the conversation while it runs. The app prompted
    `team-lead` several times that the user had not heard from it.
29. **Weight.** A change of eight production files came with 25 criteria, 16 invariants, 49 tests and about
    3,000 added lines, most of them tests and design documents.

### After the pull request

30. **The owner had `team-lead` merge.** Guardrail 4 and the project's rules say that only the owner merges.
    The owner wrote "merge #86" in chat. `team-lead` merged it with a merge commit, pinned to the reviewed
    head commit, and deleted no branch. The rules have no words for a merge that the owner orders in chat.
31. **Scratch files that no handoff named.** At cleanup the session's scratch folder, which lies under the
    system temp folder, held five scripts (`fix1.py` to `fix5.py`), a `suite.log`, and a folder with 48
    screenshots and a `pickers.json`. The engineer's handoff speaks of one script "in the system temp folder".
    The tester's handoff says its pictures are "easy to remake"; it does not say that they exist, or where.
    Rules section 3 has an agent clean up generated files inside the project; it says nothing of files an
    agent writes outside it. `team-lead` had taken its own screenshots for the owner without knowing that
    these existed. All were deleted at cleanup, on the owner's confirmation, without being read.
32. **A session cannot remove its own worktree.** The project's cleanup removes the worktree after the merge.
    The session runs in that folder, so it removed what git ignores there, deleted the branch on both sides,
    and left the folder to the owner, who removes it by archiving the session.
33. **An earlier feature's leftovers went in the same cleanup:** the nine working files of point 1 and a
    `.wrangler/` folder of local dev state, on the owner's confirmation.
34. **A closed issue keeps its `status:in-progress` label.** The project's rule takes the label off at cleanup
    "if the issue is still open after the merge". The merge closed issue 43 after 43 seconds, so the label
    stayed. This is the project's rule, not a 7.0 one.

## Where the material is

- **On `main`** (pull request 86 of `searope-org/market-review`, merged on 2026-10-05 as `3793d49`): the spec,
  the copy file and audit, the UI spec and the ADR, under `docs/specs/`, `docs/copy/`, `docs/design/` and
  `docs/adr/`, each named `43-mr-header-logo`.
- **Gone:** the ledger, the eight handoffs and the change record. They were in the feature's worktree and were
  removed at cleanup on 2026-10-05, after the merge. This file was made from the ledger's notes before that.
