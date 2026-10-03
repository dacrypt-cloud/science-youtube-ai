"""SRT + WebVTT from scene timings. Word-distributed within each scene."""
from __future__ import annotations
from pathlib import Path


def _fmt_srt(t: float) -> str:
    ms = int(t * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_vtt(t: float) -> str:
    ms = int(t * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


MAX_LINE = 42  # chars per subtitle line (readability standard)
MAX_LINES = 2  # lines per cue


def wrap_cues(text: str) -> list[str]:
    """Wrap narration into readable cues: <=42 chars/line, <=2 lines/cue."""
    words = (text or "").split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if len(trial) > MAX_LINE and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    if not lines:
        return [""]
    return ["\n".join(lines[i:i + MAX_LINES]) for i in range(0, len(lines), MAX_LINES)]


def build_subtitles(storyboard: list[dict], durations: dict[str, float], out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cues: list[tuple[float, float, str]] = []
    t = 0.0
    for sc in storyboard:
        dur = float(durations.get(sc["scene_id"], 0) or 0)
        chunks = wrap_cues(sc["narration"])
        per = dur / max(1, len(chunks))
        for j, ch in enumerate(chunks):
            cues.append((t + j * per, t + (j + 1) * per, ch))
        t += dur
    srt = "\n\n".join(f"{i+1}\n{_fmt_srt(a)} --> {_fmt_srt(b)}\n{c}"
                      for i, (a, b, c) in enumerate(cues)) + "\n"
    vtt = "WEBVTT\n\n" + "\n\n".join(f"{_fmt_vtt(a)} --> {_fmt_vtt(b)}\n{c}" for a, b, c in cues) + "\n"
    srt_p = out_dir / "subtitles.srt"
    vtt_p = out_dir / "subtitles.vtt"
    srt_p.write_text(srt, encoding="utf-8")
    vtt_p.write_text(vtt, encoding="utf-8")
    return {"srt": str(srt_p), "vtt": str(vtt_p), "cues": len(cues), "total_s": t}
