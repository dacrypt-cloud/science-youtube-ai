"""Script engine — narration from verified claims. Simplify language, not science."""
from __future__ import annotations
import re
from .duration import plan_for

SYSTEM = (
    "You are a science documentary scriptwriter (Kurzgesagt / Veritasium level clarity). "
    "Rules: (1) Use ONLY the verified claims and evidence provided — never invent studies, "
    "researchers, statistics, quotes, or mechanisms. (2) Simplify language, never the science: "
    "keep the actual mechanism, define jargon on first use. (3) Sound natural spoken aloud. "
    "(4) No filler, no 'in conclusion', no hype. (5) Mark uncertainty with words like "
    "'evidence suggests', 'researchers think', 'still debated'."
)


def build_script_outline(beats: list[str], causal_chain: list[str], claims: list[dict]) -> list[dict]:
    # Map claims across beats so every beat has evidence.
    outline = []
    per = max(1, len(claims) // max(1, len(beats)))
    for i, beat in enumerate(beats):
        chunk = claims[i * per:(i + 1) * per] or claims[:2]
        outline.append({"beat": beat, "claim_ids": [c["claim_id"] for c in chunk],
                        "chain_points": causal_chain[i:i + 2]})
    return outline


def write_script(outline: list[dict], claims: list[dict], evidence_text: str,
                 duration: str, idea: str, stack=None) -> dict:
    plan = plan_for(duration)
    target_words = plan["words"]
    claim_block = "\n".join(
        f"- [{c['claim_id']}] ({c['confidence']}) {c['claim']} :: {c.get('evidence_summary','')}"
        for c in claims[:40])
    scenes_outline = [
        {"title": o["beat"], "claim_ids": o["claim_ids"]} for o in outline
    ]
    # Expand beats into scenes to hit scene count (round-robin, no nesting)
    lo, hi = plan["scenes"]
    parts = ["", " — part 2", " — part 3", " — part 4"]
    counts: dict[str, int] = {}
    i = 0
    while len(scenes_outline) < lo and len(scenes_outline) < hi:
        base = outline[i % len(outline)]["beat"]
        n = counts.get(base, 0) + 1
        counts[base] = n
        if n == 1:
            i += 1
            continue  # originals already present
        suffix = parts[n - 1] if n <= len(parts) else f" — part {n}"
        # insert after the last scene of the same beat
        idx = max([j for j, s in enumerate(scenes_outline)
                   if s["title"].split(" — part")[0] == base])
        scenes_outline.insert(idx + 1, {"title": base + suffix,
                                        "claim_ids": outline[i % len(outline)]["claim_ids"]})
        i += 1

    provider_used = "template-fallback"
    scene_narrations: list[dict] = []
    if stack is not None:
        try:
            from ..providers.registry import ai_generate
            import json as _json
            prompt = (
                f"TOPIC: {idea}\nTARGET: ~{target_words} words total spoken narration.\n\n"
                f"VERIFIED CLAIMS (use these, cite nothing inline, just be faithful):\n{claim_block}\n\n"
                f"SCENES (write narration for EACH, {len(scenes_outline)} scenes):\n"
                + "\n".join(f"{i+1}. {s['title']}" for i, s in enumerate(scenes_outline))
                + "\n\nReturn ONLY a JSON array: [{\"title\": ..., \"narration\": \"...\"}]. "
                  "Each narration 90-160 words, spoken style. Open scene 1 with genuine curiosity, "
                  "no 'Hey guys'. Close with what remains unknown or why it matters."
            )
            text, provider_used = ai_generate(stack, prompt, system=SYSTEM, max_tokens=6000,
                                              temperature=0.6)
            m = re.search(r"\[.*\]", text, re.S)
            arr = _json.loads(m.group(0) if m else text)
            for s, a in zip(scenes_outline, arr):
                nar = str(a.get("narration", "")).strip()
                if len(nar.split()) >= 20:
                    scene_narrations.append({"title": str(a.get("title", s["title"])),
                                             "narration": nar, "claim_ids": s["claim_ids"]})
        except Exception:
            scene_narrations = []
    if not scene_narrations:
        from ..providers.llm_template import TemplateAIProvider
        tpl = TemplateAIProvider()
        from ..research.planner import topic_anchors
        scene_narrations = tpl.assemble_script(
            scenes_outline, evidence_text, target_words, claims=claims,
            anchors=topic_anchors(idea))
        provider_used = "template-fallback"

    # Tag script_location/scene_location back onto claims
    full_text = "\n\n".join(f"## {s['title']}\n{s['narration']}" for s in scene_narrations)
    for idx, s in enumerate(scene_narrations):
        for cid in s.get("claim_ids", []):
            for c in claims:
                if c["claim_id"] == cid and not c.get("scene_location"):
                    c["scene_location"] = f"scene_{idx+1:02d}"
                    c["script_location"] = s["title"]
    words = len(full_text.split())
    traceability = build_traceability(scene_narrations, claims)
    return {"scenes": scene_narrations, "full_text": full_text, "words": words,
            "est_seconds": words / 150 * 60, "provider": provider_used,
            "target_words": target_words, "traceability": traceability}


def build_traceability(scenes: list[dict], claims: list[dict]) -> list[dict]:
    """CLAIM -> SOURCE -> SCRIPT SENTENCE -> SCENE audit map.

    For each claim, finds script sentences sharing >=2 rare words with the
    claim (extractive scripts usually contain the claim verbatim). Purely
    observational: reports what is/isn't traceable, never invents links.
    """
    from ..providers.llm_template import STOP, split_sentences
    rows = []
    for c in claims:
        ctoks = {w for w in re.findall(r"[a-zA-Z][a-zA-Z\-]{4,}", c.get("claim", "").lower())} - STOP
        hits = []
        for i, s in enumerate(scenes):
            for sent in split_sentences(s.get("narration", "")):
                stoks = {w for w in re.findall(r"[a-zA-Z][a-zA-Z\-]{4,}", sent.lower())} - STOP
                if len(ctoks & stoks) >= 2:
                    hits.append({"scene": f"scene_{i+1:02d}",
                                 "sentence": sent[:240]})
                    break
        rows.append({"claim_id": c.get("claim_id"), "claim": c.get("claim", "")[:300],
                     "confidence": c.get("confidence"), "source_ids": c.get("source_ids", []),
                     "status": c.get("status", "supported"),
                     "script_scenes": [h["scene"] for h in hits][:6],
                     "matched_sentences": [h["sentence"] for h in hits][:3],
                     "traceable": bool(hits)})
    return rows
