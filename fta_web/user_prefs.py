"""
The few things the editor remembers between launches.

Two values, in ``ui_prefs.json`` beside the AI credentials (``~/.fta_editor``):

* ``lastFolder`` -- the folder of the file last opened or saved, so the file
  dialog of an untitled document starts where the user last worked instead
  of at the sandbox root every time.
* ``aiPanelCollapsed`` -- whether the AI panel is folded away.

Why on the server and not in the browser: a browser keeps its storage per
origin, port included, and up to 1.8.0 the app listened on a new port at
every launch, so whatever the page stored was gone at the next start. The
launcher now has a fixed default port (``config.DEFAULT_PORT``); these two
stay here, where they also survive a start on another port.

What this file is not
---------------------
It holds no secret and grants nothing. ``lastFolder`` is only a suggestion of
where to start: ``routes/files.py`` passes it through the sandbox check
(``fsbrowser.resolve_in_root``) before using it, exactly like a path typed by
the user, so a value somebody edited to point outside the sandbox root is
ignored. A missing, unreadable or malformed file means "nothing remembered",
and a failed write is dropped: remembering a folder must never fail the Open
or the Save it belongs to.

The directory is read from ``AICredentialManager.CREDENTIALS_DIR`` at each
call, not copied at import, so there is one place that says where the app
keeps its per-user files (and one thing for a test to redirect).
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Optional

try:  # normal package import: ``import fta_web.user_prefs``
    from . import config  # noqa: F401  (puts fta_web/core on sys.path)
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import config  # type: ignore[no-redef]  # noqa: F401

from AI_agent_handler import AICredentialManager  # noqa: E402

PREFS_NAME = "ui_prefs.json"

#: A prefs file larger than this was not written by this module; it is not read.
MAX_PREFS_BYTES = 64 * 1024

#: Longest folder path stored. Longer than any path Windows or Linux accepts.
MAX_PATH_CHARS = 4096

#: Keys the page may set through ``POST /api/prefs``, with their type.
#: ``lastFolder`` is deliberately not one of them: only an Open or a Save that
#: went through the sandbox sets it.
CLIENT_KEYS = {"aiPanelCollapsed": bool}

# Read-modify-write of one small file. Its own lock, never AppState.lock: it
# touches the disk and no document state.
_lock = threading.Lock()


def prefs_file() -> Path:
    """Where the prefs live: beside the AI credentials."""
    return Path(AICredentialManager.CREDENTIALS_DIR) / PREFS_NAME


def _read() -> Dict[str, Any]:
    """The stored object, or ``{}`` for anything that is not one."""
    path = prefs_file()
    try:
        if path.stat().st_size > MAX_PREFS_BYTES:
            return {}
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(data: Dict[str, Any]) -> bool:
    """Replace the file with ``data``. False, and nothing changed, on failure.

    Written beside the target and renamed over it, so a crash part-way leaves
    the previous file, not half of the new one.
    """
    path = prefs_file()
    temp_name: Optional[str] = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        handle, temp_name = tempfile.mkstemp(prefix=".ui_prefs_", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(data, out, indent=2, ensure_ascii=False)
        os.replace(temp_name, path)
        return True
    except (OSError, ValueError, TypeError):
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        return False


def _update(changes: Dict[str, Any]) -> bool:
    with _lock:
        data = _read()
        if all(data.get(key) == value for key, value in changes.items()):
            return True  # nothing to write
        data.update(changes)
        return _write(data)


def last_folder() -> Optional[str]:
    """The remembered folder as stored, or None. NOT validated: the caller
    confines it to the sandbox root before using it."""
    value = _read().get("lastFolder")
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        return None
    if len(value) > MAX_PATH_CHARS:
        return None
    return value


def remember_folder(folder: Any) -> bool:
    """Remember ``folder`` (a path the sandbox has already accepted)."""
    text = str(folder or "")
    if not text.strip() or "\x00" in text or len(text) > MAX_PATH_CHARS:
        return False
    return _update({"lastFolder": text})


def client_prefs() -> Dict[str, Any]:
    """The values the page reads (``/api/state`` ``prefs``), with defaults."""
    stored = _read()
    out: Dict[str, Any] = {}
    for key, kind in CLIENT_KEYS.items():
        value = stored.get(key)
        out[key] = value if isinstance(value, kind) else kind()
    return out


def set_client_prefs(changes: Dict[str, Any]) -> Dict[str, Any]:
    """Store validated page preferences and return all of them.

    Raises ``ValueError`` naming the key for one that is unknown or of the
    wrong type; nothing is written then.
    """
    clean: Dict[str, Any] = {}
    for key, value in changes.items():
        kind = CLIENT_KEYS.get(key)
        if kind is None:
            raise ValueError(key)
        # bool is checked by identity of type: 1 and "true" are not booleans.
        if type(value) is not kind:
            raise ValueError(key)
        clean[key] = value
    if clean:
        _update(clean)
    return client_prefs()
