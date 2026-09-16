"""Bootstrap an ephemeral ComfyUI GPU worker in a Linux notebook session.

This is intended for an interactive, user-opened GPU notebook (Kaggle is the
primary free option). It does not create an account, allocate a GPU, or bypass
provider quotas. It installs ComfyUI in the current session, downloads the
creator-selected model files, starts the local Comfy API and exposes it through
an ephemeral Cloudflare Quick Tunnel for Continuum's COMFY_REMOTE backend.

The tunnel is public and temporary. Use it only while actively calibrating,
never expose the Source Vault, and stop the notebook when finished.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

COMFY_REPO = "https://github.com/Comfy-Org/ComfyUI.git"
IPADAPTER_REPO = "https://github.com/cubiq/ComfyUI_IPAdapter_plus.git"
CLOUDFLARED_URL = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
)
TUNNEL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def run(*args: str, cwd: Path | None = None) -> None:
    print("+", " ".join(args))
    subprocess.run(args, cwd=cwd, check=True)


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size:
        print(f"already present: {destination}")
        return
    print(f"downloading {url} -> {destination}")
    with urllib.request.urlopen(url, timeout=120) as response, destination.open("wb") as target:
        shutil.copyfileobj(response, target)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def wait_for_comfy(timeout: float = 180.0) -> None:
    deadline = time.monotonic() + timeout
    url = "http://127.0.0.1:8188/object_info"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    print("ComfyUI API is ready")
                    return
        except OSError:
            pass
        time.sleep(2)
    raise RuntimeError("ComfyUI did not become ready within 180 seconds")


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--checkpoint-url", required=True)
    parser.add_argument("--checkpoint-name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--license", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--ipadapter-model-url", default="")
    parser.add_argument("--ipadapter-model-name", default="")
    parser.add_argument("--clip-vision-url", default="")
    parser.add_argument("--clip-vision-name", default="")
    parser.add_argument("--workdir", type=Path, default=Path("/kaggle/working/continuum-comfy"))
    parser.add_argument("--allow-cpu", action="store_true")
    args = parser.parse_args(argv)

    if not args.allow_cpu and shutil.which("nvidia-smi") is None:
        parser.error("no NVIDIA GPU runtime detected; enable a GPU in the notebook first")
    if bool(args.ipadapter_model_url) != bool(args.ipadapter_model_name):
        parser.error("IP-Adapter URL and name must be supplied together")
    if bool(args.clip_vision_url) != bool(args.clip_vision_name):
        parser.error("CLIP Vision URL and name must be supplied together")

    root = args.workdir.resolve()
    comfy = root / "ComfyUI"
    if not (comfy / ".git").exists():
        root.mkdir(parents=True, exist_ok=True)
        run("git", "clone", "--depth", "1", COMFY_REPO, str(comfy))

    run(sys.executable, "-m", "pip", "install", "-r", str(comfy / "requirements.txt"))

    custom_nodes = comfy / "custom_nodes"
    custom_nodes.mkdir(parents=True, exist_ok=True)
    ip_node = custom_nodes / "ComfyUI_IPAdapter_plus"
    if not (ip_node / ".git").exists():
        run("git", "clone", "--depth", "1", IPADAPTER_REPO, str(ip_node))
    ip_requirements = ip_node / "requirements.txt"
    if ip_requirements.exists():
        run(sys.executable, "-m", "pip", "install", "-r", str(ip_requirements))

    checkpoint = comfy / "models" / "checkpoints" / args.checkpoint_name
    download(args.checkpoint_url, checkpoint)
    if args.ipadapter_model_url:
        download(
            args.ipadapter_model_url,
            comfy / "models" / "ipadapter" / args.ipadapter_model_name,
        )
    if args.clip_vision_url:
        download(
            args.clip_vision_url,
            comfy / "models" / "clip_vision" / args.clip_vision_name,
        )

    checkpoint_sha = sha256(checkpoint)
    cloudflared = root / "cloudflared"
    download(CLOUDFLARED_URL, cloudflared)
    cloudflared.chmod(0o755)

    comfy_process = subprocess.Popen(
        [
            sys.executable,
            "main.py",
            "--listen",
            "127.0.0.1",
            "--port",
            "8188",
            "--disable-api-nodes",
        ],
        cwd=comfy,
    )
    try:
        wait_for_comfy()
        tunnel = subprocess.Popen(
            [str(cloudflared), "tunnel", "--url", "http://127.0.0.1:8188"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        tunnel_url = ""
        assert tunnel.stdout is not None
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            line = tunnel.stdout.readline()
            if line:
                print(line.rstrip())
                match = TUNNEL_PATTERN.search(line)
                if match:
                    tunnel_url = match.group(0)
                    break
            elif tunnel.poll() is not None:
                break
        if not tunnel_url:
            tunnel.terminate()
            raise RuntimeError("Cloudflare Quick Tunnel did not return an endpoint")

        print("\n=== CONTINUUM REMOTE COMFY READY ===")
        print(f"Endpoint: {tunnel_url}")
        print(f"Checkpoint SHA-256: {checkpoint_sha}")
        print("\nOn the Windows Continuum machine, run:")
        command = [
            "uv run --no-sync python scripts/configure_comfy.py",
            f"--remote-url {ps_quote(tunnel_url)}",
            f"--checkpoint {ps_quote(args.checkpoint_name)}",
            f"--version {ps_quote(args.version)}",
            f"--sha256 {ps_quote(checkpoint_sha)}",
            f"--license {ps_quote(args.license)}",
            f"--source {ps_quote(args.source)}",
            "--deny-source-excerpts",
        ]
        print(" `\n    ".join(command))
        print("\nThen restart continuum-api and continuum-worker.")
        print("Keep this cell/session running while Continuum renders. Ctrl+C stops it.")

        while comfy_process.poll() is None and tunnel.poll() is None:
            time.sleep(5)
        return 1
    except KeyboardInterrupt:
        print("\nstopping ephemeral ComfyUI session")
        return 0
    finally:
        if "tunnel" in locals() and tunnel.poll() is None:
            tunnel.terminate()
        if comfy_process.poll() is None:
            comfy_process.terminate()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
