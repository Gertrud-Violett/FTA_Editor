"""Analysis, diagram and AI (usability work order, batch 3).

One block per item of the work order, by its number there. The server side
is exercised through the real blueprints on a bare Flask app. A pure function
of the page is run in node where node is installed; what only exists as
wiring is checked in the source, and the whole flow is driven in a real
browser by ``tests/gui/s_ux3.js``.

No test reaches the network. The AI provider is mocked at the instance, as in
``test_api_ai.py``, and the per-user folder (credentials, ``ui_prefs.json``)
is redirected to ``tmp_path`` for every test here.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from AI_agent_handler import AIAgentHandler, AICredentialManager  # noqa: E402
from ai_providers import AIProviderFactory  # noqa: E402

from fta_web import ai_bridge, config  # noqa: E402
from fta_web.diagram_dot import build_dot_text2  # noqa: E402
from fta_web.engine import WebCore  # noqa: E402
from fta_web.state import get_state, reset_state  # noqa: E402

STATIC = REPO / "fta_web" / "static" / "js"
CSS = REPO / "fta_web" / "static" / "css" / "app.css"
INDEX = REPO / "fta_web" / "templates" / "index.html"
DOCS = REPO / "docs"

API_KEY = "sk-testkeyDONOTLEAK0123456789abcdefAB12"
PROVIDER_NAME = "OpenAI"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _braced(src: str, start: int) -> str:
    """Source from `start` to the brace that closes the first `{` after it."""
    depth = 0
    for i in range(src.index("{", start), len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError("unbalanced braces")


def _function(src: str, header: str) -> str:
    return _braced(src, src.index(header))


def _node(script: str):
    out = subprocess.run(["node", "-"], input=script, capture_output=True, text=True,
                         encoding="utf-8", check=True, timeout=60).stdout
    return json.loads(out)


def body(response):
    return json.loads(response.get_data(as_text=True))


def error(response):
    return body(response)["error"]


# ---- fixtures -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def per_user_home(tmp_path, monkeypatch):
    """The per-user folder in tmp_path: credentials and ui_prefs.json."""
    directory = tmp_path / "fta_editor_home"
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_DIR", directory)
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_FILE", directory / "ai_credentials.json")
    return directory


@pytest.fixture
def app(tmp_path, monkeypatch):
    flask = pytest.importorskip("flask")
    from fta_web.routes import ai as ai_routes
    from fta_web.routes.ai import ai_bp
    from fta_web.routes.analysis import analysis_bp
    from fta_web.routes.files import files_bp
    from fta_web.routes.render import render_bp
    from fta_web.routes.tree import tree_bp

    reset_state()
    # No handler yet, as in a process nobody has used the assistant in.
    monkeypatch.setattr(ai_bridge, "_handler", None)
    ai_routes._set_pending_update(None)
    built = flask.Flask(__name__)
    for blueprint in (tree_bp, files_bp, ai_bp, analysis_bp, render_bp):
        built.register_blueprint(blueprint)
    built.config.update(TESTING=True)
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    get_state().fs_root = sandbox
    return built


@pytest.fixture
def client(app):
    with app.test_client() as test_client:
        yield test_client


def add(client, parent="root", **fields):
    payload = {"parentId": parent, "name": "node", "probability": 0.1}
    payload.update(fields)
    response = client.post("/api/nodes", json=payload)
    assert response.status_code == 200, body(response)
    return body(response)["node"]["id"]


def state_of(client):
    return body(client.get("/api/state"))


def find(tree, node_id):
    if str(tree["id"]) == node_id:
        return tree
    for child in tree.get("children") or []:
        found = find(child, node_id)
        if found:
            return found
    return None


def child_ids(client, node_id="root"):
    return [c["id"] for c in find(state_of(client)["tree"], node_id).get("children") or []]


def undo_depth(client):
    """How many undo steps there are, counted by taking them (and putting them back)."""
    steps = 0
    while client.post("/api/undo", json={}).status_code == 200:
        steps += 1
    for _ in range(steps):
        assert client.post("/api/redo", json={}).status_code == 200
    return steps


@pytest.fixture
def tree(client):
    """root -> G (A, B), C, D, E. Returns the ids by name."""
    ids = {"G": add(client, name="G", logicGate="AND")}
    ids["A"] = add(client, ids["G"], name="A", probability=0.1)
    ids["B"] = add(client, ids["G"], name="B", probability=0.2)
    for name in ("C", "D", "E"):
        ids[name] = add(client, name=name, probability=0.05)
    return ids


# =============================================================================================
# 37: an event tree is drawn without gates
# =============================================================================================


def _core(mode):
    core = WebCore()
    core.set_metadata(title="T", date="2026-10-12")
    core.mode = mode
    def leaf(node_id, name, probability, gate="OR"):
        return {"id": node_id, "name": name, "type": "Event", "probability": probability,
                "logicGate": gate, "notes": "", "links": [], "children": []}

    core.add_node_to_data("root", leaf("root_0", "Branch", 0.5, "AND"))
    core.add_node_to_data("root_0", leaf("root_0_0", "Leaf one", 0.1))
    core.add_node_to_data("root_0", leaf("root_0_1", "Leaf two", 0.2))
    core.recalculate_probabilities()
    return core


def test_37_the_symbols_diagram_of_an_event_tree_has_no_gate_or_event_symbols():
    eta, id_map = build_dot_text2(_core("ETA"), style="symbols")
    assert "fta-gate" not in eta and "fta-event" not in eta and "__gate" not in eta
    assert eta.count('class="fta-box"') == 4
    # every node is drawn and maps to itself only: no symbol nodes in the id map
    assert sorted(set(id_map.values())) == sorted(id_map.values())
    assert len(id_map) == 4
    # the boxes are joined to each other
    assert re.search(r"\n  root -> \w+;", eta)

    fta, fta_map = build_dot_text2(_core("FTA"), style="symbols")
    assert fta.count('class="fta-gate ') == 2 and "__gate" in fta and "fta-event-basic" in fta
    assert len(fta_map) == 8, "FTA is drawn as before: a box and a symbol per node"


def test_37_an_event_tree_box_shows_its_own_and_its_path_probability():
    eta, _ = build_dot_text2(_core("ETA"), style="symbols")
    # the branch: its own 0.5, and the root's 1.0 x 0.5 down to it
    assert "q=0.500" in eta and "q=0.100 | Q=0.0500" in eta and "q=0.200 | Q=0.100" in eta
    fta, _ = build_dot_text2(_core("FTA"), style="symbols")
    assert "Q=0.0200" in fta and "q=0.100" in fta and "| Q=" not in fta


def test_37_the_compact_diagram_of_an_event_tree_names_no_gate():
    eta, _ = build_dot_text2(_core("ETA"), style="compact")
    assert "Gate:" not in eta
    assert eta.count("P:") == 4 and eta.count("P_calc:") == 4, "the numbers the label parsers read stay"
    fta, _ = build_dot_text2(_core("FTA"), style="compact")
    assert "Gate: AND" in fta


def test_37_the_dot_endpoint_follows_the_document_mode(client, tree):
    assert "fta-gate" in body(client.get("/api/dot?style=symbols"))["dot"]
    assert client.post("/api/metadata", json={"mode": "ETA"}).status_code == 200
    answer = body(client.get("/api/dot?style=symbols"))
    assert "fta-gate" not in answer["dot"] and "fta-event" not in answer["dot"]
    assert sorted(answer["idMap"].values()) == sorted(["root"] + list(tree.values()))


def test_37_the_page_greys_the_four_tabs_and_names_the_initiating_event():
    host = _read(STATIC / "tabs" / "host.js")
    assert "ETA_UNAVAILABLE = Object.freeze(['quant', 'cutsets', 'importance', 'uncertainty'])" in host
    mode = _function(host, "function applyMode()")
    assert "classList.toggle('is-unavailable', off)" in mode and "t('tab.etaUnavailable')" in mode
    assert "disabled" not in mode, "greyed, not disabled: the panel still explains itself"
    main = _read(STATIC / "main.js")
    label = _function(main, "function syncHeadlineLabel(state)")
    assert "'headline.labelEta'" in label and "'headline.titleEta'" in label
    assert "syncHeadlineLabel(state);" in _function(main, "function renderShell(state)")
    assert ".tabstrip__tab.is-unavailable" in _read(CSS)


# =============================================================================================
# 44: several nodes in one step
# =============================================================================================


def test_44_batch_delete_removes_them_all_as_one_undo_step(client, tree):
    before = state_of(client)["tree"]
    depth = undo_depth(client)
    response = client.post("/api/batch/delete", json={"ids": [tree["C"], tree["E"], tree["G"]]})
    answer = body(response)
    assert response.status_code == 200, answer
    assert sorted(answer["deletedIds"]) == sorted([tree["C"], tree["E"], tree["G"]])
    assert child_ids(client) == [tree["D"]]
    assert undo_depth(client) == depth + 1
    assert client.post("/api/undo", json={}).status_code == 200
    assert state_of(client)["tree"] == before


def test_44_batch_delete_drops_a_node_that_goes_with_its_ancestor(client, tree):
    answer = body(client.post("/api/batch/delete", json={"ids": [tree["A"], tree["G"]]}))
    assert answer["deletedIds"] == [tree["G"]]
    assert find(answer["tree"], tree["A"]) is None and find(answer["tree"], tree["B"]) is None


def test_44_batch_delete_reports_the_links_it_removed(client, tree):
    client.patch("/api/nodes/%s" % tree["D"], json={"links": [{"targetId": tree["C"], "relation": "AND"}]})
    answer = body(client.post("/api/batch/delete", json={"ids": [tree["C"], tree["E"]]}))
    assert [link["targetId"] for link in answer["removedLinks"]] == [tree["C"]]
    assert not find(answer["tree"], tree["D"]).get("links")
    assert any(issue["code"] == "LINKS_REMOVED" for issue in answer["sessionWarnings"])


@pytest.mark.parametrize("ids,status,code", [
    (["root", "C"], 400, "ROOT_PROTECTED"),
    (["C", "no-such-node"], 404, "NODE_NOT_FOUND"),
    ([], 400, "INVALID_FIELD"),
    ("C", 400, "INVALID_FIELD"),
    (["C", 7], 400, "INVALID_FIELD"),
    (None, 400, "INVALID_FIELD"),
])
def test_44_a_refused_batch_delete_deletes_nothing(client, tree, ids, status, code):
    if isinstance(ids, list):
        ids = [tree.get(value, value) if isinstance(value, str) else value for value in ids]
    before = state_of(client)
    response = client.post("/api/batch/delete", json={"ids": ids})
    assert response.status_code == status and error(response)["code"] == code
    after = state_of(client)
    assert after["tree"] == before["tree"] and after["revision"] == before["revision"]


def test_44_batch_move_keeps_the_tree_order_and_is_one_undo_step(client, tree):
    before = state_of(client)["tree"]
    depth = undo_depth(client)
    # asked for in the "wrong" order: the block keeps the order the tree showed
    response = client.post("/api/batch/move", json={
        "ids": [tree["E"], tree["C"]], "newParentId": tree["G"], "index": 1})
    answer = body(response)
    assert response.status_code == 200, answer
    assert answer["movedIds"] == [tree["C"], tree["E"]] and answer["parentId"] == tree["G"]
    assert child_ids(client, tree["G"]) == [tree["A"], tree["C"], tree["E"], tree["B"]]
    assert child_ids(client) == [tree["G"], tree["D"]]
    assert undo_depth(client) == depth + 1
    client.post("/api/undo", json={})
    assert state_of(client)["tree"] == before


def test_44_batch_move_index_counts_the_nodes_that_stay(client, tree):
    # root: G C D E. Move C and D to after E: among the stayers [G, E] that is index 2.
    client.post("/api/batch/move", json={"ids": [tree["C"], tree["D"]], "newParentId": "root", "index": 2})
    assert child_ids(client) == [tree["G"], tree["E"], tree["C"], tree["D"]]
    # and to the front, the two not next to each other gathered into a block
    client.post("/api/batch/move", json={"ids": [tree["G"], tree["C"]], "newParentId": "root", "index": 0})
    assert child_ids(client) == [tree["G"], tree["C"], tree["E"], tree["D"]]
    # null appends; an index past the end is clamped
    client.post("/api/batch/move", json={"ids": [tree["G"], tree["C"]], "newParentId": "root", "index": None})
    assert child_ids(client) == [tree["E"], tree["D"], tree["G"], tree["C"]]
    client.post("/api/batch/move", json={"ids": [tree["E"]], "newParentId": "root", "index": 99})
    assert child_ids(client) == [tree["D"], tree["G"], tree["C"], tree["E"]]


def test_44_a_batch_move_to_where_they_are_costs_no_undo_step(client, tree):
    depth = undo_depth(client)
    before = state_of(client)
    response = client.post("/api/batch/move", json={
        "ids": [tree["C"], tree["D"]], "newParentId": "root", "index": 1})
    assert response.status_code == 200
    after = state_of(client)
    assert after["tree"] == before["tree"] and after["revision"] == before["revision"]
    assert undo_depth(client) == depth


def test_44_a_node_travels_with_its_selected_ancestor(client, tree):
    answer = body(client.post("/api/batch/move", json={
        "ids": [tree["A"], tree["G"]], "newParentId": tree["C"], "index": None}))
    assert answer["movedIds"] == [tree["G"]]
    assert child_ids(client, tree["C"]) == [tree["G"]]
    assert child_ids(client, tree["G"]) == [tree["A"], tree["B"]]


@pytest.mark.parametrize("payload,status,code", [
    ({"ids": ["G", "C"], "newParentId": "A"}, 400, "CYCLE_REJECTED"),
    ({"ids": ["C"], "newParentId": "C"}, 400, "CYCLE_REJECTED"),
    ({"ids": ["root"], "newParentId": "C"}, 400, "ROOT_PROTECTED"),
    ({"ids": ["C"], "newParentId": "nowhere"}, 404, "PARENT_NOT_FOUND"),
    ({"ids": ["C", "gone"], "newParentId": "G"}, 404, "NODE_NOT_FOUND"),
    ({"ids": ["C"]}, 400, "INVALID_FIELD"),
    ({"ids": ["C"], "newParentId": "G", "index": "first"}, 400, "INVALID_FIELD"),
    ({"ids": [], "newParentId": "G"}, 400, "INVALID_FIELD"),
])
def test_44_a_refused_batch_move_moves_nothing(client, tree, payload, status, code):
    payload = dict(payload)
    payload["ids"] = [tree.get(value, value) for value in payload["ids"]]
    if "newParentId" in payload:
        payload["newParentId"] = tree.get(payload["newParentId"], payload["newParentId"])
    before = state_of(client)
    response = client.post("/api/batch/move", json=payload)
    assert response.status_code == status and error(response)["code"] == code, body(response)
    after = state_of(client)
    assert after["tree"] == before["tree"] and after["revision"] == before["revision"]


def test_44_a_batch_move_cannot_go_deeper_than_the_tree_may_be(client, tree, monkeypatch):
    from fta_web.routes import tree as tree_routes

    monkeypatch.setattr(tree_routes, "MAX_TREE_DEPTH", 2)
    response = client.post("/api/batch/move", json={"ids": [tree["C"], tree["D"]], "newParentId": tree["A"]})
    assert response.status_code == 400 and error(response)["detail"]["field"] == "newParentId"
    assert child_ids(client, tree["A"]) == []


def test_44_the_tree_panel_sends_one_request_for_a_selection():
    src = _read(STATIC / "tree.js")
    delete = _function(src, "async function deleteMany(ids)")
    assert "api.post('/batch/delete', { ids: ids })" in delete
    assert "api.del(" not in delete, "one request, so one undo step"
    move = _function(src, "async function requestMoveMany(ids, newParentId, index, focusId)")
    assert "api.post('/batch/move'" in move
    queue = _function(src, "function queueKeyboardMove(id, direction)")
    assert "selection.size > 1 && selection.has(String(id))" in queue and "moveSelectionByKeyboard(direction)" in queue
    start = _braced(src, src.index("host.addEventListener('dragstart'"))
    assert "movableSelection()" in start and "dragging = { id: id, ids: ids, blocked: blocked };" in start
    assert "new CustomEvent('fta:selection'" in src
    main = _read(STATIC / "main.js")
    meta = _function(main, "function renderSelectionMeta()")
    assert "t('meta.selectedMany', { n: selectionCount })" in meta and "t('meta.selectedName', { name })" in meta
    assert "window.addEventListener('fta:selection'" in main


_SELECTION_HARNESS = r"""
const kids = { root: ['g', 'c', 'd', 'e'], g: ['a', 'b'], a: [], b: [], c: [], d: [], e: [] };
const parentOf = (id) => Object.keys(kids).find((p) => kids[p].indexOf(id) !== -1) || null;
function rootId() { return 'root'; }
function parentIdOf(id) { return parentOf(id); }
function childIdsOf(id) { return (kids[id] || []).slice(); }
function ancestorsOf(id) { const out = []; for (let p = parentOf(id); p; p = parentOf(p)) out.push(p); return out; }
const order = ['root', 'g', 'a', 'b', 'c', 'd', 'e'];
const store = { flat: () => order.map((id) => ({ id })), findNode: (id) => (order.includes(id) ? { id } : null) };
const said = [];
function say(message) { said.push(message); }
function t(key) { return key; }
const document = { activeElement: null };
let selection = new Set();
const sent = [];
function requestMoveMany(ids, parent, index) { sent.push([ids, parent, index]); }
function moveByKeyboard(id, direction) { sent.push(['one', id, direction]); }
function ask(ids, direction) { selection = new Set(ids); sent.length = 0; said.length = 0; moveSelectionByKeyboard(direction); return [sent.slice(), said.slice()]; }
"""


@needs_node
def test_44_the_keyboard_moves_a_selection_as_a_block():
    src = _read(STATIC / "tree.js")
    script = _SELECTION_HARNESS + _function(src, "function movableSelection()") + "\n" + _function(
        src, "function moveSelectionByKeyboard(direction)") + """
