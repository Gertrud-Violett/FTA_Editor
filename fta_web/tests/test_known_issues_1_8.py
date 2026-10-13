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
    # the other tab's work is read and shown before the question is asked
    assert (replace.index("await reloadFromServer();") < replace.index("store.applyMutation({ dirty: true });")
            < replace.index("leaveDocument('open')"))
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


# =============================================================================================
# 5: the recovery copy
# =============================================================================================
#
# The folder is tmp_path/fta_editor_home/recovery (see per_user_home). No
# test here depends on the writer thread's timing except the one that is
# about that thread, and it shortens the two delays.

import os  # noqa: E402
import re  # noqa: E402

from fta_web import recovery  # noqa: E402


@pytest.fixture(autouse=True)
def _no_recovery_session_is_left():
    """Whatever a test does, the next one starts without a session."""
    yield
    recovery.end_session()


@pytest.fixture
def recovering(app, per_user_home):
    """Recovery started for this test without the background thread: the
    copy is written by recovery.flush()."""
    assert recovery.session_id() is None
    session = recovery.start(background=False)
    assert session and recovery.directory() == per_user_home / "recovery"
    yield session
    recovery.end_session()


def _copy_files(folder, session):
    return sorted(p.name for p in folder.iterdir() if p.name.startswith(session))


def _leave_a_copy(client, per_user_home, title="Pump station", save_to=None):
    """Run a session that ends without saving, as a crash does: its copy
    and sidecar stay, and its lock is gone. Returns the session id."""
    session = recovery.start(background=False)
    client.post("/api/new", json={"force": True})
    client.post("/api/metadata", json={"title": title})
    add(client, name="unsaved event", probability=0.25)
    if save_to is not None:
        assert client.post("/api/file/save-as", json={"path": str(save_to)}).status_code == 200
        add(client, name="after the save", probability=0.5)
    assert recovery.flush() is True
    # the crash: no end_session(). The process is gone, and with it the lock.
    current = recovery._session
    recovery._unlock_handle(current.lock_file)
    current.lock_file.close()
    recovery.state_module.remove_document_listener(recovery._on_document_event)
    recovery._session = None
    client.post("/api/new", json={"force": True})
    return session


def test_5_nothing_is_written_unless_the_launcher_started_it(client, per_user_home):
    add(client, name="unsaved")
    assert recovery.session_id() is None and recovery.flush() is False
    assert not (per_user_home / "recovery").exists()
    assert body(client.get("/api/recovery")) == {"ok": True, "copies": []}
    # the launcher is what starts it, and it ends it on the way out
    launcher = _read(REPO / "fta_web" / "run.py")
    assert launcher.index("recovery.start()") < launcher.index("app.run(")
    assert "finally:" in launcher and "recovery.end_session()" in launcher
    assert '"recovery",' in _read(REPO / "build" / "fta_editor.spec")


def test_5_the_copy_is_what_save_writes_with_a_sidecar_and_never_a_credential(
        client, sandbox, per_user_home, recovering):
    folder = per_user_home / "recovery"
    assert _copy_files(folder, recovering) == [recovering + ".lock"], "nothing unsaved yet"

    client.post("/api/metadata", json={"title": "Pump station"})
    add(client, name="Seal leaks", probability=0.02)
    assert recovery.flush() is True
    assert _copy_files(folder, recovering) == [
        recovering + ".json", recovering + ".lock", recovering + ".meta.json"]

    # byte for byte the file Save writes
    saved = sandbox / "saved.json"
    document = (folder / (recovering + ".json")).read_bytes()
    assert client.post("/api/file/save-as", json={"path": str(saved)}).status_code == 200
    assert document == saved.read_bytes()


def test_5_the_sidecar_names_the_title_the_original_path_and_the_time(
        client, sandbox, per_user_home, recovering):
    folder = per_user_home / "recovery"
    saved = sandbox / "station.json"
    client.post("/api/metadata", json={"title": "Pump station"})
    assert client.post("/api/file/save-as", json={"path": str(saved)}).status_code == 200
    add(client, name="after the save")
    assert recovery.flush() is True
    meta = json.loads((folder / (recovering + ".meta.json")).read_text("utf-8"))
    assert set(meta) == {"version", "session", "title", "originalPath", "savedAt"}
    assert meta["title"] == "Pump station" and meta["session"] == recovering
    assert meta["originalPath"] == str(saved.resolve())
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", meta["savedAt"])
    # the copy did not become the document's file, and did not touch its date
    assert state_of(client)["currentPath"] == str(saved.resolve())
    assert get_state().core.last_saved_file == str(saved.resolve())
    # no credential anywhere in the folder (one is saved in this home)
    AICredentialManager().save_credentials(API_KEY, "https://api.openai.com/v1", "gpt-4o", "OpenAI")
    assert (per_user_home / "ai_credentials.json").exists()
    add(client, name="once more")
    recovery.flush()
    for path in folder.iterdir():
        if path.suffix != ".lock":  # held locked by the session; one NUL byte
            assert API_KEY not in path.read_text("utf-8", errors="replace"), path.name


def test_5_the_copy_goes_with_save_new_and_open(client, sandbox, per_user_home, recovering):
    folder = per_user_home / "recovery"
    copy_file = folder / (recovering + ".json")

    def dirty_copy():
        add(client, name="unsaved")
        assert recovery.flush() is True and copy_file.exists()

    dirty_copy()
    assert client.post("/api/file/save-as", json={"path": str(sandbox / "a.json")}).status_code == 200
    assert recovery.flush() is False and not copy_file.exists(), "Save As"

    dirty_copy()
    assert client.post("/api/file/save", json={}).status_code == 200
    assert recovery.flush() is False and not copy_file.exists(), "Save"

    dirty_copy()
    # refused: the work is still unsaved, and so the copy stays
    assert client.post("/api/new", json={}).status_code == 409
    assert recovery.flush() is True and copy_file.exists()
    assert client.post("/api/new", json={"force": True}).status_code == 200
    assert recovery.flush() is False and not copy_file.exists(), "New, after Discard"

    dirty_copy()
    opened = client.post("/api/file/open", json={"path": str(sandbox / "a.json"), "force": True})
    assert opened.status_code == 200
    assert recovery.flush() is False and not copy_file.exists(), "Open, after Discard"

    dirty_copy()
    client.post("/api/examples/open", json={"name": "sampleFTA.json", "force": True})
    assert recovery.flush() is False and not copy_file.exists(), "an example"
    assert not (folder / (recovering + ".meta.json")).exists()


