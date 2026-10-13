"""Protecting work (usability work order, batch 2).

One block per item of the work order, by its number there. The server side
is exercised through the real blueprints on a bare Flask app. A pure function
of the page is run in node where node is installed: ``docutil.js`` as the
module it is, the others cut out of their file and run against small
stand-ins for the store and the browser. What only exists as wiring is
checked in the source, and the whole flow is driven in a real browser by
``tests/gui/s_ux2.js``.

No test reaches the network. The AI provider is mocked at the instance, as in
``test_api_ai.py``, and the per-user folder (credentials, ``ui_prefs.json``)
is redirected to ``tmp_path`` for every test here.
"""
import copy
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from AI_agent_handler import AICredentialManager  # noqa: E402
from ai_providers import AIProviderFactory  # noqa: E402

from fta_web import ai_bridge, config, fsbrowser, runtime_paths, user_prefs  # noqa: E402
from fta_web.engine import WebCore  # noqa: E402
from fta_web.state import AppState, get_state, reset_state  # noqa: E402

STATIC = REPO / "fta_web" / "static" / "js"
CSS = REPO / "fta_web" / "static" / "css" / "app.css"
INDEX = REPO / "fta_web" / "templates" / "index.html"
EXAMPLES = REPO / "fta_web" / "examples"
DOCS = REPO / "docs"

API_KEY = "sk-testkeyDONOTLEAK0123456789abcdefAB12"
PROVIDER_NAME = "OpenAI"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _symlinks_supported() -> bool:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        try:
            os.symlink(os.path.join(tmp, "a"), os.path.join(tmp, "b"))
        except (OSError, NotImplementedError, AttributeError):
            return False
    return True


requires_symlinks = pytest.mark.skipif(
    not _symlinks_supported(), reason="creating symlinks is not permitted here")


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
    """One function of a module, as plain script text."""
    return _braced(src, src.index(header))


def _node(script: str, module: bool = False):
    """Run `script` under node, read from stdin; its stdout as JSON."""
    args = ["node", "--input-type=module", "-"] if module else ["node", "-"]
    out = subprocess.run(args, input=script, capture_output=True, text=True, encoding="utf-8",
                         check=True, timeout=60).stdout
    return json.loads(out)


def _docutil(expression: str, **values):
    """Evaluate `expression` with docutil.js imported as `d` and `values` in scope."""
    script = "import * as d from %s;\n" % json.dumps((STATIC / "docutil.js").as_uri())
    for name, value in values.items():
        script += "const %s = %s;\n" % (name, json.dumps(value))
    script += "console.log(JSON.stringify(%s));" % expression
    return _node(script, module=True)


def body(response):
    return json.loads(response.get_data(as_text=True))


def error(response):
    return body(response)["error"]


def plain(node):
    """A tree without the values the engine derives."""
    out = {k: v for k, v in node.items() if k not in ("children", "calculatedProbability")}
    out["children"] = [plain(c) for c in node.get("children") or []]
    return out


# ---- fixtures -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def per_user_home(tmp_path, monkeypatch):
    """The per-user folder in tmp_path: credentials and ui_prefs.json."""
    directory = tmp_path / "fta_editor_home"
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_DIR", directory)
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_FILE", directory / "ai_credentials.json")
    return directory


@pytest.fixture
def sandbox(tmp_path):
    root = tmp_path / "sandbox"
    (root / "sub").mkdir(parents=True)
    shutil.copyfile(EXAMPLES / "sampleFTA.json", root / "sample.json")
    shutil.copyfile(EXAMPLES / "sampleFTA.json", root / "sub" / "inner.json")
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.copyfile(EXAMPLES / "sampleFTA.json", outside / "secret.json")
    return root


def _blueprints():
    from fta_web.routes.ai import ai_bp
    from fta_web.routes.analysis import analysis_bp
    from fta_web.routes.files import files_bp
    from fta_web.routes.tree import tree_bp

    return (tree_bp, files_bp, ai_bp, analysis_bp)


@pytest.fixture
def app(sandbox):
    flask = pytest.importorskip("flask")
    reset_state()
    ai_bridge.reset_handler()
    from fta_web.routes import ai as ai_routes

    ai_routes._set_pending_update(None)
    built = flask.Flask(__name__)
    for blueprint in _blueprints():
        built.register_blueprint(blueprint)
    built.config.update(TESTING=True)
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
    return body(response)


def state_of(client):
    return body(client.get("/api/state"))


def revision_of(client):
    return body(client.get("/api/revision"))


# =============================================================================================
# 17: a second tab knows when the document changed elsewhere
# =============================================================================================


def test_17_the_revision_counts_content_changes_and_not_saves():
    state = AppState()
    first = state.revision_fields()
    state.mark_dirty()
    assert state.revision_fields() == {"revision": first["revision"] + 1,
                                       "documentSerial": first["documentSerial"]}
    state.mark_saved()
    assert state.revision_fields()["revision"] == first["revision"] + 1, "a save is not a change"
    state.reset()
    assert state.revision_fields() == {"revision": first["revision"] + 2,
                                       "documentSerial": first["documentSerial"] + 1}


def test_17_every_answer_with_a_tree_carries_the_revision(client, sandbox):
    start = state_of(client)
    assert {"revision", "documentSerial"} <= set(start)
    assert revision_of(client) == {
        "ok": True, "dirty": False, "currentPath": None,
        "revision": start["revision"], "documentSerial": start["documentSerial"],
    }

    made = add(client, name="Pump A")
    assert made["revision"] == start["revision"] + 1
    assert revision_of(client)["revision"] == made["revision"]
    assert revision_of(client)["dirty"] is True

    for call in (
        lambda: client.patch("/api/nodes/" + made["nodeId"], json={"name": "Pump A fails"}),
        lambda: client.post("/api/undo", json={}),
        lambda: client.post("/api/redo", json={}),
        lambda: client.post("/api/metadata", json={"title": "Cooling"}),
        lambda: client.post("/api/analysis/settings", json={"cutsets": {"maxOrder": 3}}),
        lambda: client.delete("/api/nodes/" + made["nodeId"]),
    ):
        before = revision_of(client)["revision"]
        answer = body(call())
        assert answer["ok"] is True and "tree" in answer
        assert answer["revision"] == before + 1 == revision_of(client)["revision"]

    # an edit that changes nothing is not a new revision
    before = revision_of(client)["revision"]
    assert body(client.post("/api/metadata", json={"title": "Cooling"}))["revision"] == before


def test_17_a_save_keeps_the_revision_and_reports_the_path_beside_it(client, sandbox):
    add(client, name="Pump A")
    before = revision_of(client)
    saved = body(client.post("/api/file/save-as", json={"path": str(sandbox / "mine.json")}))
    assert "revision" not in saved, "a save answers without the tree, so without a revision"
    after = revision_of(client)
    assert after["revision"] == before["revision"]
    assert after["dirty"] is False and Path(after["currentPath"]) == sandbox / "mine.json"


def test_17_another_document_is_another_serial(client, sandbox):
    first = revision_of(client)
    opened = body(client.post("/api/file/open", json={"path": str(sandbox / "sample.json")}))
    assert opened["documentSerial"] == first["documentSerial"] + 1
    assert opened["revision"] > first["revision"]
    made = add(client)
    assert made["documentSerial"] == opened["documentSerial"], "an edit is the same document"
    fresh = body(client.post("/api/new", json={"force": True}))
    assert fresh["documentSerial"] == opened["documentSerial"] + 1
    upload = {"file": (io.BytesIO(_read(EXAMPLES / "sampleFTA.json").encode("utf-8")), "x.json")}
    imported = body(client.post("/api/import/json", data=upload, content_type="multipart/form-data"))
    assert imported["documentSerial"] == fresh["documentSerial"] + 1


@needs_node
def test_17_the_store_takes_the_revision_only_with_the_tree():
    """A stale tab that saves must not come to believe it is current."""
    script = (
        "globalThis.window = { dispatchEvent() {}, ftaShell: null };\n"
        "globalThis.CustomEvent = class { constructor(t, i) { this.type = t; this.detail = i && i.detail; } };\n"
        "const { store } = await import(%s);\n" % json.dumps((STATIC / "store.js").as_uri())
        + "store.setState({ tree: { id: 'root', children: [] }, revision: 5, documentSerial: 1, dirty: true });\n"
        "const out = [];\n"
        "store.applyMutation({ dirty: false, currentPath: 'x.json', revision: 9, documentSerial: 4 });\n"
        "out.push([store.state.revision, store.state.documentSerial, store.state.dirty, store.state.currentPath]);\n"
        "store.applyMutation({ tree: { id: 'root', children: [] }, revision: 6, documentSerial: 1 });\n"
        "out.push([store.state.revision, store.state.documentSerial]);\n"
        "console.log(JSON.stringify(out));"
    )
    assert _node(script, module=True) == [[5, 1, False, "x.json"], [6, 1]]


