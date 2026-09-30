"""OpenAlex — free scholarly index, no key (mailto polite). CC0 API.

Note: anonymous search is occasionally rate-limited; we retry with backoff and
the engine treats other searchers as fallback.
"""
from __future__ import annotations
import urllib.parse, urllib.request, json, time
from .base import SearchProvider, ProviderStatus, CacheMixin


class OpenAlexSearchProvider(CacheMixin, SearchProvider):
    name = "openalex"

    def __init__(self):
        CacheMixin.__init__(self, "search-openalex")

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, True, True, "api.openalex.org, no key")

    def search(self, query: str, limit: int = 8) -> list[dict]:
        cached = self.cache_get(query, str(limit))
        if cached is not None:
            return cached
        out: list[dict] = []
        for attempt in range(2):
            try:
                q = urllib.parse.urlencode({"search": query, "per-page": min(limit, 25),
                                            "mailto": "science-youtube-ai@localhost"})
                url = "https://api.openalex.org/works?" + q
                req = urllib.request.Request(url, headers={"User-Agent": "science-youtube-ai/0.1"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = json.loads(r.read().decode())
                if "results" not in data:
                    raise RuntimeError(str(data)[:150])
                for w in data.get("results", [])[:limit]:
                    title = w.get("title") or w.get("display_name") or "Untitled"
                    doi = (w.get("doi") or "").replace("https://doi.org/", "")
                    url2 = w.get("doi") or w.get("id", "")
                    year = w.get("publication_year", "")
                    venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name", "")
                    cited = w.get("cited_by_count", 0)
                    ab = w.get("abstract_inverted_index")
                    snippet = ""
                    if ab:
                        try:
                            pos = {}
                            for word, idxs in ab.items():
                                for i in idxs:
                                    pos[i] = word
                            snippet = " ".join(pos[i] for i in sorted(pos)[:80])
                        except Exception:
                            snippet = ""
                    out.append({"title": title, "url": url2, "snippet": snippet,
                                "source_type": "journal", "publisher": venue or "OpenAlex",
                                "publication_date": str(year), "doi": doi,
                                "reliability": 5 if cited else 4})
                break
            except Exception:
                out = []
                time.sleep(3 * (attempt + 1))
        self.cache_put(out, query, str(limit))
        return out
