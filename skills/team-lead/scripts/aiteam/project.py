"""The project file (.claude/ai-team-project.md) and the areas of paths."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import model

IGNORE_CASE = os.name == "nt"


def read_text(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            return fh.read()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None


def to_posix(path: str) -> str:
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def norm_key(rel: str) -> str:
    """Comparison key for a project-relative path (case-insensitive on Windows)."""
    rel = to_posix(rel).strip("/")
    return rel.lower() if IGNORE_CASE else rel


def _glob_to_regex(glob: str) -> str:
    out = []
    i = 0
    while i < len(glob):
        ch = glob[i]
        if ch == "*":
            if glob[i:i + 2] == "**":
                i += 2
                if glob[i:i + 1] == "/":
                    out.append("(?:.*/)?")
                    i += 1
                else:
                    out.append(".*")
                continue
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        elif ch == "[":
            end = glob.find("]", i + 1)
            if end == -1:
                out.append(re.escape(ch))
            else:
                out.append(glob[i:end + 1])
                i = end + 1
                continue
        else:
            out.append(re.escape(ch))
        i += 1
    return "".join(out)


@dataclass
class PathPattern:
    """A path written in backticks in the project file, matched like a .gitignore line.

    `src/` matches a folder named src at any depth, `/src/` only at the root,
    `*.test.*` a file name anywhere, and `src/**/Migrations/` a path from the root.
    """

    token: str
    regex: "re.Pattern[str]" = field(repr=False, default=None)  # type: ignore[assignment]

    @classmethod
    def compile(cls, token: str) -> "PathPattern":
        tok = to_posix(token.strip())
        dir_only = tok.endswith("/")
        body = tok.strip("/") if tok.startswith("/") else tok.rstrip("/")
        anchored = tok.startswith("/") or "/" in body
        body = body.lstrip("/")
        prefix = "^" if anchored else "^(?:.*/)?"
        suffix = "/.*$" if dir_only else "(?:/.*)?$"
        flags = re.IGNORECASE if IGNORE_CASE else 0
        return cls(token=token, regex=re.compile(prefix + _glob_to_regex(body) + suffix, flags))

    def matches(self, rel: str) -> bool:
        return bool(self.regex.match(to_posix(rel).strip("/")))


@dataclass
class Scan:
    """A command of the project file's `Scans` section."""

    command: str
    fails_when: Optional[str] = None


@dataclass
class Project:
    root: str
    path: str
    exists: bool
    text: str = ""
    source: List[PathPattern] = field(default_factory=list)
    tests: List[PathPattern] = field(default_factory=list)
    infra: List[PathPattern] = field(default_factory=list)
    workflow: str = ""
    worktree_setup: str = ""
    mockup: str = ""
    overrides: str = ""
    scans: List[Scan] = field(default_factory=list)
    second_review: Optional[bool] = None
    second_review_raw: str = ""

    @property
    def has_gates(self) -> bool:
        return bool(re.search(r"\*\*Gates:?\*\*", self.overrides or ""))

    def area_of(self, rel: str, slug: Optional[str] = None) -> Optional[str]:
        """The area a project-relative path lies in, or None."""
        rel = to_posix(rel).strip("/")
        key = norm_key(rel)
        if slug:
            for area, names in model.AREA_ARTIFACTS.items():
                for name in names:
                    if key == norm_key(model.artifact_path(name, slug)):
                        return area
        for area, patterns in (("Tests", self.tests), ("Infra", self.infra), ("Source", self.source)):
            if any(p.matches(rel) for p in patterns):
                return area
        return None

    def describe(self) -> Dict[str, object]:
        return {
            "path": self.path,
            "exists": self.exists,
            "source": [p.token for p in self.source],
            "tests": [p.token for p in self.tests],
            "infra": [p.token for p in self.infra],
            "workflow": self.workflow,
            "worktree_setup": self.worktree_setup,
            "mockup": self.mockup,
            "scans": [{"command": s.command, "fails_when": s.fails_when} for s in self.scans],
            "second_review": self.second_review,
            "gates": self.has_gates,
        }


_FIELD = re.compile(r"^\s*[-*]\s+\*\*(?P<name>[^*:]+):?\*\*:?\s*(?P<rest>.*)$")


def _fields(text: str) -> Dict[str, str]:
    """Collect `- **Name:** value` lines, joining wrapped continuation lines."""
    found: Dict[str, str] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _FIELD.match(lines[i])
        if not m:
            i += 1
            continue
        name = m.group("name").strip().lower()
        parts = [m.group("rest").strip()]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if not nxt.strip() or re.match(r"^\s*([-*]\s|#)", nxt) or not nxt.startswith((" ", "\t")):
                break
            parts.append(nxt.strip())
            i += 1
        found.setdefault(name, " ".join(p for p in parts if p))
    return found


def _section(text: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$(?P<body>.*?)(?=^##\s|\Z)",
                         re.MULTILINE | re.DOTALL | re.IGNORECASE)
    m = pattern.search(text)
    return m.group("body").strip() if m else ""


def _patterns(value: str) -> List[PathPattern]:
    return [PathPattern.compile(tok) for tok in re.findall(r"`([^`]+)`", value or "") if tok.strip()]


def _scans(text: str) -> List[Scan]:
    """List items of the `## Scans` section: a command in backticks, then optionally
    `fails when` and a pattern in backticks."""
    scans: List[Scan] = []
    for line in _section(text, "Scans").splitlines():
        if not re.match(r"^\s*[-*+]\s+`", line):
            continue  # a scan is a list item that starts with its command in backticks
        ticks = re.findall(r"`([^`]+)`", line)
        if not ticks:
            continue
        fails = None
        m = re.search(r"fails\s+when\s+`([^`]+)`", line, re.IGNORECASE)
        if m:
            fails = m.group(1)
        scans.append(Scan(command=ticks[0].strip(), fails_when=fails))
    return scans


def _yes_no(value: str) -> Optional[bool]:
    m = re.match(r"\W*(yes|no)\b", value or "", re.IGNORECASE)
    return (m.group(1).lower() == "yes") if m else None


def load(root: str) -> Project:
    path = os.path.join(root, *model.PROJECT_FILE.split("/"))
    text = read_text(path)
    if text is None:
        return Project(root=root, path=model.PROJECT_FILE, exists=False)
    fields = _fields(text)
    return Project(
        root=root,
        path=model.PROJECT_FILE,
        exists=True,
        text=text,
        source=_patterns(fields.get("source", "")),
        tests=_patterns(fields.get("tests", "")),
        infra=_patterns(fields.get("infra", "")),
        workflow=fields.get("workflow", "").strip("` "),
        worktree_setup=fields.get("worktree setup", ""),
        mockup=fields.get("mock-up", ""),
        overrides=_section(text, "Overrides for this project"),
        scans=_scans(text),
        second_review=_yes_no(fields.get("second review", "")),
        second_review_raw=fields.get("second review", ""),
    )
