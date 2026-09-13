"""
The filesystem sandbox for the fta_web file endpoints.

WHY THIS MODULE EXISTS
======================
``security.py`` decides *who* may call the API: a per-launch token plus
Origin/Host pinning, which together stop a foreign web page from driving the
editor. This module decides *what* a caller who got that far may touch. The
two are independent on purpose. The token check is the outer wall; if it ever
fails -- a token leaked through a screenshot, a future endpoint mounted
outside ``/api``, a user who pasted the bootstrap URL into a chat window --
the only thing standing between an attacker and ``~/.ssh/id_rsa`` is this
file. So every path arriving from the client is treated as hostile, and
nothing here trusts a check performed by the caller.

THE RULES, AND WHY EACH ONE IS NOT REDUNDANT
============================================
Applied in this order by :func:`resolve_in_root`:

1. **It must be a string, non-empty, and free of NUL bytes.**
   A NUL is not a theoretical concern: C's path APIs terminate at it, so
   ``"/root/ok.json\\x00.png"`` can pass a naive suffix check in Python and
   then open ``/root/ok.json`` in the C layer underneath. Python's own
   ``open()`` raises ValueError on embedded NULs, but the rejection belongs
   here, where it is a documented 400 instead of an accidental 500.

2. **No ``..`` component**, checked on the raw string against both separators.
   Step 4 already makes traversal harmless, so this is belt and braces -- but
   it is also the only step that can distinguish "you tried to climb out" from
   "that path is simply elsewhere", and the user deserves the accurate
   message.

3. **A relative path is joined to the root, never to the process CWD.**
   ``Path("sub/x.json").resolve()`` silently resolves against whatever
   directory the server happens to have been started in, which is not a
   sandbox at all. Joining to the root makes a relative path mean what the
   client obviously intended. An absolute path is left alone and lands in
   step 4.

4. **Resolve first, then check containment.** This is the load-bearing step
   and the order matters. ``Path.resolve()`` follows symlinks, so a symlink
   *inside* the root that points outside it is resolved to its real target
   before containment is tested, and is therefore rejected. Checking
   containment on the unresolved path -- or resolving only the parent, or
   comparing string prefixes -- lets exactly that trick through. The root is
   resolved too, or a symlinked root (``/tmp`` on macOS, a pytest ``tmp_path``
   under ``/private/var``) would reject every path inside itself.

5. **Extension allow-list.** ``ALLOWED_OPEN_EXTENSIONS`` on the way in,
   ``ALLOWED_WRITE_EXTENSIONS`` on the way out. Confinement alone would still
   let a caller read ``~/.aws/credentials`` if it happened to live under the
   root, and let it overwrite ``~/.bashrc`` with JSON.

WHAT ERROR MESSAGES MAY SAY
===========================
Never the resolved path, and never anything about the filesystem outside the
root. Reporting "``/home/u/link`` -> ``/etc/shadow`` is outside the root"
would turn this sandbox into an oracle for probing the host: a rejected symlink
would report where it points, and a rejected absolute path would confirm what
does or does not exist. Messages therefore name only the *root* (which the
client already knows -- it is in ``/api/fs/home``) and a basename the caller
supplied. The machine-readable ``reason`` says which rule fired.

This module is deliberately Flask-free, mirroring ``rendering.py``: it raises
:class:`PathRejected` and ``routes/files.py`` translates that into the API's
``PATH_REJECTED`` envelope. That keeps the security core unit-testable without
a request context.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

try:  # normal package import: ``import fta_web.fsbrowser``
    from . import config
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import config  # type: ignore[no-redef]

# ---- knobs ---------------------------------------------------------------

#: Cap on a single file opened from disk. The same number as the HTTP upload
#: limit: a 2 GB "tree" is a memory exhaustion of the process holding the
#: user's unsaved work whether it arrives by POST or by path.
MAX_OPEN_BYTES = config.MAX_UPLOAD_BYTES

#: Cap on entries returned per kind by :func:`list_directory`. A picker
#: pointed at a 200k-file Downloads folder should not build a 200 MB JSON
#: response; the payload says ``truncated`` when it happens so the frontend
#: can tell the user rather than quietly showing a partial folder.
MAX_LIST_ENTRIES = 1000

#: Splits a client path on both separators, so a Windows-style ``..\\..``
#: is caught by the traversal check on POSIX too (where ``PurePath`` would
#: treat the whole thing as one filename).
_SEPARATORS = re.compile(r"[\\/]+")


# ---- errors --------------------------------------------------------------


class PathRejected(ValueError):
    """A client-supplied path did not survive the sandbox checks.

    ``reason`` is a stable machine-readable discriminator surfaced in the API
    error detail; ``status`` is the HTTP status the route should use (400 for
    a malformed or out-of-bounds path, 404 for a legal path that is not there,
    403 for one the OS will not let us read, 413 for one that is too big).
    """

    reason = "rejected"
    status = 400

    def __init__(self, message: str, reason: Optional[str] = None,
                 status: Optional[int] = None):
        super().__init__(message)
        if reason is not None:
            self.reason = reason
        if status is not None:
            self.status = status


# ---- the root ------------------------------------------------------------


def resolve_root(root: Any) -> Path:
    """The sandbox root, resolved once.

    Resolved rather than used as given because every containment test below
    compares against it: a symlinked root that was not resolved would reject
    every path inside itself.
    """
    try:
        resolved = Path(root).expanduser().resolve()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise PathRejected(
            "The file sandbox root is not usable (%s). Restart the editor with "
            "a valid --root." % exc,
            reason="root_unavailable",
            status=500,
        ) from exc
    if not resolved.is_dir():
        raise PathRejected(
            "The file sandbox root %s is not a directory. Restart the editor "
            "with a valid --root." % resolved,
            reason="root_unavailable",
            status=500,
        )
    return resolved


def is_within(root: Path, candidate: Path) -> bool:
    """True if ``candidate`` is ``root`` or lives underneath it.

    Purely lexical, which is correct *only* because both arguments are already
    resolved -- see rule 4 in the module docstring. On a case-insensitive
    filesystem a differently-cased path fails this test and is rejected; that
    is the safe direction to be wrong in.
    """
    if candidate == root:
        return True
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


# ---- the core check ------------------------------------------------------


def resolve_in_root(raw: Any, root: Path) -> Path:
    """Validate a client path and return it resolved inside ``root``.

    Rules 1-4 of the module docstring, in order. Existence is not required and
    not checked: this is also the entry point for "where should I write?".

    Raises:
        PathRejected: on any malformed or escaping path.
    """
    # Rule 1: shape.
    if isinstance(raw, Path):
        raw = str(raw)
    if not isinstance(raw, str):
        raise PathRejected("A file path must be a string.", reason="not_a_string")
    if "\x00" in raw:
        # Never echo the value back; it is hostile by construction.
        raise PathRejected(
            "A file path may not contain a NUL byte.", reason="nul_byte"
        )
    text = raw.strip()
    if not text:
        raise PathRejected("A file path is required.", reason="empty")

    # Rule 2: no traversal segments, on either separator.
    if any(part == ".." for part in _SEPARATORS.split(text)):
        raise PathRejected(
            "A file path may not contain '..'. Paths are confined to %s."
            % root,
            reason="traversal",
        )

    # Rule 3: relative means relative to the root, never to the server's CWD.
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = root / candidate

    # Rule 4: resolve (following symlinks), then confine.
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        # A symlink loop, a path longer than PATH_MAX, or a filename the
        # platform refuses to encode. Nothing about the target is disclosed.
        raise PathRejected(
            "That path could not be resolved.", reason="unresolvable"
        ) from exc
    if not is_within(root, resolved):
        raise PathRejected(
            "That path is outside %s, which is the only folder this editor "
            "may read or write. Relaunch with --root to change it." % root,
            reason="outside_root",
        )
    return resolved


def require_extension(path: Path, allowed: Iterable[str], action: str) -> Path:
    """Rule 5: the file's suffix must be in the allow-list."""
    permitted: Set[str] = {str(ext).lower() for ext in allowed}
    if path.suffix.lower() not in permitted:
        raise PathRejected(
            "'%s' cannot be %s: only %s files are allowed."
            % (path.name, action, ", ".join(sorted(permitted))),
            reason="extension",
        )
    return path


