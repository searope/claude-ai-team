"""Write allowlists of dispatched stages, and the decisions of the PreToolUse guard.

The guard is a seat belt, not a sandbox: an agent is told not to work around it,
and the per-stage snapshot (snapshot.py) finds what it changed anyway. Within that
limit it is strict by default:

- the file tools write only the dispatched stage's allowlist;
- a shell command may write only into a temp folder or that allowlist, through
  any writer the guard can see (redirection, cp/mv/tee/curl -o, Out-File, ...);
- git and gh run only in their known read-only forms; everything else is denied,
  aliases, variables and `-c` tricks included;
- files that hold secrets are not read, printed, copied, sourced or searched;
- shells fed from a pipe or a here-string, `eval`, and in-place editors are denied.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import tempfile
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import model
from .project import PathPattern, norm_key, to_posix

ACTIVE_MAX_AGE = 72 * 3600
FORBIDDEN_PREFIXES = (".git/", ".claude/", ".ai-team/state/", ".ai-team/snapshots/")

# --- allowlists ----------------------------------------------------------------------------------


def _dedupe(items: Iterable[str]) -> List[str]:
    seen, out = set(), []
    for item in items:
        key = norm_key(item)
        if item and key not in seen:
            seen.add(key)
            out.append(to_posix(item).strip("/"))
    return out


def forbidden_path(rel: str) -> bool:
    """A project path no stage may ever write, whatever an ADR says."""
    rel = to_posix(rel).strip()
    if not rel or os.path.isabs(rel) or re.match(r"^[A-Za-z]:", rel) or rel.startswith(("//", "\\\\")):
        return True
    parts = rel.split("/")
    if ".." in parts:
        return True
    low = rel.lower() + "/"
    if low == ".git/" or low.startswith(FORBIDDEN_PREFIXES) or rel == model.PROJECT_FILE:
        return True
    return False


def stage_allowlist(ctx: Any, number: int) -> Dict[str, List[str]]:
    """What the stage may write in the project with its file tools and its shell."""
    slug, proj, led = ctx.slug, ctx.project, ctx.led
    exact: List[str] = []
    dirs: List[str] = []
    patterns: List[str] = []
    if number == 2:
        exact += [model.artifact_path("Copy file", slug), model.artifact_path("Copy audit", slug)]
    elif number == 3:
        exact.append(model.artifact_path("UI spec", slug))
        dirs.append(model.mockup_dir(slug))
    elif number == 4:
        exact.append(model.artifact_path("ADR", slug))
    elif number == 5:
        exact += ctx.radius_files("Source")
    elif number == 6:
        exact += ctx.radius_files("Infra")
    elif number == 7:
        patterns += [p.token for p in proj.tests]
    merge = led.get("merge") or {}
    for item in merge.get("files", []):
        if item.get("owner") == number:
            exact.append(item["path"])
    handoff = model.handoff_path(slug, number)
    if handoff and not model.is_review(number):
        exact.append(handoff)
    deny_read: List[str] = []
    if number == 9:  # the second review stays independent of the first
        deny_read.append(model.handoff_path(slug, model.REVIEW_STAGE))
    exact = [e for e in exact if not forbidden_path(e)]
    return {"exact": _dedupe(exact), "dirs": _dedupe(dirs), "patterns": patterns, "deny_read": deny_read}


def is_allowed(allow: Dict[str, List[str]], rel: str) -> bool:
    rel = to_posix(rel).strip("/")
    if forbidden_path(rel):
        return False
    key = norm_key(rel)
    if key in {norm_key(e) for e in allow.get("exact", [])}:
        return True
    for d in allow.get("dirs", []):
        if key.startswith(norm_key(d).rstrip("/") + "/"):
            return True
    return any(PathPattern.compile(tok).matches(rel) for tok in allow.get("patterns", []))


def write_active(root: str, payload: Dict[str, Any]) -> None:
    path = os.path.join(root, *model.ACTIVE_DISPATCH.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=2)


def read_active(root: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(root, *model.ACTIVE_DISPATCH.split("/"))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if time.time() - float(data.get("created", 0)) > ACTIVE_MAX_AGE:
        return None
    return data


def clear_active(root: str) -> None:
    path = os.path.join(root, *model.ACTIVE_DISPATCH.split("/"))
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


# --- path helpers --------------------------------------------------------------------------------


def _norm_abs(path: str) -> str:
    try:
        return os.path.normcase(os.path.realpath(path))
    except OSError:
        return os.path.normcase(os.path.abspath(path))


def inside(path: str, folder: str) -> bool:
    p, f = _norm_abs(path), _norm_abs(folder)
    return p == f or p.startswith(f.rstrip(os.sep) + os.sep)


def find_root(cwd: str) -> str:
    """The feature folder: the nearest folder up from cwd that holds .git or an active dispatch.

    A worktree's folder holds a .git file, so the search never climbs out of it into
    the main folder.
    """
    cur = os.path.abspath(cwd)
    while True:
        if os.path.isfile(os.path.join(cur, *model.ACTIVE_DISPATCH.split("/"))) or \
                os.path.exists(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(cwd)
        cur = parent


def temp_dirs(event: Dict[str, Any]) -> List[str]:
    dirs = [tempfile.gettempdir()]
    for var in ("TMP", "TEMP", "TMPDIR"):
        if os.environ.get(var):
            dirs.append(os.environ[var])
    if event.get("scratchpad_dir"):
        dirs.append(event["scratchpad_dir"])
    if os.name != "nt":
        dirs.append("/tmp")
    return dirs


# --- secrets -------------------------------------------------------------------------------------

_SECRET_NAME = (r"(?:\.env(?:\.[\w.-]+)?|[\w.-]*\.(?:pem|key|pfx|p12|kdbx|jks|keystore)|"
                r"id_(?:rsa|dsa|ecdsa|ed25519)|secrets?\.(?:json|ya?ml|toml)|[\w.-]*\.secrets?\.[\w]+|"
                r"credentials(?:\.json)?|\.npmrc|\.pypirc|\.netrc|\.git-credentials|"
                r"appsettings\.(?:development|local|secrets)\.json|local\.settings\.json|"
                r"terraform\.tfvars|\.htpasswd)")
_SECRET = re.compile(rf"(?:^|/){_SECRET_NAME}$", re.IGNORECASE)
_NOT_SECRET = re.compile(r"\.env\.(?:example|sample|template|dist|defaults|schema)$|(?:^|/)public\.pem$",
                         re.IGNORECASE)
_SECRET_IN_TEXT = re.compile(rf"(?<![\w.-]){_SECRET_NAME}(?![\w-])", re.IGNORECASE)
_SECRET_GLOB = re.compile(r"\.env\b|\.pem\b|\.key\b|\.pfx\b|\.p12\b|id_rsa|id_ed25519|secrets?\.|"
                          r"credentials|\.npmrc|\.pypirc|\.netrc", re.IGNORECASE)


def is_secret_path(path: str) -> bool:
    p = to_posix(path).rstrip("/")
    return bool(_SECRET.search(p)) and not _NOT_SECRET.search(p)


def secret_names_in(text: str) -> List[str]:
    found = [m.group(0) for m in _SECRET_IN_TEXT.finditer(text)]
    return [f for f in found if not _NOT_SECRET.search(f)]


_READERS = {"cat", "type", "more", "less", "head", "tail", "nl", "bat", "gc", "get-content",
            "select-string", "sls", "findstr", "grep", "rg", "ag", "ack", "awk", "sed", "strings", "xxd",
            "od", "hexdump", "base64", "cp", "copy", "copy-item", "cpi", "mv", "move", "move-item", "mi",
            "scp", "rsync", "certutil", "openssl", "sort", "uniq", "cut", "jq", "yq", "curl", "wget",
            "invoke-webrequest", "iwr", "tar", "zip", "7z", "compress-archive", "source", ".", "python",
            "python3", "py", "node", "ruby", "perl", "php", "dotnet", "pwsh", "powershell", "bash", "sh",
            "zsh", "cmd", "git", "gh", "xargs", "eval", "tee", "diff", "cmp", "import-csv", "ipcsv",
            "get-item", "gi", "resolve-path", "export-csv", "out-file", "set-content", "add-content",
            "dd", "install", "ln", "sqlite3", "psql", "mysql", "docker", "kubectl", "az", "aws", "gcloud",
            "env", "printenv"}

# --- shell parsing -------------------------------------------------------------------------------
#
# Commands are read the way the shell would split them: heredoc bodies and
# PowerShell here-strings are dropped (they are data), each line is tokenized with
# quotes respected, and `;`, `|`, `||`, `&&`, `&` end a command. A script handed to
# `bash -c`, `pwsh -Command` or `cmd /c` is read as a command of its own.

_SEPARATORS = {";", "|", "||", "&&", "&", "(", ")", ";;", "|&"}
_HERESTRING = re.compile(r"@(['\"])[ \t]*\r?\n.*?\r?\n\1@", re.DOTALL)
_HEREDOC_MARK = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_WRAPPERS = {"env", "time", "nice", "nohup", "command", "exec", "sudo", "doas", "busybox", "timeout",
             "stdbuf", "ionice", "caffeinate", "uv", "uvx", "pipenv", "poetry", "npx", "pnpm", "bunx", "yarn"}
_WRAPPER_WITH_ARG = {"timeout", "nice", "ionice", "stdbuf"}
_SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish", "pwsh", "powershell", "cmd"}
_UNRESOLVABLE = re.compile(r"[$`{}*?\[]")


def _strip_bodies(command: str) -> str:
    command = _HERESTRING.sub("''", command)
    kept: List[str] = []
    waiting: List[str] = []
    for line in command.split("\n"):
        if waiting:
            if line.strip() == waiting[0]:
                waiting.pop(0)
            continue
        kept.append(line)
        waiting = [m.group(2) for m in _HEREDOC_MARK.finditer(line)]
    return "\n".join(kept)


def _unquote(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "'\"":
        return token[1:-1]
    return token


def _ps_normalize(line: str) -> str:
    line = line.replace("`", "")                          # backtick escapes hide nothing from the guard
    line = re.sub(r"(-[A-Za-z]+):(?=\S)", r"\1 ", line)   # -FilePath:x  ->  -FilePath x
    return line


def _lex(line: str, shell: str) -> List[str]:
    if shell != "Bash":
        line = _ps_normalize(line)
    elif os.name == "nt":
        # Git Bash commands on Windows carry Windows paths (C:\Users\...), whose
        # backslashes POSIX shlex would eat as escapes. A backslash between two
        # path characters is a separator here, not an escape: spell it as one.
        line = re.sub(r"(?<=[\w.:~])\\(?=[\w.\-~])", "/", line)
    try:
        lexer = shlex.shlex(line, posix=(shell == "Bash"), punctuation_chars="<>&|;()")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        tokens = line.split()
    return tokens if shell == "Bash" else [_unquote(t) for t in tokens]


def _segments(command: str, shell: str) -> List[List[str]]:
    segments: List[List[str]] = []
    for line in _strip_bodies(command).splitlines():
        current: List[str] = []
        for tok in _lex(line, shell):
            if tok in _SEPARATORS:
                if current:
                    segments.append(current)
                current = []
            else:
                current.append(tok)
        if current:
            segments.append(current)
    return segments


def _cmd_name(token: str) -> str:
    name = to_posix(token).rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _unwrap(segment: List[str]) -> Tuple[List[str], List[str]]:
    """Strip env assignments and wrappers (env, time, xargs, find -exec): (assignments, command)."""
    assigns: List[str] = []
    seg = list(segment)
    while seg:
        name = _cmd_name(seg[0])
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg[0]):
            assigns.append(seg.pop(0))
            continue
        if name in _WRAPPERS:
            seg.pop(0)
            if name in _WRAPPER_WITH_ARG and seg:
                seg.pop(0)
            elif name == "env":
                while seg and (seg[0].startswith("-") or "=" in seg[0]):
                    seg.pop(0)
            elif name in ("uv", "uvx", "pipenv", "poetry", "npx", "pnpm", "bunx", "yarn"):
                if seg and seg[0] in ("run", "exec", "x"):
                    seg.pop(0)
                while seg and seg[0].startswith("-"):
                    seg.pop(0)
            continue
        if name == "xargs":
            seg.pop(0)
            while seg and seg[0].startswith("-"):
                seg.pop(0)
            seg.append("$XARGS_INPUT")  # whatever the pipe feeds in
            continue
        if name == "find" and "-exec" in seg:
            seg = seg[seg.index("-exec") + 1:]
            continue
        break
    return assigns, seg


def _nested(segment: List[str]) -> List[Tuple[str, str]]:
    """Scripts handed to another shell in this command: (shell, script)."""
    found = []
    for i, tok in enumerate(segment):
        name = _cmd_name(tok)
        rest = segment[i + 1:]
        if name in ("bash", "sh", "zsh", "dash", "ksh"):
            for j, arg in enumerate(rest):
                if arg == "-c" or (arg.startswith("-") and not arg.startswith("--") and arg.endswith("c")):
                    if j + 1 < len(rest):
                        found.append(("Bash", rest[j + 1]))
                    break
        elif name in ("pwsh", "powershell"):
            for j, arg in enumerate(rest):
                if arg.lower() in ("-command", "-c", "-commandwithargs", "-cwa"):
                    found.append(("PowerShell", " ".join(rest[j + 1:])))
                    break
        elif name == "cmd":
            for j, arg in enumerate(rest):
                if arg.lower() in ("/c", "/k"):
                    found.append(("PowerShell", " ".join(rest[j + 1:])))
                    break
    return found


def _unseen_script(segment: List[str], command_text: str) -> Optional[str]:
    """A shell that runs text the guard cannot read: eval, `| sh`, `sh <<< ...`, encoded commands."""
    _, seg = _unwrap(segment)
    if not seg:
        return None
    name = _cmd_name(seg[0])
    if name == "eval":
        return "eval"
    if name in _SHELLS:
        lowered = [a.lower() for a in seg[1:]]
        if any(a in ("-encodedcommand", "-e", "-ec", "-enc") for a in lowered):
            return f"{name} -EncodedCommand"
        inline = any(a in ("-c", "-command", "/c", "/k", "-commandwithargs", "-cwa") for a in lowered)
        args = [a for a in seg[1:] if not a.startswith(("-", "/"))]
        if not inline and not args:
            return f"{name} reading a script from its input"
        if "<<<" in command_text and not inline:
            return f"{name} <<<"
    return None


# --- git and gh: allowlists of read-only forms -----------------------------------------------------

_GIT_GLOBAL_WITH_ARG = {"-C", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix"}
_GIT_READ_ONLY = {
    "status", "log", "diff", "show", "rev-parse", "rev-list", "merge-base", "ls-files", "ls-tree", "blame",
    "grep", "describe", "name-rev", "shortlog", "check-ignore", "check-attr", "var", "version", "help",
    "count-objects", "for-each-ref", "diff-tree", "diff-index", "diff-files", "whatchanged", "cat-file",
    "show-ref", "branch", "tag", "stash", "worktree", "remote", "config", "notes", "reflog", "lfs",
    "submodule", "symbolic-ref", "annotate", "range-diff", "cherry", "show-branch", "ls-remote",
    "verify-commit", "verify-tag",
}
_GIT_WRITE_FLAGS = {"--output", "-o", "--ext-diff", "--edit", "-e"}


def _git_read_only(sub: str, args: List[str]) -> bool:
    flags = [a for a in args if a.startswith("-")]
    positional = [a for a in args if not a.startswith("-")]
    if sub not in _GIT_READ_ONLY:
        return False
    if any(f.split("=", 1)[0] in _GIT_WRITE_FLAGS for f in flags):
        return False
    if sub == "stash":
        return bool(positional) and positional[0] in ("list", "show")
    if sub == "worktree":
        return bool(positional) and positional[0] == "list"
    if sub == "branch":
        writes = {"-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy", "-f", "--force",
                  "-u", "--set-upstream-to", "--unset-upstream", "--edit-description", "--track",
                  "--no-track"}
        if any(f.split("=", 1)[0] in writes for f in flags):
            return False
        listing = {"--list", "-l", "-a", "--all", "-r", "--remotes", "--show-current", "-v", "-vv",
                   "--contains", "--merged", "--no-merged", "--points-at", "--format", "--sort"}
        return not positional or any(f.split("=", 1)[0] in listing for f in flags)
    if sub == "tag":
        return not positional or any(f in ("-l", "--list") for f in flags)
    if sub == "config":
        if any(f.split("=", 1)[0] in ("--get", "--get-all", "--get-regexp", "--list", "-l") for f in flags):
            return True
        writes = {"--unset", "--unset-all", "--add", "--replace-all", "--edit", "-e", "--rename-section",
                  "--remove-section"}
        return len(positional) == 1 and not any(f in writes for f in flags)
    if sub == "remote":
        return not positional or positional[0] in ("show", "get-url")
    if sub == "notes":
        return not positional or positional[0] in ("list", "show")
    if sub == "reflog":
        return not positional or positional[0] == "show"
    if sub == "lfs":
        return bool(positional) and positional[0] in ("ls-files", "status", "env", "version")
    if sub == "submodule":
        return not positional or positional[0] in ("status", "summary")
    if sub == "symbolic-ref":
        return "--short" in flags or len(positional) <= 1
    if sub == "cat-file":
        return "-w" not in flags
    return True


def _git_problem(segment: List[str]) -> Optional[str]:
    """Why this git invocation is not a known read-only form, or None."""
    assigns, seg = _unwrap(segment)
    for a in assigns:
        key = a.split("=", 1)[0].upper()
        if key.startswith("GIT_") and key not in ("GIT_PAGER", "GIT_TERMINAL_PROMPT", "GIT_LFS_SKIP_SMUDGE"):
            return f"git with {key} set"
    for idx, tok in enumerate(seg):
        if _cmd_name(tok) != "git":
            continue
        rest = seg[idx + 1:]
        j = 0
        while j < len(rest) and rest[j].startswith("-"):
            opt = rest[j].split("=", 1)[0]
            if opt == "-c" or opt.startswith("--config-env"):
                return "git -c"
            j += 2 if (opt in _GIT_GLOBAL_WITH_ARG and "=" not in rest[j]) else 1
        rest = rest[j:]
        if not rest:
            return "git with no subcommand the guard can read"
        sub = rest[0].lower()
        if _UNRESOLVABLE.search(sub):
            return "git with a subcommand the guard cannot read"
        if any(_UNRESOLVABLE.search(a) for a in rest[1:] if a.startswith("-")):
            return f"git {sub} with options the guard cannot read"
        if not _git_read_only(sub, rest[1:]):
            return f"git {sub}"
        return None
    return None


_GH_READ_ONLY = {
    "pr": {"view", "list", "diff", "status", "checks"},
    "issue": {"view", "list", "status"},
    "repo": {"view", "list"},
    "run": {"view", "list", "watch"},
    "release": {"view", "list"},
    "workflow": {"view", "list"},
    "label": {"list"},
    "search": {"repos", "issues", "prs", "commits", "code"},
    "auth": {"status"},
    "gist": {"view", "list"},
    "cache": {"list"},
    "variable": {"list"},
    "secret": {"list"},
}
_GH_GLOBAL_WITH_ARG = {"-R", "--repo", "--hostname"}


def _gh_api_writes(args: List[str]) -> bool:
    k = 0
    while k < len(args):
        a = args[k]
        low = a.lower()
        if low in ("-x", "--method"):
            if k + 1 >= len(args) or args[k + 1].upper() != "GET":
                return True
            k += 2
            continue
        if low.startswith("--method="):
            if low.split("=", 1)[1].upper() != "GET":
                return True
        elif low.startswith("-x") and len(low) > 2:
            if low[2:].upper() != "GET":
                return True
        elif low in ("-f", "--field", "--raw-field", "--input") or low.startswith(("--field=", "--raw-field=",
                                                                                     "--input=", "-f=")):
            return True
        elif len(a) == 2 and a[0] == "-" and a[1] == "F":
            return True
        k += 1
    return False


def _gh_problem(segment: List[str]) -> Optional[str]:
    _, seg = _unwrap(segment)
    for idx, tok in enumerate(seg):
        if _cmd_name(tok) != "gh":
            continue
        rest = seg[idx + 1:]
        j = 0
        while j < len(rest) and rest[j].startswith("-"):
            opt = rest[j].split("=", 1)[0]
            j += 2 if (opt in _GH_GLOBAL_WITH_ARG and "=" not in rest[j]) else 1
        rest = rest[j:]
        if not rest or _UNRESOLVABLE.search(rest[0]):
            return "gh with a command the guard cannot read"
        sub = rest[0].lower()
        if sub in ("version", "help"):
            return None
        if sub == "api":
            return "gh api (writing)" if _gh_api_writes(rest[1:]) else None
        actions = _GH_READ_ONLY.get(sub)
        words = [w for w in rest[1:] if not w.startswith("-")]
        if actions and words and not _UNRESOLVABLE.search(words[0]) and words[0].lower() in actions:
            return None
        return f"gh {sub}" + (f" {words[0]}" if words else "")
    return None


def git_mutation(command: str, shell: str = "Bash", depth: int = 0) -> Optional[str]:
    """A git or gh invocation that is not a known read-only form, if the command runs one."""
    for segment in _segments(command, shell):
        for check in (_git_problem, _gh_problem):
            problem = check(segment)
            if problem:
                return problem
        if depth < 3:
            for inner_shell, script in _nested(segment):
                found = git_mutation(script, inner_shell, depth + 1)
                if found:
                    return found
    return None


# --- secrets in commands ---------------------------------------------------------------------------

_FILE_ARG_READERS = {"cat", "type", "gc", "get-content", "source", ".", "less", "more", "head", "tail"}


def secret_read(command: str, shell: str = "Bash", depth: int = 0) -> Optional[str]:
    text = _strip_bodies(command)
    if re.search(r"\buser-secrets\s+list\b", text, re.IGNORECASE):
        return "dotnet user-secrets list"
    if re.search(r"(?:^|[\s;|&(])(?:env|printenv)\s*(?:$|[;|&)])", text, re.IGNORECASE | re.MULTILINE) or \
            re.search(r"\b(?:gci|dir|ls|get-childitem)\s+env:", text, re.IGNORECASE):
        return "the process environment"
    if re.search(r"\[(?:System\.)?IO\.File\]::Read\w*\(", text, re.IGNORECASE) and secret_names_in(text):
        return secret_names_in(text)[0]
    for segment in _segments(command, shell):
        _, seg = _unwrap(segment)
        if not seg:
            continue
        names = {_cmd_name(t) for t in seg}
        if names & _READERS:
            literal = [t for t in seg if is_secret_path(t.strip("<>\"'").split(":")[-1])]
            if literal:
                return literal[0]
            hits = secret_names_in(" ".join(seg))
            if hits:
                return hits[0]
            for t in seg[1:]:
                bare = t.strip("\"'")
                if bare.startswith(".") and _UNRESOLVABLE.search(bare):
                    return f"{bare} (a hidden-file pattern the guard cannot resolve)"
                if re.match(r"^\$\{?\w+\}?$", bare) and _cmd_name(seg[0]) in _FILE_ARG_READERS:
                    return f"{bare} (a file name the guard cannot resolve)"
        if depth < 3:
            for inner_shell, script in _nested(segment):
                found = secret_read(script, inner_shell, depth + 1)
                if found:
                    return found
    for m in re.finditer(r"<\s*([^\s<>|;&]+)", text):
        if is_secret_path(m.group(1).strip("\"'")):
            return m.group(1)
    return None


# --- writes from the shell -------------------------------------------------------------------------

_REDIRECT_OPS = {">", ">>", "&>", "&>>", ">|", "*>", "*>>", "2>", "2>>", "1>", "1>>"}
_PS_PATH_PARAMS = {"-path", "-filepath", "-literalpath", "-destination", "-destinationpath", "-outfile",
                   "-pspath"}
_PS_NO_VALUE = {"-force", "-recurse", "-append", "-nonewline", "-passthru", "-whatif", "-confirm", "-raw",
                "-wait", "-notypeinformation", "-literal", "-usebasicparsing", "-skiphttperrorcheck"}
_PS_WRITERS = {"out-file", "set-content", "sc", "add-content", "ac", "tee-object", "tee", "new-item", "ni",
               "copy-item", "cpi", "copy", "cp", "move-item", "mi", "move", "mv", "remove-item", "ri", "rm",
               "del", "erase", "rd", "rmdir", "rename-item", "rni", "ren", "export-csv", "epcsv",
               "export-clixml", "invoke-webrequest", "iwr", "curl", "wget", "start-bitstransfer",
               "expand-archive", "compress-archive", "set-itemproperty", "clear-content", "clc",
               "invoke-restmethod", "irm"}
_UNIX_WRITERS = {"cp", "mv", "install", "ln", "rm", "rmdir", "truncate", "touch", "dd", "tar", "unzip",
                 "curl", "wget", "tee", "rsync", "scp", "shred", "unlink", "7z", "zip", "gzip", "gunzip",
                 "bunzip2", "xz", "patch"}
_DEVNULL = {"/dev/null", "/dev/stdout", "/dev/stderr", "nul", "$null", "con", "nul:", "/dev/tty"}
_DOTNET_WRITE = re.compile(r"\[(?:System\.)?IO\.(?:File|Directory)\]::(?:Write|Append|Create|Copy|Move|"
                           r"Delete|Replace|Set|Open)\w*\(", re.IGNORECASE)
_CWD = "<cwd>"


def _ps_param_values(rest: List[str], wanted: set) -> Tuple[List[str], List[str]]:
    """Values of the wanted PowerShell parameters, and the positional arguments."""
    values, positional = [], []
    j = 0
    while j < len(rest):
        t = rest[j]
        low = t.lower()
        if low.startswith("-") and not re.match(r"^-\d", low):
            if low in wanted and j + 1 < len(rest):
                values.append(rest[j + 1])
                j += 2
            elif low in _PS_NO_VALUE:
                j += 1
            else:
                j += 2  # a parameter with a value the guard does not use
            continue
        positional.append(t)
        j += 1
    return values, positional


def _unix_targets(name: str, rest: List[str]) -> List[str]:
    positional = [a for a in rest if not a.startswith("-") or a == "-"]
    if name in ("cp", "mv", "install", "ln", "rsync", "scp", "patch"):
        if name == "patch":
            return [_CWD]
        if name == "install" and "-d" in rest:
            return positional
        return positional[-1:] if len(positional) >= 2 else []
    if name in ("rm", "rmdir", "shred", "unlink", "gzip", "gunzip", "bunzip2", "xz", "touch"):
        return positional
    if name == "truncate":
        return [p for p in positional if not re.match(r"^\d", p)]
    if name == "dd":
        return [a[3:] for a in rest if a.startswith("of=")]
    if name == "zip":
        return positional[:1]
    if name in ("tar", "unzip", "7z"):
        if name == "tar" and not any(re.match(r"^-?[a-zA-Z]*x", a) or a == "--extract" for a in rest[:2]):
            if any(re.match(r"^-?[a-zA-Z]*c", a) or a == "--create" for a in rest[:2]):
                for k, a in enumerate(rest):
                    if a in ("-f", "--file") and k + 1 < len(rest):
                        return [rest[k + 1]]
                    if re.match(r"^-[a-zA-Z]*f$", a) and k + 1 < len(rest):
                        return [rest[k + 1]]
            return []
        for key in ("-C", "-d", "--directory"):
            if key in rest and rest.index(key) + 1 < len(rest):
                return [rest[rest.index(key) + 1]]
        for a in rest:
            if a.startswith("--directory="):
                return [a.split("=", 1)[1]]
            if name == "7z" and a.startswith("-o") and len(a) > 2:
                return [a[2:]]
        return [_CWD]
    if name in ("curl", "wget"):
        out = []
        for k, a in enumerate(rest):
            if a in ("-o", "--output", "--output-document", "-P", "--directory-prefix"):
                if k + 1 < len(rest):
                    out.append(rest[k + 1])
            elif a in ("-O", "--remote-name", "--remote-name-all"):
                out.append(_CWD)
            elif a.startswith(("-o", "--output=", "--output-document=", "-P")) and len(a) > 2:
                out.append(a.split("=", 1)[-1] if "=" in a else a[2:])
        if name == "wget" and not out and not any(a in ("--spider", "-S", "--server-response") for a in rest):
            out.append(_CWD)
        return out
    if name == "tee":
        return positional
    return []


def write_targets(command: str, shell: str = "Bash", depth: int = 0) -> List[str]:
    """Files or folders a shell command writes, as far as the guard can tell (best-effort)."""
    targets: List[str] = []
    for segment in _segments(command, shell):
        for i, tok in enumerate(segment):
            if tok in _REDIRECT_OPS and i + 1 < len(segment):
                target = _unquote(segment[i + 1])
                if target and not target.startswith("&"):
                    targets.append(target)
        _, seg = _unwrap(segment)
        if not seg:
            continue
        name = _cmd_name(seg[0])
        rest = seg[1:]
        ps_style = shell != "Bash" or (name in _PS_WRITERS and name not in _UNIX_WRITERS)
        if ps_style and name in _PS_WRITERS:
            values, positional = _ps_param_values(rest, _PS_PATH_PARAMS)
            if name in ("copy-item", "cpi", "copy", "cp", "move-item", "mi", "move", "mv", "rename-item", "rni",
                        "ren"):
                targets += values or positional[-1:]
            elif name in ("invoke-webrequest", "iwr", "curl", "wget", "invoke-restmethod", "irm",
                          "start-bitstransfer", "expand-archive", "compress-archive"):
                targets += values
            elif name in ("remove-item", "ri", "rm", "del", "erase", "rd", "rmdir"):
                targets += values or positional
            else:
                targets += values or positional[:1]
        elif name in _UNIX_WRITERS:
            targets += _unix_targets(name, rest)
        if depth < 3:
            for inner_shell, script in _nested(segment):
                targets += write_targets(script, inner_shell, depth + 1)
    return [t for t in targets if t]


_FORMATTERS = {"black", "isort", "autopep8", "yapf"}


def in_place_editor(command: str, shell: str = "Bash") -> bool:
    for segment in _segments(command, shell):
        _, seg = _unwrap(segment)
        if not seg:
            continue
        name = _cmd_name(seg[0])
        rest = seg[1:]
        if name in ("sed", "perl", "ruby", "gsed") and any(
                re.match(r"^-(?:[a-zA-Z]*i|-in-place)", t) for t in rest if t.startswith("-")):
            return True
        if name in ("prettier", "eslint", "ruff", "dotnet") and ("--write" in rest or "--fix" in rest):
            return True
        if name == "dotnet" and rest[:1] == ["format"] and "--verify-no-changes" not in rest:
            return True
        if name == "ruff" and rest[:1] == ["format"] and "--check" not in rest and "--diff" not in rest:
            return True
        if name in _FORMATTERS and "--check" not in rest and "--diff" not in rest:
            return True
    return False


_TEMP_VARS = re.compile(r"^(?:\$\{?(?:TMPDIR|TMP|TEMP)\}?|\$env:(?:TMP|TEMP|TMPDIR)|%(?:TMP|TEMP)%)(?:[/\\]|$)",
                        re.IGNORECASE)


def _resolve_target(target: str, cwd: str) -> Tuple[Optional[str], bool]:
    """(absolute path, or None to ignore; True when it is a temp folder the guard trusts)."""
    t = target.strip()
    if not t or t.lower() in _DEVNULL:
        return None, False
    if t == _CWD:
        return cwd, False
    if _TEMP_VARS.match(t):
        return None, True
    posix_tmp = re.match(r"^[\\/]+(?:tmp|var/tmp)(?:/(.*))?$", t.replace("\\", "/"))
    if posix_tmp:  # a Bash /tmp/... on Windows names the MSYS temp folder, not <drive>:\tmp
        rest = posix_tmp.group(1) or ""
        return (os.path.join(tempfile.gettempdir(), *rest.split("/")) if rest
                else tempfile.gettempdir()), False
    t = re.sub(r"\$env:(\w+)", lambda m: os.environ.get(m.group(1), m.group(0)), t, flags=re.IGNORECASE)
    t = re.sub(r"%(\w+)%", lambda m: os.environ.get(m.group(1), m.group(0)), t)
    t = os.path.expanduser(os.path.expandvars(t))
    if _UNRESOLVABLE.search(t):
        return os.path.join(cwd, "<unresolved>"), False  # a path the guard cannot read: treated as the project
    msys = re.match(r"^/([a-zA-Z])/(.*)$", t)
    if os.name == "nt" and msys:  # Git Bash spelling of C:\...
        t = f"{msys.group(1)}:/{msys.group(2)}"
    return (t if os.path.isabs(t) else os.path.join(cwd, t)), False


# --- the decision --------------------------------------------------------------------------------

FILE_TOOLS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path",
              "NotebookEdit": "notebook_path"}
SHELL_TOOLS = {"Bash", "PowerShell"}

ADVICE = ("Do not retry it in another form. If your work needs it, stop and report it in your "
          "handoff as the pipeline rules say (ESCALATE, naming the area).")


def _rel_in_root(path: str, root: str) -> str:
    return to_posix(os.path.relpath(_norm_abs(path), _norm_abs(root)))


def decide(event: Dict[str, Any], agent: Optional[str]) -> Optional[str]:
    """None to leave the call to the normal permission flow, or the reason to deny it."""
    tool = event.get("tool_name") or ""
    tinput = event.get("tool_input") or {}
    cwd = event.get("cwd") or os.getcwd()
    root = find_root(cwd)
    active = read_active(root)
    temps = temp_dirs(event)

    if tool == "Grep":
        target = tinput.get("path") or ""
        pattern_glob = tinput.get("glob") or ""
        if isinstance(target, str) and target and (is_secret_path(target) or is_secret_path(os.path.realpath(target))):
            return f"Blocked by the AI team guard: the search would read a file that holds secrets. {ADVICE}"
        if isinstance(pattern_glob, str) and pattern_glob and _SECRET_GLOB.search(pattern_glob):
            return f"Blocked by the AI team guard: the search would read files that hold secrets. {ADVICE}"
        return None

    if tool == "Read" or tool in FILE_TOOLS:
        key = FILE_TOOLS.get(tool, "file_path")
        raw = tinput.get(key) or ""
        if not isinstance(raw, str) or not raw:
            return None
        path = raw if os.path.isabs(raw) else os.path.join(cwd, raw)
        real = os.path.realpath(path)
        if tool == "Read":
            if is_secret_path(raw) or is_secret_path(real):
                return f"Blocked by the AI team guard: {raw} holds secrets, and no agent opens it. {ADVICE}"
            if active and inside(path, root):
                rel = _rel_in_root(path, root)
                if norm_key(rel) in {norm_key(p) for p in active.get("allow", {}).get("deny_read", [])}:
                    return (f"Blocked by the AI team guard: {rel} is the first review's report, and the second "
                            f"review stays independent of it. Go on without it.")
            return None
        if inside(path, root) and inside(real, root):
            rel = _rel_in_root(path, root)
            if not active:
                return ("Blocked by the AI team guard: no stage is dispatched in this folder, so a pipeline "
                        "agent changes nothing. " + ADVICE)
            if is_allowed(active.get("allow", {}), rel):
                return None
            return (f"Blocked by the AI team guard: {rel} is outside the area of stage "
                    f"{active.get('label')}. {ADVICE}")
        if any(inside(real, d) for d in temps):
            return None  # a scratch file is fine with or without a dispatch
        return (f"Blocked by the AI team guard: {raw} is outside the project and outside your scratch "
                f"folder. {ADVICE}")

    if tool in SHELL_TOOLS:
        command = tinput.get("command") or ""
        if not isinstance(command, str):
            return None
        text = _strip_bodies(command)
        for segment in _segments(command, tool):
            unseen = _unseen_script(segment, text)
            if unseen:
                return (f"Blocked by the AI team guard: `{unseen}` runs text the guard cannot read. Run the "
                        f"command itself. {ADVICE}")
        mutation = git_mutation(command, tool)
        if mutation:
            return (f"Blocked by the AI team guard: `{mutation}` is not one of the read-only git/gh forms an "
                    f"agent may run; only the orchestrator changes the repository. {ADVICE}")
        secret = secret_read(command, tool)
        if secret:
            return f"Blocked by the AI team guard: the command would read, print or copy secrets ({secret}). {ADVICE}"
        if in_place_editor(command, tool):
            return ("Blocked by the AI team guard: edit project files with your file tools, never in place "
                    "from the shell. " + ADVICE)
        if _DOTNET_WRITE.search(text):
            return ("Blocked by the AI team guard: write files with your file tools, not with .NET calls from "
                    "the shell. " + ADVICE)
        allow = (active or {}).get("allow", {})
        for target in write_targets(command, tool):
            resolved, trusted_temp = _resolve_target(target, cwd)
            if trusted_temp or resolved is None:
                continue
            if inside(resolved, root):  # the project comes first, even when it lies under a temp folder
                rel = _rel_in_root(resolved, root)
                if active and rel != "<unresolved>" and is_allowed(allow, rel):
                    continue
                return (f"Blocked by the AI team guard: the command writes {target}, which is not in the area "
                        f"of stage {(active or {}).get('label', 'none (no stage is dispatched)')}. Logs go to "
                        f"your scratch folder. {ADVICE}")
            if any(inside(resolved, d) for d in temps):
                continue
            return (f"Blocked by the AI team guard: the command writes {target}, outside the project and outside "
                    f"your scratch folder. {ADVICE}")
        return None
    return None
