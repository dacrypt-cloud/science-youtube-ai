from science_studio.providers.registry import build_providers

def test_registry_builds():
    s = build_providers()
    r = s.status_report()
    assert "ai_chain" in r and len(s.ai_chain) >= 1
    assert len(s.searchers) >= 3
    assert s.renderer is not None
    # template fallback always available
    assert any(p.name == "template-fallback" for p in s.ai_chain)

def test_free_only_default():
    from science_studio.config import get_settings
    assert get_settings().free_only in (True, False)
