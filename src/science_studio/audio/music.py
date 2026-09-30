"""Background music — only legally safe sources.

Default: procedurally generated ambient bed (FFmpeg sine pads, CC0, project-made).
Optional: user-supplied files in production/music/ (must record license).
Never scrapes YouTube / copyrighted music.
"""
from __future__ import annotations
import subprocess, shutil
from pathlib import Path


def _ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ensure_music(music_dir: Path, duration_s: float) -> dict:
    music_dir.mkdir(parents=True, exist_ok=True)
    # user files take precedence
    for ext in ("*.mp3", "*.wav", "*.ogg", "*.m4a"):
        for f in sorted(music_dir.glob(ext)):
            if f.name.startswith("_"):
                continue
            return {"path": str(f), "source": "user-supplied",
                    "license": "see user documentation — verify before upload",
                    "gain": 0.08}
    # generate ambient bed
    exe = _ffmpeg()
    out = music_dir / "_generated_ambient.wav"
    if exe and not (out.exists() and out.stat().st_size > 10000):
        dur = max(30.0, duration_s + 10)
        # layered soft sines (A2+E3+A3) w/ slow tremolo — quiet by design
        filt = ("sine=frequency=110:duration={d},volume=0.12[a];"
                "sine=frequency=164.8:duration={d},volume=0.08[b];"
                "sine=frequency=220:duration={d},volume=0.06[c];"
                "[a][b][c]amix=inputs=3:duration=longest,tremolo=f=0.15:d=0.6").format(d=int(dur))
        try:
            subprocess.run([exe, "-y", "-f", "lavfi", "-i", filt, "-t", str(int(dur)),
                            "-ar", "44100", str(out)],
                           capture_output=True, timeout=300, check=True)
        except Exception:
            return {"path": "", "source": "none", "license": "", "gain": 0.0}
    if out.exists():
        return {"path": str(out), "source": "generated-sine-ambient",
                "license": "CC0 (project-generated)", "gain": 0.08}
    return {"path": "", "source": "none", "license": "", "gain": 0.0}
