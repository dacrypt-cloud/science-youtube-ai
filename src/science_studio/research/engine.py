"""Stages 6-13: multi-source search, evidence extraction, cross-check,
contradictions, uncertainty, and the claim-evidence map.

Evidence strategy (generic, topic-independent):
1. TOPIC BACKBONE first: full reference articles for the topic's anchor terms,
   so the evidence base always has a coherent on-topic core.
2. Broad search across providers, gated by STRICT relevance (stem overlap >= 2
   against backbone-bootstrapped vocabulary + an anchor hit) and a minimum
   snippet length (thin/empty snippets are dropped, never used as evidence).
3. Full-text fetch for top sources until K substantive texts (failures recorded).
4. Extractive claims with hygiene + confidence calibration (corroboration /
   debate / hedge markers).
"""
from __future__ import annotations
import re, time
from collections import Counter

from ..providers.llm_template import stem, keywords as _kw


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


# Generic glue words that must NOT count as topical overlap for relevance.
# (Prevents off-topic papers matching on words like "before"/"inside".)
IDEA_STOP = {
    "before", "after", "inside", "outside", "actually", "really", "happens",
    "happen", "occurs", "between", "through", "during", "under", "about",
    "their", "there", "these", "those", "which", "while", "would", "could",
    "other", "using", "based", "effects", "effect", "study", "studies",
}
IDEA_STOP_STEMS = {stem(w) for w in IDEA_STOP}

MIN_SNIPPET = 80  # chars; thinner snippets are dropped, never evidence


def _text_stems(text: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-z]{4,}", (text or "").lower())} - IDEA_STOP_STEMS


def _relevant(title: str, snippet: str, vocab_stems: set[str],
              anchor_stems: set[str], source_type: str = "other") -> bool:
    """Strict topical gate (all source types): >=2 vocabulary-stem overlaps
    AND >=1 anchor-stem hit. Kills cross-domain homonyms
    (e.g. 'Lightning Search Algorithm' for a lightning storm topic)."""
    toks = _text_stems(f"{title} {snippet}")
    if len(toks & set(vocab_stems)) < 2:
        return False
    if anchor_stems and not (toks & set(anchor_stems)):
        return False
    return True