# ---- the three things routes actually ask for ----------------------------


def resolve_for_open(raw: Any, root: Path) -> Path:
    """A path that may be read as a document. Must exist and be a real file."""
    resolved = resolve_in_root(raw, root)
    require_extension(resolved, config.ALLOWED_OPEN_EXTENSIONS, "opened")

    try:
        stat = resolved.stat()
    except FileNotFoundError as exc:
        raise PathRejected(
            "'%s' does not exist." % resolved.name, reason="not_found", status=404
        ) from exc
    except PermissionError as exc:
        raise PathRejected(
            "'%s' cannot be read: permission denied." % resolved.name,
            reason="unreadable",
            status=403,
        ) from exc
    except OSError as exc:
        raise PathRejected(
            "'%s' cannot be read (%s)." % (resolved.name, exc.strerror or exc),
            reason="unreadable",
            status=400,
        ) from exc

    if not resolved.is_file():
        # Directories, but also FIFOs and device nodes: reading /dev/zero
        # would hang the single process that holds the user's unsaved work.
        raise PathRejected(
            "'%s' is not a file." % resolved.name, reason="not_a_file"
        )
    if stat.st_size > MAX_OPEN_BYTES:
        raise PathRejected(
            "'%s' is %.1f MB, over the %.0f MB limit for one analysis."
            % (resolved.name, stat.st_size / 1048576.0, MAX_OPEN_BYTES / 1048576.0),
            reason="too_large",
            status=413,
        )
    return resolved


