#!/usr/bin/env python3
"""Push the trained Hammerstein-7B LoRA adapter to HuggingFace Hub.

Reads HF token from ~/.huggingface_token (mode 600). Creates the repo
as PRIVATE by default; pass --public to flip.

Usage:
    python tools/distill/hf_push.py
    python tools/distill/hf_push.py --public  # flip an existing private repo
    python tools/distill/hf_push.py --repo-name custom-name

The adapter is expected at:
    tools/distill/output/qwen-7b-hammerstein-lora/lora-adapter/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TOKEN_PATH = Path.home() / ".huggingface_token"
ADAPTER_DIR = ROOT / "tools" / "distill" / "output" / "qwen-7b-hammerstein-lora" / "lora-adapter"


def main() -> int:
    p = argparse.ArgumentParser(description="Push Hammerstein-7B adapter to HF Hub")
    p.add_argument("--repo-name", default="hammerstein-7b-lora",
                   help="Repo name under the authenticated user (default: hammerstein-7b-lora)")
    p.add_argument("--public", action="store_true",
                   help="Create or flip the repo to PUBLIC. Default is private.")
    p.add_argument("--adapter-dir", default=str(ADAPTER_DIR),
                   help=f"Path to adapter dir (default: {ADAPTER_DIR})")
    p.add_argument("--commit-message", default=None,
                   help="Commit message (default: auto-generated)")
    args = p.parse_args()

    # Verify token + adapter exist
    if not TOKEN_PATH.exists():
        sys.exit(f"HF token not found at {TOKEN_PATH}. "
                 "Save your write token there with mode 600.")
    adapter_path = Path(args.adapter_dir)
    if not adapter_path.exists():
        sys.exit(f"Adapter dir not found at {adapter_path}")
    expected_files = ["adapter_config.json", "adapter_model.safetensors",
                      "tokenizer.json", "tokenizer_config.json", "chat_template.jinja"]
    missing = [f for f in expected_files if not (adapter_path / f).exists()]
    if missing:
        sys.exit(f"Adapter dir missing expected files: {missing}")

    token = TOKEN_PATH.read_text().strip()
    if not token.startswith("hf_"):
        sys.exit("Token doesn't look right (expected to start with hf_). "
                 "Re-check the file contents.")

    try:
        from huggingface_hub import HfApi
    except ImportError:
        sys.exit("missing dependency: huggingface_hub\n"
                 "Install: pip install huggingface_hub")

    api = HfApi(token=token)

    # whoami to determine the user namespace
    try:
        me = api.whoami()
    except Exception as e:
        sys.exit(f"whoami failed (token may be invalid): {e}")
    username = me.get("name") or me.get("orgs", [{}])[0].get("name", "unknown")
    print(f"Authenticated as: {username}")

    repo_id = f"{username}/{args.repo_name}"
    visibility = "public" if args.public else "private"
    print(f"Target repo:      {repo_id}  ({visibility})")
    print(f"Adapter dir:      {adapter_path}")
    total_bytes = sum(f.stat().st_size for f in adapter_path.iterdir() if f.is_file())
    print(f"Upload size:      {total_bytes / 1024 / 1024:.1f} MB")

    # Create or update repo
    print(f"\nCreating/ensuring repo (private={not args.public})…")
    api.create_repo(
        repo_id=repo_id,
        repo_type="model",
        private=not args.public,
        exist_ok=True,
    )

    # If --public was passed and repo exists as private, flip it
    if args.public:
        print(f"Setting visibility to public…")
        api.update_repo_settings(repo_id=repo_id, private=False)

    # Upload the folder
    commit_msg = args.commit_message or (
        "v0: initial push — adapter trained 2026-05-08, "
        "spot-check passed (3/3), full eval pending"
    )
    print(f"\nUploading {len(list(adapter_path.iterdir()))} files…")
    api.upload_folder(
        folder_path=str(adapter_path),
        repo_id=repo_id,
        repo_type="model",
        commit_message=commit_msg,
    )

    print(f"\n✓ Push complete.")
    print(f"  View at: https://huggingface.co/{repo_id}")
    if not args.public:
        print(f"  (Private — only visible when logged in as {username})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
