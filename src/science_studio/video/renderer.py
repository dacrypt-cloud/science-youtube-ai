"""Assembles the FFmpeg job from storyboard + assets + narration. Scenes timed
to ACTUAL narration durations — never word-count guesses."""
from __future__ import annotations
from pathlib import Path


def build_job(storyboard: list[dict], assets: list[dict], narrations: list[dict],
              music: dict, cfg, claims_map=None, stages_dir=None) -> dict:
    by_scene_assets: dict[str, list[dict]] = {}
    for a in assets:
        by_scene_assets.setdefault(a["scene_id"], []).append(a)
    # honour the primary flag: renderer uses the primary asset only
    for sid in by_scene_assets:
        prim = [a for a in by_scene_assets[sid] if a.get("primary")]
        if prim:
            by_scene_assets[sid] = prim
    narr = {n["scene_id"]: n for n in narrations}
    scenes = []
    for sc in storyboard:
        sid = sc["scene_id"]
        n = narr.get(sid, {})
        dur = float(n.get("duration_s", 0) or 0)
        if dur <= 0:
            from ..story.duration import estimate_text_seconds
            dur = estimate_text_seconds(sc["narration"])
        alist = by_scene_assets.get(sid, [])
        img, vid, is_diagram = "", "", False
        for a in alist:
            p = a.get("path", "")
            if a.get("kind") == "video" and p.endswith(".mp4"):
                vid = p
            elif a.get("kind") in ("image", "diagram") and not img:
                if p.endswith(".png") or p.endswith(".jpg") or p.endswith(".jpeg"):
                    img = p
                    is_diagram = (a.get("kind") == "diagram")
        stages: list[str] = []
        if stages_dir and is_diagram and img:
            # cumulative diagram build-up (boxes 1, 1-2, ...); title cards
            # collapse to a single stage automatically.
            try:
                from .motion import render_stages
                kind = Path(img).stem.split("_")[-1]
                if kind in ("lifecycle", "anatomy", "process", "timeline",
                            "chart", "scale", "title"):
                    ids = sc.get("claim_ids") or []
                    if isinstance(ids, str):
                        try:
                            import ast as _ast
                            ids = _ast.literal_eval(ids)
                        except Exception:
                            ids = []
                    cmap = claims_map or {}
                    claims = tuple(cmap[i] for i in ids if cmap.get(i))
                    stages = [str(x) for x in render_stages(
                        kind, sc.get("title", ""), sc.get("narration", ""),
                        Path(stages_dir), sid, claims=claims)]
                    if stages:
                        img = stages[-1]
            except Exception:
                stages = []
        scenes.append({"scene_id": sid, "title": sc["title"], "onscreen_text": sc.get("onscreen_text", ""),
                       "image": img, "video": vid, "audio": n.get("path", ""), "duration_s": dur,
                       "is_diagram": is_diagram, "stages": stages})
    return {"width": cfg.video_width, "height": cfg.video_height, "fps": cfg.video_fps,
            "scenes": scenes, "music": music.get("path", ""),
            "music_gain": music.get("gain", 0.08)}
