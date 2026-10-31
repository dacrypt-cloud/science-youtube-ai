from science_studio.providers.registry import build_providers

def test_registry_builds():
    s = build_providers()
    r = s.status_report()
    assert "ai_chain" in r and len(s.ai_chain) >= 1
    assert len(s.searchers) >= 3
    assert s.renderer is not None
    # template fallback always available
    assert any(p.name == "template-fallback" for p in s.ai_chain)

def test_free_only_default():
    from science_studio.config import get_settings
    assert get_settings().free_only in (True, False)


# ── key-day activation tests (mocked HTTP: no network, no real keys) ──
import io as _io
import json as _json
import pytest as _pytest


class _FakeResp:
    def __init__(self, payload):
        self._b = _json.dumps(payload).encode()
    def read(self):
        return self._b
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


@_pytest.fixture
def _cfg(monkeypatch, tmp_path):
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    from science_studio.config import get_settings
    get_settings(reload=True)
    yield tmp_path
    for k in ("GEMINI_API_KEY", "PEXELS_API_KEY", "PIXABAY_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    get_settings(reload=True)


def _keyed(monkeypatch, **keys):
    from science_studio.config import get_settings
    for k, v in keys.items():
        monkeypatch.setenv(k, v)
    get_settings(reload=True)


def _fake_urlopen(routes):
    def _open(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        for sub, payload in routes:
            if sub in url:
                if isinstance(payload, Exception):
                    raise payload
                return _FakeResp(payload)
        raise AssertionError(f"unexpected URL: {url}")
    return _open


def test_gemini_parses_candidates_and_caches(_cfg, monkeypatch):
    from science_studio.providers.llm_gemini import GeminiProvider
    _keyed(monkeypatch, GEMINI_API_KEY="test")
    monkeypatch.setattr("urllib.request.urlopen",
                        _fake_urlopen([("generativelanguage",
                                        {"candidates": [{"content": {"parts": [{"text": " hello "}]}}]})]))
    g = GeminiProvider()
    assert g.status().available
    assert g.generate("hi") == "hello"
    # second call served from cache (urlopen now explodes)
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen([]))
    assert g.generate("hi") == "hello"


def test_gemini_no_candidates_raises(_cfg, monkeypatch):
    from science_studio.providers.llm_gemini import GeminiProvider
    _keyed(monkeypatch, GEMINI_API_KEY="test")
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("urllib.request.urlopen",
                        _fake_urlopen([("generativelanguage", {"candidates": []})]))
    import pytest
    with pytest.raises(RuntimeError):
        GeminiProvider().generate("hi")


def test_gemini_no_key_unavailable(_cfg):
    from science_studio.providers.llm_gemini import GeminiProvider
    g = GeminiProvider()
    assert not g.status().available
    import pytest
    with pytest.raises(RuntimeError):
        g.generate("hi")


def test_pexels_image_parse(_cfg, monkeypatch):
    from science_studio.providers.image_pexels import PexelsImageProvider
    _keyed(monkeypatch, PEXELS_API_KEY="test")
    photo = {"id": 7, "alt": "Lightning over lake", "photographer": "Jane",
             "url": "https://pexels.com/p7", "width": 4000, "height": 2250,
             "src": {"large2x": "https://img/lg2x", "large": "https://img/lg",
                     "medium": "https://img/md"}}
    monkeypatch.setattr("urllib.request.urlopen",
                        _fake_urlopen([("api.pexels.com/v1/search", {"photos": [photo]})]))
    hits = PexelsImageProvider().search_images("lightning", limit=2)
    assert len(hits) == 1 and hits[0]["url"] == "https://img/lg2x"
    assert hits[0]["creator"] == "Jane" and "Pexels" in hits[0]["license"]


def test_pexels_video_picks_1080_mp4(_cfg, monkeypatch):
    from science_studio.providers.image_pexels import PexelsVideoProvider
    _keyed(monkeypatch, PEXELS_API_KEY="test")
    files = [{"file_type": "video/mp4", "width": 3840, "link": "https://v/4k"},
             {"file_type": "video/mp4", "width": 1920, "link": "https://v/hd"},
             {"file_type": "video/mp4", "width": 1280, "link": "https://v/sd"},
             {"file_type": "video/webm", "width": 1920, "link": "https://v/webm"}]
    vid = {"id": 9, "url": "https://pexels.com/v9", "duration": 12,
           "user": {"name": "Bob"}, "video_files": files}
    monkeypatch.setattr("urllib.request.urlopen",
                        _fake_urlopen([("api.pexels.com/videos/search", {"videos": [vid]})]))
    hits = PexelsVideoProvider().search_videos("storm", limit=2)
    assert len(hits) == 1 and hits[0]["url"] == "https://v/hd"
    assert hits[0]["width"] == 1920 and hits[0]["creator"] == "Bob"


def test_pexels_video_all_4k_picks_smallest(_cfg, monkeypatch):
    from science_studio.providers.image_pexels import PexelsVideoProvider
    _keyed(monkeypatch, PEXELS_API_KEY="test")
    files = [{"file_type": "video/mp4", "width": 3840, "link": "https://v/4k"},
             {"file_type": "video/mp4", "width": 2560, "link": "https://v/qhd"}]
    vid = {"id": 1, "video_files": files, "user": {}}
    monkeypatch.setattr("urllib.request.urlopen",
                        _fake_urlopen([("videos/search", {"videos": [vid]})]))
    hits = PexelsVideoProvider().search_videos("storm", limit=1)
    assert hits and hits[0]["url"] == "https://v/qhd"


def test_providers_no_key_return_empty(_cfg):
    from science_studio.providers.image_pexels import PexelsImageProvider, PexelsVideoProvider
    from science_studio.providers.image_pixabay import PixabayImageProvider, PixabayVideoProvider
    assert PexelsImageProvider().search_images("x") == []
    assert PexelsVideoProvider().search_videos("x") == []
    assert PixabayImageProvider().search_images("x") == []
    assert PixabayVideoProvider().search_videos("x") == []


def test_pixabay_image_tags(_cfg, monkeypatch):
    from science_studio.providers.image_pixabay import PixabayImageProvider
    _keyed(monkeypatch, PIXABAY_API_KEY="test")
    hit = {"id": 3, "tags": "lightning, storm, night sky", "user": "Ann",
           "pageURL": "https://pixabay.com/3", "largeImageURL": "https://px/lg",
           "webformatURL": "https://px/wf", "previewURL": "https://px/pv",
           "imageWidth": 1920, "imageHeight": 1280}
    monkeypatch.setattr("urllib.request.urlopen",
                        _fake_urlopen([("pixabay.com/api/", {"hits": [hit]})]))
    hits = PixabayImageProvider().search_images("lightning", limit=2)
    assert len(hits) == 1 and "lightning" in hits[0]["title"]
    assert "storm" in hits[0]["categories"] and hits[0]["creator"] == "Ann"


def test_pixabay_video_tags_and_1080(_cfg, monkeypatch):
    from science_studio.providers.image_pixabay import PixabayVideoProvider
    _keyed(monkeypatch, PIXABAY_API_KEY="test")
    hit = {"id": 5, "tags": "thunderstorm, clouds", "user": "Zed", "duration": 9,
           "pageURL": "https://pixabay.com/5",
           "videos": {"large": {"url": "https://px/4k", "width": 3840, "height": 2160},
                      "medium": {"url": "https://px/hd", "width": 1280, "height": 720}}}
    monkeypatch.setattr("urllib.request.urlopen",
                        _fake_urlopen([("pixabay.com/api/videos/", {"hits": [hit]})]))
    hits = PixabayVideoProvider().search_videos("storm", limit=2)
    assert len(hits) == 1 and hits[0]["url"] == "https://px/hd"
    assert "thunderstorm" in hits[0]["title"] and hits[0]["duration"] == 9


def test_ai_generate_fallback_order():
    import types
    from science_studio.providers.registry import ai_generate
    from science_studio.providers.base import ProviderStatus

    class Boom:
        name = "boom"
        def status(self):
            return ProviderStatus(self.name, True, True, "")
        def generate(self, prompt, **k):
            raise RuntimeError("down")

    class Okay:
        name = "okay"
        def status(self):
            return ProviderStatus(self.name, True, True, "")
        def generate(self, prompt, **k):
            return "  fine  "

    stack = types.SimpleNamespace(ai_chain=[Boom(), Okay()])
    text, used = ai_generate(stack, "hi")
    assert (text, used) == ("fine", "okay")
    import pytest
    with pytest.raises(RuntimeError):
        ai_generate(types.SimpleNamespace(ai_chain=[Boom()]), "hi")


def test_query_trusted_lets_video_through_but_keeps_vetoes():
    from science_studio.visuals.assets import _img_relevant
    anchors = {"lightn", "bolt", "storm"}
    bare = {"title": "Pexels video 123456"}
    assert _img_relevant(bare, anchors, query_trusted=True) is True
    assert _img_relevant(bare, anchors) is False  # strict path unchanged
    gig = {"title": "rock concert live music band performing on stage"}
    assert _img_relevant(gig, anchors, query_trusted=True) is False
    sport = {"title": "goals", "categories": ["Football stadium crowd"]}
    assert _img_relevant(sport, anchors, query_trusted=True) is False


def test_commons_strict_veto_unchanged():
    from science_studio.visuals.assets import _img_relevant
    anchors = {"lightn", "bolt"}
    band = {"title": "Lightning Bolt", "description": "live concert performance",
            "categories": ["Lightning Bolt (band)"]}
    assert _img_relevant(band, anchors) is False


def test_story_craft_constants():
    from science_studio.story.script import SYSTEM, CRAFT
    from science_studio.story.structure import STORY_SYSTEM
    low = SYSTEM.lower()
    for word in ("hook", "analogy", "example", "open loops", "never invent"):
        assert word in low, word
    assert "open loops" in CRAFT and "hook" in CRAFT
    assert "arc" in STORY_SYSTEM and "10 words" in STORY_SYSTEM


def test_registry_keyed_status(_cfg, monkeypatch):
    _keyed(monkeypatch, PEXELS_API_KEY="t", PIXABAY_API_KEY="t")
    s = build_providers()
    by_name = {p.name: p.status().available for p in s.images + s.videos}
    assert by_name.get("pexels-image") is True
    assert by_name.get("pexels-video") is True
    assert by_name.get("pixabay-image") is True
    assert by_name.get("pixabay-video") is True
    assert by_name.get("wikimedia") in (True, False)  # keyless, env-dependent


def test_openai_compat_posts_chat_shape(_cfg, monkeypatch):
    from science_studio.providers.openai_compat import chat_complete
    seen = {}

    def _open(req, timeout=None):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())
        seen["body"] = _json.loads(req.data.decode())
        return _FakeResp({"choices": [{"message": {"content": "  hey  "}}]})

    monkeypatch.setattr("urllib.request.urlopen", _open)
    out = chat_complete("https://x.test/v1", "k", "m", "prompt-hi",
                        system="sys-hi", max_tokens=50, temperature=0.1)
    assert out == "hey"
    assert seen["url"] == "https://x.test/v1/chat/completions"
    assert seen["headers"].get("Authorization") == "Bearer k"
    roles = [m["role"] for m in seen["body"]["messages"]]
    assert roles == ["system", "user"] and seen["body"]["model"] == "m"


