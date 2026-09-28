"""
FMEA import -- ``/api/fmea/*`` (1.7, workstream C).

Both endpoints read a ``.csv`` or ``.xlsx`` file **on the server**, named by a
path the client picked with the sandboxed file dialog -- exactly like
``POST /api/file/open``. The path goes through ``fsbrowser.resolve_in_root``
(traversal, symlink and outside-root checks) plus an extension allow-list of
``.csv``/``.xlsx`` and the ``config.MAX_UPLOAD_BYTES`` size cap; every refusal
is 4xx ``PATH_REJECTED`` with ``detail.reason``.

``POST /api/fmea/preview``
    Body ``{path, sheet?}``. Returns ``{path, name, sheets: [names], sheet,
    columns: [header], rows: [[cell]] (first 50), rowNumbers, rowCount,
    suggestedMapping: {field: column}, suggestedLambdaUnit: h|y|FIT, fields,
    occurrenceTable}`` -- the table is the document's
    ``analysis.fmeaOccurrenceTable``. Read-only.

``POST /api/fmea/import``
    Body ``{path, sheet?, mapping: {field: column}, lambdaUnit: h|y|FIT,
    parentId, update: true, occurrenceTable?: {"1".."10": p}}``.
    One undo step, pushed only when something changes: rows whose key matches
    a node's ``fmea.id`` update it in place, the rest become new events under
    ``parentId`` (see ``fmea_import`` for the rules). An ``occurrenceTable``
    that differs from the document's is saved into
    ``analysis.fmeaOccurrenceTable`` in the same undo step. Returns the
    mutation payload plus ``{created: [ids], updated: [ids], unchanged: [ids],
    skipped: [{row, fmeaId, reason, field?, value?, message}], changed}``.

Errors: 409 ``MODE_UNSUPPORTED`` in ETA mode (checked first); 503
``EXPORT_UNAVAILABLE`` with ``detail.package = 'openpyxl'`` for an ``.xlsx``
when openpyxl is missing; 400 ``INVALID_FIELD`` for a bad body, an unreadable
file or an impossible mapping (``detail.reason`` from ``FmeaImportError``);
404 ``PARENT_NOT_FOUND``.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict

from flask import Blueprint, request

try:  # normal package import: ``import fta_web.routes.fmea``
    from .. import engine, fmea_import, fsbrowser
    from ..config import MAX_UPLOAD_BYTES
    from ..errors import (
        EXPORT_UNAVAILABLE,
        INVALID_FIELD,
        INVALID_JSON,
        MODE_UNSUPPORTED,
        PARENT_NOT_FOUND,
        PATH_REJECTED,
        ApiError,
        api_error_response,
        ok_response,
    )
    from ..state import get_state
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import engine  # type: ignore[no-redef]
    import fmea_import  # type: ignore[no-redef]
    import fsbrowser  # type: ignore[no-redef]
    from config import MAX_UPLOAD_BYTES  # type: ignore[no-redef]
    from errors import (  # type: ignore[no-redef]
        EXPORT_UNAVAILABLE,
        INVALID_FIELD,
        INVALID_JSON,
        MODE_UNSUPPORTED,
        PARENT_NOT_FOUND,
        PATH_REJECTED,
        ApiError,
        api_error_response,
        ok_response,
    )
    from state import get_state  # type: ignore[no-redef]

fmea_bp = Blueprint("fmea", __name__, url_prefix="/api/fmea")

PREVIEW_ROWS = 50

OPENPYXL_MISSING_MESSAGE = (
    "Reading .xlsx FMEA sheets needs the 'openpyxl' package, which is not "
    "installed on this machine. Install it with 'pip install openpyxl' and "
    "restart the editor, or save the sheet as .csv and import that."
)


@fmea_bp.errorhandler(ApiError)
def _handle_api_error(exc: ApiError):
    return api_error_response(exc)


@fmea_bp.errorhandler(fsbrowser.PathRejected)
def _handle_path_rejected(exc: fsbrowser.PathRejected):
    return api_error_response(
        ApiError(PATH_REJECTED, str(exc), exc.status, {"reason": exc.reason})
    )


# ---- helpers ---------------------------------------------------------------------


def _body() -> Dict[str, Any]:
    data = request.get_json(silent=True)
    if data is None:
        if not request.get_data():
            return {}
        raise ApiError(INVALID_JSON, "Request body must be a JSON object.", 400)
    if not isinstance(data, dict):
        raise ApiError(INVALID_JSON, "Request body must be a JSON object.", 400)
    return data


def _require_fta(state) -> None:
    if str(state.core.mode).upper() == "ETA":
        raise ApiError(
            MODE_UNSUPPORTED,
            "FMEA import is only available for fault trees (FTA mode); "
            "the document is an event tree (ETA mode).",
            409,
            {"mode": "ETA"},
        )


def _resolve(raw: Any) -> Path:
    """``resolve_for_open`` with the FMEA extension list (same checks)."""
    root = fsbrowser.resolve_root(get_state().fs_root)
    resolved = fsbrowser.resolve_in_root(raw, root)
    fsbrowser.require_extension(resolved, fmea_import.SUPPORTED_EXTENSIONS, "imported")
    try:
        stat = resolved.stat()
    except FileNotFoundError as exc:
        raise fsbrowser.PathRejected(
            "'%s' does not exist." % resolved.name, reason="not_found", status=404
        ) from exc
    except PermissionError as exc:
        raise fsbrowser.PathRejected(
            "'%s' cannot be read: permission denied." % resolved.name,
            reason="unreadable", status=403,
        ) from exc
    except OSError as exc:
        raise fsbrowser.PathRejected(
            "'%s' cannot be read (%s)." % (resolved.name, exc.strerror or exc),
            reason="unreadable",
        ) from exc
    if not resolved.is_file():
        raise fsbrowser.PathRejected("'%s' is not a file." % resolved.name, reason="not_a_file")
    if stat.st_size > MAX_UPLOAD_BYTES:
        raise fsbrowser.PathRejected(
            "'%s' is %.1f MB, over the %.0f MB import limit."
            % (resolved.name, stat.st_size / 1048576.0, MAX_UPLOAD_BYTES / 1048576.0),
            reason="too_large", status=413,
        )
    return resolved


def _sheet_arg(payload: Dict[str, Any]):
    sheet = payload.get("sheet")
    if sheet is None or sheet == "":
        return None
    if not isinstance(sheet, str):
        raise ApiError(INVALID_FIELD, "'sheet' must be a string.", 400, {"field": "sheet"})
    return sheet


def _read(payload: Dict[str, Any]):
    """``(path, table)`` for the request's file, with the error mapping."""
    if "path" not in payload:
        raise ApiError(INVALID_FIELD, "'path' is required.", 400, {"field": "path"})
    target = _resolve(payload["path"])
    sheet = _sheet_arg(payload)
    if target.suffix.lower() == ".xlsx" and not fmea_import.openpyxl_available():
        raise _openpyxl_missing()
    try:
        table = fmea_import.read_table(target, sheet)
    except fmea_import.FmeaImportError as exc:
        if exc.reason == "openpyxl_missing":
            raise _openpyxl_missing()
        raise _import_error(exc)
    return target, table


