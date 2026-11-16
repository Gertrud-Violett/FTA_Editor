"""
The what-if engine (F4, FN-53, FN-55, FN-56, PERF-8).

A factor ``f`` multiplies one basic event's main parameter (lambda for
``rate``, ``standby`` and ``repairable``; q for ``fixed``), the way Monte Carlo
moves it (``uncertainty._q_function``). q follows from the model and is capped
at 1. The top event is then worked out by the headline's own method over a
BASELINE that is computed once per document version and kept in a one-entry
cache:

* ``mcub``       the baseline cut sets with the changed products, through
                 :func:`cutsets.mcub_of` (the function the headline uses);
* ``treeWalk``   the tree walk of a copy of the tree with the changed q;
* ``incomplete`` no number (FN-21).

A factor on a member of an applied CCF group applies to every member of the
group; the CCF event probabilities come from :func:`ccf.event_probabilities`
only (never a formula of this module).

Nothing here changes the document: the live tree is read, compared and, on a
miss, deep-copied by the caller; every computation works on those copies. No
Flask import (``errors`` is the project's error type).

Cache (DESIGN 2.2): ``(id(state), documentSerial, revision)`` plus equality of
the cached tree and analysis with the live ones; a summary that ran out of time
is never stored.
"""
from __future__ import annotations

import copy
import math
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # normal package import: ``import fta_web.whatif``
    from . import ccf, cutsets, engine, logic, uncertainty
    from .errors import INVALID_FIELD, ApiError
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import ccf  # type: ignore[no-redef]
    import cutsets  # type: ignore[no-redef]
    import engine  # type: ignore[no-redef]
    import logic  # type: ignore[no-redef]
    import uncertainty  # type: ignore[no-redef]
    from errors import INVALID_FIELD, ApiError  # type: ignore[no-redef]

#: 422: a factor on an event whose model cannot be evaluated (a parameter is missing).
WHATIF_NOT_EVALUABLE = "WHATIF_NOT_EVALUABLE"

#: ``STANDBY_LARGE_LT`` threshold on lambda * tau: the literal of ``engine.derive_quant``
#: (``lt = lam * tau; if lt > 0.2``), which has no named constant. Strict, like the engine.
STANDBY_LT_LIMIT = 0.2

#: The order of the entries of ``cautions`` (typed severity: the error, then the warnings).
#: CCF_NOT_APPLIED is first: the whole CCF contribution is missing from the number.
CAUTION_ORDER = ("CCF_NOT_APPLIED", "CCF_Q_ONE", "CCF_HIGH_Q", "STANDBY_LARGE_LT",
                 "CUTSETS_TRUNCATED")

NOTE_INCOMPLETE = "incomplete"
NOTE_CUTSETS_FROM_NOMINAL = "cutsets_from_nominal"


# ---- the events of a document ----------------------------------------------------


def classify(tree: Any) -> Dict[str, Optional[Dict[str, Any]]]:
    """``{id: node or None}`` for every id of ``tree``: the node when it is a basic
    event (a leaf that is not the root, not a house event, not a TRANSFER; the first
    node found for an id wins, as the Grid tab reads it), else None."""
    found: Dict[str, Optional[Dict[str, Any]]] = {}
    if not isinstance(tree, dict) or not tree:
        return found
    stack = [tree]
    while stack:
        node = stack.pop()
        key = str(node.get("id"))
        children = node.get("children") or []
        if key not in found:
            basic = (
                node is not tree
                and not children
                and str(node.get("eventKind") or "").lower() != "house"
                and str(node.get("gateType") or "").upper() != "TRANSFER"
            )
            found[key] = node if basic else None
        stack.extend(reversed(children))
    return found


