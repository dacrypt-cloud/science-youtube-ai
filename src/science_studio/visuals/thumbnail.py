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
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1280, 720
    base = None
    if bg_image:
        try:
            if Path(bg_image).exists():
                base = Image.open(bg_image).convert("RGB")
        except Exception:
            base = None
    if base is None:
        base = Image.new("RGB", (W, H), (9, 20, 38))
        gd_bg = ImageDraw.Draw(base)
        gd_bg.ellipse([620, 40, 1260, 680], fill=(22, 58, 104), outline=(56, 189, 248), width=5)
        gd_bg.ellipse([720, 140, 1160, 580], fill=(16, 42, 78), outline=(255, 183, 77), width=4)
    w, h = base.size
    s = max(W / w, H / h)
    base = base.resize((int(w * s) + 1, int(h * s) + 1))
    x = (base.size[0] - W) // 2
    y = (base.size[1] - H) // 2
    base = base.crop((x, y, x + W, y + H)).convert("RGBA")

    # Smooth horizontal cinematic vignette (solid left -> transparent right)
    grad = Image.new("L", (W, 1))
    for px in range(W):
        if px < 380:
            a = 242
        elif px < 980:
            t = (px - 380) / 600.0
            a = int(242 * (1.0 - t) ** 1.6)
        else:
            a = 0
        grad.putpixel((px, 0), a)
    dark = Image.new("RGBA", (W, H), (6, 13, 26, 255))
    dark.putalpha(grad.resize((W, H)))
    base = Image.alpha_composite(base, dark)

    d = ImageDraw.Draw(base)

    def _font(bold: bool, size: int):
        for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                  if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
        return ImageFont.load_default()

    # Top accent pill badge
    d.rounded_rectangle([56, 56, 336, 104], radius=24, fill=(56, 189, 248, 255))
    d.text((196, 80), "SCIENCE EXPLAINED", font=_font(True, 22), fill=(6, 14, 26, 255), anchor="mm")

    text = concept_d.get("text", "?")
    words, lines, cur = text.split(), [], ""
    for wd in words:
        if len(cur) + len(wd) + 1 > 16 and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = f"{cur} {wd}".strip()
    if cur:
        lines.append(cur)

    yy = 148
    for idx, ln in enumerate(lines[:4]):
        col = (255, 214, 56, 255) if idx == len(lines[:4]) - 1 else (248, 252, 255, 255)
        d.text((58, yy), ln, font=_font(True, 74), fill=col,
               stroke_width=4, stroke_fill=(4, 8, 18, 255))
        yy += 90

    sub = (concept_d.get("subtext") or "").strip()
    if sub:
        d.rounded_rectangle([58, yy + 14, 58 + min(680, len(sub) * 21 + 44), yy + 72],
                            radius=14, fill=(15, 32, 58, 220), outline=(255, 183, 77, 220), width=2)
        d.text((80, yy + 43), sub[:34], font=_font(True, 30),
               fill=(255, 200, 100, 255), anchor="lm")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(out_path)
    return out_path
