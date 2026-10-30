"""Tests for video/conceptual.py — visual<->narration alignment."""
from science_studio.video.conceptual import visuals_only, narration_only, combined
from science_studio.research.planner import topic_anchors
from science_studio.providers.llm_template import stem

ANCH = {stem(a) for a in topic_anchors("How does a lightning bolt form inside a thundercloud?")}

SVG_SHELL = ('<svg><text font-size="64">TITLE</text>'
             '<text font-size="34">SUB</text>{labels}'
             '<text font-size="24">science-youtube-ai · footer</text></svg>')


def _svg(*labels):
    return SVG_SHELL.format(labels="".join(
        f'<text font-size="26">{l}</text>' for l in labels))


def test_placeholder_labels_fail(tmp_path):
    svg = tmp_path / "scene_01_process.svg"
    svg.write_text(_svg("Step 1", "Step 2", "Step 3"))
    png = tmp_path / "scene_01_process.png"
    png.write_bytes(b"fake")
    board = [{"scene_id": "scene_01", "title": "Hook",
              "narration": "Lightning splits the night sky over the mountains."}]
    assets = [{"scene_id": "scene_01", "primary": True, "kind": "diagram",
               "path": str(png)}]
    out = visuals_only(board, assets, ANCH, tmp_path)
    assert "scene_01" in out
    assert any(sev == "fail" and "placeholder" in msg for sev, msg in out["scene_01"])


def test_misleading_stock_fails():
    board = [{"scene_id": "scene_04", "title": "X",
              "narration": "Lightning leaders descend from the thundercloud."}]
    assets = [{"scene_id": "scene_04", "primary": True, "kind": "image",
               "path": "/tmp/x.jpg",
               "description": "File:Lightning Bolt, 2008, Barcelona.jpg",
               "img_description": "za + lightning bolt 2008_11_21 KGB, Barcelona",
               "categories": ["Category:Lightning Bolt"]}]
    out = visuals_only(board, assets, ANCH)
    assert any(sev == "fail" and "misleading" in msg
               for sev, msg in out.get("scene_04", []))


def test_good_stock_passes():
    board = [{"scene_id": "scene_01", "title": "X",
              "narration": "Lightning splits the night sky."}]
    assets = [{"scene_id": "scene_01", "primary": True, "kind": "image",
               "path": "/tmp/x.jpg",
               "description": "File:Lightning 14.07.2009 20-42-33.JPG",
               "img_description": "Lightning over Schaffhausen, photographed",
               "categories": ["Category:Cloud-to-ground lightning in Switzerland",
                              "Category:Night in Schaffhausen"]}]
    assert visuals_only(board, assets, ANCH) == {}


def test_connected_diagram_passes(tmp_path):
    svg = tmp_path / "scene_02_process.svg"
    svg.write_text(_svg("Charge separation in clouds", "Ice crystals collide",
                        "Electric field grows"))
    png = tmp_path / "scene_02_process.png"
    png.write_bytes(b"fake")
    board = [{"scene_id": "scene_02", "title": "Charge",
              "narration": ("Ice crystals collide inside the thundercloud, separating "
                            "electric charge until the field grows strong.")}]
    assets = [{"scene_id": "scene_02", "primary": True, "kind": "diagram",
               "path": str(png)}]
    narr = [{"scene_id": "scene_02", "duration_s": 6.0}]
    assert combined(board, assets, narr, ANCH, tmp_path) == {}


def test_disconnected_diagram_fails(tmp_path):
    svg = tmp_path / "scene_02_process.svg"
    svg.write_text(_svg("Photosynthesis in leaves", "Chlorophyll absorbs sunlight",
                        "Roots uptake potassium nitrate"))
    png = tmp_path / "scene_02_process.png"
    png.write_bytes(b"fake")
    board = [{"scene_id": "scene_02", "title": "Charge",
              "narration": ("Ice crystals collide inside the thundercloud, separating "
                            "electric charge until the field grows strong.")}]
    assets = [{"scene_id": "scene_02", "primary": True, "kind": "diagram",
               "path": str(png)}]
    narr = [{"scene_id": "scene_02", "duration_s": 30.0}]
    out = combined(board, assets, narr, ANCH, tmp_path)
    assert any(sev == "fail" and "disconnected" in msg
               for sev, msg in out.get("scene_02", []))


def test_title_card_never_fails(tmp_path):
    # a title card has <3 labels — honest fallback, no pile-on
    svg = tmp_path / "scene_05_title.svg"
    svg.write_text(_svg("A short onscreen line"))
    png = tmp_path / "scene_05_title.png"
    png.write_bytes(b"fake")
    board = [{"scene_id": "scene_05", "title": "Recap",
              "narration": "Thunder follows lightning after the strike channel heats."}]
    assets = [{"scene_id": "scene_05", "primary": True, "kind": "diagram",
               "path": str(png)}]
    narr = [{"scene_id": "scene_05", "duration_s": 20.0}]
    out = combined(board, assets, narr, ANCH, tmp_path)
    assert all(sev != "fail" for sev, _ in out.get("scene_05", []))


def test_narration_rate_warnings():
    board = [{"scene_id": "s1", "narration": "word " * 100},
             {"scene_id": "s2", "narration": "word " * 100}]
    narr = [{"scene_id": "s1", "duration_s": 200.0},   # 30 wpm — padded?
            {"scene_id": "s2", "duration_s": 10.0}]    # 600 wpm — truncated?
    out = narration_only(board, narr)
    assert any("padded" in m for _, m in out["s1"])
    assert any("truncated" in m for _, m in out["s2"])


def test_missing_primary_fails():
    board = [{"scene_id": "s9", "title": "X", "narration": "Lightning flashes."}]
    out = visuals_only(board, [], ANCH)
    assert any(sev == "fail" for sev, _ in out["s9"])
