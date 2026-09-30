# Architecture

```
idea.json → research_plan → sources → claims → outline → script → factcheck
→ storyboard → assets → narration → subtitles → render → QA → final/
```

- `config.py` — env-driven settings, FREE_ONLY guard.
- `models.py` — typed artifacts (Source, Claim, Scene, Asset, ProjectState).
- `storage.py` — per-project directories, resumable states, history.
- `providers/` — replaceable interfaces: AI, Search, Image, Video, Speech, Rendering.
  Registry builds a free-first chain with honest `status()` per provider.
- `research/` — planner (depth controller) + multi-source engine + factcheck.
- `story/` — structure picker + script engine + duration planner.
- `visuals/` — storyboard, asset manager (cache/dedupe/license), SVG diagrams, thumbnail.
- `audio/` — narration chain, procedural CC0 music bed, SRT/VTT.
- `video/` — FFmpeg job builder + QA checks.
- `metadata/` — titles/description/chapters + optional YouTube upload.
- `pipeline.py` — orchestrator with explicit states and resume-from-last-success.
- `web/app.py` — mobile-friendly Flask UI.
```
