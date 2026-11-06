"""The pipeline's state machine: evaluate, route, dispatch and the user's decisions.

Every function works on a Ctx (project root, feature slug, ledger) and returns plain
dicts that ai_team.py prints as JSON. Nothing here runs a git command that changes
the repository.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple

from . import artifacts, checks, gitio, guard, ledger, model, snapshot
from . import project as projmod

SLUG_RX = re.compile(r"^(?:\d+-)?[a-z0-9]+(?:-[a-z0-9]+){1,3}$")

STAGE_SAYS = {
    1: "the product manager asks its questions and writes the spec",
    2: "the copywriter writes the new text and audits the existing text the feature touches",
    3: "the UI designer makes the mock-up and the UI spec",
    4: "the architect writes the ADR: contracts, invariants, tasks and the files that may change",
    5: "the engineer implements the design in the files the ADR allows",
    6: "the DevOps engineer makes the infrastructure changes",
    7: "the test engineer writes and runs a test for every criterion and invariant",
    8: "the security reviewer audits the change record, read-only",
    9: "a second reviewer, on another model, audits the same change on its own, read-only",
}


class PipelineError(Exception):
    """A request the pipeline refuses; the message says why."""


class Ctx:
    def __init__(self, root: str, slug: str, led: Optional[ledger.Ledger] = None,
                 skill_dir: Optional[str] = None) -> None:
        self.root = root
        self.slug = slug
        self.led = led if led is not None else ledger.load(root, slug)
        self.led.setdefault("rerun", {})
        self.led.setdefault("directions", {})
        self.led.setdefault("notices", [])
        self.project = projmod.load(root)
        self.skill_dir = skill_dir or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self._text: Dict[str, Optional[str]] = {}

    # files ------------------------------------------------------------------------------------
    def abs(self, rel: str) -> str:
        return os.path.join(self.root, *rel.split("/"))

    def rel(self, name: str) -> str:
        return model.artifact_path(name, self.slug)

    def text(self, name: str) -> Optional[str]:
        if name not in self._text:
            self._text[name] = projmod.read_text(self.abs(self.rel(name)))
        return self._text[name]

    def exists(self, name: str) -> bool:
        return os.path.isfile(self.abs(self.rel(name)))

    def refresh(self) -> None:
        self._text.clear()

    def handoff(self, number: int) -> artifacts.Handoff:
        rel = model.handoff_path(self.slug, number)
        return artifacts.parse_handoff(self.root, rel) if rel else artifacts.Handoff(path="", exists=False)

    def spec_rev(self) -> Optional[int]:
        return artifacts.revision(self.text("Spec"))

    def adr_rev(self) -> Optional[int]:
        return artifacts.revision(self.text("ADR"))

    @property
    def rules_path(self) -> str:
        return os.path.join(self.skill_dir, model.RULES_FILE_NAME)

    def radius_files(self, which: str) -> List[str]:
        """Files the build may change in Source or Infra: the ADR's list, or Files on a fast path."""
        fast = self.led.get("fast_path")
        if fast:
            files = list(fast.get("files", []))
        else:
            files = [p for p, _ in artifacts.blast_radius(self.text("ADR"), which)]
        out = []
        for f in files:
            if guard.forbidden_path(f):
                continue  # .git/, .claude/, the pipeline's state, absolute or .. paths: never writable
            area = self.project.area_of(f, self.slug)
            if (which == "Source" and area in ("Source", None)) or (which == "Infra" and area == "Infra"):
                out.append(f)
        return out


# --- small helpers -------------------------------------------------------------------------------

def _rec(ctx: Ctx, number: int) -> Dict[str, Any]:
    return ledger.stage_rec(ctx.led, number)


def _fp(text: Optional[str]) -> Optional[str]:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] if text is not None else None


def _status_ok(number: int, status: Optional[str]) -> bool:
    if status is None:
        return False
    return status in (model.REVIEW_STATUSES if model.is_review(number) else model.STAGE_STATUSES)


def _design_artifact_exists(ctx: Ctx, number: int) -> bool:
    area = model.stage(number).writes
    return any(ctx.exists(name) for name in model.AREA_ARTIFACTS.get(area, ()))


def current_handoff(ctx: Ctx, number: int) -> Optional[artifacts.Handoff]:
    """The stage's handoff if it is of the current round and was written after its dispatch."""
    h = ctx.handoff(number)
    led = ctx.led
    if not h.parsed or h.round != led["round"]:
        return None
    runs = ledger.dispatches_in_round(led, number)
    if not runs:
        return None
    if h.mtime + 2 < max(d["at"] for d in runs):
        return None
    return h


def _note(ctx: Ctx, line: str) -> str:
    rel = model.notes_path(ctx.slug)
    path = ctx.abs(rel)
    existing = projmod.read_text(path)
    if existing is None:
        existing = f"# Notes for the stages: {ctx.slug}\n\n## For Later Stages\n"
    elif not re.search(r"^##\s+For Later Stages\s*$", existing, re.MULTILINE):
        existing = existing.rstrip("\n") + "\n\n## For Later Stages\n"
    one_line = " ".join(line.split())
    ledger.write_text(path, existing.rstrip("\n") + f"\n- {one_line}\n")
    return rel


# --- conditions, completion, routing --------------------------------------------------------------

def _condition(ctx: Ctx, number: int) -> Tuple[Optional[bool], Optional[str], str]:
    """The value of a conditional stage's `runs_when`, the fingerprint it was read from, and its source."""
    st = model.stage(number)
    kind = st.runs_when.split(":", 1)[0]
    if kind == "spec":
        text = ctx.text("Spec")
        if text is None:
            return None, None, "Spec"
        return artifacts.topology_flags(text)[st.flag], _fp(text), "Spec"
    if kind == "adr":
        text = ctx.text("ADR")
        if text is None:
            return None, None, "ADR"
        return artifacts.infra_impact(text), _fp(text), "ADR"
    if kind == "project":
        raw = ctx.project.second_review_raw if ctx.project.exists else ""
        return bool(ctx.project.second_review), _fp("second review:" + raw), "project file"
    return True, None, ""


def _decide_conditionals(ctx: Ctx) -> bool:
    led = ctx.led
    changed = False
    for number in model.CONDITIONAL_STAGES:
        rec = _rec(ctx, number)
        if rec.get("skip_reason") == "fast path":
            continue
        if number == 9 and _rec(ctx, model.MERGE_STAGE)["status"] == "DONE":
            continue
        value, fp, source = _condition(ctx, number)
        if fp is None or rec.get("decided_from") == fp:
            continue
        rec["decided_from"] = fp
        st = model.stage(number)
        flag = st.flag
        if value is None:
            ledger.notice(led, f"The {source} has no readable '{flag}' line, so {st.label} runs to be safe.")
            value = True
        if not value and rec["status"] != "SKIPPED":
            leftover = [ctx.rel(a) for a in model.AREA_ARTIFACTS.get(st.writes or "", ()) if ctx.exists(a)]
            rec.update(status="SKIPPED", skip_reason="condition", done_seq=None, done_round=None)
            ledger.history(led, f"{st.label}: SKIPPED ({source} says {flag}: no)")
            if leftover:
                ledger.notice(led, f"{st.label} is skipped now, and its earlier output is left over: "
                                   f"{', '.join(leftover)}. No stage is given it.")
            changed = True
        elif value and rec["status"] == "SKIPPED":
            rec.update(status="PENDING", skip_reason=None)
            ledger.history(led, f"{st.label}: runs ({source} says {flag}: yes)")
            changed = True
    return changed


def _plan_items(ctx: Ctx, number: int, areas: List[str]) -> List[Dict[str, Any]]:
    items = []
    for area in areas:
        if area == "user" or area.startswith("?") or area not in model.AREA_OWNER:
            items.append({"area": area.lstrip("?") if area != "user" else "user", "user": True,
                          "owner": None, "route_to": None, "edge": False,
                          "unknown": area != "user"})
            continue
        owner = model.AREA_OWNER[area]
        rec = _rec(ctx, owner)
        route_to: Optional[int] = owner
        edge = False
        if rec["status"] == "SKIPPED":
            if rec.get("skip_reason") == "fast path":
                edge, route_to = True, None
            else:
                route_to = model.CONDITION_WRITER.get(owner, owner)
        items.append({"area": area, "user": False, "owner": owner, "route_to": route_to, "edge": edge,
                      "unknown": False})
    if not items:  # the handoff names no area: only the user can say where it goes
        items.append({"area": "user", "user": True, "owner": None, "route_to": None, "edge": False,
                      "unknown": False})
    return items


