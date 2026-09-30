"""Wikipedia / MediaWiki search + extracts. Free, no key. CC BY-SA (attribute)."""
from __future__ import annotations
import urllib.parse, urllib.request, json
from .base import SearchProvider, ProviderStatus, CacheMixin


class WikipediaSearchProvider(CacheMixin, SearchProvider):
    name = "wikipedia"

    def __init__(self):
        CacheMixin.__init__(self, "search-wikipedia")

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, True, True, "MediaWiki API, no key")

    def _get(self, params: dict) -> dict:
        params = {"format": "json", **params}
        url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "science-youtube-ai/0.1 (research; contact: local)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())

    def search(self, query: str, limit: int = 8) -> list[dict]:
        cached = self.cache_get(query, str(limit))
        if cached is not None:
            return cached
        out: list[dict] = []
        try:
            data = self._get({"action": "query", "list": "search", "srsearch": query,
                              "srlimit": limit, "srprop": "snippet"})
            hits = data.get("query", {}).get("search", [])
            for h in hits:
                title = h.get("title", "")
                # fetch extract
                try:
                    ex = self._get({"action": "query", "prop": "extracts", "exintro": 1,
                                    "explaintext": 1, "titles": title})
                    pages = ex.get("query", {}).get("pages", {})
                    text = ""
                    for pg in pages.values():
                        text = (pg.get("extract") or "")[:2000]
                    url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
                    out.append({"title": title, "url": url, "snippet": text,
                                "source_type": "reference", "publisher": "Wikipedia",
                                "reliability": 3})
                except Exception:
                    continue
        except Exception as e:
            out = []
        self.cache_put(out, query, str(limit))
        return out
