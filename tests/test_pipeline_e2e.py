"""End-to-end pipeline test with stub network (offline-safe, fast).

Uses template AI + silent TTS + tiny render to verify stage wiring.
Real-network e2e is scripts/run_malaria_test.py (manual, documented).
"""
import json

def test_pipeline_offline(monkeypatch, tmp_path):
    monkeypatch.setenv("PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("VIDEO_WIDTH", "640")
    monkeypatch.setenv("VIDEO_HEIGHT", "360")
    monkeypatch.setenv("VIDEO_FPS", "24")
    from science_studio.config import get_settings
    get_settings(reload=True)
    from science_studio import storage
    from science_studio.providers.registry import build_providers
    from science_studio.research.planner import plan_research

    # stub searchers to avoid network
    stack = build_providers()
    class Stub:
        name = "stub"
        def status(self):
            from science_studio.providers.base import ProviderStatus
            return ProviderStatus("stub", True, True, "test")
        def search(self, q, limit=4):
            return [{"title": f"Result for {q[:30]}", "url": f"https://example.com/{abs(hash(q))%99999}",
                     "snippet": "Mosquitoes transmit Plasmodium parasites. Inside the midgut the ookinete forms an oocyst which releases sporozoites.",
                     "source_type": "reference", "publisher": "Test", "reliability": 3}]
    stack.searchers = [Stub()]
    from science_studio.providers.tts_silent import SilentSpeechProvider
    stack.speech_chain = [SilentSpeechProvider()]
    stack.images = []
    stack.videos = []

    plan = plan_research("How do mosquitoes transmit malaria?", duration="8-10", stack=stack)
    assert plan["research_questions"]
    from science_studio.research.engine import run_research
    res = run_research(plan, stack)
    assert len(res["sources"]) > 0 and len(res["claims"]) > 0