console.log(JSON.stringify({
  down: ask(['c', 'd'], 'down'), up: ask(['d', 'e'], 'up'), upGap: ask(['c', 'e'], 'up'),
  top: ask(['g', 'c'], 'up'), bottom: ask(['d', 'e'], 'down'),
  indent: ask(['c', 'd'], 'in'), outdent: ask(['a', 'b'], 'out'), topOut: ask(['c', 'd'], 'out'),
  mixed: ask(['a', 'c'], 'down'), nested: ask(['g', 'a'], 'down'), withRoot: ask(['root', 'c'], 'down'),
}));"""
    got = _node(script)
    assert got["down"] == [[[["c", "d"], "root", 2]], []]          # after e, among the stayers [g, e]
    assert got["up"] == [[[["d", "e"], "root", 1]], []]            # before c
    assert got["upGap"] == [[[["c", "e"], "root", 0]], []]         # gathered, before g
    assert got["top"] == [[], ["tree.moveNoRoomUp"]]
    assert got["bottom"] == [[], ["tree.moveNoRoomDown"]]
    assert got["indent"] == [[[["c", "d"], "g", None]], []]        # under the sibling above the block
    assert got["outdent"] == [[[["a", "b"], "root", 1]], []]       # right after their parent
    assert got["topOut"] == [[], ["tree.moveNoOutdent"]]
    assert got["mixed"] == [[], ["tree.moveManyMixed"]]
    assert got["nested"] == [[["one", "g", "down"]], []]           # a goes with g: one node to move
    assert got["withRoot"] == [[["one", "c", "down"]], []]         # the root is never moved


# =============================================================================================
# 38: uncertainty for every event at once
# =============================================================================================


def test_38_every_basic_event_without_a_distribution_gets_one_in_one_step(client, tree):
    client.patch("/api/nodes/%s" % tree["C"], json={"quant": {"unc": {"dist": "lognormal", "ef": 10}}})
    client.patch("/api/nodes/%s" % tree["D"], json={"eventKind": "house", "houseState": True})
    client.patch("/api/nodes/%s" % tree["E"], json={"quant": {"model": "fixed", "source": "handbook"}})
    before = state_of(client)["tree"]
    depth = undo_depth(client)
    response = client.post("/api/batch/uncertainty", json={})
    answer = body(response)
    assert response.status_code == 200, answer
    assert sorted(answer["updatedIds"]) == sorted([tree["A"], tree["B"], tree["E"]])
    after = answer["tree"]
    for name in ("A", "B"):
        assert find(after, tree[name])["quant"] == {"unc": {"dist": "lognormal", "ef": 3}}
    assert find(after, tree["E"])["quant"] == {"model": "fixed", "source": "handbook",
                                              "unc": {"dist": "lognormal", "ef": 3}}
    assert find(after, tree["C"])["quant"]["unc"]["ef"] == 10, "one that is set is left alone"
    assert "quant" not in find(after, tree["D"]), "a house event is a constant"
    assert "quant" not in find(after, tree["G"]) and "quant" not in after, "gates and the root are not events"
    assert undo_depth(client) == depth + 1
    client.post("/api/undo", json={})
    assert state_of(client)["tree"] == before


def test_38_with_nothing_to_do_it_changes_nothing(client, tree):
    assert len(body(client.post("/api/batch/uncertainty", json={"ef": 5}))["updatedIds"]) == 5
    depth = undo_depth(client)
    before = state_of(client)
    answer = body(client.post("/api/batch/uncertainty", json={}))
    assert answer["updatedIds"] == []
    after = state_of(client)
    assert after["tree"] == before["tree"] and after["revision"] == before["revision"]
    assert undo_depth(client) == depth
    assert find(after["tree"], tree["A"])["quant"]["unc"]["ef"] == 5


@pytest.mark.parametrize("payload", [{"ef": "big"}, {"ef": True}, {"ef": 0.5}, {"ef": None, "x": 1}, {"dist": "normal"}])
def test_38_a_bad_request_is_refused_before_anything_changes(client, tree, payload):
    before = state_of(client)
    response = client.post("/api/batch/uncertainty", json=payload)
    assert response.status_code == 400 and error(response)["code"] == "INVALID_FIELD", body(response)
    assert state_of(client)["tree"] == before["tree"]


def test_38_a_null_error_factor_means_the_default(client, tree):
    answer = body(client.post("/api/batch/uncertainty", json={"ef": None}))
    assert len(answer["updatedIds"]) == 5
    assert find(answer["tree"], tree["A"])["quant"] == {"unc": {"dist": "lognormal", "ef": 3}}


def test_38_an_error_factor_typed_without_a_distribution_is_kept(client, tree):
    client.patch("/api/nodes/%s" % tree["A"], json={"quant": {"unc": {"ef": 10}}})
    answer = body(client.post("/api/batch/uncertainty", json={}))
    assert tree["A"] in answer["updatedIds"]
    assert find(answer["tree"], tree["A"])["quant"]["unc"] == {"dist": "lognormal", "ef": 10}
    assert find(answer["tree"], tree["B"])["quant"]["unc"] == {"dist": "lognormal", "ef": 3}


def test_38_an_event_tree_is_refused_and_left_alone(client, tree):
    assert client.post("/api/metadata", json={"mode": "ETA"}).status_code == 200
    before = state_of(client)
    response = client.post("/api/batch/uncertainty", json={})
    assert response.status_code == 409 and error(response)["code"] == "MODE_UNSUPPORTED", body(response)
    after = state_of(client)
    assert after["tree"] == before["tree"] and after["revision"] == before["revision"]


def test_38_the_monte_carlo_then_has_a_spread(client, tree):
    flat = body(client.post("/api/analysis/uncertainty", json={"n": 500, "seed": 3}))
    assert flat["std"] == 0 and flat["uncertainEvents"] == []
    client.post("/api/batch/uncertainty", json={})
    spread = body(client.post("/api/analysis/uncertainty", json={"n": 500, "seed": 3}))
    assert spread["std"] > 0 and len(spread["uncertainEvents"]) == 5


def test_38_the_tab_offers_it_and_draws_no_chart_without_a_spread():
    src = _read(STATIC / "tabs" / "uncertainty.js")
    assert "const DEFAULT_EF = 3;" in src
    assert "ctx.api.post('/batch/uncertainty', { ef: DEFAULT_EF })" in src
    paint = _function(src, "function paint()")
    assert "const figure = result && !flat ? chart() : null;" in paint
    assert "!(Number(result.std) > 0)" in paint and "t('unc.noSpread'" in paint


# =============================================================================================
# 45: the conversation survives a reload
# =============================================================================================


@pytest.fixture
def provider():
    instance = AIProviderFactory.get_provider(PROVIDER_NAME)
    assert instance is not None
    return instance


@pytest.fixture
def configured(client, provider, monkeypatch):
    monkeypatch.setattr(provider, "test_connection", lambda *a, **k: (True, "ok"))
    response = client.post("/api/ai/credentials", json={
        "provider": PROVIDER_NAME, "apiKey": API_KEY,
        "endpoint": "https://api.openai.com/v1", "model": "gpt-4o",
    })
    assert response.status_code == 200, body(response)
    return client


def answers(provider, monkeypatch, *replies):
    """The provider answers with `replies`, in turn; returns the list of calls."""
    calls = []
    queue = list(replies)

    def send_message(api_key, endpoint, model, messages, max_tokens=2000):
        calls.append(messages)
        return queue.pop(0), None

    monkeypatch.setattr(provider, "send_message", send_message)
    return calls


def test_45_nothing_configured_answers_empty_and_touches_nothing(client, per_user_home):
    response = client.get("/api/ai/conversation")
    assert response.status_code == 200
    assert body(response) == {"ok": True, "messages": [], "changes": [], "pendingUpdate": None}
    assert ai_bridge.existing_handler() is None, "a page load must not create the AI handler"
    assert not per_user_home.exists(), "nor the per-user folder"


def test_45_the_turns_come_back_in_order_without_the_prompt_or_the_tree(configured, provider, monkeypatch):
    client = configured
    add(client, name="Pump A", probability=0.01)
    calls = answers(provider, monkeypatch, "It is the **pump**.", "Then the valve.")
    assert client.post("/api/ai/chat", json={"message": "What fails first?"}).status_code == 200
    assert client.post("/api/ai/chat", json={"message": "And after that?"}).status_code == 200
    answer = body(client.get("/api/ai/conversation"))
    assert answer["messages"] == [
        {"role": "user", "kind": "chat", "content": "What fails first?"},
        {"role": "assistant", "kind": "chat", "content": "It is the **pump**."},
        {"role": "user", "kind": "chat", "content": "And after that?"},
        {"role": "assistant", "kind": "chat", "content": "Then the valve."},
    ]
    assert answer["changes"] == [] and answer["pendingUpdate"] is None
    sent = json.dumps(calls)
    assert "Current FTA Structure" in sent and "Pump A" in sent, "the provider was sent the tree"
    text = json.dumps(answer)
    assert "Current FTA Structure" not in text and AIAgentHandler.SYSTEM_PROMPT[:40] not in text


def test_45_no_credential_is_in_the_answer(configured, provider, monkeypatch):
    client = configured
    answers(provider, monkeypatch, "Your key is %s, by the way." % API_KEY)
    client.post("/api/ai/chat", json={"message": "Repeat my key %s" % API_KEY})
    response = client.get("/api/ai/conversation")
    text = response.get_data(as_text=True)
    assert API_KEY not in text and text.count(ai_bridge.REDACTED) == 2
    assert set(body(response)) == {"ok", "messages", "changes", "pendingUpdate"}
    for message in body(response)["messages"]:
        assert set(message) <= {"role", "kind", "content"}
    for word in ("apiKey", "api_key", "keyPreview", "endpoint"):
        assert word not in text


def test_45_it_is_a_read(configured, provider, monkeypatch):
    client = configured
    answers(provider, monkeypatch, "One.")
    client.post("/api/ai/chat", json={"message": "Hello"})
    before = state_of(client)
    history = list(ai_bridge.get_handler().conversation_history)
    first = body(client.get("/api/ai/conversation"))
    assert body(client.get("/api/ai/conversation")) == first
    assert ai_bridge.get_handler().conversation_history == history
    after = state_of(client)
    assert after["revision"] == before["revision"] and after["dirty"] == before["dirty"]


PROPOSAL = (
    "I suggest one change.\n\n"
    "PROPOSED_CHANGE:\n"
    "ACTION: add\n"
    "TARGET_ID: root\n"
    "DESCRIPTION: Add a common cause\n"
    'DATA: {"id": "common_cause", "name": "Common cause", "type": "Event", "probability": 0.01, '
    '"logicGate": "OR", "notes": ""}\n'
    "END_PROPOSED_CHANGE\n"
)


def test_45_an_analyze_is_named_and_its_pending_suggestions_come_back(configured, provider, monkeypatch):
    client = configured
    answers(provider, monkeypatch, PROPOSAL)
    made = body(client.post("/api/ai/analyze", json={}))
    assert len(made["changes"]) == 1, "the mocked reply must parse as one proposal"
    answer = body(client.get("/api/ai/conversation"))
    assert answer["messages"][0] == {"role": "user", "kind": "analyze"}, "the built-in prompt is not echoed"
    assert answer["messages"][1] == {"role": "assistant", "kind": "analyze", "content": PROPOSAL}
    assert answer["changes"] == made["changes"]
    assert answer["changes"][0]["index"] == 0 and answer["changes"][0]["changeType"] == "add"


def test_45_suggestions_for_another_document_are_not_offered(configured, provider, monkeypatch):
    client = configured
    answers(provider, monkeypatch, PROPOSAL)
    client.post("/api/ai/analyze", json={})
    assert len(body(client.get("/api/ai/conversation"))["changes"]) == 1
    assert client.post("/api/new", json={"force": True}).status_code == 200
    answer = body(client.get("/api/ai/conversation"))
    assert answer["changes"] == [], "they name nodes of the document that was open"
    assert len(answer["messages"]) == 2, "the conversation itself is still the handler's"


def test_45_an_update_is_named_and_its_preview_still_waits(configured, provider, monkeypatch):
    client = configured
    add(client, name="Cause A", probability=0.2)
    rewrite = {
        "id": "root", "name": state_of(client)["tree"]["name"], "type": "Root", "probability": 1.0,
        "logicGate": "OR", "notes": "", "links": [],
        "children": [
            {"id": "root_0", "name": "Cause A", "type": "Event", "probability": 0.2, "logicGate": "OR",
             "notes": "", "links": [], "children": []},
            {"id": "root_9", "name": "Common cause", "type": "Event", "probability": 0.01,
             "logicGate": "OR", "notes": "", "links": [], "children": []},
        ],
    }
    answers(provider, monkeypatch, json.dumps(rewrite))
    preview = body(client.post("/api/ai/update", json={"preview": True}))
    assert preview["preview"] is True
    answer = body(client.get("/api/ai/conversation"))
    assert answer["messages"] == [{"role": "user", "kind": "update"}, {"role": "assistant", "kind": "update"}], (
        "neither the built-in instruction nor the tree as JSON is replayed")
    assert answer["pendingUpdate"] == {"updateId": preview["updateId"], "updateSummary": preview["updateSummary"]}
    assert [entry["name"] for entry in answer["pendingUpdate"]["updateSummary"]["added"]] == ["Common cause"]
    assert client.post("/api/ai/update/discard", json={"id": preview["updateId"]}).status_code == 200
    assert body(client.get("/api/ai/conversation"))["pendingUpdate"] is None


def test_45_clear_chat_empties_it(configured, provider, monkeypatch):
    client = configured
    answers(provider, monkeypatch, PROPOSAL)
    client.post("/api/ai/analyze", json={})
    assert client.delete("/api/ai/conversation").status_code == 200
    assert body(client.get("/api/ai/conversation")) == {"ok": True, "messages": [], "changes": [], "pendingUpdate": None}


def test_45_the_two_built_in_prompts_still_begin_as_the_route_expects(monkeypatch):
    """`kind` is read off how the vendored handler's own prompts begin."""
    from fta_web.routes import ai as ai_routes

    seen = []
    handler = AIAgentHandler()
    monkeypatch.setattr(handler, "send_message", lambda text, include_fta_context=True: (seen.append(text) or ("{}", [])))
    handler.get_quick_analysis({"id": "root", "name": "T", "children": []})
    handler.generate_full_fta_update({"id": "root", "name": "T", "children": []})
    assert seen[0].startswith(ai_routes._ANALYZE_PROMPT_START)
    assert seen[1].startswith(ai_routes._UPDATE_PROMPT_START)


