"""
``POST /api/grid/paste``: a block pasted into the Grid tab (F3, SPEC 7.5).

The browser reads the clipboard text with each field's own parser and sends
numbers; this route never reads text a second way. Each row names a basic
event by node id (not by position), so a sort or a filter in the browser cannot
send a value to the wrong event.

Request: ``{revision, documentSerial, rows: [{clipRow, nodeId, cells}]}``.
Order of the checks, all before anything changes:

1. the body is read by ``strict_input.read_strict_json`` and every field is
   validated (400 ``INVALID_JSON`` / ``INVALID_FIELD``);
2. ETA mode: 409 ``MODE_UNSUPPORTED``;
3. ``revision`` or ``documentSerial`` differ from the document's: 409
   ``STALE_REVISION``, nothing applied.

Then per row (a refused row changes nothing, the other rows apply): the node
must be a basic event, ``id`` must match, ``q`` is written on a ``fixed`` model
and must equal the computed value on any other, a number the row's model does
not use is refused, and text must be savable. The whole paste is one undo
step; a paste that writes nothing new pushes none.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, request

try:  # normal package import: ``import fta_web.routes.grid``
    from .. import grid_schema, node_schema
    from ..errors import (
        INVALID_FIELD,
        INVALID_JSON,
        MODE_UNSUPPORTED,
        STALE_REVISION,
        ApiError,
        api_error_response,
        ok_response,
    )
    from ..state import get_state
    from ..strict_input import read_strict_json, validate_revision
    from .tree import _mutation_payload, _validate_name
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import grid_schema  # type: ignore[no-redef]
    import node_schema  # type: ignore[no-redef]
    from errors import (  # type: ignore[no-redef]
        INVALID_FIELD,
        INVALID_JSON,
        MODE_UNSUPPORTED,
        STALE_REVISION,
        ApiError,
        api_error_response,
        ok_response,
    )
    from routes.tree import _mutation_payload, _validate_name  # type: ignore[no-redef]
    from state import get_state  # type: ignore[no-redef]
    from strict_input import read_strict_json, validate_revision  # type: ignore[no-redef]

grid_bp = Blueprint("grid", __name__, url_prefix="/api/grid")

STALE_MESSAGE = "The analysis changed; paste again"

#: Refusal codes and their English texts (the browser shows its own wording).
NOT_BASIC_EVENT = "NOT_BASIC_EVENT"
ID_MISMATCH = "ID_MISMATCH"
Q_COMPUTED = "Q_COMPUTED"
NOT_USED = "NOT_USED"
INVALID_TEXT = "INVALID_TEXT"

_SYMBOLS = {"lambda": "λ", "T": "T", "tau": "τ", "mu": "μ"}
_ORDER = {key: index for index, key in enumerate(grid_schema.GRID_COLUMNS)}
_ABSENT = object()


@grid_bp.errorhandler(ApiError)
def _handle_api_error(exc: ApiError):
    return api_error_response(exc)


# ---- reading the request -------------------------------------------------------


def _bad(field: str, message: str, clip_row: Optional[int] = None) -> ApiError:
    detail: Dict[str, Any] = {"field": field}
    if clip_row is not None:
        detail["clipRow"] = clip_row
    return ApiError(INVALID_FIELD, message, 400, detail)


def _read_cells(clip_row: int, cells: Any) -> Dict[str, Any]:
    """The validated cells of one row: numbers as floats, text as strings."""
    if not isinstance(cells, dict):
        raise _bad("cells", "'cells' must be an object.", clip_row)
    unknown = sorted(key for key in cells if key not in grid_schema.GRID_COLUMNS)
    if unknown:
        raise ApiError(
            INVALID_FIELD,
            "Unsupported key(s) in 'cells': %s." % ", ".join(repr(key) for key in unknown),
            400,
            {"field": "cells", "fields": unknown, "clipRow": clip_row},
        )
    out: Dict[str, Any] = {}
    for key, value in cells.items():
        if key in grid_schema.NUMBER_COLUMNS:
            try:
                out[key] = float(grid_schema.validate_number_cell(key, value))
            except ApiError as exc:
                exc.detail["clipRow"] = clip_row
                raise
        elif not isinstance(value, str):
            raise _bad(key, "'%s' must be a string." % key, clip_row)
        elif key == "model" and value not in grid_schema.MODELS:
            raise _bad(
                "model",
                "'model' must be one of %s." % ", ".join(grid_schema.MODELS),
                clip_row,
            )
        else:
            out[key] = value
    return out


def _read_request() -> Tuple[int, int, List[Tuple[int, str, Dict[str, Any]]]]:
    """``(revision, documentSerial, rows)`` once every field is valid."""
    body = read_strict_json(request)
    if not isinstance(body, dict):
        raise ApiError(INVALID_JSON, "Request body must be a JSON object.", 400)
    revision = validate_revision(body.get("revision"), "revision")
    serial = validate_revision(body.get("documentSerial"), "documentSerial")
    rows = body.get("rows")
    if not isinstance(rows, list):
        raise _bad("rows", "'rows' must be a list.")
    if len(rows) > grid_schema.MAX_PASTE_ROWS:
        raise _bad(
            "rows",
            "'rows' holds %d rows; a paste can hold at most %d."
            % (len(rows), grid_schema.MAX_PASTE_ROWS),
        )
    out: List[Tuple[int, str, Dict[str, Any]]] = []
    seen_clip = set()
    seen_ids = set()
    for item in rows:
        if not isinstance(item, dict):
            raise _bad("rows", "Each row must be an object with clipRow, nodeId and cells.")
        clip_row = item.get("clipRow")
        if isinstance(clip_row, bool) or not isinstance(clip_row, int) or clip_row < 1:
            raise _bad("rows", "'clipRow' must be a positive integer.")
        if clip_row in seen_clip:
            raise _bad("rows", "'clipRow' %d appears twice." % clip_row, clip_row)
        seen_clip.add(clip_row)
        node_id = item.get("nodeId")
        if not isinstance(node_id, str):
            raise _bad("rows", "'nodeId' must be a string.", clip_row)
        if node_id in seen_ids:
            raise _bad("rows", "nodeId '%s' appears twice." % node_id, clip_row)
        seen_ids.add(node_id)
        out.append((clip_row, node_id, _read_cells(clip_row, item.get("cells"))))
    return revision, serial, out


# ---- the document --------------------------------------------------------------


def _basic_events(root: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """``{id: node}`` of the document's basic events: a leaf that is not the
    root, not a house event and not a TRANSFER (mirrors the grid's own row set).
    The first node found for an id wins, as ``find_node_by_id`` does."""
    found: Dict[str, Dict[str, Any]] = {}
    seen = set()
    stack = [root]
    while stack:
        node = stack.pop()
        key = str(node.get("id"))
        if key not in seen:
            seen.add(key)
            children = node.get("children") or []
            if (
                node is not root
                and not children
                and str(node.get("eventKind") or "").lower() != "house"
                and str(node.get("gateType") or "").upper() != "TRANSFER"
            ):
                found[key] = node
        stack.extend(reversed(node.get("children") or []))
    return found


def _same_q(shown: Any, pasted: float) -> bool:
    try:
        current = float(shown)
    except (TypeError, ValueError):
        return False
    return current == pasted or math.isclose(current, pasted, rel_tol=1e-9)


def _refusal(clip_row: int, column: str, code: str, message: str) -> Dict[str, Any]:
    return {"clipRow": clip_row, "column": column, "code": code, "message": message}


class _Plan:
    """What one accepted row will write; nothing is touched while planning."""

    def __init__(self, node: Dict[str, Any]) -> None:
        self.node = node
        self.name: Any = _ABSENT
        self.probability: Any = _ABSENT
        self.quant: Dict[str, Any] = {}
        self.trace: Dict[str, Any] = {}

    @property
    def writes(self) -> bool:
        return (self.name is not _ABSENT or self.probability is not _ABSENT
                or bool(self.quant) or bool(self.trace))

    def changes(self) -> bool:
        """True when applying this plan alters the node."""
        node = self.node
        if self.name is not _ABSENT and node.get("name") != self.name:
            return True
        if self.probability is not _ABSENT and node.get("probability") != self.probability:
            return True
        for key, patch in (("quant", self.quant), ("trace", self.trace)):
            if patch and node_schema.merge_partial(node.get(key), patch) != (node.get(key) or {}):
                return True
        return False

    def apply(self) -> None:
        node = self.node
        if self.name is not _ABSENT:
            node["name"] = self.name
        if self.probability is not _ABSENT:
            node["probability"] = self.probability
        for key, patch in (("quant", self.quant), ("trace", self.trace)):
            if not patch:
                continue
            merged = node_schema.merge_partial(node.get(key), patch)
            if merged:
                node[key] = merged
            else:
                node.pop(key, None)


def _plan_row(
    clip_row: int, node: Dict[str, Any], cells: Dict[str, Any]
) -> Tuple[Optional[_Plan], List[Dict[str, Any]]]:
    """``(plan, refusals)`` for one row. A row with any refusal has no plan."""
    refused: List[Dict[str, Any]] = []

    def refuse(column: str, code: str, message: str) -> None:
        refused.append(_refusal(clip_row, column, code, message))

    if "id" in cells and cells["id"].strip() != str(node.get("id")):
        refuse("id", ID_MISMATCH, "id does not match this row")

    quant = node.get("quant") if isinstance(node.get("quant"), dict) else {}
    model = cells.get("model") or str(quant.get("model") or "fixed").lower()
    if model not in grid_schema.MODELS:
        model = "fixed"

    plan = _Plan(node)
    if "model" in cells:
        plan.quant["model"] = cells["model"]

    for key in ("lambda", "T", "tau", "mu"):
        if key not in cells:
            continue
        if model not in grid_schema.USED_BY_MODEL[key]:
            refuse(key, NOT_USED, "%s is not used by the model of this row" % _SYMBOLS[key])
        else:
            plan.quant[key] = cells[key]

    if "q" in cells:
        if model == "fixed":
            plan.probability = cells["q"]
        elif not _same_q(node.get("probability"), cells["q"]):
            refuse("q", Q_COMPUTED, "q is computed from the model")

    try:
        if "name" in cells:
            name = _validate_name(cells["name"])
            if not name:
                raise ApiError(INVALID_FIELD, "'name' is empty.", 400, {"field": "name"})
            plan.name = name
    except ApiError:
        refuse("name", INVALID_TEXT, "The text cannot be saved")
    try:
        if "source" in cells:
            plan.quant["source"] = node_schema.validate_quant({"source": cells["source"]})["source"]
    except ApiError:
        refuse("source", INVALID_TEXT, "The text cannot be saved")
    try:
        if "tags" in cells:
            tags = node_schema.validate_trace({"tags": grid_schema.split_tags(cells["tags"])})["tags"]
            plan.trace["tags"] = tags or None
    except ApiError:
        refuse("tags", INVALID_TEXT, "The text cannot be saved")

    if refused:
        refused.sort(key=lambda item: _ORDER[item["column"]])
        return None, refused
    return plan, []


# ---- the route -----------------------------------------------------------------


@grid_bp.post("/paste")
def paste():
    """Apply a pasted block (SPEC 7.5): one undo step, per-row refusals."""
    revision, serial, rows = _read_request()
    state = get_state()

    with state.lock:
        if str(state.core.mode).upper() == "ETA":
            raise ApiError(
                MODE_UNSUPPORTED,
                "Pasting into the grid is only available for fault trees (FTA mode); "
                "the document is an event tree (ETA mode).",
                409,
                {"mode": "ETA"},
            )
        now = state.revision_fields()
        if revision != now["revision"] or serial != now["documentSerial"]:
            raise ApiError(STALE_REVISION, STALE_MESSAGE, 409, dict(now))

        events = _basic_events(state.core.get_data())
        applied = 0
        refused: List[Dict[str, Any]] = []
        plans: List[_Plan] = []
        for clip_row, node_id, cells in rows:
            node = events.get(node_id)
            if node is None:
                refused.append(_refusal(clip_row, "", NOT_BASIC_EVENT, "This row is not a basic event"))
                continue
            plan, row_refused = _plan_row(clip_row, node, cells)
            refused.extend(row_refused)
            if plan is not None and plan.writes:
                plans.append(plan)
                applied += 1

        if any(plan.changes() for plan in plans):
            state.push_undo()
            for plan in plans:
                plan.apply()
            state.core.recalculate_probabilities()
            state.mark_dirty()

        return ok_response(applied=applied, refused=refused, **_mutation_payload(state))
