"""
Monte Carlo uncertainty propagation (workstream A).

:func:`run` samples each event's *main parameter* from a lognormal given by
``quant.unc`` and pushes the samples through the model:

==============  ================  ==========================================
model           main parameter    q from a sample x
==============  ================  ==========================================
fixed           q                 x
rate            λ                 1 - exp(-xT)
standby         λ                 min(1, xτ/2)
repairable      λ                 x / (x + μ)
==============  ================  ==========================================

``unc = {dist: "lognormal", median | mean, ef}``: σ = ln(EF)/1.645 (EF is the
p95/median ratio); a mean is converted to the median as mean·e^(−σ²/2); with
neither, the nominal parameter is the median. Every q is clamped to [0, 1].

Two evaluation methods, chosen automatically:

``tree``      the compiled formula graph evaluated with the engine's gate
              formulas (KOFN DP, XOR parity, PAND Πp/n!, links) -- exact when
              the tree is coherent and has no repeated events, and it is then
              the tree walk sample for sample.
``cutsets``   otherwise: the most probable minimal cut sets covering 99.99 %
              of the rare-event sum (at most 2000), each compiled to a
              constant factor (events without uncertainty) and a tuple of
              sampled events, combined per sample by the min-cut upper bound.

Pure Python. Samples are processed column-wise in fixed chunks (a list
comprehension per operator per chunk), which is several times faster than a
per-sample interpreter loop and keeps the result deterministic for a seed
whatever the time limit cut off: a chunk is either complete or not counted.
"""
from __future__ import annotations

import math
import random
import time
from typing import Any, Dict, List, Optional

try:  # normal package import: ``import fta_web.uncertainty``
    from . import cutsets as cutsets_mod
    from . import engine, logic
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import cutsets as cutsets_mod  # type: ignore[no-redef]
    import engine  # type: ignore[no-redef]
    import logic  # type: ignore[no-redef]

Z95 = 1.645
CHUNK = 500
MAX_CUTSETS = 2000
COVERAGE = 0.9999
DEFAULT_N = 10000
DEFAULT_TIME_LIMIT = 30.0
#: Largest log of a sampled parameter (exp(700) ~ 1e304, below the float max).
_MAX_LOG = 700.0


# ---- parameters ----------------------------------------------------------------------


def lognormal_params(unc: Any, nominal: Optional[float]) -> Optional[Dict[str, float]]:
    """``{median, sigma}`` for a ``quant.unc`` object, or None when there is
    no usable lognormal."""
    if not isinstance(unc, dict) or str(unc.get("dist") or "").lower() != "lognormal":
        return None
    ef = unc.get("ef")
    if isinstance(ef, bool) or not isinstance(ef, (int, float)) or not ef >= 1.0:
        return None
    sigma = math.log(float(ef)) / Z95
    median = unc.get("median")
    mean = unc.get("mean")
    if isinstance(median, (int, float)) and not isinstance(median, bool) and median > 0:
        m = float(median)
    elif isinstance(mean, (int, float)) and not isinstance(mean, bool) and mean > 0:
        m = float(mean) * math.exp(-sigma * sigma / 2.0)
    elif nominal is not None and nominal > 0:
        m = float(nominal)
    else:
        return None
    return {"median": m, "sigma": sigma}


def _q_function(derived: Dict[str, Any]):
    """(main-parameter nominal value, x -> q) for an event's model."""
    model = derived.get("model")
    params = derived.get("params") or {}
    if model == "rate":
        t = params.get("T")
        return params.get("lambda"), (lambda x, t=t: -math.expm1(-x * t))
    if model == "standby":
        tau = params.get("tau")
        return params.get("lambda"), (lambda x, tau=tau: min(1.0, x * tau / 2.0))
    if model == "repairable":
        mu = params.get("mu")
        return params.get("lambda"), (lambda x, mu=mu: x / (x + mu) if (x + mu) > 0 else 0.0)
    return params.get("q"), (lambda x: x)


def _clamp(v: float) -> float:
    if v != v or v < 0.0:
        return 0.0
    return 1.0 if v > 1.0 else v


# ---- evaluators ----------------------------------------------------------------------


def _col_and(cols):
    result = cols[0]
    for c in cols[1:]:
        result = [a * b for a, b in zip(result, c)]
    return result


def _col_or(cols):
    acc = [1.0 - v for v in cols[0]]
    for c in cols[1:]:
        acc = [a * (1.0 - b) for a, b in zip(acc, c)]
    return [1.0 - a for a in acc]


