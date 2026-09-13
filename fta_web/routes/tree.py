"""
Tree and document endpoints -- the ``/api`` blueprint the editor talks to.

Contract every mutating endpoint honours:

1. take ``state.lock`` for the whole read-modify-write,
2. ``state.push_undo()`` **before** touching the tree,
3. mutate,
4. ``core.recalculate_probabilities()``,
5. ``state.mark_dirty()``,
6. return the full post-mutation view -- ``tree``, ``zeroNodes``, ``dirty``,
   ``canUndo``, ``canRedo`` -- so the client never needs a follow-up GET.

``POST /api/new`` is the documented exception: it resets the document, so it
clears the history instead of pushing to it and lands on ``dirty: false``.

Validation rules that are not obvious:

* ``logicGate`` accepts only ``AND`` and ``OR``. ``NOT`` is **rejected**, not
  silently accepted: the engine branches on ``gate == "AND"`` and treats every
  other value as OR, so a NOT gate would produce a plausible-looking wrong
  number with no warning anywhere. See divergence D5 in
  ``fta_web/core/DIVERGENCE.md``. An empty/missing/None gate means OR, matching
  ``FTACore._normalize_node``.
* ``links`` are never checked for reachability or cycles. A link to a missing
  or self-referential target is legal -- the engine skips unresolvable targets
  and its ``visiting`` set breaks cycles -- and rejecting them here would
  refuse trees the desktop editor happily loads.
* Node ids are assigned by the server (``next_child_id``), never by the client,
  so the ids stay in the desktop editor's format.

The ``ApiError`` handler is registered on the blueprint (not the app), so the
blueprint is self-contained: it returns the documented error envelope whether
or not ``create_app`` also installs a global handler. Both render the identical
payload via ``ApiError.to_payload()``.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Optional

from flask import Blueprint, request

try:  # normal package import: ``import fta_web.routes.tree``
    from ..errors import (
        CYCLE_REJECTED,
        DUPLICATE_NODE_ID,
        INVALID_FIELD,
        INVALID_JSON,
        NODE_NOT_FOUND,
        NOTHING_TO_REDO,
        NOTHING_TO_UNDO,
        PARENT_NOT_FOUND,
        ROOT_PROTECTED,
        UNSAVED_CHANGES,
        ApiError,
        ok_response,
    )
    from ..state import get_state
    from ..tree_ops import (
        ROOT_ID,
        collect_flat,
        depth_of,
        find_parent_id,
        move_node,
        next_child_id,
        would_create_cycle,
    )
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    from errors import (  # type: ignore[no-redef]
        CYCLE_REJECTED,
        DUPLICATE_NODE_ID,
        INVALID_FIELD,
        INVALID_JSON,
        NODE_NOT_FOUND,
        NOTHING_TO_REDO,
        NOTHING_TO_UNDO,
        PARENT_NOT_FOUND,
        ROOT_PROTECTED,
        UNSAVED_CHANGES,
        ApiError,
        ok_response,
    )
    from state import get_state  # type: ignore[no-redef]
    from tree_ops import (  # type: ignore[no-redef]
        ROOT_ID,
        collect_flat,
        depth_of,
        find_parent_id,
        move_node,
        next_child_id,
        would_create_cycle,
    )

# Both import paths above have already put fta_web/core on sys.path.
from FTA_Editor_core import sanitize_name  # noqa: E402

tree_bp = Blueprint("tree", __name__, url_prefix="/api")

VALID_GATES = ("AND", "OR")
VALID_MODES = ("FTA", "ETA")
VALID_RELATIONS = ("AND", "OR")
NODE_FIELDS = ("name", "type", "probability", "logicGate", "notes", "links")


@tree_bp.errorhandler(ApiError)
def _handle_api_error(exc: ApiError):
    return exc.to_payload(), exc.status


# ---- request helpers -----------------------------------------------------


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


def _as_float(value: Any, default: float = 0.0) -> float:
    """Best-effort float, for reading values that came off disk."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _validate_name(value: Any, field: str = "name") -> str:
    """Names go through the core's sanitizer, exactly as the desktop editor does."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ApiError(
            INVALID_FIELD,
            f"'{field}' must be a string.",
            400,
            {"field": field},
        )
    return sanitize_name(value)


def _validate_probability(value: Any) -> float:
    """A real number in [0.0, 1.0]. Booleans and NaN/inf are not numbers here."""
    if isinstance(value, bool) or value is None:
        raise ApiError(
            INVALID_FIELD,
            "'probability' must be a number between 0.0 and 1.0.",
            400,
            {"field": "probability", "value": value},
        )
    try:
        prob = float(value)
    except (TypeError, ValueError):
        raise ApiError(
            INVALID_FIELD,
            "'probability' must be a number between 0.0 and 1.0.",
            400,
            {"field": "probability", "value": value},
        )
    if math.isnan(prob) or math.isinf(prob) or not (0.0 <= prob <= 1.0):
        raise ApiError(
            INVALID_FIELD,
            "'probability' must be a number between 0.0 and 1.0.",
            400,
            {"field": "probability", "value": value},
        )
    return prob


def _validate_gate(value: Any) -> str:
    """AND or OR. Empty/None means OR; NOT is refused (divergence D5)."""
    if value is None or value == "":
        return "OR"
    if not isinstance(value, str):
        raise ApiError(
            INVALID_FIELD,
            "'logicGate' must be 'AND' or 'OR'.",
            400,
            {"field": "logicGate", "value": value},
        )
    gate = value.strip().upper()
    if not gate:
        return "OR"
    if gate == "NOT":
        raise ApiError(
            INVALID_FIELD,
            "NOT gates are not supported: the probability engine has no NOT "
            "semantics and would score the node as OR. Use 'AND' or 'OR'.",
            400,
            {"field": "logicGate", "value": value},
        )
    if gate not in VALID_GATES:
        raise ApiError(
            INVALID_FIELD,
            "'logicGate' must be 'AND' or 'OR'.",
            400,
            {"field": "logicGate", "value": value},
        )
    return gate


def _validate_notes(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ApiError(
            INVALID_FIELD, "'notes' must be a string.", 400, {"field": "notes"}
        )
    return value


def _validate_links(value: Any) -> List[Dict[str, Any]]:
    """Normalize links to the on-disk shape.

    Accepts ``target_id`` or ``targetId`` on input and always stores
    ``target_id``, which is what ``FTACore`` reads and writes. Targets are
    deliberately not resolved: dangling and circular links are legal.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise ApiError(
            INVALID_FIELD, "'links' must be a list.", 400, {"field": "links"}
        )

    links: List[Dict[str, Any]] = []
    for position, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ApiError(
                INVALID_FIELD,
                "Each link must be an object with 'target_id' and 'relation'.",
                400,
                {"field": "links", "index": position},
            )
        target_id = raw.get("target_id", raw.get("targetId"))
        if target_id is None or str(target_id).strip() == "":
            raise ApiError(
                INVALID_FIELD,
                "Each link needs a non-empty 'target_id'.",
                400,
                {"field": "links", "index": position},
            )
        relation = raw.get("relation") or "OR"
        if not isinstance(relation, str):
            relation = str(relation)
        relation = relation.strip().upper()
        if relation not in VALID_RELATIONS:
            raise ApiError(
                INVALID_FIELD,
                "A link 'relation' must be 'AND' or 'OR'.",
                400,
                {"field": "links", "index": position, "value": raw.get("relation")},
            )
        links.append({"target_id": str(target_id), "relation": relation})
    return links


