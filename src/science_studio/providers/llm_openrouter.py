"""OpenRouter provider — free :free models, no card, OpenAI-compatible.

Default model `openrouter/free` auto-routes to an available free model, so no
model ID can go stale. Free tier ~200 req/day per key — plenty per video run.
Docs: https://openrouter.ai/docs
"""
from __future__ import annotations
from .base import AIProvider, ProviderStatus, CacheMixin
from .openai_compat import chat_complete
from ..config import get_settings

BASE_URL = "https://openrouter.ai/api/v1"
HEADERS = {"HTTP-Referer": "https://github.com/dacrypt-cloud/science-youtube-ai",
           "X-Title": "science-youtube-ai"}


class OpenRouterProvider(CacheMixin, AIProvider):
    name = "openrouter"

    def __init__(self):
        CacheMixin.__init__(self, "openrouter")

    def status(self) -> ProviderStatus:
        cfg = get_settings()
        if not cfg.openrouter_api_key:
            return ProviderStatus(self.name, False, True, "OPENROUTER_API_KEY not set (optional)")
        return ProviderStatus(self.name, True, True, f"free tier, model={cfg.openrouter_model}")

    def generate(self, prompt: str, *, system: str = "", max_tokens: int = 2000,
                 temperature: float = 0.4) -> str:
        cfg = get_settings()
        if not cfg.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        cached = self.cache_get(cfg.openrouter_model, system, prompt, str(max_tokens))
        if cached:
            return cached
        text = chat_complete(BASE_URL, cfg.openrouter_api_key, cfg.openrouter_model,
                             prompt, system=system, max_tokens=max_tokens,
                             temperature=temperature, extra_headers=HEADERS)
        self.cache_put(text, cfg.openrouter_model, system, prompt, str(max_tokens))
        return text
