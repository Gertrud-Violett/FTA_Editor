"""F0 BRIEF criteria 3, 4, 5 and 6: the shape of the committed performance fixtures.

Every expected value is built here from SPEC 7.6 / 7.1 / 7.3 by loops (ids,
parent-child structure, gate rule per node, component q, the CCF groups,
settings), never by reading the generator. The files checked are the ones
committed in ``fta_web/tests/fixtures/``:

* criterion 3 -- ``perf_ccf_301.json`` (beta groups G1..G10)
* criterion 4 -- ``perf_alpha_301.json`` (alpha groups A1..A5)
* criterion 5 -- the two ``_nogroups`` files equal the group files minus
  ``analysis.ccfGroups`` and ``fileFormatVersion`` and open in the current
  app with no load warning
* criterion 6 -- ``perf_grid_500.json`` and ``perf_grid_500_paste.tsv``

Assumption (SPEC 7.6 shows ``G00``..``G24`` only): the event ids of the grid
are zero-padded to two digits on both sides, ``E00_00`` .. ``E24_19``.
"""
import json
import math
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

CCF = "perf_ccf_301.json"
ALPHA = "perf_alpha_301.json"
CCF_NG = "perf_ccf_301_nogroups.json"
ALPHA_NG = "perf_alpha_301_nogroups.json"
GRID = "perf_grid_500.json"
PASTE = "perf_grid_500_paste.tsv"

CUTSETS = {"maxOrder": 6, "maxCount": 5000, "cutoff": 1e-30}
MODEL_KEYS = {"lambda", "T", "tau", "mu", "mttr"}

# SPEC 7.6
BETA_MODULES = [(0, 1), (0, 3), (0, 5), (2, 1), (2, 3), (2, 5), (4, 1), (4, 3), (4, 5)]
BETA_MEMBERS = [["C%d_%d_%d" % (i, j, m) for m in range(3)] for i, j in BETA_MODULES]
BETA_MEMBERS.append(["C4_5_3", "C4_5_4", "C4_5_5"])
ALPHA_MODULES = [(0, 1), (0, 3), (0, 5), (2, 1), (2, 3)]
ALPHA_MEMBERS = [["C%d_%d_%d" % (i, j, m) for m in range(4)] for i, j in ALPHA_MODULES]
ALPHA_VALUES = [0.95, 0.03, 0.01, 0.01]
GROUP_KEYS = {"id", "name", "model", "beta", "alpha", "testing", "members", "source"}


def load(name):
    path = FIXTURES / name
    assert path.is_file(), "missing fixture file: %s" % path
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# the expected trees, as (id, parent, gate-or-None-for-a-leaf, q-or-None)
# --------------------------------------------------------------------------


def expected_rows_301(member_ids):
    members = set(member_ids)
    rows = [("root", None, "OR", None)]
    for i in range(6):
        rows.append(("S%d" % i, "root", "AND" if i % 2 else "OR", None))
        for j in range(7):
            mid = "M%d_%d" % (i, j)
            rows.append((mid, "S%d" % i, "AND" if (i + j) % 2 else "OR", None))
            for m in range(6):
                cid = "C%d_%d_%d" % (i, j, m)
                rows.append((cid, mid, None, 1e-3 if cid in members else 1e-3 * (m + 1)))
    return rows


def expected_rows_grid():
    rows = [("root", None, "OR", None)]
    for gg in range(25):
        rows.append(("G%02d" % gg, "root", "OR", None))
        for nn in range(20):
            rows.append(("E%02d_%02d" % (gg, nn), "G%02d" % gg, None, None))
    return rows


def walk(node, parent=None):
    """Document order (pre-order): (id, parent id, gate or None for a leaf, node)."""
    out = [(node["id"], parent, node["logicGate"] if node["children"] else None, node)]
    for child in node["children"]:
        out.extend(walk(child, node["id"]))
    return out


def beta_groups():
    return [{"id": "G%d" % (k + 1), "name": None, "model": "beta", "beta": 0.1,
             "alpha": None, "testing": None, "members": members, "source": None}
            for k, members in enumerate(BETA_MEMBERS)]


def alpha_groups():
    return [{"id": "A%d" % (k + 1), "name": None, "model": "alpha", "beta": None,
             "alpha": ALPHA_VALUES, "testing": "staggered", "members": members,
             "source": None}
            for k, members in enumerate(ALPHA_MEMBERS)]


