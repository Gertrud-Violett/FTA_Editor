"""
FMEA spreadsheet import (1.7, workstream C).

Three plain functions, no Flask and no AppState, so they are testable on a
bare dict tree and reusable from the CLI:

``read_table(path, sheet=None)``
    ``.csv`` or ``.xlsx`` -> ``{sheets, sheet, columns, rows, rowNumbers,
    delimiter}``. The first non-empty row is the header; empty rows are
    skipped; ``rowNumbers[i]`` is the 1-based spreadsheet row ``rows[i]`` came
    from, so a skipped-row report can point at the line the user sees in
    Excel. ``delimiter`` is the CSV's (None for a workbook).

``suggest_mapping(columns)``
    ``{field: column}`` for the import fields (see :data:`FIELDS`), guessed
    from English and Japanese header keywords. A column is used at most once.

``suggest_lambda_unit(column, values=None, delimiter=None)``
    ``FIT``/``y``/``h`` for the λ column: the unit its header names, else
    guessed from the magnitude of its values (median >= 1: FIT; 1e-3..1: /y).

``apply_import(tree, rows, mapping, parent_id, occurrence_table, source_label,
update=True, lambda_unit="h", columns=None, row_numbers=None, delimiter=None)``
    Mutates ``tree`` (the root node dict) and returns
    ``{created: [ids], updated: [ids], unchanged: [ids], skipped: [{row,
    fmeaId, reason, field, value, message}], notInSheet: [{id, name,
    fmeaId}]}``.

Import rules
------------
* **Key.** ``fmea.id`` comes from the mapped ID column, else ``"item / mode"``.
  A row with neither is skipped (``noKey``).
* **Item fill-down.** A row with a failure mode but a blank item takes the
  last item above it: the usual layout writes the item once per group
  (merged cells read as blank). :func:`fill_down` does the same for the
  preview.
* **Update in place.** With ``update`` true a row whose key equals the
  ``fmea.id`` of a node *anywhere* in the tree updates that node (the
  ``fmea`` block, the name, and -- for a leaf -- its quantification). Only
  the fields whose columns are mapped change (a mapped column left blank
  empties its field); the name is re-derived only when the item or mode
  column is mapped. With ``update`` false such a row is skipped (``exists``).
  A key repeated inside the same sheet is imported once; later repeats are
  skipped (``duplicate``).
* **Rows gone from the sheet.** Nodes of an earlier import of this sheet
  (``fmea.source`` is this import's label, or that of a node it matched)
  whose key no row holds any more are kept, and listed in ``notInSheet``.
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
* **Numbers in text cells** accept a decimal comma ('1,5') and European
  grouping ('1.200,5'). In a comma-delimited CSV, where a comma cannot be the
  decimal mark of an unquoted number, '1,200' and '12,345.6' are grouped
  thousands (Excel's export of a '#,##0' column); elsewhere '1,200' is 1.2.
* **Parent.** Must exist and must not be a TRANSFER gate (``FmeaImportError``
  otherwise). A parent that is currently a leaf becomes an OR gate: its
  ``logicGate`` is set to OR (unless it has a ``gateType``) and its
  ``eventKind``/``houseState`` are removed, because an event with children is
  a gate and its own value is no longer used.
"""
from __future__ import annotations

import codecs
import csv
import datetime as _dt
import io
import math
import re
import statistics
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

#: The encodings a CSV is read in, in this order (see :func:`_decode`: cp932
#: only for text with kana, UTF-16/32 only with a byte-order mark).
CSV_ENCODINGS = ("utf-8-sig", "utf-16", "utf-32", "cp932", "cp1252", "latin-1")

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


#: Byte-order marks of the wide encodings, UTF-32 first (its LE mark starts
#: with UTF-16's). Excel's "Unicode Text" and Windows PowerShell write
#: UTF-16 with a BOM; without this it decoded as latin-1, NULs and all.
_WIDE_BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32"), (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16"),
)


#: Kana: what tells a Japanese cp932 file from a Western cp1252 one that also
#: decodes as cp932 without an error ('Défaut' -> 'D馭aut', 'Válvula' ->
#: 'V疝vula'). A half-width katakana counts only next to another: each of
#: cp1252's 0xA6-0xDF (°, ±, µ, ², Ä, Ö, Ü, ß ...) decodes as a lone one
#: ('80°C' -> '80ｰC', 'Überhitzung' -> 'ﾜberhitzung'), while half-width
#: Japanese words are runs ('ﾎﾟﾝﾌﾟ').
_KANA = re.compile("[぀-ヿ]|[ｦ-ﾟ]{2}")