def _tree_chunk(structure, plan, event_cols, m):
    """Evaluate the reachable ops on ``m`` samples; returns the top column."""
    vals: Dict[int, List[float]] = {}
    for i, op in plan:
        kind = op[0]
        if kind == "var":
            vals[i] = event_cols[op[1]]
        elif kind == "const":
            vals[i] = [1.0 if op[1] else 0.0] * m
        elif kind == "and":
            vals[i] = _col_and([vals[r] for r in op[1]]) if op[1] else [1.0] * m
        elif kind == "or":
            vals[i] = _col_or([vals[r] for r in op[1]]) if op[1] else [0.0] * m
        elif kind == "pand":
            if op[1]:
                n_in = len(op[1])
                vals[i] = [engine.pand_divide(v, n_in)
                           for v in _col_and([vals[r] for r in op[1]])]
            else:
                vals[i] = [1.0] * m
        elif kind == "kofn":
            cols = [vals[r] for r in op[2]]
            k = op[1]
            vals[i] = [engine.kofn_probability(list(ps), k) for ps in zip(*cols)] \
                if cols else [0.0 if k > 0 else 1.0] * m
        elif kind == "xor":
            cols = [vals[r] for r in op[1]]
            vals[i] = [engine.xor_probability(list(ps)) for ps in zip(*cols)] \
                if cols else [0.0] * m
    return vals[structure.top]


def _mcub_chunk(compiled, event_cols, m):
    acc = [0.0] * m
    ones = [False] * m
    for const, vars_ in compiled:
        if vars_:
            col = [const] * m if const != 1.0 else None
            for v in vars_:
                col = list(event_cols[v]) if col is None else [a * b for a, b in zip(col, event_cols[v])]
        else:
            col = [const] * m
        for s, p in enumerate(col):
            if p >= 1.0:
                ones[s] = True
            elif p > 0.0:
                acc[s] += math.log1p(-p)
    return [1.0 if one else -math.expm1(a) for a, one in zip(acc, ones)]


# ---- statistics ----------------------------------------------------------------------


def _quantile(sorted_vals: List[float], p: float) -> float:
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    pos = p * (n - 1)
    lo = int(math.floor(pos))
    hi = min(n - 1, lo + 1)
    frac = pos - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def histogram(values: List[float], bins: int = 40) -> Dict[str, Any]:
    """``{edges, counts, logBins}``; log-spaced when the (positive) range
    spans more than two decades."""
    if not values:
        return {"edges": [], "counts": [], "logBins": False}
    lo, hi = min(values), max(values)
    bins = max(1, int(bins))
    if hi <= lo:
        return {"edges": [lo, hi], "counts": [len(values)], "logBins": False}
    log_bins = lo > 0 and hi / lo > 100.0
    if log_bins:
        a, b = math.log10(lo), math.log10(hi)
        edges = [10 ** (a + (b - a) * k / bins) for k in range(bins + 1)]
        edges[0], edges[-1] = lo, hi
        width = (b - a) / bins
        counts = [0] * bins
        for v in values:
            k = int((math.log10(v) - a) / width) if v > lo else 0
            counts[min(bins - 1, max(0, k))] += 1
    else:
        width = (hi - lo) / bins
        edges = [lo + width * k for k in range(bins + 1)]
        edges[-1] = hi
        counts = [0] * bins
        for v in values:
            k = int((v - lo) / width)
            counts[min(bins - 1, max(0, k))] += 1
    return {"edges": edges, "counts": counts, "logBins": log_bins}


# ---- the run ---------------------------------------------------------------------------


