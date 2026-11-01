"""Asset manager — download/cache/dedupe with full license metadata.

Priority per scene: generated diagram (mechanisms) > stock video > stock image >
claims-driven diagram fallback (verified labels, no stock needed) > bare
title card. The winning asset is flagged primary=True for the renderer.
"""
from __future__ import annotations
import hashlib, urllib.request
from pathlib import Path


def download(url: str, dest: Path, timeout: int = 60) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # dedupe by URL hash
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    dest = dest.parent / f"{h}_{dest.name}"
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": "science-youtube-ai/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        f.write(r.read())
    return dest


def _add(assets: list[dict], scene_id: str, primary: bool, **kw) -> dict:
    a = {"asset_id": f"A{len(assets)+1:03d}", "scene_id": scene_id,
         "primary": bool(primary), **kw}
    assets.append(a)
    return a


# Namesake veto: a science topic must not illustrate itself with band concert,
# sports, or celebrity photos that merely share a name ("Lightning Bolt" the
# band). Three tiers, from precise to broad — all skipped when the topic
# itself is entertainment (question-gated, like the discourse vetoes):
#  1. MUSIC markers (title + description + categories). Single words are
#     boundary-matched ("tour" must not fire on "toward"); bare "band" and
#     "performance" are deliberately absent ("frequency band", "line
#     lightning performance" are legitimate engineering phrases), as is bare
#     "album" ("photo album" is a common legitimate description).
#  2. SUBJECT markers (categories only — Commons categories describe what the
#     file IS about, so background mentions elsewhere are safe).
#  3. PHENOMENON CONTEXT: surviving candidates must show photographic or
#     nature context (a stemmed word) or carry an anchor-bearing category
#     that is not a bare multi-word namesake ("Lightning" / "Cloud-to-ground
#     lightning in X" count; "Lightning Bolt" alone does not).
MUSIC_SUBSTR = {
    "(band)", "(musician)", "(musicians)", "(singer)", "(guitarist)",
    "(drummer)", "(bassist)", "(vocalist)", "live music", "music festival",
    "music venue", "on stage", "band performing", "rock band",
    "studio album", "debut album", "music album", "live album",
    "concert tour", "world tour", "performing live", "live performance",
}
MUSIC_WORDS = {
    "concert", "concerts", "gig", "tour", "duo", "trio", "quartet",
    "vocalist", "guitarist", "drummer", "bassist", "frontman", "nightclub",
}
SUBJECT_WORDS = {
    "actor", "actress", "celebrity", "singer", "musician", "football",
    "soccer", "basketball", "tennis", "cricket", "rugby", "olympic",
    "stadium", "arena", "sport", "sports", "athlete", "baseball", "hockey",
    "golf",
}
PHENOMENON_CONTEXT = {
    "photo", "photograph", "picture", "image", "storm", "thunderstorm",
    "thunder", "cloud", "cloudy", "sky", "skies", "nature", "natural",
    "weather", "night", "nighttime", "daylight", "landscape", "outdoor",
    "outdoors", "wild", "wildlife", "phenomenon", "closeup", "aerial",
    "macro", "satellite", "radar", "rain", "rainfall", "hail", "snow",
    "fog", "mist", "rainbow", "sunset", "sunrise", "mountain", "sea",
    "ocean", "lake", "river", "field", "forest", "tree", "desert",
    "volcano", "city", "town", "village", "street", "building", "house",
    "skyline", "discharge", "spark", "observatory", "exposure",
}
ENTERTAINMENT_TOPIC_WORDS = (
    "music band song concert album guitar piano drum rock pop jazz sing "
    "singer film movie cinema sport football soccer game olympic dance "
    "theatre theater comedy"
).split()


def is_query_trusted_source(source: str) -> bool:
    """True when the asset came from a stock API searched with our own query
    (Pexels/Pixabay), where tags lack Wikimedia-style category sentences."""
    return (source or "").split("-")[0] in ("pexels", "pixabay")


