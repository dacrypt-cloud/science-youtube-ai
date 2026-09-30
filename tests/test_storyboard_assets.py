from science_studio.visuals.storyboard import build_storyboard
from science_studio.visuals.diagrams import render_diagram

def test_storyboard_diagram_detection():
    scenes = [{"title": "Inside the midgut", "narration": "The ookinete becomes an oocyst in the mosquito midgut life cycle stage."}]
    b = build_storyboard(scenes, "malaria", None)
    assert b[0]["diagram"] in ("lifecycle", "anatomy", "process")
    assert b[0]["visual_query"]

def test_diagram_renders(tmp_path):
    p = render_diagram("lifecycle", "Plasmodium", "Stage one. Stage two. Stage three.", tmp_path / "d.svg")
    assert p.exists() and "<svg" in p.read_text()
