"""
Regression tests for the October 2026 review of the web backend (B-* items):
the HTTP layer, application state, files, rendering and security.

Each class pins one finding. Two ways of building the app are used, as in
``test_backend_fixes.py``:

* the blueprint under test on a bare ``Flask`` app, imported as the package
  module (``fta_web.routes.tree``), whose state is ``fta_web.state``;
* ``create_app`` for what only the full application does (the JSON provider,
  the security layer). ``create_app`` imports its blueprints as the bare
  ``routes.*`` modules, exactly as ``run.py`` does, and those use the bare
  ``state`` module -- a different singleton -- so the fixtures reset and read
  that one.
"""
import json
import sys
from pathlib import Path
from urllib.parse import quote

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

pytest.importorskip("flask")

from fta_web.state import get_state, reset_state  # noqa: E402


# --------------------------------------------------------------------------
# fixtures and helpers
# --------------------------------------------------------------------------


@pytest.fixture
def tree_client():
    """The tree blueprint on a bare Flask app."""
    import flask

    from fta_web.routes.tree import tree_bp

    reset_state()
    app = flask.Flask(__name__)
    app.register_blueprint(tree_bp)
    app.config.update(TESTING=True)
    with app.test_client() as client:
        yield client


def body(response):
    return json.loads(response.get_data(as_text=True))


def install(tree, mode="FTA"):
    """Make ``tree`` the live document of the package-level state."""
    state = get_state()
    with state.lock:
        state.core.set_data(tree)
        state.core.mode = mode
        state.core.recalculate_probabilities()
    return state


def node_url(node_id, suffix=""):
    """The URL the frontend builds: ``'/nodes/' + encodeURIComponent(id)``."""
    return "/api/nodes/" + quote(str(node_id), safe="") + suffix


# --------------------------------------------------------------------------
# B-1: a node id containing '/' could not be addressed at all
# --------------------------------------------------------------------------


def _slash_tree():
    return {
        "id": "root", "name": "Top", "logicGate": "OR", "probability": 1.0,
        "links": [], "notes": "", "type": "Root",
        "children": [
            {"id": "PUMP/A", "name": "Pump A", "probability": 0.1, "logicGate": "OR",
             "links": [], "notes": "", "type": "Event", "children": []},
            {"id": "PUMP/B", "name": "Pump B", "probability": 0.2, "logicGate": "OR",
             "links": [], "notes": "", "type": "Event", "children": []},
            {"id": "x/move", "name": "Tricky", "probability": 0.3, "logicGate": "OR",
             "links": [], "notes": "", "type": "Event", "children": []},
        ],
    }


class TestNodeIdsWithSlashes:
    """Ids from hand-edited or tool-generated files can contain '/'. The
    frontend percent-encodes them, the server decodes the path before
    routing, and the default URL converter stops at '/': every
    ``/api/nodes/<id>`` call for such a node answered 404 ``NOT_FOUND``."""

    def test_get_patch_move_delete_reach_the_node(self, tree_client):
        c = tree_client
        install(_slash_tree())

        got = c.get(node_url("PUMP/A"))
        assert got.status_code == 200, body(got)
        assert body(got)["node"]["id"] == "PUMP/A"

        patched = c.patch(node_url("PUMP/A"), json={"name": "Pump A1"})
        assert patched.status_code == 200, body(patched)
        assert body(patched)["node"]["name"] == "Pump A1"

        moved = c.post(node_url("PUMP/A", "/move"), json={"newParentId": "PUMP/B"})
        assert moved.status_code == 200, body(moved)
        assert body(moved)["parentId"] == "PUMP/B"

        deleted = c.delete(node_url("PUMP/A"))
        assert deleted.status_code == 200, body(deleted)
        assert get_state().core.find_node_by_id("PUMP/A") is None

    def test_an_id_ending_in_move_is_not_mistaken_for_the_move_endpoint(self, tree_client):
        c = tree_client
        install(_slash_tree())
        patched = c.patch(node_url("x/move"), json={"name": "Renamed"})
        assert patched.status_code == 200, body(patched)
        assert body(patched)["node"]["id"] == "x/move"
        moved = c.post(node_url("x/move", "/move"), json={"newParentId": "PUMP/B"})
        assert moved.status_code == 200, body(moved)
        assert body(moved)["nodeId"] == "x/move"
        assert body(moved)["parentId"] == "PUMP/B"

    def test_plain_ids_and_unknown_ids_are_unchanged(self, tree_client):
        c = tree_client
        install(_slash_tree())
        assert c.get(node_url("root")).status_code == 200
        missing = c.get(node_url("no/such/node"))
        assert missing.status_code == 404
        assert body(missing)["error"]["code"] == "NODE_NOT_FOUND"


