"""
File and export endpoints -- opening, saving, and downloading the document.

This is the blueprint that reaches the real filesystem, so read
``fta_web/fsbrowser.py`` first: it holds the sandbox rules and the reasoning
behind them. Nothing here builds a path by hand. Every path that arrives from
the client goes through ``fsbrowser.resolve_for_open`` /
``resolve_for_write`` / ``list_directory``, and those are the only functions
that turn client text into something ``open()`` ever sees.

Endpoints
---------
==============================  ==========================================
``GET  /api/fs/home``           where the picker should start
``GET  /api/fs/list``           one directory, filtered to openable files
``POST /api/file/open``         replace the document from a file on disk
``POST /api/file/save``         write back to the current path
``POST /api/file/save-as``      write to a new path and adopt it
``GET  /api/export/{json,xml,xlsx}``  download a rendering of the document
``POST /api/import/json``       replace the document from an upload
==============================  ==========================================

Decisions a reviewer should know about
--------------------------------------
**Open and import build a throwaway ``FTACore`` first.** ``load_from_json``
mutates in place and reports failure by return value, so loading straight into
the live core would leave a half-replaced document behind on a bad file. The
new core is built, loaded and only then swapped in under the lock, which makes
a failed open a no-op for the user's work.

**Open does not refuse to discard unsaved changes**, unlike ``POST /api/new``,
which answers 409 ``UNSAVED_CHANGES`` unless forced. The published contract
for this endpoint is ``{path}`` in, document out, and the frontend is written
against exactly that -- it owns the "you have unsaved changes" confirmation,
because it is the side that can show a dialog. Adding a server-side refusal
here would break it. The tension is deliberate and recorded rather than
silently resolved either way.

**Import leaves ``currentPath`` null and the document dirty.** The bytes came
from the browser, not from a file this server can write back to, so there is
nothing to Save to; the next Save answers 409 ``NO_CURRENT_PATH`` and the
frontend sends the user to Save As. Marking it dirty is what makes
``POST /api/new`` warn before throwing the import away.

**Saves are atomic.** The document is written to a temp file beside the target
and then ``os.replace``d onto it. ``save_to_json`` opens the target with
``'w'``, which truncates before writing, so a full disk part-way through a
direct save would leave the user with a truncated analysis and no backup. A
rename cannot half-happen.

**Exports never touch the sandbox.** They are downloads: written to a temp
file outside the user's tree, read back, deleted in a ``finally``, and
streamed from memory. Nothing is left behind on any path, including failure,
and an export cannot overwrite a file by accident.

Known limitation inherited from the frozen core
-----------------------------------------------
``load_from_json`` decides a file is double-brace-wrapped by testing
``content.endswith("}}")`` and then strips a brace off each end. A *minified*
analysis ends in exactly those two braces -- the tree's, then the document's
-- so it is mangled into invalid JSON and reported as unreadable, by both
``/api/file/open`` and ``/api/import/json``. Files written by this editor and
by the desktop one are indented (``save_to_json`` uses ``indent=2``) and never
trip it; a tree minified by another tool does. It is not worked around here:
this layer must not grow a second JSON reader, and the fix belongs in the core
behind a DIVERGENCE entry. ``test_api_files.py`` pins the behaviour so the day
it changes is not a silent one.
"""
from __future__ import annotations

import copy
import importlib.util
import io
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from flask import Blueprint, request, send_file

try:  # normal package import: ``import fta_web.routes.files``
    from .. import fsbrowser
    from ..config import ALLOWED_OPEN_EXTENSIONS, MAX_UPLOAD_BYTES
    from ..errors import (
        INVALID_FIELD,
        INVALID_JSON,
        NO_CURRENT_PATH,
        PATH_REJECTED,
        ApiError,
        ok_response,
    )
    from ..state import get_state
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import fsbrowser  # type: ignore[no-redef]
    from config import (  # type: ignore[no-redef]
        ALLOWED_OPEN_EXTENSIONS,
        MAX_UPLOAD_BYTES,
    )
    from errors import (  # type: ignore[no-redef]
        INVALID_FIELD,
        INVALID_JSON,
        NO_CURRENT_PATH,
        PATH_REJECTED,
        ApiError,
        ok_response,
    )
    from state import get_state  # type: ignore[no-redef]

# Both import paths above have already put fta_web/core on sys.path.
from FTA_Editor_core import FTACore  # noqa: E402

files_bp = Blueprint("files", __name__, url_prefix="/api")

