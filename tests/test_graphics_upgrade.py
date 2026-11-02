"""Regression tests for the colorful multi-layout graphics & caption-safe-zone upgrade."""
from __future__ import annotations
import re
from pathlib import Path

from science_studio.providers.render_ffmpeg import FFmpegRenderer
from science_studio.video.conceptual import _svg_labels
from science_studio.visuals.diagrams import (
    PALETTE,
    _pil_render,
    render_diagram,
    render_diagram_png,
)
from science_studio.visuals.thumbnail import render as render_thumbnail

CLAIMS = (
    "Ovulation releases a mature egg cell into the fallopian tube.",
    "Capacitated sperm cells bind receptor proteins on the zona pellucida.",
    "Rapid cleavage divisions form a hollow blastocyst over five days.",
    "Trophoblast cells implant into the receptive uterine lining.",
    "Hormonal signals sustain early placental blood vessel growth.",
)
NARR = " ".join(CLAIMS)
KINDS = ("process", "lifecycle", "timeline", "anatomy", "chart", "scale")


def test_all_six_diagram_kinds_are_distinct_and_colorful(tmp_path: Path):
    svgs = {}
    for k in KINDS:
        p = render_diagram(k, f"Scene {k}", NARR, tmp_path / f"{k}.svg", claims=CLAIMS)
        txt = p.read_text(encoding="utf-8")
        svgs[k] = txt
        used_colors = [c for c in PALETTE if c in txt]
        assert len(used_colors) >= 3, f"{k} only used {used_colors}"
        labels = _svg_labels(p)
        assert labels, f"{k} lost conceptual labels"
    # Every kind produces its own distinct layout signature
    assert len(set(svgs.values())) == len(KINDS)


def test_diagrams_respect_caption_safe_zone_and_qa_text_budget(tmp_path: Path):
    for k in KINDS:
        p = render_diagram(k, f"Topic {k}", NARR, tmp_path / f"{k}.svg", claims=CLAIMS)
        svg = p.read_text(encoding="utf-8")
        # QA check #21 character budget per font-size tier
        for fs, txt in re.findall(r'<text[^>]*font-size="(\d+)"[^>]*>([^<]*)</text>', svg):
            t = txt.strip()
            if not t or "science-youtube-ai" in t or int(fs) >= 60:
                continue
            budget = 80 if int(fs) >= 40 else (55 if int(fs) >= 30 else 22)
            assert len(t) <= budget, f"{k}: '{t}' ({len(t)}) > {budget} @ fs={fs}"
        # Caption lane starts around y=885; body <text y="..."> must stay <= 850
        for y_str, txt in re.findall(r'<text[^>]*\by="([0-9.]+)"[^>]*>([^<]*)</text>', svg):
            if "science-youtube-ai" in txt:
                continue
            assert float(y_str) <= 850.0, f"{k} text at y={y_str} intrudes on caption lane: {txt}"


def test_pil_fallback_and_png_render_all_kinds(tmp_path: Path):
    from PIL import Image

    for k in KINDS:
        pil_p = _pil_render(k, f"PIL {k}", NARR, tmp_path / f"pil_{k}.png", claims=CLAIMS)
        with Image.open(pil_p) as im:
            assert im.size == (1920, 1080)
        png_p = render_diagram_png(
            k, f"PNG {k}", NARR, tmp_path / f"{k}.svg", tmp_path / f"{k}.png", claims=CLAIMS
        )
        with Image.open(png_p) as im:
            assert im.size == (1920, 1080)


def test_broll_badge_and_gradient_thumbnail(tmp_path: Path):
    from PIL import Image

    r = FFmpegRenderer()
    badge = tmp_path / "badge.png"
    ok = r._make_broll_badge(
        {"title": "Fertilization Mechanism", "onscreen_text": "Zona pellucida binding"},
        badge, 1920, 1080,
    )
    assert ok and badge.exists()
    with Image.open(badge) as im:
        assert im.mode == "RGBA" and im.size == (1920, 1080)
        # Bottom-right corner remains fully transparent over B-roll footage
        assert im.getpixel((1800, 900))[3] == 0

    th = render_thumbnail(
        {"text": "How Does Life Actually Begin?", "subtext": "Cell-by-cell biology"},
        tmp_path / "thumb.png",
    )
    with Image.open(th) as im:
        assert im.size == (1280, 720)
