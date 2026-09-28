"""
The 1.7 node-key vocabulary and its validators -- one place for both.

Every key here is optional on a node. A node without any of them behaves
exactly as it did in 1.6 (and as it does in the desktop app), which is what
keeps files round-trippable between the two:

==============  ===========================================================
``gateType``    AND, OR, KOFN, XOR, INHIBIT, PAND or TRANSFER
``k``           vote threshold for KOFN (integer >= 1)
``transferTo``  target node id for TRANSFER (same file only)
``eventKind``   basic, house, undeveloped or conditioning
``houseState``  true/false for a house event
``quant``       ``{model, lambda, T, tau, mu, mttr, source, unc: {dist,
                median, mean, ef}}``
``trace``       ``{requirementId, testRef, owner, status, evidence, tags[]}``
``fmea``        ``{id, item, mode, cause, severity, occurrence, detection,
                rpn, source}``
==============  ===========================================================

``logicGate`` stays AND/OR only -- the AI validator and the desktop app accept
nothing else -- and is always the *projection* of ``gateType``
(:func:`project_logic_gate`), so a reader that only knows ``logicGate`` still
gets the closest coherent answer.

λ (``quant.lambda``) is always stored **per hour**. ``mu`` is a repair rate,
also per hour; ``T``, ``tau`` and ``mttr`` are hours. The UI converts from
per-year and FIT; nothing on disk ever carries another unit.

``static/js/schema.js`` mirrors the constants below. Change both together.

Validators raise :class:`errors.ApiError` with ``INVALID_FIELD`` and a
``detail.field`` naming the offending (dotted) key, exactly like the
validators in ``routes/tree.py``. The ``partial`` validators accept ``None``
for a sub-key, meaning "remove it" (see :func:`merge_partial`).
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Optional

try:  # normal package import: ``import fta_web.node_schema``
    from .errors import INVALID_FIELD, ApiError
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    from errors import INVALID_FIELD, ApiError  # type: ignore[no-redef]


# ---- vocabulary ------------------------------------------------------------

GATE_TYPES = ("AND", "OR", "KOFN", "XOR", "INHIBIT", "PAND", "TRANSFER")
EVENT_KINDS = ("basic", "house", "undeveloped", "conditioning")
QUANT_MODELS = ("fixed", "rate", "standby", "repairable")
TRACE_STATUS = ("draft", "reviewed", "approved")
UNC_DISTS = ("none", "lognormal")

#: gateType -> the AND/OR the legacy ``logicGate`` field carries.
_PROJECTION = {
    "AND": "AND",
    "INHIBIT": "AND",
    "PAND": "AND",
    "OR": "OR",
    "KOFN": "OR",
    "XOR": "OR",
    "TRANSFER": "OR",
}

#: Every 1.7 node key, in the order ``_node_view`` emits them.
NODE_KEYS = (
    "gateType",
    "k",
    "transferTo",
    "eventKind",
    "houseState",
    "quant",
    "trace",
    "fmea",
)

#: The keys whose PATCH merges partially rather than replacing.
PARTIAL_KEYS = ("quant", "trace", "fmea")

_QUANT_NUMBERS = ("lambda", "T", "tau", "mu", "mttr")
_UNC_NUMBERS = ("median", "mean", "ef")
_TRACE_STRINGS = ("requirementId", "testRef", "owner", "evidence")
_FMEA_STRINGS = ("id", "item", "mode", "cause", "source")
_FMEA_RANKS = ("severity", "occurrence", "detection")

MAX_TEXT = 4000
MAX_TAGS = 64


def project_logic_gate(gate_type: Any) -> str:
    """The AND/OR ``logicGate`` a ``gateType`` projects to. Unknown -> OR."""
    if not isinstance(gate_type, str):
        return "OR"
    return _PROJECTION.get(gate_type.strip().upper(), "OR")


# ---- helpers -----------------------------------------------------------------


def _invalid(field: str, message: str, value: Any = None) -> ApiError:
    detail: Dict[str, Any] = {"field": field}
    if value is not None:
        detail["value"] = value
    return ApiError(INVALID_FIELD, message, 400, detail)


def _number(value: Any, field: str, *, minimum: float = 0.0,
            exclusive_min: bool = False) -> float:
    """A finite real number >= ``minimum`` (or > when ``exclusive_min``)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid(field, "'%s' must be a number." % field, value)
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        raise _invalid(field, "'%s' must be a finite number." % field, value)
    if number < minimum or (exclusive_min and number == minimum):
        op = ">" if exclusive_min else ">="
        raise _invalid(field, "'%s' must be %s %g." % (field, op, minimum), value)
    return number


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise _invalid(field, "'%s' must be a string." % field, value)
    if len(value) > MAX_TEXT:
        raise _invalid(field, "'%s' is longer than %d characters." % (field, MAX_TEXT))
    return value


