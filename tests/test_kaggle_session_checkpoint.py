from __future__ import annotations

import json
import tarfile
from pathlib import Path

from scripts.kaggle_session_checkpoint import create_bundle


def test_create_bundle_records_revisions_models_logs_and_outputs(tmp_path: Path) -> None:
    workdir = tmp_path / "continuum-comfy"
    comfy = workdir / "ComfyUI"
    (comfy / "models" / "checkpoints").mkdir(parents=True)
    (comfy / "models" / "ipadapter").mkdir(parents=True)
    (comfy / "models" / "clip_vision").mkdir(parents=True)
    (comfy / "output").mkdir(parents=True)

    (comfy / "models" / "checkpoints" / "demo.safetensors").write_bytes(b"checkpoint")
    (comfy / "models" / "ipadapter" / "ip.bin").write_bytes(b"ipadapter")
    (comfy / "models" / "clip_vision" / "clip.bin").write_bytes(b"clip")
    (comfy / "output" / "page.png").write_bytes(b"page")
    log = tmp_path / "session.log"
    log.write_text("hello\n", encoding="utf-8")

    archive = create_bundle(workdir, tmp_path, session_log=log, endpoint="https://example.test")

    recovery = tmp_path / "continuum-recovery"
    manifest = json.loads((recovery / "session-state.json").read_text(encoding="utf-8"))
    assert manifest["endpoint"] == "https://example.test"
    assert {row["kind"] for row in manifest["models"]} == {
        "checkpoints",
        "ipadapter",
        "clip_vision",
    }
    assert manifest["outputs"][0]["path"] == "comfy-output/page.png"
    assert (recovery / "logs" / "session.log").read_text(encoding="utf-8") == "hello\n"

    assert archive.exists()
    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
    assert "continuum-recovery/session-state.json" in names
    assert "continuum-recovery/comfy-output/page.png" in names
