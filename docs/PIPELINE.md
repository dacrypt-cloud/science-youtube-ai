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
