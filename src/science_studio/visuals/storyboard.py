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
    "process": ["process", "mechanism", "pathway", "step by step",
                "cascade", "formation", "forms", "develops", "develop",
                "collide", "collision", "charge", "discharge", "current", "flow",
                "transfer", "buildup", "build-up", "propagat", "breakdown", "trigger"],
    "timeline": ["history", "discover", "19", "20th century", "year", "timeline",
                 "century", "decade"],
    "chart": ["percent", "%", "million", "billion", "rate", "increase", "decrease",
              "graph", "data", "temperature", "degrees", "volt", "energy", "speed",
              "kelvin", "milliseconds", "average", "measure"],
    "scale": ["microscop", "molecular", "molecule", "atom", "nanometer", "zoom",
              "scale", "particle", "particles", "droplet", "crystal", "electron",
              "photon", "micro", "tiny", "invisible"],
}

VALID_DIAGRAMS = frozenset(DIAGRAM_TRIGGERS.keys())

# Observable-scale nouns: what a camera could film across weather, biology,
# medicine, human life, lab work, and everyday analogies. When these dominate
# a scene, real B-roll / photography leads instead of a diagram.
OBSERVED_TRIGGERS = [
    "storm", "storms", "thunderstorm", "sky", "skies", "rain", "rainbow",
    "tornado", "hurricane", "weather", "bolt", "flash", "thunder", "strike",
    "strikes", "lightning", "photograph", "footage", "satellite", "landscape",
    "horizon", "night", "clouds gather", "dark clouds", "eruption", "aurora",
    "ocean", "forest", "city", "aircraft", "you can see", "visible",
    "patient", "patients", "doctor", "doctors", "hospital", "clinic",
    "baby", "newborn", "infant", "mother", "pregnant", "pregnancy",
    "child", "children", "person", "people", "human", "hand", "hands",
    "face", "eyes", "sleep", "sleeping", "kitchen", "cooking", "phone",
    "laboratory", "scientist", "scientists", "researcher", "wildlife",
    "animal", "animals", "mosquito", "insect", "tree", "trees", "water",
    "river", "mountain", "mountains", "earth", "sunlight", "imagine",
    "picture a", "every day", "daily life",
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


def _mechanism_margin(text: str) -> int:
    t = text.lower()
    mech = max((sum(1 for k in keys if k in t) for keys in DIAGRAM_TRIGGERS.values()), default=0)
    obs = sum(1 for k in OBSERVED_TRIGGERS if k in t)
    return mech - obs


def _norm_diagram(val) -> str:
    d = str(val or "").strip().lower()
    return d if d in VALID_DIAGRAMS else ""


def build_storyboard(scenes: list[dict], idea: str, stack=None) -> list[dict]:
    board: list[dict] = []
    # Optional LLM visual pass
    llm_visuals: dict[int, dict] = {}
    if stack is not None:
        try:
            from ..providers.registry import ai_generate
            from ..providers.openai_compat import extract_json_array
            prompt = (
                "For each scene below give: visual_objective (1 line), visual_query "
                "(3-5 concrete filmable nouns for stock video/photo search, e.g. 'pregnant mother ultrasound clinic'), "
                "diagram (one of lifecycle/anatomy/process/timeline/chart/scale ONLY for invisible mechanisms, "
                "or \"\" empty string for observable/human/story/hook scenes so real B-roll footage plays — "
                "keep at least half the scenes \"\" including scene 1), "
                "onscreen_text (<=8 words or \"\"). Return ONLY a JSON array.\n\n"
                + "\n".join(f"{i+1}. {s['title']}: {s['narration'][:200]}" for i, s in enumerate(scenes))
            )
            text, used = ai_generate(stack, prompt,
                                     system="You are a science visual director balancing real B-roll footage and mechanism diagrams.",
                                     max_tokens=2800)
            if used == "template-fallback":
                raise RuntimeError("skip template visuals")
            arr = extract_json_array(text)
            for i, a in enumerate(arr):
                if isinstance(a, dict):
                    llm_visuals[i] = a
        except Exception:
            llm_visuals = {}
    for i, s in enumerate(scenes):
        lv = llm_visuals.get(i, {})
        text = f"{s['title']} {s['narration']}"
        q, fb = _query_for(s["title"], s["narration"], idea)
        if "diagram" in lv:
            diag = _norm_diagram(lv.get("diagram"))
        else:
            diag = _diagram_for(text)
        board.append({
            "scene_id": f"scene_{i+1:02d}",
            "index": i,
            "title": s["title"],
            "narration": s["narration"],
            "concept": s["title"],
            "visual_objective": lv.get("visual_objective") or f"Show: {s['title']}",
            "visual_query": lv.get("visual_query") or q,
            "visual_query_fallback": fb,
            "diagram": diag,
            "onscreen_text": (lv.get("onscreen_text") or "")[:80],
            "transition": "fade" if i % 3 else "cut",
            "claim_ids": s.get("claim_ids", []),
        })
    # Full-length visual pacing: open the cold-open hook on real B-roll/photo,
    # and cap diagrams at <=50% of scenes (retaining the strongest mechanism
    # scenes) so a documentary never degenerates into back-to-back box charts.
    if len(board) >= 6:
        board[0]["diagram"] = ""
        max_diag = len(board) // 2
        diag_idxs = [b["index"] for b in board if b["diagram"]]
        if len(diag_idxs) > max_diag:
            ranked = sorted(
                diag_idxs,
                key=lambda idx: _mechanism_margin(f"{board[idx]['title']} {board[idx]['narration']}"),
                reverse=True,
            )
            keep = set(ranked[:max_diag])
            for b in board:
                if b["index"] not in keep:
                    b["diagram"] = ""
    return board
