from science_studio.research.factcheck import factcheck_script, apply_autofixes

def test_factcheck_flags_hype():
    claims = [{"claim_id": "C001", "claim": "Mosquitoes transmit Plasmodium.", "confidence": "established"}]
    r = factcheck_script("This miracle cure is proven to cure malaria instantly. All scientists agree.", claims, None)
    assert r["status"] in ("review", "fail")
    assert len(r["issues"]) >= 1

def test_autofix():
    fixed = apply_autofixes("It is proven that X. All scientists agree.", {})
    assert "proven that" not in fixed
