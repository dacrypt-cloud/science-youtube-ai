"""Programmatic scientific diagrams (SVG, 1920x1080). No paid image gen needed.

Kinds: lifecycle, anatomy, process, timeline, chart, scale, title.
Each renders labelled boxes/arrows from the scene text — structured, legible.
"""
from __future__ import annotations
import re, html
from pathlib import Path

W, H = 1920, 1080
BG = "#0a1420"
FG = "#e8f1ff"
ACC = "#4fc3f7"
ACC2 = "#ffb74d"


def _esc(s: str) -> str:
    return html.escape(s[:80])


def _shorten(s: str, n: int) -> str:
    """Truncate to ~n chars at a word boundary with an ellipsis (never mid-word)."""
    s = " ".join((s or "").split())
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0].rstrip(" ,;:")
    if len(cut) < max(10, n - 20):
        cut = s[:n].rstrip(" ,;:")
    return cut + "…"


def _steps(narration: str, n: int = 5) -> list[str]:
    sents = re.split(r"(?<=[.!?])\s+", narration)
    sents = [s.strip() for s in sents if len(s.strip()) > 20]
    if not sents:
        return ["Step 1", "Step 2", "Step 3"][:n]
    # pick evenly spaced sentences, shortened to ~8 words
    out = []
    for i in range(min(n, len(sents))):
        idx = int(i * len(sents) / min(n, len(sents)))
        words = sents[idx].split()[:9]
        out.append(" ".join(words))
    while len(out) < 3:
        out.append("…")
    return out


