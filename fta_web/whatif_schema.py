"""
Validators and constants of ``POST /api/whatif`` (F4, FN-70 for ``factor``).

The what-if endpoint reads its numbers in one way only: a finite JSON number,
through :func:`strict_input.number_field`. A string, a bool, ``null``, ``NaN``
or an infinity is never converted: the browser sends numbers it has already
parsed, so anything else means a broken client and answers ``INVALID_FIELD``
(400) naming the field.

``validate_whatif_factor``  a factor, a number in [0.01, 100] (both ends closed)
``read_request``            the whole body, in the order of DESIGN 3.1

Revision and document serial use :func:`strict_input.validate_revision`.
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

try:  # normal package import: ``import fta_web.whatif_schema``
    from .errors import INVALID_FIELD, INVALID_JSON, ApiError
    from .strict_input import number_field, read_strict_json, validate_revision
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    from errors import INVALID_FIELD, INVALID_JSON, ApiError  # type: ignore[no-redef]
    from strict_input import (  # type: ignore[no-redef]
        number_field,
        read_strict_json,
        validate_revision,
    )

#: The factor range of the slider (UI-14): 1/100 to 100, ends included.
MIN_FACTOR = 0.01
MAX_FACTOR = 100.0

#: The most entries one request may hold in ``factors``.
MAX_FACTORS = 1000


def validate_whatif_factor(value: Any, field: str = "factor") -> float:
    """A factor: a finite JSON number in [0.01, 100]."""
    return float(number_field(value, field, MIN_FACTOR, MAX_FACTOR))


def read_request(request: Any) -> Tuple[int, Optional[int], List[Tuple[str, float]]]:
    """``(revision, documentSerial or None, [(nodeId, factor), ...])``.

    Order of the checks (DESIGN 3.1): the body is strict JSON and an object,
    ``revision``, ``documentSerial`` (optional), the shape of ``factors``, then
    every factor value in request order. The ids are checked against the
    document later, under its lock.
    """
    body = read_strict_json(request)
    if not isinstance(body, dict):
        raise ApiError(INVALID_JSON, "Request body must be a JSON object.", 400)
    revision = validate_revision(body.get("revision"), "revision")
    serial: Optional[int] = None
    if "documentSerial" in body:
        serial = validate_revision(body["documentSerial"], "documentSerial")
    factors = body.get("factors")
    if not isinstance(factors, dict):
        raise ApiError(INVALID_FIELD, "'factors' must be an object.", 400, {"field": "factors"})
    if len(factors) > MAX_FACTORS:
        raise ApiError(
            INVALID_FIELD,
            "'factors' holds %d entries; a request can hold at most %d."
            % (len(factors), MAX_FACTORS),
            400,
            {"field": "factors"},
        )
    out: List[Tuple[str, float]] = []
    for node_id, value in factors.items():
        try:
            out.append((node_id, validate_whatif_factor(value, "factor")))
        except ApiError as exc:
            exc.detail["id"] = node_id
            raise
    return revision, serial, out