@needs_node
def test_17_the_tab_reloads_when_behind_and_only_syncs_the_badge_when_level():
    src = _read(STATIC / "main.js")
    script = (
        "const calls = [];\n"
        "let writes = 0;\n"
        "const store = { state: null, applyMutation(p) { calls.push(['apply', p]); } };\n"
        "const pendingWrites = () => writes;\n"
        "function reloadWhenIdle() { calls.push(['reload']); }\n"
        + _function(src, "function noteServerRevision(info)") + "\n"
        "const held = { revision: 7, documentSerial: 2, dirty: true, currentPath: null };\n"
        "const run = (info, w) => { calls.length = 0; writes = w || 0; store.state = { ...held };"
        " noteServerRevision(info); return JSON.parse(JSON.stringify(calls)); };\n"
        "console.log(JSON.stringify([\n"
        "  run({ revision: 8, documentSerial: 2, dirty: true, currentPath: null }),\n"
        "  run({ revision: 7, documentSerial: 3, dirty: false, currentPath: null }),\n"
        "  run({ revision: 7, documentSerial: 2, dirty: true, currentPath: null }),\n"
        "  run({ revision: 7, documentSerial: 2, dirty: false, currentPath: 'a.json' }),\n"
        "  run({ revision: 7, documentSerial: 2, dirty: false, currentPath: 'a.json' }, 1),\n"
        "]));"
    )
    assert _node(script) == [
        [["reload"]],                                                # another tab edited
        [["reload"]],                                                # another document
        [],                                                          # nothing happened
        [["apply", {"dirty": False, "currentPath": "a.json"}]],      # another tab saved
        [],                                                          # this tab's own save is on the wire
    ]


def test_17_a_busy_tab_is_not_reloaded_and_nothing_polls_the_document():
    src = _read(STATIC / "main.js")
    idle = _function(src, "function tabIsIdle()")
    for guard in ("modalOpen()", "pendingWrites() > 0", '[data-dirty="true"]', ".fta-tree-rename",
                  "metadataChanged()", "isBooting()"):
        assert guard in idle, guard
    later = _function(src, "function reloadWhenIdle()")
    assert "if (!tabIsIdle())" in later and "STALE_RETRY_MS" in later
    reload = _function(src, "async function reloadFromServer()")
    assert reload.index("api.get('/state')") < reload.index("if (!tabIsIdle())") < reload.index("store.setState(next)")
    assert "announceDocument();" in reload
    # asked when the tab comes back, with the comparison; the timer only pings
    boot = _function(src, "async function boot()")
    assert "window.addEventListener('focus', () => checkServer(true));" in boot
    visible = _braced(boot, boot.index("document.addEventListener('visibilitychange'"))
    assert "checkServer(true);" in visible and "stopPing();" in visible
    assert "await checkServer(false);" in _function(src, "function schedulePing()")
    # an answer already on its way may predate the change: ask again
    check = _function(src, "async function checkServer(act)")
    assert "if (act) askAgain = true;" in check and "checkServer(true);" in check


# =============================================================================================
# 19: the server stopped; the page can still hand the document over
# =============================================================================================


@needs_node
@pytest.mark.parametrize("example", ["sampleFTA.json", "challenger_fta_ja.json", "tmi2_eta_en.json"])
def test_19_the_rescue_copy_is_a_file_load_accepts(client, tmp_path, example):
    """Built by the page from /api/state, opened by the editor's own loader."""
    assert client.post("/api/examples/open", json={"name": example}).status_code == 200
    add(client, name="Not saved yet", probability=0.25)
    held = state_of(client)
    text = _docutil("d.rescueText(state)", state=held)
    assert isinstance(text, str) and text.endswith("}\n")
    # The loader mistakes a file that ends "}}" for an old wrapped format.
    assert not text.rstrip().endswith("}}")
    assert list(json.loads(text)) == ["title", "date", "mode", "tree", "analysis"]

    target = tmp_path / "rescue.json"
    target.write_text(text, encoding="utf-8")
    loaded = WebCore()
    ok, problem = loaded.load_from_json(str(target))
    assert ok, problem
    assert not loaded.last_load_warnings
    assert plain(loaded.get_data()) == plain(held["tree"])
    assert loaded.get_metadata() == held["metadata"]
    assert loaded.get_analysis() == held["analysis"]

    # and through the endpoint the Load dialog's "A file on this computer" uses
    client.post("/api/new", json={"force": True})
    upload = {"file": (io.BytesIO(text.encode("utf-8")), "rescue.json")}
    again = body(client.post("/api/import/json", data=upload, content_type="multipart/form-data"))
    assert again["ok"] is True and again["currentPath"] is None
    assert again["tree"] == held["tree"] and again["metadata"] == held["metadata"]
    assert again["analysis"] == held["analysis"]


@needs_node
def test_19_the_rescue_copy_needs_a_document_and_names_itself():
    got = _docutil(
        "[d.rescueText(null), d.rescueText({}), d.buildRescueDocument({tree: {id: 'root'}, metadata: {mode: 'eta'}}),"
        " d.rescueFilename({currentPath: 'C:\\\\work\\\\pump study.json'}, new Date(2026, 9, 12, 9, 5)),"
        " d.rescueFilename({currentPath: '/home/u/plant.v2.json'}, new Date(2026, 0, 2, 23, 59)),"
        " d.rescueFilename({metadata: {title: 'Loss of cooling: A/B?'}}, new Date(2026, 9, 12, 9, 5)),"
        " d.rescueFilename({metadata: {title: '  '}}, new Date(2026, 9, 12, 9, 5))]")
    assert got == [
        None, None,
        {"title": "", "date": "", "mode": "ETA", "tree": {"id": "root"}},
        "pump study-rescue-20261012-0905.json",
        "plant.v2-rescue-20260102-2359.json",
        "Loss of cooling_ A_B_-rescue-20261012-0905.json",
        "fta_analysis-rescue-20261012-0905.json",
    ]


def test_19_the_ping_does_not_fill_the_terminal():
    """Werkzeug prints every request; the ping would scroll the URL away."""
    import logging

    sys.path.insert(0, str(REPO / "fta_web"))
    import run as launcher

    def shown(line):
        record = logging.LogRecord("werkzeug", logging.INFO, __file__, 1, "%s - - [%s] %s\n",
                                   ("127.0.0.1", "12/Oct/2026 09:00:00", line), None)
        return launcher.QuietPing().filter(record)

    assert shown('"GET /api/revision HTTP/1.1" 200 -') is False
    # everything else is printed: other requests, and a ping that was refused
    assert shown('"GET /api/state HTTP/1.1" 200 -') is True
    assert shown('"GET /api/revision HTTP/1.1" 403 -') is True
    assert shown('"POST /api/revision HTTP/1.1" 405 -') is True
    assert shown('"GET /api/revisions HTTP/1.1" 200 -') is True
    assert 'logging.getLogger("werkzeug").addFilter(QuietPing())' in _read(REPO / "fta_web" / "run.py")


def test_19_the_banner_follows_a_ping_that_stops_while_the_tab_is_hidden():
    src = _read(STATIC / "main.js")
    assert re.search(r"const PING_MS = (\d+);", src) and 2000 <= int(re.search(r"const PING_MS = (\d+);", src).group(1)) <= 15000
    ping = _function(src, "function schedulePing()")
    assert "if (sessionLost || document.hidden) return;" in ping and "PING_MS" in ping
    check = _function(src, "async function checkServer(act)")
    assert "api.get('/revision')" in check
    # only a request that never arrived is "the server is gone"
    assert "err.code === 'NETWORK_ERROR') setServerDown(true)" in check
    assert "setServerDown(false);" in check
    down = _function(src, "function setServerDown(down)")
    assert "banner.hidden = !down;" in down and "t('rescue.back')" in down
    # any failed request asks at once, and the ping decides
    assert "window.addEventListener(SERVER_UNREACHABLE_EVENT" in src
    # ...once: a failed check must not start the next one (a busy loop while the server is away)
    listener = _braced(src, src.index("window.addEventListener(SERVER_UNREACHABLE_EVENT"))
    assert listener.index("if (pinging || serverDown) return;") < listener.index("checkServer(false)")
    api =_read(STATIC / "api.js")
    assert "new CustomEvent(SERVER_UNREACHABLE_EVENT" in _function(api, "async function send(method, url, init)")
    rescue = _function(src, "function downloadRescueCopy()")
    assert "rescueText(store.state)" in rescue and "saveBlob(" in rescue and "api." not in rescue

    html = _read(INDEX)
    banner = html[html.index('id="server-banner"'):html.index("</div>", html.index('id="server-banner"'))]
    assert 'role="alert"' in banner and "hidden" in banner
    assert 'id="server-banner-rescue"' in banner and 'data-i18n="rescue.download"' in banner
    assert 'id="server-banner-retry"' in banner
    # the screen of a session that ended offers the same download
    assert 'id="overlay-rescue-btn"' in html
    lost = _function(src, "function onSessionInvalid()")
    assert "rescue.hidden = !rescueText(store.state);" in lost


