"""Stages 6-13: multi-source search, evidence extraction, cross-check,
contradictions, uncertainty, and the claim-evidence map."""
from __future__ import annotations
import re, time
from collections import Counter


def clean_text(raw: str) -> str:
    """Strip HTML tags/markers for storage and TTS safety."""
    import html as _html
    t = re.sub(r"<[^>]+>", " ", raw or "")
    t = _html.unescape(t)
    t = re.sub(r"\[[A-Z]\d{2,4}\]", " ", t)  # source markers like [S034]
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _clip(text: str, n: int) -> str:
    """Clip to n chars at a sentence boundary (fallback: word boundary).

    Always drops a trailing fragment: raw provider cuts can leave text that
    ends mid-sentence even when short.
    """
    window = text[:n] if len(text) > n else text
    ends = [m.end() for m in re.finditer(r"[.!?][\"\"]?\s+(?=[A-Z0-9])", window)]
    unfinished = not re.search(r"[.!?][\"\"]?\s*$", window)
    if ends and (len(text) > n or unfinished):
        if len(text) <= n or ends[-1] > n * 0.4:
            return window[:ends[-1]].strip()
    if len(text) > n:
        return window.rsplit(" ", 1)[0]
    return window.strip()


def _relevant(title: str, snippet: str, idea_words: set[str], source_type: str) -> bool:
    toks = set(re.findall(r"[a-z]{5,}", (title + " " + snippet).lower()))
    need = 1 if source_type in ("journal", "preprint", "agency", "university", "database") else 2
    return len(toks & idea_words) >= need


def run_research(plan: dict, stack, progress_cb=None) -> dict:
    interp0 = plan.get("interpretation", {}) or {}
    idea_words = set(w for w in (interp0.get("keywords") or [])
                     if len(w) >= 5)
    idea_words |= {w.lower() for e in (interp0.get("entities") or [])
                   for w in re.findall(r"[A-Za-z]{5,}", e)}
    questions = plan.get("research_questions", [])
    budget = plan.get("budget", {})
    per_q = int(budget.get("queries_per_question", 3))
    per_query = int(budget.get("sources_per_query", 5))
    max_sources = int(budget.get("max_sources", 30))

    def _short(q: str, n: int = 7) -> str:
        toks = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", q.lower())
                if w not in ("what", "does", "with", "from", "that", "this", "about",
                             "into", "under", "over", "behind", "current", "actually")]
        return " ".join(toks[:n]) or q[:80]

    queries: list[str] = []
    interp = plan.get("interpretation", {}) or {}
    # Seed queries: the raw idea + entities + keyword cores (best for search APIs).
    if interp.get("idea"):
        queries.append(interp["idea"][:160])
    for ent in (interp.get("entities") or [])[:4]:
        queries.append(ent)
    kws = interp.get("keywords") or []
    if len(kws) >= 3:
        queries.append(" ".join(kws[:5]))
    for q in questions:
        queries.append(_short(q))
        queries.append(f"{_short(q)} mechanism explanation")
        if per_q >= 3:
            queries.append(f"{_short(q)} evidence research")
        if per_q >= 4:
            queries.append(f"{_short(q, 5)} history discovery")
        if per_q >= 5:
            queries.append(f"{_short(q, 5)} misconceptions uncertainty")
    # dedupe while preserving order
    queries = list(dict.fromkeys(queries))

    sources: list[dict] = []
    seen_urls: set[str] = set()
    notes: list[str] = []
    total = len(queries) * len(stack.searchers)
    done = 0
    failures: dict[str, int] = {}  # circuit breaker: skip dead providers
    for qi, query in enumerate(queries):
        for s in stack.searchers:
            done += 1
            if progress_cb:
                progress_cb(done, total, f"{s.name}: {query[:60]}")
            if failures.get(s.name, 0) >= 4:
                continue
            try:
                st = s.status()
                if not st.available:
                    continue
                hits = s.search(query, limit=per_query)
                if not hits:
                    failures[s.name] = failures.get(s.name, 0) + 1
                else:
                    failures[s.name] = 0
                for hit in hits:
                    url = (hit.get("url") or "").strip()
                    if not url or url in seen_urls:
                        continue
                    title = clean_text(hit.get("title", ""))[:300]
                    snippet = clean_text(hit.get("snippet", ""))[:1500]
                    stype = hit.get("source_type", "other")
                    if not title or not _relevant(title, snippet, idea_words, stype):
                        continue
                    seen_urls.add(url)
                    sid = f"S{len(sources)+1:03d}"
                    sources.append({
                        "source_id": sid,
                        "title": title,
                        "url": url,
                        "source_type": stype,
                        "publisher": hit.get("publisher", ""),
                        "publication_date": hit.get("publication_date", ""),
                        "authors": hit.get("authors", ""),
                        "doi": hit.get("doi", ""),
                        "snippet": snippet,
                        "reliability": int(hit.get("reliability", 2) or 2),
                        "via": s.name, "query": query,
                    })
                    if snippet:
                        notes.append(f"[{sid}] {title}: {_clip(snippet, 600)}")
                    if len(sources) >= max_sources:
                        break
            except Exception as e:
                notes.append(f"search error {s.name}: {e}")
            if len(sources) >= max_sources:
                break
        if len(sources) >= max_sources:
            break

    # Rank: journals/agencies first, then reliability
    type_rank = {"journal": 0, "agency": 0, "university": 1, "database": 1,
                 "reference": 2, "preprint": 3, "news_science": 3, "other": 4}
    sources.sort(key=lambda s: (type_rank.get(s["source_type"], 4), -s["reliability"]))

    blocks = []
    for s in sources:
        if not s["snippet"]:
            continue
        # snippet first, attribution tail (stripped by template preclean, kept for LLM context)
        pub = s["publisher"] or "?"
        date = s.get("publication_date", "") or "?"
        blocks.append(f"{s['title']}. {s['snippet']}\n[{s['source_id']}] ({pub}, {date}).")
    evidence_text = "\n\n".join(blocks)

    claims = _extract_claims(evidence_text, sources, stack)
    contradictions, uncertainty = _audit(claims, sources)
    causal_chain = _causal_chain(plan, claims)
    return {
        "sources": sources,
        "notes": notes[:400],
        "claims": claims,
        "contradictions": contradictions,
        "uncertainty": uncertainty,
        "causal_chain": causal_chain,
        "evidence_text": evidence_text[:60000],
        "queries": queries,
    }


