"""Procedural sound design — CC0, project-generated, $0.

Builds a quiet ambience bed under the narration:
- soft rain/wind wash (filtered noise, very low) for the full duration,
- 2-3 distant thunder rolls (lowpassed noise bursts with natural decay),
- optionally layered under the generated ambient music bed.

Everything is synthesized with FFmpeg lavfi filters — no downloads, no
copyright risk. Levels are restrained by design (bed gain keeps it well
under the narration).
"""
from __future__ import annotations
import subprocess
from pathlib import Path

from .music import _ffmpeg


def ensure_storm_bed(out_dir: Path, duration_s: float, music_path: str = "") -> dict:
    """Create the final ambience bed. Returns {path, source, license, gain}.

    Falls back gracefully: thunder+rain -> rain-only -> music-only -> none.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # AAC (.m4a): ~10x smaller than WAV for full-length beds (workspace budget).
    out = out_dir / "_storm_bed.m4a"
    exe = _ffmpeg()
    dur = max(30, int(duration_s + 10))
    if exe is None:
        if music_path and Path(music_path).exists():
            return {"path": music_path, "source": "music-only (no ffmpeg for sfx mix)",
                    "license": "CC0 (project-generated)", "gain": 0.08}
        return {"path": "", "source": "none", "license": "", "gain": 0.0}

    # Thunder roll = brown noise, heavy lowpass, attack/decay envelope, delayed.
    # Positions scale with duration so rolls land mid-video, never over the hook.
    t1, t2, t3 = int(dur * 0.30), int(dur * 0.55), int(dur * 0.78)
    inputs: list[str] = []
    mix_parts: list[str] = []
    # rain wash: pink noise, lowpassed, very quiet
    inputs += ["-f", "lavfi", "-i", f"anoisesrc=color=pink:duration={dur}:seed=7"]
    mix_parts.append("[0:a]lowpass=f=900,volume=0.035[rain]")
    # music bed passthrough (already quiet by design)
    labels = ["[rain]"]
    n_in = 1
    if music_path and Path(music_path).exists():
        inputs += ["-i", str(music_path)]
        mix_parts.append(f"[{n_in}:a]volume=0.5[mus]")
        labels.append("[mus]")
        n_in += 1
    # thunder rolls
    for k, (tt, seed) in enumerate(((t1, 11), (t2, 23), (t3, 47))):
        inputs += ["-f", "lavfi", "-i", f"anoisesrc=color=brown:duration=9:seed={seed}"]
        # quick attack, ~6s exponential decay, sub-bass emphasis
        mix_parts.append(
            f"[{n_in}:a]lowpass=f=140,volume='0.9*exp(-0.55*t)+0.05':eval=frame,"
            f"adelay={tt * 1000}|{tt * 1000}[th{k}]")
        labels.append(f"[th{k}]")
        n_in += 1
    filt = (";".join(mix_parts) + f";{''.join(labels)}amix=inputs={len(labels)}"
            f":duration=longest:dropout_transition=2,volume=1.0")
    try:
        subprocess.run([exe, "-y", *inputs, "-filter_complex", filt,
                        "-t", str(dur), "-ar", "44100", "-ac", "2", str(out)],
                       capture_output=True, timeout=300, check=True)
    except Exception:
        # rain-only fallback (simpler graph)
        try:
            subprocess.run(
                [exe, "-y", "-f", "lavfi", "-i",
                 f"anoisesrc=color=pink:duration={dur}:seed=7,lowpass=f=900,volume=0.035",
                 "-t", str(dur), "-ar", "44100", str(out)],
                capture_output=True, timeout=300, check=True)
        except Exception:
            if music_path and Path(music_path).exists():
                return {"path": music_path, "source": "music-only (sfx mix failed)",
                        "license": "CC0 (project-generated)", "gain": 0.08}
            return {"path": "", "source": "none", "license": "", "gain": 0.0}
    if not (out.exists() and out.stat().st_size > 10000):
        if music_path and Path(music_path).exists():
            return {"path": music_path, "source": "music-only (bed too small)",
                    "license": "CC0 (project-generated)", "gain": 0.08}
        return {"path": "", "source": "none", "license": "", "gain": 0.0}
    src = "generated-ambient+procedural-rain-thunder" if music_path else "procedural-rain-thunder"
    return {"path": str(out), "source": src,
            "license": "CC0 (project-generated)", "gain": 0.15}
