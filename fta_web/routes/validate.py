"""
``GET /api/analysis/validate`` -- the Validation tab's issue list.

Response: ``{issues: [{severity, code, nodeId, message, params}], counts:
{error, warning, info}}``.

Phase 0 reports the session warnings only (``LOAD_REPAIR`` from open/import,
``LINKS_REMOVED`` from deletes -- see ``AppState.session_warnings``);
workstream E adds the tree rules through ``lint.run(tree, analysis,
session_warnings)``. Works in both modes: ETA has rules of its own.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

from flask import Blueprint

try:  # normal package import: ``import fta_web.routes.validate``
    from ..errors import ApiError, api_error_response, ok_response
    from ..state import get_state
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    from errors import ApiError, api_error_response, ok_response  # type: ignore[no-redef]
    from state import get_state  # type: ignore[no-redef]

validate_bp = Blueprint("validate", __name__, url_prefix="/api")

SEVERITIES = ("error", "warning", "info")


@validate_bp.errorhandler(ApiError)
def _handle_api_error(exc: ApiError):
    return api_error_response(exc)


def _as_issue(entry: Dict[str, Any]) -> Dict[str, Any]:
    severity = entry.get("severity")
    return {
        "severity": severity if severity in SEVERITIES else "warning",
        "code": entry.get("code") or "LOAD_REPAIR",
        "nodeId": entry.get("nodeId"),
        "message": entry.get("message", ""),
        "params": copy.deepcopy(entry.get("params") or {}),
    }


@validate_bp.get("/analysis/validate")
def get_validate():
    state = get_state()
    with state.lock:
        warnings = copy.deepcopy(state.session_warnings)
    issues: List[Dict[str, Any]] = [_as_issue(w) for w in warnings]
    counts = {severity: 0 for severity in SEVERITIES}
    for issue in issues:
        counts[issue["severity"]] += 1
    return ok_response(issues=issues, counts=counts)