def test_45_the_panel_repaints_stops_and_gives_a_failed_message_back():
    src = _read(STATIC / "chat.js")
    restore = _function(src, "async function restore()")
    assert "api.get('/ai/conversation')" in restore
    assert "addMessage('assistant', text, { reply: true })" in restore and "renderChanges(changes)" in restore
    assert "renderUpdatePreview(" in restore
    # never over something the user has started in this page
    assert "if (busy || log.querySelector('.chat-msg--user, .chat-changes')) return;" in restore
    stop = _function(src, "function actionStop()")
    assert "job.stopped = true;" in stop and "setBusy(false);" in stop and "say('system', 'ai.msg.stopped')" in stop
    assert "api." not in stop, "Stop is the page giving up waiting; nothing is sent"
    send = _function(src, "function actionSend()")
    assert "if (input.value.trim() === '') input.value = typed;" in send
    assert "{ onFail: giveBack }" in send and "if (!showReply(result)) giveBack();" in send
    assert "if (destroyed || job.stopped) return;" in send
    update = _function(src, "function actionUpdate()")
    assert "api.post('/ai/update/discard', { id: result.updateId })" in update, "a preview nobody waits for is dropped"


# =============================================================================================
# the new endpoints are behind the session token, and documented
# =============================================================================================

PORT = 8765
BASE_URL = "http://127.0.0.1:%d" % PORT
TOKEN = "test-token-0123456789-abcdefghijklmnopqrstuvwxyz"

