"""
The recovery copy: unsaved work that survives a crash.

The editor keeps the one open document in memory. Until 1.8.1 nothing else
held it: a power cut, a killed process or a closed terminal window took every
change since the last Save. While the document has unsaved changes, this
module keeps a copy of it on disk, and the next start offers it back.

What is written, and where
--------------------------
``<per-user folder>/recovery/`` -- the folder that also holds the AI
credentials and ``ui_prefs.json`` (``~/.fta_editor``; read from
``AICredentialManager.CREDENTIALS_DIR`` at each call, like ``user_prefs``, so
there is one place that says where it is and one thing for a test to
redirect). Per running editor ("session"), three files named after a random
session id::

    <id>.json        the document, written by the same writer Save uses
    <id>.meta.json   {"session", "title", "originalPath", "savedAt", ...}
    <id>.lock        held open (and locked) for as long as the session lives

The location is fixed. It is never derived from the sandbox root, from the
document's path or from anything a request says, and nothing here goes
through ``fsbrowser``: a recovery copy is not a file the user chose, and its
endpoints take an id from the server's own listing, never a path (the
allow-list approach of ``POST /api/examples/open``).

With the default sandbox root -- the home directory -- the per-user folder is
*inside* the root, so "outside the root" cannot be what keeps the file
endpoints away from the copies. The folder is registered with
``fsbrowser.reserve`` instead: a client path into it is refused
(``PATH_REJECTED``, reason ``reserved``) for open, save and listing alike.

No credential is ever written: the copy is the document (what Save writes),
and the sidecar holds the title, the path the document was opened from and a
time.

When
----
A change (``AppState.mark_dirty``) wakes the writer thread. It writes once
the document has been quiet for ``DEBOUNCE_SECONDS``, and at the latest
``MAX_WAIT_SECONDS`` after the first change it has not written yet -- so
steady typing costs one write every 30 s, not one per keystroke, and at most
30 s of work can be lost. The write is atomic (temp file, ``os.replace``),
so a crash during it leaves the previous copy.

The copy is removed when the document stops having unsaved changes: Save,
and New / Open / an example, which the server only allows over unsaved work
after the user chose to discard it (or saved it). It is removed on a clean
exit as well (Ctrl-C). What is left is, by construction, a document whose
session ended without either.

Which copies are offered
------------------------
A copy belongs to a session that did not end cleanly when its lock file can
be locked by somebody else: the lock is held by the process, and the
operating system drops it when the process dies, however it dies. This is
what keeps a second running copy of the editor from offering (or pruning)
the unsaved work of the first. A process id is deliberately not used:
ids are reused, and on Windows there is no harmless way to ask whether one
is alive (``os.kill(pid, 0)`` terminates the process there).

Opt-in
------
Nothing happens until :func:`start` is called, and only the launcher
(``run.py``) calls it. An app built by ``create_app`` in a test writes no
recovery copy. The read side (:func:`abandoned`, :func:`read_copy`,
:func:`discard`) works without it.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # normal package import: ``import fta_web.recovery``
    from . import config, fsbrowser
    from . import state as state_module
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import config  # type: ignore[no-redef]
    import fsbrowser  # type: ignore[no-redef]
    import state as state_module  # type: ignore[no-redef]

# Importing config placed fta_web/core on sys.path (see config.py).
from AI_agent_handler import AICredentialManager  # noqa: E402

log = logging.getLogger(__name__)

#: Folder name under the per-user folder.
DIRECTORY_NAME = "recovery"

#: Write once the document has been quiet for this long ...
DEBOUNCE_SECONDS = 2.0
#: ... and at the latest this long after the first unwritten change.
MAX_WAIT_SECONDS = 30.0

#: A document larger than this is not copied (the limit for opening one: a
#: copy that could not be opened again would be of no use).
MAX_COPY_BYTES = config.MAX_UPLOAD_BYTES

#: How many copies of ended sessions are kept; older ones are removed at
#: start-up. One is the usual number: this only bounds the folder.
MAX_COPIES = 5

#: A session id as this module makes them. A file whose name does not have
#: this shape is not a recovery copy and is never read, listed or removed.
_ID = re.compile(r"^[0-9a-f]{16}$")

_SIDECAR_VERSION = 1


def directory() -> Path:
    """Where the copies are kept (not created by asking)."""
    return Path(AICredentialManager.CREDENTIALS_DIR) / DIRECTORY_NAME


# The file endpoints never reach into this folder, wherever the sandbox root
# is (with the default root, the home directory, it is inside it).
fsbrowser.reserve(directory)


def _paths(session: str) -> Dict[str, Path]:
    base = directory()
    return {
        "doc": base / (session + ".json"),
        "meta": base / (session + ".meta.json"),
        "lock": base / (session + ".lock"),
    }


# ---- the session lock --------------------------------------------------------


def _lock_handle(handle) -> bool:
    """Take a non-blocking exclusive lock on an open file. False when
    somebody else holds it."""
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock_handle(handle) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def _session_is_live(session: str) -> bool:
    """Whether the process that owns ``session`` is still running: its lock
    file exists and cannot be locked. A copy without a lock file was left by
    a session that is gone."""
    lock = _paths(session)["lock"]
    try:
        handle = open(lock, "r+b")
    except OSError:
        return False
    try:
        if _lock_handle(handle):
            _unlock_handle(handle)
            return False
        return True
    finally:
        handle.close()


# ---- this session ------------------------------------------------------------


class _Session:
    """The running editor's own copy, and the thread that keeps it."""

    def __init__(self) -> None:
        self.id = secrets.token_hex(8)
        self.lock_file = None
        #: Serialises every write and removal of this session's files. Taken
        #: before ``state.lock`` and never while holding it.
        self.io_lock = threading.Lock()
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.thread: Optional[threading.Thread] = None
        #: monotonic time of the first change not yet written, or None.
        self.first_change: Optional[float] = None
        self.last_change: float = 0.0
        self.urgent = False
        self.mark = threading.Lock()


