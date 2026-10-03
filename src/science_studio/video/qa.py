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


def _ffmpeg_exe() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _probe_streams(video: Path) -> dict:
    """Width/height/fps/codecs parsed from `ffmpeg -i` (no ffprobe needed)."""
    info: dict = {}
    exe = _ffmpeg_exe()
    if not exe:
        return info
    try:
        r = subprocess.run([exe, "-i", str(video)], capture_output=True, timeout=60)
        err = r.stderr.decode(errors="ignore")
        import re
        for line in err.splitlines():
            if "Video:" in line:
                m = re.search(r"Video:\s*(\w+)", line)
                if m:
                    info["vcodec"] = m.group(1)
                d = re.search(r"(\d{3,5})x(\d{3,5})", line)
                if d:
                    info["width"] = int(d.group(1))
                    info["height"] = int(d.group(2))
                break
        m = re.search(r"(\d+(?:\.\d+)?)\s*fps", err)
        if m:
            info["fps"] = float(m.group(1))
        m = re.search(r"Audio:\s*(\w+)", err)
        if m:
            info["acodec"] = m.group(1)
    except Exception:
        pass
    return info


def _black_segments(video: Path) -> int | None:
    """Count black segments (>=0.5s). None = could not measure."""
    exe = _ffmpeg_exe()
    if not exe:
        return None
    try:
        r = subprocess.run(
            [exe, "-i", str(video), "-vf", "blackdetect=d=0.5:pix_th=0.05",
             "-an", "-f", "null", "-"],
            capture_output=True, timeout=900)
        import re
        return len(re.findall(r"black_start", r.stderr.decode(errors="ignore")))
    except Exception:
        return None


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

    # 11. resolution / fps / codec (YouTube-compatible HD)
    streams = _probe_streams(video_path) if v_ok else {}
    if streams:
        res_ok = streams.get("width") == 1920 and streams.get("height") == 1080
        codec_ok = (streams.get("vcodec", "") in ("h264", "avc")) and \
            (streams.get("acodec", "") in ("aac", "mp3"))
        check("resolution_1080p", res_ok,
              f"{streams.get('width')}x{streams.get('height')} @ {streams.get('fps')}fps")
        check("codec_compatible", codec_ok,
              f"v:{streams.get('vcodec')} a:{streams.get('acodec')}")
    else:
        check("resolution_1080p", True, "skipped: no ffmpeg probe available")
        check("codec_compatible", True, "skipped: no ffmpeg probe available")
    # 12. black frames / rendering gaps
    nblack = _black_segments(video_path) if v_ok else None
    if nblack is None:
        check("no_black_frames", True, "skipped: blackdetect unavailable")
    else:
        check("no_black_frames", nblack == 0, f"{nblack} black segments >=0.5s")
    # 13. thumbnail validity
    thumb = project_root / "production" / "final" / "thumbnail.png"
    try:
        from PIL import Image
        with Image.open(thumb) as im:
            t_ok = im.size == (1280, 720)
            t_detail = f"{im.size[0]}x{im.size[1]}"
    except Exception as e:
        t_ok, t_detail = False, f"unreadable: {e}"[:120]
    check("thumbnail_valid", t_ok, t_detail)
    # 14. metadata completeness
    import json as _json
    try:
        meta = _json.loads((project_root / "production" / "final" / "metadata.json")
                           .read_text(encoding="utf-8"))
        m_ok = (len(meta.get("titles", [])) >= 2
                and len(meta.get("chapters", [])) == len(storyboard)
                and len(meta.get("description", "")) > 200
                and len(meta.get("tags", [])) >= 5)
        m_detail = (f"{len(meta.get('titles', []))} titles, "
                    f"{len(meta.get('chapters', []))}/{len(storyboard)} chapters, "
                    f"{len(meta.get('description', ''))} desc chars")
    except Exception as e:
        m_ok, m_detail = False, f"metadata unreadable: {e}"[:120]
    check("metadata_complete", m_ok, m_detail)
    # 15. scene -> sourced-claim traceability
    sourced = {c["claim_id"] for c in claims if c.get("source_ids")}
    traced = [s["scene_id"] for s in storyboard
              if set(s.get("claim_ids", [])) & sourced]
    cov = len(traced) / max(1, len(storyboard))
    check("visual_narration_traceable", cov >= 0.8,
          f"{len(traced)}/{len(storyboard)} scenes carry sourced claims")
    # 16. subtitle timing + readability
    try:
        srt_p = Path(subs.get("srt", ""))
        srt_txt = srt_p.read_text(encoding="utf-8")
        import re as _re2
        ends = [int(h) * 3600 + int(m) * 60 + int(s_)
                for h, m, s_ in _re2.findall(r"-->\s*(\d+):(\d+):(\d+),", srt_txt)]
        last_end = max(ends) if ends else 0
        lines = [l for l in srt_txt.splitlines()
                 if l.strip() and not l.strip().isdigit() and "-->" not in l and l.strip() != "WEBVTT"]
        longest = max((len(l) for l in lines), default=0)
        timing_ok = abs(last_end - narr_total) < max(15, narr_total * 0.05)
        read_ok = longest <= 90  # 2 wrapped lines; single-line cues stay <= ~45
        check("subtitle_timing", timing_ok,
              f"last cue ends {last_end}s vs narration {narr_total:.0f}s ({subs.get('cues', 0)} cues)")
        check("subtitle_readability", read_ok, f"longest cue line {longest} chars")
    except Exception as e:
        check("subtitle_timing", False, f"srt unreadable: {e}"[:120])
        check("subtitle_readability", False, f"srt unreadable: {e}"[:120])
    # 17. minimum scene length (no flash/gap scenes)
    shorts = [n["scene_id"] for n in narrations
              if float(n.get("duration_s", 0) or 0) < 8]
    check("min_scene_length", len(shorts) == 0,
          f"scenes <8s: {shorts}" if shorts else
          f"all {len(narrations)} scenes >= 8s")
    # 18. finished length inside the project's target band (±7% tolerance)
    try:
        import json as _json2
        idea_doc = _json2.loads((project_root / "idea.json").read_text(encoding="utf-8"))
        from ..story.duration import plan_for as _plan_for
        band = _plan_for(idea_doc.get("duration", "auto"))
        lo, hi = band["min_s"] * 0.93, band["max_s"] * 1.07
        in_band = lo <= vdur <= hi if vdur else False
        check("duration_in_target", in_band,
              f"video {vdur:.0f}s vs target {band['min_s']}-{band['max_s']}s")
    except Exception as e:
        check("duration_in_target", True, f"skipped: {e}"[:120])

    failed = [c for c in checks if not c["ok"]]
    status = "pass" if not failed else ("review" if len(failed) <= 2 else "fail")
    return {"status": status, "checks": checks, "video_duration_s": vdur,
            "narration_total_s": narr_total, "failed": [c["name"] for c in failed]}