NEW_ENDPOINTS = [
    ("get", "/api/ai/conversation", None),
    ("post", "/api/batch/delete", {"ids": ["root_0"]}),
    ("post", "/api/batch/move", {"ids": ["root_0"], "newParentId": "root_1", "index": None}),
    ("post", "/api/batch/uncertainty", {}),
]


@pytest.fixture
def guarded(app):
    """The same blueprints behind the real guard (security.init_app)."""
    sys.path.insert(0, str(REPO / "fta_web"))
    import security  # the launcher's own module name

    security.init_app(app, TOKEN, PORT)
    return app.test_client()


@pytest.mark.parametrize("method,path,payload", NEW_ENDPOINTS)
def test_the_new_endpoints_refuse_a_request_without_the_token(guarded, method, path, payload):
    def call(headers, base_url=BASE_URL):
        kwargs = {"base_url": base_url, "headers": headers}
        if payload is not None:
            kwargs["json"] = payload
        return getattr(guarded, method)(path, **kwargs)

    seeded = {config.TOKEN_HEADER: TOKEN}
    for name in ("first", "second"):
        assert guarded.post("/api/nodes", base_url=BASE_URL, headers=seeded,
                            json={"parentId": "root", "name": name, "probability": 0.1}).status_code == 200
    ai_bridge.get_handler().conversation_history = [
        {"role": "user", "content": "a private question"}, {"role": "assistant", "content": "a private answer"}]
    before = get_state().revision_fields()
    tree_before = json.dumps(get_state().core.get_data(), sort_keys=True)
    for headers, reason in (
        ({}, "missing_token"),
        ({config.TOKEN_HEADER: "wrong"}, "invalid_token"),
        ({config.TOKEN_HEADER: TOKEN, "Origin": "http://evil.example"}, "origin_not_allowed"),
    ):
        refused = call(headers)
        assert refused.status_code == 403, (path, headers)
        assert error(refused)["code"] == "FORBIDDEN" and error(refused)["detail"] == {"reason": reason}
        assert "private" not in refused.get_data(as_text=True)
    rebound = call({config.TOKEN_HEADER: TOKEN}, base_url="http://evil.example:%d" % PORT)
    assert rebound.status_code == 403 and error(rebound)["detail"] == {"reason": "host_not_allowed"}
    assert "private" not in rebound.get_data(as_text=True)
    # nothing happened
    assert get_state().revision_fields() == before
    assert json.dumps(get_state().core.get_data(), sort_keys=True) == tree_before

    allowed = call({config.TOKEN_HEADER: TOKEN})
    assert allowed.status_code == 200, body(allowed)
    assert allowed.headers["Cache-Control"] == "no-store"
    if path == "/api/ai/conversation":
        assert [m["content"] for m in body(allowed)["messages"]] == ["a private question", "a private answer"]