# --------------------------------------------------------------------------
# diagram helpers: render DOT with the vendored viz.js, as the browser does
# --------------------------------------------------------------------------

import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

VIZ_JS = REPO_ROOT / "fta_web" / "static" / "vendor" / "viz-js" / "viz.js"
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

_VIZ_SCRIPT = """
import { instance } from %s;
let dot = '';
process.stdin.setEncoding('utf8');
for await (const chunk of process.stdin) dot += chunk;
const viz = await instance();
const r = viz.render(dot, { format: 'svg' });
const out = { status: r.status, errors: r.errors.filter((e) => e.level === 'error') };
if (r.status === 'success') {
  out.titles = [...r.output.matchAll(/<g id="node\\d+" class="[^"]*">\\s*<title>([^<]*)<\\/title>/g)]
    .map((m) => m[1]);
  // what DOMParser('image/svg+xml') would refuse: XML 1.0 forbids these
  out.xmlInvalid = /[\\u0000-\\u0008\\u000b\\u000c\\u000e-\\u001f\\ufffe\\uffff]|&#(?:[0-8]|1[1-2]|1[4-9]|2[0-9]|3[01]);/.test(r.output);
}
console.log(JSON.stringify(out));
"""


def viz_render(dot):
    """``{status, errors, titles}`` from viz.js for ``dot``."""
    script = _VIZ_SCRIPT % json.dumps(VIZ_JS.resolve().as_uri())
    done = subprocess.run(["node", "--input-type=module", "-e", script], input=dot,
                          capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _core(tree, title="T"):
    from fta_web.engine import WebCore

    core = WebCore()
    core.set_data(tree)
    core.set_metadata(title=title, date="2026-10-10")
    core.recalculate_probabilities()
    return core


def _leaf(nid, name, p=0.1, **extra):
    node = {"id": nid, "name": name, "type": "Event", "probability": p,
            "logicGate": "OR", "notes": "", "links": [], "children": []}
    node.update(extra)
    return node


def _digit_tree():
    return {"id": "root", "name": "Top", "type": "Root", "probability": 1.0,
            "logicGate": "OR", "notes": "", "links": [], "children": [
                _leaf("1a", "First"),
                _leaf("1.1", "Dotted", links=[{"target_id": "2b", "relation": "OR"}]),
                _leaf("2b", "Second", gateType="TRANSFER", transferTo="1a"),
                _leaf("3", "Numeral"),
            ]}


# --------------------------------------------------------------------------
# B-2: an id that starts with a digit split into two DOT tokens
# --------------------------------------------------------------------------


class TestDigitLedIds:
    """``1a`` (or ``1_1_<hash>``, sanitize_id's answer for ``1.1``) is not a
    DOT ID unquoted: Graphviz reads ``1`` then ``a``, so the diagram gained a
    stray unlabelled node ``1`` wired to the parent while the real box floated
    unconnected, and click-to-select missed it."""

    @pytest.mark.parametrize("style", ["compact", "symbols"])
    def test_digit_led_names_are_quoted_and_mapped(self, style):
        from fta_web.diagram_dot import build_dot_text2

        dot, id_map = build_dot_text2(_core(_digit_tree()), style=style)
        assert '"1a" [' in dot
        assert not re.search(r"(^|[\s>-])1a\b", dot.replace('"1a"', "")), dot
        assert id_map["1a"] == "1a"
        dotted = [name for name, nid in id_map.items() if nid == "1.1" and "__" not in name][0]
        assert '"%s"' % dotted in dot
        # a plain numeral is a valid DOT ID and stays as it was
        assert re.search(r"^\s{2}3 \[", dot, re.M)
        # ordinary ids are not quoted (byte-identical DOT for normal trees)
        assert re.search(r"^\s{2}root \[", dot, re.M)

    def test_symbols_group_attribute_stays_well_formed(self):
        from fta_web.diagram_dot import build_dot_text2

        dot, _ = build_dot_text2(_core(_digit_tree()), style="symbols")
        assert 'group="1a"' in dot and 'group=""' not in dot

    @needs_node
    @pytest.mark.parametrize("style", ["compact", "symbols"])
    @pytest.mark.parametrize("rankdir", ["LR", "TB"])
    def test_viz_draws_exactly_the_mapped_nodes(self, style, rankdir):
        from fta_web.diagram_dot import build_dot_text2

        dot, id_map = build_dot_text2(_core(_digit_tree()), style=style, rankdir=rankdir)
        out = viz_render(dot)
        assert out["status"] == "success" and not out["errors"], out
        assert sorted(out["titles"]) == sorted(id_map), out["titles"]


# --------------------------------------------------------------------------
# B-3: a character XML 1.0 forbids blanked a label, or the whole diagram
# --------------------------------------------------------------------------

_XML_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


def _ctrl_tree():
    return {"id": "root", "name": "Top\x01event", "type": "Root", "probability": 1.0,
            "logicGate": "OR", "notes": "", "links": [], "children": [
                _leaf("e1", "nul\x00here"),
                _leaf("e2", "bell\x07 esc\x1b nonchar￾"),
                _leaf("e3", "lone \ud800 surrogate"),
                _leaf("t1", "Transfer", gateType="TRANSFER", transferTo="e1"),
            ]}


class TestXmlInvalidCharacters:
    """Graphviz parses an HTML-like label as XML. A NUL in a node name (or in
    the title) cut the DOT short and nothing rendered at all; any other C0
    control character, U+FFFE/U+FFFF or a lone surrogate made that node's
    label unparseable, so the box lost its text. ``sanitize_name`` only
    collapses whitespace, and a file is taken as written, so both reach the
    diagram. They are drawn as U+FFFD now; the stored names are untouched."""

    @pytest.mark.parametrize("style", ["compact", "symbols"])
    def test_dot_carries_no_xml_invalid_character(self, style):
        from fta_web.diagram_dot import build_dot_text2

        core = _core(_ctrl_tree(), title="Ti\x00tle\x07")
        dot, _ = build_dot_text2(core, style=style)
        assert not _XML_INVALID.search(dot), repr(_XML_INVALID.search(dot))
        assert "nul�here" in dot and "Ti�tle�" in dot
        # the document itself is not rewritten
        assert core.find_node_by_id("e1")["name"] == "nul\x00here"

    def test_plain_text_is_unchanged(self):
        from fta_web.rendering import xml_safe

        text = "Pressure > 5 bar & T < 50 ポンプ \U0001f600\ttab\nnl"
        assert xml_safe(text) == text

    @needs_node
    @pytest.mark.parametrize("style", ["compact", "symbols"])
    def test_viz_renders_every_label(self, style):
        from fta_web.diagram_dot import build_dot_text2

        dot, id_map = build_dot_text2(_core(_ctrl_tree(), title="Ti\x00tle\x07"), style=style)
        out = viz_render(dot)
        assert out["status"] == "success" and not out["errors"], out
        assert sorted(out["titles"]) == sorted(id_map)
        assert out["xmlInvalid"] is False


# --------------------------------------------------------------------------
# file fixtures: the file and tree blueprints on a sandbox root
# --------------------------------------------------------------------------


@pytest.fixture
def sandbox(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


@pytest.fixture
def files_client(sandbox):
    """files_bp + tree_bp + analysis_bp + validate_bp on a bare app; the
    state's sandbox root is the test's own directory."""
    import flask

    from fta_web.routes.analysis import analysis_bp
    from fta_web.routes.files import files_bp
    from fta_web.routes.tree import tree_bp
    from fta_web.routes.validate import validate_bp

    reset_state()
    app = flask.Flask(__name__)
    for bp in (files_bp, tree_bp, analysis_bp, validate_bp):
        app.register_blueprint(bp)
    app.config.update(TESTING=True)
    get_state().fs_root = sandbox
    with app.test_client() as client:
        yield client


def write_doc(directory, name, document):
    path = Path(directory) / name
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _calc(tree, node_id):
    stack = [tree]
    while stack:
        node = stack.pop()
        if node.get("id") == node_id:
            return node.get("calculatedProbability")
        stack.extend(node.get("children") or [])
    raise KeyError(node_id)


# --------------------------------------------------------------------------
# B-8: a file's "mode" was used verbatim: "eta" was computed as a fault tree
# --------------------------------------------------------------------------

_EVENT_TREE = {"id": "root", "name": "Initiator", "probability": 0.1, "children": [
    {"id": "a", "name": "Branch", "probability": 0.5, "children": [
        {"id": "a1", "name": "Outcome", "probability": 0.2, "children": []}]}]}


class TestModeFromAFile:
    """The engine computes ETA only for the exact string "ETA" while the
    analysis endpoints compared case-insensitively: a file saying "eta" was
    computed bottom-up as a fault tree (the end state read 0.2 instead of
    0.1 x 0.5 x 0.2 = 0.01), showed as FTA, and Cut Sets refused it as an
    event tree. ``POST /api/metadata`` only ever accepts FTA/ETA; a loaded
    mode is normalised the same way."""

    @pytest.mark.parametrize("raw", ["eta", " Eta ", "ETA"])
    def test_eta_in_any_case_is_an_event_tree(self, files_client, sandbox, raw):
        write_doc(sandbox, "m.json", {"title": "t", "mode": raw, "tree": _EVENT_TREE})
        opened = files_client.post("/api/file/open", json={"path": "m.json"})
        assert opened.status_code == 200, body(opened)
        doc = body(opened)
        assert doc["metadata"]["mode"] == "ETA"
        assert _calc(doc["tree"], "a1") == pytest.approx(0.01)
        assert files_client.get("/api/analysis/summary").status_code == 409
        assert body(files_client.get("/api/analysis/validate"))["mode"] == "ETA"

    @pytest.mark.parametrize("raw", ["fta", " FTA", "bogus", None, 5])
    def test_anything_else_is_a_fault_tree(self, files_client, sandbox, raw):
        write_doc(sandbox, "m.json", {"title": "t", "mode": raw, "tree": _EVENT_TREE})
        doc = body(files_client.post("/api/file/open", json={"path": "m.json"}))
        assert doc["metadata"]["mode"] == "FTA"
        assert files_client.get("/api/analysis/summary").status_code == 200

    def test_import_normalises_too(self, files_client):
        import io

        data = json.dumps({"title": "t", "mode": "eta", "tree": _EVENT_TREE}).encode("utf-8")
        imported = files_client.post("/api/import/json",
                                     data={"file": (io.BytesIO(data), "m.json")},
                                     content_type="multipart/form-data")
        assert imported.status_code == 200, body(imported)
        assert body(imported)["metadata"]["mode"] == "ETA"
        assert _calc(body(imported)["tree"], "a1") == pytest.approx(0.01)
