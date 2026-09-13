"""
Where the app's files live, in both of the two layouts it ships in.

There are exactly two:

* **source** -- ``python3 fta_web/run.py`` from a checkout. Data files sit
  beside this module: ``fta_web/static``, ``fta_web/templates``,
  ``fta_web/core``, ``fta_web/examples``.
* **frozen** -- a PyInstaller *onedir* bundle. The Python modules are compiled
  into the archive and the four data directories are unpacked next to it, at
  the root PyInstaller exposes as ``sys._MEIPASS``. In a onedir build that is
  ``<dist>/fta_editor/_internal/``; the executable is one level up.

The layouts are deliberately identical below the root, so every caller is
``resource_root() / "static"`` and friends, and the only thing that varies is
which directory ``resource_root()`` returns. ``build/fta_editor.spec`` is the
other half of that contract: it maps ``fta_web/<dir>`` to ``<dir>`` for each of
the four. Change one and you must change the other.

Why this module exists at all
-----------------------------
``config.py`` used to derive everything from ``Path(__file__).parent``. Frozen
modules do get a ``__file__``, but it points at a compiled entry inside the
archive, which is a coincidence of the current PyInstaller rather than a
documented guarantee -- and it silently produces a *plausible* wrong path
(no exception, just a 404 for every stylesheet) when it changes. ``_MEIPASS``
is the documented answer, so ask for it explicitly, in one place, instead of
scattering ``sys.frozen`` tests through the modules that need a path.

Nothing here is cached: these are three attribute reads and a ``Path`` build,
and a test that freezes/unfreezes ``sys`` would have to invalidate a cache.
"""
from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["is_frozen", "resource_root", "app_root", "resource"]


def is_frozen() -> bool:
    """True when running from a PyInstaller (or equivalent) bundle."""
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """The directory that holds ``static/``, ``templates/``, ``core/``, ``examples/``.

    Frozen: ``sys._MEIPASS``. The fallback to the executable's own directory
    covers freezers that set ``sys.frozen`` without ``_MEIPASS`` -- it is not a
    layout this project builds, but returning the wrong-but-existing source
    path there would be worse than a near miss.

    Source: the ``fta_web/`` directory this file lives in.
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def app_root() -> Path:
    """The installation root: the repo checkout, or the unpacked bundle directory.

    Frozen, this is the directory containing the executable -- the folder the
    user actually copied around -- not ``_MEIPASS``. It is the right thing to
    put in a diagnostic; it is *not* a place to look for bundled data (use
    :func:`resource` for that), and it is not writable on every platform.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource(*parts: str) -> Path:
    """``resource_root()`` joined with ``parts``. Not checked for existence."""
    return resource_root().joinpath(*parts)
