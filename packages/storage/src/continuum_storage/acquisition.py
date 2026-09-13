"""Library acquisition: read its documents, run its safe CLI actions.

The acquisition engine is a separate local tool that owns the logic (what is
official, what is missing, which source may be used). It writes plain JSON
documents into a data directory. Continuum READS those documents and renders
them; it never re-implements the rules, so there is one source of truth.

Two boundaries are enforced here rather than by convention:

* **Read-only over the library.** The only filesystem writes this module can
  cause are the ones the acquisition CLI performs itself, and the verbs it
  may be asked to perform are an allowlist. ``--apply`` is absent from that
  allowlist, so nothing reachable from a browser can write into the Source
  Vault (ADR-0001: the vault is read-only to Continuum).
* **No caller-supplied paths.** The data directory comes from configuration.
  Document names are validated against a fixed tuple, so a request can never
  address an arbitrary file (F-50).

An absent or empty data directory is a valid state: a new user has no
library yet, and every reader returns ``None`` rather than raising.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "ACQUISITION_DOCUMENTS",
    "AcquisitionCliError",
    "AcquisitionDocument",
    "AcquisitionStore",
    "CliResult",
    "VaultChanges",
]

#: Every document the acquisition engine publishes. A name outside this
#: tuple cannot be read, which is what makes document names safe to accept
#: from a route.
ACQUISITION_DOCUMENTS: tuple[str, ...] = (
    "works-catalog.json",
    "vault-layout.json",
    "vault-coverage.json",
    "acquisition-queue.json",
    "update-watch.json",
    "REVIEW_REQUIRED.json",
    "sources.json",
    "ingest-last.json",
)

#: CLI verbs the API may run, and the sub-verbs allowed for each.
#: Deliberately absent: anything that writes into the Vault. `scaffold` is
#: present only because it is a dry run without ``--apply``.
ALLOWED_CLI: dict[str, frozenset[str]] = {
    "sources": frozenset({"add", "list", "remove", "test", "enable", "disable", "unofficial"}),
    "coverage": frozenset(),
    "scaffold": frozenset(),
    "ingest": frozenset(),
    "verify-vault": frozenset(),
    "status": frozenset(),
}

#: Flags the API may pass through. An unknown flag is refused rather than
#: forwarded, so a new destructive flag cannot arrive by surprise.
ALLOWED_FLAGS: frozenset[str] = frozenset(
    {
        "--id",
        "--name",
        "--adapter",
        "--search",
        "--watch-url",
        "--access",
        "--language",
        "--role",
        "--download-permitted",
        "--note",
        "--no-test",
        "--replace",
        "--json",
        "--all",
        "--offline",
        "--no-rescan",
        "--details",
        "--limit",
        "--no-anilist",
        # Read-only and cheaper: a library refresh does not need content hashes,
        # which exist for duplicate detection and can take minutes after a large
        # download. Coverage is decided by what is where, not by bytes.
        "--no-hash",
    }
)

#: How long a Vault change check is trusted before it is repeated. Every
#: screen asks; walking the directory tree on each request would make page
#: cost scale with library size.
VAULT_CHECK_TTL_SECONDS = 15.0
#: A bound on the directories one check will look at, so a pathological tree
#: degrades to "unknown" instead of a slow page.
VAULT_CHECK_MAX_DIRS = 50_000


class AcquisitionCliError(RuntimeError):
    """The acquisition CLI is not configured, or the action is not allowed."""


@dataclass(frozen=True, slots=True)
class AcquisitionDocument:
    """One document's availability, for diagnostics in the UI."""

    name: str
    present: bool
    generated_at: str | None
    size_bytes: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class VaultChanges:
    """Whether the Vault changed after the documents describing it were made.

    Decided from directory modification times only - no file is opened, and
    nothing is written. Adding, removing or renaming an entry updates its
    parent directory's time, which is exactly the event that makes a coverage
    report stale.
    """

    checked: bool
    changed: bool = False
    #: Top-level folder names whose subtree changed (a family, usually).
    folders: tuple[str, ...] = ()
    #: Top-level folders that did not exist when the scan ran is not knowable
    #: from times alone; a changed Vault root is reported here instead.
    root_changed: bool = False
    detail: str = ""
    checked_at: float = field(default=0.0)


@dataclass(frozen=True, slots=True)
class CliResult:
    """Outcome of one acquisition CLI run."""

    ok: bool
    command: tuple[str, ...]
    display_command: str
    exit_code: int
    stdout: str
    stderr: str
    seconds: float