def _openpyxl_missing() -> ApiError:
    return ApiError(
        EXPORT_UNAVAILABLE, OPENPYXL_MISSING_MESSAGE, 503,
        {"format": "xlsx", "feature": "fmea", "package": "openpyxl",
         "install": "pip install openpyxl"},
    )


def _import_error(exc: "fmea_import.FmeaImportError") -> ApiError:
    detail = fmea_import.import_error_detail(exc)
    if exc.reason == "parent_not_found":
        return ApiError(PARENT_NOT_FOUND, str(exc), 404, detail)
    detail.setdefault("field", {
        "unknown_sheet": "sheet",
        "unknown_column": "mapping",
        "no_key_column": "mapping",
        "lambda_unit": "lambdaUnit",
        "parent_transfer": "parentId",
    }.get(exc.reason, "path"))
    return ApiError(INVALID_FIELD, str(exc), 400, detail)


def _mutation_payload(state) -> Dict[str, Any]:
    """Mirrors routes/tree.py's payload of the same name."""
    core = state.core
    return {
        "tree": copy.deepcopy(core.get_data()),
        "zeroNodes": core.get_zero_probability_nodes(),
        "dirty": state.dirty,
        "canUndo": state.can_undo,
        "canRedo": state.can_redo,
        "analysis": copy.deepcopy(getattr(core, "analysis", None)),
        "sessionWarnings": copy.deepcopy(state.session_warnings),
    }


def _mapping_arg(payload: Dict[str, Any]) -> Dict[str, str]:
    mapping = payload.get("mapping")
    if not isinstance(mapping, dict):
        raise ApiError(INVALID_FIELD, "'mapping' must be an object {field: column}.", 400,
                       {"field": "mapping"})
    out: Dict[str, str] = {}
    for field, column in mapping.items():
        if field not in fmea_import.FIELDS:
            raise ApiError(INVALID_FIELD, "Unknown mapping field '%s'." % field, 400,
                           {"field": "mapping", "value": field})
        if column in (None, ""):
            continue
        if not isinstance(column, str):
            raise ApiError(INVALID_FIELD, "Mapped columns must be header names.", 400,
                           {"field": "mapping." + field})
        out[field] = column
    return out


