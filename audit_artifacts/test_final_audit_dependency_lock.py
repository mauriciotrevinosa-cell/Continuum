"""Additional adversarial coverage for the global dependency mutation lock."""

from __future__ import annotations

import threading
import uuid

from continuum_db.models import JobDependency
from continuum_db.session import session_scope
from continuum_jobs import DependencyCycleError, add_dependency, enqueue
from sqlalchemy import select

pytest_plugins = ["tests.conftest"]


def _jobs(session, count: int):
    rows = [
        enqueue(
            session,
            "synthetic.counted_work",
            payload={"units": 1, "audit": str(uuid.uuid4())},
        )[0]
        for _ in range(count)
    ]
    session.commit()
    return rows


def _race(settings, edges):
    barrier = threading.Barrier(len(edges), timeout=20)
    committed = []
    errors = []
    guard = threading.Lock()

    def mutate(edge):
        try:
            barrier.wait()
            with session_scope(settings) as session:
                add_dependency(session, *edge)
            with guard:
                committed.append(edge)
        except BaseException as exc:
            with guard:
                errors.append(exc)

    threads = [threading.Thread(target=mutate, args=(edge,), daemon=True) for edge in edges]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert all(not thread.is_alive() for thread in threads), "advisory-lock deadlock"
    return committed, errors


def _acyclic(edges):
    graph = {}
    for source, target in edges:
        graph.setdefault(source, set()).add(target)
    active, done = set(), set()

    def visit(node):
        if node in active:
            return False
        if node in done:
            return True
        active.add(node)
        valid = all(visit(child) for child in graph.get(node, ()))
        active.remove(node)
        done.add(node)
        return valid

    return all(visit(node) for node in graph)


def test_concurrent_four_and_eight_node_cycles_are_serialized(clean_jobs, db_settings) -> None:
    for size in (4, 8):
        jobs = _jobs(clean_jobs, size)
        proposed = [(jobs[i].id, jobs[(i + 1) % size].id) for i in range(size)]
        committed, errors = _race(db_settings, proposed)
        assert len(committed) == size - 1
        assert len(errors) == 1 and isinstance(errors[0], DependencyCycleError)
        clean_jobs.expire_all()
        persisted = set(
            clean_jobs.execute(select(JobDependency.job_id, JobDependency.depends_on_job_id))
        )
        assert _acyclic(persisted)


def test_concurrent_valid_mutations_all_commit_without_deadlock(clean_jobs, db_settings) -> None:
    jobs = _jobs(clean_jobs, 10)
    proposed = [(jobs[i].id, jobs[i + 5].id) for i in range(5)]
    committed, errors = _race(db_settings, proposed)
    assert set(committed) == set(proposed)
    assert errors == []


def test_rejected_transaction_rollback_releases_lock(clean_jobs, db_settings) -> None:
    a, b, c, d = _jobs(clean_jobs, 4)
    add_dependency(clean_jobs, a.id, b.id)
    clean_jobs.commit()
    try:
        add_dependency(clean_jobs, b.id, a.id)
    except DependencyCycleError:
        clean_jobs.rollback()
    else:
        raise AssertionError("cycle unexpectedly accepted")

    # A fresh process/transaction must immediately acquire the same lock.
    with session_scope(db_settings) as other:
        add_dependency(other, c.id, d.id)
