"""
FMEA import -- ``/api/fmea/*`` (workstream C).

``POST /api/fmea/preview``: multipart ``file`` (.xlsx or .csv). Returns
``{sheets: [names], sheet, columns: [header], rows: [[cell]] (first rows),
rowCount, mapping: {field: column}}`` -- the suggested column mapping for
``fmea.{id,item,mode,cause,severity,occurrence,detection,rpn}``.

``POST /api/fmea/import``: the same file plus ``{sheet, mapping, parentId,
occurrenceTable?}``. One undo step; rows whose ``fmea.id`` matches an existing
node update it in place, the rest become new events. Returns ``{created,
updated, skipped}`` plus the mutation payload.

Phase 0 answers 501 ``NOT_IMPLEMENTED`` for both.
"""
from __future__ import annotations

from flask import Blueprint

try:  # normal package import: ``import fta_web.routes.fmea``
    from ..errors import NOT_IMPLEMENTED, ApiError, api_error_response
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    from errors import NOT_IMPLEMENTED, ApiError, api_error_response  # type: ignore[no-redef]

fmea_bp = Blueprint("fmea", __name__, url_prefix="/api/fmea")


@fmea_bp.errorhandler(ApiError)
def _handle_api_error(exc: ApiError):
    return api_error_response(exc)


def _not_implemented(what: str) -> ApiError:
    return ApiError(
        NOT_IMPLEMENTED, "%s is not implemented in this build yet." % what, 501,
        {"feature": "fmea"},
    )


@fmea_bp.post("/preview")
def post_preview():
    raise _not_implemented("FMEA preview")


@fmea_bp.post("/import")
def post_import():
    raise _not_implemented("FMEA import")
