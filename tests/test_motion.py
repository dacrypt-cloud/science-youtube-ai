"""Tests for video/motion.py — Ken Burns, builds, kinetic captions, progress."""
import re
import pytest
from science_studio.video import motion as M


def test_variants_cycle():
    assert [M.zoom_variant(i) for i in range(5)] == \
        ["zoom_in", "zoom_out", "pan_right", "pan_left", "zoom_in"]


def test_zoom_filter_bounds():
    for v in ("zoom_in", "zoom_out", "pan_right", "pan_left"):
        f = M.zoom_filter(v, 1800, 1920, 1080, 30)
        assert "zoompan" in f and "s=1920x1080" in f
        assert "0.10*on" in f or "0.08*on" in f or "'1.10'" in f  # max zoom <=1.10
        assert "1.5" not in f and "2.0" not in f
    assert "iw/2-(iw/zoom/2)" in M.zoom_filter("zoom_in", 99, 1920, 1080, 30)


def test_fade_guard():
    assert M.fade_filter(0.5) == ""
    f = M.fade_filter(10.0)
    assert "fade=t=in:st=0:d=0.3" in f and "fade=t=out:st=9.70:d=0.3" in f


def test_progress_filter():
    f = M.progress_filter(1920, 1080, 707.7)
    assert f.count("drawbox") == 2 and "1920*t/707.70" in f


def test_parse_srt(tmp_path):
    srt = tmp_path / "t.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,500\nHello brave world\n\n"
                   "2\n00:01:00,000 --> 00:01:03,000\nSecond cue here\n")
    cues = M.parse_srt(srt)
    assert cues == [(1.0, 2.5, "Hello brave world"), (60.0, 63.0, "Second cue here")]


def test_word_dialogues_cover_cue():
    dlg = M.word_dialogues([(10.0, 14.0, "one two three four")])
    assert len(dlg) == 4
    assert dlg[0][0] == 10.0 and dlg[-1][1] == 14.0
    for (s1, e1, _, _), (s2, e2, _, _) in zip(dlg, dlg[1:]):
        assert e1 == s2 and e1 > s1  # contiguous, non-overlapping
    assert dlg[2][2] == "one two" and dlg[2][3] == "three"


def test_write_ass(tmp_path):
    p = M.write_ass([(1.0, 2.0, "Hello {braced} world")], tmp_path / "c.ass")
    t = p.read_text(encoding="utf-8")
    assert "DejaVu Sans" in t and "MarginL, MarginR, MarginV" in t
    assert t.count("Dialogue:") == 3
    assert "\\{braced\\}" in t  # braces escaped
    assert "\\c&H0000FFFF&" in t  # highlight override present


def test_render_stages(tmp_path):
    narr = ("First storm clouds gather over the plains. Then ice crystals collide "
            "aloft. Charge separates across the cloud. Finally lightning strikes.")
    stages = M.render_stages("process", "T", narr, tmp_path / "st", "sc",
                             claims=())
    assert 2 <= len(stages) <= 6
    assert all(p.exists() for p in stages)
    assert stages[0].read_bytes() != stages[-1].read_bytes()
    # title cards collapse to a single stage
    one = M.render_stages("title", "T", narr, tmp_path / "st", "tt", claims=())
    assert len(one) == 1


def test_diagram_limit(tmp_path):
    from science_studio.visuals.diagrams import render_diagram
    p = render_diagram("process", "T", "one two three. four five six seven. eight nine ten eleven.",
                       tmp_path / "d.svg", claims=(), limit=2)
    q = render_diagram("process", "T", "one two three. four five six seven. eight nine ten eleven.",
                       tmp_path / "d_full.svg", claims=())
    n_lim = p.read_text(encoding="utf-8").count("<rect x=")
    n_full = q.read_text(encoding="utf-8").count("<rect x=")
    assert n_full - n_lim == 1  # limit=2 sliced exactly one box off the full 3


def test_concat_list_file(tmp_path):
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    p = M.concat_list_file([(a, 1.5), (b, 2.0)], tmp_path / "l.txt")
    t = p.read_text(encoding="utf-8")
    assert "duration 1.500" in t and t.count("file '") == 3  # last repeated


def _ffmpeg():
    import shutil
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pytest.skip("ffmpeg unavailable")


def test_kenburns_ass_smoke(tmp_path):
    """Actually execute zoompan + ASS burn + progress on a 2s clip."""
    import subprocess
    from PIL import Image
    exe = _ffmpeg()
    img = tmp_path / "f.png"
    Image.new("RGB", (640, 360), (20, 40, 80)).save(img)
    ass = M.write_ass([(0.2, 1.8, "smoke test caption")], tmp_path / "c.ass",
                      640, 360)
    vf = (M.zoom_filter("zoom_in", 60, 640, 360, 30) +
          f",subtitles='{M.ffesc(ass)}'," + M.progress_filter(640, 360, 2.0))
    out = tmp_path / "o.mp4"
    r = subprocess.run([exe, "-y", "-loop", "1", "-i", str(img), "-t", "2",
                        "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast",
                        str(out)], capture_output=True, timeout=300)
    assert r.returncode == 0, r.stderr[-800:].decode(errors="ignore")
    assert out.exists() and out.stat().st_size > 5000
    r2 = subprocess.run([exe, "-i", str(out)], capture_output=True, timeout=30)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r2.stderr.decode(errors="ignore"))
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    assert 1.8 <= dur <= 2.2


def test_concat_build_smoke(tmp_path):
    """Actually execute the diagram-build path: stills+durations must hold.

    Regression: an input `-r` before the concat demuxer collapses every
    stage to ~1 frame (take-7 shipped a 112s video instead of 708s).
    """
    import subprocess
    from PIL import Image
    exe = _ffmpeg()
    pngs = []
    for j, col in enumerate(((200, 40, 40), (40, 200, 40))):
        p = tmp_path / f"s{j}.png"
        Image.new("RGB", (640, 360), col).save(p)
        pngs.append(p)
    lst = M.concat_list_file([(str(pngs[0]), 1.0), (str(pngs[1]), 1.0)],
                             tmp_path / "frames.txt")
    out = tmp_path / "b.mp4"
    # NOTE: no input -r — mirrors render_ffmpeg.py build in_args exactly.
    r = subprocess.run(
        [exe, "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=2.00",
         "-t", "2.00", "-vf",
         "scale=640:360:force_original_aspect_ratio=increase,crop=640:360,"
         "fps=30,format=yuv420p",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
         "-shortest", str(out)], capture_output=True, timeout=300)
    assert r.returncode == 0, r.stderr[-800:].decode(errors="ignore")
    r2 = subprocess.run([exe, "-i", str(out)], capture_output=True, timeout=30)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r2.stderr.decode(errors="ignore"))
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    assert 1.8 <= dur <= 2.2, f"build seg collapsed to {dur}s"
