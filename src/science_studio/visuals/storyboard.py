"""Visual planning — every scene gets a visual objective, never random footage."""
from __future__ import annotations
import re

DIAGRAM_TRIGGERS = {
    "lifecycle": ["life cycle", "lifecycle", "stage", "ookinete", "oocyst", "sporozoite", "larva", "pupa"],
    "anatomy": ["inside", "cross-section", "organ", "tissue", "gut", "midgut", "salivary", "liver", "lung", "brain", "cell structure"],
    "process": ["process", "mechanism", "pathway", "step by step", "first", "then", "finally", "cascade"],
    "timeline": ["history", "discover", "19", "20th century", "year", "timeline"],
    "chart": ["percent", "%", "million", "rate", "increase", "decrease", "graph", "data"],
    "scale": ["microscop", "molecular", "atom", "nanometer", "zoom", "scale"],
}


def _diagram_for(text: str) -> str:
    t = text.lower()
    best, score = "", 0
    for kind, keys in DIAGRAM_TRIGGERS.items():
        n = sum(1 for k in keys if k in t)
        if n > score:
            best, score = kind, n
    return best if score >= 1 else ""


def _query_for(title: str, narration: str, idea: str = "") -> str:
    stop = {"that", "this", "with", "from", "have", "what", "when", "then", "than",
            "about", "into", "through", "scene", "continued", "stage", "hook",
            "follow", "journey", "part", "where", "matters", "ends"}
    idea_keys = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{4,}", idea)
                 if w.lower() not in stop]
    narr_keys = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{5,}", narration[:600])
                 if w.lower() not in stop]
    # anchor every query to the topic so stock results stay relevant
    q = " ".join(dict.fromkeys(idea_keys[:2] + narr_keys[:3]))
    return q or title


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
        board.append({
            "scene_id": f"scene_{i+1:02d}",
            "index": i,
            "title": s["title"],
            "narration": s["narration"],
            "concept": s["title"],
            "visual_objective": lv.get("visual_objective") or f"Show: {s['title']}",
            "visual_query": lv.get("visual_query") or _query_for(s["title"], s["narration"], idea),
            "diagram": (lv.get("diagram") or _diagram_for(text)).strip(),
            "onscreen_text": (lv.get("onscreen_text") or "")[:80],
            "transition": "fade" if i % 3 else "cut",
            "claim_ids": s.get("claim_ids", []),
        })
    return board
