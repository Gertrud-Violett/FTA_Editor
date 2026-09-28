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

Error codes beyond the shared ones: 409 ``BUSY`` (a Monte Carlo run is
already in progress) and 422 ``ANALYSIS_TOO_LARGE`` (a voting gate expands to
too many combinations, or the cut-set time budget ran out; ``detail.reason``
is ``kofn`` or ``time``).
"""
from __future__ import annotations

import copy
import threading
from typing import Any, Dict, Tuple

from flask import Blueprint, request

try:  # normal package import: ``import fta_web.routes.analysis``
    from .. import cutsets, engine, importance, uncertainty
    from ..errors import (
        INVALID_FIELD,
        INVALID_JSON,
        MODE_UNSUPPORTED,
        ApiError,
        api_error_response,
        ok_response,
    )
    from ..state import get_state
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import cutsets  # type: ignore[no-redef]
    import engine  # type: ignore[no-redef]
    import importance  # type: ignore[no-redef]
    import uncertainty  # type: ignore[no-redef]
    from errors import (  # type: ignore[no-redef]
        INVALID_FIELD,
        INVALID_JSON,
        MODE_UNSUPPORTED,
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

#: Default and maximum number of cut sets a /cutsets response carries.
DEFAULT_CUTSET_LIMIT = 500
MAX_CUTSET_LIMIT = 100000
#: Cut-set time budget for the interactive endpoints (seconds).
CUTSET_TIME_BUDGET = 30.0
#: Monte Carlo bounds for the endpoint (the settings block allows more for the CLI).
MAX_MC_N = 100000
MAX_MC_TIME_LIMIT = 60.0
DEFAULT_MC_TIME_LIMIT = 30.0

#: One Monte Carlo run at a time: runs are CPU-bound, and a second click while
#: one is running is almost always a mistake.
_mc_lock = threading.Lock()

BUSY = "BUSY"
ANALYSIS_TOO_LARGE = "ANALYSIS_TOO_LARGE"


def _int_field(payload: Dict[str, Any], key: str, lo: int, hi: int) -> Any:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise ApiError(INVALID_FIELD,
                       "'%s' must be an integer between %d and %d." % (key, lo, hi),
                       400, {"field": key, "value": value})
    return value


def _cutset_limits(payload: Dict[str, Any]) -> Dict[str, Any]:
    """``{maxOrder?, maxCount?, cutoff?}`` from the body, validated like the
    ``analysis.cutsets`` settings (same bounds)."""
    partial = {k: payload[k] for k in ("maxOrder", "maxCount", "cutoff")
               if payload.get(k) is not None}
    if partial:
        try:
            engine.merge_analysis(engine.default_analysis(), {"cutsets": partial})
        except engine.AnalysisError as exc:
            field = exc.field.split(".")[-1]
            raise ApiError(INVALID_FIELD, str(exc), 400, {"field": field, "value": exc.value})
    partial["timeBudgetS"] = CUTSET_TIME_BUDGET
    return partial


def _too_large(exc: Exception) -> ApiError:
    detail: Dict[str, Any] = {"reason": getattr(exc, "reason", "")}
    if getattr(exc, "node_id", None):
        detail["nodeId"] = exc.node_id
    detail.update(getattr(exc, "params", {}) or {})
    return ApiError(ANALYSIS_TOO_LARGE, str(exc), 422, detail)


@analysis_bp.get("/summary")
def get_summary():
    """``{treeWalk, mcub, rareEvent, headline, headlineMethod, repeatedEvents,
    nonCoherent, approximations, truncated, elapsedMs}`` for the current
    document (``engine.summary``: cheaper cut-set caps, tree-walk fallback)."""
    tree, analysis = document_copy()
    return ok_response(**engine.summary(tree, analysis))


@analysis_bp.post("/cutsets")
def post_cutsets():
    """Body ``{maxOrder?, maxCount?, cutoff?, limit?}`` (limits default to
    ``analysis.cutsets``; ``limit`` -- how many cut sets to return -- to 500).

    Returns ``cutsets.compute``'s result: ``{cutSets: [{rank, events: [{id,
    name, q}], order, probability, share}], total, returned, truncated,
    truncatedBy, mcub, rareEvent, treeWalk, repeatedEvents, nonCoherent,
    approximations, warnings, limits, elapsedMs}``. ``total``, ``mcub`` and
    ``rareEvent`` cover every cut set, not just the returned ones.
    422 ``ANALYSIS_TOO_LARGE`` when a voting gate is too large or the time
    budget runs out.
    """
    payload = _body()
    limits = _cutset_limits(payload)
    limit = _int_field(payload, "limit", 0, MAX_CUTSET_LIMIT)
    limit = DEFAULT_CUTSET_LIMIT if limit is None else limit
    tree, analysis = document_copy()
    try:
        result = cutsets.compute(tree, analysis, limits)
    except cutsets.CutsetError as exc:
        raise _too_large(exc)
    result["cutSets"] = result["cutSets"][:limit]
    result["returned"] = len(result["cutSets"])
    return ok_response(**result)


@analysis_bp.post("/importance")
def post_importance():
    """Body as ``/cutsets`` (``limit`` ignored). Returns ``{events: [{id, name,
    q, fv, birnbaum, raw, rrw, rrwInfinite, cutSetCount}], basis: "mcub",
    topValue, cutSetTotal, truncated, truncatedBy, warnings}``; events sorted
    by FV, largest first."""
    payload = _body()
    limits = _cutset_limits(payload)
    tree, analysis = document_copy()
    try:
        result = cutsets.compute(tree, analysis, limits)
    except cutsets.CutsetError as exc:
        raise _too_large(exc)
    return ok_response(
        events=importance.compute(result),
        basis="mcub",
        topValue=result["mcub"],
        cutSetTotal=result["total"],
        truncated=result["truncated"],
        truncatedBy=result["truncatedBy"],
        warnings=result["warnings"],
    )


@analysis_bp.post("/uncertainty")
def post_uncertainty():
    """Body ``{n?, seed?, timeLimit?, bins?}`` (``n``/``seed`` default to
    ``analysis.mc``; n <= 100000; timeLimit in (0, 60] s, default 30).

    Returns ``uncertainty.run``'s result: ``{requested, completed, seed,
    method, mean, median, p05, p95, std, pointEstimate, histogram: {edges,
    counts, logBins}, truncatedByTime, cutsetsTruncated, uncertainEvents,
    certainEvents, repeatedEvents, nonCoherent, warnings, elapsedMs}``.
    One run at a time: 409 ``BUSY`` while another is in progress.
    """
    payload = _body()
    n = _int_field(payload, "n", 1, MAX_MC_N)
    seed = _int_field(payload, "seed", 0, 2 ** 63 - 1)
    bins = _int_field(payload, "bins", 1, 200)
    time_limit = payload.get("timeLimit")
    if time_limit is None:
        time_limit = DEFAULT_MC_TIME_LIMIT
    elif (isinstance(time_limit, bool) or not isinstance(time_limit, (int, float))
          or not 0 < time_limit <= MAX_MC_TIME_LIMIT):
        raise ApiError(INVALID_FIELD,
                       "'timeLimit' must be a number of seconds in (0, %g]." % MAX_MC_TIME_LIMIT,
                       400, {"field": "timeLimit", "value": time_limit})
    tree, analysis = document_copy()
    if n is None:
        mc = analysis.get("mc") if isinstance(analysis.get("mc"), dict) else {}
        n = min(MAX_MC_N, int(mc.get("n") or 10000))
    if not _mc_lock.acquire(blocking=False):
        raise ApiError(BUSY, "An uncertainty analysis is already running; "
                             "wait for it to finish.", 409, {})
    try:
        result = uncertainty.run(tree, analysis, n=n, seed=seed,
                                 time_limit=float(time_limit), bins=bins or 40)
    except cutsets.CutsetError as exc:
        raise _too_large(exc)
    finally:
        _mc_lock.release()
    return ok_response(**result)


