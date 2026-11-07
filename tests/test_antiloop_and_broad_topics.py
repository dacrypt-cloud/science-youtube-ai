"""Regression tests for disambiguation-proof research, broad-topic bridges, and anti-loop scripting."""
from __future__ import annotations
from collections import Counter
import re

from science_studio.providers.llm_template import domain_veto
from science_studio.research.backbone import _is_junk_reference
from science_studio.research.planner import interpret_idea, topic_anchors
from science_studio.story.script import _dedupe_scene_repetitions, build_script_outline, write_script


def test_disambiguation_and_unrelated_biographies_rejected():
    assert _is_junk_reference(
        "Rich",
        "Rich may refer to: Common uses Rich, an entity possessing wealth; Rich County, Utah.",
        idea="How To Become Rich",
    )
    assert _is_junk_reference(
        "Marc Rich",
        "Marc Rich (born Marcell David Reich; December 18, 1934) was a Belgian-American commodities trader.",
        idea="How To Become Rich",
    )
    assert not _is_junk_reference(
        "Wealth",
        "Wealth is the abundance of valuable financial assets or physical possessions which can be converted into a form that can be used for transactions.",
        idea="How To Become Rich",
    )


def test_colloquial_and_crypto_topics_bridge_cleanly_without_domain_veto():
    rich_interp = interpret_idea("How To Become Rich")
    assert "become" not in rich_interp["anchors"]
    assert "wealth" in rich_interp["anchors"]
    assert "Wealth" in rich_interp["backbone_queries"]
    assert domain_veto("Households build wealth through diversified stock market portfolios.", rich_interp["anchors"]) == ""

    crypto_anchors = topic_anchors("Top 10 Most Dangerous Crypto Hacks")
    assert "cryptocurrency" in crypto_anchors
    assert "blockchain" in crypto_anchors
    assert domain_veto("Attackers drained cryptocurrency from the blockchain bridge smart contract.", crypto_anchors) == ""


def test_dedupe_kills_according_imagine_farmer_loop():
    distinct_facts = [
        "Compound returns grow exponentially as reinvested earnings generate further yield.",
        "Household savings rates determine how quickly liquid reserves accumulate.",
        "Diversified equity portfolios reduce idiosyncratic risk across market cycles.",
        "Human capital investments raise lifetime earning capacity across industries.",
        "Tax-advantaged accounts shelter long-term compounding from annual drag.",
        "High-interest consumer debt erodes net worth through reverse compounding.",
        "Broad index funds minimize management fees compared with active trading.",
        "Real estate equity builds gradually through principal amortization.",
        "Emergency cash buffers prevent forced asset sales during downturns.",
        "Long time horizons amplify small differences in annual return rates.",
    ]
    looping = [
        {
            "title": f"Scene {i+1}",
            "narration": (
                "According to this, imagine a farmer tending water bodies on small plots every season. "
                + distinct_facts[i]
            ),
            "claim_ids": ["C001"],
        }
        for i in range(10)
    ]
    cleaned = _dedupe_scene_repetitions(
        looping, anchors=["wealth", "savings", "investment"], is_llm=True, enforce_hygiene=True
    )
    full = " ".join(s["narration"] for s in cleaned)
    assert "according to this" not in full.lower()
    assert full.lower().count("farmer") <= 1
    toks = re.findall(r"[a-z]{4,}", full.lower())
    grams = Counter(" ".join(toks[i:i + 3]) for i in range(len(toks) - 2))
    assert not grams or grams.most_common(1)[0][1] <= 6


def test_write_script_caps_scenes_when_claims_are_sparse():
    claims = [
        {"claim_id": f"C00{i}", "claim": f"Verified mechanism step {i} drives energy storage in cells.",
         "evidence_summary": "cellular energy", "confidence": "established", "source_ids": ["S001"]}
        for i in range(1, 7)
    ]
    beats = ["Hook", "Cause", "Mechanism", "Evidence", "Limits", "Takeaway"]
    outline = build_script_outline(beats, ["energy", "cells"], claims)
    ev = " ".join(c["claim"] for c in claims)
    scr = write_script(outline, claims, ev, "12-15", "How cellular energy storage works", stack=None)
    assert scr["evidence_capped"] is True
    assert len(scr["scenes"]) == 6


def test_dedupe_catches_paraphrased_echo_across_scenes():
    scenes = [
        {
            "title": "Scene 1",
            "narration": (
                "Reinvested dividends allow household savings to compound exponentially across decades. "
                "Automatic payroll deductions remove behavioral friction from monthly saving."
            ),
            "claim_ids": ["C001"],
        },
        {
            "title": "Scene 2",
            "narration": (
                "Household savings compound exponentially over decades through reinvesting dividends. "
                "Low-cost index funds diversify equity exposure across hundreds of companies."
            ),
            "claim_ids": ["C002"],
        },
    ]
    cleaned = _dedupe_scene_repetitions(
        scenes, anchors=["savings", "dividend", "index", "equity"], is_llm=True, enforce_hygiene=True
    )
    assert "reinvesting dividends" not in cleaned[1]["narration"].lower()
    assert "index funds" in cleaned[1]["narration"].lower()


def test_qa_rejects_repeated_narration_loops(tmp_path):
    import json
    from science_studio.video.qa import run_qa

    (tmp_path / "idea.json").write_text(
        json.dumps({"idea": "How To Become Rich", "duration": "8-10"}), encoding="utf-8"
    )
    repeated = "Compound returns grow household wealth exponentially when dividends stay invested over decades."
    dirty_sb = [
        {"scene_id": f"scene_0{i}", "narration": repeated, "claim_ids": ["C001"]}
        for i in range(1, 5)
    ]
    narr = [{"scene_id": s["scene_id"], "path": "", "duration_s": 30, "provider": "edge-tts"} for s in dirty_sb]
    claims = [{"claim_id": "C001", "claim": repeated, "source_ids": ["S001"]}]
    rep_dirty = run_qa("t", tmp_path, dirty_sb, [], narr, tmp_path / "nope.mp4", {}, claims)
    by_dirty = {c["name"]: c for c in rep_dirty["checks"]}
    assert not by_dirty["no_narration_repetition"]["ok"]

    clean_sb = [
        {"scene_id": "scene_01", "narration": "Compound returns grow household wealth when dividends stay invested.", "claim_ids": ["C001"]},
        {"scene_id": "scene_02", "narration": "Broad index funds reduce management fees across equity markets.", "claim_ids": ["C001"]},
    ]
    narr_clean = [{"scene_id": s["scene_id"], "path": "", "duration_s": 30, "provider": "edge-tts"} for s in clean_sb]
    rep_clean = run_qa("t", tmp_path, clean_sb, [], narr_clean, tmp_path / "nope.mp4", {}, claims)
    by_clean = {c["name"]: c for c in rep_clean["checks"]}
    assert by_clean["no_narration_repetition"]["ok"], by_clean["no_narration_repetition"]