_session: Optional[_Session] = None
_session_guard = threading.Lock()


def session_id() -> Optional[str]:
    """The running session's id, or None when recovery was not started."""
    current = _session
    return current.id if current else None


def start(background: bool = True) -> Optional[str]:
    """Begin keeping a recovery copy for this process. Idempotent.

    Returns the session id, or None when the folder cannot be used (a
    read-only home, a full disk): the editor then runs as it did before,
    without a recovery copy, and says so in the log.

    ``background=False`` starts no thread: the copy is then written only by
    :func:`flush` (for tests, which must not depend on timing).
    """
    global _session
    with _session_guard:
        if _session is not None:
            return _session.id
        session = _Session()
        try:
            base = directory()
            base.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(base, 0o700)  # the user's unsaved work: theirs alone
            except OSError:
                pass
            handle = open(_paths(session.id)["lock"], "w+b")
            handle.write(b"\0")
            handle.flush()
            if not _lock_handle(handle):  # a fresh random name: cannot happen
                handle.close()
                raise OSError("could not lock the session file")
            session.lock_file = handle
        except OSError as exc:
            log.warning("No recovery copy will be kept: %s", exc)
            return None
        _session = session
        state_module.add_document_listener(_on_document_event)
        prune()
        if background:
            session.thread = threading.Thread(target=_writer, args=(session,),
                                              name="recovery-writer", daemon=True)
            session.thread.start()
        return session.id


def end_session() -> None:
    """A clean exit: stop the writer and remove this session's files.

    The document may still have unsaved changes; leaving the editor with
    Ctrl-C is the user's decision, as closing a window without saving is.
    """
    global _session
    with _session_guard:
        session = _session
        _session = None
    if session is None:
        return
    state_module.remove_document_listener(_on_document_event)
    session.stop.set()
    session.wake.set()
    if session.thread is not None and session.thread is not threading.current_thread():
        session.thread.join(2.0)
    with session.io_lock:
        paths = _paths(session.id)
        _unlink(paths["doc"])
        _unlink(paths["meta"])
        if session.lock_file is not None:
            _unlock_handle(session.lock_file)
            try:
                session.lock_file.close()
            except OSError:
                pass
            session.lock_file = None
        _unlink(paths["lock"])