def test_groq_parses_and_caches(_cfg, monkeypatch):
    from science_studio.providers.llm_groq import GroqProvider
    _keyed(monkeypatch, GROQ_API_KEY="test")
    monkeypatch.setattr("urllib.request.urlopen",
                        _fake_urlopen([("api.groq.com",
                                        {"choices": [{"message": {"content": "groq-text"}}]})]))
    g = GroqProvider()
    assert g.status().available and "gpt-oss" in g.status().reason
    assert g.generate("hi") == "groq-text"
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen([]))
    assert g.generate("hi") == "groq-text"  # cached
    assert GroqProvider().status().available


def test_openrouter_headers_and_no_key(_cfg, monkeypatch):
    from science_studio.providers.llm_openrouter import OpenRouterProvider
    assert not OpenRouterProvider().status().available
    import pytest
    with pytest.raises(RuntimeError):
        OpenRouterProvider().generate("hi")
    _keyed(monkeypatch, OPENROUTER_API_KEY="test")
    seen = {}

    def _open(req, timeout=None):
        seen["headers"] = dict(req.header_items())
        return _FakeResp({"choices": [{"message": {"content": "or-text"}}]})

    monkeypatch.setattr("urllib.request.urlopen", _open)
    assert OpenRouterProvider().generate("hi") == "or-text"
    lowered = {k.lower(): v for k, v in seen["headers"].items()}
    assert "http-referer" in lowered and "x-title" in lowered


