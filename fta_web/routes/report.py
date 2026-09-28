"""
``POST /api/report/docx`` -- the analysis report as a Word document.

Body (final shape, workstream D): ``{sections?: [...], diagramPng?: base64,
sigFigs?: 1..6, lang?: "en"|"ja"}``; the response is the ``.docx`` bytes as an
attachment. 503 ``EXPORT_UNAVAILABLE`` (``detail.format: "docx"``) when
python-docx is not installed -- probed per request, like the xlsx export.
Phase 0 answers 501 ``NOT_IMPLEMENTED`` when it is.
"""
from __future__ import annotations

import importlib.util

from flask import Blueprint

try:  # normal package import: ``import fta_web.routes.report``
    from ..errors import (
        EXPORT_UNAVAILABLE,
        NOT_IMPLEMENTED,
        ApiError,
        api_error_response,
    )
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    from errors import (  # type: ignore[no-redef]
        EXPORT_UNAVAILABLE,
        NOT_IMPLEMENTED,
        ApiError,
        api_error_response,
    )

report_bp = Blueprint("report", __name__, url_prefix="/api/report")

DOCX_MISSING_MESSAGE = (
    "The DOCX report needs the 'python-docx' package, which is not installed "
    "on this machine. Install it with:\n"
    "\n"
    "    pip install python-docx\n"
    "\n"
    "then restart the editor."
)


@report_bp.errorhandler(ApiError)
def _handle_api_error(exc: ApiError):
    return api_error_response(exc)


def docx_available() -> bool:
    """Whether python-docx can be imported right now (``find_spec``)."""
    try:
        return importlib.util.find_spec("docx") is not None
    except (ImportError, ValueError):
        return False


def docx_unavailable() -> ApiError:
    return ApiError(
        EXPORT_UNAVAILABLE,
        DOCX_MISSING_MESSAGE,
        503,
        {"format": "docx", "package": "python-docx", "install": "pip install python-docx"},
    )


@report_bp.post("/docx")
def post_docx():
    if not docx_available():
        raise docx_unavailable()
    raise ApiError(
        NOT_IMPLEMENTED,
        "The DOCX report is not implemented in this build yet.",
        501,
        {"feature": "report"},
    )
