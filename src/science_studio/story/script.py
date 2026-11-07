"""Script engine — narration from verified claims. Simplify language, not science."""
from __future__ import annotations
import re
from collections import Counter
from .duration import plan_for

SYSTEM = (
    "You are a science & evidence documentary scriptwriter (Kurzgesagt / Veritasium level clarity). "
    "Rules: (1) Use ONLY the verified claims and evidence provided — never invent studies, "
    "researchers, statistics, quotes, or mechanisms. (2) Simplify language, never the facts: "
    "keep the actual mechanism, define jargon on first use. (3) Sound natural spoken aloud. "
    "(4) NEVER start sentences with 'According to...', 'In conclusion', or robotic citations. "
    "(5) Mark uncertainty naturally ('evidence suggests', 'researchers debate'). "
    "(6) Open scene 1 with a concrete curiosity hook straight from the claims, and use natural "
    "open loops between scenes when appropriate. "
    "(7) Ground abstractions with a concrete everyday example or analogy where helpful, "
    "but use AT MOST ONE brief analogy every 3 scenes; NEVER repeat or revisit the same analogy "
    "domain (e.g. never reuse farming, cooking, or traffic twice in one script), and NEVER open "
    "multiple scenes with 'Imagine...'. "
    "(8) ZERO REPETITION: every scene MUST advance to NEW facts and mechanisms — never restate "
    "a fact, number, or example already spoken in an earlier scene."
)


CRAFT = (
    "CRAFT: cold-open hook in scene 1; advance strictly forward scene by scene with ZERO "
    "repeated facts, ZERO 'According to...' openers, and at most one fresh analogy per batch; "
    "speak naturally to one curious listener; use natural open loops and callback the opening hook in the final scene."
)


