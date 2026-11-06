"""Deterministic checks: the project's scans, run by ai_team.py before the reviews,
and a proposal of gates and scans for a project that has none.
"""

from __future__ import annotations

import json
import locale
import os
import re
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from . import model
from .project import Project, Scan, read_text

CALL_BUDGET = 540           # one call runs scans for at most this long: 60 s under the shell tool's 600 s
SCAN_TIMEOUT = 540          # seconds per scan, at most; less when the call's budget is nearly spent
OUTPUT_LIMIT = 15000        # characters of a scan's output kept in the report
NOT_FOUND = re.compile(r"not recognized as an internal or external command|command not found|"
                       r"No such file or directory|is not recognized as the name of a cmdlet", re.IGNORECASE)


def _approvals_path() -> str:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "ai-team-approved-scans.json")


def scans_fingerprint(scans: List[Scan]) -> str:
    import hashlib
    text = "\n".join(f"{s.command}\t{s.fails_when or ''}" for s in scans)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def scans_approved(scans: List[Scan]) -> bool:
    """The user approved this exact list of scan commands before (in any project)."""
    try:
        with open(_approvals_path(), "r", encoding="utf-8") as fh:
            approved = json.load(fh)
    except (OSError, ValueError):
        return False
    return scans_fingerprint(scans) in approved


def approve_scans(scans: List[Scan]) -> None:
    path = _approvals_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            approved = json.load(fh)
    except (OSError, ValueError):
        approved = {}
    approved[scans_fingerprint(scans)] = {"approved": time.strftime("%Y-%m-%d %H:%M"),
                                          "commands": [s.command for s in scans]}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(approved, fh, indent=1)


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(locale.getpreferredencoding(False) or "latin-1", "replace")


def output_path(slug: str, index: int) -> str:
    return f"{model.SCRATCH_DIR}/{slug}-scan-{index + 1}.txt"


def _run_tree(command: str, cwd: str, timeout: float) -> Tuple[Optional[int], str]:
    """Run a shell command and, on timeout, kill it with everything it started."""
    kwargs: Dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(command, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            **kwargs)
    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, _decode(out or b"")
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        else:
            import signal
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
        try:
            out, _ = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            out = b""
        return None, _decode(out or b"")


def run_one(root: str, slug: str, index: int, scan: Scan, timeout: float = SCAN_TIMEOUT) -> Dict[str, Any]:
    started = time.time()
    timed_out = False
    timeout = max(30.0, min(float(timeout), SCAN_TIMEOUT))
    code: Optional[int]
    code, out = _run_tree(scan.command, root, timeout)
    if code is None:
        timed_out = True
    matched = bool(scan.fails_when and re.search(scan.fails_when, out, re.IGNORECASE | re.MULTILINE))
    if timed_out:
        result, why = "FAILED", f"timed out after {int(timeout)} s"
    elif code in (127, 9009) or (code != 0 and NOT_FOUND.search((out or "").strip().split("\n")[0][:300])):
        result, why = "COULD NOT RUN", f"exit code {code}: the tool is not installed or not on PATH"
    elif code != 0:
        result, why = "FAILED", f"exit code {code}"
    elif matched:
        result, why = "FAILED", f"output matches `{scan.fails_when}`"
    else:
        result, why = "passed", "exit code 0"
    path = os.path.join(root, *output_path(slug, index).split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(out)
    return {"index": index, "command": scan.command, "fails_when": scan.fails_when, "exit_code": code,
            "result": result, "why": why, "seconds": round(time.time() - started, 1),
            "output": output_path(slug, index)}


def write_report(root: str, slug: str, rnd: int, results: List[Dict[str, Any]]) -> str:
    failed = [r for r in results if r["result"] == "FAILED"]
    missing = [r for r in results if r["result"] == "COULD NOT RUN"]
    lines = [f"# Scan Report: {slug}", f"- **Round:** {rnd}",
             f"- **Result:** {len(failed)} of {len(results)} scans failed"
             + (f", {len(missing)} could not run" if missing else ""), "",
             "Written by ai_team.py, which ran each scan of the project file from the feature's folder."]
    for r in results:
        lines += ["", f"## `{r['command']}`", f"- **Result:** {r['result']} ({r['why']})",
                  f"- **Exit code:** {r['exit_code']}"]
        if r.get("fails_when"):
            lines.append(f"- **Fails when:** `{r['fails_when']}`")
        out = read_text(os.path.join(root, *r["output"].split("/"))) or ""
        if len(out) > OUTPUT_LIMIT:
            out = f"[... {len(out) - OUTPUT_LIMIT} characters cut; the full output is in {r['output']} ...]\n" \
                  + out[-OUTPUT_LIMIT:]
        fence = "````" if "```" in out else "```"
        lines += ["", f"{fence}text", out.rstrip("\n") or "(no output)", fence]
    rel = model.scan_report_path(slug)
    path = os.path.join(root, *rel.split("/"))
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return rel


# --- proposal ------------------------------------------------------------------------------------

_SKIP = {".git", ".ai-team", "node_modules", ".venv", "venv", "env", "bin", "obj", "dist", "build",
         "__pycache__", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "target", ".claude"}


def _files(root: str, depth: int = 3) -> List[str]:
    found = []
    base = len(os.path.abspath(root).rstrip(os.sep).split(os.sep))
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP and not d.startswith(".")]
        if len(os.path.abspath(dirpath).split(os.sep)) - base >= depth:
            dirnames[:] = []
        for name in filenames:
            found.append(os.path.relpath(os.path.join(dirpath, name), root).replace("\\", "/"))
    return found


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def _pyproject_has(root: str, needle: str) -> bool:
    text = read_text(os.path.join(root, "pyproject.toml")) or ""
    return needle in text


