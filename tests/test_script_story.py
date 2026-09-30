from science_studio.story.structure import pick_structure
from science_studio.story.script import build_script_outline, write_script
from science_studio.story.duration import plan_for, estimate_text_seconds

def test_structure_picks_journey_for_lifecycle():
    key, beats = pick_structure(["life cycle stage transmission inside mosquito"], "mosquito malaria", None)
    assert key == "journey_process" and len(beats) >= 5

def test_script_template_mode():
    claims = [{"claim_id": f"C{i:03d}", "claim": f"Mosquito biology fact number {i} about transmission.",
               "confidence": "established", "evidence_summary": "x"} for i in range(1, 12)]
    outline = build_script_outline(["Hook", "Mechanism", "Evidence", "Takeaway"], ["a", "b"], claims)
    s = write_script(outline, claims, " ".join(c["claim"] for c in claims), "8-10", "mosquitoes", None)
    assert len(s["scenes"]) >= 4 and s["words"] > 200

def test_duration_plan():
    assert plan_for("12-15")["words"] == 2000
    assert estimate_text_seconds("word " * 150) > 50
