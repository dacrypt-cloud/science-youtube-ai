"""Script assembly: claim-aware scene ranking + traceability map (offline)."""
import sys
sys.path.insert(0, "src")
from science_studio.providers.llm_template import TemplateAIProvider
from science_studio.story.script import build_traceability


EVIDENCE = (
    "Thunderclouds develop powerful updrafts that lift warm moist air high into the atmosphere. "
    "Supercooled water droplets freeze onto graupel pellets in the mixed-phase region of the cloud. "
    "Collisions between graupel and small ice crystals transfer electric charge between particles. "
    "The upper cloud becomes positively charged while the lower cloud accumulates negative charge. "
    "A stepped leader propagates downward from the cloud in discrete luminous steps. "
    "The return stroke races upward and heats the channel hot enough to glow brilliantly. "
    "Thunder is the shock wave from air explosively heated by the lightning channel. "
    "Why does lightning zigzag across the sky instead of striking in a straight line? "
    "Researchers still debate exactly how lightning initiates inside thunderclouds."
)

CLAIMS = [
    {"claim_id": "C001", "claim": "Collisions between graupel and ice crystals transfer charge.",
     "confidence": "established", "source_ids": ["S001"], "status": "supported"},
    {"claim_id": "C002", "claim": "The return stroke heats the channel and causes thunder.",
     "confidence": "strong_evidence", "source_ids": ["S002"], "status": "supported"},
    {"claim_id": "C003", "claim": "Lightning initiation is still debated by researchers.",
     "confidence": "active_debate", "source_ids": ["S003"], "status": "supported"},
]


def test_claim_ids_resolved_to_text():
    """Regression: scene claim_ids must rank by claim TEXT, not the ID string."""
    tpl = TemplateAIProvider()
    outline = [{"title": "Charge separation", "claim_ids": ["C001"]},
               {"title": "Return stroke", "claim_ids": ["C002"]}]
    scenes = tpl.assemble_script(outline, EVIDENCE, 300, claims=CLAIMS)
    assert "graupel" in scenes[0]["narration"].lower() or "charge" in scenes[0]["narration"].lower()
    assert "return stroke" in scenes[1]["narration"].lower() or "thunder" in scenes[1]["narration"].lower()
    # titles are on-screen text, never spoken
    assert "charge separation." not in scenes[0]["narration"].lower()[:40]


def test_no_sentence_repeated_across_scenes():
    tpl = TemplateAIProvider()
    outline = [{"title": f"S{i}", "claim_ids": ["C001"]} for i in range(3)]
    scenes = tpl.assemble_script(outline, EVIDENCE, 180, claims=CLAIMS)
    from science_studio.providers.llm_template import split_sentences
    seen: set[str] = set()
    for s in scenes:
        for sent in split_sentences(s["narration"]):
            assert sent not in seen, f"repeated: {sent[:60]}"
            seen.add(sent)


def test_traceability_map():
    scenes = [{"narration": "Collisions between graupel and ice crystals transfer electric charge."},
              {"narration": "Thunder is the shock wave from the heated lightning channel."}]
    rows = build_traceability(scenes, CLAIMS)
    by_id = {r["claim_id"]: r for r in rows}
    assert by_id["C001"]["traceable"] and by_id["C001"]["script_scenes"] == ["scene_01"]
    assert by_id["C002"]["traceable"]


def test_subtitle_wrapping():
    from science_studio.audio.subtitles import wrap_cues
    cues = wrap_cues("Thunderclouds develop powerful updrafts that lift warm moist air high into the freezing atmosphere above.")
    for cue in cues:
        for line in cue.split("\n"):
            assert len(line) <= 42, line
    assert cues and all(c.strip() for c in cues)
