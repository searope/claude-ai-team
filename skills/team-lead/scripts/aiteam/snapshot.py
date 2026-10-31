"""Per-stage snapshots: which files did a stage change, and were they its own?

Before an isolated stage is dispatched, the hash of every file git reports as
changed or new is recorded, together with every file under .ai-team/ and .claude/
(git ignores most of those, so a change record would never show them). Small
files are copied, so that a change outside the stage's area can be put back.

Files that ai_team.py writes itself (the ledger, the notes, the change record, the
scan report) are left out: the orchestrator may write them while a stage runs.
A file that cannot be read (locked, a folder, a path too long) is recorded as such
and never stops the pipeline.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from typing import Any, Dict, List, Optional

from . import gitio, model
from .guard import is_allowed
from .project import to_posix

COPY_LIMIT = 5 * 1024 * 1024
EXTRA_ROOTS = (".ai-team", ".claude", ".git/hooks", ".git/info")
EXTRA_FILES = (".git/config", ".git/HEAD")
EXTRA_SKIP = (".ai-team/snapshots", ".claude/worktrees", ".git/hooks/_sample")
LOCK_FILES = {"package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "packages.lock.json",
              "poetry.lock", "uv.lock", "Pipfile.lock", "Cargo.lock", "go.sum", "composer.lock", "Gemfile.lock"}
SETTINGS_LOCAL = ".claude/settings.local.json"
UNREADABLE = "<unreadable>"


def _long(path: str) -> str:
    """A path Windows accepts past 260 characters."""
    if os.name == "nt":
        full = os.path.abspath(path)
        if full.startswith("\\\\?\\"):
            return full
        if full.startswith("\\\\"):  # a UNC path: \\server\share -> \\?\UNC\server\share
            return "\\\\?\\UNC\\" + full[2:]
        return "\\\\?\\" + full
    return path


def _sha(path: str) -> Optional[str]:
    try:
        if os.path.isdir(_long(path)):
            return UNREADABLE
        digest = hashlib.sha256()
        with open(_long(path), "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except FileNotFoundError:
        return None
    except (OSError, MemoryError):
        return UNREADABLE


def _abs(root: str, rel: str) -> str:
    return os.path.join(root, *rel.rstrip("/").split("/"))


def owned_by_tool(slug: str) -> set:
    """Working files that ai_team.py writes itself while a stage may be running.

    The active dispatch is not among them: a stage that rewrites its own allowlist
    must be caught.
    """
    return {model.ledger_json_path(slug), model.ledger_md_path(slug), model.notes_path(slug),
            model.change_record_path(slug), model.scan_report_path(slug)}


def _skip(rel: str, slug: str) -> bool:
    if rel in owned_by_tool(slug):
        return True
    if any(rel.startswith(skip + "/") for skip in EXTRA_SKIP):
        return True
    if rel.startswith(f"{model.SCRATCH_DIR}/{slug}-scan-") and rel.endswith(".txt"):
        return True
    return rel.endswith(".tmp") and rel.startswith(f"{model.STATE_DIR}/")


def _extra_files(root: str) -> List[str]:
    found: List[str] = []
    for top in EXTRA_ROOTS:
        base = _abs(root, top)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            rel_dir = to_posix(os.path.relpath(dirpath, root))
            dirnames[:] = [d for d in dirnames
                           if not any(f"{rel_dir}/{d}".startswith(skip) for skip in EXTRA_SKIP)]
            for name in filenames:
                found.append(f"{rel_dir}/{name}")
    for rel in EXTRA_FILES:
        if os.path.isfile(_abs(root, rel)):
            found.append(rel)
    return found


def _state(root: str, slug: str) -> Dict[str, Optional[str]]:
    """Hash of every file that could carry a stage's change: changed, new, git-ignored
    (as single files; a whole ignored folder such as bin/ is one entry and not hashed),
    and the working folders git never sees."""
    paths = {p.rstrip("/") for p in gitio.changed_paths(root, ignored=True)} | set(_extra_files(root))
    return {p: _sha(_abs(root, p)) for p in sorted(paths) if not _skip(p, slug)}


def folder_for(slug: str, seq: int, number: int) -> str:
    return f"{model.snapshot_dir(slug)}/{seq:04d}-s{number}"


def take(root: str, slug: str, number: int, seq: int) -> str:
    folder_rel = folder_for(slug, seq, number)
    folder = _abs(root, folder_rel)
    if os.path.isdir(_long(folder)):
        shutil.rmtree(_long(folder), ignore_errors=True)
    os.makedirs(_long(os.path.join(folder, "f")), exist_ok=True)
    state = _state(root, slug)
    copies: Dict[str, str] = {}
    for index, (rel, sha) in enumerate(state.items()):
        if sha in (None, UNREADABLE):
            continue
        src = _abs(root, rel)
        try:
            if os.path.getsize(_long(src)) > COPY_LIMIT:
                continue
            shutil.copyfile(_long(src), _long(os.path.join(folder, "f", str(index))))
        except OSError:
            continue
        copies[rel] = f"f/{index}"
    manifest = {"slug": slug, "stage": number, "seq": seq, "head": gitio.head(root), "state": state,
                "copies": copies}
    with open(_long(os.path.join(folder, "manifest.json")), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    return folder_rel


def load(root: str, folder_rel: str) -> Optional[Dict[str, Any]]:
    try:
        with open(_long(os.path.join(_abs(root, folder_rel), "manifest.json")), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def changes(root: str, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    before: Dict[str, Optional[str]] = manifest["state"]
    after = _state(root, manifest.get("slug", ""))
    out: List[Dict[str, Any]] = []
    for rel in sorted(set(before) | set(after)):
        if rel not in before:
            # clean (or absent) before the stage: compare with the commit it started from
            a_sha = after.get(rel)
            head_sha = None
            if manifest.get("head"):
                blob = gitio.show_file(root, manifest["head"], rel)
                head_sha = hashlib.sha256(blob).hexdigest() if blob is not None else None
            if a_sha == head_sha:
                continue
            kind = "deleted" if a_sha is None else ("added" if head_sha is None else "modified")
        elif rel not in after:
            # listed before, gone from the list now: put back to HEAD, or deleted
            if before[rel] is None:
                kind = "added"
            else:
                kind = "modified" if os.path.exists(_long(_abs(root, rel))) else "deleted"
        else:
            b, a = before[rel], after[rel]
            if b == a:
                continue
            kind = "deleted" if a is None else ("added" if b is None else "modified")
        out.append({"path": rel, "change": kind})
    return out


def violations(root: str, manifest: Dict[str, Any], allow: Dict[str, List[str]], project: Any,
               slug: str) -> Dict[str, List[Dict[str, Any]]]:
    """Changes outside the stage's area, and changes to report without blaming the stage."""
    found: List[Dict[str, Any]] = []
    notes: List[Dict[str, Any]] = []
    build_stage = int(manifest.get("stage", 0)) in (5, 6, 7)
    for item in changes(root, manifest):
        rel = item["path"]
        if is_allowed(allow, rel):
            continue
        if build_stage and rel.rsplit("/", 1)[-1] in LOCK_FILES and item["change"] != "deleted":
            continue  # what a package manager changes when a dependency is installed is its own work
        if rel == SETTINGS_LOCAL:
            notes.append(item)  # an "always allow" answer of the user lands here
            continue
        area = project.area_of(rel, slug)
        if area is None and rel.startswith((".ai-team/", ".claude/")):
            area = "working file"
        item["area"] = area or "no area"
        found.append(item)
    return {"violations": found, "notes": notes}


def revert(root: str, folder_rel: str, paths: List[str]) -> Dict[str, List[str]]:
    manifest = load(root, folder_rel)
    done: List[str] = []
    failed: List[str] = []
    if manifest is None:
        return {"reverted": done, "failed": list(paths)}
    folder = _abs(root, folder_rel)
    for rel in paths:
        target = _abs(root, rel)
        try:
            if rel in manifest["state"]:
                if manifest["state"][rel] is None:
                    if os.path.isfile(_long(target)):
                        os.remove(_long(target))
                elif rel in manifest["copies"]:
                    os.makedirs(_long(os.path.dirname(target)), exist_ok=True)
                    shutil.copyfile(_long(os.path.join(folder, *manifest["copies"][rel].split("/"))), _long(target))
                else:
                    failed.append(rel)
                    continue
            else:
                blob = gitio.show_file(root, manifest.get("head") or "HEAD", rel)
                if blob is None:
                    if os.path.isfile(_long(target)):
                        os.remove(_long(target))
                else:
                    os.makedirs(_long(os.path.dirname(target)), exist_ok=True)
                    with open(_long(target), "wb") as fh:
                        fh.write(blob)
            done.append(rel)
        except OSError:
            failed.append(rel)
    return {"reverted": done, "failed": failed}
