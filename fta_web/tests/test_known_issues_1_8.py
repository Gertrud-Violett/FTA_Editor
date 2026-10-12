"""The known issues of release 1.8.0, fixed.

One block per issue, in the order of the release notes:

1. the launcher's fixed default port (preferences were lost at each start)
2. Load, Open example and import refuse to replace unsaved work
3. moving or deleting several thousand nodes at once
4. Stop in the AI chat frees the server's AI slot
5. the recovery copy of unsaved work
6. choosing the allowed folder while the editor runs
7. the number reader: ``1e-400`` and ``-0``

No test reaches the network (the AI provider is a fake that waits on a
``threading.Event``), none opens a native folder picker (the picker is
replaced by a function), and the per-user folder -- credentials,
``ui_prefs.json`` and the recovery copies -- is redirected to ``tmp_path``
for every test here. The whole flow is driven in a real browser by
``tests/gui/s_ki.js``.
"""
import copy
import json
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from AI_agent_handler import AICredentialManager  # noqa: E402

from fta_web import ai_bridge, config, tree_ops  # noqa: E402
from fta_web.state import get_state, reset_state  # noqa: E402

STATIC = REPO / "fta_web" / "static" / "js"
DOCS = REPO / "docs"

PORT = 8765
BASE_URL = "http://127.0.0.1:%d" % PORT
TOKEN = "test-token-0123456789-abcdefghijklmnopqrstuvwxyz"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _node(script: str):
    out = subprocess.run(["node", "--input-type=module", "-"], input=script, capture_output=True,
                         text=True, encoding="utf-8", check=True, timeout=60).stdout
    return json.loads(out)


def body(response):
    return json.loads(response.get_data(as_text=True))


def error(response):
    return body(response)["error"]


# ---- fixtures -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def per_user_home(tmp_path, monkeypatch):
    """The per-user folder in tmp_path: credentials, ui_prefs.json, recovery."""
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


@pytest.fixture
def sandbox(app):
    return Path(get_state().fs_root)


def add(client, parent="root", **fields):
    payload = {"parentId": parent, "name": "node", "probability": 0.1}
    payload.update(fields)
    response = client.post("/api/nodes", json=payload)
    assert response.status_code == 200, body(response)
    return body(response)["node"]["id"]


def state_of(client):
    return body(client.get("/api/state"))


# =============================================================================================
# 7: the number reader
# =============================================================================================


def _parse_numbers(texts):
    script = (
        "import { parseNumberText } from %s;\n" % json.dumps((STATIC / "numfmt.js").as_uri())
        + "const input = %s;\n" % json.dumps(texts)
        + "console.log(JSON.stringify(input.map((t) => { const r = parseNumberText(t);"
          " return r.ok ? [r.value, r.text, r.changed, Object.is(r.value, -0)] : null; })));"
    )
    return dict(zip(texts, _node(script)))


@needs_node
def test_7_a_number_too_small_for_a_double_is_refused_not_read_as_zero():
    refused = ["1e-400", "-1e-400", "1E-999", "0.0001e-400", "1e-400%", "1e-322%", "1e-200/1e200",
               "１ｅ－４００", "5,0e-400"]
    assert _parse_numbers(refused) == {text: None for text in refused}


@needs_node
def test_7_the_smallest_numbers_a_double_holds_are_still_read():
    got = _parse_numbers(["1e-300", "5e-324", "1e-320%"])
    assert got["1e-300"] == [1e-300, "1e-300", False, False]
    assert got["5e-324"][0] == 5e-324
    assert got["1e-320%"][0] > 0


@needs_node
def test_7_a_typed_zero_is_zero_and_minus_zero_is_shown_as_zero():
    got = _parse_numbers(["0", "0.0", "0e5", ".0", "0%", "0/5", "0,0", "-0", "-0.0", "－０", "-0%",
                          "-0/5", "-0e3"])
    assert all(row is not None and row[0] == 0 and row[3] is False for row in got.values()), got
    # a zero written without a sign is left as typed
    assert got["0"] == [0, "0", False, False]
    assert got["0.0"] == [0, "0.0", False, False]
    assert got["0e5"] == [0, "0e5", False, False]
    # a negative zero is shown as the zero it is
    for text in ("-0", "-0.0", "－０", "-0%", "-0/5", "-0e3"):
        assert got[text] == [0, "0", True, False], text


# =============================================================================================
# 3: several thousand nodes in one batch
# =============================================================================================


