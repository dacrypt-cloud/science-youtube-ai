"""DuckDuckGo Instant Answer API — free, no key. Best-effort web backup.

Prioritises .gov/.edu/official domains when present.
"""
from __future__ import annotations
import urllib.parse, urllib.request, json
from .base import SearchProvider, ProviderStatus, CacheMixin


class DuckDuckGoSearchProvider(CacheMixin, SearchProvider):
    name = "duckduckgo"

    def __init__(self):
        CacheMixin.__init__(self, "search-ddg")

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, True, True, "api.duckduckgo.com, no key, best-effort")

    def search(self, query: str, limit: int = 8) -> list[dict]:
        cached = self.cache_get(query, str(limit))
        if cached is not None:
            return cached
        out: list[dict] = []
        try:
            q = urllib.parse.urlencode({"q": query, "format": "json", "no_html": 1, "skip_disambig": 1})
            url = "https://api.duckduckgo.com/?" + q
            req = urllib.request.Request(url, headers={"User-Agent": "science-youtube-ai/0.1"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode())
            if data.get("AbstractText"):
                out.append({"title": data.get("Heading") or query,
                            "url": data.get("AbstractURL") or "",
                            "snippet": data.get("AbstractText", "")[:800],
                            "source_type": "reference",
                            "publisher": data.get("AbstractSource") or "DuckDuckGo",
                            "reliability": 3})
            for t in (data.get("RelatedTopics") or [])[:limit]:
                if isinstance(t, dict) and t.get("FirstURL"):
                    rel = 4 if any(d in t["FirstURL"] for d in (".gov", ".edu", "nih.gov", "cdc.gov", "who.int", "nasa.gov")) else 2
                    out.append({"title": (t.get("Text") or "")[:120], "url": t["FirstURL"],
                                "snippet": (t.get("Text") or "")[:500],
                                "source_type": "reference" if rel >= 3 else "other",
                                "publisher": "web", "reliability": rel})
        except Exception:
            out = []
        self.cache_put(out[:limit], query, str(limit))
        return out[:limit]