# =============================================================================================
# 20: Update FTA shows what it would do and waits
# =============================================================================================

OLD_TREE_NODES = [("Cause A", 0.2), ("Cause B", 0.3)]

#: The model's rewrite of the tree `seeded` builds: Cause A changed, Cause B
#: removed, one node added.
REWRITE = {
    "id": "root", "name": "Top event", "type": "Root", "probability": 1.0, "logicGate": "OR",
    "notes": "", "links": [],
    "children": [
        {"id": "root_0", "name": "Cause A", "type": "Event", "probability": 0.05, "logicGate": "OR",
         "notes": "", "links": [], "children": []},
        {"id": "root_7", "name": "Common cause", "type": "Event", "probability": 0.01, "logicGate": "OR",
         "notes": "", "links": [], "children": []},
    ],
}


@pytest.fixture
def provider():
    instance = AIProviderFactory.get_provider(PROVIDER_NAME)
    assert instance is not None
    return instance


@pytest.fixture
def configured(client, provider, monkeypatch):
    """Credentials saved through the real path, against a mocked connection test."""
    monkeypatch.setattr(provider, "test_connection", lambda *a, **k: (True, "ok"))
    response = client.post("/api/ai/credentials", json={
        "provider": PROVIDER_NAME, "apiKey": API_KEY,
        "endpoint": "https://api.openai.com/v1", "model": "gpt-4o",
    })
    assert response.status_code == 200, body(response)
    return client


@pytest.fixture
def seeded(configured, provider, monkeypatch):
    """A document with two causes, and a provider that answers with REWRITE."""
    client = configured
    client.patch("/api/nodes/root", json={"name": "Top event"})
    for name, probability in OLD_TREE_NODES:
        add(client, name=name, probability=probability)
    client.post("/api/file/save-as", json={"path": str(get_state().fs_root / "seeded.json")})
    calls = []

    def send_message(api_key, endpoint, model, messages, max_tokens=2000):
        calls.append(messages)
        return json.dumps(REWRITE), None

    monkeypatch.setattr(provider, "send_message", send_message)
    client.provider_calls = calls
    return client


def names(entries):
    return sorted(entry["name"] for entry in entries)


def test_20_a_preview_changes_nothing_and_says_what_it_would_do(seeded):
    client = seeded
    before = state_of(client)
    response = client.post("/api/ai/update", json={"preview": True})
    answer = body(response)
    assert response.status_code == 200, answer
    assert answer["preview"] is True and isinstance(answer["updateId"], str) and answer["updateId"]
    assert "tree" not in answer and "revision" not in answer
    summary = answer["updateSummary"]
    assert names(summary["added"]) == ["Common cause"]
    assert names(summary["removed"]) == ["Cause B"]
    assert names(summary["changed"]) == ["Cause A"]
    assert len(client.provider_calls) == 1
    after = state_of(client)
    assert after == before, "a preview must leave the document exactly as it was"
    assert after["dirty"] is False and after["canUndo"] is True


def test_20_apply_installs_the_previewed_rewrite_in_one_undo_step(seeded):
    client = seeded
    before = state_of(client)
    preview = body(client.post("/api/ai/update", json={"preview": True}))
    applied_response = client.post("/api/ai/update/apply", json={"id": preview["updateId"]})
    applied = body(applied_response)
    assert applied_response.status_code == 200, applied
    assert len(client.provider_calls) == 1, "apply must not call the provider again"
    assert applied["updateSummary"] == preview["updateSummary"]
    assert [c["name"] for c in applied["tree"]["children"]] == ["Cause A", "Common cause"]
    assert applied["tree"]["children"][0]["probability"] == 0.05
    assert applied["dirty"] is True and applied["revision"] == before["revision"] + 1
    assert state_of(client)["tree"] == applied["tree"]

    undone = body(client.post("/api/undo", json={}))
    assert undone["tree"] == before["tree"], "one Ctrl+Z puts the previous tree back"

    again = client.post("/api/ai/update/apply", json={"id": preview["updateId"]})
    assert again.status_code == 409 and error(again)["code"] == "AI_UPDATE_EXPIRED"


def test_20_a_preview_and_a_one_step_update_report_the_same(seeded):
    client = seeded
    preview = body(client.post("/api/ai/update", json={"preview": True}))
    client.post("/api/ai/update/discard", json={"id": preview["updateId"]})
    direct = body(client.post("/api/ai/update", json={}))
    assert direct["updateSummary"] == preview["updateSummary"]
    assert direct["mergedFields"] == preview["mergedFields"]
    assert "preview" not in direct and "tree" in direct, "without the flag it applies, as it always did"


@pytest.mark.parametrize("change", ["edit", "undo", "new", "open"])
def test_20_apply_refuses_a_document_that_changed_since_the_preview(seeded, change):
    client = seeded
    preview = body(client.post("/api/ai/update", json={"preview": True}))
    if change == "edit":
        add(client, name="Typed meanwhile")
    elif change == "undo":
        client.post("/api/undo", json={})
    elif change == "new":
        client.post("/api/new", json={"force": True})
    else:
        client.post("/api/file/open", json={"path": str(get_state().fs_root / "sample.json")})
    before = state_of(client)
    refused = client.post("/api/ai/update/apply", json={"id": preview["updateId"]})
    assert refused.status_code == 409 and error(refused)["code"] == "AI_DOCUMENT_CHANGED"
    assert state_of(client) == before, "a refused apply changes nothing"
    # the rewrite is dropped, not kept for a second try
    gone = client.post("/api/ai/update/apply", json={"id": preview["updateId"]})
    assert error(gone)["code"] == "AI_UPDATE_EXPIRED"


def test_20_a_preview_refuses_a_document_edited_while_the_model_worked(seeded, provider, monkeypatch):
    client = seeded

    def edits_meanwhile(api_key, endpoint, model, messages, max_tokens=2000):
        state = get_state()
        with state.lock:
            state.push_undo()
            state.core.find_node_by_id("root")["notes"] = "edited while the AI was writing"
            state.mark_dirty()
        return json.dumps(REWRITE), None

    monkeypatch.setattr(provider, "send_message", edits_meanwhile)
    refused = client.post("/api/ai/update", json={"preview": True})
    assert refused.status_code == 409 and error(refused)["code"] == "AI_DOCUMENT_CHANGED"
    assert body(client.post("/api/ai/update/discard", json={}))["discarded"] is False, "nothing was left waiting"


def test_20_discard_wrong_ids_and_a_newer_preview(seeded):
    client = seeded
    before = state_of(client)
    first = body(client.post("/api/ai/update", json={"preview": True}))
    wrong = client.post("/api/ai/update/apply", json={"id": "not-the-id"})
    assert wrong.status_code == 409 and error(wrong)["code"] == "AI_UPDATE_EXPIRED"
    for bad in ({}, {"id": None}, {"id": 5}, {"id": ["x"]}):
        assert error(client.post("/api/ai/update/apply", json=bad))["code"] == "AI_UPDATE_EXPIRED"
    # none of those consumed or applied it
    assert state_of(client) == before
    assert body(client.post("/api/ai/update/discard", json={"id": "other"}))["discarded"] is False
    second = body(client.post("/api/ai/update", json={"preview": True}))
    assert second["updateId"] != first["updateId"]
    assert error(client.post("/api/ai/update/apply", json={"id": first["updateId"]}))["code"] == "AI_UPDATE_EXPIRED"
    # ...and asking for the old one did not throw the new one away
    assert body(client.post("/api/ai/update/discard", json={"id": second["updateId"]}))["discarded"] is True
    assert error(client.post("/api/ai/update/apply", json={"id": second["updateId"]}))["code"] == "AI_UPDATE_EXPIRED"
    assert state_of(client) == before
    assert client.post("/api/ai/update/discard", json={"id": 7}).status_code == 400


def test_20_clearing_the_conversation_drops_the_waiting_rewrite(seeded):
    client = seeded
    preview = body(client.post("/api/ai/update", json={"preview": True}))
    assert client.delete("/api/ai/conversation").status_code == 200
    assert error(client.post("/api/ai/update/apply", json={"id": preview["updateId"]}))["code"] == "AI_UPDATE_EXPIRED"


def test_20_the_preview_flag_is_a_boolean_and_bad_output_is_refused_as_before(seeded, provider, monkeypatch):
    client = seeded
    bad = client.post("/api/ai/update", json={"preview": "yes"})
    assert bad.status_code == 400 and error(bad)["detail"]["field"] == "preview"
    assert len(client.provider_calls) == 0, "refused before the provider is called"
    monkeypatch.setattr(provider, "send_message", lambda *a, **k: ("I cannot do that.", None))
    refused = client.post("/api/ai/update", json={"preview": True})
    assert refused.status_code == 400 and error(refused)["code"] == "AI_INVALID_JSON"
    assert body(client.post("/api/ai/update/discard", json={}))["discarded"] is False


