"""Export starred clips from a batch as a publish-ready CSV + JSON.

Reads a selection.json (exported from the gallery) and the batch's
manifest + sidecars, produces:
  - publish_ready.csv  (one row per starred clip, flat columns for Excel/Sheets)
  - publish_ready.json (same data, nested structure for programmatic use)

Usage:
    python scripts/export_selection.py \\
        --batch-dir cache/batches/quotes-2026-04-21 \\
        --selection ~/Downloads/selection.json

If --selection is omitted, the script looks for `selection.json` in the
batch dir itself.

Columns written:
    job_id, filename, preset, motion, format, seed,
    subject, prompt, prompt_hash,
    title, caption, cta, hashtags,
    title_shorts, caption_shorts,
    title_tiktok, caption_tiktok,
    title_reels, caption_reels
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def _load_selection(path: Path) -> tuple[set[str], set[str]]:
    """Return (starred_ids, rejected_ids) from a selection.json file."""
    if not path.exists():
        raise FileNotFoundError(f"Selection not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return set(data.get("starred", [])), set(data.get("rejected", []))


def _sidecar_to_row(job_id: str, sidecar: dict) -> dict:
    """Flatten a sidecar into a publish-ready row."""
    publish = sidecar.get("publish") or {}
    platforms = publish.get("platforms") or {}

    def _platform(name: str, field: str) -> str:
        p = platforms.get(name) or {}
        return p.get(field) or publish.get(field) or ""

    fmt_block = sidecar.get("format") or {}
    return {
        "job_id": job_id,
        "filename": f"{job_id}.mp4",
        "preset": sidecar.get("preset_name", ""),
        "motion": sidecar.get("motion", ""),
        "format": fmt_block.get("name", ""),
        "seed": sidecar.get("seed", ""),
        "subject": (sidecar.get("style_config") or {}).get("preset_name", "")
                   or sidecar.get("row_id", ""),
        "prompt": sidecar.get("compiled_prompt", ""),
        "prompt_hash": sidecar.get("prompt_hash", ""),
        "title": publish.get("title", ""),
        "caption": publish.get("caption", ""),
        "cta": publish.get("cta", ""),
        "hashtags": " ".join(publish.get("hashtags", []) or []),
        "title_shorts":   _platform("shorts", "title"),
        "caption_shorts": _platform("shorts", "caption"),
        "title_tiktok":   _platform("tiktok", "title"),
        "caption_tiktok": _platform("tiktok", "caption"),
        "title_reels":    _platform("reels", "title"),
        "caption_reels":  _platform("reels", "caption"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-dir", required=True,
                        help="Path to batch folder (contains clips/, manifest.csv)")
    parser.add_argument("--selection", default=None,
                        help="Path to selection.json (default: <batch-dir>/selection.json)")
    parser.add_argument("--include-rejected", action="store_true",
                        help="Also export rejected clips (useful for QA)")
    parser.add_argument("--out-prefix", default="publish_ready",
                        help="Output filename prefix (default: publish_ready)")
    args = parser.parse_args()

    batch_dir = Path(args.batch_dir).resolve()
    if not batch_dir.is_dir():
        print(f"[ERROR] Not a directory: {batch_dir}")
        return 1

    sel_path = Path(args.selection) if args.selection else (batch_dir / "selection.json")
    try:
        starred, rejected = _load_selection(sel_path)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        print("        Export a selection from the gallery, then pass --selection.")
        return 2

    if not starred:
        print("[WARN] No starred clips in selection.json")
        if not args.include_rejected:
            print("       Pass --include-rejected to export rejected clips for QA.")
            return 3

    clips_dir = batch_dir / "clips"
    ids_to_export = list(starred)
    if args.include_rejected:
        ids_to_export.extend(sorted(rejected))

    rows: list[dict] = []
    missing: list[str] = []
    for job_id in ids_to_export:
        sidecar_path = clips_dir / f"{job_id}.meta.json"
        if not sidecar_path.exists():
            missing.append(job_id)
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] Sidecar unreadable for {job_id}: {e}")
            continue
        row = _sidecar_to_row(job_id, sidecar)
        row["_status"] = "starred" if job_id in starred else "rejected"
        rows.append(row)

    if missing:
        print(f"[WARN] {len(missing)} jobs had no sidecar: {missing[:5]}"
              f"{'...' if len(missing) > 5 else ''}")

    if not rows:
        print("[ERROR] Nothing to export.")
        return 4

    # CSV (flat, Excel/Sheets friendly)
    csv_path = batch_dir / f"{args.out_prefix}.csv"
    fieldnames = [
        "job_id", "filename", "preset", "motion", "format", "seed", "_status",
        "subject", "prompt", "prompt_hash",
        "title", "caption", "cta", "hashtags",
        "title_shorts", "caption_shorts",
        "title_tiktok", "caption_tiktok",
        "title_reels", "caption_reels",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # JSON (nested, programmatic)
    json_path = batch_dir / f"{args.out_prefix}.json"
    json_path.write_text(json.dumps({
        "batch_dir": str(batch_dir),
        "selection_source": str(sel_path),
        "starred_count": len(starred),
        "rejected_count": len(rejected) if args.include_rejected else 0,
        "clips": rows,
    }, indent=2), encoding="utf-8")

    # Summary
    starred_exported = sum(1 for r in rows if r["_status"] == "starred")
    rejected_exported = sum(1 for r in rows if r["_status"] == "rejected")
    print(f"[OK] Exported {len(rows)} clips ({starred_exported} starred, "
          f"{rejected_exported} rejected)")
    print(f"     CSV:  {csv_path}")
    print(f"     JSON: {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
