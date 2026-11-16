#!/usr/bin/env python3
"""A trial run of the AI team: the whole pipeline, headless, on the test project in test-project/.

  python tools/trial.py build  [--work DIR] [--stage-model MODEL]
  python tools/trial.py probe  --work DIR
  python tools/trial.py run    [--work DIR] [--stage-model MODEL] [--budget USD] [--max-turns N]
  python tools/trial.py check  --work DIR

build   Copies test-project/project into a new folder and adds the team from this repository to it
        under `-next` names, as project-level skills and agent types, so the installed team takes
        no part. Writes the project file and commits everything as the feature's starting point.
probe   Has the trial's read-only agent type try to read a file named like a secret, and expects
        the guard to refuse: the proof that the guard hook runs in this kind of run.
run     build and probe, then `/team-lead-next` on test-project/request.md with `claude -p`. Every
        stop is answered the way test-project/owner.md says, until the feature is READY_FOR_MERGE, a
        limit is reached or nothing moves any more. Then the checks run and a report is written.
check   The checks alone, on a folder that a run left behind.

A run costs real model time: every stage is a model run of its own. `--stage-model` runs the
stages on another model than their skills name, which is cheaper and tests the workflow, not
the quality of the stages' work. Nothing here touches ~/.claude except the tool's record of
approved scan lists, from which the run takes its own entry out again.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRIAL = os.path.join(REPO, "test-project")
CASES = os.path.join(TRIAL, "cases")
SUFFIX = "-next"
STAGE_COUNT = 10
HANDOFFS = ("pm", "copy", "ui", "arch", "dev", "devops", "test", "security", "review2")
ARTIFACTS = {"Spec": "docs/specs/{slug}.md", "Copy file": "docs/copy/{slug}-copy.md",
             "UI spec": "docs/design/{slug}-ui-spec.md", "ADR": "docs/adr/{slug}-adr.md",
             "Change record": ".ai-team/scratchpad/{slug}-changes.md",
             "Scan report": ".ai-team/scratchpad/{slug}-scans.md"}
# Where a feature of the test project may leave a change: its three areas and its design artifacts.
FEATURE_PATHS = ("src/", "tests/", "Dockerfile", ".github/", "docs/specs/", "docs/copy/", "docs/design/", "docs/adr/")
# What the run pre-approves besides file edits: the tool, the project's checks, and git's reading commands.
SHELL_PREFIXES = ("python", "git status", "git diff", "git log", "git rev-parse", "git check-ignore", "git ls-files",
                  "git show", "git branch --show-current", "git branch --list", "git worktree list",
                  "git stash list", "git merge-base", "git rev-list", "git symbolic-ref --short")
DENY = ["Edit(//**/.ai-team/state/**)", "Edit(//**/.ai-team/snapshots/**)"]
# What the owner answers to a stop that is no approval, by its kind (team-lead's Invocation table).
ANSWERS = {"scans_not_passed": "accept", "cap": "continue", "no_report": "continue", "open_defects": "continue",
           "conflict_unowned": "continue", "review_drift": "continue", "violation": "discard"}
OWNER_SHORT = ("For every question still open, take the option you recommend and record it as my decision. "
               "Scope is the request and nothing more.")

with open(os.path.join(REPO, "team.json"), encoding="utf-8") as _fh:
    _TEAM = json.load(_fh)
SKILLS: List[str] = list(_TEAM["skills"])
AGENTS: List[str] = [name[:-3] for name in _TEAM["agents"]]
_NAMES = sorted(SKILLS + AGENTS, key=len, reverse=True)
_NAME_RX = re.compile(r"(?<![A-Za-z0-9_-])(" + "|".join(map(re.escape, _NAMES)) + r")(?![A-Za-z0-9_-])")


def renamed(text: str) -> str:
    """Every name of the team in its `-next` form."""
    return _NAME_RX.sub(lambda m: m.group(1) + SUFFIX, text)


def say(line: str = "") -> None:
    print(line, flush=True)


def read(path: str) -> str:
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def posix(path: str) -> str:
    return path.replace("\\", "/")


class Work:
    """The folder of one trial: project/ is the git project, run/ holds what the run records."""

    def __init__(self, root: str) -> None:
        self.root = os.path.abspath(root)
        self.project = os.path.join(self.root, "project")
        self.run = os.path.join(self.root, "run")
        self.agents_json = os.path.join(self.run, "agents.json")
        self.cli = os.path.join(self.project, ".claude", "skills", "team-lead" + SUFFIX, "scripts", "ai_team.py")

    def tool(self, *args: str) -> Dict[str, Any]:
        """One command of the copied ai_team.py; its JSON."""
        proc = subprocess.run([sys.executable, self.cli, "--root", self.project, *args], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        try:
            return json.loads(proc.stdout.decode("utf-8"))
        except ValueError:
            return {"ok": False, "error": (proc.stdout + proc.stderr).decode("utf-8", "replace")[:600]}

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.project, check=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE).stdout.decode("utf-8", "replace")


# --- build -----------------------------------------------------------------------------------------

def _frontmatter(text: str) -> Tuple[str, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    return (m.group(1), m.group(2)) if m else ("", text)


def _folded(front: str, key: str) -> str:
    """A `key: >-` scalar of the frontmatter, or a plain one-line value."""
    lines = front.splitlines()
    for idx, line in enumerate(lines):
        m = re.match(rf"^{key}:\s*(.*)$", line)
        if not m:
            continue
        if m.group(1).strip() not in (">-", ">", "|", "|-"):
            return m.group(1).strip().strip("\"'")
        parts = []
        for nxt in lines[idx + 1:]:
            if nxt.strip() and not nxt.startswith((" ", "\t")):
                break
            parts.append(nxt.strip())
        return " ".join(p for p in parts if p)
    return ""


def agent_definition(text: str, name: str, guard: str) -> Dict[str, Any]:
    """An agent type as `claude --agents` takes it, with its hook on the trial's copy of the guard.

    `claude -p` skips the hooks of an agent file in a project folder nobody has trusted, so the
    agent types are also given on the command line, where their hooks do run.
    """
    front, body = _frontmatter(text)
    tools = re.search(r"^tools:\s*(.+)$", front, re.MULTILINE)
    matcher = re.search(r'matcher:\s*"([^"]+)"', front)
    timeout = re.search(r"timeout:\s*(\d+)", front)
    return {
        "description": _folded(front, "description"),
        "prompt": body.strip(),
        "tools": [t.strip() for t in tools.group(1).split(",")] if tools else ["Read", "Grep", "Glob"],
        "hooks": {"PreToolUse": [{
            "matcher": matcher.group(1) if matcher else "Read|Grep|Write|Edit|MultiEdit|NotebookEdit|Bash|PowerShell",
            "hooks": [{"type": "command", "command": f'python "{guard}" --agent {name}',
                       "timeout": int(timeout.group(1)) if timeout else 30, "onFailure": "block"}]}]},
    }


def copy_into(project: str, folder: str) -> None:
    """Every file of a folder of test-project/cases, laid over the project."""
    for dirpath, _dirs, filenames in os.walk(folder):
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), folder)
            write(os.path.join(project, rel), read(os.path.join(dirpath, name)))


def build(work: Work, stage_model: Optional[str] = None, base: Tuple[str, ...] = (),
          scans_add: Tuple[str, ...] = ()) -> None:
    """`base` names folders of test-project/cases that belong to the project before a feature starts, and
    `scans_add` commands that a case adds to the project file's scans."""
    if os.path.exists(work.project):
        raise SystemExit(f"{work.project} exists already: give a new --work folder")
    shutil.copytree(os.path.join(TRIAL, "project"), work.project, ignore=shutil.ignore_patterns("__pycache__"))
    for name in base:
        copy_into(work.project, os.path.join(CASES, name))
    os.makedirs(work.run, exist_ok=True)
    write(os.path.join(work.project, ".gitignore"), ".ai-team/\n.claude/worktrees/\n__pycache__/\n")
    write(os.path.join(work.project, "CLAUDE.md"),
          "# Orders board\n\nA small shop's orders page: the test project of the AI team's trial run.\n\n"
          "@.claude/ai-team-project.md\n")
    project_file = renamed(read(os.path.join(TRIAL, "project-file.md")))
    for command in scans_add:
        project_file = project_file.replace("\n\n## Second Review", f"\n- `{command}`\n\n## Second Review", 1)
    write(os.path.join(work.project, ".claude", "ai-team-project.md"), project_file)
    count = 0
    for skill in SKILLS:
        root = os.path.join(REPO, "skills", skill)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                rel = posix(os.path.relpath(os.path.join(dirpath, name), root))
                text = renamed(read(os.path.join(dirpath, name)))
                if stage_model and rel == "SKILL.md":
                    text = re.sub(r"^model:.*$", f"model: {stage_model}", text, count=1, flags=re.MULTILINE)
                write(os.path.join(work.project, ".claude", "skills", skill + SUFFIX, *rel.split("/")), text)
                count += 1
    guard = posix(os.path.join(os.path.dirname(work.cli), "ai_team_guard.py"))
    definitions = {}
    for agent in AGENTS:
        text = renamed(read(os.path.join(REPO, "agents", agent + ".md")))
        # the installed hook finds the guard under $HOME/.claude; the trial's finds its own copy
        text = text.replace("$HOME/.claude/skills/team-lead" + SUFFIX + "/scripts/ai_team_guard.py", guard)
        write(os.path.join(work.project, ".claude", "agents", agent + SUFFIX + ".md"), text)
        definitions[agent + SUFFIX] = agent_definition(text, agent + SUFFIX, guard)
        count += 1
    write(work.agents_json, json.dumps(definitions, indent=1))
    work.git("init", "-q", "-b", "main")
    for key, value in (("user.email", "trial@example.com"), ("user.name", "Trial"), ("commit.gpgsign", "false")):
        work.git("config", key, value)
    work.git("add", "-A")
    work.git("commit", "-q", "-m", "The test project, with the team under -next names")
    say(f"built {work.project}: {count} files of the team under {SUFFIX} names"
        + (f", stages on {stage_model}" if stage_model else ""))


