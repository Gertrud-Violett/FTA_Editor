"""
The ``.xlsx`` export: the core's workbook plus "Events" and "Analysis" sheets.

:func:`export_xlsx` lets ``core.export_to_excel`` write its hierarchical "FTA"
sheet exactly as in 1.6 (the core is hash-pinned and is not edited), then
re-opens that workbook with openpyxl and appends:

* **Events** -- one row per node in tree (pre-)order with the identity,
  structure, quantification, traceability and FMEA columns of
  :data:`EVENT_COLUMNS`. Numbers are written as numbers (never strings) with a
  scientific ``number_format`` at the requested significant figures, so Excel
  can sort, filter and compute on them. Header bold, frozen, auto-filtered.
* **Analysis** -- the document's ``analysis`` settings (mission time, cut-set
  limits, Monte Carlo defaults) and, in FTA mode, the headline figures from
  ``engine.summary``.

A pre-existing sheet of either name is replaced. No images, so no PIL.

Text is passed through :func:`xml_text` on the way into any sheet: a
character XML cannot hold makes openpyxl raise, which lost the whole export.
The core writes its sheet from :func:`export_view`, a cleaned copy of the
document, for the same reason (the routes' XML export uses it too).
"""
from __future__ import annotations

import copy
import math
import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

try:  # normal package import: ``import fta_web.excel_events``
    from .numfmt import clamp_sig_figs
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    from numfmt import clamp_sig_figs  # type: ignore[no-redef]

EVENTS_SHEET = "Events"
ANALYSIS_SHEET = "Analysis"

#: (header, kind) in column order. kind: "text" | "num" | "int" | "prob".
EVENT_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("Id", "text"),
    ("Name", "text"),
    ("Parent Id", "text"),
    ("Depth", "int"),
    ("Node type", "text"),
    ("Gate type", "text"),
    ("k", "int"),
    ("Event kind", "text"),
    ("House state", "text"),
    ("Transfer to", "text"),
    ("Model", "text"),
    ("λ (/h)", "num"),
    ("T (h)", "num"),
    ("τ (h)", "num"),
    ("μ (/h)", "num"),
    ("MTTR (h)", "num"),
    ("Base probability", "prob"),
    ("Calculated probability", "prob"),
    ("Source", "text"),
    ("Unc. dist", "text"),
    ("Unc. median", "num"),
    ("Unc. mean", "num"),
    ("Unc. EF", "num"),
    ("Requirement ID", "text"),
    ("Test ref", "text"),
    ("Owner", "text"),
    ("Status", "text"),
    ("Evidence", "text"),
    ("Tags", "text"),
    ("FMEA ID", "text"),
    ("FMEA item", "text"),
    ("FMEA mode", "text"),
    ("FMEA cause", "text"),
    ("S", "int"),
    ("O", "int"),
    ("D", "int"),
    ("RPN", "int"),
)

EVENT_HEADERS = tuple(name for name, _kind in EVENT_COLUMNS)


def sci_format(sig_figs: Any) -> str:
    """An Excel number format showing ``sig_figs`` significant figures in
    scientific notation (``0.00E+00`` for 3)."""
    sf = clamp_sig_figs(sig_figs)
    return "0" + ("." + "0" * (sf - 1) if sf > 1 else "") + "E+00"


def iter_nodes(tree: Any) -> Iterator[Tuple[Dict[str, Any], Optional[str], int]]:
    """``(node, parent_id, depth)`` in pre-order (the order of the tree view).

    Iterative, and guarded against a node object appearing twice (the core
    never builds one, but a hand-edited file could alias).
    """
    if not isinstance(tree, dict) or not tree:
        return
    seen = set()
    stack: List[Tuple[Dict[str, Any], Optional[str], int]] = [(tree, None, 0)]
    while stack:
        node, parent, depth = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        yield node, parent, depth
        children = [c for c in (node.get("children") or []) if isinstance(c, dict)]
        for child in reversed(children):
            stack.append((child, str(node.get("id")), depth + 1))