def resolve_for_write(raw: Any, root: Path,
                      allowed: Optional[Iterable[str]] = None) -> Path:
    """A path that may be written to.

    The parent directory must already exist inside the sandbox. Creating it
    would mean a hostile path could scatter directories through the user's
    files, and a typo would silently save into a folder that only looks right.
    """
    resolved = resolve_in_root(raw, root)
    require_extension(
        resolved,
        config.ALLOWED_WRITE_EXTENSIONS if allowed is None else allowed,
        "written",
    )

    if resolved.is_dir():
        raise PathRejected(
            "'%s' is a folder." % resolved.name, reason="not_a_file"
        )
    parent = resolved.parent
    if not is_within(root, parent):  # pragma: no cover - implied by resolve_in_root
        raise PathRejected(
            "That path is outside %s." % root, reason="outside_root"
        )
    if not parent.is_dir():
        raise PathRejected(
            "The folder for '%s' does not exist. Create it first, or choose "
            "another location." % resolved.name,
            reason="parent_missing",
            status=404,
        )
    return resolved


def list_directory(raw: Any, root: Path) -> Dict[str, Any]:
    """One directory's contents, as the file picker wants them.

    ``raw`` may be None or empty, meaning the root itself. Returns
    ``{path, parent, dirs, files, truncated}`` with absolute paths; ``parent``
    is None at the root, so the picker can never offer a way out of it.

    Entries excluded, all deliberately:

    * dotfiles -- a home directory is mostly ``.config``/``.ssh``/``.aws``
      noise, and not listing them keeps the picker from advertising them. They
      are not *blocked*: a user who types the path may still open a
      ``.hidden.json``, which is the correct trade (this hides clutter, it is
      not an access control).
    * files whose extension is not openable -- the picker exists to choose a
      document, and listing the rest would leak the shape of the user's
      folders for no benefit.
    * symlinks leaving the root -- skipped rather than shown-and-then-refused,
      so the listing cannot be used to probe for the existence of files
      outside the sandbox.
    * anything that fails to stat (a broken symlink, a race with a deletion).
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        target = root
    else:
        target = resolve_in_root(raw, root)
    if not target.is_dir():
        raise PathRejected(
            "'%s' is not a folder." % target.name, reason="not_a_directory",
            status=404 if not target.exists() else 400,
        )

    dirs: List[Dict[str, Any]] = []
    files: List[Dict[str, Any]] = []
    truncated = False
    openable = {ext.lower() for ext in config.ALLOWED_OPEN_EXTENSIONS}

    try:
        with os.scandir(target) as entries:
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                try:
                    # A symlink is the only way a child of a resolved,
                    # contained directory can point outside the root, so pay
                    # for the extra resolve only when there is one.
                    if entry.is_symlink():
                        real = Path(entry.path).resolve()
                        if not is_within(root, real):
                            continue
                    if entry.is_dir():
                        if len(dirs) >= MAX_LIST_ENTRIES:
                            truncated = True
                            continue
                        dirs.append({"name": entry.name, "path": entry.path})
                        continue
                    if not entry.is_file():
                        continue  # FIFO, socket, device node
                    if Path(entry.name).suffix.lower() not in openable:
                        continue
                    if len(files) >= MAX_LIST_ENTRIES:
                        truncated = True
                        continue
                    stat = entry.stat()
                    files.append(
                        {
                            "name": entry.name,
                            "path": entry.path,
                            "size": stat.st_size,
                            "modified": _isoformat(stat.st_mtime),
                        }
                    )
                except OSError:
                    continue  # broken symlink, or it vanished mid-listing
    except PermissionError as exc:
        raise PathRejected(
            "'%s' cannot be listed: permission denied." % target.name,
            reason="unreadable",
            status=403,
        ) from exc
    except OSError as exc:
        raise PathRejected(
            "'%s' cannot be listed (%s)." % (target.name, exc.strerror or exc),
            reason="unreadable",
        ) from exc

    dirs.sort(key=lambda item: item["name"].lower())
    files.sort(key=lambda item: item["name"].lower())

    return {
        "path": str(target),
        # None at the root: the picker gets no "up" affordance that would take
        # it out of the sandbox, and does not have to know where to stop.
        "parent": None if target == root else str(target.parent),
        "dirs": dirs,
        "files": files,
        "truncated": truncated,
    }


def _isoformat(timestamp: float) -> Optional[str]:
    """Local-time ISO 8601 to the second, or None for an unrepresentable stamp."""
    try:
        return datetime.fromtimestamp(timestamp).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):  # pragma: no cover - platform
        return None


# ---- download names ------------------------------------------------------

#: Anything that must not reach a ``Content-Disposition`` filename: path
#: separators (a download named ``../../x`` is a client-side traversal) and
#: control characters (which could split the header on a lax client).
_UNSAFE_NAME_CHARS = re.compile(r"[\\/\x00-\x1f\x7f]+")

#: Filesystems stop caring long before this; the cap just keeps a pathological
#: title out of a response header.
MAX_DOWNLOAD_NAME = 100


def safe_download_name(stem: Any, suffix: str, fallback: str = "fta_export") -> str:
    """A ``<stem><suffix>`` filename that is safe to put in a response header.

    The stem comes from the open document's filename or title, both of which
    are user data that has been nowhere near this module's checks. Non-ASCII
    is preserved -- Flask encodes it per RFC 6266 -- because mangling a
    Japanese title into underscores would be its own kind of wrong.
    """
    text = "" if stem is None else str(stem)
    text = _UNSAFE_NAME_CHARS.sub("_", text).strip().strip(".")
    text = text[:MAX_DOWNLOAD_NAME].strip()
    return (text or fallback) + suffix
