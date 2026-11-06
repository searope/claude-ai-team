#!/usr/bin/env python3
"""PreToolUse hook for the agents of the AI team pipeline.

Registered in the frontmatter of ai-team-auditor, ai-team-author and ai-team-builder
with `--agent <name>`. It can also be registered in a settings file without
`--agent`: it then acts only where the hook input's `agent_type` is one of those.

It denies, with a reason the agent reads:
- Edit/Write/MultiEdit/NotebookEdit outside the dispatched stage's allowlist
  (.ai-team/state/active-dispatch.json), or anywhere when no stage is dispatched;
- Read of files that hold secrets (.env, keys, credentials);
- shell commands that change the repository (git commit, merge, stash, ...),
  print or copy secrets, edit files in place, or redirect output into the project.
Everything else is left to Claude Code's normal permission flow.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _deny(reason: str) -> None:
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.stdout.flush()
    sys.exit(0)


def main() -> None:
    args = sys.argv[1:]
    agent = args[args.index("--agent") + 1] if "--agent" in args and args.index("--agent") + 1 < len(args) else None
    if "--agent" in args and not agent:
        agent = "(none)"  # a hook line with --agent and no name is a broken one: it is denied below
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", "replace")
        event = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        if agent:
            _deny(f"Blocked by the AI team guard: it could not read the hook input ({exc}).")
        sys.exit(0)
    if agent and not event.get("tool_name"):
        _deny("Blocked by the AI team guard: the hook received no tool call to check. Report this in your handoff.")
    try:
        from aiteam import model  # noqa: E402
    except Exception as exc:  # a broken installation denies, on every version of Claude Code
        if agent:
            _deny(f"Blocked by the AI team guard: it could not load its package ({type(exc).__name__}: {exc}). "
                  "Report this in your handoff.")
        sys.exit(0)

    if agent and agent not in model.PIPELINE_AGENTS:
        _deny(f"Blocked by the AI team guard: its hook names the agent type '{agent}', which is not one of the "
              f"pipeline's. Report this in your handoff.")
    agent = agent or event.get("agent_type")
    if agent not in model.PIPELINE_AGENTS:
        sys.exit(0)  # not a pipeline agent: no decision
    try:
        from aiteam import guard  # noqa: E402

        reason = guard.decide(event, agent)
    except Exception as exc:  # fail closed for pipeline agents
        reason = (f"Blocked by the AI team guard: the guard failed ({type(exc).__name__}: {exc}). "
                  "Report this in your handoff.")
    if reason:
        _deny(reason)
    sys.exit(0)


if __name__ == "__main__":
    main()
