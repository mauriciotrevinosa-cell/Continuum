"""Bootstrap an ephemeral ComfyUI GPU worker in a Linux notebook session.

This is intended for an interactive, user-opened GPU notebook (Kaggle is the
primary free option). It does not create an account, allocate a GPU, or bypass
provider quotas. It installs ComfyUI in the current session, downloads the
creator-selected model files, starts the local Comfy API and exposes it through
an ephemeral Cloudflare Quick Tunnel for Continuum's COMFY_REMOTE backend.

The tunnel is public and temporary. Use it only while actively calibrating,
never expose the Source Vault, and stop the notebook when finished.

Shutdown is graceful: Ctrl+C writes a lightweight recovery bundle under
``/kaggle/working`` with logs, model hashes/revisions and generated Comfy output
before terminating ComfyUI and the tunnel. The bundle still needs to be
preserved/downloaded before ending the notebook accelerator session.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
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

# Audited baseline for The Arrivals' first real visual calibration pass. Manual
# arguments remain supported so this does not make Continuum model-specific.
CALIBRATION_PRESETS: dict[str, dict[str, str]] = {
    "animagine-xl-4.0": {
        "checkpoint_url": (
            "https://huggingface.co/cagliostrolab/animagine-xl-4.0/resolve/main/"
            "animagine-xl-4.0.safetensors?download=true"
        ),
        "checkpoint_name": "animagine-xl-4.0.safetensors",
        "checkpoint_sha256": "1d5b43ff75b6ab598502d4c779d2fbfa3dceca51c60c3b609640a60772333916",
        "version": "4.0",
        "license": "openrail++",
        "source": "https://huggingface.co/cagliostrolab/animagine-xl-4.0",
        "ipadapter_model_url": (
            "https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/"
            "ip-adapter-plus_sdxl_vit-h.safetensors"
        ),
        "ipadapter_model_name": "ip-adapter-plus_sdxl_vit-h.safetensors",
        "ipadapter_sha256": "3f5062b8400c94b7159665b21ba5c62acdcd7682262743d7f2aefedef00e6581",
        "clip_vision_url": (
            "https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/"
            "model.safetensors"
        ),
        "clip_vision_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
        "clip_vision_sha256": "6ca9667da1ca9e0b0f75e46bb030f7e011f44f86cbfb8d5a36590fcd7507b030",
    }
}


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


def verify_sha256(path: Path, expected: str, label: str) -> str:
    actual = sha256(path)
    if expected and actual != expected.lower():
        raise RuntimeError(
            f"{label} SHA-256 mismatch: expected {expected.lower()}, received {actual}"
        )
    if expected:
        print(f"verified {label} SHA-256: {actual}")
    return actual


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


def _resolve_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict[str, str]:
    preset = CALIBRATION_PRESETS.get(args.preset or "", {})
    for field in (
        "checkpoint_url",
        "checkpoint_name",
        "version",
        "license",
        "source",
        "ipadapter_model_url",
        "ipadapter_model_name",
        "clip_vision_url",
        "clip_vision_name",
    ):
        if not getattr(args, field) and preset.get(field):
            setattr(args, field, preset[field])

    required = ("checkpoint_url", "checkpoint_name", "version", "license", "source")
    missing = [field for field in required if not getattr(args, field)]
    if missing:
        flags = ", ".join("--" + field.replace("_", "-") for field in missing)
        parser.error("missing required model arguments: " + flags)
    return preset


def _write_recovery_bundle(root: Path, endpoint: str, session_log: Path) -> None:
    """Best-effort checkpoint before an ephemeral notebook is stopped."""
    try:
        from scripts.kaggle_session_checkpoint import create_bundle
    except ModuleNotFoundError:
        # The setup script is often uploaded by itself into Kaggle. Import the
        # sibling helper when present, otherwise do not make shutdown fragile.
        helper = Path(__file__).resolve().with_name("kaggle_session_checkpoint.py")
        if not helper.exists():
            print("Recovery helper not present; no recovery bundle was written.")
            return
        import importlib.util

        spec = importlib.util.spec_from_file_location("kaggle_session_checkpoint", helper)
        if spec is None or spec.loader is None:
            print("Recovery helper could not be loaded; no recovery bundle was written.")
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        create_bundle = module.create_bundle

    try:
        archive = create_bundle(
            root,
            Path("/kaggle/working"),
            session_log=session_log,
            endpoint=endpoint,
        )
    except Exception as exc:  # shutdown must continue even if checkpointing fails
        print(f"Recovery bundle failed: {type(exc).__name__}: {exc}")
        return
    print(f"Recovery bundle ready: {archive}")
    print("Download/preserve it before stopping the Kaggle accelerator session.")


def _terminate(process: subprocess.Popen[str] | subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preset", choices=tuple(CALIBRATION_PRESETS))
    parser.add_argument("--checkpoint-url")
    parser.add_argument("--checkpoint-name")
    parser.add_argument("--version")
    parser.add_argument("--license")
    parser.add_argument("--source")
    parser.add_argument("--ipadapter-model-url", default="")
    parser.add_argument("--ipadapter-model-name", default="")
    parser.add_argument("--clip-vision-url", default="")
    parser.add_argument("--clip-vision-name", default="")
    parser.add_argument("--workdir", type=Path, default=Path("/kaggle/working/continuum-comfy"))
    parser.add_argument("--allow-cpu", action="store_true")
    args = parser.parse_args(argv)
    preset = _resolve_args(args, parser)

    if not args.allow_cpu and shutil.which("nvidia-smi") is None:
        parser.error("no NVIDIA GPU runtime detected; enable a GPU in the notebook first")
    if bool(args.ipadapter_model_url) != bool(args.ipadapter_model_name):
        parser.error("IP-Adapter URL and name must be supplied together")
    if bool(args.clip_vision_url) != bool(args.clip_vision_name):
        parser.error("CLIP Vision URL and name must be supplied together")

    root = args.workdir.resolve()
    comfy = root / "ComfyUI"
    session_log = root / "session.log"
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
    checkpoint_sha = verify_sha256(
        checkpoint, preset.get("checkpoint_sha256", ""), "checkpoint"
    )

    if args.ipadapter_model_url:
        ip_path = comfy / "models" / "ipadapter" / args.ipadapter_model_name
        download(args.ipadapter_model_url, ip_path)
        verify_sha256(ip_path, preset.get("ipadapter_sha256", ""), "IP-Adapter")
    if args.clip_vision_url:
        clip_path = comfy / "models" / "clip_vision" / args.clip_vision_name
        download(args.clip_vision_url, clip_path)
        verify_sha256(clip_path, preset.get("clip_vision_sha256", ""), "CLIP Vision")

    cloudflared = root / "cloudflared"
    download(CLOUDFLARED_URL, cloudflared)
    cloudflared.chmod(0o755)

    log_stream = session_log.open("a", encoding="utf-8", buffering=1)
    comfy_process: subprocess.Popen[str] | None = None
    tunnel: subprocess.Popen[str] | None = None
    tunnel_url = ""
    exit_code = 1
    try:
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
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            text=True,
        )
        wait_for_comfy()
        tunnel = subprocess.Popen(
            [str(cloudflared), "tunnel", "--url", "http://127.0.0.1:8188"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert tunnel.stdout is not None
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            line = tunnel.stdout.readline()
            if line:
                print(line.rstrip())
                log_stream.write("[cloudflared] " + line)
                match = TUNNEL_PATTERN.search(line)
                if match:
                    tunnel_url = match.group(0)
                    break
            elif tunnel.poll() is not None:
                break
        if not tunnel_url:
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
        print("Keep this cell/session running while Continuum renders.")
        print("Ctrl+C performs a graceful stop and writes a recovery bundle first.")

        while comfy_process.poll() is None and tunnel.poll() is None:
            time.sleep(5)
        exit_code = 1
    except KeyboardInterrupt:
        print("\nGraceful stop requested; stopping workloads before checkpointing...")
        exit_code = 0
    finally:
        _terminate(tunnel)
        _terminate(comfy_process)
        with contextlib.suppress(Exception):
            log_stream.flush()
        log_stream.close()
        _write_recovery_bundle(root, tunnel_url, session_log)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
