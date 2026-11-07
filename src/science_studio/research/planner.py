"""Stages 1-5 + depth controller: interpret idea, central question, research
questions, background needs, causal chain, and dynamic depth."""
from __future__ import annotations
import re

RESEARCH_DEPTHS = {
    "shallow": {"questions": 5, "queries_per_question": 2, "sources_per_query": 4, "max_sources": 15},
    "standard": {"questions": 8, "queries_per_question": 3, "sources_per_query": 5, "max_sources": 30},
    "deep": {"questions": 12, "queries_per_question": 4, "sources_per_query": 6, "max_sources": 50},
    "exhaustive": {"questions": 16, "queries_per_question": 5, "sources_per_query": 8, "max_sources": 80},
}

COMPLEXITY_HINTS = [
    (r"\b(how|why|mechanism|process|pathway|enzyme|quantum|relativ|evolution|climate|immune|neuro)\b", 2),
    (r"\b(and|vs|versus|compared|relationship|effect on|feedback)\b", 1),
    (r"\b(history|discover|experiment|evidence|controvers|debat|uncertain|mystery)\b", 1),
    (r"\b(molecular|cellular|atomic|particle|gene|protein|parasite|virus|bacteria)\b", 2),
    (r"\?", 1),
]

# Words that carry no topical signal (questions, glue, weak verbs, YouTube-title superlatives).
ANCHOR_STOP = {
    "how", "what", "why", "when", "where", "which", "who", "whom", "whose",
    "does", "do", "did", "is", "are", "was", "were", "been", "being", "have",
    "has", "had", "actually", "really", "very", "just", "inside", "outside",
    "before", "after", "between", "through", "during", "under", "about",
    "happens", "happen", "occurs", "occur", "with", "from", "that", "this",
    "into", "over", "such", "than", "then", "them", "they", "their", "there",
    "these", "those", "while", "would", "could", "should", "more", "most",
    "other", "some", "using", "used", "make", "makes", "making", "made",
    "take", "takes", "taking", "know", "known", "part", "form", "forms",
    "work", "works", "working", "explain", "explained",
    "become", "becomes", "becoming", "became", "getting", "gets",
    "best", "worst", "biggest", "largest", "smallest", "fastest", "slowest",
    "dangerous", "deadliest", "scariest", "strangest", "weirdest", "amazing",
    "top", "ways", "things", "reasons", "facts", "secrets", "secret", "truth",
    "guide", "ultimate", "simple", "easy", "fast", "quickly", "ever", "every",
    "never", "always", "people", "person", "human", "world", "life", "need",
    "needs", "start", "starting", "stop", "stopping",
}

# Bridge colloquial / abbreviated YouTube phrasing to canonical encyclopedic &
# research terminology so search + relevance gates work on everyday titles too.
CONCEPT_BRIDGES: list[tuple[set[str], list[str], list[str]]] = [
    (
        {"rich", "wealthy", "millionaire", "billionaires", "millionaires", "billionaire", "wealth"},
        ["wealth", "income", "savings", "investment", "capital"],
        ["Wealth", "Distribution of wealth", "Economic mobility", "Personal finance"],
    ),
    (
        {"money", "invest", "investing", "passive", "financial", "finance"},
        ["finance", "investment", "income", "compound", "market"],
        ["Personal finance", "Investment", "Compound interest"],
    ),
    (
        {"crypto", "bitcoin", "ethereum", "blockchain", "defi"},
        ["cryptocurrency", "blockchain", "bitcoin", "security", "decentralized"],
        ["Cryptocurrency", "Cryptocurrency crime", "Blockchain", "Smart contract"],
    ),
    (
        {"hack", "hacks", "hacked", "hacker", "hackers", "cyber", "exploit", "breach"},
        ["security", "vulnerability", "exploit", "attack", "breach"],
        ["Cyberattack", "Vulnerability (computing)", "Cryptocurrency crime"],
    ),
]


def _central_question(idea: str) -> str:
    q = " ".join((idea or "").split()).strip()
    if "?" in q:
        return q
    low = q.lower()
    if low.startswith(("how to ", "how do ", "how does ", "how can ", "why do ", "why does ", "why is ", "what is ", "what are ")):
        return q.rstrip(".") + " — what does empirical evidence actually show?"
    if re.match(r"^(top\s+\d+|the\s+\d+|\d+\s+most)\b", low):
        return f"What are the mechanisms, causes, and documented evidence behind {q.rstrip('.')}?"
    return f"How does {q.rstrip('.')} actually work, and what is the evidence?"


def interpret_idea(idea: str, instructions: str = "") -> dict:
    q = _central_question(idea)
    raw_ents = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", idea)
    ent_stop = {
        "How", "What", "Why", "When", "Where", "Which", "Explain", "Describe",
        "The", "This", "That", "Does", "Do\u2019s", "Dos", "And", "Top", "Most",
        "Best", "Worst", "Become", "Becoming", "Dangerous", "Secret", "Secrets",
        "Guide", "Ways", "Things", "Reasons",
    }
    cleaned_ents = []
    for e in raw_ents:
        kept_words = [w for w in e.split() if w not in ent_stop and w.lower() not in ANCHOR_STOP]
        phrase = " ".join(kept_words).strip()
        if len(phrase) >= 4:
            cleaned_ents.append(phrase)
    nouns = [w for w in re.findall(r"[a-zA-Z]{4,}", idea.lower()) if w not in ANCHOR_STOP]

    # Trigger deterministic colloquial -> research concept bridges when matched
    idea_toks = set(re.findall(r"[a-zA-Z]{3,}", idea.lower()))
    backbone_queries: list[str] = []
    bridged_terms: list[str] = []
    for triggers, extra_anchors, wiki_titles in CONCEPT_BRIDGES:
        if idea_toks & triggers:
            bridged_terms.extend(extra_anchors)
            for wt in wiki_titles:
                if wt not in backbone_queries:
                    backbone_queries.append(wt)

    anchors = topic_anchors(idea, {"entities": cleaned_ents, "keywords": nouns + bridged_terms})
    if not backbone_queries:
        # Multi-word cleaned topic phrase first, then individual anchors
        clean_phrase = " ".join(w for w in re.findall(r"[A-Za-z]{3,}", idea)
                                if w.lower() not in ANCHOR_STOP and not w.isdigit())
        if len(clean_phrase) >= 4:
            backbone_queries.append(clean_phrase)
    return {
        "idea": idea,
        "instructions": instructions,
        "central_question": q,
        "entities": list(dict.fromkeys(cleaned_ents))[:10],
        "keywords": list(dict.fromkeys(nouns + bridged_terms))[:15],
        "anchors": anchors,
        "backbone_queries": backbone_queries[:6],
    }