def run(tree: Dict[str, Any], analysis: Optional[Dict[str, Any]] = None,
        n: Optional[int] = None, seed: Optional[int] = None,
        time_limit: float = DEFAULT_TIME_LIMIT, bins: int = 40) -> Dict[str, Any]:
    """Monte Carlo on ``tree`` (not modified). See the module docstring.

    ``n`` defaults to ``analysis.mc.n``, ``seed`` to ``analysis.mc.seed``; a
    None seed is drawn and reported so the run can be repeated.
    """
    started = time.perf_counter()
    mc = (analysis or {}).get("mc") if isinstance(analysis, dict) else None
    mc = mc if isinstance(mc, dict) else {}
    if n is None:
        n = mc.get("n") or DEFAULT_N
    n = max(1, int(n))
    if seed is None:
        seed = mc.get("seed")
    if seed is None:
        seed = random.SystemRandom().randrange(0, 2 ** 32)
    seed = int(seed)
    rng = random.Random(seed)

    s = logic.compile_tree(tree, analysis)
    reachable = s.reachable_events()
    method = "tree" if (not s.non_coherent and not s.repeated) else "cutsets"
    warnings: List[Dict[str, Any]] = list(s.warnings)

    # Per-event samplers (only for events the top depends on).
    samplers = {}
    certain: List[str] = []
    for i in reachable:
        ev = s.events[i]
        derived = ev["derived"]
        nominal, fn = _q_function(derived)
        params = None
        if derived.get("q") is not None:
            params = lognormal_params((ev["quant"] or {}).get("unc"), nominal)
        if params is None:
            certain.append(ev["id"])
        else:
            samplers[i] = (params["median"], params["sigma"], fn)
    uncertain = [s.events[i]["id"] for i in reachable if i in samplers]

    # Compile the evaluator.
    base_q = [_clamp(e["q"]) for e in s.events]
    compiled = None
    truncated_cutsets = False
    if method == "tree":
        plan = [(i, op) for i, op in enumerate(s.ops) if s.reachable[i]]
        point = _clamp(s.evaluate(base_q)) if s.top is not None else 0.0
    else:
        # May raise cutsets.CutsetError (voting gate too large, time budget).
        result = cutsets_mod.compute(tree, analysis, {"timeBudgetS": max(1.0, time_limit / 2)},
                                     structure=s)
        truncated_cutsets = bool(result["truncated"])
        rows = result["cutSets"]
        rare = result["rareEvent"]
        chosen = []
        running = 0.0
        dropped = False
        for row in rows:
            if len(chosen) >= MAX_CUTSETS or (rare > 0 and running >= COVERAGE * rare):
                dropped = True
                break
            chosen.append(row)
            running += row["probability"]
        truncated_cutsets = truncated_cutsets or dropped
        compiled = []
        for row in chosen:
            const = 1.0
            vars_ = []
            for ev in row["events"]:
                idx = s.event_index[ev["id"]]
                if idx in samplers:
                    vars_.append(idx)
                else:
                    const *= base_q[idx]
            compiled.append((const, tuple(vars_)))
        point = cutsets_mod.mcub_of(r["probability"] for r in chosen)
        if dropped:
            warnings.append({"code": "MC_CUTSETS_TRUNCATED", "nodeId": None,
                             "params": {"used": len(chosen), "total": result["total"],
                                        "coverage": (running / rare) if rare > 0 else 1.0}})
        if result["truncated"]:
            warnings.extend(w for w in result["warnings"] if w["code"] == "CUTSETS_TRUNCATED")

    deadline = started + max(0.0, float(time_limit))
    samples: List[float] = []
    truncated_by_time = False
    done = 0
    while done < n:
        m = min(CHUNK, n - done)
        event_cols: Dict[int, List[float]] = {}
        for i in range(len(s.events)):
            if i in samplers:
                med, sig, fn = samplers[i]
                gauss = rng.gauss
                if med > 0.0:
                    # In log space, clamped below the float ceiling: an
                    # extreme error factor (EF is only bounded below) must
                    # give a huge sample, not an OverflowError.
                    log_med = math.log(med)
                    exp = math.exp
                    event_cols[i] = [
                        _clamp(fn(exp(min(_MAX_LOG, log_med + sig * gauss(0.0, 1.0)))))
                        for _ in range(m)
                    ]
                else:  # a mean so spread out its median underflowed to 0
                    for _ in range(m):
                        gauss(0.0, 1.0)  # keep the stream aligned for the seed
                    event_cols[i] = [_clamp(fn(0.0))] * m
            elif s.reachable[s.events[i]["op"]]:
                event_cols[i] = [base_q[i]] * m
        if method == "tree":
            col = _tree_chunk(s, plan, event_cols, m) if s.top is not None else [0.0] * m
        else:
            col = _mcub_chunk(compiled, event_cols, m)
        samples.extend(_clamp(v) for v in col)
        done += m
        if done < n and time.perf_counter() > deadline:
            truncated_by_time = True
            break

    completed = len(samples)
    ordered = sorted(samples)
    mean = sum(samples) / completed if completed else None
    if completed > 1:
        var = sum((v - mean) ** 2 for v in samples) / (completed - 1)
        std = math.sqrt(max(0.0, var))
    else:
        std = 0.0 if completed else None
    if not uncertain:
        warnings.append({"code": "MC_NO_UNCERTAINTY", "nodeId": None, "params": {}})
    return {
        "requested": n,
        "completed": completed,
        "seed": seed,
        "method": method,
        "mean": mean,
        "median": _quantile(ordered, 0.5) if completed else None,
        "p05": _quantile(ordered, 0.05) if completed else None,
        "p95": _quantile(ordered, 0.95) if completed else None,
        "std": std,
        "pointEstimate": point,
        "histogram": histogram(samples, bins),
        "truncatedByTime": truncated_by_time,
        "cutsetsTruncated": truncated_cutsets,
        "uncertainEvents": uncertain,
        "certainEvents": certain,
        "repeatedEvents": s.repeated_events(),
        "nonCoherent": s.non_coherent,
        "warnings": warnings,
        "elapsedMs": round((time.perf_counter() - started) * 1000.0, 1),
    }
