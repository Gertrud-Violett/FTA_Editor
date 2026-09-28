"""
``POST /api/report/docx`` -- the analysis report as a Word document.

Body (every key optional)::

    {sections?: ["metadata","headline","assumptions","diagram","events",
                 "cutsets","importance","uncertainty","validation",
                 "traceability"],
     sigFigs?: 1..6, lang?: "en"|"ja",
     diagramPng?: base64 PNG (<= 8 MB decoded, PNG signature required),
     topN?: {cutsets?: int, importance?: int},
     runUncertainty?: bool,
     limits?: {maxOrder?, maxCount?, cutoff?},   # as analysis.cutsets
     uncertaintyN?: 1..MAX_REPORT_MC_N, uncertaintyTimeLimit?: (0, 60] s}

Any other key is ignored (never passed to the report builder); a bad value
of a listed key is 400 ``INVALID_FIELD``.

The response is the ``.docx`` bytes as an attachment named
``<document>_report.docx``. 503 ``EXPORT_UNAVAILABLE`` (``detail.format:
"docx"``) when python-docx is not installed -- probed per request, like the
xlsx export.

The document is deep-copied under ``state.lock`` and everything slow (cut
sets, Monte Carlo, Graphviz, python-docx) runs outside it. ETA documents are
accepted; the fault-tree-only sections carry a note instead of content.
When the browser sent no diagram and a native ``dot`` exists, the diagram is
rendered server-side in the compact style; otherwise the report says it is
not available.
"""
from __future__ import annotations

import base64
import binascii
import importlib.util
import io
from pathlib import Path
from typing import Any, Dict

from flask import Blueprint, request, send_file

try:  # normal package import: ``import fta_web.routes.report``
    from .. import engine, fsbrowser
    from .. import report_docx
    from ..errors import (
        EXPORT_UNAVAILABLE,
        INVALID_FIELD,
        INVALID_JSON,
        ApiError,
        api_error_response,
    )
    from ..i18n import request_language
    from ..state import get_state
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import engine  # type: ignore[no-redef]
    import fsbrowser  # type: ignore[no-redef]
    import report_docx  # type: ignore[no-redef]
    from errors import (  # type: ignore[no-redef]
        EXPORT_UNAVAILABLE,
        INVALID_FIELD,
        INVALID_JSON,
        ApiError,
        api_error_response,
    )
    from i18n import request_language  # type: ignore[no-redef]
    from state import get_state  # type: ignore[no-redef]

report_bp = Blueprint("report", __name__, url_prefix="/api/report")

DOCX_MISSING_MESSAGE = (
    "The DOCX report needs the 'python-docx' package, which is not installed "
    "on this machine. Install it with:\n"
    "\n"
    "    uv sync --extra report\n"
    "\n"
    "(or 'pip install python-docx'), then restart the editor."
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
        {"format": "docx", "package": "python-docx", "install": "uv sync --extra report"},
    )


def _body() -> Dict[str, Any]:
    data = request.get_json(silent=True)
    if data is None:
        if not request.get_data():
            return {}
        raise ApiError(INVALID_JSON, "Request body must be a JSON object.", 400)
    if not isinstance(data, dict):
        raise ApiError(INVALID_JSON, "Request body must be a JSON object.", 400)
    return data


def _bad(field: str, message: str, value: Any = None) -> ApiError:
    detail = {"field": field}
    if value is not None and not isinstance(value, str):
        detail["value"] = value
    return ApiError(INVALID_FIELD, message, 400, detail)


def decode_png(value: Any) -> bytes:
    """A base64 PNG (a ``data:image/png;base64,`` prefix is tolerated)."""
    if not isinstance(value, str):
        raise _bad("diagramPng", "'diagramPng' must be a base64 string.")
    text = value.strip()
    if text.startswith("data:"):
        text = text.split(",", 1)[-1]
    if len(text) > (report_docx.MAX_DIAGRAM_BYTES * 4) // 3 + 8:
        raise _bad("diagramPng", "'diagramPng' is larger than 8 MB.")
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise _bad("diagramPng", "'diagramPng' is not valid base64.")
    if len(raw) > report_docx.MAX_DIAGRAM_BYTES:
        raise _bad("diagramPng", "'diagramPng' is larger than 8 MB.")
    if not raw.startswith(report_docx.PNG_SIGNATURE):
        raise _bad("diagramPng", "'diagramPng' is not a PNG image.")
    return raw


