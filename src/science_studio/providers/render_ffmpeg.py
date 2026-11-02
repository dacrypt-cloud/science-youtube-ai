"""FFmpeg renderer — real automated editing. 16:9 1080p, scenes timed to narration.

Job spec:
  {width, height, fps, scenes: [{image, video?, audio, duration_s, title, onscreen_text}],
   music?, music_gain?, subtitles_srt?, out_extra?}
Each scene -> segment mp4 (still image w/ slow zoompan + audio, or video loop/trim),
then concat. Text overlay drawn with Pillow onto the image (no font dependency).
Motion (Ken Burns variants, diagram builds, kinetic captions, progress bar)
is automatic; set MOTION=0 to disable.
"""
from __future__ import annotations
import subprocess, json, shutil, os
from pathlib import Path
from .base import RenderingProvider, ProviderStatus
from ..config import get_settings


def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        raise RuntimeError(f"no ffmpeg available: {e}")


class FFmpegRenderer(RenderingProvider):
    name = "ffmpeg"

    def status(self) -> ProviderStatus:
        try:
            exe = ffmpeg_exe()
            r = subprocess.run([exe, "-version"], capture_output=True, timeout=15)
            if r.returncode == 0:
                return ProviderStatus(self.name, True, True, f"ffmpeg at {exe}")
            return ProviderStatus(self.name, False, True, "ffmpeg binary failed")
        except Exception as e:
            return ProviderStatus(self.name, False, True, str(e))

    def render(self, job: dict, out_path: Path, progress_cb=None) -> dict:
        from PIL import Image, ImageDraw
        exe = ffmpeg_exe()
        cfg = get_settings()
        W = int(job.get("width", cfg.video_width))
        H = int(job.get("height", cfg.video_height))
        fps = int(job.get("fps", cfg.video_fps))
        scenes = job.get("scenes", [])
        from ..video.motion import (zoom_variant, zoom_filter, fade_filter,
                                    concat_list_file, parse_srt, write_ass,
                                    progress_filter, ffesc, has_filter)
        motion_on = os.environ.get("MOTION", "1") != "0"
        if not scenes:
            raise RuntimeError("render job has no scenes")
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        work = out_path.parent / "_segments"
        work.mkdir(parents=True, exist_ok=True)

        # Prepare background music (optional, quiet)
        music = job.get("music")
        seg_files: list[Path] = []
        total = 0.0
        for i, sc in enumerate(scenes):
            dur = float(sc.get("duration_s", 0) or 0)
            if dur <= 0:
                continue
            total += dur
            audio = sc.get("audio", "")
            # 1) segment video (stock B-roll clip or still/diagram frame)
            seg = work / f"seg_{i:03d}.mp4"
            video_src = sc.get("video", "")
            base_vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                       f"crop={W}:{H},fps={fps},format=yuv420p")
            if motion_on:
                _fz = fade_filter(dur)
                if _fz:
                    base_vf += "," + _fz
            if video_src and Path(video_src).exists():
                # Explicit -map / filter_complex strips any embedded stock-clip
                # audio (which would otherwise beat mono TTS in ffmpeg's stream
                # selector and mute narration); -stream_loop -1 + apad + -t dur
                # locks segment duration to exact millisecond parity with captions.
                badge_png = work / f"badge_{i:03d}.png"
                has_badge = (motion_on and dur >= 3.0 and bool((sc.get("title") or "").strip())
                             and self._make_broll_badge(sc, badge_png, W, H))
                if has_badge:
                    end_b = min(dur - 0.3, 4.8)
                    fc_vid = (
                        f"[0:v]{base_vf}[bv];"
                        f"[bv][1:v]overlay=0:0:enable='between(t,0.25,{end_b:.2f})'[vout]"
                    )
                    if audio and Path(audio).exists():
                        cmd = [exe, "-y", "-stream_loop", "-1", "-i", str(video_src),
                               "-loop", "1", "-t", f"{dur:.3f}", "-i", str(badge_png),
                               "-i", str(audio),
                               "-filter_complex", fc_vid,
                               "-map", "[vout]", "-map", "2:a:0",
                               "-af", "apad", "-t", f"{dur:.3f}",
                               "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                               "-c:a", "aac", str(seg)]
                    else:
                        cmd = [exe, "-y", "-stream_loop", "-1", "-i", str(video_src),
                               "-loop", "1", "-t", f"{dur:.3f}", "-i", str(badge_png),
                               "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={dur:.3f}",
                               "-filter_complex", fc_vid,
                               "-map", "[vout]", "-map", "2:a:0",
                               "-t", f"{dur:.3f}",
                               "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                               "-c:a", "aac", str(seg)]
                elif audio and Path(audio).exists():
                    cmd = [exe, "-y", "-stream_loop", "-1", "-i", str(video_src),
                           "-i", str(audio),
                           "-map", "0:v:0", "-map", "1:a:0",
                           "-vf", base_vf, "-af", "apad",
                           "-t", f"{dur:.3f}",
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                           "-c:a", "aac", str(seg)]
                else:
                    cmd = [exe, "-y", "-stream_loop", "-1", "-i", str(video_src),
                           "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={dur:.3f}",
                           "-map", "0:v:0", "-map", "1:a:0",
                           "-vf", base_vf,
                           "-t", f"{dur:.3f}",
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                           "-c:a", "aac", str(seg)]
            else:
                frame = work / f"frame_{i:03d}.png"
                self._make_frame(sc, frame, W, H)
                stages = sc.get("stages") or []
                _fz = fade_filter(dur) if motion_on else ""
                if len(stages) > 1:
                    # diagram build-up: cumulative stages, equal splits, static (crisp text)
                    per_st = dur / len(stages)
                    entries = [(s, per_st + (0.15 if k == len(stages) - 1 else 0.0))
                               for k, s in enumerate(stages)]
                    lst_in = concat_list_file(entries, work / f"frames_{i:03d}.txt")
                    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                          f"crop={W}:{H},fps={fps},format=yuv420p")
                    if _fz:
                        vf += "," + _fz
                    # NOTE: no -r input option — it overrides concat durations;
                    # the fps= filter in vf generates the steady frame rate.
                    in_args = ["-f", "concat", "-safe", "0",
                               "-i", str(lst_in)]
                else:
                    # photo: Ken Burns variant; single diagrams stay static (crisp text)
                    frames = max(2, int(round(dur * fps)) + 2)
                    if motion_on and not sc.get("is_diagram"):
                        vf = zoom_filter(zoom_variant(i), frames, W, H, fps)
                    elif motion_on:
                        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                              f"crop={W}:{H},fps={fps},format=yuv420p")
                    else:
                        # legacy gentle drift (MOTION=0)
                        vf = (f"scale=4000:-1,zoompan=z='1+0.05*on/{frames}':"
                              f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={fps},format=yuv420p")
                    if _fz:
                        vf += "," + _fz
                    in_args = ["-loop", "1", "-i", str(frame)]
                if audio and Path(audio).exists():
                    cmd = [exe, "-y", *in_args, "-i", str(audio),
                           "-vf", vf, "-af", "apad",
                           "-t", f"{dur:.3f}",
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                           "-c:a", "aac", str(seg)]
                else:
                    cmd = [exe, "-y", *in_args,
                           "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={dur:.3f}",
                           "-vf", vf,
                           "-t", f"{dur:.3f}",
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                           "-c:a", "aac", str(seg)]
            r = subprocess.run(cmd, capture_output=True, timeout=900)
            if r.returncode != 0 or not seg.exists():
                raise RuntimeError(f"scene {i} render failed: {r.stderr[-2000:].decode(errors='ignore')}")
            seg_files.append(seg)
            if progress_cb:
                progress_cb(i + 1, len(scenes))

        # 3) concat (absolute paths: ffmpeg resolves relative to the list file)
        lst = work / "concat.txt"
        lst.write_text("".join(f"file '{s.resolve().as_posix()}'\n" for s in seg_files), encoding="utf-8")
        tmp = out_path.parent / "_concat.mp4"
        r = subprocess.run([exe, "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-c", "copy", str(tmp)], capture_output=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError("concat failed: " + r.stderr[-2000:].decode(errors="ignore"))
        # 3b) motion finishing pass: kinetic captions + progress bar.
        # Video-only (audio copied) so A/V and subtitles stay sample-synced.
        subs_srt = job.get("subtitles_srt", "")
        if motion_on and subs_srt and Path(subs_srt).exists():
            try:
                cues = parse_srt(subs_srt)
                timed_cues = None
                sw_path = job.get("subtitles_words", "")
                if sw_path and Path(sw_path).exists():
                    try:
                        timed_cues = json.loads(Path(sw_path).read_text(encoding="utf-8"))
                    except Exception:
                        timed_cues = None
                vf_fin = [progress_filter(W, H, total)]
                if (cues or timed_cues) and has_filter(exe, "subtitles"):
                    ass = out_path.parent / "captions.ass"
                    write_ass(cues, ass, W, H, timed_cues=timed_cues)
                    vf_fin.insert(0, f"subtitles='{ffesc(ass)}'")
                tmp2 = out_path.parent / "_captioned.mp4"
                rcap = subprocess.run(
                    [exe, "-y", "-i", str(tmp), "-vf", ",".join(vf_fin),
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                     "-c:a", "copy", str(tmp2)], capture_output=True, timeout=900)
                if rcap.returncode == 0 and tmp2.exists():
                    tmp.unlink(missing_ok=True)
                    tmp = tmp2
            except Exception:
                pass  # non-fatal: ship the concat as-is
        # 4) optional music bed @ low volume
        if music and Path(music).exists():
            gain = float(job.get("music_gain", 0.08))
            r2 = subprocess.run(
                [exe, "-y", "-i", str(tmp), "-stream_loop", "10", "-i", str(music),
                 "-filter_complex", f"[1:a]volume={gain}[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[a]",
                 "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
                 "-shortest", str(out_path)], capture_output=True, timeout=600)
            if r2.returncode != 0:
                # non-fatal: ship without music
                shutil.copy2(tmp, out_path)
        else:
            shutil.copy2(tmp, out_path)
        # workspace budget: segments + concat are regenerable — remove on success
        # (kept on failure for debugging, since cleanup only runs here).
        try:
            shutil.rmtree(work, ignore_errors=True)
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return {"path": str(out_path), "duration_s": total, "scenes": len(seg_files),
                "width": W, "height": H, "fps": fps, "provider": self.name}

    def _make_frame(self, sc: dict, frame_path: Path, W: int, H: int) -> None:
        from PIL import Image, ImageDraw, ImageFilter
        img_path = sc.get("image", "")
        base = None
        if img_path and Path(img_path).exists():
            try:
                base = Image.open(img_path).convert("RGB")
            except Exception:
                base = None
        if base is None:
            base = Image.new("RGB", (W, H), (10, 18, 32))
        # cover-fit
        base = _cover(base, W, H)
        # subtle dark gradient bottom for text legibility
        overlay = Image.new("L", (1, H))
        for y in range(H):
            t = y / H
            overlay.putpixel((0, y), int(150 * max(0, (t - 0.55) / 0.45)))
        black = Image.new("RGB", (W, H), (0, 0, 0))
        base = Image.composite(black, base, overlay.resize((W, H)))
        d = ImageDraw.Draw(base)
        from PIL import ImageFont
        def _font(bold: bool, size: int):
            for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                      if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                      "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
            return ImageFont.load_default()
        scale = W / 1280
        # diagrams already carry their own title header — don't double-print
        title = "" if sc.get("is_diagram") else (sc.get("title") or "")[:72]
        cap = "" if sc.get("is_diagram") else (sc.get("onscreen_text") or "")[:90]
        if title or cap:
            rgba = base.convert("RGBA")
            glass = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gd = ImageDraw.Draw(glass)
            f_title = _font(True, int(36 * scale))
            f_cap = _font(False, int(24 * scale))
            pad_x, pad_y = int(44 * scale), int(38 * scale)
            card_h = int((92 if (title and cap) else 62) * scale)
            t_len = max(len(title) * int(20 * scale), len(cap) * int(13 * scale), int(260 * scale))
            card_w = min(W - 2 * pad_x, t_len + int(64 * scale))
            gd.rounded_rectangle(
                [pad_x, pad_y, pad_x + card_w, pad_y + card_h],
                radius=int(14 * scale),
                fill=(8, 17, 32, 205),
                outline=(56, 189, 248, 190),
                width=max(2, int(2 * scale)),
            )
            gd.rounded_rectangle(
                [pad_x + int(12 * scale), pad_y + int(12 * scale),
                 pad_x + int(19 * scale), pad_y + card_h - int(12 * scale)],
                radius=3,
                fill=(56, 189, 248, 255),
            )
            tx = pad_x + int(32 * scale)
            if title:
                gd.text((tx, pad_y + int(12 * scale)), title, font=f_title, fill=(244, 248, 255, 255))
            if cap:
                cy = pad_y + int((54 if title else 18) * scale)
                gd.text((tx, cy), cap, font=f_cap, fill=(140, 212, 255, 255))
            base = Image.alpha_composite(rgba, glass).convert("RGB")
        base.save(frame_path)

    def _make_broll_badge(self, sc: dict, badge_path: Path, W: int, H: int) -> bool:
        """Render a transparent-RGBA top-left glassmorphic chapter pill for B-roll video."""
        try:
            from PIL import Image, ImageDraw, ImageFont

            def _font(bold: bool, size: int):
                for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                          if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
                    try:
                        return ImageFont.truetype(p, size)
                    except Exception:
                        continue
                return ImageFont.load_default()

            scale = W / 1280
            title = (sc.get("title") or "").strip()[:68]
            cap = (sc.get("onscreen_text") or "").strip()[:84]
            if not title:
                return False
            img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            gd = ImageDraw.Draw(img)
            f_title = _font(True, int(32 * scale))
            f_cap = _font(False, int(22 * scale))
            pad_x, pad_y = int(42 * scale), int(36 * scale)
            card_h = int((86 if cap else 58) * scale)
            t_len = max(len(title) * int(18 * scale), len(cap) * int(12 * scale), int(240 * scale))
            card_w = min(W - 2 * pad_x, t_len + int(60 * scale))
            gd.rounded_rectangle(
                [pad_x, pad_y, pad_x + card_w, pad_y + card_h],
                radius=int(14 * scale),
                fill=(8, 17, 32, 210),
                outline=(56, 189, 248, 200),
                width=max(2, int(2 * scale)),
            )
            gd.rounded_rectangle(
                [pad_x + int(12 * scale), pad_y + int(11 * scale),
                 pad_x + int(19 * scale), pad_y + card_h - int(11 * scale)],
                radius=3,
                fill=(255, 183, 77, 255),
            )
            tx = pad_x + int(32 * scale)
            gd.text((tx, pad_y + int(11 * scale)), title, font=f_title, fill=(244, 248, 255, 255))
            if cap:
                gd.text((tx, pad_y + int(50 * scale)), cap, font=f_cap, fill=(140, 212, 255, 255))
            img.save(badge_path)
            return True
        except Exception:
            return False


def _cover(img, W: int, H: int):
    w, h = img.size
    scale = max(W / w, H / h)
    img = img.resize((int(w * scale) + 1, int(h * scale) + 1))
    x = (img.size[0] - W) // 2
    y = (img.size[1] - H) // 2
    return img.crop((x, y, x + W, y + H))
