#!/usr/bin/env bash
# Continuum Phase 0 - start the local stack (POSIX).
# See scripts/dev.ps1 for the rationale; the worker is a service, never a
# child of the API or the web server.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Starting PostgreSQL (database only)"
docker compose up -d db

echo "==> Waiting for the database"
for _ in $(seq 1 30); do
  docker compose exec -T db pg_isready -U continuum -d continuum >/dev/null 2>&1 && break
  sleep 2
done

echo "==> Applying migrations"
uv run alembic upgrade head

echo "==> Start these in three separate terminals:"
echo "      uv run continuum-api"
echo "      uv run continuum-worker"
echo "      pnpm dev:web"
