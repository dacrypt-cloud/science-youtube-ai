"""Full-text fetcher: snippets are leads, fetched text is evidence (offline tests)."""
import sys
sys.path.insert(0, "src")
from science_studio.research import fetcher


def test_html_to_text_strips_chrome():
    html = (b"<html><head><script>var x=1;</script><style>.a{}</style></head><body>"
            b"<nav>Home About Contact login search menu button click here now today</nav>"
            b"<p>Lightning is a naturally occurring electrostatic discharge during which two "
            b"electrically charged regions equalize through a massive flow of current.</p>"
            b"<p>Thunderclouds develop strong updrafts that carry water droplets upward into "
            b"freezing regions where graupel and ice crystals collide and exchange charge.</p>"
            b"</body></html>")
    text = fetcher.html_to_text(html)
    assert "electrostatic discharge" in text
    assert "graupel" in text
    assert "var x=1" not in text
    assert len(text) < fetcher.HTML_CHAR_CAP + 100


def test_skip_rules():
    assert fetcher.fetch_source_text({"url": "https://x.org/paper.pdf"})["method"] == "skipped-binary"
    assert fetcher.fetch_source_text({"url": "https://arxiv.org/abs/1234.5678"})["method"] == "abstract-only"
    assert fetcher.fetch_source_text({"url": ""})["method"] == "no-url"


def test_fetch_wikipedia_monkeypatched(monkeypatch):
    payload = {"query": {"pages": {"1": {"extract": "Lightning. " * 5000}}}}
    import json as _json
    monkeypatch.setattr(fetcher, "_get", lambda *a, **k: _json.dumps(payload).encode())
    text, method = fetcher.fetch_wikipedia("https://en.wikipedia.org/wiki/Lightning")
    assert method == "wikipedia-fulltext"
    assert 0 < len(text) <= fetcher.WIKI_CHAR_CAP
    assert "Lightning" in text


def test_fetch_generic_monkeypatched(monkeypatch):
    body = b"<html><body><p>" + b"Charge separation inside thunderclouds. " * 60 + b"</p></body></html>"
    monkeypatch.setattr(fetcher, "_get", lambda *a, **k: body)
    res = fetcher.fetch_source_text({"url": "https://example.com/storm"})
    assert res["chars"] > 200 and res["method"] == "html-extract"


def test_fetch_for_sources_respects_budget(monkeypatch, tmp_path):
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    from science_studio.config import get_settings
    get_settings(reload=True)
    calls = []
    def fake_fetch(source, cache=None):
        calls.append(source["source_id"])
        return {"text": "substantive fetched text " * 30, "method": "html-extract",
                "chars": 700, "error": ""}
    monkeypatch.setattr(fetcher, "fetch_source_text", fake_fetch)
    sources = [{"source_id": f"S{i:03d}", "title": f"T{i}", "url": f"https://e.com/{i}",
                "source_type": "reference", "reliability": 3, "snippet": "storm charge"} for i in range(5)]
    out = fetcher.fetch_for_sources(sources, budget_s=60, max_substantive=2)
    assert len(out) == 2 and len(calls) == 2
    assert sources[0]["fetched_chars"] == 700
    assert sources[0]["fetch_method"] == "html-extract"
