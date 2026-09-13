"""Console entrypoint: ``uv run continuum-api``.

Binds to the configured host, which configuration validation has already
guaranteed is loopback (A-03). Reload is opt-in and off by default: a
reloader restarts THIS process only -- it must never be able to affect the
worker, which is a separate service (ADR-0002 section 12).
"""

from __future__ import annotations

import argparse
import sys

import uvicorn
from continuum_config import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="continuum-api", description="Continuum Phase 0 API.")
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes.")
    args = parser.parse_args(argv)

    settings = get_settings()
    uvicorn.run(
        "continuum_api.asgi:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=args.reload,
        log_config=None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