# ---------------------------------------------------------------------------
# Error codes owned by this blueprint.
#
# errors.py holds the shared vocabulary; these two are local for the same
# reason app.py keeps its transport-level codes local -- promote them into
# errors.py if anything else ever needs them. PAYLOAD_TOO_LARGE deliberately
# repeats the string app.py's 413 handler emits, so an oversized import looks
# the same to the frontend whether Flask's MAX_CONTENT_LENGTH caught it or we
# did.
# ---------------------------------------------------------------------------
EXPORT_UNAVAILABLE = "EXPORT_UNAVAILABLE"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"

#: Named in the "no openpyxl" failure so the remedy travels with the error
#: instead of living only in the docs -- the same policy rendering.py applies
#: to a missing Graphviz.
EXCEL_MISSING_MESSAGE = (
    "Excel export needs the 'openpyxl' package, which is not installed on "
    "this machine. Install it with:\n"
    "\n"
    "    pip install openpyxl\n"
    "\n"
    "(or 'python3 -m pip install openpyxl' if 'pip' is not on your PATH), "
    "then restart the editor. JSON and XML export do not need it."
)

XLSX_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

#: Multipart field names accepted by /api/import/json, in order of preference.
#: More than one because the frontend is being written concurrently; any other
#: single file part is accepted too (see _uploaded_file).
UPLOAD_FIELDS = ("file", "json", "upload", "tree")

# Mode for a newly created save file. mkstemp makes its file 0600, which would
# silently make every new analysis owner-only -- stricter than the desktop
# editor and surprising on a shared drive. The umask is read once at import
# (single-threaded, before any request) because reading it requires
# temporarily clearing it, which is not safe to do with requests in flight.
def _default_file_mode() -> int:
    current = os.umask(0)
    os.umask(current)
    return 0o666 & ~current


_NEW_FILE_MODE = _default_file_mode()


@files_bp.errorhandler(ApiError)
def _handle_api_error(exc: ApiError):
    # Registered on the blueprint as well as the app (see routes/tree.py) so
    # the blueprint returns the documented envelope wherever it is mounted.
    return exc.to_payload(), exc.status


@files_bp.errorhandler(fsbrowser.PathRejected)
def _handle_path_rejected(exc: fsbrowser.PathRejected):
    """Every sandbox refusal becomes one error code: ``PATH_REJECTED``.

    One code, because the client's recovery is always the same -- pick a
    different path -- and because a per-rule code would tell an attacker
    which check fired. ``detail.reason`` carries that distinction for the log
    and for the frontend's wording; it never names anything outside the root.
    """
    return (
        ApiError(
            PATH_REJECTED, str(exc), exc.status, {"reason": exc.reason}
        ).to_payload(),
        exc.status,
    )


@files_bp.record_once
def _adopt_app_fs_root(setup_state) -> None:
    """Copy the app's configured sandbox root onto the shared AppState.

    ``create_app(fs_root=...)`` stores the root in ``app.config`` while
    everything at runtime reads ``AppState.fs_root``; without this bridge
    ``run.py --root`` would be accepted, printed at startup, and then ignored
    -- leaving the sandbox pointing at the whole home directory. Runs once, at
    blueprint registration, so ``AppState.fs_root`` stays the single source of
    truth for every request (and stays overridable by tests, which set it
    after building the app).
    """
    root = setup_state.app.config.get("FTA_FS_ROOT")
    if root:
        get_state().fs_root = Path(root)


# ---- request helpers -----------------------------------------------------


def _body() -> Dict[str, Any]:
    """The request's JSON object. An absent body is an empty object."""
    data = request.get_json(silent=True)
    if data is None:
        if not request.get_data():
            return {}
        raise ApiError(INVALID_JSON, "Request body must be a JSON object.", 400)
    if not isinstance(data, dict):
        raise ApiError(INVALID_JSON, "Request body must be a JSON object.", 400)
    return data


def _required_path(payload: Dict[str, Any]) -> Any:
    """The raw ``path`` field, unvalidated -- fsbrowser does that."""
    if "path" not in payload:
        raise ApiError(INVALID_FIELD, "'path' is required.", 400, {"field": "path"})
    return payload["path"]


def _fs_root() -> Path:
    """The sandbox root for this request, resolved."""
    return fsbrowser.resolve_root(get_state().fs_root)


# ---- response helpers ----------------------------------------------------


def _document_payload(state) -> Dict[str, Any]:
    """The whole-document view returned by open and import."""
    core = state.core
    return {
        "tree": copy.deepcopy(core.get_data()),
        "metadata": core.get_metadata(),
        "zeroNodes": core.get_zero_probability_nodes(),
        "currentPath": str(state.current_path) if state.current_path else None,
        "dirty": state.dirty,
        "canUndo": state.can_undo,
        "canRedo": state.can_redo,
    }


