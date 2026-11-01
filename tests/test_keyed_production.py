"""Regression tests for keyed production (Groq/OpenRouter + Pexels/Pixabay)
and non-weather science topics (biology, medicine, physiology)."""
from __future__ import annotations
import json
import subprocess
import wave
import struct
import math
from pathlib import Path
import pytest


def test_extract_json_array_with_think_and_stray_brackets():
    from science_studio.providers.openai_compat import extract_json_array
    raw = (
        "<think>Let me check claims [C001] and [S002] for [12 scenes].</think>\n"
        "Here is the output for [batch 1]:\n"
        "```json\n"
        '[{"title": "Hook", "narration": "A single cell divides."}]\n'
        "```\n"
        "Note: see [appendix]."
    )
    arr = extract_json_array(raw)
    assert len(arr) == 1 and arr[0]["title"] == "Hook"


def test_anchor_stop_excludes_work_and_works():
    from science_studio.research.planner import topic_anchors
    assert topic_anchors("How do pregnancy works?") == ["pregnancy"]
    assert "explain" not in topic_anchors("Explain how vaccines train immunity")


def test_batched_llm_scripting_and_honest_error_logging():
    import types
    from science_studio.story.script import build_script_outline, write_script
    from science_studio.providers.base import ProviderStatus

    calls = []

    class FakeGroq:
        name = "groq"

        def status(self):
            return ProviderStatus("groq", True, True, "free")

        def generate(self, prompt, *, system="", max_tokens=2000, temperature=0.4):
            calls.append({"prompt": prompt, "max_tokens": max_tokens})
            import re
            nums = re.findall(r"^\d+\.\s+(.+)$", prompt, flags=re.M)
            words = ("Fertilized cells divide rapidly inside the fallopian tube "
                     "before reaching the receptive uterine lining where chemical "
                     "signals guide implantation carefully. ") * 2
            return json.dumps([
                {"title": t, "narration": f"{words}[C001]"} for t in nums
            ])

    claims = [
        {"claim_id": f"C{i:03d}", "claim": f"Embryo development fact {i} during gestation.",
         "confidence": "established", "evidence_summary": "clinical"}
        for i in range(1, 16)
    ]
    outline = build_script_outline(
        ["Hook", "Fertilization", "Cleavage", "Implantation", "Placenta", "Takeaway"],
        ["ovulation", "implantation"], claims,
    )
    stack = types.SimpleNamespace(ai_chain=[FakeGroq()])
    out = write_script(outline, claims, "evidence", "12-15", "How does pregnancy work?", stack)
    assert out["provider"] == "groq"
    assert out["llm_error"] == ""
    assert len(calls) >= 2 and all(c["max_tokens"] <= 3500 for c in calls)
    assert len(out["scenes"]) >= 12
    assert all("[C001]" not in s["narration"] for s in out["scenes"])

    class BrokenGroq:
        name = "groq"

        def status(self):
            return ProviderStatus("groq", True, True, "free")

        def generate(self, prompt, **kw):
            raise RuntimeError("HTTP 429 rate limit")

    out_fb = write_script(outline, claims, " ".join(c["claim"] for c in claims),
                          "8-10", "How does pregnancy work?",
                          types.SimpleNamespace(ai_chain=[BrokenGroq()]))
    assert out_fb["provider"] == "template-fallback"
    assert "429" in out_fb["llm_error"]


def test_storyboard_respects_empty_llm_diagram_and_caps_diagrams():
    import types
    from science_studio.visuals.storyboard import build_storyboard
    from science_studio.providers.base import ProviderStatus

    scenes = [
        {"title": f"Stage {i}",
         "narration": "Cells develop and form layers inside the organ pathway process.",
         "claim_ids": ["C001"]}
        for i in range(12)
    ]
    # Heuristic-only: 12 mechanism-heavy scenes must still leave >=50% for B-roll, incl. scene 0
    board_h = build_storyboard(scenes, "How does pregnancy work?", None)
    assert board_h[0]["diagram"] == ""
    assert sum(1 for b in board_h if b["diagram"] == "") >= 6

    # LLM visual director explicitly marks scenes as "" or "b-roll": must NOT be overridden
    class FakeDir:
        name = "groq"

        def status(self):
            return ProviderStatus("groq", True, True, "free")

        def generate(self, prompt, **kw):
            return json.dumps([
                {"visual_objective": "Show clinic", "visual_query": "mother ultrasound",
                 "diagram": "" if i % 2 == 0 else "b-roll", "onscreen_text": "Week 1"}
                for i in range(4)
            ])

    board_llm = build_storyboard(scenes[:4], "How does pregnancy work?",
                                 types.SimpleNamespace(ai_chain=[FakeDir()]))
    assert all(b["diagram"] == "" for b in board_llm)


