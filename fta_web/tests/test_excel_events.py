"""The .xlsx export's Events and Analysis sheets (workstream D)."""
import copy
import io
import json

import pytest

openpyxl = pytest.importorskip("openpyxl")

from fta_web import excel_events  # noqa: E402
from fta_web.engine import WebCore  # noqa: E402


def sample_tree():
    return {
        "id": "root", "name": "Top", "type": "Root", "logicGate": "OR",
        "children": [
            {"id": "g1", "name": "Both fail", "type": "Event", "logicGate": "AND",
             "gateType": "AND", "children": [
                 {"id": "a", "name": "Pump λ", "type": "Event", "probability": 0.1,
                  "quant": {"model": "rate", "lambda": 1e-5, "T": 1000, "source": "OREDA",
                            "unc": {"dist": "lognormal", "median": 1e-5, "ef": 3}},
                  "children": []},
                 {"id": "b", "name": "Valve", "type": "Event", "probability": 0.01,
                  "children": []},
             ]},
            {"id": "c", "name": "Sensor", "type": "Event", "probability": 2e-7,
             "trace": {"requirementId": "REQ-1", "owner": "Ann", "status": "reviewed",
                       "tags": ["safety", "sil2"]},
             "fmea": {"id": "F-1", "item": "Sensor", "mode": "drift", "cause": "age",
                      "severity": 7, "occurrence": 3, "detection": 4},
             "children": []},
            {"id": "v", "name": "Vote", "type": "Event", "gateType": "KOFN", "k": 2,
             "logicGate": "OR", "children": [
                 {"id": "v1", "name": "V1", "probability": 0.1, "children": []},
                 {"id": "v2", "name": "V2", "probability": 0.1, "children": []},
                 {"id": "h", "name": "House", "eventKind": "house", "houseState": True,
                  "children": []},
             ]},
        ],
    }


def make_core(tree=None, mode="FTA"):
    core = WebCore()
    core.set_data(copy.deepcopy(tree or sample_tree()))
    core.set_metadata(title="Plant", date="2026-01-01", mode=mode)
    core.recalculate_probabilities()
    return core


def sheet_values(ws):
    return [[c.value for c in row] for row in ws.iter_rows()]


def test_events_and_analysis_sheets_are_added(tmp_path):
    core = make_core()
    path = tmp_path / "out.xlsx"
    ok, error = excel_events.export_xlsx(core, str(path))
    assert ok, error
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ["FTA", "Events", "Analysis"]
    assert wb.active.title == "FTA"

    ws = wb["Events"]
    header = [c.value for c in ws[1]]
    assert header == list(excel_events.EVENT_HEADERS)
    assert all(c.font.bold for c in ws[1])
    assert ws.freeze_panes == "C2"
    assert ws.auto_filter.ref.startswith("A1:")
    ids = [ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)]
    assert ids == ["root", "g1", "a", "b", "c", "v", "v1", "v2", "h"]  # tree order

    col = {h: i + 1 for i, h in enumerate(header)}
    row_of = {ws.cell(row=r, column=1).value: r for r in range(2, ws.max_row + 1)}
    a = row_of["a"]
    assert isinstance(ws.cell(row=a, column=col["λ (/h)"]).value, float)
    assert ws.cell(row=a, column=col["λ (/h)"]).value == pytest.approx(1e-5)
    assert ws.cell(row=a, column=col["λ (/h)"]).number_format == "0.00E+00"
    assert ws.cell(row=a, column=col["Model"]).value == "rate"
    assert ws.cell(row=a, column=col["Source"]).value == "OREDA"
    assert ws.cell(row=a, column=col["Unc. EF"]).value == 3
    calc = ws.cell(row=a, column=col["Calculated probability"]).value
    assert isinstance(calc, float) and calc == pytest.approx(1 - 2.718281828459045 ** -0.01, rel=1e-6)
    assert ws.cell(row=a, column=col["Parent Id"]).value == "g1"
    assert ws.cell(row=a, column=col["Depth"]).value == 2

    c = row_of["c"]
    assert ws.cell(row=c, column=col["Base probability"]).value == pytest.approx(2e-7)
    assert ws.cell(row=c, column=col["Requirement ID"]).value == "REQ-1"
    assert ws.cell(row=c, column=col["Tags"]).value == "safety, sil2"
    assert ws.cell(row=c, column=col["RPN"]).value == 84  # derived S*O*D
    assert isinstance(ws.cell(row=c, column=col["S"]).value, int)

    g = row_of["g1"]
    assert ws.cell(row=g, column=col["Node type"]).value == "gate"
    assert ws.cell(row=g, column=col["Gate type"]).value == "AND"
    v = row_of["v"]
    assert ws.cell(row=v, column=col["Gate type"]).value == "KOFN"
    assert ws.cell(row=v, column=col["k"]).value == 2
    h = row_of["h"]
    assert ws.cell(row=h, column=col["Event kind"]).value == "house"
    assert ws.cell(row=h, column=col["House state"]).value == "true"

    analysis = {r[0]: r[1] for r in sheet_values(wb["Analysis"])[1:]}
    assert analysis["Mission time (h)"] == 8760
    assert analysis["Cut sets: max order"] == 6
    assert isinstance(analysis["Top event (headline)"], float)
    assert analysis["Mode"] == "FTA"


