"""
FMEA spreadsheet import (1.7, workstream C).

Three plain functions, no Flask and no AppState, so they are testable on a
bare dict tree and reusable from the CLI:

``read_table(path, sheet=None)``
    ``.csv`` or ``.xlsx`` -> ``{sheets, sheet, columns, rows, rowNumbers}``.
    The first non-empty row is the header; empty rows are skipped;
    ``rowNumbers[i]`` is the 1-based spreadsheet row ``rows[i]`` came from,
    so a skipped-row report can point at the line the user sees in Excel.

``suggest_mapping(columns)``
    ``{field: column}`` for the import fields (see :data:`FIELDS`), guessed
    from English and Japanese header keywords. A column is used at most once.

``apply_import(tree, rows, mapping, parent_id, occurrence_table, source_label,
update=True, lambda_unit="h", columns=None, row_numbers=None)``
    Mutates ``tree`` (the root node dict) and returns
    ``{created: [ids], updated: [ids], unchanged: [ids], skipped: [{row,
    fmeaId, reason, field, value, message}]}``.

Import rules
------------
* **Key.** ``fmea.id`` comes from the mapped ID column, else ``"item / mode"``.
  A row with neither is skipped (``noKey``).
* **Update in place.** With ``update`` true a row whose key equals the
  ``fmea.id`` of a node *anywhere* in the tree updates that node (name, the
  ``fmea`` block, and -- for a leaf -- its quantification). With ``update``
  false such a row is skipped (``exists``). A key repeated inside the same
  sheet is imported once; later repeats are skipped (``duplicate``).
* **New rows** become leaf events under ``parent_id`` with ids from
  ``tree_ops.next_child_id`` (the desktop id format), named ``"item – mode"``
  (or whichever of the two is present, else the key).
* **Quantification**, in order of preference:
  1. a λ column -> ``quant = {model: rate, lambda}`` with λ converted to per
     hour (``lambda_unit`` ``h``; ``y`` divides by 8760; ``FIT`` is 1e-9/h);
  2. an occurrence rank -> ``quant.model = fixed`` and ``probability =
     occurrence_table[str(rank)]``;
  3. neither -> a new event keeps probability 1.0 and is marked
     ``eventKind: undeveloped``; an existing node's numbers are left alone.
  An existing ``quant`` is merged, not replaced, so ``T``/``unc`` survive a
  re-import. An event that gains a value loses a previous ``undeveloped``.
* **Validation.** Ranks must be integers 1..10, RPN a non-negative integer, λ a
  non-negative finite number. A failing row is skipped with the reason; the
  rest of the sheet still imports. RPN is computed as S×O×D when it is not
  mapped and all three ranks are present.
* **Parent.** Must exist and must not be a TRANSFER gate (``FmeaImportError``
  otherwise). A parent that is currently a leaf becomes an OR gate: its
  ``logicGate`` is set to OR (unless it has a ``gateType``) and its
  ``eventKind``/``houseState`` are removed, because an event with children is
  a gate and its own value is no longer used.
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:  # normal package import: ``import fta_web.fmea_import``
    from . import config  # noqa: F401  (puts fta_web/core on sys.path)
    from . import node_schema
    from .tree_ops import next_child_id
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import config  # type: ignore[no-redef]  # noqa: F401
    import node_schema  # type: ignore[no-redef]
    from tree_ops import next_child_id  # type: ignore[no-redef]

from FTA_Editor_core import sanitize_name  # noqa: E402

SUPPORTED_EXTENSIONS = (".csv", ".xlsx")

#: The mappable fields, in the order the UI lists them.
FIELDS = (
    "id", "item", "mode", "cause", "severity", "occurrence", "detection",
    "rpn", "lambda",
)

#: unit -> divisor giving per-hour (divided, not multiplied by 1e-9, so
#: 1000 FIT is exactly 1e-06 rather than 1.0000000000000002e-06).
LAMBDA_UNITS = {"h": 1.0, "y": 8760.0, "FIT": 1e9}

CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp932", "latin-1")

#: Hard ceiling on rows read from one sheet (the file size cap is the other).
MAX_ROWS = 20000
MAX_COLUMNS = 200


class FmeaImportError(ValueError):
    """A file or a request that cannot be imported at all (not one bad row).

    ``reason`` is a stable discriminator for the API detail and the UI text.
    """

    def __init__(self, message: str, reason: str, **detail: Any):
        super().__init__(message)
        self.reason = reason
        self.detail = detail


# ---- reading -------------------------------------------------------------------


def _cell(value: Any) -> Any:
    """A JSON-safe cell: str (stripped), int/float, or None for blank."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    text = str(value).strip()
    return text if text else None