def _svg_shell(title: str, subtitle: str, body: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<rect width="{W}" height="{H}" fill="{BG}"/>
<rect x="0" y="0" width="{W}" height="200" fill="#0d1b2e"/>
<text x="80" y="100" font-family="sans-serif" font-size="64" font-weight="bold" fill="{FG}">{_esc(title)}</text>
<text x="80" y="160" font-family="sans-serif" font-size="34" fill="{ACC}">{_esc(subtitle)}</text>
{body}
<text x="80" y="{H-40}" font-family="sans-serif" font-size="24" fill="#5b7a99">science-youtube-ai · diagram generated from verified research</text>
</svg>"""


def _flow(title: str, narration: str, subtitle: str, vertical: bool = False) -> str:
    steps = _steps(narration, 5)
    n = len(steps)
    body = []
    if not vertical:
        bw, gap = 300, 60
        total = n * bw + (n - 1) * gap
        x0 = (W - total) // 2
        y = 420
        for i, s in enumerate(steps):
            x = x0 + i * (bw + gap)
            body.append(f'<rect x="{x}" y="{y}" width="{bw}" height="220" rx="18" fill="#12263f" stroke="{ACC}" stroke-width="3"/>')
            body.append(f'<text x="{x+20}" y="{y+60}" font-family="sans-serif" font-size="30" font-weight="bold" fill="{ACC2}">{i+1}</text>')
            words = s.split()
            lines = [" ".join(words[j:j+5]) for j in range(0, len(words), 5)][:4]
            for li, ln in enumerate(lines):
                body.append(f'<text x="{x+20}" y="{y+110+li*40}" font-family="sans-serif" font-size="26" fill="{FG}">{_esc(_shorten(ln, 22))}</text>')
            if i < n - 1:
                ax = x + bw
                body.append(f'<line x1="{ax+6}" y1="{y+110}" x2="{ax+gap-6}" y2="{y+110}" stroke="{ACC}" stroke-width="5" marker-end="url(#a)"/>')
        body.insert(0, '<defs><marker id="a" markerWidth="12" markerHeight="12" refX="10" refY="5" orient="auto"><path d="M0,0 L12,5 L0,10 z" fill="#4fc3f7"/></marker></defs>')
    else:
        bw, bh, gap = 900, 110, 40
        x0 = (W - bw) // 2
        y0 = 260
        for i, s in enumerate(steps):
            y = y0 + i * (bh + gap)
            body.append(f'<rect x="{x0}" y="{y}" width="{bw}" height="{bh}" rx="14" fill="#12263f" stroke="{ACC}" stroke-width="3"/>')
            body.append(f'<text x="{x0+24}" y="{y+66}" font-family="sans-serif" font-size="30" fill="{FG}">{i+1}. {_esc(_shorten(s, 46))}</text>')
            if i < n - 1:
                body.append(f'<line x1="{W//2}" y1="{y+bh+6}" x2="{W//2}" y2="{y+bh+gap-6}" stroke="{ACC}" stroke-width="5"/>')
    return _svg_shell(title, subtitle, "\n".join(body))


def _cycle(title: str, narration: str) -> str:
    import math
    steps = _steps(narration, 6)
    n = len(steps)
    cx, cy, R = W // 2, 590, 260
    body = [f'<ellipse cx="{cx}" cy="{cy}" rx="{R}" ry="{R}" fill="none" stroke="{ACC}" stroke-width="4" stroke-dasharray="14 10"/>']
    for i, s in enumerate(steps):
        a = 2 * math.pi * i / n - math.pi / 2
        x, y = cx + R * math.cos(a), cy + R * math.sin(a)
        body.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="26" fill="{ACC2}"/><text x="{x:.0f}" y="{y+9:.0f}" text-anchor="middle" font-family="sans-serif" font-size="28" font-weight="bold" fill="#102030">{i+1}</text>')
        short = _shorten(" ".join(s.split()[:6]), 34)
        lx = x + (100 if math.cos(a) >= 0 else -100)
        anchor = "start" if math.cos(a) >= 0 else "end"
        body.append(f'<text x="{lx:.0f}" y="{y:.0f}" text-anchor="{anchor}" font-family="sans-serif" font-size="24" fill="{FG}">{_esc(short)}</text>')
    return _svg_shell(title, "Life cycle / circular process", "\n".join(body))


def rasterize(svg_path: Path, png_path: Path, width: int = 1920, height: int = 1080) -> Path | None:
    """SVG -> PNG for ffmpeg. Returns png path or None if unavailable."""
    try:
        import cairosvg
        png_path = Path(png_path)
        png_path.parent.mkdir(parents=True, exist_ok=True)
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path),
                         output_width=width, output_height=height)
        return png_path
    except Exception:
        return None


def render_diagram_png(kind: str, title: str, narration: str,
                       svg_path: Path, png_path: Path) -> Path:
    """Write the SVG artifact AND a PNG for the renderer.

    Prefers cairosvg rasterization of the SVG; falls back to a Pillow-native
    renderer drawing the same layout (works with zero system graphics libs).
    Always returns a PNG path (raises only if Pillow itself is missing).
    """
    render_diagram(kind, title, narration, svg_path)
    rp = rasterize(Path(svg_path), Path(png_path))
    if rp and Path(rp).exists():
        return Path(rp)
    return _pil_render(kind, title, narration, Path(png_path))


def _pil_font(bold: bool, size: int):
    from PIL import ImageFont
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
              if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _pil_shell(title: str, subtitle: str):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 200], fill="#0d1b2e")
    d.text((80, 36), title[:80], font=_pil_font(True, 64), fill=FG)
    d.text((80, 122), subtitle[:80], font=_pil_font(False, 34), fill=ACC)
    d.text((80, H - 70), "science-youtube-ai · diagram generated from verified research",
           font=_pil_font(False, 24), fill="#5b7a99")
    return img, d


def _pil_flow(title: str, narration: str, subtitle: str, vertical: bool = False):
    from PIL import ImageDraw
    img, d = _pil_shell(title, subtitle)
    steps = _steps(narration, 5)
    n = len(steps)
    if not vertical:
        bw, gap = 300, 60
        total = n * bw + (n - 1) * gap
        x0 = (W - total) // 2
        y = 420
        for i, s in enumerate(steps):
            x = x0 + i * (bw + gap)
            d.rounded_rectangle([x, y, x + bw, y + 220], radius=18,
                                fill="#12263f", outline=ACC, width=3)
            d.text((x + 20, y + 18), str(i + 1), font=_pil_font(True, 30), fill=ACC2)
            words = s.split()
            lines = [" ".join(words[j:j + 5]) for j in range(0, len(words), 5)][:4]
            for li, ln in enumerate(lines):
                d.text((x + 20, y + 62 + li * 38), _shorten(ln, 22),
                       font=_pil_font(False, 26), fill=FG)
            if i < n - 1:
                ax = x + bw
                d.line([ax + 6, y + 110, ax + gap - 6, y + 110], fill=ACC, width=5)
                d.polygon([ax + gap - 6, y + 98, ax + gap - 6, y + 122, ax + gap + 8, y + 110],
                          fill=ACC)
    else:
        bw, bh, gap = 900, 110, 40
        x0 = (W - bw) // 2
        y0 = 260
        for i, s in enumerate(steps):
            y = y0 + i * (bh + gap)
            d.rounded_rectangle([x0, y, x0 + bw, y + bh], radius=14,
                                fill="#12263f", outline=ACC, width=3)
            d.text((x0 + 24, y + 34), f"{i + 1}. {_shorten(s, 46)}",
                   font=_pil_font(False, 30), fill=FG)
            if i < n - 1:
                d.line([W // 2, y + bh + 6, W // 2, y + bh + gap - 6], fill=ACC, width=5)
    return img


def _pil_cycle(title: str, narration: str):
    import math
    img, d = _pil_shell(title, "Life cycle / circular process")
    steps = _steps(narration, 6)
    n = len(steps)
    cx, cy, R = W // 2, 590, 260
    d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=ACC, width=4)
    for i, s in enumerate(steps):
        a = 2 * math.pi * i / n - math.pi / 2
        x, y = cx + R * math.cos(a), cy + R * math.sin(a)
        d.ellipse([x - 26, y - 26, x + 26, y + 26], fill=ACC2)
        d.text((x - 9, y - 20), str(i + 1), font=_pil_font(True, 28), fill="#102030")
        short = _shorten(" ".join(s.split()[:6]), 34)
        lx = x + (110 if math.cos(a) >= 0 else -110)
        anchor = "lm" if math.cos(a) >= 0 else "rm"
        d.text((lx, y), short, font=_pil_font(False, 24), fill=FG, anchor=anchor)
    return img


def _pil_title(title: str, narration: str):
    img, d = _pil_shell(title, "Science explainer")
    d.text((80, 470), _shorten(" ".join(narration.split()[:14]), 76),
           font=_pil_font(False, 44), fill=FG)
    return img


_SUBTITLES = {
    "lifecycle": None, "timeline": "Timeline — how understanding developed",
    "anatomy": "Anatomy — where it happens (labels from narration)",
    "chart": "Key numbers and comparisons", "scale": "Zooming in — scale by scale",
    "process": "Mechanism — step by step",
}


def _pil_render(kind: str, title: str, narration: str, png_path: Path) -> Path:
    k = (kind or "title").lower()
    if k == "lifecycle":
        img = _pil_cycle(title, narration)
    elif k in ("timeline", "chart", "scale", "process", "anatomy"):
        img = _pil_flow(title, narration, _SUBTITLES[k],
                        vertical=(k in ("chart", "anatomy")))
    else:
        img = _pil_title(title, narration)
    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(png_path)
    return png_path


def render_diagram(kind: str, title: str, narration: str, out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    k = (kind or "title").lower()
    if k == "lifecycle":
        svg = _cycle(title, narration)
    elif k == "timeline":
        svg = _flow(title, narration, "Timeline — how understanding developed")
    elif k == "anatomy":
        svg = _flow(title, narration, "Anatomy — where it happens (labels from narration)", vertical=True)
    elif k == "chart":
        svg = _flow(title, narration, "Key numbers and comparisons", vertical=True)
    elif k == "scale":
        svg = _flow(title, narration, "Zooming in — scale by scale")
    elif k == "process":
        svg = _flow(title, narration, "Mechanism — step by step")
    else:
        svg = _svg_shell(title, "Science explainer",
                         f'<text x="80" y="500" font-family="sans-serif" font-size="44" fill="{FG}">{_esc(_shorten(" ".join(narration.split()[:14]), 76))}</text>')
    out_path.write_text(svg, encoding="utf-8")
    return out_path
