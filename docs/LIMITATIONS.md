# Known limitations (honest)

1. Without any LLM key (`GEMINI_API_KEY`, `GROQ_API_KEY`, or `OPENROUTER_API_KEY`), the
   system uses extractive `template-fallback` generation — factually grounded in retrieved
   sources but less conversational than an LLM script.
2. `edge-tts` is unofficial and may throttle; the chain falls back to gTTS → local; the
   pipeline refuses to ship a silent video (`real_voices` QA gate).
3. Stock motion B-roll requires free `PEXELS_API_KEY` or `PIXABAY_API_KEY`; without them
   the renderer uses Wikimedia photographs + multi-stage SVG diagrams + Ken Burns motion.
4. Diagrams are structured multi-stage SVG schematics, not hand-drawn character animation.
5. Subtitles/kinetic captions are phrase-distributed within each scene's measured TTS audio,
   not phoneme-forced-aligned.
6. Fact-check is heuristic + optional LLM review — human spot-check is recommended before
   publishing, especially for medical or clinical topics.