def _install_document(state, core: FTACore, path: Optional[Path],
                      dirty: bool) -> None:
    """Make ``core`` the live document. Caller holds ``state.lock``.

    ``reset()`` is what clears the undo/redo stacks -- they are private to
    AppState and this is the supported way to drop them -- and it also clears
    the path and the dirty flag, which are then set to the values this load
    implies. The freshly loaded core replaces the empty one reset() made.
    """
    state.reset()
    state.core = core
    state.current_path = path
    state.dirty = dirty


# ---- filesystem browsing -------------------------------------------------


@files_bp.get("/fs/home")
def fs_home():
    """Where the file picker should open.

    ``cwd`` is the folder of the open document when there is one, so Save As
    lands next to the file the user is editing; the root otherwise. A
    ``current_path`` that no longer resolves inside the root (the sandbox
    moved, the file was moved out) falls back to the root rather than
    reporting a folder the picker would then refuse to list.
    """
    state = get_state()
    root = _fs_root()
    with state.lock:
        current = state.current_path

    cwd = root
    if current is not None:
        try:
            resolved = fsbrowser.resolve_in_root(str(current), root)
            if resolved.parent.is_dir():
                cwd = resolved.parent
        except fsbrowser.PathRejected:
            cwd = root
    return ok_response(root=str(root), cwd=str(cwd))


@files_bp.get("/fs/list")
def fs_list():
    """One directory's contents. ``?path=`` defaults to the sandbox root."""
    root = _fs_root()
    return ok_response(**fsbrowser.list_directory(request.args.get("path"), root))


# ---- open / save ---------------------------------------------------------


@files_bp.post("/file/open")
def file_open():
    """Replace the document with the contents of a JSON file on disk."""
    payload = _body()
    raw_path = _required_path(payload)
    state = get_state()
    target = fsbrowser.resolve_for_open(raw_path, _fs_root())

    # Read outside the lock: the file may be large and the parse is the slow
    # part of this request. Nothing shared is touched until the swap below.
    loaded = FTACore()
    ok, error = loaded.load_from_json(str(target))
    if not ok:
        # The message names the file, never the full path: the client already
        # knows the path it sent, and the vendored loader's own text can
        # contain one.
        raise ApiError(
            INVALID_JSON,
            "'%s' could not be read as an FTA analysis: %s"
            % (target.name, error or "unrecognised format"),
            400,
            {"reason": "load_failed"},
        )

    with state.lock:
        _install_document(state, loaded, target, dirty=False)
        return ok_response(**_document_payload(state))


@files_bp.post("/file/save")
def file_save():
    """Write the document back to the path it was opened from or saved to."""
    state = get_state()
    root = _fs_root()
    with state.lock:
        if state.current_path is None:
            raise ApiError(
                NO_CURRENT_PATH,
                "This analysis has never been saved, so there is no file to "
                "save it to. Use Save As and choose a location.",
                409,
            )
        # Re-validated rather than trusted: the path was checked when it was
        # set, but the sandbox root can be different now (a fresh launch with
        # another --root), and a path that is no longer inside it must not be
        # written to just because we remembered it.
        target = fsbrowser.resolve_for_write(
            str(state.current_path), root, {".json"}
        )
        _save_document(state.core, target)
        state.current_path = target
        state.mark_saved()
        return ok_response(currentPath=str(target), dirty=state.dirty)


@files_bp.post("/file/save-as")
def file_save_as():
    """Write the document to a new path and make that the current one."""
    payload = _body()
    raw_path = _required_path(payload)
    state = get_state()
    # ``.json`` only, not the whole write allow-list: this endpoint writes the
    # editor's own format, and saving it as ``.xlsx`` would produce a file
    # neither this editor nor Excel could open. The other extensions in
    # ALLOWED_WRITE_EXTENSIONS belong to the export endpoints.
    target = fsbrowser.resolve_for_write(raw_path, _fs_root(), {".json"})

    with state.lock:
        _save_document(state.core, target)
        state.current_path = target
        state.mark_saved()
        return ok_response(currentPath=str(target), dirty=state.dirty)


