"""Groq provider — free tier, no card, OpenAI-compatible endpoint.

Free tier (~14.4k req/day, 30 RPM) covers a video run many times over.
Docs: https://console.groq.com/docs
"""
from __future__ import annotations
from .base import AIProvider, ProviderStatus, CacheMixin
from .openai_compat import chat_complete
from ..config import get_settings

BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(CacheMixin, AIProvider):
    name = "groq"

    def __init__(self):
        CacheMixin.__init__(self, "groq")

    def status(self) -> ProviderStatus:
        cfg = get_settings()
        if not cfg.groq_api_key:
            return ProviderStatus(self.name, False, True, "GROQ_API_KEY not set (optional)")
        return ProviderStatus(self.name, True, True, f"free tier, model={cfg.groq_model}")

    def generate(self, prompt: str, *, system: str = "", max_tokens: int = 2000,
                 temperature: float = 0.4) -> str:
        cfg = get_settings()
        if not cfg.groq_api_key:
            raise RuntimeError("GROQ_API_KEY not set")
        cached = self.cache_get(cfg.groq_model, system, prompt, str(max_tokens))
        if cached:
            return cached
        text = chat_complete(BASE_URL, cfg.groq_api_key, cfg.groq_model, prompt,
                             system=system, max_tokens=max_tokens,
                             temperature=temperature)
        self.cache_put(text, cfg.groq_model, system, prompt, str(max_tokens))
        return text