def run_research(plan: dict, stack, progress_cb=None) -> dict:
    interp0 = plan.get("interpretation", {}) or {}
    anchors = list(interp0.get("anchors") or [])
    if not anchors:
        from .planner import topic_anchors
        anchors = topic_anchors(interp0.get("idea", ""), interp0)
    anchor_stems = {stem(a) for a in anchors}
    questions = plan.get("research_questions", [])
    budget = plan.get("budget", {})
    per_q = int(budget.get("queries_per_question", 3))
    per_query = int(budget.get("sources_per_query", 5))
    max_sources = int(budget.get("max_sources", 30))

    sources: list[dict] = []
    seen_urls: set[str] = set()
    notes: list[str] = []
    fetched_pre: dict[str, str] = {}

    # ── 1) topic backbone: full reference articles for anchor terms ──
    backbone_stats = {"articles": 0, "chars": 0}
    backbone_vocab: set[str] = set()
    if not plan.get("skip_backbone"):
        try:
            from .backbone import fetch_topic_backbone
            bb_sources, bb_texts = fetch_topic_backbone(
                anchors, progress_cb=(lambda d, t, m: progress_cb(d, t, m)) if progress_cb else None)
            for bs in bb_sources:
                url = bs["url"]
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                sid = f"S{len(sources)+1:03d}"
                sources.append({"source_id": sid, **bs})
                fetched_pre[sid] = bb_texts[url]
                backbone_stats["articles"] += 1
                backbone_stats["chars"] += len(bb_texts[url])
                backbone_vocab |= _text_stems(bb_texts[url][:6000])
            if progress_cb:
                progress_cb(0, 1, f"backbone: {backbone_stats['articles']} articles "
                                  f"({backbone_stats['chars']} chars)")
        except Exception as e:
            notes.append(f"backbone skipped: {e}")

    # Relevance vocabulary: topic anchors + backbone-bootstrapped terms.
    vocab_stems = set(anchor_stems)
    if backbone_vocab:
        core = " ".join(fetched_pre.values())[:20000]
        for w in _kw(core, 15):
            vocab_stems.add(stem(w))
    else:  # no backbone: fall back to idea keywords
        idea_words = [w for w in (interp0.get("keywords") or []) if len(w) >= 4]
        vocab_stems |= {stem(w) for w in idea_words}

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

    # ── 2) broad multi-provider search ──
    total = len(queries) * len(stack.searchers)
    done = 0
    thin_dropped = 0
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
                    if not title or len(snippet) < MIN_SNIPPET:
                        thin_dropped += 1
                        continue
                    if not _relevant(title, snippet, vocab_stems, anchor_stems, stype):
                        continue
                    if backbone_vocab:
                        # drift gate: the source must speak the topic's language
                        # (>=3 backbone-vocabulary overlaps) — drops subtopic drift
                        # like ball-lightning/aircraft papers on a formation topic.
                        if len(_text_stems(f"{title} {snippet}") & backbone_vocab) < 3:
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
    if thin_dropped and progress_cb:
        progress_cb(total, total, f"dropped {thin_dropped} thin/empty snippets")

    # Rank: journals/agencies first, then reliability
    type_rank = {"journal": 0, "agency": 0, "university": 1, "database": 1,
                 "reference": 2, "preprint": 3, "news_science": 3, "other": 4}
    sources.sort(key=lambda s: (type_rank.get(s["source_type"], 4), -s["reliability"]))

    # ── 3) full-text pass: snippets are leads, fetched text is evidence ──
    fetched: dict[str, str] = dict(fetched_pre)
    fetch_stats = {"attempted": 0, "substantive": len(fetched),
                   "total_chars": sum(len(v) for v in fetched.values())}
    try:
        from .fetcher import fetch_for_sources
        q_stems = _text_stems(plan.get("interpretation", {}).get("central_question", ""))
        more = fetch_for_sources(
            sources, progress_cb=(lambda d, t, m: progress_cb(d, t, m)) if progress_cb else None,
            question_stems=q_stems)
        for sid, text in more.items():
            fetched.setdefault(sid, text)
        # Post-fetch content gate: fetched texts must speak the tier-1 core
        # language (top-50-stem core density >= 0.12) or they drop back to
        # snippet-only evidence (source kept as metadata, full text unused).
        if backbone_vocab:
            # distinctive core: backbone-lead stems repeated >=3x (topical
            # repetition, not generic one-off words like 'large'/'often').
            lead = " ".join(fetched_pre.values())[:12000].lower()
            _lf = Counter(stem(w) for w in re.findall(r"[a-z]{6,}", lead))
            core_freq = {w for w, n in _lf.items() if n >= 3}
            dropped = []
            for sid in list(more):
                toks = [stem(w) for w in re.findall(r"[a-z]{6,}", more[sid].lower())]
                top = [w for w, _ in Counter(toks).most_common(50)]
                dens = len(set(top) & core_freq) / max(1, len(top))
                if dens < 0.12:
                    dropped.append(sid)
                    fetched.pop(sid, None)
                    for s in sources:
                        if s.get("source_id") == sid:
                            s["fetch_error"] = f"content-gate: core-density {dens:.2f} < 0.12"
                            s["fetched_chars"] = 0
            if dropped and progress_cb:
                progress_cb(total, total, f"content-gate dropped {len(dropped)} drift texts")
        fetch_stats = {"attempted": sum(1 for s in sources if s.get("fetch_method")),
                       "substantive": len(fetched),
                       "total_chars": sum(len(v) for v in fetched.values())}
        if progress_cb:
            progress_cb(total, total,
                        f"fetched {fetch_stats['substantive']} full texts ({fetch_stats['total_chars']} chars)")
    except Exception as e:
        notes.append(f"full-text fetch skipped: {e}")

    blocks = []
    for s in sources:
        if not s["snippet"] and s["source_id"] not in fetched:
            continue
        # snippet first, attribution tail (stripped by template preclean, kept for LLM context)
        pub = s["publisher"] or "?"
        date = s.get("publication_date", "") or "?"
        body = s["snippet"]
        if s["source_id"] in fetched:
            body = (body + "\n" + fetched[s["source_id"]][:12000]).strip()
        # Titles are metadata, not prose: (see:) refs are stripped before any
        # sentence splitting, so titles can never become spoken narration.
        blocks.append(f"{body}\n(see: {s['title']}) [{s['source_id']}] ({pub}, {date}).")
    evidence_text = "\n\n".join(blocks)

    claims = _extract_claims(evidence_text, sources, stack, fetched, anchors)
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
        "fetch_stats": fetch_stats,
        "backbone_stats": backbone_stats,
    }


