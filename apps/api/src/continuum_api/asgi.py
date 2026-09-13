"""ASGI entrypoint for uvicorn."""

from __future__ import annotations

from continuum_api.main import create_app

app = create_app()
