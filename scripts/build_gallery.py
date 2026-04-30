"""Generate (or regenerate) an index.html review gallery for a batch.

Useful for:
  - Rebuilding the gallery for an older batch (before this feature existed)
  - Re-rendering after you've added/removed clips manually

Usage:
    python scripts/build_gallery.py --batch-dir cache/batches/smoke3
    python scripts/build_gallery.py --batch-dir cache/batches/2026-04-21
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from xvideo.gallery import build_gallery


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-dir", required=True,
                        help="Path to batch folder (contains clips/, manifest.csv)")
    args = parser.parse_args()

    batch_dir = Path(args.batch_dir).resolve()
    if not batch_dir.is_dir():
        print(f"[ERROR] Not a directory: {batch_dir}")
        return 1

    out = build_gallery(batch_dir)
    print(f"[OK] Gallery: {out}")
    print(f"     Open in browser: file:///{str(out).replace(chr(92), '/')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
