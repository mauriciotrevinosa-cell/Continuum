"""Read one directory of a Git commit, without a checkout.

A project whose source of truth is a branch should be shown exactly as that
branch is committed - not as whatever happens to be checked out in some
working tree. A ``git:`` project source names a repository, a ref and a
directory; Continuum reads the tree at the commit the ref points to and
reports which commit that was.

Boundaries:

* The repository, ref and directory come from configuration, never from a
  request (F-50). They are validated before any command runs.
* Every command is a fixed argv with no shell. Nothing here writes to the
  working tree, the index or any local branch. The one network operation,
  :meth:`GitTree.fetch`, only updates a remote-tracking ref, and only when
  someone asks for a resync.
* Credentials are never prompted for: a fetch that would need them fails
  and says so.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import PurePosixPath

__all__ = [
    "GIT_SOURCE_PREFIX",
    "GitCommit",
    "GitFile",
    "GitSourceError",
    "GitSpec",
    "GitTree",
]

GIT_SOURCE_PREFIX = "git:"
#: Ref names Continuum accepts: branch-like names, no ``..``, no leading dash.
_REF = re.compile(r"^(?![-/])(?!.*\.\.)(?!.*//)[A-Za-z0-9._/-]{1,200}(?<![/.])$")
_SUBDIR = re.compile(r"^(?!.*\.\.)[A-Za-z0-9._ /-]{0,300}$")
_OID = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
DEFAULT_TIMEOUT = 30.0
FETCH_TIMEOUT = 120.0


class GitSourceError(RuntimeError):
    """A Git project source could not be read (or fetched)."""


@dataclass(frozen=True, slots=True)
class GitSpec:
    """``git:<repository>@<ref>[:<directory>]``, parsed and validated."""

    repo: str
    ref: str
    subdir: str = ""

    @classmethod
    def parse(cls, text: str) -> GitSpec | None:
        """The spec in a configured source string, or None if it is not one."""
        if not text.startswith(GIT_SOURCE_PREFIX):
            return None
        body = text[len(GIT_SOURCE_PREFIX) :].strip()
        repo, at, rest = body.rpartition("@")
        if not at or not repo.strip():
            raise GitSourceError(f"a git project source needs '<repository>@<ref>': {text!r}")
        ref, _colon, subdir = rest.partition(":")
        ref = ref.strip()
        subdir = subdir.strip().replace("\\", "/").strip("/")
        if not _REF.match(ref):
            raise GitSourceError(f"not an acceptable git ref: {ref!r}")
        if not _SUBDIR.match(subdir) or subdir.startswith("-"):
            raise GitSourceError(f"not an acceptable directory inside the repository: {subdir!r}")
        return cls(repo=repo.strip(), ref=ref, subdir=subdir)

    @property
    def label(self) -> str:
        """How the source is described to people: the ref and directory, never a path."""
        return f"{self.ref}:{self.subdir}" if self.subdir else self.ref


@dataclass(frozen=True, slots=True)
class GitCommit:
    sha: str
    committed_ns: int
    subject: str

    @property
    def short(self) -> str:
        return self.sha[:7]


@dataclass(frozen=True, slots=True)
class GitFile:
    #: Path relative to the source directory, with forward slashes.
    name: str
    oid: str
    size: int


class GitTree:
    """Read-only access to ``spec.subdir`` at the commit ``spec.ref`` names."""

    def __init__(
        self, spec: GitSpec, *, git: str = "git", timeout: float = DEFAULT_TIMEOUT
    ) -> None:
        self.spec = spec
        self._git = git
        self._timeout = timeout

    # -- commands -------------------------------------------------------------
    def _run(self, *args: str, stdin: bytes | None = None, timeout: float | None = None) -> bytes:
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_OPTIONAL_LOCKS"] = "0"
        env["GCM_INTERACTIVE"] = "never"
        command = [self._git, "-C", self.spec.repo, "-c", "core.quotepath=off", *args]
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, validated inputs
                command,
                input=stdin,
                capture_output=True,
                timeout=timeout or self._timeout,
                shell=False,
                check=False,
                env=env,
            )
        except FileNotFoundError as exc:
            raise GitSourceError("git is not installed or not on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise GitSourceError(f"git {args[0]} timed out") from exc
        except OSError as exc:
            raise GitSourceError(f"git {args[0]} could not run: {exc}") from exc
        if completed.returncode != 0:
            message = completed.stderr.decode("utf-8", errors="replace").strip()
            raise GitSourceError(f"git {args[0]} failed: {message[:400] or completed.returncode}")
        return completed.stdout

    # -- reads ----------------------------------------------------------------
    def commit(self) -> GitCommit:
        """The commit the ref points to right now."""
        out = self._run(
            "log", "-1", "--format=%H%x1f%ct%x1f%s", f"{self.spec.ref}^{{commit}}", "--"
        )
        sha, ct, subject = out.decode("utf-8", errors="replace").strip().split("\x1f", 2)
        if not _OID.match(sha):
            raise GitSourceError(f"unexpected commit id from git: {sha!r}")
        return GitCommit(sha=sha, committed_ns=int(ct) * 1_000_000_000, subject=subject)

    def files(self, commit: str) -> dict[str, GitFile]:
        """Every blob under the source directory at ``commit``."""
        self._check_oid(commit)
        pathspec = [self.spec.subdir] if self.spec.subdir else []
        out = self._run("ls-tree", "-r", "-z", "--long", "--full-tree", commit, "--", *pathspec)
        prefix = f"{self.spec.subdir}/" if self.spec.subdir else ""
        found: dict[str, GitFile] = {}
        for record in out.split(b"\0"):
            if not record:
                continue
            meta, _tab, raw_path = record.partition(b"\t")
            parts = meta.split()
            if len(parts) != 4 or parts[1] != b"blob":
                continue
            path = raw_path.decode("utf-8", errors="replace")
            if not path.startswith(prefix):
                continue
            size = int(parts[3]) if parts[3].isdigit() else 0
            name = path[len(prefix) :]
            found[name] = GitFile(name=name, oid=parts[2].decode("ascii"), size=size)
        return found

    def read(self, oids: list[str], *, limit: int) -> dict[str, bytes]:
        """Blob contents by object id, each truncated to ``limit`` + 1 bytes."""
        wanted = sorted({oid for oid in oids if _OID.match(oid)})
        if not wanted:
            return {}
        out = self._run("cat-file", "--batch", stdin=("\n".join(wanted) + "\n").encode("ascii"))
        blobs: dict[str, bytes] = {}
        position = 0
        while position < len(out):
            end = out.index(b"\n", position)
            header = out[position:end].split()
            position = end + 1
            if len(header) == 2 and header[1] == b"missing":
                continue
            if len(header) != 3:
                raise GitSourceError("unexpected output from git cat-file")
            size = int(header[2])
            blobs[header[0].decode("ascii")] = out[position : position + min(size, limit + 1)]
            position += size + 1
        return blobs

    def last_changes(self, commit: str) -> dict[str, GitCommit]:
        """For each file under the directory, the newest commit that changed it."""
        self._check_oid(commit)
        pathspec = [self.spec.subdir] if self.spec.subdir else []
        out = self._run(
            "log",
            "--format=%x1e%H%x1f%ct%x1f%s",
            "--name-only",
            "--no-renames",
            commit,
            "--",
            *pathspec,
        )
        prefix = f"{self.spec.subdir}/" if self.spec.subdir else ""
        changes: dict[str, GitCommit] = {}
        for block in out.decode("utf-8", errors="replace").split("\x1e"):
            lines = [line for line in block.splitlines() if line.strip()]
            if not lines:
                continue
            fields = lines[0].split("\x1f", 2)
            if len(fields) != 3 or not _OID.match(fields[0]):
                continue
            change = GitCommit(fields[0], int(fields[1]) * 1_000_000_000, fields[2])
            for path in lines[1:]:
                if path.startswith(prefix):
                    changes.setdefault(path[len(prefix) :], change)
        return changes

    # -- the one write: a remote-tracking ref ---------------------------------
    def fetch(self) -> bool:
        """Update the ref from its remote, when it is a remote-tracking ref.

        Returns False when the ref is not remote-tracking (a local branch is
        never moved here - pulling it is the user's own action).
        """
        remotes = self._run("remote").decode("utf-8", errors="replace").split()
        remote, _slash, branch = self.spec.ref.partition("/")
        if remote not in remotes or not branch:
            return False
        self._run(
            "fetch",
            "--no-tags",
            "--quiet",
            remote,
            f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}",
            timeout=FETCH_TIMEOUT,
        )
        return True

    @staticmethod
    def _check_oid(commit: str) -> None:
        if not _OID.match(commit):
            raise GitSourceError(f"not a commit id: {commit!r}")


def normal_name(relative: str) -> str | None:
    """A manifest path as a tree name, or None if it could leave the directory."""
    text = relative.replace("\\", "/").strip()
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts or ":" in text:
        return None
    return str(path)
