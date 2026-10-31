"""Shared OpenAI-compatible chat client (Groq, OpenRouter, ...).

Both vendors speak POST {base_url}/chat/completions with bearer auth and the
same JSON shape — one client, thin provider wrappers, one mock point.
"""
from __future__ import annotations
import json
import time
import urllib.request


def chat_complete(base_url: str, api_key: str, model: str, prompt: str, *,
                  system: str = "", max_tokens: int = 2000,
                  temperature: float = 0.4,
                  extra_headers: dict | None = None,
                  timeout: int = 60, tries: int = 3) -> str:
    """POST a chat-completions request. Returns stripped text; raises on failure."""
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    body = json.dumps({"model": model, "messages": msgs,
                       "temperature": temperature,
                       "max_tokens": max_tokens}).encode()
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {api_key}"}
    if extra_headers:
        headers.update(extra_headers)
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions",
                                         data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode())
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError(f"no choices: {str(data)[:300]}")
            text = (choices[0].get("message", {}).get("content") or "").strip()
            if not text:
                raise RuntimeError("empty choice")
            return text
        except Exception as e:
            last = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"chat completions failed: {last}")