def _complete_stages(ctx: Ctx) -> bool:
    led = ctx.led
    changed = False
    for st in model.STAGES:
        if st.number == model.MERGE_STAGE:
            continue
        rec = _rec(ctx, st.number)
        if rec["status"] != "PENDING":
            continue
        h = current_handoff(ctx, st.number)
        if not h or not _status_ok(st.number, h.status):
            continue
        ok = False
        if h.status in ("DONE", "PASS"):
            ok = True
        elif h.status == "DEFECTS":
            items = _plan_items(ctx, st.number, h.blocked_on)
            ok = all(i["user"] or (not i["edge"] and i["route_to"] and i["route_to"] > st.number)
                     for i in items)
        if ok and st.design and not _design_artifact_exists(ctx, st.number):
            paths = " or ".join(ctx.rel(a) for a in model.AREA_ARTIFACTS.get(st.writes or "", ()))
            if led.get("missing_artifact_round", {}).get(str(st.number)) != led["round"]:
                led.setdefault("missing_artifact_round", {})[str(st.number)] = led["round"]
                ledger.notice(led, f"{st.label} reported {h.status}, but {paths} does not exist. "
                                   f"It runs again with that direction.")
            led["directions"][str(st.number)] = (
                f"Your last run reported {h.status}, but {paths} does not exist. Write it at exactly that "
                f"path, then your handoff.")
            ok = False
        if ok and st.number == model.AREA_OWNER["ADR"] and not led.get("fast_path"):
            problem = _adr_lists_problem(ctx)
            if problem:
                ok = False
                if led.get("adr_problem_round") != led["round"]:
                    led["adr_problem_round"] = led["round"]
                    ledger.notice(led, f"{st.label} reported DONE, but {problem}. It runs again with that "
                                       f"direction: the guard reads that list to know what Coding may write.")
                led["directions"][str(st.number)] = (
                    f"The ADR is not complete: {problem}. Write each Allowed Blast Radius list as rules "
                    f"section 4 says: a heading or bold label with that exact name, then one list item per "
                    f"file starting with the path in backticks, or the one item none.")
        if ok:
            rec.update(status="DONE", done_seq=ledger.next_seq(led), done_round=led["round"])
            ledger.history(led, f"{st.label}: {h.status} (round {led['round']})")
            scans = led.get("scan_summary") or {}
            if st.review and h.status == "PASS" and scans.get("round") == led["round"] and scans.get("failed"):
                ledger.notice(led, f"{st.label} passed although {len(scans['failed'])} scan(s) failed "
                                   f"({', '.join(scans['failed'])}): its report should say under Observations why "
                                   f"each finding is a false positive or outside the feature. Check that it does.")
            changed = True
    return changed


def _adr_lists_problem(ctx: Ctx) -> Optional[str]:
    adr = ctx.text("ADR")
    checks_needed = ["Source"] + (["Infra"] if artifacts.infra_impact(adr) else [])
    for which in checks_needed:
        read = artifacts.blast_radius_read(adr, which)
        if not read["found"]:
            return f"its `Allowed Blast Radius ({which})` heading or bold label is missing"
        if not read["entries"] and not read["none"]:
            return f"its `Allowed Blast Radius ({which})` list names no file as a path in backticks"
        bad = [path for path, _ in read["entries"] if guard.forbidden_path(path)]
        if bad:
            return (f"its `Allowed Blast Radius ({which})` names {', '.join(bad)}: no stage may write under "
                    f".git/, .claude/ or the pipeline's state, nor outside the project")
    return None


def _add_defects(ctx: Ctx, items: List[Dict[str, Any]], kind: str, line: str, handoff: Optional[str]) -> None:
    led = ctx.led
    for item in items:
        led["active_defects"].append({
            "id": max([d.get("id", 0) for d in led["active_defects"]] + [0]) + 1,
            "kind": kind, "area": item["area"], "owner": item.get("owner"),
            "route_to": item.get("route_to"), "line": line or "(no reason given)",
            "handoff": handoff, "seq": ledger.next_seq(led), "user": bool(item.get("user")),
        })


def backward_route(ctx: Ctx, target: int, why: str) -> None:
    """Reset the stage routed to and every later stage that is not SKIPPED; Round goes up."""
    led = ctx.led
    led["round"] += 1
    for st in model.STAGES:
        if st.number < target:
            continue
        rec = _rec(ctx, st.number)
        if rec["status"] == "SKIPPED":
            continue
        rec.update(status="PENDING", done_seq=None, done_round=None)
        led["directions"].pop(str(st.number), None)
        if st.number != model.MERGE_STAGE:
            led["rerun"][str(st.number)] = (
                why if st.number == target else
                f"Run again: {model.stage(target).label} changed in round {led['round']} ({why}).")
    if target < model.FIRST_BUILD_STAGE and led["design_gate"] != model.FAST_PATH_GATE:
        led["design_gate"] = "PENDING"
    if led["gate_status"] in ("READY_FOR_MERGE",):
        led["gate_status"] = "IN_PROGRESS"
    ledger.history(led, f"Backward route to {model.stage(target).label}, round {led['round']}: {why}")


def _apply_items(ctx: Ctx, number: int, status: str, items: List[Dict[str, Any]], handoff: Optional[str],
                 reason: str, counted: bool = True) -> None:
    led = ctx.led
    if not items:
        return
    backward = [i for i in items if i["route_to"] <= number]
    forward = [i for i in items if i["route_to"] > number]
    kind = model.STATUS_KIND.get(status, "change")
    if backward:
        target = min(i["route_to"] for i in backward)
        if counted:
            counter = model.STATUS_COUNTER[status]
            if led["counters"][counter] >= model.CAPS[counter]:
                led["awaiting"] = {
                    "kind": "cap", "counter": counter, "stage": number, "status": status,
                    "items": items, "handoff": handoff, "reason": reason,
                    "summary": f"loop cap reached: {counter} {led['counters'][counter]}/{model.CAPS[counter]}",
                }
                ledger.history(led, f"BLOCKED: the {counter} cap is reached; the route to "
                                    f"{model.stage(target).label} is not applied")
                return
            led["counters"][counter] += 1
        _add_defects(ctx, items, kind, reason, handoff)
        backward_route(ctx, target, f"{kind} from {model.stage(number).label}: {reason}")
    else:
        _add_defects(ctx, forward, kind, reason, handoff)
        for item in forward:
            ledger.history(led, f"Forward route: {kind} on {item['area']} for "
                                f"{model.stage(item['owner']).label}: {reason}")


def _route_handoff(ctx: Ctx, number: int, h: artifacts.Handoff) -> None:
    led = ctx.led
    led["routed"].append(f"{h.path}@r{led['round']}")
    items = _plan_items(ctx, number, h.blocked_on)
    if h.status == "ESCALATE" and any(not i["user"] and not i["edge"] and i["route_to"] > number
                                      for i in items):
        # An ESCALATE cannot wait for a later stage: blocked on the user and on nothing else.
        for i in items:
            i["user"] = True
    edge = [i for i in items if i["edge"]]
    users = [i for i in items if i["user"]]
    normal = [i for i in items if not i["user"] and not i["edge"]]
    if edge:
        led["awaiting"] = {
            "kind": "fast_path_edge", "stage": number, "status": h.status, "items": items,
            "handoff": h.path, "reason": h.reason,
            "summary": f"{model.stage(number).label} is blocked on the area of a stage the fast path skips",
        }
        ledger.history(led, f"BLOCKED: {model.stage(number).label} is at the edge of the fast path "
                            f"({', '.join(i['area'] for i in edge)}): {h.reason}")
        return
    if users:
        _add_defects(ctx, users, model.STATUS_KIND[h.status], h.reason, h.path)
        led["awaiting"] = {
            "kind": "user", "stage": number, "status": h.status, "handoff": h.path,
            "reason": h.reason, "pending": normal,
            "unknown": [i["area"] for i in users if i.get("unknown")],
            "summary": f"{model.stage(number).label} reports {h.status}, blocked on the user"
                       + ("" if h.blocked_on else " (its handoff names no area)"),
        }
        ledger.history(led, f"BLOCKED: {model.stage(number).label} {h.status} on the user: {h.reason}")
        return
    _apply_items(ctx, number, h.status, normal, h.path, h.reason, counted=True)


def _route_pass(ctx: Ctx) -> bool:
    led = ctx.led
    if led.get("awaiting"):
        return False
    for st in model.STAGES:
        if st.number == model.MERGE_STAGE:
            continue
        h = current_handoff(ctx, st.number)
        if not h or h.status not in ("ESCALATE", "DEFECTS", "BLOCK") or not _status_ok(st.number, h.status):
            continue
        if f"{h.path}@r{led['round']}" in led["routed"]:
            continue
        _route_handoff(ctx, st.number, h)
        return True
    return False


def _prune_defects(ctx: Ctx) -> bool:
    led = ctx.led
    keep, changed = [], False
    for d in led["active_defects"]:
        owner = d.get("owner")
        if d.get("user") or not owner:
            keep.append(d)
            continue
        rec = _rec(ctx, owner)
        done_after = rec["status"] == "DONE" and (rec.get("done_seq") or 0) > d["seq"]
        skipped = False
        if rec["status"] == "SKIPPED":
            route_to = d.get("route_to") or owner
            if route_to == owner:
                skipped = True
            else:
                writer = _rec(ctx, route_to)
                skipped = writer["status"] == "DONE" and (writer.get("done_seq") or 0) > d["seq"]
        if done_after or skipped:
            changed = True
            ledger.history(led, f"Resolved: {d['kind']} on {d['area']}"
                                + (" (its stage is skipped)" if skipped else ""))
            continue
        keep.append(d)
    led["active_defects"] = keep
    return changed


# --- gates and the next action ------------------------------------------------------------------

def _design_summary(ctx: Ctx) -> Dict[str, Any]:
    arts = []
    for name in ("Spec", "Copy file", "Copy audit", "UI spec", "ADR"):
        writer = model.ARTIFACT_WRITER[name]
        if writer and _rec(ctx, writer)["status"] == "SKIPPED":
            continue
        if ctx.exists(name):
            arts.append({"name": name, "path": ctx.rel(name), "revision": artifacts.revision(ctx.text(name))})
    handoffs = [model.handoff_path(ctx.slug, st.number) for st in model.STAGES
                if st.design and _rec(ctx, st.number)["status"] != "SKIPPED" and ctx.handoff(st.number).exists]
    return {"artifacts": arts, "design_handoffs": handoffs}


def _design_fps(ctx: Ctx) -> Dict[str, Optional[str]]:
    """Fingerprints of the design artifacts the design gate shows."""
    out: Dict[str, Optional[str]] = {}
    for name in ("Spec", "Copy file", "Copy audit", "UI spec", "ADR"):
        writer = model.ARTIFACT_WRITER[name]
        if writer and _rec(ctx, writer)["status"] == "SKIPPED":
            continue
        if ctx.exists(name):
            out[name] = _fp(ctx.text(name))
    return out


