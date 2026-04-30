"""Post-production CLI: starred clip -> finished upload.

Reads a batch's starred clips (from selection.json + manifest.csv),
produces:
    final_exports/
        {job_id}_final.mp4          # bg video + voice + captions + hook
        {job_id}_final.srt          # caption file (standalone)
        {job_id}_final_metadata.json # provenance: source clip, voice, script

MVP behavior:
    --voice on     generate TTS voiceover (edge-tts)
    --captions on  burn SRT captions into the video
    --hook on      overlay title text in first ~2s
Any of these can be turned off to produce partial outputs.

Usage:
    python scripts/render_final_video.py \\
        --batch-dir cache/batches/quotes-2026-04-21 \\
        --selection selection.json \\
        --voice on --captions on --hook on

    # or with an explicit voice, skip captions:
    python scripts/render_final_video.py \\
        --batch-dir cache/batches/quotes-2026-04-21 \\
        --voice-name en-US-AriaNeural --captions off
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from xvideo.post.captions import build_captions
from xvideo.post.ffmpeg_render import (
    RenderOptions, probe_duration, render_final,
)
from xvideo.post.script_builder import build_script
from xvideo.post.tts import synthesize, voice_for_pack
from xvideo.post.word_captions import build_ass


def _onoff(s: str) -> bool:
    s = s.strip().lower()
    if s in ("on", "true", "1", "yes"):
        return True
    if s in ("off", "false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError(f"expected on/off, got '{s}'")


def _load_selection(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Selection file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("starred", []))


def _load_manifest(batch_dir: Path) -> dict[str, dict]:
    mf = batch_dir / "manifest.csv"
    if not mf.exists():
        raise FileNotFoundError(f"manifest.csv not found in {batch_dir}")
    with open(mf, newline="", encoding="utf-8") as f:
        return {r["job_id"]: r for r in csv.DictReader(f)}


def _load_sidecar(clips_dir: Path, job_id: str) -> dict:
    p = clips_dir / f"{job_id}.meta.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _render_one(
    job_id: str,
    batch_dir: Path,
    clips_dir: Path,
    final_dir: Path,
    manifest_row: dict,
    sidecar: dict,
    want_voice: bool,
    want_captions: bool,
    want_hook: bool,
    voice_name: str | None,
    voice_rate: str,
    caption_mode: str,
) -> dict:
    """Produce one finished export. Returns a dict describing what we made."""

    bg_video = clips_dir / f"{job_id}.mp4"
    if not bg_video.exists():
        raise FileNotFoundError(f"Source clip not found: {bg_video}")

    publish = sidecar.get("publish") or {}
    fmt_block = sidecar.get("format") or {}
    primary = fmt_block.get("primary_platform")

    script = build_script(publish, primary_platform=primary)

    out_mp4 = final_dir / f"{job_id}_final.mp4"
    out_srt = final_dir / f"{job_id}_final.srt"
    out_ass = final_dir / f"{job_id}_word.ass"
    out_voice = final_dir / f"{job_id}_voice.mp3"
    out_meta = final_dir / f"{job_id}_final_metadata.json"
    final_dir.mkdir(parents=True, exist_ok=True)

    # 1. TTS — produce voice audio if requested.
    #    Word mode also asks for per-word timing (derived from sentence
    #    boundaries + syllable-proportional split).
    tts_result = None
    if want_voice:
        if not script.lines:
            raise ValueError(f"{job_id}: script has no lines to voice")
        chosen_voice = voice_name or voice_for_pack(sidecar.get("pack"))
        tts_result = synthesize(
            text=script.as_plain_text(),
            out_path=out_voice,
            voice=chosen_voice,
            rate=voice_rate,
            want_words=(caption_mode == "word"),
        )

    # 2. Captions. Two modes:
    #    - "line": one line at a time (SRT, bottom-center). When the hook
    #      overlay is on, line #1 is the same text as the hook so we skip
    #      it in the caption track and start at line #2's voice time.
    #    - "word": per-word events (ASS, lower third, bold single word).
    #      No hook offset — hook sits at top, words at bottom, no clash.
    bg_duration = probe_duration(bg_video)
    vo_duration = tts_result.duration_sec if tts_result else bg_duration
    target_duration = max(bg_duration, vo_duration)

    hook_on = bool(want_hook and script.hook)
    segments = []
    captions_path_for_render: Path | None = None

    if caption_mode == "line":
        if hook_on and len(script.lines) > 1:
            import re as _re
            word_counts = [max(1, len(_re.findall(r"\S+", L))) for L in script.lines]
            total_words = sum(word_counts)
            line1_voice_dur = (word_counts[0] / total_words) * vo_duration
            caption_lines = script.lines[1:]
            caption_start_offset = line1_voice_dur
        else:
            caption_lines = list(script.lines)
            caption_start_offset = 0.0

        if want_captions and caption_lines:
            segments = build_captions(
                lines=caption_lines,
                total_duration=vo_duration,
                out_srt=out_srt,
                start_offset=caption_start_offset,
            )
            captions_path_for_render = out_srt

    elif caption_mode == "word":
        if want_captions and tts_result and tts_result.words:
            build_ass(
                words=tts_result.words,
                out_path=out_ass,
                video_width=576, video_height=1024,
            )
            captions_path_for_render = out_ass
    else:
        raise ValueError(f"Unknown caption-mode: {caption_mode}")

    # 3. FFmpeg composite
    if want_captions or want_hook or want_voice:
        voice_path = out_voice if tts_result else None
        if voice_path is None:
            raise RuntimeError(
                f"{job_id}: --voice off produces no audio; MVP requires "
                f"at least a voice track. Re-run with --voice on."
            )
        opts = RenderOptions(
            hook_text=(script.hook if want_hook else ""),
            target_duration_sec=target_duration,
        )
        # Captions off: ffmpeg still needs a subtitles input; use an empty SRT.
        if captions_path_for_render is None:
            empty_srt = final_dir / f"{job_id}_empty.srt"
            empty_srt.write_text("", encoding="utf-8")
            captions_path_for_render = empty_srt
            used_empty = True
        else:
            used_empty = False
        render_final(
            bg_video=bg_video,
            voice_audio=voice_path,
            captions_path=captions_path_for_render,
            out_path=out_mp4,
            opts=opts,
        )
        if used_empty:
            captions_path_for_render.unlink(missing_ok=True)

    # 4. Sidecar metadata
    meta = {
        "job_id": job_id,
        "source_clip": str(bg_video),
        "final_clip": str(out_mp4) if out_mp4.exists() else "",
        "final_srt": str(out_srt) if out_srt.exists() else "",
        "final_ass": str(out_ass) if out_ass.exists() else "",
        "caption_mode": caption_mode,
        "hook_text": script.hook if want_hook else "",
        "voice": {
            "engine": tts_result.engine,
            "voice_name": tts_result.voice,
            "duration_sec": tts_result.duration_sec,
            "audio_path": str(tts_result.audio_path),
        } if tts_result else None,
        "script": {
            "hook": script.hook,
            "lines": script.lines,
            "cta": script.cta,
        },
        "segments": [asdict(s) for s in segments],
        "sentences": (
            [asdict(s) for s in tts_result.sentences] if tts_result else []
        ),
        "words": (
            [asdict(w) for w in tts_result.words]
            if tts_result and caption_mode == "word" else []
        ),
        "bg_video_duration_sec": round(bg_duration, 2),
        "target_duration_sec": round(target_duration, 2),
        "pack": sidecar.get("pack") or manifest_row.get("pack") or "",
        "format": fmt_block.get("name") or manifest_row.get("format") or "",
        "publish": publish,
        "rendered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    out_meta.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-dir", required=True,
                    help="Path to batch folder (cache/batches/<name>/)")
    ap.add_argument("--selection", default=None,
                    help="Path to selection.json (default: <batch-dir>/selection.json)")
    ap.add_argument("--out-dir", default=None,
                    help="Output dir (default: <batch-dir>/final_exports/)")
    ap.add_argument("--voice", type=_onoff, default=True,
                    help="Generate TTS voiceover (on/off, default on)")
    ap.add_argument("--captions", type=_onoff, default=True,
                    help="Burn SRT captions into video (on/off, default on)")
    ap.add_argument("--hook", type=_onoff, default=True,
                    help="Overlay title as hook text in first ~2s (on/off, default on)")
    ap.add_argument("--voice-name", default=None,
                    help="Override TTS voice (e.g. en-US-JennyNeural)")
    ap.add_argument("--voice-rate", default="+0%",
                    help="TTS speech rate, edge-tts format (default '+0%%')")
    ap.add_argument("--caption-mode", choices=("line", "word"), default="line",
                    help="Caption granularity. 'line' = one sentence at a time "
                         "via SRT (current default). 'word' = per-word ASS, "
                         "bold single-word lower-third, the Shorts/TikTok look.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Stop after N starred clips (for iteration)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s",
                        datefmt="%H:%M:%S")

    batch_dir = Path(args.batch_dir).resolve()
    if not batch_dir.is_dir():
        print(f"[ERROR] batch dir not found: {batch_dir}")
        return 2
    clips_dir = batch_dir / "clips"

    sel_path = Path(args.selection) if args.selection else batch_dir / "selection.json"
    try:
        starred = _load_selection(sel_path)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        print("        Export a selection from the gallery first.")
        return 2
    if not starred:
        print(f"[WARN] No starred clips in {sel_path}")
        return 3

    final_dir = Path(args.out_dir) if args.out_dir else batch_dir / "final_exports"
    manifest = _load_manifest(batch_dir)

    if args.limit:
        starred = starred[: args.limit]

    print("=" * 68)
    print(f"POST-PRODUCTION  batch={batch_dir.name}")
    print(f"  clips: {len(starred)}   voice={args.voice}  "
          f"captions={args.captions}  hook={args.hook}")
    print(f"  out:   {final_dir}")
    print("=" * 68)

    ok = 0
    failed: list[tuple[str, str]] = []
    for i, job_id in enumerate(starred, 1):
        row = manifest.get(job_id, {})
        sidecar = _load_sidecar(clips_dir, job_id)
        print(f"  [{i}/{len(starred)}] {job_id} ...", end=" ", flush=True)
        t0 = time.time()
        try:
            meta = _render_one(
                job_id=job_id,
                batch_dir=batch_dir,
                clips_dir=clips_dir,
                final_dir=final_dir,
                manifest_row=row,
                sidecar=sidecar,
                want_voice=args.voice,
                want_captions=args.captions,
                want_hook=args.hook,
                voice_name=args.voice_name,
                voice_rate=args.voice_rate,
                caption_mode=args.caption_mode,
            )
            dur = time.time() - t0
            print(f"OK ({dur:.1f}s)  -> {Path(meta['final_clip']).name}")
            ok += 1
        except Exception as e:
            print(f"FAIL: {e}")
            failed.append((job_id, str(e)))

    print()
    print("=" * 68)
    print(f"POST COMPLETE  ok={ok}/{len(starred)}  failed={len(failed)}")
    print(f"  outputs: {final_dir}")
    if failed:
        print("  failures:")
        for jid, err in failed:
            print(f"    - {jid}: {err[:120]}")
    print("=" * 68)
    return 0 if not failed else 3


if __name__ == "__main__":
    sys.exit(main())
