"""Push HF-MODEL-CARD.md as the README.md of the lerugray/hammerstein-7b-lora HF repo.

Requires HF_TOKEN env var (write-access token from
https://huggingface.co/settings/tokens). Easiest: add the line
    export HF_TOKEN=hf_xxxxxxxx
to ~/.generalstaff/.env alongside OPENROUTER_API_KEY / RUNPOD_API_KEY,
then `source ~/.generalstaff/.env` and run this script.

Usage:
    source ~/.generalstaff/.env
    python tools/distill/hf_push_card.py

The HF model card is the README.md at the root of the HF model repo.
This script uploads tools/distill/HF-MODEL-CARD.md to that location.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ID = "lerugray/hammerstein-7b-lora"
CARD_PATH = Path(__file__).resolve().parent / "HF-MODEL-CARD.md"


def main() -> int:
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token.startswith("hf_"):
        print(
            "ERR: HF_TOKEN not set in env (expected format: hf_xxxxxxxx).\n"
            "  Add it to ~/.generalstaff/.env as: export HF_TOKEN=hf_xxxxxxxx\n"
            "  Then: source ~/.generalstaff/.env && python tools/distill/hf_push_card.py\n"
            "  Get a write token at https://huggingface.co/settings/tokens",
            file=sys.stderr,
        )
        return 1

    if not CARD_PATH.is_file():
        print(f"ERR: card not found at {CARD_PATH}", file=sys.stderr)
        return 1

    from huggingface_hub import HfApi

    api = HfApi(token=token)
    print(f"uploading {CARD_PATH} -> https://huggingface.co/{REPO_ID}/blob/main/README.md", file=sys.stderr)
    api.upload_file(
        path_or_fileobj=str(CARD_PATH),
        path_in_repo="README.md",
        repo_id=REPO_ID,
        repo_type="model",
        commit_message="model card: framework-first reframe + v0.4 cross-scale numbers (2026-05-11)",
    )
    print(f"OK: card live at https://huggingface.co/{REPO_ID}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