def _on_document_event(kind: str) -> None:
    """Called by AppState (possibly with ``state.lock`` held): only notes
    what happened and wakes the writer. No file is touched here."""
    session = _session
    if session is None:
        return
    now = time.monotonic()
    with session.mark:
        if kind == "dirty":
            if session.first_change is None:
                session.first_change = now
            session.last_change = now
        else:  # "saved" or "reset": the copy is out of date at once
            session.urgent = True
    session.wake.set()


def _writer(session: _Session) -> None:
    """The background thread: sleep until there is something to do, wait for
    the document to go quiet (but not for ever), then :func:`_sync`."""
    while not session.stop.is_set():
        session.wake.wait()
        if session.stop.is_set():
            return
        session.wake.clear()
        while not session.stop.is_set():
            now = time.monotonic()
            with session.mark:
                if session.urgent or session.first_change is None:
                    due = now
                else:
                    due = min(session.last_change + DEBOUNCE_SECONDS,
                              session.first_change + MAX_WAIT_SECONDS)
            if due <= now:
                break
            # Woken early by another change (the quiet period starts again)
            # or by a save: look at the clock again either way.
            session.wake.wait(due - now)
            session.wake.clear()
        if session.stop.is_set():
            return
        try:
            _sync(session)
        except Exception:  # the writer must outlive any one failed write
            log.exception("The recovery copy could not be updated.")


def flush() -> bool:
    """Bring the copy up to date now: written when the document has unsaved
    changes, removed when it has none. True when a copy exists afterwards.
    Must not be called with ``state.lock`` held."""
    session = _session
    if session is None:
        return False
    return _sync(session)


def _sync(session: _Session) -> bool:
    with session.io_lock:
        if _session is not session:  # ended meanwhile: its files are gone
            return False
        with session.mark:
            session.first_change = None
            session.urgent = False
        paths = _paths(session.id)
        state = state_module.get_state()
        temp_doc: Optional[Path] = None
        meta: Optional[Dict[str, Any]] = None
        with state.lock:
            if state.dirty:
                temp_doc = _write_document(state.core, paths["doc"].parent)
                if temp_doc is not None:
                    meta = {
                        "version": _SIDECAR_VERSION,
                        "session": session.id,
                        "title": str(state.core.title or ""),
                        "originalPath": str(state.current_path) if state.current_path else None,
                        "savedAt": datetime.now().isoformat(timespec="seconds"),
                    }
        if temp_doc is None or meta is None:
            # Nothing unsaved (or a document that cannot be copied): no copy
            # may claim to be this document.
            _unlink(paths["doc"])
            _unlink(paths["meta"])
            return False
        try:
            # The sidecar first: a document without one is not offered, so a
            # crash between the two leaves nothing half-described.
            _write_json_atomic(paths["meta"], meta)
            os.replace(temp_doc, paths["doc"])
        except OSError as exc:
            log.warning("The recovery copy could not be written: %s", exc)
            _unlink(temp_doc)
            return False
        return True


def _write_document(core, folder: Path) -> Optional[Path]:
    """The document as Save writes it, in a temp file in ``folder``. None
    when it cannot be written or is over ``MAX_COPY_BYTES``. Caller holds
    ``state.lock``."""
    try:
        handle, name = tempfile.mkstemp(prefix=".write_", suffix=".tmp", dir=str(folder))
    except OSError as exc:
        log.warning("The recovery copy could not be written: %s", exc)
        return None
    os.close(handle)
    temp = Path(name)
    # save_to_json() records where it wrote and fills in an empty date. This
    # is not a save: the document keeps its file and its date (as for the
    # JSON export, routes/files.py).
    previous = getattr(core, "last_saved_file", None)
    date = core.date
    try:
        ok, error = core.save_to_json(str(temp))
    except Exception as exc:  # a document the writer cannot serialise
        ok, error = False, str(exc)
    finally:
        core.last_saved_file = previous
        core.date = date
    if not ok:
        log.warning("The recovery copy could not be written: %s", error)
        _unlink(temp)
        return None
    try:
        if temp.stat().st_size > MAX_COPY_BYTES:
            _unlink(temp)
            return None
    except OSError:
        _unlink(temp)
        return None
    return temp