def test_the_new_endpoints_are_in_the_api_reference_and_the_changelog():
    reference = _read(DOCS / "API_REFERENCE.md")
    for method, path, _payload in NEW_ENDPOINTS:
        assert "`%s %s`" % (method.upper(), path) in reference, path
    for key in ("deletedIds", "movedIds", "updatedIds", "pendingUpdate"):
        assert "`%s`" % key in reference, key
    unreleased = _read(REPO / "CHANGELOG.md").split("## [1.8.0]", 1)[1].split("\n## [", 1)[0]
    unreleased = " ".join(unreleased.split())  # a phrase may be wrapped over two lines
    for phrase in ("Diagram settings", "Copy CSV", "Initiating event", "one undo step", "Formatted",
                   "light colours", "Stop", "Google Gemini", "legend"):
        assert phrase in unreleased, phrase
    guide = " ".join(_read(DOCS / "USER_GUIDE.md").split())
    for phrase in ("Diagram settings", "Box padding", "Copy CSV", "Initiating event", "Formatted"):
        assert phrase in guide, phrase


# =============================================================================================
# 13, 14, 39: what is on screen is what is exported, in light colours, under the document's name
# =============================================================================================


def test_13_an_export_is_built_from_the_painted_diagram_with_its_legend():
    src = _read(STATIC / "diagram.js")
    build = _function(src, "async function buildExportSvg(options)")
    assert "renderedDark ? await lightSvg() : svgEl.cloneNode(true)" in build
    assert build.index("paintOverlay(copy, over || null);") < build.index("appendLegend(copy, over,") < build.index(
        "new XMLSerializer().serializeToString(copy)")
    assert "classList.remove('is-selected', 'is-highlighted')" in build
    # the screen and the file are painted by the same function
    assert "paintOverlay(svgEl, overlay);" in _function(src, "function applyOverlay()")
    legend = _function(src, "function appendLegend(root, over, font)")
    for piece in ("linearGradient", "scaleColor(0)", "scaleColor(1)", "texts.title", "texts.low", "texts.high"):
        assert piece in legend, piece
    assert "await buildExportSvg()" in _function(src, "async function exportSvg()")
    png = _function(src, "async function toPngBlob(options)")
    assert "await buildExportSvg(options)" in png and "ctx.fillStyle = '#ffffff'" in png
    # a coloured diagram never takes the server path, which does not know the overlay
    assert "effectiveBoxSettings().style !== 'symbols' && !overlayValues(overlay)" in _function(
        src, "async function exportPng()")