class AcquisitionStore:
    """Read-only view of one acquisition data directory."""

    def __init__(
        self,
        data_dir: str,
        *,
        cli_path: str = "",
        python_executable: str | None = None,
        timeout_seconds: float = 180.0,
    ) -> None:
        self._root = Path(data_dir) if data_dir else None
        self._cli = Path(cli_path) if cli_path else None
        self._python = python_executable or sys.executable
        self._timeout = timeout_seconds
        self._cache: dict[str, tuple[int, dict[str, Any] | None]] = {}
        self._errors: dict[str, str] = {}
        self._vault_check: tuple[tuple[str, str], VaultChanges] | None = None

    # -- location -----------------------------------------------------------
    @property
    def root(self) -> Path | None:
        return self._root

    @property
    def configured(self) -> bool:
        return self._root is not None

    @property
    def available(self) -> bool:
        """True when the directory exists. An empty library is not an error."""
        return self._root is not None and self._root.is_dir()

    @property
    def cli_available(self) -> bool:
        return self._cli is not None and self._cli.is_file()

    @property
    def cli_path(self) -> str:
        return str(self._cli) if self._cli else ""

    # -- documents ----------------------------------------------------------
    def _path(self, name: str) -> Path:
        if name not in ACQUISITION_DOCUMENTS:
            raise KeyError(f"unknown acquisition document {name!r}")
        if self._root is None:  # pragma: no cover - guarded by `available`
            raise FileNotFoundError("no acquisition data directory configured")
        return self._root / name

    def read(self, name: str) -> dict[str, Any] | None:
        """Parsed document, or None when absent or unreadable.

        Re-parsed only when the file changed: the layout document is large
        and several screens read it on every request.
        """
        if not self.available:
            return None
        path = self._path(name)
        try:
            stat = path.stat()
        except OSError:
            self._cache.pop(name, None)
            return None
        cached = self._cache.get(name)
        if cached is not None and cached[0] == stat.st_mtime_ns:
            return cached[1]
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            # A half-written or hand-edited document must not take the API
            # down; the UI shows it as unreadable instead.
            self._errors[name] = f"{type(exc).__name__}: {exc}"
            self._cache[name] = (stat.st_mtime_ns, None)
            return None
        self._errors.pop(name, None)
        document = parsed if isinstance(parsed, dict) else {"items": parsed}
        self._cache[name] = (stat.st_mtime_ns, document)
        return document

    def documents(self) -> list[AcquisitionDocument]:
        out: list[AcquisitionDocument] = []
        for name in ACQUISITION_DOCUMENTS:
            if not self.available:
                out.append(
                    AcquisitionDocument(name=name, present=False, generated_at=None, size_bytes=0)
                )
                continue
            path = self._path(name)
            try:
                size = path.stat().st_size
            except OSError:
                out.append(
                    AcquisitionDocument(name=name, present=False, generated_at=None, size_bytes=0)
                )
                continue
            document = self.read(name)
            generated = None
            if isinstance(document, dict):
                raw = document.get("generated_at") or document.get("updated_at")
                generated = str(raw) if raw is not None else None
            out.append(
                AcquisitionDocument(
                    name=name,
                    present=True,
                    generated_at=generated,
                    size_bytes=size,
                    error=self._errors.get(name),
                )
            )
        return out

    def summary(self) -> dict[str, Any]:
        """Enough to tell the user what state their library tooling is in."""
        return {
            "configured": self.configured,
            "available": self.available,
            "data_dir": str(self._root) if self._root else "",
            "cli_available": self.cli_available,
            "cli_path": self.cli_path,
            "documents": [
                {
                    "name": d.name,
                    "present": d.present,
                    "generated_at": d.generated_at,
                    "size_bytes": d.size_bytes,
                    "error": d.error,
                }
                for d in self.documents()
            ],
        }

    # -- freshness ------------------------------------------------------------
    def vault_changes(
        self, vault_root: str, since: str | None, *, scan_seconds: float = 0.0
    ) -> VaultChanges:
        """Directories under ``vault_root`` modified after ``since``.

        ``vault_root`` and ``since`` come from the engine's own documents in
        the configured data directory, never from a request (F-50). The scan's
        duration is subtracted from ``since``: an entry added while the scan
        was walking elsewhere must count as a change.
        """
        if not vault_root or not since:
            return VaultChanges(checked=False, detail="no scan time in the documents")
        key = (vault_root, since)
        now = time.monotonic()
        cached = self._vault_check
        if cached is not None and cached[0] == key:
            if now - cached[1].checked_at < VAULT_CHECK_TTL_SECONDS:
                return cached[1]
        result = self._walk_for_changes(vault_root, since, scan_seconds, now)
        self._vault_check = (key, result)
        return result

    @staticmethod
    def _walk_for_changes(
        vault_root: str, since: str, scan_seconds: float, now: float
    ) -> VaultChanges:
        def unknown(detail: str) -> VaultChanges:
            return VaultChanges(checked=False, detail=detail, checked_at=now)

        try:
            cutoff = dt.datetime.fromisoformat(since).timestamp() - max(scan_seconds, 0.0)
        except ValueError:
            return unknown(f"unreadable scan time {since!r}")
        root = Path(vault_root)
        if not root.is_dir():
            return unknown("the Vault folder is not reachable")
        changed: set[str] = set()
        seen = 0
        try:
            root_changed = root.stat().st_mtime > cutoff
            with os.scandir(root) as top:
                stack = [(e.path, e.name) for e in top if e.is_dir(follow_symlinks=False)]
            while stack:
                path, top_name = stack.pop()
                seen += 1
                if seen > VAULT_CHECK_MAX_DIRS:
                    return unknown("the Vault is too large to check quickly")
                try:
                    if os.stat(path).st_mtime > cutoff:
                        changed.add(top_name)
                    with os.scandir(path) as entries:
                        stack.extend(
                            (e.path, top_name) for e in entries if e.is_dir(follow_symlinks=False)
                        )
                except OSError:
                    continue
        except OSError as exc:
            return unknown(f"{type(exc).__name__}: {exc}")
        return VaultChanges(
            checked=True,
            changed=bool(changed) or root_changed,
            folders=tuple(sorted(changed)),
            root_changed=root_changed,
            checked_at=now,
        )

    def forget_vault_check(self) -> None:
        """Drop the cached change check, e.g. after a refresh rewrote the documents."""
        self._vault_check = None

    # -- actions ------------------------------------------------------------
    def build_command(self, verb: str, *args: str) -> tuple[str, ...]:
        """Validate an action and return the exact argv that would run."""
        if verb not in ALLOWED_CLI:
            raise AcquisitionCliError(
                f"action {verb!r} is not available through the API "
                f"(allowed: {', '.join(sorted(ALLOWED_CLI))})"
            )
        sub_allowed = ALLOWED_CLI[verb]
        rest = list(args)
        prefix: tuple[str, ...]
        if sub_allowed:
            if not rest or rest[0] not in sub_allowed:
                raise AcquisitionCliError(f"{verb} needs one of: {', '.join(sorted(sub_allowed))}")
            rest = rest[1:]
            prefix = (verb, args[0])
        else:
            prefix = (verb,)
        for value in rest:
            if value.startswith("-") and value not in ALLOWED_FLAGS:
                raise AcquisitionCliError(f"flag {value!r} is not allowed from the API")
        if self._root is None:
            raise AcquisitionCliError("no acquisition data directory configured")
        if self._cli is None:
            raise AcquisitionCliError("no acquisition CLI path configured")
        return (self._python, str(self._cli), "--data-dir", str(self._root), *prefix, *rest)

    def run(self, verb: str, *args: str) -> CliResult:
        """Run one allowlisted acquisition action.

        The API stays a thin caller: the engine decides what is legal, what
        is official and what may be downloaded.
        """
        if not self.cli_available:
            raise AcquisitionCliError(
                "the acquisition CLI is not configured. Set CONTINUUM_ACQUISITION_CLI to the "
                "full path "
                "of acquisition_orchestrator.py, or run the command yourself."
            )
        command = self.build_command(verb, *args)
        self.forget_vault_check()
        started = time.monotonic()
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, allowlisted verbs
                list(command),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return CliResult(
                ok=False,
                command=command,
                display_command=self.display(command),
                exit_code=124,
                stdout="",
                stderr=f"timed out after {self._timeout:.0f}s",
                seconds=time.monotonic() - started,
            )
        except OSError as exc:
            return CliResult(
                ok=False,
                command=command,
                display_command=self.display(command),
                exit_code=127,
                stdout="",
                stderr=str(exc),
                seconds=time.monotonic() - started,
            )
        return CliResult(
            ok=completed.returncode == 0,
            command=command,
            display_command=self.display(command),
            exit_code=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            seconds=time.monotonic() - started,
        )

    @staticmethod
    def display(command: tuple[str, ...]) -> str:
        """The command as a human would type it, for the UI to show."""
        return " ".join(f'"{part}"' if " " in part else part for part in command)
