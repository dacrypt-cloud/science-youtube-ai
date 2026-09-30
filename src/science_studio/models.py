"""Structured pipeline schemas — every stage produces typed artifacts."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
import json


class ProjectState(str, Enum):
    IDEA = "IDEA"
    RESEARCHING = "RESEARCHING"
    RESEARCH_COMPLETE = "RESEARCH_COMPLETE"
    OUTLINING = "OUTLINING"
    SCRIPTING = "SCRIPTING"
    FACT_CHECKING = "FACT_CHECKING"
    VISUAL_PLANNING = "VISUAL_PLANNING"
    ASSET_COLLECTION = "ASSET_COLLECTION"
    NARRATION = "NARRATION"
    RENDERING = "RENDERING"
    QA = "QA"
    READY = "READY"
    FAILED = "FAILED"


STATE_ORDER: list[ProjectState] = [
    ProjectState.IDEA, ProjectState.RESEARCHING, ProjectState.RESEARCH_COMPLETE,
    ProjectState.OUTLINING, ProjectState.SCRIPTING, ProjectState.FACT_CHECKING,
    ProjectState.VISUAL_PLANNING, ProjectState.ASSET_COLLECTION, ProjectState.NARRATION,
    ProjectState.RENDERING, ProjectState.QA, ProjectState.READY,
]


class EvidenceLevel(str, Enum):
    ESTABLISHED = "established"
    STRONG = "strong_evidence"
    LIMITED = "limited_evidence"
    DEBATE = "active_debate"
    HYPOTHESIS = "plausible_hypothesis"
    SPECULATION = "speculation"


@dataclass
class Source:
    source_id: str
    title: str
    url: str
    source_type: str  # journal | preprint | agency | university | database | reference | news_science | other
    publisher: str = ""
    publication_date: str = ""
    authors: str = ""
    doi: str = ""
    snippet: str = ""
    reliability: int = 3  # 1-5

    def to_dict(self) -> dict: return asdict(self)


@dataclass
class Claim:
    claim_id: str
    claim: str
    source_ids: list[str] = field(default_factory=list)
    evidence_summary: str = ""
    confidence: str = "limited_evidence"  # EvidenceLevel value
    script_location: str = ""
    scene_location: str = ""
    status: str = "supported"  # supported | qualified | removed | uncertain

    def to_dict(self) -> dict: return asdict(self)


@dataclass
class Scene:
    scene_id: str
    index: int
    title: str
    narration: str
    concept: str = ""
    visual_objective: str = ""
    visual_query: str = ""
    diagram: str = ""  # diagram kind or "" e.g. lifecycle|timeline|chart|anatomy|process
    onscreen_text: str = ""
    transition: str = "fade"
    est_duration_s: float = 0.0
    audio_file: str = ""
    audio_duration_s: float = 0.0

    def to_dict(self) -> dict: return asdict(self)


@dataclass
class Asset:
    asset_id: str
    scene_id: str
    kind: str  # image | video | diagram | music
    path: str
    source: str = ""
    source_url: str = ""
    license: str = ""
    creator: str = ""
    description: str = ""

    def to_dict(self) -> dict: return asdict(self)


def to_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