def test_13_the_report_can_colour_its_diagram_and_is_plain_otherwise():
    src = _read(STATIC / "tabs" / "report.js")
    assert "'data-report-fv'" in src and "label(el('span'), 'report.fvDiagram')" in src
    assert "ctx.api.post('/analysis/importance', {})" in _function(src, "async function fvOverlay()")
    assert "const png = await ctx.diagramPng({ overlay });" in src
    assert "let overlay = null;" in src, "an overlay that happens to be on screen does not leak into a report"
    main = _read(STATIC / "main.js")
    assert "diagramPng: (opts) => diagramPng(opts)," in main
    assert "diagramPanel.toPngBlob(options)" in _function(main, "async function diagramPng(options)")


def test_14_every_export_asks_for_the_light_colours():
    src = _read(STATIC / "diagram.js")
    assert "return { ...effectiveBoxSettings(), dark: false };" in _function(src, "function exportBoxSettings()")
    png = _function(src, "async function exportPng()")
    assert "const box = exportBoxSettings();" in png and "dark: box.dark," in png
    light = _function(src, "async function lightSvg()")
    assert "const box = exportBoxSettings();" in light and "api.get(dotUrl(box))" in light
    assert "sanitizeSvg(parsed);" in _function(src, "function svgFromText(svgText, style, rankdir)")
    assert "fitLabels(node);" in light
    main = _read(STATIC / "main.js")
    render = _function(main, "async function actionRenderImage()")
    assert "diagramPanel.getExportSettings()" in render and "getBoxSettings()" not in render
    # the preview itself still follows the theme
    assert "dark: isDarkMode()," in _function(src, "function effectiveBoxSettings()")


def test_14_the_server_draws_light_when_asked_whatever_was_drawn_before(client, tree):
    dark = body(client.get("/api/dot?dark=true"))["dot"]
    light = body(client.get("/api/dot?dark=false"))["dot"]
    assert "#1b1f23" in dark and "#1b1f23" not in light and 'bgcolor="white"' in light


def test_39_the_diagram_buttons_use_the_shell_name_and_toast():
    src = _read(STATIC / "diagram.js")
    assert "'fta_diagram.svg'" not in src and "'fta_diagram.png'" not in src
    name = _function(src, "function exportName(extension)")
    assert "shell.exportFilename(extension)" in name and "'fta_diagram.' + extension" in name
    assert "shell.toastDownloaded(name)" in _function(src, "function downloaded(name)")
    for function in ("async function exportSvg()", "async function exportPng()", "async function exportPngViaCanvas(name)"):
        assert "downloaded(" in _function(src, function), function
    main = _read(STATIC / "main.js")
    shell = main[main.index("window.ftaShell = {"):]
    assert "\n  exportFilename,\n" in shell and "\n  toastDownloaded,\n" in shell


def test_the_wasm_fallback_for_large_graphs_is_untouched():
    src = _read(STATIC / "diagram.js")
    assert "const ORTHO_MAX_EDGES = 100;" in src
    assert "return edges > ORTHO_MAX_EDGES ? withoutOrtho(text) : text;" in _function(src, "export function wasmSafeDot(dot)")
    layout = _function(src, "async function layoutSvg(dot)")
    assert "const safe = wasmSafeDot(dot);" in layout and "withoutOrtho(safe)" in layout


# =============================================================================================
# 30, 35, 36: the diagram's settings, zoom, and the bottom panel
# =============================================================================================


