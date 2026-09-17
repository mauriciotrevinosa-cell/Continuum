"""Create a lightweight recovery bundle for a Kaggle ComfyUI session.

This does not attempt to snapshot GPU RAM or running processes. It records the
state needed to reproduce a session: logs, Comfy/IP-Adapter revisions, model
filenames and hashes, selected outputs, and a manifest with restart hints.

The bundle is written under /kaggle/working by default so it can be downloaded
or preserved with a Kaggle notebook version before the accelerator is stopped.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_rev(path: Path) -> str | None:
    if not (path / ".git").exists():
        return None
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=path, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _copy_if_present(source: Path, target_dir: Path) -> str | None:
    if not source.exists() or not source.is_file():
        return None
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    shutil.copy2(source, target)
    return str(target)


def create_bundle(
    workdir: Path,
    output_dir: Path,
    *,
    session_log: Path | None = None,
    endpoint: str = "",
) -> Path:
    workdir = workdir.resolve()
    comfy = workdir / "ComfyUI"
    recovery = output_dir.resolve() / "continuum-recovery"
    recovery.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    if session_log:
        copied_log = _copy_if_present(session_log.resolve(), recovery / "logs")
        if copied_log:
            copied.append(copied_log)

    output_files: list[dict[str, Any]] = []
    comfy_output = comfy / "output"
    if comfy_output.exists():
        preserved = recovery / "comfy-output"
        preserved.mkdir(parents=True, exist_ok=True)
        for path in sorted(comfy_output.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(comfy_output)
            destination = preserved / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            output_files.append(_file_record(destination, recovery))

    model_files: list[dict[str, Any]] = []
    for model_dir in ("checkpoints", "ipadapter", "clip_vision"):
        root = comfy / "models" / model_dir
        if not root.exists():
            continue
        for path in sorted(root.iterdir()):
            if path.is_file():
                model_files.append(
                    {
                        "kind": model_dir,
                        "name": path.name,
                        "bytes": path.stat().st_size,
                        "sha256": _sha256(path),
                    }
                )

    manifest = {
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
        "workdir": str(workdir),
        "endpoint": endpoint,
        "comfy_revision": _git_rev(comfy),
        "ipadapter_revision": _git_rev(comfy / "custom_nodes" / "ComfyUI_IPAdapter_plus"),
        "models": model_files,
        "outputs": output_files,
        "copied_files": copied,
        "restart": {
            "note": (
                "Recreate the Kaggle GPU session, rerun setup_comfy_free_gpu.py, then compare "
                "this manifest's revisions/model hashes before rendering further pages."
            )
        },
    }
    manifest_path = recovery / "session-state.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    archive = output_dir.resolve() / "continuum-recovery.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(recovery, arcname="continuum-recovery")
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path("/kaggle/working/continuum-comfy"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/kaggle/working"),
    )
    parser.add_argument("--session-log", type=Path)
    parser.add_argument("--endpoint", default="")
    args = parser.parse_args()

    archive = create_bundle(
        args.workdir,
        args.output_dir,
        session_log=args.session_log,
        endpoint=args.endpoint,
    )
    print(f"Recovery bundle: {archive}")
    print("Preserve/download that file before stopping the Kaggle session.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
