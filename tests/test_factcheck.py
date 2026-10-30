"""Factcheck number verification: claims blob + evidence blob."""

def test_numbers_verified_against_claims_or_evidence():
    from science_studio.research.factcheck import factcheck_script
    sent = "The air around the lightning flash rapidly heats to temperatures of about 30,000 °C in storms."
    claims = [{"claim": "Lightning is hot.", "claim_id": "C001"}]
    # in claims only
    r = factcheck_script(sent, [{"claim": sent, "claim_id": "C001"}])
    assert not [i for i in r["issues"] if i["type"] == "number_unverified"], r["issues"]
    # in evidence only (narrated from a non-claim evidence sentence)
    r = factcheck_script(sent, claims, evidence_text="Background. " + sent + " More context here.")
    assert not [i for i in r["issues"] if i["type"] == "number_unverified"], r["issues"]
    # in neither -> flagged
    r = factcheck_script(sent, claims, evidence_text="Lightning is a discharge.")
    assert [i for i in r["issues"] if i["type"] == "number_unverified"], r
