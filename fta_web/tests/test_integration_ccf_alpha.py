"""Integration of CCF beta (F2) and alpha (F2A): PLAN section 6, scenario F2 + F2A.

One file holds a beta group of 2 members and a staggered alpha group of 3 members
in one tree. It must round-trip through the file routes (FN-18, SPEC 7.1: the
eight keys of a group, ``fileFormatVersion`` 2), and both groups must appear in the
cut sets (with the MCUB as headline), in the DOCX report and in the CLI ``ccf``
block. The expected top value is written out here from S1 Eq. 5.6 (staggered
alpha) and the beta split Q_1 = (1-beta) Q_t, Q_m = beta Q_t; no expected value
comes from the product.
"""
import io
import json
import math

import pytest

flask = pytest.importorskip("flask")

QT_BETA = 2e-3       # the two beta members (identical, as the beta model needs)
BETA = 0.1
QT_ALPHA = 1e-3      # the three alpha members
ALPHA = [0.955, 0.034, 0.011]
GROUP_KEYS = {"id", "name", "model", "beta", "alpha", "testing", "members", "source"}


def _leaf(node_id, q):
    return {"id": node_id, "name": "Pump " + node_id, "type": "Event", "logicGate": "OR",
            "probability": q, "notes": "", "links": [], "children": [],
            "quant": {"model": "fixed"}}


def _document():
    """Top = OR[ AND(A, B), 2-of-3(C, D, E) ]; beta group over A, B; alpha group over C, D, E."""
    pair = {"id": "G1", "name": "Feed pumps fail", "type": "Event", "logicGate": "AND",
            "probability": 1.0, "notes": "", "links": [],
            "children": [_leaf("A", QT_BETA), _leaf("B", QT_BETA)]}
    vote = {"id": "V1", "name": "Relief valves fail", "type": "Event", "logicGate": "OR",
            "gateType": "KOFN", "k": 2, "probability": 1.0, "notes": "", "links": [],
            "children": [_leaf("C", QT_ALPHA), _leaf("D", QT_ALPHA), _leaf("E", QT_ALPHA)]}
    tree = {"id": "root", "name": "Top event", "type": "Root", "logicGate": "OR",
            "probability": 1.0, "notes": "", "links": [], "children": [pair, vote]}
    groups = [
        {"id": "gb", "name": "Feed pumps", "model": "beta", "beta": BETA, "alpha": None,
         "testing": None, "members": ["A", "B"], "source": "test"},
        {"id": "ga", "name": "Relief valves", "model": "alpha", "beta": None,
         "alpha": list(ALPHA), "testing": "staggered", "members": ["C", "D", "E"],
         "source": "test"},
    ]
    return {"title": "CCF beta and alpha", "date": "2026-11-02", "mode": "FTA",
            "fileFormatVersion": 2, "tree": tree, "analysis": {"ccfGroups": groups}}


def _hand_mcub():
    """MCUB = 1 - prod(1 - P(cut set)), the cut sets written out by hand.

    beta group (AND of A, B): {A_ind, B_ind} and {CCF}; Q_1 = (1-b) Q_t, Q_m = b Q_t.
    alpha group (2-of-3 of C, D, E), staggered Eq. 5.6: Q_k = alpha_k / C(m-1, k-1) Q_t.
    The 2-of-3 has {Ci, Cj} for the 3 pairs of independent parts, one cut set per
    2-member CCF event, and the 3-member CCF event: 7 cut sets."""
    q1_beta, q_ccf_beta = (1 - BETA) * QT_BETA, BETA * QT_BETA
    m = len(ALPHA)
    q1, q2, q3 = (ALPHA[k - 1] / math.comb(m - 1, k - 1) * QT_ALPHA for k in (1, 2, 3))
    survive = ((1 - q1_beta ** 2) * (1 - q_ccf_beta)
               * (1 - q1 ** 2) ** 3 * (1 - q2) ** 3 * (1 - q3))
    return 1 - survive


@pytest.fixture()
def api(tmp_path):
    from fta_web.routes.analysis import analysis_bp
    from fta_web.routes.ccf import ccf_bp
    from fta_web.routes.files import files_bp
    from fta_web.routes.report import report_bp
    from fta_web.routes.tree import tree_bp
    from fta_web.state import get_state, reset_state

    reset_state()
    app = flask.Flask(__name__)
    for blueprint in (tree_bp, files_bp, analysis_bp, report_bp, ccf_bp):
        app.register_blueprint(blueprint)
    app.config.update(TESTING=True)
    get_state().fs_root = tmp_path
    with app.test_client() as client:
        yield client
    reset_state()


