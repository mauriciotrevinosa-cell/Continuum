"""Invariant - worker-owned writes always assert ownership (final audit H-1/H-3).

The runtime guard lives in the database: :func:`continuum_jobs.transition`,
``fail_job`` and ``block_job`` lock the job row and refuse a caller whose
``owner`` no longer holds the lease, and ``renew_lease`` has no unowned form.
That guard only protects callers that *say* which worker they are. This
static check keeps every executing-worker call site saying so, so a future
edit cannot quietly reintroduce an unowned write on the paths that race.

No database is needed; this runs in the offline job too.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from continuum_jobs import renew_lease

from tests.conftest import REPO_ROOT

#: Modules whose job writes are made by the executing worker.
WORKER_OWNED_SOURCES: tuple[Path, ...] = (
    REPO_ROOT / "packages" / "jobs" / "src" / "continuum_jobs" / "execution.py",
    REPO_ROOT / "workers" / "runner" / "src" / "continuum_worker" / "main.py",
)

#: Status and failure writers that must be told the executing worker.
OWNED_WRITERS = frozenset({"transition", "fail_job", "block_job"})

PRODUCT_ROOTS: tuple[Path, ...] = (
    REPO_ROOT / "packages",
    REPO_ROOT / "apps",
    REPO_ROOT / "workers",
)


def _calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


def _name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _keywords(call: ast.Call) -> set[str]:
    return {k.arg for k in call.keywords if k.arg is not None}


def test_every_worker_owned_status_write_names_its_owner() -> None:
    missing: list[str] = []
    for path in WORKER_OWNED_SOURCES:
        for call in _calls(path):
            if _name(call) in OWNED_WRITERS and "owner" not in _keywords(call):
                missing.append(f"{path.relative_to(REPO_ROOT)}:{call.lineno} {_name(call)}()")
    assert missing == [], (
        "worker-owned status writes must pass owner=<worker id> so the database "
        f"can refuse a worker that lost the job: {missing}"
    )


def test_renew_lease_cannot_be_called_without_a_worker() -> None:
    parameter = inspect.signature(renew_lease).parameters["worker_id"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty, "renew_lease must have no unowned form"

    unowned: list[str] = []
    for root in PRODUCT_ROOTS:
        for path in root.rglob("*.py"):
            if ".venv" in path.parts or "node_modules" in path.parts:
                continue
            for call in _calls(path):
                if _name(call) == "renew_lease" and "worker_id" not in _keywords(call):
                    unowned.append(f"{path.relative_to(REPO_ROOT)}:{call.lineno}")
    assert unowned == [], f"renew_lease called without worker_id: {unowned}"


def test_the_executing_worker_never_bypasses_the_guard_with_a_raw_update() -> None:
    """A bulk ``update(Job)`` in the execution loop would write without the
    row lock and ownership proof every other write goes through."""
    execution = WORKER_OWNED_SOURCES[0]
    raw = [f"line {call.lineno}" for call in _calls(execution) if _name(call) == "update"]
    assert raw == [], f"raw UPDATE in the execution loop: {raw}"