def _object(value: Any, field: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise _invalid(field, "'%s' must be an object." % field)
    return value


def _unknown_keys(value: Dict[str, Any], allowed, field: str) -> None:
    unknown = sorted(k for k in value if k not in allowed)
    if unknown:
        raise ApiError(
            INVALID_FIELD,
            "Unsupported key(s) in '%s': %s." % (field, ", ".join(unknown)),
            400,
            {"field": field, "fields": unknown},
        )


# ---- scalar keys ---------------------------------------------------------------


def validate_gate_type(value: Any) -> Optional[str]:
    """One of :data:`GATE_TYPES` (case-insensitive), or None/"" to remove it."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or value.strip().upper() not in GATE_TYPES:
        raise _invalid(
            "gateType",
            "'gateType' must be one of %s." % ", ".join(GATE_TYPES),
            value,
        )
    return value.strip().upper()


def validate_k(value: Any) -> Optional[int]:
    """KOFN vote threshold: an integer >= 1, or None to remove it."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _invalid("k", "'k' must be an integer of at least 1.", value)
    return value


def validate_transfer_to(value: Any) -> Optional[str]:
    """A node id (not resolved here -- a dangling transfer is a lint, not a 400)."""
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise _invalid("transferTo", "'transferTo' must be a node id.", value)
    text = str(value).strip()
    if not text:
        return None
    return text


def validate_event_kind(value: Any) -> Optional[str]:
    """One of :data:`EVENT_KINDS` (case-insensitive), or None/"" to remove it."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or value.strip().lower() not in EVENT_KINDS:
        raise _invalid(
            "eventKind",
            "'eventKind' must be one of %s." % ", ".join(EVENT_KINDS),
            value,
        )
    return value.strip().lower()


def validate_house_state(value: Any) -> Optional[bool]:
    """A real boolean, or None to remove it."""
    if value is None:
        return None
    if not isinstance(value, bool):
        raise _invalid("houseState", "'houseState' must be true or false.", value)
    return value


# ---- partial object keys --------------------------------------------------------


def validate_quant(partial: Any) -> Optional[Dict[str, Any]]:
    """Validate a (partial) ``quant`` object. ``None`` removes the whole key.

    Sub-keys set to ``None`` survive validation and mean "remove this key" to
    :func:`merge_partial`. ``unc`` is itself partial the same way.
    """
    if partial is None:
        return None
    partial = _object(partial, "quant")
    _unknown_keys(partial, ("model",) + _QUANT_NUMBERS + ("source", "unc"), "quant")
    out: Dict[str, Any] = {}
    for key, value in partial.items():
        field = "quant." + key
        if value is None:
            out[key] = None
        elif key == "model":
            if not isinstance(value, str) or value.strip().lower() not in QUANT_MODELS:
                raise _invalid(
                    field, "'%s' must be one of %s." % (field, ", ".join(QUANT_MODELS)), value
                )
            out[key] = value.strip().lower()
        elif key in ("T", "tau", "mttr"):
            out[key] = _number(value, field, exclusive_min=True)
        elif key in _QUANT_NUMBERS:
            out[key] = _number(value, field)
        elif key == "source":
            out[key] = _text(value, field)
        elif key == "unc":
            out[key] = _validate_unc(value)
    return out


def _validate_unc(partial: Any) -> Dict[str, Any]:
    partial = _object(partial, "quant.unc")
    _unknown_keys(partial, ("dist",) + _UNC_NUMBERS, "quant.unc")
    out: Dict[str, Any] = {}
    for key, value in partial.items():
        field = "quant.unc." + key
        if value is None:
            out[key] = None
        elif key == "dist":
            if not isinstance(value, str) or value.strip().lower() not in UNC_DISTS:
                raise _invalid(
                    field, "'%s' must be one of %s." % (field, ", ".join(UNC_DISTS)), value
                )
            out[key] = value.strip().lower()
        elif key == "ef":
            # An error factor is the p95/median ratio: 1 means no spread.
            out[key] = _number(value, field, minimum=1.0)
        else:
            out[key] = _number(value, field, exclusive_min=True)
    return out


def validate_trace(partial: Any) -> Optional[Dict[str, Any]]:
    """Validate a (partial) ``trace`` object. ``None`` removes the whole key."""
    if partial is None:
        return None
    partial = _object(partial, "trace")
    _unknown_keys(partial, _TRACE_STRINGS + ("status", "tags"), "trace")
    out: Dict[str, Any] = {}
    for key, value in partial.items():
        field = "trace." + key
        if value is None:
            out[key] = None
        elif key == "status":
            if not isinstance(value, str) or value.strip().lower() not in TRACE_STATUS:
                raise _invalid(
                    field, "'%s' must be one of %s." % (field, ", ".join(TRACE_STATUS)), value
                )
            out[key] = value.strip().lower()
        elif key == "tags":
            if not isinstance(value, list) or len(value) > MAX_TAGS:
                raise _invalid(field, "'trace.tags' must be a list of strings.")
            tags = []
            for tag in value:
                if not isinstance(tag, str):
                    raise _invalid(field, "'trace.tags' must be a list of strings.")
                tag = tag.strip()
                if tag and tag not in tags:
                    tags.append(tag[:200])
            out[key] = tags
        else:
            out[key] = _text(value, field)
    return out


def validate_fmea(partial: Any) -> Optional[Dict[str, Any]]:
    """Validate a (partial) ``fmea`` object. ``None`` removes the whole key.

    Severity/occurrence/detection are AIAG ranks 1..10; ``rpn`` is accepted
    as given (an imported sheet's own value) as a non-negative integer.
    """
    if partial is None:
        return None
    partial = _object(partial, "fmea")
    _unknown_keys(partial, _FMEA_STRINGS + _FMEA_RANKS + ("rpn",), "fmea")
    out: Dict[str, Any] = {}
    for key, value in partial.items():
        field = "fmea." + key
        if value is None:
            out[key] = None
        elif key in _FMEA_RANKS or key == "rpn":
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            if isinstance(value, bool) or not isinstance(value, int):
                raise _invalid(field, "'%s' must be an integer." % field, value)
            if key in _FMEA_RANKS and not 1 <= value <= 10:
                raise _invalid(field, "'%s' must be between 1 and 10." % field, value)
            if key == "rpn" and value < 0:
                raise _invalid(field, "'fmea.rpn' must not be negative.", value)
            out[key] = value
        elif key == "id":
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                raise _invalid(field, "'fmea.id' must be a string.", value)
            out[key] = _text(str(value), field)
        else:
            out[key] = _text(value, field)
    return out


#: key -> validator, for the PATCH/create field registry in routes/tree.py.
VALIDATORS = {
    "gateType": validate_gate_type,
    "k": validate_k,
    "transferTo": validate_transfer_to,
    "eventKind": validate_event_kind,
    "houseState": validate_house_state,
    "quant": validate_quant,
    "trace": validate_trace,
    "fmea": validate_fmea,
}


# ---- merging --------------------------------------------------------------------


def merge_partial(existing: Any, patch: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge a validated partial object onto ``existing`` and return a new dict.

    A ``None`` value removes that sub-key; a dict value merges recursively
    into a dict already there (so ``{"unc": {"ef": 3}}`` keeps ``unc.dist``);
    anything else replaces. Neither argument is mutated. A sub-object left
    empty by removals is dropped too, so ``{}`` never lingers on disk.
    """
    result: Dict[str, Any] = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    for key, value in (patch or {}).items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict):
            merged = merge_partial(result.get(key), value)
            if merged:
                result[key] = merged
            else:
                result.pop(key, None)
        else:
            result[key] = copy.deepcopy(value)
    return result


# ---- AI full-tree update merge-back -------------------------------------------------

#: What an AI full-tree rewrite is not asked to reproduce and usually drops.
MERGE_BACK_KEYS = (
    "gateType", "k", "transferTo", "eventKind", "houseState", "quant", "trace", "fmea",
)


def reconcile_gate_types(tree: Any) -> List[Dict[str, Any]]:
    """Drop every ``gateType`` that no longer projects to its node's
    ``logicGate``. Mutates ``tree``; returns load warnings
    (``kind: "gate_type_reset"``).

    The 1.6 desktop app edits only ``logicGate`` and keeps unknown keys, so a
    file edited there can carry a stale ``gateType`` (a KOFN whose gate the
    user switched to AND). The web engine follows ``gateType``, which would
    silently discard the desktop edit -- so ``logicGate`` is trusted, and the
    ``gateType`` goes together with the ``k``/``transferTo`` that only it used.
    """
    warnings: List[Dict[str, Any]] = []
    stack = [tree] if isinstance(tree, dict) else []
    seen = set()
    while stack:
        node = stack.pop()
        if not isinstance(node, dict) or id(node) in seen:
            continue
        seen.add(id(node))
        stack.extend(reversed([c for c in node.get("children") or [] if isinstance(c, dict)]))
        gate_type = node.get("gateType")
        if gate_type in (None, ""):
            continue
        logic = str(node.get("logicGate") or "OR").strip().upper()
        if project_logic_gate(gate_type) == logic:
            continue
        node.pop("gateType", None)
        dropped = ["gateType"]
        for key in ("k", "transferTo"):
            if key in node:
                node.pop(key)
                dropped.append(key)
        node_id = str(node.get("id"))
        warnings.append({
            "kind": "gate_type_reset",
            "old_id": node_id,
            "new_id": node_id,
            "name": node.get("name"),
            "gateType": gate_type,
            "logicGate": logic,
            "dropped": dropped,
            "message": "Node %r: its gate is %s (probably changed in the desktop editor) but the "
                       "stored gate type was %s; the gate type was dropped and %s is used."
                       % (node_id, logic, str(gate_type), logic),
        })
    return warnings


def merge_back_node_keys(before: Dict[str, Any], after: Dict[str, Any]) -> int:
    """Copy the 1.7 keys from ``before`` onto the same-id nodes of ``after``
    wherever ``after`` lacks them. Mutates ``after``; returns how many fields
    were restored.

    ``gateType`` (and ``k`` with it) is restored only while it still projects
    to the node's new ``logicGate``: an AI that turned an AND into an OR meant
    it, and a stale KOFN would silently overrule that.
    """
    def walk(node):
        stack = [node]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                yield current
                stack.extend(reversed(current.get("children") or []))

    old_by_id: Dict[str, Dict[str, Any]] = {}
    for node in walk(before or {}):
        old_by_id.setdefault(str(node.get("id")), node)

    restored = 0
    for node in walk(after or {}):
        old = old_by_id.get(str(node.get("id")))
        if old is None:
            continue
        gate_ok = True
        if "gateType" not in node and old.get("gateType"):
            new_gate = str(node.get("logicGate") or "OR").strip().upper()
            gate_ok = project_logic_gate(old["gateType"]) == new_gate
        for key in MERGE_BACK_KEYS:
            if key in node or key not in old:
                continue
            if key in ("gateType", "k", "transferTo") and not gate_ok:
                continue
            node[key] = copy.deepcopy(old[key])
            restored += 1
    return restored
