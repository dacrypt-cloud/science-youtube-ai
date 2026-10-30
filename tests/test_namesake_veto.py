"""Regression tests for the namesake veto in visuals/assets._img_relevant.

Grounded in real Wikimedia Commons metadata probed 2026-10-03: the band
"Lightning Bolt" shares its exact name with the lightning phenomenon, and
three of its concert photos passed the old title-only gate into run #3
(scenes 4/8/10). The veto must reject all three while keeping real
lightning photos — including bare-titled ones saved by their categories.
"""
from science_studio.visuals.assets import _img_relevant
from science_studio.research.planner import topic_anchors
from science_studio.providers.llm_template import stem

ANCH = {stem(a) for a in topic_anchors("How does a lightning bolt form inside a thundercloud?")}

BAND_BARCELONA = {
    "title": "File:Lightning Bolt, 2008, Barcelona.jpg",
    "description": "za + lightning bolt 2008_11_21 KGB, Barcelona",
    "categories": ["Category:CC-BY-SA-2.0", "Category:FlickreviewR",
                   "Category:Lightning Bolt"],
}
BAND_HERMANN = {
    "title": "File:Lightning Bolt, at Sons of Hermann Hall.jpg",
    "description": "Sons of Hermann Hall, Dallas TX August 28, 2012",
    "categories": ["Category:CC-BY-2.0", "Category:FlickreviewR",
                   "Category:Lightning Bolt",
                   "Category:Sons of Hermann Hall (Dallas)"],
}
BAND_DUO = {
    "title": "File:Lightning Bolt.jpg",
    "description": "Noise Rock duo Lightning Bolt",
    "categories": ["Category:Lightning Bolt",
                   "Category:Self-published work"],
}
REAL_BARE = {
    # run #3 scene_01 primary (good): bare title, rich categories
    "title": "File:Lightning 14.07.2009 20-42-33.JPG",
    "description": "Lightning over Schaffhausen and Kohlfirst, photographed",
    "categories": ["Category:Cloud-to-ground lightning in Switzerland",
                   "Category:Night in Schaffhausen",
                   "Category:Switzerland photographs taken on 2009-07-14"],
}
REAL_NOCATS = {
    # real photo, NO categories at all: description must save it
    "title": "File:A Vintage Lightning Storm at Kitt Peak.jpg",
    "description": "The skies over Kitt Peak National Observatory are clear",
    "categories": [],
}
REAL_CITY = {
    "title": "File:Las Vegas Lightning Storm.jpg",
    "description": "Taken from Henderson, Nevada, looking toward the strip",
    "categories": ["Category:Cloud-to-ground lightning in the United States",
                   "Category:Dark skies in the United States",
                   "Category:Night in Las Vegas", "Category:Rain in Nevada"],
}


def test_band_concert_photos_rejected():
    assert _img_relevant(BAND_BARCELONA, ANCH) is False
    assert _img_relevant(BAND_HERMANN, ANCH) is False
    assert _img_relevant(BAND_DUO, ANCH) is False


def test_real_lightning_photos_kept():
    assert _img_relevant(REAL_BARE, ANCH) is True
    assert _img_relevant(REAL_NOCATS, ANCH) is True
    assert _img_relevant(REAL_CITY, ANCH) is True


def test_toward_does_not_trigger_tour_marker():
    # "tour" is boundary-matched: "looking toward the strip" is safe.
    assert "tour" in REAL_CITY["description"].lower().replace("toward", "tour")
    assert _img_relevant(REAL_CITY, ANCH) is True


def test_engineering_band_phrase_safe():
    im = {"title": "500kV line lightning performance, C-band radar",
          "description": "Storm clouds over the switchyard at night",
          "categories": ["Category:Lightning"] }
    assert _img_relevant(im, ANCH) is True


def test_sports_subject_category_rejected():
    im = {"title": "Lightning delay at the stadium",
          "description": "Storm over the field during a match",
          "categories": ["Category:Soccer", "Category:Stadium"]}
    assert _img_relevant(im, ANCH) is False


def test_background_sports_mention_safe():
    # "tennis courts" in prose is a background detail, not the subject.
    im = {"title": "Lightning over the tennis courts",
          "description": "Night storm photographed from the clubhouse",
          "categories": ["Category:Lightning", "Category:Night"]}
    assert _img_relevant(im, ANCH) is True


def test_entertainment_topic_skips_veto():
    band_anchors = {stem(w) for w in
                    ["lightning", "bolt", "band", "music", "concert"]}
    assert _img_relevant(BAND_DUO, band_anchors) is True
