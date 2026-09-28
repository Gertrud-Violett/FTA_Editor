"""
``GET /api/analysis/validate`` -- the Validation tab's issue list.

Response: ``{issues: [{severity, code, nodeId, message, params}], counts:
{error, warning, info}, mode}``.

The tree, ``analysis`` block, mode and ``AppState.session_warnings``
(``LOAD_REPAIR`` from open/import, ``LINKS_REMOVED`` from deletes) are
deep-copied under ``state.lock``; ``lint.run`` then works outside the lock.
In FTA mode the cut sets are also expanded with the document's own limits
(``analysis.cutsets``, 2 s budget) so ``CUTSETS_TRUNCATED`` can be reported.
Works in both modes -- ETA has rules of its own (see ``lint``).

The issue objects keep the frozen five keys of the Phase-0 contract. The
``nodeName``/``hintKey`` that ``lint.run`` adds for Python callers (report,
CLI) are left out: the browser reads the current name from its store and
derives the hint key (``val.fix.<code>``) from the code.
"""
from __future__ import annotations

import copy
from typing import Any, Dict

from flask import Blueprint

try:  # normal package import: ``import fta_web.routes.validate``
    from .. import cutsets, lint
    from ..errors import ApiError, api_error_response, ok_response
    from ..state import get_state
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import cutsets  # type: ignore[no-redef]
    import lint  # type: ignore[no-redef]
    from errors import ApiError, api_error_response, ok_response  # type: ignore[no-redef]
    from state import get_state  # type: ignore[no-redef]

validate_bp = Blueprint("validate", __name__, url_prefix="/api")

SEVERITIES = lint.SEVERITIES
_ISSUE_KEYS = ("severity", "code", "nodeId", "message", "params")


@validate_bp.errorhandler(ApiError)
def _handle_api_error(exc: ApiError):
    return api_error_response(exc)


def _public(issue: Dict[str, Any]) -> Dict[str, Any]:
    return {key: issue.get(key) for key in _ISSUE_KEYS}


@validate_bp.get("/analysis/validate")
def get_validate():
    state = get_state()
    with state.lock:
        tree = copy.deepcopy(state.core.get_data())
        analysis = copy.deepcopy(getattr(state.core, "analysis", None))
        mode = state.core.mode
        warnings = copy.deepcopy(state.session_warnings)
    # Cut-set truncation under the document's limits (short time budget,
    # outside the lock); None -- failure or timeout -- says nothing.
    extra = None
    if mode != "ETA":
        signal = cutsets.truncation_signal(tree, analysis)
        if signal is not None:
            extra = {"cutsets": signal}
    issues = [_public(issue) for issue in lint.run(tree, analysis, warnings, mode=mode, extra=extra)]
    return ok_response(issues=issues, counts=lint.counts(issues),
                       mode="ETA" if mode == "ETA" else "FTA")
