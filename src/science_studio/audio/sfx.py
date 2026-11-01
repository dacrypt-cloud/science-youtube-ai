"""Procedural sound design — CC0, project-generated, $0.

Topic-aware ambience under narration:
- Storm/weather topics -> soft rain wash + 2-3 distant thunder rolls + music bed.
- All other science topics -> clean studio air floor + ambient music bed (no thunder/rain).

Everything is synthesized with FFmpeg lavfi filters — no downloads, no
copyright risk. Levels are restrained by design (bed gain keeps it well
under the narration).
"""
from __future__ import annotations
import re
import subprocess
from pathlib import Path

from .music import _ffmpeg

STORM_TOPIC_WORDS = frozenset({
    "lightning", "thunder", "thunderstorm", "thunderstorms", "thundercloud",
    "thunderclouds", "storm", "storms", "hurricane", "hurricanes", "tornado",
    "tornadoes", "cyclone", "typhoon", "monsoon", "rain", "rainfall",
    "downpour", "blizzard", "squall",
})


def is_storm_topic(idea: str) -> bool:
    words = set(re.findall(r"[a-z]{4,}", (idea or "").lower()))
    return bool(words & STORM_TOPIC_WORDS)


def ensure_ambience_bed(out_dir: Path, duration_s: float,
                        music_path: str = "", idea: str = "") -> dict:
    """Topic-appropriate ambience bed. Delegates to storm bed only for weather/storm topics."""
    if is_storm_topic(idea):
        return ensure_storm_bed(out_dir, duration_s, music_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "_ambience_bed.m4a"
    exe = _ffmpeg()
    dur = max(30, int(duration_s + 10))
    if exe is None:
        if music_path and Path(music_path).exists():
            return {"path": music_path, "source": "music-only (no ffmpeg for sfx mix)",
                    "license": "CC0 (project-generated)", "gain": 0.08}
        return {"path": "", "source": "none", "license": "", "gain": 0.0}
    inputs = ["-f", "lavfi", "-i", f"anoisesrc=color=pink:duration={dur}:seed=3"]
    mix_parts = ["[0:a]lowpass=f=450,volume=0.012[air]"]
    labels = ["[air]"]
    if music_path and Path(music_path).exists():
        inputs += ["-i", str(music_path)]
        mix_parts.append("[1:a]volume=0.85[mus]")
        labels.append("[mus]")
    filt = (";".join(mix_parts) + f";{''.join(labels)}amix=inputs={len(labels)}"
            f":duration=longest:dropout_transition=2,volume=1.0")
    try:
        subprocess.run([exe, "-y", *inputs, "-filter_complex", filt,
                        "-t", str(dur), "-ar", "44100", "-ac", "2", str(out)],
                       capture_output=True, timeout=300, check=True)
    except Exception:
        if music_path and Path(music_path).exists():
            return {"path": music_path, "source": "music-only",
                    "license": "CC0 (project-generated)", "gain": 0.08}
        return {"path": "", "source": "none", "license": "", "gain": 0.0}
    if not (out.exists() and out.stat().st_size > 5000):
        if music_path and Path(music_path).exists():
            return {"path": music_path, "source": "music-only",
                    "license": "CC0 (project-generated)", "gain": 0.08}
        return {"path": "", "source": "none", "license": "", "gain": 0.0}
    src = "generated-ambient+studio-air" if music_path else "studio-air"
    return {"path": str(out), "source": src,
            "license": "CC0 (project-generated)", "gain": 0.09}


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