def _options(kind: str, aw: Dict[str, Any], slug: str) -> List[Dict[str, str]]:
    """The ways on, each with the full command to run; <area> and <...> are filled in from the answer."""
    def opt(label: str, leads_to: str, args: str) -> Dict[str, str]:
        return {"label": label, "leads_to": leads_to, "run": f"ai_team {args.format(slug=slug)}"}

    stop = opt("Stop the feature", "Nothing changes yet: you then choose a rollback or shelving.",
               "decide {slug} stop")
    if kind in ("design_gate", "mockup_gate"):
        what = "design" if kind == "design_gate" else "look of the mock-up"
        nxt = ("The build stages start." if kind == "design_gate"
               else "The next stage starts; the design gate still follows.")
        return [opt(f"Approve the {what}", nxt, "decide {slug} approve --dispatch"),
                opt("Request changes", "The stage that writes that area runs again, and this gate opens again.",
                    'decide {slug} change --area <area> --text "<the user\'s words>" --dispatch'),
                stop]
    if kind == "scans_approval":
        return [opt("Run these scans", "They run before every review in projects with this exact list; "
                    "you are asked again when the list changes.", "decide {slug} approve --dispatch"),
                stop]
    if kind == "user":
        if aw.get("status") == "DEFECTS":
            return [opt("Accept it", "The feature runs on as it is.", "decide {slug} accept --dispatch"),
                    opt("Have it changed", "The stage that writes that area runs again with your words.",
                        'decide {slug} change --area <area> --text "<what should change>" --dispatch'),
                    stop]
        return [opt("Answer and go on", "The blocked stage runs again with your answer.",
                    'decide {slug} continue --text "<the answer>" --dispatch'), stop]
    if kind == "cap":
        return [opt("Allow more rounds", "The counter goes back to 0 and the route is applied.",
                    "decide {slug} continue --dispatch"), stop]
    if kind == "no_report":
        return [opt("Run the stage again", "The stage is dispatched once more.",
                    "decide {slug} continue --dispatch"), stop]
    if kind == "violation":
        return [opt("Revert and re-run (Recommended)",
                    "Those files go back to how they were before the stage, and the stage runs again.",
                    "decide {slug} revert --dispatch"),
                opt("Put them back, go on", "Those files go back to how they were; the stage's work stands and "
                    "does not run again. Fits files a tool left behind.", "decide {slug} discard --dispatch"),
                opt("Keep the changes", "The feature goes on; the review still checks them against Write "
                    "Isolation.", "decide {slug} accept --dispatch"),
                stop]
    if kind == "fast_path_edge":
        return [opt("All the stages", "The feature moves to the full lane: spec, ADR and the design gate.",
                    "fast-path {slug} to-full --dispatch"),
                opt("Stay on the fast path", "The blocked stage runs again with your answer.",
                    'fast-path {slug} stay --direction "<the answer>" --dispatch'),
                stop]
    if kind == "review_drift":
        return [opt("Review it again", "Security runs again on the current change record.",
                    "review-again {slug} --dispatch"),
                opt("I took the change out", "Delivery is checked again.", "decide {slug} continue --dispatch"),
                stop]
    if kind == "open_defects":
        return [opt("Drop them and deliver", "The open items are closed as your decision, and delivery goes on.",
                    "decide {slug} continue --dispatch"), stop]
    if kind == "conflict_unowned":
        return [opt("I resolved them", "The merge is completed once the routed stages are done.",
                    "decide {slug} continue --dispatch"), stop]
    return [opt("Go on", "The feature is evaluated again.", "decide {slug} continue --dispatch"), stop]


def _ask(ctx: Ctx, aw: Dict[str, Any]) -> Dict[str, Any]:
    led = ctx.led
    kind = aw["kind"]
    led["gate_status"] = "AWAITING_USER" if kind in ("design_gate", "mockup_gate") else "BLOCKED"
    details: Dict[str, Any] = {k: v for k, v in aw.items() if k not in ("kind", "summary")}
    if kind == "design_gate":
        details.update(_design_summary(ctx))
        if led.get("mockup_gate") == "APPROVED":
            details["mockup"] = artifacts.mockup_listing(ctx.root, ctx.slug)
    if kind == "mockup_gate":
        details["mockup"] = artifacts.mockup_listing(ctx.root, ctx.slug)
        details["ui_handoff"] = model.handoff_path(ctx.slug, 3)
        line = (ctx.project.mockup or "").strip().strip("`").lower()
        details["mockup_line"] = "none" if line in ("", "none") or line.startswith("<") else "set"
    if kind == "violation":
        details["stage_label"] = model.stage(aw["stage"]).label
    if kind == "scans_approval":
        details["commands"] = [{"command": s.command, "fails_when": s.fails_when} for s in ctx.project.scans]
    return {"type": "ask_user", "kind": kind, "summary": aw.get("summary", kind), "details": details,
            "options": _options(kind, aw, ctx.slug)}


def _mockup_gate(ctx: Ctx, cur: int) -> Optional[Dict[str, Any]]:
    led = ctx.led
    gate = led.get("mockup_gate")
    if gate is None:
        return None  # a ledger from before the mock-up gate existed
    rec3 = _rec(ctx, 3)
    if rec3["status"] == "SKIPPED":
        if gate != "SKIPPED":
            led["mockup_gate"] = "SKIPPED"
            led["mockup_gate_reason"] = "stage skipped"
        return None
    if gate == "SKIPPED" and led.get("mockup_gate_reason") != "no page":
        led["mockup_gate"] = gate = "PENDING"  # UI/UX runs now: its mock-up is shown again
        led["mockup_gate_reason"] = None
        ledger.history(led, "Mock-up Gate: PENDING, UI/UX runs")
    if rec3["status"] != "DONE":
        return None
    listing = artifacts.mockup_listing(ctx.root, ctx.slug)
    digest = artifacts.mockup_hash(ctx.root, ctx.slug)
    if gate == "APPROVED" and led.get("approved_mockup") and digest != led["approved_mockup"]:
        led["mockup_gate"] = gate = "PENDING"
        ledger.history(led, "Mock-up Gate: PENDING, the mock-up changed since its approval")
    if gate == "SKIPPED" and led.get("mockup_gate_reason") == "no page" and listing["pages"]:
        led["mockup_gate"] = gate = "PENDING"
        led["mockup_gate_reason"] = None
    if gate != "PENDING":
        return None
    if not listing["pages"]:
        led["mockup_gate"] = "SKIPPED"
        led["mockup_gate_reason"] = "no page"
        ledger.history(led, "Mock-up Gate: SKIPPED, the mock-up folder holds no page")
        ledger.notice(led, "The mock-up folder holds no page; the design gate shows the UI spec's sketch.")
        return None
    if cur <= 3:
        return None
    led["awaiting"] = {"kind": "mockup_gate", "summary": "the user's approval of the mock-up"}
    ledger.history(led, "Mock-up gate opened")
    return _ask(ctx, led["awaiting"])


def _design_gate(ctx: Ctx, cur: int) -> Optional[Dict[str, Any]]:
    led = ctx.led
    gate = led["design_gate"]
    if gate == model.FAST_PATH_GATE:
        return None
    revs = {"spec": ctx.spec_rev(), "adr": ctx.adr_rev()}
    approved = led.get("approved_design")
    changed: List[str] = []
    if approved:
        if approved.get("fp") is not None:  # what was approved, artifact by artifact
            now = _design_fps(ctx)
            changed = sorted(n for n in set(now) | set(approved["fp"]) if now.get(n) != approved["fp"].get(n))
        elif (approved.get("spec"), approved.get("adr")) != (revs["spec"], revs["adr"]):
            changed = ["Spec", "ADR"]  # an approval recorded before fingerprints: revisions only
    if gate == "APPROVED" and changed:
        led["design_gate"] = gate = "PENDING"
        ledger.history(led, f"Design Gate: PENDING, changed since its approval: {', '.join(changed)} "
                            f"(now spec r{revs['spec']}, ADR r{revs['adr']})")
    if cur < model.FIRST_BUILD_STAGE or gate != "PENDING":
        return None
    led["awaiting"] = {
        "kind": "design_gate", "summary": "the user's approval of the design",
        "reopened": bool(approved), "previous": approved and {k: approved.get(k) for k in ("spec", "adr")},
        "current": revs, "changed": changed,
    }
    ledger.history(led, "Design gate opened" + (" again" if approved else ""))
    return _ask(ctx, led["awaiting"])


def _merge_ready(ctx: Ctx) -> bool:
    merge = ctx.led.get("merge")
    if not merge:
        return False
    for item in merge["files"]:
        owner = item.get("owner")
        if owner is None:
            if not item.get("resolved"):
                return False
            continue
        rec = _rec(ctx, owner)
        if not (rec["status"] == "DONE" and (rec.get("done_seq") or 0) > merge["seq"]):
            return False
    return True


def _direction(ctx: Ctx, number: int) -> str:
    led = ctx.led
    explicit = led["directions"].get(str(number))
    if explicit:
        return explicit
    if _rec(ctx, number).get("dispatches"):
        rerun = led["rerun"].get(str(number))
        if rerun:
            return rerun
        return "Run again: no usable report came back from the last run."
    return led.get("request_short") or led.get("request") or ""


def _last_run(ctx: Ctx, number: int) -> str:
    """What the last run of a stage that is dispatched again brought back, in a few words."""
    led = ctx.led
    st = model.stage(number)
    h = ctx.handoff(number)
    if not h.exists:
        return "no handoff"
    if not h.parsed:
        return "a handoff whose Status or Round line could not be read"
    if h.round != led["round"]:
        return f"a handoff of round {h.round}, not of round {led['round']}"
    if not _status_ok(number, h.status):
        return f"a handoff with status {h.status}, which this stage does not report"
    if not current_handoff(ctx, number):
        return "only a handoff older than its dispatch"
    if st.design and not _design_artifact_exists(ctx, number):
        return f"a {h.status} handoff, but not its artifact"
    if st.number == model.AREA_OWNER["ADR"] and not led.get("fast_path") and _adr_lists_problem(ctx):
        return "a DONE handoff, but an ADR whose Allowed Blast Radius lists could not be read"
    return f"a handoff with status {h.status}"


