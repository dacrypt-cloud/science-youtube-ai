"""Thumbnail concept + render (Pillow, 1280x720). One clear question, no clickbait."""
from __future__ import annotations
from pathlib import Path


def concept(idea: str, claims: list[dict], stack=None) -> dict:
    # Short idea-derived question (claims are long; idea is the hook).
    words = idea.strip().rstrip("?").split()[:7]
    while len(words) > 3 and words[-1].lower().strip(",;:") in (
            "and", "or", "the", "a", "an", "of", "to", "in", "on",
            "for", "with", "from", "what", "that", "this", "is"):
        words.pop()
    short = " ".join(words).rstrip(",;:")
    question = short if short.endswith("?") else f"{short}?"
    hook = idea
    for c in claims:
        if c.get("confidence") in ("established", "strong_evidence") and len(c["claim"]) > 40:
            hook = c["claim"]
            break
    concept_d = {"text": question[:60], "subtext": "The science, explained",
                 "visual": f"diagram/stock composite about: {idea[:80]}",
                 "layout": "left text (yellow/white on dark), right visual", "hook_claim": hook[:200]}
    if stack is not None:
        try:
            from ..providers.registry import ai_generate
            prompt = (f"Topic: {idea}\nHook claim: {hook[:300]}\nWrite a YouTube thumbnail: "
                      f"TEXT (<=6 words, accurate, curious), SUBTEXT (<=5 words). Two lines: TEXT: ... SUBTEXT: ...")
            import re as _re
            t, used = ai_generate(stack, prompt, system="You write honest science thumbnails.", max_tokens=900)
            if used == "template-fallback":
                raise RuntimeError("skip template thumbnail")
            t = _re.sub(r"<think>.*?</think>", "", t, flags=_re.S | _re.I)
            for line in t.splitlines():
                if line.upper().startswith("TEXT:"):
                    concept_d["text"] = line.split(":", 1)[1].strip()[:60]
                elif line.upper().startswith("SUBTEXT:"):
                    concept_d["subtext"] = line.split(":", 1)[1].strip()[:60]
        except Exception:
            pass
    return concept_d


def render(concept_d: dict, out_path: Path, bg_image: str = "") -> Path:
    from PIL import Image, ImageDraw
    W, H = 1280, 720
    base = None
    if bg_image:
        try:
            from pathlib import Path as P
            if P(bg_image).exists():
                base = Image.open(bg_image).convert("RGB")
        except Exception:
            base = None
    if base is None:
        base = Image.new("RGB", (W, H), (8, 15, 28))
    # cover
    w, h = base.size
    s = max(W / w, H / h)
    base = base.resize((int(w * s) + 1, int(h * s) + 1))
    x = (base.size[0] - W) // 2
    y = (base.size[1] - H) // 2
    base = base.crop((x, y, x + W, y + H))
    d = ImageDraw.Draw(base)
    d.rectangle([0, 0, 760, H], fill=(5, 10, 20))
    # wrap text crudely
    text = concept_d.get("text", "?")
    words, lines, cur = text.split(), [], ""
    for wd in words:
        if len(cur) + len(wd) + 1 > 16:
            lines.append(cur)
            cur = wd
        else:
            cur = f"{cur} {wd}".strip()
    if cur:
        lines.append(cur)
    from PIL import ImageFont

    def _font(bold: bool, size: int):
        for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                  if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
        return ImageFont.load_default()

    yy = 180
    for ln in lines[:4]:
        d.text((60, yy), ln, font=_font(True, 72), fill=(255, 210, 60),
               stroke_width=3, stroke_fill=(0, 0, 0))
        yy += 92
    d.text((60, yy + 16), concept_d.get("subtext", ""), font=_font(False, 40),
           fill=(160, 200, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base.save(out_path)
    return out_path
