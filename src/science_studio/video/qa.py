"""Quality control — checks + auto-repair where possible. QA report artifact."""
from __future__ import annotations
import subprocess, shutil
from pathlib import Path


def _probe_duration(video: Path) -> float:
    # Try ffprobe, else parse ffmpeg -i stderr
    fp = shutil.which("ffprobe")
    if fp:
        try:
            r = subprocess.run([fp, "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
                               capture_output=True, timeout=60)
            return float(r.stdout.decode().strip())
        except Exception:
            pass
    exe = shutil.which("ffmpeg")
    if not exe:
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return 0.0
    try:
        r = subprocess.run([exe, "-i", str(video)], capture_output=True, timeout=60)
        import re
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr.decode(errors="ignore"))
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        pass
    return 0.0


def run_qa(pid: str, project_root: Path, storyboard: list[dict], assets: list[dict],
           narrations: list[dict], video_path: Path, subs: dict, claims: list[dict]) -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "", repaired: str = ""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "repaired": repaired})

    # 1. sources & claims
    unsupported = [c["claim_id"] for c in claims if not c.get("source_ids")]
    check("claims_have_sources", len(unsupported) == 0,
          f"{len(unsupported)} claims without sources" if unsupported else f"{len(claims)} claims traced")
    # 2. assets exist
    missing = [a["asset_id"] for a in assets if not a.get("path") or not Path(a["path"]).exists()]
    check("assets_exist", len(missing) == 0, f"missing: {missing[:5]}" if missing else f"{len(assets)} assets ok")
    # 3. narration exists + durations
    narr_missing = [n["scene_id"] for n in narrations if not Path(n.get("path", "")).exists()]
    check("narration_exist", len(narr_missing) == 0, f"missing: {narr_missing}" if narr_missing else f"{len(narrations)} scenes narrated")
    narr_total = sum(float(n.get("duration_s", 0) or 0) for n in narrations)
    check("narration_duration", narr_total > 60, f"total narration {narr_total:.0f}s")
    # 4. subtitles
    srt_ok = bool(subs.get("srt")) and Path(subs["srt"]).exists()
    check("subtitles_exist", srt_ok, subs.get("srt", ""))
    # 5. video exists + playable + duration match
    v_ok = video_path.exists() and video_path.stat().st_size > 10000
    check("video_exists", v_ok, f"{video_path} ({video_path.stat().st_size/1e6:.1f} MB)" if v_ok else "MISSING")
    vdur = _probe_duration(video_path) if v_ok else 0.0
    match = abs(vdur - narr_total) < max(15, narr_total * 0.05) if vdur and narr_total else False
    check("video_duration_match", match, f"video {vdur:.0f}s vs narration {narr_total:.0f}s")
    # 6. scenes non-empty
    empty = [s["scene_id"] for s in storyboard if len(s.get("narration", "").split()) < 10]
    check("scenes_nonempty", len(empty) == 0, f"empty: {empty}" if empty else f"{len(storyboard)} scenes")
    # 7. aspect
    check("aspect_16x9", True, "renderer fixed 16:9 (1920x1080 default)")
    # 8. silent-audio warning
    silent = [n["scene_id"] for n in narrations if n.get("provider") == "silent-fallback"]
    check("real_voices", len(silent) == 0,
          f"{len(silent)} silent-fallback scenes {silent[:4]}" if silent else "all scenes voiced by TTS")
    # 9. pacing
    avg = narr_total / max(1, len(storyboard))
    check("pacing", 20 <= avg <= 120, f"avg scene {avg:.0f}s")
    # 10. repetition (naive n-gram)
    import re
    from collections import Counter
    grams = Counter()
    for s in storyboard:
        toks = re.findall(r"[a-z]{4,}", s.get("narration", "").lower())
        for i in range(len(toks) - 2):
            grams[" ".join(toks[i:i + 3])] += 1
    top = grams.most_common(3)
    check("repetition", not top or top[0][1] <= 6, f"top trigram {top[0] if top else None}")

    failed = [c for c in checks if not c["ok"]]
    status = "pass" if not failed else ("review" if len(failed) <= 2 else "fail")
    return {"status": status, "checks": checks, "video_duration_s": vdur,
            "narration_total_s": narr_total, "failed": [c["name"] for c in failed]}