def check_ids(tree: Any, ids: Sequence[str]) -> None:
    """400 ``INVALID_FIELD`` for the first id that is not a basic event of ``tree``."""
    kinds = classify(tree)
    for node_id in ids:
        if node_id not in kinds:
            raise ApiError(
                INVALID_FIELD,
                "Event '%s' is not in the tree." % node_id,
                400,
                {"field": "factors", "id": node_id, "reason": "unknown_event"},
            )
        if kinds[node_id] is None:
            raise ApiError(
                INVALID_FIELD,
                "'%s' is not a basic event." % node_id,
                400,
                {"field": "factors", "id": node_id, "reason": "not_basic_event"},
            )


class EventInfo:
    """What the scaling of one basic event needs, taken from ``derive_quant``."""

    __slots__ = ("id", "name", "model", "param_key", "nominal_param", "nominal_q", "fn",
                 "tau", "missing")

    def __init__(self, node: Dict[str, Any], analysis: Dict[str, Any]) -> None:
        derived = engine.derive_quant(node, analysis)
        self.id = str(node.get("id"))
        self.name = str(node.get("name", "") or "")
        self.model = derived["model"]
        self.param_key = "q" if self.model == "fixed" else "lambda"
        self.nominal_q = derived["q"]
        nominal, self.fn = uncertainty._q_function(derived)
        self.nominal_param = nominal
        self.tau = (derived.get("params") or {}).get("tau")
        missing: List[str] = []
        for warning in derived.get("warnings") or []:
            if warning.get("code") == "QUANT_PARAM_MISSING":
                for name in (warning.get("params") or {}).get("missing") or []:
                    if name not in missing:
                        missing.append(name)
        self.missing = missing

    @property
    def evaluable(self) -> bool:
        return self.nominal_q is not None and self.nominal_param is not None


# ---- the baseline and its cache ----------------------------------------------------


class Baseline:
    """Everything a request needs, computed once per document version."""

    __slots__ = ("key", "tree", "analysis", "data", "core_analysis", "summary", "cut_sets",
                 "probs", "event_q", "inverted", "events", "plan", "unapplied", "built_ms")

    def __init__(self) -> None:
        self.key: Tuple[Any, ...] = ()
        self.tree: Any = None             # deep copies taken under the lock, for the guard
        self.analysis: Any = None
        self.data: Any = None             # the recalculated tree (tree-walk method)
        self.core_analysis: Any = None    # the coerced analysis of that core
        self.summary: Dict[str, Any] = {}
        self.cut_sets: List[Tuple[str, ...]] = []           # event ids per set, rank order
        self.probs: List[float] = []      # baseline probability per set, same order
        self.event_q: Dict[str, float] = {}
        self.inverted: Dict[str, List[int]] = {}
        self.events: Dict[str, EventInfo] = {}
        self.plan: Any = None
        # (group id, members) of every stored group that is not applied; filled by build() only
        self.unapplied: List[Tuple[Optional[str], Tuple[str, ...]]] = []
        self.built_ms: float = 0.0


_lock = threading.Lock()          # guards _cache and CACHE_STATS
_build_lock = threading.Lock()    # one baseline build at a time (single flight)
_cache: Optional[Baseline] = None
CACHE_STATS: Dict[str, int] = {"hits": 0, "misses": 0}


def cache_info() -> Dict[str, Any]:
    with _lock:
        entry = _cache
        return {
            "hits": CACHE_STATS["hits"],
            "misses": CACHE_STATS["misses"],
            "size": 0 if entry is None else 1,
            "key": None if entry is None else list(entry.key),
        }


def clear_cache() -> None:
    """Empty the entry and the counters (tests only)."""
    global _cache
    with _lock:
        _cache = None
        CACHE_STATS["hits"] = 0
        CACHE_STATS["misses"] = 0


def _matches(entry: Optional[Baseline], key: Tuple[Any, ...], tree: Any, analysis: Any) -> bool:
    return (
        entry is not None
        and entry.key == key
        and entry.tree == tree
        and entry.analysis == analysis
    )


