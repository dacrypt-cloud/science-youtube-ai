"""Pillow-native diagram fallback: PNG diagrams with zero system graphics libs."""
import sys
sys.path.insert(0, "src")


def _block_cairosvg(monkeypatch):
    # Simulate an environment without cairosvg (ImportError on import).
    import builtins
    real_import = builtins.__import__
    def fake_import(name, *args, **kwargs):
        if name == "cairosvg":
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_render_png_all_kinds_without_cairo(monkeypatch, tmp_path):
    _block_cairosvg(monkeypatch)
    from science_studio.visuals.diagrams import render_diagram_png
    from PIL import Image
    narr = ("First, warm air rises inside the cloud. Then water droplets freeze into ice. "
            "Next, collisions separate electric charge. Finally the field breaks the air down.")
    for kind in ("lifecycle", "anatomy", "process", "timeline", "chart", "scale", "title"):
        png = render_diagram_png(kind, f"Test {kind}", narr,
                                 tmp_path / f"{kind}.svg", tmp_path / f"{kind}.png")
        assert png.exists() and png.stat().st_size > 5000
        with Image.open(png) as im:
            assert im.size == (1920, 1080)


def test_svg_artifact_always_written(tmp_path):
    from science_studio.visuals.diagrams import render_diagram_png
    png = render_diagram_png("process", "T", "First this happens. Then that happens. Finally done.",
                             tmp_path / "d.svg", tmp_path / "d.png")
    assert (tmp_path / "d.svg").exists()
    assert png.exists()


def test_shorten_word_boundary_ellipsis():
    from science_studio.visuals.diagrams import _shorten
    assert _shorten("short text", 46) == "short text"
    out = _shorten("Positive lightning produces both higher peak currents and longer continuing currents", 46)
    assert out.endswith("…") and len(out) <= 48
    assert out == "Positive lightning produces both higher peak…", out
    # no mid-word cut, no trailing punctuation before ellipsis
    out2 = _shorten("The conductivity of the electrical ground, be it soil, fresh water", 46)
    assert out2.endswith("…") and "…" not in out2[:-1] and not out2[-2] in " ,;:"
