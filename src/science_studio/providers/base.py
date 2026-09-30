"""Provider abstractions — every external service behind a replaceable interface."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProviderStatus:
    name: str
    available: bool
    free: bool = True
    reason: str = ""
    details: dict = field(default_factory=dict)


class AIProvider(ABC):
    name = "ai-base"

    @abstractmethod
    def status(self) -> ProviderStatus: ...
    @abstractmethod
    def generate(self, prompt: str, *, system: str = "", max_tokens: int = 2000,
                 temperature: float = 0.4) -> str:
        """Return model text. Raise on failure so the registry can fall back."""


class SearchProvider(ABC):
    name = "search-base"

    @abstractmethod
    def status(self) -> ProviderStatus: ...
    @abstractmethod
    def search(self, query: str, limit: int = 8) -> list[dict]:
        """Return list of {title, url, snippet, source_type, publisher, ...}."""


class ImageProvider(ABC):
    name = "image-base"

    @abstractmethod
    def status(self) -> ProviderStatus: ...
    @abstractmethod
    def search_images(self, query: str, limit: int = 4) -> list[dict]:
        """Return list of {url, thumb, title, creator, license, page_url, width, height}."""


class VideoProvider(ABC):
    name = "video-base"

    @abstractmethod
    def status(self) -> ProviderStatus: ...
    @abstractmethod
    def search_videos(self, query: str, limit: int = 4) -> list[dict]:
        ...


class SpeechProvider(ABC):
    name = "speech-base"

    @abstractmethod
    def status(self) -> ProviderStatus: ...
    @abstractmethod
    def synthesize(self, text: str, out_path: Path, *, voice: str = "") -> dict:
        """Write audio to out_path. Return {path, duration_s, voice, provider}."""


class RenderingProvider(ABC):
    name = "render-base"

    @abstractmethod
    def status(self) -> ProviderStatus: ...
    @abstractmethod
    def render(self, job: dict, out_path: Path, progress_cb=None) -> dict:
        """Render job spec -> video file. Return {path, duration_s, ...}."""


class CacheMixin:
    """File-based JSON cache with request deduplication for free-quota protection."""
    def __init__(self, namespace: str):
        from ..config import get_settings
        import hashlib
        self._ns = namespace
        self._hash = hashlib
        root = get_settings().cache_dir / namespace
        root.mkdir(parents=True, exist_ok=True)
        self._cache_root = root

    def _ckey(self, *parts: str) -> Path:
        h = self._hash.sha256("|".join(parts).encode()).hexdigest()[:32]
        return self._cache_root / f"{h}.json"

    def cache_get(self, *parts: str) -> Any | None:
        import json
        p = self._ckey(*parts)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def cache_put(self, value: Any, *parts: str) -> None:
        import json
        try:
            self._ckey(*parts).write_text(json.dumps(value, ensure_ascii=False, default=str), encoding="utf-8")
        except Exception:
            pass
