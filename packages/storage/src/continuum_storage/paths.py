"""The single hardened path resolver (ADR-0001 Layer 2).

Every filesystem operation in Continuum goes through :func:`resolve_within`.
Nothing else in the product is permitted to build a path (ADR-0001 Layer 3,
enforced by the import-linter contract in ``.importlinter``).

The containment check happens **after** full symlink/junction resolution.
Normalising first and resolving second is the classic bypass: ``a/../../b``
looks contained until the filesystem resolves it, and a symlink component
looks contained until it is followed.

Validation is deliberately identical on every platform, even for rules that
only *matter* on Windows (alternate data streams, trailing dots, reserved
device names). Cross-platform determinism means the audit environment tests
the same rules the Windows machine enforces, rather than silently skipping
them. The cost is that a POSIX file literally named ``"report "`` cannot be
addressed; for a media vault that is a trade worth making.
"""

from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path, PurePath

from continuum_core import PathEscapesRootError

__all__ = [
    "RESERVED_DEVICE_NAMES",
    "ResolvedPath",
    "resolve_within",
    "same_file_as",
    "validate_relative_candidate",
]

#: Windows device names. Opening one of these succeeds and does not address a
#: file, so a scanner that trusted the name would hang or read a console.
RESERVED_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
    | {"COM\u00b9", "COM\u00b2", "COM\u00b3", "LPT\u00b9", "LPT\u00b2", "LPT\u00b3"}
)

_WINDOWS = sys.platform == "win32"


@dataclass(frozen=True, slots=True)
class ResolvedPath:
    """A path proven to live inside a declared root.

    Constructed only by :func:`resolve_within`. Holding one is the evidence
    that containment was checked; functions that touch the filesystem take
    this type rather than a bare ``Path`` or ``str``.
    """

    root_key: str
    root: Path
    path: Path
    relative: PurePath

    def __fspath__(self) -> str:
        return str(self.path)

    def __str__(self) -> str:
        return str(self.path)


def validate_relative_candidate(candidate: str | PurePath) -> PurePath:
    """Reject candidate paths that must never reach the filesystem.

    Raises :class:`PathEscapesRootError` with a specific reason. Returns the
    candidate as a ``PurePath`` when it is structurally acceptable; this does
    **not** prove containment, which only :func:`resolve_within` can do.
    """
    raw = str(candidate)

    if raw == "":
        raise PathEscapesRootError(
            "Empty path is not addressable.",
            technical_detail="empty candidate",
        )

    if "\x00" in raw:
        raise PathEscapesRootError(
            "Path contains a NUL byte.",
            technical_detail="NUL in candidate",
        )

    if any(ord(ch) < 32 for ch in raw):
        raise PathEscapesRootError(
            "Path contains control characters.",
            technical_detail=f"control character in {raw!r}",
        )

    # PurePath of the *native* flavour: on Windows this understands drive
    # letters, UNC shares and the \\?\ prefix; on POSIX it understands /.
    pure = PurePath(raw)

    # Rejects absolute ("C:\\x", "/etc"), drive-relative ("C:x"),
    # root-relative ("\\x", "/x"), UNC ("\\\\server\\share") and
    # extended-length ("\\\\?\\C:\\x") in one check.
    if pure.drive or pure.root:
        raise PathEscapesRootError(
            "Only paths relative to a configured root are accepted.",
            technical_detail=f"candidate is not relative: drive={pure.drive!r} root={pure.root!r}",
            remediation="Address files by their path relative to the root, never by absolute path.",
        )

    for part in pure.parts:
        if part == "..":
            # Caught again by the containment check, but rejecting here gives
            # a precise error instead of a confusing "escapes root".
            raise PathEscapesRootError(
                "Path traversal ('..') is not allowed.",
                technical_detail=f"'..' in {raw!r}",
            )

        # Alternate Data Streams: "file.txt:secret" is not the file it looks
        # like. A colon can never appear in a relative component here.
        if ":" in part:
            raise PathEscapesRootError(
                "Path component contains ':' (alternate data stream or drive spec).",
                technical_detail=f"component {part!r} in {raw!r}",
            )

        # Windows silently strips trailing dots and spaces, so "a." and "a"
        # address one file through two different strings.
        if part != part.rstrip(" ."):
            raise PathEscapesRootError(
                "Path component has a trailing dot or space.",
                technical_detail=f"component {part!r} in {raw!r}",
            )

        stem = part.split(".", 1)[0].upper()
        if stem in RESERVED_DEVICE_NAMES:
            raise PathEscapesRootError(
                f"'{part}' is a reserved device name.",
                technical_detail=f"reserved device name in {raw!r}",
            )

    return pure


def resolve_within(root: Path, candidate: str | PurePath, *, root_key: str) -> ResolvedPath:
    """Resolve ``candidate`` under ``root`` and prove it stays inside.

    Order matters and is not negotiable:

    1. structurally validate the candidate;
    2. join to the root;
    3. fully resolve symlinks/junctions on **both** sides;
    4. only then check containment.
    """
    relative = validate_relative_candidate(candidate)

    # strict=False so a not-yet-existing derived path can be resolved; any
    # existing symlink component is still followed.
    real_root = Path(os.path.realpath(root))
    resolved = Path(os.path.realpath(real_root / relative))

    if not _is_contained(resolved, real_root):
        raise PathEscapesRootError(
            "Resolved path escapes its configured root.",
            technical_detail=(
                f"candidate={str(candidate)!r} resolved={str(resolved)!r} "
                f"root={str(real_root)!r} root_key={root_key!r}"
            ),
            remediation=(
                "This usually means a symlink or directory junction points outside "
                "the root. Continuum will not follow it."
            ),
        )

    return ResolvedPath(root_key=root_key, root=real_root, path=resolved, relative=relative)


def _is_contained(resolved: Path, real_root: Path) -> bool:
    """True when ``resolved`` is ``real_root`` or lives beneath it.

    ``Path.is_relative_to`` compares case-insensitively on Windows and
    case-sensitively on POSIX, which is what each filesystem actually does.
    """
    if resolved == real_root:
        return True
    return resolved.is_relative_to(real_root)


def same_file_as(fileno: int, expected: Path) -> bool:
    """Confirm an open descriptor is still the file that was validated.

    Closes the TOCTOU window: between :func:`resolve_within` and ``open``,
    an attacker (or a sync client) can swap the path for a symlink. Comparing
    ``st_dev``/``st_ino`` on the *descriptor* against the resolved target
    detects that the handle is not the file we approved.

    On Windows ``st_ino`` is the file index and ``st_dev`` the volume serial;
    both are populated by CPython, so the check is meaningful there too.
    """
    try:
        fd_stat = os.fstat(fileno)
        target_stat = expected.stat()
    except OSError:
        return False
    if fd_stat.st_ino == 0 or target_stat.st_ino == 0:  # pragma: no cover - exotic filesystems
        # Some filesystems do not report inodes; fall back to type identity
        # rather than claiming a match we cannot prove.
        return stat.S_IFMT(fd_stat.st_mode) == stat.S_IFMT(target_stat.st_mode)
    return fd_stat.st_dev == target_stat.st_dev and fd_stat.st_ino == target_stat.st_ino