def test_20_apply_needs_a_provider_and_discard_does_not(client):
    assert error(client.post("/api/ai/update/apply", json={"id": "x"}))["code"] == "AI_NOT_CONFIGURED"
    assert body(client.post("/api/ai/update/discard", json={})) == {"ok": True, "discarded": False}


def test_20_the_key_is_not_in_a_preview(seeded, provider, monkeypatch):
    client = seeded
    leaky = copy.deepcopy(REWRITE)
    leaky["children"][1]["name"] = "Leaked " + API_KEY
    monkeypatch.setattr(provider, "send_message", lambda *a, **k: (json.dumps(leaky), None))
    response = client.post("/api/ai/update", json={"preview": True})
    assert response.status_code == 200
    assert API_KEY not in response.get_data(as_text=True)


def test_20_the_panel_asks_then_previews_then_applies():
    src = _read(STATIC / "chat.js")
    action = re.search(r"  function actionUpdate\(\) \{(.*?)\n  \}\n", src, re.S).group(1)
    assert action.index("choiceDialog(t('ai.update.confirm')") < action.index("api.post('/ai/update', { preview: true, requestId: job.id })")
    assert "if (!go || destroyed || blocked()) return;" in action
    assert "renderUpdatePreview(result);" in action
    preview = _function(src, "function renderUpdatePreview(result)")
    assert "role: 'apply-update'" in preview and "role: 'discard-update'" in preview
    assert "refreshDocument" not in preview, "the preview itself never touches the store"
    apply = _function(src, "async function applyUpdate(handle)")
    assert "api.post('/ai/update/apply', { id: handle.id })" in apply
    assert apply.index("api.post('/ai/update/apply'") < apply.index("await refreshDocument(result);")
    # a card made for the previous document is retired when another one opens
    assert "window.addEventListener('fta:document', onDocument);" in src


# =============================================================================================
# 21 + 25: bundled examples open as untitled copies
# =============================================================================================


def bundled():
    return sorted(p.name for p in EXAMPLES.glob("*.json"))


def test_21_the_examples_are_listed_from_the_examples_folder(client):
    listed = body(client.get("/api/examples"))["examples"]
    assert sorted(entry["name"] for entry in listed) == bundled()
    assert [entry["name"].lower() for entry in listed] == sorted(n.lower() for n in bundled())
    by_name = {entry["name"]: entry for entry in listed}
    assert set(by_name["sampleFTA.json"]) == {"name", "title", "mode"}
    assert by_name["tmi2_eta_en.json"]["mode"] == "ETA"
    assert by_name["challenger_fta_ja.json"]["mode"] == "FTA"
    assert by_name["challenger_fta_ja.json"]["title"] == json.loads(_read(EXAMPLES / "challenger_fta_ja.json"))["title"]
    # nothing in the listing is a path
    assert not any(os.sep in entry["name"] or "/" in entry["name"] for entry in listed)


def test_21_an_example_opens_untitled_and_save_cannot_reach_the_bundled_file(client, sandbox):
    originals = {name: (EXAMPLES / name).read_bytes() for name in bundled()}
    add(client, name="left over")  # a dirty document: refused since 1.8.1, unless forced
    assert error(client.post("/api/examples/open", json={"name": "sampleFTA.json"}))["code"] == "UNSAVED_CHANGES"
    opened = body(client.post("/api/examples/open", json={"name": "sampleFTA.json", "force": True}))
    assert opened["ok"] is True and opened["example"] == "sampleFTA.json"
    assert opened["currentPath"] is None and opened["dirty"] is False
    assert opened["canUndo"] is False and opened["tree"]["children"]
    assert get_state().current_path is None
    assert get_state().core.last_saved_file is None, "the core must not remember the bundled file"

    refused = client.post("/api/file/save", json={})
    assert refused.status_code == 409 and error(refused)["code"] == "NO_CURRENT_PATH"

    add(client, name="my own change")
    assert client.post("/api/file/save", json={}).status_code == 409, "still no path after an edit"
    saved = body(client.post("/api/file/save-as", json={"path": str(sandbox / "my copy.json")}))
    assert Path(saved["currentPath"]) == sandbox / "my copy.json"
    assert client.post("/api/file/save", json={}).status_code == 200
    assert "my own change" in (sandbox / "my copy.json").read_text(encoding="utf-8")
    assert {name: (EXAMPLES / name).read_bytes() for name in bundled()} == originals
    # exporting does not adopt a path either
    client.post("/api/examples/open", json={"name": "sampleFTA.json"})
    assert client.get("/api/export/json").status_code == 200
    assert get_state().core.last_saved_file is None and get_state().current_path is None


def test_21_only_a_listed_name_opens_an_example(client, sandbox, tmp_path):
    secret = tmp_path / "outside" / "secret.json"
    assert secret.is_file()
    before = state_of(client)
    hostile = [
        str(secret), "../outside/secret.json", "..\\outside\\secret.json", "sampleFTA.json/../sampleFTA.json",
        "./sampleFTA.json", "sub/sampleFTA.json", str(EXAMPLES / "sampleFTA.json"), "SAMPLEFTA.JSON\x00.json",
        "samplefta.json" if "samplefta.json" not in bundled() else "nope.json", "sampleFTA", "", " sampleFTA.json",
    ]
    for name in hostile:
        response = client.post("/api/examples/open", json={"name": name})
        assert response.status_code in (400, 404), name
        problem = error(response)
        assert problem["code"] == "INVALID_FIELD" and problem["detail"] == {"field": "name"}
        if name:
            assert name not in problem["message"], "the value is never echoed back"
    for name in (None, 5, ["sampleFTA.json"], {"name": "sampleFTA.json"}, True):
        assert client.post("/api/examples/open", json={"name": name}).status_code == 400
    assert client.post("/api/examples/open", json={}).status_code == 400
    assert state_of(client) == before, "no refused request replaced the document"


def test_21_only_json_files_directly_in_the_folder_are_examples(client, tmp_path, monkeypatch):
    folder = tmp_path / "examples"
    (folder / "nested").mkdir(parents=True)
    shutil.copyfile(EXAMPLES / "sampleFTA.json", folder / "good.json")
    shutil.copyfile(EXAMPLES / "sampleFTA.json", folder / "nested" / "deep.json")
    shutil.copyfile(EXAMPLES / "sampleFTA.json", folder / ".hidden.json")
    (folder / "notes.txt").write_text("not an analysis", encoding="utf-8")
    (folder / "broken.json").write_text("{ not json", encoding="utf-8")
    (folder / "folder.json").mkdir()
    monkeypatch.setattr(config, "EXAMPLES_DIR", folder)

    listed = body(client.get("/api/examples"))["examples"]
    assert [entry["name"] for entry in listed] == ["broken.json", "good.json"]
    assert listed[0]["title"] is None, "an unreadable file keeps its place and says nothing"
    for name in ("deep.json", "nested/deep.json", ".hidden.json", "notes.txt", "folder.json", "nested"):
        assert client.post("/api/examples/open", json={"name": name}).status_code == 404, name
    broken = client.post("/api/examples/open", json={"name": "broken.json"})
    assert broken.status_code == 400 and error(broken)["code"] == "INVALID_JSON"
    assert client.post("/api/examples/open", json={"name": "good.json"}).status_code == 200

    monkeypatch.setattr(config, "EXAMPLES_DIR", tmp_path / "missing")
    assert body(client.get("/api/examples"))["examples"] == []
    assert client.post("/api/examples/open", json={"name": "good.json"}).status_code == 404


@requires_symlinks
def test_21_a_link_in_the_examples_folder_is_not_followed(client, tmp_path, monkeypatch):
    folder = tmp_path / "examples"
    folder.mkdir()
    shutil.copyfile(EXAMPLES / "sampleFTA.json", folder / "good.json")
    secret = tmp_path / "outside" / "secret.json"
    os.symlink(secret, folder / "link.json")
    monkeypatch.setattr(config, "EXAMPLES_DIR", folder)
    assert [entry["name"] for entry in body(client.get("/api/examples"))["examples"]] == ["good.json"]
    assert client.post("/api/examples/open", json={"name": "link.json"}).status_code == 404


def test_25_the_sandbox_root_is_as_narrow_as_it_was(client, sandbox, tmp_path):
    """Nothing in this batch lets a request read or write outside the root."""
    secret = tmp_path / "outside" / "secret.json"
    for call in (
        lambda: client.post("/api/file/open", json={"path": str(secret)}),
        lambda: client.post("/api/file/save-as", json={"path": str(tmp_path / "outside" / "new.json")}),
        lambda: client.get("/api/fs/list", query_string={"path": str(tmp_path / "outside")}),
        # the examples live outside this sandbox too: the file endpoints still refuse them
        lambda: client.post("/api/file/open", json={"path": str(EXAMPLES / "sampleFTA.json")}),
        lambda: client.post("/api/file/save-as", json={"path": str(EXAMPLES / "sampleFTA.json")}),
    ):
        response = call()
        assert response.status_code == 400
        assert error(response)["code"] == "PATH_REJECTED" and error(response)["detail"]["reason"] == "outside_root"
    assert not (tmp_path / "outside" / "new.json").exists()
    assert state_of(client)["currentPath"] is None
    routes = {rule.rule for rule in client.application.url_map.iter_rules()}
    # Since 1.8.1 one endpoint can change the root, and it takes no path:
    # the person picks the folder in a dialog the server opens
    # (test_known_issues_1_8.py proves a request cannot name one).
    assert {rule for rule in routes if "root" in rule} == {"/api/fs/root/choose"}
    assert "fs_root" not in _read(REPO / "fta_web" / "user_prefs.py"), "the root is not a stored preference"