def _save_document(core: FTACore, target: Path) -> None:
    """Serialize ``core`` onto ``target`` atomically.

    Writes a temp file in the target's own directory (so the rename stays on
    one filesystem and cannot fail with EXDEV) and renames it into place.
    Nothing observes a partially written analysis, and a failure leaves the
    previous file exactly as it was.
    """
    handle, temp_name = tempfile.mkstemp(
        prefix=".fta_save_", suffix=".tmp", dir=str(target.parent)
    )
    os.close(handle)
    temp_path = Path(temp_name)
    # save_to_json() records the path it wrote as ``last_saved_file``. Left
    # alone it would point at this temp file, which is about to stop existing
    # -- and a later save_to_json(None) would then write the user's analysis
    # to a deleted temp name.
    previous = getattr(core, "last_saved_file", None)
    try:
        ok, error = core.save_to_json(str(temp_path))
        if not ok:
            raise ApiError(
                INVALID_FIELD,
                "Could not save '%s': %s" % (target.name, error or "unknown error"),
                500,
                {"reason": "write_failed"},
            )
        _apply_mode(target, temp_path)
        os.replace(temp_path, target)
        core.last_saved_file = str(target)
    except Exception:
        core.last_saved_file = previous
        raise
    finally:
        _unlink_quietly(temp_path)


def _apply_mode(target: Path, temp_path: Path) -> None:
    """Give the replacement file the permissions the user expects.

    Overwriting keeps the existing file's mode; a new file gets the umask
    default instead of mkstemp's 0600. Permission games are never fatal --
    a saved analysis with unexpected bits is better than a failed save.
    """
    try:
        if target.exists():
            shutil.copymode(target, temp_path)
        else:
            os.chmod(temp_path, _NEW_FILE_MODE)
    except OSError:  # pragma: no cover - platform dependent
        pass


def _unlink_quietly(path: Path) -> None:
    """Delete a temp file, ignoring the ways deletion can fail.

    A cleanup failure must never replace the real exception on the way out of
    a ``finally`` block.
    """
    try:
        os.unlink(path)
    except OSError:
        pass


# ---- exports -------------------------------------------------------------


def _export_json(core: FTACore, path: str) -> Tuple[bool, Optional[str]]:
    """The document as the editor's own JSON, byte-for-byte what Save writes."""
    previous = getattr(core, "last_saved_file", None)
    try:
        return core.save_to_json(path)
    finally:
        # An export is not a save: the document keeps whatever file it belongs
        # to, and must not start considering this temp file its home.
        core.last_saved_file = previous


def _export_xml(core: FTACore, path: str) -> Tuple[bool, Optional[str]]:
    return core.export_to_xml(path)


def _export_xlsx(core: FTACore, path: str) -> Tuple[bool, Optional[str]]:
    return core.export_to_excel(path)


#: format -> (suffix, MIME type, writer). Also the allow-list: the ``<fmt>``
#: in the URL is looked up here and nothing else is served, so the path
#: segment never reaches a filename or a MIME type unchecked.
EXPORTS: Dict[str, Tuple[str, str, Callable[[FTACore, str], Tuple[bool, Optional[str]]]]] = {
    "json": (".json", "application/json", _export_json),
    "xml": (".xml", "application/xml", _export_xml),
    "xlsx": (".xlsx", XLSX_MIME, _export_xlsx),
}


def _openpyxl_available() -> bool:
    """Whether ``openpyxl`` can be imported *right now*.

    Re-probed per request rather than read from ``AppState.excel_export``, for
    the reason routes/render.py re-probes Graphviz: the startup flag is a
    snapshot, and the only honest answer is about the run that is happening.
    The probe is the same ``find_spec`` call ``state._probe_excel_export``
    uses -- including catching the ValueError a broken or stubbed installation
    raises -- so ``capabilities.excelExport`` and this endpoint cannot
    disagree about the same machine.
    """
    try:
        return importlib.util.find_spec("openpyxl") is not None
    except (ImportError, ValueError):
        return False


def _excel_unavailable() -> ApiError:
    return ApiError(
        EXPORT_UNAVAILABLE,
        EXCEL_MISSING_MESSAGE,
        503,
        {"format": "xlsx", "package": "openpyxl", "install": "pip install openpyxl"},
    )


