"""
Analysis endpoints -- ``/api/analysis/*``.

==================================  ==============================================
``POST /api/analysis/settings``     undoable, partial edit of the ``analysis`` block
``GET  /api/analysis/summary``      headline figures (``engine.summary``)
``POST /api/analysis/cutsets``      ranked minimal cut sets        (workstream A)
``POST /api/analysis/importance``   FV, Birnbaum, RAW, RRW per event (workstream A)
``POST /api/analysis/uncertainty``  Monte Carlo on the quant models (workstream A)
==================================  ==============================================

The computing endpoints answer 409 ``MODE_UNSUPPORTED`` in ETA mode -- an event
tree has no cut sets -- and work on a deep copy of the tree taken under the
lock, so a long computation never blocks editing. ``settings`` works in both
modes: it only edits document settings.

Phase 0 ships ``settings`` and ``summary`` for real; the other three answer
501 ``NOT_IMPLEMENTED`` with their final request shapes documented below.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Tuple

from flask import Blueprint, request

try:  # normal package import: ``import fta_web.routes.analysis``
    from .. import engine
    from ..errors import (
        INVALID_FIELD,
        INVALID_JSON,
        MODE_UNSUPPORTED,
        NOT_IMPLEMENTED,
        ApiError,
        api_error_response,
        ok_response,
    )
    from ..state import get_state
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import engine  # type: ignore[no-redef]
    from errors import (  # type: ignore[no-redef]
        INVALID_FIELD,
        INVALID_JSON,
        MODE_UNSUPPORTED,
        NOT_IMPLEMENTED,
        ApiError,
        api_error_response,
        ok_response,
    )
    from state import get_state  # type: ignore[no-redef]

analysis_bp = Blueprint("analysis", __name__, url_prefix="/api/analysis")


@analysis_bp.errorhandler(ApiError)
def _handle_api_error(exc: ApiError):
    return api_error_response(exc)


# ---- helpers -------------------------------------------------------------------


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


def _mutation_payload(state) -> Dict[str, Any]:
    """Mirrors routes/tree.py's payload of the same name (kept separate so
    neither blueprint needs the other mounted)."""
    core = state.core
    return {
        "tree": copy.deepcopy(core.get_data()),
        "zeroNodes": core.get_zero_probability_nodes(),
        "dirty": state.dirty,
        "canUndo": state.can_undo,
        "canRedo": state.can_redo,
        "analysis": copy.deepcopy(core.analysis),
        "sessionWarnings": copy.deepcopy(state.session_warnings),
    }


def require_fta(state) -> None:
    """409 ``MODE_UNSUPPORTED`` unless the document is a fault tree."""
    if str(state.core.mode).upper() == "ETA":
        raise ApiError(
            MODE_UNSUPPORTED,
            "This analysis is only available for fault trees (FTA mode); "
            "the document is an event tree (ETA mode).",
            409,
            {"mode": "ETA"},
        )


def document_copy() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """``(tree, analysis)`` deep-copied under the lock, FTA mode enforced."""
    state = get_state()
    with state.lock:
        require_fta(state)
        return copy.deepcopy(state.core.get_data()), copy.deepcopy(state.core.analysis)


def _not_implemented(what: str) -> ApiError:
    return ApiError(
        NOT_IMPLEMENTED,
        "%s is not implemented in this build yet." % what,
        501,
        {"feature": what},
    )


# ---- settings --------------------------------------------------------------------


@analysis_bp.post("/settings")
def post_settings():
    """Partial, validated, undoable edit of ``analysis``.

    Body: a partial ``analysis`` object -- ``{"missionTime": 100}``,
    ``{"cutsets": {"maxOrder": 4}}`` -- or the same wrapped as
    ``{"analysis": {...}}``. ``null`` resets a setting to its default.
    Returns ``analysis`` plus the usual mutation payload (the tree is
    recalculated: a rate model's T defaults to the mission time).
    """
    payload = _body()
    if set(payload) == {"analysis"} and isinstance(payload["analysis"], dict):
        payload = payload["analysis"]
    if not payload:
        raise ApiError(INVALID_FIELD, "No analysis settings to update.", 400)

    state = get_state()
    with state.lock:
        try:
            merged = engine.merge_analysis(state.core.analysis, payload)
        except engine.AnalysisError as exc:
            detail: Dict[str, Any] = {"field": "analysis." + exc.field}
            if exc.value is not None:
                detail["value"] = exc.value
            raise ApiError(INVALID_FIELD, str(exc), 400, detail)
        state.push_undo()
        state.core.analysis = merged
        state.core.recalculate_probabilities()
        state.mark_dirty()
        return ok_response(**_mutation_payload(state))


# ---- computations -----------------------------------------------------------------


@analysis_bp.get("/summary")
def get_summary():
    """``{treeWalk, mcub, rareEvent, headline, headlineMethod, repeatedEvents,
    nonCoherent, approximations, truncated}`` for the current document."""
    tree, analysis = document_copy()
    return ok_response(**engine.summary(tree, analysis))


@analysis_bp.post("/cutsets")
def post_cutsets():
    """Body ``{maxOrder?, maxCount?, cutoff?}`` (defaults from
    ``analysis.cutsets``). Returns ``{cutsets: [{events: [ids], names,
    order, probability, share}], count, truncated: {order, count, cutoff},
    mcub, rareEvent, treeWalk}``. Workstream A."""
    _body()
    document_copy()
    raise _not_implemented("Cut set analysis")


@analysis_bp.post("/importance")
def post_importance():
    """Body as ``/cutsets``. Returns ``{events: [{id, name, q, fv, birnbaum,
    raw, rrw}], basis: "mcub"}``. Workstream A."""
    _body()
    document_copy()
    raise _not_implemented("Importance analysis")


@analysis_bp.post("/uncertainty")
def post_uncertainty():
    """Body ``{n?, seed?, timeLimit?}`` (defaults from ``analysis.mc``).
    Returns ``{mean, median, p05, p95, std, histogram: {edges, counts}, n,
    seed, partial, method}``. One run at a time. Workstream A."""
    _body()
    document_copy()
    raise _not_implemented("Uncertainty analysis")
