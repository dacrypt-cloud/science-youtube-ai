"""Builds the provider stack from current config. Free-first ordering, honest status."""
from __future__ import annotations
from dataclasses import dataclass, field
from ..config import get_settings


@dataclass
class ProviderStack:
    ai: object = None
    ai_chain: list = field(default_factory=list)
    searchers: list = field(default_factory=list)
    images: list = field(default_factory=list)
    videos: list = field(default_factory=list)
    speech: object = None
    speech_chain: list = field(default_factory=list)
    renderer: object = None

    def status_report(self) -> dict:
        def s(p):
            try:
                st = p.status()
                return {"name": st.name, "available": st.available, "free": st.free, "reason": st.reason}
            except Exception as e:
                return {"name": getattr(p, "name", "?"), "available": False, "reason": str(e)}
        return {
            "ai_chain": [s(p) for p in self.ai_chain],
            "searchers": [s(p) for p in self.searchers],
            "images": [s(p) for p in self.images],
            "videos": [s(p) for p in self.videos],
            "speech_chain": [s(p) for p in self.speech_chain],
            "renderer": s(self.renderer) if self.renderer else None,
        }


def build_providers() -> ProviderStack:
    from .llm_gemini import GeminiProvider
    from .llm_groq import GroqProvider
    from .llm_openrouter import OpenRouterProvider
    from .llm_template import TemplateAIProvider
    from .search_wikipedia import WikipediaSearchProvider
    from .search_openalex import OpenAlexSearchProvider
    from .search_europepmc import EuropePCMSearchProvider
    from .search_arxiv import ArxivSearchProvider
    from .search_duckduckgo import DuckDuckGoSearchProvider
    from .image_wikimedia import WikimediaImageProvider
    from .image_pexels import PexelsImageProvider, PexelsVideoProvider
    from .image_pixabay import PixabayImageProvider, PixabayVideoProvider
    from .tts_edge import EdgeTTSProvider
    from .tts_gtts import GTTSProvider
    from .tts_espeak import EspeakProvider
    from .tts_silent import SilentSpeechProvider
    from .render_ffmpeg import FFmpegRenderer

    cfg = get_settings()
    stack = ProviderStack()

    # AI chain: Gemini -> Groq -> OpenRouter (all free tiers) -> Ollama
    # (local, optional) -> template fallback (always works).
    ai_chain: list = []
    for cls in (GeminiProvider, GroqProvider, OpenRouterProvider):
        p = cls()
        if p.status().available:
            ai_chain.append(p)
    if cfg.ollama_base_url:
        try:
            from .llm_ollama import OllamaProvider
            ol = OllamaProvider()
            if ol.status().available:
                ai_chain.append(ol)
        except Exception:
            pass
    ai_chain.append(TemplateAIProvider())
    stack.ai_chain = ai_chain
    stack.ai = ai_chain[0]

    stack.searchers = [
        WikipediaSearchProvider(),
        OpenAlexSearchProvider(),
        EuropePCMSearchProvider(),
        ArxivSearchProvider(),
        DuckDuckGoSearchProvider(),
    ]
    stack.images = [WikimediaImageProvider(), PexelsImageProvider(), PixabayImageProvider()]
    stack.videos = [PexelsVideoProvider(), PixabayVideoProvider()]
    # Speech chain ordered by quality; silent fallback guarantees the pipeline never dies.
    order = {"edge": 0, "gtts": 1, "espeak": 2, "piper": 1, "silent": 9}
    cands = [EdgeTTSProvider(), GTTSProvider(), EspeakProvider(), SilentSpeechProvider()]
    try:
        from .tts_piper import PiperProvider
        cands.insert(2, PiperProvider())
    except Exception:
        pass
    pref = (cfg.default_voice or "edge").lower()
    cands.sort(key=lambda p: (0 if pref in p.name else 1, order.get(p.name.split("-")[0], 5)))
    # Always keep silent last as guarantee.
    cands = [c for c in cands if "silent" not in c.name] + [SilentSpeechProvider()]
    stack.speech_chain = cands
    stack.speech = cands[0]
    stack.renderer = FFmpegRenderer()
    return stack


def ai_generate(stack: ProviderStack, prompt: str, *, system: str = "",
                max_tokens: int = 2000, temperature: float = 0.4) -> tuple[str, str]:
    """Try AI providers in order. Returns (text, provider_name). Never returns fake success."""
    errors = []
    for p in stack.ai_chain:
        try:
            st = p.status()
            if not st.available:
                errors.append(f"{p.name}: unavailable ({st.reason})")
                continue
            text = p.generate(prompt, system=system, max_tokens=max_tokens, temperature=temperature)
            if text and text.strip():
                return text.strip(), p.name
            errors.append(f"{p.name}: empty response")
        except Exception as e:
            errors.append(f"{p.name}: {e}")
    raise RuntimeError("All AI providers failed: " + " | ".join(errors))