def build_script_outline(beats: list[str], causal_chain: list[str], claims: list[dict]) -> list[dict]:
    outline = []
    per = max(1, len(claims) // max(1, len(beats)))
    for i, beat in enumerate(beats):
        chunk = claims[i * per:(i + 1) * per] or claims[:2]
        outline.append({"beat": beat, "claim_ids": [c["claim_id"] for c in chunk],
                        "chain_points": causal_chain[i:i + 2]})
    return outline


def _content_toks(s: str) -> set[str]:
    from ..providers.llm_template import STOP, stem
    raw = re.findall(r"[a-z]{4,}|\d+", (s or "").lower())
    return {(stem(w) if w.isalpha() else w) for w in raw if w not in STOP}


def _strip_robotic_lead(s: str) -> str:
    s_mod = re.sub(r"^\s*According\s+(?:to\s+)?(?:this|the\s+\w+(?:\s+\w+)?)\s*,?\s*", "", s or "", flags=re.I)
    if s_mod and s_mod[0].islower():
        s_mod = s_mod[0].upper() + s_mod[1:]
    return s_mod.strip()


def _dedupe_scene_repetitions(scenes: list[dict], anchors: list[str] | None = None,
                              is_llm: bool = False,
                              enforce_hygiene: bool = False) -> list[dict]:
    """Hard post-generation anti-loop & hygiene guard.

    Removes any sentence that echoes an earlier sentence (Jaccard >= 0.80),
    strips robotic 'According to...' prefixes, caps 'Imagine...' openers to at
    most 2 across the entire documentary, prevents trigram loops, and drops any
    sentence that would violate QA narration hygiene.
    """
    from ..providers.llm_template import is_clean_llm_sentence, is_clean_sentence, split_sentences_raw

    seen_sets: list[set[str]] = []
    trigram_counts: Counter = Counter()
    imagine_count = 0
    cleaned_scenes: list[dict] = []

    for sc in scenes:
        raw_sents = [_strip_robotic_lead(x) for x in split_sentences_raw(sc.get("narration", ""))]
        raw_sents = [x for x in raw_sents if len(x.split()) >= 4]
        kept: list[str] = []
        for s in raw_sents:
            if enforce_hygiene and len(s) > 40:
                hygiene_ok = is_clean_llm_sentence(s, anchors) if is_llm else is_clean_sentence(s, anchors)
                if not hygiene_ok:
                    continue
            low = s.lower()
            if low.startswith("imagine "):
                if imagine_count >= 2:
                    continue
                imagine_count += 1
            toks = _content_toks(s)
            if enforce_hygiene and len(toks) >= 4:
                is_dup = any(
                    len(toks & prev) / max(1, len(toks | prev)) >= 0.65
                    for prev in seen_sets
                )
                if is_dup and (len(raw_sents) > 1 or len(kept) >= 1):
                    continue
            w4 = re.findall(r"[a-z]{4,}", low)
            s_tris = [" ".join(w4[j:j + 3]) for j in range(len(w4) - 2)]
            if enforce_hygiene and s_tris and any(trigram_counts[t] >= 4 for t in s_tris) and len(kept) >= 1:
                continue
            kept.append(s)
            if toks:
                seen_sets.append(toks)
            for t in s_tris:
                trigram_counts[t] += 1

        if not kept and raw_sents:
            # Prefer a non-imagine fallback sentence if all sentences were filtered
            non_im = [x for x in raw_sents if not x.lower().startswith("imagine ")]
            kept = [(non_im or raw_sents)[-1]]
        cleaned_scenes.append({**sc, "narration": " ".join(kept)})
    return cleaned_scenes


def write_script(outline: list[dict], claims: list[dict], evidence_text: str,
                 duration: str, idea: str, stack=None) -> dict:
    plan = plan_for(duration)
    target_words = plan["words"]
    lo, hi = plan["scenes"]

    # Quality & completeness over artificial length: never stretch a small pool
    # of verified claims across 16 scenes (which forces LLMs/templates to loop!).
    evidence_capped = False
    n_distinct_claims = len(claims)
    if 0 < n_distinct_claims < lo:
        capped_lo = max(6, n_distinct_claims)
        if capped_lo < lo:
            scale_ratio = capped_lo / float(lo)
            lo = capped_lo
            hi = max(lo, min(hi, n_distinct_claims + 2))
            target_words = max(650, int(target_words * scale_ratio))
            evidence_capped = True

    scenes_outline = [
        {"title": o["beat"], "claim_ids": list(o["claim_ids"])} for o in outline
    ]
    parts = ["", " — part 2", " — part 3", " — part 4"]
    counts: dict[str, int] = {}
    i = 0
    while len(scenes_outline) < lo and len(scenes_outline) < hi:
        base = outline[i % len(outline)]["beat"]
        n = counts.get(base, 0) + 1
        counts[base] = n
        if n == 1:
            i += 1
            continue
        suffix = parts[n - 1] if n <= len(parts) else f" — part {n}"
        idx = max([j for j, s in enumerate(scenes_outline)
                   if s["title"].split(" — part")[0] == base])
        scenes_outline.insert(idx + 1, {"title": base + suffix,
                                        "claim_ids": list(outline[i % len(outline)]["claim_ids"])})
        i += 1

    # Partition claims evenly across scenes_outline so every scene gets its OWN
    # primary slice of verified claims instead of sharing identical claim_ids!
    if claims and scenes_outline:
        n_sc = len(scenes_outline)
        for s_idx, sc_item in enumerate(scenes_outline):
            c_start = int(s_idx * len(claims) / n_sc)
            c_end = max(c_start + 2, int((s_idx + 1) * len(claims) / n_sc))
            slice_ids = [c["claim_id"] for c in claims[c_start:c_end]]
            if slice_ids:
                sc_item["claim_ids"] = slice_ids

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
            per_words = max(90, round(target_words / n_total))
            lo_w, hi_w = max(80, per_words - 20), min(185, per_words + 25)
            batch_size = 6
            hook_summary = ""
            prev_tail = ""
            covered_summaries: list[str] = []
            providers_seen: list[str] = []
            claim_by_id = {c["claim_id"]: c for c in claims}

            for start in range(0, n_total, batch_size):
                chunk = scenes_outline[start:start + batch_size]
                is_first = (start == 0)
                is_last = (start + batch_size >= n_total)
                chunk_claims_ids = [cid for s in chunk for cid in s.get("claim_ids", [])]
                seen_cid: set[str] = set()
                rel_claims = []
                for cid in chunk_claims_ids:
                    if cid in claim_by_id and cid not in seen_cid:
                        rel_claims.append(claim_by_id[cid])
                        seen_cid.add(cid)
                other_claims = [c for c in claims if c["claim_id"] not in seen_cid]
                ordered_claims = (rel_claims + other_claims)[:32]
                cblock = "\n".join(
                    f"- [{c['claim_id']}] ({c['confidence']}) {c['claim']} :: {c.get('evidence_summary','')}"
                    for c in ordered_claims
                )
                ctx_lines = []
                if hook_summary:
                    ctx_lines.append(f"OPENING HOOK TO CALLBACK ONLY IN FINAL SCENE: {hook_summary}")
                if covered_summaries:
                    ctx_lines.append(
                        "POINTS & ANALOGIES ALREADY SPOKEN IN EARLIER SCENES (STRICTLY FORBIDDEN TO REPEAT):\n"
                        + "\n".join(f"  * {cs}" for cs in covered_summaries[-12:])
                    )
                if prev_tail:
                    ctx_lines.append(f"PREVIOUS SCENE ENDED WITH (continue smoothly, do not repeat): {prev_tail}")
                role_note = (
                    "Scene 1 is the cold-open hook — open with genuine curiosity, no 'Hey guys'. "
                    if is_first else "Continue mid-documentary — no re-introductions, no repeating earlier facts. "
                ) + (
                    "Close the final scene by paying off the opening hook and stating what remains open or why it matters."
                    if is_last else "End the last scene in this batch on a natural forward transition."
                )
                scene_lines = []
                for k, s in enumerate(chunk):
                    assigned = ", ".join(s.get("claim_ids", [])[:4])
                    scene_lines.append(f"{start + k + 1}. {s['title']} (focus on claims: {assigned})")
                prompt = (
                    f"TOPIC: {idea}\n"
                    f"BATCH: scenes {start + 1}-{start + len(chunk)} of {n_total} "
                    f"(full documentary target ~{target_words} words).\n{CRAFT}\n"
                    + ("\n".join(ctx_lines) + "\n\n" if ctx_lines else "\n")
                    + f"VERIFIED CLAIMS (use ONLY these facts; never invent numbers, studies, or quotes; no inline [C001] tags):\n{cblock}\n\n"
                    + f"SCENES IN THIS BATCH (write UNIQUE spoken narration for EACH of these {len(chunk)} scenes):\n"
                    + "\n".join(scene_lines)
                    + f"\n\nReturn ONLY a JSON array of {len(chunk)} objects: "
                      f"[{{\"title\": \"...\", \"narration\": \"...\"}}]. "
                      f"Each narration MUST be {lo_w}-{hi_w} words, natural spoken documentary prose, "
                      f"with ZERO repeated sentences or recycled analogies. {role_note}"
                )
                text, used = ai_generate(stack, prompt, system=SYSTEM, max_tokens=3400,
                                         temperature=0.5)
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
                        covered_summaries.append(f"Scene {start + k + 1} ({s['title']}): {nar[:140]}")
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

    # Hard anti-loop + hygiene pass across both LLM and template outputs
    from ..research.planner import topic_anchors as _ta_dedupe
    _anc = _ta_dedupe(idea)
    _is_llm = (provider_used != "template-fallback")
    scene_narrations = _dedupe_scene_repetitions(
        scene_narrations,
        anchors=_anc,
        is_llm=_is_llm,
        enforce_hygiene=_is_llm or len(claims) >= 12,
    )

    full_text = "\n\n".join(f"## {s['title']}\n{s['narration']}" for s in scene_narrations)
    for idx, s in enumerate(scene_narrations):
        for cid in s.get("claim_ids", []):
            for c in claims:
                if c["claim_id"] == cid and not c.get("scene_location"):
                    c["scene_location"] = f"scene_{idx+1:02d}"
                    c["script_location"] = s["title"]
    words = len(full_text.split())
    traceability = build_traceability(scene_narrations, claims)
    return {
        "scenes": scene_narrations,
        "full_text": full_text,
        "words": words,
        "est_seconds": words / 150 * 60,
        "provider": provider_used,
        "llm_error": llm_error,
        "evidence_capped": evidence_capped,
        "target_words": target_words,
        "traceability": traceability,
    }


def build_traceability(scenes: list[dict], claims: list[dict]) -> list[dict]:
    """CLAIM -> SOURCE -> SCRIPT SENTENCE -> SCENE audit map."""
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
                     "script_hits": hits, "used_in_script": bool(hits),
                     "traceable": bool(hits)})
    return rows