def test_25_the_refusal_says_how_to_start_the_editor_on_another_folder(client, sandbox, tmp_path, monkeypatch):
    secret = tmp_path / "outside" / "secret.json"
    refusal = error(client.post("/api/file/open", json={"path": str(secret)}))
    command = 'uv run python fta_web/run.py --root "<folder>"'
    assert refusal["detail"] == {"reason": "outside_root", "root": str(sandbox.resolve()), "relaunch": command}
    assert command in refusal["message"] and str(sandbox.resolve()) in refusal["message"]
    assert str(secret) not in refusal["message"] and "secret" not in refusal["message"]
    assert "outside" not in json.dumps(refusal["detail"]).replace("outside_root", "")

    # the packaged app names its own file, and never its folder
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Program Files" / "FTA" / "fta_editor.exe"))
    packaged = error(client.post("/api/file/open", json={"path": str(secret)}))
    assert packaged["detail"]["relaunch"] == 'fta_editor.exe --root "<folder>"'
    assert "Program Files" not in json.dumps(packaged)

    dialog = _read(STATIC / "filedialog.js")
    # Since 1.8.1 the function takes one more argument (whether the folder
    # can be changed from the page) and the outside_root test has a name.
    text = _function(dialog, "function errorText(err, fallbackKey, sources, canChoose)")
    assert "isOutsideRoot(err) && detail.relaunch" in text
    assert "detail.reason === 'outside_root'" in _function(dialog, "function isOutsideRoot(err)")
    assert "t('file.errOutsideRoot', { root: detail.root || '', command: detail.relaunch })" in text


def test_25_the_load_dialog_offers_the_examples_and_this_computer():
    main = _read(STATIC / "main.js")
    load = _function(main, "async function actionLoad()")
    assert "pickPath({ mode: 'open', sources: documentSources() })" in load
    assert "actionOpenExample(true)" in load and "pickImportFile()" in load
    sources = _function(main, "function documentSources()")
    assert "id: 'example'" in sources and "id: 'import'" in sources
    example = _function(main, "async function actionOpenExample(asked)")
    assert example.index("leaveDocument('open')") < example.index("api.get('/examples')") < example.index("api.post('/examples/open', force ? { name, force: true } : { name })")
    assert "await adoptDocument(payload);" in example
    dialog = _read(STATIC / "filedialog.js")
    assert "onclick: () => close({ source: String(source.id) })" in dialog


# =============================================================================================
# 26: the file dialog starts where the last file was
# =============================================================================================


def home_of(client):
    # root and cwd; since 1.8.1 the answer also says whether the folder can
    # be changed from the page (canChooseRoot, relaunch), which are not paths
    return {key: Path(value) for key, value in body(client.get("/api/fs/home")).items()
            if key in ("root", "cwd")}


def test_26_the_folder_of_the_last_open_or_save_is_where_an_untitled_document_starts(client, sandbox, per_user_home):
    assert home_of(client) == {"root": sandbox, "cwd": sandbox}
    assert not user_prefs.prefs_file().exists()

    client.post("/api/file/open", json={"path": str(sandbox / "sub" / "inner.json")})
    assert home_of(client)["cwd"] == sandbox / "sub", "the open document's own folder, as before"
    assert user_prefs.prefs_file() == per_user_home / "ui_prefs.json"
    assert Path(json.loads(_read(user_prefs.prefs_file()))["lastFolder"]) == sandbox / "sub"

    client.post("/api/new", json={"force": True})
    assert home_of(client) == {"root": sandbox, "cwd": sandbox / "sub"}, "remembered for a document with no file"

    add(client)
    client.post("/api/file/save-as", json={"path": str(sandbox / "at root.json")})
    client.post("/api/new", json={"force": True})
    assert home_of(client)["cwd"] == sandbox, "Save As moves it too"

    # an example and an import have no folder to remember
    client.post("/api/examples/open", json={"name": "sampleFTA.json"})
    assert Path(user_prefs.last_folder()) == sandbox
    assert home_of(client)["cwd"] == sandbox


def test_26_a_remembered_folder_is_confined_like_any_client_path(client, sandbox, tmp_path, per_user_home):
    per_user_home.mkdir(parents=True, exist_ok=True)
    prefs = per_user_home / "ui_prefs.json"
    outside = tmp_path / "outside"
    for stored in (
        str(outside), str(outside / "secret.json"), str(sandbox / ".." / "outside"), "../outside",
        str(sandbox / "gone"), str(sandbox / "sample.json"), "\\\\server\\share\\x", "", "   ", "a\x00b",
        "x" * 5000, 7, None, ["x"], {"a": 1},
    ):
        prefs.write_text(json.dumps({"lastFolder": stored}), encoding="utf-8")
        response = client.get("/api/fs/home")
        assert response.status_code == 200, stored
        assert home_of(client)["cwd"] == sandbox, "falls back to the root: %r" % (stored,)
    for junk in ("{ not json", "[1, 2]", '"text"', "", "null", "{" * 20000):
        prefs.write_text(junk, encoding="utf-8")
        assert home_of(client)["cwd"] == sandbox
        assert state_of(client)["prefs"] == {"aiPanelCollapsed": False}
    prefs.write_text(json.dumps({"lastFolder": str(sandbox / "sub"), "pad": "x" * 70000}), encoding="utf-8")
    assert home_of(client)["cwd"] == sandbox, "a file this module did not write is not read"
    # a relative value means relative to the root, as for any client path
    prefs.write_text(json.dumps({"lastFolder": "sub"}), encoding="utf-8")
    assert home_of(client)["cwd"] == sandbox / "sub"


def test_26_remembering_never_fails_the_open_or_the_save(client, sandbox, tmp_path, monkeypatch):
    # A per-user folder that cannot be made: its place is taken by a file.
    blocked = tmp_path / "not_a_folder"
    blocked.write_text("in the way", encoding="utf-8")
    monkeypatch.setattr(AICredentialManager, "CREDENTIALS_DIR", blocked)
    opened = client.post("/api/file/open", json={"path": str(sandbox / "sub" / "inner.json")})
    assert opened.status_code == 200
    add(client)
    assert client.post("/api/file/save-as", json={"path": str(sandbox / "x.json")}).status_code == 200
    assert user_prefs.last_folder() is None
    assert home_of(client)["cwd"] == sandbox
    assert body(client.post("/api/prefs", json={"aiPanelCollapsed": True}))["prefs"] == {"aiPanelCollapsed": False}
    assert blocked.read_text(encoding="utf-8") == "in the way"


def test_26_a_write_that_fails_leaves_the_old_file_and_no_temporary_one(per_user_home):
    assert user_prefs.remember_folder("C:/somewhere") is True
    kept = _read(user_prefs.prefs_file())
    assert user_prefs._write({"lastFolder": object()}) is False  # not JSON: the dump raises
    assert _read(user_prefs.prefs_file()) == kept
    assert [p.name for p in per_user_home.iterdir()] == ["ui_prefs.json"]
    for bad in ("", "   ", None, "a\x00b", "x" * 5000):
        assert user_prefs.remember_folder(bad) is False
    assert _read(user_prefs.prefs_file()) == kept


def test_26_the_prefs_live_beside_the_credentials_and_tests_do_not_touch_the_real_home(per_user_home):
    assert user_prefs.prefs_file().parent == Path(AICredentialManager.CREDENTIALS_DIR) == per_user_home
    assert Path.home() not in user_prefs.prefs_file().parents or str(per_user_home).startswith(str(Path.home()))
    assert (Path.home() / ".fta_editor") != per_user_home
    src = _read(REPO / "fta_web" / "user_prefs.py")
    assert "try:  # normal package import" in src and "except ImportError:" in src
    spec = _read(REPO / "build" / "fta_editor.spec")
    assert '"user_prefs",' in spec[spec.index("hiddenimports = ["):]


# =============================================================================================
# 27: first launch, and the AI panel folds away
# =============================================================================================


def test_27_the_page_remembers_the_folded_ai_panel_on_the_server(client, per_user_home):
    assert state_of(client)["prefs"] == {"aiPanelCollapsed": False}
    answer = body(client.post("/api/prefs", json={"aiPanelCollapsed": True}))
    assert answer == {"ok": True, "prefs": {"aiPanelCollapsed": True}}
    assert state_of(client)["prefs"] == {"aiPanelCollapsed": True}
    reset_state()  # "the next launch"
    get_state().fs_root = per_user_home.parent / "sandbox"
    assert state_of(client)["prefs"] == {"aiPanelCollapsed": True}
    assert body(client.post("/api/prefs", json={}))["prefs"] == {"aiPanelCollapsed": True}
    # not part of the document
    before = revision_of(client)
    client.post("/api/prefs", json={"aiPanelCollapsed": False})
    assert revision_of(client) == before and state_of(client)["canUndo"] is False


