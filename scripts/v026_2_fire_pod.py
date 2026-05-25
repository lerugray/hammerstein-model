#!/usr/bin/env python3
r"""v0.2.6.2 pod fire — iteration on v0.2.6.1.

Mirrors v026_1_fire_pod.py with version-bumped paths + HF repo id.
GPU preference: A6000-first per Ray's standing preference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
KEY_DIR = Path.home() / ".runpod-overnight"
KEY_PATH = KEY_DIR / "key"
PUB_PATH = Path(str(KEY_PATH) + ".pub")

LOCAL_STORE = Path("D:/hammerstein-store/models/v0.2.6.2")

RUNPOD_API = "https://api.runpod.io/graphql"

HF_REPO_ID = "lerugray/hammerstein-7b-v026-2"
HF_TOKEN_PATH = Path.home() / ".cache" / "huggingface" / "token"


def load_hf_token() -> str:
    env = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if env:
        return env.strip()
    if HF_TOKEN_PATH.exists():
        return HF_TOKEN_PATH.read_text(encoding="utf-8").strip()
    return ""


PREFERRED_GPU_TYPES = [
    "RTX A6000",       # 48GB, secure, ~$0.33/hr — power-first per Ray's standing preference
    "RTX 4090",        # 24GB, secure, ~$0.34/hr
    "RTX A5000",       # 24GB, secure, ~$0.16/hr — fallback only
    "RTX A4500",       # 20GB, secure, ~$0.19/hr — last resort
]

DEFAULT_TEMPLATE = "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, Exception):
    pass


def load_env() -> dict:
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.+)$", line)
            if m:
                env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return env


def gql(api_key: str, query: str, variables: dict | None = None) -> dict:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        RUNPOD_API,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; hammerstein-pod-driver/1.0)",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:500]}")
    out = json.loads(body)
    if "errors" in out:
        raise RuntimeError(f"GraphQL error: {json.dumps(out['errors'], indent=2)}")
    return out["data"]


def ensure_ssh_keypair() -> str:
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    if not KEY_PATH.exists():
        sys.stdout.flush(); print(f"  Generating ed25519 keypair at {KEY_PATH}...")
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(KEY_PATH), "-C", "v026-2-pod"],
            check=True,
        )
    return PUB_PATH.read_text(encoding="utf-8").strip()


def pick_gpu_types(api_key: str) -> list[tuple[str, str, float]]:
    sys.stdout.flush(); print("  Querying GPU availability...")
    q = """
    query {
      gpuTypes {
        id
        displayName
        memoryInGb
        secureCloud
        lowestPrice(input: { gpuCount: 1 }) {
          uninterruptablePrice
        }
      }
    }
    """
    data = gql(api_key, q)
    types = data.get("gpuTypes", [])
    by_name = {g["displayName"]: g for g in types}
    out = []
    for name in PREFERRED_GPU_TYPES:
        g = by_name.get(name)
        if g and g.get("lowestPrice", {}).get("uninterruptablePrice") is not None:
            price = g["lowestPrice"]["uninterruptablePrice"]
            out.append((g["id"], name, price))
    if not out:
        raise RuntimeError(f"No preferred GPU available. Saw: {list(by_name)[:10]}")
    sys.stdout.flush(); print(f"  Found {len(out)} candidate GPU types:")
    for gid, gname, gprice in out:
        sys.stdout.flush(); print(f"    {gname:20s} ${gprice:.3f}/hr  ({gid})")
    return out


def fire_pod(api_key: str, pubkey: str, gpu_type_id: str,
             template: str = DEFAULT_TEMPLATE) -> str:
    sys.stdout.flush(); print(f"  Firing pod (GPU {gpu_type_id})...")
    mutation = """
    mutation($input: PodFindAndDeployOnDemandInput!) {
      podFindAndDeployOnDemand(input: $input) {
        id
        machineId
        desiredStatus
        env
      }
    }
    """
    variables = {
        "input": {
            "cloudType": "SECURE",
            "gpuCount": 1,
            "gpuTypeId": gpu_type_id,
            "containerDiskInGb": 80,
            "volumeInGb": 0,
            "minMemoryInGb": 16,
            "minVcpuCount": 4,
            "imageName": template,
            "ports": "22/tcp,8888/http",
            "name": f"hammerstein-v026-2-{int(time.time())}",
            "env": [
                {"key": "PUBLIC_KEY", "value": pubkey},
            ],
            "dockerArgs": "",
        },
    }
    data = gql(api_key, mutation, variables)
    pod = data.get("podFindAndDeployOnDemand")
    if not pod or not pod.get("id"):
        raise RuntimeError(f"podFindAndDeployOnDemand returned no id: {data}")
    pod_id = pod["id"]
    sys.stdout.flush(); print(f"  Pod created: {pod_id}")
    return pod_id


def poll_for_ssh(api_key: str, pod_id: str, timeout_sec: int = 300) -> tuple[str, int]:
    q = """
    query($podId: String!) {
      pod(input: { podId: $podId }) {
        id
        desiredStatus
        runtime {
          uptimeInSeconds
          ports {
            ip
            isIpPublic
            privatePort
            publicPort
            type
          }
        }
      }
    }
    """
    start = time.time()
    sys.stdout.flush(); print(f"  Polling for SSH endpoint (timeout {timeout_sec}s)...")
    while time.time() - start < timeout_sec:
        data = gql(api_key, q, {"podId": pod_id})
        pod = data.get("pod") or {}
        runtime = pod.get("runtime")
        if runtime:
            for p in runtime.get("ports", []) or []:
                if p.get("privatePort") == 22 and p.get("publicPort"):
                    ip = p.get("ip")
                    port = p.get("publicPort")
                    sys.stdout.flush(); print(f"  SSH ready: {ip}:{port}")
                    return ip, port
        time.sleep(8)
    raise RuntimeError(f"Pod {pod_id} did not surface SSH in {timeout_sec}s")


def ssh_write_file(ip: str, port: int, remote_path: str, content: str,
                   mode: str = "600") -> None:
    cmd = (
        f"umask 077 && mkdir -p \"$(dirname '{remote_path}')\" "
        f"&& cat > '{remote_path}' && chmod {mode} '{remote_path}'"
    )
    full_cmd = [
        "ssh",
        "-i", str(KEY_PATH),
        "-p", str(port),
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-o", "ConnectTimeout=30",
        f"root@{ip}",
        cmd,
    ]
    res = subprocess.run(
        full_cmd,
        input=content,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"ssh_write_file({remote_path}) failed (rc={res.returncode}): "
            f"{(res.stderr or '')[-300:]}"
        )


def ssh_run(ip: str, port: int, cmd: str, timeout: int = 600, capture: bool = True) -> tuple[int, str]:
    full_cmd = [
        "ssh",
        "-i", str(KEY_PATH),
        "-p", str(port),
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-o", "ConnectTimeout=30",
        f"root@{ip}",
        cmd,
    ]
    if capture:
        res = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return res.returncode, ((res.stdout or "") + (res.stderr or ""))
    else:
        res = subprocess.run(full_cmd, timeout=timeout)
        return res.returncode, ""


def terminate_pod(api_key: str, pod_id: str) -> None:
    sys.stdout.flush(); print(f"  Terminating pod {pod_id}...")
    mutation = """
    mutation($podId: String!) {
      podTerminate(input: { podId: $podId })
    }
    """
    gql(api_key, mutation, {"podId": pod_id})
    sys.stdout.flush(); print(f"  Pod terminated.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-terminate", action="store_true")
    args = p.parse_args()

    env = load_env()
    api_key = env.get("RUNPOD_API_KEY")
    if not api_key:
        sys.stdout.flush(); print(f"ERROR: RUNPOD_API_KEY not in {ENV_PATH}")
        return 1

    sys.stdout.flush(); print("=== v0.2.6.2 pod fire ===")
    sys.stdout.flush(); print(f"  Local store target: {LOCAL_STORE}")
    sys.stdout.flush(); print()

    pubkey = ensure_ssh_keypair()
    gpu_candidates = pick_gpu_types(api_key)

    hf_token = load_hf_token()
    if not hf_token:
        raise RuntimeError("HF token not found.")
    sys.stdout.flush(); print(f"  HF token loaded.")

    if args.dry_run:
        sys.stdout.flush(); print("\nDry-run complete.")
        return 0

    pod_id = None
    last_err = None
    for gpu_type_id, gpu_name, gpu_price in gpu_candidates:
        try:
            sys.stdout.flush(); print(f"\n  Attempting deploy on {gpu_name} (${gpu_price:.3f}/hr)...")
            pod_id = fire_pod(api_key, pubkey, gpu_type_id)
            sys.stdout.flush(); print(f"  Deploy succeeded on {gpu_name}.")
            break
        except RuntimeError as e:
            msg = str(e)
            last_err = e
            if "does not have the resources" in msg or "no available" in msg.lower():
                sys.stdout.flush(); print(f"  {gpu_name} unavailable; trying next.")
                continue
            raise
    if pod_id is None:
        raise RuntimeError(f"All GPU candidates failed. Last error: {last_err}")
    try:
        ip, port = poll_for_ssh(api_key, pod_id)

        sys.stdout.flush(); print()
        sys.stdout.flush(); print("  Bootstrapping pod...")
        bootstrap = (
            "set -e; "
            "cd /workspace 2>/dev/null || cd ~; "
            "if [ ! -d hammerstein-model ]; then "
            "  git clone https://github.com/lerugray/hammerstein-model.git; "
            "fi; "
            "cd hammerstein-model && git fetch --all && git checkout v0.2.6-retrain && git pull origin v0.2.6-retrain; "
            "command -v tmux >/dev/null || (apt-get update -qq >/dev/null 2>&1 && "
            "apt-get install -y -qq tmux >/dev/null 2>&1); "
            "command -v tmux >/dev/null && echo 'tmux: ok' || echo 'tmux: MISSING'; "
            "echo 'Repo ready.'"
        )
        rc, out = ssh_run(ip, port, bootstrap, timeout=240)
        if rc != 0:
            raise RuntimeError(f"Bootstrap failed (rc={rc}): {out[-500:]}")
        for ln in out.strip().splitlines()[-4:]:
            sys.stdout.flush(); print(f"  {ln}")

        sys.stdout.flush(); print()
        sys.stdout.flush(); print("  Planting HF token...")
        ssh_write_file(ip, port, "/workspace/.hf_token", hf_token)
        ssh_write_file(ip, port, "/workspace/.hf_repo_id", HF_REPO_ID, mode="644")

        sys.stdout.flush(); print()
        sys.stdout.flush(); print("  Launching run_v026_2_pod.sh in tmux session 'v026-2'...")
        launch = (
            "cd /workspace/hammerstein-model && "
            "tmux new-session -d -s v026-2 "
            "'bash training/24-7-variant/run_v026_2_pod.sh > /workspace/v026-2-run.log 2>&1' && "
            "tmux ls"
        )
        rc, out = ssh_run(ip, port, launch, timeout=30)
        if rc != 0:
            raise RuntimeError(f"tmux launch failed (rc={rc}): {out[-500:]}")
        sys.stdout.flush(); print(f"  {out.strip()}")

        sys.stdout.flush(); print()
        sys.stdout.flush(); print("  Polling for HF upload sentinel (train + GGUF + HF push ~40-45 min on A6000)...")
        sentinel_path = "/workspace/v026-2-hf-upload-done"
        deadline = time.time() + 90 * 60
        last_log_size = -1
        consecutive_errors = 0
        upload_done = False
        upload_meta_text = ""
        while time.time() < deadline:
            time.sleep(60)
            try:
                check = (
                    f"if [ -f {sentinel_path} ]; then echo READY; cat {sentinel_path}; "
                    f"else wc -c < /workspace/v026-2-run.log 2>/dev/null || echo 0; fi"
                )
                rc, out = ssh_run(ip, port, check, timeout=60)
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                sys.stdout.flush(); print(f"  poll error ({consecutive_errors}/5): {type(e).__name__}: {str(e)[:120]}")
                if consecutive_errors >= 5:
                    raise RuntimeError(f"5 consecutive polling errors; bailing.")
                continue

            out_s = (out or "").strip()
            if "READY" in out_s:
                sys.stdout.flush(); print(f"  HF upload sentinel present.")
                upload_meta_text = out_s
                upload_done = True
                break
            try:
                log_size = int(out_s.split()[-1])
            except (ValueError, IndexError):
                log_size = -1
            if log_size != last_log_size:
                try:
                    rc2, tail = ssh_run(ip, port, "tail -8 /workspace/v026-2-run.log 2>/dev/null", timeout=30)
                    sys.stdout.flush(); print(f"  [log size {log_size} bytes]")
                    for ln in (tail or "").strip().splitlines()[-4:]:
                        sys.stdout.flush(); print(f"    {ln}")
                except Exception as e:
                    sys.stdout.flush(); print(f"  [log size {log_size} bytes — tail fetch failed: {e}]")
                last_log_size = log_size

        if not upload_done:
            sys.stdout.flush(); print("  TIMEOUT — fetching tail of run log...")
            try:
                _, tail = ssh_run(ip, port, "tail -80 /workspace/v026-2-run.log 2>/dev/null", timeout=60)
                sys.stdout.flush(); print(tail)
            except Exception as e:
                sys.stdout.flush(); print(f"  (tail fetch failed: {e})")
            raise RuntimeError("Training + HF upload did not finish within 90 min.")

        expected_sha = ""
        for ln in upload_meta_text.splitlines():
            if ln.startswith("gguf_sha256="):
                expected_sha = ln.split("=", 1)[1].strip()

        sys.stdout.flush(); print()
        sys.stdout.flush(); print(f"  Downloading artifacts from HF private repo {HF_REPO_ID}...")
        try:
            from huggingface_hub import hf_hub_download
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "huggingface_hub>=0.23"], check=True)
            from huggingface_hub import hf_hub_download

        LOCAL_STORE.mkdir(parents=True, exist_ok=True)
        gguf_filename = "hammerstein-7b-v026-2-q5_k_m.gguf"
        adapter_filename = "lora-adapter-v026-2.tar.gz"

        sys.stdout.flush(); print(f"    pulling {gguf_filename} ...")
        gguf_local = hf_hub_download(
            repo_id=HF_REPO_ID,
            filename=gguf_filename,
            repo_type="model",
            local_dir=str(LOCAL_STORE),
        )
        try:
            hf_hub_download(repo_id=HF_REPO_ID, filename=adapter_filename,
                            repo_type="model", local_dir=str(LOCAL_STORE))
        except Exception as e:
            sys.stdout.flush(); print(f"    (adapter pull skipped: {e})")

        sys.stdout.flush(); print(f"  Verifying GGUF integrity (sha256)...")
        h = hashlib.sha256()
        with open(gguf_local, "rb") as f:
            while True:
                chunk = f.read(8 * 1024 * 1024)
                if not chunk: break
                h.update(chunk)
        local_sha = h.hexdigest()
        if expected_sha and local_sha != expected_sha:
            raise RuntimeError(f"GGUF integrity check FAILED. Expected {expected_sha}, got {local_sha}.")
        sys.stdout.flush(); print(f"  GGUF verified ({local_sha[:16]}...).")
        with open(gguf_local, "rb") as f:
            magic = f.read(4)
        if magic != b"GGUF":
            raise RuntimeError(f"GGUF magic bytes wrong: {magic!r}")
        sys.stdout.flush(); print(f"  Magic bytes OK.")
        sys.stdout.flush(); print()
        sys.stdout.flush(); print("  Artifacts retrieved + verified.")

    finally:
        if not args.no_terminate:
            try:
                terminate_pod(api_key, pod_id)
            except Exception as e:
                sys.stdout.flush(); print(f"  WARN: terminate failed: {e}")
                sys.stdout.flush(); print(f"  STOP THE POD MANUALLY in the RunPod dashboard. Pod id: {pod_id}")

    sys.stdout.flush(); print()
    sys.stdout.flush(); print("=== v0.2.6.2 pod fire complete ===")
    sys.stdout.flush(); print()
    sys.stdout.flush(); print(f"GGUF: {LOCAL_STORE}/hammerstein-7b-v026-2-q5_k_m.gguf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
