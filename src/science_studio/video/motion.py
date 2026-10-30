"""Motion system — Ken Burns, diagram builds, kinetic captions, progress bar.

Everything here is ffmpeg + Pillow ($0, no keys, no external services).
Scenes keep EXACT durations (fades/captions never shift timing), so narration,
subtitles, and QA stay in sync. Set MOTION=0 to disable (legacy static look).
"""
from __future__ import annotations
from pathlib import Path

ZOOM_MAX = 1.10
FADE_S = 0.3
VARIANTS = ("zoom_in", "zoom_out", "pan_right", "pan_left")

_probe_cache: dict = {}


def has_filter(exe: str, name: str) -> bool:
    """Probe the ffmpeg binary for a filter (cached)."""
    key = (exe, name)
    if key not in _probe_cache:
        import subprocess
        try:
            r = subprocess.run([exe, "-hide_banner", "-filters"],
                               capture_output=True, timeout=30, text=True)
            _probe_cache[key] = f" {name} " in (r.stdout or "")
        except Exception:
            _probe_cache[key] = False
    return _probe_cache[key]


def zoom_variant(index: int) -> str:
    """Cycle Ken Burns variants so adjacent scenes move differently."""
    return VARIANTS[index % len(VARIANTS)]


def zoom_filter(variant: str, frames: int, W: int, H: int, fps: int) -> str:
    """Ken Burns vf fragment (input upscaled first so edges stay safe)."""
    frames = max(1, int(frames))
    center = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    if variant == "zoom_out":
        z = f"z='1.10-0.10*on/{frames}':{center}"
    elif variant == "pan_right":
        z = (f"z='1+0.08*on/{frames}':x='(iw-iw/zoom)*on/{frames}':"
             f"y='ih/2-(ih/zoom/2)'")
    elif variant == "pan_left":
        z = (f"z='1+0.08*on/{frames}':x='(iw-iw/zoom)*(1-on/{frames})':"
             f"y='ih/2-(ih/zoom/2)'")
    else:  # zoom_in
        z = f"z='1+0.10*on/{frames}':{center}"
    return (f"scale=4000:-1,zoompan={z}:d={frames}:s={W}x{H}:fps={fps},"
            f"format=yuv420p")


def fade_filter(dur: float, amt: float = FADE_S) -> str:
    """Gentle in/out fades (0.3s — under QA's 0.5s blackdetect trip)."""
    if dur <= 2 * amt + 0.1:
        return ""
    return f"fade=t=in:st=0:d={amt},fade=t=out:st={dur - amt:.2f}:d={amt}"


def progress_filter(W: int, H: int, total: float) -> str:
    """Thin progress bar along the bottom (track + fill)."""
    total = max(0.1, float(total))
    y = H - 12
    return (f"drawbox=x=0:y={y}:w={W}:h=12:c=0x1A2B45:t=fill,"
            f"drawbox=x=0:y={y}:w='{W}*t/{total:.2f}':h=12:c=0x4FC3F7:t=fill")


def ffesc(path) -> str:
    """Escape a path for use inside an ffmpeg filter argument."""
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _srt_t(s: str) -> float:
    h, m, rest = s.strip().split(":")
    sec, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000.0


def parse_srt(path) -> list[tuple[float, float, str]]:
    """Parse an .srt file into (start_s, end_s, text) cues."""
    import re
    txt = Path(path).read_text(encoding="utf-8", errors="ignore")
    out = []
    for block in re.split(r"\n\s*\n", txt):
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        tl = next((l for l in lines if "-->" in l), None)
        if tl is None:
            continue
        try:
            s1, s2 = tl.split("-->")
            st, en = _srt_t(s1), _srt_t(s2)
            text = " ".join(lines[lines.index(tl) + 1:]).strip()
            if text and en > st:
                out.append((st, en, text))
        except Exception:
            continue
    return out


def word_dialogues(cues) -> list[tuple[float, float, str, str]]:
    """Split cues into per-word (start, end, prefix_plain, current_word).

    Each dialogue shows the cue-so-far with the current word highlighted
    (typewriter + highlight, the modern caption style). Boundaries cover
    each cue exactly, proportional to word length.
    """
    out = []
    for st, en, text in cues:
        words = text.split()
        if not words:
            continue
        weights = [len(w) + 1 for w in words]
        tot = sum(weights)
        bounds = [st]
        for i in range(len(words) - 1):
            bounds.append(st + (en - st) * sum(weights[:i + 1]) / tot)
        bounds.append(en)
        for i, w in enumerate(words):
            out.append((bounds[i], bounds[i + 1], " ".join(words[:i]), w))
    return out


def ass_time(t: float) -> str:
    cs = max(0, int(round(t * 100)))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cc = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cc:02d}"


def ass_esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def write_ass(cues, path, W: int = 1920, H: int = 1080) -> Path:
    """Write kinetic-caption .ass (one dialogue per word, current highlighted).

    Captions sit at MarginV=90 — in the lane below the burned scene
    titles and above the progress bar.
    """
    fontsize = max(28, int(58 * H / 1080))
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{fontsize},&H00FFFFFF,&H0000FFFF,&H80000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,40,40,90,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [head.rstrip("\n")]
    for st, en, pre, cur in word_dialogues(cues):
        pre, cur = ass_esc(pre), ass_esc(cur)
        if pre:
            text = f"{pre} {{\\c&H0000FFFF&}}{cur}{{\\c&H00FFFFFF&}}"
        else:
            text = f"{{\\c&H0000FFFF&}}{cur}{{\\c&H00FFFFFF&}}"
        lines.append(f"Dialogue: 0,{ass_time(st)},{ass_time(en)},Default,,0,0,0,,{text}")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def render_stages(kind: str, title: str, narration: str, out_dir,
                  basename: str, claims=()) -> list[Path]:
    """Render cumulative diagram stages (boxes 1, 1-2, 1-3, ...).

    Tries limits 1..6 and keeps renders until the bytes stop changing —
    title cards (no boxes) therefore collapse to a single stage.
    """
    import hashlib
    from ..visuals.diagrams import render_diagram_png
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stages: list[Path] = []
    seen: set[str] = set()
    for j in range(1, 7):
        svg = out_dir / f"{basename}_s{j}.svg"
        png = out_dir / f"{basename}_s{j}.png"
        render_diagram_png(kind, title, narration, svg, png,
                           claims=claims, limit=j)
        digest = hashlib.sha256(png.read_bytes()).hexdigest()
        if digest in seen:
            svg.unlink(missing_ok=True)
            png.unlink(missing_ok=True)
            break
        seen.add(digest)
        stages.append(png)
    return stages


def concat_list_file(entries, path) -> Path:
    """Write an ffmpeg concat-demuxer list ([(png_path, dur_s)], last repeated)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for img, d in entries:
        lines.append(f"file '{Path(img).resolve().as_posix()}'")
        lines.append(f"duration {float(d):.3f}")
    lines.append(f"file '{Path(entries[-1][0]).resolve().as_posix()}'")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p
