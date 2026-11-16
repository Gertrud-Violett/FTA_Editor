"""
The operating system's own "choose a folder" dialog, opened by the server.

WHY THE SERVER OPENS IT
=======================
The sandbox root (``fsbrowser.py``) is the one thing that still stands when
the session token has leaked: whoever holds the token can read and write
inside the root, and nowhere else. If the root could be changed by a request
that names a folder, it would stand for nothing -- the same caller would first
ask for ``/`` and then read what it liked.

So the root can be changed while the editor runs in exactly one way: the
*person at the machine* picks a folder in a native dialog that this process
opens. The request that asks for it (``POST /api/fs/root/choose``) carries no
path and is refused if it carries anything at all; a page, a script or a
stolen token can make the dialog appear, and cannot answer it. The dialog
belongs to the operating system, not to the browser, so nothing running in a
page can click in it or read from it.

HOW
===
A short-lived helper process shows the dialog and prints the choice; this
process reads one line from it. A separate process because a native dialog
needs a thread of its own kind (an STA thread on Windows, the main thread
for Tk on macOS), and a Flask worker thread is neither.

* **Windows:** ``powershell.exe`` with a constant script that shows
  ``System.Windows.Forms.FolderBrowserDialog``. No extra package, and it
  works in the packaged app, which excludes tkinter (``build/fta_editor.spec``)
  to save tens of megabytes.
* **Elsewhere, from source:** this Python with a constant ``-c`` program that
  shows ``tkinter.filedialog.askdirectory`` on a hidden root window.

Both command lines are **constants**: nothing from a request, from the
document or from the filesystem is ever interpolated into them. The folder
the dialog starts in is the current root, handed over in an environment
variable and used only as the value of a property. The answer comes back as
base64 of the UTF-8 path, so a folder with Japanese characters survives
whatever code page the console has.

When there is no way to show a dialog -- a packaged build on Linux or macOS
(no tkinter in it), no display (SSH, CI, a container), PowerShell missing or
forbidden -- :func:`available` says so and the route answers 501
``PICKER_UNAVAILABLE``. The page then shows what it always showed: the
command that starts the editor on another folder.

This module is Flask-free and knows nothing about the sandbox: it returns a
string the person chose, and ``routes/files.py`` puts it through the same
normalisation as ``--root`` before it means anything.
"""
from __future__ import annotations

import base64
import importlib.util
import os
import subprocess
import sys
import threading
from typing import Dict, List, Optional, Tuple

try:  # normal package import: ``import fta_web.folder_picker``
    from . import runtime_paths
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import runtime_paths  # type: ignore[no-redef]

#: How long the dialog may stay open before the helper is stopped and the
#: request answered as cancelled. Long: the person may be looking for the
#: folder. Bounded: a dialog nobody sees (behind a full-screen window) must
#: not hold the picker for ever.
TIMEOUT_SECONDS = 600

#: The environment variable the helper reads its start folder from.
START_ENV = "FTA_EDITOR_PICKER_START"

#: Set (to anything) to switch the dialog off: the endpoint then answers 501
#: as on a machine without a display. The GUI test suite sets it for the
#: server it starts.
DISABLE_ENV = "FTA_EDITOR_NO_FOLDER_PICKER"

#: The marker in front of the answer, so that anything else a helper prints
#: (a banner, a warning) is not taken for a path.
ANSWER_PREFIX = "FTA_PICKED:"

#: The dialog's caption. A constant in both helpers.
PROMPT = "FTA Editor: choose the folder this editor may read and write"

# -- the two helpers. CONSTANTS: never formatted, never concatenated with data.

_POWERSHELL_SCRIPT = (
    "$ErrorActionPreference = 'Stop'; "
    "Add-Type -AssemblyName System.Windows.Forms; "
    "[System.Windows.Forms.Application]::EnableVisualStyles(); "
    "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
    "$d.Description = 'FTA Editor: choose the folder this editor may read and write'; "
    "$d.ShowNewFolderButton = $true; "
    "$s = $env:FTA_EDITOR_PICKER_START; "
    "if ($s -and (Test-Path -LiteralPath $s -PathType Container)) { $d.SelectedPath = $s }; "
    # An invisible, top-most owner: without one the dialog can open behind
    # the browser window, where nobody looks for it.
    "$o = New-Object System.Windows.Forms.Form; "
    "$o.TopMost = $true; $o.ShowInTaskbar = $false; $o.Opacity = 0; "
    "$o.StartPosition = 'CenterScreen'; $o.Show(); $o.Activate(); "
    "$r = $d.ShowDialog($o); $o.Close(); "
    "if ($r -eq [System.Windows.Forms.DialogResult]::OK) { "
    "[Console]::Out.WriteLine('FTA_PICKED:' + [Convert]::ToBase64String("
    "[System.Text.Encoding]::UTF8.GetBytes($d.SelectedPath))) }"
)

_TKINTER_PROGRAM = (
    "import base64, os, sys\n"
    "import tkinter\n"
    "from tkinter import filedialog\n"
    "root = tkinter.Tk()\n"
    "root.withdraw()\n"
    "try:\n"
    "    root.attributes('-topmost', True)\n"
    "except Exception:\n"
    "    pass\n"
    "start = os.environ.get('FTA_EDITOR_PICKER_START') or None\n"
    "if start and not os.path.isdir(start):\n"
    "    start = None\n"
    "chosen = filedialog.askdirectory(parent=root, mustexist=True, initialdir=start,\n"
    "    title='FTA Editor: choose the folder this editor may read and write')\n"
    "root.destroy()\n"
    "if chosen:\n"
    "    sys.stdout.write('FTA_PICKED:' + base64.b64encode(str(chosen).encode('utf-8')).decode('ascii') + '\\n')\n"
)


