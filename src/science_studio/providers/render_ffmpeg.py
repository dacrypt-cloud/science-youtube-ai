"""FFmpeg renderer — real automated editing. 16:9 1080p, scenes timed to narration.

Job spec:
  {width, height, fps, scenes: [{image, video?, audio, duration_s, title, onscreen_text}],
   music?, music_gain?, subtitles_srt?, out_extra?}
Each scene -> segment mp4 (still image w/ slow zoompan + audio, or video loop/trim),
then concat. Text overlay drawn with Pillow onto the image (no font dependency).
"""
from __future__ import annotations
import subprocess, json, shutil
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
            # 1) base frame
            frame = work / f"frame_{i:03d}.png"
            self._make_frame(sc, frame, W, H)
            # 2) segment video
            seg = work / f"seg_{i:03d}.mp4"
            video_src = sc.get("video", "")
            if video_src and Path(video_src).exists():
                cmd = [exe, "-y", "-stream_loop", "10", "-i", str(video_src),
                       "-i", str(audio) if audio else "anullsrc",
                       "-t", f"{dur:.2f}", "-vf",
                       f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps},format=yuv420p",
                       "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                       "-c:a", "aac", "-shortest", str(seg)]
                # if no audio file, synthesize silence
                if not audio or not Path(audio).exists():
                    cmd = [exe, "-y", "-stream_loop", "10", "-i", str(video_src),
                           "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={dur:.2f}",
                           "-t", f"{dur:.2f}", "-vf",
                           f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={fps},format=yuv420p",
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                           "-c:a", "aac", "-shortest", str(seg)]
            else:
                # still image + slow zoompan + narration audio
                frames = max(1, int(dur * fps))
                # zoompan from 1.0 -> 1.05 over the scene (gentle; keeps edges safe)
                vf = (f"scale=4000:-1,zoompan=z='1+0.05*on/{frames}':"
                      f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={fps},format=yuv420p")
                if audio and Path(audio).exists():
                    cmd = [exe, "-y", "-loop", "1", "-i", str(frame), "-i", str(audio),
                           "-t", f"{dur:.2f}", "-vf", vf,
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                           "-c:a", "aac", "-shortest", str(seg)]
                else:
                    cmd = [exe, "-y", "-loop", "1", "-i", str(frame),
                           "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={dur:.2f}",
                           "-t", f"{dur:.2f}", "-vf", vf,
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                           "-c:a", "aac", "-shortest", str(seg)]
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
        title = "" if sc.get("is_diagram") else (sc.get("title") or "")[:90]
        cap = (sc.get("onscreen_text") or "")[:140]
        if title:
            d.text((int(60 * scale), H - int(170 * scale)), title,
                   font=_font(True, int(52 * scale)), fill=(255, 255, 255),
                   stroke_width=2, stroke_fill=(0, 0, 0))
        if cap:
            d.text((int(60 * scale), H - int(105 * scale)), cap,
                   font=_font(False, int(36 * scale)), fill=(200, 220, 255),
                   stroke_width=1, stroke_fill=(0, 0, 0))
        base.save(frame_path)


def _cover(img, W: int, H: int):
    w, h = img.size
    scale = max(W / w, H / h)
    img = img.resize((int(w * scale) + 1, int(h * scale) + 1))
    x = (img.size[0] - W) // 2
    y = (img.size[1] - H) // 2
    return img.crop((x, y, x + W, y + H))
