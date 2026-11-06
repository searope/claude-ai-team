"""Static model of the pipeline: stages, areas, artifacts and paths.

This module is the only place where the skills of the stages are named.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

PIPELINE_VERSION = "8.1"
LEDGER_SCHEMA = 1

AREAS = ("Spec", "Copy", "UI spec", "ADR", "Source", "Tests", "Infra")
DESIGN_AREAS = ("Spec", "Copy", "UI spec", "ADR")

# Agent types (permission tiers) of the isolated stages.
AGENT_AUDITOR = "ai-team-auditor"
AGENT_AUTHOR = "ai-team-author"
AGENT_BUILDER = "ai-team-builder"
PIPELINE_AGENTS = (AGENT_AUDITOR, AGENT_AUTHOR, AGENT_BUILDER)


@dataclass(frozen=True)
class Stage:
    number: int
    name: str
    skill: Optional[str]
    handoff: Optional[str]
    inputs: Tuple[str, ...]
    writes: Optional[str]
    runs_when: str
    agent: Optional[str]
    design: bool = False

    @property
    def label(self) -> str:
        return f"{self.number}. {self.name}"

    @property
    def isolated(self) -> bool:
        return self.agent is not None

    @property
    def review(self) -> bool:
        return self.number in REVIEW_STAGES

    @property
    def flag(self) -> Optional[str]:
        """The flag a conditional stage's `runs_when` reads, such as `UI` in `spec:UI`."""
        return self.runs_when.split(":", 1)[1] if ":" in self.runs_when else None


STAGES = (
    Stage(1, "Discovery", "product-manager", "pm", (), "Spec", "always", None, True),
    Stage(2, "Copy", "copywriter", "copy", ("Spec",), "Copy",
          "spec:User-Facing Text", AGENT_AUTHOR, True),
    Stage(3, "UI/UX", "ui-designer", "ui", ("Spec", "Copy file"), "UI spec",
          "spec:UI", AGENT_BUILDER, True),
    Stage(4, "Architecture", "system-architect", "arch",
          ("Spec", "Copy file", "Copy audit", "UI spec"), "ADR", "always", AGENT_AUTHOR, True),
    Stage(5, "Coding", "software-engineer", "dev",
          ("Spec", "Copy file", "Copy audit", "UI spec", "ADR"), "Source", "always", AGENT_BUILDER),
    Stage(6, "Infra", "devops-engineer", "devops", ("ADR",), "Infra",
          "adr:Infra Impact", AGENT_BUILDER),
    Stage(7, "Testing", "test-engineer", "test",
          ("Spec", "Copy file", "Copy audit", "UI spec", "ADR"), "Tests", "always", AGENT_BUILDER),
    Stage(8, "Security", "security-reviewer", "security",
          ("Spec", "Copy file", "Copy audit", "UI spec", "ADR", "Change record", "Scan report"), None,
          "always", AGENT_AUDITOR),
    Stage(9, "Second Review", "second-reviewer", "review2",
          ("Spec", "Copy file", "Copy audit", "UI spec", "ADR", "Change record", "Scan report"), None,
          "project:Second Review", AGENT_AUDITOR),
    Stage(10, "Merge", None, None, (), None, "always", None),
)

STAGE_BY_NUMBER = {s.number: s for s in STAGES}
LAST_STAGE = 10
MERGE_STAGE = 10
REVIEW_STAGE = 8          # the first review; a route back to "the review" goes here
REVIEW_STAGES = (8, 9)
FIRST_BUILD_STAGE = 5
CONDITIONAL_STAGES = tuple(s.number for s in STAGES if s.runs_when != "always")
# The stages a fast path skips besides those its project names: the design stages, and Infra,
# which builds only from an ADR.
FAST_PATH_SKIPS = tuple(s.number for s in STAGES if s.design) + (6,)


def is_review(number: int) -> bool:
    return int(number) in REVIEW_STAGES

