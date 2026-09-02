"""PostgreSQL dependency-DAG concurrency acceptance coverage.

Serial reachability is not enough: graph mutations must remain acyclic when
separate processes propose individually valid-looking edges concurrently.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from continuum_db.models import JobDependency
from continuum_db.session import session_scope
from continuum_jobs import DependencyCycleError, add_dependency, enqueue
from sqlalchemy import select


def _jobs(session, count: int, prefix: str):
    jobs = []
    for index in range(count):
        job, _ = enqueue(
            session,
            "synthetic.counted_work",
            payload={"units": 1, "marker": f"{prefix}-{index}"},
        )
        jobs.append(job)
    session.commit()
    return jobs


def _edges(session) -> set[tuple[uuid.UUID, uuid.UUID]]:
    return set(session.execute(select(JobDependency.job_id, JobDependency.depends_on_job_id)))


def _assert_acyclic(edges: set[tuple[uuid.UUID, uuid.UUID]]) -> None:
    adjacency: dict[uuid.UUID, set[uuid.UUID]] = {}
    for job_id, dependency_id in edges:
        adjacency.setdefault(job_id, set()).add(dependency_id)

    visiting: set[uuid.UUID] = set()
    visited: set[uuid.UUID] = set()

    def visit(node: uuid.UUID) -> None:
        if node in visiting:
            raise AssertionError(f"persisted dependency graph contains a cycle at {node}")
        if node in visited:
            return
        visiting.add(node)
        for dependency in adjacency.get(node, ()):
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in adjacency:
        visit(node)


def _concurrent_adds(db_settings, edges: list[tuple[uuid.UUID, uuid.UUID]]):
    ready = threading.Barrier(len(edges))
    errors: list[BaseException] = []
    committed: list[tuple[uuid.UUID, uuid.UUID]] = []
    guard = threading.Lock()

    def add(edge: tuple[uuid.UUID, uuid.UUID]) -> None:
        try:
            ready.wait(timeout=10)
            with session_scope(db_settings) as session:
                add_dependency(session, edge[0], edge[1])
            with guard:
                committed.append(edge)
        except BaseException as exc:
            with guard:
                errors.append(exc)

    threads = [threading.Thread(target=add, args=(edge,)) for edge in edges]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert all(not thread.is_alive() for thread in threads), "dependency mutation deadlocked"
    return committed, errors


def test_self_edge_is_rejected(clean_jobs) -> None:
    job = _jobs(clean_jobs, 1, "self")[0]
    with pytest.raises(DependencyCycleError):
        add_dependency(clean_jobs, job.id, job.id)


def test_serial_two_node_cycle_is_rejected(clean_jobs) -> None:
    a, b = _jobs(clean_jobs, 2, "serial-two")
    add_dependency(clean_jobs, a.id, b.id)
    clean_jobs.commit()
    with pytest.raises(DependencyCycleError):
        add_dependency(clean_jobs, b.id, a.id)


def test_serial_deep_cycle_is_rejected(clean_jobs) -> None:
    a, b, c, d, e = _jobs(clean_jobs, 5, "serial-deep")
    for dependent, dependency in ((a, b), (b, c), (c, d), (d, e)):
        add_dependency(clean_jobs, dependent.id, dependency.id)
    clean_jobs.commit()
    with pytest.raises(DependencyCycleError):
        add_dependency(clean_jobs, e.id, a.id)


def test_valid_diamond_is_accepted(clean_jobs) -> None:
    a, b, c, d = _jobs(clean_jobs, 4, "diamond")
    for dependent, dependency in ((a, b), (a, c), (b, d), (c, d)):
        add_dependency(clean_jobs, dependent.id, dependency.id)
    clean_jobs.commit()
    persisted = _edges(clean_jobs)
    assert len(persisted) == 4
    _assert_acyclic(persisted)


def test_concurrent_opposing_edges_cannot_both_commit(clean_jobs, db_settings) -> None:
    a, b = _jobs(clean_jobs, 2, "concurrent-two")
    proposed = [(a.id, b.id), (b.id, a.id)]

    committed, errors = _concurrent_adds(db_settings, proposed)

    assert len(committed) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], DependencyCycleError)
    clean_jobs.expire_all()
    persisted = _edges(clean_jobs)
    assert persisted == set(committed)
    _assert_acyclic(persisted)


def test_concurrent_three_edge_cycle_cannot_fully_commit(clean_jobs, db_settings) -> None:
    a, b, c = _jobs(clean_jobs, 3, "concurrent-three")
    proposed = [(a.id, b.id), (b.id, c.id), (c.id, a.id)]

    committed, errors = _concurrent_adds(db_settings, proposed)

    assert len(committed) == 2
    assert len(errors) == 1
    assert isinstance(errors[0], DependencyCycleError)
    clean_jobs.expire_all()
    persisted = _edges(clean_jobs)
    assert persisted == set(committed)
    _assert_acyclic(persisted)


def test_graph_remains_usable_after_concurrent_rejection(clean_jobs, db_settings) -> None:
    a, b, c, d = _jobs(clean_jobs, 4, "usable")
    committed, errors = _concurrent_adds(db_settings, [(a.id, b.id), (b.id, a.id)])
    assert len(committed) == 1 and len(errors) == 1

    # Add a fresh sink edge after the rejected transaction. The advisory lock
    # must have been released by rollback and the surviving DAG must remain
    # writable.
    clean_jobs.expire_all()
    add_dependency(clean_jobs, c.id, d.id)
    clean_jobs.commit()
    persisted = _edges(clean_jobs)
    assert set(committed).issubset(persisted)
    assert (c.id, d.id) in persisted
    _assert_acyclic(persisted)
