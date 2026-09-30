"""Persistent, organized project memory. Nothing overwrites a previous project."""
from __future__ import annotations
import json, uuid, shutil
from datetime import datetime, timezone
from pathlib import Path
from .config import get_settings
from .models import ProjectState


def projects_root() -> Path:
    p = get_settings().projects_dir
    p.mkdir(parents=True, exist_ok=True)
    return p


def new_project_id(idea: str) -> str:
    slug = "".join(c.lower() if c.isalnum() else "-" for c in idea[:40]).strip("-")
    slug = "-".join([w for w in slug.split("-") if w])[:40] or "project"
    return f"{datetime.now(timezone.utc):%Y%m%d}-{slug[:30]}-{uuid.uuid4().hex[:6]}"


STANDARD_DIRS = [
    "research", "script", "production/narration", "production/subtitles",
    "production/video", "production/final", "production/assets",
    "production/diagrams", "production/music",
]


def create_project(idea: str, instructions: str = "", duration: str = "12-15",
                   mode: str = "autonomous") -> tuple[str, Path]:
    pid = new_project_id(idea)
    root = projects_root() / pid
    for d in STANDARD_DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    idea_doc = {
        "project_id": pid, "idea": idea, "instructions": instructions,
        "duration": duration, "mode": mode, "state": ProjectState.IDEA.value,
        "created_at": now, "updated_at": now, "history": [{"state": "IDEA", "at": now}],
    }
    (root / "idea.json").write_text(json.dumps(idea_doc, indent=2), encoding="utf-8")
    return pid, root


def project_dir(pid: str) -> Path:
    return projects_root() / pid


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def set_state(pid: str, state: ProjectState, note: str = "") -> dict:
    root = project_dir(pid)
    idea_path = root / "idea.json"
    doc = read_json(idea_path, {})
    doc["state"] = state.value
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    hist = doc.setdefault("history", [])
    hist.append({"state": state.value, "at": doc["updated_at"], "note": note})
    write_json(idea_path, doc)
    return doc


def get_state(pid: str) -> str:
    doc = read_json(project_dir(pid) / "idea.json", {})
    return doc.get("state", "IDEA")


def list_projects() -> list[dict]:
    out = []
    for p in sorted(projects_root().iterdir(), reverse=True):
        if p.is_dir() and (p / "idea.json").exists():
            try:
                out.append(read_json(p / "idea.json", {}))
            except Exception:
                pass
    return out


def copy_into_project(pid: str, src: Path, dest_rel: str) -> Path:
    dest = project_dir(pid) / dest_rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest
