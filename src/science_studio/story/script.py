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
    "'evidence suggests', 'researchers think', 'still debated'. "
    "(6) Craft: open scene 1 with a concrete hook — an observable puzzle, a vivid "
    "'imagine' scenario, or a surprising fact straight from the claims. "
    "(7) Ground every abstraction with an everyday example or analogy (kitchens, "
    "weather, sports, phones); flag them as analogies ('it's like...', 'imagine...'), "
    "never state an analogy as the mechanism. "
    "(8) Rhythm: vary short punchy lines with longer explanatory ones; address ONE "
    "curious listener as 'you'. End scenes on open loops when natural, pay them off "
    "later, and callback the hook in the final scene."
)


CRAFT = (
    "CRAFT: cold-open hook in scene 1 (first 2 sentences must earn the next 10 minutes); "
    "one concrete everyday example or analogy per scene where it fits; "
    "speak to one curious listener; end scenes on open loops, callback the hook at the close."
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
    llm_error = ""
    scene_narrations: list[dict] = []
    if stack is not None:
        try:
            from ..providers.registry import ai_generate
            from ..providers.openai_compat import extract_json_array
            has_real_llm = any(
                getattr(p, "name", "") != "template-fallback" and p.status().available
                for p in getattr(stack, "ai_chain", [])
            )
            if not has_real_llm:
                raise RuntimeError("no external LLM configured")
            n_total = max(1, len(scenes_outline))
            per_words = max(95, round(target_words / n_total))
            lo_w, hi_w = max(85, per_words - 20), min(185, per_words + 25)
            batch_size = 6
            hook_summary = ""
            prev_tail = ""
            providers_seen: list[str] = []
            for start in range(0, n_total, batch_size):
                chunk = scenes_outline[start:start + batch_size]
                is_first = (start == 0)
                is_last = (start + batch_size >= n_total)
                chunk_claims_ids = {cid for s in chunk for cid in s.get("claim_ids", [])}
                rel_claims = [c for c in claims if c["claim_id"] in chunk_claims_ids]
                other_claims = [c for c in claims if c["claim_id"] not in chunk_claims_ids]
                ordered_claims = (rel_claims + other_claims)[:32]
                cblock = "\n".join(
                    f"- [{c['claim_id']}] ({c['confidence']}) {c['claim']} :: {c.get('evidence_summary','')}"
                    for c in ordered_claims
                )
                ctx_lines = []
                if hook_summary:
                    ctx_lines.append(f"OPENING HOOK TO CALLBACK AT END: {hook_summary}")
                if prev_tail:
                    ctx_lines.append(f"PREVIOUS SCENE ENDED WITH (continue smoothly, do not repeat): {prev_tail}")
                role_note = (
                    "Scene 1 is the cold-open hook — open with genuine curiosity, no 'Hey guys'. "
                    if is_first else "Continue mid-documentary — no re-introductions. "
                ) + (
                    "Close the final scene by paying off the opening hook and stating what remains unknown or why it matters."
                    if is_last else "End the last scene in this batch on a natural open loop into the next scene."
                )
                prompt = (
                    f"TOPIC: {idea}\n"
                    f"BATCH: scenes {start + 1}-{start + len(chunk)} of {n_total} "
                    f"(full documentary target ~{target_words} words).\n{CRAFT}\n"
                    + ("\n".join(ctx_lines) + "\n\n" if ctx_lines else "\n")
                    + f"VERIFIED CLAIMS (use ONLY these facts; never invent numbers, studies, or quotes; no inline [C001] tags):\n{cblock}\n\n"
                    + f"SCENES IN THIS BATCH (write spoken narration for EACH of these {len(chunk)} scenes):\n"
                    + "\n".join(f"{start + k + 1}. {s['title']}" for k, s in enumerate(chunk))
                    + f"\n\nReturn ONLY a JSON array of {len(chunk)} objects: "
                      f"[{{\"title\": \"...\", \"narration\": \"...\"}}]. "
                      f"Each narration MUST be {lo_w}-{hi_w} words, natural spoken documentary prose. "
                      f"{role_note}"
                )
                text, used = ai_generate(stack, prompt, system=SYSTEM, max_tokens=3200,
                                         temperature=0.55)
                if used == "template-fallback":
                    raise RuntimeError("all external LLMs fell through to template-fallback")
                providers_seen.append(used)
                arr = extract_json_array(text)
                batch_out: list[dict] = []
                for k, s in enumerate(chunk):
                    a = arr[k] if k < len(arr) and isinstance(arr[k], dict) else {}
                    nar = re.sub(r"\[C\d{2,4}\]|\[S\d{2,4}\]", "", str(a.get("narration", ""))).strip()
                    nar = re.sub(r"\s+", " ", nar)
                    if len(nar.split()) >= 20:
                        batch_out.append({"title": str(a.get("title") or s["title"]).strip(),
                                          "narration": nar, "claim_ids": s["claim_ids"]})
                if len(batch_out) < len(chunk):
                    raise RuntimeError(f"LLM returned {len(batch_out)}/{len(chunk)} valid scenes in batch {start}")
                if is_first and batch_out:
                    hook_summary = batch_out[0]["narration"][:220]
                if batch_out:
                    prev_tail = batch_out[-1]["narration"][-200:]
                scene_narrations.extend(batch_out)
            provider_used = providers_seen[0] if len(set(providers_seen)) == 1 else "+".join(dict.fromkeys(providers_seen))
        except Exception as e:
            if str(e) != "no external LLM configured":
                llm_error = str(e)[:300]
            scene_narrations = []
            provider_used = "template-fallback"
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
            "llm_error": llm_error,
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