def _options(payload: Dict[str, Any]) -> Dict[str, Any]:
    sections = payload.get("sections")
    if sections is not None:
        if not isinstance(sections, list) or not all(isinstance(s, str) for s in sections):
            raise _bad("sections", "'sections' must be a list of section names.")
        unknown = [s for s in sections if s not in report_docx.SECTIONS]
        if unknown:
            raise ApiError(
                INVALID_FIELD,
                "Unknown report section(s): %s. Known: %s."
                % (", ".join(unknown), ", ".join(report_docx.SECTIONS)),
                400, {"field": "sections", "value": unknown},
            )
    top = payload.get("topN")
    if top is not None and not isinstance(top, dict):
        raise _bad("topN", "'topN' must be an object {cutsets, importance}.")
    lang = payload.get("lang")
    if lang is not None and lang not in ("en", "ja"):
        raise _bad("lang", "'lang' must be 'en' or 'ja'.")
    # Only the documented keys reach normalize_options: nothing else in the
    # body (a forged 'generated' stamp, precomputed 'uncertainty' results)
    # is trusted, and the numeric ones are validated here, not just clamped.
    raw: Dict[str, Any] = {k: payload[k] for k in _PASSTHROUGH if k in payload}
    raw["lang"] = lang or request_language()
    raw["diagramPng"] = decode_png(payload["diagramPng"]) if payload.get("diagramPng") else None
    raw["runUncertainty"] = payload.get("runUncertainty") is True
    if payload.get("limits") is not None:
        raw["limits"] = _limits(payload["limits"])
    if payload.get("uncertaintyN") is not None:
        raw["uncertaintyN"] = _report_int(payload["uncertaintyN"], "uncertaintyN", 1,
                                          report_docx.MAX_REPORT_MC_N)
    if payload.get("uncertaintyTimeLimit") is not None:
        raw["uncertaintyTimeLimit"] = _time_limit(payload["uncertaintyTimeLimit"])
    return report_docx.normalize_options(raw)


#: Body keys handed to normalize_options as given (it clamps/filters them).
_PASSTHROUGH = ("sections", "sigFigs", "topN", "topCutsets", "topImportance")
#: The report's own Monte Carlo cap, as for POST /api/analysis/uncertainty.
MAX_REPORT_MC_SECONDS = 60.0


def _report_int(value: Any, field: str, lo: int, hi: int) -> int:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise _bad(field, "'%s' must be an integer between %d and %d." % (field, lo, hi), value)
    return value


def _time_limit(value: Any) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not 0 < value <= MAX_REPORT_MC_SECONDS):
        raise _bad("uncertaintyTimeLimit",
                   "'uncertaintyTimeLimit' must be a number of seconds in (0, %g]."
                   % MAX_REPORT_MC_SECONDS, value)
    return float(value)


def _limits(value: Any) -> Dict[str, Any]:
    """``{maxOrder?, maxCount?, cutoff?}`` validated exactly like the
    ``analysis.cutsets`` settings (and /api/analysis/cutsets). No time budget:
    the report keeps cutsets.compute's own."""
    if not isinstance(value, dict):
        raise _bad("limits", "'limits' must be an object {maxOrder, maxCount, cutoff}.")
    unknown = sorted(str(k) for k in value if k not in ("maxOrder", "maxCount", "cutoff"))
    if unknown:
        raise _bad("limits", "Unsupported key(s) in 'limits': %s." % ", ".join(unknown))
    partial = {k: v for k, v in value.items() if v is not None}
    try:
        merged = engine.merge_analysis(engine.default_analysis(), {"cutsets": partial})
    except engine.AnalysisError as exc:
        raise _bad("limits." + exc.field.split(".")[-1], str(exc), exc.value)
    return {k: merged["cutsets"][k] for k in partial}


def _stem(state) -> str:
    if state.current_path is not None:
        return Path(state.current_path).stem
    return state.core.title or "fta"


@report_bp.post("/docx")
def post_docx():
    if not docx_available():
        raise docx_unavailable()
    options = _options(_body())
    state = get_state()
    want_diagram = "diagram" in options["sections"] and options["diagramPng"] is None
    with state.lock:
        snapshot = report_docx.DocSnapshot.of(state.core)
        warnings = list(state.session_warnings)
        dot_text = (report_docx.diagram_dot_text(state.core, options["sigFigs"])
                    if want_diagram else None)
        download_name = fsbrowser.safe_download_name(_stem(state) + "_report", ".docx")
    if want_diagram:
        options["diagramPng"] = report_docx.render_png(dot_text)

    data = report_docx.collect_report_data(snapshot, warnings, options)
    try:
        blob = report_docx.build_report(data, options)
    except ImportError:
        raise docx_unavailable()
    return send_file(
        io.BytesIO(blob),
        mimetype=report_docx.DOCX_MIME,
        as_attachment=True,
        download_name=download_name,
        max_age=0,
    )
