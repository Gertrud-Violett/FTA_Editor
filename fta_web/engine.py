"""
The 1.7 probability engine: ``WebCore``, an ``FTACore`` that knows the new
gate kinds, event kinds and rate models, and keeps the document's ``analysis``
settings block.

Why a subclass and not an edit
------------------------------
``fta_web/core/`` is hash-pinned against ``BASELINE.json`` (and ``desktop/``
against its own copy); every behaviour 1.7 adds lives here instead. ``WebCore``
overrides exactly three things:

* ``_recalculate_fta_probabilities`` -- the core tree walk, reproduced
  **exactly** for a legacy tree (identity memo, ``visiting`` set, the
  ``gate_only`` cycle fallback, AND-links then OR-links, ``_tidy`` at the same
  points, ``calculatedProbability`` written on the way out), then extended by
  ``gateType``/``eventKind``/``quant``. ``test_engine.py`` proves the legacy
  equivalence on a few hundred random trees with links and cycles.
* ``load_from_json`` -- the core drops unknown *top-level* keys, so the file is
  re-read to recover the ``analysis`` block.
* ``prepare_export_data`` -- adds ``analysis`` beside ``tree``.

Unknown *node* keys already survive the core untouched (``_normalize_node``
edits only the keys it knows), so the new node keys need no loader work.

Semantics added (see node_schema for the key vocabulary)
--------------------------------------------------------
Quant models run first and write the node's ``probability`` (so the desktop
app, which only reads ``probability``, still sees a meaningful number):

* ``fixed``       q as entered (no-op)
* ``rate``        1 - exp(-λT), T defaulting to ``analysis.missionTime``
* ``standby``     min(1, λτ/2); warning ``STANDBY_LARGE_LT`` when λτ > 0.2
* ``repairable``  λ/(λ+μ), μ = ``mu`` or 1/``mttr``

A model whose parameters are missing or invalid keeps the previous
``probability`` and records ``QUANT_PARAM_MISSING``.

Gate types (``gateType`` wins over ``logicGate`` when both are present):
KOFN -- P(at least k of n) by Poisson-binomial DP; XOR -- a+b-2ab (parity for
n != 2, flagged); INHIBIT -- AND over the input and its conditioning child;
PAND -- Πp/n!, always flagged as an approximation; TRANSFER -- the value of
the ``transferTo`` node, through the shared memo (missing target -> 0 and a
warning). A leaf with ``eventKind: house`` is 1 or 0 by ``houseState``.

Warnings land in ``self.quant_warnings`` as ``{code, nodeId, params}``.
"""
from __future__ import annotations

import copy
import json
import math
from typing import Any, Dict, List, Optional, Tuple

try:  # normal package import: ``import fta_web.engine``
    from . import config  # noqa: F401  (puts fta_web/core on sys.path)
    from .node_schema import project_logic_gate  # noqa: F401  (re-exported)
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import config  # type: ignore[no-redef]  # noqa: F401
    from node_schema import project_logic_gate  # type: ignore[no-redef]  # noqa: F401

from FTA_Editor_core import FTACore, _tidy  # noqa: E402


# ---- analysis settings -----------------------------------------------------------

#: AIAG PFMEA (4th ed.) occurrence ranks -> per-item failure probability. The
#: AIAG table gives "failures per 1000 items"; each rank is mapped to the lower
#: edge of its band divided by 1000 (10: >=100/1000, 9: 50/1000, 8: 20/1000,
#: 7: 10/1000, 6: 2/1000, 5: 0.5/1000, 4: 0.1/1000, 3: 0.01/1000,
#: 2: <=0.001/1000). Rank 1 ("failure eliminated through prevention") has no
#: band; 1e-7 is a nominal value. Editable per document (it is saved in the
#: ``analysis`` block) because organisations calibrate their own table.
AIAG_OCCURRENCE_TABLE = {
    "1": 1e-7,
    "2": 1e-6,
    "3": 1e-5,
    "4": 1e-4,
    "5": 5e-4,
    "6": 2e-3,
    "7": 1e-2,
    "8": 2e-2,
    "9": 5e-2,
    "10": 1e-1,
}

TIME_UNITS = ("h", "d", "y")

