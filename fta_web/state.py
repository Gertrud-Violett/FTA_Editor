"""
Process-wide mutable application state for the fta_web app.

The desktop editor keeps one open document per process; the web app keeps the
same model. ``AppState`` owns the single ``FTACore`` instance, the undo/redo
history, the dirty flag and the handful of per-launch facts the frontend needs
(whether Graphviz' ``dot`` binary exists, whether AI credentials are
configured, which language is active).

Threading
---------
Flask's dev server is threaded, so two requests can land at once. Every
mutation must be serialized on ``AppState.lock`` -- an ``RLock``, so a route
that already holds it can call ``push_undo()``/``snapshot()`` (which take it
again) without deadlocking. The lock guards the *tree*, not the process: it is
the caller's job to take it around a whole read-modify-write, not just around
the individual helper calls.

Import style
------------
Prefer the package form (``from fta_web.state import get_state``). The bare
fallback below exists only for a launcher that puts ``fta_web/`` itself on
``sys.path``; mixing the two in one process would create two distinct module
objects and therefore two distinct singletons.
"""
from __future__ import annotations

import copy
import shutil
import threading
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, Optional

try:  # normal package import: ``import fta_web.state``
    from . import config
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import config  # type: ignore[no-redef]

# Importing config placed fta_web/core on sys.path, so the vendored modules
# import under their bare names. See config.py for why that is mandatory.
from AI_agent_handler import AICredentialManager  # noqa: E402
from FTA_Editor_core import FTACore  # noqa: E402


# ``shutil.which`` hits the filesystem for every entry in PATH. The answer
# cannot change during a run, so probe once per process and share the result
# across AppState instances (tests build many via reset_state()).
_NATIVE_DOT_UNPROBED = object()
_native_dot_cache: Any = _NATIVE_DOT_UNPROBED


def _probe_native_dot() -> Optional[str]:
    """Return the path to the Graphviz ``dot`` binary, or None. Probed once."""
    global _native_dot_cache
    if _native_dot_cache is _NATIVE_DOT_UNPROBED:
        _native_dot_cache = shutil.which("dot")
    return _native_dot_cache  # type: ignore[return-value]


def _ai_configured() -> bool:
    """Whether AI credentials are on disk.

    ``AICredentialManager.__init__`` mkdir's ~/.fta_editor as a side effect, so
    this is deliberately cheap-but-not-free; a failure to create that directory
    is reported as "not configured" rather than breaking /api/state.
    """
    try:
        return bool(AICredentialManager().has_credentials())
    except Exception:
        return False


class AppState:
    """The single open document, plus its undo history and session facts."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.core = FTACore()
        self.current_path: Optional[Path] = None
        self.dirty: bool = False
        self.native_dot: Optional[str] = _probe_native_dot()
        self.language: str = config.DEFAULT_LANGUAGE
        self.fs_root: Path = Path(config.DEFAULT_FS_ROOT)
        self._undo: Deque[Dict[str, Any]] = deque(maxlen=config.UNDO_DEPTH)
        self._redo: Deque[Dict[str, Any]] = deque(maxlen=config.UNDO_DEPTH)
        # Give the fresh root a calculatedProbability so every payload the API
        # emits has the same node shape, even before the first mutation.
        self.core.recalculate_probabilities()

    # ---- history ---------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        """A deep, detached copy of everything a document edit can change."""
        with self.lock:
            return {
                "tree": copy.deepcopy(self.core.get_data()),
                "title": self.core.title,
                "date": self.core.date,
                "mode": self.core.mode,
            }

    def restore(self, snap: Dict[str, Any]) -> None:
        """Install a snapshot as the live document.

        The tree is deep-copied on the way in as well as on the way out: the
        same snapshot dict may still be sitting on the redo stack, and a live
        tree that shared structure with it would corrupt the history the next
        time a node was edited in place.
        """
        with self.lock:
            self.core.set_data(copy.deepcopy(snap.get("tree", {})))
            # Assigned directly rather than through set_metadata(), which
            # rewrites `date` to today whenever it is passed None.
            self.core.title = snap.get("title", self.core.title)
            self.core.date = snap.get("date", self.core.date)
            self.core.mode = snap.get("mode", self.core.mode)

    def push_undo(self) -> None:
        """Record the pre-mutation state. Call this *before* mutating."""
        with self.lock:
            self._undo.append(self.snapshot())
            self._redo.clear()

    def undo(self) -> bool:
        """Step back one edit. False (and no change) if there is nothing to undo."""
        with self.lock:
            if not self._undo:
                return False
            self._redo.append(self.snapshot())
            self.restore(self._undo.pop())
            return True

    def redo(self) -> bool:
        """Step forward one edit. False (and no change) if there is nothing to redo."""
        with self.lock:
            if not self._redo:
                return False
            self._undo.append(self.snapshot())
            self.restore(self._redo.pop())
            return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    # ---- document lifecycle ---------------------------------------------

    def mark_dirty(self) -> None:
        with self.lock:
            self.dirty = True

    def mark_saved(self) -> None:
        with self.lock:
            self.dirty = False

    def reset(self) -> None:
        """Start a new, empty document. Clears history, path and dirty flag."""
        with self.lock:
            self.core = FTACore()
            self._undo.clear()
            self._redo.clear()
            self.current_path = None
            self.dirty = False
            self.core.recalculate_probabilities()

    # ---- serialization ---------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """The /api/state payload.

        The tree is deep-copied so the caller can serialize it without holding
        the lock while another request mutates the live structure.
        """
        with self.lock:
            return {
                "tree": copy.deepcopy(self.core.get_data()),
                "metadata": self.core.get_metadata(),
                "dirty": self.dirty,
                "currentPath": str(self.current_path) if self.current_path else None,
                "nativeDot": bool(self.native_dot),
                "aiConfigured": _ai_configured(),
                "canUndo": self.can_undo,
                "canRedo": self.can_redo,
                "language": self.language,
                "zeroNodes": self.core.get_zero_probability_nodes(),
            }


# ---- process singleton ---------------------------------------------------

_state: Optional[AppState] = None
_state_lock = threading.Lock()


def get_state() -> AppState:
    """The one AppState for this process, created on first use."""
    global _state
    with _state_lock:
        if _state is None:
            _state = AppState()
        return _state


def reset_state() -> AppState:
    """Replace the singleton with a fresh AppState and return it.

    Used by tests to get an isolated document; also the honest way to drop a
    session's history without leaving stale references behind.
    """
    global _state
    with _state_lock:
        _state = AppState()
        return _state
