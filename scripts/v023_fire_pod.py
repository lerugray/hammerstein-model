#!/usr/bin/env python3
r"""v0.2.3 pod fire — local driver for autonomous RunPod training.

Lifecycle:
  1. Generate ephemeral ed25519 keypair at ~/.runpod-overnight/key
  2. Find an A5000-class GPU via RunPod GraphQL gpuTypes query
  3. podFindAndDeployOnDemand with PUBLIC_KEY env + 22/tcp port
  4. Poll for SSH endpoint (runtime.ports[22/tcp].publicPort + .ip)
  5. SSH in, clone repo (or pull), plant HF_TOKEN at /workspace/.hf_token
     via SSH stdin, then launch run_v023_pod.sh in a detached tmux session
  6. Poll for /workspace/v023-hf-upload-done sentinel (pod pushes the
     GGUF + LoRA tar to a private HF repo as the transfer channel)
  7. hf_hub_download GGUF + adapter to D:\hammerstein-store\models\v0.2.3\
     (sha256 + GGUF magic-byte verify)
  8. Terminate the pod
  9. Print Ollama deploy + eval commands for the local PC

Reads RUNPOD_API_KEY from hammerstein-model/.env.

Per-pod SSH avoids touching the account-level pubKey field (see memory
reference-runpod-per-pod-ssh). HF_TOKEN is planted by ssh_write_file
because container env from podFindAndDeployOnDemand only hits
/etc/environment (interactive PAM only) — invisible to ssh non-
interactive shells.
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

LOCAL_STORE = Path("D:/hammerstein-store/models/v0.2.3")

RUNPOD_API = "https://api.runpod.io/graphql"

# HuggingFace push-pull config. The pod pushes GGUF + LoRA tar to this
# private repo; the local driver pulls from it via huggingface_hub.
# Replaces scp after two consecutive Windows-side scp corruptions on
# 2026-05-23. HF transfer is chunked, checksummed, retryable.
HF_REPO_ID = "lerugray/hammerstein-7b-v023"
HF_TOKEN_PATH = Path.home() / ".cache" / "huggingface" / "token"


def load_hf_token() -> str:
    """Read the HF token from the standard CLI cache location. Never
    print or log the value. Returns empty string if unavailable so the
    caller can produce a useful error."""
    env = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if env:
        return env.strip()
    if HF_TOKEN_PATH.exists():
        return HF_TOKEN_PATH.read_text(encoding="utf-8").strip()
    return ""

# GPU type IDs we prefer, in order. A5000 SECURE was used for v0.2.2;
# 4090 also works. The script picks the first available.
PREFERRED_GPU_TYPES = [
    "RTX A5000",       # 24GB, secure, $0.16/hr — used for v0.2.2
    "RTX 4090",        # 24GB, secure, $0.34/hr
    "RTX A4500",       # 20GB, secure, $0.19/hr
    "RTX A6000",       # 48GB, secure, $0.33/hr
]

# RunPod template with PyTorch 2.4 + CUDA 12.4 baked in.
DEFAULT_TEMPLATE = "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"


# Force the driver's own stdout to UTF-8 with replace, so progress-bar
# bytes from the remote log don't choke local prints (Windows defaults
# stdout to cp1252 even when stdin is a pipe).
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
    """RunPod GraphQL call. Cloudflare WAF rejects requests without a
    real User-Agent (code 1010). Use Authorization: Bearer for auth."""
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
    """Generate fresh ed25519 if missing. Returns the public key string."""
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    if not KEY_PATH.exists():
        sys.stdout.flush(); print(f"  Generating ed25519 keypair at {KEY_PATH}...")
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(KEY_PATH), "-C", "v023-pod"],
            check=True,
        )
    return PUB_PATH.read_text(encoding="utf-8").strip()


def pick_gpu_types(api_key: str) -> list[tuple[str, str, float]]:
    """Query availability, return ALL preferred GPUs that have stock, in
    preference order. Returns list of (id, display_name, price)."""
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
    """Create the pod. Returns podId.

    NOTE: HF_TOKEN is NOT passed via the env block here. RunPod's API env
    vars only land in /etc/environment, which is read by PAM for
    interactive SSH logins but NOT by `ssh root@host 'cmd'` style
    non-interactive shells (which our tmux launch uses). The driver
    instead writes the token to /workspace/.hf_token via SSH stdin after
    bootstrap; the run script reads from there. See attempt 8 failure
    log + ssh_write_file() below."""
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
            "name": f"hammerstein-v023-{int(time.time())}",
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
    """Poll for runtime.ports[22/tcp].ip + publicPort. Returns (ip, port)."""
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
    """Write `content` to `remote_path` on the pod via SSH stdin. Used
    for the HF token and any other secret that must reach the pod
    without appearing in argv (visible to /proc on the remote)."""
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
    """Run a command on the pod over SSH. Forces UTF-8 decoding with
    `replace` to survive binary bytes in remote logs (progress bars from
    llama.cpp / training; nvidia-smi output)."""
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


def scp_back(ip: str, port: int, remote_path: str, local_path: Path) -> None:
    """scp a file from pod to local."""
    local_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "scp",
        "-i", str(KEY_PATH),
        "-P", str(port),
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        f"root@{ip}:{remote_path}",
        str(local_path),
    ]
    sys.stdout.flush(); print(f"  scp {remote_path} -> {local_path} ...")
    # 60 min — the v0.2.3 fire on 2026-05-23 transferred a ~5GB GGUF in ~28
    # minutes but Python's subprocess timeout fired right when scp was
    # finalizing the last bytes, killing the connection and leaving a
    # truncated file. Doubling to 60min gives generous margin.
    res = subprocess.run(cmd, timeout=3600)
    if res.returncode != 0:
        raise RuntimeError(f"scp failed (rc={res.returncode})")


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
    p.add_argument("--dry-run", action="store_true",
                   help="Pick GPU and print plan; don't fire.")
    p.add_argument("--no-terminate", action="store_true",
                   help="Leave pod running after artifacts are scp'd back.")
    args = p.parse_args()

    env = load_env()
    api_key = env.get("RUNPOD_API_KEY")
    if not api_key:
        sys.stdout.flush(); print(f"ERROR: RUNPOD_API_KEY not in {ENV_PATH}")
        return 1

    sys.stdout.flush(); print("=== v0.2.3 pod fire ===")
    sys.stdout.flush(); print(f"  Local store target: {LOCAL_STORE}")
    sys.stdout.flush(); print(f"  SSH key: {KEY_PATH}")
    sys.stdout.flush(); print()

    pubkey = ensure_ssh_keypair()
    gpu_candidates = pick_gpu_types(api_key)

    hf_token = load_hf_token()
    if not hf_token:
        raise RuntimeError(
            "HF token not found. Expected at ~/.cache/huggingface/token "
            "(login via `huggingface-cli login`) or HF_TOKEN env var. The "
            "pod needs this to push the GGUF to the private HF repo."
        )
    sys.stdout.flush(); print(f"  HF token loaded (will plant at /workspace/.hf_token post-bootstrap).")

    if args.dry_run:
        sys.stdout.flush(); print("\nDry-run complete. Would fire pod next.")
        return 0

    # Try each GPU candidate in order until one deploys.
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

        # Bootstrap remote: clone repo + ensure tmux is available. tmux is
        # the most reliable way to detach a long-running command from an
        # SSH session: `tmux new-session -d` returns immediately, fully
        # decoupled from the SSH channel.
        sys.stdout.flush(); print()
        sys.stdout.flush(); print("  Bootstrapping pod...")
        bootstrap = (
            "set -e; "
            "cd /workspace 2>/dev/null || cd ~; "
            "if [ ! -d hammerstein-model ]; then "
            "  git clone https://github.com/lerugray/hammerstein-model.git; "
            "fi; "
            "cd hammerstein-model && git fetch --all && git checkout master && git pull; "
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

        # Plant the HF token on the pod via SSH stdin. The run script reads
        # /workspace/.hf_token in step 5. Bypasses the broken
        # podFindAndDeployOnDemand env path (see fire_pod docstring).
        sys.stdout.flush(); print()
        sys.stdout.flush(); print("  Planting HF token at /workspace/.hf_token...")
        ssh_write_file(ip, port, "/workspace/.hf_token", hf_token)
        # Also plant the repo id so the run script doesn't need a fallback.
        ssh_write_file(ip, port, "/workspace/.hf_repo_id", HF_REPO_ID, mode="644")

        # Launch the training inside a detached tmux session. tmux is the
        # canonical "run this on a remote and disconnect" tool.
        sys.stdout.flush(); print()
        sys.stdout.flush(); print("  Launching run_v023_pod.sh in tmux session 'v023'...")
        launch = (
            "cd /workspace/hammerstein-model && "
            "tmux new-session -d -s v023 "
            "'bash training/24-7-variant/run_v023_pod.sh > /workspace/v023-run.log 2>&1' && "
            "tmux ls"
        )
        rc, out = ssh_run(ip, port, launch, timeout=30)
        if rc != 0:
            raise RuntimeError(f"tmux launch failed (rc={rc}): {out[-500:]}")
        sys.stdout.flush(); print(f"  {out.strip()}")

        # Poll for HF upload sentinel — the pod's run script uploads the
        # GGUF + LoRA tar to a private HF repo and writes
        # /workspace/v023-hf-upload-done when both are uploaded. This is
        # the scp-replacement after two Windows scp corruptions in a row.
        sys.stdout.flush(); print()
        sys.stdout.flush(); print("  Polling for HF upload sentinel (train + GGUF convert + HF push ~40-50 min)...")
        sentinel_path = "/workspace/v023-hf-upload-done"
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
                    f"else wc -c < /workspace/v023-run.log 2>/dev/null || echo 0; fi"
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
                    rc2, tail = ssh_run(ip, port, "tail -8 /workspace/v023-run.log 2>/dev/null", timeout=30)
                    sys.stdout.flush(); print(f"  [log size {log_size} bytes]")
                    for ln in (tail or "").strip().splitlines()[-4:]:
                        sys.stdout.flush(); print(f"    {ln}")
                except Exception as e:
                    sys.stdout.flush(); print(f"  [log size {log_size} bytes — tail fetch failed: {e}]")
                last_log_size = log_size

        if not upload_done:
            sys.stdout.flush(); print("  TIMEOUT — fetching tail of run log...")
            try:
                _, tail = ssh_run(ip, port, "tail -80 /workspace/v023-run.log 2>/dev/null", timeout=60)
                sys.stdout.flush(); print(tail)
            except Exception as e:
                sys.stdout.flush(); print(f"  (tail fetch failed: {e})")
            raise RuntimeError("Training + HF upload did not finish within 90 min.")

        # Parse the sentinel content for the GGUF sha256 (for integrity verify).
        expected_sha = ""
        for ln in upload_meta_text.splitlines():
            if ln.startswith("gguf_sha256="):
                expected_sha = ln.split("=", 1)[1].strip()

        # Pull GGUF + adapter via huggingface_hub. Token is read from the
        # standard cache location automatically; we never inline it here.
        sys.stdout.flush(); print()
        sys.stdout.flush(); print(f"  Downloading artifacts from HF private repo {HF_REPO_ID}...")
        try:
            from huggingface_hub import hf_hub_download
        except ImportError:
            sys.stdout.flush(); print("  huggingface_hub not installed locally; pip-installing...")
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "huggingface_hub>=0.23"], check=True)
            from huggingface_hub import hf_hub_download

        LOCAL_STORE.mkdir(parents=True, exist_ok=True)
        gguf_filename = "hammerstein-7b-v023-q5_k_m.gguf"
        adapter_filename = "lora-adapter-v023.tar.gz"

        sys.stdout.flush(); print(f"    pulling {gguf_filename} ...")
        gguf_local = hf_hub_download(
            repo_id=HF_REPO_ID,
            filename=gguf_filename,
            repo_type="model",
            local_dir=str(LOCAL_STORE),
        )
        sys.stdout.flush(); print(f"    pulling {adapter_filename} ...")
        try:
            hf_hub_download(
                repo_id=HF_REPO_ID,
                filename=adapter_filename,
                repo_type="model",
                local_dir=str(LOCAL_STORE),
            )
        except Exception as e:
            sys.stdout.flush(); print(f"    (adapter pull skipped: {e})")

        # Verify GGUF integrity by recomputing sha256 locally.
        sys.stdout.flush(); print(f"  Verifying GGUF integrity (sha256)...")
        h = hashlib.sha256()
        with open(gguf_local, "rb") as f:
            while True:
                chunk = f.read(8 * 1024 * 1024)
                if not chunk: break
                h.update(chunk)
        local_sha = h.hexdigest()
        if expected_sha and local_sha != expected_sha:
            raise RuntimeError(
                f"GGUF integrity check FAILED. Expected {expected_sha}, got {local_sha}."
            )
        sys.stdout.flush(); print(f"  GGUF verified ({local_sha[:16]}...).")
        # Also verify GGUF magic bytes, the failure mode we hit twice on scp.
        with open(gguf_local, "rb") as f:
            magic = f.read(4)
        if magic != b"GGUF":
            raise RuntimeError(f"GGUF magic bytes wrong: {magic!r} (expected b'GGUF')")
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
        else:
            sys.stdout.flush(); print(f"  Pod left running per --no-terminate. Pod id: {pod_id}")

    sys.stdout.flush(); print()
    sys.stdout.flush(); print("=== v0.2.3 pod fire complete ===")
    sys.stdout.flush(); print()
    sys.stdout.flush(); print(f"GGUF: {LOCAL_STORE}/hammerstein-7b-v023-q5_k_m.gguf")
    sys.stdout.flush(); print()
    sys.stdout.flush(); print("Next steps (local):")
    sys.stdout.flush(); print(f"  1. Build Modelfile.v023 (copy Modelfile.v022, point at the new GGUF)")
    sys.stdout.flush(); print(f"  2. ollama create hammerstein-7b-v023 -f deploy/Modelfile.v023")
    sys.stdout.flush(); print(f"  3. python scripts/v023_self_state_probe.py --model hammerstein-7b-v023 --tag v023-post-train")
    sys.stdout.flush(); print(f"  4. python scripts/v2_eval_failure_modes.py --model hammerstein-7b-v023 --tag v023-post-train")
    sys.stdout.flush(); print(f"  5. Compare to v0.2.2 baselines; deploy if win.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