def _leaf(node_id, name="e", probability=0.001):
    return {"id": node_id, "name": name, "type": "Event", "probability": probability,
            "logicGate": "OR", "notes": "", "links": [], "children": []}


def _install(tree):
    """Make ``tree`` the live document (as an opened file would be)."""
    state = get_state()
    with state.lock:
        state.reset()
        state.core.set_data(tree)
        state.core.recalculate_probabilities()
    return state


def _wide_tree(gates=60, leaves=80):
    """root -> ``gates`` gates -> ``leaves`` events each (4,861 nodes by default)."""
    root = _leaf("root", "Top")
    for g in range(gates):
        gate = _leaf("root_%d" % g, "G%d" % g)
        gate["children"] = [_leaf("root_%d_%d" % (g, i)) for i in range(leaves)]
        root["children"].append(gate)
    return root


def test_3_a_batch_of_4800_nodes_moves_and_deletes_within_the_bound(client):
    _install(_wide_tree())
    original = state_of(client)["tree"]
    ids = ["root_%d_%d" % (g, i) for g in range(60) for i in range(80)]
    assert len(ids) == 4800

    started = time.perf_counter()
    moved = client.post("/api/batch/move", json={"ids": ids, "newParentId": "root_0", "index": 0})
    move_s = time.perf_counter() - started
    assert moved.status_code == 200, body(moved)
    assert body(moved)["movedIds"] == ids
    tree = body(moved)["tree"]
    assert [c["id"] for c in tree["children"][0]["children"]] == ids
    assert all(g["children"] == [] for g in tree["children"][1:])

    started = time.perf_counter()
    deleted = client.post("/api/batch/delete", json={"ids": ids})
    delete_s = time.perf_counter() - started
    assert deleted.status_code == 200, body(deleted)
    assert body(deleted)["deletedIds"] == ids
    assert all(g["children"] == [] for g in body(deleted)["tree"]["children"])

    # Each was seconds (9.4 s and 4.1 s measured on 1.8.0) and is well under
    # one now; the bound is wide so that a slow CI machine does not fail it.
    assert move_s < 3.0 and delete_s < 3.0, (move_s, delete_s)
    # one undo step each
    assert client.post("/api/undo", json={}).status_code == 200
    assert client.post("/api/undo", json={}).status_code == 200
    assert state_of(client)["tree"] == original
    assert state_of(client)["canUndo"] is False
    print("batch of 4800: move %.2f s, delete %.2f s" % (move_s, delete_s))


def _random_tree(rng, size):
    nodes = [_leaf("root", "Top")]
    for n in range(size):
        parent = rng.choice(nodes[-12:] if rng.random() < 0.5 else nodes)
        node = _leaf("n%d" % n, "N%d" % n, round(rng.random() / 10, 4))
        if rng.random() < 0.3:
            node["links"] = [{"target_id": "n%d" % rng.randrange(size), "relation": "OR"}]
        if rng.random() < 0.05:
            node["transferTo"] = "n%d" % rng.randrange(size)
        parent["children"].append(node)
        nodes.append(node)
    return nodes[0]


def _answer(client, path, payload):
    response = client.post(path, json=payload)
    answer = body(response)
    # The counters differ between two documents; everything else must not.
    for key in ("revision", "documentSerial"):
        answer.pop(key, None)
    return response.status_code, answer


def test_3_the_one_pass_answers_exactly_what_the_walk_per_id_answered(client, monkeypatch):
    """Every request is sent twice to the same document: once with the index
    and once without it (which is the 1.8.0 code path)."""
    rng = random.Random(1810)
    requests = 0
    refused = set()
    for round_ in range(60):
        tree = _random_tree(rng, rng.randrange(3, 60))
        every = sorted(tree_ops.all_ids(type("C", (), {"get_data": lambda self: tree})()))
        ids = rng.sample(every, rng.randrange(1, min(len(every), 12) + 1))
        if rng.random() < 0.15:
            ids.append("nowhere")
        if rng.random() < 0.3 and "root" in ids:
            ids.remove("root")
        if not ids:
            ids = ["n0"]
        rng.shuffle(ids)
        parent = rng.choice(every + ["missing"] if rng.random() < 0.1 else every)
        index = rng.choice([None, 0, 1, 2, 99])
        for path, payload in (
            ("/api/batch/move", {"ids": ids, "newParentId": parent, "index": index}),
            ("/api/batch/delete", {"ids": ids}),
        ):
            answers = []
            for fast in (True, False):
                with monkeypatch.context() as patch:
                    if not fast:
                        from fta_web.routes import tree as tree_routes
                        patch.setattr(tree_routes, "index_tree", lambda core: None)
                    _install(copy.deepcopy(tree))
                    answers.append(_answer(client, path, payload))
                    answers.append(state_of(client)["tree"])
                    answers.append(state_of(client)["canUndo"])
            assert answers[:3] == answers[3:], (round_, path, payload)
            requests += 1
            if answers[0][0] != 200:
                refused.add(answers[0][1]["error"]["code"])
    # the comparison saw refusals of each kind as well as successes
    assert requests == 120
    assert {"NODE_NOT_FOUND", "ROOT_PROTECTED", "CYCLE_REJECTED"} <= refused, refused


