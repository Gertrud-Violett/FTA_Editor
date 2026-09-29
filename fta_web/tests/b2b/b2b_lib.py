"""
Back-to-back (B2B) harness: feed the same corpus file through every
independent path and compare what comes out.

Shared by ``fta_web/tests/test_b2b.py`` (the fast subset, in pytest) and
``fta_web/tests/b2b/run_b2b.py`` (everything, with a comparison matrix).

Every path returns a **Result**: ``{metric: {key: scalar}}``. A scalar is a
float, int, str, bool, None or a tuple of those, so two results compare key by
key with :func:`compare`. The engine path (``run_engine``) is the reference;
formatted outputs (DOT labels, the DOCX report) are compared with the
reference values formatted the same way (``numfmt.format_prob`` at 6 s.f.).

Paths
-----
engine        fta_web.engine.WebCore + summary / cutsets / importance /
              uncertainty / lint, called directly (the reference)
api:client    create_app() test client (bare-module blueprints, as run.py)
api:server    a real ``fta_web/run.py`` server over HTTP with the token
exe:server    the packaged fta_editor.exe's server over HTTP
cli / exe:cli ``run.py <command> --json`` / ``fta_editor.exe <command> --json``
cli:csv       ``--csv`` spot checks
legacy_core   fta_web/core FTACore (the 1.6 engine) on legacy-only trees
desktop       the frozen desktop/src FTACore, divergences attributed to
              DIVERGENCE.md entries by :func:`desktop_attribution`
oracle        truth-table enumeration (exact top event, minimal cut sets)
expected      hand-computed values in expected.json
roundtrip     open -> save -> reopen
desktop_compat  1.7-saved files read by the desktop core
"""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FTA_WEB = REPO / "fta_web"
CORE_DIR = FTA_WEB / "core"
DESKTOP_CORE = REPO / "desktop" / "src" / "FTA_Editor_core.py"
RUN_PY = FTA_WEB / "run.py"