class PickerUnavailable(Exception):
    """No dialog can be shown here. ``reason`` is a stable discriminator."""

    def __init__(self, message: str, reason: str):
        super().__init__(message)
        self.reason = reason


class PickerBusy(Exception):
    """A dialog is already open: one at a time."""


def _powershell_path() -> Optional[str]:
    """Windows PowerShell at its fixed place under the system folder, or
    None. Not looked up on PATH: the first ``powershell.exe`` on PATH is
    whatever somebody put there."""
    system_root = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    candidate = os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return candidate if os.path.isfile(candidate) else None


def _has_display() -> bool:
    """Whether a graphical session is there for Tk to open a window in."""
    if sys.platform == "darwin":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def backend() -> Tuple[Optional[str], str]:
    """``(name, reason)``: the helper that would be used (``"powershell"`` or
    ``"tkinter"``) and ``""``, or ``(None, why not)``. Cheap; asked on every
    ``/api/fs/home``."""
    if os.environ.get(DISABLE_ENV):
        # Switched off for this process: a server driven by a test suite (a
        # dialog nobody is there to answer), or by somebody who wants the
        # folder fixed for the whole run.
        return None, "disabled"
    if os.name == "nt":
        if _powershell_path():
            return "powershell", ""
        return None, "no_powershell"
    if runtime_paths.is_frozen():
        # The packaged app carries no tkinter (build/fta_editor.spec), and
        # sys.executable is the app, not a Python that takes ``-c``.
        return None, "packaged_without_tkinter"
    if not _has_display():
        return None, "no_display"
    try:
        if importlib.util.find_spec("tkinter") is None:
            return None, "no_tkinter"
    except (ImportError, ValueError):
        return None, "no_tkinter"
    return "tkinter", ""


def available() -> bool:
    return backend()[0] is not None


def command(name: str) -> List[str]:
    """The helper's command line. Every element is a constant or the path of
    a fixed executable; no caller can add to it."""
    if name == "powershell":
        return [
            _powershell_path() or "powershell.exe",
            "-NoLogo", "-NoProfile", "-NonInteractive", "-STA",
            "-Command", _POWERSHELL_SCRIPT,
        ]
    if name == "tkinter":
        return [sys.executable, "-I", "-c", _TKINTER_PROGRAM]
    raise ValueError("unknown picker backend")


def _helper_environment(start: Optional[str]) -> Dict[str, str]:
    env = dict(os.environ)
    env.pop(START_ENV, None)
    if isinstance(start, str) and start and "\x00" not in start:
        env[START_ENV] = start
    return env


def parse_answer(output: str) -> Optional[str]:
    """The chosen folder from a helper's output, or None for a cancel.

    Only a line that starts with the marker and decodes cleanly counts. No
    such line is a cancel: a dialog that was closed prints nothing.
    """
    for line in (output or "").splitlines():
        line = line.strip()
        if not line.startswith(ANSWER_PREFIX):
            continue
        try:
            text = base64.b64decode(line[len(ANSWER_PREFIX):], validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
        text = text.strip()
        return text if text and "\x00" not in text else None
    return None


_one_at_a_time = threading.Lock()


def is_open() -> bool:
    return _one_at_a_time.locked()


def pick(start: Optional[str] = None) -> Optional[str]:
    """Show the dialog and wait for the person. Returns the folder they
    chose, as the dialog reported it, or None when they cancelled (or the
    dialog was open for ``TIMEOUT_SECONDS``).

    Raises:
        PickerUnavailable: no dialog can be shown here, or the helper failed
            to show one.
        PickerBusy: a dialog is already open.

    ``start`` is where the dialog opens; it comes from the server's own
    state (the current root), never from a request.
    """
    name, reason = backend()
    if name is None:
        raise PickerUnavailable("No folder chooser can be opened here (%s)." % reason, reason)
    if not _one_at_a_time.acquire(blocking=False):
        raise PickerBusy("A folder chooser is already open on this computer.")
    try:
        return _run_helper(name, start)
    finally:
        _one_at_a_time.release()


def _start_helper(argv: List[str], **kwargs):
    """``subprocess.run``, under a name of this module's own: the one place a
    process is started, and the one thing a test replaces so that no dialog
    is ever opened by the test suite."""
    return subprocess.run(argv, **kwargs)


def _run_helper(name: str, start: Optional[str]) -> Optional[str]:
    kwargs = {}
    if os.name == "nt":
        # No console window flashing up beside the dialog.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        done = _start_helper(
            command(name),
            env=_helper_environment(start),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=TIMEOUT_SECONDS,
            shell=False,
            **kwargs,
        )
    except subprocess.TimeoutExpired:
        return None  # subprocess.run has stopped the helper by then
    except OSError as exc:
        raise PickerUnavailable(
            "The folder chooser could not be started (%s)." % (exc.strerror or type(exc).__name__),
            "helper_failed",
        ) from exc
    output = done.stdout.decode("utf-8", errors="replace") if done.stdout else ""
    chosen = parse_answer(output)
    if chosen is None and done.returncode != 0:
        # It did not show a dialog at all (PowerShell forbidden by policy,
        # Tk without a display after all): that is not a cancel.
        raise PickerUnavailable(
            "The folder chooser could not be shown on this computer.", "helper_failed"
        )
    return chosen
