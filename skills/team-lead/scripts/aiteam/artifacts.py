"""Parsers for the parts of the artifacts that the Artifact Contracts fix."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import model
from .project import read_text, to_posix

_REVISION = re.compile(r"^\s*[-*]?\s*\**Revision:?\**:?\s*\**\s*(\d+)", re.IGNORECASE | re.MULTILINE)


def revision(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    m = _REVISION.search(text)
    return int(m.group(1)) if m else None


def _yes_no(text: str, label: str) -> Optional[bool]:
    m = re.search(rf"{re.escape(label)}\W*?\s*\**\s*`?(yes|no)\b", text, re.IGNORECASE)
    if not m:
        return None
    return m.group(1).lower() == "yes"


def topology_flags(spec_text: Optional[str]) -> Dict[str, Optional[bool]]:
    flags: Dict[str, Optional[bool]] = {"User-Facing Text": None, "UI": None}
    if not spec_text:
        return flags
    m = re.search(r"^##\s+Topology Flags\s*$(?P<body>.*?)(?=^##\s|\Z)", spec_text,
                  re.MULTILINE | re.DOTALL | re.IGNORECASE)
    body = m.group("body") if m else spec_text
    flags["User-Facing Text"] = _yes_no(body, "User-Facing Text")
    ui = re.search(r"^\s*[-*]\s*\**UI:?\**:?\s*\**\s*`?(yes|no)\b", body, re.IGNORECASE | re.MULTILINE)
    flags["UI"] = (ui.group(1).lower() == "yes") if ui else None
    if flags["UI"]:
        flags["User-Facing Text"] = True  # the contract: UI yes implies text yes
    return flags


def infra_impact(adr_text: Optional[str]) -> Optional[bool]:
    if not adr_text:
        return None
    return _yes_no(adr_text, "Infra Impact")


_LABEL_RX = {
    which: re.compile(rf"Allowed Blast Radius\s*\(\s*{which}\s*\)", re.IGNORECASE)
    for which in ("Source", "Infra")
}
_LABEL_LINE = {
    which: re.compile(rf"^\s*(?:#+\s*.*?|(?:[-*+]\s+)?\*\*\s*`?)Allowed Blast Radius\s*\(\s*{which}\s*\)",
                      re.IGNORECASE)
    for which in ("Source", "Infra")
}


def blast_radius_read(adr_text: Optional[str], which: str) -> Dict[str, object]:
    """Read `Allowed Blast Radius (Source|Infra)` as rules 8.0 write it.

    The label is a heading or a bold label; it is followed by a list, one item per
    file, starting with the path in backticks, or the one item `none`. A mention of
    the label in prose is not the label.
    """
    result: Dict[str, object] = {"found": False, "none": False, "entries": []}
    if not adr_text:
        return result
    lines = adr_text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if _LABEL_LINE[which].search(line):
            start = idx
            break
    if start is None:
        return result
    result["found"] = True
    entries: List[Tuple[str, str]] = []
    head = _LABEL_RX[which].split(lines[start], maxsplit=1)[1]
    head = re.sub(r"^[\s*:]+", "", head).strip()
    if head.lower().strip("`. ") in ("none", "nothing"):
        result["none"] = True
    elif head:
        toks = re.findall(r"`([^`]+)`", head)
        for tok in toks:
            entries.append((to_posix(tok.strip()), ""))
        if not toks:
            result["unreadable_head"] = head
    in_list = False
    for line in lines[start + 1:]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or any(r.search(stripped) for r in _LABEL_LINE.values()):
            break
        item = re.match(r"^(?:[-*+]|\d+\.)\s+(?P<body>.*)$", stripped)
        if not item:
            if in_list:
                break  # a paragraph after the list ends it
            continue  # prose between the label and its list
        body = item.group("body")
        if body.startswith("**") and not body.startswith("**`"):
            break  # the next labelled field of a flat list
        in_list = True
        body = body.strip("*")
        if body.lower().strip(". ") in ("none", "nothing"):
            result["none"] = True
            continue
        m = re.match(r"\s*`([^`]+)`\s*(?P<note>.*)$", body)
        if m:
            entries.append((to_posix(m.group(1).strip()), m.group("note").strip(" -—:;,")))
    result["entries"] = entries
    if entries or result["none"]:
        result.pop("unreadable_head", None)
    return result


def blast_radius(adr_text: Optional[str], which: str) -> List[Tuple[str, str]]:
    """Entries of `Allowed Blast Radius (Source|Infra)`: (path, note)."""
    return list(blast_radius_read(adr_text, which)["entries"])  # type: ignore[arg-type]


@dataclass
class Handoff:
    path: str
    exists: bool
    status: Optional[str] = None
    round: Optional[int] = None
    blocked_on: List[str] = field(default_factory=list)
    blocked_on_raw: str = ""
    reason: str = ""
    has_for_later: bool = False
    remarks: str = ""
    mtime: float = 0.0
    text: str = ""

    @property
    def parsed(self) -> bool:
        return self.exists and self.status is not None and self.round is not None


_HFIELD = re.compile(r"^\s*(?:[-*+]\s+)?\*\*(?P<name>[^*:]+):?\*\*:?\s*(?P<value>.*)$")
_HFIELD_NAMES = ("status", "round", "blocked on", "reason", "files touched")


def split_areas(raw: str) -> List[str]:
    """`Source, Tests` -> ['Source', 'Tests']; an unknown name is kept as '?name'."""
    areas: List[str] = []
    for part in re.split(r"\s*(?:,|;|&|\band\b|\s/\s)\s*", raw or ""):
        part = re.sub(r"\(.*?\)", "", part)
        part = re.split(r"\s[-—–:]\s|:\s", part)[0].strip()
        if not part or part.strip("`*_ .").lower() in ("none", "n/a", "-", "nothing"):
            continue
        area = model.normalize_area(part)
        if area is None:
            area = "?" + part
        if area not in areas:
            areas.append(area)
    return areas


def parse_handoff(root: str, rel: str) -> Handoff:
    full = os.path.join(root, *rel.split("/"))
    text = read_text(full)
    if text is None:
        return Handoff(path=rel, exists=False)
    h = Handoff(path=rel, exists=True, text=text, mtime=os.path.getmtime(full))
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if re.match(r"^#{1,3}\s+Handoff\b", line.strip(), re.IGNORECASE):
            start = idx
            break
    if start is None:
        return h
    end = start + 1
    blank_seen = False
    for idx in range(start + 1, len(lines)):
        line = lines[idx]
        if not line.strip():
            blank_seen = True  # a blank line between the fields does not end the block
            continue
        m = _HFIELD.match(line)
        name = m.group("name").strip().lower() if m else ""
        if not m or (blank_seen and name not in _HFIELD_NAMES):
            end = idx  # after a blank line, only a field of the block continues it
            break
        end = idx + 1
        value = m.group("value").strip()
        if name == "status":
            word = re.match(r"([A-Za-z_]+)", value.strip("`*_ "))
            h.status = word.group(1).upper() if word else None
        elif name == "round":
            num = re.search(r"\d+", value)
            h.round = int(num.group()) if num else None
        elif name == "blocked on":
            h.blocked_on_raw = value
            h.blocked_on = split_areas(value)
        elif name == "reason":
            h.reason = value
    rest = "\n".join(lines[end:]).strip()
    h.has_for_later = bool(re.search(r"^#{2,4}\s+For Later Stages\s*$", text, re.MULTILINE | re.IGNORECASE))
    h.remarks = rest
    return h


# Mock-ups -----------------------------------------------------------------------------------

_SHOT = re.compile(r"^(?P<screen>.+)-(?P<kind>before|after)-(?P<width>[^.]+)\.png$", re.IGNORECASE)


def mockup_listing(root: str, slug: str) -> Dict[str, object]:
    folder = os.path.join(root, *model.mockup_dir(slug).split("/"))
    screens: Dict[str, Dict[str, object]] = {}
    others: List[str] = []
    if not os.path.isdir(folder):
        return {"folder": model.mockup_dir(slug), "screens": [], "pages": 0, "others": []}
    for name in sorted(os.listdir(folder)):
        rel = f"{model.mockup_dir(slug)}/{name}"
        if name.lower().endswith(".html"):
            screen = name[:-5]
            screens.setdefault(screen, {"screen": screen, "page": None, "before": [], "after": []})
            screens[screen]["page"] = rel
            continue
        m = _SHOT.match(name)
        if m:
            entry = screens.setdefault(m.group("screen"),
                                       {"screen": m.group("screen"), "page": None, "before": [], "after": []})
            entry[m.group("kind").lower()].append({"width": m.group("width"), "file": rel})
            continue
        others.append(rel)
    pages = sum(1 for s in screens.values() if s["page"])
    return {"folder": model.mockup_dir(slug), "screens": list(screens.values()), "pages": pages,
            "others": others}


def mockup_hash(root: str, slug: str) -> Optional[str]:
    """Hash of the mock-up's pages and assets; screenshots are left out."""
    folder = os.path.join(root, *model.mockup_dir(slug).split("/"))
    if not os.path.isdir(folder):
        return None
    digest = hashlib.sha256()
    found = False
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames.sort()
        for name in sorted(filenames):
            if name.lower().endswith(".png"):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, folder).replace("\\", "/")
            digest.update(rel.encode("utf-8") + b"\0")
            with open(full, "rb") as fh:
                digest.update(hashlib.sha256(fh.read()).digest())
            found = True
    return digest.hexdigest() if found else None