def _extract_claims(evidence_text: str, sources: list[dict], stack,
                    fetched: dict | None = None,
                    anchors: list[str] | None = None) -> list[dict]:
    claims: list[dict] = []
    fetched = fetched or {}
    # Try LLM structuring first
    valid_sids = {s["source_id"] for s in sources if s.get("source_id")}
    if stack is not None and evidence_text.strip():
        try:
            from ..providers.registry import ai_generate
            from ..providers.openai_compat import extract_json_array
            prompt = (
                "From the RESEARCH NOTES below, extract the 15-30 most important factual claims "
                "for a science documentary. For each: claim (one sentence), evidence_summary "
                "(<=40 words), confidence (one of: established, strong_evidence, limited_evidence, "
                "active_debate, plausible_hypothesis, speculation), source_ids (list of IDs like \"S001\" from brackets).\n"
                "Return ONLY a JSON array of objects with keys claim, evidence_summary, confidence, source_ids.\n\n"
                f"RESEARCH NOTES:\n{evidence_text[:12000]}"
            )
            text, used = ai_generate(stack, prompt,
                                     system="You extract verifiable claims. Never invent sources.",
                                     max_tokens=2800)
            if used == "template-fallback":
                raise RuntimeError("skip template claim json")
            arr = extract_json_array(text)
            for c in arr:
                if not isinstance(c, dict) or not c.get("claim"):
                    continue
                raw_ids = c.get("source_ids") or []
                if isinstance(raw_ids, str):
                    raw_ids = [raw_ids]
                sids = []
                for sid in raw_ids:
                    if isinstance(sid, str):
                        clean_sid = sid.strip("[]() ,;\"'")
                        if clean_sid in valid_sids and clean_sid not in sids:
                            sids.append(clean_sid)
                if not sids:
                    continue  # never accept unsourced LLM claims
                claims.append({
                    "claim_id": f"C{len(claims)+1:03d}",
                    "claim": str(c["claim"])[:500],
                    "source_ids": sids[:4],
                    "evidence_summary": str(c.get("evidence_summary", ""))[:300],
                    "confidence": str(c.get("confidence", "limited_evidence")),
                    "status": "supported",
                })
            if len(claims) < 8:
                claims = []  # too few valid sourced claims; use full extractive set
        except Exception:
            claims = []
    # Fallback: per-source extractive claims (honest, traceable).
    # Prefer fetched full text over snippets whenever available.
    if not claims:
        from ..providers.llm_template import TemplateAIProvider
        tpl = TemplateAIProvider()
        for s in sources[:25]:
            full = (fetched.get(s["source_id"], "") or "")[:6000]
            text = full if len(full) > 300 else (s.get("snippet") or "")
            if not text:
                continue
            # richer texts yield more claims (fetched core dominates snippets)
            mc = 6 if len(full) > 3000 else (3 if full else 2)
            for c in tpl.extract_claims(text, s["source_id"], max_claims=mc,
                                        anchors=anchors):
                claims.append({"claim_id": f"C{len(claims)+1:03d}", **c, "status": "supported"})
    # normalise confidence values
    valid = {"established", "strong_evidence", "limited_evidence", "active_debate",
             "plausible_hypothesis", "speculation"}
    for c in claims:
        if c.get("confidence") not in valid:
            c["confidence"] = "limited_evidence"
    claims = claims[:60]
    # Drift filter: when a backbone exists, claims must connect to the topic
    # core (>=3 shared 6+ letter stems with backbone full text). Always keeps
    # the 12 most-connected claims so recall never collapses.
    bb_ids = {s.get("source_id", "") for s in sources if s.get("via") == "wikipedia-backbone"}
    # Tier-1 core: article LEADS (first ~6k chars), where reference articles put
    # the definitional core — not late sections (trivia, culture, other planets).
    bb_text = " ".join(fetched.get(sid, "")[:6000] for sid in bb_ids)
    if bb_text.strip() and len(claims) > 12:
        core = {stem(w) for w in re.findall(r"[a-zA-Z]{6,}", bb_text.lower())}

        def _conn(c: dict) -> int:
            return len({stem(w) for w in re.findall(r"[a-zA-Z]{6,}",
                        c.get("claim", "").lower())} & core)

        ranked = sorted(claims, key=_conn, reverse=True)
        keep = [c for c in ranked if _conn(c) >= 3]
        # top-connected claims only (ranked order = core-first for scripting)
        claims = keep[:24] if len(keep) >= 12 else ranked[:12]
    # Narrative phase sort (generic): definitional claims open, mechanism fills
    # the middle, consequences/open-questions close. Beats are positional, so
    # positional claim order = narrative order.
    claims.sort(key=lambda c: _claim_phase(c.get("claim", "")))  # stable: keeps conn order in phase
    _calibrate_confidence(claims, sources, anchors)
    return claims


