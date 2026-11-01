"""Storytelling engine — picks a documentary structure that serves the science."""
from __future__ import annotations

STRUCTURES = {
    "mystery_investigation": ["Hook: the mystery", "Clues from observation", "Investigation: mechanisms",
                              "Key experiment / evidence", "Resolution", "What remains unknown"],
    "question_evidence": ["Hook: the question", "Why it matters", "What the evidence shows",
                          "How it works (mechanism)", "Misconceptions corrected", "Takeaway"],
    "historical_modern": ["Hook from history", "The discovery story", "What they got right/wrong",
                          "Modern mechanism", "Current frontiers", "Takeaway"],
    "journey_process": ["Hook: follow the journey", "Stage 1", "Stage 2", "Stage 3", "Stage 4",
                        "Where it ends / why it matters"],
    "cause_mechanism": ["Hook: surprising consequence", "The cause", "The mechanism step by step",
                        "The consequence explained", "What can change it", "Takeaway"],
    "misconception_correction": ["Hook: what most people believe", "Why it seems plausible",
                                 "What the evidence actually shows", "The real mechanism",
                                 "Why the myth persists", "Takeaway"],
    "visible_to_molecular": ["Hook: what you can see", "Zooming in: microscopic",
                             "Deeper: cellular", "Deepest: molecular", "Back out: meaning", "Takeaway"],
    "experiment_result": ["Hook: the experiment", "The setup", "The result",
                          "The explanation", "What it changed", "Takeaway"],
}


STORY_SYSTEM = (
    "You are a documentary story editor. Beat titles must build an arc: promise "
    "payoff, escalate curiosity, vary shape (questions, stakes, revelations). "
    "Keep each under 10 words, topic-specific, no generic labels."
)


def pick_structure(causal_chain: list[str], idea: str, stack=None) -> tuple[str, list[str]]:
    text = (idea + " " + " ".join(causal_chain[:6])).lower()
    if any(w in text for w in ("life cycle", "travel", "inside", "through", "journey", "stage", "transmit")):
        key = "journey_process"
    elif any(w in text for w in ("myth", "misconception", "wrong", "actually", "really")):
        key = "misconception_correction"
    elif any(w in text for w in ("discover", "history", "19", "century", "nobel")):
        key = "historical_modern"
    elif any(w in text for w in ("mystery", "unknown", "puzzle", "strange")):
        key = "mystery_investigation"
    elif any(w in text for w in ("molecule", "cell", "microscop", "atom", "protein", "gene")):
        key = "visible_to_molecular"
    elif any(w in text for w in ("experiment", "trial", "study found")):
        key = "experiment_result"
    elif any(w in text for w in ("cause", "leads to", "results in", "because")):
        key = "cause_mechanism"
    else:
        key = "question_evidence"
    beats = list(STRUCTURES[key])
    # A real LLM may refine beat titles to the topic (optional). The extractive
    # template fallback must NOT rewrite beats (it would echo prompt sentences).
    if stack is not None:
        try:
            from ..providers.registry import ai_generate
            prompt = (f"Topic: {idea}\nStructure: {key} with beats {beats}\n"
                      f"Rewrite the {len(beats)} beat titles for this exact topic as a "
                      f"curiosity arc (hook -> escalate -> payoff). One per line, no numbering.")
            import re as _re
            t, used = ai_generate(stack, prompt, system=STORY_SYSTEM,
                                  max_tokens=1000)
            if used == "template-fallback":
                return key, beats
            t = _re.sub(r"<think>.*?</think>", "", t, flags=_re.S | _re.I)
            lines = [l.strip(" -•0123456789.)").strip() for l in t.splitlines() if l.strip()]
            if len(lines) >= 4:
                beats = lines[:len(beats)]
        except Exception:
            pass
    return key, beats