# Artifacts of a feature, by the names the routing table uses.
ARTIFACT_PATHS = {
    "Spec": "docs/specs/{slug}.md",
    "Copy file": "docs/copy/{slug}-copy.md",
    "Copy audit": "docs/copy/{slug}-copy-audit.md",
    "UI spec": "docs/design/{slug}-ui-spec.md",
    "ADR": "docs/adr/{slug}-adr.md",
    "Change record": ".ai-team/scratchpad/{slug}-changes.md",
    "Scan report": ".ai-team/scratchpad/{slug}-scans.md",
}
ARTIFACT_WRITER = {"Spec": 1, "Copy file": 2, "Copy audit": 2, "UI spec": 3, "ADR": 4,
                   "Change record": None, "Scan report": None}
AREA_ARTIFACTS = {"Spec": ("Spec",), "Copy": ("Copy file", "Copy audit"),
                  "UI spec": ("UI spec",), "ADR": ("ADR",)}
AREA_OWNER = {"Spec": 1, "Copy": 2, "UI spec": 3, "ADR": 4, "Source": 5, "Infra": 6, "Tests": 7}

# Conditional stages and the stage that writes the artifact their condition reads.
CONDITION_WRITER = {2: 1, 3: 1, 6: 4}

CAPS = {"tests": 3, "security": 3, "escalations": 5}
STATUS_COUNTER = {"DEFECTS": "tests", "BLOCK": "security", "ESCALATE": "escalations"}
STATUS_KIND = {"DEFECTS": "test", "BLOCK": "security", "ESCALATE": "escalation"}
REVIEW_STATUSES = ("PASS", "BLOCK")
STAGE_STATUSES = ("DONE", "ESCALATE", "DEFECTS")

GATE_STATUSES = ("IN_PROGRESS", "AWAITING_USER", "BLOCKED", "REJECTED", "READY_FOR_MERGE")
FAST_PATH_GATE = "SKIPPED (fast path)"

# Working files.
STATE_DIR = ".ai-team/state"
SCRATCH_DIR = ".ai-team/scratchpad"
MOCKUP_DIR = ".ai-team/mockups/{slug}"
SNAPSHOT_DIR = ".ai-team/snapshots/{slug}"
ACTIVE_DISPATCH = ".ai-team/state/active-dispatch.json"
PROJECT_FILE = ".claude/ai-team-project.md"
RULES_FILE_NAME = "ai-team-pipeline.md"


def stage(number: int) -> Stage:
    return STAGE_BY_NUMBER[int(number)]


def artifact_path(name: str, slug: str) -> str:
    return ARTIFACT_PATHS[name].format(slug=slug)


def ledger_json_path(slug: str) -> str:
    return f"{STATE_DIR}/{slug}-pipeline.json"


def ledger_md_path(slug: str) -> str:
    return f"{STATE_DIR}/{slug}-pipeline.md"


def handoff_path(slug: str, number: int) -> Optional[str]:
    st = stage(number)
    if not st.handoff:
        return None
    return f"{SCRATCH_DIR}/{slug}-{st.handoff}-context.md"


def notes_path(slug: str) -> str:
    return f"{SCRATCH_DIR}/{slug}-notes.md"


def change_record_path(slug: str) -> str:
    return artifact_path("Change record", slug)


def scan_report_path(slug: str) -> str:
    return artifact_path("Scan report", slug)


def mockup_dir(slug: str) -> str:
    return MOCKUP_DIR.format(slug=slug)


def snapshot_dir(slug: str) -> str:
    return SNAPSHOT_DIR.format(slug=slug)


def normalize_area(raw: str) -> Optional[str]:
    """Map a free-form area name from a handoff to its canonical name, or 'user'."""
    text = raw.strip().strip("`'\"*_ .").lower()
    if not text:
        return None
    if text in ("user", "the user"):
        return "user"
    aliases = {
        "spec": "Spec", "specification": "Spec",
        "copy": "Copy", "copy file": "Copy", "copy audit": "Copy",
        "ui spec": "UI spec", "ui-spec": "UI spec", "uispec": "UI spec", "ui": "UI spec",
        "adr": "ADR",
        "source": "Source", "src": "Source",
        "tests": "Tests", "test": "Tests",
        "infra": "Infra", "infrastructure": "Infra",
    }
    return aliases.get(text)