def test_5_an_imported_document_is_unsaved_work_and_is_copied(client, per_user_home, recovering):
    import io

    upload = {"file": (io.BytesIO((EXAMPLES / "sampleFTA.json").read_bytes()), "mine.json")}
    assert client.post("/api/import/json", data=upload,
                       content_type="multipart/form-data").status_code == 200
    assert recovery._session.first_change is not None, "the writer was told"
    assert recovery.flush() is True
    meta = json.loads((per_user_home / "recovery" / (recovering + ".meta.json")).read_text("utf-8"))
    assert meta["originalPath"] is None


def test_5_a_clean_exit_leaves_nothing(client, per_user_home):
    session = recovery.start(background=False)
    add(client, name="unsaved")
    assert recovery.flush() is True
    recovery.end_session()
    assert list((per_user_home / "recovery").iterdir()) == []
    assert recovery.session_id() is None
    # and edits after it write nothing
    add(client, name="later")
    assert recovery.flush() is False and list((per_user_home / "recovery").iterdir()) == []
    assert session


def test_5_a_copy_from_a_session_that_did_not_end_cleanly_is_offered(client, sandbox, per_user_home):
    original = sandbox / "station.json"
    crashed = _leave_a_copy(client, per_user_home, save_to=original)
    on_disk = original.read_bytes()

    # the next start
    recovery.start(background=False)
    try:
        listed = body(client.get("/api/recovery"))["copies"]
        assert [c["id"] for c in listed] == [crashed]
        assert listed[0]["title"] == "Pump station"
        assert listed[0]["originalPath"] == str(original.resolve())
        assert set(listed[0]) == {"id", "title", "savedAt", "originalPath"}, "no server path of the copy"

        restored = client.post("/api/recovery/restore", json={"id": crashed})
        assert restored.status_code == 200, body(restored)
        answer = body(restored)
        # untitled and modified: Save goes to Save As, never over the original
        assert answer["currentPath"] is None and answer["dirty"] is True
        assert answer["restoredFrom"]["title"] == "Pump station"
        names = [c["name"] for c in answer["tree"]["children"]]
        assert names == ["unsaved event", "after the save"]
        assert client.post("/api/file/save", json={}).status_code == 409
        assert error(client.post("/api/file/save", json={}))["code"] == "NO_CURRENT_PATH"
        assert original.read_bytes() == on_disk, "the original file is untouched"
        assert get_state().core.last_saved_file is None

        # the copy that was restored is gone, and this session has its own
        assert body(client.get("/api/recovery"))["copies"] == []
        own = recovery.session_id()
        assert _copy_files(per_user_home / "recovery", crashed) == []
        assert (per_user_home / "recovery" / (own + ".json")).exists()
    finally:
        recovery.end_session()


def test_5_discard_removes_the_copy_and_nothing_else(client, per_user_home):
    first = _leave_a_copy(client, per_user_home, title="First")
    second = _leave_a_copy(client, per_user_home, title="Second")
    listed = body(client.get("/api/recovery"))["copies"]
    assert {c["id"] for c in listed} == {first, second}

    before = state_of(client)
    gone = client.post("/api/recovery/discard", json={"id": first})
    assert gone.status_code == 200 and body(gone)["discarded"] is True
    assert [c["id"] for c in body(client.get("/api/recovery"))["copies"]] == [second]
    assert _copy_files(per_user_home / "recovery", first) == []
    assert state_of(client)["revision"] == before["revision"], "the document is not touched"
    # twice is 404, not an error that removes something else
    assert client.post("/api/recovery/discard", json={"id": first}).status_code == 404
    assert [c["id"] for c in body(client.get("/api/recovery"))["copies"]] == [second]


def test_5_restore_does_not_replace_unsaved_work_without_the_flag(client, per_user_home):
    crashed = _leave_a_copy(client, per_user_home)
    add(client, name="typed since the start")
    refused = client.post("/api/recovery/restore", json={"id": crashed})
    assert refused.status_code == 409 and error(refused)["code"] == "UNSAVED_CHANGES"
    assert [c["id"] for c in body(client.get("/api/recovery"))["copies"]] == [crashed], "the copy stays"
    assert client.post("/api/recovery/restore", json={"id": crashed, "force": "true"}).status_code == 400
    assert client.post("/api/recovery/restore", json={"id": crashed, "force": True}).status_code == 200


def test_5_the_id_is_looked_up_in_the_listing_and_is_never_a_path(client, sandbox, per_user_home):
    crashed = _leave_a_copy(client, per_user_home)
    folder = per_user_home / "recovery"
    secret = sandbox / "secret.json"
    secret.write_bytes((EXAMPLES / "sampleFTA.json").read_bytes())
    planted = folder / "notes.json"            # a .json in the folder that is not a copy
    planted.write_bytes(secret.read_bytes())
    (folder / "notes.meta.json").write_text('{"title": "x"}', encoding="utf-8")
    before = state_of(client)

    hostile = [
        str(secret), str(folder / (crashed + ".json")), crashed + ".json", "../" + crashed,
        "..\\" + crashed, crashed + "/", "notes", "notes.json", crashed.upper(), crashed + "\x00",
        "0" * 16, "", " " + crashed, str(per_user_home / "ai_credentials.json"),
    ]
    for value in hostile:
        for route in ("/api/recovery/restore", "/api/recovery/discard"):
            answer = client.post(route, json={"id": value, "force": True})
            assert answer.status_code in (400, 404), (route, value)
            assert value == "" or value not in answer.get_data(as_text=True), "never echoed"
    for value in (None, 5, ["a"], {"id": crashed}):
        assert client.post("/api/recovery/restore", json={"id": value}).status_code == 400
    assert client.post("/api/recovery/restore", json={}).status_code == 400
    # a path in the body is not an id and opens nothing
    assert client.post("/api/recovery/restore", json={"path": str(secret)}).status_code == 400

    assert state_of(client)["revision"] == before["revision"]
    assert planted.exists() and secret.exists() and (folder / (crashed + ".json")).exists()
    assert [c["id"] for c in body(client.get("/api/recovery"))["copies"]] == [crashed]


def test_5_the_copy_of_an_editor_that_is_still_running_is_not_offered(client, per_user_home):
    """A second copy of the editor must not offer, restore, discard or prune
    the unsaved work of the first."""
    recovery.start(background=False)
    try:
        add(client, name="in the first editor")
        assert recovery.flush() is True
        first = recovery.session_id()
        # What a second process sees: the same folder, and a lock it does
        # not hold. (Its own session is another one, or none.)
        current, recovery._session = recovery._session, None
        try:
            assert recovery._session_is_live(first) is True
            assert recovery.abandoned() == {}
            assert body(client.get("/api/recovery"))["copies"] == []
            assert client.post("/api/recovery/restore", json={"id": first, "force": True}).status_code == 404
            assert client.post("/api/recovery/discard", json={"id": first}).status_code == 404
            recovery.prune()
        finally:
            recovery._session = current
        assert len(_copy_files(per_user_home / "recovery", first)) == 3
    finally:
        recovery.end_session()


