"""Downloads the Kokoro-82M ONNX model + voice pack used by app/tts/kokoro_tts.py.

Run once: `python scripts/download_tts_model.py`. Safe to re-run -- skips files
that already exist. Total download is ~330MB.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

RELEASE_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
FILES = ["kokoro-v1.0.onnx", "voices-v1.0.bin"]

DEST_DIR = Path(__file__).resolve().parent.parent / "models" / "kokoro"


def download(url: str, dest: Path) -> None:
    print(f"downloading {url} -> {dest}")

    def report(block_num: int, block_size: int, total_size: int) -> None:
        if total_size <= 0:
            return
        done = block_num * block_size
        pct = min(100, done * 100 // total_size)
        print(f"\r  {pct}%", end="", flush=True)

    urllib.request.urlretrieve(url, dest, reporthook=report)
    print()


def main() -> None:
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    for filename in FILES:
        dest = DEST_DIR / filename
        if dest.exists():
            print(f"already have {dest}, skipping")
            continue
        download(f"{RELEASE_BASE}/{filename}", dest)
    print(f"done. model files in {DEST_DIR}")


if __name__ == "__main__":
    sys.exit(main())
