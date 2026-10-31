"""Read-only git helpers. Nothing here changes the repository."""

from __future__ import annotations

import os
import subprocess
from typing import List, Optional, Tuple


class GitError(RuntimeError):
    pass


def _git(root: str, *args: str, check: bool = True) -> Tuple[int, bytes, bytes]:
    cmd = ["git", "-c", "core.quotepath=off", "--no-pager", *args]
    try:
        proc = subprocess.run(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:  # git not installed
        raise GitError("git is not installed or not on PATH") from exc
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.returncode, proc.stdout, proc.stderr


def text(root: str, *args: str, check: bool = True) -> str:
    return _git(root, *args, check=check)[1].decode("utf-8", "replace")


def toplevel(cwd: str) -> Optional[str]:
    code, out, _ = _git(cwd, "rev-parse", "--show-toplevel", check=False)
    if code != 0:
        return None
    return os.path.normpath(out.decode("utf-8", "replace").strip())


def head(root: str) -> Optional[str]:
    code, out, _ = _git(root, "rev-parse", "HEAD", check=False)
    return out.decode().strip() if code == 0 else None


def rev_parse(root: str, ref: str) -> Optional[str]:
    code, out, _ = _git(root, "rev-parse", "--verify", "--quiet", ref, check=False)
    value = out.decode().strip()
    return value if code == 0 and value else None


def branch_exists(root: str, name: str) -> bool:
    return bool(text(root, "branch", "--list", name, check=False).strip())


def in_worktree(root: str) -> bool:
    git_dir = text(root, "rev-parse", "--absolute-git-dir", check=False).strip()
    common = text(root, "rev-parse", "--git-common-dir", check=False).strip()
    if not git_dir or not common:
        return False
    if not os.path.isabs(common):
        common = os.path.join(root, common)
    return os.path.normcase(os.path.realpath(git_dir)) != os.path.normcase(os.path.realpath(common))


def status_porcelain(root: str) -> str:
    """The status list exactly as the change record contract defines it."""
    return text(root, "status", "--porcelain", "--untracked-files=all")


def diff_from(root: str, start_point: str) -> str:
    return text(root, "diff", "--no-color", "--no-ext-diff", start_point)


def status_entries(root: str, ignored: bool = False) -> List[Tuple[str, str, Optional[str]]]:
    """Parse `git status --porcelain=v1 -z`: (XY, path, original path for renames).

    With `ignored`, ignored files are listed too (`!!`), a wholly ignored folder as one
    entry ending in `/`."""
    args = ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
    if ignored:
        args.append("--ignored=matching")
    raw = _git(root, *args)[1]
    parts = raw.split(b"\0")
    entries: List[Tuple[str, str, Optional[str]]] = []
    i = 0
    while i < len(parts):
        item = parts[i]
        i += 1
        if not item:
            continue
        xy = item[:2].decode("ascii", "replace")
        path = item[3:].decode("utf-8", "replace")
        orig = None
        if xy[0] in "RC" or xy[1] in "RC":
            if i < len(parts):
                orig = parts[i].decode("utf-8", "replace")
                i += 1
        entries.append((xy, path, orig))
    return entries


def changed_paths(root: str, ignored: bool = False) -> List[str]:
    paths: List[str] = []
    for _, path, orig in status_entries(root, ignored):
        if path.endswith("/"):
            continue  # a wholly ignored folder: its files cannot be followed one by one
        paths.append(path)
        if orig:
            paths.append(orig)
    return paths


def diff_names(root: str, start_point: str) -> List[str]:
    out = text(root, "diff", "--name-only", start_point)
    return [line for line in out.splitlines() if line.strip()]


def unmerged_files(root: str) -> List[str]:
    out = text(root, "diff", "--name-only", "--diff-filter=U", check=False)
    return [line for line in out.splitlines() if line.strip()]


def show_file(root: str, rev: str, path: str) -> Optional[bytes]:
    code, out, _ = _git(root, "show", f"{rev}:{path}", check=False)
    return out if code == 0 else None


def log_oneline(root: str, rev_range: str) -> List[str]:
    out = text(root, "log", "--oneline", rev_range, check=False)
    return [line for line in out.splitlines() if line.strip()]


def untracked(root: str) -> List[str]:
    out = text(root, "ls-files", "--others", "--exclude-standard", check=False)
    return [line for line in out.splitlines() if line.strip()]


def is_ancestor(root: str, ancestor: str, descendant: str = "HEAD") -> bool:
    code, _, _ = _git(root, "merge-base", "--is-ancestor", ancestor, descendant, check=False)
    return code == 0
