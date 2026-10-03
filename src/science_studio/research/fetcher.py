"""Full-text fetching for top research sources.

Search snippets are treated as LEADS, not evidence. After the snippet pass,
the engine fetches full article text for the highest-ranked sources so claims
and scripts are grounded in real passages:

- Wikipedia URLs -> MediaWiki extracts API (full plaintext article).
- arXiv abs URLs  -> abstract already present; marked abstract-only (no fetch).
- DOI/publisher/agency pages -> generic HTML main-text extraction.
- PDFs and media files -> skipped (recorded, never silently treated as read).

Bounded: per-fetch timeout, download cap, char cap, global time budget, cache.
"""
from __future__ import annotations
import html as _html
import re
import time
import urllib.parse
import urllib.request
import json as _json

from ..providers.base import CacheMixin

FETCH_TIMEOUT = 25          # seconds per fetch
DOWNLOAD_CAP = 2_000_000    # bytes per page
WIKI_CHAR_CAP = 15000       # chars kept per Wikipedia article
HTML_CHAR_CAP = 9000        # chars kept per generic page
DEFAULT_MAX_FETCH = 10
DEFAULT_BUDGET_S = 420      # global fetch budget per research run

_SKIP_EXT = (".pdf", ".mp4", ".mp3", ".wav", ".ogg", ".jpg", ".jpeg",
             ".png", ".gif", ".svg", ".zip", ".tar.gz")


def _get(url: str, timeout: int = FETCH_TIMEOUT, cap: int = DOWNLOAD_CAP) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": "science-youtube-ai/0.1 (research; contact: local)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(cap + 1)[:cap + 1]


def fetch_wikipedia(url: str) -> tuple[str, str]:
    """Full plaintext article via MediaWiki API. Returns (text, method)."""
    m = re.search(r"wikipedia\.org/wiki/([^#?]+)", url)
    if not m:
        return "", "wiki-unparseable"
    title = urllib.parse.unquote(m.group(1)).replace("_", " ")
    api = ("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "prop": "extracts",
        "explaintext": 1, "exsectionformat": "plain", "titles": title}))
    data = _json.loads(_get(api).decode("utf-8", "ignore"))
    pages = (data.get("query") or {}).get("pages", {})
    text = ""
    for pg in pages.values():
        text = (pg.get("extract") or "")
        break
    text = re.sub(r"\s+", " ", text).strip()
    return text[:WIKI_CHAR_CAP], "wikipedia-fulltext"


def html_to_text(raw: bytes) -> str:
    """Best-effort main-text extraction from generic HTML."""
    try:
        page = raw.decode("utf-8", "ignore")
    except Exception:
        return ""
    # drop scripts/styles/nav-ish blocks
    page = re.sub(r"(?is)<(script|style|noscript|nav|footer|header|form|aside)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?i)<br\s*/?>|\s*</p\s*>", "\n", page)
    text = re.sub(r"<[^>]+>", " ", page)
    text = _html.unescape(text)
    paras = [re.sub(r"\s+", " ", p).strip() for p in text.split("\n")]
    # keep substantive paragraphs (body copy, not menus/buttons)
    keep = [p for p in paras if len(p) > 80 and len(p.split()) > 8]
    if not keep:  # fallback: longest raw runs
        runs = sorted((re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n+", text)),
                      key=len, reverse=True)
        keep = [r for r in runs if len(r) > 120][:6]
    return "\n".join(keep)[:HTML_CHAR_CAP]


def fetch_generic(url: str) -> tuple[str, str]:
    raw = _get(url)
    if len(raw) > DOWNLOAD_CAP:
        return "", "too-large"
    return html_to_text(raw), "html-extract"


def fetch_source_text(source: dict, cache: CacheMixin | None = None) -> dict:
    """Fetch full text for one source. Returns {text, method, chars, error}.

    Never raises; failures are recorded so QA/audit stays honest.
    """
    url = (source.get("url") or "").strip()
    if not url or not url.startswith("http"):
        return {"text": "", "method": "no-url", "chars": 0, "error": "empty url"}
    if url.lower().split("?")[0].endswith(_SKIP_EXT):
        return {"text": "", "method": "skipped-binary", "chars": 0, "error": "binary/pdf skipped"}
    if "arxiv.org/abs/" in url:
        return {"text": "", "method": "abstract-only", "chars": 0,
                "error": "arXiv abstract used (snippet); full paper is PDF"}
    if cache is not None:
        hit = cache.cache_get(url)
        if isinstance(hit, dict) and "text" in hit:
            return hit
    try:
        if "wikipedia.org/wiki/" in url:
            text, method = fetch_wikipedia(url)
        else:
            text, method = fetch_generic(url)
        res = {"text": text, "method": method, "chars": len(text),
               "error": "" if len(text) > 200 else "no-substantive-text"}
    except Exception as e:  # network/parse failure — recorded, not fatal
        res = {"text": "", "method": "fetch-failed", "chars": 0, "error": str(e)[:200]}
    if cache is not None:
        try:
            cache.cache_put(res, url)
        except Exception:
            pass
    return res


def fetch_for_sources(sources: list[dict], budget_s: int = DEFAULT_BUDGET_S,
                      progress_cb=None, max_substantive: int = 8,
                      max_attempts: int = 24,
                      question_stems: set[str] | None = None) -> dict[str, str]:
    """Fetch full text for top-ranked sources until `max_substantive` succeed.

    Keeps attempting (up to `max_attempts`/budget) so paywalled failures don't
    crowd out fetchable sources. Skips sources that already carry full text
    (e.g. the topic backbone). When `question_stems` is given, sources whose
    title+snippet speak the QUESTION's language fetch first, so the limited
    full-text budget fills with on-question texts, not subtopic drift.
    Mutates `sources` in place: adds fetched_chars / fetch_method / fetch_error.
    Returns {source_id: text} for substantive hits.
    """
    from ..providers.llm_template import stem as _stem
    import re as _re
    cache = CacheMixin("fetch-fulltext")
    out: dict[str, str] = {}
    start = time.time()
    # rank order = list order (engine sorts best-first); open HTML pages
    # (reference/agency/university) fetch best, journals often paywalled.
    prefer = {"reference": 0, "agency": 0, "university": 1, "database": 1,
              "journal": 2, "news_science": 2, "preprint": 3, "other": 4}

    def _qhits(s: dict) -> int:
        if not question_stems:
            return 0
        toks = {_stem(w) for w in _re.findall(r"[a-z]{4,}",
                ((s.get("title") or "") + " " + (s.get("snippet") or "")).lower())}
        return len(toks & set(question_stems))

    cands = sorted(sources, key=lambda s: (prefer.get(s.get("source_type", "other"), 4),
                                           -_qhits(s),
                                           -(s.get("reliability", 0) or 0)))
    attempts = 0
    for s in cands:
        if len(out) >= max_substantive or attempts >= max_attempts \
                or (time.time() - start) > budget_s:
            break
        if (s.get("fetched_chars") or 0) > 200:
            continue  # backbone / already-fetched: text in hand
        if not (s.get("url") or ""):
            continue
        attempts += 1
        if progress_cb:
            progress_cb(attempts, max_attempts,
                        f"fetch {s.get('source_id')}: {(s.get('title') or '')[:50]}")
        res = fetch_source_text(s, cache)
        s["fetched_chars"] = res["chars"]
        s["fetch_method"] = res["method"]
        s["fetch_error"] = res["error"]
        if res["chars"] > 200:
            out[s["source_id"]] = res["text"]
    return out