def _validate_index(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(
            INVALID_FIELD, "'index' must be an integer.", 400, {"field": "index"}
        )
    return value


def _require_node(
    core, node_id: str, code: str = NODE_NOT_FOUND, label: str = "Node"
) -> Dict[str, Any]:
    node = core.find_node_by_id(node_id)
    if node is None:
        key = "parentId" if code == PARENT_NOT_FOUND else "nodeId"
        raise ApiError(
            code,
            f"{label} '{node_id}' was not found.",
            404,
            {key: str(node_id)},
        )
    return node


# ---- response helpers ----------------------------------------------------


def _mutation_payload(state) -> Dict[str, Any]:
    """The post-mutation view every mutating endpoint returns."""
    core = state.core
    return {
        "tree": copy.deepcopy(core.get_data()),
        "zeroNodes": core.get_zero_probability_nodes(),
        "dirty": state.dirty,
        "canUndo": state.can_undo,
        "canRedo": state.can_redo,
    }


def _node_view(core, node: Dict[str, Any]) -> Dict[str, Any]:
    """One node as the detail pane wants it, with link targets resolved."""
    links = []
    for raw in node.get("links") or []:
        target_id = raw.get("target_id")
        target = core.find_node_by_id(target_id) if target_id else None
        links.append(
            {
                "target_id": str(target_id) if target_id is not None else None,
                "relation": (raw.get("relation") or "OR").upper(),
                # None means the link dangles; the client shows the raw id.
                "targetName": target.get("name") if target else None,
            }
        )

    base_probability = _as_float(node.get("probability"), 0.0)
    return {
        "id": str(node.get("id")),
        "name": node.get("name", ""),
        "type": node.get("type", "Event"),
        "probability": base_probability,
        "logicGate": node.get("logicGate", ""),
        "notes": node.get("notes", "") or "",
        "calculatedProbability": _as_float(
            node.get("calculatedProbability", base_probability), base_probability
        ),
        "links": links,
        "childIds": [str(c.get("id")) for c in node.get("children") or []],
    }


# ---- document ------------------------------------------------------------


@tree_bp.get("/state")
def get_full_state():
    """Everything the client needs to render from cold."""
    return ok_response(**get_state().to_dict())


@tree_bp.post("/metadata")
def update_metadata():
    """Update title/date/mode. A mode change re-runs the whole calculation."""
    payload = _body()
    state = get_state()

    title = _validate_name(payload["title"], "title") if "title" in payload else None

    date = None
    if "date" in payload:
        if payload["date"] is None or not isinstance(payload["date"], str):
            raise ApiError(
                INVALID_FIELD, "'date' must be a string.", 400, {"field": "date"}
            )
        date = payload["date"].strip()

    mode = None
    if "mode" in payload:
        mode = payload["mode"]
        if not isinstance(mode, str) or mode.strip().upper() not in VALID_MODES:
            raise ApiError(
                INVALID_FIELD,
                "'mode' must be 'FTA' or 'ETA'.",
                400,
                {"field": "mode", "value": payload["mode"]},
            )
        mode = mode.strip().upper()

    if title is None and date is None and mode is None:
        raise ApiError(
            INVALID_FIELD,
            "Provide at least one of 'title', 'date' or 'mode'.",
            400,
        )

    with state.lock:
        state.push_undo()
        # set_metadata() rewrites `date` to today when it is passed None
        # alongside another field -- desktop behaviour, kept deliberately.
        state.core.set_metadata(title=title, date=date, mode=mode)
        state.core.recalculate_probabilities()
        state.mark_dirty()
        return ok_response(metadata=state.core.get_metadata(), **_mutation_payload(state))


@tree_bp.post("/new")
def new_document():
    """Start an empty document. Refuses to discard unsaved work unless forced."""
    payload = _body()
    force = bool(payload.get("force", False))
    state = get_state()

    with state.lock:
        if state.dirty and not force:
            raise ApiError(
                UNSAVED_CHANGES,
                "The current analysis has unsaved changes. "
                "Save it, or resend with {\"force\": true} to discard them.",
                409,
            )
        # reset() clears the history, so there is nothing to push an undo onto
        # and nothing to be dirty about: this endpoint is the documented
        # exception to the push_undo/mark_dirty rule.
        state.reset()
        return ok_response(
            metadata=state.core.get_metadata(),
            currentPath=None,
            **_mutation_payload(state),
        )


# ---- nodes ---------------------------------------------------------------


@tree_bp.get("/nodes")
def list_nodes():
    """Flat pre-order listing, for pickers and link target dropdowns."""
    state = get_state()
    with state.lock:
        return ok_response(nodes=collect_flat(state.core))


@tree_bp.get("/nodes/<node_id>")
def get_node(node_id: str):
    """One node in detail, with its computed probability and link target names."""
    state = get_state()
    with state.lock:
        node = _require_node(state.core, node_id)
        view = _node_view(state.core, node)
        view["parentId"] = find_parent_id(state.core, node_id)
        view["depth"] = depth_of(state.core, node_id)
        return ok_response(node=view)


@tree_bp.post("/nodes")
def create_node():
    """Add a child under ``parentId``. The server assigns the id."""
    payload = _body()
    state = get_state()

    parent_id = payload.get("parentId")
    if parent_id is None or not str(parent_id).strip():
        raise ApiError(
            INVALID_FIELD, "'parentId' is required.", 400, {"field": "parentId"}
        )
    parent_id = str(parent_id)

    if "name" not in payload:
        raise ApiError(INVALID_FIELD, "'name' is required.", 400, {"field": "name"})

    name = _validate_name(payload["name"])
    node_type = payload.get("type", "Event")
    if not isinstance(node_type, str) or not node_type.strip():
        raise ApiError(
            INVALID_FIELD, "'type' must be a non-empty string.", 400, {"field": "type"}
        )
    # Desktop default for a new node is 1.0 (src/FTA_Editor_UI.py:1431).
    probability = _validate_probability(payload.get("probability", 1.0))
    gate = _validate_gate(payload.get("logicGate", "OR"))
    notes = _validate_notes(payload.get("notes", ""))
    links = _validate_links(payload.get("links", []))

    with state.lock:
        core = state.core
        _require_node(core, parent_id, PARENT_NOT_FOUND, "Parent node")

        new_id = next_child_id(core, parent_id)
        if core.find_node_by_id(new_id) is not None:
            # Only reachable for a hand-edited file that already uses the id
            # elsewhere in the tree; the desktop editor would crash on the
            # duplicate treeview iid, so step past it instead.
            new_id = _unused_id(core, parent_id)
            if new_id is None:
                raise ApiError(
                    DUPLICATE_NODE_ID,
                    f"Could not allocate a free child id under '{parent_id}'.",
                    409,
                    {"parentId": parent_id},
                )

        new_node = {
            "id": new_id,
            "name": name,
            "type": node_type.strip(),
            "probability": probability,
            "logicGate": gate,
            "notes": notes,
            "links": links,
            "children": [],
        }

        state.push_undo()
        core.add_node_to_data(parent_id, new_node)
        core.recalculate_probabilities()
        state.mark_dirty()

        created = core.find_node_by_id(new_id)
        return ok_response(
            nodeId=new_id,
            node=_node_view(core, created),
            **_mutation_payload(state),
        )


def _unused_id(core, parent_id: str, limit: int = 10000) -> Optional[str]:
    """First ``<parent_id>_<n>`` not already taken anywhere in the tree."""
    start = int(next_child_id(core, parent_id).rsplit("_", 1)[-1])
    for candidate_index in range(start, start + limit):
        candidate = f"{parent_id}_{candidate_index}"
        if core.find_node_by_id(candidate) is None:
            return candidate
    return None


@tree_bp.patch("/nodes/<node_id>")
def update_node(node_id: str):
    """Partial update. Only the six editable node fields are accepted."""
    payload = _body()
    state = get_state()

    unknown = [key for key in payload if key not in NODE_FIELDS]
    if unknown:
        raise ApiError(
            INVALID_FIELD,
            "Unsupported field(s): "
            + ", ".join(sorted(unknown))
            + ". Node ids are server-assigned and children are changed with "
            "the move and delete endpoints.",
            400,
            {"fields": sorted(unknown)},
        )
    if not payload:
        raise ApiError(INVALID_FIELD, "No fields to update.", 400)

    updates: Dict[str, Any] = {}
    if "name" in payload:
        updates["name"] = _validate_name(payload["name"])
    if "type" in payload:
        node_type = payload["type"]
        if not isinstance(node_type, str) or not node_type.strip():
            raise ApiError(
                INVALID_FIELD,
                "'type' must be a non-empty string.",
                400,
                {"field": "type"},
            )
        updates["type"] = node_type.strip()
    if "probability" in payload:
        updates["probability"] = _validate_probability(payload["probability"])
    if "logicGate" in payload:
        updates["logicGate"] = _validate_gate(payload["logicGate"])
    if "notes" in payload:
        updates["notes"] = _validate_notes(payload["notes"])
    if "links" in payload:
        updates["links"] = _validate_links(payload["links"])

    with state.lock:
        core = state.core
        _require_node(core, node_id)

        state.push_undo()
        core.update_node(node_id, updates)
        core.recalculate_probabilities()
        state.mark_dirty()

        return ok_response(
            node=_node_view(core, core.find_node_by_id(node_id)),
            **_mutation_payload(state),
        )


@tree_bp.delete("/nodes/<node_id>")
def delete_node(node_id: str):
    """Delete a node and its subtree. The root is not deletable.

    Links pointing at the deleted node are left alone; the engine skips
    unresolvable targets, which is what the desktop editor does too.
    """
    state = get_state()

    if str(node_id) == ROOT_ID:
        raise ApiError(
            ROOT_PROTECTED,
            "The root node cannot be deleted.",
            400,
            {"nodeId": ROOT_ID},
        )

    with state.lock:
        core = state.core
        _require_node(core, node_id)

        state.push_undo()
        core.delete_node_from_data(node_id)
        core.recalculate_probabilities()
        state.mark_dirty()

        return ok_response(deletedId=str(node_id), **_mutation_payload(state))


@tree_bp.post("/nodes/<node_id>/move")
def move_node_endpoint(node_id: str):
    """Re-parent a node, optionally at a specific position among its new siblings."""
    payload = _body()
    state = get_state()

    new_parent_id = payload.get("newParentId")
    if new_parent_id is None or not str(new_parent_id).strip():
        raise ApiError(
            INVALID_FIELD, "'newParentId' is required.", 400, {"field": "newParentId"}
        )
    new_parent_id = str(new_parent_id)
    index = _validate_index(payload.get("index"))

    if str(node_id) == ROOT_ID:
        raise ApiError(
            ROOT_PROTECTED, "The root node cannot be moved.", 400, {"nodeId": ROOT_ID}
        )

    with state.lock:
        core = state.core
        # Pre-checked here rather than relying on move_node's message so each
        # failure gets its own stable error code.
        _require_node(core, node_id)
        _require_node(core, new_parent_id, PARENT_NOT_FOUND, "New parent node")
        if would_create_cycle(core, node_id, new_parent_id):
            raise ApiError(
                CYCLE_REJECTED,
                f"Cannot move '{node_id}' into itself or one of its descendants.",
                400,
                {"nodeId": str(node_id), "newParentId": new_parent_id},
            )

        state.push_undo()
        moved, reason = move_node(core, node_id, new_parent_id, index)
        if not moved:  # pragma: no cover - every cause is pre-checked above
            # move_node only ever returns False before it touches the tree, so
            # the document is unchanged here and the undo entry just pushed is
            # a harmless no-op.
            raise ApiError(INVALID_FIELD, reason or "Move rejected.", 400)
        core.recalculate_probabilities()
        state.mark_dirty()

        return ok_response(
            nodeId=str(node_id),
            parentId=find_parent_id(core, node_id),
            **_mutation_payload(state),
        )


# ---- history -------------------------------------------------------------


@tree_bp.post("/undo")
def undo():
    """Step back one edit.

    The document stays dirty afterwards: undoing back to the last saved state
    is not tracked, and claiming "saved" when it might not be would risk
    losing work at the next New/Open.
    """
    state = get_state()
    with state.lock:
        if not state.undo():
            raise ApiError(NOTHING_TO_UNDO, "There is nothing to undo.", 400)
        state.core.recalculate_probabilities()
        state.mark_dirty()
        return ok_response(
            metadata=state.core.get_metadata(), **_mutation_payload(state)
        )


@tree_bp.post("/redo")
def redo():
    """Step forward one undone edit."""
    state = get_state()
    with state.lock:
        if not state.redo():
            raise ApiError(NOTHING_TO_REDO, "There is nothing to redo.", 400)
        state.core.recalculate_probabilities()
        state.mark_dirty()
        return ok_response(
            metadata=state.core.get_metadata(), **_mutation_payload(state)
        )