def _extract_claims(evidence_text: str, sources: list[dict], stack) -> list[dict]:
    claims: list[dict] = []
    # Try LLM structuring first
    if stack is not None and evidence_text.strip():
        try:
            from ..providers.registry import ai_generate
            import json as _json
            prompt = (
                "From the RESEARCH NOTES below, extract the 15-30 most important factual claims "
                "for a science documentary. For each: claim (one sentence), evidence_summary "
                "(<=40 words), confidence (one of: established, strong_evidence, limited_evidence, "
                "active_debate, plausible_hypothesis, speculation), source_ids (from brackets).\n"
                "Return ONLY a JSON array of objects with keys claim, evidence_summary, confidence, source_ids.\n\n"
                f"RESEARCH NOTES:\n{evidence_text[:18000]}"
            )
            text, _ = ai_generate(stack, prompt,
                                  system="You extract verifiable claims. Never invent sources.",
                                  max_tokens=3000)
            m = re.search(r"\[.*\]", text, re.S)
            arr = _json.loads(m.group(0) if m else text)
            for c in arr:
                if not isinstance(c, dict) or not c.get("claim"):
                    continue
                claims.append({
                    "claim_id": f"C{len(claims)+1:03d}",
                    "claim": str(c["claim"])[:500],
                    "source_ids": [s for s in (c.get("source_ids") or []) if isinstance(s, str)][:4],
                    "evidence_summary": str(c.get("evidence_summary", ""))[:300],
                    "confidence": str(c.get("confidence", "limited_evidence")),
                    "status": "supported",
                })
        except Exception:
            claims = []
    # Fallback: per-source extractive claims (honest, traceable)
    if not claims:
        from ..providers.llm_template import TemplateAIProvider
        tpl = TemplateAIProvider()
        for s in sources[:25]:
            if not s.get("snippet"):
                continue
            for c in tpl.extract_claims(s["snippet"], s["source_id"], max_claims=2):
                claims.append({"claim_id": f"C{len(claims)+1:03d}", **c, "status": "supported"})
    # normalise confidence values
    valid = {"established", "strong_evidence", "limited_evidence", "active_debate",
             "plausible_hypothesis", "speculation"}
    for c in claims:
        if c.get("confidence") not in valid:
            c["confidence"] = "limited_evidence"
    return claims[:60]


def _audit(claims: list[dict], sources: list[dict]) -> tuple[list[dict], list[dict]]:
    contradictions: list[dict] = []
    # heuristic: claims sharing rare keywords but different confidence -> flag for review
    by_kw: dict[str, list[dict]] = {}
    for c in claims:
        for w in re.findall(r"[a-z]{6,}", c["claim"].lower()):
            by_kw.setdefault(w, []).append(c)
    seen = set()
    for w, cs in by_kw.items():
        confs = {c["confidence"] for c in cs}
        if len(cs) >= 2 and len(confs) >= 2 and w not in seen:
            seen.add(w)
            contradictions.append({
                "topic": w, "claim_ids": [c["claim_id"] for c in cs[:4]],
                "note": "Same topic described with different confidence levels — verify before scripting.",
            })
        if len(contradictions) >= 10:
            break
    uncertainty = [
        {"claim_id": c["claim_id"], "claim": c["claim"][:200], "confidence": c["confidence"],
         "guidance": "Qualify on screen / in narration; do not present as settled fact."}
        for c in claims if c["confidence"] in ("active_debate", "plausible_hypothesis", "speculation", "limited_evidence")
    ][:20]
    return contradictions, uncertainty


def _causal_chain(plan: dict, claims: list[dict]) -> list[str]:
    chain = [plan.get("interpretation", {}).get("central_question", "")]
    # order strongest-supported claims first as the backbone
    rank = {"established": 0, "strong_evidence": 1, "limited_evidence": 2,
            "active_debate": 3, "plausible_hypothesis": 4, "speculation": 5}
    ordered = sorted(claims, key=lambda c: rank.get(c["confidence"], 2))
    for c in ordered[:14]:
        s = c["claim"].strip().rstrip(".")
        if s and s not in chain:
            chain.append(s)
    return chain
