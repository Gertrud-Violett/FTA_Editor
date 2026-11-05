"""
CCF group endpoints -- ``/api/ccf/groups`` (F2, SPEC 7.5, DESIGN section 8; F2A
adds the alpha model: ``alpha``, ``testing`` and the model switch).

========  ====================  ==========================================
GET       /groups               the stored groups, each with its status
POST      /groups               create a group (id ``g<N>`` assigned here)
PATCH     /groups/<id>          change a group's fields (also its model)
DELETE    /groups/<id>          delete a group
========  ====================  ==========================================

Every body goes through ``strict_input.read_strict_json`` (a body that is not
a JSON object, or that holds NaN or Infinity, is ``INVALID_JSON``) and every
field through ``ccf_schema`` (``INVALID_FIELD`` with ``detail.field``). The
groups live in the document's ``analysis["ccfGroups"]`` (DESIGN D1), so the
standard undo and redo restore them.

Each change that alters something is one undo step and raises ``revision``:
``state.push_undo()`` before the change, ``state.mark_dirty()`` after, under
``state.lock``. A ``PATCH`` that would change nothing answers ``changed:
false`` and makes no undo step. Groups can be edited in ETA mode too (they are
data; the status then reads ``CCF_ETA_MODE``).

The status of a group (``applied``, the reason and message in English and
Japanese, the warnings) is worked out by ``ccf.assess`` (FN-33). A member
that is in another group or is not a basic event is accepted here and shows
up in the status, never as a refusal.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from flask import Blueprint, request

try:  # normal package import: ``import fta_web.routes.ccf``
    from .. import ccf, ccf_schema
    from ..errors import INVALID_JSON, ApiError, api_error_response, ok_response
    from ..state import get_state
    from ..strict_input import read_strict_json
    from ..tree_ops import all_ids
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import ccf  # type: ignore[no-redef]
    import ccf_schema  # type: ignore[no-redef]
    from errors import INVALID_JSON, ApiError, api_error_response, ok_response  # type: ignore[no-redef]
    from state import get_state  # type: ignore[no-redef]
    from strict_input import read_strict_json  # type: ignore[no-redef]
    from tree_ops import all_ids  # type: ignore[no-redef]

ccf_bp = Blueprint("ccf", __name__, url_prefix="/api/ccf")

#: Error code of a group id that no stored group has (404).
GROUP_NOT_FOUND = "GROUP_NOT_FOUND"


@ccf_bp.errorhandler(ApiError)
def _handle_api_error(exc: ApiError):
    return api_error_response(exc)


# ---- helpers -----------------------------------------------------------------


def _body() -> Dict[str, Any]:
    """The request's JSON object (strict: no NaN, no Infinity)."""
    data = read_strict_json(request)
    if not isinstance(data, dict):
        raise ApiError(INVALID_JSON, "Request body must be a JSON object.", 400)
    return data


def _mutation_payload(state) -> Dict[str, Any]:
    """The post-mutation view every mutating endpoint returns (as routes/tree.py)."""
    core = state.core
    return {
        "tree": copy.deepcopy(core.get_data()),
        "zeroNodes": core.get_zero_probability_nodes(),
        "dirty": state.dirty,
        "canUndo": state.can_undo,
        "canRedo": state.can_redo,
        "analysis": ccf.public_analysis(getattr(core, "analysis", None)),
        "sessionWarnings": copy.deepcopy(state.session_warnings),
        **state.revision_fields(),
    }


def _listing(core):
    """``(groups, block)`` as ``ccf.listing`` gives them, for the live document."""
    return ccf.listing(core.get_data(), core.analysis, core.mode)


def _stored_groups(core) -> List[Any]:
    """The live list of stored groups; created on the document when absent."""
    groups = core.analysis.get(ccf.ANALYSIS_KEY)
    if not isinstance(groups, list):
        groups = []
        core.analysis[ccf.ANALYSIS_KEY] = groups
    return groups


def _find(core, group_id: str) -> Optional[Dict[str, Any]]:
    for group in ccf.groups_of(core.analysis):
        if isinstance(group, dict) and group.get("id") == group_id:
            return group
    return None


def _not_found(group_id: str) -> ApiError:
    return ApiError(GROUP_NOT_FOUND, "CCF group '%s' was not found." % group_id, 404,
                    {"groupId": group_id})


