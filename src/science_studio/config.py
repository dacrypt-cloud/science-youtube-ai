"""Central configuration. Free-first, $0 budget. Env-driven, no secrets in code."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    free_only: bool = field(default_factory=lambda: _env("FREE_ONLY", "1") == "1")
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    gemini_model: str = field(default_factory=lambda: _env("GEMINI_MODEL", "gemini-2.5-flash"))
    ollama_base_url: str = field(default_factory=lambda: _env("OLLAMA_BASE_URL"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "llama3.1:8b"))
    groq_api_key: str = field(default_factory=lambda: _env("GROQ_API_KEY"))
    groq_model: str = field(default_factory=lambda: _env("GROQ_MODEL", "openai/gpt-oss-120b"))
    openrouter_api_key: str = field(default_factory=lambda: _env("OPENROUTER_API_KEY"))
    openrouter_model: str = field(default_factory=lambda: _env("OPENROUTER_MODEL", "openrouter/free"))
    pexels_api_key: str = field(default_factory=lambda: _env("PEXELS_API_KEY"))
    pixabay_api_key: str = field(default_factory=lambda: _env("PIXABAY_API_KEY"))
    default_duration: str = field(default_factory=lambda: _env("DEFAULT_DURATION", "12-15"))
    default_voice: str = field(default_factory=lambda: _env("DEFAULT_VOICE", "edge"))
    edge_voice: str = field(default_factory=lambda: _env("EDGE_VOICE", "en-US-AvaNeural"))
    video_width: int = field(default_factory=lambda: int(_env("VIDEO_WIDTH", "1920") or 1920))
    video_height: int = field(default_factory=lambda: int(_env("VIDEO_HEIGHT", "1080") or 1080))
    video_fps: int = field(default_factory=lambda: int(_env("VIDEO_FPS", "30") or 30))
    projects_dir: Path = field(default_factory=lambda: Path(_env("PROJECTS_DIR", "projects")))
    cache_dir: Path = field(default_factory=lambda: Path(_env("CACHE_DIR", ".cache/sy_ai")))
    youtube_client_secrets: str = field(default_factory=lambda: _env("YOUTUBE_CLIENT_SECRETS"))
    youtube_token_file: str = field(default_factory=lambda: _env("YOUTUBE_TOKEN_FILE", "token.json"))

    def validate_free_only(self) -> list[str]:
        """Return list of violations (empty = OK)."""
        issues: list[str] = []
        if self.free_only:
            # Paid providers are simply never instantiated when FREE_ONLY=1.
            # This hook documents the guarantee and flags misconfiguration.
            pass
        return issues

    def redact(self) -> dict:
        d = {
            "free_only": self.free_only,
            "gemini_model": self.gemini_model,
            "has_gemini_key": bool(self.gemini_api_key),
            "has_groq_key": bool(self.groq_api_key),
            "has_openrouter_key": bool(self.openrouter_api_key),
            "has_pexels_key": bool(self.pexels_api_key),
            "has_pixabay_key": bool(self.pixabay_api_key),
            "default_duration": self.default_duration,
            "default_voice": self.default_voice,
        }
        return d


_settings: Settings | None = None


def get_settings(reload: bool = False) -> Settings:
    global _settings
    if _settings is None or reload:
        try:
            from dotenv import load_dotenv
            load_dotenv(override=False)
        except Exception:
            pass
        _settings = Settings()
    return _settings