def test_5_only_a_few_copies_are_kept(client, per_user_home, monkeypatch):
    monkeypatch.setattr(recovery, "MAX_COPIES", 3)
    made = []
    for n in range(5):
        made.append(_leave_a_copy(client, per_user_home, title="Copy %d" % n))
        # distinct, increasing times (the listing is newest first)
        for path in (per_user_home / "recovery").glob(made[-1] + ".*"):
            os.utime(path, (1_700_000_000 + n * 100, 1_700_000_000 + n * 100))
    # each start pruned what was there before it; the last one is still to come
    assert len(recovery.abandoned()) == 4
    recovery.start(background=False)   # start-up prunes
    try:
        kept = [c["title"] for c in body(client.get("/api/recovery"))["copies"]]
        assert kept == ["Copy 4", "Copy 3", "Copy 2"]
        for gone in made[:2]:
            assert _copy_files(per_user_home / "recovery", gone) == []
    finally:
        recovery.end_session()


def test_5_a_document_over_the_size_cap_is_not_copied(client, per_user_home, recovering, monkeypatch):
    add(client, name="unsaved")
    assert recovery.flush() is True
    monkeypatch.setattr(recovery, "MAX_COPY_BYTES", 10)
    add(client, name="more")
    assert recovery.flush() is False
    assert _copy_files(per_user_home / "recovery", recovering) == [recovering + ".lock"]
    # ... and a file of that size left in the folder is not offered either
    monkeypatch.setattr(recovery, "MAX_COPY_BYTES", config.MAX_UPLOAD_BYTES)


def test_5_the_folder_is_the_per_user_one_whatever_the_root_is(client, sandbox, per_user_home, recovering):
    """Fixed: not derived from the sandbox root or from the document."""
    saved = sandbox / "deep.json"
    client.post("/api/file/save-as", json={"path": str(saved)})
    add(client, name="unsaved")
    assert recovery.flush() is True
    assert recovery.directory() == per_user_home / "recovery"
    assert [p.name for p in sandbox.iterdir()] == ["deep.json"], "nothing beside the document"
    # in this test's layout it is outside the root, and no file endpoint reaches it
    copy_path = per_user_home / "recovery" / (recovering + ".json")
    assert not fsbrowser_within(sandbox, copy_path)
    refused = client.post("/api/file/open", json={"path": str(copy_path), "force": True})
    assert error(refused)["detail"]["reason"] == "outside_root"


def fsbrowser_within(root, path):
    from fta_web import fsbrowser

    return fsbrowser.is_within(Path(root).resolve(), Path(path).resolve())


def test_5_the_writer_waits_for_quiet_but_not_for_ever(client, per_user_home, monkeypatch):
    """The background thread: a burst of edits is one write after the quiet
    period; edits that never stop are written at the latest after the
    maximum wait; a save removes the copy without waiting."""
    monkeypatch.setattr(recovery, "DEBOUNCE_SECONDS", 0.25)
    monkeypatch.setattr(recovery, "MAX_WAIT_SECONDS", 1.0)
    writes = []
    real = recovery._sync
    monkeypatch.setattr(recovery, "_sync", lambda session: writes.append(time.monotonic()) or real(session))
    session = recovery.start()
    copy_file = per_user_home / "recovery" / (session + ".json")
    try:
        def wait_for(condition, seconds=5.0):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                if condition():
                    return True
                time.sleep(0.02)
            return False

        # a burst: three edits within the quiet period are one write
        for n in range(3):
            add(client, name="burst %d" % n)
        assert not copy_file.exists(), "not written while the edits are coming"
        assert wait_for(copy_file.exists)
        time.sleep(0.4)
        assert len(writes) == 1, writes
        assert "burst 2" in copy_file.read_text("utf-8")

        # edits that never stop: written anyway, about every MAX_WAIT_SECONDS
        writes.clear()
        started = time.monotonic()
        while time.monotonic() - started < 1.6:
            client.post("/api/metadata", json={"title": "t %f" % time.monotonic()})
            time.sleep(0.05)
        assert 1 <= len(writes) <= 2, writes
        assert writes[0] - started >= 0.9, "not before the maximum wait"

        # a save removes the copy at once
        assert wait_for(copy_file.exists)
        client.post("/api/file/save-as", json={"path": str(get_state().fs_root / "s.json")})
        assert wait_for(lambda: not copy_file.exists(), 2.0)
    finally:
        recovery.end_session()
    assert list((per_user_home / "recovery").iterdir()) == []
    assert not any(t.name == "recovery-writer" and t.is_alive() for t in threading.enumerate())


def test_5_the_page_offers_the_copy_on_the_first_run_screen():
    html = _read(REPO / "fta_web" / "templates" / "index.html")
    assert 'id="recovery-offer"' in html and 'id="recovery-restore"' in html and 'id="recovery-discard"' in html
    assert html.index('id="recovery-offer"') < html.index('id="first-run"'), "above the Start here hint"
    src = _read(STATIC / "main.js")
    offer = _function(src, "async function refreshRecoveryOffer()")
    assert "api.get('/recovery')" in offer
    restore = _function(src, "async function actionRestoreRecovery()")
    assert restore.index("leaveDocument('open')") < restore.index("await replaceDocument(")
    assert "api.post('/recovery/restore', force ? { id, force: true } : { id })" in restore
    discard = _function(src, "async function actionDiscardRecovery()")
    assert "askConfirm(" in discard and "api.post('/recovery/discard', { id })" in discard
    catalog = _read(STATIC / "i18n" / "fix181.js")
    for key in ("recovery.offer", "recovery.restore", "recovery.discard", "recovery.restored",
                "recovery.discardConfirm"):
        assert catalog.count("'%s':" % key) == 2, key
    assert "Restore unsaved work from {date} ({title})" in catalog and "Discard it" in catalog


# =============================================================================================
# 6: choosing the allowed folder while the editor runs
# =============================================================================================
#
# The native dialog is never opened here: folder_picker.pick (or the helper
# process under it) is replaced by a function in every test, and an autouse
# fixture fails any test that would reach the real one.

import base64  # noqa: E402

from fta_web import folder_picker, fsbrowser, user_prefs  # noqa: E402


@pytest.fixture(autouse=True)
def _no_native_dialog(monkeypatch):
    """No test in this file may start the helper process that shows a
    dialog. A test that wants an answer replaces this again."""

    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to open the native folder dialog")

    monkeypatch.setattr(folder_picker, "_start_helper", refuse)