# ---- endpoints ---------------------------------------------------------------------


@fmea_bp.post("/preview")
def post_preview():
    payload = _body()
    state = get_state()
    with state.lock:
        _require_fta(state)
        table_setting = copy.deepcopy(state.core.analysis.get("fmeaOccurrenceTable"))
    target, table = _read(payload)
    columns = table["columns"]
    suggested = fmea_import.suggest_mapping(columns)
    unit = fmea_import.suggest_lambda_unit(suggested["lambda"]) if "lambda" in suggested else "h"
    return ok_response(
        path=str(target),
        name=target.name,
        sheets=table["sheets"],
        sheet=table["sheet"],
        columns=columns,
        rows=table["rows"][:PREVIEW_ROWS],
        rowNumbers=table["rowNumbers"][:PREVIEW_ROWS],
        rowCount=len(table["rows"]),
        fields=list(fmea_import.FIELDS),
        suggestedMapping=suggested,
        suggestedLambdaUnit=unit,
        occurrenceTable=table_setting or copy.deepcopy(engine.AIAG_OCCURRENCE_TABLE),
        defaultOccurrenceTable=copy.deepcopy(engine.AIAG_OCCURRENCE_TABLE),
    )


@fmea_bp.post("/import")
def post_import():
    payload = _body()
    state = get_state()
    with state.lock:
        _require_fta(state)

    mapping = _mapping_arg(payload)
    lambda_unit = payload.get("lambdaUnit", "h") or "h"
    # isinstance first: LAMBDA_UNITS is a dict, and a list/object value is
    # unhashable (TypeError -> 500) in the membership test.
    if not isinstance(lambda_unit, str) or lambda_unit not in fmea_import.LAMBDA_UNITS:
        raise ApiError(INVALID_FIELD, "'lambdaUnit' must be one of h, y, FIT.", 400,
                       {"field": "lambdaUnit", "value": lambda_unit})
    update = payload.get("update", True)
    if not isinstance(update, bool):
        raise ApiError(INVALID_FIELD, "'update' must be true or false.", 400, {"field": "update"})
    parent_id = payload.get("parentId")
    if parent_id is None or not str(parent_id).strip():
        raise ApiError(INVALID_FIELD, "'parentId' is required.", 400, {"field": "parentId"})
    table_patch = payload.get("occurrenceTable")
    if table_patch is not None and not isinstance(table_patch, dict):
        raise ApiError(INVALID_FIELD, "'occurrenceTable' must be an object.", 400,
                       {"field": "occurrenceTable"})

    # The file is read outside the lock: parsing is the slow part.
    target, table = _read(payload)
    label = target.name + (" [%s]" % table["sheet"] if table.get("sheet") else "")

    with state.lock:
        core = state.core
        _require_fta(state)  # the mode may have changed while reading
        analysis = core.analysis
        if table_patch is not None:
            try:
                analysis = engine.merge_analysis(
                    core.analysis, {"fmeaOccurrenceTable": table_patch}
                )
            except engine.AnalysisError as exc:
                detail: Dict[str, Any] = {"field": "analysis." + exc.field}
                if exc.value is not None:
                    detail["value"] = exc.value
                raise ApiError(INVALID_FIELD, str(exc), 400, detail)
        analysis_changed = analysis != core.analysis

        tree = copy.deepcopy(core.get_data())
        try:
            result = fmea_import.apply_import(
                tree,
                table["rows"],
                mapping,
                str(parent_id),
                analysis.get("fmeaOccurrenceTable"),
                source_label=label,
                update=update,
                lambda_unit=lambda_unit,
                columns=table["columns"],
                row_numbers=table["rowNumbers"],
            )
        except fmea_import.FmeaImportError as exc:
            raise _import_error(exc)

        changed = analysis_changed or tree != core.get_data()
        if changed:
            state.push_undo()
            core.set_data(tree)
            core.analysis = analysis
            core.recalculate_probabilities()
            state.mark_dirty()
        return ok_response(
            created=result["created"],
            updated=result["updated"],
            unchanged=result["unchanged"],
            skipped=result["skipped"],
            changed=changed,
            source=label,
            **_mutation_payload(state),
        )
