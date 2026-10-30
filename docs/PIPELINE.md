# Pipeline & resume

States: IDEA → RESEARCHING → RESEARCH_COMPLETE → OUTLINING → SCRIPTING →
FACT_CHECKING → VISUAL_PLANNING → ASSET_COLLECTION → NARRATION → RENDERING → QA → READY
(FAILED on fatal error; fix cause and re-run to resume from last success.)

CLI:
```
pip install -r requirements.txt
cp .env.example .env   # add GEMINI_API_KEY for best quality (optional)
python -m science_studio new "Your idea" --duration 12-15
python -m science_studio run <project-id>
python -m science_studio run <project-id>   # resumes after failure
```

Web UI: `python -m science_studio.web.app` → http://localhost:5000 (phone-friendly).

Approval mode: `--mode approval` pauses after research and after script.

## Runtime rules

- **Fail fast, never silently degrade.** Startup verifies critical packages
  (`imageio-ffmpeg`, `Pillow`, `mutagen`); narration refuses to ship
  silent-fallback scenes. A missing dependency is an error with the fix,
  not quiet garbage.
- **QA gates READY.** `pass` → READY. `review` (≤2 failed checks) → READY with
  the flag recorded. `fail` (>2) → FAILED with the checklist in `error.json`.
- **QA judges production quality, not just file validity:** narration hygiene
  (every spoken sentence re-validated), primary-image topical relevance,
  diagram label fit, subtitle cue integrity — plus resolution/codec/sync,
  traceability, and duration band.

## FAILED recovery

Re-running after FAILED infers the furthest stage from artifacts **and**
validates them first: silent narration, empty sound beds, and asset lists
with dangling/empty primary paths are discarded so their stages re-run
instead of being mistaken for complete. Research and script artifacts are
preserved, so recovery never pays for research twice.