def _dispatch_action(ctx: Ctx, number: int) -> Dict[str, Any]:
    led = ctx.led
    st = model.stage(number)
    runs = ledger.dispatches_in_round(led, number)
    again = False
    what = ""
    if runs:
        what = _last_run(ctx, number)
        if len(runs) >= 2:
            led["awaiting"] = {"kind": "no_report", "stage": number,
                               "summary": f"{st.label} returned twice with no usable report ({what})",
                               "handoff": model.handoff_path(ctx.slug, number)}
            ledger.history(led, f"BLOCKED: {st.label} returned twice with no usable report ({what})")
            return _ask(ctx, led["awaiting"])
        again = True
    led["gate_status"] = "IN_PROGRESS"
    if (number == model.AREA_OWNER["Tests"] and not runs and (led.get("workflow") or {}).get("kind") == "worktree"
            and led.get("updated_round") != led["round"] and not led.get("merge")):
        return {"type": "update", "stage": number, "base": led["workflow"].get("base"),
                "say": "Before Testing, bring the feature's branch up to date with its base "
                       "(Update of the worktree workflow), then run `updated`."}
    if st.review and not runs and ctx.project.scans and led.get("scanned_round") != led["round"]:
        if not checks.scans_approved(ctx.project.scans):
            led["awaiting"] = {"kind": "scans_approval",
                               "summary": "the project's scan commands run only once you approve them"}
            ledger.history(led, "Waiting for the user's approval of the scan commands")
            return _ask(ctx, led["awaiting"])
        pending = len(ctx.project.scans) - len((led.get("scan_progress") or {}).get("results", []))
        return {"type": "scan", "stage": number, "scans": len(ctx.project.scans), "remaining": max(pending, 1),
                "say": f"Before {st.label}, the project's scans run ({len(ctx.project.scans)}): "
                       "run `scan` until it dispatches the review."}
    say = f"{st.label} starts" + (" again" if again else "") + f": {STAGE_SAYS.get(number, '')}."
    if again:
        say += f" The last run brought {what}."
    return {"type": "dispatch", "stage": number, "label": st.label, "skill": st.skill,
            "runs_in": "fork" if st.isolated else "conversation", "direction": _direction(ctx, number),
            "again": again, "say": say}


def evaluate(ctx: Ctx) -> Dict[str, Any]:
    led = ctx.led
    if led["gate_status"] == "REJECTED":
        return {"type": "rejected", "say": "The feature is shelved or stopped: it takes resume, rollback or stop."}
    aw = led.get("awaiting") or {}
    if aw.get("kind") == "scans_approval" and (not ctx.project.scans or checks.scans_approved(ctx.project.scans)):
        led["awaiting"] = None  # the scans were taken out or approved elsewhere
    if aw.get("kind") == "violation":
        return _ask(ctx, aw)  # the stage's report counts only once its changes are settled
    for _ in range(100):
        ctx.refresh()
        changed = _decide_conditionals(ctx)
        changed = _complete_stages(ctx) or changed
        changed = _route_pass(ctx) or changed
        changed = _prune_defects(ctx) or changed
        if not changed:
            break
    if _rec(ctx, model.MERGE_STAGE)["status"] == "DONE":
        led["gate_status"] = "READY_FOR_MERGE"
        return {"type": "ready", "say": "The feature is READY_FOR_MERGE.",
                "workflow": led["workflow"], "delivered_commit": led.get("delivered_commit")}
    if led.get("awaiting"):
        return _ask(ctx, led["awaiting"])
    if _merge_ready(ctx):
        merge = led["merge"]
        return {"type": "complete_merge", "base": merge["base"], "merge_head": merge["merge_head"],
                "files": [f["path"] for f in merge["files"]],
                "say": "Every conflict is resolved: complete the merge before any other stage runs."}
    cur = ledger.current_stage(led)
    gate = _mockup_gate(ctx, cur) or _design_gate(ctx, cur)
    if gate:
        return gate
    if cur == model.MERGE_STAGE:
        open_items = [d for d in led["active_defects"]]
        if open_items:
            led["awaiting"] = {"kind": "open_defects", "items": open_items,
                               "summary": "items are still open at delivery"}
            ledger.history(led, "BLOCKED: items are still open at delivery")
            return _ask(ctx, led["awaiting"])
        led["gate_status"] = "IN_PROGRESS"
        return {"type": "deliver", "workflow": led["workflow"],
                "say": "Every stage is done: carry out Deliver of the feature's git workflow."}
    if led.get("merge"):
        owners = sorted({f["owner"] for f in led["merge"]["files"] if f.get("owner")})
        pending = [o for o in owners if _rec(ctx, o)["status"] == "PENDING"]
        if pending:
            cur = pending[0]
    return _dispatch_action(ctx, cur)


# --- dispatch ------------------------------------------------------------------------------------

def _inputs(ctx: Ctx, number: int) -> List[str]:
    st = model.stage(number)
    paths: List[str] = []
    for name in st.inputs:
        if name == "Change record":
            if ctx.exists(name):
                paths.append(ctx.rel(name))
            continue
        if name == "Scan report":
            if ctx.exists(name) and ctx.led.get("scanned_round") == ctx.led["round"] and ctx.project.scans:
                paths.append(ctx.rel(name))
            continue
        writer = model.ARTIFACT_WRITER[name]
        if writer and _rec(ctx, writer)["status"] == "SKIPPED":
            continue
        if ctx.exists(name):
            paths.append(ctx.rel(name))
    for earlier in model.STAGES:
        if earlier.number >= number or earlier.number == model.MERGE_STAGE:
            continue
        if _rec(ctx, earlier.number)["status"] == "SKIPPED" or earlier.review:
            continue  # a review's handoff goes to no later stage: the second review stays independent
        h = ctx.handoff(earlier.number)
        if h.exists and h.has_for_later:
            paths.append(h.path)
    if os.path.isfile(ctx.abs(model.notes_path(ctx.slug))):
        paths.append(model.notes_path(ctx.slug))
    return paths


def dispatch_text(ctx: Ctx, number: int, direction: str) -> str:
    led = ctx.led
    st = model.stage(number)
    inputs = _inputs(ctx, number)
    lines = [
        f"{ctx.slug} {direction}".rstrip(),
        f"Stage: {st.label}",
        f"Round: {led['round']}",
        f"Rules: {ctx.rules_path}",
        f"Project: {model.PROJECT_FILE}",
        f"Inputs: {', '.join(inputs) if inputs else 'none'}",
        f"Handoff: {model.handoff_path(ctx.slug, number)}",
    ]
    defects = [d for d in led["active_defects"]
               if number in (d.get("route_to"), d.get("owner")) and not d.get("user")]
    if defects:
        lines.append("Defects:")
        lines += [f"- {d['area']}: {d['line']} ({d.get('handoff') or 'the user'})" for d in defects]
    fast = led.get("fast_path")
    if fast:
        lines.append(f"Fast Path: {fast.get('request', '')}")
        lines.append(f"Files: {', '.join(fast.get('files', [])) or 'none'}")
    return "\n".join(lines)


def change_record_text(ctx: Ctx) -> str:
    start = ctx.led.get("start_point")
    if not start:
        raise PipelineError("the ledger has no Start Point")
    return gitio.status_porcelain(ctx.root) + gitio.diff_from(ctx.root, start)


def change_fingerprint(ctx: Ctx) -> Dict[str, Optional[str]]:
    """Every path that differs from the Start Point, with the hash of its content now.

    Staging a file (`git add`) changes `git status` but not this, so a user who stages
    the reviewed files before committing them is not sent back to the review.
    """
    start = ctx.led.get("start_point")
    if not start:
        raise PipelineError("the ledger has no Start Point")
    paths = set(gitio.diff_names(ctx.root, start)) | set(gitio.untracked(ctx.root))
    out: Dict[str, Optional[str]] = {}
    for rel in sorted(paths):
        full = ctx.abs(rel)
        try:
            with open(full, "rb") as fh:
                out[rel] = hashlib.sha256(fh.read()).hexdigest()
        except FileNotFoundError:
            out[rel] = None
        except OSError:
            out[rel] = "<unreadable>"
    return out