def lookup(key: Tuple[Any, ...], tree: Any, analysis: Any) -> Optional[Baseline]:
    """The cached baseline when it is for this version AND this very tree and analysis
    (the live ones; nothing is copied), else None. Counts a hit. The caller holds the
    document lock, so ``tree`` cannot change while it is compared."""
    with _lock:
        entry = _cache
        if _matches(entry, key, tree, analysis):
            CACHE_STATS["hits"] += 1
            return entry
    return None


def obtain(key: Tuple[Any, ...], tree: Any, analysis: Any) -> Tuple[Baseline, bool]:
    """``(baseline, hit)`` after a miss in :func:`lookup`. ``tree`` and ``analysis`` are
    the caller's private deep copies of the live ones (kept in the entry for the guard,
    never changed). One build at a time: a request that waited for another build of the
    same version takes that entry (a hit). Counts one hit or one miss."""
    global _cache
    with _build_lock:
        with _lock:
            entry = _cache
            if _matches(entry, key, tree, analysis):
                CACHE_STATS["hits"] += 1
                return entry, True
        built = build(tree, analysis, key)
        with _lock:
            CACHE_STATS["misses"] += 1
            if "time" in (built.summary.get("truncatedBy") or []):
                _cache = None          # a baseline cut short by time is not kept
            else:
                _cache = built
    return built, False


def build(tree: Any, analysis: Any, key: Tuple[Any, ...]) -> Baseline:
    """The baseline of ``tree`` / ``analysis`` (private copies; they are not changed)."""
    entry = Baseline()
    entry.key = key
    entry.tree = tree
    entry.analysis = analysis
    summary, result = engine.summary_with_cut_sets(tree, analysis)
    entry.summary = summary
    entry.built_ms = float(summary.get("elapsedMs") or 0.0)

    core = logic.recalculated_core(tree, analysis)
    entry.data = core.get_data()
    entry.core_analysis = core.analysis
    if isinstance(analysis, dict) and ccf.groups_of(analysis):
        built = ccf.build_plan(
            ccf.groups_of(analysis), analysis.get(ccf.RENAMED_KEY), entry.data, core.analysis)
        if built is not None:
            # groups that are not applied at baseline (any reason): CCF_NOT_APPLIED reads them
            entry.unapplied = [(a.id, tuple(a.members)) for a in built.assessments if not a.applied]
            # the plan itself is kept only when a group is applied, as before
            if ccf.any_applied(tree, analysis, "FTA"):
                entry.plan = built

    for node_id, node in classify(entry.data).items():
        if node is not None:
            entry.events[node_id] = EventInfo(node, core.analysis)

    if summary.get("headlineMethod") == "mcub" and result is not None:
        for index, cut in enumerate(result["cutSets"]):
            ids = tuple(event["id"] for event in cut["events"])
            entry.cut_sets.append(ids)
            entry.probs.append(cut["probability"])
            for event in cut["events"]:
                entry.event_q[event["id"]] = event["q"]
            for node_id in ids:
                entry.inverted.setdefault(node_id, []).append(index)
    return entry


# ---- scaling (DESIGN 4.1) --------------------------------------------------------------


def _not_evaluable(info: EventInfo) -> ApiError:
    shown = ", ".join(info.missing) if info.missing else "a parameter"
    return ApiError(
        WHATIF_NOT_EVALUABLE,
        "Event '%s' cannot be evaluated (%s is missing or invalid), so a factor cannot be applied."
        % (info.id, shown),
        422,
        {"id": info.id, "missing": list(info.missing)},
    )