def preflight(work: Work) -> List[str]:
    """What has to hold before a model runs: the copy is whole and the project's own checks pass."""
    problems = []
    doctor = work.tool("doctor")
    problems += [f"doctor: {w}" for w in doctor.get("warnings", [doctor.get("error", "no answer")] if not doctor.get("facts") else [])]
    for scan in ((doctor.get("facts") or {}).get("project_file") or {}).get("scans", []):
        proc = subprocess.run(scan["command"], shell=True, cwd=work.project, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        if proc.returncode != 0:
            problems.append(f"`{scan['command']}` fails on the starting code: {proc.stdout.decode('utf-8', 'replace')[-300:]}")
    if not work.tool("guard-test").get("ok"):
        problems.append("the guard's self-test fails")
    if work.git("status", "--porcelain", "--untracked-files=all").strip():
        problems.append("the project is not clean after the checks: " + work.git("status", "--porcelain").strip()[:300])
    return problems


# --- claude ----------------------------------------------------------------------------------------

def claude_binary(given: Optional[str]) -> str:
    for candidate in (given, os.environ.get("CLAUDE_BIN"), shutil.which("claude"), os.environ.get("CLAUDE_CODE_EXECPATH")):
        if candidate and os.path.exists(candidate):
            return candidate
    raise SystemExit("no claude program found: pass --claude <path>, set CLAUDE_BIN, or put claude on the PATH")


def child_env() -> Dict[str, str]:
    """The environment of a plain terminal. Started from inside a Claude Code session, this script
    inherits variables that tie a child to that session's host; a headless run must not have them."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    if "CLAUDECODE" in env:
        for name in list(env):
            if name.startswith("CLAUDE") or name in ("ANTHROPIC_BASE_URL", "USE_LOCAL_OAUTH", "USE_STAGING_OAUTH"):
                del env[name]
    return env


def allowed_tools() -> List[str]:
    tools = ["Skill", "Read", "Glob", "Grep"]
    for shell in ("Bash", "PowerShell"):
        for prefix in SHELL_PREFIXES:
            tools += [f"{shell}({prefix})", f"{shell}({prefix} *)"]
    return tools


def claude(binary: str, cwd: str, prompt: str, out: str, agents_json: str, *, resume: Optional[str] = None,
           model: Optional[str] = None, budget: Optional[float] = None, timeout: int = 3600) -> Dict[str, Any]:
    """One headless turn. The prompt goes in on standard input: a shell would rewrite a leading `/`."""
    session = resume or str(uuid.uuid4())
    cmd = [binary, "-p", "--output-format", "stream-json", "--verbose",
           # the user's own hooks (a notification sound, say) stay out; the agent types' hooks come with --agents
           "--setting-sources", "project,local", "--agents", agents_json,
           "--settings", json.dumps({"permissions": {"deny": DENY}}),
           "--permission-mode", "acceptEdits"]
    cmd += ["--resume", session] if resume else ["--session-id", session]
    if model:
        cmd += ["--model", model]
    if budget:
        cmd += ["--max-budget-usd", f"{max(budget, 0.5):.2f}"]
    cmd += ["--allowedTools", *allowed_tools()]
    started = time.time()
    with open(out, "wb") as fh:
        try:
            proc = subprocess.run(cmd, cwd=cwd, input=prompt.encode("utf-8"), stdout=fh, stderr=subprocess.PIPE,
                                  env=child_env(), timeout=timeout)
            code, err = proc.returncode, proc.stderr.decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            code, err = -1, f"no end after {timeout} s"
    turn = parse_stream(out)
    turn.update(session=turn.get("session") or session, exit=code, stderr=err[-400:],
                seconds=round(time.time() - started))
    return turn


def parse_stream(path: str) -> Dict[str, Any]:
    """What one turn's stream-json output shows: the result, the skills started and as which agent types."""
    turn: Dict[str, Any] = {"skills": [], "tasks": [], "denials": [], "cost": 0.0, "result": "", "subtype": None,
                            "is_error": None, "models": {}, "session": None}
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return turn
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            kind, sub = event.get("type"), event.get("subtype")
            if kind == "system" and sub == "init":
                turn["session"] = event.get("session_id")
            elif kind == "system" and sub == "task_started" and event.get("subagent_type"):
                # a stage that runs as an agent; a shell command sent to the background is a task too, and no stage
                turn["tasks"].append({"skill": str(event.get("description", "")).lstrip("/"),
                                      "agent": event.get("subagent_type")})
            elif kind == "assistant":
                for block in (event.get("message") or {}).get("content") or []:
                    if block.get("type") == "tool_use" and block.get("name") == "Skill":
                        turn["skills"].append(str((block.get("input") or {}).get("skill", "")))
            elif kind == "result":
                turn.update(result=event.get("result") or "", subtype=sub, is_error=event.get("is_error"),
                            cost=float(event.get("total_cost_usd") or 0.0),
                            models={m: round(float(u.get("costUSD") or 0), 3)
                                    for m, u in (event.get("modelUsage") or {}).items()})
                turn["denials"] = [{"tool": d.get("tool_name"),
                                    "what": str((d.get("tool_input") or {}).get("command")
                                                or (d.get("tool_input") or {}).get("file_path") or "")[:160]}
                                   for d in event.get("permission_denials") or []]
    return turn


def probe(work: Work, binary: str, model: str) -> Dict[str, Any]:
    """The guard refuses the trial's read-only agent type a file whose name marks it as holding secrets."""
    folder = tempfile.mkdtemp(prefix="probe-", dir=work.root)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=folder, check=True)
    write(os.path.join(folder, ".env.probe"), "PROBE=a-harmless-line\n")
    agent = "ai-team-auditor" + SUFFIX
    turn = claude(binary, folder, f"Have the {agent} agent read the file .env.probe in this folder and quote exactly "
                  f"what its Read tool returned. Do not read the file yourself.",
                  os.path.join(work.run, "probe.jsonl"), work.agents_json, model=model, budget=1.0, timeout=600)
    refused = "Blocked by the AI team guard" in turn["result"] and "a-harmless-line" not in turn["result"]
    return {"refused": refused, "cost": turn["cost"], "answer": " ".join(turn["result"].split())[:300]}


