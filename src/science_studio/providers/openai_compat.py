"""Shared OpenAI-compatible chat client (Groq, OpenRouter, ...).

Both vendors speak POST {base_url}/chat/completions with bearer auth and the
same JSON shape — one client, thin provider wrappers, one mock point.
"""
from __future__ import annotations
import json
import re
import time
import urllib.error
import urllib.request


def extract_json_array(text: str) -> list:
    """Extract the best top-level JSON array from LLM output.

    Tolerates <think>...</think> blocks, ```json fences, and stray [brackets]
    in prose (which break greedy regexes like r'\\[.*\\]').
    """
    cleaned = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S | re.I).strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I).strip()
    dec = json.JSONDecoder()
    best: list | None = None
    pos = 0
    while True:
        idx = cleaned.find("[", pos)
        if idx < 0:
            break
        try:
            obj, _ = dec.raw_decode(cleaned, idx)
            if isinstance(obj, list):
                if obj and all(isinstance(x, dict) for x in obj):
                    return obj
                if best is None or len(obj) > len(best):
                    best = obj
        except Exception:
            pass
        pos = idx + 1
    if best is not None:
        return best
    raise ValueError("no valid JSON array found in LLM response")


def chat_complete(base_url: str, api_key: str, model: str, prompt: str, *,
                  system: str = "", max_tokens: int = 2000,
                  temperature: float = 0.4,
                  extra_headers: dict | None = None,
                  timeout: int = 90, tries: int = 3) -> str:
    """POST a chat-completions request. Returns stripped text; raises on failure."""
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    body = json.dumps({"model": model, "messages": msgs,
                       "temperature": temperature,
                       "max_tokens": max_tokens}).encode()
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {api_key}",
               # urllib's default UA gets 403 from some WAFs; identify honestly.
               "User-Agent": "science-youtube-ai/0.1"}
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
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode(errors="ignore")[:240]
            except Exception:
                pass
            last = RuntimeError(f"HTTP {e.code}: {detail or e.reason}")
            if e.code in (401, 403, 413):
                break  # auth or request-too-large won't succeed on retry; let chain fall over
            wait = 2 ** attempt
            if e.code == 429:
                try:
                    ra = float(e.headers.get("Retry-After", "0") or 0)
                    if 0 < ra <= 12:
                        wait = max(wait, ra)
                except Exception:
                    pass
            if attempt + 1 < tries:
                time.sleep(wait)
        except Exception as e:
            last = e
            if attempt + 1 < tries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"chat completions failed: {last}")