def _decode(data: bytes) -> str:
    """UTF-8 (BOM or not), UTF-16/32 by their BOM, cp932 when the text has
    kana, else cp1252, else latin-1."""
    for bom, encoding in _WIDE_BOMS:
        if data.startswith(bom):
            try:
                return data.decode(encoding)  # the codec reads and drops the BOM
            except UnicodeDecodeError:
                break
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        text = data.decode("cp932")
        if _KANA.search(text):
            return text
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1252")
    except UnicodeDecodeError:
        return data.decode("latin-1")  # never fails


CSV_DELIMITERS = ",;\t|"


def _header_delimiter(sample: str) -> str:
    """The candidate delimiter the first non-empty line uses most (outside
    quotes); a comma when it uses none. Ties go to the comma."""
    line = next((ln for ln in sample.splitlines() if ln.strip()), "")
    counts = dict.fromkeys(CSV_DELIMITERS, 0)
    quoted = False
    for ch in line:
        if ch == '"':
            quoted = not quoted
        elif not quoted and ch in counts:
            counts[ch] += 1
    best = max(CSV_DELIMITERS, key=lambda d: counts[d])
    return best if counts[best] else ","


def _read_csv(path: Path) -> Dict[str, Any]:
    text = _decode(path.read_bytes())
    sample = text[:65536]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=CSV_DELIMITERS)
        delimiter = dialect.delimiter
        reader = csv.reader(io.StringIO(text, newline=""), dialect)
    except csv.Error:
        # The sniffer wants the same count on ~90 % of the lines, so a short
        # or ragged file (trailing ';' on the data rows, empty trailing
        # fields left out) defeats it -- and a plain comma fallback read a
        # ';' file as one column. The header line decides instead.
        delimiter = _header_delimiter(sample)
        reader = csv.reader(io.StringIO(text, newline=""), csv.excel, delimiter=delimiter)
    try:
        table = _tabulate((index + 1, row) for index, row in enumerate(reader))
    except csv.Error as exc:
        raise FmeaImportError("'%s' is not a readable CSV file (%s)." % (path.name, exc),
                              "unreadable")
    table.update(sheets=[], sheet=None, delimiter=delimiter)
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
        # Worksheets only: a chart sheet has no cells (and, as the first
        # sheet, was the default -- AttributeError, a 500 on preview).
        names = [ws.title for ws in book.worksheets]
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
        # Read-only mode trusts the sheet's declared <dimension>, and some
        # exporters write 'A1' whatever the data: only A1 was read. Read the
        # rows that are actually there instead (openpyxl's documented remedy;
        # missing rows still come back empty, so row numbers stay right).
        if hasattr(worksheet, "reset_dimensions"):
            worksheet.reset_dimensions()
        table = _tabulate(
            (index + 1, row)
            for index, row in enumerate(worksheet.iter_rows(values_only=True))
        )
    finally:
        book.close()
    table.update(sheets=names, sheet=chosen, delimiter=None)
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


def _blank_cell(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


class _ItemFill:
    """Fill a blank item cell down from the rows above.

    The usual FMEA layout writes an item once over its failure modes --
    merged cells, which read as blank below the first, or simply left blank.
    A row that carries a failure mode but no item takes the last item above
    it (rows without a mode, such as a further cause, are left as they are).
    Without this those rows lost their item, and with the key "item / mode"
    'Valve / Stuck' became 'Stuck' and was skipped as a duplicate.
    """

    def __init__(self, mapping: Dict[str, Any]):
        self.item = (mapping or {}).get("item")
        self.mode = (mapping or {}).get("mode")
        self.last: Any = None

    def __call__(self, cells: Dict[str, Any]) -> Dict[str, Any]:
        if not (self.item and self.mode):
            return cells
        value = cells.get(self.item)
        if not _blank_cell(value):
            self.last = value
        elif self.last is not None and not _blank_cell(cells.get(self.mode)):
            cells = dict(cells)
            cells[self.item] = self.last
        return cells


def fill_down(table: Dict[str, Any], mapping: Dict[str, Any]) -> List[List[Any]]:
    """``table``'s rows with blank item cells filled as :func:`apply_import`
    fills them for ``mapping`` (for the preview)."""
    columns = list(table.get("columns") or [])
    fill = _ItemFill(mapping)
    out = []
    for row in table.get("rows") or []:
        cells = fill(dict(zip(columns, row)))
        out.append([cells.get(column) for column in columns])
    return out


# ---- column mapping -------------------------------------------------------------


def _norm(text: Any) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).lower().strip()
    return re.sub(r"\s+", " ", text)