def _blank(row: Sequence[Any]) -> bool:
    return all(cell is None or (isinstance(cell, str) and not cell.strip()) for cell in row)


def _unique_headers(raw: Sequence[Any]) -> List[str]:
    """Header texts, blanks named ``Column N`` and duplicates suffixed ``(2)``."""
    out: List[str] = []
    taken = set()
    for index, value in enumerate(raw):
        text = _cell(value)
        text = sanitize_name(text) if text is not None else ""
        if not text:
            text = "Column %d" % (index + 1)
        candidate, n = text, 1
        while candidate in taken:
            n += 1
            candidate = "%s (%d)" % (text, n)
        taken.add(candidate)
        out.append(candidate)
    return out


def _tabulate(raw_rows: Iterable[Tuple[int, Sequence[Any]]]) -> Dict[str, Any]:
    """Header + data rows from ``(row_number, cells)`` pairs."""
    header: Optional[List[str]] = None
    rows: List[List[Any]] = []
    numbers: List[int] = []
    for number, cells in raw_rows:
        cells = [_cell(c) for c in list(cells)[:MAX_COLUMNS]]
        if _blank(cells):
            continue
        if header is None:
            # Trailing blank header cells are padding, not columns.
            while cells and cells[-1] is None:
                cells.pop()
            header = _unique_headers(cells)
            continue
        if len(rows) >= MAX_ROWS:
            raise FmeaImportError(
                "The sheet has more than %d rows." % MAX_ROWS, "too_many_rows",
                limit=MAX_ROWS,
            )
        width = len(header)
        cells = (cells + [None] * width)[:width]
        if _blank(cells):
            continue
        rows.append(cells)
        numbers.append(number)
    return {"columns": header or [], "rows": rows, "rowNumbers": numbers}


def _decode(data: bytes) -> str:
    for encoding in CSV_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")  # pragma: no cover - latin-1 never fails


def _read_csv(path: Path) -> Dict[str, Any]:
    text = _decode(path.read_bytes())
    sample = text[:65536]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text, newline=""), dialect)
    try:
        table = _tabulate((index + 1, row) for index, row in enumerate(reader))
    except csv.Error as exc:
        raise FmeaImportError("'%s' is not a readable CSV file (%s)." % (path.name, exc),
                              "unreadable")
    table.update(sheets=[], sheet=None)
    return table


def openpyxl_available() -> bool:
    """Whether openpyxl can be imported right now (same probe as routes/files)."""
    import importlib.util

    try:
        return importlib.util.find_spec("openpyxl") is not None
    except (ImportError, ValueError):
        return False


def _read_xlsx(path: Path, sheet: Optional[str]) -> Dict[str, Any]:
    try:
        import openpyxl  # noqa: WPS433 (optional dependency)
    except ImportError as exc:
        raise FmeaImportError("Reading .xlsx needs the 'openpyxl' package.",
                              "openpyxl_missing") from exc
    try:
        book = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    except Exception as exc:  # zipfile.BadZipFile, KeyError, InvalidFileException...
        raise FmeaImportError("'%s' is not a readable .xlsx workbook." % path.name,
                              "unreadable") from exc
    try:
        names = list(book.sheetnames)
        if not names:
            raise FmeaImportError("'%s' has no sheets." % path.name, "no_sheets")
        if sheet in (None, ""):
            chosen = names[0]
        elif str(sheet) in names:
            chosen = str(sheet)
        else:
            raise FmeaImportError("'%s' has no sheet named '%s'." % (path.name, sheet),
                                  "unknown_sheet", sheet=str(sheet))
        worksheet = book[chosen]
        table = _tabulate(
            (index + 1, row)
            for index, row in enumerate(worksheet.iter_rows(values_only=True))
        )
    finally:
        book.close()
    table.update(sheets=names, sheet=chosen)
    return table


