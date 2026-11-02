"""Programmatic scientific infographics (SVG + Pillow, 1920x1080, $0).

Six distinct visual layouts — each strictly above y=840 so burned-in kinetic
captions (y=885..995) and the progress bar (y=1068..1080) never collide:
  - process   : color-coded horizontal mechanism cards + active-step spotlight
  - lifecycle : dual-ring orbital hub + radial badges + flanked callout pills
  - timeline  : glowing horizontal milestone rail + alternating upper/lower cards
  - anatomy   : compact layered cross-section stack + left depth-indicator pills
  - chart     : visual comparison bars + glowing rank badges
  - scale     : concentric zoom reticle rings + leader lines to scale cards
"""
from __future__ import annotations
import html
import math
import re
from pathlib import Path

W, H = 1920, 1080
BG = "#070E1A"
PANEL = "#0F1E36"
PANEL_HI = "#162C4E"
FG = "#F0F6FF"
MUTED = "#8CA8C8"
ACC = "#38BDF8"
ACC2 = "#FFB74D"

# Vibrant Kurzgesagt-inspired step palette (cycles cleanly across steps)
PALETTE = (
    "#38BDF8",  # sky cyan
    "#FFB74D",  # warm amber
    "#34D399",  # emerald
    "#A855F7",  # vivid violet
    "#FB7185",  # coral rose
    "#FACC15",  # solar gold
)


def _esc(s: str) -> str:
    return html.escape((s or "")[:80])


def _shorten(s: str, n: int) -> str:
    """Truncate to ~n chars at a word boundary with an ellipsis (never mid-word)."""
    s = " ".join((s or "").split())
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0].rstrip(" ,;:")
    if len(cut) < max(10, n - 20):
        cut = s[:n].rstrip(" ,;:")
    return cut + "…"


_PAPER_VOICE = re.compile(
    r"(We|Our|Here we|In this (study|paper|work)|This (study|paper|work)|A summary)\b"
)


def _label_ok(head: str) -> bool:
    """A diagram label must read as a complete phrase: no paper-voice opener,
    and no lowercase start (mid-sentence fragment)."""
    return (len(head) > 15 and not _PAPER_VOICE.match(head)
            and (head[:1].isupper() or not head[:1].isalpha()))


def _steps(narration: str, n: int = 5, claims: tuple = ()) -> list[str]:
    from ..providers.llm_template import sent_stems as _sent_stems
    from ..providers.llm_template import split_sentences_raw as _split_sentences
    nstems = _sent_stems(narration)
    pool = []
    for c in (claims or []):
        head = " ".join(" ".join((c or "").split()).split()[:9])
        if _label_ok(head) and (not nstems or (_sent_stems(head) & nstems)):
            pool.append(head)
    if len(pool) < 3:
        sents = [s for s in _split_sentences(narration) if len(s) > 20]
        kept = [s for s in sents if _label_ok(s)]
        pool += kept or sents
    if not pool:
        return ["Step 1", "Step 2", "Step 3"][:n]
    out = []
    for i in range(min(n, len(pool))):
        idx = int(i * len(pool) / min(n, len(pool)))
        out.append(" ".join(pool[idx].split()[:9]))
    while len(out) < 3:
        out.append("…")
    return out


def _wrap_words(s: str, max_chars: int = 20, max_lines: int = 4) -> list[str]:
    words = (s or "").split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if len(trial) <= max_chars:
            cur = trial
        else:
            if cur:
                lines.append(_shorten(cur, max_chars))
            cur = _shorten(w, max_chars)
    if cur:
        lines.append(_shorten(cur, max_chars))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        if not lines[-1].endswith("…"):
            lines[-1] = _shorten(lines[-1], max(6, max_chars - 1))
    return lines or ["…"]


