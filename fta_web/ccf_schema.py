"""
Validators of the CCF group API input (FN-70, ``beta`` and ``alpha``).

``POST`` and ``PATCH /api/ccf/groups`` read the body with
``strict_input.read_strict_json`` and check each field here. Errors are
:class:`errors.ApiError` (``INVALID_FIELD``, 400) with ``detail.field`` naming
the offending key, like ``node_schema`` and ``strict_input``.

``validate_ccf_beta`` checks the beta factor and ``validate_ccf_alpha`` the
list of alpha factors of the alpha model (F2A); the validators of the other
group fields and :func:`parse_group_payload` (one body, whole) follow them.
Length and sum of the alphas are not checked here: they are lint (FN-43).
"""
from __future__ import annotations

from typing import Any, Collection, Dict, List, Mapping, Optional

try:  # normal package import: ``import fta_web.ccf_schema``
    from . import config  # noqa: F401  (puts fta_web/core on sys.path)
    from .errors import INVALID_FIELD, ApiError
    from .node_schema import refuse_unsavable_text
    from .strict_input import number_field
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import config  # type: ignore[no-redef]  # noqa: F401
    from errors import INVALID_FIELD, ApiError  # type: ignore[no-redef]
    from node_schema import refuse_unsavable_text  # type: ignore[no-redef]
    from strict_input import number_field  # type: ignore[no-redef]

from FTA_Editor_core import sanitize_name  # noqa: E402

#: The longest group name the API stores.
MAX_NAME_LENGTH = 4000

#: Fields a new group may carry. ``alpha`` and ``testing`` belong to the alpha
#: model and ``beta`` to the beta model; the other model's fields must be
#: absent or null.
CREATE_FIELDS = ("name", "model", "beta", "members", "source", "alpha", "testing")
#: Fields ``PATCH`` may change. The id is fixed once created.
PATCH_FIELDS = ("name", "model", "beta", "alpha", "testing", "source", "members")
#: The group models the API accepts.
MODELS = ("beta", "alpha")
#: The testing schemes (SPEC 7.1 spelling).
TESTING_SCHEMES = ("staggered", "nonStaggered")


def _invalid(field: str, message: str, **detail: Any) -> ApiError:
    return ApiError(INVALID_FIELD, message, 400, dict({"field": field}, **detail))


def validate_ccf_beta(value: Any, field: str = "beta") -> Any:
    """``value`` if it is a finite JSON number in [0, 1] (FN-70), else
    ``INVALID_FIELD`` naming ``field``.

    Both ends are allowed: beta 0 means no common cause and beta 1 means every
    failure is common. A string such as ``"0.1"``, a bool, None, a list, an
    infinity or a number outside the range is refused; ``-0`` comes back as
    ``0.0``. The NaN and Infinity tokens never get here: ``read_strict_json``
    refuses them as ``INVALID_JSON`` first.
    """
    return number_field(value, field, 0.0, 1.0)


def validate_ccf_alpha(value: Any, field: str = "alpha") -> List[float]:
    """The alpha factors of an alpha group: a list of finite JSON numbers, each
    in [0, 1] (FN-70, like ``beta``), else ``INVALID_FIELD`` naming ``field``.

    A bad item (a string such as ``"0.1"``, a bool, None, a list, a number
    outside the range) is refused with ``detail.index``, its 0-based position
    (the message names the 1-based position, like the field labels α1, α2 ...).
    ``-0`` comes back as ``0.0``; the empty list is accepted. The length and the
    sum are not checked: a list that does not fit the members or does not add
    up to 1 is lint (``CCF_ALPHA_SUM``, FN-43), so the editor can save it and
    show the reason.
    """
    if not isinstance(value, list):
        raise _invalid(field, "'%s' must be a list of numbers." % field)
    out = []
    for index, item in enumerate(value):
        try:
            out.append(number_field(item, field, 0.0, 1.0))
        except ApiError:
            raise _invalid(field, "'%s' item %d must be a number in [0, 1]." % (field, index + 1),
                           index=index) from None
    return out


def validate_ccf_testing(value: Any, field: str = "testing") -> Optional[str]:
    """``None`` (no scheme chosen), ``"staggered"`` or ``"nonStaggered"``, else
    ``INVALID_FIELD`` naming ``field`` (SPEC 7.1 spells the second one without
    a hyphen)."""
    if value is not None and not (isinstance(value, str) and value in TESTING_SCHEMES):
        raise _invalid(field, "'%s' must be 'staggered', 'nonStaggered' or null." % field)
    return value


def validate_group_name(value: Any, field: str = "name") -> str:
    """A group name: a string, sanitized like a node name (runs of white space
    become one space, ends trimmed), not empty, at most 4000 characters."""
    if not isinstance(value, str):
        raise _invalid(field, "'%s' must be a string." % field)
    name = refuse_unsavable_text(sanitize_name(value), field)
    if not name:
        raise _invalid(field, "'%s' must not be empty." % field)
    if len(name) > MAX_NAME_LENGTH:
        raise _invalid(field, "'%s' must be at most %d characters." % (field, MAX_NAME_LENGTH))
    return name