def test_30_the_settings_are_named_for_what_they_are():
    src = _read(STATIC / "diagram.js")
    assert "btn('Aa'" not in src
    assert "aaBtn.dataset.role = 'diagram-settings';" in src
    assert "t('diagram3.settingsButton', 'Settings')" in src
    main = _read(STATIC / "main.js")
    assert "'diagram.fontSettings': 'Diagram settings'," in main and "'diagram.fontSettings': '図の設定'," in main
    assert "'diagram.scaleLabel': 'Box padding (0-30)'," in main
    assert "Font & box size" not in main and "'Box scale'" not in main and "Font & box size" not in src


def test_35_a_selection_is_brought_into_view_and_there_is_a_100_percent_button():
    src = _read(STATIC / "diagram.js")
    pan = _function(src, "function panIntoView(id)")
    assert "tx += dx;" in pan and "ty += dy;" in pan and "scale =" not in pan, "it moves, it does not zoom"
    subscribe = re.search(r"const unsubscribe = store\.subscribe\(\(\) => \{(.*?)\n  \}\);", src, re.S).group(1)
    assert "if (reselected && selected) panIntoView(selected);" in subscribe
    assert "btn('1:1', 'diagram3.actualSize', 'Actual size (100%)', () => zoomTo(1))," in src
    assert "'diagram3.toSelection'" in src and "() => showSelection())" in src


_SHIFT = r"""
const REVEAL_MARGIN_PX = 8;
const shift = (lo, hi, viewLo, viewHi) => {
  const room = viewHi - viewLo - 2 * REVEAL_MARGIN_PX;
  if (hi - lo > room) return (viewLo + viewHi) / 2 - (lo + hi) / 2;
  if (lo < viewLo + REVEAL_MARGIN_PX) return viewLo + REVEAL_MARGIN_PX - lo;
  if (hi > viewHi - REVEAL_MARGIN_PX) return viewHi - REVEAL_MARGIN_PX - hi;
  return 0;
};
"""


@needs_node
def test_35_the_pan_is_the_least_that_shows_the_node():
    src = _read(STATIC / "diagram.js")
    pan = _function(src, "function panIntoView(id)")
    cut = pan[pan.index("const shift = "):pan.index("const dx = ")]
    assert " ".join(cut.split()) == " ".join(_SHIFT.split("\n", 2)[2].split()), "the harness below is this code"
    got = _node(_SHIFT + """
console.log(JSON.stringify([
  shift(100, 200, 0, 500),     // inside: stays
  shift(-40, 60, 0, 500),      // off the left: just enough to the right
  shift(480, 580, 0, 500),     // off the right: just enough to the left
  shift(-100, 700, 0, 500),    // larger than the stage: centred
  shift(4, 104, 0, 500),       // inside the margin: nudged
]));""")
    assert got == [0, 48, -88, -50, 4]


def test_36_the_bottom_panel_has_a_height_per_kind_of_tab_and_leaves_the_diagram_room():
    main = _read(STATIC / "main.js")
    assert "const MIN_DIAGRAM_PX = 240;" in main and "const ANALYSIS_SHARE = 0.45;" in main
    height = _function(main, "function bottomHeight()")
    assert "if (bottomMax) want = cap;" in height and "else if (bottomTab !== 'details')" in height
    assert "return clamp(Math.round(want), PANES.details.min, cap);" in height, "never past what leaves the diagram room"
    cap = _function(main, "function bottomCap()")
    assert "- MIN_DIAGRAM_PX" in cap
    assert "window.addEventListener('fta:tab', onBottomTab);" in main
    assert "window.addEventListener('resize', applyLayout);" in main
    host = _read(STATIC / "tabs" / "host.js")
    assert "new CustomEvent('fta:tab', { detail: { id: wanted } })" in host
    index = _read(INDEX)
    assert 'id="btn-bottom-max"' in index and 'aria-pressed="false"' in index


# =============================================================================================
# 40, 41 and the smaller notes
# =============================================================================================


def test_40_importance_has_copy_csv_through_the_shared_cell_writer():
    src = _read(STATIC / "tabs" / "importance.js")
    assert "copyText," in src and "csvCell," in src
    csv = _function(src, "function csvText()")
    assert ".map(csvCell).join(',')" in csv and "sortedRows()" in csv and "row.rrwInfinite ? 'inf' : row.rrw" in csv
    assert "await copyText(csvText())" in src and "t('imp.copied', { n })" in src


@needs_node
def test_40_a_name_that_looks_like_a_formula_is_neutralised_in_the_csv():
    script = "import { csvCell } from %s;\n" % json.dumps((STATIC / "tabs" / "analysis_common.js").as_uri())
    # analysis_common.js imports dialogs.js, which wants a document: cut csvCell out instead
    src = _read(STATIC / "tabs" / "analysis_common.js")
    script = _function(src, "export function csvCell(value)").replace("export ", "") + """
console.log(JSON.stringify([csvCell('=SUM(A1)'), csvCell('Pump, main'), csvCell(0.5), csvCell('inf'), csvCell(null)]));"""
    assert _node(script) == ["'=SUM(A1)", '"Pump, main"', "0.5", "inf", ""]


def test_41_a_tree_row_shows_gate_and_probability_and_only_an_event_is_red():
    src = _read(STATIC / "tree.js")
    item = _function(src, "function buildItem(node, depth, ctx)")
    assert "const isFull = Number(node.probability) === 1 && !isBranch;" in item
    assert "class: 'fta-tree-gate'" in item and "class: 'fta-tree-prob'" in item
    assert "const gateChip = ctx.eta ? null : gateLabel(node, isBranch);" in item
    assert "eta: isEtaDocument()," in src


_ROW_HARNESS = r"""
function formatProb(v) { return 'P' + v; }
function getSigFigs() { return 3; }
"""


@needs_node
def test_41_the_chip_and_the_number_of_each_kind_of_row():
    src = _read(STATIC / "tree.js")
    script = _ROW_HARNESS + _function(src, "function gateLabel(node, isBranch)") + "\n" + _function(
        src, "function rowProbability(node, isBranch, eta)") + """
const kid = { id: 'k' };
console.log(JSON.stringify({
  or: gateLabel({ children: [kid] }, true),
  and: gateLabel({ logicGate: 'AND', children: [kid] }, true),
  kofn: gateLabel({ gateType: 'KOFN', k: 2, children: [kid, kid, kid] }, true),
  xor: gateLabel({ gateType: 'XOR', logicGate: 'OR', children: [kid, kid] }, true),
  leaf: gateLabel({ logicGate: 'OR', children: [] }, false),
  transfer: gateLabel({ gateType: 'TRANSFER', children: [] }, false),
  gateProb: rowProbability({ probability: 1, calculatedProbability: 0.02 }, true, false),
  leafProb: rowProbability({ probability: 0.1, calculatedProbability: 0.1 }, false, false),
  etaProb: rowProbability({ probability: 0.5, calculatedProbability: 0.05 }, false, true),
  none: rowProbability({ probability: null }, false, false),
}));"""
    got = _node(script)
    assert [got[k] for k in ("or", "and", "kofn", "xor", "leaf", "transfer")] == ["OR", "AND", "2/3", "XOR", None, "TRANSFER"]
    assert got["gateProb"] == {"text": "P0.02", "key": "tree.probCalcTitle"}
    assert got["leafProb"] == {"text": "P0.1", "key": "tree.probOwnTitle"}
    assert got["etaProb"] == {"text": "P0.05", "key": "tree.probCalcTitle"}
    assert got["none"] is None