DEFAULT_ANALYSIS: Dict[str, Any] = {
    "missionTime": 8760.0,  # hours; one year
    "timeUnit": "h",        # display unit only -- stored times are hours
    "cutsets": {"maxOrder": 6, "maxCount": 5000, "cutoff": 1e-15},
    "mc": {"n": 10000, "seed": None},
    "fmeaOccurrenceTable": AIAG_OCCURRENCE_TABLE,
}

MAX_MC_N = 1_000_000
MAX_CUTSET_ORDER = 20
MAX_CUTSET_COUNT = 1_000_000


def default_analysis() -> Dict[str, Any]:
    """A fresh, independent copy of the default ``analysis`` block."""
    return copy.deepcopy(DEFAULT_ANALYSIS)


class AnalysisError(ValueError):
    """An ``analysis`` value failed validation. ``field`` is the dotted key."""

    def __init__(self, field: str, message: str, value: Any = None):
        super().__init__(message)
        self.field = field
        self.value = value


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalysisError(field, "'%s' must be a number." % field, value)
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        raise AnalysisError(field, "'%s' must be a finite number." % field, value)
    return number


def _integer(value: Any, field: str, lo: int, hi: int) -> int:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise AnalysisError(
            field, "'%s' must be an integer between %d and %d." % (field, lo, hi), value
        )
    return value


def _validate_analysis_value(path: Tuple[str, ...], value: Any) -> Any:
    """Validate one leaf (or the occurrence table) of an ``analysis`` patch."""
    field = ".".join(path)
    if path == ("missionTime",):
        number = _finite(value, field)
        if number <= 0:
            raise AnalysisError(field, "'missionTime' must be greater than 0.", value)
        return number
    if path == ("timeUnit",):
        if value not in TIME_UNITS:
            raise AnalysisError(
                field, "'timeUnit' must be one of %s." % ", ".join(TIME_UNITS), value
            )
        return value
    if path == ("cutsets", "maxOrder"):
        return _integer(value, field, 1, MAX_CUTSET_ORDER)
    if path == ("cutsets", "maxCount"):
        return _integer(value, field, 1, MAX_CUTSET_COUNT)
    if path == ("cutsets", "cutoff"):
        number = _finite(value, field)
        if not 0.0 <= number < 1.0:
            raise AnalysisError(field, "'cutsets.cutoff' must be in [0, 1).", value)
        return number
    if path == ("mc", "n"):
        return _integer(value, field, 1, MAX_MC_N)
    if path == ("mc", "seed"):
        return _integer(value, field, 0, 2**63 - 1)
    if len(path) == 2 and path[0] == "fmeaOccurrenceTable":
        if path[1] not in AIAG_OCCURRENCE_TABLE:
            raise AnalysisError(
                field, "Occurrence ranks are '1'..'10'; got '%s'." % path[1], value
            )
        number = _finite(value, field)
        if not 0.0 <= number <= 1.0:
            raise AnalysisError(field, "An occurrence probability must be in [0, 1].", value)
        return number
    raise AnalysisError(field, "Unsupported analysis setting '%s'." % field, value)


def merge_analysis(current: Dict[str, Any], partial: Any,
                   _path: Tuple[str, ...] = ()) -> Dict[str, Any]:
    """Validate ``partial`` and deep-merge it onto a copy of ``current``.

    ``None`` for any key resets it to its default. Raises
    :class:`AnalysisError` on the first bad value; ``current`` is never
    modified, so a failed merge changes nothing.
    """
    field = ".".join(_path) or "analysis"
    if not isinstance(partial, dict):
        raise AnalysisError(field, "'%s' must be an object." % field, partial)
    result = copy.deepcopy(current) if isinstance(current, dict) else {}
    defaults: Any = DEFAULT_ANALYSIS
    for part in _path:
        defaults = defaults.get(part, {}) if isinstance(defaults, dict) else {}
    for key, value in partial.items():
        key = str(key)
        path = _path + (key,)
        default_value = defaults.get(key) if isinstance(defaults, dict) else None
        known_branch = isinstance(default_value, dict)
        if value is None:
            if key not in (defaults or {}) and not (
                len(path) == 2 and path[0] == "fmeaOccurrenceTable"
            ):
                raise AnalysisError(".".join(path), "Unsupported analysis setting '%s'." % ".".join(path))
            if path == ("mc", "seed"):
                result[key] = None
            elif default_value is not None:
                result[key] = copy.deepcopy(default_value)
            else:
                result.pop(key, None)
        elif known_branch:
            result[key] = merge_analysis(result.get(key, default_value), value, path)
        else:
            result[key] = _validate_analysis_value(path, value)
    return result