def test_3_a_tree_in_another_shape_keeps_the_walk_per_id(client):
    """Ids that are not strings, or twice in the tree: no index is built, so
    the answer is the one the per-id helpers always gave."""
    tree = _wide_tree(2, 3)
    assert tree_ops.index_tree(_install(copy.deepcopy(tree)).core) is not None

    numbered = copy.deepcopy(tree)
    numbered["children"][0]["children"][0]["id"] = 7
    assert tree_ops.index_tree(_install(numbered).core) is None

    twice = copy.deepcopy(tree)
    twice["children"][1]["children"][0]["id"] = "root_0_0"
    assert tree_ops.index_tree(_install(twice).core) is None
    deleted = client.post("/api/batch/delete", json={"ids": ["root_0_0"]})
    assert deleted.status_code == 200
    # delete_node_from_data removes every node of that id, as it always did
    assert [len(g["children"]) for g in body(deleted)["tree"]["children"]] == [2, 2]

    no_list = copy.deepcopy(tree)
    del no_list["children"][0]["children"][0]["children"]
    assert tree_ops.index_tree(_install(no_list).core) is None


def test_3_the_index_answers_what_the_helpers_answer():
    rng = random.Random(3)
    for _ in range(30):
        tree = _random_tree(rng, rng.randrange(1, 80))
        core = type("C", (), {
            "get_data": lambda self: tree,
            "find_node_by_id": lambda self, node_id: next(
                (n for n in _walk(tree) if n["id"] == node_id), None),
        })()
        index = tree_ops.index_tree(core)
        assert index.order == [n["id"] for n in _walk(tree)]
        heights = index.heights()
        for node in _walk(tree):
            node_id = node["id"]
            assert index.subtree_ids(node_id) == tree_ops.subtree_ids(core, node_id)
            assert heights[node_id] == tree_ops.tree_height(node)
            assert len(index.ancestors(node_id)) == tree_ops.depth_of(core, node_id)
            assert (index.ancestors(node_id)[:1] or [None])[0] == tree_ops.find_parent_id(core, node_id)


def _walk(node):
    yield node
    for child in node["children"]:
        yield from _walk(child)


# =============================================================================================
# 1: the launcher's default port
# =============================================================================================


@pytest.fixture
def launcher():
    sys.path.insert(0, str(REPO / "fta_web"))
    import run  # the launcher's own module name

    return run