for _p in (str(REPO), str(CORE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fta_web import cutsets as cutsets_mod  # noqa: E402
from fta_web import engine, importance, lint, uncertainty  # noqa: E402
from fta_web.numfmt import format_prob  # noqa: E402
from fta_web.state import load_warning_issues  # noqa: E402

from FTA_Editor_core import FTACore as VendoredFTACore  # noqa: E402  (the 1.6 engine)

#: Monte Carlo settings every path runs with (identical seed -> identical numbers).
MC_N = 2000
MC_SEED = 20260928
MC_TIME_LIMIT = 60.0
#: Significant figures for every formatted output compared here.
SF = 6
#: Report sections compared (no diagram: that needs a native Graphviz).
REPORT_SECTIONS = ["headline", "events", "cutsets", "importance", "uncertainty", "validation"]

LARGE_PREFIX = "R"
#: openpyxl serialises floats with 16 significant digits: at most 1.2e-16
#: relative (half a unit in the 16th digit is 5e-16 of the leading digit).
XLSX_REL = 5e-16


def exe_path() -> Optional[Path]:
    """The packaged 1.7.0 build, if present (``FTA_B2B_EXE`` overrides)."""
    raw = os.environ.get("FTA_B2B_EXE")
    if raw:
        path = Path(raw)
    else:
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            return None
        path = Path(base) / "fta_build_170" / "dist" / "fta_editor" / "fta_editor.exe"
    return path if path.is_file() else None


# ---- corpus ---------------------------------------------------------------------------


def corpus_names(large: bool = True) -> List[str]:
    names = sorted(p.name for p in HERE.glob("*.json") if p.name != "expected.json")
    if not large:
        names = [n for n in names if not n.startswith(LARGE_PREFIX)]
    return names


def corpus_path(name: str) -> Path:
    return HERE / name


def load_expected() -> Dict[str, Dict[str, Any]]:
    return json.loads((HERE / "expected.json").read_text(encoding="utf-8"))


def raw_document(name_or_path) -> Any:
    path = Path(name_or_path)
    if not path.is_absolute():
        path = HERE / path
    return json.loads(path.read_text(encoding="utf-8-sig"))


def raw_tree(document: Any) -> Dict[str, Any]:
    if isinstance(document, dict) and "tree" in document:
        return document["tree"]
    if isinstance(document, dict) and "FTA" in document:
        return document["FTA"]
    return document


_NEW_KEYS = ("gateType", "k", "transferTo", "eventKind", "houseState", "quant", "trace", "fmea")


def is_legacy(name: str) -> bool:
    """A 1.6 file: no 1.7 node keys and no ``analysis`` block."""
    document = raw_document(name)
    if isinstance(document, dict) and "analysis" in document:
        return False
    stack = [raw_tree(document)]
    while stack:
        node = stack.pop()
        if any(k in node for k in _NEW_KEYS):
            return False
        stack.extend(node.get("children") or [])
    return True


def copy_corpus(dest: Path, names: Iterable[str]) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copyfile(HERE / name, dest / name)
    return dest


# ---- helpers -------------------------------------------------------------------------------


def walk(tree: Any):
    """Pre-order nodes (the tree view's order)."""
    stack = [tree] if isinstance(tree, dict) else []
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed([c for c in node.get("children") or [] if isinstance(c, dict)]))


def _f(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return value


def _tuple(values: Iterable[Any]) -> tuple:
    return tuple(values)


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def fmt(value: Any, sf: int = SF) -> str:
    return format_prob(value, sf)


# ---- normalizers (one per result shape; every path shares them) --------------------------


def norm_tree(tree: Any) -> Dict[str, Dict[str, Any]]:
    calc, prob, order = {}, {}, []
    for node in walk(tree):
        nid = str(node.get("id"))
        order.append(nid)
        calc[nid] = _f(node.get("calculatedProbability"))
        prob[nid] = _f(node.get("probability"))
    return {"calc": calc, "prob": prob, "order": {"ids": tuple(order)}}


def norm_summary(s: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not s:
        return {}
    return {
        "treeWalk": _f(s.get("treeWalk")),
        "mcub": _f(s.get("mcub")),
        "rareEvent": _f(s.get("rareEvent")),
        "headline": _f(s.get("headline")),
        "headlineMethod": s.get("headlineMethod"),
        "repeatedEvents": tuple(sorted(str(r.get("id")) for r in s.get("repeatedEvents") or [])),
        "nonCoherent": s.get("nonCoherent"),
        "approximations": tuple(sorted("%s@%s" % (a.get("code"), a.get("nodeId"))
                                       for a in s.get("approximations") or [])),
        "truncated": s.get("truncated"),
        "truncatedBy": tuple(s.get("truncatedBy") or ()),
        "capped": s.get("capped"),
    }


def norm_cutsets(r: Dict[str, Any]) -> Dict[str, Any]:
    if "error" in r:
        return {"error": r["error"]}
    out: Dict[str, Any] = {
        "total": r.get("total"),
        "mcub": _f(r.get("mcub")),
        "rareEvent": _f(r.get("rareEvent")),
        "treeWalk": _f(r.get("treeWalk")),
        "truncated": r.get("truncated"),
        "truncatedBy": tuple(r.get("truncatedBy") or ()),
        "repeatedEvents": tuple(sorted(str(e.get("id")) for e in r.get("repeatedEvents") or [])),
        "nonCoherent": r.get("nonCoherent"),
        "approximations": tuple(sorted("%s@%s" % (a.get("code"), a.get("nodeId"))
                                       for a in r.get("approximations") or [])),
        "warnings": tuple(sorted("%s@%s" % (w.get("code"), w.get("nodeId"))
                                 for w in r.get("warnings") or [])),
    }
    for c in r.get("cutSets") or []:
        rank = c.get("rank")
        out["set/%d" % rank] = ",".join(sorted(str(e.get("id")) for e in c.get("events") or []))
        out["p/%d" % rank] = _f(c.get("probability"))
        out["share/%d" % rank] = _f(c.get("share"))
        out["order/%d" % rank] = c.get("order")
    return out


IMPORTANCE_KEYS = ("q", "fv", "birnbaum", "raw", "rrw", "rrwInfinite", "cutSetCount")


def norm_importance(rows: Any) -> Dict[str, Any]:
    if isinstance(rows, dict) and "error" in rows:
        return {"error": rows["error"]}
    out: Dict[str, Any] = {"order": tuple(str(m.get("id")) for m in rows or [])}
    for m in rows or []:
        for key in IMPORTANCE_KEYS:
            out["%s/%s" % (m.get("id"), key)] = _f(m.get(key)) if key != "cutSetCount" else m.get(key)
    return out


MC_KEYS = ("requested", "completed", "seed", "method", "mean", "median", "p05", "p95", "std",
           "pointEstimate", "truncatedByTime", "cutsetsTruncated", "nonCoherent")


def norm_mc(r: Dict[str, Any]) -> Dict[str, Any]:
    if "error" in r:
        return {"error": r["error"]}
    out = {k: (_f(r.get(k)) if k in ("mean", "median", "p05", "p95", "std", "pointEstimate")
               else r.get(k)) for k in MC_KEYS}
    hist = r.get("histogram") or {}
    out["hist.edges"] = tuple(_f(e) for e in hist.get("edges") or [])
    out["hist.counts"] = tuple(hist.get("counts") or [])
    out["hist.logBins"] = hist.get("logBins")
    out["uncertainEvents"] = tuple(r.get("uncertainEvents") or [])
    out["certainEvents"] = tuple(r.get("certainEvents") or [])
    out["repeatedEvents"] = tuple(sorted(str(e.get("id")) for e in r.get("repeatedEvents") or []))
    out["warnings"] = tuple(sorted(str(w.get("code")) for w in r.get("warnings") or []))
    return out


def norm_issues(issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    counts = {"error": 0, "warning": 0, "info": 0}
    for i, issue in enumerate(issues):
        out["%03d" % i] = "%s|%s|%s|%s" % (issue.get("severity"), issue.get("code"),
                                           issue.get("nodeId"), issue.get("message"))
        out["%03d/params" % i] = _canon(issue.get("params"))
        counts[issue.get("severity")] = counts.get(issue.get("severity"), 0) + 1
    for sev, n in counts.items():
        out["count/%s" % sev] = n
    return out


def norm_analysis(analysis: Any) -> Dict[str, Any]:
    return {"analysis": _canon(analysis)}


def norm_keys(tree: Any) -> Dict[str, Any]:
    """Every node's full content (keys and values), for round-trip checks."""
    return {str(n.get("id")): _canon({k: v for k, v in n.items() if k != "children"})
            for n in walk(tree)}


# ---- the reference: engine direct ------------------------------------------------------------


def session_issues(core) -> List[Dict[str, Any]]:
    return load_warning_issues(getattr(core, "last_load_warnings", None) or [])


def load_web(path) -> "engine.WebCore":
    core = engine.WebCore()
    ok, err = core.load_from_json(str(path))
    if not ok:
        raise ValueError(err)
    return core


def run_engine(path, mc_n: int = MC_N, mc_seed: int = MC_SEED,
               report_mc: bool = True) -> Dict[str, Any]:
    """The reference Result for one file."""
    core = load_web(path)
    tree = core.get_data()
    analysis = core.analysis
    res: Dict[str, Any] = norm_tree(tree)
    res["meta"] = {"mode": core.mode, "title": core.title}
    res["analysis"] = norm_analysis(analysis)
    res["keys"] = norm_keys(tree)
    res["qDerived"] = {str(n.get("id")): _f(engine.derive_quant(n, analysis)["q"])
                       for n in walk(tree)}
    res["loadWarnings"] = {"kinds": tuple(w.get("kind") for w in core.last_load_warnings)}
    mode = core.mode
    extra = None
    if mode != "ETA":
        res["summary"] = norm_summary(engine.summary(copy.deepcopy(tree), copy.deepcopy(analysis)))
        try:
            cut = cutsets_mod.compute(copy.deepcopy(tree), copy.deepcopy(analysis))
            res["cutsets"] = norm_cutsets(cut)
            res["importance"] = norm_importance(importance.compute(cut))
            res["_cut_raw"] = cut
        except cutsets_mod.CutsetError as exc:
            res["cutsets"] = {"error": exc.reason}
            res["importance"] = {"error": exc.reason}
        try:
            res["mc"] = norm_mc(uncertainty.run(copy.deepcopy(tree), copy.deepcopy(analysis),
                                                n=mc_n, seed=mc_seed, time_limit=MC_TIME_LIMIT))
        except cutsets_mod.CutsetError as exc:
            res["mc"] = {"error": exc.reason}
        doc_seed = (analysis.get("mc") or {}).get("seed")
        if report_mc and doc_seed is not None:
            try:
                res["_report_mc"] = uncertainty.run(copy.deepcopy(tree), copy.deepcopy(analysis),
                                                    n=min(mc_n, 5000), seed=doc_seed,
                                                    time_limit=MC_TIME_LIMIT)
            except cutsets_mod.CutsetError:
                pass
        signal = cutsets_mod.truncation_signal(copy.deepcopy(tree), copy.deepcopy(analysis))
        if signal is not None:
            extra = {"cutsets": signal}
    res["validate"] = norm_issues(lint.run(copy.deepcopy(tree), copy.deepcopy(analysis),
                                           session_issues(core), mode=mode, extra=extra))
    # The report judges truncation on its own (document-limit, 30 s) cut sets,
    # which complete on large trees where the tab's 2 s signal times out.
    report_extra = extra
    if "_cut_raw" in res:
        cut = res["_cut_raw"]
        report_extra = {"cutsets": {"truncated": bool(cut["truncated"]),
                                    "truncatedBy": list(cut["truncatedBy"]),
                                    "count": cut["total"]}}
    res["_report_validate"] = norm_issues(lint.run(copy.deepcopy(tree), copy.deepcopy(analysis),
                                                   session_issues(core), mode=mode,
                                                   extra=report_extra))
    res["_core"] = core
    return res


def public(result: Dict[str, Any]) -> Dict[str, Any]:
    """A Result without the private ``_`` entries (for printing / comparing)."""
    return {k: v for k, v in result.items() if not k.startswith("_")}


# ---- comparison -----------------------------------------------------------------------------


@dataclass
class Row:
    tree: str
    path: str
    metric: str
    status: str  # match | mismatch | divergence | skip | error
    n: int = 0
    max_abs: float = 0.0
    max_rel: float = 0.0
    note: str = ""
    diffs: List[Tuple[str, Any, Any]] = field(default_factory=list)


def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_float(text: Any) -> Optional[float]:
    if _num(text):
        return float(text)
    if not isinstance(text, str):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def compare(tree: str, path: str, metric: str, ref: Dict[str, Any], got: Dict[str, Any],
            rel: float = 0.0, abs_tol: float = 0.0, keys: str = "ref",
            parse: bool = False, note: str = "") -> Row:
    """Key-by-key comparison. Floats must be equal (or within ``rel``/``abs_tol``);
    anything else must be equal. ``keys``: ``ref`` (every reference key must be
    present), ``both`` (and no extra keys), ``common`` (intersection only).
    ``parse``: the values are formatted strings; errors are measured on the
    parsed numbers but equality is on the strings."""
    row = Row(tree, path, metric, "match", note=note)
    if ref is None or got is None:
        row.status = "skip"
        return row
    if keys == "common":
        wanted = [k for k in ref if k in got]
    else:
        wanted = list(ref)
        if keys == "both":
            wanted += [k for k in got if k not in ref]
    def close(fa: float, fb: float) -> bool:
        if math.isnan(fa) and math.isnan(fb):
            return True
        d = abs(fa - fb)
        scale = max(abs(fa), abs(fb))
        r = d / scale if scale > 0 else 0.0
        if d > 0:
            row.max_abs = max(row.max_abs, d)
            row.max_rel = max(row.max_rel, r)
        return d <= abs_tol or (rel > 0 and r <= rel) or d == 0

    for key in wanted:
        a = ref.get(key, "<missing>")
        b = got.get(key, "<missing>")
        row.n += 1
        ok = True
        if _num(a) and _num(b):
            ok = close(float(a), float(b))
        elif (isinstance(a, tuple) and isinstance(b, tuple) and len(a) == len(b) and a
              and all(_num(x) for x in a + b)):
            # A tuple of numbers (histogram edges): element by element.
            ok = all([close(float(x), float(y)) for x, y in zip(a, b)])
        else:
            ok = a == b
            if parse:
                fa, fb = _parse_float(a), _parse_float(b)
                if fa is not None and fb is not None and fa != fb:
                    d = abs(fa - fb)
                    scale = max(abs(fa), abs(fb))
                    row.max_abs = max(row.max_abs, d)
                    row.max_rel = max(row.max_rel, d / scale if scale else 0.0)
        if not ok:
            row.status = "mismatch"
            if len(row.diffs) < MAX_DIFFS:
                row.diffs.append((key, a, b))
    return row


#: Differing keys a Row keeps (enough for a whole Monte Carlo result).
MAX_DIFFS = 40


def compare_results(tree: str, path: str, ref: Dict[str, Any], got: Dict[str, Any],
                    specs: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Row]:
    """Every metric present in ``got`` against the same metric of ``ref``."""
    rows = []
    specs = specs or {}
    for metric, values in got.items():
        if metric.startswith("_"):
            continue
        if metric not in ref:
            continue
        spec = dict(specs.get(metric, {}))
        rows.append(compare(tree, path, metric, ref[metric], values, **spec))
    return rows


# ---- formatted references ----------------------------------------------------------------------


def ref_dot(ref: Dict[str, Any]) -> Dict[str, str]:
    return {nid: "P:%s|P_calc:%s" % (fmt(ref["prob"][nid]), fmt(ref["calc"][nid]))
            for nid in ref["order"]["ids"]}


_DOT_NODE = re.compile(r"^  ([A-Za-z0-9_]+) \[label=<<TABLE", re.M)
_DOT_META = re.compile(r"P:(\S+) \| P_calc:(\S+?)\s*</FONT>")


def parse_dot(dot: str, id_map: Dict[str, str]) -> Dict[str, str]:
    out = {}
    starts = [(m.start(), m.group(1)) for m in _DOT_NODE.finditer(dot)]
    for i, (pos, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(dot)
        block = dot[pos:end]
        meta = _DOT_META.search(block)
        if meta:
            out[id_map.get(name, name)] = "P:%s|P_calc:%s" % (meta.group(1), meta.group(2))
    return out


def parse_xlsx(blob: bytes) -> Dict[str, Dict[str, Any]]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(blob))
    ws = wb["Events"]
    rows = list(ws.iter_rows(values_only=True))
    headers = list(rows[0])
    idx = {h: i for i, h in enumerate(headers)}
    events: Dict[str, Any] = {}
    formats: Dict[str, Any] = {}
    for r_i, row in enumerate(rows[1:], start=2):
        nid = str(row[idx["Id"]])
        for header in ("Base probability", "Calculated probability", "λ (/h)", "T (h)", "τ (h)",
                       "μ (/h)", "MTTR (h)", "Unc. EF", "RPN", "k"):
            value = row[idx[header]]
            events["%s/%s" % (nid, header)] = _f(value)
        cell = ws.cell(row=r_i, column=idx["Calculated probability"] + 1)
        formats[nid] = cell.number_format
    analysis = {}
    ws2 = wb["Analysis"]
    for setting, value, _note in list(ws2.iter_rows(values_only=True))[1:]:
        analysis[str(setting)] = _f(value)
    return {"events": events, "analysis": analysis, "formats": formats,
            "sheets": tuple(wb.sheetnames)}


def ref_xlsx_events(ref: Dict[str, Any]) -> Dict[str, Any]:
    core = ref["_core"]
    from fta_web.excel_events import event_rows

    out = {}
    for row in event_rows(core.get_data()):
        nid = str(row["Id"])
        for header in ("Base probability", "Calculated probability", "λ (/h)", "T (h)", "τ (h)",
                       "μ (/h)", "MTTR (h)", "Unc. EF", "RPN", "k"):
            value = row[header]
            out["%s/%s" % (nid, header)] = _f(value)
    # The two probability columns must be the engine's own numbers.
    for nid in ref["order"]["ids"]:
        out["%s/Base probability" % nid] = ref["prob"][nid]
        out["%s/Calculated probability" % nid] = ref["calc"][nid]
    return out


def ref_xlsx_analysis(ref: Dict[str, Any]) -> Dict[str, Any]:
    s = ref.get("summary")
    if not s:
        return {}
    return {"Top event (headline)": s["headline"], "Tree walk": s["treeWalk"],
            "MCUB": s["mcub"], "Rare-event approximation": s["rareEvent"]}


def parse_docx(blob: bytes) -> Dict[str, Any]:
    """The report's numbers as printed, keyed like :func:`ref_docx`."""
    from docx import Document

    d = Document(io.BytesIO(blob))
    out: Dict[str, Any] = {}
    paras = d.paragraphs
    for i, p in enumerate(paras):
        if p.style.name.startswith("Heading") and p.text == "Top-event probability":
            nxt = paras[i + 1] if i + 1 < len(paras) else None
            if nxt is not None and nxt.runs:
                out["headline"] = nxt.runs[0].text
            break
    for p in paras:
        m = re.match(r"MCUB \(all cut sets\): (\S+); rare-event approximation: (\S+)\.$", p.text)
        if m:
            out["cs/mcub"], out["cs/rare"] = m.group(1), m.group(2)
    for table in d.tables:
        head = [c.text for c in table.rows[0].cells]
        body = [[c.text for c in r.cells] for r in table.rows[1:]]
        if head[:2] == ["Id", "Name"] and "Calculated" in head:
            for r in body:
                out["ev/%s/q" % r[0]] = r[5]
                out["ev/%s/calc" % r[0]] = r[6]
        elif head[:2] == ["#", "Events"]:
            for r in body:
                out["cs/%s/p" % r[0]] = r[3]
        elif head[:2] == ["Id", "Name"] and "FV" in head:
            for r in body:
                for col, key in ((2, "q"), (3, "fv"), (4, "birnbaum"), (5, "raw"), (6, "rrw"),
                                 (7, "cutSetCount")):
                    out["imp/%s/%s" % (r[0], key)] = r[col]
        elif head == ["Statistic", "Value"]:
            for r in body:
                out["mc/%s" % r[0]] = r[1]
        elif head[:2] == ["Severity", "Code"]:
            for i, r in enumerate(body):
                out["val/%03d" % i] = "%s|%s" % (r[0], r[1])
    return out


_STAT = {"pointEstimate": "Point estimate", "mean": "Mean", "median": "Median",
         "p05": "5th percentile", "p95": "95th percentile", "std": "Std. deviation"}


def ref_docx(ref: Dict[str, Any], mc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    core = ref["_core"]
    if core.mode == "ETA":
        out["headline"] = "Event tree (ETA) mode: this section applies to fault trees only."
    elif ref.get("summary"):
        out["headline"] = fmt(ref["summary"]["headline"])
    for node in walk(core.get_data()):
        nid = str(node.get("id"))
        if node.get("children") or str(node.get("gateType") or "").upper() == "TRANSFER":
            continue
        out["ev/%s/q" % nid] = fmt(ref["prob"][nid])
        out["ev/%s/calc" % nid] = fmt(ref["calc"][nid])
    cut = ref.get("cutsets") or {}
    if core.mode != "ETA" and "error" not in cut:
        out["cs/mcub"] = fmt(cut["mcub"])
        out["cs/rare"] = fmt(cut["rareEvent"])
        for key, value in cut.items():
            if key.startswith("p/") and int(key[2:]) <= 50:
                out["cs/%s/p" % key[2:]] = fmt(value)
        imp = ref.get("importance") or {}
        for nid in list(imp.get("order", ()))[:30]:
            for key in ("q", "fv", "birnbaum", "raw"):
                out["imp/%s/%s" % (nid, key)] = fmt(imp["%s/%s" % (nid, key)])
            rrw = imp["%s/rrw" % nid]
            out["imp/%s/rrw" % nid] = ("∞" if imp["%s/rrwInfinite" % nid] and rrw is None
                                       else fmt(rrw))
            out["imp/%s/cutSetCount" % nid] = str(imp["%s/cutSetCount" % nid])
    if mc:
        for key, label in _STAT.items():
            out["mc/%s" % label] = fmt(mc.get(key))
        samples = str(mc.get("completed"))
        if mc.get("requested") != mc.get("completed"):
            samples = "%s / %s" % (mc.get("completed"), mc.get("requested"))
        out["mc/Samples"] = samples
        out["mc/Seed"] = str(mc.get("seed"))
        out["mc/Method"] = str(mc.get("method"))
    for key, value in ref.get("_report_validate", ref["validate"]).items():
        if re.fullmatch(r"\d{3}", key):
            sev, code = value.split("|")[:2]
            out["val/%s" % key] = "%s|%s" % (sev, code)
    return out


def xml_values(blob: bytes) -> Dict[str, Any]:
    root = ET.fromstring(blob)
    out = {}
    for i, node in enumerate(root.iter("Node")):
        out["%04d/base" % i] = _f(float(node.get("baseProbability")))
        cp = node.get("calculatedProbability")
        out["%04d/calc" % i] = _f(float(cp)) if cp not in (None, "") else None
    return out


def ref_xml(ref: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for i, nid in enumerate(ref["order"]["ids"]):
        out["%04d/base" % i] = ref["prob"][nid]
        out["%04d/calc" % i] = ref["calc"][nid]
    return out


def reload_json_bytes(blob: bytes) -> Dict[str, Any]:
    """Round trip: the exported/saved JSON loaded again by the engine."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rt.json"
        path.write_bytes(blob)
        core = load_web(path)
        res = norm_tree(core.get_data())
        res["keys"] = norm_keys(core.get_data())
        res["analysis"] = norm_analysis(core.analysis)
        res["loadWarnings"] = {"kinds": tuple(w.get("kind") for w in core.last_load_warnings)}
        return res


# ---- HTTP transports ------------------------------------------------------------------------


class Transport:
    def get(self, url: str) -> Tuple[int, bytes]:
        raise NotImplementedError

    def post(self, url: str, body: Any) -> Tuple[int, bytes]:
        raise NotImplementedError

    def get_json(self, url: str) -> Dict[str, Any]:
        status, data = self.get(url)
        payload = json.loads(data.decode("utf-8"))
        if status != 200:
            raise HttpError(status, payload)
        return payload

    def post_json(self, url: str, body: Any) -> Dict[str, Any]:
        status, data = self.post(url, body)
        payload = json.loads(data.decode("utf-8"))
        if status != 200:
            raise HttpError(status, payload)
        return payload


class HttpError(Exception):
    def __init__(self, status: int, payload: Any):
        super().__init__("HTTP %s: %s" % (status, str(payload)[:300]))
        self.status = status
        self.payload = payload


class ClientTransport(Transport):
    """A ``create_app()`` test client (the blueprints as run.py mounts them)."""

    def __init__(self, fs_root: Path):
        web_dir = str(FTA_WEB)
        if web_dir not in sys.path:
            sys.path.insert(0, web_dir)
        import app as bare_app  # noqa: E402  (bare name, exactly as run.py)
        import state as bare_state  # noqa: E402

        bare_state.reset_state()
        self.app = bare_app.create_app(fs_root=fs_root)
        self.app.config.update(TESTING=True)
        bare_state.get_state().fs_root = fs_root
        self.client = self.app.test_client()

    def get(self, url):
        r = self.client.get(url)
        return r.status_code, r.get_data()

    def post(self, url, body):
        r = self.client.post(url, json=body)
        return r.status_code, r.get_data()


class ServerTransport(Transport):
    """A real server process (``run.py`` or the exe) over loopback HTTP."""

    def __init__(self, command: Sequence[str], fs_root: Path, timeout: float = 60.0):
        port = _free_port()
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        self.proc = subprocess.Popen(
            list(command) + ["--port", str(port), "--no-browser", "--root", str(fs_root)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=str(REPO),
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        self.base = "http://127.0.0.1:%d" % port
        self.token = None
        deadline = time.monotonic() + timeout
        lines = []
        while time.monotonic() < deadline:
            line = self.proc.stdout.readline().decode("utf-8", "replace")
            if not line:
                if self.proc.poll() is not None:
                    break
                continue
            lines.append(line)
            m = re.search(r"\?t=([A-Za-z0-9_\-]+)", line)
            if m:
                self.token = m.group(1)
                break
        if not self.token:
            self.close()
            raise RuntimeError("server did not start: %s" % "".join(lines)[-2000:])
        # Drain the rest of the output so the pipe never fills up.
        import threading

        threading.Thread(target=self._drain, daemon=True).start()
        for _ in range(200):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                    break
            except OSError:
                time.sleep(0.05)

    def _drain(self):
        try:
            for _line in self.proc.stdout:
                pass
        except Exception:
            pass

    def _request(self, method: str, url: str, body: Any = None) -> Tuple[int, bytes]:
        data = None
        headers = {"X-FTA-Token": self.token}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def get(self, url):
        return self._request("GET", url)

    def post(self, url, body):
        return self._request("POST", url, body if body is not None else {})

    def close(self):
        """Stop the process this transport started (and only that one)."""
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def source_server_command(python: Optional[Path] = None, run_py: Optional[Path] = None
                          ) -> List[str]:
    return [str(python or sys.executable), str(run_py or RUN_PY)]


#: The commit the packaged exe was built from (v1.7.0). FTA_B2B_EXE_COMMIT
#: overrides it for a newer build.
RELEASE_COMMIT = os.environ.get("FTA_B2B_EXE_COMMIT", "544492b")


def export_commit(commit: str, dest: Path) -> Path:
    """``fta_web/`` as it was at ``commit`` (``git archive``, read-only), for
    running the exe's own source side by side. Returns its ``run.py``."""
    import tarfile

    proc = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", commit, "fta_web"],
                          capture_output=True, check=True, timeout=120)
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
        tar.extractall(dest)
    return dest / "fta_web" / "run.py"


# ---- the API path --------------------------------------------------------------------------


def run_api(t: Transport, root: Path, name: str, ref: Dict[str, Any],
            per_node_limit: Optional[int] = None, report: bool = True,
            exports: bool = True, roundtrip: bool = True) -> Dict[str, Any]:
    """Every API view of one file, as a Result (plus private raw pieces)."""
    doc = t.post_json("/api/file/open", {"path": str(root / name)})
    res: Dict[str, Any] = norm_tree(doc["tree"])
    res["meta"] = {"mode": doc["metadata"]["mode"], "title": doc["metadata"]["title"]}
    res["analysis"] = norm_analysis(doc["analysis"])
    res["keys"] = norm_keys(doc["tree"])
    res["loadWarnings"] = {"kinds": tuple(w.get("kind") for w in doc.get("warnings") or [])}
    state = t.get_json("/api/state")
    st = norm_tree(state["tree"])
    res["state.calc"] = st["calc"]
    res["state.prob"] = st["prob"]
    ids = list(ref["order"]["ids"])
    if per_node_limit is not None:
        ids = ids[:per_node_limit]
    node_calc, node_prob, node_q = {}, {}, {}
    for nid in ids:
        view = t.get_json("/api/nodes/" + urllib.parse.quote(nid, safe=""))["node"]
        node_calc[nid] = _f(view.get("calculatedProbability"))
        node_prob[nid] = _f(view.get("probability"))
        node_q[nid] = _f((view.get("quantDerived") or {}).get("q"))
    res["nodes.calc"] = node_calc
    res["nodes.prob"] = node_prob
    res["qDerived"] = node_q
    mode = doc["metadata"]["mode"]
    if mode != "ETA":
        res["summary"] = norm_summary(t.get_json("/api/analysis/summary"))
        try:
            res["cutsets"] = norm_cutsets(t.post_json("/api/analysis/cutsets", {"limit": 100000}))
        except HttpError as exc:
            res["cutsets"] = {"error": (exc.payload.get("error") or {}).get("detail", {}).get("reason")}
        try:
            imp = t.post_json("/api/analysis/importance", {})
            res["importance"] = norm_importance(imp["events"])
        except HttpError as exc:
            res["importance"] = {"error": (exc.payload.get("error") or {}).get("detail", {}).get("reason")}
        try:
            res["mc"] = norm_mc(t.post_json("/api/analysis/uncertainty",
                                            {"n": MC_N, "seed": MC_SEED, "timeLimit": MC_TIME_LIMIT}))
        except HttpError as exc:
            res["mc"] = {"error": (exc.payload.get("error") or {}).get("detail", {}).get("reason")}
    res["validate"] = norm_issues(t.get_json("/api/analysis/validate")["issues"])
    dot = t.get_json("/api/dot?sigFigs=%d" % SF)
    res["dot"] = parse_dot(dot["dot"], dot.get("idMap") or {})
    if exports:
        status, blob = t.get("/api/export/xlsx?sigFigs=%d" % SF)
        if status == 200:
            x = parse_xlsx(blob)
            res["xlsx.events"] = x["events"]
            res["xlsx.analysis"] = x["analysis"]
            res["_xlsx_formats"] = x["formats"]
        status, blob = t.get("/api/export/xml")
        if status == 200:
            res["xml"] = xml_values(blob)
        status, blob = t.get("/api/export/json")
        if status == 200:
            rt = reload_json_bytes(blob)
            res["export.calc"] = rt["calc"]
            res["export.keys"] = rt["keys"]
            res["export.analysis"] = rt["analysis"]
            res["_export_json"] = blob
    if report:
        seed = (json.loads(res["analysis"]["analysis"]).get("mc") or {}).get("seed")
        body = {"sections": REPORT_SECTIONS, "sigFigs": SF, "lang": "en",
                "runUncertainty": seed is not None and mode != "ETA",
                "uncertaintyN": min(MC_N, 5000), "uncertaintyTimeLimit": 60,
                "topN": {"cutsets": 50, "importance": 30}}
        status, blob = t.post("/api/report/docx", body)
        if status == 200:
            res["docx"] = parse_docx(blob)
        else:
            res["docx"] = {"error": status}
    if roundtrip:
        out_name = "_rt_" + name
        t.post_json("/api/file/save-as", {"path": str(root / out_name)})
        again = t.post_json("/api/file/open", {"path": str(root / out_name)})
        rt = norm_tree(again["tree"])
        res["roundtrip.calc"] = rt["calc"]
        res["roundtrip.keys"] = norm_keys(again["tree"])
        res["roundtrip.analysis"] = norm_analysis(again["analysis"])
        saved = (root / out_name).read_bytes()
        res["_saved_json"] = saved
        if "_export_json" in res:
            res["roundtrip.exportIsSave"] = {"same": _strip_date(res["_export_json"]) ==
                                             _strip_date(saved)}
    return res


def _strip_date(blob: bytes) -> Any:
    doc = json.loads(blob.decode("utf-8"))
    doc.pop("date", None)
    return doc


def api_rows(name: str, ref: Dict[str, Any], got: Dict[str, Any], path: str,
             rel: float = 0.0) -> List[Row]:
    """The standard comparisons of an API Result against the engine reference.
    ``rel`` loosens the numeric metrics (a different Python build: LIBM_REL)."""
    rows = []
    same = [("calc", "calc"), ("prob", "prob"), ("state.calc", "calc"), ("state.prob", "prob"),
            ("nodes.calc", "calc"), ("nodes.prob", "prob"), ("qDerived", "qDerived"),
            ("summary", "summary"), ("cutsets", "cutsets"), ("importance", "importance"),
            ("mc", "mc"), ("validate", "validate"), ("analysis", "analysis"), ("keys", "keys"),
            ("loadWarnings", "loadWarnings"), ("meta", "meta")]
    for metric, ref_metric in same:
        if metric not in got or ref_metric not in ref:
            continue
        keys = "common" if metric.startswith("nodes.") or metric == "qDerived" else "both"
        rows.append(compare(name, path, metric, ref[ref_metric], got[metric], keys=keys, rel=rel))
    if "dot" in got:
        rows.append(compare(name, path, "dot@6sf", ref_dot(ref), got["dot"], keys="both",
                            parse=True))
    if "xlsx.events" in got:
        # openpyxl writes a float as "%.16g" (compat/strings.py), so a number
        # with 17 significant digits comes back rounded to 16: XLSX_REL.
        rows.append(compare(name, path, "xlsx.events", ref_xlsx_events(ref), got["xlsx.events"],
                            keys="both", rel=max(rel, XLSX_REL)))
        rows.append(compare(name, path, "xlsx.analysis", ref_xlsx_analysis(ref),
                            got["xlsx.analysis"], keys="ref", rel=max(rel, XLSX_REL)))
    if "xml" in got:
        rows.append(compare(name, path, "xml", ref_xml(ref), got["xml"], keys="both", rel=rel))
    for metric, ref_metric in (("export.calc", "calc"), ("export.keys", "keys"),
                               ("export.analysis", "analysis"), ("roundtrip.calc", "calc"),
                               ("roundtrip.keys", "keys"), ("roundtrip.analysis", "analysis")):
        if metric in got:
            rows.append(compare(name, path, metric, ref[ref_metric], got[metric], keys="both",
                                rel=rel))
    if "roundtrip.exportIsSave" in got:
        rows.append(compare(name, path, "export==save", {"same": True},
                            got["roundtrip.exportIsSave"]))
    if "docx" in got:
        rows.append(compare(name, path, "docx@6sf", ref_docx(ref, ref.get("_report_mc")),
                            got["docx"], keys="both", parse=True))
    return rows


# ---- the CLI path ----------------------------------------------------------------------------


CLI_COMMANDS = ("quantify", "cutsets", "importance", "mc", "validate")


def run_cli_batch(command: str, files: Sequence[Path], exe: Optional[Path] = None,
                  extra: Sequence[str] = (), fmt_flag: str = "--json",
                  timeout: float = 1800.0, python: Optional[Path] = None,
                  run_py: Optional[Path] = None) -> Tuple[int, Any, str]:
    """One CLI invocation over several files (the exe, or ``run_py`` -- this
    checkout's by default -- under ``python``). Returns (exit code, parsed
    output, stderr)."""
    base = [str(exe)] if exe else [str(python or sys.executable), str(run_py or RUN_PY)]
    args = base + [command] + [str(f) for f in files] + [fmt_flag] + list(extra)
    if command == "mc":
        args += ["--n", str(MC_N), "--seed", str(MC_SEED), "--time-limit", str(int(MC_TIME_LIMIT))]
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run(args, capture_output=True, cwd=str(REPO), env=env, timeout=timeout)
    out = proc.stdout.decode("utf-8", "replace")
    if fmt_flag == "--json":
        payload = json.loads(out) if out.strip() else None
        if isinstance(payload, dict):
            payload = [payload]
    else:
        payload = out
    return proc.returncode, payload, proc.stderr.decode("utf-8", "replace")


def cli_results(outputs: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    """{file name: Result} from the five commands' --json outputs."""
    results: Dict[str, Dict[str, Any]] = {}
    for command, entries in outputs.items():
        for entry in entries or []:
            name = Path(entry["file"]).name
            res = results.setdefault(name, {})
            if "error" in entry:
                res.setdefault("errors", {})[command] = entry["error"]
                continue
            r = entry["results"]
            res["meta"] = {"mode": entry.get("mode"), "title": entry.get("title")}
            if command == "quantify":
                s = r["summary"]
                if res["meta"]["mode"] != "ETA":
                    res["summary"] = norm_summary(s)
                res["events.calc"] = {str(e["id"]): _f(e["calculated"]) for e in r["events"]}
                res["events.prob"] = {str(e["id"]): _f(e["q"]) for e in r["events"]}
            elif command == "cutsets":
                res["cutsets"] = norm_cutsets(r)
            elif command == "importance":
                res["importance"] = norm_importance(r["measures"])
            elif command == "mc":
                res["mc"] = norm_mc(r)
            elif command == "validate":
                res["validate"] = norm_issues(r["issues"])
    return results


def cli_rows(name: str, ref: Dict[str, Any], got: Dict[str, Any], path: str,
             rel: float = 0.0) -> List[Row]:
    rows = []
    if "errors" in got:
        ref_err = {}
        for command in got["errors"]:
            ref_err[command] = "ETA" if ref["meta"]["mode"] == "ETA" else (
                ref.get("cutsets", {}).get("error") or ref.get("mc", {}).get("error"))
        rows.append(compare(name, path, "cli.errors", {k: bool(v) for k, v in ref_err.items()},
                            {k: True for k in got["errors"]}))
    for metric, ref_metric in (("events.calc", "calc"), ("events.prob", "prob")):
        if metric in got:
            rows.append(compare(name, path, metric, ref[ref_metric], got[metric], keys="common",
                                rel=rel))
    for metric in ("summary", "cutsets", "importance", "mc", "validate", "meta"):
        if metric in got and metric in ref:
            rows.append(compare(name, path, metric, ref[metric], got[metric], keys="both",
                                rel=rel))
    return rows


#: A different Python build (the packaged exe is CPython 3.14, the default
#: venv 3.10) links a different libm: math.log1p / expm1 / exp may differ in
#: the last bit (expm1(-0.030149) is ...917 on 3.14, ...913 on 3.10). Every
#: value that goes through them -- MCUB, importance, Monte Carlo samples, the
#: log-space OR -- can then differ by a few ulp. Same build: bit-identical.
LIBM = "LIBM"
LIBM_REL = 1e-13


def cross_build(exact: List[Row], loose: List[Row]) -> List[Row]:
    """``exact`` rows, with each mismatch that ``loose`` (the same comparison
    at LIBM_REL) accepts turned into a documented LIBM divergence."""
    by_metric = {(r.tree, r.metric): r for r in loose}
    out = []
    for row in exact:
        other = by_metric.get((row.tree, row.metric))
        if row.status == "mismatch" and other is not None and other.status == "match":
            row.status = "divergence"
            row.note = (row.note + " " if row.note else "") + \
                "%s: last-ulp libm difference between Python builds" % LIBM
            row.diffs = row.diffs[:3]
        out.append(row)
    return out


#: The headline's own 2 s cut-set budget (engine.SUMMARY_LIMITS): on a large
#: tree two processes can stop at different points. Not a numeric claim.
TIME = "TIME"


def relabel_timing(rows: List[Row], ref: Dict[str, Any], got: Dict[str, Any]) -> List[Row]:
    def timed(s):
        return bool(s) and bool(s.get("capped") or "time" in (s.get("truncatedBy") or ()))

    if not (timed(ref.get("summary")) or timed(got.get("summary"))):
        return rows
    for row in rows:
        if row.metric == "summary" and row.status == "mismatch":
            row.status = "divergence"
            row.note = "%s: the summary's 2 s budget ran out in one of the runs" % TIME
    return rows


def cli_csv_rows(name: str, ref: Dict[str, Any], exe: Optional[Path] = None) -> List[Row]:
    """--csv spot check: quantify (per event) and cutsets (per rank)."""
    rows = []
    _code, text, _err = run_cli_batch("quantify", [corpus_path(name)], exe=exe, fmt_flag="--csv")
    table = parse_cli_csv(text)
    ids = {r["id"] for r in table}
    rows.append(compare(name, "cli:csv", "quantify.calculated",
                        {k: v for k, v in ref["calc"].items() if k in ids},
                        {r["id"]: float(r["calculated"]) for r in table}, keys="both"))
    rows.append(compare(name, "cli:csv", "quantify.q",
                        {k: v for k, v in ref["prob"].items() if k in ids},
                        {r["id"]: float(r["q"]) for r in table}, keys="both"))
    _code, text, _err = run_cli_batch("cutsets", [corpus_path(name)], exe=exe, fmt_flag="--csv")
    table = parse_cli_csv(text)
    cut = ref.get("cutsets") or {}
    rows.append(compare(name, "cli:csv", "cutsets.probability",
                        {k: v for k, v in cut.items() if k.startswith("p/")},
                        {"p/%s" % r["rank"]: float(r["probability"]) for r in table}, keys="both"))
    rows.append(compare(name, "cli:csv", "cutsets.events",
                        {k: v for k, v in cut.items() if k.startswith("set/")},
                        {"set/%s" % r["rank"]: ",".join(sorted(r["events"].split(";")))
                         for r in table}, keys="both"))
    return rows


#: What this branch changed on purpose since the release the exe was built
#: from; a 1.7.0-vs-1.7.1 difference must be one of these.
FIX_OR = "FIXED:OR-LOG"      # engine.or_probability (OR gates flushed tiny values)
#: uncertainty: the mean pivot (constant samples: mean == point, std == 0), and
#: samples whose OR is below 1e-3 now evaluated in log space (last digits).
FIX_MC = "FIXED:MC-MEAN/OR-LOG"
FIX_FMT = "FIXED:NUMFMT"     # numfmt.format_prob mirrors numfmt.js


def or_affected(names: Iterable[str]) -> set:
    """Trees whose numbers change when the OR is the 1.6 product form."""
    def naive(probs):
        product = 1
        for p in probs:
            product *= 1 - p
        return 1 - product

    before = {n: positional(load_web(corpus_path(n)).get_data()) for n in names}
    saved = engine.or_probability
    engine.or_probability = naive
    try:
        after = {n: positional(load_web(corpus_path(n)).get_data()) for n in names}
    finally:
        engine.or_probability = saved
    return {n for n in before if before[n] != after[n]}


def classify_release(rows: List[Row], or_trees: set) -> List[Row]:
    """Mismatches between the release's output and this branch's that one of
    the branch's fixes explains become divergences naming the fix."""
    def tiny(a, b):
        """Last-digit difference (numbers or tuples of numbers)."""
        if isinstance(a, tuple) and isinstance(b, tuple) and len(a) == len(b):
            return all(tiny(x, y) for x, y in zip(a, b))
        if _num(a) and _num(b):
            scale = max(abs(a), abs(b))
            return scale == 0 or abs(a - b) / scale <= 1e-12
        return False

    for row in rows:
        if row.status != "mismatch":
            continue
        texts = [str(d[1]) + str(d[2]) for d in row.diffs]
        if row.tree in or_trees:
            row.status, row.note = "divergence", FIX_OR
        elif row.metric == "mc" and len(row.diffs) < MAX_DIFFS and all(
                d[0] in ("mean", "std") or tiny(d[1], d[2]) for d in row.diffs):
            row.status, row.note = "divergence", FIX_MC
        elif row.metric.startswith(("docx", "dot")) and all(
                "e+" in t or "e" in t for t in texts):
            row.status, row.note = "divergence", FIX_FMT
    return rows


FRONTEND_BUG_NUMFMT = ("FRONTEND BUG: numfmt.js picks the plain/exponent form from the "
                       "unrounded magnitude (USER_GUIDE: rounded)")


def numfmt_rows(results: Iterable[Dict[str, Any]]) -> List[Row]:
    """static/js/numfmt.js vs numfmt.format_prob at 1..6 s.f. on every corpus
    number. The documented frontend bug is reported as its own row."""
    values = format_probe_values(results)
    sfs = [1, 2, 3, 4, 5, 6]
    js = js_format(values, sfs)
    if js is None:
        return [Row("*", "numfmt:js", "formatProb", "skip", note="node not installed")]
    py = py_format(values, sfs)
    ok_ref, ok_got, bug_ref, bug_got = {}, {}, {}, {}
    for key, text in py.items():
        i, sf = (int(x) for x in key.split("@"))
        value = values[i]
        mag = abs(value)
        rounded = float("%.*e" % (sf - 1, mag)) if mag else 0.0
        boundary = (mag < 1e-3) != (rounded < 1e-3) or (mag >= 1e4) != (rounded >= 1e4)
        target = (bug_ref, bug_got) if boundary else (ok_ref, ok_got)
        target[0]["%r@%d" % (value, sf)] = text
        target[1]["%r@%d" % (value, sf)] = js[key]
    rows = [compare("*", "numfmt:js", "formatProb", ok_ref, ok_got, keys="both", parse=True)]
    bug = compare("*", "numfmt:js", "formatProb@1e-3/1e4 boundary", bug_ref, bug_got,
                  keys="both", parse=True, note=FRONTEND_BUG_NUMFMT)
    if bug.status == "mismatch":
        bug.status = "divergence"
    rows.append(bug)
    return rows


def parse_cli_csv(text: str) -> List[Dict[str, str]]:
    import csv

    return list(csv.DictReader(io.StringIO(text)))


# ---- legacy engines --------------------------------------------------------------------------


_DESKTOP_MODULE = None


def desktop_core_module():
    """The frozen desktop/src/FTA_Editor_core.py under a distinct module name."""
    global _DESKTOP_MODULE
    if _DESKTOP_MODULE is None:
        spec = importlib.util.spec_from_file_location("desktop_FTA_Editor_core", str(DESKTOP_CORE))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _DESKTOP_MODULE = module
    return _DESKTOP_MODULE


def positional(tree: Any) -> Dict[str, Any]:
    """Pre-order position -> calculatedProbability (ids may differ: D15/D16)."""
    return {"%04d" % i: _f(n.get("calculatedProbability")) for i, n in enumerate(walk(tree))}


def run_vendored(path) -> Dict[str, Any]:
    core = VendoredFTACore()
    ok, err = core.load_from_json(str(path))
    if not ok:
        return {"error": {"load": err}}
    res = norm_tree(core.get_data())
    res["keys"] = norm_keys(core.get_data())
    return res


def run_desktop(path) -> Tuple[Optional[Any], Optional[str]]:
    """(loaded desktop core or None, error)."""
    module = desktop_core_module()
    core = module.FTACore()
    ok, err = core.load_from_json(str(path))
    if not ok:
        return None, err
    return core, None


def _round6(x: float) -> float:
    return round(x, 6)


def legacy_walk(tree: Dict[str, Any], rounding: str, memo_by: str, cycles: str,
                or_mode: str = "product") -> None:
    """An independent re-implementation of the AND/OR/link tree walk, with the
    behaviours DIVERGENCE.md (and 1.7.1) changed as switches:

    * ``rounding``: ``round6`` (baseline) or ``tidy`` (D14);
    * ``memo_by``: ``id`` string (baseline) or object ``identity`` (D15);
    * ``cycles``: ``base`` -- re-entry returns and memoises the node's own
      probability (baseline) -- or ``gate_only`` (D17);
    * ``or_mode``: ``product`` -- ``1 - Π(1 - p)`` (the cores) -- or ``web``
      (``engine.or_probability``: log space below 1e-3, WebCore 1.7.1).

    Writes ``calculatedProbability`` like the engines do.
    """
    rnd = _round6 if rounding == "round6" else engine._tidy
    index: Dict[str, Dict[str, Any]] = {}
    for node in walk(tree):
        index.setdefault(str(node.get("id")), node)
    memo: Dict[Any, float] = {}
    visiting = set()
    gate_only: Dict[Any, float] = {}

    def key(node):
        return node.get("id") if memo_by == "id" else id(node)

    def prod(xs):
        out = 1
        for x in xs:
            out *= x
        return out

    def union(xs):
        if or_mode == "web":
            return engine.or_probability(xs)
        return 1 - prod([1 - p for p in xs])

    def get(node):
        k = key(node)
        if k in memo:
            return memo[k]
        if k in visiting:
            if cycles == "base":
                val = float(node.get("probability", 1.0))
                memo[k] = val
                return val
            if k in gate_only:
                return gate_only[k]
            if not (node.get("children") or []):
                return float(node.get("probability", 1.0))
            return None
        visiting.add(k)
        children = node.get("children", []) or []
        if not children:
            base = float(node.get("probability", 0.0))
        else:
            probs = [get(c) for c in children]
            probs = [p for p in probs if p is not None]
            gate_value = node.get("logicGate", "OR")
            gate = str(gate_value).strip().upper() if gate_value else "OR"
            base = rnd(prod(probs)) if gate == "AND" else rnd(union(probs))
        if cycles == "gate_only":
            gate_only[k] = base
        and_p, or_p = [], []
        for link in node.get("links", []) or []:
            tid = link.get("target_id")
            rel = (link.get("relation") or "OR").upper()
            if not tid:
                continue
            target = index.get(str(tid))
            if not target:
                continue
            tp = get(target)
            if tp is None:
                continue
            (and_p if rel == "AND" else or_p).append(tp)
        if and_p:
            base = rnd(base * prod(and_p))
        if or_p:
            base = rnd(union([base] + or_p))
        memo[k] = base
        visiting.discard(k)
        gate_only.pop(k, None)
        node["calculatedProbability"] = base
        return base

    get(tree)


def legacy_eta(tree: Dict[str, Any], rounding: str) -> None:
    rnd = _round6 if rounding == "round6" else engine._tidy

    def calc(node, parent=1.0):
        value = rnd(parent * float(node.get("probability", 1.0)))
        node["calculatedProbability"] = value
        for child in node.get("children", []) or []:
            calc(child, value)

    calc(tree)


def _dedupe(tree: Dict[str, Any]) -> None:
    """Mirror of the documented D15 rename (``<id>_dupN``) for the model."""
    taken = {n.get("id") for n in walk(tree)}
    seen = set()
    for n in walk(tree):
        nid = n.get("id")
        if nid not in seen:
            seen.add(nid)
            continue
        suffix = 2
        while "%s_dup%d" % (nid, suffix) in taken:
            suffix += 1
        new = "%s_dup%d" % (nid, suffix)
        taken.add(new)
        seen.add(new)
        n["id"] = new


#: WebCore 1.7.1: an OR result below 1e-3 is computed in log space
#: (engine.or_probability) -- the one intended difference from the vendored
#: 1.6 core's tree walk.
OR_LOG = "OR-LOG"


@dataclass
class Attribution:
    tree: str
    ok: bool
    divergences: List[str]
    detail: List[str]


def desktop_attribution(name: str) -> Attribution:
    """Compare the desktop core with WebCore on a legacy file and attribute
    every difference to a DIVERGENCE.md entry (or report it unexplained)."""
    path = corpus_path(name)
    web = load_web(path)
    web_pos = positional(web.get_data())
    divergences: List[str] = []
    detail: List[str] = []
    if web.last_load_warnings:
        kinds = sorted({w["kind"] for w in web.last_load_warnings})
        if "root_id" in kinds:
            divergences.append("D16")
            detail.append("top id canonicalised to 'root' (numbers unaffected)")
        if "duplicate_id" in kinds:
            divergences.append("D15")
            detail.append("duplicate ids renamed <id>_dupN")
    desk, err = run_desktop(path)
    if desk is None:
        # D8: the baseline repair strips a brace off every minified document.
        text = path.read_text(encoding="utf-8").strip()
        if text.endswith("}}"):
            return Attribution(name, True, divergences + ["D8"],
                               detail + ["desktop cannot read a minified document: %s" % err])
        return Attribution(name, False, divergences, detail + ["desktop load failed: %s" % err])
    desk_pos = positional(desk.get_data())
    # 1. The model of the baseline reproduces the desktop core exactly.
    model = copy.deepcopy(desk.get_data())
    for n in walk(model):
        n.pop("calculatedProbability", None)
    eta = desk.mode == "ETA"
    if eta:
        legacy_eta(model, "round6")
    else:
        legacy_walk(model, "round6", "id", "base")
    if positional(model) != desk_pos:
        return Attribution(name, False, divergences, detail + ["baseline model != desktop"])
    # 2. Switch the documented changes on one at a time.
    steps = [("D14", "tidy", "id", "base", False, "product"),
             ("D15", "tidy", "identity", "base", True, "product"),
             ("D17", "tidy", "identity", "gate_only", True, "product"),
             (OR_LOG, "tidy", "identity", "gate_only", True, "web")]
    previous = desk_pos
    last = None
    for code, rounding, memo_by, cyc, dedupe, or_mode in steps:
        variant = copy.deepcopy(desk.get_data())
        for n in walk(variant):
            n.pop("calculatedProbability", None)
        if dedupe:
            _dedupe(variant)
        if eta:
            legacy_eta(variant, rounding)
        else:
            legacy_walk(variant, rounding, memo_by, cyc, or_mode)
        now = positional(variant)
        changed = [k for k in now if now[k] != previous.get(k)]
        if changed:
            if code not in divergences:
                divergences.append(code)
            detail.append("%s changes %d node value(s), e.g. #%s %r -> %r" % (
                code, len(changed), changed[0], previous.get(changed[0]), now[changed[0]]))
        previous = now
        last = now
    ok = last == web_pos
    if not ok:
        diff = [k for k in web_pos if web_pos[k] != (last or {}).get(k)]
        detail.append("UNEXPLAINED: %d node(s) differ after D14/D15/D17/OR-LOG, e.g. #%s web=%r model=%r"
                      % (len(diff), diff[0], web_pos[diff[0]], (last or {}).get(diff[0])))
    return Attribution(name, ok, sorted(set(divergences)), detail)


def vendored_attribution(name: str) -> Attribution:
    """The vendored 1.6 engine (fta_web/core FTACore) vs WebCore on a legacy
    file: identical except for OR-LOG, which is measured and attributed."""
    path = corpus_path(name)
    web = load_web(path)
    vendored = VendoredFTACore()
    ok, err = vendored.load_from_json(str(path))
    if not ok:
        return Attribution(name, False, [], ["vendored core cannot load: %s" % err])
    web_pos, ven_pos = positional(web.get_data()), positional(vendored.get_data())
    same_shape = _strip_calcs(web.get_data()) == _strip_calcs(vendored.get_data())
    if not same_shape:
        return Attribution(name, False, [], ["loaded trees differ (not only numbers)"])
    if web_pos == ven_pos:
        return Attribution(name, True, [], [])
    detail = []
    model = copy.deepcopy(vendored.get_data())
    for n in walk(model):
        n.pop("calculatedProbability", None)
    if vendored.mode == "ETA":
        return Attribution(name, False, [], ["ETA values differ"])
    legacy_walk(model, "tidy", "identity", "gate_only", "product")
    if positional(model) != ven_pos:
        return Attribution(name, False, [], ["model != vendored core"])
    legacy_walk(model, "tidy", "identity", "gate_only", "web")
    changed = [k for k in ven_pos if ven_pos[k] != web_pos[k]]
    if positional(model) != web_pos:
        return Attribution(name, False, [], ["UNEXPLAINED web/vendored difference"])
    worst = max(abs(web_pos[k] - ven_pos[k]) / max(abs(web_pos[k]), 1e-300) for k in changed)
    detail.append("%s changes %d node value(s), max rel %.2g, e.g. #%s %r -> %r" % (
        OR_LOG, len(changed), worst, changed[0], ven_pos[changed[0]], web_pos[changed[0]]))
    return Attribution(name, True, [OR_LOG], detail)


def _strip_calcs(tree: Any) -> Any:
    tree = copy.deepcopy(tree)
    for n in walk(tree):
        n.pop("calculatedProbability", None)
    return tree


# ---- 1.7 files in the desktop core ---------------------------------------------------------------


def desktop_compat(name: str, tmp: Path) -> Tuple[bool, List[str]]:
    """Check the USER_GUIDE "Desktop app compatibility" claims on one 1.7 file.

    Returns (ok, findings). A finding starting with ``FAIL`` is a broken claim.
    """
    from fta_web.node_schema import project_logic_gate

    findings: List[str] = []
    ok = True
    web = load_web(corpus_path(name))
    saved = tmp / ("web_" + name)
    web.save_to_json(str(saved))
    saved_doc = json.loads(saved.read_text(encoding="utf-8"))
    web_tree = web.get_data()
    web_by_id = {str(n.get("id")): n for n in walk(web_tree)}

    # Claim 1: logicGate is the AND/OR projection of gateType.
    for node in walk(saved_doc["tree"]):
        gt = node.get("gateType")
        if gt and node.get("logicGate") != project_logic_gate(gt):
            ok = False
            findings.append("FAIL projection: %s gateType %s logicGate %s"
                            % (node["id"], gt, node.get("logicGate")))
    # Claim 2: derived probability written into `probability`.
    for node in walk(saved_doc["tree"]):
        nid = str(node["id"])
        quant = node.get("quant") if isinstance(node.get("quant"), dict) else {}
        model = str(quant.get("model") or "fixed").lower()
        derived = engine.derive_quant(web_by_id[nid], web.analysis)
        if model != "fixed" and derived["q"] is not None and not node.get("children"):
            if node["probability"] != engine._tidy(derived["q"]):
                ok = False
                findings.append("FAIL derived q not written: %s" % nid)
        if str(node.get("eventKind") or "").lower() == "house" and not node.get("children"):
            if node["probability"] != (1.0 if node.get("houseState") is True else 0.0):
                ok = False
                findings.append("FAIL house probability: %s" % nid)
        if str(node.get("gateType") or "").upper() == "TRANSFER":
            if node["probability"] != web_by_id[nid]["calculatedProbability"]:
                ok = False
                findings.append("FAIL transfer probability: %s" % nid)
    # Claim 3: the desktop core computes AND/OR from logicGate + probability only
    # (with its own 6-decimal rounding and cycle rule: the baseline model).
    desk, err = run_desktop(saved)
    if desk is None:
        return False, findings + ["FAIL desktop cannot open the 1.7 file: %s" % err]
    model = copy.deepcopy(saved_doc["tree"])
    for n in walk(model):
        n.pop("calculatedProbability", None)
    if desk.mode == "ETA":
        legacy_eta(model, "round6")
    else:
        legacy_walk(model, "round6", "id", "base")
    if positional(model) != positional(desk.get_data()):
        ok = False
        findings.append("FAIL desktop numbers are not the AND/OR projection")
    # Claim 3b: for a tree whose gates all project exactly (AND/OR/INHIBIT,
    # no transfer children) the top event matches the web app up to D14.
    web_top = web_tree.get("calculatedProbability")
    desk_top = desk.get_data().get("calculatedProbability")
    kinds = {str(n.get("gateType") or "").upper() for n in walk(web_tree) if n.get("children")}
    transfer_kids = any(str(n.get("gateType") or "").upper() == "TRANSFER" and n.get("children")
                        for n in walk(web_tree))
    exact_projection = kinds <= {"", "AND", "OR", "INHIBIT"} and not transfer_kids
    if exact_projection and desk.mode != "ETA":
        unrounded = copy.deepcopy(saved_doc["tree"])
        for n in walk(unrounded):
            n.pop("calculatedProbability", None)
        legacy_walk(unrounded, "tidy", "identity", "gate_only", "web")
        if unrounded.get("calculatedProbability") != web_top:
            ok = False
            findings.append("FAIL AND/OR tree: projection %r != web %r"
                            % (unrounded.get("calculatedProbability"), web_top))
        else:
            findings.append("top web %r / desktop %r (difference = D14 rounding)"
                            % (web_top, desk_top))
    else:
        findings.append("advanced gates %s: desktop top %r vs web %r (projection, documented)"
                        % (sorted(k for k in kinds if k not in ("", "AND", "OR")), desk_top, web_top))
    # Claim 4: per-gate projection semantics on nodes without links.
    desk_by_id = {str(n.get("id")): n for n in walk(desk.get_data())}
    for node in walk(saved_doc["tree"]):
        gt = str(node.get("gateType") or "").upper()
        kids = node.get("children") or []
        if not kids or node.get("links") or gt in ("", "AND", "OR"):
            continue
        child_vals = [desk_by_id[str(c["id"])].get("calculatedProbability") for c in kids]
        got = desk_by_id[str(node["id"])].get("calculatedProbability")
        prod = 1.0
        for v in child_vals:
            prod *= v
        orv = 1.0
        for v in child_vals:
            orv *= 1 - v
        want = round(prod, 6) if gt in ("INHIBIT", "PAND") else round(1 - orv, 6)
        if got != want:
            ok = False
            findings.append("FAIL %s %s: desktop %r, projection %r" % (gt, node["id"], got, want))
    # Claim 5: desktop save keeps node keys, drops the analysis block.
    desk_saved = tmp / ("desk_" + name)
    desk.save_to_json(str(desk_saved))
    desk_doc = json.loads(desk_saved.read_text(encoding="utf-8"))
    if "analysis" in desk_doc:
        ok = False
        findings.append("FAIL desktop kept the analysis block")
    web_keys = {str(n["id"]): sorted(k for k in n if k != "calculatedProbability")
                for n in walk(saved_doc["tree"])}
    desk_keys = {str(n["id"]): sorted(k for k in n if k != "calculatedProbability")
                 for n in walk(desk_doc["tree"])}
    if web_keys != desk_keys:
        ok = False
        findings.append("FAIL desktop save lost node keys")
    # Claim 6: reopening the desktop-saved file in the web app restores the 1.7
    # numbers (models requantify with the *default* mission time).
    again = load_web(desk_saved)
    if again.analysis != engine.default_analysis():
        ok = False
        findings.append("FAIL analysis block not reset to defaults")
    fresh = copy.deepcopy(saved_doc)
    fresh.pop("analysis", None)
    fresh_path = tmp / ("noanalysis_" + name)
    fresh_path.write_text(json.dumps(fresh), encoding="utf-8")
    expect = load_web(fresh_path)
    if positional(again.get_data()) != positional(expect.get_data()):
        ok = False
        findings.append("FAIL web reopen of desktop save differs from the file without analysis")
    return ok, findings


# ---- oracle -------------------------------------------------------------------------------------


class NotApplicable(Exception):
    pass


MAX_ORACLE_VARS = 16


def _oracle_q(node: Dict[str, Any], mission: float) -> float:
    """q from the documented model formulas (independent of engine.derive_quant)."""
    quant = node.get("quant") if isinstance(node.get("quant"), dict) else {}
    model = str(quant.get("model") or "fixed").lower()

    def num(key):
        v = quant.get(key)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None

    lam = num("lambda")
    try:
        if model == "rate" and lam is not None:
            t = num("T") if num("T") is not None else mission
            return 1.0 - math.exp(-lam * t)
        if model == "standby" and lam is not None and num("tau") is not None:
            return min(1.0, lam * num("tau") / 2.0)
        if model == "repairable" and lam is not None:
            mu = num("mu")
            if mu is None and num("mttr"):
                mu = 1.0 / num("mttr")
            if mu is not None and lam + mu > 0:
                return lam / (lam + mu)
    except (TypeError, ValueError):
        pass
    return float(node.get("probability", 1.0))


_PROJ = {"AND": "AND", "INHIBIT": "AND", "PAND": "AND", "OR": "OR", "KOFN": "OR", "XOR": "OR",
         "TRANSFER": "OR"}


@dataclass
class OracleResult:
    names: List[str]
    q: List[float]
    exact: float
    exact_or: float  # XOR read as OR (the cut sets' Boolean model)
    min_sets: List[Tuple[str, ...]]
    repeated: List[str]
    coherent: bool


def oracle(document: Any, max_vars: int = MAX_ORACLE_VARS) -> OracleResult:
    """Exact top-event probability and minimal cut sets by enumerating all 2^n
    event states. Independent of the engine: its own reading of the file, the
    model formulas, gate logic, links and transfers as USER_GUIDE documents
    them. Raises NotApplicable for PAND, cycles, ETA, or too many events."""
    if isinstance(document, dict) and document.get("mode") == "ETA":
        raise NotApplicable("ETA")
    analysis = document.get("analysis") if isinstance(document, dict) else None
    mission = float((analysis or {}).get("missionTime") or 8760.0)
    tree = raw_tree(document)
    index: Dict[str, Dict[str, Any]] = {}
    for n in walk(tree):
        nid = str(n.get("id"))
        if nid in index:
            raise NotApplicable("duplicate ids")
        index[nid] = n

    def gate_of(node):
        logic = str(node.get("logicGate") or "OR").strip().upper()
        gt = node.get("gateType")
        if isinstance(gt, str) and gt.strip():
            gt = gt.strip().upper()
            if _PROJ.get(gt, "OR") == logic:  # a stale gateType yields to logicGate
                return gt
        return "AND" if logic == "AND" else "OR"

    # Variables: leaves that are not house events, in pre-order.
    names: List[str] = []
    qs: List[float] = []
    for n in walk(tree):
        if not (n.get("children") or []) and gate_of(n) != "TRANSFER" \
                and str(n.get("eventKind") or "").lower() != "house":
            names.append(str(n.get("id")))
            qs.append(_oracle_q(n, mission))
    nvar = len(names)
    if nvar > max_vars:
        raise NotApplicable("%d events" % nvar)
    states = 1 << nvar
    full = (1 << states) - 1
    cols = {}
    for i, nid in enumerate(names):
        block = 1 << i
        pattern = ((1 << block) - 1) << block
        period = 1 << (i + 1)
        cols[nid] = pattern * (full // ((1 << period) - 1))

    def kofn(masks, k):
        if k > len(masks):
            return 0
        at_least = [full] + [0] * k
        for m in masks:
            for j in range(k, 0, -1):
                at_least[j] = at_least[j] | (at_least[j - 1] & m)
        return at_least[k]

    def evaluate(xor_as_or: bool):
        memo: Dict[int, int] = {}
        stack = set()
        paths: Dict[str, int] = {}

        def f(node) -> int:
            key = id(node)
            if key in memo:
                return memo[key]
            if key in stack:
                raise NotApplicable("cycle")
            stack.add(key)
            g = gate_of(node)
            kids = node.get("children") or []
            if g == "TRANSFER":
                target = index.get(str(node.get("transferTo")))
                base = 0 if target is None or target is node else f(target)
            elif not kids:
                if str(node.get("eventKind") or "").lower() == "house":
                    base = full if node.get("houseState") is True else 0
                else:
                    base = cols[str(node.get("id"))]
            else:
                vals = [f(c) for c in kids]
                if g in ("AND", "INHIBIT"):
                    base = full
                    for v in vals:
                        base &= v
                elif g == "PAND":
                    raise NotApplicable("PAND")
                elif g == "KOFN":
                    k = node.get("k")
                    if isinstance(k, float) and k.is_integer():
                        k = int(k)
                    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
                        raise NotApplicable("invalid k")
                    base = kofn(vals, k)
                elif g == "XOR" and not xor_as_or:
                    base = 0
                    for v in vals:
                        base ^= v
                else:
                    base = 0
                    for v in vals:
                        base |= v
            ands, ors = [], []
            for link in node.get("links") or []:
                tid = link.get("target_id")
                if not tid or str(tid) not in index:
                    continue
                rel = str(link.get("relation") or "OR").upper()
                (ands if rel == "AND" else ors).append(f(index[str(tid)]))
            for v in ands:
                base &= v
            for v in ors:
                base |= v
            stack.discard(key)
            memo[key] = base
            return base

        return f(tree)

    # Path counting for repeated events (tree expansion, bounded).
    counts: Dict[str, int] = {}
    budget = [200000]

    def count(node, depth=0):
        budget[0] -= 1
        if budget[0] < 0 or depth > 400:
            raise NotApplicable("expansion too large")
        g = gate_of(node)
        kids = node.get("children") or []
        if g == "TRANSFER":
            target = index.get(str(node.get("transferTo")))
            if target is not None and target is not node:
                count(target, depth + 1)
        elif not kids:
            if str(node.get("eventKind") or "").lower() != "house":
                nid = str(node.get("id"))
                counts[nid] = counts.get(nid, 0) + 1
        else:
            for c in kids:
                count(c, depth + 1)
        for link in node.get("links") or []:
            tid = link.get("target_id")
            if tid and str(tid) in index:
                count(index[str(tid)], depth + 1)

    top = evaluate(False)
    top_or = evaluate(True)
    count(tree)

    weights = [1.0]
    for q in qs:
        weights = [w * (1.0 - q) for w in weights] + [w * q for w in weights]

    def prob(mask):
        bits = bin(mask)[2:][::-1]
        return math.fsum(weights[s] for s, b in enumerate(bits) if b == "1")

    min_sets = []
    bits = bin(top_or)[2:][::-1]
    for s, b in enumerate(bits):
        if b != "1":
            continue
        minimal = True
        rest = s
        while rest:
            low = rest & -rest
            rest ^= low
            if (top_or >> (s ^ low)) & 1:
                minimal = False
                break
        if minimal:
            min_sets.append(tuple(sorted(names[i] for i in range(nvar) if (s >> i) & 1)))
    coherent = top == top_or
    return OracleResult(names, qs, prob(top), prob(top_or), sorted(min_sets),
                        sorted(n for n, c in counts.items() if c > 1), coherent)


#: The engine keeps 12 significant figures (``_tidy``, D14) at every gate, so
#: a value derived through a few gates agrees with the closed form to ~1e-11.
TIDY_REL = 1e-10


def check_oracle(name: str, ref: Dict[str, Any]) -> List[Row]:
    """Truth-table oracle vs the engine. [] when the oracle does not apply."""
    try:
        o = oracle(raw_document(name))
    except NotApplicable:
        return []
    core = ref["_core"]
    tree_walk = core.get_data()["calculatedProbability"]
    full = cutsets_mod.compute(copy.deepcopy(core.get_data()), copy.deepcopy(core.analysis),
                               {"maxOrder": 20, "maxCount": 1000000, "cutoff": 0.0})
    sets = sorted(tuple(sorted(e["id"] for e in c["events"])) for c in full["cutSets"])
    repeated = sorted(e["id"] for e in full["repeatedEvents"])
    probs = []
    for s in o.min_sets:
        p = 1.0
        for nid in s:
            p *= o.q[o.names.index(nid)]
        probs.append(p)
    rows = [
        compare(name, "oracle", "minimalCutSets", {"sets": tuple(o.min_sets)},
                {"sets": tuple(sets)}),
        compare(name, "oracle", "repeatedEvents", {"ids": tuple(o.repeated)},
                {"ids": tuple(repeated)}),
        compare(name, "oracle", "mcub(min sets)", {"mcub": cutsets_mod.mcub_of(probs)},
                {"mcub": full["mcub"]}, rel=TIDY_REL),
        compare(name, "oracle", "q", dict(zip(o.names, o.q)),
                {n: ref["prob"][n] for n in o.names}, rel=TIDY_REL),
    ]
    rows += _oracle_truncation(name, ref, o)
    rows += _oracle_importance(name, ref, o)
    if not repeated:
        rows.append(compare(name, "oracle", "treeWalk==exact", {"top": o.exact},
                            {"top": tree_walk}, rel=TIDY_REL,
                            note="no repeated events: the tree walk is exact"))
    if o.coherent:
        # Esary-Proschan: MCUB >= exact for a coherent tree; rare-event >= MCUB.
        slack = 1.0 - TIDY_REL
        bound = full["mcub"] >= o.exact * slack and full["rareEvent"] >= full["mcub"] * slack
        rows.append(compare(name, "oracle", "rare>=MCUB>=exact", {"holds": True},
                            {"holds": bound},
                            note="exact %.6g mcub %.6g rare %.6g" % (o.exact, full["mcub"],
                                                                     full["rareEvent"])))
    return rows


def _oracle_truncation(name: str, ref: Dict[str, Any], o: "OracleResult") -> List[Row]:
    """The engine's cut sets under the document's limits must be exactly the
    oracle's minimal sets of order <= maxOrder and P >= cutoff (truncating
    inside the products is sound for order and cutoff; count is not tested:
    the small trees stay under it)."""
    cut = ref.get("cutsets") or {}
    if "error" in cut:
        return []
    limits = ref["_core"].analysis.get("cutsets") or {}
    max_order, cutoff = limits.get("maxOrder", 6), limits.get("cutoff", 1e-15)
    kept = []
    for s in o.min_sets:
        p = 1.0
        for nid in sorted(s, key=o.names.index):
            p *= ref["prob"][nid]
        if len(s) <= max_order and p >= cutoff:
            kept.append(",".join(sorted(s)))
    got = sorted(v for k, v in cut.items() if k.startswith("set/"))
    return [compare(name, "oracle", "truncated sets==filtered minimal sets",
                    {"sets": tuple(sorted(kept))}, {"sets": tuple(got)},
                    note="maxOrder %s, cutoff %g" % (max_order, cutoff))]


def _oracle_importance(name: str, ref: Dict[str, Any], o: "OracleResult") -> List[Row]:
    """FV, Birnbaum, RAW, RRW on the MCUB of the (untruncated) minimal cut
    sets, in exact rational arithmetic with the engine's own q values --
    independent of importance.py's inverted index and log-space sums."""
    from fractions import Fraction

    if not o.min_sets or len(o.min_sets) > 60:
        return []
    core = ref["_core"]
    full = cutsets_mod.compute(copy.deepcopy(core.get_data()), copy.deepcopy(core.analysis),
                               {"maxOrder": 20, "maxCount": 1000000, "cutoff": 0.0})
    measures = {m["id"]: m for m in importance.compute(full)}
    q = {nid: Fraction(ref["prob"][nid]) for s in o.min_sets for nid in s}

    def top(override=None):
        prod = Fraction(1)
        for s in o.min_sets:
            p = Fraction(1)
            for nid in s:
                p *= override[1] if override and nid == override[0] else q[nid]
            prod *= 1 - p
        return 1 - prod

    base = top()
    want, got = {}, {}
    for nid in sorted(q):
        if nid not in measures or q[nid] == 0:
            continue
        q0, q1 = top((nid, Fraction(0))), top((nid, Fraction(1)))
        m = measures[nid]
        want["%s/birnbaum" % nid] = float(q1 - q0)
        got["%s/birnbaum" % nid] = m["birnbaum"]
        if base > 0:
            want["%s/fv" % nid] = float((base - q0) / base)
            want["%s/raw" % nid] = float(q1 / base)
            got["%s/fv" % nid] = m["fv"]
            got["%s/raw" % nid] = m["raw"]
            if q0 > 0:
                want["%s/rrw" % nid] = float(base / q0)
                got["%s/rrw" % nid] = m["rrw"]
            else:
                want["%s/rrwInfinite" % nid] = True
                got["%s/rrwInfinite" % nid] = m["rrwInfinite"]
    return [compare(name, "oracle", "importance (exact rational)", want, got, rel=1e-12,
                    abs_tol=1e-300)]


def check_expected(name: str, ref: Dict[str, Any], exp: Dict[str, Any]) -> List[Row]:
    """The hand-computed values of expected.json against the engine."""
    rows: List[Row] = []
    core = ref["_core"]
    summary = ref.get("summary") or {}
    cut = ref.get("_cut_raw") or {}
    got_top = {"top": core.get_data().get("calculatedProbability")}
    if "top" in exp:
        rows.append(compare(name, "expected", "top", {"top": exp["top"]}, got_top, rel=TIDY_REL))
    if "treeWalk" in exp:
        rows.append(compare(name, "expected", "treeWalk", {"treeWalk": exp["treeWalk"]},
                            {"treeWalk": got_top["top"]}, rel=TIDY_REL))
    if "nodes" in exp:
        rows.append(compare(name, "expected", "nodes", exp["nodes"],
                            {k: ref["calc"].get(k) for k in exp["nodes"]}, rel=TIDY_REL))
    if "q" in exp:
        rows.append(compare(name, "expected", "q", exp["q"],
                            {k: ref["prob"].get(k) for k in exp["q"]}, rel=TIDY_REL))
    for key in ("mcub", "rareEvent"):
        if key in exp:
            rows.append(compare(name, "expected", key, {key: exp[key]}, {key: cut.get(key)},
                                rel=TIDY_REL))
    if "headlineMethod" in exp:
        rows.append(compare(name, "expected", "headlineMethod",
                            {"m": exp["headlineMethod"]}, {"m": summary.get("headlineMethod")}))
    if "cutsets" in exp:
        got = sorted(tuple(sorted(e["id"] for e in c["events"])) for c in cut.get("cutSets", []))
        rows.append(compare(name, "expected", "cutsets",
                            {"sets": tuple(sorted(tuple(s) for s in exp["cutsets"]))},
                            {"sets": tuple(got)}))
    if "exact_top" in exp:
        try:
            o = oracle(raw_document(name))
            rows.append(compare(name, "expected", "exact(oracle)", {"exact": exp["exact_top"]},
                                {"exact": o.exact}, rel=TIDY_REL))
        except NotApplicable:
            pass
    if "importance" in exp:
        imp = ref.get("importance") or {}
        want, got = {}, {}
        for nid, measures in exp["importance"].items():
            for key, value in measures.items():
                want["%s/%s" % (nid, key)] = value
                got["%s/%s" % (nid, key)] = imp.get("%s/%s" % (nid, key))
        rows.append(compare(name, "expected", "importance", want, got, rel=TIDY_REL))
    if "rpn" in exp:
        from fta_web.excel_events import event_rows

        rpn = {str(r["Id"]): r["RPN"] for r in event_rows(core.get_data())}
        rows.append(compare(name, "expected", "rpn", exp["rpn"],
                            {k: rpn.get(k) for k in exp["rpn"]}))
    return rows


def check_mc(name: str, ref: Dict[str, Any], exp: Optional[Dict[str, Any]] = None,
             n_analytic: int = 20000) -> List[Row]:
    """Monte Carlo sanity: without uncertainty every sample is the point
    estimate; the point estimate is the tree walk (method tree) or the MCUB
    (method cutsets); lognormal means agree with the analytical ones."""
    rows: List[Row] = []
    mc = ref.get("mc") or {}
    if not mc or "error" in mc:
        return rows
    if not mc["uncertainEvents"]:
        rows.append(compare(name, "mc", "no-uncertainty==point",
                            {k: mc["pointEstimate"] for k in ("mean", "median", "p05", "p95")}
                            | {"std": 0.0},
                            {k: mc[k] for k in ("mean", "median", "p05", "p95", "std")}))
    cut = ref.get("_cut_raw") or {}
    if mc["method"] == "tree":
        rows.append(compare(name, "mc", "point==treeWalk", {"v": ref["summary"]["treeWalk"]},
                            {"v": mc["pointEstimate"]}, rel=TIDY_REL,
                            note="the MC evaluator does not _tidy (D14) at each gate"))
    elif cut and "MC_CUTSETS_TRUNCATED" not in mc["warnings"]:
        rows.append(compare(name, "mc", "point==mcub", {"v": cut["mcub"]},
                            {"v": mc["pointEstimate"]}, rel=1e-15))
    if exp and exp.get("mc_means"):
        core = ref["_core"]
        index = {str(n.get("id")): n for n in walk(core.get_data())}
        want, got, tol = {}, {}, {}
        for nid, mean in exp["mc_means"].items():
            sub = copy.deepcopy(index[nid])
            sub["id"] = "root"
            r = uncertainty.run(sub, copy.deepcopy(core.analysis), n=n_analytic, seed=MC_SEED,
                                time_limit=MC_TIME_LIMIT)
            want[nid] = mean
            got[nid] = r["mean"]
            tol[nid] = 5.0 * r["std"] / math.sqrt(r["completed"])  # 5 standard errors
        row = compare(name, "mc", "mean~analytical(5SE)", want, got)
        row.status = "match"
        row.diffs = []
        for nid in want:
            if abs(want[nid] - got[nid]) > tol[nid]:
                row.status = "mismatch"
                row.diffs.append((nid, want[nid], got[nid]))
        rows.append(row)
    return rows


def check_engine_internal(name: str, ref: Dict[str, Any]) -> List[Row]:
    """Cross-metric checks inside the engine path (intended divergences
    measured, not hidden): the derived q vs the stored probability (tidied
    to 12 s.f.), summary vs cut sets, importance top value vs MCUB."""
    rows = []
    q = {k: v for k, v in ref["qDerived"].items() if v is not None}
    core = ref["_core"]
    leaves = {str(n.get("id")) for n in walk(core.get_data())
              if not n.get("children") and isinstance(n.get("quant"), dict)
              and str(n["quant"].get("model") or "fixed").lower() != "fixed"}
    if leaves & set(q):
        rows.append(compare(name, "engine", "quantDerived.q~probability",
                            {k: q[k] for k in leaves & set(q)},
                            {k: ref["prob"][k] for k in leaves & set(q)}, rel=TIDY_REL,
                            note="probability = _tidy(q), 12 s.f."))
    cut = ref.get("cutsets") or {}
    s = ref.get("summary") or {}
    if cut and "error" not in cut and s and not s.get("capped") and not s.get("truncated") \
            and not cut.get("truncated") and s.get("mcub") is not None:
        rows.append(compare(name, "engine", "summary==cutsets",
                            {k: cut[k] for k in ("mcub", "rareEvent", "treeWalk")},
                            {k: s[k] for k in ("mcub", "rareEvent", "treeWalk")}))
    return rows


# ---- JS formatter parity -----------------------------------------------------------------------


def node_available() -> bool:
    return shutil.which("node") is not None


def js_format(values: Sequence[float], sig_figs: Sequence[int]) -> Optional[Dict[str, str]]:
    """``static/js/numfmt.js`` ``formatProb`` over values x sig figs, run by
    node (None when node is not installed). Keyed ``"<index>@<sf>"``."""
    node = shutil.which("node")
    if not node:
        return None
    module = (FTA_WEB / "static" / "js" / "numfmt.js").as_uri()
    # The values go through stdin: a large corpus overflows the command line.
    script = (
        "let raw = ''; process.stdin.on('data', c => raw += c); process.stdin.on('end', () =>"
        " import(%s).then(m => {const [vs, sfs] = JSON.parse(raw); const out = {};"
        "vs.forEach((v, i) => { for (const sf of sfs) out[i + '@' + sf] = m.formatProb(v, sf); });"
        "process.stdout.write(JSON.stringify(out));}));" % json.dumps(module))
    proc = subprocess.run([node, "--input-type=module", "-e", script],
                          input=json.dumps([list(values), list(sig_figs)]).encode("utf-8"),
                          capture_output=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace"))
    return json.loads(proc.stdout.decode("utf-8"))


def py_format(values: Sequence[float], sig_figs: Sequence[int]) -> Dict[str, str]:
    """``numfmt.format_prob`` keyed like :func:`js_format`."""
    return {"%d@%d" % (i, sf): format_prob(v, sf) for i, v in enumerate(values) for sf in sig_figs}


def format_probe_values(results: Iterable[Dict[str, Any]] = ()) -> List[float]:
    """Edge cases of the formatting rules plus every number the corpus produced."""
    values = [1e-7, 1.234e-7, 0.5, 0.123456, 0.0123456, 0.001, 0.00099996, 0.000999, 1.0,
              1234.0, 12345.0, 9999.7, 999.96, 99.996, 0.0099996, 0.99996, 1.5, 12.3456,
              123.456, 5000.4, 2.5e-12, 0.30000000000000004, 1e4, 1e-3, 0.0009995, 0.00099949,
              -2e-5, 585.0746, 9238.778557185406, 25000.0]
    seen = set(values)
    for res in results:
        for metric in ("calc", "prob", "summary", "importance", "mc"):
            for value in (res.get(metric) or {}).values():
                if _num(value) and value not in seen and math.isfinite(value):
                    seen.add(value)
                    values.append(float(value))
    return values