def check_node_keys(node):
    assert isinstance(node["id"], str) and node["id"]
    assert isinstance(node["name"], str) and node["name"].strip(), node["id"]
    assert isinstance(node["type"], str) and node["type"], node["id"]
    assert node["logicGate"] in ("AND", "OR"), node["id"]
    assert isinstance(node["probability"], (int, float)) and not isinstance(node["probability"], bool)
    assert math.isfinite(node["probability"]), node["id"]
    assert isinstance(node["children"], list)


# --------------------------------------------------------------------------
# criteria 3 and 4: the two group files
# --------------------------------------------------------------------------

CCF_CASES = [(CCF, BETA_MEMBERS), (ALPHA, ALPHA_MEMBERS),
             (CCF_NG, BETA_MEMBERS), (ALPHA_NG, ALPHA_MEMBERS)]


@pytest.mark.parametrize("name", [CCF, ALPHA, CCF_NG, ALPHA_NG, GRID])
def test_top_level_keys_of_the_analysis_file(name):
    document = load(name)
    assert isinstance(document["title"], str) and document["title"]
    assert isinstance(document["date"], str) and document["date"]
    assert document["mode"] == "FTA"
    assert isinstance(document["tree"], dict)
    assert isinstance(document["analysis"], dict)


@pytest.mark.parametrize("name, groups", CCF_CASES)
def test_the_301_node_tree_has_the_ids_structure_gates_and_q_of_spec_7_6(name, groups):
    members = [m for g in groups for m in g]
    tree = load(name)["tree"]
    actual = walk(tree)
    expected = expected_rows_301(members)
    assert len(actual) == 301
    assert [row[:3] for row in actual] == [row[:3] for row in expected]
    assert len({row[0] for row in actual}) == 301
    for (nid, _p, gate, node), (_i, _pp, _g, q) in zip(actual, expected):
        check_node_keys(node)
        if gate is None:
            assert node["children"] == []
            assert node["probability"] == pytest.approx(q, rel=1e-12), nid
            quant = node["quant"]
            assert quant["model"] == "fixed", nid
            assert not (set(quant) & MODEL_KEYS), nid
    assert tree["id"] == "root"


@pytest.mark.parametrize("name", [CCF, ALPHA, CCF_NG, ALPHA_NG])
def test_the_analysis_cutset_settings_are_stored(name):
    assert load(name)["analysis"]["cutsets"] == CUTSETS


def test_the_beta_fixture_has_the_ten_groups_of_spec_7_6():
    document = load(CCF)
    assert document["fileFormatVersion"] == 2
    assert type(document["fileFormatVersion"]) is int
    groups = document["analysis"]["ccfGroups"]
    expected = beta_groups()
    assert [g["id"] for g in groups] == ["G%d" % k for k in range(1, 11)]
    for group, want in zip(groups, expected):
        assert set(group) == GROUP_KEYS
        assert group["model"] == "beta"
        assert group["beta"] == pytest.approx(0.1, rel=1e-12)
        assert group["alpha"] is None and group["testing"] is None
        assert group["members"] == want["members"]
        assert isinstance(group["name"], str) and group["name"].strip()
        assert isinstance(group["source"], str)


def test_the_alpha_fixture_has_the_five_staggered_groups_of_spec_7_6():
    document = load(ALPHA)
    assert document["fileFormatVersion"] == 2
    assert type(document["fileFormatVersion"]) is int
    groups = document["analysis"]["ccfGroups"]
    expected = alpha_groups()
    assert [g["id"] for g in groups] == ["A%d" % k for k in range(1, 6)]
    for group, want in zip(groups, expected):
        assert set(group) == GROUP_KEYS
        assert group["model"] == "alpha"
        assert group["beta"] is None
        assert group["testing"] == "staggered"
        assert group["alpha"] == pytest.approx(ALPHA_VALUES, rel=1e-12)
        assert len(group["alpha"]) == 4
        assert group["members"] == want["members"]
        assert isinstance(group["name"], str) and group["name"].strip()
        assert isinstance(group["source"], str)


def test_ccf_group_members_are_components_of_and_modules_under_or_subsystems():
    """SPEC 7.6: all groups sit in AND modules under S0, S2, S4."""
    for name in (CCF, ALPHA):
        document = load(name)
        parent = {nid: (p, node) for nid, p, _g, node in walk(document["tree"])}
        for group in document["analysis"]["ccfGroups"]:
            for member in group["members"]:
                module_id, node = parent[member]
                assert node["children"] == []
                module = parent[module_id][1]
                assert module["logicGate"] == "AND"
                assert parent[module_id][0] in ("S0", "S2", "S4")


