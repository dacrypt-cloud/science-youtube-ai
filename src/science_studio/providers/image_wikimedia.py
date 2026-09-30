"""Wikimedia Commons — free media, no key. License per file (CC BY/SA, CC0, PD).

Must attribute creator + license + link. Commercial use allowed for Commons files
(NC/ND files are not hosted on Commons).
"""
from __future__ import annotations
import urllib.parse, urllib.request, json, re
from .base import ImageProvider, ProviderStatus, CacheMixin


class WikimediaImageProvider(CacheMixin, ImageProvider):
    name = "wikimedia"

    def __init__(self):
        CacheMixin.__init__(self, "img-wikimedia")

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, True, True, "commons.wikimedia.org API, no key")

    def search_images(self, query: str, limit: int = 4) -> list[dict]:
        cached = self.cache_get(query, str(limit))
        if cached is not None:
            return cached
        out: list[dict] = []
        try:
            params = urllib.parse.urlencode({
                "action": "query", "format": "json", "generator": "search",
                "gsrsearch": f"filetype:bitmap {query}", "gsrnamespace": 6,
                "gsrlimit": min(limit * 2, 20), "prop": "imageinfo",
                "iiprop": "url|user|extmetadata", "iiurlwidth": 1280,
            })
            url = "https://commons.wikimedia.org/w/api.php?" + params
            req = urllib.request.Request(url, headers={"User-Agent": "science-youtube-ai/0.1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
            pages = (data.get("query") or {}).get("pages", {})
            for pg in list(pages.values())[:limit * 2]:
                ii = (pg.get("imageinfo") or [{}])[0]
                meta = ii.get("extmetadata") or {}
                lic = (meta.get("LicenseShortName") or {}).get("value", "")
                artist = re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", ""))[:120]
                imgurl = ii.get("thumburl") or ii.get("url") or ""
                if not imgurl or not imgurl.startswith("http"):
                    continue
                out.append({
                    "url": imgurl, "thumb": ii.get("thumburl", ""),
                    "title": pg.get("title", ""), "creator": artist or ii.get("user", ""),
                    "license": lic or "see Commons page",
                    "page_url": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(pg.get("title", "").replace(" ", "_")),
                    "width": ii.get("thumbwidth", 1280), "height": ii.get("thumbheight", 720),
                })
                if len(out) >= limit:
                    break
        except Exception:
            out = []
        self.cache_put(out, query, str(limit))
        return out