def _json(response):
    assert response.status_code == 200, response.get_data(as_text=True)[:300]
    return json.loads(response.get_data(as_text=True))


def _open(api, path):
    return _json(api.post("/api/file/open", json={"path": str(path), "force": True}))


@pytest.fixture()
def opened(api, tmp_path):
    path = tmp_path / "both.json"
    path.write_text(json.dumps(_document(), ensure_ascii=False, indent=2), encoding="utf-8")
    _open(api, path)
    return path


def _stored_groups():
    from fta_web.state import get_state

    return json.loads(json.dumps(get_state().core.analysis.get("ccfGroups")))


def test_both_groups_round_trip_through_the_file_routes(api, opened, tmp_path):
    groups = _document()["analysis"]["ccfGroups"]
    assert _stored_groups() == groups
    listing = _json(api.get("/api/ccf/groups"))
    assert [g["status"]["applied"] for g in listing["groups"]] == [True, True]

    saved = tmp_path / "saved.json"
    _json(api.post("/api/file/save-as", json={"path": str(saved)}))
    on_disk = json.loads(saved.read_text(encoding="utf-8"))
    assert on_disk["fileFormatVersion"] == 2
    assert on_disk["analysis"]["ccfGroups"] == groups
    assert all(set(g) == GROUP_KEYS for g in on_disk["analysis"]["ccfGroups"])

    _open(api, opened)                       # replace the document, then reopen the saved file
    assert _stored_groups() == groups
    _open(api, saved)
    assert _stored_groups() == groups


def test_cut_sets_hold_the_beta_and_alpha_events_and_the_headline_is_the_mcub(api, opened):
    body = _json(api.post("/api/analysis/cutsets", json={"limit": 50}))
    ids = {e["id"] for cs in body["cutSets"] for e in cs["events"] if e["id"].startswith("ccf:")}
    assert ids == {"ccf:gb", "ccf:ga:C+D", "ccf:ga:C+E", "ccf:ga:D+E", "ccf:ga:C+D+E"}
    assert body["total"] == 2 + 7
    expected = _hand_mcub()
    assert body["mcub"] == pytest.approx(expected, rel=1e-9, abs=0)

    summary = _json(api.get("/api/analysis/summary"))
    assert summary["headlineMethod"] == "mcub"
    assert summary["headline"] == pytest.approx(expected, rel=1e-9, abs=0)


def _docx_text(blob):
    import docx

    document = docx.Document(io.BytesIO(blob))
    rows = [[c.text for c in row.cells] for table in document.tables for row in table.rows]
    text = "\n".join([p.text for p in document.paragraphs] + [" | ".join(r) for r in rows])
    table = next(t for t in document.tables if "Testing scheme" in [c.text for c in t.rows[0].cells])
    header = [c.text for c in table.rows[0].cells]
    groups = {row.cells[0].text: dict(zip(header, (c.text for c in row.cells)))
              for row in table.rows[1:]}
    return text, groups


def test_the_report_lists_both_groups_with_model_parameters_and_testing_scheme(api, opened):
    response = api.post("/api/report/docx", json={"lang": "en"})
    assert response.status_code == 200, response.get_data()[:300]
    text, groups = _docx_text(response.get_data())
    beta_row, alpha_row = groups["Feed pumps"], groups["Relief valves"]
    assert beta_row["Model"] == "Beta factor" and "β = 0.1" in beta_row["Parameters"]
    assert alpha_row["Model"] == "Alpha factor"
    assert "α = (0.955, 0.034, 0.011)" in alpha_row["Parameters"]
    assert alpha_row["Testing scheme"] == "Staggered testing"
    assert "Pump A" in beta_row["Members"] and "Pump E" in alpha_row["Members"]
    assert "includes CCF (2 groups)" in text


def test_the_cli_json_ccf_block_lists_both_groups(opened, capsys):
    from fta_web import cli

    for command in ("quantify", "cutsets"):
        assert cli.main([command, str(opened), "--json"]) == 0
        entry = json.loads(capsys.readouterr().out)
        by_id = {item["id"]: item for item in entry["results"]["ccf"]["applied"]}
        assert set(by_id) == {"gb", "ga"} and entry["results"]["ccf"]["notApplied"] == []
        assert by_id["gb"]["model"] == "beta" and by_id["gb"]["beta"] == BETA
        assert by_id["ga"]["model"] == "alpha" and by_id["ga"]["beta"] is None
        assert by_id["ga"]["alpha"] == ALPHA and by_id["ga"]["testing"] == "staggered"
        assert by_id["ga"]["members"] == ["C", "D", "E"]