def read_table(path: Any, sheet: Optional[str] = None) -> Dict[str, Any]:
    """Read a ``.csv`` or ``.xlsx`` file. See the module docstring for the shape."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _read_csv(path)
    if suffix == ".xlsx":
        return _read_xlsx(path, sheet)
    raise FmeaImportError("Only .csv and .xlsx files can be imported.", "extension")


def rows_as_dicts(table: Dict[str, Any]) -> List[Dict[str, Any]]:
    """``read_table`` rows as ``{column: value}`` dicts."""
    columns = table.get("columns") or []
    return [dict(zip(columns, row)) for row in table.get("rows") or []]


# ---- column mapping -------------------------------------------------------------


def _norm(text: Any) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).lower().strip()
    return re.sub(r"\s+", " ", text)


def _word(token: str) -> "re.Pattern[str]":
    return re.compile(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])")


#: field -> (exact header texts, "contains" patterns). NFKC + lower-cased, so
#: full-width 'ＩＤ' and 'Ｎｏ．' match too. Order of FIELDS breaks ties.
_RULES: Dict[str, Tuple[Tuple[str, ...], Tuple[Any, ...]]] = {
    "rpn": (("rpn", "ap"), ("rpn", "risk priority", "リスク優先", "危険優先", "優先度数")),
    "lambda": (
        ("λ", "lambda", "rate", "fit", "fr"),
        ("failure rate", "故障率", "λ", "lambda", _word("fit"), "hazard rate"),
    ),
    "severity": (("s", "sev", "sev."), ("severity", "影響度", "厳しさ", "重大度", "致命度", "深刻度")),
    "occurrence": (
        ("o", "occ", "occ."),
        ("occurrence", "発生度", "発生頻度", "発生ランク", "発生可能性"),
    ),
    "detection": (("d", "det", "det."), ("detection", "検出度", "検知度", "検出性", "検出難易度")),
    "mode": (
        ("mode", "モード", "故障モード"),
        ("failure mode", "故障モード", "不具合モード", "故障形態", _word("mode")),
    ),
    "cause": (("cause", "原因"), ("cause", "原因", "mechanism", "メカニズム", "要因")),
    "id": (
        ("id", "no", "no.", "#", "番号", "fmea id", "ref", "ref.", "item no", "item no."),
        (_word("id"), "番号", "fmea no", _word("no.")),
    ),
    "item": (
        ("item", "品目", "部品", "component", "part", "function", "機能", "構成品"),
        ("item", "品目", "部品", "構成品", "component", _word("part"), "function", "機能", "部位"),
    ),
}


def _score(field: str, header: str) -> int:
    exact, contains = _RULES[field]
    if header in exact:
        return 2
    for pattern in contains:
        if isinstance(pattern, str):
            if pattern in header:
                return 1
        elif pattern.search(header):
            return 1
    return 0


_FIELD_PRIORITY = ("rpn", "lambda", "severity", "occurrence", "detection",
                   "mode", "cause", "id", "item")


def suggest_mapping(columns: Sequence[Any]) -> Dict[str, str]:
    """Best-guess ``{field: column}``. Exact header matches win over partial
    ones; within a score, :data:`_FIELD_PRIORITY` then column order decide."""
    headers = [(_norm(c), str(c)) for c in columns or []]
    candidates = []
    for f_rank, field in enumerate(_FIELD_PRIORITY):
        for c_rank, (norm, original) in enumerate(headers):
            score = _score(field, norm)
            if score:
                candidates.append((-score, f_rank, c_rank, field, original))
    candidates.sort()
    mapping: Dict[str, str] = {}
    used = set()
    for _s, _f, c_rank, field, original in candidates:
        if field in mapping or c_rank in used:
            continue
        mapping[field] = original
        used.add(c_rank)
    return {field: mapping[field] for field in FIELDS if field in mapping}


def suggest_lambda_unit(column: Any) -> str:
    """``FIT``/``y``/``h`` from a λ header such as ``λ (FIT)`` or ``故障率 [/年]``."""
    text = _norm(column)
    if _word("fit").search(text):
        return "FIT"
    if re.search(r"/\s*(y|yr|year)\b|per year|/年|年", text):
        return "y"
    return "h"


# ---- value parsing ---------------------------------------------------------------


class _RowError(Exception):
    def __init__(self, reason: str, field: str, value: Any, message: str):
        super().__init__(message)
        self.reason = reason
        self.field = field
        self.value = value
        self.message = message


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return sanitize_name(value)


def _number(value: Any) -> Optional[float]:
    """A float from a cell, tolerating '1,5' and '1.2E-06'. None when blank."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(value)
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = unicodedata.normalize("NFKC", str(value)).strip().replace(" ", "")
        if not text:
            return None
        if "," in text and "." not in text:
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")
        number = float(text)
    if math.isnan(number) or math.isinf(number):
        raise ValueError(value)
    return number


