"""Tests for exact voice-to-caption word synchronization (Edge WordBoundary +
weighted fallback + ASS highlight timing)."""
from __future__ import annotations
import json
import re
from pathlib import Path


def test_align_word_events_preserves_punctuation_and_numbers():
    from science_studio.providers.tts_edge import align_word_events
    text = "Within 6 days, about 99.5% of signals reach 37°C — remarkable?"
    events = [
        {"offset": int(0.10 * 1e7), "duration": int(0.43 * 1e7), "text": "Within"},
        {"offset": int(0.55 * 1e7), "duration": int(0.71 * 1e7), "text": "6 days"},
        {"offset": int(1.62 * 1e7), "duration": int(0.26 * 1e7), "text": "about"},
        {"offset": int(1.90 * 1e7), "duration": int(1.70 * 1e7), "text": "99.5%"},
        {"offset": int(3.62 * 1e7), "duration": int(0.12 * 1e7), "text": "of"},
        {"offset": int(3.75 * 1e7), "duration": int(0.50 * 1e7), "text": "signals"},
        {"offset": int(4.26 * 1e7), "duration": int(0.35 * 1e7), "text": "reach"},
        {"offset": int(4.62 * 1e7), "duration": int(1.80 * 1e7), "text": "37°C"},
        {"offset": int(6.85 * 1e7), "duration": int(0.65 * 1e7), "text": "remarkable"},
    ]
    words = align_word_events(text, events)
    toks = [w["word"] for w in words]
    assert toks[:4] == ["Within", "6", "days,", "about"]
    assert "99.5%" in toks and "remarkable?" in toks
    pct = next(w for w in words if w["word"] == "99.5%")
    assert abs(pct["start_s"] - 1.90) < 0.02
    assert abs(pct["end_s"] - 3.60) < 0.02


def test_build_subtitles_with_neural_words_obeys_qa_and_sync(tmp_path):
    from science_studio.audio.subtitles import build_subtitles
    from science_studio.video.motion import word_dialogues, write_ass

    words_s1 = [
        {"word": "Within", "start_s": 0.12, "end_s": 0.52},
        {"word": "six", "start_s": 0.54, "end_s": 0.85},
        {"word": "days,", "start_s": 0.86, "end_s": 1.30},
        # 380ms comma pause before '99.5%'
        {"word": "99.5%", "start_s": 1.68, "end_s": 3.45},
        {"word": "of", "start_s": 3.47, "end_s": 3.60},
        {"word": "cells", "start_s": 3.62, "end_s": 4.10},
        {"word": "divide.", "start_s": 4.12, "end_s": 4.75},
        # 450ms sentence pause
        {"word": "What", "start_s": 5.20, "end_s": 5.45},
        {"word": "happens", "start_s": 5.47, "end_s": 5.95},
        {"word": "next?", "start_s": 5.97, "end_s": 6.55},
    ]
    board = [{"scene_id": "scene_01",
              "narration": "Within six days, 99.5% of cells divide. What happens next?"}]
    narr = [{"scene_id": "scene_01", "duration_s": 7.0, "words": words_s1}]
    subs = build_subtitles(board, {"scene_01": 7.0}, tmp_path, narrations=narr)
    assert Path(subs["words_path"]).exists()
    timed_cues = json.loads(Path(subs["words_path"]).read_text(encoding="utf-8"))
    assert len(timed_cues) == 2  # broke cleanly at sentence boundary

    # Every SRT cue obeys QA Check #22 (monotonic, 0.4..10.0s, <=42 chars/line)
    srt_txt = Path(subs["srt"]).read_text(encoding="utf-8")
    cues = re.findall(r"(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)", srt_txt)
    prev = 0.0
    for h1, m1, s1, x1, h2, m2, s2, x2 in cues:
        st = int(h1) * 3600 + int(m1) * 60 + int(s1) + int(x1) / 1000
        en = int(h2) * 3600 + int(m2) * 60 + int(s2) + int(x2) / 1000
        assert st >= prev - 0.001
        assert 0.4 <= en - st <= 10.0
        prev = en

    # Word highlight for '99.5%' starts at exact 1.68s (NOT raced ahead by char count!)
    dlgs = word_dialogues([], timed_cues=timed_cues)
    pct_dlg = next(d for d in dlgs if d[3] == "99.5%")
    assert abs(pct_dlg[0] - 1.68) < 0.01
    assert abs(pct_dlg[1] - 3.47) < 0.01  # holds until 'of' starts at 3.47s

    # Comma-pause word 'days,' holds through the 380ms pause until 1.68s
    days_dlg = next(d for d in dlgs if d[3] == "days,")
    assert abs(days_dlg[1] - 1.68) < 0.01

    ass_p = write_ass([], tmp_path / "c.ass", timed_cues=timed_cues)
    ass_txt = ass_p.read_text(encoding="utf-8")
    assert "0:00:01.68,0:00:03.47" in ass_txt


def test_weighted_fallback_no_longer_races_ahead_on_short_tail_cue(tmp_path):
    """Regression: equal `dur / len(chunks)` gave a 2-word tail chunk 50% of the
    scene time, forcing the first 16 words to race at 2x speed."""
    from science_studio.audio.subtitles import build_subtitles
    from science_studio.video.motion import parse_srt

    narration = (
        "Collisions between graupel pellets and tiny ice crystals inside storm clouds "
        "into life."
    )
    board = [{"scene_id": "scene_01", "narration": narration}]
    subs = build_subtitles(board, {"scene_01": 12.0}, tmp_path)
    cues = parse_srt(subs["srt"])
    assert len(cues) == 2
    first_dur = cues[0][1] - cues[0][0]
    tail_dur = cues[1][1] - cues[1][0]
    # First cue has ~77 chars, second has 10 chars ("into life."): first must get >8.5s (not 6.0s!)
    assert first_dur > 8.5, f"first cue raced ahead ({first_dur:.2f}s vs tail {tail_dur:.2f}s)"
    assert tail_dur >= 0.45
