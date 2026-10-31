"""Pexels — free photos+videos, free key. 200 req/hr, 20k req/mo (2026).
License: free commercial use incl. YouTube; link-back appreciated / API guideline.
Needs PEXELS_API_KEY. Skipped gracefully when absent (FREE_ONLY-safe)."""
from __future__ import annotations
import urllib.parse, urllib.request, json
from .base import ImageProvider, VideoProvider, ProviderStatus, CacheMixin
from ..config import get_settings


def _headers():
    return {"Authorization": get_settings().pexels_api_key, "User-Agent": "science-youtube-ai/0.1"}


class PexelsImageProvider(CacheMixin, ImageProvider):
    name = "pexels-image"

    def __init__(self):
        CacheMixin.__init__(self, "img-pexels")

    def status(self) -> ProviderStatus:
        if not get_settings().pexels_api_key:
            return ProviderStatus(self.name, False, True, "PEXELS_API_KEY not set (optional)")
        return ProviderStatus(self.name, True, True, "free key, 200/hr 20k/mo")

    def search_images(self, query: str, limit: int = 4) -> list[dict]:
        if not get_settings().pexels_api_key:
            return []
        cached = self.cache_get(query, str(limit))
        if cached is not None:
            return cached
        out: list[dict] = []
        try:
            q = urllib.parse.urlencode({"query": query, "per_page": min(limit, 20), "orientation": "landscape"})
            req = urllib.request.Request("https://api.pexels.com/v1/search?" + q, headers=_headers())
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
            for p in data.get("photos", [])[:limit]:
                src = p.get("src", {})
                out.append({"url": src.get("large2x") or src.get("large") or src.get("original", ""),
                            "thumb": src.get("medium", ""), "title": p.get("alt") or f"Pexels {p.get('id')}",
                            "creator": p.get("photographer", ""), "license": "Pexels License (free commercial)",
                            "page_url": p.get("url", ""), "width": p.get("width", 1920),
                            "height": p.get("height", 1080)})
        except Exception:
            out = []
        self.cache_put(out, query, str(limit))
        return out


class PexelsVideoProvider(CacheMixin, VideoProvider):
    name = "pexels-video"

    def __init__(self):
        CacheMixin.__init__(self, "vid-pexels")

    def status(self) -> ProviderStatus:
        if not get_settings().pexels_api_key:
            return ProviderStatus(self.name, False, True, "PEXELS_API_KEY not set (optional)")
        return ProviderStatus(self.name, True, True, "free key, 200/hr 20k/mo")

    def search_videos(self, query: str, limit: int = 4) -> list[dict]:
        if not get_settings().pexels_api_key:
            return []
        cached = self.cache_get(query, str(limit))
        if cached is not None:
            return cached
        out: list[dict] = []
        try:
            q = urllib.parse.urlencode({"query": query, "per_page": min(limit, 20), "orientation": "landscape"})
            req = urllib.request.Request("https://api.pexels.com/videos/search?" + q, headers=_headers())
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
            for v in data.get("videos", [])[:limit]:
                files = sorted(v.get("video_files", []), key=lambda f: f.get("width", 0), reverse=True)
                mp4s = [f for f in files if f.get("file_type") == "video/mp4"]
                if not mp4s:
                    continue
                # Cap at 1080p: 4K files are slow to fetch and gain nothing
                # at our 1920x1080 render. Fall back to the smallest file.
                ok = [f for f in mp4s if (f.get("width") or 0) <= 1920]
                best = (max(ok, key=lambda f: f.get("width", 0)) if ok
                        else min(mp4s, key=lambda f: f.get("width", 0)))
                out.append({"url": best.get("link", ""), "title": f"Pexels video {v.get('id')}",
                            "creator": v.get("user", {}).get("name", ""),
                            "license": "Pexels License (free commercial)",
                            "page_url": v.get("url", ""), "width": best.get("width", 1920),
                            "height": best.get("height", 1080), "duration": v.get("duration", 0)})
        except Exception:
            out = []
        self.cache_put(out, query, str(limit))
        return out
