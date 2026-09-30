# 🔬 Science YouTube AI — Autonomous Science Video Production

One **idea** in → deeply researched, fact-checked, narrated, rendered **science YouTube video** out.
$0 software budget. Provider-independent. Resumable. Phone-friendly UI.

## What it does

```
IDEA → research (multi-source) → claims+evidence → story → script → fact-check
→ storyboard → assets → narration → subtitles → FFmpeg render → QA → package
```

You enter e.g. *"How does a mosquito transmit malaria, and what happens to
Plasmodium inside the mosquito?"* — the system plans research questions,
searches Wikipedia / OpenAlex / Europe PMC / arXiv, builds a claim→source→scene
map, writes a spoken script, fact-checks it, plans visuals per scene
(stock + generated SVG diagrams), synthesizes narration, renders 1080p 16:9
video with music + subtitles, generates thumbnail + metadata + chapters, and
runs QA. Every stage is an artifact the next stage consumes; every run resumes
from the last success.

## Quick start

```bash
git clone <this-repo> && cd science-youtube-ai
pip install -r requirements.txt
cp .env.example .env   # optional: add GEMINI_API_KEY for best script quality
# CLI
python -m science_studio new "How do mosquitoes transmit malaria?" --duration 12-15
python -m science_studio run <project-id>
# Web UI (phone-friendly)
python -m science_studio.web.app  # → http://localhost:5000
```

No keys at all? It still runs: template generation + Wikimedia + free TTS + FFmpeg.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Key ideas:

- **Provider abstractions** (`AIProvider`, `SearchProvider`, `ImageProvider`,
  `VideoProvider`, `SpeechProvider`, `RenderingProvider`) — every external
  service replaceable; `registry.build_providers()` orders free-first chains
  with honest `status()`.
- **FREE_ONLY=1** (default) — paid services are never instantiated; free-limit
  hits fall back / queue / report, never silently charge.
- **Depth controller** — research budget scales with topic complexity, not fixed.
- **Traceability** — `claim_id → source_ids → evidence → script_location → scene`.
- **Real timing** — scene durations come from actual TTS audio, never word counts.

## Providers & free tiers

See [docs/PROVIDERS.md](docs/PROVIDERS.md) (researched Sep 2026). Summary:

| Need | Default ($0, keyless) | Better ($0, free key) |
|---|---|---|
| LLM | template-fallback (offline) | Gemini 2.5 Flash — 1,500 req/day, no card |
| Research | Wikipedia, OpenAlex, Europe PMC, arXiv, DDG | — |
| Images | Wikimedia Commons | + Pexels (200/hr), Pixabay (100/min) |
| TTS | edge-tts → gTTS → local → silent | — |
| Render | FFmpeg (static binary via imageio-ffmpeg) | — |

## Project layout

```
projects/<id>/idea.json  research/{research_plan,sources,claims,evidence,
  contradictions,uncertainty,notes.md}  script/{outline,script,factcheck}
  production/{storyboard,assets,narration,subtitles,video,final/{final.mp4,
  thumbnail.png,metadata.json,qa-report.json}}  pipeline.log
```

## Tests

`python -m pytest tests/ -q` (28 tests: intake, planning, claims, factcheck,
script, storyboard, assets, TTS, render incl. relative-path regression,
subtitles, states, recovery, providers, QA, e2e-stub).
First real e2e: `python scripts/run_malaria_test.py`.

## Demo run (malaria / Plasmodium, keyless $0 mode)

Idea: *"How does a mosquito transmit malaria, and what actually happens to
Plasmodium inside the mosquito?"* — fully autonomous, no API keys:

| Stage | Result |
|---|---|
| Research | 42 sources (Europe PMC, Wikipedia, arXiv), 50 claims, claim→source→scene map |
| Script | 2,356 words, 12 scenes, journey_process structure |
| Fact-check | heuristic pass + autofix (2 minor notes) |
| Visuals | 11 generated SVG diagrams + Wikimedia images, licensed + attributed |
| Narration | 12/12 scenes edge-TTS, 17.7 min actual audio |
| Subtitles | SRT + WebVTT, scene-timed |
| Video | 17.7 min, 1280×720, 24fps, H.264+AAC, music bed (CC0 generated) |
| Thumbnail | concept + 1280×720 render |
| Metadata | 3 titles, description, 12 chapters, tags, sources section |
| QA | **pass** — 12/12 checks (durations match to the second) |

Artifacts: `projects/20260930-how-does-a-mosquito-transmit-m-8f2cb6/`
(JSON/MD/SVG/SRT committed; binaries gitignored).
With a free `GEMINI_API_KEY`, script fluency and claim synthesis improve further.

## YouTube upload (optional)

Never blocks production. See [docs/YOUTUBE_UPLOAD.md](docs/YOUTUBE_UPLOAD.md).

## Limitations

Honest list in [docs/LIMITATIONS.md](docs/LIMITATIONS.md) — including that
human spot-check is recommended before publishing medical content.

## Science quality standard

Accuracy > clarity > storytelling > entertainment > speed. No invented studies,
stats, quotes, or mechanisms; uncertainty explicitly labelled
(established → speculation); peer-reviewed/agency sources preferred.
