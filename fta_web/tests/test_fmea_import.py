"""
FMEA import (1.7 workstream C): ``fta_web.fmea_import`` and ``/api/fmea/*``.
"""
import copy
import json
import math

import pytest

from fta_web import fmea_import
from fta_web.engine import AIAG_OCCURRENCE_TABLE
from fta_web.state import get_state, reset_state

pytest.importorskip("flask")

EN_CSV = (
    "FMEA ID,Item,Failure Mode,Cause,Severity,Occurrence,Detection,RPN,Failure rate\n"
    "F-1,Pump,Fails to start,Motor burnout,8,3,4,96,1e-6\n"
    "F-2,Valve,Stuck closed,Corrosion,7,5,2,70,2e-6\n"
    "\n"
    "F-3,Sensor,No signal,,6,,,,\n"
)


def write(tmp_path, name, text, encoding="utf-8"):
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return path


# ---- read_table ---------------------------------------------------------------------


def test_read_csv_utf8_skips_empty_rows(tmp_path):
    table = fmea_import.read_table(write(tmp_path, "a.csv", EN_CSV))
    assert table["sheets"] == [] and table["sheet"] is None
    assert table["columns"][:3] == ["FMEA ID", "Item", "Failure Mode"]
    assert len(table["rows"]) == 3
    assert table["rowNumbers"] == [2, 3, 5]
    assert table["rows"][2][3] is None  # blank cell -> None


def test_read_csv_cp932_japanese_headers(tmp_path):
    text = "番号,部品,故障モード,原因,影響度,発生度,検出度\nJ-1,ポンプ,起動しない,焼損,8,3,4\n"
    table = fmea_import.read_table(write(tmp_path, "ja.csv", text, "cp932"))
    assert table["columns"][:3] == ["番号", "部品", "故障モード"]
    assert table["rows"][0][1] == "ポンプ"
    mapping = fmea_import.suggest_mapping(table["columns"])
    assert mapping == {
        "id": "番号", "item": "部品", "mode": "故障モード", "cause": "原因",
        "severity": "影響度", "occurrence": "発生度", "detection": "検出度",
    }


def test_read_csv_utf8_bom_and_semicolon(tmp_path):
    text = "﻿ID;Item;Mode;Lambda\nA;Pump;Leak;1,5e-6\nB;Valve;Stuck;2e-6\n"
    table = fmea_import.read_table(write(tmp_path, "semi.csv", text))
    assert table["columns"] == ["ID", "Item", "Mode", "Lambda"]
    assert table["rows"][0] == ["A", "Pump", "Leak", "1,5e-6"]


def test_duplicate_and_blank_headers_are_made_unique(tmp_path):
    table = fmea_import.read_table(write(tmp_path, "d.csv", "Item,Item,,Mode\na,b,c,d\n"))
    assert table["columns"] == ["Item", "Item (2)", "Column 3", "Mode"]


