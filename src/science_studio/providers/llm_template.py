"""Deterministic fallback 'AI' — real extractive/templated generation, $0, offline.

This is NOT a fake LLM: it performs genuine text processing (sentence scoring,
keyword extraction, outline assembly) so the pipeline works with zero API keys.
Quality is lower than Gemini; the provider name is always recorded so outputs
are honest about how they were produced.
"""
from __future__ import annotations
import re
from collections import Counter
from .base import AIProvider, ProviderStatus


STOP = set("""a an the and or but if then else when while of at by for with about into
through during before after above below to from up down in out on off over under again
further once here there all any both each few more most other some such no nor not only
own same so than too very can will just don should now is are was were be been being
have has had having do does did doing would could ought i you he she it we they them
his her its our their this that these those as than""".split())


def keywords(text: str, n: int = 12) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
    c = Counter(w for w in words if w not in STOP)
    return [w for w, _ in c.most_common(n)]


def _preclean(text: str) -> str:
    # remove source attribution tails like: [S018] (Publisher, 2026).
    text = re.sub(r"\[[A-Z]\d{2,4}\]", " ", text)
    text = re.sub(r"\(\s*[^,()\n]{0,60},\s*(\?|\d{4})\s*\)\.?", " ", text)
    text = re.sub(r"\bABSTRACT\b:? ?", " ", text)
    return text


def split_sentences(text: str) -> list[str]:
    text = _preclean(text)
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    out = []
    for p in parts:
        p = p.strip()
        # drop truncated fragments (no terminal punctuation, cut mid-word)
        if len(p) > 40 and p[-1:] in ".!?":
            out.append(p)
    return out


def score_sentences(sentences: list[str], keys: list[str]) -> list[tuple[float, str]]:
    kset = set(keys)
    out = []
    for s in sentences:
        toks = set(re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", s.lower()))
        overlap = len(toks & kset)
        # prefer medium-length informative sentences
        length_pen = 1.0 if 60 < len(s) < 300 else 0.6
        out.append((overlap * length_pen, s))
    out.sort(reverse=True, key=lambda x: x[0])
    return out


class TemplateAIProvider(AIProvider):
    name = "template-fallback"

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, True, True, "always available, offline, deterministic")

    # The research/story modules call targeted helpers below rather than free-form
    # generation, which keeps output structured.
    def generate(self, prompt: str, *, system: str = "", max_tokens: int = 2000,
                 temperature: float = 0.4) -> str:
        # Generic handler: extractive summary of whatever context is embedded.
        sents = split_sentences(prompt)
        if not sents:
            return "No content available to summarize."
        keys = keywords(prompt)
        ranked = score_sentences(sents, keys)
        budget = max(300, min(max_tokens * 4, 6000))
        out, total = [], 0
        for _, s in ranked:
            if total + len(s) > budget:
                break
            out.append(s)
            total += len(s)
        return " ".join(out) if out else sents[0]

    # ── structured helpers used by pipeline stages ──
    def expand_questions(self, idea: str, central: str) -> list[str]:
        base = central or idea
        return [
            f"What is the core mechanism behind {base}?",
            f"What causes {base}, step by step?",
            f"What background concepts are needed to understand {base}?",
            f"What evidence supports the current understanding of {base}?",
            f"What are common misconceptions about {base}?",
            f"What remains uncertain or debated about {base}?",
            f"What is the history of discovery for {base}?",
            f"Why does {base} matter, and what are its consequences?",
        ]

    def extract_claims(self, text: str, source_id: str, max_claims: int = 10) -> list[dict]:
        sents = split_sentences(text)
        keys = keywords(text)
        ranked = score_sentences(sents, keys)[:max_claims]
        claims = []
        for i, (_, s) in enumerate(ranked):
            claims.append({
                "claim": s,
                "evidence_summary": s[:220],
                "confidence": "limited_evidence",
                "source_ids": [source_id],
            })
        return claims

    def assemble_script(self, scenes_outline: list[dict], evidence: str, target_words: int) -> list[dict]:
        """Build narration per scene from evidence sentences most relevant to
        each scene's title/claims (extractive, grounded, non-repeating)."""
        import re as _re
        sents = split_sentences(evidence)
        if not sents:
            sents = ["Research is still being gathered for this topic."]
        per_scene = max(60, target_words // max(1, len(scenes_outline)))
        word_cap = int(per_scene * 1.25)
        sents_per_scene = max(3, per_scene // 18)
        used: set[str] = set()
        out = []
        for sc in scenes_outline:
            title_keys = set(_re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}",
                                         (sc.get("title", "") + " " + " ".join(sc.get("claim_ids", []))).lower()))
            # rank by title overlap first, then global keywords
            keys = keywords(evidence)
            kset = set(keys)
            scored = []
            for s in sents:
                if s in used:
                    continue
                toks = set(_re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", s.lower()))
                title_hit = len(toks & title_keys)
                key_hit = len(toks & kset)
                scored.append((title_hit * 3 + key_hit, s))
            scored.sort(reverse=True, key=lambda x: x[0])
            chunk = []
            for _, s in scored[:sents_per_scene]:
                chunk.append(s)
                used.add(s)
            if len(chunk) < 2:  # recycle least-used if evidence is thin
                for s in sents:
                    if s not in chunk:
                        chunk.append(s)
                    if len(chunk) >= sents_per_scene:
                        break
            title = sc.get("title", "Next")
            narration = f"{title}. " + " ".join(chunk)
            words = narration.split()
            if len(words) > word_cap:
                narration = " ".join(words[:word_cap])
                if "." in narration:
                    narration = narration.rsplit(".", 1)[0] + "."
            out.append({**sc, "narration": narration})
        return out
