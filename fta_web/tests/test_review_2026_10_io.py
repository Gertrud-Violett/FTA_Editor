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


def test_docx_route_with_control_characters(files_client, tmp_path):
    pytest.importorskip("docx")
    open_doc(files_client, write_doc(tmp_path / "c.json", control_char_tree(), title="T\x02"))
    response = files_client.post("/api/report/docx", json={})
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
