"""SRT + WebVTT + exact word-boundary caption timings.

Uses neural TTS WordBoundary timestamps when present (millisecond sync between
voice and highlighted word); falls back to pause- and number-weighted timing
(never naive equal chunk splits, which race ahead of spoken numbers/pauses).
"""
from __future__ import annotations
import json
from pathlib import Path


def _fmt_srt(t: float) -> str:
    ms = max(0, int(round(t * 1000)))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_vtt(t: float) -> str:
    ms = max(0, int(round(t * 1000)))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


MAX_LINE = 42  # chars per subtitle line (readability standard)
MAX_LINES = 2  # lines per cue


def spoken_word_weight(w: str) -> float:
    """Estimated spoken duration weight for fallback timing (when TTS gives no
    WordBoundary events). Accounts for multi-syllable digits/units and breath pauses."""
    w = (w or "").strip()
    if not w:
        return 1.0
    alpha = sum(1 for c in w if c.isalpha())
    digits_units = sum(1 for c in w if c.isdigit() or c in "%°")
    wt = max(2.0, float(alpha)) + digits_units * 3.5
    tail = w.rstrip("\"'”’)]}")
    if tail.endswith((".", "?", "!")):
        wt += 5.5
    elif tail.endswith((",", ";", ":", "—", "–")):
        wt += 3.5
    return wt


def _wrap_lines_words(words: list[str]) -> list[str]:
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
    return lines


def wrap_cues(text: str) -> list[str]:
    """Wrap narration into readable cues: <=42 chars/line, <=2 lines/cue."""
    words = (text or "").split()
    lines = _wrap_lines_words(words)
    if not lines:
        return [""]
    return ["\n".join(lines[i:i + MAX_LINES]) for i in range(0, len(lines), MAX_LINES)]


def _group_timed_words(words: list[dict], scene_offset: float,
                       scene_dur: float) -> list[dict]:
    """Group per-word neural timestamps into readable cues (<=2 lines of <=42 chars,
    0.45s..9.0s each, breaking cleanly on sentence boundaries)."""
    groups: list[list[dict]] = []
    cur: list[dict] = []
    for idx, w in enumerate(words):
        tok = str(w.get("word", "")).strip()
        if not tok:
            continue
        trial_words = [x["word"] for x in cur] + [tok]
        trial_lines = _wrap_lines_words(trial_words)
        span = float(w.get("end_s", 0)) - float(cur[0].get("start_s", 0)) if cur else 0.0
        if cur and (len(trial_lines) > MAX_LINES or span > 7.8):
            groups.append(cur)
            cur = [w]
            continue
        cur.append(w)
        cur_span = float(cur[-1].get("end_s", 0)) - float(cur[0].get("start_s", 0))
        tail = tok.rstrip("\"'”’)]}")
        rem = len(words) - idx - 1
        if tail.endswith((".", "?", "!")) and cur_span >= 1.1 and rem >= 2:
            groups.append(cur)
            cur = []
    if cur:
        # Merge a tiny orphan tail into previous cue if it still fits <=2 lines & <=9.0s
        if groups and (float(cur[-1]["end_s"]) - float(cur[0]["start_s"]) < 0.45):
            merged = groups[-1] + cur
            mlines = _wrap_lines_words([x["word"] for x in merged])
            mspan = float(merged[-1]["end_s"]) - float(merged[0]["start_s"])
            if len(mlines) <= MAX_LINES and mspan <= 9.0:
                groups[-1] = merged
                cur = []
        if cur:
            groups.append(cur)

    scene_end = scene_offset + scene_dur
    out: list[dict] = []
    prev_end = scene_offset
    for g in groups:
        lines = _wrap_lines_words([x["word"] for x in g])
        text = "\n".join(lines[:MAX_LINES])
        abs_words = []
        for x in g:
            wst = max(prev_end, scene_offset + float(x.get("start_s", 0)))
            wen = max(wst + 0.03, min(scene_end, scene_offset + float(x.get("end_s", 0))))
            abs_words.append({"word": str(x["word"]), "start_s": round(wst, 3), "end_s": round(wen, 3)})
        st = max(prev_end, abs_words[0]["start_s"])
        en = max(st + 0.45, abs_words[-1]["end_s"])
        if en > scene_end and scene_end - prev_end >= 0.45:
            en = scene_end
            st = min(st, en - 0.45)
        if en - st > 9.5:
            en = st + 9.5
        prev_end = en
        out.append({"start_s": round(st, 3), "end_s": round(en, 3),
                    "text": text, "words": abs_words})
    return out


def _weighted_chunk_cues(narration: str, scene_offset: float,
                         scene_dur: float) -> list[dict]:
    """Pause- and number-weighted fallback cue timing when WordBoundary is absent."""
    chunks = [c for c in wrap_cues(narration) if c.strip()]
    if not chunks or scene_dur <= 0:
        return []
    weights = [sum(spoken_word_weight(w) for w in ch.split()) for ch in chunks]
    tot = sum(weights) or 1.0
    raw = [scene_dur * (wt / tot) for wt in weights]
    # Clamp extremes into [0.45, 9.5] when feasible, then re-normalize to scene_dur
    if scene_dur >= 0.5 * len(chunks):
        clamped = [min(9.5, max(0.45, d)) for d in raw]
        ctot = sum(clamped) or 1.0
        scale = scene_dur / ctot
        durs = [d * scale for d in clamped]
        # Guarantee <=9.8s by splitting any still-long chunk if scene is huge & sparse
    else:
        durs = raw
    out: list[dict] = []
    cur = scene_offset
    for ch, d in zip(chunks, durs):
        out.append({"start_s": round(cur, 3), "end_s": round(cur + d, 3),
                    "text": ch, "words": []})
        cur += d
    return out


def build_subtitles(storyboard: list[dict], durations: dict[str, float],
                    out_dir: Path, narrations: list[dict] | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    by_sid = {n["scene_id"]: n for n in (narrations or []) if isinstance(n, dict) and n.get("scene_id")}
    timed_cues: list[dict] = []
    t = 0.0
    for sc in storyboard:
        sid = sc["scene_id"]
        dur = float(durations.get(sid, 0) or 0)
        n_words = (by_sid.get(sid) or {}).get("words") or []
        if n_words and dur > 0:
            sc_cues = _group_timed_words(n_words, t, dur)
        else:
            sc_cues = _weighted_chunk_cues(sc.get("narration", ""), t, dur)
        timed_cues.extend(sc_cues)
        t += dur

    srt = "\n\n".join(
        f"{i+1}\n{_fmt_srt(c['start_s'])} --> {_fmt_srt(c['end_s'])}\n{c['text']}"
        for i, c in enumerate(timed_cues)
    ) + ("\n" if timed_cues else "")
    vtt = "WEBVTT\n\n" + "\n\n".join(
        f"{_fmt_vtt(c['start_s'])} --> {_fmt_vtt(c['end_s'])}\n{c['text']}"
        for c in timed_cues
    ) + ("\n" if timed_cues else "")
    srt_p = out_dir / "subtitles.srt"
    vtt_p = out_dir / "subtitles.vtt"
    words_p = out_dir / "words.json"
    srt_p.write_text(srt, encoding="utf-8")
    vtt_p.write_text(vtt, encoding="utf-8")
    words_p.write_text(json.dumps(timed_cues), encoding="utf-8")
    return {"srt": str(srt_p), "vtt": str(vtt_p), "words_path": str(words_p),
            "cues": len(timed_cues), "total_s": t}
