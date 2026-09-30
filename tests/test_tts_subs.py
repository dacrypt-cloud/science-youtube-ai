from pathlib import Path
from science_studio.providers.tts_silent import SilentSpeechProvider, estimate_duration
from science_studio.audio.subtitles import build_subtitles

def test_silent_tts(tmp_path):
    p = SilentSpeechProvider()
    assert p.status().available
    r = p.synthesize("Hello world, this is a test of the narration system.", tmp_path / "t.wav")
    assert Path(r["path"]).exists() and r["duration_s"] > 0

def test_estimate():
    assert estimate_duration("word " * 150) == 60.0

def test_subtitles(tmp_path):
    board = [{"scene_id": "scene_01", "narration": "one two three four five six seven eight"}]
    out = build_subtitles(board, {"scene_01": 8.0}, tmp_path)
    assert Path(out["srt"]).exists() and Path(out["vtt"]).exists()