class FakePicker:
    """Stands in for the person at the dialog: ``answer`` is the folder they
    pick (None: they close it)."""

    def __init__(self, answer):
        self.answer = answer
        self.started_in = []

    def __call__(self, start=None):
        self.started_in.append(start)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def other(tmp_path):
    folder = tmp_path / "other folder"
    folder.mkdir()
    return folder


def _choose(client, monkeypatch, answer, **request):
    picker = FakePicker(answer)
    monkeypatch.setattr(folder_picker, "pick", picker)
    return client.post("/api/fs/root/choose", **request), picker


def test_6_the_folder_the_person_picks_becomes_the_root(client, sandbox, other, monkeypatch):
    inside_new = other / "tree.json"
    inside_new.write_bytes((EXAMPLES / "sampleFTA.json").read_bytes())
    assert client.post("/api/file/open", json={"path": str(inside_new)}).status_code == 400

    answer, picker = _choose(client, monkeypatch, str(other))
    assert answer.status_code == 200, body(answer)
    got = body(answer)
    assert got["changed"] is True and got["cancelled"] is False
    assert got["root"] == str(other.resolve())
    assert picker.started_in == [str(sandbox.resolve())], "the dialog starts in the current root"
    assert Path(get_state().fs_root) == other.resolve()
    home = body(client.get("/api/fs/home"))
    assert home["root"] == str(other.resolve()) and home["cwd"] == str(other.resolve())

    # the boundary moved, it did not go: the new folder is readable ...
    assert client.post("/api/file/open", json={"path": str(inside_new)}).status_code == 200
    # ... and the old one is outside now
    old = _sample(sandbox, "old.json")
    refused = client.post("/api/file/open", json={"path": str(old), "force": True})
    assert error(refused)["detail"]["reason"] == "outside_root"
    assert error(refused)["detail"]["root"] == str(other.resolve())


PATHS_IN_A_REQUEST = [
    {"json": {"path": "PLACEHOLDER"}},
    {"json": {"root": "PLACEHOLDER"}},
    {"json": {"folder": "PLACEHOLDER", "force": True}},
    {"json": {"anything": 1}},
    {"json": ["PLACEHOLDER"]},
    {"json": "PLACEHOLDER"},
    {"data": b"null", "content_type": "application/json"},
    {"data": b"{} x", "content_type": "application/json"},
    {"data": "PLACEHOLDER", "content_type": "text/plain"},
    {"data": b"{\"path\": \"PLACEHOLDER\"}", "content_type": "text/plain"},
    {"data": {"path": "PLACEHOLDER"}, "content_type": "multipart/form-data"},
    {"data": {"path": "PLACEHOLDER"}, "content_type": "application/x-www-form-urlencoded"},
    {"query_string": {"path": "PLACEHOLDER"}},
    {"query_string": {"root": "PLACEHOLDER"}, "json": {}},
    {"data": b"\xff\xfe", "content_type": "application/json"},
]


@pytest.mark.parametrize("request_", PATHS_IN_A_REQUEST)
def test_6_a_path_in_the_request_cannot_change_the_root(client, sandbox, other, monkeypatch, request_):
    """The security property of this endpoint. Whatever a request carries,
    it is refused before any dialog is opened, and the root stays."""

    def fill(value):
        if isinstance(value, dict):
            return {key: fill(item) for key, item in value.items()}
        if isinstance(value, list):
            return [fill(item) for item in value]
        if isinstance(value, bytes):
            return value.replace(b"PLACEHOLDER", str(other).replace("\\", "\\\\").encode("utf-8"))
        return str(other) if value == "PLACEHOLDER" else value

    # Even with a person who would pick that very folder: the request is
    # refused first, so the dialog never opens.
    answer, picker = _choose(client, monkeypatch, str(other), **fill(request_))
    assert answer.status_code == 400, (request_, body(answer))
    assert error(answer)["code"] == "INVALID_FIELD" and error(answer)["detail"] == {"field": "body"}
    assert picker.started_in == [], "no dialog was opened"
    assert Path(get_state().fs_root) == sandbox
    assert body(client.get("/api/fs/home"))["root"] == str(sandbox.resolve())
    assert str(other) not in answer.get_data(as_text=True), "nothing of the input is echoed"
    assert client.get("/api/fs/list", query_string={"path": str(other)}).status_code == 400


def test_6_an_empty_request_is_the_only_one_taken(client, sandbox, other, monkeypatch):
    for request_ in ({}, {"json": {}}, {"data": b"", "content_type": "application/json"},
                     {"data": b"  {}  ", "content_type": "application/json"},
                     {"query_string": {"lang": "ja"}}):
        get_state().fs_root = sandbox
        answer, picker = _choose(client, monkeypatch, str(other), **request_)
        assert answer.status_code == 200 and len(picker.started_in) == 1, request_


def test_6_no_other_request_reaches_the_root(client, sandbox, other):
    """Nothing but the dialog's answer is ever assigned to the root."""
    routes = {rule.rule for rule in client.application.url_map.iter_rules()}
    assert {rule for rule in routes if "root" in rule} == {"/api/fs/root/choose"}
    assert "fs_root" not in _read(REPO / "fta_web" / "user_prefs.py")
    assignments = {}
    for path in (REPO / "fta_web").rglob("*.py"):
        if "tests" in path.parts or ".venv" in path.parts or "build" in path.parts:
            continue
        hits = [line.strip() for line in _read(path).splitlines()
                if re.match(r"^(?:[\w()]+\.)*fs_root(?::\s*[\w.\[\]]+)?\s*=[^=]", line.strip())]
        if hits:
            assignments[path.name] = hits
    assert assignments == {
        # the default, in AppState.__init__
        "state.py": ["self.fs_root: Path = Path(config.DEFAULT_FS_ROOT)"],
        # --root (or the default) at start-up
        "run.py": ["fs_root = _resolve_root(args.root) if args.root else config.DEFAULT_FS_ROOT"],
        "app.py": ["fs_root: Path = None,"],
        "files.py": [
            # create_app's fs_root, once, at registration
            "get_state().fs_root = Path(root)",
            # the answer of the dialog
            "state.fs_root = new_root",
        ],
    }, assignments
    # /api/prefs cannot store one either
    stored = client.post("/api/prefs", json={"fsRoot": str(other), "lastFolder": str(other)})
    assert Path(get_state().fs_root) == sandbox and stored.status_code in (200, 400)
    assert user_prefs.last_folder() is None


def test_6_cancel_changes_nothing(client, sandbox, monkeypatch):
    opened = _sample(sandbox)
    client.post("/api/file/open", json={"path": str(opened)})
    add(client, name="unsaved")
    before = state_of(client)
    answer, picker = _choose(client, monkeypatch, None)
    assert answer.status_code == 200
    assert body(answer) == {"ok": True, "changed": False, "cancelled": True, "root": str(sandbox.resolve())}
    assert len(picker.started_in) == 1
    after = state_of(client)
    assert Path(get_state().fs_root) == sandbox
    assert (after["currentPath"], after["dirty"], after["revision"], after["tree"]) == (
        before["currentPath"], before["dirty"], before["revision"], before["tree"])


