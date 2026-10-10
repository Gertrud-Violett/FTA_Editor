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