def test_smaller_notes():
    main = _read(STATIC / "main.js")
    toast = _function(main, "function toast(message, kind = 'info', code = null, options = null)")
    assert "if (code) node.dataset.code = String(code);" in toast and "if (code && kind === 'error') {" in toast
    assert "placeToasts(host);" in toast
    cut = _read(STATIC / "tabs" / "cutsets.js")
    rare = _function(cut, "function rareStat()")
    assert "t('cutsets.rareTitle')" in rare and "Number(result.rareEvent) > 1" in rare
    dialogs = _read(STATIC / "dialogs.js")
    assert "export const NODE_TYPES = Object.freeze(['Event', 'Gate', 'Intermediate']);" in dialogs
    assert "list: nodeTypeListId()" in dialogs and "list: nodeTypeListId()" in _read(STATIC / "details.js")


# =============================================================================================
# 46, 47, 48: the assistant
# =============================================================================================


def test_46_a_card_names_nodes_reads_its_changes_and_is_retired_with_its_document():
    src = _read(STATIC / "chat.js")
    link = _function(src, "function nodeLink(id)")
    assert "store.jumpTo(String(id))" in link and "class: 'chat-link'" in link
    assert "textContent" not in link and "innerHTML" not in src, "names are written as text"
    render = _function(src, "function renderChanges(changes)")
    assert "nodeLink(target)" in render and "fieldLines(change, target)" in render
    assert "safeJson(change.data)" not in render, "no raw JSON on a card"
    apply = _function(src, "async function applyChanges(handle, total)")
    assert "showDiagnostics({ rejected" not in apply, "nor for a rejected suggestion"
    document = src[src.index("const onDocument = () => {"):]
    document = document[:document.index("};") + 2]
    assert "retireChanges(openChanges, t('ai.changes.otherDocument'));" in document


def test_47_gemini_is_the_first_choice_only_when_nothing_is_configured():
    src = _read(STATIC / "aisettings.js")
    assert "selectProvider(configured || defaultProvider(providers), { fromUser: false });" in src
    assert "text: t('ai.disclosure')," in src
    form = src[src.index("const form = el('div', { class: 'aiset-form'"):]
    assert form.index("disclosure,") < form.index("providerBlock,") < form.index("keyBlock,")
    first = src[src.index("const PROVIDER_META = ["):]
    assert first.index("'microsoft', 'azure', 'copilot'") < first.index("'openai', 'gpt'"), (
        "Microsoft Copilot (Azure OpenAI) must not be taken for OpenAI")
    en = _catalog("ux3.js")[0]
    assert "sent to the provider you choose" in en["ai.disclosure"] and "whole tree" in en["ai.disclosure"]
    assert "Azure OpenAI resource" in en["ai.hint.azure"]


@needs_node
def test_47_the_default_provider():
    src = _read(STATIC / "aisettings.js")
    script = _function(src, "export function defaultProvider(providers)").replace("export ", "") + """
const names = (list) => { const p = defaultProvider(list.map((name) => ({ name }))); return p ? p.name : null; };
console.log(JSON.stringify([
  names(['OpenAI', 'Microsoft Copilot', 'Anthropic Claude', 'Google Gemini']),
  names(['OpenAI', 'Anthropic Claude']),
  names([]),
]));"""
    assert _node(script) == ["Google Gemini", "OpenAI", None]


def test_47_the_server_still_lists_the_providers_in_its_own_order(client):
    names = [entry["name"] for entry in body(client.get("/api/ai/providers"))["providers"]]
    assert any("gemini" in name.lower() or "google" in name.lower() for name in names), names


def _catalog(name):
    src = _read(STATIC / "i18n" / name)
    block = re.search(r"export default \{(.*?)\n\};", src, re.S).group(1)
    en_block, ja_block = block.split("\n  ja:", 1)
    entry = re.compile(r"'([A-Za-z0-9_.]+)'\s*:\s*'((?:[^'\\]|\\.)*)'")
    return dict(entry.findall(en_block)), dict(entry.findall(ja_block))


def test_48_wording():
    main = _read(STATIC / "main.js")
    assert "'ai.chat.markdown': 'Formatted'," in main and "'ai.chat.markdown': '整形表示'," in main
    commit = _function(main, "async function commitMetadata()")
    assert "toast(t('msg.metadataSaved')" not in commit
    assert "if (modeNow !== modeBefore) toast(t(modeNow === 'ETA' ? 'msg.modeEta' : 'msg.modeFta'), 'ok');" in commit
    chat = _read(STATIC / "chat.js")
    assert chat.count("say('system', 'ai.msg.notConfigured')") == 1, "one place, and it says it once"
    once = _function(chat, "function sayNotConfigured()")
    assert "log.appendChild(notConfiguredRow);" in once
    reply = _function(chat, "function showReply(payload)")
    assert "reply.trim().indexOf(AI_ERROR_PREFIX) === 0" in reply and "addMessage('error'" in reply
    for key in ("ai.chat.analyze", "ai.chat.update", "ai.chat.placeholder", "ai.msg.welcome", "ai.msg.analyzePrompt"):
        assert "modeKey('%s')" % key in chat, key
    assert "placeToasts" in main


def test_48_every_mode_aware_string_has_its_eta_wording_in_both_languages():
    en, ja = _catalog("ux3.js")
    eta = sorted(key for key in en if key.endswith(".eta"))
    assert len(eta) == 12
    main = _read(STATIC / "main.js")
    ux2 = _read(STATIC / "i18n" / "ux2.js")
    for key in eta:
        base = key[:-len(".eta")]
        assert ("'%s'" % base) in main or ("'%s'" % base) in ux2, "no base string for " + key
        assert "FTA" not in en[key] and "fault tree" not in en[key], key
        assert "FTA" not in ja[key] and "フォールトツリー" not in ja[key], key
    assert en["ai.chat.analyze.eta"] == "Analyze ETA" and en["headline.labelEta"] == "Initiating event"


@needs_node
def test_48_mode_key_falls_back_to_the_plain_string():
    src = _read(STATIC / "chat.js")
    script = """
let mode = 'FTA';
const store = { metadata: () => ({ mode }) };
const table = { 'a.eta': 'A for ETA' };
function t(key) { return table[key] || key; }
""" + _function(src, "function isEta()") + "\n" + _function(src, "function modeKey(key)") + """
const out = [modeKey('a'), modeKey('b')];
mode = 'eta';
out.push(modeKey('a'), modeKey('b'));
console.log(JSON.stringify(out));"""
    assert _node(script) == ["a", "b", "a.eta", "b"]


def test_the_catalog_is_registered_and_complete():
    assert "'./i18n/ux3.js'," in _read(STATIC / "main.js")
    en, ja = _catalog("ux3.js")
    assert set(en) == set(ja) and len(en) > 50
    used = "".join(_read(path) for path in list(STATIC.glob("*.js")) + list((STATIC / "tabs").glob("*.js")))
    used += _read(INDEX)
    for key in en:
        if key.endswith(".eta") or key.startswith("ai.changes.kind."):
            continue  # built from a base key at run time
        assert ("'%s'" % key) in used or ('"%s"' % key) in used, "unused string " + key
