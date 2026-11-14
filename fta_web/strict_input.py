"""
Strict reading of request input (FN-70, the shared part).

Three helpers that a route calls instead of ``request.get_json(silent=True)``
and ad-hoc ``float()``: they differ from today's readers only in strictness.

``read_strict_json``    the body as JSON, refusing the tokens ``NaN``,
                        ``Infinity`` and ``-Infinity`` (Python accepts them,
                        JSON does not) and any body that is empty, truncated,
                        not JSON or not UTF-8: ``INVALID_JSON``, 400.
``number_field``        a finite JSON number inside a range with open or closed
                        ends; ``-0`` comes back as ``0.0``: ``INVALID_FIELD``.
``validate_revision``   a non-negative integer (a revision or document
                        serial): ``INVALID_FIELD``.

Errors are :class:`errors.ApiError` with a ``detail.field`` naming the
offending key, exactly like ``node_schema`` and ``routes/tree.py``. Importing
this module registers nothing: no route, no change to the app's JSON provider.
"""
from __future__ import annotations

import json
import math
from typing import Any

try:  # normal package import: ``import fta_web.strict_input``
    from .errors import INVALID_FIELD, INVALID_JSON, ApiError
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    from errors import INVALID_FIELD, INVALID_JSON, ApiError  # type: ignore[no-redef]


def _refuse_constant(token: str) -> Any:
    """``json`` calls this for NaN, Infinity and -Infinity."""
    raise ValueError("%s is not valid JSON" % token)


def read_strict_json(request: Any) -> Any:
    """The parsed JSON body of ``request`` (FN-70).

    The Content-Type header does not matter. A body that is empty, truncated,
    not JSON, not UTF-8, nested too deeply, or that holds ``NaN``,
    ``Infinity`` or ``-Infinity`` as a bare token anywhere raises
    ``INVALID_JSON`` (400). The words inside a string are just text.

    A number literal beyond the float range (``1e999``) becomes ``inf`` in
    Python without being a token; only :func:`number_field` makes a value
    finite, so every numeric field must go through it.
    """
    raw = request.get_data()
    try:
        return json.loads(raw.decode("utf-8"), parse_constant=_refuse_constant)
    except (ValueError, RecursionError):  # JSONDecodeError and UnicodeDecodeError too
        raise ApiError(
            INVALID_JSON,
            "Request body must be valid JSON (no NaN or Infinity).",
            400,
        ) from None


def _bound(value: float) -> str:
    if math.isinf(value):
        return "infinity" if value > 0 else "-infinity"
    return "%g" % value


def number_field(
    value: Any,
    field: str,
    lo: float,
    hi: float,
    *,
    lo_open: bool = False,
    hi_open: bool = False,
) -> Any:
    """``value`` if it is a finite JSON number inside the range (FN-70).

    The range is ``lo`` .. ``hi``; each end is excluded when its ``*_open``
    flag is set, and ``hi`` may be ``math.inf`` (``lo`` ``-math.inf``).
    Accepted: an int or a float; refused: a bool, a string, None, a list, an
    object, NaN, an infinity, an integer too large for a float. ``-0`` comes
    back as ``0.0``. Otherwise ``INVALID_FIELD`` (400), the message naming the
    field and its range.
    """
    message = "'%s' must be a number in %s%s, %s%s." % (
        field,
        "(" if lo_open else "[",
        _bound(lo),
        _bound(hi),
        ")" if hi_open else "]",
    )
    invalid = ApiError(INVALID_FIELD, message, 400, {"field": field})
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise invalid
    try:
        finite = math.isfinite(float(value))
    except OverflowError:  # an int beyond the float range (a 400-digit literal)
        finite = False
    if not finite:
        raise invalid
    if value < lo or (lo_open and value == lo):
        raise invalid
    if value > hi or (hi_open and value == hi):
        raise invalid
    if value == 0:
        return 0.0
    return value


def validate_revision(value: Any, field: str) -> int:
    """``value`` if it is a non-negative integer (FN-70), else ``INVALID_FIELD``.

    Only a JSON integer counts: a bool, a float (even ``1.0``), a negative
    number, a string and None are refused.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ApiError(
            INVALID_FIELD,
            "'%s' must be a non-negative integer." % field,
            400,
            {"field": field},
        )
    return value