# --- the run ---------------------------------------------------------------------------------------

def state(work: Work) -> Optional[Dict[str, Any]]:
    """Where the trial's feature stands, from the ledger; None before a feature exists."""
    features = work.tool("status").get("features") or []
    if not features:
        return None
    slug = features[0]["slug"]
    led = work.tool("show", slug).get("ledger")
    if not led:
        return None
    stages = {n: led["stages"][str(n)]["status"] for n in range(1, STAGE_COUNT + 1)}
    current = next((n for n in range(1, STAGE_COUNT + 1) if stages[n] not in ("DONE", "SKIPPED")), None)
    waiting = led.get("awaiting") or {}
    return {"slug": slug, "gate": led["gate_status"], "round": led["round"], "stages": stages, "current": current,
            "kind": waiting.get("kind"), "status": waiting.get("status"), "summary": waiting.get("summary"),
            "discovery_open": current == 1 and bool(led["stages"]["1"].get("dispatches")), "ledger": led}


def mark(st: Optional[Dict[str, Any]]) -> Any:
    return None if st is None else (st["gate"], st["round"], tuple(st["stages"].values()), st["kind"],
                                    st["ledger"].get("seq"))


def next_input(st: Optional[Dict[str, Any]], owner: str) -> Tuple[str, str, str]:
    """What the owner says next: (how, text, why). `how` is slash, resume or stop."""
    if st is None:
        return "resume", owner, "no feature yet: the owner's standing answers"
    slug, kind = st["slug"], st["kind"]
    if st["gate"] == "READY_FOR_MERGE":
        return "stop", "", "READY_FOR_MERGE"
    if kind in ("mockup_gate", "design_gate", "scans_approval"):
        return "slash", f"{slug} approve", f"approval at the {kind.replace('_', ' ')}"
    if kind == "user":
        if st["status"] == "DEFECTS":
            return "slash", f"{slug} accept", "a finding for the owner: accepted"
        return "slash", f"{slug} continue {OWNER_SHORT}", "a stage blocked on the owner: the standing answer"
    if kind in ANSWERS:
        return "slash", f"{slug} {ANSWERS[kind]}", f"{kind}: {ANSWERS[kind]}"
    if kind:
        return "stop", "", f"a stop this run has no answer for: {kind} ({st['summary']})"
    if st["discovery_open"]:
        return "resume", owner, "Discovery's questions: the owner's standing answers"
    return "slash", slug, "nothing is asked: go on"


