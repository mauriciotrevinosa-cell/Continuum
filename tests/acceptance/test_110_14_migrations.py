"""Acceptance 110.14 - migrations are clean and the strategy is documented.

Two of these run WITHOUT a database, because they are static properties of
the migration scripts: exactly one Alembic head, and a migration that
compiles to valid PostgreSQL DDL. The offline SQL render is genuinely
useful here -- it catches a malformed migration on a machine with no
PostgreSQL at all.

The upgrade/downgrade round trip requires a live database and skips
otherwise.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from tests.conftest import DEMO_VAULT, REPO_ROOT


def _alembic(*args: str, data_home: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "CONTINUUM_DATA_HOME": data_home,
        "CONTINUUM_SOURCE_VAULT_ROOT": str(DEMO_VAULT),
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=300,
    )


class TestMigrationsWithoutADatabase:
    """Static properties, checkable on a machine with no PostgreSQL."""

    def test_exactly_one_head(self, tmp_path) -> None:
        """A multi-head merge discovered at runtime is a very bad day."""
        result = _alembic("heads", data_home=str(tmp_path))
        assert result.returncode == 0, result.stderr
        heads = [line for line in result.stdout.splitlines() if line.strip()]
        assert len(heads) == 1, f"expected one Alembic head, got: {heads}"
        assert "(head)" in heads[0]

    def test_migration_compiles_to_valid_ddl(self, tmp_path) -> None:
        """Offline render: proves the script is well-formed without a server."""
        result = _alembic("upgrade", "head", "--sql", data_home=str(tmp_path))
        assert result.returncode == 0, result.stderr
        sql = result.stdout
        # Six application tables plus alembic_version.
        assert sql.count("CREATE TABLE") == 7, sql.count("CREATE TABLE")
        for table in ("job", "job_step", "job_checkpoint", "job_dependency", "job_event", "worker"):
            assert f"CREATE TABLE {table} " in sql, f"{table} missing from migration"

    def test_pgvector_extension_is_created(self, tmp_path) -> None:
        """Proves the database image is the one Continuum expects. No column
        in Phase 0 uses a vector type."""
        result = _alembic("upgrade", "head", "--sql", data_home=str(tmp_path))
        assert "CREATE EXTENSION IF NOT EXISTS vector" in result.stdout

    def test_no_vector_column_exists_in_phase_0(self, tmp_path) -> None:
        """F-47: embeddings arrive in Phase 3 as model-versioned ROWS, never
        as a column on a segment."""
        result = _alembic("upgrade", "head", "--sql", data_home=str(tmp_path))
        assert " vector(" not in result.stdout.lower()

    def test_critical_constraints_are_present(self, tmp_path) -> None:
        sql = _alembic("upgrade", "head", "--sql", data_home=str(tmp_path)).stdout
        # F-26: only one active job per dedupe key.
        assert "uq_job_dedupe_key_active" in sql
        assert "WHERE status NOT IN ('SUCCEEDED','FAILED_FINAL','CANCELLED')" in sql
        # F-24: a blocked job must say why.
        assert "ck_job_blocked_reason_iff_blocked" in sql
        # The idempotency boundary.
        assert "uq_job_step_job_id_unit_key" in sql
        # No self-dependency in the DAG.
        assert "ck_job_dependency_no_self_dependency" in sql


class TestSchemaIsPhaseZeroOnly:
    """ADR-0006 section 3 -- exactly six application tables, nothing else."""

    def test_exactly_six_application_tables(self) -> None:
        from continuum_db.models import Base

        assert set(Base.metadata.tables) == {
            "job",
            "job_step",
            "job_checkpoint",
            "job_dependency",
            "job_event",
            "worker",
        }

    def test_no_premature_domain_tables(self) -> None:
        """No franchise, asset, character, canon, project, branch, artifact,
        visual or provider table may exist in Phase 0."""
        from continuum_db.models import Base

        forbidden = {
            "franchise",
            "source_asset",
            "source_segment",
            "character",
            "character_version",
            "canon_claim",
            "event",
            "relationship",
            "location",
            "faction",
            "ability",
            "power_system",
            "item",
            "project",
            "branch",
            "story_bible",
            "artifact",
            "artifact_version",
            "generation_recipe",
            "visual_design",
            "moodboard",
            "provider",
            "approval_request",
            "segment_embedding",
        }
        leaked = set(Base.metadata.tables) & forbidden
        assert leaked == set(), (
            f"Phase 1+ tables leaked into Phase 0: {sorted(leaked)}. "
            "See docs/PHASE_0_SCOPE_LOCK.md."
        )


@pytest.mark.requires_db
class TestMigrationRoundTrip:
    """Needs a live database."""

    def test_clean_upgrade_then_downgrade_then_upgrade(self, db_settings) -> None:
        home = str(db_settings.data_home)
        assert _alembic("upgrade", "head", data_home=home).returncode == 0
        down = _alembic("downgrade", "base", data_home=home)
        assert down.returncode == 0, down.stderr
        up = _alembic("upgrade", "head", data_home=home)
        assert up.returncode == 0, up.stderr

    def test_current_matches_head_after_upgrade(self, db_settings) -> None:
        home = str(db_settings.data_home)
        _alembic("upgrade", "head", data_home=home)
        current = _alembic("current", data_home=home)
        assert "0001_phase0" in current.stdout