@pytest.mark.parametrize("payload,field", [
    ({"aiPanelCollapsed": "true"}, "aiPanelCollapsed"),
    ({"aiPanelCollapsed": 1}, "aiPanelCollapsed"),
    ({"aiPanelCollapsed": None}, "aiPanelCollapsed"),
    ({"lastFolder": "C:\\\\"}, "lastFolder"),
    ({"aiPanelCollapsed": True, "fs_root": "/"}, "fs_root"),
    ({"__proto__": 1}, "__proto__"),
])
def test_27_only_known_preferences_of_the_right_type_are_stored(client, payload, field):
    response = client.post("/api/prefs", json=payload)
    assert response.status_code == 400 and error(response)["code"] == "INVALID_FIELD"
    assert error(response)["detail"] == {"field": field}
    assert not user_prefs.prefs_file().exists(), "a refused request writes nothing"
    assert client.post("/api/prefs", data="[1]", content_type="application/json").status_code == 400


@needs_node
def test_27_the_hint_is_for_a_new_analysis_nobody_has_touched():
    src = _read(STATIC / "main.js")
    blank = {"tree": {"id": "root", "children": []}, "dirty": False, "currentPath": None,
             "canUndo": False, "canRedo": False}
    cases = [
        blank,
        dict(blank, dirty=True),
        dict(blank, currentPath="a.json"),
        dict(blank, canUndo=True),
        dict(blank, canRedo=True),
        dict(blank, tree={"id": "root", "children": [{"id": "root_0"}]}),
        dict(blank, tree={"id": "root"}),
        None,
    ]
    got = _node(_function(src, "function isUntouchedDocument(state)")
                + "\nconsole.log(JSON.stringify(%s.map(isUntouchedDocument)));" % json.dumps(cases))
    assert got == [True, False, False, False, False, False, True, False]
    shell = _function(src, "function renderShell(state)")
    assert "firstRun.hidden = firstRunDismissed || !isUntouchedDocument(state);" in shell
    wire = _function(src, "function wireFirstRun()")
    assert wire.index("store.select(rootId());") < wire.index("actionEdit();")
    assert "actionOpenExample(false)" in wire

    html = _read(INDEX)
    hint = html[html.index('id="first-run"'):html.index('id="tree-root"')]
    assert "hidden" in hint.split(">")[0]
    assert 'id="first-run-name"' in hint and 'data-i18n="firstrun.name"' in hint
    assert 'id="first-run-example"' in hint and 'data-i18n="firstrun.example"' in hint
    assert 'id="btn-ai-collapse"' in html and 'aria-controls="ai-root"' in html
    assert '[data-ai-collapsed="1"] #ai-root' in _read(CSS)
    collapse = _function(src, "function setAiCollapsed(on)")
    assert "api.post('/prefs', { aiPanelCollapsed: aiCollapsed })" in collapse
    assert "aiCollapsed = Boolean(state.prefs && state.prefs.aiPanelCollapsed);" in _function(src, "async function boot()")


def test_27_the_docs_call_the_add_button_add():
    """The web app's button is "Add". "Add Node" is the desktop app's button
    ("(A)dd Node"), and only its own shortcut list may say so."""
    for name in ("QUICKSTART.md", "README.md"):
        assert "Add Node" not in _read(REPO / name), name
    guide = _read(DOCS / "USER_GUIDE.md")
    desktop = guide[guide.index("### Desktop app\n"):guide.index("## Examples\n")]
    assert guide.count("Add Node") == desktop.count("Add Node") == 1
    assert "Click the **Add** button (or press Ctrl+A)" in guide


# =============================================================================================
# 28: exports say what they are, and a file from this computer can be opened
# =============================================================================================


def test_28_exports_are_a_labelled_group_and_the_toast_says_copy():
    html = _read(INDEX)
    group = html[html.index('class="actionbar__group"'):html.index('class="statusline"')]
    assert 'role="group"' in group and 'aria-labelledby="export-label"' in group
    assert 'id="export-label" data-i18n="bar.exportGroup"' in group
    assert [m for m in re.findall(r'data-action="([a-z-]+)"', group)] == ["json", "xml", "excel", "render"]
    assert 'data-action="save"' not in group

    src = _read(STATIC / "main.js")
    said = _function(src, "function toastDownloaded(name)")
    assert "t('msg.exportedCopy', { name, file })" in said and "t('msg.exportedCopyUntitled', { name })" in said
    assert "toastDownloaded(name);" in _function(src, "async function actionExport(kind)")
    assert _function(src, "async function actionRenderImage()").count("toastDownloaded(name);") == 2
    sys.path.insert(0, str(REPO / "fta_web" / "tests"))
    import test_catalog_parity

    en, ja = test_catalog_parity._catalogs()
    for key in ("msg.exportedCopy", "msg.exportedCopyUntitled"):
        assert "copy" in en[key] and "{name}" in en[key] and "{name}" in ja[key]
    assert "unchanged" in en["msg.exportedCopy"] and "{file}" in en["msg.exportedCopy"]
    assert "not saved" in en["msg.exportedCopyUntitled"]


def test_28_a_file_from_this_computer_goes_through_the_unsaved_prompt_and_opens_untitled(client):
    src = _read(STATIC / "main.js")
    imp = _function(src, "async function importFile(file, asked)")
    assert imp.index("if (!asked) {") < imp.index("leaveDocument('open')") < imp.index("api.upload('/import/json', file, 'file', force ? { force: 'true' } : null)")
    assert "await adoptDocument(payload);" in imp
    drop = _function(src, "function wireFileDrop()")
    assert "importFile(file, true)" in drop, "the picker was reached through Load, which has asked"
    assert "importFile(file, false)" in drop, "a dropped file has not been asked about"
    # a file dropped anywhere on the page is kept from the browser
    assert drop.count("event.preventDefault();") == 2 and "panel.contains(event.target)" in drop
    html = _read(INDEX)
    assert re.search(r'<input type="file" id="import-file" accept="\.json,application/json" hidden', html)
    api = _read(STATIC / "api.js")
    upload = _function(api, "async function upload(path, file, field, fields)")
    assert "buildInit('POST', undefined, 'application/json')" in upload, "the session token is sent"
    assert "new FormData()" in upload and "Content-Type" not in upload

    # what the endpoint the page posts to does with it
    add(client, name="left over")
    upload = {"file": (io.BytesIO(_read(EXAMPLES / "sampleFTA.json").encode("utf-8")), "from my desktop.json"),
              "force": "true"}  # the node above is unsaved work (refused without it since 1.8.1)
    opened = body(client.post("/api/import/json", data=upload, content_type="multipart/form-data"))
    assert opened["currentPath"] is None and opened["dirty"] is True
    assert client.post("/api/file/save", json={}).status_code == 409
    assert user_prefs.last_folder() is None, "an upload has no folder to remember"


# =============================================================================================
# 29: unsaved changes -> Cancel / Discard / Save and continue
# =============================================================================================


@needs_node
def test_29_save_and_continue_goes_ahead_only_when_the_save_happened():
    src = _read(STATIC / "main.js")
    script = (
        "const log = [];\n"
        "const store = { state: null };\n"
        "let answer = 'cancel'; let saves = true; let cleans = true;\n"
        "const t = (key) => key;\n"
        "const toast = (message) => log.push('toast:' + message);\n"
        "async function askUnsaved(kind) { log.push('ask:' + kind); return answer; }\n"
        "async function actionSave() { log.push('save'); if (saves && cleans) store.state.dirty = false; return saves; }\n"
        + _function(src, "async function leaveDocument(kind)") + "\n"
        "const run = async (dirty, a, s, c) => { log.length = 0; store.state = { dirty }; answer = a; saves = s; cleans = c;"
        " const go = await leaveDocument('open'); return [go, log.slice()]; };\n"
        "console.log(JSON.stringify([\n"
        "  await run(false, 'cancel', true, true),\n"
        "  await run(true, 'cancel', true, true),\n"
        "  await run(true, 'discard', true, true),\n"
        "  await run(true, 'save', true, true),\n"
        "  await run(true, 'save', false, true),\n"
        "  await run(true, 'save', true, false),\n"
        "  await run(true, 'something else', true, true),\n"
        "]));"
    )
    assert _node(script, module=True) == [
        [True, []],                                                  # nothing unsaved: no question
        [False, ["ask:open"]],
        [True, ["ask:open"]],
        [True, ["ask:open", "save"]],
        [False, ["ask:open", "save", "toast:confirm.notSaved"]],     # Save As was cancelled, or refused
        [False, ["ask:open", "save", "toast:confirm.notSaved"]],     # "saved", yet still dirty: do not go on
        [False, ["ask:open"]],
    ]


