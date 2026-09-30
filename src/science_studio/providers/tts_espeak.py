"""espeak-ng — local, offline, unlimited. Robotic but always works if installed."""
from __future__ import annotations
import shutil, subprocess
from pathlib import Path
from .base import SpeechProvider, ProviderStatus


class EspeakProvider(SpeechProvider):
    name = "espeak"

    def status(self) -> ProviderStatus:
        if shutil.which("espeak-ng") or shutil.which("espeak"):
            return ProviderStatus(self.name, True, True, "local binary")
        return ProviderStatus(self.name, False, True, "espeak-ng not installed")

    def synthesize(self, text: str, out_path: Path, *, voice: str = "") -> dict:
        from .tts_edge import _audio_duration
        binary = shutil.which("espeak-ng") or shutil.which("espeak")
        if not binary:
            raise RuntimeError("espeak not installed")
        out_path = Path(out_path).with_suffix(".wav")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([binary, "-v", voice or "en", "-s", "165", "-w", str(out_path), text],
                       check=True, timeout=300, capture_output=True)
        return {"path": str(out_path), "duration_s": _audio_duration(out_path, text),
                "voice": voice or "en", "provider": self.name}
