"""Topic backbone — a coherent reference core for the evidence base.

General web/journal search returns thin, sometimes off-topic snippets. The
backbone fetches FULL reference articles for the topic's canonical concepts
and anchor terms (direct Wikipedia lookup) BEFORE the general search, so the
evidence base always contains a coherent, on-topic, mechanism-level core.

Disambiguation pages, song/place lists, and unrelated person biographies are
strictly rejected so homonyms (e.g. 'Rich' -> Rich County / Marc Rich) can
never poison downstream relevance filtering.
"""
from __future__ import annotations
import re as _re

DISAMBIG_PATTERNS = (
    "may refer to:",
    "can refer to:",
    "commonly refers to:",
    "also refers to:",
    "is a surname",
    "is a given name",
    "is an unincorporated community",
    "a song by ",
    "studio album by ",
)

BIO_LEAD_RE = _re.compile(
    r"^[^.]{0,160}(?:\(\s*born\s+[A-Z0-9]|\bwas\s+a[n]?\s+[A-Z][a-z\-]+(?:\s+[a-zA-Z\-]+){0,3}\s+"
    r"(?:businessman|financier|trader|politician|actor|actress|singer|rapper|musician|"
    r"footballer|player|author|novelist|director)\b)"
)


def _is_junk_reference(title: str, text: str, idea: str = "") -> bool:
    tl = (title or "").lower()
    if "(disambiguation)" in tl or tl.startswith("list of "):
        # Allow legitimate historical/event lists (e.g. "List of security breaches") only if long prose
        if "(disambiguation)" in tl:
            return True
    head = (text or "")[:450].lower()
    if any(p in head for p in DISAMBIG_PATTERNS):
        return True
    # Reject random person biographies unless the user's idea actually names them
    if BIO_LEAD_RE.search((text or "")[:260]):
        idea_low = (idea or "").lower()
        title_words = [w for w in _re.findall(r"[a-z]{3,}", tl)]
        if len(title_words) >= 2 and not all(w in idea_low for w in title_words[:2]):
            return True
    return False


def _hit_matches(hit: dict, anchor: str, anchors: list[str], strict: bool = False) -> bool:
    """Accept a Wikipedia hit for an anchor/query when it is really about the topic."""
    from ..providers.llm_template import stem
    t, a = (hit.get("title") or "").lower(), anchor.lower()
    if "(disambiguation)" in t:
        return False
    intro = (hit.get("snippet") or "").lower()
    if any(p in intro for p in DISAMBIG_PATTERNS):
        return False
    astems = {stem(x) for x in anchors} | {stem(w) for w in _re.findall(r"[a-z]{4,}", a)}
    title_stems = {stem(w) for w in _re.findall(r"[a-z]{4,}", t)}
    intro_stems = {stem(w) for w in _re.findall(r"[a-z]{4,}", intro)}
    if not strict:
        if a in t or any(len(w) >= 4 and w in t for w in a.split()):
            return True
        return len((title_stems | intro_stems) & astems) >= 2
    return len(title_stems & astems) >= 1 and len((title_stems | intro_stems) & astems) >= 2


def fetch_topic_backbone(anchors: list[str], max_articles: int = 3,
                         chars_per_article: int = 12000,
                         progress_cb=None,
                         queries: list[str] | None = None,
                         idea: str = "") -> tuple[list[dict], dict[str, str]]:
    """Returns (sources_without_ids, {url: full_text}).

    The engine assigns source_ids and merges texts into the fetched map.
    Never raises: backbone failure just yields an empty core (search carries on).
    """
    from ..providers.search_wikipedia import WikipediaSearchProvider
    from ..providers.llm_template import stem as _stem
    from .fetcher import fetch_wikipedia

    sources: list[dict] = []
    texts: dict[str, str] = {}
    seen: set[str] = set()
    accepted_vocab: set[str] = set()
    wiki = WikipediaSearchProvider()

    # Prefer multi-word canonical topic queries before single-token anchors
    candidates: list[str] = []
    for q in (queries or []):
        if q and q not in candidates:
            candidates.append(q)
    for a in (anchors or []):
        if a and a not in candidates:
            candidates.append(a)

    for cand in candidates[:max_articles + 5]:
        if len(sources) >= max_articles:
            break
        try:
            if progress_cb:
                progress_cb(len(sources) + 1, max_articles, f"backbone: {cand}")
            hits = wiki.search(cand, limit=4)
        except Exception:
            continue
        strict = len(sources) >= 2
        for h in hits:
            url = (h.get("url") or "")
            if not url or url in seen or not _hit_matches(h, cand, anchors, strict):
                continue
            if accepted_vocab and len(sources) >= 2:
                intro_stems = {_stem(w) for w in
                               _re.findall(r"[a-z]{4,}", ((h.get("snippet") or "") + " " + h.get("title", "")).lower())}
                if len(intro_stems & accepted_vocab) < 3:
                    continue
            try:
                text, _ = fetch_wikipedia(url)
            except Exception:
                continue
            if len(text) < 600 or _is_junk_reference(h.get("title", ""), text, idea=idea):
                continue
            accepted_vocab |= {_stem(w) for w in _re.findall(r"[a-z]{4,}", text[:6000].lower())}
            seen.add(url)
            sources.append({
                "title": h.get("title", cand), "url": url,
                "snippet": text[:1500], "source_type": "reference",
                "publisher": "Wikipedia", "publication_date": "",
                "authors": "", "doi": "", "reliability": 4,
                "via": "wikipedia-backbone", "query": f"backbone:{cand}",
                "fetched_chars": len(text[:chars_per_article]),
                "fetch_method": "wikipedia-fulltext",
                "fetch_error": "",
            })
            texts[url] = text[:chars_per_article]
            break
    return sources, texts
