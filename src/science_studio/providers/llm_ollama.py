"""Optional local LLM via Ollama (free, offline after pull). Never required."""
from __future__ import annotations
import json, urllib.request
from .base import AIProvider, ProviderStatus, CacheMixin
from ..config import get_settings


class OllamaProvider(CacheMixin, AIProvider):
    name = "ollama"

    def __init__(self):
        CacheMixin.__init__(self, "ollama")

    def status(self) -> ProviderStatus:
        base = get_settings().ollama_base_url
        if not base:
            return ProviderStatus(self.name, False, True, "OLLAMA_BASE_URL not set")
        try:
            with urllib.request.urlopen(base.rstrip("/") + "/api/tags", timeout=5) as r:
                if r.status == 200:
                    return ProviderStatus(self.name, True, True, "local ollama reachable")
        except Exception as e:
            return ProviderStatus(self.name, False, True, f"unreachable: {e}")
        return ProviderStatus(self.name, False, True, "unreachable")

    def generate(self, prompt: str, *, system: str = "", max_tokens: int = 2000,
                 temperature: float = 0.4) -> str:
        cfg = get_settings()
        cached = self.cache_get(cfg.ollama_model, system, prompt, str(max_tokens))
        if cached:
            return cached
        url = cfg.ollama_base_url.rstrip("/") + "/api/generate"
        body = json.dumps({
            "model": cfg.ollama_model, "prompt": prompt, "system": system,
            "stream": False, "options": {"temperature": temperature, "num_predict": max_tokens},
        }).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
        text = (data.get("response") or "").strip()
        if not text:
            raise RuntimeError("ollama empty response")
        self.cache_put(text, cfg.ollama_model, system, prompt, str(max_tokens))
        return text
