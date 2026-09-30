"""Assembles the FFmpeg job from storyboard + assets + narration. Scenes timed
to ACTUAL narration durations — never word-count guesses."""
from __future__ import annotations
from pathlib import Path


def build_job(storyboard: list[dict], assets: list[dict], narrations: list[dict],
              music: dict, cfg) -> dict:
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
        scenes.append({"scene_id": sid, "title": sc["title"], "onscreen_text": sc.get("onscreen_text", ""),
                       "image": img, "video": vid, "audio": n.get("path", ""), "duration_s": dur,
                       "is_diagram": is_diagram})
    return {"width": cfg.video_width, "height": cfg.video_height, "fps": cfg.video_fps,
            "scenes": scenes, "music": music.get("path", ""),
            "music_gain": music.get("gain", 0.08)}
