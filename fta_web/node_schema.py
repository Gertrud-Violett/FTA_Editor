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
import re
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


def canonical_mode(mode: Any) -> str:
    """A document mode as ``POST /api/metadata`` stores it: "ETA" in any case
    or spacing is "ETA", anything else "FTA". The engine computes an event
    tree only for the exact string "ETA" while the analysis endpoints and the
    CLI compare case-insensitively, so a file saying "eta" was computed as a
    fault tree and refused as an event tree."""
    return "ETA" if str(mode or "").strip().upper() == "ETA" else "FTA"


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
    try:
        number = float(value)
    except OverflowError:  # an int beyond the float range (a 400-digit literal)
        number = math.inf
    if math.isnan(number) or math.isinf(number):
        raise _invalid(field, "'%s' must be a finite number." % field, value)
    if number < minimum or (exclusive_min and number == minimum):
        op = ">" if exclusive_min else ">="
        raise _invalid(field, "'%s' must be %s %g." % (field, op, minimum), value)
    return number


#: An unpaired UTF-16 surrogate. Python keeps one that JSON spells
#: (``"\\ud83d"``, half of an emoji) -- a *paired* escape becomes one astral
#: character -- but it cannot be encoded as UTF-8, so a document holding one
#: could not be saved, exported or printed any more.
_LONE_SURROGATE = re.compile("[\ud800-\udfff]")


def refuse_unsavable_text(value: str, field: str) -> str:
    """``value``, or a 400 ``INVALID_FIELD`` naming ``field`` when it holds an
    unpaired surrogate (see :data:`_LONE_SURROGATE`). Every validator of
    stored text goes through here."""
    found = _LONE_SURROGATE.search(value)
    if found:
        raise _invalid(
            field,
            "'%s' contains an unpaired surrogate (U+%04X), which cannot be saved."
            % (field, ord(found.group())),
        )
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise _invalid(field, "'%s' must be a string." % field, value)
    if len(value) > MAX_TEXT:
        raise _invalid(field, "'%s' is longer than %d characters." % (field, MAX_TEXT))
    return refuse_unsavable_text(value, field)


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
    text = refuse_unsavable_text(str(value).strip(), "transferTo")
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
                tag = refuse_unsavable_text(tag.strip(), field)
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


#: The gate types logicGate (AND/OR only) can never hold: one found there is
#: promoted to gateType by :func:`reconcile_gate_types`.
_PROMOTABLE = tuple(g for g in GATE_TYPES if g not in ("AND", "OR"))


def _promote(node: Dict[str, Any], gate_type: str, cause: str) -> Dict[str, Any]:
    """Move an advanced gate name out of ``logicGate`` into ``gateType``;
    the ``gate_type_promoted`` warning that says so."""
    projected = project_logic_gate(gate_type)
    node["gateType"] = gate_type
    node["logicGate"] = projected
    node_id = str(node.get("id"))
    where = ("set by the AI assistant" if cause == "ai"
             else "written by hand or by another program")
    return {
        "kind": "gate_type_promoted",
        "old_id": node_id,
        "new_id": node_id,
        "name": node.get("name"),
        "gateType": gate_type,
        "logicGate": projected,
        "cause": cause,
        "message": "Node %r: logicGate held %s (%s), but it holds only AND or OR; "
                   "%s is now the gate type and logicGate is %s."
                   % (node_id, gate_type, where, gate_type, projected),
    }


