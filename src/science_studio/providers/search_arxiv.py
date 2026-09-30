"""arXiv — free preprints (physics/math/cs/bio). No key. Treat as preprint evidence."""
from __future__ import annotations
import urllib.parse, urllib.request, xml.etree.ElementTree as ET
from .base import SearchProvider, ProviderStatus, CacheMixin


class ArxivSearchProvider(CacheMixin, SearchProvider):
    name = "arxiv"

    def __init__(self):
        CacheMixin.__init__(self, "search-arxiv")

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, True, True, "export.arxiv.org, no key")

    def search(self, query: str, limit: int = 8) -> list[dict]:
        cached = self.cache_get(query, str(limit))
        if cached is not None:
            return cached
        out: list[dict] = []
        try:
            q = urllib.parse.urlencode({"search_query": f"all:{query}",
                                        "start": 0, "max_results": min(limit, 20)})
            url = "http://export.arxiv.org/api/query?" + q
            req = urllib.request.Request(url, headers={"User-Agent": "science-youtube-ai/0.1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                xml = r.read().decode()
            ns = {"a": "http://www.w3.org/2005/Atom"}
            root = ET.fromstring(xml)
            for e in root.findall("a:entry", ns)[:limit]:
                title = (e.findtext("a:title", default="", namespaces=ns) or "").strip().replace("\n", " ")
                link = (e.findtext("a:id", default="", namespaces=ns) or "").strip()
                summ = (e.findtext("a:summary", default="", namespaces=ns) or "").strip().replace("\n", " ")[:800]
                pub = (e.findtext("a:published", default="", namespaces=ns) or "")[:10]
                out.append({"title": title, "url": link, "snippet": summ,
                            "source_type": "preprint", "publisher": "arXiv",
                            "publication_date": pub, "reliability": 3})
        except Exception:
            out = []
        self.cache_put(out, query, str(limit))
        return out