def write_change_record(ctx: Ctx) -> Dict[str, Any]:
    content = change_record_text(ctx)
    rel = model.change_record_path(ctx.slug)
    ledger.write_text(ctx.abs(rel), content)
    return {"path": rel, "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(), "bytes": len(content)}


def perform_dispatch(ctx: Ctx, action: Dict[str, Any], direction: Optional[str]) -> Dict[str, Any]:
    led = ctx.led
    number = action["stage"]
    st = model.stage(number)
    direction = " ".join((direction or action["direction"] or "").split())
    if st.review:
        try:
            record = write_change_record(ctx)
        except (gitio.GitError, PipelineError) as exc:
            led["awaiting"] = {"kind": "blocked", "summary": f"the change record could not be written: {exc}"}
            ledger.history(led, f"BLOCKED: the change record could not be written: {exc}")
            ledger.save(ctx.root, led)
            raise PipelineError(f"the change record could not be written: {exc}")
        led["reviewed_change_record"] = {"sha256": record["sha256"], "round": led["round"],
                                         "fingerprint": change_fingerprint(ctx)}
    seq = ledger.next_seq(led)
    _rec(ctx, number)["dispatches"].append({"round": led["round"], "seq": seq, "at": time.time()})
    text = dispatch_text(ctx, number, direction)
    led["directions"].pop(str(number), None)
    led["rerun"].pop(str(number), None)
    led["gate_status"] = "IN_PROGRESS"
    ledger.history(led, f"Dispatched {st.label}, round {led['round']}" + (" (again)" if action.get("again") else ""))
    ledger.save(ctx.root, led)
    snap = None
    if st.isolated:
        allow = guard.stage_allowlist(ctx, number)
        guard.write_active(ctx.root, {
            "slug": ctx.slug, "stage": number, "label": st.label, "round": led["round"], "seq": seq,
            "agent": st.agent, "allow": allow, "created": time.time(), "root": ctx.root,
        })
        if not st.review:
            try:
                snap = snapshot.take(ctx.root, ctx.slug, number, seq)
            except OSError as exc:
                snap = None
                ledger.notice(led, f"The snapshot before {st.label} failed ({exc}); what the stage changes "
                                   f"outside its area will not be checked this time.")
    else:
        guard.clear_active(ctx.root)
    return {"stage": number, "label": st.label, "skill": st.skill, "runs_in": action["runs_in"],
            "text": text, "say": action["say"], "snapshot": snap}


# --- commands ------------------------------------------------------------------------------------

def _take_notices(ctx: Ctx, out: Dict[str, Any]) -> None:
    notices = ctx.led.get("notices") or []
    if notices:
        out.setdefault("notices", []).extend(notices)
    ctx.led["notices"] = []


def _finish(ctx: Ctx, out: Dict[str, Any], save: bool = True) -> Dict[str, Any]:
    """Collect notices, save the ledger, and add where the feature stands.

    After a dispatch the ledger was saved before the stage's snapshot, and is not
    written again: a later write would show up as a change the stage made.
    """
    _take_notices(ctx, out)
    if save:
        ledger.save(ctx.root, ctx.led)
    out.setdefault("ok", True)
    out["gate_status"] = ctx.led["gate_status"]
    out["round"] = ctx.led["round"]
    cur = ledger.current_stage(ctx.led)
    out["current_stage"] = model.stage(cur).label if cur <= model.LAST_STAGE else "none"
    out["ledger"] = model.ledger_md_path(ctx.slug)
    return out


def next_action(ctx: Ctx, do_dispatch: bool = False, direction: Optional[str] = None) -> Dict[str, Any]:
    action = evaluate(ctx)
    out: Dict[str, Any] = {"action": action}
    if do_dispatch and action["type"] == "dispatch":
        _take_notices(ctx, out)
        out["dispatch"] = perform_dispatch(ctx, action, direction)  # saves, then snapshots
        return _finish(ctx, out, save=False)
    return _finish(ctx, out)


def returned(ctx: Ctx, number: Optional[int] = None, do_dispatch: bool = False,
             direction: Optional[str] = None) -> Dict[str, Any]:
    led = ctx.led
    active = guard.read_active(ctx.root)
    if active and active.get("slug") != ctx.slug:
        active = None
    if number is None:
        if active:
            number = int(active["stage"])
        else:
            last = max(((d["seq"], int(n)) for n, r in led["stages"].items() for d in r.get("dispatches", [])),
                       default=None)
            if last is None:
                raise PipelineError("no stage has been dispatched for this feature")
            number = last[1]
    st = model.stage(number)
    result: Dict[str, Any] = {"stage": st.label}
    runs = _rec(ctx, number).get("dispatches") or []
    if st.isolated and not st.review and runs:
        folder = snapshot.folder_for(ctx.slug, runs[-1]["seq"], number)
        manifest = snapshot.load(ctx.root, folder)
        if manifest is not None:
            allow = guard.stage_allowlist(ctx, number)
            try:
                checked = snapshot.violations(ctx.root, manifest, allow, ctx.project, ctx.slug)
            except (OSError, gitio.GitError) as exc:
                checked = {"violations": [], "notes": []}
                ledger.notice(led, f"What {st.label} changed could not be checked ({exc}).")
            found = checked["violations"]
            for item in checked["notes"]:
                ledger.notice(led, f"{item['path']} changed while {st.label} ran. An 'always allow' answer you "
                                   f"gave lands there; if you gave none, look at it.")
            before, now = manifest.get("head"), gitio.head(ctx.root)
            moved = (f"HEAD moved from {before[:12]} to {(now or 'nothing')[:12]} while {st.label} ran: "
                     f"`git log {before[:12]}..HEAD` shows what was committed; `git reset --soft {before[:12]}` "
                     f"undoes the commits and keeps the files") if before and now != before else ""
            if found:
                led["awaiting"] = {"kind": "violation", "stage": number, "files": found, "snapshot": folder,
                                   "summary": f"{st.label} changed files outside its area"
                                              + (f"; {moved}" if moved else "")}
                ledger.history(led, f"BLOCKED: {st.label} changed files outside its area: "
                                    + ", ".join(f["path"] for f in found) + (f"; {moved}" if moved else ""))
            elif moved:
                led["awaiting"] = {"kind": "blocked", "stage": number, "summary": moved}
                ledger.history(led, f"BLOCKED: {moved}")
            result["outside_area"] = found
    guard.clear_active(ctx.root)
    h = ctx.handoff(number)
    result["handoff"] = {"path": h.path, "exists": h.exists, "status": h.status, "round": h.round,
                         "blocked_on": h.blocked_on_raw, "reason": h.reason}
    if h.remarks:
        result["remarks"] = h.remarks[:6000]
    out = next_action(ctx, do_dispatch, direction)
    out["returned"] = result
    return out


def _reset_stage(ctx: Ctx, number: int) -> None:
    _rec(ctx, number).update(status="PENDING", done_seq=None, done_round=None)


def decide(ctx: Ctx, decision: str, text: Optional[str] = None, area: Optional[str] = None,
           do_dispatch: bool = False, direction: Optional[str] = None) -> Dict[str, Any]:
    led = ctx.led
    aw = led.get("awaiting")
    kind = aw["kind"] if aw else None
    answer = " ".join((text or "").split())
    said: Dict[str, Any] = {"decision": decision}

    if led["gate_status"] == "REJECTED" and decision != "stop":
        raise PipelineError("the feature is shelved: it takes resume, rollback or stop, and a resumed feature "
                            "asks for the design again")

    if decision == "stop":
        wf = led["workflow"]["kind"]
        return _finish(ctx, {"action": {"type": "stop", "procedure": f"git-workflow-{wf}.md, section Stop",
                                        "say": "Show what would be lost, and let the user choose rollback or shelving."}})

    if decision == "approve":
        if kind == "design_gate":
            led["design_gate"] = "APPROVED"
            led["approved_design"] = {"spec": ctx.spec_rev(), "adr": ctx.adr_rev(), "fp": _design_fps(ctx)}
            ledger.history(led, f"Design Gate: APPROVED (spec r{ctx.spec_rev()}, ADR r{ctx.adr_rev()})")
        elif kind == "mockup_gate":
            led["mockup_gate"] = "APPROVED"
            led["approved_mockup"] = artifacts.mockup_hash(ctx.root, ctx.slug)
            ledger.history(led, "Mock-up Gate: APPROVED")
        elif kind == "scans_approval":
            checks.approve_scans(ctx.project.scans)
            ledger.history(led, "The user approved the scan commands: "
                                + "; ".join(s.command for s in ctx.project.scans))
        else:
            raise PipelineError("no gate is open, so there is nothing to approve: "
                                + _where(ctx))
        led["awaiting"] = None

    elif decision == "change":
        norm = model.normalize_area(area or "")
        if not norm or norm == "user":
            raise PipelineError("a change needs --area: Spec, Copy, UI spec, ADR, Source, Tests or Infra")
        if not answer:
            raise PipelineError("a change needs --text with the user's words")
        if kind in ("design_gate", "mockup_gate"):
            if norm not in model.DESIGN_AREAS:
                raise PipelineError("a change at a gate belongs to Spec (what), Copy (wording), "
                                    "UI spec (look and layout) or ADR (how it is built)")
            item = _plan_items(ctx, 99, [norm])[0]
            led["awaiting"] = None
            _add_defects(ctx, [item], "change", answer, None)
            backward_route(ctx, item["route_to"], f"change request at the {kind.replace('_', ' ')}: {answer}")
            led["directions"][str(item["route_to"])] = answer
        elif kind == "user" and aw.get("status") == "DEFECTS":
            item = _plan_items(ctx, aw["stage"], [norm])[0]
            if item["edge"]:
                raise PipelineError(f"{norm} belongs to a stage the fast path skips: accept the finding, have "
                                    f"it changed in another area, stop, or move the feature to all the stages "
                                    f"(`fast-path {ctx.slug} to-full`)")
            _close_user_items(ctx)
            led["awaiting"] = None
            _note(ctx, f"The user had a finding of {model.stage(aw['stage']).label} changed: {answer}")
            pending = [i for i in (aw.get("pending") or []) if i.get("route_to") != item["route_to"]]
            _apply_items(ctx, aw["stage"], "DEFECTS", [item] + pending, aw.get("handoff"), answer, counted=False)
            led["directions"][str(item["route_to"])] = answer
        elif kind in (None, "design_gate", "mockup_gate"):
            raise PipelineError("no gate is open: the design was approved already. The feature can run on to "
                                "READY_FOR_MERGE or be stopped. " + _where(ctx))
        else:
            raise PipelineError(f"a change request does not answer this question ({aw.get('summary', kind)}): "
                                f"use one of its options. " + _where(ctx))

    elif decision in ("continue", "accept"):
        if kind in ("design_gate", "mockup_gate"):
            raise PipelineError("continue is not an approval: approve, request a change, or stop")
        if kind == "user":
            _close_user_items(ctx)
            led["awaiting"] = None
            stage_no = aw["stage"]
            st = model.stage(stage_no)
            if aw.get("status") == "DEFECTS":
                _note(ctx, f"The user accepted the finding of {st.label}: {aw.get('reason')}"
                           + (f" ({answer})" if answer else ""))
                _apply_pending(ctx, aw)
            else:
                if answer:
                    _note(ctx, f"The user's answer to {st.label}: {answer}")
                if aw.get("pending"):
                    _apply_pending(ctx, aw)
                else:
                    led["round"] += 1
                    led["directions"][str(stage_no)] = answer or "The user has dealt with what blocked this stage; go on."
                    ledger.history(led, f"{st.label} unblocked by the user, round {led['round']}")
        elif kind == "cap":
            counter = aw["counter"]
            led["counters"][counter] = 0
            led["awaiting"] = None
            ledger.history(led, f"The user reset the {counter} counter")
            _apply_items(ctx, aw["stage"], aw["status"], aw["items"], aw.get("handoff"), aw.get("reason", ""),
                         counted=True)
        elif kind == "no_report":
            led["awaiting"] = None
            led["round"] += 1
            ledger.history(led, f"{model.stage(aw['stage']).label} unblocked by the user, round {led['round']}")
        elif kind == "violation":
            led["awaiting"] = None
            files = ", ".join(f["path"] for f in aw["files"])
            _note(ctx, f"The user kept changes that {model.stage(aw['stage']).label} made outside its area: {files}")
            ledger.history(led, f"The user kept changes outside the area of {model.stage(aw['stage']).label}")
        elif kind == "fast_path_edge":
            raise PipelineError("the feature is at the edge of its fast path: follow lanes.md, Leave, with "
                                "fast-path add-file, fast-path stay or fast-path to-full")
        elif kind == "open_defects":
            for d in aw.get("items", []):
                ledger.history(led, f"Closed by the user at delivery: {d['kind']} on {d['area']}: {d['line']}")
            led["active_defects"] = []
            led["awaiting"] = None
        elif kind == "conflict_unowned":
            merge = led.get("merge") or {}
            for item in merge.get("files", []):
                if item.get("owner") is None:
                    item["resolved"] = True
            led["awaiting"] = None
            ledger.history(led, "The user resolved the conflicts no running stage writes")
        elif kind is None:
            pass
        else:
            led["awaiting"] = None
            ledger.history(led, f"The user went on after: {aw.get('summary', kind)}")
        if answer and kind != "user":  # the user's words reach the later stages through the notes
            said["noted"] = _note(ctx, f"The user said: {answer}")

    elif decision == "revert":
        if kind != "violation":
            raise PipelineError("there is nothing to revert: no stage changed files outside its area")
        res = snapshot.revert(ctx.root, aw["snapshot"], [f["path"] for f in aw["files"]])
        said["reverted"] = res
        stage_no = aw["stage"]
        led["awaiting"] = None
        for n in range(stage_no, model.LAST_STAGE + 1):
            if _rec(ctx, n)["status"] == "DONE":
                _reset_stage(ctx, n)
        led["round"] += 1
        files = ", ".join(f["path"] for f in aw["files"])
        own_area = model.stage(stage_no).writes
        own = [f["path"] for f in aw["files"] if f.get("area") == own_area]
        others = [f["path"] for f in aw["files"] if f.get("area") != own_area]
        parts = []
        if own:
            parts.append(f"{', '.join(own)} lie in your area but are not among the files you may change (the "
                         f"ADR's Allowed Blast Radius, or the Files line on a fast path)")
        if others:
            parts.append(f"{', '.join(others)} lie outside your area")
        led["directions"][str(stage_no)] = (
            f"Your last run changed files it may not change, and they were put back: {'; '.join(parts)}. "
            f"If your work needs one of them, report ESCALATE: blocked on ADR for a file of your area, else on "
            f"the area the file lies in.")
        ledger.history(led, f"Reverted {files}; {model.stage(stage_no).label} runs again, round {led['round']}")
        if res["failed"]:
            ledger.notice(led, "Could not put back: " + ", ".join(res["failed"]))
    elif decision == "discard":
        if kind != "violation":
            raise PipelineError("there is nothing to put back: no stage changed files outside its area")
        res = snapshot.revert(ctx.root, aw["snapshot"], [f["path"] for f in aw["files"]])
        said["reverted"] = res
        led["awaiting"] = None
        files = ", ".join(f["path"] for f in aw["files"])
        ledger.history(led, f"Put back {files}; the work of {model.stage(aw['stage']).label} stands")
        if res["failed"]:
            ledger.notice(led, "Could not put back: " + ", ".join(res["failed"]))
    else:
        raise PipelineError(f"unknown decision '{decision}'")

    out = next_action(ctx, do_dispatch, direction)
    out["decided"] = said
    return out


def _close_user_items(ctx: Ctx) -> None:
    ctx.led["active_defects"] = [d for d in ctx.led["active_defects"] if not d.get("user")]


def _apply_pending(ctx: Ctx, aw: Dict[str, Any]) -> None:
    pending = aw.get("pending") or []
    if pending:
        _apply_items(ctx, aw["stage"], aw["status"], pending, aw.get("handoff"), aw.get("reason", ""), counted=True)


def _where(ctx: Ctx) -> str:
    cur = ledger.current_stage(ctx.led)
    label = model.stage(cur).label if cur <= model.LAST_STAGE else "delivered"
    return f"The feature is at {label}, gate status {ctx.led['gate_status']}."


# --- features ------------------------------------------------------------------------------------

def validate_slug(root: str, slug: str) -> None:
    if not SLUG_RX.match(slug):
        raise PipelineError("the slug must be kebab-case: an optional issue number, then two to four words, "
                            "e.g. 42-export-csv or dark-mode-toggle")
    if os.path.isfile(os.path.join(root, *model.ledger_json_path(slug).split("/"))) or \
            os.path.isfile(os.path.join(root, *model.ledger_md_path(slug).split("/"))):
        raise PipelineError(f"a ledger for '{slug}' exists already")
    if os.path.isfile(os.path.join(root, *model.artifact_path("Spec", slug).split("/"))):
        raise PipelineError(f"a spec for '{slug}' exists already")
    branch = f"agent/{slug}"
    if gitio.branch_exists(root, branch) and gitio.current_branch(root) != branch:
        raise PipelineError(f"the branch {branch} exists already")  # the worktree's own branch is no clash


def _fast_path_files(root: str, files: List[str]) -> List[str]:
    """Files of a fast path; a file in Infra is refused, since a fast path does not run Infra."""
    project = projmod.load(root)
    files = [projmod.to_posix(f) for f in files]
    infra = [f for f in files if project.area_of(f) == "Infra"]
    if infra:
        raise PipelineError(f"{', '.join(infra)} lies in Infra, which a fast path does not build: narrow the "
                            f"change, or run it through all the stages")
    return files


def new_feature(root: str, slug: str, request: str, workflow: str, start_point: str, base: Optional[str] = None,
                lane: str = "full", files: Optional[List[str]] = None, skip_stages: Optional[List[int]] = None,
                lane_reason: Optional[str] = None, short: Optional[str] = None,
                skill_dir: Optional[str] = None) -> Ctx:
    validate_slug(root, slug)
    if workflow not in ("in-place", "worktree"):
        raise PipelineError("--workflow is in-place or worktree")
    led = ledger.new_ledger(slug, request, workflow, base, start_point, lane)
    if short:
        led["request_short"] = short
    ledger.history(led, f"Pipeline Version {model.PIPELINE_VERSION}; request: {request}")
    if lane == "fast":
        if not files:
            raise PipelineError("a fast path needs --files: the files in Source and Infra the change touches")
        # the request stands in for the Acceptance Criteria, so the stages get all of it, on one line
        led["fast_path"] = {"request": " ".join(request.split()), "files": _fast_path_files(root, files)}
        led["design_gate"] = model.FAST_PATH_GATE
        led["mockup_gate"] = "SKIPPED"
        skipped = set(model.FAST_PATH_SKIPS) | set(int(s) for s in (skip_stages or []))
        for n in sorted(skipped):
            if n in (model.MERGE_STAGE,):
                raise PipelineError("Merge is never skipped")
            ledger.stage_rec(led, n).update(status="SKIPPED", skip_reason="fast path")
    if lane_reason:
        ledger.history(led, f"Lane: {lane}; {lane_reason}")
    wf = workflow + (f", base {base}" if base else "")
    ledger.history(led, f"Workflow: {wf}; Start Point {start_point}")
    ctx = Ctx(root, slug, led, skill_dir)
    ledger.save(root, led)
    return ctx


def recover(root: str, slug: str, workflow: str, start_point: str, base: Optional[str] = None,
            skill_dir: Optional[str] = None) -> Ctx:
    if os.path.isfile(os.path.join(root, *model.ledger_json_path(slug).split("/"))):
        raise PipelineError(f"a ledger for '{slug}' exists already")
    if os.path.isfile(os.path.join(root, *model.ledger_md_path(slug).split("/"))):
        raise PipelineError(f"'{slug}' has a markdown ledger from before pipeline 8.0, which this version does "
                            f"not read")
    led = ledger.new_ledger(slug, f"(recovered) {slug}", workflow, base, start_point)
    ctx = Ctx(root, slug, led, skill_dir)
    for st in model.STAGES:
        if st.design and _design_artifact_exists(ctx, st.number):
            ledger.stage_rec(led, st.number).update(status="DONE", done_seq=ledger.next_seq(led), done_round=0)
    ledger.history(led, f"Pipeline Version {model.PIPELINE_VERSION}; recovered from its artifacts")
    ledger.save(root, led)
    return ctx


# --- fast path -----------------------------------------------------------------------------------

def fast_path(ctx: Ctx, op: str, path: Optional[str] = None, files: Optional[List[str]] = None,
              direction: Optional[str] = None, do_dispatch: bool = False) -> Dict[str, Any]:
    led = ctx.led
    aw = led.get("awaiting")
    if not led.get("fast_path") and op != "to-full":
        raise PipelineError("the feature is not on a fast path")
    if op == "add-file":
        if not path:
            raise PipelineError("add-file needs a path")
        if not aw or aw["kind"] != "fast_path_edge":
            raise PipelineError("add-file answers a feature at the edge of its fast path")
        led["fast_path"]["files"] += _fast_path_files(ctx.root, [path])
        led["awaiting"] = None
        led["round"] += 1
        stage_no = aw["stage"]
        led["directions"][str(stage_no)] = f"{path} is added to Files; go on."
        ledger.history(led, f"Fast path: {path} added to Files; {model.stage(stage_no).label} runs again, "
                            f"round {led['round']}")
    elif op == "stay":
        if not aw or aw["kind"] != "fast_path_edge":
            raise PipelineError("stay answers a feature at the edge of its fast path")
        if files:
            led["fast_path"]["files"] = _fast_path_files(ctx.root, files)
        led["awaiting"] = None
        led["round"] += 1
        stage_no = aw["stage"]
        answer = " ".join((direction or "").split()) or "The user settled what was open; go on."
        led["directions"][str(stage_no)] = answer
        _note(ctx, f"The user kept the feature on its fast path: {answer}")
        ledger.history(led, f"Fast path kept by the user; {model.stage(stage_no).label} runs again, "
                            f"round {led['round']}")
        direction = None
    elif op == "to-full":
        fast = led.get("fast_path")
        if not fast:
            raise PipelineError("the feature is not on a fast path")
        edge_items = [i for i in (aw or {}).get("items", []) if i.get("edge")] if aw and aw["kind"] == "fast_path_edge" else []
        for n, rec in led["stages"].items():
            if rec.get("skip_reason") == "fast path":
                rec.update(status="PENDING", skip_reason=None, decided_from=None)
        led["design_gate"] = "PENDING"
        led["mockup_gate"] = "PENDING"
        changed = gitio.changed_paths(ctx.root)
        _note(ctx, f"This feature began on the fast path. Its request: {fast.get('request')}. Files its stages "
                   f"changed so far: {', '.join(changed) or 'none'}.")
        led["fast_path"] = None
        led["lane"] = "full"
        led["awaiting"] = None
        for item in edge_items:
            item["route_to"] = item["owner"]
            item["edge"] = False
        if edge_items:
            _add_defects(ctx, edge_items, "escalation", (aw or {}).get("reason", ""), (aw or {}).get("handoff"))
        backward_route(ctx, 1, "the feature moves from the fast path to all the stages")
    else:
        raise PipelineError("fast-path takes add-file, stay or to-full")
    return next_action(ctx, do_dispatch, direction)


# --- merges and delivery -------------------------------------------------------------------------

def route_conflicts(ctx: Ctx, base: str, do_dispatch: bool = False) -> Dict[str, Any]:
    led = ctx.led
    files = gitio.unmerged_files(ctx.root)
    if not files:
        raise PipelineError("git reports no conflicting file")
    merge_head = gitio.rev_parse(ctx.root, "MERGE_HEAD")
    items = []
    for f in files:
        area = ctx.project.area_of(f, ctx.slug)
        owner = model.AREA_OWNER.get(area) if area else None
        if owner and _rec(ctx, owner)["status"] == "SKIPPED":
            owner = None
        items.append({"path": f, "area": area, "owner": owner, "resolved": False})
    led["merge"] = {"base": base, "merge_head": merge_head, "files": items, "seq": ledger.next_seq(led)}
    owners = sorted({i["owner"] for i in items if i["owner"]})
    for owner in owners:
        mine = [i["path"] for i in items if i["owner"] == owner]
        _add_defects(ctx, [{"area": model.stage(owner).writes, "owner": owner, "route_to": owner}],
                     "conflict", f"merge conflict with {base} in {', '.join(mine)}", None)
    if owners:
        backward_route(ctx, owners[0], f"merge conflict with {base}")
    for owner in owners:
        mine = [i["path"] for i in items if i["owner"] == owner]
        led["directions"][str(owner)] = f"Resolve the merge conflict with {base} in {', '.join(mine)}."
    led["updated_round"] = led["round"]  # this is the Update; Testing does not ask for another
    unowned = [i["path"] for i in items if not i["owner"]]
    if unowned:
        led["awaiting"] = {"kind": "conflict_unowned", "files": unowned,
                           "summary": "conflicting files that no running stage writes (no area, or the area of "
                                      "a skipped stage) are the user's to resolve"}
        ledger.history(led, "BLOCKED: conflicts in files no running stage writes: " + ", ".join(unowned))
    return next_action(ctx, do_dispatch)


def _drop_merge(ctx: Ctx, why: str) -> None:
    led = ctx.led
    if not led.get("merge"):
        return
    led["merge"] = None
    led["active_defects"] = [d for d in led["active_defects"] if d.get("kind") != "conflict"]
    if (led.get("awaiting") or {}).get("kind") == "conflict_unowned":
        led["awaiting"] = None
    ledger.history(led, f"Merge state dropped: {why}")


def merged(ctx: Ctx, do_dispatch: bool = False) -> Dict[str, Any]:
    led = ctx.led
    merge = led.get("merge")
    if not merge:
        raise PipelineError("no merge is in progress for this feature")
    if gitio.rev_parse(ctx.root, "MERGE_HEAD"):
        raise PipelineError("the merge is not committed yet (MERGE_HEAD exists)")
    if gitio.unmerged_files(ctx.root):
        raise PipelineError("files are still unmerged")
    if merge.get("merge_head") and not gitio.is_ancestor(ctx.root, merge["merge_head"]):
        raise PipelineError("the base commit of that merge is not part of this branch: the merge was not "
                            "completed (it was aborted?). Run Update again.")
    led["start_point"] = merge["merge_head"] or led["start_point"]
    led["merge"] = None
    led["updated_round"] = led["round"]
    ledger.history(led, f"Merged {merge['base']}; Start Point {led['start_point']}")
    return next_action(ctx, do_dispatch)


def updated(ctx: Ctx, start_point: Optional[str] = None, do_dispatch: bool = False,
            direction: Optional[str] = None) -> Dict[str, Any]:
    """Update of the worktree workflow is done: clean merge (new Start Point) or nothing to bring in."""
    led = ctx.led
    if led.get("merge") and not gitio.rev_parse(ctx.root, "MERGE_HEAD"):
        _drop_merge(ctx, "a clean Update replaced the merge that was aborted")
    if start_point:
        led["start_point"] = start_point
        ledger.history(led, f"Update: merged the base; Start Point {start_point}")
    else:
        ledger.history(led, "Update: the branch is up to date with its base")
    led["updated_round"] = led["round"]
    return next_action(ctx, do_dispatch, direction)


def run_scans(ctx: Ctx, do_dispatch: bool = False, direction: Optional[str] = None) -> Dict[str, Any]:
    """Run the project's scans for this round, a few at a time, then write the scan report.

    One call stops starting scans after checks.CALL_BUDGET seconds, so that it stays
    inside the time a shell tool allows; the action then says `scan` again.
    """
    led = ctx.led
    scans = ctx.project.scans
    if not scans:
        raise PipelineError("the project file has no Scans section with commands")
    if not checks.scans_approved(scans):
        raise PipelineError("the scan commands are not approved yet: run `next` and ask the user")
    progress = led.get("scan_progress") or {}
    if progress.get("round") != led["round"] or len(progress.get("results", [])) > len(scans):
        progress = {"round": led["round"], "results": []}
    started = time.time()
    ran = []
    while len(progress["results"]) < len(scans):
        remaining = checks.CALL_BUDGET - (time.time() - started)
        if ran and remaining < 60:
            break  # the next scan gets its own call
        index = len(progress["results"])
        result = checks.run_one(ctx.root, ctx.slug, index, scans[index], timeout=remaining)
        progress["results"].append(result)
        ran.append(result)
        led["scan_progress"] = progress
        ledger.save(ctx.root, led)  # keeps what ran if the call is cut off
    summary = [{k: r[k] for k in ("command", "result", "why", "seconds")} for r in progress["results"]]
    if len(progress["results"]) < len(scans):
        left = len(scans) - len(progress["results"])
        return _finish(ctx, {"action": {"type": "scan", "remaining": left,
                                        "say": f"{left} scan(s) still to run: run `scan` again."},
                             "scans": {"results": summary}})
    report = checks.write_report(ctx.root, ctx.slug, led["round"], progress["results"])
    failed = [r["command"] for r in progress["results"] if r["result"] == "FAILED"]
    missing = [r["command"] for r in progress["results"] if r["result"] == "COULD NOT RUN"]
    led["scanned_round"] = led["round"]
    led["scan_summary"] = {"round": led["round"], "failed": failed, "could_not_run": missing}
    led["scan_progress"] = None
    ledger.history(led, f"Scans, round {led['round']}: {len(failed)} of {len(scans)} failed"
                        + (f", {len(missing)} could not run" if missing else ""))
    if failed:
        ledger.notice(led, f"{len(failed)} scan(s) failed: {', '.join(failed)}. The reviewers get the report "
                           f"({report}).")
    if missing:
        ledger.notice(led, f"These scans could not run, most likely because the tool is not installed: "
                           f"{', '.join(missing)}. Install it, or take the scan out of the project file.")
    out = next_action(ctx, do_dispatch, direction)
    out["scans"] = {"report": report, "results": summary}
    return out


def route_back(ctx: Ctx, number: int, reason: str, do_dispatch: bool = False) -> Dict[str, Any]:
    """A backward route the git workflow makes (e.g. a sync brought changes in): no cap."""
    if not 1 <= number <= model.REVIEW_STAGE:
        raise PipelineError("route-back takes a stage from 1 to 8")
    if _rec(ctx, number)["status"] == "SKIPPED":
        raise PipelineError(f"{model.stage(number).label} is SKIPPED")
    led = ctx.led
    up_to_date = led.get("updated_round") == led["round"]
    backward_route(ctx, number, reason)
    if up_to_date:  # the branch was just brought up to date: Testing needs no second Update
        led["updated_round"] = led["round"]
    return next_action(ctx, do_dispatch)


def verify_delivery(ctx: Ctx) -> Dict[str, Any]:
    """Is what would be delivered exactly what the last review saw?

    Compares the content of every changed path with the review's fingerprint, so
    staging files with `git add` changes nothing.
    """
    led = ctx.led
    reviewed = led.get("reviewed_change_record")
    if not reviewed:
        if all(_rec(ctx, n)["status"] == "SKIPPED" for n in model.REVIEW_STAGES):
            return {"unchanged": True, "note": "this lane has no review: there is nothing to compare with",
                    "paths": sorted(change_fingerprint(ctx))}
        raise PipelineError("no change record was reviewed for this feature")
    now = change_fingerprint(ctx)
    before = reviewed.get("fingerprint") or {}
    changed = sorted(p for p in set(before) | set(now) if before.get(p) != now.get(p))
    out: Dict[str, Any] = {"unchanged": not changed, "paths": sorted(now)}
    if changed:
        out["changed_paths"] = changed
    return out


def review_again(ctx: Ctx, do_dispatch: bool = False) -> Dict[str, Any]:
    led = ctx.led
    if (led.get("awaiting") or {}).get("kind") == "review_drift":
        led["awaiting"] = None  # the user chose to review again: that is not a third drift
        led["review_again_streak"] = 0
        backward_route(ctx, model.REVIEW_STAGE, "paths changed after the review; the user asked for a new review")
        return next_action(ctx, do_dispatch)
    if ledger.current_stage(led) < model.MERGE_STAGE:
        raise PipelineError("review-again follows a change after the review, at delivery or after it: "
                            + _where(ctx))
    led["review_again_streak"] = int(led.get("review_again_streak", 0)) + 1
    if led["review_again_streak"] >= 2:
        check = verify_delivery(ctx)
        led["awaiting"] = {"kind": "review_drift", "paths": check.get("changed_paths", []),
                           "summary": "paths changed after the review twice in a row"}
        ledger.history(led, "BLOCKED: paths changed after the review twice in a row: "
                            + ", ".join(check.get("changed_paths", [])))
        led["review_again_streak"] = 0
        return next_action(ctx)
    backward_route(ctx, model.REVIEW_STAGE, "paths changed after the review")
    return next_action(ctx, do_dispatch)


def delivered(ctx: Ctx, commit: Optional[str] = None) -> Dict[str, Any]:
    led = ctx.led
    if ledger.current_stage(led) != model.MERGE_STAGE:
        raise PipelineError("not every stage before Merge is DONE or SKIPPED: " + _where(ctx))
    if led["active_defects"]:
        raise PipelineError("items are still open: " + ", ".join(d["line"] for d in led["active_defects"]))
    if led.get("awaiting"):
        raise PipelineError(f"a question is open: {led['awaiting'].get('summary', led['awaiting']['kind'])}. "
                            f"Answer it first.")
    check = verify_delivery(ctx)
    if not check["unchanged"]:
        raise PipelineError("what would be delivered is not what the review saw ("
                            + ", ".join(check.get("changed_paths", [])) + "): run `review-again`")
    rec = _rec(ctx, model.MERGE_STAGE)
    rec.update(status="DONE", done_seq=ledger.next_seq(led), done_round=led["round"])
    led["gate_status"] = "READY_FOR_MERGE"
    led["delivered_commit"] = (gitio.rev_parse(ctx.root, commit) or commit) if commit else None
    led["review_again_streak"] = 0
    ledger.history(led, "Delivered: READY_FOR_MERGE" + (f", commit {commit}" if commit else ""))
    return _finish(ctx, {"action": {"type": "ready", "say": "The feature is READY_FOR_MERGE."}})


def verify_delivered(ctx: Ctx) -> Dict[str, Any]:
    """The check before a step the user orders: is the feature unchanged since delivery?"""
    led = ctx.led
    if led["gate_status"] != "READY_FOR_MERGE":
        return {"ready": False, "unchanged": False, "reason": "not READY_FOR_MERGE: " + _where(ctx)}
    root = ctx.root
    dirty = gitio.changed_paths(root)
    if led["workflow"]["kind"] == "worktree":
        head = gitio.head(root)
        delivered = gitio.rev_parse(root, led["delivered_commit"]) if led.get("delivered_commit") else None
        ok = bool(delivered) and head == delivered and not dirty
        return {"ready": True, "unchanged": ok, "head": head, "delivered_commit": led.get("delivered_commit"),
                "uncommitted": dirty}
    if dirty:
        check = verify_delivery(ctx)
        return {"ready": True, "state": "uncommitted", **check}
    names = set(gitio.diff_names(root, led["start_point"]))
    reviewed = set((led.get("reviewed_change_record") or {}).get("fingerprint") or {})
    return {"ready": True, "unchanged": names == reviewed, "state": "committed", "paths": sorted(names),
            "unexpected": sorted(names - reviewed), "missing": sorted(reviewed - names)}


# --- other ledger edits ------------------------------------------------------------------------------

def set_fields(ctx: Ctx, gate_status: Optional[str] = None, design_gate_pending: bool = False,
               start_point: Optional[str] = None, shelved_stash: Optional[str] = None,
               history_line: Optional[str] = None) -> Dict[str, Any]:
    led = ctx.led
    before = led["gate_status"]
    if gate_status:
        if gate_status not in model.GATE_STATUSES:
            raise PipelineError(f"gate status is one of {', '.join(model.GATE_STATUSES)}")
        led["gate_status"] = gate_status
        if gate_status == "REJECTED":
            _drop_merge(ctx, "the feature is shelved; the base is merged again when it resumes")
        if gate_status == "IN_PROGRESS":
            if (led.get("awaiting") or {}).get("kind") in ("design_gate", "mockup_gate"):
                led["awaiting"] = None
            if before == "REJECTED":  # resumed: a new round, and the current stage starts afresh
                led["round"] += 1
                cur = ledger.current_stage(led)
                if cur <= model.LAST_STAGE:
                    led["rerun"][str(cur)] = ("The feature was shelved and is resumed: take up the work where it "
                                              "stands in the folder.")
                ledger.history(led, f"Resumed, round {led['round']}")
    if design_gate_pending and led["design_gate"] != model.FAST_PATH_GATE:
        led["design_gate"] = "PENDING"
    if start_point:
        led["start_point"] = start_point
    if shelved_stash is not None:
        led["shelved_stash"] = None if shelved_stash in ("", "none") else shelved_stash
    if history_line:
        ledger.history(led, history_line)
    return next_action(ctx)


def add_note(ctx: Ctx, line: str) -> Dict[str, Any]:
    rel = _note(ctx, line)
    return _finish(ctx, {"action": {"type": "noted", "notes": rel}})


def stop_list(ctx: Ctx) -> Dict[str, Any]:
    led = ctx.led
    root = ctx.root
    entries = [{"status": xy, "path": p, "from": o} for xy, p, o in gitio.status_entries(root)]
    if led["workflow"]["kind"] == "worktree" and led["workflow"].get("base"):
        commits = gitio.log_oneline(root, f"{led['workflow']['base']}..HEAD")
    else:
        commits = gitio.log_oneline(root, f"{led['start_point']}..HEAD") if led.get("start_point") else []
    return {"ok": True, "uncommitted": entries, "commits": commits, "working_files": _working_files(ctx),
            "shelved_stash": led.get("shelved_stash")}


def _working_files(ctx: Ctx) -> List[str]:
    rels = [model.ledger_json_path(ctx.slug), model.ledger_md_path(ctx.slug), model.notes_path(ctx.slug),
            model.change_record_path(ctx.slug), model.scan_report_path(ctx.slug)]
    rels += [checks.output_path(ctx.slug, i) for i in range(len(ctx.project.scans) + 20)]
    rels += [model.handoff_path(ctx.slug, st.number) for st in model.STAGES if st.handoff]
    found = [r for r in rels if os.path.isfile(ctx.abs(r))]
    for folder in (model.mockup_dir(ctx.slug), model.snapshot_dir(ctx.slug)):
        if os.path.isdir(ctx.abs(folder)):
            found.append(folder + "/")
    return found


def purge(ctx: Ctx) -> Dict[str, Any]:
    removed = []
    active = guard.read_active(ctx.root)
    if active and active.get("slug") == ctx.slug:
        guard.clear_active(ctx.root)
    for rel in _working_files(ctx):
        path = ctx.abs(rel.rstrip("/"))
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.isfile(path):
            os.remove(path)
        removed.append(rel)
    return {"ok": True, "removed": removed}


def status_all(root: str) -> Dict[str, Any]:
    folder = os.path.join(root, *model.STATE_DIR.split("/"))
    features = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if name.endswith("-pipeline.json"):
                slug = name[: -len("-pipeline.json")]
                try:
                    led = ledger.load(root, slug)
                except (OSError, ValueError):
                    continue
                cur = ledger.current_stage(led)
                features.append({"slug": slug, "gate_status": led["gate_status"], "round": led["round"],
                                 "current_stage": model.stage(cur).label if cur <= model.LAST_STAGE else "none",
                                 "waiting_on": (led.get("awaiting") or {}).get("summary")})
    active = [f for f in features if f["gate_status"] not in ("READY_FOR_MERGE", "REJECTED")]
    return {"ok": True, "features": features, "active": [f["slug"] for f in active],
            "rejected": [f["slug"] for f in features if f["gate_status"] == "REJECTED"]}
