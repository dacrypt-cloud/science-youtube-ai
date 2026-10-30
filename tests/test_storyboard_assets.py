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

class _EmptyStack:
    videos = []
    images = []

def _scene(**kw):
    d = {"scene_id": "scene_04", "title": "Stage 1b", "narration": "Electrons flow down.",
         "visual_query": "lightning bolt", "diagram": "", "claim_ids": ["C1", "C2", "C3"]}
    d.update(kw)
    return d

def test_claims_diagram_fallback(tmp_path):
    from science_studio.visuals.assets import collect_assets
    cmap = {"C1": "Negative charge pools at the cloud base.",
            "C2": "Positive charge gathers at the cloud top.",
            "C3": "The electric field between them intensifies."}
    a = collect_assets([_scene()], _EmptyStack(), tmp_path / "assets", claims_map=cmap)
    prim = next(x for x in a if x["primary"])
    assert prim["kind"] == "diagram" and "claims fallback" in prim["description"]
    from pathlib import Path
    assert Path(prim["path"]).exists()

def test_title_card_without_claims(tmp_path):
    from science_studio.visuals.assets import collect_assets
    a = collect_assets([_scene(claim_ids=[])], _EmptyStack(), tmp_path / "assets",
                       claims_map={})
    prim = next(x for x in a if x["primary"])
    assert prim["kind"] == "diagram" and prim["description"].startswith("Title card:")

def test_steps_drops_divergent_claims():
    # run #3 take-3 scene_11 repro: claim heads that share no vocabulary
    # with the narration are dropped; narrated sentences back the labels.
    from science_studio.visuals.diagrams import _steps
    narr = "Lightning prevention rule recommends when the thunder roars, go indoors."
    claims = ("Electric currents circulating between charged clouds and the earth surface during lightning discharges",
              "The effectiveness of the lightning interception and protection measures is tested widely")
    labels = _steps(narr, 5, claims)
    assert any("effectiveness" in l for l in labels)
    assert not any("Electric currents" in l for l in labels)
    assert any("thunder roars" in l for l in labels)

def test_steps_keeps_aligned_claims():
    from science_studio.visuals.diagrams import _steps
    narr = "Ice crystals collide inside the thundercloud, separating electric charge until the field grows strong."
    claims = ("Ice crystals collide and transfer electric charge between cloud regions.",
              "The electric field between charge regions intensifies rapidly.")
    labels = _steps(narr, 2, claims)
    assert "crystals" in labels[0] and "field" in labels[1]  # [2] is "…" padding

def test_process_lines_fit_boxes(tmp_path):
    # take-4 scene_11 repro: horizontal box lines must stay <=22 chars or
    # the rendered text touches the box border.
    import re
    from science_studio.visuals.diagrams import render_diagram
    narr = ("Lightning prevention matters because thunderstorms grow quickly "
            "over the plains each summer season.")
    claims = ("Positive and negative lightning discharges reshape thunderstorm "
              "electrification patterns worldwide",)
    p = render_diagram("process", "T", narr, tmp_path / "p.svg", claims=claims)
    svg = p.read_text(encoding="utf-8")
    lines26 = [t.strip() for fs, t in
               re.findall(r'<text[^>]*font-size="(\d+)"[^>]*>([^<]*)</text>', svg)
               if fs == "26" and t.strip()]
    assert lines26, "expected horizontal box lines"
    assert all(len(t) <= 22 for t in lines26), lines26

def test_steps_drops_in_this_study():
    from science_studio.visuals.diagrams import _steps
    narr = "Lightning initiation remains puzzling despite decades of study."
    labels = _steps(narr, 5, ("In this study, lightning initiation mechanisms "
                             "are investigated thoroughly and carefully",))
    assert not any("In this study" in l for l in labels)
    assert any("puzzling" in l for l in labels)

def test_steps_etc_does_not_fragment():
    # take-5 scene_08 box 5 repro: "etc. benefit ..." must not break into a
    # lowercase fragment label.
    from science_studio.visuals.diagrams import _steps
    narr = ("Lightning warning systems in parks, schools, airports, etc. benefit "
            "from the output of such lightning nowcasting schemes every day.")
    labels = _steps(narr, 5, ())
    assert labels[0].startswith("Lightning warning")
    assert not any(l[:1].islower() for l in labels)

def test_steps_drops_lowercase_claim_head():
    from science_studio.visuals.diagrams import _steps
    narr = "Lightning detection networks improve warnings for vulnerable communities today."
    labels = _steps(narr, 5, ("benefit from the output of such lightning sensors worldwide daily",))
    assert not any("benefit" in l for l in labels)
    assert any("detection networks" in l for l in labels)