def test_read_xlsx_with_sheets(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    book = openpyxl.Workbook()
    first = book.active
    first.title = "Cover"
    first.append(["nothing here"])
    sheet = book.create_sheet("FMEA")
    sheet.append(["No.", "Item", "Failure mode", "O"])
    sheet.append([1, "Pump", "Leak", 4])
    sheet.append([None, None, None, None])
    sheet.append([2, "Valve", "Stuck", 6])
    path = tmp_path / "f.xlsx"
    book.save(path)

    table = fmea_import.read_table(path, "FMEA")
    assert table["sheets"] == ["Cover", "FMEA"] and table["sheet"] == "FMEA"
    assert table["columns"] == ["No.", "Item", "Failure mode", "O"]
    assert table["rows"] == [[1, "Pump", "Leak", 4], [2, "Valve", "Stuck", 6]]
    assert table["rowNumbers"] == [2, 4]
    assert fmea_import.read_table(path)["sheet"] == "Cover"
    with pytest.raises(fmea_import.FmeaImportError) as info:
        fmea_import.read_table(path, "Nope")
    assert info.value.reason == "unknown_sheet"


def test_unreadable_xlsx(tmp_path):
    pytest.importorskip("openpyxl")
    path = write(tmp_path, "bad.xlsx", "not a zip")
    with pytest.raises(fmea_import.FmeaImportError) as info:
        fmea_import.read_table(path)
    assert info.value.reason == "unreadable"


# ---- suggest_mapping --------------------------------------------------------------------


def test_suggest_mapping_english():
    columns = ["No.", "Item", "Potential Failure Mode", "Potential Cause(s) of Failure",
               "Potential Effect(s)", "Sev", "Occ", "Det", "RPN", "λ (FIT)"]
    assert fmea_import.suggest_mapping(columns) == {
        "id": "No.", "item": "Item", "mode": "Potential Failure Mode",
        "cause": "Potential Cause(s) of Failure", "severity": "Sev", "occurrence": "Occ",
        "detection": "Det", "rpn": "RPN", "lambda": "λ (FIT)",
    }
    assert fmea_import.suggest_lambda_unit("λ (FIT)") == "FIT"


def test_suggest_mapping_japanese_and_fullwidth():
    columns = ["ＩＤ", "構成品", "故障モード", "故障原因", "厳しさ", "発生頻度", "検出度", "故障率 [/年]"]
    mapping = fmea_import.suggest_mapping(columns)
    assert mapping == {
        "id": "ＩＤ", "item": "構成品", "mode": "故障モード", "cause": "故障原因",
        "severity": "厳しさ", "occurrence": "発生頻度", "detection": "検出度",
        "lambda": "故障率 [/年]",
    }
    assert fmea_import.suggest_lambda_unit(mapping["lambda"]) == "y"


def test_suggest_mapping_never_reuses_a_column():
    mapping = fmea_import.suggest_mapping(["Item ID", "Mode"])
    assert list(mapping.values()).count("Item ID") == 1


# ---- apply_import --------------------------------------------------------------------------


def fresh_tree():
    return {"id": "root", "name": "Top", "type": "Root", "probability": 1.0,
            "logicGate": "OR", "notes": "", "links": [], "children": []}


def rows_of(tmp_path, text=EN_CSV):
    table = fmea_import.read_table(write(tmp_path, "x.csv", text))
    return table, fmea_import.suggest_mapping(table["columns"])


def run(tree, table, mapping, **kw):
    kw.setdefault("lambda_unit", "h")
    return fmea_import.apply_import(
        tree, table["rows"], mapping, kw.pop("parent", "root"),
        kw.pop("occ", AIAG_OCCURRENCE_TABLE), "x.csv", columns=table["columns"],
        row_numbers=table["rowNumbers"], **kw)


def test_import_creates_events(tmp_path):
    table, mapping = rows_of(tmp_path)
    tree = fresh_tree()
    result = run(tree, table, mapping)
    assert result["created"] == ["root_0", "root_1", "root_2"]
    pump, valve, sensor = tree["children"]
    assert pump["name"] == "Pump – Fails to start"
    assert pump["fmea"] == {"id": "F-1", "item": "Pump", "mode": "Fails to start",
                            "cause": "Motor burnout", "severity": 8, "occurrence": 3,
                            "detection": 4, "rpn": 96, "source": "x.csv"}
    assert pump["quant"]["model"] == "rate" and pump["quant"]["lambda"] == 1e-6
    assert valve["quant"]["lambda"] == 2e-6
    # No λ and no occurrence: an undeveloped event at 1.0.
    assert sensor["eventKind"] == "undeveloped" and sensor["probability"] == 1.0
    assert "quant" not in sensor


def test_reimport_updates_in_place(tmp_path):
    table, mapping = rows_of(tmp_path)
    tree = fresh_tree()
    run(tree, table, mapping)
    # Move F-2 somewhere else: the update must find it anywhere in the tree.
    valve = tree["children"].pop(1)
    tree["children"][0]["children"].append(valve)
    valve["quant"]["T"] = 100.0

    changed = EN_CSV.replace("2e-6", "5e-6").replace("Stuck closed", "Stuck shut")
    table2, _ = rows_of(tmp_path, changed)
    result = run(tree, table2, mapping)
    assert result["created"] == []
    assert result["updated"] == ["root_1"]
    assert sorted(result["unchanged"]) == ["root_0", "root_2"]
    assert valve["quant"] == {"model": "rate", "lambda": 5e-6, "T": 100.0, "source": "x.csv"}
    assert valve["name"] == "Valve – Stuck shut"
    ids = []
    stack = [tree]
    while stack:
        node = stack.pop()
        ids.append(node.get("fmea", {}).get("id"))
        stack.extend(node.get("children", []))
    assert sorted(i for i in ids if i) == ["F-1", "F-2", "F-3"]


def test_update_false_skips_existing(tmp_path):
    table, mapping = rows_of(tmp_path)
    tree = fresh_tree()
    run(tree, table, mapping)
    result = run(tree, table, mapping, update=False)
    assert [s["reason"] for s in result["skipped"]] == ["exists"] * 3
    assert len(tree["children"]) == 3


@pytest.mark.parametrize("unit,expected", [("FIT", 2.5e-7), ("y", 250 / 8760.0), ("h", 250.0)])
def test_lambda_units(tmp_path, unit, expected):
    table, mapping = rows_of(tmp_path, "ID,Mode,Rate\nA,Leak,250\n")
    tree = fresh_tree()
    run(tree, table, mapping, lambda_unit=unit)
    assert tree["children"][0]["quant"]["lambda"] == pytest.approx(expected)


def test_fit_conversion_has_no_float_noise(tmp_path):
    table, mapping = rows_of(tmp_path, "ID,Mode,Rate\nA,Leak,1000\n")
    tree = fresh_tree()
    run(tree, table, mapping, lambda_unit="FIT")
    assert tree["children"][0]["quant"]["lambda"] == 1e-6


def test_occurrence_uses_the_table(tmp_path):
    table, mapping = rows_of(tmp_path, "ID,Mode,Occurrence\nA,Leak,4\nB,Stuck,7\n")
    custom = dict(AIAG_OCCURRENCE_TABLE, **{"4": 0.123})
    tree = fresh_tree()
    run(tree, table, mapping, occ=custom)
    a, b = tree["children"]
    assert a["probability"] == 0.123 and a["quant"] == {"model": "fixed"}
    assert b["probability"] == AIAG_OCCURRENCE_TABLE["7"]


def test_bad_rows_are_skipped_with_reasons(tmp_path):
    text = ("ID,Item,Mode,Severity,RPN,Rate\n"
            "A,Pump,Leak,11,,\n"
            "B,Pump,Leak2,5,-3,\n"
            "C,Pump,Leak3,5,,abc\n"
            ",,,5,,\n"
            "E,Pump,Ok,5,,1e-6\n"
            "E,Pump,Again,5,,1e-6\n")
    table, mapping = rows_of(tmp_path, text)
    tree = fresh_tree()
    result = run(tree, table, mapping)
    reasons = [(s["row"], s["reason"]) for s in result["skipped"]]
    assert reasons == [(2, "invalidRank"), (3, "invalidRpn"), (4, "invalidLambda"),
                       (5, "noKey"), (7, "duplicate")]
    assert result["created"] == ["root_0"]
    json.dumps(result)  # JSON-safe


def test_key_from_item_and_mode_and_rpn_computed(tmp_path):
    table, mapping = rows_of(tmp_path, "Item,Mode,S,O,D\nPump,Leak,2,3,4\n")
    tree = fresh_tree()
    run(tree, table, mapping)
    fmea = tree["children"][0]["fmea"]
    assert fmea["id"] == "Pump / Leak" and fmea["rpn"] == 24


def test_leaf_parent_becomes_or_gate_and_transfer_refused(tmp_path):
    table, mapping = rows_of(tmp_path, "ID,Mode\nA,Leak\n")
    tree = fresh_tree()
    tree["children"].append({"id": "root_0", "name": "Leaf", "type": "Event",
                             "probability": 0.1, "logicGate": "AND", "eventKind": "basic",
                             "children": []})
    run(tree, table, mapping, parent="root_0")
    leaf = tree["children"][0]
    assert leaf["logicGate"] == "OR" and "eventKind" not in leaf
    assert leaf["children"][0]["id"] == "root_0_0"

    tree["children"].append({"id": "root_1", "name": "T", "gateType": "TRANSFER",
                             "transferTo": "root_0", "children": []})
    with pytest.raises(fmea_import.FmeaImportError) as info:
        run(tree, table, mapping, parent="root_1")
    assert info.value.reason == "parent_transfer"
    with pytest.raises(fmea_import.FmeaImportError) as info:
        run(tree, table, mapping, parent="nope")
    assert info.value.reason == "parent_not_found"


# ---- routes ----------------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    import flask

    from fta_web.routes.files import files_bp
    from fta_web.routes.fmea import fmea_bp
    from fta_web.routes.tree import tree_bp

    reset_state()
    app = flask.Flask(__name__)
    for bp in (tree_bp, files_bp, fmea_bp):
        app.register_blueprint(bp)
    app.config.update(TESTING=True)
    get_state().fs_root = tmp_path
    with app.test_client() as test_client:
        yield test_client


def body(response):
    return json.loads(response.get_data(as_text=True))


def test_preview_route(client, tmp_path):
    path = write(tmp_path, "fmea.csv", EN_CSV)
    response = client.post("/api/fmea/preview", json={"path": str(path)})
    assert response.status_code == 200, body(response)
    payload = body(response)
    assert payload["rowCount"] == 3 and len(payload["rows"]) == 3
    assert payload["suggestedMapping"]["id"] == "FMEA ID"
    assert payload["suggestedLambdaUnit"] == "h"
    assert payload["occurrenceTable"] == AIAG_OCCURRENCE_TABLE
    assert payload["name"] == "fmea.csv"


def test_preview_caps_rows(client, tmp_path):
    lines = ["ID,Mode"] + ["%d,m%d" % (i, i) for i in range(120)]
    path = write(tmp_path, "big.csv", "\n".join(lines))
    payload = body(client.post("/api/fmea/preview", json={"path": "big.csv"}))
    assert payload["rowCount"] == 120 and len(payload["rows"]) == 50


def test_preview_xlsx_route(client, tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    book = openpyxl.Workbook()
    book.active.title = "S1"
    book.active.append(["ID", "Mode"])
    book.active.append(["A", "Leak"])
    book.create_sheet("S2").append(["x"])
    book.save(tmp_path / "f.xlsx")
    payload = body(client.post("/api/fmea/preview", json={"path": "f.xlsx"}))
    assert payload["sheets"] == ["S1", "S2"] and payload["rows"] == [["A", "Leak"]]
    bad = client.post("/api/fmea/preview", json={"path": "f.xlsx", "sheet": "S9"})
    assert bad.status_code == 400 and body(bad)["error"]["detail"]["reason"] == "unknown_sheet"


def import_body(path, **extra):
    base = {"path": str(path), "mapping": {"id": "FMEA ID", "item": "Item",
            "mode": "Failure Mode", "cause": "Cause", "severity": "Severity",
            "occurrence": "Occurrence", "detection": "Detection", "rpn": "RPN",
            "lambda": "Failure rate"}, "lambdaUnit": "h", "parentId": "root", "update": True}
    base.update(extra)
    return base


def test_import_route_single_undo_step(client, tmp_path):
    path = write(tmp_path, "fmea.csv", EN_CSV)
    state = get_state()
    before = copy.deepcopy(state.core.get_data())

    response = client.post("/api/fmea/import", json=import_body(path))
    assert response.status_code == 200, body(response)
    payload = body(response)
    assert payload["created"] == ["root_0", "root_1", "root_2"]
    assert payload["changed"] is True and payload["dirty"] is True and payload["canUndo"]
    assert set(payload) >= {"tree", "zeroNodes", "analysis", "sessionWarnings", "canRedo"}
    pump = state.core.find_node_by_id("root_0")
    assert pump["probability"] == pytest.approx(1 - math.exp(-1e-6 * 8760), rel=1e-6)
    after_import = copy.deepcopy(state.core.get_data())

    undone = body(client.post("/api/undo"))
    assert undone["tree"] == before
    assert undone["canUndo"] is False
    redone = body(client.post("/api/redo"))
    assert redone["tree"] == after_import


def test_import_route_reimport_and_no_op(client, tmp_path):
    path = write(tmp_path, "fmea.csv", EN_CSV)
    client.post("/api/fmea/import", json=import_body(path))
    # Same file again: nothing changes, so no undo step is pushed.
    state = get_state()
    depth = len(state._undo)
    payload = body(client.post("/api/fmea/import", json=import_body(path)))
    assert payload["changed"] is False and payload["created"] == []
    assert sorted(payload["unchanged"]) == ["root_0", "root_1", "root_2"]
    assert len(state._undo) == depth

    path.write_text(EN_CSV.replace("1e-6", "3e-6"), encoding="utf-8")
    payload = body(client.post("/api/fmea/import", json=import_body(path)))
    assert payload["updated"] == ["root_0"] and payload["created"] == []
    assert state.core.find_node_by_id("root_0")["quant"]["lambda"] == 3e-6
    assert len(state._undo) == depth + 1
    assert len(state.core.get_data()["children"]) == 3


def test_import_route_saves_occurrence_table_in_same_step(client, tmp_path):
    path = write(tmp_path, "o.csv", "ID,Mode,Occurrence\nA,Leak,4\n")
    table = {"4": 0.25}
    response = client.post("/api/fmea/import", json={
        "path": "o.csv", "mapping": {"id": "ID", "mode": "Mode", "occurrence": "Occurrence"},
        "parentId": "root", "occurrenceTable": table})
    payload = body(response)
    assert response.status_code == 200, payload
    assert payload["analysis"]["fmeaOccurrenceTable"]["4"] == 0.25
    assert payload["analysis"]["fmeaOccurrenceTable"]["5"] == AIAG_OCCURRENCE_TABLE["5"]
    state = get_state()
    assert state.core.find_node_by_id("root_0")["probability"] == 0.25
    body(client.post("/api/undo"))
    assert state.core.analysis["fmeaOccurrenceTable"] == AIAG_OCCURRENCE_TABLE
    assert state.core.get_data()["children"] == []

    bad = client.post("/api/fmea/import", json={
        "path": "o.csv", "mapping": {"id": "ID"}, "parentId": "root",
        "occurrenceTable": {"4": 2}})
    assert bad.status_code == 400
    assert body(bad)["error"]["detail"]["field"] == "analysis.fmeaOccurrenceTable.4"
    del path


def test_import_route_errors(client, tmp_path):
    path = write(tmp_path, "fmea.csv", EN_CSV)
    r = client.post("/api/fmea/import", json=import_body(path, parentId="missing"))
    assert r.status_code == 404 and body(r)["error"]["code"] == "PARENT_NOT_FOUND"
    r = client.post("/api/fmea/import", json=import_body(path, lambdaUnit="per-min"))
    assert r.status_code == 400
    r = client.post("/api/fmea/import", json=import_body(path, mapping={"id": "Nope"}))
    assert r.status_code == 400 and body(r)["error"]["detail"]["reason"] == "unknown_column"
    r = client.post("/api/fmea/import", json=import_body(path, mapping={"bogus": "Item"}))
    assert r.status_code == 400


@pytest.mark.parametrize("url", ["/api/fmea/preview", "/api/fmea/import"])
def test_sandbox_rejections(client, tmp_path, url):
    outside = tmp_path.parent / "outside_fmea.csv"
    outside.write_text(EN_CSV, encoding="utf-8")
    try:
        for raw, reason in ((str(outside), "outside_root"), ("../outside_fmea.csv", "traversal")):
            r = client.post(url, json=import_body(raw))
            assert r.status_code == 400, body(r)
            err = body(r)["error"]
            assert err["code"] == "PATH_REJECTED" and err["detail"]["reason"] == reason
    finally:
        outside.unlink()
    write(tmp_path, "tree.json", "{}")
    r = client.post(url, json=import_body("tree.json"))
    assert body(r)["error"]["detail"]["reason"] == "extension"
    r = client.post(url, json=import_body("missing.csv"))
    assert r.status_code == 404
    r = client.post(url, json={})
    assert r.status_code == 400


def test_size_cap(client, tmp_path, monkeypatch):
    from fta_web.routes import fmea as fmea_routes

    write(tmp_path, "fmea.csv", EN_CSV)
    monkeypatch.setattr(fmea_routes, "MAX_UPLOAD_BYTES", 10)
    r = client.post("/api/fmea/preview", json={"path": "fmea.csv"})
    assert r.status_code == 413 and body(r)["error"]["detail"]["reason"] == "too_large"


def test_xlsx_without_openpyxl_is_503(client, tmp_path, monkeypatch):
    import importlib.util

    (tmp_path / "f.xlsx").write_bytes(b"PK")
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name, *a, **k: None if name == "openpyxl" else real(name, *a, **k))
    for url in ("/api/fmea/preview", "/api/fmea/import"):
        r = client.post(url, json=import_body("f.xlsx"))
        assert r.status_code == 503
        err = body(r)["error"]
        assert err["code"] == "EXPORT_UNAVAILABLE" and err["detail"]["package"] == "openpyxl"
    # CSV still works without openpyxl.
    write(tmp_path, "fmea.csv", EN_CSV)
    assert client.post("/api/fmea/preview", json={"path": "fmea.csv"}).status_code == 200


@pytest.mark.parametrize("url", ["/api/fmea/preview", "/api/fmea/import"])
def test_eta_mode_is_409(client, tmp_path, url):
    path = write(tmp_path, "fmea.csv", EN_CSV)
    client.post("/api/metadata", json={"mode": "ETA"})
    r = client.post(url, json=import_body(path))
    assert r.status_code == 409 and body(r)["error"]["code"] == "MODE_UNSUPPORTED"