def _img_relevant(im: dict, anchor_stems: set[str], query_trusted: bool = False) -> bool:
    """Stock relevance gate (see tiers above). Rejected candidates fall
    through to the next hit / query / the honest title-card diagram fallback.

    query_trusted: the provider searched OUR query (Pexels/Pixabay), so the
    query match itself is the relevance evidence — tiers 1-2 vetoes still
    apply, but tier 3 (context words) and the anchor-token check are skipped
    (these providers return no descriptions/categories).
    """
    if not anchor_stems:
        return True
    from ..providers.llm_template import stem as _stem
    import re as _re
    cats = im.get("categories") or []
    text = ((im.get("title") or "") + " " + (im.get("description") or "")
            + " " + " ".join(cats)).lower()
    anchors = set(anchor_stems)
    ent_topic = {_stem(w) for w in ENTERTAINMENT_TOPIC_WORDS}
    if not (ent_topic & anchors):
        for m in MUSIC_SUBSTR:
            if m in text:
                return False
        words = set(_re.findall(r"[a-z]{3,}", text))
        if words & MUSIC_WORDS:
            return False
        catwords = set()
        for ct in cats:
            catwords.update(_re.findall(r"[a-z]{3,}", ct.lower()))
        if catwords & SUBJECT_WORDS:
            return False
        if not query_trusted:
            # phenomenon context (stemmed both sides so plurals match)
            ctx = {_stem(w) for w in PHENOMENON_CONTEXT}
            textstems = {_stem(w) for w in _re.findall(r"[a-z]{4,}", text)}
            if not (textstems & ctx):
                # ...or an anchor-bearing category that is not a bare namesake
                cat_ok = False
                for ct in cats:
                    stems = {_stem(w) for w in _re.findall(r"[a-z]{4,}", ct.lower())}
                    stems.discard("category")
                    if not (stems & anchors):
                        continue
                    if len(stems) == 1 or (stems - anchors):
                        cat_ok = True
                        break
                if not cat_ok:
                    return False
    if query_trusted:
        return True
    toks = {_stem(w) for w in _re.findall(r"[a-zA-Z]{4,}", text)}
    return bool(toks & anchors)


def _scene_claims(sc: dict, claims_map: dict | None) -> tuple:
    """Resolve a scene's claim_ids (list or stringified list) to claim texts
    for diagram labels. Empty tuple when unavailable (labels fall back to
    narration sentences)."""
    if not claims_map:
        return ()
    ids = sc.get("claim_ids") or []
    if isinstance(ids, str):
        try:
            import ast as _ast
            ids = _ast.literal_eval(ids)
        except Exception:
            ids = [ids]
    if not isinstance(ids, (list, tuple)):
        ids = [ids]
    return tuple(claims_map[i] for i in ids if i in claims_map)