def scale(info: EventInfo, factor: float) -> Tuple[float, float, float, float, bool]:
    """``(nominalParam, param, nominalQ, q, clamped)`` of ``info`` with ``factor`` on its
    main parameter. Only the main parameter moves (T, tau and mu never do); q is the
    model's value of it, set to 1 when above 1 (``clamped`` only for a strict excess)."""
    if not info.evaluable:
        raise _not_evaluable(info)
    nominal = float(info.nominal_param)
    if factor == 1:
        # a standby event can be capped at 1 already at its nominal value
        capped = info.model == "standby" and nominal * float(info.tau) / 2.0 > 1.0
        return nominal, nominal, float(info.nominal_q), float(info.nominal_q), capped
    x = factor * nominal
    if info.model == "fixed":
        raw = x
    elif info.model == "standby":
        raw = x * float(info.tau) / 2.0     # _q_function's min(1, .) would hide the excess
    else:
        raw = info.fn(x)
    # A finite parameter whose raw q overflows is simply above 1 (clamped); only a
    # non-finite parameter or a NaN cannot be shown (and is not JSON).
    if not math.isfinite(x) or math.isnan(raw):
        raise _not_evaluable(info)
    return nominal, x, float(info.nominal_q), min(1.0, raw), raw > 1.0


def engine_q(info: EventInfo, q: float) -> float:
    """The q the engine's cut sets, tree walk and CCF plan use for this event: the
    model's q rounded to 12 significant digits (``engine._tidy``, as
    ``_apply_quant_models`` stores it) for every model but ``fixed``. The rows show the
    raw q; the top event is computed from this one, so it equals the headline of the
    same document with the scaled parameter typed in."""
    return q if info.model == "fixed" else engine._tidy(q)


# ---- the request ----------------------------------------------------------------------------


def _group_conflicts(plan: Any, factors: Sequence[Tuple[str, float]]) -> Dict[str, float]:
    """``{groupId: group factor}`` for the applied groups the request touches with a
    factor other than 1; 400 ``group_conflict`` when two members differ."""
    by_member = plan.by_member if plan is not None else {}
    asked: Dict[str, List[Tuple[str, float]]] = {}
    for node_id, factor in factors:
        hit = by_member.get(node_id)
        if hit is not None and factor != 1:
            asked.setdefault(hit[0].id, []).append((node_id, factor))
    out: Dict[str, float] = {}
    for group_id, entries in asked.items():
        if len({factor for _id, factor in entries}) > 1:
            raise ApiError(
                INVALID_FIELD,
                "Members of the group '%s' have different factors; a group takes one."
                % group_id,
                400,
                {"field": "factors", "reason": "group_conflict", "groupId": group_id,
                 "ids": [node_id for node_id, _factor in entries]},
            )
        out[group_id] = entries[0][1]
    return out


def _ratio(baseline: Optional[float], what_if: Optional[float]) -> Optional[float]:
    if baseline is None or what_if is None:
        return None
    if baseline > 0:
        try:
            ratio = what_if / baseline
        except OverflowError:
            return None
        return ratio if math.isfinite(ratio) else None
    if baseline == 0:
        return 1.0 if what_if == 0 else None
    return None


