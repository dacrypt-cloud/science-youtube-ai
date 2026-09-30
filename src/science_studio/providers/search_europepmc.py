"""Europe PMC — free life-science literature, no key. Good for biomedical topics."""
from __future__ import annotations
import urllib.parse, urllib.request, json
from .base import SearchProvider, ProviderStatus, CacheMixin


class EuropePCMSearchProvider(CacheMixin, SearchProvider):
    name = "europepmc"

    def __init__(self):
        CacheMixin.__init__(self, "search-europepmc")

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, True, True, "ebi.ac.uk/europepmc, no key")

    def search(self, query: str, limit: int = 8) -> list[dict]:
        cached = self.cache_get(query, str(limit))
        if cached is not None:
            return cached
        out: list[dict] = []
        try:
            q = urllib.parse.urlencode({"query": query, "format": "json",
                                        "pageSize": min(limit, 25),
                                        "resultType": "core"})
            url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + q
            req = urllib.request.Request(url, headers={"User-Agent": "science-youtube-ai/0.1"})
            with urllib.request.urlopen(req, timeout=12) as r:
                data = json.loads(r.read().decode())
            for d in (data.get("resultList", {}).get("result", []) or [])[:limit]:
                title = d.get("title", "Untitled")
                src = d.get("source", "")
                pmid = d.get("pmid", "")
                doi = d.get("doi", "")
                journal = d.get("journalTitle", "")
                year = d.get("pubYear", "")
                url2 = f"https://europepmc.org/article/{src}/{d.get('id', '')}" if d.get("id") else (
                    f"https://doi.org/{doi}" if doi else "")
                out.append({"title": title, "url": url2, "snippet": (d.get("abstractText") or "")[:800],
                            "source_type": "journal", "publisher": journal or "Europe PMC",
                            "publication_date": str(year), "doi": doi,
                            "authors": d.get("authorString", "")[:200], "reliability": 5})
        except Exception:
            out = []
        self.cache_put(out, query, str(limit))
        return out
