"""Gemini provider — Google AI Studio free tier (Flash models, no card required).

Researched Sep 2026: free tier ~1,500 RPD / 15 RPM for Flash, 1M TPM, no expiry;
Pro models effectively paid-only since Apr 2026. Free-tier data may train Google models.
Docs: https://aistudio.google.com + https://ai.google.dev/pricing
"""
from __future__ import annotations
import json, time, urllib.request
from .base import AIProvider, ProviderStatus, CacheMixin
from ..config import get_settings


class GeminiProvider(CacheMixin, AIProvider):
    name = "gemini"

    def __init__(self):
        CacheMixin.__init__(self, "gemini")

    def status(self) -> ProviderStatus:
        key = get_settings().gemini_api_key
        if not key:
            return ProviderStatus(self.name, False, True, "GEMINI_API_KEY not set")
        return ProviderStatus(self.name, True, True, f"free tier, model={get_settings().gemini_model}")

    def generate(self, prompt: str, *, system: str = "", max_tokens: int = 2000,
                 temperature: float = 0.4) -> str:
        cfg = get_settings()
        if not cfg.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        cached = self.cache_get(cfg.gemini_model, system, prompt, str(max_tokens))
        if cached:
            return cached
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{cfg.gemini_model}:generateContent?key={cfg.gemini_api_key}")
        full = f"{system}\n\n{prompt}" if system else prompt
        body = json.dumps({
            "contents": [{"parts": [{"text": full}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }).encode()
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode())
                cands = data.get("candidates", [])
                if not cands:
                    raise RuntimeError(f"no candidates: {str(data)[:300]}")
                parts = cands[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts).strip()
                if text:
                    self.cache_put(text, cfg.gemini_model, system, prompt, str(max_tokens))
                    return text
                raise RuntimeError("empty candidates")
            except Exception as e:
                last_err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"Gemini failed: {last_err}")