def _number(value: Any) -> Optional[float]:
    """A finite float, or None. NaN and infinities (Python's json reads the
    bare ``NaN``/``Infinity`` literals) have no Excel representation: openpyxl
    writes them as an empty numeric cell (``<v></v>``), which is malformed
    SpreadsheetML, so they are left blank instead."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value) if isinstance(value, (int, float)) else float(str(value).strip())
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> Optional[int]:
    number = _number(value)
    if number is None:
        return None
    try:
        return int(round(number))
    except (OverflowError, ValueError):
        return None


def _text(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value if v not in (None, "")) or None
    return str(value)


#: What XML 1.0 cannot hold at all -- C0 controls other than tab, newline and
#: carriage return, lone surrogates, U+FFFE/U+FFFF -- and so neither can an
#: .xlsx, a .docx or the XML export: openpyxl and python-docx raise on them,
#: and ElementTree writes a file no parser accepts. They reach a tree through
#: pasted text (PowerPoint's soft line break is \x0b, a Word cell mark \x07),
#: which only names are cleaned of, and through hand-edited or third-party
#: files.
_NOT_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


def xml_text(value: Any) -> str:
    """``str(value)`` ("" for None) without the characters XML cannot hold.

    The whitespace-like ones (\\x0b, \\x0c, \\x1c-\\x1f) become a space, as
    the core's ``sanitize_name`` makes them in names; the rest are dropped.
    """
    text = "" if value is None else str(value)
    if _NOT_XML.search(text) is None:
        return text
    return _NOT_XML.sub(lambda m: " " if m.group().isspace() else "", text)


#: The node keys the core's own writers (``export_to_excel``,
#: ``export_to_xml``) put into the file, and a link's.
_CORE_TEXT_KEYS = ("name", "type", "logicGate", "notes")
_CORE_LINK_KEYS = ("target_id", "relation")


def export_view(core):
    """A shallow copy of ``core`` for the core's hash-pinned writers.

    Its tree is a deep copy in which every text the writers emit has been
    through :func:`xml_text`, so ``export_to_excel`` does not raise on a
    control character (losing the whole workbook) and ``export_to_xml``
    does not write a file no parser accepts -- or raise on a non-string
    ``type``/``notes`` from a hand-edited file. Text that needs no cleaning
    is left as it is, so an ordinary document exports byte for byte as
    before. ``core`` itself is not modified.
    """
    view = copy.copy(core)
    tree = copy.deepcopy(core.get_data())
    for node, _parent, _depth in iter_nodes(tree):
        for key in _CORE_TEXT_KEYS:
            if key in node and not (isinstance(node[key], str) and _NOT_XML.search(node[key]) is None):
                node[key] = xml_text(node[key])
        for link in node.get("links") or []:
            if not isinstance(link, dict):
                continue
            for key in _CORE_LINK_KEYS:
                value = link.get(key)
                if value is not None and not (isinstance(value, str) and _NOT_XML.search(value) is None):
                    link[key] = xml_text(value)
    view.fta_data = tree
    return view


def node_kind(node: Dict[str, Any]) -> str:
    """``gate`` for a node with children or an explicit gate type, else ``event``."""
    if node.get("children"):
        return "gate"
    if str(node.get("gateType") or "").upper() == "TRANSFER":
        return "gate"
    return "event"


def gate_type(node: Dict[str, Any]) -> Optional[str]:
    """``gateType`` when set, else the legacy ``logicGate`` -- gates only."""
    if node_kind(node) != "gate":
        return None
    raw = node.get("gateType") or node.get("logicGate") or "OR"
    return str(raw).strip().upper() or None


def event_row(node: Dict[str, Any], parent_id: Optional[str], depth: int) -> Dict[str, Any]:
    """One node as ``{header: raw value}`` (numbers stay numbers)."""
    quant = node.get("quant") if isinstance(node.get("quant"), dict) else {}
    unc = quant.get("unc") if isinstance(quant.get("unc"), dict) else {}
    trace = node.get("trace") if isinstance(node.get("trace"), dict) else {}
    fmea = node.get("fmea") if isinstance(node.get("fmea"), dict) else {}
    kind = node_kind(node)
    gtype = gate_type(node)
    house = node.get("houseState")
    event_kind = node.get("eventKind") if kind == "event" else node.get("eventKind")
    model = quant.get("model") if quant else None
    if kind == "event" and not model:
        model = "fixed"
    unc_dist = unc.get("dist") if unc else None
    rpn = fmea.get("rpn")
    if rpn in (None, "") and all(
        _integer(fmea.get(k)) is not None for k in ("severity", "occurrence", "detection")
    ):
        rpn = _integer(fmea["severity"]) * _integer(fmea["occurrence"]) * _integer(fmea["detection"])
    raw = {
        "Id": node.get("id"),
        "Name": node.get("name"),
        "Parent Id": parent_id,
        "Depth": depth,
        "Node type": kind,
        "Gate type": gtype,
        "k": node.get("k") if gtype == "KOFN" else None,
        "Event kind": event_kind or ("basic" if kind == "event" else None),
        "House state": (None if house is None else ("true" if house is True else "false"))
        if str(event_kind or "").lower() == "house" else None,
        "Transfer to": node.get("transferTo") if gtype == "TRANSFER" else None,
        "Model": model,
        "λ (/h)": quant.get("lambda"),
        "T (h)": quant.get("T"),
        "τ (h)": quant.get("tau"),
        "μ (/h)": quant.get("mu"),
        "MTTR (h)": quant.get("mttr"),
        "Base probability": node.get("probability"),
        "Calculated probability": node.get("calculatedProbability"),
        "Source": quant.get("source"),
        "Unc. dist": unc_dist,
        "Unc. median": unc.get("median"),
        "Unc. mean": unc.get("mean"),
        "Unc. EF": unc.get("ef"),
        "Requirement ID": trace.get("requirementId"),
        "Test ref": trace.get("testRef"),
        "Owner": trace.get("owner"),
        "Status": trace.get("status"),
        "Evidence": trace.get("evidence"),
        "Tags": trace.get("tags"),
        "FMEA ID": fmea.get("id"),
        "FMEA item": fmea.get("item"),
        "FMEA mode": fmea.get("mode"),
        "FMEA cause": fmea.get("cause"),
        "S": fmea.get("severity"),
        "O": fmea.get("occurrence"),
        "D": fmea.get("detection"),
        "RPN": rpn,
    }
    out: Dict[str, Any] = {}
    for header, col_kind in EVENT_COLUMNS:
        value = raw.get(header)
        if col_kind in ("num", "prob"):
            out[header] = _number(value)
        elif col_kind == "int":
            out[header] = _integer(value)
        else:
            out[header] = _text(value)
    return out


def event_rows(tree: Any) -> List[Dict[str, Any]]:
    """Every node of ``tree`` as :func:`event_row` dicts, in tree order."""
    return [event_row(n, p, d) for n, p, d in iter_nodes(tree)]


def _summary(tree: Any, analysis: Any) -> Optional[Dict[str, Any]]:
    try:
        try:
            from .engine import summary
        except ImportError:
            from engine import summary  # type: ignore[no-redef]
        return summary(tree, analysis)
    except Exception:  # a summary failure must not lose the export
        return None


#: Analysis-sheet rows whose value is a probability.
PROBABILITY_SETTINGS = frozenset((
    "Cut sets: cutoff", "Top event (headline)", "Tree walk", "MCUB", "Rare-event approximation",
))


def analysis_rows(core) -> List[Tuple[str, Any, str]]:
    """``(setting, value, note)`` rows for the Analysis sheet."""
    analysis = copy.deepcopy(getattr(core, "analysis", None) or {})
    cut = analysis.get("cutsets") or {}
    mc = analysis.get("mc") or {}
    rows: List[Tuple[str, Any, str]] = [
        ("Title", getattr(core, "title", "") or "", ""),
        ("Date", getattr(core, "date", "") or "", ""),
        ("Mode", getattr(core, "mode", "FTA") or "FTA", ""),
        ("Mission time (h)", _number(analysis.get("missionTime")), "stored in hours"),
        ("Display time unit", analysis.get("timeUnit") or "h", ""),
        ("Cut sets: max order", _integer(cut.get("maxOrder")), ""),
        ("Cut sets: max count", _integer(cut.get("maxCount")), ""),
        ("Cut sets: cutoff", _number(cut.get("cutoff")), "probability"),
        ("Monte Carlo: samples", _integer(mc.get("n")), ""),
        ("Monte Carlo: seed", mc.get("seed") if mc.get("seed") is not None else "", ""),
    ]
    if (getattr(core, "mode", "FTA") or "FTA") != "ETA":
        summ = _summary(copy.deepcopy(core.get_data()), analysis)
        if summ:
            rows.extend([
                ("Top event (headline)", _number(summ.get("headline")),
                 "method: %s" % (summ.get("headlineMethod") or "treeWalk")),
                ("Tree walk", _number(summ.get("treeWalk")), ""),
                ("MCUB", _number(summ.get("mcub")), "min-cut upper bound"),
                ("Rare-event approximation", _number(summ.get("rareEvent")), ""),
                ("Repeated events", len(summ.get("repeatedEvents") or []), ""),
                ("Non-coherent (XOR)", "yes" if summ.get("nonCoherent") else "no", ""),
                ("Approximations flagged", len(summ.get("approximations") or []), ""),
                ("Cut sets truncated", "yes" if summ.get("truncated") else "no", ""),
            ])
    else:
        rows.append(("Summary", "", "not available in ETA mode"))
    return rows


def _as_text(cell) -> None:
    """Keep a text cell text. openpyxl stores any string that starts with
    '=' as a formula, so a node named '=HYPERLINK(...)' (from a supplier's
    tree or FMEA sheet) became a live link, and '=1+1' showed as 2."""
    if cell.data_type == "f":
        cell.data_type = "s"


def _replace_sheet(wb, title: str):
    if title in wb.sheetnames:
        index = wb.sheetnames.index(title)
        wb.remove(wb[title])
        return wb.create_sheet(title, index)
    return wb.create_sheet(title)


def _write_events(wb, tree: Any, sig_figs: int) -> None:
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    ws = _replace_sheet(wb, EVENTS_SHEET)
    ws.append(list(EVENT_HEADERS))
    bold = Font(bold=True)
    for cell in ws[1]:
        cell.font = bold
    fmt = sci_format(sig_figs)
    widths = [len(h) for h in EVENT_HEADERS]
    for row in event_rows(tree):
        for header, kind in EVENT_COLUMNS:
            if kind == "text" and row[header] is not None:
                row[header] = xml_text(row[header]) or None
        ws.append([row[h] for h in EVENT_HEADERS])
        row_idx = ws.max_row
        for col_idx, (header, kind) in enumerate(EVENT_COLUMNS, start=1):
            value = row[header]
            if value is None:
                continue
            if kind in ("num", "prob"):
                ws.cell(row=row_idx, column=col_idx).number_format = fmt
                widths[col_idx - 1] = max(widths[col_idx - 1], sig_figs + 6)
            else:
                if kind == "text":
                    _as_text(ws.cell(row=row_idx, column=col_idx))
                widths[col_idx - 1] = max(widths[col_idx - 1], len(str(value)))
    for col_idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max(width + 2, 6), 50)
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = "A1:%s%d" % (get_column_letter(len(EVENT_HEADERS)), max(ws.max_row, 1))


def _write_analysis(wb, core, sig_figs: int) -> None:
    from openpyxl.styles import Font

    ws = _replace_sheet(wb, ANALYSIS_SHEET)
    ws.append(["Setting", "Value", "Note"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    fmt = sci_format(sig_figs)
    for setting, value, note in analysis_rows(core):
        if not (value is None or isinstance(value, (int, float))):
            value = xml_text(value)  # title, date, mode: text from the file
        ws.append([setting, value, note])
        _as_text(ws.cell(row=ws.max_row, column=2))
        # Probabilities get the scientific format; hours and counts stay
        # General (8760 h, not 8.76E+03).
        if isinstance(value, float) and setting in PROBABILITY_SETTINGS:
            ws.cell(row=ws.max_row, column=2).number_format = fmt
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 30
    ws.freeze_panes = "A2"


def export_xlsx(core, path: str, sig_figs: int = 3) -> Tuple[bool, Optional[str]]:
    """Write ``core``'s document to ``path`` as .xlsx. ``(ok, error)``.

    The "FTA" sheet is the core's, untouched -- written from
    :func:`export_view`, so it never fails on a control character. The
    caller holds the state lock (``routes/files.py`` does) -- the tree is
    read, never modified.
    """
    ok, error = export_view(core).export_to_excel(path)
    if not ok:
        return ok, error
    try:
        from openpyxl import load_workbook

        sf = clamp_sig_figs(sig_figs)
        wb = load_workbook(path)
        # The core writes text only; a "formula" in its sheet is a name that
        # starts with '=' (and, with its '\n(Type: ...)' tail, a broken one
        # Excel offers to repair).
        for sheet in wb.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    _as_text(cell)
        _write_events(wb, core.get_data(), sf)
        _write_analysis(wb, core, sf)
        wb.save(path)
    except ImportError as exc:  # pragma: no cover - openpyxl broke after the core's write
        return False, "Failed to add the Events sheet: openpyxl could not be imported (%s)" % exc
    except Exception as exc:
        # No "openpyxl" in this message: routes/files.py answers an error that
        # names it with "openpyxl is not installed", which a full disk is not.
        return False, "Failed to add the Events and Analysis sheets: %s" % exc
    return True, None