def test_29_the_prompt_has_three_answers_and_new_load_example_and_drop_all_use_it():
    src = _read(STATIC / "main.js")
    ask = _function(src, "async function askUnsaved(kind)")
    assert "dialogs.choiceDialog(" in ask and "cancelValue: 'cancel'" in ask
    discard = ask.index("value: 'discard'")
    save = ask.index("value: 'save'")
    assert discard < save
    assert "danger: true" in ask[discard:save]
    assert "primary: true, focus: true" in ask[save:ask.index("\n", save)], "Enter saves; it does not discard"
    for owner, call in (
        ("async function actionNew()", "leaveDocument('new')"),
        ("async function actionLoad()", "leaveDocument('open')"),
        ("async function actionOpenExample(asked)", "leaveDocument('open')"),
        ("async function importFile(file, asked)", "leaveDocument('open')"),
    ):
        assert call in _function(src, owner), owner
    new = _function(src, "async function actionNew()")
    assert "let force = Boolean(store.state && store.state.dirty);" in new, "saved means nothing is forced"
    # Save tells its caller whether it saved
    assert "return true;" in _function(src, "async function actionSave()")
    save_as = _function(src, "async function actionSaveAs()")
    assert "if (!path) return false;" in save_as and "return true;" in save_as

    dialogs = _read(STATIC / "dialogs.js")
    choice = _function(dialogs, "export function choiceDialog(message, options)")
    assert "dataset: { role: 'cancel' }" in choice and "if (spec.focus) first = button;" in choice
    assert "first.focus();" in choice and "return modal.done;" in choice


# =============================================================================================
# 18: the "not connected" screen
# =============================================================================================


def _index_page(tmp_path):
    sys.path.insert(0, str(REPO / "fta_web"))
    import app as app_module  # the launcher's own module names

    built = app_module.create_app(token="t" * 40, port=8765, fs_root=tmp_path)
    return built.test_client().get("/", base_url="http://127.0.0.1:8765").get_data(as_text=True)


def test_18_the_server_supplies_the_command_that_starts_it_again(tmp_path, monkeypatch):
    assert runtime_paths.launch_command() == "uv run python fta_web/run.py"
    page = _index_page(tmp_path)
    assert '<code class="overlay__cmd" id="overlay-cmd">uv run python fta_web/run.py</code>' in page
    assert 'data-packaged="0"' in page
    assert "python3 fta_web/run.py" not in page

    install = tmp_path / "Program Files" / "FTA Editor"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(install / "fta_editor.exe"))
    assert runtime_paths.launch_command() == "fta_editor.exe"
    packaged = _index_page(tmp_path)
    assert '<code class="overlay__cmd" id="overlay-cmd">fta_editor.exe</code>' in packaged
    assert 'data-packaged="1"' in packaged
    # this page is served without the token: it must not say where the app is installed
    assert "Program Files" not in packaged and str(tmp_path) not in packaged


def test_18_the_screen_is_in_plain_words_in_both_languages():
    sys.path.insert(0, str(REPO / "fta_web" / "tests"))
    import test_catalog_parity

    en, ja = test_catalog_parity._catalogs()
    for key in ("session.title", "session.body", "session.hint", "session.hintExe"):
        assert key in en and key in ja
        for jargon in ("session key", "one-time", "token", "launcher printed"):
            assert jargon not in en[key], (key, jargon)
    assert en["session.title"] == "This tab is not connected to the editor"
    assert "double-click" in en["session.hintExe"]
    html = _read(INDEX)
    overlay = html[html.index('id="blocking-overlay"'):html.index('<script type="module"')]
    assert "session key" not in overlay and "This tab is not connected to the editor" in overlay
    src = _read(STATIC / "main.js")
    assert "overlay.dataset.packaged === '1' ? 'session.hintExe' : 'session.hint'" in _function(src, "function sessionHintKey()")
    assert "t(sessionHintKey())" in _function(src, "function onSessionInvalid()")


# =============================================================================================
# 22: Cut Sets when a limit leaves nothing
# =============================================================================================


def test_22_a_limit_that_cuts_every_set_away_is_reported_as_truncation(client):
    client.patch("/api/nodes/root", json={"logicGate": "AND"})
    add(client, name="Pump A", probability=0.01)
    add(client, name="Pump B", probability=0.02)
    full = body(client.post("/api/analysis/cutsets", json={}))
    assert full["total"] == 1 and full["truncated"] is False
    tight = body(client.post("/api/analysis/cutsets", json={"maxOrder": 1}))
    # what the page keys its wording on: nothing found, and said to be cut short
    assert tight["total"] == 0 and tight["cutSets"] == [] and tight["mcub"] == 0
    assert tight["truncated"] is True and tight["truncatedBy"] == ["order"]
    assert tight["treeWalk"] == pytest.approx(0.0002)
    # the per-run limit is not the document's
    assert state_of(client)["analysis"]["cutsets"]["maxOrder"] != 1


@needs_node
def test_22_none_within_these_limits_is_not_the_top_event_cannot_occur():
    src = _read(STATIC / "tabs" / "cutsets.js")
    cases = [
        None,
        {"cutSets": [], "total": 0, "returned": 0, "truncated": False},
        {"cutSets": [], "total": 0, "returned": 0, "truncated": True, "truncatedBy": ["order"]},
        {"cutSets": [], "total": 2, "returned": 0, "truncated": True},
        {"cutSets": [{"rank": 1, "events": []}], "total": 1, "returned": 1, "truncated": True},
    ]
    script = (_function(src, "function emptyMessageKey(result)") + "\n"
              + _function(src, "function nothingWithinLimits(result)") + "\n"
              + "console.log(JSON.stringify(%s.map((r) => [emptyMessageKey(r), nothingWithinLimits(r)])));"
              % json.dumps(cases))
    assert _node(script) == [
        ["cutsets.notRun", False],
        ["cutsets.none", False],
        ["cutsets.noneWithinLimits", True],
        [None, False],
        [None, False],
    ]
    summary = _function(src, "function paintSummary()")
    hidden = summary[summary.index("if (nothingWithinLimits(result)) {"):summary.index("} else {")]
    assert "cutsets.treeWalk" in hidden
    assert "cutsets.mcub" not in hidden and "cutsets.rare" not in hidden and "cutsets.count" not in hidden


def test_22_a_typed_limit_is_marked_this_run_only_with_a_reset():
    src = _read(STATIC / "tabs" / "cutsets.js")
    assert "dataset: { role: 'run-only' }, hidden: true" in src
    assert "dataset: { role: 'reset-limits' }, hidden: true" in src
    over = _function(src, "function overridden()")
    assert "!edited.has(input) || typed === ''" in over, "a blank box means the document value"
    paint = _function(src, "function paintRunOnly()")
    assert "runOnly.hidden = inputs.length === 0;" in paint and "resetBtn.hidden = inputs.length === 0;" in paint
    reset = _function(src, "function resetLimits()")
    assert reset.index("edited.clear();") < reset.index("paintToolbar();") < reset.index("run();")
    assert "resetBtn.addEventListener('click', () => resetLimits());" in src
    # the mark follows the typing, not only the next run
    assert re.search(r"input\.addEventListener\('input', \(\) => \{\s*edited\.add\(input\);\s*paintRunOnly\(\);", src)


# =============================================================================================
# 24: undo and redo say what they did
# =============================================================================================


def _steps(pairs):
    return _docutil("pairs.map(([a, b]) => d.describeStep(a, b))", pairs=pairs)