def test_6_the_choice_is_normalised_like_the_root_option(client, sandbox, other, tmp_path, monkeypatch, launcher):
    (other / "sub").mkdir()
    spellings = [
        str(other) + os.sep,
        str(other / "sub" / ".."),
        str(other / "." / "sub" / ".." / "."),
        str(other).replace("\\", "/"),
    ]
    if os.name == "nt":
        spellings.append(str(other).upper())
    for spelling in spellings:
        get_state().fs_root = sandbox
        answer, _picker = _choose(client, monkeypatch, spelling)
        assert answer.status_code == 200, spelling
        # exactly what `--root <spelling>` gives at start-up
        assert Path(body(answer)["root"]) == launcher._resolve_root(spelling), spelling
        assert Path(get_state().fs_root) == launcher._resolve_root(spelling)

    # "~" is expanded by both
    monkeypatch.setenv("HOME", str(other))
    monkeypatch.setenv("USERPROFILE", str(other))
    get_state().fs_root = sandbox
    answer, _picker = _choose(client, monkeypatch, "~")
    assert Path(body(answer)["root"]) == launcher._resolve_root("~") == other.resolve()

    # what --root refuses is refused here, and the root stays
    get_state().fs_root = sandbox
    a_file = other / "file.txt"
    a_file.write_text("x", encoding="utf-8")
    for bad in (str(other / "gone"), str(a_file)):
        with pytest.raises(SystemExit):
            launcher._resolve_root(bad)
        answer, _picker = _choose(client, monkeypatch, bad)
        assert answer.status_code == 400 and error(answer)["code"] == "PATH_REJECTED"
        assert error(answer)["detail"]["reason"] == "not_a_directory"
        assert Path(get_state().fs_root) == sandbox
        assert bad not in answer.get_data(as_text=True)


@pytest.mark.skipif(os.name == "nt", reason="needs a symbolic link")
def test_6_a_link_that_is_chosen_is_resolved_as_for_the_root_option(client, sandbox, other, tmp_path,
                                                                 monkeypatch, launcher):
    link = tmp_path / "link"
    link.symlink_to(other, target_is_directory=True)
    answer, _picker = _choose(client, monkeypatch, str(link))
    assert Path(body(answer)["root"]) == other.resolve() == launcher._resolve_root(str(link))


def test_6_the_document_keeps_its_path_only_inside_the_new_root(client, sandbox, tmp_path, monkeypatch):
    project = sandbox / "project"
    project.mkdir()
    target = project / "tree.json"
    target.write_bytes((EXAMPLES / "sampleFTA.json").read_bytes())
    assert client.post("/api/file/open", json={"path": str(target)}).status_code == 200
    add(client, name="unsaved edit")
    before = state_of(client)

    # a narrower root that still holds the file: the path is kept
    answer, _picker = _choose(client, monkeypatch, str(project))
    got = body(answer)
    assert got["documentUntitled"] is False and got["currentPath"] == str(target.resolve())
    assert client.post("/api/file/save", json={}).status_code == 200
    assert "unsaved edit" in target.read_text("utf-8")

    # a root elsewhere: the document becomes untitled, and nothing of it is lost
    add(client, name="second edit")
    on_disk = target.read_bytes()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    answer, _picker = _choose(client, monkeypatch, str(elsewhere))
    got = body(answer)
    assert got["documentUntitled"] is True and got["currentPath"] is None and got["dirty"] is True
    after = state_of(client)
    assert after["currentPath"] is None and after["dirty"] is True
    assert after["tree"] == body(client.get("/api/state"))["tree"]
    names = [c["name"] for c in after["tree"]["children"]]
    assert "unsaved edit" in names and "second edit" in names
    assert after["canUndo"] is True and after["documentSerial"] == before["documentSerial"]
    # Save has nowhere to write: Save As, inside the new root
    assert error(client.post("/api/file/save", json={}))["code"] == "NO_CURRENT_PATH"
    assert target.read_bytes() == on_disk, "the file outside the new root is not written"
    assert get_state().core.last_saved_file is None
    kept = elsewhere / "kept.json"
    assert client.post("/api/file/save-as", json={"path": str(kept)}).status_code == 200
    assert "second edit" in kept.read_text("utf-8")


def test_6_the_remembered_folder_is_checked_against_the_new_root(client, sandbox, other, monkeypatch):
    sub = sandbox / "sub"
    sub.mkdir()
    target = _sample(sub, "inner.json")
    client.post("/api/file/open", json={"path": str(target)})
    client.post("/api/new", json={})
    assert user_prefs.last_folder() == str(sub.resolve())
    assert body(client.get("/api/fs/home"))["cwd"] == str(sub.resolve())

    _choose(client, monkeypatch, str(other))
    # the stored value is still the old folder, and it is no longer offered
    assert user_prefs.last_folder() == str(sub.resolve())
    home = body(client.get("/api/fs/home"))
    assert home["cwd"] == str(other.resolve()) == home["root"]
    # back to a root that holds it: offered again
    _choose(client, monkeypatch, str(sandbox))
    assert body(client.get("/api/fs/home"))["cwd"] == str(sub.resolve())


def test_6_only_one_dialog_at_a_time(app, client, sandbox, other, monkeypatch):
    opened, close = threading.Event(), threading.Event()
    starts = []

    def helper(name, start):
        starts.append(start)
        opened.set()
        close.wait(10)
        return str(other)

    monkeypatch.setattr(folder_picker, "_run_helper", helper)
    monkeypatch.setattr(folder_picker, "backend", lambda: ("powershell", ""))
    thread, outcome = _in_background(app, "/api/fs/root/choose")
    try:
        assert opened.wait(5)
        assert folder_picker.is_open()
        second = client.post("/api/fs/root/choose")
        assert second.status_code == 409 and error(second)["code"] == "PICKER_BUSY"
        assert Path(get_state().fs_root) == sandbox, "still the old root while the dialog is open"
        # the editor is not held while the dialog is open
        assert client.get("/api/state").status_code == 200
        assert add(client, name="typed meanwhile")
    finally:
        close.set()
    thread.join(5)
    assert outcome["response"].status_code == 200 and len(starts) == 1
    assert Path(get_state().fs_root) == other.resolve()
    assert not folder_picker.is_open()
    assert client.post("/api/fs/root/choose").status_code == 200


@pytest.mark.parametrize("reason", ["no_display", "packaged_without_tkinter", "no_tkinter",
                                    "no_powershell", "helper_failed"])