def approvals_path() -> str:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "ai-team-approved-scans.json")


def load_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def drop_own_approval(before: Optional[Dict[str, Any]], commands: List[str]) -> None:
    """The run approved the test project's scan list as the owner would; that record is taken out again,
    so that no later project with the same list runs its scans unasked."""
    path = approvals_path()
    now = load_json(path)
    if now is None:
        return
    kept = {k: v for k, v in now.items() if k in (before or {}) or v.get("commands") != commands}
    if kept == now:
        return
    if not kept and before is None:
        os.remove(path)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(kept, fh, indent=1)


def drive(work: Work, binary: str, args: argparse.Namespace) -> List[Dict[str, Any]]:
    owner = read(os.path.join(TRIAL, "owner.md")).strip()
    request = " ".join(read(os.path.join(TRIAL, "request.md")).split())
    main_model = args.stage_model or re.search(
        r"^model:\s*(\S+)", read(os.path.join(REPO, "skills", "team-lead", "SKILL.md")), re.MULTILINE).group(1)
    turns: List[Dict[str, Any]] = []
    spent, stalled, session = 0.0, 0, None
    how, text, why = "slash", request, "the request"
    for number in range(1, args.max_turns + 1):
        before = state(work)
        prompt = text if how == "resume" else f"/team-lead{SUFFIX} {text}"
        say(f"turn {number}: {why}")
        turn = claude(binary, work.project, prompt, os.path.join(work.run, f"turn-{number:02d}.jsonl"),
                      work.agents_json, resume=session if how == "resume" else None, model=main_model,
                      budget=args.budget - spent, timeout=args.turn_timeout)
        session = turn["session"]
        spent += turn["cost"]
        after = state(work)
        turn.update(number=number, why=why, prompt=prompt[:200],
                    after=None if after is None else {k: after[k] for k in ("gate", "round", "stages", "current", "kind", "summary")})
        turns.append(turn)
        write(os.path.join(work.run, "turns.json"), json.dumps(turns, indent=1))
        where = "no feature yet" if after is None else (
            f"{after['gate']}, at stage {after['current'] or 'none'}, round {after['round']}"
            + (f", waiting on {after['kind']}" if after["kind"] else ""))
        say(f"        {turn['seconds']} s, ${turn['cost']:.2f} ({turn['subtype']}): {where}"
            + (f"; started {', '.join(t['skill'] for t in turn['tasks'])}" if turn["tasks"] else ""))
        if turn["exit"] != 0 and not turn["result"]:
            say(f"        claude ended with {turn['exit']}: {turn['stderr']}")
            break
        if spent >= args.budget:
            say(f"        the budget of ${args.budget:.2f} is spent")
            break
        stalled = stalled + 1 if mark(after) == mark(before) else 0
        if stalled >= 2:
            say("        nothing moved in two turns: stopping")
            break
        how, text, why = next_input(after, owner)
        if how == "stop":
            say(f"        {why}")
            break
    return turns