@needs_node
def test_24_a_step_is_described_from_the_tree_before_and_after(client):
    """Real documents on both sides: each edit made through the API."""
    states = [state_of(client)]

    def snap():
        states.append(state_of(client))
        return len(states) - 1

    a = add(client, name="Pump A", probability=0.01)["nodeId"]
    i_add = snap()
    seal = add(client, parent=a, name="Seal leak", probability=0.02)["nodeId"]
    add(client, parent=a, name="Bearing", probability=0.03)
    b = add(client, name="Pump B", probability=0.04)["nodeId"]
    i_three = snap()
    client.patch("/api/nodes/" + seal, json={"name": "Seal leaks", "probability": 0.5})
    i_edit = snap()
    client.post("/api/nodes/%s/move" % seal, json={"newParentId": b})
    i_move = snap()
    client.post("/api/nodes/%s/move" % b, json={"newParentId": "root", "index": 0})
    i_order = snap()
    client.delete("/api/nodes/" + a)
    i_delete = snap()
    client.post("/api/metadata", json={"title": "Cooling", "mode": "ETA"})
    i_meta = snap()
    client.post("/api/metadata", json={"mode": "FTA"})
    i_before_settings = snap()
    client.post("/api/analysis/settings", json={"cutsets": {"maxOrder": 3}})
    i_settings = snap()

    pairs = [
        (states[0], states[i_add]),               # a node added
        (states[i_add], states[0]),               # ...and undone
        (states[i_three], states[i_edit]),        # two fields of one node
        (states[i_edit], states[i_move]),         # another parent
        (states[i_move], states[i_order]),        # another place under the same parent
        (states[i_order], states[i_delete]),      # a subtree deleted
        (states[i_delete], states[i_order]),      # ...and undone
        (states[i_delete], states[i_meta]),       # title and mode
        (states[i_before_settings], states[i_settings]),  # a setting
        (states[i_three], states[i_three]),       # nothing
    ]
    got = _steps(pairs)
    picked = [(g["kind"], g["names"], g["count"], sorted(g["fields"]), g["parentName"], g["selectId"]) for g in got]
    assert picked == [
        ("added", ["Pump A"], 1, [], None, a),
        ("removed", ["Pump A"], 1, [], None, "root"),
        ("changed", ["Seal leaks"], 1, ["name", "probability"], None, seal),
        ("moved", ["Seal leaks"], 1, [], "Pump B", seal),
        ("moved", ["Pump B"], 1, [], states[0]["tree"]["name"], b),
        ("removed", ["Pump A"], 2, [], None, "root"),          # Pump A and Bearing; named by its top
        ("added", ["Pump A"], 2, [], None, a),
        ("metadata", [], 0, ["mode", "title"], None, None),
        ("settings", [], 0, [], None, None),
        ("none", [], 0, [], None, None),
    ]


@needs_node
def test_24_where_the_selection_goes_when_the_node_is_gone():
    def leaf(node_id, name):
        return {"id": node_id, "name": name, "probability": 0.1, "children": []}

    def tree(*children):
        return {"tree": {"id": "root", "name": "Top", "probability": 1, "children": list(children)}}

    gate = dict(leaf("g", "Gate"), children=[leaf("g_0", "Inner"), leaf("g_1", "Other")])
    deep = dict(leaf("g", "Gate"), children=[dict(leaf("g_0", "Inner"), children=[leaf("g_0_0", "Deepest")])])
    rewrite = tree(leaf("n1", "New one"), leaf("n2", "New two"))
    got = _steps([
        (tree(gate), tree(dict(gate, children=[leaf("g_1", "Other")]))),    # a leaf under a gate goes
        (tree(deep), tree(leaf("x", "Keep"))),                                # replaced: both sides differ
        (tree(deep, leaf("x", "Keep")), tree(leaf("x", "Keep"))),             # a whole branch goes
        (tree(gate), rewrite),                                                # an AI rewrite
        (tree(gate), tree(dict(gate, calculatedProbability=0.5))),            # only a derived value
        ({}, tree(gate)),                                                     # no document before
    ])
    assert [(g["kind"], g["selectId"]) for g in got] == [
        ("removed", "g"),          # the former parent, not the top event
        ("replaced", "x"),
        ("removed", "root"),
        ("replaced", "n1"),
        ("none", None),            # calculatedProbability is not the node's own content
        ("added", "root"),
    ]
    assert (got[3]["added"], got[3]["removed"]) == (2, 3)
    assert got[2]["count"] == 3 and got[2]["names"] == ["Gate"]


@needs_node
def test_24_the_toast_names_the_action_that_was_undone():
    src = _read(STATIC / "main.js")
    script = (
        "const log = [];\n"
        # the catalog has a label for "name" and none for "zzz" (t answers the key itself then)
        "const t = (key, vars) => (key === 'history.field.name' ? 'Name' : key + (vars ? JSON.stringify(vars) : ''));\n"
        "const toast = (message) => log.push(message);\n"
        "let step = null;\n"
        "const describeStep = () => step;\n"
        "const store = { findNode: (id) => (id === 'gone' ? null : { id }), jumpTo: (id) => log.push('select:' + id) };\n"
        + _function(src, "function fieldNames(fields)") + "\n"
        + _function(src, "function announceStep(kind, before, after)") + "\n"
        "const base = { names: [], count: 0, added: 0, removed: 0, fields: [], parentName: null, selectId: null };\n"
        "const run = (kind, s) => { log.length = 0; step = { ...base, ...s }; announceStep(kind, {}, {}); return log.slice(); };\n"
        "console.log(JSON.stringify([\n"
        "  run('undo', { kind: 'removed', names: ['A'], count: 1, selectId: 'p' }),\n"
        "  run('redo', { kind: 'added', names: ['A'], count: 1, selectId: 'a' }),\n"
        "  run('undo', { kind: 'added', names: ['A'], count: 3, selectId: 'a' }),\n"
        "  run('redo', { kind: 'removed', names: ['A'], count: 1, selectId: 'gone' }),\n"
        "  run('undo', { kind: 'changed', names: ['A'], count: 1, fields: ['name', 'zzz'], selectId: 'a' }),\n"
        "  run('undo', { kind: 'changed', names: ['A', 'B'], count: 2, fields: ['probability'], selectId: 'a' }),\n"
        "  run('undo', { kind: 'replaced', added: 2, removed: 5, selectId: 'n' }),\n"
        "  run('redo', { kind: 'replaced', added: 2, removed: 5, selectId: 'n' }),\n"
        "  run('undo', { kind: 'none' }),\n"
        "]));"
    )
    assert _node(script) == [
        ['history.undid{"what":"history.add1{\\"name\\":\\"A\\"}"}', "select:p"],          # undo of an Add
        ['history.redid{"what":"history.add1{\\"name\\":\\"A\\"}"}', "select:a"],
        ['history.undid{"what":"history.deleteN{\\"n\\":3}"}', "select:a"],               # undo of a Delete
        ['history.redid{"what":"history.delete1{\\"name\\":\\"A\\"}"}'],                   # nothing to select
        ['history.undid{"what":"history.change1{\\"name\\":\\"A\\",\\"fields\\":\\"Name, zzz\\"}"}', "select:a"],
        ['history.undid{"what":"history.changeN{\\"n\\":2}"}'],                           # many nodes: stay put
        ['history.undid{"what":"history.rewrite{\\"added\\":5,\\"removed\\":2}"}', "select:n"],
        ['history.redid{"what":"history.rewrite{\\"added\\":2,\\"removed\\":5}"}', "select:n"],
        ['history.undid{"what":"history.step"}'],
    ]
    history = _function(src, "async function actionHistory(kind)")
    assert history.index("const before = store.state;") < history.index("api.post('/' + kind") < history.index(
        "announceStep(kind, before, store.state);")


# =============================================================================================
# the new endpoints are behind the session token, and documented
# =============================================================================================

PORT = 8765
BASE_URL = "http://127.0.0.1:%d" % PORT
TOKEN = "test-token-0123456789-abcdefghijklmnopqrstuvwxyz"

NEW_ENDPOINTS = [
    ("get", "/api/revision", None),
    ("post", "/api/prefs", {"aiPanelCollapsed": True}),
    ("get", "/api/examples", None),
    ("post", "/api/examples/open", {"name": "sampleFTA.json"}),
    ("post", "/api/ai/update/apply", {"id": "x"}),
    ("post", "/api/ai/update/discard", {}),
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
    def call(headers):
        kwargs = {"base_url": BASE_URL, "headers": headers}
        if payload is not None:
            kwargs["json"] = payload
        return getattr(guarded, method)(path, **kwargs)

    before = get_state().revision_fields()
    for headers, reason in (
        ({}, "missing_token"),
        ({config.TOKEN_HEADER: "wrong"}, "invalid_token"),
        ({config.TOKEN_HEADER: TOKEN, "Origin": "http://evil.example"}, "origin_not_allowed"),
    ):
        refused = call(headers)
        assert refused.status_code == 403, (path, headers)
        assert error(refused)["code"] == "FORBIDDEN" and error(refused)["detail"] == {"reason": reason}
    rebound = getattr(guarded, method)(path, base_url="http://evil.example:%d" % PORT,
                                       headers={config.TOKEN_HEADER: TOKEN}, json=payload)
    assert rebound.status_code == 403 and error(rebound)["detail"] == {"reason": "host_not_allowed"}
    # nothing happened: no document replaced, no preference written
    assert get_state().revision_fields() == before
    assert not user_prefs.prefs_file().exists()

    allowed = call({config.TOKEN_HEADER: TOKEN})
    assert allowed.status_code != 403
    assert allowed.headers["Cache-Control"] == "no-store"


def test_the_new_endpoints_are_in_the_api_reference_and_the_changelog():
    reference = _read(DOCS / "API_REFERENCE.md")
    for _method, path, _payload in NEW_ENDPOINTS:
        assert "`%s %s`" % (_method.upper(), path) in reference, path
    assert '"preview": true' in reference
    for key in ("revision", "documentSerial", "prefs"):
        assert "`%s`" % key in reference, key
    unreleased = _read(REPO / "CHANGELOG.md").split("## [1.8.0]", 1)[1].split("\n## [", 1)[0]
    for phrase in ("rescue copy", "Save and continue", "Open an example", "another tab", "This run only"):
        assert phrase in unreleased, phrase
