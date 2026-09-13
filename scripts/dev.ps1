# Continuum Phase 0 - start the local stack (Windows).
#
# Three processes, deliberately separate (ADR-0002 section 12):
#   db     PostgreSQL + pgvector, in Docker (D-03: the DATABASE ONLY)
#   api    FastAPI, native
#   worker standalone, native -- NEVER a child of the API or the web server
#
# Each runs in its own window so closing one cannot take down the others.
# That is the whole point: closing the UI must not cancel worker jobs.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

Write-Host "==> Starting PostgreSQL (database only)" -ForegroundColor Cyan
docker compose up -d db
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker is not available. Install Docker Desktop, then re-run." -ForegroundColor Red
    exit 1
}

Write-Host "==> Waiting for the database to accept connections"
for ($i = 0; $i -lt 30; $i++) {
    docker compose exec -T db pg_isready -U continuum -d continuum *> $null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 2
}

Write-Host "==> Applying migrations"
uv run alembic upgrade head

Write-Host "==> Launching API and worker in separate windows" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$repo'; uv run continuum-api"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$repo'; uv run continuum-worker"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$repo'; pnpm dev:web"

Write-Host ""
Write-Host "  Web    http://127.0.0.1:3000"
Write-Host "  API    http://127.0.0.1:8000/health"
Write-Host ""
Write-Host "Close the web window: the worker keeps running. That is acceptance test 110.8."