def _rank(value: Any, field: str) -> Optional[int]:
    try:
        number = _number(value)
    except (TypeError, ValueError):
        number = float("nan")
    if number is None:
        return None
    if not (number == number and float(number).is_integer() and 1 <= number <= 10):
        raise _RowError("invalidRank", field, value,
                        "'%s' must be an integer rank from 1 to 10." % field)
    return int(number)


def _parse_row(get, lambda_divisor: float) -> Dict[str, Any]:
    """The validated values of one row (``get(field)`` reads a mapped cell)."""
    out: Dict[str, Any] = {
        "id": _text(get("id")),
        "item": _text(get("item")),
        "mode": _text(get("mode")),
        "cause": _text(get("cause")),
    }
    for field in ("severity", "occurrence", "detection"):
        out[field] = _rank(get(field), field)

    raw_rpn = get("rpn")
    try:
        rpn = _number(raw_rpn)
    except (TypeError, ValueError):
        rpn = -1.0
    if rpn is not None and not (rpn >= 0 and float(rpn).is_integer()):
        raise _RowError("invalidRpn", "rpn", raw_rpn, "'rpn' must be a non-negative integer.")
    if rpn is None and None not in (out["severity"], out["occurrence"], out["detection"]):
        rpn = out["severity"] * out["occurrence"] * out["detection"]
    out["rpn"] = int(rpn) if rpn is not None else None

    raw_lambda = get("lambda")
    try:
        lam = _number(raw_lambda)
    except (TypeError, ValueError):
        lam = -1.0
    if lam is not None and lam < 0:
        raise _RowError("invalidLambda", "lambda", raw_lambda,
                        "The failure rate must be a non-negative number.")
    out["lambda"] = lam / lambda_divisor if lam is not None else None
    return out


# ---- the tree --------------------------------------------------------------------


class _TreeView:
    """Just enough of FTACore for ``tree_ops.next_child_id``."""

    def __init__(self, tree: Dict[str, Any]):
        self._tree = tree

    def get_data(self) -> Dict[str, Any]:
        return self._tree

    def find_node_by_id(self, node_id: Any) -> Optional[Dict[str, Any]]:
        for node in _walk(self._tree):
            if str(node.get("id")) == str(node_id):
                return node
        return None


def _walk(root: Any):
    stack = [root] if isinstance(root, dict) else []
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        yield node
        stack.extend(reversed(node.get("children") or []))


def _is_leaf(node: Dict[str, Any]) -> bool:
    return not (node.get("children") or [])


def _quantifiable(node: Dict[str, Any]) -> bool:
    gate_type = str(node.get("gateType") or "").upper()
    kind = str(node.get("eventKind") or "").lower()
    return _is_leaf(node) and gate_type != "TRANSFER" and kind != "house" \
        and node.get("type") != "Root"


