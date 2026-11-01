"""Pipeline orchestrator — explicit states, resumable, failure-recovering.

IDEA -> RESEARCHING -> RESEARCH_COMPLETE -> OUTLINING -> SCRIPTING ->
FACT_CHECKING -> VISUAL_PLANNING -> ASSET_COLLECTION -> NARRATION ->
RENDERING -> QA -> READY
"""
from __future__ import annotations
import traceback
from pathlib import Path
from .models import ProjectState
from . import storage
from .config import get_settings


def _log(pid: str, msg: str):
    root = storage.project_dir(pid)
    with open(root / "pipeline.log", "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(f"[{pid}] {msg}", flush=True)


def _infer_state_from_artifacts(root: Path) -> str:
    """Furthest stage whose key artifacts exist (for FAILED recovery)."""
    has = lambda *parts: (root.joinpath(*parts)).exists()
    state = ProjectState.IDEA.value
    if has("research", "sources.json") and has("research", "claims.json"):
        state = ProjectState.RESEARCH_COMPLETE.value
    if has("script", "script.json"):
        state = ProjectState.SCRIPTING.value
    if has("script", "factcheck.json"):
        state = ProjectState.FACT_CHECKING.value
    if has("production", "storyboard.json"):
        state = ProjectState.VISUAL_PLANNING.value
    if has("production", "assets.json"):
        state = ProjectState.ASSET_COLLECTION.value
    if has("production", "narration.json"):
        state = ProjectState.NARRATION.value
    if has("production", "video", "video.mp4"):
        state = ProjectState.RENDERING.value
    if has("production", "final", "qa-report.json"):
        state = ProjectState.QA.value
    return state


def _check_runtime_deps() -> None:
    """Fail fast when critical runtime packages are missing.

    Installed packages live outside the persisted workspace snapshot and can
    vanish across sandbox restores; every silent fallback downstream would
    otherwise produce unshippable artifacts (silent narration, empty beds)
    before crashing at render. Raise with the exact fix instead.
    """
    missing = []
    for mod in ("imageio_ffmpeg", "PIL", "mutagen"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise RuntimeError(
            "missing runtime dependencies: " + ", ".join(missing)
            + " — run `pip install -r requirements.txt` in the repo root and retry."
        )


def run_project(pid: str, *, resume: bool = True, stop_after: str = "",
                approvals: dict | None = None) -> dict:
    """Run (or resume) the full pipeline. Returns final summary. Raises on fatal error
    after persisting FAILED state + traceback (recovery: fix cause, call again)."""
    _check_runtime_deps()  # fail fast: never silently degrade on missing packages
    from .providers.registry import build_providers
    root = storage.project_dir(pid)
    idea_doc = storage.read_json(root / "idea.json", {})
    idea = idea_doc.get("idea", "")
    instructions = idea_doc.get("instructions", "")
    duration = idea_doc.get("duration", get_settings().default_duration)
    mode = idea_doc.get("mode", "autonomous")
    approvals = approvals or {}
    stack = build_providers()
    state = storage.get_state(pid) if resume else ProjectState.IDEA.value
    if resume and state == ProjectState.FAILED.value:
        # FAILED auto-recovery: infer furthest valid stage from artifacts.
        # Degraded artifacts (silent narration, empty beds, dangling asset
        # paths) are discarded so their stages re-run instead of being
        # mistaken for complete.
        for rel, bad in (
            ("production/narration.json", lambda d:
             isinstance(d, list) and any(n.get("provider") == "silent-fallback" for n in d)),
            ("production/music.json", lambda d:
             isinstance(d, dict) and not d.get("path")),
            ("production/sfx.json", lambda d:
             isinstance(d, dict) and not d.get("path")),
            ("production/assets.json", lambda d:
             isinstance(d, list) and any(
                 (not a.get("path") and a.get("primary"))
                 or (a.get("path")
                     and not (root.parent.parent / a["path"]).exists()
                     and not Path(a["path"]).exists()) for a in d)),
        ):
            p = root / rel
            try:
                if p.exists() and bad(storage.read_json(p, [])):
                    p.unlink()
                    _log(pid, f"FAILED recovery: discarded degraded {rel} (will re-run)")
            except Exception:
                pass
        state = _infer_state_from_artifacts(root)
        _log(pid, f"FAILED recovery: inferred state {state} from artifacts")
    order = [s.value for s in
             [ProjectState.IDEA, ProjectState.RESEARCHING, ProjectState.RESEARCH_COMPLETE,
              ProjectState.OUTLINING, ProjectState.SCRIPTING, ProjectState.FACT_CHECKING,
              ProjectState.VISUAL_PLANNING, ProjectState.ASSET_COLLECTION, ProjectState.NARRATION,
              ProjectState.RENDERING, ProjectState.QA, ProjectState.READY]]

    def reached(s: str) -> bool:
        try:
            return order.index(state) >= order.index(s)
        except ValueError:
            return False

    try:
        # ── RESEARCHING ──
        if not reached("RESEARCH_COMPLETE"):
            storage.set_state(pid, ProjectState.RESEARCHING)
            _log(pid, "STAGE: research planning")
            from .research.planner import plan_research
            plan = plan_research(idea, instructions, duration, stack=stack)
            storage.write_json(root / "research" / "research_plan.json", plan)
            _log(pid, f"plan: depth={plan['depth']} questions={len(plan['research_questions'])}")
            _log(pid, "STAGE: deep research")
            from .research.engine import run_research
            res = run_research(plan, stack,
                               progress_cb=lambda d, t, m: _log(pid, f"research {d}/{t} {m}"))
            storage.write_json(root / "research" / "sources.json", res["sources"])
            storage.write_json(root / "research" / "claims.json", res["claims"])
            storage.write_json(root / "research" / "evidence.json",
                               {"queries": res["queries"], "causal_chain": res["causal_chain"],
                                "fetch_stats": res.get("fetch_stats", {}),
                                "backbone_stats": res.get("backbone_stats", {})})
            storage.write_json(root / "research" / "contradictions.json", res["contradictions"])
            storage.write_json(root / "research" / "uncertainty.json", res["uncertainty"])
            (root / "research" / "notes.md").write_text(
                "# Research notes\n\n" + "\n\n".join(res["notes"][:200]), encoding="utf-8")
            (root / "research" / "evidence_full.txt").write_text(res["evidence_text"][:60000], encoding="utf-8")
            storage.write_json(root / "research" / "provider_status.json", stack.status_report())
            storage.set_state(pid, ProjectState.RESEARCH_COMPLETE,
                              f"{len(res['sources'])} sources, {len(res['claims'])} claims")
            _log(pid, f"research complete: {len(res['sources'])} sources, {len(res['claims'])} claims")
            if stop_after == "RESEARCH_COMPLETE":
                return {"project_id": pid, "state": "RESEARCH_COMPLETE"}
            if mode == "approval" and approvals.get("research") is False:
                _log(pid, "approval mode: paused after research (set approvals['research']=True to continue)")
                return {"project_id": pid, "state": "RESEARCH_COMPLETE", "paused": True}

        # ── OUTLINING + SCRIPTING ──
        if not reached("SCRIPTING") or not (root / "script" / "script.md").exists():
            storage.set_state(pid, ProjectState.OUTLINING)
            from .story.structure import pick_structure
            from .story.script import build_script_outline, write_script
            plan = storage.read_json(root / "research" / "research_plan.json", {})
            claims = storage.read_json(root / "research" / "claims.json", [])
            ev = storage.read_json(root / "research" / "evidence.json", {})
            chain = ev.get("causal_chain", [])
            key, beats = pick_structure(chain, idea, stack)
            outline = build_script_outline(beats, chain, claims)
            storage.write_json(root / "script" / "outline.json",
                               {"structure": key, "beats": beats, "outline": outline})
            (root / "script" / "outline.md").write_text(
                f"# Outline — {key}\n\n" + "\n".join(f"{i+1}. {b}" for i, b in enumerate(beats)),
                encoding="utf-8")
            storage.set_state(pid, ProjectState.SCRIPTING)
            _log(pid, f"STAGE: scripting ({key}, {len(beats)} beats)")
            evidence_text = (root / "research" / "evidence_full.txt").read_text(encoding="utf-8") \
                if (root / "research" / "evidence_full.txt").exists() else ""
            script = write_script(outline, claims, evidence_text, duration, idea, stack)
            (root / "script" / "script.md").write_text(
                f"# Script — {idea}\n\n_provider: {script['provider']}_ · "
                f"~{script['words']} words · ~{script['est_seconds']/60:.1f} min_\n\n" + script["full_text"],
                encoding="utf-8")
            storage.write_json(root / "script" / "script.json", script)
            storage.write_json(root / "script" / "traceability.json",
                               script.get("traceability", []))
            storage.write_json(root / "research" / "claims.json", claims)  # with scene mapping
            _log(pid, f"script: {script['words']} words, ~{script['est_seconds']/60:.1f} min, via {script['provider']}"
                 + (f" (llm fallback reason: {script['llm_error']})" if script.get("llm_error") else ""))
            if stop_after == "SCRIPTING":
                return {"project_id": pid, "state": "SCRIPTING"}
            if mode == "approval" and approvals.get("script") is False:
                _log(pid, "approval mode: paused after script")
                return {"project_id": pid, "state": "SCRIPTING", "paused": True}

        # ── FACT_CHECKING ──
        if not reached("FACT_CHECKING") or not (root / "script" / "factcheck.json").exists():
            storage.set_state(pid, ProjectState.FACT_CHECKING)
            from .research.factcheck import factcheck_script, apply_autofixes
            script_text = (root / "script" / "script.md").read_text(encoding="utf-8")
            claims = storage.read_json(root / "research" / "claims.json", [])
            ev_path = root / "research" / "evidence_full.txt"
            evidence_text = ev_path.read_text(encoding="utf-8") if ev_path.exists() else ""
            report = factcheck_script(script_text, claims, stack, evidence_text)
            if report["status"] == "fail":
                fixed = apply_autofixes(script_text, report)
                (root / "script" / "script.md").write_text(fixed, encoding="utf-8")
                report["autofix_applied"] = True
                report2 = factcheck_script(fixed, claims, None, evidence_text)
                report["recheck"] = report2["status"]
            storage.write_json(root / "script" / "factcheck.json", report)
            _log(pid, f"factcheck: {report['status']} ({len(report['issues'])} issues)")
            if stop_after == "FACT_CHECKING":
                return {"project_id": pid, "state": "FACT_CHECKING"}

        # ── VISUAL_PLANNING ──
        if not reached("VISUAL_PLANNING") or not (root / "production" / "storyboard.json").exists():
            storage.set_state(pid, ProjectState.VISUAL_PLANNING)
            from .visuals.storyboard import build_storyboard
            script = storage.read_json(root / "script" / "script.json", {})
            board = build_storyboard(script.get("scenes", []), idea, stack)
            storage.write_json(root / "production" / "storyboard.json", board)
            _log(pid, f"storyboard: {len(board)} scenes")
            if stop_after == "VISUAL_PLANNING":
                return {"project_id": pid, "state": "VISUAL_PLANNING"}

        # ── ASSET_COLLECTION ──
        if not reached("ASSET_COLLECTION") or not (root / "production" / "assets.json").exists():
            storage.set_state(pid, ProjectState.ASSET_COLLECTION)
            from .visuals.assets import collect_assets
            from .research.planner import topic_anchors
            board = storage.read_json(root / "production" / "storyboard.json", [])
            _claims = storage.read_json(root / "research" / "claims.json", [])
            _cmap = {c.get("claim_id"): c.get("claim", "") for c in _claims
                     if c.get("claim_id") and c.get("claim")}
            assets = collect_assets(board, stack, root / "production" / "assets",
                                    progress_cb=lambda d, t, m: _log(pid, f"assets {d}/{t} {m}"),
                                    anchors=topic_anchors(idea), claims_map=_cmap)
            storage.write_json(root / "production" / "assets.json", assets)
            _log(pid, f"assets: {len(assets)} collected")
            if stop_after == "ASSET_COLLECTION":
                return {"project_id": pid, "state": "ASSET_COLLECTION"}

        # ── NARRATION ──
        if not reached("NARRATION") or not (root / "production" / "narration.json").exists():
            storage.set_state(pid, ProjectState.NARRATION)
            from .audio.narration import synthesize_scenes
            from .audio.subtitles import build_subtitles
            board = storage.read_json(root / "production" / "storyboard.json", [])
            narr = synthesize_scenes(board, stack, root / "production" / "narration",
                                     progress_cb=lambda d, t, m: _log(pid, f"narration {d}/{t} {m}"))
            silent = [n.get("scene_id") for n in narr
                      if n.get("provider") == "silent-fallback"]
            if silent:
                raise RuntimeError(
                    f"no working TTS provider ({len(silent)} silent scenes: "
                    f"{silent[:4]}...) — refusing to ship a silent video. "
                    "Check edge-tts/gTTS connectivity and retry.")
            storage.write_json(root / "production" / "narration.json", narr)
            durs = {n["scene_id"]: float(n.get("duration_s", 0) or 0) for n in narr}
            subs = build_subtitles(board, durs, root / "production" / "subtitles")
            storage.write_json(root / "production" / "subtitles.json", subs)
            total = sum(durs.values())
            _log(pid, f"narration: {len(narr)} scenes, {total/60:.1f} min total")
            if stop_after == "NARRATION":
                return {"project_id": pid, "state": "NARRATION"}

        # ── RENDERING ──
        if not reached("RENDERING") or not (root / "production" / "video" / "video.mp4").exists():
            storage.set_state(pid, ProjectState.RENDERING)
            from .video.renderer import build_job
            from .audio.music import ensure_music
            board = storage.read_json(root / "production" / "storyboard.json", [])
            assets = storage.read_json(root / "production" / "assets.json", [])
            narr = storage.read_json(root / "production" / "narration.json", [])
            durs = {n["scene_id"]: float(n.get("duration_s", 0) or 0) for n in narr}
            music = ensure_music(root / "production" / "music", sum(durs.values()))
            storage.write_json(root / "production" / "music.json", music)
            from .audio.sfx import ensure_ambience_bed
            bed = ensure_ambience_bed(root / "production" / "music", sum(durs.values()),
                                      music.get("path", ""), idea=idea)
            storage.write_json(root / "production" / "sfx.json", bed)
            _log(pid, f"sound bed: {bed.get('source', 'none')}")
            _subs = storage.read_json(root / "production" / "subtitles.json", {})
            _claims = storage.read_json(root / "research" / "claims.json", [])
            _cmap = {c.get("claim_id"): c.get("claim", "") for c in _claims
                     if c.get("claim_id") and c.get("claim")}
            job = build_job(board, assets, narr,
                            {"path": bed.get("path") or music.get("path", ""),
                             "gain": bed.get("gain", 0.08) if bed.get("path") else music.get("gain", 0.08)},
                            get_settings(), claims_map=_cmap,
                            stages_dir=root / "production" / "stages")
            if _subs.get("srt"):
                job["subtitles_srt"] = _subs["srt"]
            storage.write_json(root / "production" / "render_job.json",
                               {**job, "scenes": [{k: v for k, v in s.items() if k != "audio"} | {"audio": s.get("audio", "")} for s in job["scenes"]]})
            out = root / "production" / "video" / "video.mp4"
            result = stack.renderer.render(job, out,
                                           progress_cb=lambda d, t: _log(pid, f"render scene {d}/{t}"))
            storage.write_json(root / "production" / "render_result.json", result)
            # final copy + thumbnail + metadata
            final = root / "production" / "final" / "final.mp4"
            final.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(out, final)
            from .visuals.thumbnail import concept, render
            claims = storage.read_json(root / "research" / "claims.json", [])
            th_c = concept(idea, claims, stack)
            storage.write_json(root / "production" / "final" / "thumbnail_concept.json", th_c)
            # thumbnail bg: most topic-relevant downloaded image
            import re as _re
            idea_keys = set(_re.findall(r"[a-z]{5,}", idea.lower()))
            best_img, best_score = "", -1
            for a in assets:
                p = str(a.get("path", ""))
                if a.get("kind") != "image" or not p.endswith((".jpg", ".png", ".jpeg")):
                    continue
                desc = _re.findall(r"[a-z]{5,}", (a.get("description", "") + " " + a.get("scene_id", "")).lower())
                score = len(set(desc) & idea_keys)
                if score > best_score:
                    best_img, best_score = p, score
            render(th_c, root / "production" / "final" / "thumbnail.png", best_img)
            from .metadata.youtube import build_metadata
            sources = storage.read_json(root / "research" / "sources.json", [])
            meta = build_metadata(idea, board, durs, claims, sources, stack)
            storage.write_json(root / "production" / "final" / "metadata.json", meta)
            (root / "production" / "final" / "description.txt").write_text(
                meta["description"], encoding="utf-8")
            _log(pid, f"rendered: {result.get('duration_s', 0)/60:.1f} min -> {final}")
            if stop_after == "RENDERING":
                return {"project_id": pid, "state": "RENDERING"}

        # ── QA ──
        storage.set_state(pid, ProjectState.QA)
        from .video.qa import run_qa
        board = storage.read_json(root / "production" / "storyboard.json", [])
        assets = storage.read_json(root / "production" / "assets.json", [])
        narr = storage.read_json(root / "production" / "narration.json", [])
        subs = storage.read_json(root / "production" / "subtitles.json", {})
        claims = storage.read_json(root / "research" / "claims.json", [])
        qa = run_qa(pid, root, board, assets, narr,
                    root / "production" / "final" / "final.mp4", subs, claims)
        storage.write_json(root / "production" / "final" / "qa-report.json", qa)
        _log(pid, f"QA: {qa['status']} ({len(qa['failed'])} failed: {qa['failed']})")
        if qa["status"] == "fail":
            raise RuntimeError(
                f"QA failed ({len(qa['failed'])} checks: {qa['failed']}) — "
                "refusing to mark READY. Fix the cause and resume.")
        storage.set_state(pid, ProjectState.READY, f"QA {qa['status']}")
        return {"project_id": pid, "state": "READY", "qa": qa["status"],
                "video": str(root / "production" / "final" / "final.mp4")}
    except Exception as e:
        tb = traceback.format_exc()
        _log(pid, f"FATAL: {e}\n{tb}")
        storage.set_state(pid, ProjectState.FAILED, str(e)[:300])
        try:
            storage.write_json(root / "error.json", {"error": str(e), "traceback": tb[-4000:]})
        except Exception:
            pass
        raise