_DEBATE_RE = re.compile(
    r"\b(debat|controvers|disagre|disput|unknown|unclear|uncertain|myster|"
    r"paradox|unresolved|elusive|poorly understood)\w*\b", re.I)
_HEDGE_RE = re.compile(
    r"\b(may|might|could|suggest|suggests|hypothes|believed|thought to|"
    r"likely|possibly|potential|appears to|seems to)\b", re.I)


_DEF_RE = re.compile(
    r"\b(is a|is an|are defined|refers to|consists of|defined as|known as|"
    r"is the process|is a natural|is one of)\b", re.I)
_CLOSE_RE = re.compile(
    r"\b(future|remains|remaining|unknown|debate|debated|mystery|mysteries|"
    r"protect|protection|prevent|application|applications|impact|impacts|"
    r"climate|death|deaths|fatal|fatalit|injur|damage|threat|risk|"
    r"harvest|benefit|warning|forecast)\w*\b", re.I)


def _claim_phase(claim: str) -> int:
    """Narrative phase: 0 definitional (opens), 1 mechanism (middle, default),
    2 consequences/open-questions (closes). Generic documentary logic."""
    if _DEF_RE.search(claim or ""):
        return 0
    if _CLOSE_RE.search(claim or ""):
        return 2
    return 1


def _claim_sig(claim: str, anchor_stems: set[str] | None = None) -> set[str]:
    """Specific-word signature for corroboration matching.

    Generic topic words (the anchors) are excluded: every claim shares them,
    so they must not count as corroboration. Only SPECIFIC shared words
    (graupel, leader, avalanche...) corroborate.
    """
    sig = {stem(w) for w in re.findall(r"[a-zA-Z]{7,}", (claim or "").lower())}
    return sig - (set(anchor_stems) if anchor_stems else set())


def _calibrate_confidence(claims: list[dict], sources: list[dict] | None = None,
                          anchors: list[str] | None = None) -> None:
    """Deterministic confidence calibration (documented, auditable):

    - explicit debate/uncertainty language -> active_debate
    - same signature in claims from >=2 DIFFERENT source TYPES
      (e.g. reference + journal) -> strong_evidence
    - hedged + single-source -> plausible_hypothesis
    - otherwise limited_evidence (honest default for extractive claims)
    """
    stype = {s.get("source_id", ""): s.get("source_type", "other") for s in (sources or [])}

    def _types(c: dict) -> set[str]:
        return {stype.get(sid, "?") for sid in c.get("source_ids", [])}

    anchor_stems = {stem(w) for a in (anchors or [])
                    for w in re.findall(r"[a-zA-Z]{4,}", a.lower())}
    sigs = [_claim_sig(c.get("claim", ""), anchor_stems) for c in claims]
    for i, c in enumerate(claims):
        text = c.get("claim", "")
        if _DEBATE_RE.search(text):
            c["confidence"] = "active_debate"
            continue
        corroborated = False
        my_src = set(c.get("source_ids", []))
        my_types = _types(c)
        for j, other in enumerate(claims):
            if i == j or not sigs[i] or not sigs[j]:
                continue
            if set(other.get("source_ids", [])) & my_src:
                continue
            if not (_types(other) - my_types):
                continue  # same source type: agreement, not independence
            if len(sigs[i] & sigs[j]) >= 2:
                corroborated = True
                break
        if corroborated:
            c["confidence"] = "strong_evidence"
        elif _HEDGE_RE.search(text):
            c["confidence"] = "plausible_hypothesis"
        else:
            c["confidence"] = "limited_evidence"


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