def reconcile_gate_types(tree: Any, cause: str = "desktop") -> List[Dict[str, Any]]:
    """Make every node's ``gateType`` and ``logicGate`` agree. Mutates
    ``tree``; returns load warnings (``kind`` ``gate_type_reset`` or
    ``gate_type_promoted``; ``cause``: ``desktop`` for a loaded file, ``ai``
    for an AI edit -- it picks the message).

    The 1.6 desktop app edits only ``logicGate`` and keeps unknown keys, so a
    file edited there can carry a stale ``gateType`` (a KOFN whose gate the
    user switched to AND). The web engine follows ``gateType``, which would
    silently discard the desktop edit -- so ``logicGate`` is trusted, and the
    ``gateType`` goes together with the ``k``/``transferTo`` that only it used.

    The desktop app only ever writes AND or OR, so only those values can be a
    desktop edit. Any other ``logicGate`` (a hand-written ``"PAND"`` beside
    gateType PAND) keeps the ``gateType`` and is set to its projection,
    without a warning.

    No 1.6 program writes an advanced gate name into ``logicGate`` either, so
    one there without a ``gateType`` (a hand edit) means that gate: it is
    *promoted* to the ``gateType`` and ``logicGate`` becomes its projection
    (``gate_type_promoted``). Any other value is left alone; the engine reads
    it as 1.6 does (AND, else OR).
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
        if gate_type is None or (isinstance(gate_type, str) and not gate_type.strip()):
            raw = str(node.get("logicGate") or "").strip().upper()
            if raw in _PROMOTABLE:
                warnings.append(_promote(node, raw, cause))
            continue
        logic = str(node.get("logicGate") or "OR").strip().upper()
        projected = project_logic_gate(gate_type)
        if logic not in ("AND", "OR"):
            node["logicGate"] = projected
            continue
        if projected == logic:
            continue
        node.pop("gateType", None)
        dropped = ["gateType"]
        for key in ("k", "transferTo"):
            if key in node:
                node.pop(key)
                dropped.append(key)
        node_id = str(node.get("id"))
        where = ("set by the AI assistant" if cause == "ai"
                 else "probably changed in the desktop editor")
        warnings.append({
            "kind": "gate_type_reset",
            "old_id": node_id,
            "new_id": node_id,
            "name": node.get("name"),
            "gateType": gate_type,
            "logicGate": logic,
            "dropped": dropped,
            "cause": cause,
            "message": "Node %r: its gate is %s (%s) but the "
                       "stored gate type was %s; the gate type was dropped and %s is used."
                       % (node_id, logic, where, str(gate_type), logic),
        })
    return warnings


def drop_duplicate_links(tree: Any) -> List[Dict[str, Any]]:
    """Drop every repeated link -- same ``target_id``, same effective relation
    -- keeping the first. Mutates ``tree``; returns one load warning
    (``kind: "duplicate_link"``) per link dropped.

    The engine applies every link it finds, so a repeated link counted as a
    second independent event: an AND-link twice multiplied by its target's
    probability twice. The UI's links editor and ``PATCH /api/nodes`` refuse
    a duplicate; a file can still carry one. "Effective" is what the engine
    does with the relation: "AND" (any case) is AND, anything else OR.
    """
    warnings: List[Dict[str, Any]] = []
    stack = [tree] if isinstance(tree, dict) else []
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        stack.extend(reversed([c for c in node.get("children") or [] if isinstance(c, dict)]))
        links = node.get("links")
        if not isinstance(links, list) or len(links) < 2:
            continue
        kept: List[Any] = []
        seen = set()
        for link in links:
            target = link.get("target_id") if isinstance(link, dict) else None
            if target in (None, ""):
                kept.append(link)
                continue
            relation = "AND" if str(link.get("relation") or "OR").upper() == "AND" else "OR"
            if (str(target), relation) in seen:
                node_id = str(node.get("id"))
                warnings.append({
                    "kind": "duplicate_link",
                    "old_id": node_id,
                    "new_id": node_id,
                    "name": node.get("name"),
                    "targetId": str(target),
                    "relation": relation,
                    "message": "Node %r linked to %r (%s) more than once; the repeated "
                               "link was removed (it was counted twice)."
                               % (node_id, str(target), relation),
                })
                continue
            seen.add((str(target), relation))
            kept.append(link)
        if len(kept) != len(links):
            node["links"] = kept
    return warnings


def _scrub(value: Any, path: str, changed: List[str], skip: Optional[str] = None) -> Any:
    """``value`` with every unpaired surrogate -- in strings and dict keys, at
    any depth -- replaced by U+FFFD. Dicts and lists are repaired in place
    (and returned); the dotted path of every repaired text is appended to
    ``changed``. ``skip`` names a dict key left alone (a node's children)."""
    if isinstance(value, str):
        fixed = _LONE_SURROGATE.sub("\ufffd", value)
        if fixed != value:
            changed.append(path)
        return fixed
    if isinstance(value, list):
        for position, item in enumerate(value):
            value[position] = _scrub(item, path, changed)
        return value
    if isinstance(value, dict):
        before = len(changed)
        entries = []
        for key, item in value.items():
            new_key = _LONE_SURROGATE.sub("\ufffd", key) if isinstance(key, str) else key
            sub_path = "%s.%s" % (path, new_key) if path else str(new_key)
            if new_key != key:
                changed.append(sub_path)
            entries.append((new_key, item if key == skip else _scrub(item, sub_path, changed)))
        if len(changed) != before:
            value.clear()
            value.update(entries)
        return value
    return value


def repair_unsavable_text(core: Any) -> List[Dict[str, Any]]:
    """Replace every unpaired surrogate in a loaded document with U+FFFD.

    Python keeps one that JSON spells, but it cannot be encoded: the document
    could not be saved, exported or printed. Every node's text (ids, links
    and nested objects included), the title and the date are repaired in
    place, as are the load warnings already recorded (they reach the page,
    the CLI and the report). Returns load warnings (``kind:
    "invalid_text"``, ``fields``: the dotted keys repaired): one per node,
    one for the title/date. Two ids that become equal are told apart again
    the way the core tells duplicate ids apart.
    """
    warnings: List[Dict[str, Any]] = []
    ids_changed = False
    tree = getattr(core, "fta_data", None)
    stack = [tree] if isinstance(tree, dict) else []
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        old_id = node.get("id")
        changed: List[str] = []
        _scrub(node, "", changed, skip="children")
        if changed:
            ids_changed = ids_changed or node.get("id") != old_id
            fields = list(dict.fromkeys(changed))
            node_id = str(node.get("id"))
            warnings.append({
                "kind": "invalid_text",
                "old_id": node_id,
                "new_id": node_id,
                "name": node.get("name"),
                "fields": fields,
                "message": "Node %r: text that cannot be saved (an unpaired surrogate) "
                           "was replaced with U+FFFD in %s." % (node_id, ", ".join(fields)),
            })
        stack.extend(reversed([c for c in node.get("children") or [] if isinstance(c, dict)]))

    fields = []
    for attr in ("title", "date"):
        changed = []
        setattr(core, attr, _scrub(getattr(core, attr, None), attr, changed))
        if changed:
            fields.append(attr)
    if fields:
        warnings.append({
            "kind": "invalid_text",
            "old_id": None,
            "new_id": None,
            "fields": fields,
            "message": "The document's %s held text that cannot be saved (an unpaired "
                       "surrogate); it was replaced with U+FFFD." % " and ".join(fields),
        })
    _scrub(getattr(core, "last_load_warnings", None), "", [])
    if ids_changed:
        core._dedupe_node_ids(tree, warnings)
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
