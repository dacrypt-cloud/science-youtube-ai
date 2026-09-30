import pytest
from pathlib import Path

def test_render_short(tmp_path):
    from science_studio.providers.render_ffmpeg import FFmpegRenderer
    r = FFmpegRenderer()
    st = r.status()
    if not st.available:
        pytest.skip("no ffmpeg")
    from science_studio.providers.tts_silent import SilentSpeechProvider
    tts = SilentSpeechProvider()
    a = tts.synthesize("Short test narration for rendering.", tmp_path / "a.wav")
    job = {"width": 640, "height": 360, "fps": 24,
           "scenes": [{"title": "Test", "onscreen_text": "hello", "image": "",
                       "audio": a["path"], "duration_s": a["duration_s"]}], "music": ""}
    out = r.render(job, tmp_path / "v.mp4")
    assert Path(out["path"]).exists()

def test_render_relative_path(tmp_path, monkeypatch):
    """Regression: concat must work with relative out paths (ffmpeg resolves
    relative to the list file, so the renderer must write absolute paths)."""
    import pytest
    from science_studio.providers.render_ffmpeg import FFmpegRenderer
    r = FFmpegRenderer()
    if not r.status().available:
        pytest.skip("no ffmpeg")
    monkeypatch.chdir(tmp_path)
    from science_studio.providers.tts_silent import SilentSpeechProvider
    tts = SilentSpeechProvider()
    a = tts.synthesize("Relative path test.", "a.wav")
    job = {"width": 320, "height": 180, "fps": 24,
           "scenes": [{"title": "T", "onscreen_text": "", "image": "",
                       "audio": a["path"], "duration_s": a["duration_s"]}], "music": ""}
    out = r.render(job, "video/v.mp4")
    import pathlib
    assert pathlib.Path(out["path"]).exists()


def test_qa(tmp_path):
    from science_studio.video.qa import run_qa
    qa = run_qa("t", tmp_path, [], [], [], tmp_path / "no.mp4", {}, [])
    assert qa["status"] in ("pass", "review", "fail")
    assert len(qa["checks"]) >= 8
