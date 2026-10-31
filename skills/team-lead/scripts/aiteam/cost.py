"""Tokens per pipeline stage, read from Claude Code's session transcripts.

Claude Code keeps one JSONL file per session under ~/.claude/projects/, and the
subagents' transcripts beside it. A stage's subagent starts with its dispatch, so
the `Stage:` and `Round:` lines of the first prompt say which stage it ran.
The transcript format is Claude Code's own and may change: this report is
best-effort, and says so when it finds nothing it can read.
"""

from __future__ import annotations

import glob
import json
import os
import re
import time
from typing import Any, Dict, Iterable, Optional, Tuple

_STAGE = re.compile(r"^Stage:\s*(\d+)\.\s*(.+?)\s*$", re.MULTILINE)
_ROUND = re.compile(r"^Round:\s*(\d+)\s*$", re.MULTILINE)
_RULES = re.compile(r"^Rules:\s*\S", re.MULTILINE)
_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block.get("content"), (str, list)):
                    parts.append(_text_of(block["content"]))
        return "\n".join(parts)
    return ""


def _dispatch_of(text: str) -> Optional[Tuple[str, int, str, int]]:
    st, rnd = _STAGE.search(text), _ROUND.search(text)
    if not st or not _RULES.search(text):
        return None
    head = text[: st.start()].strip().splitlines()
    slug = head[-1].split()[0] if head and head[-1].split() else "?"
    return slug, int(st.group(1)), st.group(2), int(rnd.group(1)) if rnd else 0


def _lines(path: str) -> Iterable[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    yield obj
    except OSError:
        return


def scan(projects_dir: str, days: float = 30, slug: Optional[str] = None) -> Dict[str, Any]:
    since = time.time() - days * 86400
    files = [p for p in glob.glob(os.path.join(projects_dir, "**", "*.jsonl"), recursive=True)
             if os.path.getmtime(p) >= since]
    groups: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for path in files:
        for obj in _lines(path):
            agent = obj.get("agentId") or ("sidechain" if obj.get("isSidechain") else "main")
            key = (path, str(agent))
            g = groups.setdefault(key, {"dispatch": None, "usage": {}})
            msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
            if obj.get("type") == "user" and g["dispatch"] is None:
                g["dispatch"] = _dispatch_of(_text_of(msg.get("content")))
            if obj.get("type") == "assistant" and isinstance(msg.get("usage"), dict):
                mid = (msg.get("id") or obj.get("uuid"), obj.get("requestId"))
                g["usage"][mid] = (msg.get("model") or "?", msg["usage"])  # last line of a message wins
    stages: Dict[str, Dict[str, Any]] = {}
    unattributed = 0
    for g in groups.values():
        if not g["usage"]:
            continue
        if not g["dispatch"]:
            unattributed += 1
            continue
        d_slug, number, name, rnd = g["dispatch"]
        if slug and d_slug != slug:
            continue
        label = f"{number}. {name}"
        entry = stages.setdefault(label, {"runs": 0, "models": {}, **{f: 0 for f in _FIELDS}})
        entry["runs"] += 1
        for model, usage in g["usage"].values():
            entry["models"][model] = entry["models"].get(model, 0) + 1
            for f in _FIELDS:
                value = usage.get(f)
                if isinstance(value, (int, float)):
                    entry[f] += int(value)
    ordered = dict(sorted(stages.items(), key=lambda kv: int(kv[0].split(".")[0])))
    out: Dict[str, Any] = {"ok": True, "projects_dir": projects_dir, "days": days, "transcripts": len(files),
                           "stages": ordered, "unattributed_sessions_or_agents": unattributed}
    if not ordered:
        out["note"] = ("No stage dispatch was found in the transcripts. The transcript format may differ "
                       "from what this report reads; Claude Code's /cost and the Console show totals.")
    else:
        out["note"] = ("Input tokens include cache reads and writes separately. Discovery runs in the main "
                       "conversation and is not counted here. Compare stages by output and input tokens "
                       "before moving one to a cheaper model.")
    return out
