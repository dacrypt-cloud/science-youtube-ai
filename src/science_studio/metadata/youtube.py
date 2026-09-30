"""YouTube metadata — titles, description, chapters, tags. Accurate, no clickbait."""
from __future__ import annotations


def _chapters(storyboard: list[dict], durations: dict[str, float]) -> list[dict]:
    out, t = [], 0.0
    for sc in storyboard:
        out.append({"at_s": int(t), "at": f"{int(t//60):02d}:{int(t%60):02d}", "title": sc["title"]})
        t += float(durations.get(sc["scene_id"], 0) or 0)
    return out


def build_metadata(idea: str, storyboard: list[dict], durations: dict[str, float],
                   claims: list[dict], sources: list[dict], stack=None) -> dict:
    chapters = _chapters(storyboard, durations)
    total = sum(durations.values())
    titles = [f"{idea.strip().rstrip('?')} — Explained with Evidence",
              f"The Science of {idea.strip()[:60]}",
              f"{idea.strip().rstrip('?')}? What the Research Shows"]
    desc_lines = [
        idea.strip(), "",
        "A deeply researched science explainer. Every major claim is traced to sources below.",
        "", "CHAPTERS:",
        *[f"{c['at']} — {c['title']}" for c in chapters],
        "", "SOURCES & FURTHER READING:",
    ]
    by_id = {s["source_id"]: s for s in sources}
    used = set()
    for c in claims:
        used.update(c.get("source_ids", []))
    for sid in sorted(used):
        s = by_id.get(sid)
        if s:
            desc_lines.append(f"[{sid}] {s['title']} — {s['url']}")
    desc_lines += ["", "VOICES/MEDIA: narration via free TTS; visuals: Wikimedia Commons / Pexels / "
                        "Pixabay / project-generated diagrams (see credits file).",
                   "Uncertainty is stated where the evidence is limited — see claims file."]
    tags = list(dict.fromkeys((idea.replace("?", "").split() + ["science", "explained",
              "documentary", "research", "evidence"]) ))[:15]
    meta = {"titles": titles, "description": "\n".join(desc_lines)[:4800],
            "chapters": chapters, "tags": tags,
            "hashtags": "#science #explained #research",
            "duration_s": total, "sources_count": len(sources), "claims_count": len(claims)}
    if stack is not None:
        try:
            from ..providers.registry import ai_generate
            prompt = (f"Topic: {idea}\nWrite 3 accurate YouTube titles (<=70 chars, no clickbait) "
                      f"and 1 two-sentence hook for the description. Format:\nT1: ...\nT2: ...\nT3: ...\nHOOK: ...")
            t, _ = ai_generate(stack, prompt, system="You write honest science titles.", max_tokens=250)
            ts = []
            for line in t.splitlines():
                if line.strip().upper().startswith("T") and ":" in line:
                    ts.append(line.split(":", 1)[1].strip()[:70])
                if line.strip().upper().startswith("HOOK:"):
                    meta["hook"] = line.split(":", 1)[1].strip()[:300]
            if len(ts) >= 2:
                meta["titles"] = ts[:3]
        except Exception:
            pass
    return meta
