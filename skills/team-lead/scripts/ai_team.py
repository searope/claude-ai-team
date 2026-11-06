#!/usr/bin/env python3
"""ai_team.py: the deterministic core of the AI team pipeline.

The team-lead skill runs it; every command prints one JSON object. Run
`python ai_team.py --help` or `python ai_team.py <command> --help`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from aiteam import checks  # noqa: E402
from aiteam import cost as costmod  # noqa: E402
from aiteam import engine, gitio, guard, model  # noqa: E402
from aiteam import project as projmod  # noqa: E402

SKILL_DIR = os.path.dirname(HERE)


def emit(obj, code: int = 0) -> None:
    text = json.dumps(obj, indent=1, ensure_ascii=False, default=str) + "\n"
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # a Cyrillic request stays readable, not \\uXXXX
    except (AttributeError, ValueError):
        pass
    sys.stdout.write(text)
    sys.stdout.flush()
    sys.exit(code)


def find_root(explicit: str = None) -> str:
    if explicit:
        return os.path.abspath(explicit)
    top = gitio.toplevel(os.getcwd())
    return top or os.getcwd()


def ctx_for(args) -> engine.Ctx:
    return engine.Ctx(find_root(args.root), args.slug, skill_dir=SKILL_DIR)


def _files(value):
    if not value:
        return None
    return [v.strip() for v in re.split(r"[,;]", value) if v.strip()]


# --- doctor --------------------------------------------------------------------------------------

def _frontmatter(path: str) -> dict:
    text = projmod.read_text(path) or ""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    out = {}
    if m:
        for line in m.group(1).splitlines():
            kv = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
            if kv:
                out[kv.group(1)] = kv.group(2).strip().strip("\"'")
    out["_text"] = text
    return out


def cmd_doctor(args):
    root = find_root(args.root)
    warnings, facts = [], {}
    facts["python"] = sys.version.split()[0]
    if sys.version_info < (3, 9):
        warnings.append("Python 3.9 or later is needed")
    try:
        top = gitio.toplevel(root)
        facts["git_root"] = top
        if not top:
            warnings.append("this folder is not a git repository")
    except gitio.GitError as exc:
        warnings.append(str(exc))
    proj = projmod.load(root)
    facts["project_file"] = proj.describe()
    if not proj.exists:
        warnings.append("no project file: the first run of team-lead carries out project initiation")
    else:
        for area in ("source", "tests", "infra"):
            if not getattr(proj, area):
                warnings.append(f"Project Paths has no `{area.title()}` path in backticks")
        if not proj.has_gates and not proj.scans:
            warnings.append("the project file sets no Gates and no Scans, so every check rests on the agents' "
                            "word: `propose-gates` prints a block to add")
    rules = os.path.join(SKILL_DIR, model.RULES_FILE_NAME)
    rules_text = projmod.read_text(rules) or ""
    m = re.search(r"Pipeline Version:\*\*\s*([\d.]+)", rules_text)
    facts["rules"] = {"path": rules, "version": m.group(1) if m else None}
    if not m or m.group(1) != model.PIPELINE_VERSION:
        warnings.append(f"the rules file is not at Pipeline Version {model.PIPELINE_VERSION}")
    skill_text = projmod.read_text(os.path.join(SKILL_DIR, "SKILL.md")) or ""
    m = re.search(r"`Pipeline Version` ([\d.]+)", skill_text)
    if not m or m.group(1) != model.PIPELINE_VERSION:
        warnings.append(f"team-lead's SKILL.md is not written for Pipeline Version {model.PIPELINE_VERSION}")
    if proj.exists:
        code, out, _ = gitio._git(root, "check-ignore", "-q", ".ai-team/probe", check=False)
        if code != 0:
            warnings.append("git does not ignore .ai-team/: add it to .gitignore")
    skills_root = os.path.dirname(SKILL_DIR)
    claude_dir = os.path.dirname(skills_root)
    for st in model.STAGES:
        if not st.skill:
            continue
        if st.runs_when.startswith("project:") and not proj.second_review:
            continue  # optional stage, off in this project
        fm = _frontmatter(os.path.join(skills_root, st.skill, "SKILL.md"))
        if not fm.get("_text"):
            warnings.append(f"skill {st.skill} not found next to team-lead")
            continue
        if st.isolated:
            if fm.get("context") != "fork" or fm.get("agent") != st.agent:
                warnings.append(f"skill {st.skill} should run with context: fork and agent: {st.agent}")
            if fm.get("background") != "false":
                warnings.append(f"skill {st.skill} should set background: false")
    for agent in model.PIPELINE_AGENTS:
        text = projmod.read_text(os.path.join(claude_dir, "agents", f"{agent}.md"))
        if text is None:
            warnings.append(f"agent {agent} not found in {os.path.join(claude_dir, 'agents')}")
        elif not re.search(rf'ai_team_guard\.py"? --agent {re.escape(agent)}\b', text):
            warnings.append(f"agent {agent} has no PreToolUse hook running ai_team_guard.py --agent {agent}")
    emit({"ok": not warnings, "warnings": warnings, "facts": facts})


# --- guard self-test -----------------------------------------------------------------------------

def cmd_guard_test(args):
    tmp = tempfile.mkdtemp(prefix="ai-team-guard-")
    try:
        os.makedirs(os.path.join(tmp, ".git"))
        guard.write_active(tmp, {"slug": "demo-feature", "stage": 5, "label": "5. Coding", "round": 0,
                                 "allow": {"exact": ["src/app.py", ".ai-team/scratchpad/demo-feature-dev-context.md"],
                                           "dirs": [], "patterns": []},
                                 "created": __import__("time").time()})
        cases = [
            ("Write", {"file_path": os.path.join(tmp, "src", "app.py")}, "allow"),
            ("Write", {"file_path": os.path.join(tmp, "src", "other.py")}, "deny"),
            ("Edit", {"file_path": os.path.join(tmp, ".ai-team", "scratchpad", "demo-feature-test-context.md")}, "deny"),
            ("Read", {"file_path": os.path.join(tmp, ".env")}, "deny"),
            ("Read", {"file_path": os.path.join(tmp, "src", "app.py")}, "allow"),
            ("Bash", {"command": "git commit -am wip"}, "deny"),
            ("Bash", {"command": "git status --porcelain && git diff"}, "allow"),
            ("Bash", {"command": "dotnet test > results.txt"}, "deny"),
            ("Bash", {"command": "dotnet test 2>&1"}, "allow"),
            ("PowerShell", {"command": "Get-Content .env"}, "deny"),
            ("PowerShell", {"command": "git -C . stash push"}, "deny"),
        ]
        results, ok = [], True
        for tool, tinput, expect in cases:
            reason = guard.decide({"tool_name": tool, "tool_input": tinput, "cwd": tmp}, "ai-team-builder")
            got = "deny" if reason else "allow"
            ok &= got == expect
            results.append({"tool": tool, "input": tinput, "expected": expect, "got": got})
        emit({"ok": ok, "results": results,
              "live_test": "Dispatch any isolated stage, then check its handoff and the transcript for 'Blocked by "
                           "the AI team guard' on a write outside its area; or run a stage once with a deliberately "
                           "narrow ADR. The hook only works if Claude Code runs it: see README.md, Live check."})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- commands ------------------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(prog="ai_team.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", help="the feature folder (default: the git top level of the current folder)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def with_slug(name, help_text):
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("slug")
        return sp

    def dispatch_opts(sp):
        sp.add_argument("--dispatch", action="store_true", help="when the next action is a dispatch, perform it")
        sp.add_argument("--direction", help="the one-line direction for that dispatch (default: computed)")

    sub.add_parser("doctor", help="check the installation and the project")
    sub.add_parser("status", help="list the features in this folder")
    sub.add_parser("guard-test", help="run the guard's self-test")
    sub.add_parser("propose-gates", help="detect the stack and print Gates, Scans and Second Review to add")

    sp = with_slug("new", "create the ledger of a new feature")
    sp.add_argument("--request", required=True)
    sp.add_argument("--short", help="the request in one line, the first stage's direction")
    sp.add_argument("--workflow", required=True, choices=["in-place", "worktree"])
    sp.add_argument("--start-point", required=True)
    sp.add_argument("--base")
    sp.add_argument("--lane", default="full", choices=["full", "fast"])
    sp.add_argument("--files", help="fast path: comma-separated files that may change")
    sp.add_argument("--skip-stages", help="fast path: comma-separated extra stages the project's rule skips")
    sp.add_argument("--lane-reason")
    dispatch_opts(sp)

    dispatch_opts(with_slug("next", "evaluate the feature and say what comes next"))

    sp = with_slug("returned", "a stage returned: check it and evaluate")
    sp.add_argument("--stage", type=int)
    dispatch_opts(sp)

    sp = with_slug("decide", "record the user's decision")
    sp.add_argument("decision", choices=["approve", "change", "continue", "accept", "revert", "discard", "stop"])
    sp.add_argument("--text")
    sp.add_argument("--area")
    dispatch_opts(sp)

    sp = with_slug("fast-path", "leave the edge of a fast path (lanes.md, Leave)")
    sp.add_argument("op", choices=["add-file", "stay", "to-full"])
    sp.add_argument("--path")
    sp.add_argument("--files")
    dispatch_opts(sp)

    sp = with_slug("route-conflicts", "route the conflicts of a merge in progress")
    sp.add_argument("--base", required=True)
    dispatch_opts(sp)
    dispatch_opts(with_slug("merged", "the merge is committed: move the Start Point"))
    sp = with_slug("updated", "Update (worktree) is done; --start-point after a clean merge")
    sp.add_argument("--start-point")
    dispatch_opts(sp)
    sp = with_slug("route-back", "a backward route the git workflow makes (no cap)")
    sp.add_argument("--stage", type=int, required=True)
    sp.add_argument("--reason", required=True)
    dispatch_opts(sp)
    dispatch_opts(with_slug("scan", "run the project's scans before a review and write the scan report"))

    with_slug("change-record", "write the change record")
    with_slug("verify-delivery", "has anything changed since the review?")
    dispatch_opts(with_slug("review-again", "paths changed after the review: run Security again"))
    sp = with_slug("delivered", "Deliver is done: READY_FOR_MERGE (refused when the change is not what the "
                                "review saw)")
    sp.add_argument("--commit")
    with_slug("verify-delivered", "before a step the user orders: unchanged since delivery?")

    sp = with_slug("set", "change ledger fields for a git workflow step")
    sp.add_argument("--gate-status", choices=list(model.GATE_STATUSES))
    sp.add_argument("--design-gate-pending", action="store_true")
    sp.add_argument("--start-point")
    sp.add_argument("--shelved-stash")
    sp.add_argument("--history")

    sp = with_slug("note", "add a line for the later stages to the notes file")
    sp.add_argument("text")
    with_slug("stop-list", "what a rollback would remove")
    sp = with_slug("purge", "delete the feature's working files under .ai-team/")
    sp.add_argument("--confirm", action="store_true", required=True)
    with_slug("show", "the ledger as JSON")
    sp = with_slug("classify", "the area of each path")
    sp.add_argument("paths", nargs="+")
    sp = with_slug("allowlist", "what a stage may write")
    sp.add_argument("--stage", type=int, required=True)
    sp = with_slug("recover", "create a ledger from a feature's artifacts")
    sp.add_argument("--workflow", required=True, choices=["in-place", "worktree"])
    sp.add_argument("--start-point", required=True)
    sp.add_argument("--base")

    sp = sub.add_parser("cost", help="tokens per stage from Claude Code's transcripts")
    sp.add_argument("--projects-dir", default=os.path.join(os.path.expanduser("~"), ".claude", "projects"))
    sp.add_argument("--days", type=float, default=30)
    sp.add_argument("--slug")

    args = p.parse_args(argv)
    try:
        run(args)
    except engine.PipelineError as exc:
        emit({"ok": False, "error": str(exc)}, 1)
    except (FileNotFoundError, gitio.GitError) as exc:
        emit({"ok": False, "error": str(exc)}, 1)
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - reported, never swallowed
        emit({"ok": False, "error": f"{type(exc).__name__}: {exc}",
              "trace": traceback.format_exc().splitlines()[-6:]}, 2)


def run(args):
    c = args.cmd
    if c == "doctor":
        return cmd_doctor(args)
    if c == "guard-test":
        return cmd_guard_test(args)
    if c == "status":
        return emit(engine.status_all(find_root(args.root)))
    if c == "propose-gates":
        root = find_root(args.root)
        return emit(checks.propose(root, projmod.load(root)))
    if c == "cost":
        return emit(costmod.scan(args.projects_dir, args.days, args.slug))
    if c == "new":
        ctx = engine.new_feature(find_root(args.root), args.slug, args.request, args.workflow, args.start_point,
                                 base=args.base, lane=args.lane, files=_files(args.files),
                                 skip_stages=[int(s) for s in (_files(args.skip_stages) or [])],
                                 lane_reason=args.lane_reason, short=args.short, skill_dir=SKILL_DIR)
        return emit(engine.next_action(ctx, args.dispatch, args.direction))
    if c == "recover":
        ctx = engine.recover(find_root(args.root), args.slug, args.workflow, args.start_point, args.base, SKILL_DIR)
        return emit(engine.next_action(ctx))

    ctx = ctx_for(args)
    if c == "next":
        return emit(engine.next_action(ctx, args.dispatch, args.direction))
    if c == "returned":
        return emit(engine.returned(ctx, args.stage, args.dispatch, args.direction))
    if c == "decide":
        return emit(engine.decide(ctx, args.decision, args.text, args.area, args.dispatch, args.direction))
    if c == "fast-path":
        return emit(engine.fast_path(ctx, args.op, args.path, _files(args.files), args.direction, args.dispatch))
    if c == "route-conflicts":
        return emit(engine.route_conflicts(ctx, args.base, args.dispatch))
    if c == "merged":
        return emit(engine.merged(ctx, args.dispatch))
    if c == "updated":
        return emit(engine.updated(ctx, args.start_point, args.dispatch, args.direction))
    if c == "route-back":
        return emit(engine.route_back(ctx, args.stage, args.reason, args.dispatch))
    if c == "scan":
        return emit(engine.run_scans(ctx, args.dispatch, args.direction))
    if c == "change-record":
        return emit({"ok": True, **engine.write_change_record(ctx)})
    if c == "verify-delivery":
        return emit({"ok": True, **engine.verify_delivery(ctx)})
    if c == "review-again":
        return emit(engine.review_again(ctx, args.dispatch))
    if c == "delivered":
        return emit(engine.delivered(ctx, args.commit))
    if c == "verify-delivered":
        return emit({"ok": True, **engine.verify_delivered(ctx)})
    if c == "set":
        return emit(engine.set_fields(ctx, args.gate_status, args.design_gate_pending, args.start_point,
                                      args.shelved_stash, args.history))
    if c == "note":
        return emit(engine.add_note(ctx, args.text))
    if c == "stop-list":
        return emit(engine.stop_list(ctx))
    if c == "purge":
        return emit(engine.purge(ctx))
    if c == "show":
        return emit({"ok": True, "ledger": ctx.led})
    if c == "classify":
        return emit({"ok": True, "areas": {p: ctx.project.area_of(p, ctx.slug) for p in args.paths}})
    if c == "allowlist":
        return emit({"ok": True, "stage": model.stage(args.stage).label,
                     "allow": guard.stage_allowlist(ctx, args.stage)})
    raise engine.PipelineError(f"unknown command {c}")


if __name__ == "__main__":
    main()
