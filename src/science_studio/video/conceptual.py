"""Conceptual alignment: do the visuals actually show what is narrated?

Three lenses (each usable alone, combined for the QA gate):
  visuals_only(board, assets, ...)  — per-scene primary visual defects:
      placeholder diagram labels ("Step 1"), stock primaries that fail the
      namesake veto (stale/misleading assets).
  narration_only(board, narr)       — per-scene narration anomalies: extreme
      speech rates (truncated or padded TTS), overlong single sentences.
  combined(...)                     — visual<->narration alignment: diagram
      label stems must overlap the scene's narrated content stems.

Only misleading or disconnected content fails. Honest generic fallbacks
(title cards) never fail: a plain visual is not a wrong visual.
"""
from __future__ import annotations
import re
from pathlib import Path

_STOP = frozenset(
    "that this with from have has were been are was than then there their "
    "they them when which while where would could should about into over "
    "under more most some such only also between through during each other "
    "into onto your Down him her his she our you we us our your".lower().split())


def _stems(text: str) -> set[str]:
    from ..providers.llm_template import stem as _stem
    return {_stem(w) for w in re.findall(r"[a-zA-Z]{4,}", text or "")} - _STOP


def _svg_labels(svg_path: Path) -> list[str]:
    """Label texts from one of our generated diagram SVGs (title, subtitle
    and footer excluded by shell position)."""
    try:
        svg = Path(svg_path).read_text(encoding="utf-8")
    except Exception:
        return []
    texts = [t.strip() for _, t in
             re.findall(r'<text[^>]*font-size="(\d+)"[^>]*>([^<]*)</text>', svg)]
    texts = [t for t in texts if t and "science-youtube-ai" not in t]
    if len(texts) <= 2:
        return []
    return texts[2:]  # drop title + subtitle


def _scene_svg(scene_id: str, assets: list[dict],
               diagrams_dir: Path | None) -> Path | None:
    for a in assets:
        if a.get("scene_id") == scene_id and a.get("primary") \
                and a.get("kind") == "diagram" and a.get("path"):
            cand = Path(a["path"]).with_suffix(".svg")
            if cand.exists():
                return cand
    if diagrams_dir:
        cands = sorted(Path(diagrams_dir).glob(f"{scene_id}_*.svg"))
        if cands:
            return cands[0]
    return None


def visuals_only(board: list[dict], assets: list[dict],
                 anchor_stems: set[str] | None = None,
                 diagrams_dir: Path | None = None) -> dict[str, list[tuple]]:
    """Per-scene visual defects. Returns {scene_id: [(severity, message)]}."""
    from ..visuals.assets import _img_relevant
    out: dict[str, list[tuple]] = {}
    primaries = {a["scene_id"]: a for a in assets if a.get("primary")}
    for sc in board:
        sid = sc["scene_id"]
        issues: list[tuple] = []
        a = primaries.get(sid)
        if a is None:
            issues.append(("fail", "no primary visual"))
        elif a.get("kind") == "diagram":
            svg = _scene_svg(sid, assets, diagrams_dir)
            labels = _svg_labels(svg) if svg else []
            if svg is not None and labels and all(
                    re.fullmatch(r"(Step \d+|…)", l) for l in labels):
                issues.append(("fail", f"diagram shows placeholder labels {labels[:3]}"))
        elif a.get("kind") in ("image", "video") and anchor_stems:
            if not _img_relevant({"title": a.get("description", ""),
                                  "description": a.get("img_description", ""),
                                  "categories": a.get("categories", [])},
                                 anchor_stems):
                issues.append(("fail", f"misleading stock visual: "
                                       f"{a.get('description', '')[:60]}"))
        if issues:
            out[sid] = issues
    return out


def narration_only(board: list[dict], narr: list[dict]) -> dict[str, list[tuple]]:
    """Per-scene narration anomalies (warnings, never fail-grade alone)."""
    out: dict[str, list[tuple]] = {}
    durs = {n.get("scene_id"): float(n.get("duration_s", 0) or 0) for n in narr}
    for sc in board:
        sid = sc["scene_id"]
        issues: list[tuple] = []
        words = (sc.get("narration") or "").split()
        dur = durs.get(sid, 0)
        if dur > 0 and words:
            wpm = len(words) / dur * 60
            if wpm < 50:
                issues.append(("warn", f"speech rate {wpm:.0f} wpm — audio may be padded"))
            elif wpm > 300:
                issues.append(("warn", f"speech rate {wpm:.0f} wpm — audio may be truncated"))
        for sent in re.split(r"(?<=[.!?])\s+", sc.get("narration", "")):
            if len(sent.split()) > 70:
                issues.append(("warn", f"overlong sentence ({len(sent.split())} words)"))
                break
        if issues:
            out[sid] = issues
    return out


def combined(board: list[dict], assets: list[dict], narr: list[dict],
             anchor_stems: set[str] | None = None,
             diagrams_dir: Path | None = None) -> dict[str, list[tuple]]:
    """Visuals + narration + their alignment. Fail-grade issues:
    missing primaries, misleading stock, placeholder/disconnected diagrams.
    """
    out = visuals_only(board, assets, anchor_stems, diagrams_dir)
    for sid, issues in narration_only(board, narr).items():
        out.setdefault(sid, []).extend(issues)
    for sc in board:
        sid = sc["scene_id"]
        a = next((x for x in assets
                  if x.get("scene_id") == sid and x.get("primary")), None)
        if a is None or a.get("kind") != "diagram":
            continue
        if any(sev == "fail" for sev, _ in out.get(sid, [])):
            continue  # already failed (e.g. placeholders) — no pile-on
        svg = _scene_svg(sid, assets, diagrams_dir)
        labels = _svg_labels(svg) if svg else []
        if len(labels) < 3:
            continue  # title card or unreadable — honest fallback, not a defect
        content = _stems(sc.get("narration", "") + " " + sc.get("title", ""))
        labstems = _stems(" ".join(labels))
        if content and labstems and not (content & labstems):
            out.setdefault(sid, []).append(
                ("fail", f"diagram labels disconnected from narration: {labels[:3]}"))
    return out
