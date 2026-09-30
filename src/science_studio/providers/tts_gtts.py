"""gTTS — Google Translate TTS. Free, no key. Rate-limited; fallback option."""
from __future__ import annotations
from pathlib import Path
from .base import SpeechProvider, ProviderStatus


class GTTSProvider(SpeechProvider):
    name = "gtts"

    def status(self) -> ProviderStatus:
        try:
            import gtts  # noqa
        except Exception:
            return ProviderStatus(self.name, False, True, "gTTS package not installed")
        return ProviderStatus(self.name, True, True, "free, no key, rate-limited")

    def synthesize(self, text: str, out_path: Path, *, voice: str = "") -> dict:
        from gtts import gTTS
        from .tts_edge import _audio_duration
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        gTTS(text=text, lang="en").save(str(out_path))
        return {"path": str(out_path), "duration_s": _audio_duration(out_path, text),
                "voice": "gtts-en", "provider": self.name}
