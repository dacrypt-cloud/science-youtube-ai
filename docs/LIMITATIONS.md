# Known limitations (honest)

1. Without GEMINI_API_KEY the system uses extractive template generation — factually
   grounded in retrieved snippets but less fluent than an LLM script.
2. edge-tts is unofficial and may throttle; the chain falls back to gTTS → local → silent.
   Silent scenes are flagged in QA (`real_voices` check).
3. Stock video requires free Pexels/Pixabay keys; without them the renderer uses
   Wikimedia images + generated SVG diagrams (still a complete video).
4. Diagrams are structured SVG schematics, not hand-drawn animation.
5. Subtitles are scene-distributed, not word-aligned (no forced aligner in $0 scope yet).
6. Fact-check is heuristic + optional LLM review — human spot-check recommended before
   publishing, especially for medical topics.