def _new_id(core) -> str:
    """``g<N>``, N the smallest positive integer whose id no stored group has."""
    taken = {g.get("id") for g in ccf.groups_of(core.analysis) if isinstance(g, dict)}
    number = 1
    while "g%d" % number in taken:
        number += 1
    return "g%d" % number


def _same(a: Any, b: Any) -> bool:
    """Equal in value and in type, so that 1 and True, or 1 and 1.0, differ."""
    return type(a) is type(b) and a == b


def _drop_rename_flag(core, group_id: str) -> bool:
    renamed = core.analysis.get(ccf.RENAMED_KEY)
    if not isinstance(renamed, dict) or group_id not in renamed:
        return False
    del renamed[group_id]
    if not renamed:
        del core.analysis[ccf.RENAMED_KEY]
    return True


def _group_view(core, group_id: str) -> Optional[Dict[str, Any]]:
    groups, _block = _listing(core)
    for item in groups:
        if item["id"] == group_id:
            return item
    return None


# ---- routes ------------------------------------------------------------------


@ccf_bp.get("/groups")
def list_groups():
    """The stored groups with ``memberNames`` and ``status``, the ``ccf`` block
    (applied, notApplied, note), the mode and the revision."""
    state = get_state()
    with state.lock:
        core = state.core
        groups, block = _listing(core)
        return ok_response(groups=groups, ccf=block, mode=str(core.mode).upper(),
                           **state.revision_fields())


@ccf_bp.post("/groups")
def create_group():
    """Create a group. Body: ``{name, model: "beta", beta, members, source?}`` or
    ``{name, model: "alpha", alpha, testing?, members, source?}``."""
    payload = _body()
    state = get_state()
    with state.lock:
        core = state.core
        fields = ccf_schema.parse_group_payload(payload, all_ids(core), creating=True)
        group = ccf.make_group(_new_id(core), fields["name"], fields["beta"],
                               fields["members"], fields.get("source", ""), fields["model"],
                               fields["alpha"], fields["testing"])
        state.push_undo()
        _stored_groups(core).append(group)
        state.mark_dirty()
        groups, block = _listing(core)
        return ok_response(group=_group_view(core, group["id"]), groups=groups, ccf=block,
                           **_mutation_payload(state))


@ccf_bp.patch("/groups/<path:group_id>")
def update_group(group_id: str):
    """Change ``name``, ``model``, ``beta``, ``alpha``, ``testing``, ``source`` or
    ``members`` of a group (only the fields sent). A new ``model`` is one change:
    the old model's values become null (``ccf_schema.parse_group_payload``).
    ``members`` replaces the list, never touches ``alpha`` (F2A DESIGN A2) and
    clears the group's "renamed by the loader" flag. Nothing to change:
    ``changed: false``, no undo step."""
    payload = _body()
    state = get_state()
    with state.lock:
        core = state.core
        group = _find(core, group_id)
        if group is None:
            raise _not_found(group_id)
        fields = ccf_schema.parse_group_payload(payload, all_ids(core), creating=False,
                                                stored_model=group.get("model"))
        flagged = group_id in (core.analysis.get(ccf.RENAMED_KEY) or {})
        changed = any(not _same(group.get(key), value) for key, value in fields.items()) or (
            "members" in fields and flagged)
        if changed:
            state.push_undo()
            for key, value in fields.items():
                group[key] = value
            if "members" in fields:
                _drop_rename_flag(core, group_id)
            state.mark_dirty()
        groups, block = _listing(core)
        return ok_response(group=_group_view(core, group_id), groups=groups, ccf=block,
                           changed=changed, **_mutation_payload(state))


@ccf_bp.delete("/groups/<path:group_id>")
def delete_group(group_id: str):
    """Delete a group. The last one removed takes the ``ccfGroups`` key with
    it (an empty list is never stored)."""
    state = get_state()
    with state.lock:
        core = state.core
        group = _find(core, group_id)
        if group is None:
            raise _not_found(group_id)
        state.push_undo()
        groups = _stored_groups(core)
        groups[:] = [g for g in groups if g is not group]
        if not groups:
            del core.analysis[ccf.ANALYSIS_KEY]
        _drop_rename_flag(core, group_id)
        state.mark_dirty()
        listed, block = _listing(core)
        return ok_response(deletedId=group_id, groups=listed, ccf=block,
                           **_mutation_payload(state))
