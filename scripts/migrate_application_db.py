"""Back up the application database, then bring it to the current schema.

The test database is migrated constantly and nobody minds. The application
database holds the creator's real catalogue, so this does the boring safe
things in order and refuses to guess:

1. names the database it is about to touch, and refuses the test database;
2. shows the current revision and everything still pending;
3. takes a ``pg_dump`` custom-format backup into ``backups/`` first;
4. applies the migrations;
5. verifies the revision moved and that the new tables and columns are there.

It is a **dry run by default**. Nothing is dumped and nothing is applied until
``--apply`` is given.

    uv run python scripts/migrate_application_db.py            # look only
    uv run python scripts/migrate_application_db.py --apply    # back up, migrate, verify
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
#: What migrations 0019 and 0020 are supposed to have produced. Checked after.
EXPECTED_TABLES = (
    "spend_budget",
    "spend_entry",
    "project_prop",
    "project_prop_reference",
    "training_dataset",
    "training_dataset_item",
    "training_run",
)
EXPECTED_COLUMNS = (("character_model_sheet_attempt", "variant_key"),)


def _url() -> str:
    from continuum_config import get_settings

    return get_settings().database_url.get_secret_value()


def _dsn(url: str) -> dict[str, str]:
    parts = urlsplit(url.replace("postgresql+psycopg://", "postgresql://"))
    return {
        "host": parts.hostname or "127.0.0.1",
        "port": str(parts.port or 5432),
        "user": parts.username or "",
        "password": parts.password or "",
        "dbname": (parts.path or "/").lstrip("/"),
    }


def _connect(url: str):  # type: ignore[no-untyped-def]
    import psycopg

    dsn = _dsn(url)
    return psycopg.connect(
        host=dsn["host"],
        port=int(dsn["port"]),
        user=dsn["user"],
        password=dsn["password"],
        dbname=dsn["dbname"],
        connect_timeout=5,
    )


def _revision(url: str) -> str | None:
    with _connect(url) as connection:
        row = connection.execute(
            "SELECT to_regclass('public.alembic_version') IS NOT NULL"
        ).fetchone()
        if not row or not row[0]:
            return None
        found = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        return str(found[0]) if found else None


def _heads() -> str:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip().split(" ")[0] if result.returncode == 0 else ""


def _backup(url: str, into: Path) -> Path:
    dsn = _dsn(url)
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    target = into / f"{dsn['dbname']}-{stamp}.dump"
    into.mkdir(parents=True, exist_ok=True)
    binary = shutil.which("pg_dump")
    if binary is None:
        raise SystemExit(
            "pg_dump is not on PATH, so no backup can be taken here.\n"
            "Take one yourself and re-run, for example:\n"
            f"  docker exec continuum-db pg_dump -U {dsn['user']} -F c -d {dsn['dbname']} "
            f"> backups/{target.name}"
        )
    environment = {**os.environ, "PGPASSWORD": dsn["password"]}
    with target.open("wb") as handle:
        result = subprocess.run(
            [
                binary,
                "-h",
                dsn["host"],
                "-p",
                dsn["port"],
                "-U",
                dsn["user"],
                "-F",
                "c",
                "-d",
                dsn["dbname"],
            ],
            stdout=handle,
            stderr=subprocess.PIPE,
            env=environment,
            check=False,
        )
    if result.returncode != 0 or target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        raise SystemExit("pg_dump failed; nothing was migrated:\n" + result.stderr.decode())
    return target


def _verify(url: str) -> list[str]:
    problems = []
    with _connect(url) as connection:
        for table in EXPECTED_TABLES:
            found = connection.execute(f"SELECT to_regclass('public.{table}')").fetchone()
            if not found or found[0] is None:
                problems.append(f"table {table} is missing")
        for table, column in EXPECTED_COLUMNS:
            found = connection.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = %s AND column_name = %s",
                (table, column),
            ).fetchone()
            if not found:
                problems.append(f"column {table}.{column} is missing")
    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="Back up and migrate for real.")
    parser.add_argument("--backups", type=Path, default=REPO_ROOT / "backups")
    args = parser.parse_args(argv)

    url = _url()
    dsn = _dsn(url)
    if dsn["dbname"].endswith("_test"):
        raise SystemExit(
            f"{dsn['dbname']} is the test database. This script is for the application "
            "database; the test one is migrated by the test suite."
        )
    print(f"database: {dsn['dbname']} at {dsn['host']}:{dsn['port']}")
    try:
        current = _revision(url)
    except Exception as exc:  # the message is the whole point of catching it
        raise SystemExit(
            f"Cannot reach the database ({type(exc).__name__}). Start it first:\n"
            "  docker compose up -d db\n"
            "then run this again."
        ) from exc
    head = _heads()
    print(f"current revision: {current or '(none - empty database)'}")
    print(f"head revision:    {head or '(unknown)'}")
    if current == head:
        problems = _verify(url)
        print(
            "already at head."
            + (
                " Verification found: " + "; ".join(problems)
                if problems
                else " Every expected table and column is present."
            )
        )
        return 1 if problems else 0
    if not args.apply:
        print(
            "\nDry run. Nothing was dumped and nothing was applied.\n"
            "Re-run with --apply to take a backup and migrate."
        )
        return 0

    backup = _backup(url, args.backups)
    print(f"backup written: {backup} ({backup.stat().st_size} bytes)")
    print("Keep this file out of Git; backups/ is ignored.")
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        check=False,
    )
    if upgrade.returncode != 0:
        raise SystemExit(
            "The upgrade failed. The database is unchanged if the failing migration ran "
            f"in a transaction; restore from {backup} if it did not:\n"
            f"  pg_restore -h {dsn['host']} -p {dsn['port']} -U {dsn['user']} "
            f"-d {dsn['dbname']} --clean {backup}"
        )
    after = _revision(url)
    problems = _verify(url)
    print(f"revision now: {after}")
    if problems:
        print("VERIFICATION FAILED: " + "; ".join(problems))
        return 1
    print("Every expected table and column is present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
