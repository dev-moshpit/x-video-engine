"""Post-production pipeline: starred clip -> finished upload.

Modules:
    script_builder — publish dict -> {hook, VO script lines, CTA}
    tts            — text -> voiceover audio (edge-tts by default)
    captions       — script lines + duration -> SRT
    ffmpeg_render  — bg video + voice + SRT + hook overlay -> final mp4

The `scripts/render_final_video.py` orchestrator reads a selection.json,
walks the starred clips, runs them through this pipeline, and drops
finished uploads into `final_exports/`.
"""