def test_fta_sheet_is_unchanged_from_the_core(tmp_path):
    core = make_core()
    plain = tmp_path / "core.xlsx"
    ours = tmp_path / "ours.xlsx"
    assert core.export_to_excel(str(plain))[0]
    assert excel_events.export_xlsx(core, str(ours))[0]
    a = openpyxl.load_workbook(plain)["FTA"]
    b = openpyxl.load_workbook(ours)["FTA"]
    assert sheet_values(a) == sheet_values(b)
    assert {k: v.width for k, v in a.column_dimensions.items()} == {
        k: v.width for k, v in b.column_dimensions.items()}


@pytest.mark.parametrize("sf,fmt", [(1, "0E+00"), (3, "0.00E+00"), (6, "0.00000E+00")])
def test_sig_figs_drive_the_number_format(tmp_path, sf, fmt):
    path = tmp_path / "x.xlsx"
    assert excel_events.export_xlsx(make_core(), str(path), sig_figs=sf)[0]
    ws = openpyxl.load_workbook(path)["Events"]
    col = list(excel_events.EVENT_HEADERS).index("Base probability") + 1
    assert ws.cell(row=5, column=col).number_format == fmt


def test_an_existing_events_sheet_is_replaced(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.title = "FTA"
    stale = wb.create_sheet("Events")
    stale["A1"] = "stale"
    excel_events._write_events(wb, sample_tree(), 3)
    assert wb.sheetnames.count("Events") == 1
    assert wb["Events"]["A1"].value == "Id"


def test_eta_mode_skips_the_summary(tmp_path):
    path = tmp_path / "eta.xlsx"
    assert excel_events.export_xlsx(make_core(mode="ETA"), str(path))[0]
    rows = sheet_values(openpyxl.load_workbook(path)["Analysis"])
    assert any(r[0] == "Summary" and "ETA" in (r[2] or "") for r in rows)


def test_event_rows_are_plain_and_numeric():
    rows = excel_events.event_rows(sample_tree())
    assert [r["Id"] for r in rows][:3] == ["root", "g1", "a"]
    b = next(r for r in rows if r["Id"] == "b")
    assert b["Model"] == "fixed" and b["Base probability"] == 0.01
    assert b["Node type"] == "event" and b["Gate type"] is None


def test_export_route_has_the_events_sheet(tmp_path):
    import flask

    from fta_web.routes.files import files_bp
    from fta_web.routes.tree import tree_bp
    from fta_web.state import get_state, reset_state

    reset_state()
    app = flask.Flask(__name__)
    app.register_blueprint(tree_bp)
    app.register_blueprint(files_bp)
    get_state().fs_root = tmp_path
    source = tmp_path / "doc.json"
    source.write_text(json.dumps({"title": "Doc", "date": "", "mode": "FTA",
                                  "tree": sample_tree()}), encoding="utf-8")
    with app.test_client() as client:
        assert client.post("/api/file/open", json={"path": str(source)}).status_code == 200
        response = client.get("/api/export/xlsx")
        assert response.status_code == 200
        wb = openpyxl.load_workbook(io.BytesIO(response.get_data()))
        assert wb.sheetnames == ["FTA", "Events", "Analysis"]