def _tree_walk(entry: Baseline, changed: Dict[str, float]) -> Optional[float]:
    """The tree walk of a copy of the tree with these events typed in as fixed q."""
    data = copy.deepcopy(entry.data)
    stack = [data]
    while stack:
        node = stack.pop()
        children = node.get("children") or []
        if not children and str(node.get("id")) in changed:
            node["quant"] = {"model": "fixed"}
            node["probability"] = changed[str(node.get("id"))]
        stack.extend(children)
    core = engine.WebCore()
    core.set_data(data)
    core.analysis = copy.deepcopy(entry.core_analysis)
    core.mode = "FTA"
    core.recalculate_probabilities()
    value = core.get_data().get("calculatedProbability")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _cautions(entry: Baseline, rows: Sequence[Dict[str, Any]],
              scaled: Dict[str, Tuple[float, float, float, float, bool]],
              group_qts: Dict[str, List[float]], method: Any,
              truncated_by: Sequence[str]) -> List[Dict[str, Any]]:
    """The cautions of the WHAT-IF values (CR-20261102, FR DESIGN 1.3): a list of
    machine-coded entries, in :data:`CAUTION_ORDER`, ``[]`` when no row has a factor
    other than 1. A pure function of its arguments: nothing is stored in the baseline."""
    if not any(row["factor"] != 1 for row in rows):
        return []
    plan = entry.plan
    found: Dict[str, Dict[str, Any]] = {}

    # a scaled member of a group that is not applied at baseline: the what-if scales it
    # alone, with no CCF event (any not-applied reason; ids in document order, once each)
    scaled_ids = {row["id"] for row in rows if row["factor"] != 1}
    not_applied: List[str] = []
    hit_unapplied = False
    for group_id, members in entry.unapplied:
        if scaled_ids.intersection(members):
            hit_unapplied = True
            if group_id is not None and group_id not in not_applied:
                not_applied.append(group_id)
    if hit_unapplied:
        found["CCF_NOT_APPLIED"] = {"code": "CCF_NOT_APPLIED", "groupIds": not_applied}

    # CCF groups the request scaled: the error (q >= 1) first, the warning for the others
    one: List[str] = []
    high: List[str] = []
    if plan is not None:
        for group in plan.groups:
            qts = group_qts.get(group.id)
            if not qts:
                continue
            # raw q of derive_quant, as ccf.assess reads it (a clamped member is 1.0 here)
            if any(q >= 1.0 for q in qts):                       # ccf.assess: item[2] >= 1.0
                one.append(group.id)
            elif max(qts) > ccf.HIGH_Q:                          # ccf.assess: high_q > HIGH_Q
                high.append(group.id)
    if one:
        found["CCF_Q_ONE"] = {"code": "CCF_Q_ONE", "groupIds": one}
    if high:
        found["CCF_HIGH_Q"] = {"code": "CCF_HIGH_Q", "groupIds": high, "limit": ccf.HIGH_Q}

    # scaled standby events: lambda' * tau (not lambda * tau / 2), as engine.derive_quant
    large: List[str] = []
    for row in rows:
        if row["factor"] == 1 or row["model"] != "standby" or row["id"] not in scaled:
            continue
        tau = entry.events[row["id"]].tau
        if tau is None:
            continue
        if scaled[row["id"]][1] * float(tau) > STANDBY_LT_LIMIT:
            large.append(row["id"])
    if large:
        found["STANDBY_LARGE_LT"] = {"code": "STANDBY_LARGE_LT", "eventIds": large, "limit": STANDBY_LT_LIMIT}

    # cut sets limited by order or count (or the headline's own cap); not for cutoff alone
    if method == "mcub":
        capped = bool(entry.summary.get("capped"))
        by = [x for x in ("order", "count") if x in truncated_by or (x == "count" and capped)]
        if by:
            found["CUTSETS_TRUNCATED"] = {"code": "CUTSETS_TRUNCATED", "by": by}
    # the list follows CAUTION_ORDER, read here at call time
    return [found[code] for code in CAUTION_ORDER if code in found]


