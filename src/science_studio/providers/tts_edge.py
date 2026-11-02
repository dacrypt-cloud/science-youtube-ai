"""Edge TTS — Microsoft Edge read-aloud voices via edge-tts. Free, no key.

Streams neural audio + exact WordBoundary events in a single pass so on-screen
captions highlight each word at the exact millisecond the voice speaks it.
"""
from __future__ import annotations
import asyncio
import re
from pathlib import Path
from .base import SpeechProvider, ProviderStatus
from ..config import get_settings


def align_word_events(text: str, events: list[dict]) -> list[dict]:
    """Attach punctuation from `text` to Edge WordBoundary events and return
    `[{"word": str, "start_s": float, "end_s": float}, ...]`."""
    src = text or ""
    pos = 0
    out: list[dict] = []
    for ev in events:
        wtxt = (ev.get("text") or "").strip()
        if not wtxt:
            continue
        st = max(0.0, float(ev.get("offset", 0)) / 1e7)
        en = st + max(0.03, float(ev.get("duration", 0)) / 1e7)
        while pos < len(src) and src[pos].isspace():
            pos += 1
        window = src[pos:pos + max(80, len(wtxt) * 4)]
        idx = window.lower().find(wtxt.lower())
        disp = wtxt
        if idx >= 0:
            abs_start = pos + idx
            lead = src[pos:abs_start]
            if lead and all(ch in "\"'“”‘’([" for ch in lead):
                abs_start = pos
            abs_end = pos + idx + len(wtxt)
            while abs_end < len(src) and not src[abs_end].isspace():
                abs_end += 1
            disp = src[abs_start:abs_end]
            pos = abs_end
            m_dash = re.match(r"^(\s+[—–-])(?=\s|$)", src[pos:])
            if m_dash:
                pos += len(m_dash.group(1))
                disp = disp + " " + m_dash.group(1).strip()
        parts = disp.split()
        if len(parts) <= 1:
            out.append({"word": disp, "start_s": round(st, 3), "end_s": round(en, 3)})
        else:
            tot = sum(max(1, len(p)) for p in parts)
            cur = st
            for p in parts:
                nxt = cur + (en - st) * (max(1, len(p)) / tot)
                out.append({"word": p, "start_s": round(cur, 3), "end_s": round(nxt, 3)})
                cur = nxt
    return out


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
        events: list[dict] = []

        async def _run():
            try:
                comm = edge_tts.Communicate(text, v, boundary="WordBoundary")
            except TypeError:
                # Older edge-tts without boundary kwarg
                comm = edge_tts.Communicate(text, v)
            with open(out_path, "wb") as f:
                async for chunk in comm.stream():
                    ctype = chunk.get("type")
                    if ctype == "audio":
                        f.write(chunk["data"])
                    elif ctype == "WordBoundary":
                        events.append(chunk)

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
        words = align_word_events(text, events) if events else []
        return {"path": str(out_path), "duration_s": dur, "voice": v,
                "provider": self.name, "words": words}


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