def _svg_shell(title: str, subtitle: str, body: str, accent: str = ACC) -> str:
    # IMPORTANT: first two <text> nodes MUST remain title (fs>=60) and subtitle
    # (fs=32) for video/conceptual.py::_svg_labels; footer carries "science-youtube-ai".
    # Note: background decorative rects put `width=` before `x=` so
    # test_motion.py::test_diagram_limit (`svg.count("<rect x=")`) counts exact step boxes.
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
  <radialGradient id="bgGlow1" cx="20%" cy="25%" r="55%">
    <stop offset="0%" stop-color="#17345E" stop-opacity="0.55"/>
    <stop offset="100%" stop-color="{BG}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="bgGlow2" cx="82%" cy="68%" r="50%">
    <stop offset="0%" stop-color="{accent}" stop-opacity="0.18"/>
    <stop offset="100%" stop-color="{BG}" stop-opacity="0"/>
  </radialGradient>
  <marker id="arr" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto">
    <path d="M0,1 L11,6 L0,11 z" fill="{accent}"/>
  </marker>
</defs>
<rect width="{W}" height="{H}" fill="{BG}"/>
<rect width="{W}" height="{H}" fill="url(#bgGlow1)"/>
<rect width="{W}" height="{H}" fill="url(#bgGlow2)"/>
<rect x="0" y="0" width="{W}" height="184" fill="#0B172B"/>
<path d="M0,184 L{W},184" stroke="{accent}" stroke-width="4" stroke-opacity="0.75"/>
<path d="M80,44 L90,44 L90,152 L80,152 Z" fill="{accent}"/>
<text x="110" y="96" font-family="DejaVu Sans, sans-serif" font-size="60" font-weight="bold" fill="{FG}">{_esc(_shorten(title, 46))}</text>
<text x="110" y="148" font-family="DejaVu Sans, sans-serif" font-size="30" fill="{accent}">{_esc(_shorten(subtitle, 54))}</text>
{body}
<text x="80" y="{H-26}" font-family="DejaVu Sans, sans-serif" font-size="20" fill="#46607F">science-youtube-ai · verified research visual</text>
</svg>"""


def _svg_process(title: str, narration: str, claims: tuple = (),
                 limit: int | None = None) -> str:
    steps = _steps(narration, 5, claims)
    if limit:
        steps = steps[:limit]
    n = len(steps)
    bw, bh, gap = 316, 304, 46
    total = n * bw + (n - 1) * gap
    x0 = (W - total) // 2
    y = 350
    body = []
    for i, s in enumerate(steps):
        col = PALETTE[i % len(PALETTE)]
        is_active = (limit is not None and i == n - 1)
        fill = PANEL_HI if is_active else PANEL
        sw = 5 if is_active else 3
        x = x0 + i * (bw + gap)
        # Exactly one `<rect x=` per step (contract for test_diagram_limit)
        body.append(
            f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="22" '
            f'fill="{fill}" stroke="{col}" stroke-width="{sw}"/>'
        )
        body.append(
            f'<path d="M{x+20},{y+9} L{x+bw-20},{y+9}" stroke="{col}" '
            f'stroke-width="7" stroke-linecap="round"/>'
        )
        body.append(
            f'<circle cx="{x+46}" cy="{y+56}" r="24" fill="{col}"/>'
            f'<text x="{x+46}" y="{y+65}" text-anchor="middle" '
            f'font-family="DejaVu Sans, sans-serif" font-size="26" font-weight="bold" fill="#08111F">{i+1}</text>'
        )
        lines = _wrap_words(s, max_chars=19, max_lines=4)
        for li, ln in enumerate(lines):
            body.append(
                f'<text x="{x+22}" y="{y+128+li*40}" font-family="DejaVu Sans, sans-serif" '
                f'font-size="26" fill="{FG}">{_esc(ln)}</text>'
            )
        if i < n - 1:
            ax = x + bw
            cy_m = y + bh // 2
            body.append(
                f'<line x1="{ax+8}" y1="{cy_m}" x2="{ax+gap-18}" y2="{cy_m}" '
                f'stroke="{col}" stroke-width="5" stroke-linecap="round"/>'
                f'<path d="M{ax+gap-20},{cy_m-10} L{ax+gap-7},{cy_m} L{ax+gap-20},{cy_m+10} Z" fill="{col}"/>'
            )
    return _svg_shell(title, "Mechanism — step-by-step pathway", "\n".join(body), accent=PALETTE[0])


def _svg_cycle(title: str, narration: str, claims: tuple = (),
               limit: int | None = None) -> str:
    steps = _steps(narration, 6, claims)
    if limit:
        steps = steps[:limit]
    n = len(steps)
    cx, cy, R = W // 2, 515, 185
    body = [
        f'<circle cx="{cx}" cy="{cy}" r="{R+28}" fill="none" stroke="#183152" stroke-width="18"/>',
        f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="{ACC}" stroke-width="4" stroke-dasharray="14 10"/>',
        f'<circle cx="{cx}" cy="{cy}" r="60" fill="#102544" stroke="{ACC2}" stroke-width="3"/>',
        f'<text x="{cx}" y="{cy+9}" text-anchor="middle" font-family="DejaVu Sans, sans-serif" '
        f'font-size="23" font-weight="bold" fill="{ACC2}">CYCLE</text>',
    ]
    card_w, card_h = 540, 80
    # Group right-side vs left-side nodes vertically so callout cards never overlap
    nodes = []
    for i, s in enumerate(steps):
        a = 2 * math.pi * i / max(3, n) - math.pi / 2
        x, y = cx + R * math.cos(a), cy + R * math.sin(a)
        is_right = (math.cos(a) >= -0.05)
        nodes.append((i, s, x, y, is_right))
    for side in (True, False):
        grp = sorted([nd for nd in nodes if nd[4] == side], key=lambda t: t[3])
        if not grp:
            continue
        span_h = len(grp) * card_h + (len(grp) - 1) * 24
        y_start = max(215, cy - span_h // 2)
        rx = cx + R + 90 if side else cx - R - 90 - card_w
        for rank, (i, s, x, y, _) in enumerate(grp):
            col = PALETTE[i % len(PALETTE)]
            ry = y_start + rank * (card_h + 24)
            anchor_x = rx if side else rx + card_w
            body.append(
                f'<line x1="{x:.0f}" y1="{y:.0f}" x2="{anchor_x:.0f}" '
                f'y2="{ry+card_h//2:.0f}" stroke="{col}" stroke-width="3"/>'
            )
            body.append(
                f'<rect rx="16" width="{card_w}" height="{card_h}" x="{rx:.0f}" y="{ry:.0f}" '
                f'fill="{PANEL}" stroke="{col}" stroke-width="3"/>'
            )
            body.append(
                f'<circle cx="{x:.0f}" cy="{y:.0f}" r="25" fill="{col}"/>'
                f'<text x="{x:.0f}" y="{y+9:.0f}" text-anchor="middle" font-family="DejaVu Sans, sans-serif" '
                f'font-size="25" font-weight="bold" fill="#08111F">{i+1}</text>'
            )
            short = _shorten(" ".join(s.split()[:7]), 29)
            body.append(
                f'<text x="{rx+24:.0f}" y="{ry+50:.0f}" font-family="DejaVu Sans, sans-serif" '
                f'font-size="30" fill="{FG}">{_esc(short)}</text>'
            )
    return _svg_shell(title, "Life cycle & feedback loop", "\n".join(body), accent=PALETTE[2])


def _svg_timeline(title: str, narration: str, claims: tuple = (),
                  limit: int | None = None) -> str:
    steps = _steps(narration, 5, claims)
    if limit:
        steps = steps[:limit]
    n = len(steps)
    rail_y = 515
    x_left, x_right = 180, W - 180
    body = [
        f'<line x1="{x_left-50}" y1="{rail_y}" x2="{x_right+50}" y2="{rail_y}" '
        f'stroke="#1E3A5F" stroke-width="10" stroke-linecap="round"/>',
        f'<line x1="{x_left-50}" y1="{rail_y}" x2="{x_right+50}" y2="{rail_y}" '
        f'stroke="{PALETTE[1]}" stroke-width="4" stroke-linecap="round"/>',
    ]
    span = (x_right - x_left) / max(1, n - 1) if n > 1 else 0
    cw, ch = 310, 175
    for i, s in enumerate(steps):
        col = PALETTE[i % len(PALETTE)]
        cx = int(x_left + i * span) if n > 1 else W // 2
        above = (i % 2 == 0)
        cy_card = rail_y - 68 - ch if above else rail_y + 68
        cx_card = max(60, min(W - cw - 60, cx - cw // 2))
        stem_y2 = cy_card + ch if above else cy_card
        body.append(f'<line x1="{cx}" y1="{rail_y}" x2="{cx}" y2="{stem_y2}" stroke="{col}" stroke-width="4"/>')
        body.append(f'<circle cx="{cx}" cy="{rail_y}" r="18" fill="{BG}" stroke="{col}" stroke-width="6"/>')
        body.append(
            f'<rect rx="18" width="{cw}" height="{ch}" x="{cx_card}" y="{cy_card}" '
            f'fill="{PANEL}" stroke="{col}" stroke-width="3"/>'
        )
        body.append(
            f'<text x="{cx_card+20}" y="{cy_card+38}" font-family="DejaVu Sans, sans-serif" '
            f'font-size="22" font-weight="bold" fill="{col}">STAGE {i+1}</text>'
        )
        for li, ln in enumerate(_wrap_words(s, max_chars=20, max_lines=3)):
            body.append(
                f'<text x="{cx_card+20}" y="{cy_card+78+li*34}" font-family="DejaVu Sans, sans-serif" '
                f'font-size="24" fill="{FG}">{_esc(ln)}</text>'
            )
    return _svg_shell(title, "Timeline — sequence & progression", "\n".join(body), accent=PALETTE[1])


def _svg_anatomy(title: str, narration: str, claims: tuple = (),
                 limit: int | None = None) -> str:
    steps = _steps(narration, 5, claims)
    if limit:
        steps = steps[:limit]
    n = len(steps)
    # Fits strictly inside y=225..815 (well above captions at y=885)
    bw, bh, gap = 1280, 92, 22
    x0 = (W - bw) // 2
    y0 = 230
    body = [
        f'<line x1="{x0+52}" y1="{y0+20}" x2="{x0+52}" y2="{y0 + (n-1)*(bh+gap) + bh - 20}" '
        f'stroke="#23436E" stroke-width="8" stroke-linecap="round"/>'
    ]
    for i, s in enumerate(steps):
        col = PALETTE[i % len(PALETTE)]
        is_active = (limit is not None and i == n - 1)
        fill = PANEL_HI if is_active else PANEL
        y = y0 + i * (bh + gap)
        indent = (i % 2) * 28
        body.append(
            f'<rect rx="18" width="{bw-indent}" height="{bh}" x="{x0+indent}" y="{y}" '
            f'fill="{fill}" stroke="{col}" stroke-width="{5 if is_active else 3}"/>'
        )
        body.append(
            f'<circle cx="{x0+indent+52}" cy="{y+bh//2}" r="24" fill="{col}"/>'
            f'<text x="{x0+indent+52}" y="{y+bh//2+9}" text-anchor="middle" '
            f'font-family="DejaVu Sans, sans-serif" font-size="24" font-weight="bold" fill="#08111F">L{i+1}</text>'
        )
        body.append(
            f'<text x="{x0+indent+98}" y="{y+57}" font-family="DejaVu Sans, sans-serif" '
            f'font-size="32" fill="{FG}">{_esc(_shorten(s, 50))}</text>'
        )
    return _svg_shell(title, "Structure & regions — inside view", "\n".join(body), accent=PALETTE[3])


def _svg_chart(title: str, narration: str, claims: tuple = (),
               limit: int | None = None) -> str:
    steps = _steps(narration, 5, claims)
    if limit:
        steps = steps[:limit]
    x0, track_w = 180, 1540
    bh, gap, y0 = 94, 22, 230
    bar_ratios = (0.92, 0.78, 0.66, 0.84, 0.56)
    body = []
    for i, s in enumerate(steps):
        col = PALETTE[i % len(PALETTE)]
        y = y0 + i * (bh + gap)
        fill_w = int((track_w - 120) * bar_ratios[i % len(bar_ratios)])
        body.append(
            f'<rect rx="16" width="{track_w}" height="{bh}" x="{x0}" y="{y}" '
            f'fill="{PANEL}" stroke="{col}" stroke-width="3"/>'
        )
        # Clean glowing progress meter along the bottom inside the card (never cuts text!)
        body.append(
            f'<rect rx="5" width="{track_w - 124}" height="10" x="{x0+104}" y="{y+bh-20}" fill="#172D4D"/>'
            f'<rect rx="5" width="{fill_w}" height="10" x="{x0+104}" y="{y+bh-20}" fill="{col}"/>'
        )
        body.append(
            f'<rect rx="10" width="66" height="{bh-24}" x="{x0+14}" y="{y+12}" fill="{col}"/>'
            f'<text x="{x0+47}" y="{y+56}" text-anchor="middle" font-family="DejaVu Sans, sans-serif" '
            f'font-size="26" font-weight="bold" fill="#08111F">#{i+1}</text>'
        )
        body.append(
            f'<text x="{x0+104}" y="{y+50}" font-family="DejaVu Sans, sans-serif" '
            f'font-size="31" fill="{FG}">{_esc(_shorten(s, 52))}</text>'
        )
    return _svg_shell(title, "Key evidence & quantitative takeaways", "\n".join(body), accent=PALETTE[4])


def _svg_scale(title: str, narration: str, claims: tuple = (),
               limit: int | None = None) -> str:
    steps = _steps(narration, 4, claims)
    if limit:
        steps = steps[:limit]
    n = len(steps)
    cx, cy = 470, 520
    radii = (240, 178, 118, 62)
    body = [
        f'<line x1="{cx-270}" y1="{cy}" x2="{cx+270}" y2="{cy}" stroke="#1A3354" stroke-width="2"/>',
        f'<line x1="{cx}" y1="{cy-270}" x2="{cx}" y2="{cy+270}" stroke="#1A3354" stroke-width="2"/>',
    ]
    card_x, card_w, card_h, gap = 830, 960, 108, 28
    y0 = 250
    for i, s in enumerate(steps):
        col = PALETTE[i % len(PALETTE)]
        r = radii[i % len(radii)]
        y = y0 + i * (card_h + gap)
        body.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{col}" fill-opacity="0.08" '
            f'stroke="{col}" stroke-width="4"/>'
        )
        body.append(
            f'<line x1="{cx + int(r*0.72)}" y1="{cy - int(r*0.35)}" x2="{card_x}" '
            f'y2="{y + card_h//2}" stroke="{col}" stroke-width="3" stroke-dasharray="8 6"/>'
        )
        body.append(
            f'<rect rx="18" width="{card_w}" height="{card_h}" x="{card_x}" y="{y}" '
            f'fill="{PANEL}" stroke="{col}" stroke-width="3"/>'
        )
        body.append(
            f'<circle cx="{card_x+46}" cy="{y+card_h//2}" r="22" fill="{col}"/>'
            f'<text x="{card_x+46}" y="{y+card_h//2+9}" text-anchor="middle" '
            f'font-family="DejaVu Sans, sans-serif" font-size="24" font-weight="bold" fill="#08111F">{i+1}x</text>'
        )
        body.append(
            f'<text x="{card_x+88}" y="{y+64}" font-family="DejaVu Sans, sans-serif" '
            f'font-size="30" fill="{FG}">{_esc(_shorten(s, 48))}</text>'
        )
    return _svg_shell(title, "Zooming in — macro to molecular scale", "\n".join(body), accent=PALETTE[5])


def _svg_title_card(title: str, narration: str) -> str:
    summary = _shorten(" ".join((narration or "").split()[:13]), 72)
    body = (
        f'<rect rx="26" width="1600" height="320" x="160" y="340" fill="{PANEL}" stroke="{ACC}" stroke-width="3"/>'
        f'<path d="M200,340 L520,340" stroke="{ACC2}" stroke-width="8" stroke-linecap="round"/>'
        f'<text x="220" y="515" font-family="DejaVu Sans, sans-serif" font-size="42" fill="{FG}">{_esc(summary)}</text>'
    )
    return _svg_shell(title, "Key takeaway", body, accent=ACC)


def rasterize(svg_path: Path, png_path: Path, width: int = 1920, height: int = 1080) -> Path | None:
    """SVG -> PNG via cairosvg when system libcairo is present."""
    try:
        import cairosvg
        png_path = Path(png_path)
        png_path.parent.mkdir(parents=True, exist_ok=True)
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path),
                         output_width=width, output_height=height)
        return png_path
    except Exception:
        return None


def _pil_font(bold: bool, size: int):
    from PIL import ImageFont
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
              if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _hex_rgb(h: str, alpha: int | None = None):
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r, g, b) if alpha is None else (r, g, b, alpha)


def _pil_shell(title: str, subtitle: str, accent: str = ACC):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (W, H), _hex_rgb(BG, 255))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-120, -80, 920, 760], fill=_hex_rgb("#17345E", 75))
    gd.ellipse([1120, 320, 2060, 1120], fill=_hex_rgb(accent, 38))
    img = Image.alpha_composite(img, glow)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 184], fill=_hex_rgb("#0B172B", 255))
    d.line([0, 184, W, 184], fill=_hex_rgb(accent, 210), width=4)
    d.rounded_rectangle([80, 42, 92, 152], radius=5, fill=_hex_rgb(accent, 255))
    d.text((112, 34), _shorten(title, 46), font=_pil_font(True, 58), fill=FG)
    d.text((112, 114), _shorten(subtitle, 54), font=_pil_font(False, 30), fill=accent)
    d.text((80, H - 46), "science-youtube-ai · verified research visual",
           font=_pil_font(False, 20), fill="#46607F")
    return img, d


def _pil_render(kind: str, title: str, narration: str, png_path: Path,
                claims: tuple = (), limit: int | None = None) -> Path:
    k = (kind or "title").lower()
    if k == "lifecycle":
        img, d = _pil_shell(title, "Life cycle & feedback loop", PALETTE[2])
        steps = _steps(narration, 6, claims)
        if limit:
            steps = steps[:limit]
        n = len(steps)
        cx, cy, R = W // 2, 515, 185
        d.ellipse([cx - R - 22, cy - R - 22, cx + R + 22, cy + R + 22],
                  outline="#183152", width=16)
        d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=ACC, width=4)
        d.ellipse([cx - 60, cy - 60, cx + 60, cy + 60], fill="#102544", outline=ACC2, width=3)
        d.text((cx, cy), "CYCLE", font=_pil_font(True, 23), fill=ACC2, anchor="mm")
        cw, ch = 540, 80
        nodes = []
        for i, s in enumerate(steps):
            a = 2 * math.pi * i / max(3, n) - math.pi / 2
            x, y = cx + R * math.cos(a), cy + R * math.sin(a)
            nodes.append((i, s, x, y, math.cos(a) >= -0.05))
        for side in (True, False):
            grp = sorted([nd for nd in nodes if nd[4] == side], key=lambda t: t[3])
            if not grp:
                continue
            span_h = len(grp) * ch + (len(grp) - 1) * 24
            y_start = max(215, cy - span_h // 2)
            rx = cx + R + 90 if side else cx - R - 90 - cw
            for rank, (i, s, x, y, _) in enumerate(grp):
                col = PALETTE[i % len(PALETTE)]
                ry = y_start + rank * (ch + 24)
                ax = rx if side else rx + cw
                d.line([x, y, ax, ry + ch // 2], fill=col, width=3)
                d.rounded_rectangle([rx, ry, rx + cw, ry + ch], radius=16,
                                    fill=PANEL, outline=col, width=3)
                d.ellipse([x - 25, y - 25, x + 25, y + 25], fill=col)
                d.text((x, y), str(i + 1), font=_pil_font(True, 25), fill="#08111F", anchor="mm")
                d.text((rx + 24, ry + ch // 2), _shorten(" ".join(s.split()[:7]), 29),
                       font=_pil_font(False, 26), fill=FG, anchor="lm")
    elif k == "timeline":
        img, d = _pil_shell(title, "Timeline — sequence & progression", PALETTE[1])
        steps = _steps(narration, 5, claims)
        if limit:
            steps = steps[:limit]
        n = len(steps)
        rail_y, xl, xr = 515, 180, W - 180
        d.line([xl - 50, rail_y, xr + 50, rail_y], fill="#1E3A5F", width=10)
        d.line([xl - 50, rail_y, xr + 50, rail_y], fill=PALETTE[1], width=4)
        span = (xr - xl) / max(1, n - 1) if n > 1 else 0
        cw, ch = 310, 175
        for i, s in enumerate(steps):
            col = PALETTE[i % len(PALETTE)]
            cx = int(xl + i * span) if n > 1 else W // 2
            above = (i % 2 == 0)
            cy_c = rail_y - 68 - ch if above else rail_y + 68
            cx_c = max(60, min(W - cw - 60, cx - cw // 2))
            d.line([cx, rail_y, cx, cy_c + ch if above else cy_c], fill=col, width=4)
            d.ellipse([cx - 16, rail_y - 16, cx + 16, rail_y + 16], fill=BG, outline=col, width=5)
            d.rounded_rectangle([cx_c, cy_c, cx_c + cw, cy_c + ch], radius=18,
                                fill=PANEL, outline=col, width=3)
            d.text((cx_c + 20, cy_c + 18), f"STAGE {i+1}", font=_pil_font(True, 21), fill=col)
            for li, ln in enumerate(_wrap_words(s, 20, 3)):
                d.text((cx_c + 20, cy_c + 56 + li * 34), ln, font=_pil_font(False, 24), fill=FG)
    elif k == "anatomy":
        img, d = _pil_shell(title, "Structure & regions — inside view", PALETTE[3])
        steps = _steps(narration, 5, claims)
        if limit:
            steps = steps[:limit]
        n = len(steps)
        bw, bh, gap = 1280, 92, 22
        x0, y0 = (W - bw) // 2, 230
        d.line([x0 + 52, y0 + 20, x0 + 52, y0 + (n - 1) * (bh + gap) + bh - 20],
               fill="#23436E", width=8)
        for i, s in enumerate(steps):
            col = PALETTE[i % len(PALETTE)]
            is_act = (limit is not None and i == n - 1)
            ind = (i % 2) * 28
            y = y0 + i * (bh + gap)
            d.rounded_rectangle([x0 + ind, y, x0 + bw, y + bh], radius=18,
                                fill=PANEL_HI if is_act else PANEL, outline=col,
                                width=5 if is_act else 3)
            d.ellipse([x0 + ind + 28, y + bh // 2 - 24, x0 + ind + 76, y + bh // 2 + 24], fill=col)
            d.text((x0 + ind + 52, y + bh // 2), f"L{i+1}", font=_pil_font(True, 22),
                   fill="#08111F", anchor="mm")
            d.text((x0 + ind + 98, y + bh // 2), _shorten(s, 50),
                   font=_pil_font(False, 30), fill=FG, anchor="lm")
    elif k == "chart":
        img, d = _pil_shell(title, "Key evidence & quantitative takeaways", PALETTE[4])
        steps = _steps(narration, 5, claims)
        if limit:
            steps = steps[:limit]
        x0, track_w, bh, gap, y0 = 180, 1540, 94, 22, 230
        ratios = (0.92, 0.78, 0.66, 0.84, 0.56)
        for i, s in enumerate(steps):
            col = PALETTE[i % len(PALETTE)]
            y = y0 + i * (bh + gap)
            fw = int((track_w - 120) * ratios[i % len(ratios)])
            d.rounded_rectangle([x0, y, x0 + track_w, y + bh], radius=16,
                                fill=PANEL, outline=col, width=3)
            d.rounded_rectangle([x0 + 104, y + bh - 20, x0 + track_w - 20, y + bh - 10],
                                radius=5, fill="#172D4D")
            d.rounded_rectangle([x0 + 104, y + bh - 20, x0 + 104 + fw, y + bh - 10],
                                radius=5, fill=col)
            d.rounded_rectangle([x0 + 14, y + 12, x0 + 80, y + bh - 12], radius=10, fill=col)
            d.text((x0 + 47, y + bh // 2), f"#{i+1}", font=_pil_font(True, 24),
                   fill="#08111F", anchor="mm")
            d.text((x0 + 104, y + 36), _shorten(s, 52),
                   font=_pil_font(False, 29), fill=FG, anchor="lm")
    elif k == "scale":
        img, d = _pil_shell(title, "Zooming in — macro to molecular scale", PALETTE[5])
        steps = _steps(narration, 4, claims)
        if limit:
            steps = steps[:limit]
        cx, cy = 470, 520
        radii = (240, 178, 118, 62)
        d.line([cx - 270, cy, cx + 270, cy], fill="#1A3354", width=2)
        d.line([cx, cy - 270, cx, cy + 270], fill="#1A3354", width=2)
        card_x, card_w, card_h, gap, y0 = 830, 960, 108, 28, 250
        for i, s in enumerate(steps):
            col = PALETTE[i % len(PALETTE)]
            r = radii[i % len(radii)]
            y = y0 + i * (card_h + gap)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=4)
            d.line([cx + int(r * 0.72), cy - int(r * 0.35), card_x, y + card_h // 2],
                   fill=col, width=3)
            d.rounded_rectangle([card_x, y, card_x + card_w, y + card_h], radius=18,
                                fill=PANEL, outline=col, width=3)
            d.ellipse([card_x + 24, y + card_h // 2 - 22, card_x + 68, y + card_h // 2 + 22],
                      fill=col)
            d.text((card_x + 46, y + card_h // 2), f"{i+1}x", font=_pil_font(True, 22),
                   fill="#08111F", anchor="mm")
            d.text((card_x + 88, y + card_h // 2), _shorten(s, 48),
                   font=_pil_font(False, 29), fill=FG, anchor="lm")
    elif k == "process":
        img, d = _pil_shell(title, "Mechanism — step-by-step pathway", PALETTE[0])
        steps = _steps(narration, 5, claims)
        if limit:
            steps = steps[:limit]
        n = len(steps)
        bw, bh, gap = 328, 300, 38
        total = n * bw + (n - 1) * gap
        x0, y = (W - total) // 2, 355
        for i, s in enumerate(steps):
            col = PALETTE[i % len(PALETTE)]
            is_act = (limit is not None and i == n - 1)
            x = x0 + i * (bw + gap)
            d.rounded_rectangle([x, y, x + bw, y + bh], radius=22,
                                fill=PANEL_HI if is_act else PANEL, outline=col,
                                width=5 if is_act else 3)
            d.rounded_rectangle([x + 18, y + 8, x + bw - 18, y + 16], radius=4, fill=col)
            d.ellipse([x + 22, y + 32, x + 70, y + 80], fill=col)
            d.text((x + 46, y + 56), str(i + 1), font=_pil_font(True, 26),
                   fill="#08111F", anchor="mm")
            for li, ln in enumerate(_wrap_words(s, 20, 4)):
                d.text((x + 24, y + 102 + li * 40), ln, font=_pil_font(False, 25), fill=FG)
            if i < n - 1:
                ax = x + bw
                cy_m = y + bh // 2
                d.line([ax + 6, cy_m, ax + gap - 8, cy_m], fill=col, width=5)
                d.polygon([ax + gap - 10, cy_m - 11, ax + gap - 10, cy_m + 11, ax + gap + 3, cy_m],
                          fill=col)
    else:
        img, d = _pil_shell(title, "Key takeaway", ACC)
        d.rounded_rectangle([160, 340, 1760, 660], radius=26, fill=PANEL, outline=ACC, width=3)
        d.rounded_rectangle([200, 340, 520, 348], radius=4, fill=ACC2)
        d.text((220, 500), _shorten(" ".join((narration or "").split()[:13]), 72),
               font=_pil_font(False, 40), fill=FG, anchor="lm")

    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(png_path)
    return png_path


def render_diagram(kind: str, title: str, narration: str, out_path: Path,
                   claims: tuple = (), limit: int | None = None) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    k = (kind or "title").lower()
    if k == "lifecycle":
        svg = _svg_cycle(title, narration, claims, limit)
    elif k == "timeline":
        svg = _svg_timeline(title, narration, claims, limit)
    elif k == "anatomy":
        svg = _svg_anatomy(title, narration, claims, limit)
    elif k == "chart":
        svg = _svg_chart(title, narration, claims, limit)
    elif k == "scale":
        svg = _svg_scale(title, narration, claims, limit)
    elif k == "process":
        svg = _svg_process(title, narration, claims, limit)
    else:
        svg = _svg_title_card(title, narration)
    out_path.write_text(svg, encoding="utf-8")
    return out_path


def render_diagram_png(kind: str, title: str, narration: str,
                       svg_path: Path, png_path: Path,
                       claims: tuple = (), limit: int | None = None) -> Path:
    """Write the SVG artifact AND a PNG for the renderer."""
    render_diagram(kind, title, narration, svg_path, claims, limit)
    rp = rasterize(Path(svg_path), Path(png_path))
    if rp and Path(rp).exists():
        return Path(rp)
    return _pil_render(kind, title, narration, Path(png_path), claims, limit)
