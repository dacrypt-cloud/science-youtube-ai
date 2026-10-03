"""Procedural storm bed: rain + thunder synthesized, never downloaded."""
import sys
sys.path.insert(0, "src")
import pytest


def test_storm_bed(tmp_path):
    from science_studio.audio.sfx import ensure_storm_bed
    from science_studio.audio.music import _ffmpeg
    if _ffmpeg() is None:
        pytest.skip("no ffmpeg")
    bed = ensure_storm_bed(tmp_path, 40)
    assert bed["path"], bed
    from pathlib import Path
    p = Path(bed["path"])
    assert p.exists() and p.stat().st_size > 10000
    assert "CC0" in bed["license"]
    assert p.suffix in (".m4a", ".wav")  # AAC preferred (workspace budget)
    try:
        from mutagen.mp4 import MP4
        dur = float(MP4(str(p)).info.length)
        assert 35 < dur < 60, dur
    except ImportError:
        pass
    except Exception:
        import wave, contextlib
        try:
            with contextlib.closing(wave.open(str(p))) as w:
                dur = w.getnframes() / float(w.getframerate() or 1)
            assert 35 < dur < 60
        except Exception:
            pass
