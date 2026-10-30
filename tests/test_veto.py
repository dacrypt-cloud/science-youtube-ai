"""Discourse-domain drift veto (generic, question-gated)."""
import sys
sys.path.insert(0, "src")
from science_studio.providers.llm_template import domain_veto, is_clean_sentence

ANCHORS = ["lightning", "bolt", "thundercloud", "strikes"]


def test_vetoes_alien_discourse():
    assert domain_veto("Lightning strikes on commercial aircraft require radome testing.", ANCHORS) == "aviation"
    assert domain_veto("Lightning detection on Venus uses spacecraft and orbiters.", ANCHORS) == "space"
    assert domain_veto("Undergraduate students watched a video about thunder and lightning.", ANCHORS) == "education"
    assert domain_veto("The Lightning Search Algorithm routes blockchain transactions.", ANCHORS) == "finance"
    assert domain_veto("Usain Bolt won Olympics gold and became a medalist champion.", ANCHORS) == "sports"


def test_no_veto_for_on_topic():
    assert domain_veto("Lightning is an electrostatic discharge inside thunderclouds.", ANCHORS) == ""
    assert domain_veto("The marsh exhales mist at dawn near the river.", ANCHORS) == ""  # no 'mars' substring veto
    assert domain_veto("Thunder follows the lightning flash within seconds.", ANCHORS) == ""


def test_question_domain_disables_veto():
    assert domain_veto("Aircraft wings flex during flight through storms.", ["aircraft", "wings", "flight"]) == ""
    assert domain_veto("Venus lightning differs from Earth lightning.", ["venus", "lightning", "planet"]) == ""


def test_hygiene_applies_veto():
    bad = "Lightning Strikes on Commercial Aircraft: How the Airlines Are Coping with radome damage today."
    assert not is_clean_sentence(bad, ANCHORS)
    good = "A stepped leader propagates downward from the thundercloud in discrete luminous steps."
    assert is_clean_sentence(good, ANCHORS)


def test_paper_discourse_and_fragments_rejected():
    from science_studio.providers.llm_template import split_sentences
    assert not is_clean_sentence(
        "Here we present the first demonstration that filaments can guide lightning discharges.", ANCHORS)
    assert not is_clean_sentence(
        "Lightning Parameters for Engineering Applications.", ANCHORS)
    assert not is_clean_sentence(
        "Almost all of the largest impulse charge moments (greater than experts thought for lightning", ANCHORS)
    assert not is_clean_sentence("DOMITIAN'S LIGHTNING BOLTS AND CLOSE SHAVES IN PLINY.", ANCHORS)
    assert is_clean_sentence(
        "Most CG lightning is negative, meaning that a negative charge is transferred downwards.", ANCHORS)


def test_verb_lexicon_rejects_titles_keeps_sentences():
    from science_studio.providers.llm_template import is_clean_sentence
    anchors = ["lightning", "bolt", "thundercloud", "strikes"]
    # Paper titles: plural nouns must NOT pass as verbs.
    assert not is_clean_sentence(
        "Nowcasting lightning occurrence from commonly available meteorological parameters using machine learning techniques.", anchors)
    assert not is_clean_sentence(
        "Physical mechanism of initial breakdown pulses and narrow bipolar events in lightning discharges.", anchors)
    assert not is_clean_sentence(
        "Hybrid AI-enhanced lightning flash prediction in the medium-range forecast horizon "
        "A physics-guided machine learning framework for enhancing dust storm visibility "
        "prediction in arid and semi-arid regions for lightning.", anchors)
    # Real sentences with finite verbs survive.
    assert is_clean_sentence(
        "Lightning causes thunder, a sound from the shock wave in heated gases.", anchors)
    assert is_clean_sentence(
        "The air around the lightning flash rapidly heats to temperatures of about 30000C in storms.", anchors)
    assert is_clean_sentence(
        "Following the lightning, the regions become partially or wholly electrically neutralized.", anchors)


