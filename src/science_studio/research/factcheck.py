"""Stage 17: second fact-check pass on the finished script."""
from __future__ import annotations
import re


BANNED_HYPE = [
    "miracle", "proven to cure", "scientists are shocked", "shocked the world",
    "100% effective", "definitely causes", "definitely cures", "instantly",
]
ABSOLUTE_RE = re.compile(r"\b(always|never|all scientists|everyone knows|proven that)\b", re.I)
NUMBER_RE = re.compile(r"\b[\d,]+(?:\.\d+)?\s*(?:%|percent|million|billion|thousand|km|kg|°C|°F|degrees)\b")


def _norm_num(n: str) -> str:
    return n.lower().replace(",", "").replace(" ", "")


def factcheck_script(script_text: str, claims: list[dict], stack=None) -> dict:
    issues: list[dict] = []
    claim_blob = _norm_num(" ".join(c["claim"] for c in claims))
    sentences = re.split(r"(?<=[.!?])\s+", script_text)
    for i, s in enumerate(sentences):
        sl = s.lower().strip()
        if len(sl) < 25:
            continue
        for hype in BANNED_HYPE:
            if hype in sl:
                issues.append({"type": "hype", "sentence": s[:220],
                               "fix": f"Remove/soften '{hype}' — not supported by evidence language."})
        if ABSOLUTE_RE.search(s):
            # allow if clearly supported by an established claim
            if "always" not in claim_blob and "never" not in claim_blob:
                issues.append({"type": "absolute", "sentence": s[:220],
                               "fix": "Soften absolute ('always/never/proven') unless an established claim backs it."})
        if NUMBER_RE.search(s):
            nums = NUMBER_RE.findall(s)
            if not any(_norm_num(n) in claim_blob for n in nums):
                issues.append({"type": "number_unverified", "sentence": s[:220],
                               "fix": f"Verify numbers {nums} against sources or remove."})
    # coverage: every scene-critical claim should appear; flag orphan high-confidence claims
    orphans = []
    joined = script_text.lower()
    for c in claims[:20]:
        key_words = [w for w in re.findall(r"[a-z]{6,}", c["claim"].lower())][:3]
        if key_words and not any(w in joined for w in key_words):
            orphans.append(c["claim_id"])
    # Real-LLM second-opinion pass (optional, non-fabricating: only flags).
    # Skipped for the extractive template fallback (it would echo script lines).
    llm_notes: list[str] = []
    if stack is not None:
        try:
            from ..providers.registry import ai_generate
            prompt = ("You are a science fact-checker. List concrete problems in this script "
                      "(unsupported statements, exaggerations, missing qualifiers, wrong causality, "
                      "terminology errors). Quote the exact phrase, then the fix. If none, say NONE.\n\n"
                      f"SCRIPT:\n{script_text[:12000]}")
            text, used = ai_generate(stack, prompt, max_tokens=1200)
            if used != "template-fallback" and text.strip().upper() != "NONE":
                llm_notes = [l.strip() for l in text.splitlines() if len(l.strip()) > 10][:20]
        except Exception:
            pass
    status = "pass" if not issues and not llm_notes else ("review" if len(issues) < 8 else "fail")
    return {"status": status, "issues": issues[:40], "orphan_claims": orphans[:10],
            "llm_notes": llm_notes, "sentences_checked": len(sentences)}


def apply_autofixes(script_text: str, report: dict) -> str:
    fixed = script_text
    for hype in BANNED_HYPE:
        fixed = re.sub(re.escape(hype), "may help explain", fixed, flags=re.I)
    fixed = re.sub(r"\bproven that\b", "evidence suggests that", fixed, flags=re.I)
    fixed = re.sub(r"\ball scientists agree\b", "most researchers agree", fixed, flags=re.I)
    return fixed