def _listening(launcher):
    """A socket listening on a free loopback port, bound the way Werkzeug's
    server binds (with address reuse)."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((launcher.config.HOST, 0))
    sock.listen(1)
    return sock


def test_1_the_default_port_is_8765_and_is_used_when_it_is_free(launcher, monkeypatch):
    assert launcher.config.DEFAULT_PORT == 8765
    # On a port known to be free, so that an editor running on this machine
    # does not decide the test.
    free = launcher._free_port()
    monkeypatch.setattr(launcher.config, "DEFAULT_PORT", free)
    assert launcher._port_is_free(free)
    assert launcher.choose_port(None) == (free, False)


def test_1_a_second_copy_starts_on_a_free_port_and_says_so(launcher, monkeypatch):
    taken = _listening(launcher)
    try:
        port = taken.getsockname()[1]
        monkeypatch.setattr(launcher.config, "DEFAULT_PORT", port)
        assert launcher._port_is_free(port) is False
        chosen, fell_back = launcher.choose_port(None)
        assert fell_back is True and chosen != port and 1024 < chosen < 65536
        assert launcher._port_is_free(chosen)
    finally:
        taken.close()


def test_1_port_0_is_any_free_port_and_a_given_port_is_taken_as_given(launcher, monkeypatch):
    assert launcher.parse_args(["--port", "0"]).port == 0
    assert launcher.parse_args([]).port is None
    for bad in ("-1", "65536", "x"):
        with pytest.raises(SystemExit):
            launcher.parse_args(["--port", bad])

    monkeypatch.setattr(launcher.config, "DEFAULT_PORT", launcher._free_port())
    chosen, fell_back = launcher.choose_port(0)
    assert fell_back is False and chosen != launcher.config.DEFAULT_PORT and chosen > 1024
    # an explicit port is never replaced, also when it is taken: the server
    # then fails to start with "address in use", as it always did
    taken = _listening(launcher)
    try:
        port = taken.getsockname()[1]
        assert launcher.choose_port(port) == (port, False)
    finally:
        taken.close()


class _FakeApp:
    def __init__(self):
        self.ran = None

    def run(self, **kwargs):
        self.ran = kwargs


def _launch(launcher, monkeypatch, capsys, argv):
    built = {}

    def create_app(token, port, fs_root):
        built.update(token=token, port=port, fs_root=fs_root, app=_FakeApp())
        return built["app"]

    monkeypatch.setattr(launcher, "create_app", create_app)
    assert launcher.main(argv + ["--no-browser"]) == 0
    return built, capsys.readouterr().out


def test_1_the_launcher_serves_the_port_it_printed_and_pins_the_guard_to_it(
        launcher, monkeypatch, capsys, tmp_path):
    free = launcher._free_port()
    monkeypatch.setattr(launcher.config, "DEFAULT_PORT", free)
    built, out = _launch(launcher, monkeypatch, capsys, ["--root", str(tmp_path)])
    assert built["port"] == free and built["app"].ran["port"] == free
    assert built["app"].ran["host"] == "127.0.0.1"
    assert "http://127.0.0.1:%d/?t=%s" % (free, built["token"]) in out
    assert "Note" not in out

    taken = _listening(launcher)
    try:
        port = taken.getsockname()[1]
        monkeypatch.setattr(launcher.config, "DEFAULT_PORT", port)
        built, out = _launch(launcher, monkeypatch, capsys, ["--root", str(tmp_path)])
        assert built["port"] != port and built["app"].ran["port"] == built["port"]
        note = [line for line in out.splitlines() if "Note" in line]
        assert len(note) == 1
        assert "port %d is in use" % port in note[0] and str(built["port"]) in note[0]
        assert "preferences kept by the browser will not carry over" in note[0]
    finally:
        taken.close()


def test_1_the_port_is_documented():
    for path in (REPO / "build" / "README.md", REPO / "QUICKSTART.md", DOCS / "USER_GUIDE.md"):
        text = _read(path)
        assert "8765" in text and "--port 0" in text, path.name


# =============================================================================================
# 2: Load, Open example and import refuse to replace unsaved work
# =============================================================================================

EXAMPLES = REPO / "fta_web" / "examples"


def _sample(sandbox, name="sample.json"):
    target = sandbox / name
    target.write_bytes((EXAMPLES / "sampleFTA.json").read_bytes())
    return target


def _replacers(sandbox):
    """``{label: send}`` for every request that replaces the whole document;
    ``send(client, force)`` posts it, with or without the flag."""
    import io

    path = str(_sample(sandbox))

    def open_file(client, force):
        return client.post("/api/file/open", json=dict({"path": path}, **force))

    def open_example(client, force):
        return client.post("/api/examples/open", json=dict({"name": "sampleFTA.json"}, **force))

    def import_json(client, force):
        data = {"file": (io.BytesIO((EXAMPLES / "sampleFTA.json").read_bytes()), "mine.json")}
        data.update({key: json.dumps(value) if isinstance(value, bool) else value
                     for key, value in force.items()})
        return client.post("/api/import/json", data=data, content_type="multipart/form-data")

    def new(client, force):
        return client.post("/api/new", json=force)

    return {"open": open_file, "example": open_example, "import": import_json, "new": new}


@pytest.mark.parametrize("which", ["open", "example", "import", "new"])
def test_2_unsaved_work_is_not_replaced_without_the_flag(client, sandbox, which):
    send = _replacers(sandbox)[which]
    kept = add(client, name="not saved yet")
    before = state_of(client)
    assert before["dirty"] is True

    refused = send(client, {})
    assert refused.status_code == 409 and error(refused)["code"] == "UNSAVED_CHANGES"
    after = state_of(client)
    assert after["tree"] == before["tree"] and after["dirty"] is True
    assert (after["revision"], after["documentSerial"]) == (before["revision"], before["documentSerial"])
    assert after["canUndo"] is True, "the undo history is kept with the document"

    # "false" is not "discard"
    assert send(client, {"force": False}).status_code == 409
    assert "not saved yet" in json.dumps(state_of(client)["tree"]) and kept

    replaced = send(client, {"force": True})
    assert replaced.status_code == 200, body(replaced)
    assert "not saved yet" not in json.dumps(body(replaced)["tree"])
    assert state_of(client)["documentSerial"] == before["documentSerial"] + 1


@pytest.mark.parametrize("which", ["open", "example", "import", "new"])
def test_2_a_saved_document_is_replaced_without_the_flag(client, sandbox, which):
    """What every existing client does on a document with nothing to lose."""
    send = _replacers(sandbox)[which]
    assert state_of(client)["dirty"] is False
    assert send(client, {}).status_code == 200

    # and after a save the document is clean again
    client.post("/api/new", json={"force": True})
    add(client, name="saved")
    assert client.post("/api/file/save-as", json={"path": str(sandbox / "kept.json")}).status_code == 200
    assert send(client, {}).status_code == 200


@pytest.mark.parametrize("which", ["open", "example", "new"])
@pytest.mark.parametrize("flag", ["true", "false", 1, 0, "yes", [True]])
def test_2_the_flag_is_a_real_boolean(client, sandbox, which, flag):
    send = _replacers(sandbox)[which]
    add(client, name="not saved yet")
    refused = send(client, {"force": flag})
    assert refused.status_code == 400 and error(refused)["code"] == "INVALID_FIELD"
    assert error(refused)["detail"]["field"] == "force"
    assert state_of(client)["dirty"] is True


@pytest.mark.parametrize("flag", ["1", "yes", "True", "TRUE", "on", ""])
def test_2_the_form_field_of_an_import_is_true_or_false_and_nothing_else(client, sandbox, flag):
    send = _replacers(sandbox)["import"]
    add(client, name="not saved yet")
    refused = send(client, {"force": flag})
    assert refused.status_code == 400 and error(refused)["detail"]["field"] == "force"
    assert state_of(client)["dirty"] is True
    assert send(client, {"force": "false"}).status_code == 409
    assert send(client, {"force": "true"}).status_code == 200


def test_2_a_request_that_fails_anyway_fails_as_it_did(client, sandbox):
    """The refusal comes last: a wrong path is still a wrong path."""
    add(client, name="not saved yet")
    missing = client.post("/api/file/open", json={"path": str(sandbox / "nowhere.json")})
    assert missing.status_code == 404 and error(missing)["code"] == "PATH_REJECTED"
    outside = client.post("/api/file/open", json={"path": str(sandbox.parent / "x.json")})
    assert error(outside)["detail"]["reason"] == "outside_root"
    unknown = client.post("/api/examples/open", json={"name": "no such example.json"})
    assert unknown.status_code == 404
    (sandbox / "broken.json").write_text("{", encoding="utf-8")
    broken = client.post("/api/file/open", json={"path": str(sandbox / "broken.json"), "force": True})
    assert broken.status_code == 400 and error(broken)["code"] == "INVALID_JSON"
    assert state_of(client)["dirty"] is True, "a failed open, forced or not, replaces nothing"


def test_2_the_second_tab_case(client, sandbox):
    """Tab A read the document while it was saved; tab B then edited it.
    A's Load arrives without the flag (A thinks there is nothing to lose)."""
    path = str(_sample(sandbox))
    seen_by_a = state_of(client)
    assert seen_by_a["dirty"] is False
    add(client, name="typed in the other tab")

    load_from_a = client.post("/api/file/open", json={"path": path})
    assert load_from_a.status_code == 409
    assert "typed in the other tab" in json.dumps(state_of(client)["tree"])