def evaluate(entry: Baseline, factors: Sequence[Tuple[str, float]], hit: bool) -> Dict[str, Any]:
    """The response of ``POST /api/whatif`` (DESIGN 3.2, without ``ok``, ``revision`` and
    ``documentSerial``) for these ``(id, factor)`` pairs, whose ids are basic events.

    Raises 400 ``group_conflict`` or 422 ``WHATIF_NOT_EVALUABLE``. Reads ``entry`` only.
    """
    plan = entry.plan
    by_member = plan.by_member if plan is not None else {}
    group_factor = _group_conflicts(plan, factors)

    # the rows: one per requested id, then the other members of a scaled group
    requested = [node_id for node_id, _factor in factors]
    asked = dict(factors)
    order: List[Tuple[str, bool]] = [(node_id, False) for node_id in requested]
    seen = set(requested)
    for node_id in requested:
        member = by_member.get(node_id)
        if member is None:
            continue
        group = member[0]
        if group.id in group_factor and ("group", group.id) not in seen:
            seen.add(("group", group.id))
            for other in group.members:
                if other not in seen:
                    seen.add(other)
                    order.append((other, True))

    def effective(node_id: str) -> float:
        member = by_member.get(node_id)
        if member is not None:
            return group_factor.get(member[0].id, 1.0)
        return asked[node_id]

    scaled: Dict[str, Tuple[float, float, float, float, bool]] = {}
    rows: List[Dict[str, Any]] = []
    for node_id, via_group in order:
        info = entry.events[node_id]
        factor = effective(node_id)
        member = by_member.get(node_id)
        row: Dict[str, Any] = {
            "id": node_id,
            "name": info.name,
            "model": info.model,
            "paramKey": info.param_key,
            "factor": factor,
            "groupId": member[0].id if member is not None else None,
            "viaGroup": via_group,
        }
        if not info.evaluable and factor == 1:
            row.update({"nominalParam": None, "param": None, "nominalQ": None, "q": None,
                        "clamped": False, "evaluable": False})
        else:
            values = scale(info, factor)
            scaled[node_id] = values
            row.update({"nominalParam": values[0], "param": values[1], "nominalQ": values[2],
                        "q": values[3], "clamped": values[4], "evaluable": True})
        rows.append(row)

    # the probabilities that differ from the baseline's
    changed: Dict[str, float] = {}      # event id -> new q (ordinary events)
    new_q: Dict[str, float] = {}        # cut-set event id -> new q (incl. CCF parts)
    for node_id, values in scaled.items():
        if node_id in by_member:
            continue
        info = entry.events[node_id]
        q_new, q_old = engine_q(info, values[3]), engine_q(info, values[2])
        if q_new != q_old:
            changed[node_id] = q_new
            new_q[node_id] = q_new
    group_qts: Dict[str, List[float]] = {}   # group id -> member Q_t of the scaled groups
    if plan is not None:
        for group in plan.groups:
            if group.id not in group_factor:
                continue
            qts = [engine_q(entry.events[m], scaled[m][3]) for m in group.members]
            # the cautions mirror ccf.assess, which reads the raw q of derive_quant (not the 12-digit one)
            group_qts[group.id] = [scaled[m][3] for m in group.members]
            if all(q == engine_q(entry.events[m], scaled[m][2])
                   for q, m in zip(qts, group.members)):
                continue
            expansion = ccf.event_probabilities(group.model, group.params, qts)
            for position, member in enumerate(group.members):
                new_q[member] = expansion.independent[position]
            for indexes, q in expansion.events:
                new_q[ccf.event_id(group.id, group.model, group.members, indexes)] = q

    summary = entry.summary
    method = summary.get("headlineMethod")
    truncated_by = list(summary.get("truncatedBy") or [])
    baseline = summary.get("headline")
    what_if: Optional[float]
    if method == "incomplete":
        baseline, what_if = None, None
    elif method == "mcub":
        affected = set()
        for node_id in new_q:
            affected.update(entry.inverted.get(node_id, ()))
        if not affected:
            what_if = baseline
        else:
            probs = list(entry.probs)
            for index in affected:
                p = 1.0
                for node_id in entry.cut_sets[index]:
                    p *= new_q[node_id] if node_id in new_q else entry.event_q[node_id]
                probs[index] = p
            what_if = cutsets.mcub_of(probs)
    else:
        what_if = _tree_walk(entry, changed) if changed else baseline

    if method == "incomplete":
        note: Optional[str] = NOTE_INCOMPLETE
    elif method == "mcub" and "cutoff" in truncated_by:
        note = NOTE_CUTSETS_FROM_NOMINAL
    else:
        note = None

    groups = [] if plan is None else [
        {"id": g.id, "name": g.name, "model": g.model, "members": list(g.members)}
        for g in plan.groups
    ]
    return {
        "baseline": baseline,
        "whatIf": what_if,
        "ratio": _ratio(baseline, what_if),
        "method": method,
        "note": note,
        "truncatedBy": truncated_by,
        "cache": "hit" if hit else "miss",
        "baselineMs": 0.0 if hit else entry.built_ms,
        "groups": groups,
        "events": rows,
        "cautions": _cautions(entry, rows, scaled, group_qts, method, truncated_by),
    }
