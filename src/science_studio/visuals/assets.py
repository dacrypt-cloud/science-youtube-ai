"""Asset manager — download/cache/dedupe with full license metadata.

Priority per scene: generated diagram (mechanisms) > stock video > stock image >
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


def _img_relevant(im: dict, anchor_stems: set[str]) -> bool:
    """Stock relevance gate: the file title must share >=1 anchor stem.

    Without this, full-text search quirks return nebulae for 'lightning bolt
    interactions'. Rejected candidates fall through to the next hit / query /
    the honest title-card diagram fallback.
    """
    if not anchor_stems:
        return True
    from ..providers.llm_template import stem as _stem
    import re as _re
    toks = {_stem(w) for w in _re.findall(r"[a-zA-Z]{4,}",
            ((im.get("title") or "") + " " + (im.get("description") or "")).lower())}
    return bool(toks & set(anchor_stems))


def collect_assets(storyboard: list[dict], stack, assets_dir: Path, progress_cb=None,
                   anchors: list[str] | None = None) -> list[dict]:
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
                rp = render_diagram_png(sc["diagram"], sc["title"], sc["narration"], dp, png)
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
                    for v in vp.search_videos(sc["visual_query"], limit=2):
                        if v["url"] in seen_urls:
                            continue
                        if not _img_relevant(v, anchor_stems):
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
                hits: list[dict] = []
                for q in queries:
                    hits = ip.search_images(q, limit=3)
                    if hits:
                        break
                for im in hits:
                    if im["url"] in seen_urls:
                        continue
                    if not _img_relevant(im, anchor_stems):
                        continue
                    try:
                        p = download(im["url"], assets_dir / f"{sid}.jpg")
                        seen_urls.add(im["url"])
                        _add(assets, sid, not primary_done, kind="image", path=str(p),
                             source=ip.name, source_url=im.get("page_url", im.get("url", "")),
                             license=im.get("license", ""), creator=im.get("creator", ""),
                             description=im.get("title", ""))
                        primary_done = True
                        break
                    except Exception:
                        continue
                if primary_done:
                    break
            except Exception:
                continue

        # 4) title-card fallback (guaranteed visual)
        if not primary_done:
            try:
                dp = diagrams_dir / f"{sid}_title.svg"
                png = diagrams_dir / f"{sid}_title.png"
                render_diagram("title", sc["title"], sc["narration"], dp)
                rp = rasterize(dp, png)
                _add(assets, sid, True, kind="diagram", path=str(rp) if rp else "",
                     source="generated-svg", source_url="", license="CC0 (project-generated)",
                     creator="science-youtube-ai", description=f"Title card: {sc['title']}")
            except Exception:
                _add(assets, sid, True, kind="diagram", path="", source="generated-svg",
                     source_url="", license="CC0 (project-generated)", creator="science-youtube-ai",
                     description=f"Title card (unrendered): {sc['title']}")
    return assets
