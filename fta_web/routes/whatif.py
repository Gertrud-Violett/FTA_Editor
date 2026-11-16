"""
``POST /api/whatif``: the what-if top event for factors on basic events (F4, SPEC 7.5).

The factors live in the browser only; every request carries
``{revision, documentSerial, factors}`` and the server keeps nothing of them. The
endpoint never changes the document: no undo step, no revision, no flag, no file.

Order of the checks, all before any computation (DESIGN 3.1):

1. the body is read by ``strict_input.read_strict_json`` and every field is
   validated, each factor by ``whatif_schema.validate_whatif_factor``
   (400 ``INVALID_JSON`` / ``INVALID_FIELD``);
2. ETA mode: 409 ``MODE_UNSUPPORTED``;
3. ``revision`` or ``documentSerial`` differ from the document's: 409
   ``STALE_REVISION`` (the browser then starts again from factor 1);
4. every id must be a basic event of the document (400 ``INVALID_FIELD``).

Then the baseline (cut sets, per-event q) comes from the one-entry cache of
:mod:`whatif`, or is built once for this document version; two members of one
applied CCF group with different factors are 400 ``group_conflict``, and an
event with a factor whose model cannot be evaluated is 422
``WHATIF_NOT_EVALUABLE``.
"""
from __future__ import annotations

import copy

from flask import Blueprint, request

try:  # normal package import: ``import fta_web.routes.whatif``
    from .. import whatif, whatif_schema
    from ..errors import (
        MODE_UNSUPPORTED,
        STALE_REVISION,
        ApiError,
        api_error_response,
        ok_response,
    )
    from ..state import get_state
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import whatif  # type: ignore[no-redef]
    import whatif_schema  # type: ignore[no-redef]
    from errors import (  # type: ignore[no-redef]
        MODE_UNSUPPORTED,
        STALE_REVISION,
        ApiError,
        api_error_response,
        ok_response,
    )
    from state import get_state  # type: ignore[no-redef]

whatif_bp = Blueprint("whatif", __name__, url_prefix="/api")

STALE_MESSAGE = "The document changed; start again from factor 1"


@whatif_bp.errorhandler(ApiError)
def _handle_api_error(exc: ApiError):
    return api_error_response(exc)


@whatif_bp.post("/whatif")
def post_whatif():
    """The what-if answer for ``{revision, documentSerial, factors}`` (SPEC 7.5)."""
    revision, serial, factors = whatif_schema.read_request(request)
    state = get_state()

    with state.lock:
        if str(state.core.mode).upper() == "ETA":
            raise ApiError(
                MODE_UNSUPPORTED,
                "The what-if is only available for fault trees (FTA mode); "
                "the document is an event tree (ETA mode).",
                409,
                {"mode": "ETA"},
            )
        now = state.revision_fields()
        if revision != now["revision"] or (
            serial is not None and serial != now["documentSerial"]
        ):
            raise ApiError(STALE_REVISION, STALE_MESSAGE, 409, dict(now))

        tree = state.core.get_data()
        analysis = state.core.analysis
        whatif.check_ids(tree, [node_id for node_id, _factor in factors])
        key = (id(state), now["documentSerial"], now["revision"])
        entry = whatif.lookup(key, tree, analysis)
        hit = entry is not None
        if entry is None:   # private copies; the baseline is built outside the lock
            tree_copy = copy.deepcopy(tree)
            analysis_copy = copy.deepcopy(analysis)

    if entry is None:
        entry, hit = whatif.obtain(key, tree_copy, analysis_copy)
    result = whatif.evaluate(entry, factors, hit)
    return ok_response(revision=now["revision"], documentSerial=now["documentSerial"], **result)