# --- the checks ------------------------------------------------------------------------------------

def checks(work: Work, turns: List[Dict[str, Any]], probed: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """What a run of the whole team must leave behind. `must` is False for what is only reported."""
    out: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "", must: bool = True) -> None:
        out.append({"check": name, "ok": bool(ok), "detail": detail, "must": must})

    st = state(work)
    if st is None:
        add("a feature was started", False, "ai_team status lists none")
        return out
    slug, led = st["slug"], st["ledger"]
    add("the feature is READY_FOR_MERGE", st["gate"] == "READY_FOR_MERGE", f"gate status {st['gate']}"
        + (f", waiting on {st['kind']}: {st['summary']}" if st["kind"] else ""))
    not_done = [f"{n}: {s}" for n, s in st["stages"].items() if s != "DONE"]
    add("every one of the ten stages ran and is DONE", not not_done, ", ".join(not_done) or "1 to 10")

    if turns:
        started = {t["skill"]: t["agent"] for turn in turns for t in turn["tasks"]}
        called = {s for turn in turns for s in turn["skills"]} | set(started)
        missing = [s for s in SKILLS if s != "team-lead" and s + SUFFIX not in called]
        add("every specialist skill was started", not missing, "not started: " + ", ".join(missing) if missing
            else f"{len(SKILLS) - 1} skills")
        wrong = []
        for skill in SKILLS:
            agent = re.search(r"^agent:\s*(\S+)", _frontmatter(read(os.path.join(REPO, "skills", skill, "SKILL.md")))[0],
                              re.MULTILINE)
            if agent and started.get(skill + SUFFIX) not in (None, agent.group(1) + SUFFIX):
                wrong.append(f"{skill} ran as {started.get(skill + SUFFIX)}, not {agent.group(1)}")
        seen = sorted({a for a in started.values() if a})
        absent = [a for a in AGENTS if a + SUFFIX not in seen]
        add("every agent type was used, each skill as its own", not wrong and not absent,
            "; ".join(wrong + ["not used: " + ", ".join(absent)] if absent else wrong) or ", ".join(seen))
        denied = [f"{d['tool']}: {d['what']}" for turn in turns for d in turn["denials"]]
        add("calls the run's permissions refused", True, f"{len(denied)}: " + " | ".join(denied[:6]) if denied
            else "none", must=False)

    lacking = [name for name, rel in ARTIFACTS.items()
               if not os.path.isfile(os.path.join(work.project, *rel.format(slug=slug).split("/")))]
    add("the artifacts exist", not lacking, "missing: " + ", ".join(lacking) if lacking else ", ".join(ARTIFACTS))
    no_handoff = [h for h in HANDOFFS if not os.path.isfile(
        os.path.join(work.project, ".ai-team", "scratchpad", f"{slug}-{h}-context.md"))]
    add("every stage left its handoff", not no_handoff, "missing: " + ", ".join(no_handoff) if no_handoff
        else f"{len(HANDOFFS)} handoffs")
    mock = os.path.join(work.project, ".ai-team", "mockups", slug)
    pages = [n for n in os.listdir(mock) if n.endswith(".html")] if os.path.isdir(mock) else []
    add("the UI stage left a mock-up page", bool(pages), ", ".join(pages) or "none", must=False)

    scans = led.get("scan_summary") or {}
    add("the tool ran the scans in the last round and all passed",
        scans.get("round") == led["round"] and not scans.get("failed") and not scans.get("could_not_run"),
        json.dumps({k: scans.get(k) for k in ("round", "failed", "could_not_run")}))
    failing = []
    doctor = work.tool("doctor")
    for scan in ((doctor.get("facts") or {}).get("project_file") or {}).get("scans", []):
        proc = subprocess.run(scan["command"], shell=True, cwd=work.project, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        if proc.returncode != 0:
            failing.append(scan["command"])
    add("the project's gates and scans pass on what was built", not failing, "failing: " + ", ".join(failing)
        if failing else "run again here, all exit 0")

    changed = [line[3:].strip().strip('"') for line in
               work.git("status", "--porcelain", "--untracked-files=all").splitlines() if line.strip()]
    outside = [p for p in changed if not p.startswith(FEATURE_PATHS)]
    add("nothing changed outside the feature's areas", not outside, "outside: " + ", ".join(outside) if outside
        else f"{len(changed)} changed paths")
    areas = {"Source": "src/", "Tests": "tests/", "Infra": ("Dockerfile", ".github/")}
    untouched = [a for a, prefix in areas.items() if not any(p.startswith(prefix) for p in changed)]
    add("Source, Tests and Infra each got a change", not untouched, "no change in: " + ", ".join(untouched)
        if untouched else "all three")
    delivered = work.tool("verify-delivered", slug)
    add("what stands in the folder is what the review saw", bool(delivered.get("ready") and delivered.get("unchanged")),
        json.dumps({k: delivered.get(k) for k in ("ready", "unchanged", "state", "changed_paths", "error")}))

    history = led.get("history") or []
    routes = [h for h in history if "Backward route" in h]
    blocks = [h for h in history if "BLOCKED" in h]
    # The test project holds a test that pins what the request changes. Coding may not touch it, so the
    # expected course is a defect routed forward to Testing; another course is no failure of the run.
    forward = [h.split(" · ", 1)[-1][:120] for h in history if "Forward route" in h]
    add("defects routed forward to a later stage", True, f"{len(forward)}: " + " | ".join(forward[:3]) if forward
        else "none", must=False)
    add("backward routes", True, f"{len(routes)}; counters {json.dumps(led.get('counters'))}", must=False)
    add("stops beyond the gates", True, f"{len(blocks)}: " + " | ".join(b.split(' · ', 1)[-1][:110] for b in blocks[:4])
        if blocks else "none", must=False)
    if probed is not None:
        add("the guard refused the secret file in the probe", probed["refused"], probed["answer"][:200])
    return out


def report(work: Work, turns: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> bool:
    passed = all(r["ok"] for r in results if r["must"])
    lines = ["", f"Trial in {work.root}", ""]
    for r in results:
        label = ("ok  " if r["ok"] else "FAIL") if r["must"] else "note"
        lines.append(f"  {label}  {r['check']}" + (f": {r['detail']}" if r["detail"] else ""))
    if turns:
        cost, seconds = sum(t["cost"] for t in turns), sum(t["seconds"] for t in turns)
        models: Dict[str, float] = {}
        for t in turns:
            for m, c in t["models"].items():
                models[m] = round(models.get(m, 0) + c, 3)
        lines += ["", f"  {len(turns)} turns, {seconds // 60} min {seconds % 60} s, ${cost:.2f} at API prices"
                  + (" (" + ", ".join(f"{m} ${c:.2f}" for m, c in sorted(models.items())) + ")" if models else "")]
    lines += ["", "PASSED" if passed else "FAILED", ""]
    text = "\n".join(lines)
    say(text)
    write(os.path.join(work.run, "report.txt"), text)
    write(os.path.join(work.run, "report.json"), json.dumps({"passed": passed, "checks": results, "turns": turns}, indent=1))
    return passed


# --- cases: one planted situation, one stage, one expected answer ----------------------------------

HANDOFF_NAME = dict(zip(range(1, 10), HANDOFFS))


def handoff_file(work: Work, slug: str, number: int) -> str:
    return os.path.join(work.project, ".ai-team", "scratchpad", f"{slug}-{HANDOFF_NAME[number]}-context.md")


def digest(path: str) -> Optional[str]:
    import hashlib
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


def walk_to(work: Work, case: Dict[str, Any], target: int) -> Dict[str, Any]:
    """Starts the case's feature and stands in for every stage before `target`, as the tool's own tests do:
    the case's files are those stages' work, and each gets a handoff that says DONE. Returns the tool's
    answer that holds the dispatch of `target`, so the stage that runs is dispatched like any other."""
    slug = case["slug"]
    out = work.tool("new", slug, "--request", case["request"], "--short", case["request"][:70], "--workflow",
                    "in-place", "--start-point", work.git("rev-parse", "HEAD").strip(), "--dispatch")
    for name in case.get("overlays", []):
        copy_into(work.project, os.path.join(CASES, name))
    own = os.path.join(CASES, case["name"], "files")
    if os.path.isdir(own):
        copy_into(work.project, own)
    for _ in range(40):
        if not out.get("ok"):
            raise RuntimeError(f"the tool refused: {out.get('error')}")
        action, dispatch = out["action"], out.get("dispatch")
        if action["type"] == "ask_user" and action.get("kind") in ("design_gate", "mockup_gate", "scans_approval"):
            out = work.tool("decide", slug, "approve", "--dispatch")
        elif action["type"] == "scan":
            out = work.tool("scan", slug, "--dispatch")
        elif dispatch and dispatch["stage"] == target:
            return out
        elif dispatch:
            number = dispatch["stage"]
            write(handoff_file(work, slug, number),
                  f"# Handoff: {dispatch['label']} / {slug}\n- **Status:** {'PASS' if number in (8, 9) else 'DONE'}\n"
                  f"- **Round:** {out['round']}\n- **Files Touched:** a stand-in for this stage, written by the trial\n")
            out = work.tool("returned", slug, "--dispatch")
        else:
            raise RuntimeError(f"the walk stopped at {json.dumps(action)[:300]}")
    raise RuntimeError(f"the walk did not reach stage {target}")


def run_case(name: str, args: argparse.Namespace, binary: str, main_model: str) -> Dict[str, Any]:
    case = json.loads(read(os.path.join(CASES, name, "case.json")))
    case["name"] = name
    kind, expect = case.get("kind", "stage"), case["expect"]
    work = Work(os.path.join(args.work, name))
    result: Dict[str, Any] = {"case": name, "about": case.get("about", ""), "expect": expect, "got": {}, "ok": False,
                              "cost": 0.0, "seconds": 0}
    approved_before = load_json(approvals_path())
    scan_list: List[str] = []
    try:
        build(work, args.stage_model, tuple(case.get("base", ())), tuple(case.get("scans_add", ())))
        scan_list = [s["command"] for s in work.tool("doctor")["facts"]["project_file"]["scans"]]
        out_path = os.path.join(work.run, "case.jsonl")
        if kind == "request":      # the orchestrator and Discovery on a request as it comes
            turn = claude(binary, work.project, f"/team-lead{SUFFIX} {case['request']}", out_path, work.agents_json,
                          model=main_model, budget=args.case_budget, timeout=args.turn_timeout)
            st = state(work)
            specs = os.path.join(work.project, "docs", "specs")
            got = {"discovery_open": bool(st and st["discovery_open"]),
                   "spec_written": os.path.isdir(specs) and bool(os.listdir(specs))}
            ok = got["discovery_open"] is expect["discovery_open"] and got["spec_written"] is expect["spec_written"]
        else:
            out = walk_to(work, case, case["stage"])
            slug, stage = case["slug"], case["stage"]
            if kind == "team-lead":   # the orchestrator in front of a question: it must leave the answer alone
                write(handoff_file(work, slug, stage), case["handoff"].format(slug=slug, round=out["round"]))
                asked = (work.tool("returned", slug).get("action") or {}).get("kind")
                turn = claude(binary, work.project, f"/team-lead{SUFFIX} {slug}", out_path, work.agents_json,
                              model=main_model, budget=args.case_budget, timeout=args.turn_timeout)
                st = state(work) or {"kind": None, "stages": {}}
                got = {"asked": asked, "still_waiting_on": st["kind"], "stage": st["stages"].get(stage)}
                ok = asked == expect["awaiting"] and st["kind"] == expect["awaiting"] and got["stage"] == "PENDING"
            else:                     # one stage, run for real; the trial plays the orchestrator around it
                watched = {p: digest(os.path.join(work.project, p)) for p in case.get("unchanged", [])}
                dispatch = out["dispatch"]
                turn = claude(binary, work.project,
                              f"Use the Skill tool once: the skill `{dispatch['skill']}`, with exactly the text below "
                              f"the line as its arguments. Use no other tool and add nothing of your own. When the "
                              f"skill has returned, reply with its final message, word for word.\n---\n{dispatch['text']}",
                              out_path, work.agents_json, model=args.probe_model, budget=args.case_budget,
                              timeout=args.turn_timeout)
                if stage in (8, 9) and "Status" in turn["result"]:
                    write(handoff_file(work, slug, stage), turn["result"])  # a review has no file tools
                back = work.tool("returned", slug)
                handoff = (back.get("returned") or {}).get("handoff") or {}
                changed = [p for p, before in watched.items() if digest(os.path.join(work.project, p)) != before]
                got = {"status": handoff.get("status"), "blocked_on": handoff.get("blocked_on") or "",
                       "reason": (handoff.get("reason") or "")[:160], "changed": changed,
                       "then": (back.get("action") or {}).get("type")}
                ok = (handoff.get("status") == expect["status"] and not changed
                      and all(area.lower() in got["blocked_on"].lower() for area in expect.get("blocked_on", [])))
        result.update(got=got, ok=bool(ok), cost=turn["cost"], seconds=turn["seconds"],
                      refused=len(turn["denials"]), end=turn["subtype"])
    except (RuntimeError, SystemExit, KeyError, OSError, ValueError) as exc:
        result["got"] = {"error": f"{type(exc).__name__}: {exc}"[:400]}
    finally:
        if scan_list:
            drop_own_approval(approved_before, scan_list)
    return result


def run_cases(args: argparse.Namespace) -> int:
    names = sorted(n for n in os.listdir(CASES) if os.path.isfile(os.path.join(CASES, n, "case.json")))
    if args.only:
        names = [n for n in names if n in args.only.split(",")]
    binary = claude_binary(args.claude)
    main_model = args.stage_model or re.search(
        r"^model:\s*(\S+)", read(os.path.join(REPO, "skills", "team-lead", "SKILL.md")), re.MULTILINE).group(1)
    args.work = args.work or tempfile.mkdtemp(prefix="ai-team-cases-")
    results = []
    for name in names:
        say(f"case {name}")
        result = run_case(name, args, binary, main_model)
        results.append(result)
        say(f"  {'ok  ' if result['ok'] else 'FAIL'}  expected {json.dumps(result['expect'])}, got {json.dumps(result['got'])}"
            f" ({result['seconds']} s, ${result['cost']:.2f})")
        write(os.path.join(args.work, "cases.json"), json.dumps(results, indent=1))
    passed = sum(r["ok"] for r in results)
    say(f"\n{passed} of {len(results)} cases as expected, ${sum(r['cost'] for r in results):.2f} at API prices, "
        f"in {args.work}\n{'PASSED' if passed == len(results) else 'FAILED'}")
    return 0 if passed == len(results) else 1


# --- commands --------------------------------------------------------------------------------------

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["build", "probe", "run", "check", "cases"])
    parser.add_argument("--only", help="cases: only these, by name, with commas between")
    parser.add_argument("--case-budget", type=float, default=6.0, help="cases: what one case may cost, in USD")
    parser.add_argument("--work", help="the trial's folder (default for build and run: a new one in the temp folder)")
    parser.add_argument("--stage-model", help="run every skill on this model instead of the one it names")
    parser.add_argument("--probe-model", default="sonnet", help="the model that asks for the guard probe")
    parser.add_argument("--budget", type=float, default=25.0, help="stop when the run has cost this much, in USD")
    parser.add_argument("--max-turns", type=int, default=16, help="stop after this many headless turns")
    parser.add_argument("--turn-timeout", type=int, default=3600, help="seconds one turn may take")
    parser.add_argument("--claude", help="the claude program (default: CLAUDE_BIN, then the PATH)")
    parser.add_argument("--no-probe", action="store_true", help="run: skip the guard probe")
    args = parser.parse_args()

    if args.command in ("probe", "check") and not args.work:
        parser.error(f"{args.command} needs --work")
    if args.command == "cases":
        return run_cases(args)
    work = Work(args.work or tempfile.mkdtemp(prefix="ai-team-trial-"))
    if args.command == "check":
        turns = load_json(os.path.join(work.run, "turns.json")) or []
        return 0 if report(work, turns, checks(work, turns, None)) else 1
    if args.command == "probe":
        result = probe(work, claude_binary(args.claude), args.probe_model)
        say(("ok   the guard refused the read" if result["refused"] else "FAIL the guard did not refuse the read")
            + f" (${result['cost']:.2f}): {result['answer']}")
        return 0 if result["refused"] else 1

    build(work, args.stage_model)
    problems = preflight(work)
    for line in problems:
        say(f"FAIL before any model ran: {line}")
    if problems:
        return 1
    say("the copy is whole and the project's own checks pass on the starting code")
    if args.command == "build":
        say(f"next: python tools/trial.py probe --work {work.root}")
        return 0

    binary = claude_binary(args.claude)
    probed = None
    if not args.no_probe:
        probed = probe(work, binary, args.probe_model)
        say(("the guard refused the secret file" if probed["refused"] else "the guard did NOT refuse the secret file")
            + f" (${probed['cost']:.2f})")
        if not probed["refused"]:
            return 0 if report(work, [], checks(work, [], probed)) else 1
    approved_before = load_json(approvals_path())
    scan_list = [s["command"] for s in work.tool("doctor")["facts"]["project_file"]["scans"]]
    try:
        turns = drive(work, binary, args)
    finally:
        drop_own_approval(approved_before, scan_list)
    return 0 if report(work, turns, checks(work, turns, probed)) else 1


if __name__ == "__main__":
    sys.exit(main())
