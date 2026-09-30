"""Edge TTS — Microsoft Edge read-aloud voices via edge-tts. Free, no key.

Unofficial service: fine for $0 hobby/research use, may throttle. Primary default.
"""
from __future__ import annotations
import asyncio
from pathlib import Path
from .base import SpeechProvider, ProviderStatus
from ..config import get_settings


class EdgeTTSProvider(SpeechProvider):
    name = "edge-tts"

    def status(self) -> ProviderStatus:
        try:
            import edge_tts  # noqa
        except Exception:
            return ProviderStatus(self.name, False, True, "edge-tts package not installed")
        return ProviderStatus(self.name, True, True, f"voice={get_settings().edge_voice}, no key")

    def synthesize(self, text: str, out_path: Path, *, voice: str = "") -> dict:
        import edge_tts
        v = voice or get_settings().edge_voice
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        async def _run():
            comm = edge_tts.Communicate(text, v)
            await comm.save(str(out_path))

        # edge-tts needs an event loop; handle nested-loop environments
        try:
            asyncio.run(_run())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(_run())
            finally:
                loop.close()
        dur = _audio_duration(out_path, text)
        return {"path": str(out_path), "duration_s": dur, "voice": v, "provider": self.name}


def _audio_duration(path: Path, text: str = "") -> float:
    try:
        from mutagen.mp3 import MP3
        return float(MP3(str(path)).info.length)
    except Exception:
        pass
    try:
        import wave, contextlib
        with contextlib.closing(wave.open(str(path))) as f:
            return float(f.getnframes()) / float(f.getframerate() or 1)
    except Exception:
        pass
    # fallback estimate ~850 chars/min
    return max(1.0, len(text) / 850 * 60) if text else 1.0
