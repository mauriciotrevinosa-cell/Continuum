"""Configure Continuum's local or remote ComfyUI page backend in .env.

Examples:

    uv run --no-sync python scripts/configure_comfy.py \
        --local-url http://127.0.0.1:8188 \
        --checkpoint my-model.safetensors --version v1 \
        --sha256 <64-hex> --license "model license" --source https://example.invalid/model

    uv run --no-sync python scripts/configure_comfy.py \
        --remote-url https://random.trycloudflare.com \
        --checkpoint my-model.safetensors --version v1 \
        --sha256 <64-hex> --license "model license" --source https://example.invalid/model

Only CONTINUUM_COMFY_* keys are touched. The local .env is gitignored.
Restart the API and worker after changing these values.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_ENV = REPO / ".env"
EXAMPLE_ENV = REPO / ".env.example"

KEYS = {
    "local_url": "CONTINUUM_COMFY_LOCAL_URL",
    "remote_url": "CONTINUUM_COMFY_REMOTE_URL",
    "checkpoint": "CONTINUUM_COMFY_CHECKPOINT",
    "version": "CONTINUUM_COMFY_CHECKPOINT_VERSION",
    "sha256": "CONTINUUM_COMFY_CHECKPOINT_SHA256",
    "license": "CONTINUUM_COMFY_CHECKPOINT_LICENSE",
    "source": "CONTINUUM_COMFY_CHECKPOINT_SOURCE",
    "timeout": "CONTINUUM_COMFY_TIMEOUT_SECONDS",
    "allow_source_excerpts": "CONTINUUM_COMFY_REMOTE_ALLOW_SOURCE_EXCERPTS",
}


def _set(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    pattern = re.compile(rf"(?m)^{re.escape(key)}=.*$")
    if pattern.search(text):
        return pattern.sub(line, text, count=1)
    suffix = "" if text.endswith("\n") else "\n"
    return f"{text}{suffix}{line}\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--local-url")
    parser.add_argument("--remote-url")
    parser.add_argument("--checkpoint")
    parser.add_argument("--version")
    parser.add_argument("--sha256")
    parser.add_argument("--license")
    parser.add_argument("--source")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--allow-source-excerpts", action="store_true")
    parser.add_argument("--deny-source-excerpts", action="store_true")
    parser.add_argument("--clear-local", action="store_true")
    parser.add_argument("--clear-remote", action="store_true")
    args = parser.parse_args(argv)

    if args.allow_source_excerpts and args.deny_source_excerpts:
        parser.error("choose only one of --allow-source-excerpts / --deny-source-excerpts")
    if args.sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", args.sha256):
        parser.error("--sha256 must be exactly 64 hexadecimal characters")
    if args.timeout is not None and args.timeout <= 0:
        parser.error("--timeout must be positive")

    env = args.env.resolve()
    if not env.exists():
        if not EXAMPLE_ENV.exists():
            raise SystemExit(f"{env} does not exist and .env.example is unavailable")
        shutil.copyfile(EXAMPLE_ENV, env)
        print(f"created {env} from .env.example")

    changes: dict[str, str] = {}
    for field in (
        "local_url",
        "remote_url",
        "checkpoint",
        "version",
        "sha256",
        "license",
        "source",
    ):
        value = getattr(args, field)
        if value is not None:
            changes[KEYS[field]] = value.strip()
    if args.timeout is not None:
        changes[KEYS["timeout"]] = str(args.timeout)
    if args.clear_local:
        changes[KEYS["local_url"]] = ""
    if args.clear_remote:
        changes[KEYS["remote_url"]] = ""
    if args.allow_source_excerpts:
        changes[KEYS["allow_source_excerpts"]] = "true"
    elif args.deny_source_excerpts:
        changes[KEYS["allow_source_excerpts"]] = "false"

    if not changes:
        parser.error("no ComfyUI setting was requested")

    text = env.read_text(encoding="utf-8")
    for key, value in changes.items():
        text = _set(text, key, value)
    env.write_text(text, encoding="utf-8")

    print("updated ComfyUI settings:")
    for key, value in changes.items():
        shown = value if key not in {KEYS["remote_url"]} else value.split("?", 1)[0]
        print(f"  {key}={shown}")
    print("restart continuum-api and continuum-worker, then reload Manga production")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
