"""Visual planning — every scene gets a visual objective, never random footage.

Two visual tracks (generic, topic-independent):
- OBSERVED scenes (storm in the sky, flash, thunder heard...) → real photography.
- MECHANISM scenes (charge, collisions, fields, invisible steps...) → diagrams.
A scene gets a diagram only when its mechanism score beats its observed score;
otherwise the renderer leads with a real photo. This keeps the video from being
either 'AI voice + random stock' or 'AI voice + endless diagrams'.
"""
from __future__ import annotations
import re

DIAGRAM_TRIGGERS = {
    # Generic scientific vocabulary (topic-independent): lifecycle/cycle,
    # anatomy/structure, process/mechanism, timeline/history, chart/numbers, scale/zoom.
    "lifecycle": ["life cycle", "lifecycle", "cycle", "stage", "ookinete", "oocyst",
                  "sporozoite", "larva", "pupa", "phase", "stages"],
    "anatomy": ["inside", "cross-section", "cross section", "organ", "tissue", "gut",
                "midgut", "salivary", "liver", "lung", "brain", "cell structure",
                "structure", "layer", "layers", "region", "regions", "anatomy",
                "where it happens", "located"],
    "process": ["process", "mechanism", "pathway", "step by step", "first", "then",
                "finally", "cascade", "formation", "forms", "develops", "develop",
                "collide", "collision", "charge", "discharge", "current", "flow",
                "transfer", "buildup", "build-up", "propagat", "breakdown", "trigger"],
    "timeline": ["history", "discover", "19", "20th century", "year", "timeline",
                 "century", "decade"],
    "chart": ["percent", "%", "million", "billion", "rate", "increase", "decrease",
              "graph", "data", "temperature", "degrees", "volt", "energy", "speed",
              "kelvin", "second", "milliseconds", "times", "average", "measure"],
    "scale": ["microscop", "molecular", "molecule", "atom", "nanometer", "zoom",
              "scale", "particle", "particles", "droplet", "crystal", "electron",
              "photon", "micro", "tiny", "invisible"],
}

# Observable-scale nouns: what a camera could film. When these dominate a
# scene, a real photo leads instead of a diagram.
OBSERVED_TRIGGERS = [
    "storm", "storms", "thunderstorm", "sky", "skies", "rain", "rainbow",
    "tornado", "hurricane", "weather", "bolt", "flash", "thunder", "strike",
    "strikes", "lightning", "photograph", "footage", "satellite", "landscape",
    "horizon", "night", "clouds gather", "dark clouds", "eruption", "aurora",
    "ocean", "forest", "city", "aircraft", "you can see", "visible",
]

QUERY_STOP = {
    "that", "this", "with", "from", "have", "what", "when", "then", "than",
    "about", "into", "through", "scene", "continued", "stage", "hook",
    "follow", "journey", "part", "where", "matters", "ends", "actually",
    "really", "involves", "involve", "complex", "furthermore", "reported",
    "using", "there", "their", "which", "these", "those", "between", "during",
    "would", "could", "other", "such", "more", "most", "some", "very",
}


def _diagram_for(text: str) -> str:
    t = text.lower()
    best, score = "", 0
    for kind, keys in DIAGRAM_TRIGGERS.items():
        n = sum(1 for k in keys if k in t)
        if n > score:
            best, score = kind, n
    if score < 1:
        return ""
    observed = sum(1 for k in OBSERVED_TRIGGERS if k in t)
    if observed > score:
        return ""  # observable scene: lead with a real photo, not a diagram
    return best


def _query_for(title: str, narration: str, idea: str = "") -> tuple[str, str]:
    """Returns (primary_query, fallback_query) for stock search.

    Short anchor-led queries (Commons/AND semantics need few, strong words).
    """
    try:
        from ..research.planner import topic_anchors
        anchors = [a for a in topic_anchors(idea) if len(a) >= 4]
    except Exception:
        anchors = []
    if not anchors:
        anchors = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{4,}", idea)
                   if w.lower() not in QUERY_STOP]
    narr_keys = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{5,}", narration[:600])
                 if w.lower() not in QUERY_STOP and not w.lower().endswith("ly")]
    q = " ".join(dict.fromkeys(anchors[:2] + narr_keys[:2]))
    fb = " ".join(dict.fromkeys(anchors[:2])) or title
    return (q or title, fb or title)


def build_storyboard(scenes: list[dict], idea: str, stack=None) -> list[dict]:
    board: list[dict] = []
    # Optional LLM visual pass
    llm_visuals: dict[int, dict] = {}
    if stack is not None:
        try:
            from ..providers.registry import ai_generate
            import json as _json
            prompt = ("For each scene below give: visual_objective (1 line), visual_query "
                      "(3-5 word stock search), diagram (one of lifecycle/anatomy/process/timeline/chart/scale or empty), "
                      "onscreen_text (<=8 words or empty). Return ONLY JSON array.\n\n" +
                      "\n".join(f"{i+1}. {s['title']}: {s['narration'][:200]}" for i, s in enumerate(scenes)))
            text, used = ai_generate(stack, prompt,
                                     system="You are a science visual director.", max_tokens=2500)
            if used == "template-fallback":
                raise RuntimeError("skip template visuals")
            m = re.search(r"\[.*\]", text, re.S)
            arr = _json.loads(m.group(0) if m else text)
            for i, a in enumerate(arr):
                if isinstance(a, dict):
                    llm_visuals[i] = a
        except Exception:
            llm_visuals = {}
    for i, s in enumerate(scenes):
        lv = llm_visuals.get(i, {})
        text = f"{s['title']} {s['narration']}"
        q, fb = _query_for(s["title"], s["narration"], idea)
        board.append({
            "scene_id": f"scene_{i+1:02d}",
            "index": i,
            "title": s["title"],
            "narration": s["narration"],
            "concept": s["title"],
            "visual_objective": lv.get("visual_objective") or f"Show: {s['title']}",
            "visual_query": lv.get("visual_query") or q,
            "visual_query_fallback": fb,
            "diagram": (lv.get("diagram") or _diagram_for(text)).strip(),
            "onscreen_text": (lv.get("onscreen_text") or "")[:80],
            "transition": "fade" if i % 3 else "cut",
            "claim_ids": s.get("claim_ids", []),
        })
    return board
