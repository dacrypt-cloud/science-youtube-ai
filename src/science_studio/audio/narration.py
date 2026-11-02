"""Scene-by-scene narration with provider fallback chain. Real durations + word timings recorded."""
from __future__ import annotations
import json
from pathlib import Path


def synthesize_scenes(storyboard: list[dict], stack, narr_dir: Path, progress_cb=None) -> list[dict]:
    from ..research.engine import clean_text
    narr_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    chain = stack.speech_chain
    for i, sc in enumerate(storyboard):
        if progress_cb:
            progress_cb(i + 1, len(storyboard), sc["scene_id"])
        text = clean_text(sc["narration"])
        sc["narration"] = text  # keep subtitles consistent with spoken audio
        out = narr_dir / f"{sc['scene_id']}.mp3"
        sidecar = narr_dir / f"{sc['scene_id']}.txt"
        words_sidecar = narr_dir / f"{sc['scene_id']}.words.json"
        # resume: reuse cached audio ONLY if text unchanged AND word timings exist
        if (out.exists() and out.stat().st_size > 1000
                and sidecar.exists() and sidecar.read_text(encoding="utf-8") == text
                and words_sidecar.exists()):
            from ..providers.tts_edge import _audio_duration
            cached_words = []
            try:
                cached_words = json.loads(words_sidecar.read_text(encoding="utf-8"))
            except Exception:
                cached_words = []
            results.append({"scene_id": sc["scene_id"], "path": str(out),
                            "duration_s": _audio_duration(out, text),
                            "voice": "cached", "provider": "cached",
                            "words": cached_words})
            continue
        errors = []
        done = None
        for p in chain:
            try:
                st = p.status()
                if not st.available:
                    continue
                r = p.synthesize(text, out)
                done = r
                break
            except Exception as e:
                errors.append(f"{p.name}: {str(e)[:150]}")
        if not done:
            raise RuntimeError(f"TTS failed for {sc['scene_id']}: {' | '.join(errors)}")
        try:
            sidecar.write_text(text, encoding="utf-8")
            words_sidecar.write_text(json.dumps(done.get("words") or []), encoding="utf-8")
        except Exception:
            pass
        results.append({"scene_id": sc["scene_id"], **done})
    return results
