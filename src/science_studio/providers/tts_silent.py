"""Silent fallback — generates timed silence so the pipeline NEVER dies.

Clearly labelled provider='silent-fallback'. Used only when every real TTS fails.
Duration is estimated from text length (~150 wpm spoken English).
"""
from __future__ import annotations
import subprocess, wave, struct
from pathlib import Path
from .base import SpeechProvider, ProviderStatus


def estimate_duration(text: str, wpm: int = 150) -> float:
    words = max(1, len(text.split()))
    return max(1.0, words / wpm * 60)


class SilentSpeechProvider(SpeechProvider):
    name = "silent-fallback"

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, True, True, "always available, silence with estimated timing")

    def synthesize(self, text: str, out_path: Path, *, voice: str = "") -> dict:
        out_path = Path(out_path).with_suffix(".wav")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        dur = estimate_duration(text)
        # Try ffmpeg for mp3-length silence, else plain wav.
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            subprocess.run([exe, "-y", "-f", "lavfi", "-i",
                            f"anullsrc=r=44100:cl=mono:d={dur:.2f}",
                            "-c:a", "pcm_s16le", str(out_path)],
                           check=True, capture_output=True, timeout=120)
        except Exception:
            sr = 22050
            n = int(sr * dur)
            with wave.open(str(out_path), "w") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes(struct.pack("<" + "h" * n, *([0] * n)))
        return {"path": str(out_path), "duration_s": dur,
                "voice": "silent", "provider": self.name}