def propose(root: str, project: Project) -> Dict[str, Any]:
    files = _files(root)
    names = {f.rsplit("/", 1)[-1] for f in files}
    stacks: List[str] = []
    gates: Dict[str, List[str]] = {"5. Coding": [], "7. Testing": []}
    scans: List[Dict[str, Any]] = []
    notes: List[str] = []

    def scan(command: str, tool: str, fails_when: Optional[str] = None, link: Optional[str] = None) -> None:
        scans.append({"command": command, "fails_when": fails_when, "installed": _have(tool), "tool": tool,
                      "link": link})

    source_paths = [p.token.strip("/") for p in project.source] or ["src"]
    source_paths = [p for p in source_paths if os.path.isdir(os.path.join(root, p))] or ["."]

    # Python first: the most common stack here
    if names & {"pyproject.toml", "setup.py", "setup.cfg", "Pipfile"} or any(
            re.match(r"requirements.*\.txt$", n) for n in names):
        stacks.append("python")
        if "uv.lock" in names:
            run, tool_run = "uv run ", "uvx "
        elif "poetry.lock" in names:
            run, tool_run = "poetry run ", "poetry run "
        elif "Pipfile.lock" in names:
            run, tool_run = "pipenv run ", "pipenv run "
        else:
            run, tool_run = "", ""
            notes.append("No uv, Poetry or Pipenv lock file: the Python commands use the active environment. "
                         "In a worktree, write them the way the Worktree setup line starts tools.")
        test_cmd = f"{run}pytest -q"
        gates["5. Coding"].append(test_cmd)
        gates["7. Testing"].append(test_cmd)
        if "ruff.toml" in names or ".ruff.toml" in names or _pyproject_has(root, "[tool.ruff"):
            gates["5. Coding"].insert(0, f"{run}ruff check .")
        if "mypy.ini" in names or _pyproject_has(root, "[tool.mypy"):
            gates["5. Coding"].insert(0, f"{run}mypy .")
        reqs = sorted(f for f in files if re.match(r"^requirements[^/]*\.txt$", f))
        audit = f"{tool_run}pip-audit " + (f"-r {reqs[0]}" if reqs else ".")
        scan(audit.strip(), "uvx" if tool_run == "uvx " else "pip-audit", link="https://github.com/pypa/pip-audit")
        scan(f"{tool_run}bandit -r {' '.join(source_paths)} -ll -q".strip(), "uvx" if tool_run == "uvx " else "bandit",
             link="https://github.com/PyCQA/bandit")
    if any(n.endswith((".sln", ".csproj", ".fsproj")) for n in names):
        stacks.append("dotnet")
        gates["5. Coding"] += ["dotnet build", "dotnet test"]
        gates["7. Testing"].append("dotnet test")
        scan("dotnet list package --vulnerable --include-transitive", "dotnet",
             fails_when="has the following vulnerable packages",
             link="https://learn.microsoft.com/dotnet/core/tools/dotnet-list-package")
    if "package.json" in names:
        stacks.append("node")
        pm = "pnpm" if "pnpm-lock.yaml" in names else ("yarn" if "yarn.lock" in names else "npm")
        try:
            pkg = json.loads(read_text(os.path.join(root, "package.json")) or "{}")
        except ValueError:
            pkg = {}
        scripts = pkg.get("scripts") or {}
        if "build" in scripts:
            gates["5. Coding"].append(f"{pm} run build")
        if "test" in scripts:
            gates["5. Coding"].append(f"{pm} test")
            gates["7. Testing"].append(f"{pm} test")
        scan(f"{pm} audit --audit-level=high" if pm != "yarn" else "yarn npm audit --severity high", pm,
             link="https://docs.npmjs.com/cli/commands/npm-audit")
    if "Cargo.toml" in names:
        stacks.append("rust")
        gates["5. Coding"] += ["cargo build", "cargo test"]
        gates["7. Testing"].append("cargo test")
        scan("cargo audit", "cargo-audit", link="https://github.com/rustsec/rustsec/tree/main/cargo-audit")
    if "go.mod" in names:
        stacks.append("go")
        gates["5. Coding"] += ["go build ./...", "go test ./..."]
        gates["7. Testing"].append("go test ./...")
        scan("govulncheck ./...", "govulncheck", link="https://go.dev/doc/security/vuln/")
    secret_paths = source_paths + [p.token.strip("/") for p in project.tests
                                   if os.path.isdir(os.path.join(root, p.token.strip("/")))]
    for path in dict.fromkeys(secret_paths):
        scan(f"gitleaks dir {path} --redact --no-banner", "gitleaks", link="https://github.com/gitleaks/gitleaks")
    if _have("semgrep"):
        scan(f"semgrep scan --error --quiet --config auto {' '.join(source_paths)}", "semgrep",
             link="https://semgrep.dev")
    else:
        notes.append("Semgrep (https://semgrep.dev) is not installed; when it is, a scan like "
                     "`semgrep scan --error --quiet --config auto <paths>` can be added.")

    gates = {k: list(dict.fromkeys(v)) for k, v in gates.items() if v}
    md = ["## Scans", "",
          "`ai_team.py` runs these once per round, before its first review, from the feature's folder, and "
          "gives the reviewers "
          "their output. A scan fails on a non-zero exit code, or when its output matches the pattern after "
          "`fails when`.", ""]
    for s in scans:
        line = f"- `{s['command']}`"
        if s["fails_when"]:
            line += f" fails when `{s['fails_when']}`"
        md.append(line)
    md += ["", "## Second Review", "", "- **Second Review:** no", ""]
    gate_lines = ["- **Gates:**"]
    for stage, cmds in gates.items():
        gate_lines.append(f"  - {stage}: " + ", ".join(f"`{c}`" for c in cmds) + " pass.")
    missing = sorted({s["tool"] for s in scans if not s["installed"]})
    if missing:
        notes.append("Not installed here: " + ", ".join(missing) + ". A scan whose tool is missing is reported as "
                     "COULD NOT RUN; install the tool or leave the scan out.")
    return {"ok": True, "stacks": stacks, "gates": gates, "scans": scans, "notes": notes,
            "markdown_sections": "\n".join(md),
            "markdown_gates": "\n".join(gate_lines) if gates else "",
            "where": "Put the two sections before `## Overrides for this project`, and the Gates lines inside "
                     "that section in place of `- None.`"}
