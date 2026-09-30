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


def interpret_idea(idea: str, instructions: str = "") -> dict:
    text = f"{idea} {instructions}".strip()
    # central question heuristic
    q = idea.strip()
    if "?" not in q:
        q = f"How does {idea.strip().rstrip('.')} actually work, and what is the evidence?"
    # key entities: capitalised phrases (minus sentence-case stopwords) + long nouns
    raw_ents = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", idea)
    ent_stop = {"How", "What", "Why", "When", "Where", "Which", "Explain", "Describe",
                "The", "This", "That", "Does", "Do\u2019s", "Dos", "And"}
    ents = [e for e in raw_ents if e not in ent_stop and len(e) >= 4]
    nouns = [w for w in re.findall(r"[a-zA-Z]{5,}", idea.lower())]
    return {
        "idea": idea, "instructions": instructions,
        "central_question": q,
        "entities": list(dict.fromkeys(ents))[:10],
        "keywords": list(dict.fromkeys(nouns))[:15],
    }


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
    budget = RESEARCH_DEPTHS[depth]
    # Stage 3: expand into research questions (LLM if available, else template)
    questions: list[str] = []
    if stack is not None:
        try:
            from ..providers.registry import ai_generate
            prompt = (
                f"IDEA: {idea}\nINSTRUCTIONS: {instructions}\nCENTRAL QUESTION: {interp['central_question']}\n\n"
                f"List {budget['questions']} specific research questions that would let a science "
                f"documentary explain this correctly and deeply (mechanisms, causes, evidence, "
                f"history, misconceptions, uncertainties). One per line, no numbering."
            )
            text, used = ai_generate(stack, prompt, system="You are a documentary research lead.",
                                     max_tokens=800)
            questions = [l.strip(" -•0123456789.)").strip() for l in text.splitlines()
                         if len(l.strip()) > 15][:budget["questions"]]
        except Exception:
            questions = []
    if len(questions) < 4:
        from ..providers.llm_template import TemplateAIProvider
        questions = TemplateAIProvider().expand_questions(idea, interp["central_question"])[:budget["questions"]]
    # Stage 4/5: background + causal chain scaffolds (refined after evidence)
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
