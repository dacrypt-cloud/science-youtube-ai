"""Topic backbone — a coherent reference core for the evidence base.

General web/journal search returns thin, sometimes off-topic snippets. The
backbone fetches FULL reference articles for the topic's anchor terms (direct
Wikipedia lookup) BEFORE the general search, so the evidence base always
contains a coherent, on-topic, mechanism-level core.

Honest labeling: backbone sources are typed 'reference' (Wikipedia) with
their fetch_method recorded, exactly like any other fetched source.
"""
from __future__ import annotations


def _hit_matches(hit: dict, anchor: str, anchors: list[str], strict: bool = False) -> bool:
    """Accept a Wikipedia hit for an anchor when it is really about the topic.

    Primary anchor: title match wins outright (strongest topic signal).
    Later anchors (strict): homonyms lurk ('Usain Bolt' for 'bolt'), so require
    >=2 anchor stems in the TITLE or >=3 in the intro.
    """
    from ..providers.llm_template import stem
    import re as _re
    t, a = (hit.get("title") or "").lower(), anchor.lower()
    astems = {stem(x) for x in anchors}
    title_stems = {stem(w) for w in _re.findall(r"[a-z]{4,}", t)}
    intro = (hit.get("snippet") or "").lower()
    intro_stems = {stem(w) for w in _re.findall(r"[a-z]{4,}", intro)}
    if not strict:
        if a in t or any(w in t for w in a.split()):
            return True
        return len(intro_stems & astems) >= 2
    return len(title_stems & astems) >= 2 or len(intro_stems & astems) >= 3


def fetch_topic_backbone(anchors: list[str], max_articles: int = 3,
                         chars_per_article: int = 12000,
                         progress_cb=None) -> tuple[list[dict], dict[str, str]]:
    """Returns (sources_without_ids, {url: full_text}).

    The engine assigns source_ids and merges texts into the fetched map.
    Never raises: backbone failure just yields an empty core (search carries on).
    """
    from ..providers.search_wikipedia import WikipediaSearchProvider
    from ..providers.llm_template import stem as _stem
    import re as _re
    from .fetcher import fetch_wikipedia
    sources: list[dict] = []
    texts: dict[str, str] = {}
    seen: set[str] = set()
    accepted_vocab: set[str] = set()  # topic coherence: later articles must speak it
    wiki = WikipediaSearchProvider()
    for anchor in (anchors or [])[:max_articles + 2]:
        if len(sources) >= max_articles:
            break
        try:
            if progress_cb:
                progress_cb(len(sources) + 1, max_articles, f"backbone: {anchor}")
            hits = wiki.search(anchor, limit=3)
        except Exception:
            continue
        pick = None
        strict = len(sources) >= 1
        for h in hits:
            url = (h.get("url") or "")
            if not url or url in seen or not _hit_matches(h, anchor, anchors, strict):
                continue
            if accepted_vocab:
                # wrong-sense guard: 'Bolt' the fastener shares ~nothing with
                # the Lightning article; true topic articles share plenty.
                intro_stems = {_stem(w) for w in
                               _re.findall(r"[a-z]{4,}", ((h.get("snippet") or "") + " " + h.get("title", "")).lower())}
                if len(intro_stems & accepted_vocab) < 4:
                    continue
            pick = h
            break
        if pick is None:
            continue
        try:
            text, method = fetch_wikipedia(pick["url"])
        except Exception:
            continue
        if len(text) < 500:
            continue
        accepted_vocab |= {_stem(w) for w in _re.findall(r"[a-z]{4,}", text[:6000].lower())}
        seen.add(pick["url"])
        sources.append({
            "title": pick.get("title", anchor), "url": pick["url"],
            "snippet": text[:1500], "source_type": "reference",
            "publisher": "Wikipedia", "publication_date": "",
            "authors": "", "doi": "", "reliability": 4,
            "via": "wikipedia-backbone", "query": f"backbone:{anchor}",
            "fetched_chars": len(text[:chars_per_article]),
            "fetch_method": "wikipedia-fulltext",
            "fetch_error": "",
        })
        texts[pick["url"]] = text[:chars_per_article]
    return sources, texts