@files_bp.get("/export/<fmt>")
def export_document(fmt: str):
    """Download the current document as JSON, XML or XLSX.

    The file is built in a temp directory, read back, and deleted before the
    response is sent, so nothing survives the request on any path -- including
    the failure paths, where a half-written export would otherwise pile up.
    """
    key = (fmt or "").strip().lower()
    if key not in EXPORTS:
        raise ApiError(
            INVALID_FIELD,
            "Unsupported export format '%s'; expected one of %s."
            % (fmt, ", ".join(sorted(EXPORTS))),
            404,
            {"field": "format", "value": fmt},
        )
    suffix, mimetype, writer = EXPORTS[key]

    if key == "xlsx" and not _openpyxl_available():
        raise _excel_unavailable()

    state = get_state()
    handle, temp_name = tempfile.mkstemp(prefix="fta_export_", suffix=suffix)
    os.close(handle)
    temp_path = Path(temp_name)
    try:
        with state.lock:
            # Under the lock for the whole write: every exporter walks the
            # live tree, so a concurrent edit mid-walk would produce a file
            # describing a document that never existed.
            ok, error = writer(state.core, str(temp_path))
            download_name = fsbrowser.safe_download_name(
                _document_stem(state), suffix
            )
        if not ok:
            if key == "xlsx" and "openpyxl" in (error or ""):
                # openpyxl was importable a moment ago but failed on use: a
                # broken install, or a stub left by a test. Same remedy, so
                # the same actionable message rather than the raw exception.
                raise _excel_unavailable()
            raise ApiError(
                EXPORT_UNAVAILABLE,
                "Could not build the %s export: %s"
                % (key.upper(), error or "unknown error"),
                500,
                {"format": key},
            )
        data = temp_path.read_bytes()
    finally:
        _unlink_quietly(temp_path)

    return send_file(
        io.BytesIO(data),
        mimetype=mimetype,
        as_attachment=True,
        download_name=download_name,
        max_age=0,
    )


def _document_stem(state) -> str:
    """Filename stem for a download: the open file's name, else the title."""
    if state.current_path is not None:
        return Path(state.current_path).stem
    return state.core.title or "fta_export"


# ---- import --------------------------------------------------------------


def _uploaded_file():
    """The uploaded part, whatever the frontend called it."""
    for field in UPLOAD_FIELDS:
        found = request.files.get(field)
        if found is not None:
            return found
    for found in request.files.values():  # a single part under another name
        return found
    raise ApiError(
        INVALID_FIELD,
        "No file was uploaded. Send the analysis as multipart/form-data with "
        "the JSON file in a 'file' part.",
        400,
        {"field": "file"},
    )


@files_bp.post("/import/json")
def import_json():
    """Replace the document with an uploaded JSON file.

    The upload is written to a temp file outside the sandbox and loaded with
    the same loader ``/api/file/open`` uses, so an imported file gets the same
    legacy-format and encoding handling as one opened from disk. The client's
    filename never becomes a path -- the temp name is generated here -- so it
    is checked only for a plainly wrong extension, and an extension-less part
    (a browser ``Blob`` arrives as ``blob``) is accepted and judged on its
    contents.
    """
    upload = _uploaded_file()
    filename = upload.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix and suffix not in {ext.lower() for ext in ALLOWED_OPEN_EXTENSIONS}:
        raise fsbrowser.PathRejected(
            "'%s' cannot be imported: only %s files are allowed."
            % (filename, ", ".join(sorted(ALLOWED_OPEN_EXTENSIONS))),
            reason="extension",
        )

    state = get_state()
    handle, temp_name = tempfile.mkstemp(prefix="fta_import_", suffix=".json")
    os.close(handle)
    temp_path = Path(temp_name)
    try:
        upload.save(str(temp_path))
        size = temp_path.stat().st_size
        if size > MAX_UPLOAD_BYTES:
            # Belt and braces: Flask's MAX_CONTENT_LENGTH normally rejects the
            # request before it reaches here, but that is app configuration
            # and this blueprint should be safe wherever it is mounted.
            raise ApiError(
                PAYLOAD_TOO_LARGE,
                "The uploaded file is %.1f MB, over the %.0f MB limit."
                % (size / 1048576.0, MAX_UPLOAD_BYTES / 1048576.0),
                413,
                {"limitBytes": MAX_UPLOAD_BYTES},
            )

        loaded = FTACore()
        ok, error = loaded.load_from_json(str(temp_path))
        if not ok:
            raise ApiError(
                INVALID_JSON,
                "'%s' could not be read as an FTA analysis: %s"
                % (filename or "the uploaded file", error or "unrecognised format"),
                400,
                {"reason": "load_failed"},
            )
    finally:
        _unlink_quietly(temp_path)

    # load_from_json() points last_saved_file at the file it read -- here, the
    # temp file deleted a line ago. Cleared so that nothing can later write
    # the user's analysis into /tmp.
    loaded.last_saved_file = None

    with state.lock:
        # No current path (the bytes came from the browser, not from a file
        # this server can write to) and therefore dirty: the work exists only
        # in memory until the user picks a location with Save As.
        _install_document(state, loaded, None, dirty=True)
        return ok_response(**_document_payload(state))