def _occurrence_probability(table: Dict[str, Any], rank: int) -> Optional[float]:
    value = (table or {}).get(str(rank))
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if math.isnan(value) or not 0.0 <= value <= 1.0:
        return None
    return value


def _node_name(values: Dict[str, Any], key: str) -> str:
    item, mode = values["item"], values["mode"]
    if item and mode:
        name = "%s – %s" % (item, mode)
    else:
        name = mode or item or key
    return sanitize_name(name)[: node_schema.MAX_TEXT]


def _fmea_block(values: Dict[str, Any], key: str, source: str) -> Dict[str, Any]:
    block: Dict[str, Any] = {"id": key}
    for field in ("item", "mode", "cause"):
        if values[field]:
            block[field] = values[field][: node_schema.MAX_TEXT]
    for field in ("severity", "occurrence", "detection", "rpn"):
        if values[field] is not None:
            block[field] = values[field]
    if source:
        block["source"] = source[: node_schema.MAX_TEXT]
    # Round-trip through the schema validator: what lands on disk is exactly
    # what a PATCH could have written.
    return node_schema.validate_fmea(block) or {}


def _apply_values(node: Dict[str, Any], values: Dict[str, Any], key: str,
                  table: Dict[str, Any], source: str, created: bool) -> None:
    node["name"] = _node_name(values, key)
    # The fmea block is replaced wholesale: the sheet is the source of truth
    # for it, and a column emptied in the sheet must empty here too.
    node["fmea"] = _fmea_block(values, key, source)

    if not _quantifiable(node):
        return
    quant_patch: Optional[Dict[str, Any]] = None
    probability: Optional[float] = None
    if values["lambda"] is not None:
        quant_patch = {"model": "rate", "lambda": values["lambda"]}
        if source:
            quant_patch["source"] = source[: node_schema.MAX_TEXT]
    elif values["occurrence"] is not None:
        probability = _occurrence_probability(table, values["occurrence"])
        if probability is not None:
            quant_patch = {"model": "fixed"}

    if quant_patch is not None:
        validated = node_schema.validate_quant(quant_patch) or {}
        node["quant"] = node_schema.merge_partial(node.get("quant"), validated)
        if probability is not None:
            node["probability"] = probability
        if str(node.get("eventKind") or "") == "undeveloped":
            node.pop("eventKind", None)
    elif created:
        node["probability"] = 1.0
        node["eventKind"] = "undeveloped"


def _prepare_parent(parent: Dict[str, Any]) -> None:
    """A leaf parent turns into an OR gate (see the module docstring)."""
    if not _is_leaf(parent):
        return
    if not parent.get("gateType"):
        parent["logicGate"] = "OR"
    parent.pop("eventKind", None)
    parent.pop("houseState", None)