def validate_group_source(value: Any, field: str = "source") -> str:
    """The source note of a group (data handbook and page): a string or null;
    null is stored as an empty string."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise _invalid(field, "'%s' must be a string or null." % field)
    return refuse_unsavable_text(value, field)


def validate_member_ids(value: Any, tree_ids: Collection[str], field: str = "members") -> List[str]:
    """A list of distinct, non-empty node ids that all exist in the tree.

    An id that is not in the tree is refused with ``detail.ids`` listing every
    such id. A member that already belongs to another group, or is not a basic
    event, is accepted here; lint flags it (FN-33).
    """
    if not isinstance(value, list):
        raise _invalid(field, "'%s' must be a list of node ids." % field)
    seen = set()
    for item in value:
        if not isinstance(item, str) or not item:
            raise _invalid(field, "'%s' must be a list of non-empty node id strings." % field)
        if item in seen:
            raise _invalid(field, "'%s' lists node '%s' more than once." % (field, item))
        seen.add(item)
    unknown = [item for item in value if item not in tree_ids]
    if unknown:
        raise _invalid(
            field,
            "'%s' names nodes that are not in the tree: %s." % (field, ", ".join(unknown)),
            ids=unknown,
        )
    return list(value)


def _check_model_fields(payload: Mapping[str, Any], model: Any) -> None:
    """Refuse the fields of the other model unless they are null: ``alpha`` and
    ``testing`` for the beta model, ``beta`` for the alpha model."""
    for key in ("beta",) if model == "alpha" else ("alpha", "testing"):
        if payload.get(key) is not None:
            raise _invalid(key, "'%s' must be null for the %s-factor model."
                           % (key, "alpha" if model == "alpha" else "beta"))


def parse_group_payload(payload: Mapping[str, Any], tree_ids: Collection[str],
                        creating: bool, stored_model: Optional[str] = None) -> Dict[str, Any]:
    """The validated fields of a ``POST`` (``creating``) or ``PATCH`` body.

    Returns the fields the body carries, validated (``name``, ``model``,
    ``beta``, ``alpha``, ``testing``, ``members``, ``source``), plus the
    nulls the model rules imply: a new group, and a ``PATCH`` whose ``model``
    differs from ``stored_model``, get ``beta``, ``alpha`` and ``testing`` None
    unless the body gives them for the model (SPEC 7.1: ``beta: null`` for an
    alpha group; the old model's values are dropped, Undo restores them).

    A new group needs ``name``, ``model``, ``members`` and its model's
    parameter (``beta``, or ``alpha``; ``testing`` is optional). The other
    model's fields must be absent or null; the effective model of a ``PATCH``
    is the body's ``model``, else ``stored_model``. Errors are
    ``INVALID_FIELD`` naming the field: an unknown key (``id`` included), a
    missing required field on create, a field of the other model that is not
    null, or an empty ``PATCH``.
    """
    allowed = CREATE_FIELDS if creating else PATCH_FIELDS
    unknown = [str(key) for key in payload if key not in allowed]
    if unknown:
        raise ApiError(
            INVALID_FIELD,
            "Unsupported field(s): %s." % ", ".join(sorted(unknown)),
            400,
            {"field": sorted(unknown)[0], "fields": sorted(unknown)},
        )
    if not creating and not payload:
        raise ApiError(INVALID_FIELD, "No group fields to update.", 400, {"field": None})
    if creating:
        for key in ("name", "model"):
            if key not in payload:
                raise _invalid(key, "'%s' is required." % key)
    if "model" in payload and payload["model"] not in MODELS:
        raise _invalid("model", "'model' must be 'beta' or 'alpha'.")
    model = payload.get("model", stored_model)
    if creating:
        for key in (model, "members"):  # the model's parameter is named like the model
            if key not in payload:
                raise _invalid(key, "'%s' is required." % key)
    _check_model_fields(payload, model)

    out: Dict[str, Any] = {}
    if "name" in payload:
        out["name"] = validate_group_name(payload["name"])
    if "model" in payload:
        out["model"] = payload["model"]
    if "beta" in payload and model != "alpha":
        out["beta"] = validate_ccf_beta(payload["beta"])
    if "alpha" in payload and model == "alpha":
        out["alpha"] = validate_ccf_alpha(payload["alpha"])
    if "testing" in payload and model == "alpha":
        out["testing"] = validate_ccf_testing(payload["testing"])
    if "source" in payload:
        out["source"] = validate_group_source(payload["source"])
    if "members" in payload:
        out["members"] = validate_member_ids(payload["members"], tree_ids)
    if creating or model != stored_model:
        for key in ("beta", "alpha", "testing"):
            out.setdefault(key, None)
    return out