def test_citation_debris_salvaged_and_see_refs_stripped():
    from science_studio.providers.llm_template import split_sentences
    anchors = ["lightning", "bolt", "thundercloud", "strikes"]
    out = split_sentences(
        "Storms build charge over long intervals. 5 , 6 Lightning is also a major cause of damage to wind turbines today. "
        "(see: Some Paper Title Here) More lightning text about strikes and bolts in the storm.", anchors)
    assert any("wind turbines" in s and not s[0].isdigit() for s in out), out
    assert not any("see:" in s for s in out), out


def test_image_relevance_gate():
    from science_studio.visuals.assets import _img_relevant
    anchors = {"lightn", "bolt", "thundercloud", "strike"}
    assert not _img_relevant({"title": "File:Ic443 nf c shorgb nebula"}, anchors)
    assert not _img_relevant({"title": "Mithraeum of Felicissimus 02"}, anchors)
    assert _img_relevant({"title": "File:Lightning bolt over the city"}, anchors)


def test_noun_chain_and_hyphen_verbs_rejected():
    from science_studio.providers.llm_template import is_clean_sentence
    anchors = ["lightning", "bolt", "thundercloud", "strikes"]
    # Ambiguous noun-verbs without syntactic company are title chains.
    assert not is_clean_sentence(
        "Lightning morphology and impulse charge moment change of high peak current negative strokes.", anchors)
    # "cross" inside "cross-correlation" is not a verb.
    assert not is_clean_sentence(
        "Continuous broadband digital interferometry of lightning using a generalized cross-correlation algorithm.", anchors)
    # Real two-verb sentences with auxiliaries survive.
    assert is_clean_sentence(
        "We have analyzed very high frequency lightning mapping observations and remote magnetic field data for storms.", anchors)


def test_header_splice_split_and_paper_markers():
    from science_studio.providers.llm_template import split_sentences, is_clean_sentence
    anchors = ["lightning", "bolt", "thundercloud", "strikes"]
    out = split_sentences(
        "Hybrid AI-enhanced lightning flash prediction in the medium-range forecast horizon "
        "A physics-guided machine learning framework for enhancing dust storm visibility "
        "prediction in arid and semi-arid regions Lightning nowcasting with aerosol-informed "
        "machine learning and satellite-enriched dataset Introduction Lightning is responsible "
        "for human injuries and fatalities and the death of livestock in storms.", anchors)
    assert not any("hybrid ai-enhanced" in s.lower() for s in out), out
    assert any("responsible for human injuries" in s for s in out), out
    assert not is_clean_sentence(
        "The figure shows lightning leaders propagating inside thunderclouds during the flash.", anchors)


def test_headless_lowercase_verbs_rejected():
    from science_studio.providers.llm_template import split_sentences, is_clean_sentence
    anchors = ["lightning", "bolt", "thundercloud", "strikes"]
    out = split_sentences(
        "Storms build charge over land. 3. implemented an explicit electrification module for lightning today. "
        "7. developed an early lightning warning system by integrating radar data for storms.", anchors)
    assert not any("implemented an explicit" in s for s in out), out
    assert not any("developed an early" in s for s in out), out
    assert not is_clean_sentence(
        "implemented an explicit electrification module for lightning today in storms.", anchors)
    # lowercase non-verbs still pass
    assert is_clean_sentence(
        "pH levels rise inside thunderclouds during strong storms with lightning.", anchors)


def test_headless_base_verbs_rejected():
    from science_studio.providers.llm_template import is_clean_sentence
    anchors = ["lightning", "bolt", "thundercloud", "strikes"]
    assert not is_clean_sentence(
        "benefit from the output of lightning nowcasting schemes to give warnings today.", anchors)
    assert not is_clean_sentence(
        "run the lightning model twice daily for forecast storms and bolts.", anchors)