def _word(token: str) -> "re.Pattern[str]":
    return re.compile(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])")


#: field -> (exact header texts, "contains" patterns). NFKC + lower-cased, so
#: full-width 'ＩＤ' and 'Ｎｏ．' match too. Order of FIELDS breaks ties.
_RULES: Dict[str, Tuple[Tuple[str, ...], Tuple[Any, ...]]] = {
    # Not "ap": AIAG-VDA's Action Priority is H / M / L, never an RPN -- as
    # the suggestion it made every row of such a sheet an invalidRpn skip.
    "rpn": (("rpn",), ("rpn", "risk priority", "リスク優先", "危険優先", "優先度数")),
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


_UNIT_YEAR = re.compile(r"/\s*(y|yr|year)\b|per[ -]?year|/年|年")
_UNIT_HOUR = re.compile(r"/\s*(h|hr|hour)\b|per[ -]?hour|/時|時間")

#: A median λ at or above this is almost certainly FIT (1 FIT = 1e-9/h: a
#: per-hour rate of 1 means an MTBF of one hour).
FIT_MEDIAN_THRESHOLD = 1.0
#: ... and at or above this (but below 1) most likely per year: 1e-3..1 /y is
#: the normal component range, while 1e-3..1 /h is an MTBF of 1 h..1000 h.
YEAR_MEDIAN_THRESHOLD = 1e-3


def header_lambda_unit(column: Any) -> Optional[str]:
    """``FIT``/``y``/``h`` when the λ header names its unit (``λ (FIT)``,
    ``故障率 [/年]``, ``rate per hour``), else None."""
    text = _norm(column)
    if _word("fit").search(text):
        return "FIT"
    if _UNIT_YEAR.search(text):
        return "y"
    if _UNIT_HOUR.search(text):
        return "h"
    return None


def suggest_lambda_unit(column: Any, values: Optional[Iterable[Any]] = None,
                        delimiter: Optional[str] = None) -> str:
    """``FIT``/``y``/``h`` for a λ column.

    A unit named in the header wins. Otherwise the magnitude of the column's
    values decides: a median of 1 or more is FIT, 1e-3 up to 1 is per year,
    anything smaller per hour. Importing FIT values as per-hour rates makes
    every such event certain (q = 1), so guessing from the numbers is much
    safer than always defaulting to ``/h``. ``delimiter`` is the table's
    (``read_table``): values are read as :func:`apply_import` reads them.
    """
    unit = header_lambda_unit(column)
    if unit is not None:
        return unit
    numbers = []
    for value in values or ():
        try:
            number = _number(value, delimiter == ",")
        except (TypeError, ValueError):
            continue
        if number is not None and number >= 0:
            numbers.append(number)
    if numbers:
        median = statistics.median(numbers)
        if median >= FIT_MEDIAN_THRESHOLD:
            return "FIT"
        if median >= YEAR_MEDIAN_THRESHOLD:
            return "y"
    return "h"


def column_values(table: Dict[str, Any], column: Any) -> List[Any]:
    """Every row's cell in ``column`` (a header of ``table``)."""
    columns = list(table.get("columns") or [])
    if column not in columns:
        return []
    index = columns.index(column)
    return [row[index] if index < len(row) else None for row in table.get("rows") or []]


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


#: '1.200,5', '-12.345.678,9e-3': dots grouping thousands before a decimal
#: comma (European number formats). Read as 1.2005 before, with the commas
#: simply dropped -- a FIT value 1000 times too small.
_EU_GROUPED = re.compile(r"[+-]?\d{1,3}(?:\.\d{3})+,\d+(?:[eE][+-]?\d+)?$")

#: '1,200', '12,345.6': commas grouping thousands -- what Excel writes to a
#: comma-delimited CSV for a '#,##0' column (quoted). Only read so in such a
#: file (``comma_groups``): in a ';' or tab CSV, or a workbook's text cell,
#: '1,200' keeps its decimal-comma reading (1.2). A leading 0 group
#: ('0,001') is never thousands formatting.
_COMMA_GROUPED = re.compile(r"[+-]?[1-9]\d{0,2}(?:,\d{3})+(?:\.\d+)?$")


def _number(value: Any, comma_groups: bool = False) -> Optional[float]:
    """A float from a cell, tolerating '1,5', '1.200,5' and '1.2E-06' (and
    '1,200' as 1200 with ``comma_groups``). None when blank."""
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
        if comma_groups and _COMMA_GROUPED.match(text):
            text = text.replace(",", "")
        elif "," in text and "." not in text:
            text = text.replace(",", ".")
        elif _EU_GROUPED.match(text):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
        number = float(text)
    if math.isnan(number) or math.isinf(number):
        raise ValueError(value)
    return number


def _rank(value: Any, field: str, comma_groups: bool = False) -> Optional[int]:
    try:
        number = _number(value, comma_groups)
    except (TypeError, ValueError):
        number = float("nan")
    if number is None:
        return None
    if not (number == number and float(number).is_integer() and 1 <= number <= 10):
        raise _RowError("invalidRank", field, value,
                        "'%s' must be an integer rank from 1 to 10." % field)
    return int(number)


def _parse_row(get, lambda_divisor: float, comma_groups: bool = False) -> Dict[str, Any]:
    """The validated values of one row (``get(field)`` reads a mapped cell)."""
    out: Dict[str, Any] = {
        "id": _text(get("id")),
        "item": _text(get("item")),
        "mode": _text(get("mode")),
        "cause": _text(get("cause")),
    }
    for field in ("severity", "occurrence", "detection"):
        out[field] = _rank(get(field), field, comma_groups)

    raw_rpn = get("rpn")
    try:
        rpn = _number(raw_rpn, comma_groups)
    except (TypeError, ValueError):
        rpn = -1.0
    if rpn is not None and not (rpn >= 0 and float(rpn).is_integer()):
        raise _RowError("invalidRpn", "rpn", raw_rpn, "'rpn' must be a non-negative integer.")
    if rpn is None and None not in (out["severity"], out["occurrence"], out["detection"]):
        rpn = out["severity"] * out["occurrence"] * out["detection"]
    out["rpn"] = int(rpn) if rpn is not None else None

    raw_lambda = get("lambda")
    try:
        lam = _number(raw_lambda, comma_groups)
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


def _node_name(item: Any, mode: Any, key: str) -> str:
    if item and mode:
        name = "%s – %s" % (item, mode)
    else:
        name = mode or item or key
    return sanitize_name(name)[: node_schema.MAX_TEXT]


_RANKS = ("severity", "occurrence", "detection")


def _fmea_block(values: Dict[str, Any], key: str, source: str, mapped: Iterable[str],
                existing: Any = None) -> Dict[str, Any]:
    """The node's ``fmea`` block after this row.

    Only the fields whose columns are mapped come from the sheet (a mapped
    column left blank empties its field); the others keep the node's
    values -- refreshing just the failure rates must not wipe item, mode,
    cause and ranks. RPN, when not mapped itself, follows S×O×D of the
    resulting ranks once any rank is mapped and all three are known.
    """
    mapped = set(mapped)
    block = dict(existing) if isinstance(existing, dict) else {}
    patch: Dict[str, Any] = {"id": key}
    for field in ("item", "mode", "cause"):
        if field in mapped:
            if values[field]:
                patch[field] = values[field][: node_schema.MAX_TEXT]
            else:
                block.pop(field, None)
    for field in _RANKS:
        if field in mapped:
            if values[field] is not None:
                patch[field] = values[field]
            else:
                block.pop(field, None)
    if "rpn" in mapped:
        if values["rpn"] is not None:  # given, or the row's own S×O×D
            patch["rpn"] = values["rpn"]
        else:
            block.pop("rpn", None)
    elif mapped & set(_RANKS):
        ranks = [patch.get(field, block.get(field)) for field in _RANKS]
        if all(isinstance(r, int) and not isinstance(r, bool) for r in ranks):
            patch["rpn"] = ranks[0] * ranks[1] * ranks[2]
    if source:
        patch["source"] = source[: node_schema.MAX_TEXT]
    # Round-trip through the schema validator: what the sheet writes is
    # exactly what a PATCH could have written.
    block.update(node_schema.validate_fmea(patch) or {})
    return block


def _apply_values(node: Dict[str, Any], values: Dict[str, Any], key: str,
                  table: Dict[str, Any], source: str, created: bool,
                  mapped: Iterable[str] = FIELDS) -> None:
    mapped = set(mapped)
    node["fmea"] = _fmea_block(values, key, source, mapped,
                               None if created else node.get("fmea"))
    # The name is derived from item and mode: re-derived only when one of
    # them is mapped (from the node's resulting values), else kept.
    if created or mapped & {"item", "mode"}:
        node["name"] = _node_name(node["fmea"].get("item"), node["fmea"].get("mode"), key)

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
    delimiter: Optional[str] = None,
) -> Dict[str, Any]:
    """Import ``rows`` into ``tree`` (mutated). See the module docstring.

    ``rows`` are ``{column: value}`` dicts, or lists aligned with ``columns``.
    ``mapping`` is ``{field: column}``; unknown fields and blank columns are
    ignored, a column that is not in the sheet is an error. ``delimiter`` is
    the CSV delimiter the rows were read with (``read_table``'s; None for a
    workbook): in a comma-delimited file '1,200' is 1200, not 1.2.
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
    comma_groups = delimiter == ","
    table = occurrence_table or {}
    result: Dict[str, Any] = {"created": [], "updated": [], "unchanged": [], "skipped": []}
    seen = set()

    # New ids: next_child_id for the first (the desktop rule), then the same
    # rule incrementally -- each call walks the whole tree twice, so calling
    # it per row made a 20,000-row import take 81 s inside the state lock.
    parent_key = str(parent.get("id"))
    taken = {str(node.get("id")) for node in _walk(tree)}
    next_index: Optional[int] = None

    def mint_id() -> str:
        nonlocal next_index
        if next_index is None:
            new_id = next_child_id(view, parent_key)
            next_index = int(new_id.rsplit("_", 1)[1])
        else:
            while "%s_%d" % (parent_key, next_index) in taken:
                next_index += 1
            new_id = "%s_%d" % (parent_key, next_index)
        next_index += 1
        taken.add(new_id)
        return new_id

    # For notInSheet: every key the sheet holds (invalid rows too), and the
    # sources -- this one, and those of the nodes it matches -- that count
    # as earlier imports of this sheet (it may have been renamed since).
    sheet_keys = set()
    lineage = {source_label} if source_label else set()

    fill = _ItemFill(mapping)
    for index, raw in enumerate(rows or []):
        if isinstance(raw, dict):
            cells = raw
        else:
            cells = dict(zip(columns or [], raw))
        cells = fill(cells)
        row_no = row_numbers[index] if row_numbers and index < len(row_numbers) else index + 2

        def get(field, _cells=cells):
            column = mapping.get(field)
            return _cells.get(column) if column else None

        row_key = (_text(get("id")) or " / ".join(
            v for v in (_text(get("item")), _text(get("mode"))) if v))[: node_schema.MAX_TEXT]
        if row_key:
            sheet_keys.add(row_key)
            matched = by_key.get(row_key)
            source = (matched.get("fmea") or {}).get("source") if matched is not None else None
            if isinstance(source, str) and source:
                lineage.add(source)

        try:
            values = _parse_row(get, factor, comma_groups)
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
            _apply_values(existing, values, key, table, source_label, created=False,
                          mapped=mapping)
            after = repr(sorted((k, repr(v)) for k, v in existing.items() if k != "children"))
            bucket = "updated" if before != after else "unchanged"
            result[bucket].append(str(existing.get("id")))
            continue

        _prepare_parent(parent)
        new_id = mint_id()
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
        _apply_values(node, values, key, table, source_label, created=True, mapped=mapping)
        parent.setdefault("children", []).append(node)
        by_key[key] = node
        result["created"].append(new_id)

    # Nodes of an earlier import of this sheet whose rows are gone: kept (the
    # analysis may have grown around them), but reported.
    result["notInSheet"] = []
    for node in _walk(tree):
        fmea = node.get("fmea")
        if not isinstance(fmea, dict) or fmea.get("id") in (None, ""):
            continue
        source = fmea.get("source")
        if str(fmea["id"]) in sheet_keys or not isinstance(source, str) or source not in lineage:
            continue
        result["notInSheet"].append({"id": str(node.get("id")), "name": node.get("name", ""),
                                     "fmeaId": str(fmea["id"])})
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
    "column_values",
    "header_lambda_unit",
    "suggest_lambda_unit",
    "suggest_mapping",
]