def coerce_analysis(raw: Any) -> Tuple[Dict[str, Any], List[str]]:
    """The defaults with every *valid* value from ``raw`` applied.

    For loading a file: an invalid or unknown setting is dropped (and named in
    the returned list) instead of refusing the whole document.
    """
    result = default_analysis()
    problems: List[str] = []
    if raw is None:
        return result, problems
    if not isinstance(raw, dict):
        return result, ["analysis"]

    def walk(node: Dict[str, Any], path: Tuple[str, ...]) -> None:
        nonlocal result
        for key, value in node.items():
            sub = path + (str(key),)
            if isinstance(value, dict):
                walk(value, sub)
                continue
            patch: Dict[str, Any] = {}
            cursor = patch
            for part in sub[:-1]:
                cursor = cursor.setdefault(part, {})
            cursor[sub[-1]] = value
            try:
                result = merge_analysis(result, patch)
            except AnalysisError:
                problems.append(".".join(sub))

    walk(raw, ())
    return result, problems


# ---- quantification models ------------------------------------------------------------


_FORMULAS = {
    "fixed": "q",
    "rate": "1 - exp(-λT)",
    "standby": "min(1, λτ/2)",
    "repairable": "λ/(λ+μ)",
}


def _param(quant: Dict[str, Any], key: str) -> Optional[float]:
    value = quant.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if math.isnan(value) or math.isinf(value) or value < 0:
        return None
    return value


def derive_quant(node: Dict[str, Any], analysis: Optional[Dict[str, Any]] = None
                 ) -> Dict[str, Any]:
    """What ``node``'s quant model yields: ``{model, q, formula, formulaKey,
    params, warnings}``.

    ``q`` is None when the model cannot be evaluated (the node then keeps its
    previous probability). ``params`` holds the resolved inputs, including a
    ``T`` defaulted from the mission time (with ``TFromMission: true``).
    A node without ``quant`` is the ``fixed`` model on its ``probability``.
    """
    analysis = analysis or DEFAULT_ANALYSIS
    quant = node.get("quant")
    quant = quant if isinstance(quant, dict) else {}
    model = str(quant.get("model") or "fixed").lower()
    if model not in _FORMULAS:
        model = "fixed"
    node_id = str(node.get("id"))
    warnings: List[Dict[str, Any]] = []
    params: Dict[str, Any] = {}
    q: Optional[float] = None

    def missing(*names: str) -> None:
        warnings.append({
            "code": "QUANT_PARAM_MISSING",
            "nodeId": node_id,
            "params": {"model": model, "missing": list(names)},
        })

    lam = _param(quant, "lambda")
    if model == "fixed":
        try:
            q = float(node.get("probability", 0.0))
        except (TypeError, ValueError):
            q = None
        params = {"q": q}
    elif model == "rate":
        t = _param(quant, "T")
        from_mission = t is None
        if from_mission:
            t = _param(analysis, "missionTime")
        params = {"lambda": lam, "T": t, "TFromMission": from_mission}
        if lam is None or t is None:
            missing(*[n for n, v in (("lambda", lam), ("T", t)) if v is None])
        else:
            q = -math.expm1(-lam * t)
    elif model == "standby":
        tau = _param(quant, "tau")
        params = {"lambda": lam, "tau": tau}
        if lam is None or tau is None:
            missing(*[n for n, v in (("lambda", lam), ("tau", tau)) if v is None])
        else:
            lt = lam * tau
            q = min(1.0, lt / 2.0)
            params["lambdaTau"] = lt
            if lt > 0.2:
                warnings.append({
                    "code": "STANDBY_LARGE_LT",
                    "nodeId": node_id,
                    "params": {"lambdaTau": lt},
                })
    elif model == "repairable":
        mu = _param(quant, "mu")
        mttr = _param(quant, "mttr")
        if mu is None and mttr:
            mu = 1.0 / mttr
        params = {"lambda": lam, "mu": mu, "mttr": mttr}
        if lam is None or mu is None or (lam + mu) <= 0:
            missing(*[n for n, v in (("lambda", lam), ("mu", mu)) if v is None] or ["mu"])
        else:
            q = lam / (lam + mu)

    if q is not None and (math.isnan(q) or not 0.0 <= q <= 1.0):
        missing("q")
        q = None
    return {
        "model": model,
        "q": q,
        "formula": _FORMULAS[model],
        "formulaKey": "quant.formula." + model,
        "params": params,
        "warnings": warnings,
    }