def test_qa_and_conceptual_accept_pixabay_broll_and_llm_analogies(tmp_path):
    from science_studio.video.qa import run_qa
    from science_studio.video.conceptual import visuals_only
    from science_studio.research.planner import topic_anchors
    from science_studio.providers.llm_template import stem

    (tmp_path / "idea.json").write_text(json.dumps({
        "idea": "How do pregnancy works", "duration": "8-10",
    }), encoding="utf-8")
    (tmp_path / "script").mkdir(parents=True)
    (tmp_path / "script" / "script.json").write_text(json.dumps({
        "provider": "groq",
    }), encoding="utf-8")
    (tmp_path / "production" / "diagrams").mkdir(parents=True)
    srt = tmp_path / "s.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:04,000\nLife begins quietly.\n", encoding="utf-8")

    narration_1 = (
        "Within six days, the blastocyst implants deeply inside the uterine lining "
        "and exchanges chemical signals with maternal cells."
    )
    narration_2 = (
        "Imagine a smart lock that updates its own combination the moment the right "
        "key turns so nothing else can enter."
    )
    sb = [
        {"scene_id": "scene_01", "title": "Implantation", "narration": narration_1, "claim_ids": ["C001"]},
        {"scene_id": "scene_02", "title": "Zona reaction", "narration": narration_2, "claim_ids": ["C001"]},
    ]
    assets = [
        {"asset_id": "A001", "scene_id": "scene_01", "primary": True,
         "kind": "video", "source": "pixabay-video", "path": "",
         "description": "ultrasound, hospital, mother, clinic"},
        {"asset_id": "A002", "scene_id": "scene_02", "primary": True,
         "kind": "image", "source": "pixabay-image", "path": "",
         "description": "newborn, baby, hands, family"},
    ]
    narr = [{"scene_id": s["scene_id"], "path": "", "duration_s": 45, "provider": "edge-tts"} for s in sb]
    claims = [{"claim_id": "C001", "claim": narration_1, "source_ids": ["S001"]}]

    anch = {stem(a) for a in topic_anchors("How do pregnancy works")}
    assert visuals_only(sb, assets, anch) == {}

    rep = run_qa("p", tmp_path, sb, assets, narr, tmp_path / "nope.mp4",
                 {"srt": str(srt), "cues": 1}, claims)
    by_name = {c["name"]: c for c in rep["checks"]}
    assert by_name["narration_hygiene"]["ok"], by_name["narration_hygiene"]
    assert by_name["image_relevance"]["ok"], by_name["image_relevance"]
    assert by_name["conceptual_alignment"]["ok"], by_name["conceptual_alignment"]

    # Vetoes STILL catch bad Pixabay concert clips and paper-discourse LLM leaks
    bad_assets = [{"asset_id": "A003", "scene_id": "scene_01", "primary": True,
                   "kind": "video", "source": "pixabay-video", "path": "",
                   "description": "rock concert live music band performing on stage"}]
    assert "scene_01" in visuals_only(sb[:1], bad_assets, anch)

    bad_sb = [{"scene_id": "scene_01", "title": "Leak",
               "narration": "In this paper we present our findings on uterine implantation.",
               "claim_ids": ["C001"]}]
    rep_bad = run_qa("p", tmp_path, bad_sb, assets[:1], narr[:1], tmp_path / "nope.mp4",
                     {"srt": str(srt), "cues": 1}, claims)
    by_bad = {c["name"]: c for c in rep_bad["checks"]}
    assert not by_bad["narration_hygiene"]["ok"]


