"""Piper — fast local neural TTS (OHF-Voice/piper1-gpl). Unlimited, offline.

Requires `piper` binary + voice model. Auto-detected; skipped when absent.
"""
from __future__ import annotations
import shutil, subprocess
from pathlib import Path
from .base import SpeechProvider, ProviderStatus


class PiperProvider(SpeechProvider):
    name = "piper"

    def status(self) -> ProviderStatus:
        if shutil.which("piper"):
            return ProviderStatus(self.name, True, True, "local piper binary")
        try:
            import piper_tts  # noqa
            return ProviderStatus(self.name, True, True, "piper-tts package")
        except Exception:
            return ProviderStatus(self.name, False, True, "piper not installed (optional)")

    def synthesize(self, text: str, out_path: Path, *, voice: str = "") -> dict:
        from .tts_edge import _audio_duration
        binary = shutil.which("piper")
        if not binary:
            raise RuntimeError("piper binary not installed")
        out_path = Path(out_path).with_suffix(".wav")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [binary, "--output_file", str(out_path)]
        if voice:
            cmd += ["--model", voice]
        subprocess.run(cmd, input=text.encode(), check=True, timeout=600, capture_output=True)
        return {"path": str(out_path), "duration_s": _audio_duration(out_path, text),
                "voice": voice or "default", "provider": self.name}