def collect_assets(storyboard: list[dict], stack, assets_dir: Path, progress_cb=None,
                   anchors: list[str] | None = None,
                   claims_map: dict | None = None) -> list[dict]:
    from .diagrams import render_diagram_png
    from ..providers.llm_template import stem as _stem
    anchor_stems = {_stem(a) for a in (anchors or [])}
    assets_dir.mkdir(parents=True, exist_ok=True)
    diagrams_dir = assets_dir.parent / "diagrams"
    diagrams_dir.mkdir(parents=True, exist_ok=True)
    assets: list[dict] = []
    seen_urls: set[str] = set()
    for i, sc in enumerate(storyboard):
        if progress_cb:
            progress_cb(i + 1, len(storyboard), sc["scene_id"])
        sid = sc["scene_id"]
        primary_done = False

        # 1) generated diagram PNG (preferred for mechanism scenes)
        if sc.get("diagram"):
            try:
                dp = diagrams_dir / f"{sid}_{sc['diagram']}.svg"
                png = diagrams_dir / f"{sid}_{sc['diagram']}.png"
                rp = render_diagram_png(sc["diagram"], sc["title"], sc["narration"], dp, png,
                                        claims=_scene_claims(sc, claims_map))
                if rp and Path(rp).exists():
                    _add(assets, sid, True, kind="diagram", path=str(rp),
                         source="generated-svg", source_url="", license="CC0 (project-generated)",
                         creator="science-youtube-ai",
                         description=f"{sc['diagram']} diagram: {sc['title']}")
                    primary_done = True
            except Exception:
                pass

        # 2) stock video (only if a video provider is configured)
        if not primary_done:
            for vp in stack.videos:
                try:
                    if not vp.status().available:
                        continue
                    vp_trusted = is_query_trusted_source(vp.name)
                    for v in vp.search_videos(sc["visual_query"], limit=2):
                        if v["url"] in seen_urls:
                            continue
                        if not _img_relevant(v, anchor_stems, query_trusted=vp_trusted):
                            continue
                        try:
                            p = download(v["url"], assets_dir / f"{sid}.mp4")
                            seen_urls.add(v["url"])
                            _add(assets, sid, True, kind="video", path=str(p),
                                 source=vp.name, source_url=v.get("page_url", ""),
                                 license=v.get("license", ""), creator=v.get("creator", ""),
                                 description=v.get("title", ""))
                            primary_done = True
                            break
                        except Exception:
                            continue
                    if primary_done:
                        break
                except Exception:
                    continue

        # 3) stock/science image (also collected as secondary when diagram is primary,
        #    for thumbnail pool and renderer fallback). Falls back to the short
        #    anchor query when the primary query returns nothing.
        queries = [sc["visual_query"]]
        if sc.get("visual_query_fallback") and sc["visual_query_fallback"] != sc["visual_query"]:
            queries.append(sc["visual_query_fallback"])
        for ip in stack.images:
            try:
                if not ip.status().available:
                    continue
                ip_trusted = is_query_trusted_source(ip.name)
                hits: list[dict] = []
                for q in queries:
                    hits = ip.search_images(q, limit=5)
                    if hits:
                        break
                for im in hits:
                    if im["url"] in seen_urls:
                        continue
                    if not _img_relevant(im, anchor_stems, query_trusted=ip_trusted):
                        continue
                    try:
                        p = download(im["url"], assets_dir / f"{sid}.jpg")
                        seen_urls.add(im["url"])
                        _add(assets, sid, not primary_done, kind="image", path=str(p),
                             source=ip.name, source_url=im.get("page_url", im.get("url", "")),
                             license=im.get("license", ""), creator=im.get("creator", ""),
                             description=im.get("title", ""),
                             img_description=im.get("description", ""),
                             categories=im.get("categories", []))
                        primary_done = True
                        break
                    except Exception:
                        continue
                if primary_done:
                    break
            except Exception:
                continue

        # 4) claims-diagram fallback, then title card (guaranteed visual).
        #    A mechanism scene whose stock photos all failed the veto still
        #    deserves an informative visual: with >=3 verified claims we can
        #    render a real diagram instead of a bare card. Kind alternates
        #    for variety; the PNG helper has a PIL fallback so it renders
        #    even when cairosvg is unavailable.
        if not primary_done:
            claims = _scene_claims(sc, claims_map)
            kind = ("process" if i % 2 == 0 else "anatomy") if len(claims) >= 3 else "title"
            try:
                dp = diagrams_dir / f"{sid}_{kind}.svg"
                png = diagrams_dir / f"{sid}_{kind}.png"
                rp = render_diagram_png(kind, sc["title"], sc["narration"], dp, png,
                                        claims=claims)
                _add(assets, sid, True, kind="diagram", path=str(rp),
                     source="generated-svg", source_url="", license="CC0 (project-generated)",
                     creator="science-youtube-ai",
                     description=f"{kind} diagram (claims fallback): {sc['title']}"
                     if kind != "title" else f"Title card: {sc['title']}")
            except Exception:
                _add(assets, sid, True, kind="diagram", path="", source="generated-svg",
                     source_url="", license="CC0 (project-generated)", creator="science-youtube-ai",
                     description=f"Title card (unrendered): {sc['title']}")
    return assets
