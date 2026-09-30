from science_studio.models import ProjectState, STATE_ORDER, Claim, Source, Scene

def test_states():
    assert STATE_ORDER[0] == ProjectState.IDEA
    assert STATE_ORDER[-1] == ProjectState.READY

def test_claim_traceability():
    c = Claim(claim_id="C001", claim="x", source_ids=["S001"])
    d = c.to_dict()
    assert d["claim_id"] == "C001" and d["source_ids"] == ["S001"]