def apply_import(
    tree: Dict[str, Any],
    rows: Sequence[Any],
    mapping: Dict[str, Any],
    parent_id: Any,
    occurrence_table: Optional[Dict[str, Any]],
    source_label: str = "",
    update: bool = True,
    lambda_unit: str = "h",
    columns: Optional[Sequence[str]] = None,
    row_numbers: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    """Import ``rows`` into ``tree`` (mutated). See the module docstring.

    ``rows`` are ``{column: value}`` dicts, or lists aligned with ``columns``.
    ``mapping`` is ``{field: column}``; unknown fields and blank columns are
    ignored, a column that is not in the sheet is an error.
    """
    if not isinstance(tree, dict):
        raise FmeaImportError("There is no tree to import into.", "no_tree")
    if lambda_unit not in LAMBDA_UNITS:
        raise FmeaImportError("'lambdaUnit' must be one of h, y, FIT.", "lambda_unit",
                              field="lambdaUnit")
    mapping = {
        str(field): str(column)
        for field, column in (mapping or {}).items()
        if field in FIELDS and column not in (None, "")
    }
    if columns is not None:
        missing = sorted(c for c in mapping.values() if c not in list(columns))
        if missing:
            raise FmeaImportError("Mapped column(s) not in the sheet: %s." % ", ".join(missing),
                                  "unknown_column", columns=missing)
    if not any(f in mapping for f in ("id", "item", "mode")):
        raise FmeaImportError("Map at least one of the ID, item or failure-mode columns.",
                              "no_key_column")

    view = _TreeView(tree)
    parent = view.find_node_by_id(parent_id)
    if parent is None:
        raise FmeaImportError("Parent node '%s' was not found." % parent_id, "parent_not_found",
                              parentId=str(parent_id))
    if str(parent.get("gateType") or "").upper() == "TRANSFER":
        raise FmeaImportError("Events cannot be imported under a TRANSFER gate.",
                              "parent_transfer", parentId=str(parent_id))

    by_key: Dict[str, Dict[str, Any]] = {}
    for node in _walk(tree):
        fmea = node.get("fmea")
        if isinstance(fmea, dict) and fmea.get("id") not in (None, ""):
            by_key.setdefault(str(fmea["id"]), node)

    factor = LAMBDA_UNITS[lambda_unit]
    table = occurrence_table or {}
    result: Dict[str, Any] = {"created": [], "updated": [], "unchanged": [], "skipped": []}
    seen = set()

    for index, raw in enumerate(rows or []):
        if isinstance(raw, dict):
            cells = raw
        else:
            cells = dict(zip(columns or [], raw))
        row_no = row_numbers[index] if row_numbers and index < len(row_numbers) else index + 2

        def get(field, _cells=cells):
            column = mapping.get(field)
            return _cells.get(column) if column else None

        try:
            values = _parse_row(get, factor)
        except _RowError as exc:
            key_guess = _text(get("id")) or None
            result["skipped"].append({
                "row": row_no, "fmeaId": key_guess, "reason": exc.reason,
                "field": exc.field, "value": exc.value if not isinstance(exc.value, float)
                or math.isfinite(exc.value) else None,
                "message": exc.message,
            })
            continue

        key = values["id"] or (
            " / ".join(v for v in (values["item"], values["mode"]) if v)
        )
        key = key[: node_schema.MAX_TEXT]
        if not key:
            result["skipped"].append({"row": row_no, "fmeaId": None, "reason": "noKey",
                                      "message": "The row has no ID, item or failure mode."})
            continue
        if key in seen:
            result["skipped"].append({"row": row_no, "fmeaId": key, "reason": "duplicate",
                                      "message": "FMEA ID '%s' appears earlier in the sheet." % key})
            continue
        seen.add(key)

        existing = by_key.get(key)
        if existing is not None:
            if not update:
                result["skipped"].append({
                    "row": row_no, "fmeaId": key, "reason": "exists",
                    "nodeId": str(existing.get("id")),
                    "message": "FMEA ID '%s' is already in the tree." % key,
                })
                continue
            before = repr(sorted((k, repr(v)) for k, v in existing.items() if k != "children"))
            _apply_values(existing, values, key, table, source_label, created=False)
            after = repr(sorted((k, repr(v)) for k, v in existing.items() if k != "children"))
            bucket = "updated" if before != after else "unchanged"
            result[bucket].append(str(existing.get("id")))
            continue

        _prepare_parent(parent)
        new_id = next_child_id(view, str(parent.get("id")))
        node: Dict[str, Any] = {
            "id": new_id,
            "name": "",
            "type": "Event",
            "probability": 1.0,
            "logicGate": "OR",
            "notes": "",
            "links": [],
            "children": [],
        }
        _apply_values(node, values, key, table, source_label, created=True)
        parent.setdefault("children", []).append(node)
        by_key[key] = node
        result["created"].append(new_id)

    return result


def import_error_detail(exc: FmeaImportError) -> Dict[str, Any]:
    """``detail`` for an API error built from :class:`FmeaImportError`."""
    detail = {"reason": exc.reason}
    detail.update(exc.detail)
    return detail


__all__ = [
    "FIELDS",
    "LAMBDA_UNITS",
    "SUPPORTED_EXTENSIONS",
    "FmeaImportError",
    "apply_import",
    "import_error_detail",
    "openpyxl_available",
    "read_table",
    "rows_as_dicts",
    "suggest_lambda_unit",
    "suggest_mapping",
]