def test_chain_orders_free_llms_before_template(_cfg, monkeypatch):
    _keyed(monkeypatch, GROQ_API_KEY="t", OPENROUTER_API_KEY="t")
    names = [p.name for p in build_providers().ai_chain]
    assert names == ["groq", "openrouter", "template-fallback"]
    _keyed(monkeypatch, GEMINI_API_KEY="t")
    names = [p.name for p in build_providers().ai_chain]
    assert names == ["gemini", "groq", "openrouter", "template-fallback"]


def test_ai_generate_skips_unavailable():
    from science_studio.providers.registry import ai_generate
    from science_studio.providers.base import ProviderStatus

    class Off:
        name = "off"
        def status(self):
            return ProviderStatus(self.name, False, True, "no key")
        def generate(self, prompt, **k):
            raise AssertionError("must be skipped")

    class On:
        name = "on"
        def status(self):
            return ProviderStatus(self.name, True, True, "")
        def generate(self, prompt, **k):
            return "yes"

    import types
    assert ai_generate(types.SimpleNamespace(ai_chain=[Off(), On()]), "hi") == ("yes", "on")


def test_no_test_litter_in_real_projects(_cfg):
    from science_studio import storage
    from pathlib import Path
    pid, root = storage.create_project("Test idea?")
    assert str(root).startswith(str(_cfg))
    real = [p for p in Path("projects").iterdir()
            if p.is_dir() and "test-idea" in p.name] if Path("projects").exists() else []
    assert real == [], f"test litter escaped isolation: {real}"