def _write_json_atomic(target: Path, payload: Dict[str, Any]) -> None:
    handle, name = tempfile.mkstemp(prefix=".write_", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(payload, out, ensure_ascii=False, indent=2)
        os.replace(name, target)
    except BaseException:
        _unlink(Path(name))
        raise


def _unlink(path: Path) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


# ---- copies left by sessions that ended without saving ---------------------------


def _read_meta(path: Path) -> Optional[Dict[str, Any]]:
    try:
        if path.stat().st_size > 65536:
            return None
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def abandoned() -> Dict[str, Dict[str, Any]]:
    """``{id: {id, title, savedAt, originalPath, path}}`` for every copy left
    by a session that is gone, newest first.

    This listing is the allow-list of the restore and discard endpoints: an
    id is looked up here and nothing else is read or removed, so client text
    never becomes part of a path. Only regular files directly in the folder
    whose names have the shape this module writes; a symbolic link is
    skipped. The running session's own copy and the copy of any other
    running editor are not in it.
    """
    own = session_id()
    found: List[Dict[str, Any]] = []
    try:
        with os.scandir(directory()) as entries:
            names = {}
            for entry in entries:
                try:
                    if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                names[entry.name] = Path(entry.path)
    except OSError:
        return {}
    for name, path in names.items():
        if not name.endswith(".json") or name.endswith(".meta.json"):
            continue
        session = name[:-len(".json")]
        if not _ID.match(session) or session == own:
            continue
        meta_path = names.get(session + ".meta.json")
        meta = _read_meta(meta_path) if meta_path else None
        if meta is None:
            continue  # half-written, or not ours
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size > MAX_COPY_BYTES or _session_is_live(session):
            continue
        title = meta.get("title")
        original = meta.get("originalPath")
        saved = meta.get("savedAt")
        found.append({
            "id": session,
            "title": title if isinstance(title, str) else "",
            "savedAt": saved if isinstance(saved, str) else None,
            "originalPath": original if isinstance(original, str) else None,
            "path": path,
            "_mtime": stat.st_mtime,
        })
    found.sort(key=lambda item: item["_mtime"], reverse=True)
    return {item["id"]: {key: value for key, value in item.items() if key != "_mtime"}
            for item in found}


def listing() -> List[Dict[str, Any]]:
    """:func:`abandoned` as the API reports it: no server path of the copy."""
    return [{key: value for key, value in item.items() if key != "path"}
            for item in abandoned().values()]


def discard(session: Any) -> bool:
    """Remove the copy ``session`` names. False when it is not one of
    :func:`abandoned` (unknown, the running session's, a live editor's)."""
    if not isinstance(session, str) or session not in abandoned():
        return False
    _remove_session_files(session)
    return True


def _remove_session_files(session: str) -> None:
    if not _ID.match(session):  # belt and braces: only names this module makes
        return
    for path in _paths(session).values():
        _unlink(path)


def prune() -> None:
    """Keep the newest ``MAX_COPIES`` abandoned copies, and remove what dead
    sessions left besides a copy (a lock file, a sidecar, a temp file). Live
    sessions are never touched."""
    copies = abandoned()
    for session in list(copies)[MAX_COPIES:]:
        _remove_session_files(session)
    own = session_id()
    try:
        with os.scandir(directory()) as entries:
            leftovers = [Path(entry.path) for entry in entries
                         if entry.is_file(follow_symlinks=False)]
    except OSError:
        return
    kept = set(list(copies)[:MAX_COPIES])
    for path in leftovers:
        name = path.name
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            continue
        if name.startswith(".write_") and name.endswith(".tmp"):
            # A temp file of a write that never finished (a live session's
            # is renamed within seconds).
            if age > 3600:
                _unlink(path)
            continue
        # Not the files of an editor that is starting this very moment (its
        # lock file exists a moment before it is locked).
        if age < 60:
            continue
        for suffix in (".meta.json", ".lock", ".json"):
            if name.endswith(suffix):
                session = name[:-len(suffix)]
                if (_ID.match(session) and session != own and session not in kept
                        and not _session_is_live(session)):
                    _unlink(path)
                break
