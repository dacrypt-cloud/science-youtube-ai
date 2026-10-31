"""Pixabay — free images+video, free key. ~100 req/min. Pixabay Content License:
free commercial use, no attribution required (credit appreciated). Cache 24h+.
Needs PIXABAY_API_KEY. Skipped gracefully when absent."""
from __future__ import annotations
import urllib.parse, urllib.request, json
from .base import ImageProvider, VideoProvider, ProviderStatus, CacheMixin
from ..config import get_settings


class PixabayImageProvider(CacheMixin, ImageProvider):
    name = "pixabay-image"

    def __init__(self):
        CacheMixin.__init__(self, "img-pixabay")

    def status(self) -> ProviderStatus:
        if not get_settings().pixabay_api_key:
            return ProviderStatus(self.name, False, True, "PIXABAY_API_KEY not set (optional)")
        return ProviderStatus(self.name, True, True, "free key, ~100/min")

    def search_images(self, query: str, limit: int = 4) -> list[dict]:
        if not get_settings().pixabay_api_key:
            return []
        cached = self.cache_get(query, str(limit))
        if cached is not None:
            return cached
        out: list[dict] = []
        try:
            q = urllib.parse.urlencode({"key": get_settings().pixabay_api_key, "q": query,
                                        "per_page": min(limit, 20), "orientation": "horizontal",
                                        "image_type": "photo"})
            req = urllib.request.Request("https://pixabay.com/api/?" + q,
                                     headers={"User-Agent": "science-youtube-ai/0.1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
            for h in data.get("hits", [])[:limit]:
                tags = [t.strip() for t in str(h.get("tags", "")).split(",") if t.strip()]
                out.append({"url": h.get("largeImageURL") or h.get("webformatURL", ""),
                            "thumb": h.get("previewURL", ""),
                            "title": ", ".join(tags[:8]) or f"Pixabay {h.get('id')}",
                            "creator": h.get("user", ""), "license": "Pixabay Content License (free commercial)",
                            "page_url": h.get("pageURL", ""), "width": h.get("imageWidth", 1920),
                            "height": h.get("imageHeight", 1080),
                            "description": ", ".join(tags), "categories": tags})
        except Exception:
            return []  # never cache failures (would poison later calls)
        self.cache_put(out, query, str(limit))
        return out


class PixabayVideoProvider(CacheMixin, VideoProvider):
    name = "pixabay-video"

    def __init__(self):
        CacheMixin.__init__(self, "vid-pixabay")

    def status(self) -> ProviderStatus:
        if not get_settings().pixabay_api_key:
            return ProviderStatus(self.name, False, True, "PIXABAY_API_KEY not set (optional)")
        return ProviderStatus(self.name, True, True, "free key, ~100/min")

    def search_videos(self, query: str, limit: int = 4) -> list[dict]:
        if not get_settings().pixabay_api_key:
            return []
        cached = self.cache_get(query, str(limit))
        if cached is not None:
            return cached
        out: list[dict] = []
        try:
            q = urllib.parse.urlencode({"key": get_settings().pixabay_api_key, "q": query,
                                        "per_page": min(limit, 20)})
            req = urllib.request.Request("https://pixabay.com/api/videos/?" + q,
                                         headers={"User-Agent": "science-youtube-ai/0.1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
            for h in data.get("hits", [])[:limit]:
                vids = h.get("videos", {})
                cands = [v for v in (vids.get("large"), vids.get("medium"), vids.get("small"))
                         if isinstance(v, dict) and v.get("url")]
                if not cands:
                    continue
                ok = [v for v in cands if (v.get("width") or 0) <= 1920]
                best = (max(ok, key=lambda v: v.get("width", 0)) if ok
                        else min(cands, key=lambda v: v.get("width", 0)))
                tags = [t.strip() for t in str(h.get("tags", "")).split(",") if t.strip()]
                out.append({"url": best["url"],
                            "title": ", ".join(tags[:8]) or f"Pixabay video {h.get('id')}",
                            "creator": h.get("user", ""), "license": "Pixabay Content License (free commercial)",
                            "page_url": h.get("pageURL", ""), "width": best.get("width", 1920),
                            "height": best.get("height", 1080), "duration": h.get("duration", 0),
                            "description": ", ".join(tags), "categories": tags})
        except Exception:
            return []  # never cache failures (would poison later calls)
        self.cache_put(out, query, str(limit))
        return out
