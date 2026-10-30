"""Production-quality QA checks: narration hygiene, image relevance,
diagram text fit, subtitle integrity (fixture-driven, by check name)."""
from pathlib import Path

GOOD_1 = ("Collisions between graupel and ice crystals separate electric charge "
          "inside thunderclouds during lightning storms.")
GOOD_2 = ("The air around the lightning flash rapidly heats to temperatures "
          "of about 30000C in the thundercloud.")

def _idea(root: Path):
    import json
    (root / "idea.json").write_text(json.dumps({
        "idea": "How does a lightning bolt form inside a thundercloud when it strikes?",
        "duration": "12-15"}), encoding="utf-8")

def _run(root: Path, storyboard, assets, subs):
    from science_studio.video.qa import run_qa
    _idea(root)
    narr = [{"scene_id": s["scene_id"], "path": "", "duration_s": 60,
             "provider": "edge-tts"} for s in storyboard]
    claims = [{"claim_id": "C001", "claim": GOOD_1, "source_ids": ["S001"]}]
    rep = run_qa("t", root, storyboard, assets, narr, root / "nope.mp4",
                 subs, claims)
    return {c["name"]: c for c in rep["checks"]}

def test_production_checks_pass_on_clean(tmp_path):
    (tmp_path / "production" / "diagrams").mkdir(parents=True)
    (tmp_path / "production" / "diagrams" / "a.svg").write_text(
        '<svg><text x="1" y="300" font-family="s" font-size="30" fill="#fff">1. Short label here</text></svg>',
        encoding="utf-8")
    srt = tmp_path / "s.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nLightning forms.\n\n"
                   "2\n00:00:03,500 --> 00:00:06,000\nThunder follows.\n",
                   encoding="utf-8")
    sb = [{"scene_id": "scene_01", "narration": GOOD_1, "claim_ids": ["C001"]},
          {"scene_id": "scene_02", "narration": GOOD_2, "claim_ids": ["C001"]}]
    assets = [{"asset_id": "A001", "scene_id": "scene_01", "primary": True,
               "kind": "image", "path": "", "description": "File:Lightning bolt over city"}]
    got = _run(tmp_path, sb, assets, {"srt": str(srt), "cues": 2})
    assert got["narration_hygiene"]["ok"], got["narration_hygiene"]
    assert got["image_relevance"]["ok"], got["image_relevance"]
    assert got["diagram_text_fit"]["ok"], got["diagram_text_fit"]
    assert got["subtitle_integrity"]["ok"], got["subtitle_integrity"]

def test_production_checks_fail_on_dirty(tmp_path):
    (tmp_path / "production" / "diagrams").mkdir(parents=True)
    (tmp_path / "production" / "diagrams" / "a.svg").write_text(
        '<svg><text x="1" y="300" font-family="s" font-size="30" fill="#fff">'
        "1. Positive lightning produces both higher peak currents and longer continuing"
        "</text></svg>", encoding="utf-8")
    srt = tmp_path / "s.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:05,000\nLightning forms.\n\n"
                   "2\n00:00:04,000 --> 00:00:04,200\nX.\n", encoding="utf-8")
    sb = [{"scene_id": "scene_01",
           "narration": "implemented an explicit lightning module for storms today here.",
           "claim_ids": ["C001"]}]
    assets = [{"asset_id": "A001", "scene_id": "scene_01", "primary": True,
               "kind": "image", "path": "", "description": "File:Ic443 nebula stars"}]
    got = _run(tmp_path, sb, assets, {"srt": str(srt), "cues": 2})
    assert not got["narration_hygiene"]["ok"]
    assert not got["image_relevance"]["ok"]
    assert not got["diagram_text_fit"]["ok"]
    assert not got["subtitle_integrity"]["ok"]
