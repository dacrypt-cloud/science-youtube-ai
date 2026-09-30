from science_studio.research.engine import clean_text, _relevant
from science_studio.research.planner import interpret_idea
from science_studio.providers.llm_template import TemplateAIProvider


def test_clean_strips_html_and_markers():
    t = clean_text("<h4>ABSTRACT</h4> Mosquitoes <i>bite</i> [S034] humans.")
    assert "<" not in t and "[S034]" not in t and "Mosquitoes" in t


def test_clip_drops_trailing_fragment():
    from science_studio.research.engine import _clip
    # raw provider-style cut mid-sentence, even when short
    t = _clip("First full sentence here. Second sentence cut mid-wo", 1500)
    assert t == "First full sentence here."
    t2 = _clip("Complete sentence one. Complete sentence two.", 1500)
    assert t2 == "Complete sentence one. Complete sentence two."
    # long text clips at sentence boundary
    long = "Word " * 30 + "Sentence one is here. " + "Word " * 400 + "tail fragment xyz"
    assert _clip(long, 200).endswith("here.")


def test_preclean_strips_attribution_tails():
    from science_studio.providers.llm_template import split_sentences
    s = split_sentences("Malaria is transmitted by mosquitoes in tropical regions worldwide. [S018] (Europe PMC, 2026).")
    assert all("S018" not in x and "Europe PMC" not in x for x in s)
    assert any("mosquitoes" in x for x in s)


def test_entities_skip_sentence_case():
    d = interpret_idea("How does a mosquito transmit malaria, and what happens to Plasmodium?")
    assert "How" not in d["entities"]
    assert "Plasmodium" in d["entities"]


def test_relevance_filters_junk_reference():
    ideas = {"mosquito", "malaria", "plasmodium", "transmit"}
    assert not _relevant("How It Is", "A novel about life", ideas, "reference")
    assert _relevant("Plasmodium", "Plasmodium parasites cause malaria transmitted by mosquito", ideas, "reference")
    # scholarly needs >=1 keyword (filters off-topic papers)
    assert _relevant("Malaria drug trial", "patients", ideas, "journal")
    assert not _relevant("Anything", "", ideas, "journal")


def test_word_cap_enforced():
    tpl = TemplateAIProvider()
    ev = " ".join(f"Sentence number {i} about mosquito malaria plasmodium transmission cycle." for i in range(200))
    out = tpl.assemble_script([{"title": f"S{i}", "claim_ids": []} for i in range(6)], ev, 600)
    for sc in out:
        assert len(sc["narration"].split()) <= 135  # 100*1.25 + margin
    total = sum(len(sc["narration"].split()) for sc in out)
    assert total <= 900