def _function(src: str, header: str) -> str:
    """Source of the function whose header is ``header``, to its closing brace."""
    start = src.index(header)
    depth = 0
    for i in range(src.index("{", start + len(header)), len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
    raise AssertionError("unbalanced braces")


def test_2_the_page_sends_the_flag_only_after_discard_and_asks_on_a_409():
    src = _read(STATIC / "main.js")
    replace = _function(src, "async function replaceDocument(send)")
    # forced only while the document is still modified, which after
    # leaveDocument() means the user chose Discard
    assert "let force = Boolean(store.state && store.state.dirty);" in replace
    assert "err.code !== 'UNSAVED_CHANGES'" in replace
    assert replace.index("store.applyMutation({ dirty: true });") < replace.index("leaveDocument('open')")
    assert "return null;" in replace
    for header, call in (
        ("async function actionLoad()", "api.post('/file/open', force ? { path, force: true } : { path })"),
        ("async function actionOpenExample(asked)",
         "api.post('/examples/open', force ? { name, force: true } : { name })"),
        ("async function importFile(file, asked)",
         "api.upload('/import/json', file, 'file', force ? { force: 'true' } : null)"),
    ):
        text = _function(src, header)
        assert "await replaceDocument(" in text and call in text, header
        assert text.index("leaveDocument('open')") < text.index("await replaceDocument("), header
        assert "if (!payload) return;" in text
    # nothing else in the page posts to these three
    for path in ("'/file/open'", "'/examples/open'", "'/import/json'"):
        assert src.count("api.post(" + path) + src.count("api.upload(" + path) == 1, path


# =============================================================================================
# 4: Stop frees the AI slot
# =============================================================================================
#
# The provider is a fake that waits on a threading.Event, patched onto the
# provider singleton as test_api_ai.py does. Nothing here reaches a network.

import threading  # noqa: E402

from ai_providers import AIProviderFactory  # noqa: E402

API_KEY = "sk-testkeyDONOTLEAK0123456789abcdefAB12"
PROVIDER_NAME = "OpenAI"


class Blocked:
    """A provider call that waits, so the test can act while it is out."""

    def __init__(self, text):
        self.text = text
        self.inside = threading.Event()
        self.release = threading.Event()
        self.returned = threading.Event()
        self.calls = 0

    def __call__(self, api_key, endpoint, model, messages, max_tokens=2000):
        self.calls += 1
        self.inside.set()
        self.release.wait(10)
        self.returned.set()
        return self.text, None


def _replies(text):
    def send_message(api_key, endpoint, model, messages, max_tokens=2000):
        return text, None

    return send_message


def _in_background(app, url, payload=None):
    outcome = {}

    def run():
        with app.test_client() as other:
            outcome["response"] = other.post(url, json=payload)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, outcome


def _settled(blocked, timeout=5.0):
    """Wait until the abandoned worker has run to its end: the provider
    returned and the handler has written down whatever it writes down."""
    assert blocked.returned.wait(timeout)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(t.name.startswith("ai-") and t.is_alive() for t in threading.enumerate()):
            return
        time.sleep(0.01)
    raise AssertionError("the abandoned worker never finished")


SUGGESTION = (
    "SUGGESTION: Add corrosion\nDESCRIPTION: missing root cause.\n"
    "ACTION: add\nTARGET: root\n"
    'DATA: {"id": "corrosion", "name": "Corrosion", "type": "Event", '
    '"probability": 0.05, "notes": "late"}\n'
)


@pytest.fixture
def provider():
    return AIProviderFactory.get_provider(PROVIDER_NAME)


@pytest.fixture
def ai(app, client, provider, monkeypatch):
    """The client, with credentials saved through the real save path (into
    tmp_path: see per_user_home) and a fresh handler."""
    ai_bridge.reset_handler()
    monkeypatch.setattr(provider, "test_connection", lambda *a, **k: (True, "ok"))
    saved = client.post("/api/ai/credentials", json={"provider": PROVIDER_NAME, "apiKey": API_KEY})
    assert saved.status_code == 200, body(saved)
    yield client
    deadline = time.monotonic() + 5.0
    while ai_bridge._call_slot.locked() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not ai_bridge._call_slot.locked(), "an AI call slot was left held"


def _conversation(client):
    return body(client.get("/api/ai/conversation"))


def test_4_stop_frees_the_slot_and_the_late_answer_is_dropped(app, ai, provider, monkeypatch):
    # an earlier turn, which must survive the cancel
    monkeypatch.setattr(provider, "send_message", _replies("First answer."))
    assert ai.post("/api/ai/chat", json={"message": "first"}).status_code == 200
    before = _conversation(ai)
    assert [m["content"] for m in before["messages"]] == ["first", "First answer."]
    tree_before = state_of(ai)

    blocked = Blocked("Too late. " + SUGGESTION)
    monkeypatch.setattr(provider, "send_message", blocked)
    thread, outcome = _in_background(app, "/api/ai/chat", {"message": "second", "requestId": "req-2"})
    try:
        assert blocked.inside.wait(5), "the provider was never reached"
        # the slot is taken: as before, a second request is refused
        busy = ai.post("/api/ai/chat", json={"message": "impatient"})
        assert busy.status_code == 409 and error(busy)["code"] == "AI_BUSY"

        cancelled = ai.post("/api/ai/cancel", json={"requestId": "req-2"})
        assert cancelled.status_code == 200 and body(cancelled)["cancelled"] is True

        # the request that was waiting is answered now, with its own refusal
        thread.join(5)
        assert not thread.is_alive(), "the abandoned request kept waiting"
        assert outcome["response"].status_code == 409
        assert error(outcome["response"])["code"] == "AI_CANCELLED"

        # and the next one is accepted at once, while the provider still has
        # not answered the abandoned one
        assert not blocked.returned.is_set()
        monkeypatch.setattr(provider, "send_message", _replies("Third answer."))
        third = ai.post("/api/ai/chat", json={"message": "third"})
        assert third.status_code == 200 and body(third)["reply"] == "Third answer."
    finally:
        blocked.release.set()
    _settled(blocked)

    # the late answer is nowhere: not in the conversation, not a suggestion
    after = _conversation(ai)
    assert [m["content"] for m in after["messages"]] == ["first", "First answer.", "third", "Third answer."]
    assert after["changes"] == [] and after["pendingUpdate"] is None
    assert "Too late" not in json.dumps(after)
    # and the document is as it was
    now = state_of(ai)
    assert now["tree"] == tree_before["tree"] and now["revision"] == tree_before["revision"]
    assert now["dirty"] is False


def test_4_a_late_update_is_never_installed_and_leaves_no_preview(app, ai, provider, monkeypatch):
    add(ai, name="Pump fails", probability=0.01)
    held = state_of(ai)
    rewritten = copy.deepcopy(held["tree"])
    rewritten["children"][0]["name"] = "REWRITTEN BY THE MODEL"
    for preview in (True, False):
        blocked = Blocked(json.dumps(rewritten))
        monkeypatch.setattr(provider, "send_message", blocked)
        payload = {"preview": preview, "requestId": "upd"} if preview else {"requestId": "upd"}
        thread, outcome = _in_background(app, "/api/ai/update", payload)
        try:
            assert blocked.inside.wait(5)
            assert body(ai.post("/api/ai/cancel", json={"requestId": "upd"}))["cancelled"] is True
            thread.join(5)
            assert error(outcome["response"])["code"] == "AI_CANCELLED"
        finally:
            blocked.release.set()
        _settled(blocked)
        now = state_of(ai)
        assert now["tree"] == held["tree"] and now["revision"] == held["revision"], preview
        assert "REWRITTEN" not in json.dumps(now)
        assert _conversation(ai)["pendingUpdate"] is None
        assert _conversation(ai)["messages"] == []
        # nothing is waiting to be applied
        assert error(ai.post("/api/ai/update/apply", json={"id": "x"}))["code"] == "AI_UPDATE_EXPIRED"


def test_4_suggestions_and_the_conversation_from_before_are_kept(app, ai, provider, monkeypatch):
    pump = add(ai, name="Pump fails", probability=0.01)
    monkeypatch.setattr(provider, "send_message", _replies(
        "SUGGESTION: Revise\nDESCRIPTION: field data.\nACTION: edit\nTARGET: %s\n"
        'DATA: {"id": "%s", "name": "Pump fails", "probability": 0.2}\n' % (pump, pump)))
    first = body(ai.post("/api/ai/chat", json={"message": "review"}))
    assert len(first["changes"]) == 1
    index = first["changes"][0]["index"]

    blocked = Blocked(SUGGESTION)
    monkeypatch.setattr(provider, "send_message", blocked)
    thread, _outcome = _in_background(app, "/api/ai/analyze", {"requestId": "a"})
    try:
        assert blocked.inside.wait(5)
        assert body(ai.post("/api/ai/cancel", json={}))["cancelled"] is True
        thread.join(5)
    finally:
        blocked.release.set()
    _settled(blocked)

    kept = _conversation(ai)
    assert [c["index"] for c in kept["changes"]] == [index], "the earlier suggestion still waits"
    assert "corrosion" not in json.dumps(kept).lower()
    # ... and can still be applied, to the document it was made for
    applied = ai.post("/api/ai/changes/apply", json={"indices": [index]})
    assert applied.status_code == 200 and len(body(applied)["applied"]) == 1
    assert body(applied)["tree"]["children"][0]["probability"] == 0.2


def test_4_cancel_names_its_request(app, ai, provider, monkeypatch):
    blocked = Blocked("Answer.")
    monkeypatch.setattr(provider, "send_message", blocked)
    thread, outcome = _in_background(app, "/api/ai/chat", {"message": "hello", "requestId": "mine"})
    try:
        assert blocked.inside.wait(5)
        # Stop for another request (a tab whose own request has finished)
        other = ai.post("/api/ai/cancel", json={"requestId": "somebody-else"})
        assert other.status_code == 200 and body(other)["cancelled"] is False
        assert ai_bridge._call_slot.locked()
    finally:
        blocked.release.set()
    thread.join(5)
    # the request went through untouched
    assert outcome["response"].status_code == 200 and body(outcome["response"])["reply"] == "Answer."
    assert [m["content"] for m in _conversation(ai)["messages"]] == ["hello", "Answer."]


def test_4_cancel_with_nothing_in_flight_is_not_an_error(client):
    """Also unconfigured: no credentials, no handler, nothing created."""
    answer = client.post("/api/ai/cancel", json={})
    assert answer.status_code == 200 and body(answer) == {"ok": True, "cancelled": False}
    assert client.post("/api/ai/cancel").status_code == 200
    assert ai_bridge.existing_handler() is None
    for bad in (5, "", "x" * 65, ["a"]):
        refused = client.post("/api/ai/cancel", json={"requestId": bad})
        assert refused.status_code == 400 and error(refused)["detail"] == {"field": "requestId"}


def test_4_a_request_that_timed_out_can_be_abandoned_too(app, ai, provider, monkeypatch):
    """Before: after a timeout the slot stayed taken until the provider
    answered, and the only way out was to restart the editor."""
    blocked = Blocked("Too late.")
    monkeypatch.setattr(provider, "send_message", blocked)
    monkeypatch.setattr(config, "AI_TIMEOUT_SECONDS", 0.2, raising=False)
    try:
        timed_out = ai.post("/api/ai/chat", json={"message": "slow"})
        assert timed_out.status_code == 504 and error(timed_out)["code"] == "AI_TIMEOUT"
        assert error(ai.post("/api/ai/chat", json={"message": "again"}))["code"] == "AI_BUSY"
        assert body(ai.post("/api/ai/cancel", json={}))["cancelled"] is True
        monkeypatch.setattr(provider, "send_message", _replies("Here."))
        assert body(ai.post("/api/ai/chat", json={"message": "again"}))["reply"] == "Here."
    finally:
        blocked.release.set()
    _settled(blocked)
    assert [m["content"] for m in _conversation(ai)["messages"]] == ["again", "Here."]


def test_4_a_conversation_cleared_during_the_request_stays_cleared(app, ai, provider, monkeypatch):
    monkeypatch.setattr(provider, "send_message", _replies("First answer."))
    ai.post("/api/ai/chat", json={"message": "first"})
    blocked = Blocked("Too late.")
    monkeypatch.setattr(provider, "send_message", blocked)
    thread, _outcome = _in_background(app, "/api/ai/chat", {"message": "second"})
    try:
        assert blocked.inside.wait(5)
        assert ai.delete("/api/ai/conversation").status_code == 200
        assert body(ai.post("/api/ai/cancel", json={}))["cancelled"] is True
        thread.join(5)
    finally:
        blocked.release.set()
    _settled(blocked)
    assert _conversation(ai)["messages"] == []


def test_4_the_page_sends_the_cancel_with_the_request_it_stopped():
    src = _read(STATIC / "chat.js")
    stop = _function(src, "function actionStop()")
    assert stop.index("say('system', 'ai.msg.stopped')") < stop.index("api.post('/ai/cancel', { requestId: job.id })")
    assert "say('system', 'ai.msg.stopNotFreed')" in stop
    run = _function(src, "async function run(statusText, work, hooks)")
    assert "id: newRequestId()" in run
    for call in ("api.post('/ai/chat', { message: text, requestId: job.id })",
                 "api.post('/ai/analyze', { requestId: job.id })",
                 "api.post('/ai/update', { preview: true, requestId: job.id })"):
        assert call in src, call
    for catalog, key in (("ux3.js", "ai.msg.stopped"), ("fix181.js", "ai.msg.stopNotFreed")):
        text = _read(STATIC / "i18n" / catalog)
        assert text.count("'%s':" % key) == 2, "en and ja"
    assert "may be refused as busy" not in _read(STATIC / "i18n" / "ux3.js")