def topic_anchors(idea: str, interp: dict | None = None, n: int = 12) -> list[str]:
    """Distinctive topic words used for backbone lookup, relevance, and hygiene.

    Generic: content words of the idea + entity words + concept bridges, minus stopwords.
    """
    interp = interp or {}
    words = [w for w in re.findall(r"[A-Za-z]{4,}", (idea or "").lower())
             if w not in ANCHOR_STOP]
    for e in (interp.get("entities") or []):
        for w in re.findall(r"[A-Za-z]{4,}", e.lower()):
            if w not in ANCHOR_STOP:
                words.append(w)
    for w in (interp.get("keywords") or []):
        wl = w.lower()
        if len(wl) >= 4 and wl not in ANCHOR_STOP:
            words.append(wl)
    # Also apply concept bridges directly when topic_anchors(idea) is called standalone (e.g. QA)
    idea_toks = set(re.findall(r"[a-zA-Z]{3,}", (idea or "").lower()))
    for triggers, extra_anchors, _ in CONCEPT_BRIDGES:
        if idea_toks & triggers:
            for w in extra_anchors:
                if len(w) >= 4 and w not in ANCHOR_STOP:
                    words.append(w)
    return list(dict.fromkeys(words))[:n]


def depth_for(idea: str, duration: str, requested_depth: str = "auto") -> str:
    if requested_depth in RESEARCH_DEPTHS:
        return requested_depth
    score = sum(w for pat, w in COMPLEXITY_HINTS for _ in re.finditer(pat, idea, re.I))
    score += len(idea.split()) // 25
    if duration.startswith("15") or duration == "15-20":
        score += 3
    elif duration.startswith("12"):
        score += 2
    if score >= 10:
        return "exhaustive"
    if score >= 6:
        return "deep"
    if score >= 3:
        return "standard"
    return "shallow"


def plan_research(idea: str, instructions: str = "", duration: str = "12-15",
                  requested_depth: str = "auto", stack=None) -> dict:
    interp = interpret_idea(idea, instructions)
    depth = depth_for(idea, duration, requested_depth)
    budget = dict(RESEARCH_DEPTHS[depth])
    questions: list[str] = []
    if stack is not None:
        try:
            from ..providers.registry import ai_generate
            prompt = (
                f"IDEA: {idea}\nINSTRUCTIONS: {instructions}\nCENTRAL QUESTION: {interp['central_question']}\n\n"
                f"First, write a line starting with `WIKI_TOPICS:` listing 3 exact encyclopedic/scientific "
                f"Wikipedia article titles that provide the core factual foundation for this topic (comma-separated).\n"
                f"Then list {budget['questions']} specific research questions that let an evidence-based "
                f"documentary explain this deeply (mechanisms, causes, empirical data, history, "
                f"misconceptions, uncertainties). One per line, no numbering."
            )
            text, used = ai_generate(stack, prompt, system="You are a documentary research lead.",
                                     max_tokens=1200)
            if used == "template-fallback":
                raise RuntimeError("skip template questions")
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I)
            q_lines = []
            for raw_l in text.splitlines():
                l = raw_l.strip()
                if l.upper().startswith("WIKI_TOPICS:"):
                    wt_part = l.split(":", 1)[1]
                    for wt in [x.strip(" -•\"'") for x in wt_part.split(",") if len(x.strip()) >= 3]:
                        if wt not in interp["backbone_queries"]:
                            interp["backbone_queries"].insert(0, wt)
                        for w in re.findall(r"[A-Za-z]{4,}", wt.lower()):
                            if w not in ANCHOR_STOP and w not in interp["anchors"]:
                                interp["anchors"].append(w)
                    interp["backbone_queries"] = interp["backbone_queries"][:6]
                    interp["anchors"] = interp["anchors"][:14]
                else:
                    cl = l.strip(" -•0123456789.)").strip()
                    if len(cl) > 15:
                        q_lines.append(cl)
            questions = q_lines[:budget["questions"]]
        except Exception:
            questions = []
    if len(questions) < 4:
        from ..providers.llm_template import TemplateAIProvider
        questions = TemplateAIProvider().expand_questions(idea, interp["central_question"])[:budget["questions"]]
    background = [
        "Core vocabulary and definitions the viewer needs first",
        "Scale and context (where/when/how big/how fast)",
        "Prerequisite mechanisms from neighbouring fields",
    ]
    causal_seed = [idea, interp["central_question"]]
    return {
        "interpretation": interp, "depth": depth, "budget": budget,
        "research_questions": questions, "background_needs": background,
        "causal_seed": causal_seed,
    }