# ---- gate helpers --------------------------------------------------------------------


def _product(nums) -> float:
    result = 1
    for n in nums:
        result *= n
    return result


def kofn_probability(probs: List[float], k: int) -> float:
    """P(at least ``k`` of the independent events in ``probs`` occur).

    Poisson-binomial DP: ``dist[j]`` is P(exactly j occurred so far).
    """
    n = len(probs)
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    dist = [1.0] + [0.0] * n
    for i, p in enumerate(probs, start=1):
        for j in range(i, 0, -1):
            dist[j] = dist[j] * (1.0 - p) + dist[j - 1] * p
        dist[0] *= (1.0 - p)
    return min(1.0, max(0.0, sum(dist[k:])))


def xor_probability(probs: List[float]) -> float:
    """Odd-parity probability; a+b-2ab for the two-input case."""
    result = 0.0
    for p in probs:
        result = result + p - 2.0 * result * p
    return result


# ---- the core subclass ---------------------------------------------------------------


class WebCore(FTACore):
    """``FTACore`` plus the 1.7 node semantics and the ``analysis`` block."""

    def __init__(self) -> None:
        self.analysis: Dict[str, Any] = default_analysis()
        self.quant_warnings: List[Dict[str, Any]] = []
        super().__init__()

    # ---- analysis ------------------------------------------------------------

    def get_analysis(self) -> Dict[str, Any]:
        return copy.deepcopy(self.analysis)

    def set_analysis(self, partial: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and deep-merge ``partial``. Raises AnalysisError; atomic."""
        self.analysis = merge_analysis(self.analysis, partial)
        return self.get_analysis()

    # ---- file I/O ------------------------------------------------------------

    def load_from_json(self, file_path):
        self.analysis = default_analysis()
        ok, error = super().load_from_json(file_path)
        if not ok:
            return ok, error
        raw = _read_document(file_path)
        if isinstance(raw, dict) and "tree" in raw and "analysis" in raw:
            self.analysis, problems = coerce_analysis(raw.get("analysis"))
            if problems:
                self.last_load_warnings.append({
                    "kind": "analysis_invalid",
                    "old_id": None,
                    "new_id": None,
                    "fields": problems,
                    "message": "Invalid analysis setting(s) were reset to their "
                               "defaults: %s." % ", ".join(problems),
                })
        self.recalculate_probabilities()
        return True, None

    def prepare_export_data(self):
        data = super().prepare_export_data()
        data["analysis"] = copy.deepcopy(self.analysis)
        return data

    # ---- probability ---------------------------------------------------------

    def _node_index(self) -> Dict[str, Dict[str, Any]]:
        """id -> first node with that id in pre-order: what
        ``find_node_by_id`` returns, without its O(n) walk per link."""
        index: Dict[str, Dict[str, Any]] = {}
        if isinstance(self.fta_data, dict):
            for node in self._walk(self.fta_data):
                index.setdefault(str(node.get("id")), node)
        return index

    def _apply_quant_models(self, index_nodes) -> None:
        for node in index_nodes:
            quant = node.get("quant")
            if not isinstance(quant, dict):
                continue
            derived = derive_quant(node, self.analysis)
            self.quant_warnings.extend(derived["warnings"])
            if derived["model"] != "fixed" and derived["q"] is not None:
                node["probability"] = _tidy(derived["q"])

    def _recalculate_fta_probabilities(self):
        """The core walk, extended. See the module docstring."""
        self.quant_warnings = []
        warnings = self.quant_warnings
        if not isinstance(self.fta_data, dict):
            return
        self._apply_quant_models(list(self._walk(self.fta_data)))
        index = self._node_index()

        memo: Dict[int, float] = {}
        visiting = set()
        gate_only: Dict[int, float] = {}

        def warn(code: str, node: Dict[str, Any], **params: Any) -> None:
            warnings.append({"code": code, "nodeId": str(node.get("id")), "params": params})

        def gate_type_of(node: Dict[str, Any]) -> Optional[str]:
            raw = node.get("gateType")
            if isinstance(raw, str) and raw.strip():
                return raw.strip().upper()
            return None

        def get_prob(node):
            key = id(node)
            if key in memo:
                return memo[key]
            if key in visiting:
                if key in gate_only:
                    return gate_only[key]
                if gate_type_of(node) == "TRANSFER":
                    return None
                if not (node.get("children") or []):
                    return float(node.get("probability", 1.0))
                return None

            visiting.add(key)
            children = node.get("children", []) or []
            gate_type = gate_type_of(node)

            if gate_type == "TRANSFER":
                for child in children:  # evaluated for display; ignored
                    get_prob(child)
                target_id = node.get("transferTo")
                target = index.get(str(target_id)) if target_id not in (None, "") else None
                if target is None or target is node:
                    warn("TRANSFER_MISSING", node, transferTo=target_id)
                    base = 0.0
                else:
                    value = get_prob(target)
                    if value is None:
                        warn("TRANSFER_CYCLE", node, transferTo=target_id)
                        base = 0.0
                    else:
                        base = value
            elif not children:
                if str(node.get("eventKind") or "").lower() == "house":
                    base = 1.0 if node.get("houseState") is True else 0.0
                else:
                    base = float(node.get("probability", 0.0))
            else:
                child_probs = [p for p in (get_prob(c) for c in children) if p is not None]
                if gate_type is None or gate_type not in (
                    "AND", "OR", "KOFN", "XOR", "INHIBIT", "PAND"
                ):
                    gate_value = node.get("logicGate", "OR")
                    gate = str(gate_value).strip().upper() if gate_value else "OR"
                else:
                    gate = gate_type

                if gate == "AND":
                    base = _tidy(self._product(child_probs))
                elif gate == "KOFN":
                    k = node.get("k")
                    if isinstance(k, float) and k.is_integer():
                        k = int(k)
                    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
                        warn("KOFN_ARITY", node, k=node.get("k"), n=len(child_probs))
                        k = 1
                    elif k > len(child_probs):
                        warn("KOFN_ARITY", node, k=k, n=len(child_probs))
                    base = _tidy(kofn_probability(child_probs, k))
                elif gate == "XOR":
                    if len(child_probs) != 2:
                        warn("XOR_ARITY", node, n=len(child_probs))
                    base = _tidy(xor_probability(child_probs))
                elif gate == "INHIBIT":
                    conditions = sum(
                        1 for c in children
                        if str(c.get("eventKind") or "").lower() == "conditioning"
                    )
                    if conditions != 1 or len(children) < 2:
                        warn("INHIBIT_ARITY", node, conditions=conditions, n=len(children))
                    base = _tidy(self._product(child_probs))
                elif gate == "PAND":
                    warn("PAND_APPROX", node, n=len(child_probs))
                    base = _tidy(
                        self._product(child_probs) / math.factorial(len(child_probs))
                    )
                else:
                    base = _tidy(1 - self._product([1 - p for p in child_probs]))
            gate_only[key] = base

            links = node.get("links", []) or []
            and_probs = []
            or_probs = []
            for l in links:
                tid = l.get("target_id")
                rel = (l.get("relation") or "OR").upper()
                if not tid:
                    continue
                target = index.get(str(tid))
                if not target:
                    continue
                tp = get_prob(target)
                if tp is None:
                    continue
                (and_probs if rel == "AND" else or_probs).append(tp)

            if and_probs:
                base = _tidy(base * self._product(and_probs))
            if or_probs:
                vals = [base] + or_probs
                base = _tidy(1 - self._product([1 - p for p in vals]))

            memo[key] = base
            visiting.remove(key)
            gate_only.pop(key, None)
            node["calculatedProbability"] = base
            return base

        get_prob(self.fta_data)

    def node_warnings(self, node_id: str) -> List[Dict[str, Any]]:
        """The last recalculation's warnings for one node."""
        return [w for w in self.quant_warnings if w.get("nodeId") == str(node_id)]


def _read_document(file_path) -> Any:
    """Re-read a JSON document the way ``FTACore.load_from_json`` does
    (same encodings, same double-wrap repair). None when unreadable."""
    for enc in ["utf-8-sig", "utf-8", "cp932", "shift_jis", "cp1252"]:
        try:
            with open(file_path, "r", encoding=enc) as f:
                content = f.read().strip()
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                repaired = content
                if repaired.startswith("{{"):
                    repaired = "{" + repaired[2:]
                if repaired.endswith("}}"):
                    repaired = repaired[:-1]
                return json.loads(repaired)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        except Exception:
            return None
    return None


# ---- summary (workstream A completes this) ------------------------------------------


#: Cheaper cut-set caps for the headline, which runs after every edit.
SUMMARY_LIMITS = {"maxCount": 2000, "timeBudgetS": 2.0}


def summary(tree: Dict[str, Any], analysis: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Headline figures for ``tree``.

    Works on a deep copy; ``tree`` is not modified. Shape frozen:
    ``{treeWalk, mcub, rareEvent, headline, headlineMethod, repeatedEvents,
    nonCoherent, approximations, truncated, elapsedMs}``.

    The headline is the min-cut upper bound when the tree has repeated events
    or an XOR gate (the tree walk then double-counts / is not a probability of
    a coherent structure), otherwise the tree walk. Cut sets run with the
    cheaper :data:`SUMMARY_LIMITS`; if they fail or time out the tree walk is
    the headline and ``truncated`` is True.
    """
    import time as _time

    started = _time.perf_counter()
    try:
        try:
            from . import cutsets as _cutsets
        except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
            import cutsets as _cutsets  # type: ignore[no-redef]
        result = _cutsets.compute(tree, analysis, dict(SUMMARY_LIMITS))
    except Exception:  # noqa: BLE001 -- the headline must never fail
        result = None
    if result is None:
        out = _summary_tree_walk(tree, analysis)
        out["truncated"] = True
    else:
        repeated = result["repeatedEvents"]
        non_coherent = result["nonCoherent"]
        method = "mcub" if (repeated or non_coherent) else "treeWalk"
        tree_walk = result["treeWalk"]
        out = {
            "treeWalk": tree_walk,
            "mcub": result["mcub"],
            "rareEvent": result["rareEvent"],
            "headline": result["mcub"] if method == "mcub" else tree_walk,
            "headlineMethod": method,
            "repeatedEvents": repeated,
            "nonCoherent": non_coherent,
            "approximations": result["approximations"],
            "truncated": result["truncated"],
        }
    out["elapsedMs"] = round((_time.perf_counter() - started) * 1000.0, 1)
    return out


def _summary_tree_walk(tree: Dict[str, Any], analysis: Optional[Dict[str, Any]]
                       ) -> Dict[str, Any]:
    """The summary from the tree walk alone (the cut sets were unavailable)."""
    core = WebCore()
    core.set_data(copy.deepcopy(tree) if isinstance(tree, dict) else {})
    core.analysis, _problems = coerce_analysis(analysis)
    core.mode = "FTA"
    core.recalculate_probabilities()
    data = core.get_data()
    tree_walk = data.get("calculatedProbability") if isinstance(data, dict) and data else None

    non_coherent = False
    if isinstance(data, dict) and data:
        non_coherent = any(
            str(n.get("gateType") or "").upper() == "XOR" for n in core._walk(data)
        )
    approximations = [
        {"code": w["code"], "nodeId": w["nodeId"], "params": w.get("params", {})}
        for w in core.quant_warnings
        if w["code"] in ("PAND_APPROX", "XOR_ARITY", "STANDBY_LARGE_LT")
    ]
    return {
        "treeWalk": tree_walk,
        "mcub": None,
        "rareEvent": None,
        "headline": tree_walk,
        "headlineMethod": "treeWalk",
        "repeatedEvents": [],
        "nonCoherent": non_coherent,
        "approximations": approximations,
        "truncated": False,
    }