def test_broll_video_render_maps_narration_audio_and_loops_short_clip(tmp_path):
    from science_studio.providers.render_ffmpeg import FFmpegRenderer, ffmpeg_exe
    r = FFmpegRenderer()
    if not r.status().available:
        pytest.skip("no ffmpeg")
    exe = ffmpeg_exe()

    # 1.0s stock video WITH a silent stereo audio track (0:a) — previously beat mono TTS!
    stock_mp4 = tmp_path / "stock.mp4"
    subprocess.run([
        exe, "-y",
        "-f", "lavfi", "-i", "color=c=navy:s=320x180:r=24:d=1.0",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=1.0",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest",
        str(stock_mp4),
    ], check=True, capture_output=True, timeout=60)

    # 3.2s mono narration WAV with a clear 440Hz tone (non-silent!)
    narr_wav = tmp_path / "narr.wav"
    sr = 22050
    n_samples = int(sr * 3.2)
    with wave.open(str(narr_wav), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = b"".join(
            struct.pack("<h", int(18000 * math.sin(2 * math.pi * 440 * k / sr)))
            for k in range(n_samples)
        )
        w.writeframes(frames)

    out_mp4 = tmp_path / "rendered.mp4"
    res = r.render({
        "width": 320, "height": 180, "fps": 24,
        "scenes": [{
            "title": "B-roll test", "onscreen_text": "",
            "image": "", "video": str(stock_mp4),
            "audio": str(narr_wav), "duration_s": 3.2,
        }],
        "music": "",
    }, out_mp4)
    assert Path(res["path"]).exists()

    # Verify duration looped to ~3.2s (not cut at 1.0s) AND audio is audible (narr_wav mapped, not 0:a silence)
    from science_studio.video.qa import _probe_duration
    dur = _probe_duration(out_mp4)
    assert 2.9 <= dur <= 3.6, f"expected ~3.2s looped video, got {dur}s"

    pcm = subprocess.run([
        exe, "-v", "error", "-i", str(out_mp4),
        "-f", "s16le", "-ac", "1", "-ar", "8000", "-",
    ], check=True, capture_output=True, timeout=30).stdout
    samples = struct.unpack(f"<{len(pcm)//2}h", pcm)
    peak = max((abs(x) for x in samples), default=0)
    assert peak > 5000, f"narration audio was muted by stock video track (peak={peak})"


def test_ambience_bed_is_topic_aware(tmp_path):
    from science_studio.audio.sfx import is_storm_topic, ensure_ambience_bed
    from science_studio.audio.music import _ffmpeg
    assert is_storm_topic("How does a lightning bolt form inside a thundercloud?")
    assert not is_storm_topic("How do pregnancy works?")
    assert not is_storm_topic("How do vaccines train the immune system?")
    if _ffmpeg() is None:
        pytest.skip("no ffmpeg")
    bed_bio = ensure_ambience_bed(tmp_path / "bio", 20, idea="How do pregnancy works?")
    assert bed_bio["path"] and "thunder" not in bed_bio["source"]
    assert "studio-air" in bed_bio["source"]


def test_llm_extract_claims_sanitizes_source_ids():
    import types
    from science_studio.research.engine import _extract_claims
    from science_studio.providers.base import ProviderStatus

    class FakeLLM:
        name = "groq"

        def status(self):
            return ProviderStatus("groq", True, True, "free")

        def generate(self, prompt, **kw):
            items = [
                {"claim": f"Verified biological mechanism claim number {i} in pregnancy.",
                 "evidence_summary": "clinical", "confidence": "established",
                 "source_ids": ["[S001]", "S999"]}
                for i in range(10)
            ] + [
                {"claim": "Hallucinated claim with no valid source.",
                 "evidence_summary": "none", "confidence": "established",
                 "source_ids": ["S888"]}
            ]
            return json.dumps(items)

    sources = [{"source_id": "S001", "title": "Pregnancy", "url": "https://example.org/1"}]
    claims = _extract_claims("Some research notes [S001] " * 30, sources,
                             types.SimpleNamespace(ai_chain=[FakeLLM()]))
    assert len(claims) == 10
    assert all(c["source_ids"] == ["S001"] for c in claims)
