"""Acceptance 110.2 (health reachable) and 110.13 (no secrets in logs).

All of these run with the database DOWN, which is deliberate: ``/health``
must work when the database is broken, or it cannot help diagnose a broken
database.
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import pytest
from continuum_api import create_app
from continuum_config import Settings
from continuum_observability import configure_logging, secret_registry
from fastapi.testclient import TestClient


@pytest.fixture
def client(settings: Settings) -> TestClient:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


class TestHealthEndpoint:
    def test_health_is_reachable(self, client: TestClient) -> None:
        assert client.get("/health").status_code == 200

    def test_health_works_with_the_database_down(self, client: TestClient) -> None:
        """No PostgreSQL is running in this suite. /health must still answer."""
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert body["phase"] == "0"

    def test_health_reports_the_loopback_bind(self, client: TestClient) -> None:
        assert client.get("/health").json()["api_host"] == "127.0.0.1"

    def test_health_reports_free_local_as_the_default_profile(self, client: TestClient) -> None:
        assert client.get("/health").json()["production_profile"] == "FREE_LOCAL"

    def test_health_reports_only_local_free_providers(self, client: TestClient) -> None:
        providers = client.get("/health").json()["providers"]
        assert providers
        assert all(p["locality"] == "LOCAL" for p in providers)
        assert all(p["cost_class"] == "FREE" for p in providers)

    def test_health_reports_vault_protection_without_guessing(self, client: TestClient) -> None:
        """A-01: where OS hardening cannot be proven non-mutatively, the
        honest answer is not_verified."""
        protection = client.get("/health").json()["storage"]["vault_protection"]
        assert protection["status"] in {
            "verified_readonly",
            "not_hardened",
            "not_verified",
            "absent",
        }
        assert protection["informational_only"] is True

    def test_ready_reports_503_quickly_when_the_database_is_down(self, client: TestClient) -> None:
        """A readiness probe that hangs is useless. It must fail fast and say
        what to do about it."""
        response = client.get("/ready")
        assert response.status_code == 503
        body = response.json()
        assert body["ready"] is False
        assert body["database"]["reachable"] is False
        assert "docker compose" in (body["detail"] or "")


class TestApiSurfaceIsPhaseZeroOnly:
    def test_no_endpoint_accepts_a_filesystem_path(self, client: TestClient) -> None:
        """F-50: a path parameter is a directory-traversal machine no matter
        how carefully it validates."""
        spec = client.get("/openapi.json").json()
        offenders: list[str] = []
        for path, operations in spec["paths"].items():
            for method, operation in operations.items():
                for parameter in operation.get("parameters", []):
                    name = parameter["name"].lower()
                    if name in {"path", "file", "filepath", "filename", "dir", "directory"}:
                        offenders.append(f"{method.upper()} {path} -> {parameter['name']}")
        assert offenders == [], f"filesystem path parameters found: {offenders}"

    def test_surface_is_limited_to_health_jobs_workers(self, client: TestClient) -> None:
        """No Library, Reader, Story Studio or Visual Lab routes in Phase 0."""
        paths = set(client.get("/openapi.json").json()["paths"])
        assert paths == {
            "/health",
            "/ready",
            "/jobs",
            "/jobs/{job_id}",
            "/jobs/{job_id}/blocked-reason",
            "/jobs/{job_id}/cancel",
            "/jobs/{job_id}/pause",
            "/jobs/{job_id}/resume",
            "/jobs/{job_id}/retry",
            "/workers",
            "/workers/reap",
            "/workers/{worker_id}/drain",
        }

    def test_cors_is_not_a_wildcard(self, settings: Settings) -> None:
        app = create_app(settings)
        cors = [m for m in app.user_middleware if "CORS" in str(m.cls)]
        assert cors, "CORS middleware is not installed"
        assert "*" not in cors[0].kwargs["allow_origins"]


class TestLoopbackOnly:
    @pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.50", "::", "10.0.0.1"])
    def test_non_loopback_bind_is_rejected_by_configuration(
        self, data_home: Path, vault_root: Path, host: str
    ) -> None:
        """A-03: there is deliberately no dormant 'bind to LAN if auth exists'
        path, because auth does not exist yet."""
        with pytest.raises(ValueError, match="loopback"):
            Settings(
                _env_file=None,
                data_home=str(data_home),
                source_vault_root=str(vault_root),
                api_host=host,
            )

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
    def test_loopback_is_accepted(self, data_home: Path, vault_root: Path, host: str) -> None:
        assert Settings(_env_file=None, data_home=str(data_home), api_host=host).api_host == host


class TestSecretsNeverLeak:
    SENTINEL = "s3ntinel-not-a-real-password"

    def test_health_body_contains_no_credential(self, client: TestClient) -> None:
        assert "continuum_local_dev" not in client.get("/health").text

    def test_settings_dump_masks_the_database_url(self, settings: Settings) -> None:
        assert settings.safe_dump()["database_url"] == "**********"

    def test_secret_str_does_not_repr_its_value(self, settings: Settings) -> None:
        assert "continuum_local_dev" not in repr(settings.database_url)
        assert "continuum_local_dev" not in str(settings.database_url)

    def test_full_config_dump_at_debug_leaks_nothing(
        self, data_home: Path, vault_root: Path
    ) -> None:
        """110.13: dump the effective config and raise at DEBUG, then assert
        no sentinel appears in any handler output."""
        buffer = io.StringIO()
        configure_logging("DEBUG", stream=buffer)
        Settings(
            _env_file=None,
            data_home=str(data_home),
            source_vault_root=str(vault_root),
            database_url=f"postgresql+psycopg://app:{self.SENTINEL}@127.0.0.1:5433/continuum",
        )

        log = logging.getLogger("continuum.test")
        log.debug("config dump: %s", {"database_url": f"postgres://u:{self.SENTINEL}@h/db"})
        log.info("bare secret in a message: %s", self.SENTINEL)
        try:
            raise RuntimeError(f"failure containing {self.SENTINEL}")
        except RuntimeError:
            log.exception("job failed")

        output = buffer.getvalue()
        assert output, "nothing was logged; the assertion would be vacuous"
        assert self.SENTINEL not in output, "a registered secret reached the log"
        assert "[REDACTED]" in output

    def test_redaction_covers_unregistered_but_recognisable_shapes(self) -> None:
        """Pattern redaction catches secrets this process never loaded --
        e.g. a token pasted into an error message by a dependency."""
        buffer = io.StringIO()
        configure_logging("DEBUG", stream=buffer)
        logging.getLogger("continuum.test").info(
            "upstream said: sk-abcdefghijklmnopqrstuvwxyz012345 and ghp_ABCDEFGHIJKLMNOPQRST123456"
        )
        output = buffer.getvalue()
        assert "sk-abcdefghijklmnopqrstuvwxyz012345" not in output
        assert "ghp_ABCDEFGHIJKLMNOPQRST123456" not in output

    def test_log_output_is_structured_json(self) -> None:
        buffer = io.StringIO()
        configure_logging("INFO", stream=buffer)
        logging.getLogger("continuum.test").info("structured", extra={"job_id": "abc"})
        record = json.loads(buffer.getvalue().strip().splitlines()[-1])
        assert record["message"] == "structured"
        assert record["job_id"] == "abc"
        assert record["level"] == "INFO"

    def teardown_method(self) -> None:
        secret_registry.clear()


class TestCorrelationIds:
    def test_response_carries_a_correlation_id(self, client: TestClient) -> None:
        assert client.get("/health").headers.get("x-correlation-id")

    def test_inbound_correlation_id_is_continued(self, client: TestClient) -> None:
        """The id must survive request -> job -> worker, so an inbound one is
        adopted rather than replaced (F-71)."""
        response = client.get("/health", headers={"x-correlation-id": "trace-me-123"})
        assert response.headers["x-correlation-id"] == "trace-me-123"