def test_6_without_a_dialog_the_answer_is_501_and_the_relaunch_command(client, sandbox, monkeypatch, reason):
    unavailable = folder_picker.PickerUnavailable("No folder chooser can be opened here.", reason)
    answer, _picker = _choose(client, monkeypatch, unavailable)
    assert answer.status_code == 501
    assert error(answer)["code"] == "PICKER_UNAVAILABLE"
    assert error(answer)["detail"] == {"reason": reason, "relaunch": fsbrowser.relaunch_with_root()}
    assert '--root "<folder>"' in error(answer)["message"]
    assert Path(get_state().fs_root) == sandbox


def test_6_the_page_is_told_whether_the_folder_can_be_changed(client, monkeypatch):
    monkeypatch.setattr(folder_picker, "backend", lambda: (None, "no_display"))
    home = body(client.get("/api/fs/home"))
    assert home["canChooseRoot"] is False and home["relaunch"] == fsbrowser.relaunch_with_root()
    monkeypatch.setattr(folder_picker, "backend", lambda: ("tkinter", ""))
    assert body(client.get("/api/fs/home"))["canChooseRoot"] is True


# ---- the helper process: constant command lines, and what is read from them -----------------


def test_6_where_a_dialog_can_be_shown(monkeypatch):
    monkeypatch.setenv(folder_picker.DISABLE_ENV, "1")
    assert folder_picker.backend() == (None, "disabled") and not folder_picker.available()
    monkeypatch.delenv(folder_picker.DISABLE_ENV)
    monkeypatch.setattr(folder_picker.os, "name", "nt")
    monkeypatch.setattr(folder_picker, "_powershell_path", lambda: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    assert folder_picker.backend() == ("powershell", "")
    monkeypatch.setattr(folder_picker, "_powershell_path", lambda: None)
    assert folder_picker.backend() == (None, "no_powershell")

    monkeypatch.setattr(folder_picker.os, "name", "posix")
    monkeypatch.setattr(folder_picker.runtime_paths, "is_frozen", lambda: True)
    assert folder_picker.backend() == (None, "packaged_without_tkinter")
    monkeypatch.setattr(folder_picker.runtime_paths, "is_frozen", lambda: False)
    monkeypatch.setattr(folder_picker.sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert folder_picker.backend() == (None, "no_display")   # headless Linux, CI
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(folder_picker.importlib.util, "find_spec", lambda name: None)
    assert folder_picker.backend() == (None, "no_tkinter")
    monkeypatch.setattr(folder_picker.importlib.util, "find_spec", lambda name: object())
    assert folder_picker.backend() == ("tkinter", "")
    with pytest.raises(folder_picker.PickerUnavailable):
        monkeypatch.setattr(folder_picker, "backend", lambda: (None, "no_display"))
        folder_picker.pick("/somewhere")


def test_6_the_helper_command_lines_are_constants(monkeypatch, tmp_path):
    """Nothing is interpolated into what is run: the start folder travels in
    an environment variable, and a hostile one is only ever a value."""
    monkeypatch.setattr(folder_picker, "_powershell_path", lambda: r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
    hostile = "C:\\x'; Remove-Item -Recurse C:\\ ; '$(calc)`\" & echo %PATH% \n__import__('os')"
    seen = []

    def run(argv, **kwargs):
        seen.append((list(argv), kwargs))
        answer = base64.b64encode(str(tmp_path).encode("utf-8")).decode("ascii")
        return type("Done", (), {"returncode": 0, "stdout": ("FTA_PICKED:" + answer + "\r\n").encode(), "stderr": b""})()

    monkeypatch.setattr(folder_picker, "_start_helper", run)
    for name in ("powershell", "tkinter"):
        monkeypatch.setattr(folder_picker, "backend", lambda name=name: (name, ""))
        expected = folder_picker.command(name)
        assert folder_picker.pick(hostile) == str(tmp_path)
        argv, kwargs = seen[-1]
        assert argv == expected, "the same command line whatever the start folder is"
        assert not any("Remove-Item" in part or "calc" in part for part in argv)
        assert kwargs["shell"] is False and kwargs["env"][folder_picker.START_ENV] == hostile
        assert kwargs["stdin"] == folder_picker.subprocess.DEVNULL and kwargs["timeout"] == folder_picker.TIMEOUT_SECONDS
        # and with no start folder at all
        assert folder_picker.pick(None) == str(tmp_path)
        assert seen[-1][0] == expected and folder_picker.START_ENV not in seen[-1][1]["env"]

    powershell = folder_picker.command("powershell")
    assert powershell[0].lower().endswith(r"system32\windowspowershell\v1.0\powershell.exe")
    assert powershell[1:6] == ["-NoLogo", "-NoProfile", "-NonInteractive", "-STA", "-Command"]
    assert powershell[6] is folder_picker._POWERSHELL_SCRIPT and len(powershell) == 7
    assert "$env:FTA_EDITOR_PICKER_START" in powershell[6] and "FolderBrowserDialog" in powershell[6]
    tk = folder_picker.command("tkinter")
    assert tk == [sys.executable, "-I", "-c", folder_picker._TKINTER_PROGRAM]
    assert "askdirectory" in tk[3] and "os.environ.get('FTA_EDITOR_PICKER_START')" in tk[3]
    compile(tk[3], "<picker>", "exec")
    for script in (powershell[6], tk[3]):
        assert folder_picker.PROMPT in script and folder_picker.ANSWER_PREFIX in script
        assert "%" not in script and "{}" not in script and "format(" not in script
    source = _read(REPO / "fta_web" / "folder_picker.py")
    assert "shell=True" not in source and "os.system" not in source and "Popen" not in source
    assert source.count("subprocess.run(") == 1, "one place starts a process"


def test_6_what_is_read_from_the_helper(monkeypatch):
    def encode(text):
        return "FTA_PICKED:" + base64.b64encode(text.encode("utf-8")).decode("ascii")

    assert folder_picker.parse_answer(encode("C:\\解析\\ポンプ")) == "C:\\解析\\ポンプ"
    assert folder_picker.parse_answer("a banner\r\n" + encode("/home/u/trees") + "\r\n") == "/home/u/trees"
    # a closed dialog prints nothing; anything else is not an answer
    for nothing in ("", "\n", "C:\\not marked", "FTA_PICKED:", "FTA_PICKED:not base64!!",
                    "FTA_PICKED:" + base64.b64encode(b"\xff\xfe").decode("ascii"),
                    encode("a\x00b"), encode("   ")):
        assert folder_picker.parse_answer(nothing) is None, nothing

    monkeypatch.setattr(folder_picker, "backend", lambda: ("powershell", ""))
    monkeypatch.setattr(folder_picker, "_powershell_path", lambda: "powershell.exe")

    def done(returncode, stdout):
        return lambda argv, **kwargs: type("Done", (), {"returncode": returncode, "stdout": stdout, "stderr": b"x"})()

    monkeypatch.setattr(folder_picker, "_start_helper", done(0, b""))
    assert folder_picker.pick(None) is None, "closed: a cancel"
    monkeypatch.setattr(folder_picker, "_start_helper", done(1, b""))
    with pytest.raises(folder_picker.PickerUnavailable) as failed:
        folder_picker.pick(None)                      # the helper could not show a dialog
    assert failed.value.reason == "helper_failed"

    def timed_out(argv, **kwargs):
        raise folder_picker.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(folder_picker, "_start_helper", timed_out)
    assert folder_picker.pick(None) is None, "left open too long: a cancel"

    def missing(argv, **kwargs):
        raise FileNotFoundError(2, "No such file")

    monkeypatch.setattr(folder_picker, "_start_helper", missing)
    with pytest.raises(folder_picker.PickerUnavailable):
        folder_picker.pick(None)
    assert not folder_picker.is_open(), "the lock is given back on every path"


def test_6_the_packaged_app_still_excludes_tkinter_and_ships_the_picker():
    spec = _read(REPO / "build" / "fta_editor.spec")
    hidden = spec[spec.index("hiddenimports = ["):spec.index("]", spec.index("hiddenimports = ["))]
    assert '"folder_picker",' in hidden and '"recovery",' in hidden
    excludes = spec[spec.index("excludes = ["):]
    assert '"tkinter",' in excludes and '"_tkinter",' in excludes


def test_6_the_file_dialog_has_the_button_and_keeps_the_command_when_there_is_no_dialog():
    src = _read(STATIC / "filedialog.js")
    change = _function(src, "async function changeRoot()")
    # no path is sent, and none could be: the call has no body of its own
    assert "api.post('/fs/root/choose')" in change and "path" not in change.replace("pathInput", "")
    assert "t('file.changeRootUnavailable', { command:" in change
    assert "failure.code === 'PICKER_UNAVAILABLE'" in change
    assert "dataset: { role: 'change-root' }" in src
    assert src.count("offerChangeRoot(") >= 3, "offered where a path outside the folder is refused"
    catalog = _read(STATIC / "i18n" / "fix181.js")
    for key in ("file.changeRoot", "file.changeRootTitle", "file.changeRootWaiting", "file.changeRootUnavailable",
                "file.changeRootDone", "file.changeRootUntitled", "file.changeRootCancelled",
                "file.errOutsideRootChoose", "file.changeRootBusy"):
        assert catalog.count("'%s':" % key) == 2, key
    main = _read(STATIC / "main.js")
    assert "'fta:root-changed'" in main and "'fta:root-changed'" in src


# =============================================================================================
# the new endpoints are behind the session token, and documented
# =============================================================================================

NEW_ENDPOINTS = [
    ("post", "/api/ai/cancel", {}),
    ("get", "/api/recovery", None),
    ("post", "/api/recovery/restore", {"id": "0123456789abcdef"}),
    ("post", "/api/recovery/discard", {"id": "0123456789abcdef"}),
    ("post", "/api/fs/root/choose", None),
]

#: The requests that got a guard in this release are refused without the
#: token as they always were (the guard must not have opened another way in).
GUARDED_AGAIN = [
    ("post", "/api/file/open", {"path": "sample.json", "force": True}),
    ("post", "/api/examples/open", {"name": "sampleFTA.json", "force": True}),
]


@pytest.fixture
def guarded(app, other, monkeypatch, per_user_home):
    """The same blueprints behind the real guard (security.init_app), with a
    recovery copy to restore, a person who would pick a folder, and an AI
    request that could be abandoned -- so that a request that got through
    would leave a mark."""
    sys.path.insert(0, str(REPO / "fta_web"))
    import security  # the launcher's own module name

    security.init_app(app, TOKEN, PORT)
    client = app.test_client()
    return client


@pytest.mark.parametrize("method,path,payload", NEW_ENDPOINTS + GUARDED_AGAIN)
def test_the_new_endpoints_refuse_a_request_without_the_token(
        guarded, sandbox, other, per_user_home, monkeypatch, method, path, payload):
    _sample(sandbox)
    picker = FakePicker(str(other))
    monkeypatch.setattr(folder_picker, "pick", picker)
    # a copy that a restore or a discard would act on
    folder = per_user_home / "recovery"
    folder.mkdir(parents=True)
    (folder / "0123456789abcdef.json").write_bytes((EXAMPLES / "sampleFTA.json").read_bytes())
    (folder / "0123456789abcdef.meta.json").write_text(
        json.dumps({"title": "Left behind", "savedAt": "2026-10-11T09:30:00", "originalPath": None}),
        encoding="utf-8")
    # an AI call in flight that a cancel would abandon
    call = ai_bridge._Call("chat", None)
    monkeypatch.setattr(ai_bridge, "_active", call)

    def send(headers, base_url=BASE_URL):
        kwargs = {"base_url": base_url, "headers": headers}
        if payload is not None:
            kwargs["json"] = payload
        return getattr(guarded, method)(path, **kwargs)

    before = get_state().revision_fields()
    for headers, reason in (
        ({}, "missing_token"),
        ({config.TOKEN_HEADER: "wrong"}, "invalid_token"),
        ({config.TOKEN_HEADER: TOKEN, "Origin": "http://evil.example"}, "origin_not_allowed"),
        ({config.TOKEN_HEADER: TOKEN, "Origin": "http://127.0.0.1:%d" % (PORT + 1)}, "origin_not_allowed"),
    ):
        refused = send(headers)
        assert refused.status_code == 403, (path, headers)
        assert error(refused)["code"] == "FORBIDDEN" and error(refused)["detail"] == {"reason": reason}
    rebound = send({config.TOKEN_HEADER: TOKEN}, base_url="http://evil.example:%d" % PORT)
    assert rebound.status_code == 403 and error(rebound)["detail"] == {"reason": "host_not_allowed"}

    # nothing happened: no document replaced, no dialog opened, the root, the
    # recovery copy and the AI call as they were
    assert get_state().revision_fields() == before
    assert picker.started_in == [] and Path(get_state().fs_root) == sandbox
    assert sorted(p.name for p in folder.iterdir()) == ["0123456789abcdef.json", "0123456789abcdef.meta.json"]
    assert ai_bridge._active is call and call.abandoned is False

    allowed = send({config.TOKEN_HEADER: TOKEN})
    assert allowed.status_code == 200, (path, body(allowed))
    assert allowed.headers["Cache-Control"] == "no-store"
    monkeypatch.setattr(ai_bridge, "_active", None)


def test_the_new_endpoints_are_in_the_api_reference_and_the_changelog():
    reference = _read(DOCS / "API_REFERENCE.md")
    changelog = _read(REPO / "CHANGELOG.md")
    unreleased = changelog[changelog.index("## [Unreleased]"):changelog.index("## [1.8.0]")]
    for _method, path, _payload in NEW_ENDPOINTS:
        assert path in reference, path
        assert path in unreleased, path
    for code in ("AI_CANCELLED", "PICKER_UNAVAILABLE", "PICKER_BUSY", "UNSAVED_CHANGES"):
        assert "`%s`" % code in reference, code
    assert "force: true" in reference and "canChooseRoot" in reference and "requestId" in reference
    # the 1.8.0 section, which test_ux_batch_2 and _3 read, is not where this went
    released = changelog[changelog.index("## [1.8.0]"):]
    assert "/api/recovery" not in released and "/api/fs/root/choose" not in released


def test_the_user_guide_says_where_the_recovery_folder_is_and_how_the_folder_is_changed():
    guide = _read(DOCS / "USER_GUIDE.md")
    section = guide[guide.index("### Keeping your work (after 1.8.0)"):guide.index("### The assistant (after 1.7.3)")]
    assert "~/.fta_editor/recovery/" in section and "\\.fta_editor\\recovery\\" in section
    for phrase in ("Restore unsaved work from", "Discard it", "Change folder…", "30", "untitled",
                   "Ctrl-C", "At most five copies"):
        assert phrase in section, phrase
    assert "[Keeping your work](#keeping-your-work-after-180)" in guide
    assert "abandon the request" in guide
    readme = _read(REPO / "fta_web" / "tests" / "gui" / "README.md")
    assert "FTA_GUI_BROWSER" in readme and "| `ki` |" in readme and "FTA_EDITOR_NO_FOLDER_PICKER" in readme


def test_the_new_modules_are_in_the_packaged_app():
    spec = _read(REPO / "build" / "fta_editor.spec")
    hidden = spec[spec.index("hiddenimports = ["):]
    for module in ("recovery", "folder_picker"):
        assert '"%s",' % module in hidden
        assert (REPO / "fta_web" / (module + ".py")).is_file()
    # and they import under the launcher's bare names, as in the frozen app
    code = ("import sys; sys.path.insert(0, %r); import run, recovery, folder_picker; "
            "print(recovery.__name__, folder_picker.__name__)" % str(REPO / "fta_web"))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and out.stdout.split() == ["recovery", "folder_picker"], out.stderr


def test_5_with_the_home_folder_as_root_the_recovery_folder_is_still_out_of_reach(
        client, tmp_path, per_user_home, recovering):
    """The default root is the home directory, and the per-user folder is in
    it. The file endpoints refuse the recovery folder by name."""
    get_state().fs_root = tmp_path            # as if tmp_path were the home directory
    folder = per_user_home / "recovery"
    add(client, name="unsaved")
    assert recovery.flush() is True
    copy_file = folder / (recovering + ".json")
    assert fsbrowser_within(tmp_path, copy_file), "inside the root this time"
    before = copy_file.read_bytes()

    for answer in (
        client.post("/api/file/open", json={"path": str(copy_file), "force": True}),
        client.post("/api/file/save-as", json={"path": str(copy_file)}),
        client.post("/api/file/save-as", json={"path": str(folder / "new.json")}),
        client.get("/api/fs/list", query_string={"path": str(folder)}),
        client.post("/api/file/open", json={"path": "fta_editor_home/recovery/%s.json" % recovering,
                                            "force": True}),
    ):
        assert answer.status_code == 400, body(answer)
        assert error(answer)["code"] == "PATH_REJECTED" and error(answer)["detail"]["reason"] == "reserved"
    assert copy_file.read_bytes() == before and not (folder / "new.json").exists()
    assert state_of(client)["currentPath"] is None
    # the folder beside it is an ordinary one
    beside = per_user_home / "notes.json"
    assert client.post("/api/file/save-as", json={"path": str(beside)}).status_code == 200
    # and the listing of the per-user folder does not show the recovery folder's files
    listed = body(client.get("/api/fs/list", query_string={"path": str(per_user_home)}))
    assert "notes.json" in [f["name"] for f in listed["files"]]
    assert not any(recovering in f["name"] for f in listed["files"])


# =============================================================================================
# 8: what the first Firefox and WebKit runs found
# =============================================================================================


def test_8_a_save_as_confirmed_before_the_folder_is_known_waits_for_it():
    """WebKit lists the start folder more slowly than Chromium, and showed
    this: a name typed and Enter pressed while the listing was on its way was
    dropped without a word; pressed before the listing had been asked for,
    it saved into the root instead of the folder the dialog was about to
    show. The confirmation is kept and made when the listing has landed.
    (Driven in the browser by s_ki.js, with the listing held back.)"""
    src = _read(STATIC / "filedialog.js")
    confirm = _function(src, "async function confirmChoice()")
    head = confirm[:confirm.index("setMessage('');")]
    assert "if (mode === 'save' && (busy || starting)) {" in head
    assert "pendingConfirm = true;" in head and head.rstrip().endswith("if (busy) return;")
    flush = _function(src, "function flushPendingConfirm()")
    assert "if (!pendingConfirm || busy || starting || closed) return;" in flush
    # never into a folder that was not listed
    assert "mode === 'save' && cwd && !message.classList.contains('is-error')" in flush
    assert "window.setTimeout(confirmChoice, 0);" in flush
    assert "if (!next) flushPendingConfirm();" in _function(src, "function setBusy(next)")
    assert src.count("flushPendingConfirm();") == 2, "when a listing ends, and when the start folder is settled"
    # a name that is still being typed is not the one that was confirmed
    assert "nameInput.addEventListener('input', () => { pendingConfirm = false; });" in src


def test_8_the_suite_can_drive_the_two_other_engines_and_ci_does_not():
    lib = _read(REPO / "fta_web" / "tests" / "gui" / "lib.js")
    assert "process.env.FTA_GUI_BROWSER || 'chromium'" in lib
    assert "playwright[BROWSER].launch({ headless })" in lib
    assert "function chromiumOnly(name, reason)" in lib and "function skip(name, reason)" in lib
    runner = _read(REPO / "fta_web" / "tests" / "gui" / "run.mjs")
    assert "FTA_GUI_BROWSER" in runner and "'ki'" in runner
    assert "FTA_EDITOR_NO_FOLDER_PICKER: '1'" in runner, "no native dialog from a test server"
    for workflow in (REPO / ".github" / "workflows").glob("*.yml"):
        text = _read(workflow)
        assert "FTA_GUI_BROWSER" not in text and "install firefox" not in text and "webkit" not in text, workflow.name