@pytest.mark.parametrize("with_groups, without_groups", [(CCF, CCF_NG), (ALPHA, ALPHA_NG)])
def test_nogroups_file_is_the_group_file_without_groups_and_format_version(with_groups, without_groups):
    document = load(with_groups)
    del document["fileFormatVersion"]
    del document["analysis"]["ccfGroups"]
    stripped = load(without_groups)
    assert "fileFormatVersion" not in stripped
    assert "ccfGroups" not in stripped["analysis"]
    assert stripped == document


@pytest.mark.parametrize("name", [CCF_NG, ALPHA_NG, GRID])
def test_files_without_groups_carry_no_format_version(name):
    assert "fileFormatVersion" not in load(name)
    assert "ccfGroups" not in load(name)["analysis"]


# --------------------------------------------------------------------------
# criterion 5 (second half): the current app opens them without a warning
# --------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    """A bare Flask app with the file and tree blueprints (as test_api_files.py)."""
    flask = pytest.importorskip("flask")
    from fta_web.routes.files import files_bp
    from fta_web.routes.tree import tree_bp
    from fta_web.state import get_state, reset_state

    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    reset_state()
    app = flask.Flask(__name__)
    app.register_blueprint(files_bp)
    app.register_blueprint(tree_bp)
    app.config.update(TESTING=True)
    get_state().fs_root = sandbox
    with app.test_client() as test_client:
        test_client.sandbox = sandbox
        yield test_client
    reset_state()


@pytest.mark.parametrize("name", [CCF_NG, ALPHA_NG, GRID])
def test_the_current_app_opens_the_file_with_no_load_warning(client, name):
    source = FIXTURES / name
    assert source.is_file(), "missing fixture file: %s" % source
    target = client.sandbox / name
    shutil.copyfile(source, target)
    response = client.post("/api/file/open", json={"path": str(target)})
    payload = json.loads(response.get_data(as_text=True))
    assert response.status_code == 200, payload
    assert payload["ok"] is True
    assert payload["warnings"] == []


@pytest.mark.parametrize("name", [CCF_NG, ALPHA_NG])
def test_the_engine_reads_the_stored_probability_of_a_fixed_event(name):
    """For model ``fixed`` the node's ``probability`` is the q the analysis uses."""
    from fta_web import logic

    document = load(name)
    structure = logic.compile_tree(document["tree"], document["analysis"])
    stored = {nid: node["probability"] for nid, _p, gate, node in walk(document["tree"])
              if gate is None}
    assert len(stored) == 252
    assert {e["id"] for e in structure.events} == set(stored)
    for event in structure.events:
        assert event["q"] == pytest.approx(stored[event["id"]], rel=1e-12), event["id"]


# --------------------------------------------------------------------------
# criterion 6: the grid fixture and the paste file
# --------------------------------------------------------------------------


def test_the_grid_tree_has_the_ids_structure_and_gates_of_spec_7_6():
    document = load(GRID)
    actual = walk(document["tree"])
    expected = expected_rows_grid()
    assert len(actual) == 526
    assert [row[:3] for row in actual] == [row[:3] for row in expected]
    leaves = [row for row in actual if row[2] is None]
    assert len(leaves) == 500
    for _nid, _p, gate, node in actual:
        check_node_keys(node)
    assert document["tree"]["id"] == "root"


def test_every_grid_event_is_a_rate_event_of_1e_minus_6_per_hour_and_8760_hours():
    for nid, _p, gate, node in walk(load(GRID)["tree"]):
        if gate is not None:
            continue
        quant = node["quant"]
        assert set(quant) == {"model", "lambda", "T"}, nid
        assert quant["model"] == "rate", nid
        assert quant["lambda"] == pytest.approx(1e-6, rel=1e-12), nid
        assert quant["T"] == pytest.approx(8760.0, rel=1e-12), nid
        assert 0.0 <= node["probability"] <= 1.0


def test_the_paste_file_has_500_rows_of_lambda_per_year_t_and_source():
    path = FIXTURES / PASTE
    assert path.is_file(), "missing fixture file: %s" % path
    text = path.read_bytes().decode("utf-8")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # one final line break is allowed
    lines = [line[:-1] if line.endswith("\r") else line for line in lines]
    assert len(lines) == 500
    for number, line in enumerate(lines, start=1):
        cells = line.split("\t")
        assert len(cells) == 3, (number, line)
        assert all(cell.strip() for cell in cells), (number, line)
        lam, duration = float(cells[0]), float(cells[1])
        assert math.isfinite(lam) and lam > 0, (number, line)
        assert math.isfinite(duration) and duration > 0, (number, line)
