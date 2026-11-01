# Providers — all $0 usable (strict FREE_ONLY=1)

## AI / LLM (automatic fallback chain: Gemini → Groq → OpenRouter → Ollama → template)
| Provider | Free terms | Key? | Notes |
|---|---|---|---|
| Gemini 2.5 Flash (AI Studio) | ~500–1,500 req/day, no card | Optional (`GEMINI_API_KEY`) | Primary if set. |
| Groq (`openai/gpt-oss-120b`) | ~14.4k req/day, 30 RPM, no card | Optional (`GROQ_API_KEY`) | Fast OpenAI-compatible inference; scripts run in 6-scene batches within free TPM limits. |
| OpenRouter (`openrouter/free`) | ~200 req/day on `:free` auto-router, no card | Optional (`OPENROUTER_API_KEY`) | Auto-selects live free models so model IDs never go stale. |
| Ollama (local) | Unlimited, offline after pull | No (`OLLAMA_BASE_URL`) | Optional local inference. |
| `template-fallback` | Unlimited, offline | No | Deterministic extractive generation. Always available; honestly labelled. |

## Research / search (all keyless)
- Wikipedia/MediaWiki — CC BY-SA, attribute.
- OpenAlex — CC0 API, scholarly index.
- Europe PMC — life-science literature, best for biomedical.
- arXiv — preprints (treat as preprint-level evidence).
- DuckDuckGo Instant Answers — best-effort backup, prefers .gov/.edu.

## Images / video
| Provider | Free terms | Key? | License |
|---|---|---|---|
| Wikimedia Commons | Unlimited, no key | No | Per-file CC BY/SA, CC0, or PD. Must attribute creator+license+link. |
| Pexels | 200 req/hr, 20k/mo | Yes (free) | Free commercial incl. YouTube. Link-back per API guidelines. |
| Pixabay | ~100 req/min | Yes (free) | Pixabay Content License, free commercial, no attribution required. Cache 24h+. |

## Speech (TTS)
| Provider | Free terms | Key? | Notes |
|---|---|---|---|
| edge-tts | Free, no published cap | No | Unofficial MS service; may throttle. Default voice. |
| gTTS | Free | No | Rate-limited fallback. |
| Piper | Unlimited local | No | Needs binary+model (optional). |
| espeak-ng | Unlimited local | No | Robotic, needs binary. |
| silent-fallback | Unlimited | No | Timed silence, estimated durations. Last resort, clearly labelled. |

## Rendering / music
- FFmpeg (system or imageio-ffmpeg static binary) — open source.
- Music: procedurally generated sine ambient bed (CC0, project-made) or user-supplied licensed files.

## YouTube upload (optional)
- YouTube Data API v3, OAuth desktop flow, ~1600 quota units/upload, 10k units/day free.
- Never blocks production. See docs/YOUTUBE_UPLOAD.md.
