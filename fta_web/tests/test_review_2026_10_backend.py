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

_XML_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def _ctrl_tree():
    return {"id": "root", "name": "Top\x01event", "type": "Root", "probability": 1.0,
            "logicGate": "OR", "notes": "", "links": [], "children": [
                _leaf("e1", "nul\x00here"),
                _leaf("e2", "bell\x07 esc\x1b nonchar\ufffe"),
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
        assert "nul\ufffdhere" in dot and "Ti\ufffdtle\ufffd" in dot
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


# --------------------------------------------------------------------------
# B-7: the OS refusing a write (or a name) was a bare 500
# --------------------------------------------------------------------------


def _rejected(response, statuses=(400, 403, 404)):
    payload = body(response)
    assert response.status_code in statuses, payload
    assert payload["error"]["code"] == "PATH_REJECTED", payload
    return payload


class TestWriteRefusedByTheOs:
    """``mkstemp`` in a read-only folder, ``os.replace`` onto a file another
    program holds open (Windows) or a name longer than the filesystem allows
    raised straight out of the save, and the user read "Internal server
    error; see the server log." They are path refusals like the sandbox's
    own: PATH_REJECTED (403 for permission denied), naming the file, and the
    document stays unsaved."""

    def _dirty(self, client):
        assert client.post("/api/nodes", json={"parentId": "root", "name": "work"}).status_code == 200

    def test_a_name_too_long_for_the_filesystem(self, files_client, sandbox):
        self._dirty(files_client)
        _rejected(files_client.post("/api/file/save-as", json={"path": "x" * 300 + ".json"}))
        assert get_state().dirty is True and get_state().current_path is None
        assert list(sandbox.iterdir()) == []

    def test_listing_a_name_too_long_for_the_filesystem(self, files_client):
        _rejected(files_client.get("/api/fs/list", query_string={"path": "y" * 5000}))

    def test_permission_denied_creating_the_temp_file(self, files_client, sandbox, monkeypatch):
        import tempfile

        def refuse(*args, **kwargs):
            raise PermissionError(13, "Permission denied", kwargs.get("dir"))

        self._dirty(files_client)
        monkeypatch.setattr(tempfile, "mkstemp", refuse)
        payload = _rejected(files_client.post("/api/file/save-as", json={"path": "a.json"}),
                            statuses=(403,))
        assert payload["error"]["detail"]["reason"] == "unwritable"
        assert "a.json" in payload["error"]["message"]
        assert str(sandbox) not in payload["error"]["message"]
        assert get_state().dirty is True and get_state().current_path is None
        ja = body(files_client.post("/api/file/save-as?lang=ja", json={"path": "a.json"}))
        assert "書き込み権限" in ja["error"]["message"]

    def test_permission_denied_replacing_the_file(self, files_client, sandbox, monkeypatch):
        import os

        target = write_doc(sandbox, "a.json", {"title": "old", "tree": {"id": "root", "name": "R"}})
        assert files_client.post("/api/file/open", json={"path": "a.json"}).status_code == 200
        self._dirty(files_client)
        before = target.read_bytes()

        def refuse(src, dst):
            raise PermissionError(13, "Permission denied", str(dst))

        monkeypatch.setattr(os, "replace", refuse)
        _rejected(files_client.post("/api/file/save"), statuses=(403,))
        monkeypatch.undo()
        assert target.read_bytes() == before  # the old file is intact
        assert sorted(p.name for p in sandbox.iterdir()) == ["a.json"]  # no temp left
        assert get_state().dirty is True


# --------------------------------------------------------------------------
# B-5: an integer too large for a float was a 500 (OverflowError)
# --------------------------------------------------------------------------

HUGE = 10 ** 400  # a valid JSON number; float(HUGE) raises OverflowError


def _invalid_field(response, field):
    payload = body(response)
    assert response.status_code == 400, payload
    assert payload["error"]["code"] == "INVALID_FIELD", payload
    assert payload["error"]["detail"]["field"] == field, payload
    return payload


class TestHugeIntegers:
    """Python's json reads a 400-digit integer exactly, and ``float()`` of it
    raises OverflowError, which no validator caught: probability, quant
    numbers, the analysis settings and the cut-set limits answered 500, and a
    file whose ``analysis`` block held one could not be opened at all."""

    def test_probability(self, tree_client):
        _invalid_field(tree_client.post("/api/nodes", json={
            "parentId": "root", "name": "x", "probability": HUGE}), "probability")
        assert tree_client.post("/api/nodes", json={"parentId": "root", "name": "x"}).status_code == 200
        _invalid_field(tree_client.patch("/api/nodes/root_0", json={"probability": -HUGE}),
                       "probability")

    def test_quant_numbers(self, tree_client):
        assert tree_client.post("/api/nodes", json={"parentId": "root", "name": "x"}).status_code == 200
        _invalid_field(tree_client.patch("/api/nodes/root_0", json={
            "quant": {"model": "rate", "lambda": HUGE}}), "quant.lambda")
        _invalid_field(tree_client.patch("/api/nodes/root_0", json={
            "quant": {"unc": {"ef": HUGE}}}), "quant.unc.ef")

    def test_render_scale_is_clamped_like_any_other_number(self):
        from fta_web.rendering import DEFAULT_SCALE, clamp_scale

        assert clamp_scale(HUGE) == DEFAULT_SCALE
        assert clamp_scale(-HUGE) == DEFAULT_SCALE

    def test_analysis_settings_and_cutset_limits(self, files_client):
        _invalid_field(files_client.post("/api/analysis/settings", json={"missionTime": HUGE}),
                       "analysis.missionTime")
        _invalid_field(files_client.post("/api/analysis/cutsets", json={"cutoff": HUGE}), "cutoff")
        assert get_state().can_undo is False

    def test_a_file_with_one_in_its_analysis_block_opens_with_the_default(self, files_client, sandbox):
        (sandbox / "a.json").write_text(
            '{"tree": {"id": "root", "name": "R"}, "analysis": {"missionTime": %d}}' % HUGE,
            encoding="utf-8")
        opened = files_client.post("/api/file/open", json={"path": "a.json"})
        assert opened.status_code == 200, body(opened)
        doc = body(opened)
        assert doc["analysis"]["missionTime"] == 8760.0
        assert [w["kind"] for w in doc["warnings"]] == ["analysis_invalid"]


# --------------------------------------------------------------------------
# the full application (create_app): its blueprints use the bare ``state``
# --------------------------------------------------------------------------


@pytest.fixture
def app_state():
    """The ``state`` module ``create_app``'s blueprints import (bare name,
    as under run.py), reset before and after: other suites build
    ``create_app`` and only reset ``fta_web.state``."""
    import fta_web.app  # noqa: F401  (puts fta_web/ on sys.path)
    import state as bare_state

    bare_state.reset_state()
    yield bare_state
    bare_state.reset_state()


@pytest.fixture
def full_client(app_state, tmp_path):
    from fta_web.app import create_app

    app = create_app(fs_root=tmp_path)
    with app.test_client() as client:
        yield client


# --------------------------------------------------------------------------
# B-4: a deeply nested request body was a 500 (RecursionError)
# --------------------------------------------------------------------------


class TestDeeplyNestedBody:
    """``json.loads`` raises RecursionError, not ValueError, on ~10,000
    nested brackets, so ``request.get_json(silent=True)`` did not swallow it
    and every JSON endpoint answered 500 instead of the 400 a malformed body
    gets."""

    @pytest.mark.parametrize("method, url", [
        ("POST", "/api/nodes"), ("PATCH", "/api/nodes/root"), ("POST", "/api/metadata"),
        ("POST", "/api/new"), ("POST", "/api/render"), ("POST", "/api/file/open"),
        ("POST", "/api/analysis/settings"), ("POST", "/api/analysis/cutsets"),
    ])
    @pytest.mark.parametrize("deep", ["[" * 100000 + "]" * 100000,
                                      '{"a":' * 50000 + "1" + "}" * 50000],
                             ids=["array", "object"])
    def test_it_is_a_400(self, full_client, method, url, deep):
        response = full_client.open(url, method=method, data=deep, content_type="application/json")
        assert response.status_code == 400, body(response)
        assert body(response)["error"]["code"] == "INVALID_JSON"

    def test_ordinary_nesting_still_parses(self, full_client):
        response = full_client.post("/api/nodes", json={
            "parentId": "root", "name": "x", "trace": {"tags": ["a", "b"]}})
        assert response.status_code == 200, body(response)


# --------------------------------------------------------------------------
# B-9: POST /api/new {"force": "false"} discarded the unsaved document
# --------------------------------------------------------------------------


class TestNewForceFlag:
    """``force`` was read as ``bool(payload.get("force"))``, so the string
    "false" (or "0", "no") -- truthy -- discarded unsaved work that the 409
    UNSAVED_CHANGES guard exists to protect. Only a real boolean forces."""

    @pytest.mark.parametrize("value", ["false", "0", "no", 1, [], {"x": 1}])
    def test_a_non_boolean_force_is_refused_and_discards_nothing(self, tree_client, value):
        c = tree_client
        assert c.post("/api/nodes", json={"parentId": "root", "name": "work"}).status_code == 200
        refused = c.post("/api/new", json={"force": value})
        assert refused.status_code == 400, body(refused)
        assert body(refused)["error"]["code"] == "INVALID_FIELD"
        assert body(refused)["error"]["detail"]["field"] == "force"
        assert get_state().dirty is True
        assert get_state().core.find_node_by_id("root_0") is not None

    def test_null_or_false_is_not_forced_and_true_is(self, tree_client):
        c = tree_client
        assert c.post("/api/nodes", json={"parentId": "root", "name": "work"}).status_code == 200
        for value in (None, False):
            assert c.post("/api/new", json={"force": value}).status_code == 409
        assert c.post("/api/new", json={}).status_code == 409
        assert c.post("/api/new", json={"force": True}).status_code == 200
        assert get_state().core.find_node_by_id("root_0") is None


# --------------------------------------------------------------------------
# B-11 / B-12: Japanese error messages that were never applied, or wrong
# --------------------------------------------------------------------------


def _japanese(text):
    return any(ord(ch) > 0x3000 for ch in text)


class TestJapaneseErrors:
    PORT = 8765
    TOKEN = "test-token-0123456789-abcdefghijklmnopqrstuvwxyz"

    @pytest.fixture
    def guarded(self):
        import flask

        import fta_web.app  # noqa: F401  (puts fta_web/ on sys.path, as test_security does)
        import security

        app = flask.Flask(__name__)

        @app.route("/api/ping")
        def ping():
            return flask.jsonify({"ok": True})

        security.init_app(app, self.TOKEN, self.PORT)
        return app.test_client()

    def test_forbidden_is_localised(self, guarded):
        """B-11: the guard built its 403 with ``to_payload()``, bypassing
        ``api_error_response``, so the catalogued Japanese FORBIDDEN text was
        never used."""
        base = "http://127.0.0.1:%d" % self.PORT
        en = body(guarded.get("/api/ping", base_url=base))["error"]
        ja = body(guarded.get("/api/ping?lang=ja", base_url=base))["error"]
        assert en["code"] == ja["code"] == "FORBIDDEN"
        assert not _japanese(en["message"]) and _japanese(ja["message"])
        assert ja["detail"] == en["detail"] == {"reason": "missing_token"}
        host = body(guarded.get("/api/ping?lang=ja", base_url="http://evil.example:%d" % self.PORT,
                                headers={"X-FTA-Token": self.TOKEN}))["error"]
        assert host["detail"]["reason"] == "host_not_allowed"
        assert _japanese(host["message"]) and host["message"] != ja["message"]

    def test_a_failed_export_is_not_called_a_missing_openpyxl(self, files_client, monkeypatch):
        """B-12: EXPORT_UNAVAILABLE for an export that failed to build fell
        back to the code's Japanese text, which says openpyxl is not
        installed (and is about Excel) -- for a JSON or XML export."""
        from FTA_Editor_core import FTACore

        monkeypatch.setattr(FTACore, "export_to_xml", lambda self, path: (False, "disk on fire"))
        en = files_client.get("/api/export/xml")
        assert en.status_code == 500
        assert body(en)["error"]["message"] == "Could not build the XML export: disk on fire"
        ja = body(files_client.get("/api/export/xml?lang=ja"))["error"]
        assert ja["code"] == "EXPORT_UNAVAILABLE" and ja["detail"]["reason"] == "build_failed"
        assert _japanese(ja["message"]) and "openpyxl" not in ja["message"]

    @pytest.mark.parametrize("reason", ["render_failed", "timeout"])
    def test_a_failed_native_render_is_not_called_a_missing_graphviz(self, monkeypatch, reason):
        """B-12: RENDERER_UNAVAILABLE in Japanese always said Graphviz must
        be installed, also when it is installed and the render failed or
        timed out."""
        import flask

        from fta_web import rendering
        from fta_web.routes import render as render_routes

        def fail(*args, **kwargs):
            raise rendering.RenderError("dot failed", reason=reason)

        monkeypatch.setattr(render_routes, "render_native", fail)
        reset_state()
        app = flask.Flask(__name__)
        app.register_blueprint(render_routes.render_bp)
        with app.test_client() as client:
            generic = body(client.post("/api/render?lang=ja", json={"format": "png"}))["error"]
        assert generic["detail"]["reason"] == reason
        assert _japanese(generic["message"]) and "インストール" not in generic["message"]


# --------------------------------------------------------------------------
# B-6: a very deep tree was installed, then every request was a 500
# --------------------------------------------------------------------------


def _chain(levels):
    """A tree whose deepest node is ``levels`` below the root (ids n1..nN)."""
    node = {"id": "n%d" % levels, "name": "leaf", "probability": 0.5, "children": []}
    for level in range(levels - 1, 0, -1):
        node = {"id": "n%d" % level, "name": "g%d" % level, "logicGate": "OR", "children": [node]}
    return {"id": "root", "name": "Top", "logicGate": "OR", "children": [node]}


class TestTreeDepthLimit:
    """Every payload deep-copies the tree, four Python frames per level, so
    past ~245 levels a request died with RecursionError. Opening such a file
    answered 500 *after* it had replaced the document (unsaved work gone,
    history cleared), and from then on state, every edit, undo and Save As
    were 500s until New. Adding a level by hand did the same, the add itself
    applied. The tree is now limited to config.MAX_TREE_DEPTH levels: a
    deeper file is refused before anything changes, an add or a move that
    would exceed it is a 400."""

    def test_the_limit_leaves_room_below_the_recursion_failure(self):
        from fta_web import config

        assert 50 <= config.MAX_TREE_DEPTH <= 200

    def test_a_tree_at_the_limit_is_fully_usable(self, files_client, sandbox):
        from fta_web.config import MAX_TREE_DEPTH

        write_doc(sandbox, "deep.json", {"title": "d", "tree": _chain(MAX_TREE_DEPTH)})
        c = files_client
        assert c.post("/api/file/open", json={"path": "deep.json"}).status_code == 200
        assert c.patch("/api/nodes/n1", json={"name": "renamed"}).status_code == 200
        assert c.post("/api/undo").status_code == 200
        assert c.post("/api/file/save-as", json={"path": "out.json"}).status_code == 200
        assert c.get("/api/analysis/summary").status_code == 200

    def test_a_deeper_file_is_refused_before_anything_changes(self, files_client, sandbox):
        from fta_web.config import MAX_TREE_DEPTH

        c = files_client
        assert c.post("/api/nodes", json={"parentId": "root", "name": "unsaved"}).status_code == 200
        write_doc(sandbox, "deep.json", {"title": "d", "tree": _chain(MAX_TREE_DEPTH + 60)})
        refused = c.post("/api/file/open", json={"path": "deep.json"})
        assert refused.status_code == 400, body(refused)
        error = body(refused)["error"]
        assert error["code"] == "INVALID_JSON" and error["detail"]["reason"] == "too_deep"
        assert "%d" % MAX_TREE_DEPTH in error["message"]
        state = get_state()
        assert state.dirty is True and state.current_path is None and state.can_undo
        assert state.core.find_node_by_id("root_0")["name"] == "unsaved"
        assert c.get("/api/state").status_code == 200

    def test_a_deeper_import_is_refused_too(self, files_client):
        import io

        from fta_web.config import MAX_TREE_DEPTH

        data = json.dumps({"title": "d", "tree": _chain(MAX_TREE_DEPTH + 1)}).encode("utf-8")
        refused = files_client.post("/api/import/json", data={"file": (io.BytesIO(data), "d.json")},
                                    content_type="multipart/form-data")
        assert refused.status_code == 400, body(refused)
        assert body(refused)["error"]["detail"]["reason"] == "too_deep"

    def test_an_add_or_move_past_the_limit_is_refused(self, files_client, sandbox):
        from fta_web.config import MAX_TREE_DEPTH

        c = files_client
        tree = _chain(MAX_TREE_DEPTH)
        tree["children"].append({"id": "x", "name": "X", "children": [
            {"id": "x1", "name": "X1", "probability": 0.1, "children": []}]})
        write_doc(sandbox, "deep.json", {"title": "d", "tree": tree})
        assert c.post("/api/file/open", json={"path": "deep.json"}).status_code == 200

        added = c.post("/api/nodes", json={"parentId": "n%d" % MAX_TREE_DEPTH, "name": "too deep"})
        assert added.status_code == 400, body(added)
        assert body(added)["error"]["code"] == "INVALID_FIELD"
        # x (height 1) under n(MAX-1) would put x1 at MAX + 1
        moved = c.post("/api/nodes/x/move", json={"newParentId": "n%d" % (MAX_TREE_DEPTH - 1)})
        assert moved.status_code == 400, body(moved)
        assert body(moved)["error"]["code"] == "INVALID_FIELD"
        assert get_state().can_undo is False  # neither left an undo step
        # one level shallower is fine
        ok = c.post("/api/nodes/x/move", json={"newParentId": "n%d" % (MAX_TREE_DEPTH - 2)})
        assert ok.status_code == 200, body(ok)


# --------------------------------------------------------------------------
# B-13: GET /api/export/json rewrote the open document's date
# --------------------------------------------------------------------------


class TestExportIsReadOnly:
    """``save_to_json`` fills an empty date with today before writing. The
    JSON export calls it on the live document, so a GET changed the
    document -- not undoable, not marked modified. The download still
    carries the date a Save would write."""

    def test_export_leaves_an_empty_date_alone(self, files_client):
        c = files_client
        assert c.post("/api/metadata", json={"date": ""}).status_code == 200
        exported = c.get("/api/export/json")
        assert exported.status_code == 200
        assert json.loads(exported.get_data(as_text=True))["date"] != ""
        assert body(c.get("/api/state"))["metadata"]["date"] == ""
        assert get_state().core.date == ""


# --------------------------------------------------------------------------
# B-14: a symlink loop in a folder made the folder unlistable (Python < 3.13)
# --------------------------------------------------------------------------


def _symlinks_supported():
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as scratch:
        try:
            os.symlink("x", os.path.join(scratch, "link"))
        except (OSError, NotImplementedError):
            return False
    return True


@pytest.mark.skipif(not _symlinks_supported(), reason="symlinks are not available here")
class TestSymlinkLoopInAListing:
    """``list_directory`` resolves every symlink it lists to keep escaping
    ones out. Up to Python 3.12 ``Path.resolve()`` raises RuntimeError
    ("Symlink loop") even when not strict -- and only OSError was caught, so
    a folder holding one looping link answered 500 and could not be browsed
    at all. (3.13 returns the path instead; the loop is simulated so the test
    means the same on every version.)"""

    def test_the_loop_is_skipped_and_the_rest_listed(self, files_client, sandbox, monkeypatch):
        import os
        import pathlib

        write_doc(sandbox, "ok.json", {"tree": {"id": "root", "name": "R"}})
        os.symlink("loop", sandbox / "loop")
        real_resolve = pathlib.Path.resolve

        def resolve(self, strict=False):
            if self.name == "loop":  # what Python 3.10-3.12 do
                raise RuntimeError("Symlink loop from %r" % str(self))
            return real_resolve(self, strict=strict)

        monkeypatch.setattr(pathlib.Path, "resolve", resolve)
        listed = files_client.get("/api/fs/list")
        assert listed.status_code == 200, body(listed)
        assert [f["name"] for f in body(listed)["files"]] == ["ok.json"]
        assert body(listed)["dirs"] == []


# --------------------------------------------------------------------------
# B-15: an XLSX export that failed on the data blamed a missing openpyxl
# --------------------------------------------------------------------------


class TestXlsxFailureIsNotMissingOpenpyxl:
    """``excel_events`` reports every failure while adding its sheets as
    "Failed to add the Events sheet (openpyxl): ...", and the export route
    mapped any error mentioning openpyxl to 503 "Excel export needs the
    'openpyxl' package, which is not installed" -- so a control character in
    a node's data source (which openpyxl refuses in a cell) sent the user to
    reinstall a package they have. Only an import failure means that."""

    def test_a_data_error_is_reported_as_a_failed_build(self, files_client):
        pytest.importorskip("openpyxl")
        c = files_client
        assert c.post("/api/nodes", json={"parentId": "root", "name": "Pump", "probability": 0.1,
                                          "quant": {"source": "OREDA\x01 2015"}}).status_code == 200
        failed = c.get("/api/export/xlsx")
        assert failed.status_code == 500, body(failed)
        error = body(failed)["error"]
        assert error["code"] == "EXPORT_UNAVAILABLE"
        assert error["detail"]["reason"] == "build_failed"
        assert "pip install" not in error["message"] and "not installed" not in error["message"]

    def test_an_import_failure_still_explains_how_to_install(self, files_client, monkeypatch):
        from FTA_Editor_core import FTACore

        monkeypatch.setattr(FTACore, "export_to_excel", lambda self, path: (
            False, "Failed to export Excel: import of openpyxl halted; None in sys.modules"))
        missing = body(files_client.get("/api/export/xlsx"))
        assert missing["error"]["detail"]["package"] == "openpyxl", missing


# --------------------------------------------------------------------------
# B-16: a download name that cannot be encoded was a 500
# --------------------------------------------------------------------------


class TestDownloadNameIsEncodable:
    """The download is named after the title when the document has no file.
    A title holding a lone surrogate (accepted by POST /api/metadata from a
    JSON escape, or read from a file) cannot be UTF-8 encoded, so
    ``send_file`` raised building Content-Disposition: the XML export (and
    the DOCX report) answered 500 although the file itself was built."""

    def test_the_name_drops_what_cannot_be_encoded(self):
        from fta_web.fsbrowser import safe_download_name

        name = safe_download_name("Pump \ud83d", ".xml")
        name.encode("utf-8")
        assert name.startswith("Pump") and name.endswith(".xml")
        assert safe_download_name("ポンプ \U0001f600", ".xml") == "ポンプ \U0001f600.xml"

    def test_the_xml_export_downloads(self, files_client):
        c = files_client
        assert c.post("/api/metadata", data=json.dumps({"title": "Pump \ud83d"}),
                      content_type="application/json").status_code == 200
        exported = c.get("/api/export/xml")
        assert exported.status_code == 200, exported.get_data()[:300]
        assert "attachment" in exported.headers["Content-Disposition"]


# --------------------------------------------------------------------------
# B-17: the move cycle check walked the whole tree once per moved node
# --------------------------------------------------------------------------


class TestMoveCycleCheckIsLinear:
    """``_is_descendant_of`` re-found every node of the moved subtree with a
    whole-tree ``find_node_by_id`` walk: O(subtree x tree), under the state
    lock, and done twice per move. Moving a 3,000-event branch of a 6,000-node
    tree froze every request for over a second (quadratic beyond that)."""

    def _wide(self, leaves):
        return {"id": "root", "name": "Top", "logicGate": "OR", "children": [
            {"id": "b%d" % b, "name": "B%d" % b, "logicGate": "OR", "children": [
                _leaf("b%d_%d" % (b, i), "leaf") for i in range(leaves)]}
            for b in range(2)]}

    def test_the_check_does_not_search_once_per_descendant(self, monkeypatch):
        from fta_web import tree_ops

        core = _core(self._wide(300))
        calls = []
        real_find = core.find_node_by_id
        monkeypatch.setattr(core, "find_node_by_id",
                            lambda node_id: calls.append(node_id) or real_find(node_id))
        assert tree_ops.would_create_cycle(core, "b0", "b1") is False
        assert len(calls) < 10, len(calls)

    def test_answers_are_unchanged(self):
        from fta_web import tree_ops

        core = _core(self._wide(3))
        assert tree_ops.would_create_cycle(core, "b0", "b0") is True
        assert tree_ops.would_create_cycle(core, "b0", "b0_1") is True
        assert tree_ops.would_create_cycle(core, "root", "b0_1") is True
        assert tree_ops.would_create_cycle(core, "b0_1", "b0") is False   # reorder in place
        assert tree_ops.would_create_cycle(core, "b0_1", "b1") is False
        assert tree_ops.would_create_cycle(core, "b0", "root") is False
        assert tree_ops.would_create_cycle(core, "ghost", "b0") is False
        assert tree_ops.would_create_cycle(core, "b0", "ghost") is False


# --------------------------------------------------------------------------
# B-18: an edit that changes nothing cost an undo step, the redo history
#       and the "saved" state
# --------------------------------------------------------------------------


class TestNoOpEdits:
    """``POST /api/analysis/settings`` (the tabs' "Save as document
    defaults", which posts the values even when they are the document's),
    ``POST /api/metadata``, ``PATCH /api/nodes/<id>`` and a move to where the
    node already is pushed an undo step, cleared redo and marked a saved
    document modified although nothing changed: Ctrl+Z then did nothing
    visible, and the redo the user had was gone. ``POST /api/ai/changes/apply``
    already refuses to record a step for a batch that changed nothing."""

    @pytest.fixture
    def saved_with_redo(self, files_client):
        """A saved document with one step to undo and one to redo."""
        c = files_client
        assert c.post("/api/nodes", json={"parentId": "root", "name": "A", "probability": 0.1}).status_code == 200
        assert c.post("/api/nodes", json={"parentId": "root", "name": "B", "probability": 0.2}).status_code == 200
        assert c.post("/api/nodes", json={"parentId": "root", "name": "C", "probability": 0.3}).status_code == 200
        assert c.post("/api/undo").status_code == 200
        assert c.post("/api/file/save-as", json={"path": "doc.json"}).status_code == 200
        state = get_state()
        assert state.can_undo and state.can_redo and not state.dirty
        return c

    def _unchanged(self, response, undo_depth=2):
        assert response.status_code == 200, body(response)
        state = get_state()
        assert len(state._undo) == undo_depth and state.can_redo and not state.dirty, (
            len(state._undo), state.can_redo, state.dirty)
        payload = body(response)
        assert payload["canRedo"] is True and payload["dirty"] is False

    def test_settings_equal_to_the_document(self, saved_with_redo):
        c = saved_with_redo
        self._unchanged(c.post("/api/analysis/settings", json={
            "missionTime": 8760, "cutsets": {"maxOrder": 6}, "mc": {"seed": None}}))

    def test_metadata_equal_to_the_document(self, saved_with_redo):
        c = saved_with_redo
        meta = body(c.get("/api/state"))["metadata"]
        self._unchanged(c.post("/api/metadata", json=meta))

    def test_patch_with_the_values_already_there(self, saved_with_redo):
        c = saved_with_redo
        self._unchanged(c.patch("/api/nodes/root_0", json={"name": "A", "probability": 0.1}))
        self._unchanged(c.patch("/api/nodes/root_0", json={"quant": None, "trace": None}))

    def test_move_to_where_the_node_already_is(self, saved_with_redo):
        c = saved_with_redo
        self._unchanged(c.post("/api/nodes/root_1/move", json={"newParentId": "root", "index": 1}))
        self._unchanged(c.post("/api/nodes/root_1/move", json={"newParentId": "root"}))
        self._unchanged(c.post("/api/nodes/root_0/move", json={"newParentId": "root", "index": 0}))

    def test_a_real_change_is_still_one_step(self, saved_with_redo):
        c = saved_with_redo
        changed = c.patch("/api/nodes/root_0", json={"name": "A2"})
        assert changed.status_code == 200
        state = get_state()
        assert len(state._undo) == 3 and not state.can_redo and state.dirty
        moved = c.post("/api/nodes/root_0/move", json={"newParentId": "root", "index": 1})
        assert body(moved)["tree"]["children"][1]["id"] == "root_0"
        assert len(get_state()._undo) == 4
