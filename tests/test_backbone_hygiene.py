"""Backbone, hygiene, calibration, and visual-track gating (offline)."""
import sys
sys.path.insert(0, "src")


def test_backbone_picks_matching_article(monkeypatch):
    from science_studio.research import backbone
    import science_studio.research.backbone as bb

    class FakeWiki:
        def search(self, q, limit=3):
            if q == "lightning":
                return [{"title": "Lightning", "url": "https://en.wikipedia.org/wiki/Lightning"}]
            return [{"title": "Unrelated Album", "url": "https://en.wikipedia.org/wiki/Unrelated"}]

    import science_studio.research.fetcher as fmod
    monkeypatch.setattr(fmod, "fetch_wikipedia", lambda url: ("Lightning is an electrostatic discharge. " * 100, "wikipedia-fulltext"))
    import science_studio.providers.search_wikipedia as wmod
    monkeypatch.setattr(wmod, "WikipediaSearchProvider", FakeWiki)
    sources, texts = backbone.fetch_topic_backbone(["lightning", "zzzzqqqq"], max_articles=2)
    assert len(sources) == 1
    assert sources[0]["source_type"] == "reference"
    assert sources[0]["fetch_method"] == "wikipedia-fulltext"
    assert len(texts[sources[0]["url"]]) > 500


def test_backbone_skips_short_articles(monkeypatch):
    from science_studio.research import backbone
    import science_studio.research.backbone as bb

    class FakeWiki:
        def search(self, q, limit=3):
            return [{"title": "Lightning", "url": "https://en.wikipedia.org/wiki/Lightning"}]

    import science_studio.research.fetcher as fmod
    monkeypatch.setattr(fmod, "fetch_wikipedia", lambda url: ("stub", "wikipedia-fulltext"))
    import science_studio.providers.search_wikipedia as wmod
    monkeypatch.setattr(wmod, "WikipediaSearchProvider", FakeWiki)
    sources, texts = backbone.fetch_topic_backbone(["lightning"])
    assert sources == [] and texts == {}


def test_sentence_hygiene():
    from science_studio.providers.llm_template import is_clean_sentence, split_sentences
    anchors = ["lightning", "thundercloud", "charge"]
    good = "Collisions between graupel and ice crystals separate electric charge inside thunderclouds."
    assert is_clean_sentence(good, anchors)
    assert not is_clean_sentence("Thank you for visiting nature.com, we are displaying the site without styles for lightning.", anchors)
    assert not is_clean_sentence("18 implemented an explicit lightning forecast module with many parameters inside.", anchors)
    assert not is_clean_sentence("MOGA is combined with local search for globally efficient routes.", anchors)  # off-topic
    assert not is_clean_sentence("Too short.", anchors)
    sents = split_sentences(good + " " + "MOGA routes data efficiently across networks every day.", anchors=anchors)
    assert len(sents) == 1 and "graupel" in sents[0]


def test_calibration():
    from science_studio.research.engine import _calibrate_confidence
    claims = [
        {"claim_id": "C001", "claim": "Graupel collisions separate thunderstorm electric charge efficiently.",
         "source_ids": ["S001"], "confidence": "limited_evidence"},
        {"claim_id": "C002", "claim": "Thunderstorm graupel charge separation drives lightning electrification processes.",
         "source_ids": ["S002"], "confidence": "limited_evidence"},
        {"claim_id": "C003", "claim": "Researchers still debate exactly how lightning initiates inside thunderclouds.",
         "source_ids": ["S003"], "confidence": "limited_evidence"},
        {"claim_id": "C004", "claim": "Cosmic rays may sometimes trigger lightning initiation events in storms.",
         "source_ids": ["S004"], "confidence": "limited_evidence"},
    ]
    sources = [
        {"source_id": "S001", "source_type": "reference"},
        {"source_id": "S002", "source_type": "journal"},
        {"source_id": "S003", "source_type": "journal"},
        {"source_id": "S004", "source_type": "preprint"},
    ]
    _calibrate_confidence(claims, sources)
    by_id = {c["claim_id"]: c["confidence"] for c in claims}
    assert by_id["C001"] == "strong_evidence" and by_id["C002"] == "strong_evidence"
    assert by_id["C003"] == "active_debate"
    assert by_id["C004"] == "plausible_hypothesis"


def test_visual_track_gating():
    from science_studio.visuals.storyboard import build_storyboard, _diagram_for, _query_for
    hook = "A bolt splits the night sky over the storm and thunder rolls across the landscape."
    assert _diagram_for(hook) == ""  # observed -> real photo
    mech = "Collisions between graupel and ice crystals transfer electric charge step by step."
    assert _diagram_for(mech) == "process"  # mechanism -> diagram
    board = build_storyboard(
        [{"title": "Hook", "narration": hook, "claim_ids": []},
         {"title": "Mechanism", "narration": mech, "claim_ids": []}],
        "How does a lightning bolt form?", None)
    assert board[0]["diagram"] == "" and board[0]["visual_query_fallback"]
    assert board[1]["diagram"] == "process"
    q, fb = _query_for("Hook", hook, "How does a lightning bolt form inside a thundercloud?")
    assert "actually" not in q and len(q.split()) <= 5
    assert fb and "lightning" in fb


def test_anchors_extracted():
    from science_studio.research.planner import interpret_idea
    d = interpret_idea("How does a lightning bolt form, and what actually happens inside a thundercloud before lightning strikes?")
    assert "lightning" in d["anchors"] and "thundercloud" in d["anchors"]
    assert "actually" not in d["anchors"] and "inside" not in d["anchors"]
