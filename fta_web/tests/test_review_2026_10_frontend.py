"""Frontend regressions from the 2026-10 review of the frontend core.

Covers the editor shell, tree, details panel, dialogs, file dialog, diagram,
store and API client (static/js/main.js, tree.js, details.js, dialogs.js,
filedialog.js, diagram.js, store.js, api.js). Each check pins one bug verified
in Chromium against the running app, following test_frontend_b2b.py /
test_frontend_dbg2.py: pure JS is extracted from the module source (or the
module imported) and executed under Node when it is on PATH; DOM wiring is
pinned at source level.
"""
import ast
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STATIC = REPO / "fta_web" / "static" / "js"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _node(script: str, *args: str):
    out = subprocess.run(["node", "-e", script, *args], capture_output=True, encoding="utf-8",
                         check=True).stdout
    return json.loads(out)


def _braced(src: str, start: int) -> str:
    """Source from `start` to the brace that closes the first `{` after it."""
    depth = 0
    for i in range(src.index("{", start), len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    raise AssertionError("unbalanced braces")


def test_node_output_is_read_as_utf8():
    """node writes UTF-8; text mode alone decodes with the locale's code page
    (cp1252 on Windows CI), which garbled the Japanese strings these checks
    compare. Every node call in this file names the encoding."""
    tree = ast.parse(_read(Path(__file__)))
    runs = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run" and getattr(node.func.value, "id", None) == "subprocess"
    ]
    assert runs
    for run in runs:
        encoding = {kw.arg: kw.value for kw in run.keywords}.get("encoding")
        assert isinstance(encoding, ast.Constant) and encoding.value == "utf-8", "line %d" % run.lineno


# ---- diagram.js: the SVG sanitiser holds on its own ----------------------------------
#
# Fed straight to sanitizeSvg(), a crafted SVG ran script in the app origin
# (an XHTML <iframe srcdoc> / <iframe src="javascript:">, also inside a
# lower-case <foreignobject>), re-pointed every relative fetch -- the API
# calls carrying the session token -- at another host (<base href="http://">),
# turned a vetted <a> into a javascript: link (<set attributeName="href">),
# and loaded from off the box (<style>@import</style>, <image href="http://">,
# style/fill url()). Reproduced in Chromium with DOMParser + importNode exactly
# as render() does; the shim below stands in for the DOM so the real function
# runs under Node.

_SVG_DOM_SHIM = r"""
const NS = {
  svg: 'http://www.w3.org/2000/svg',
  xhtml: 'http://www.w3.org/1999/xhtml',
  xlink: 'http://www.w3.org/1999/xlink',
};
class FakeAttr {
  constructor(qname, value, ns) {
    const colon = qname.indexOf(':');
    this.name = qname;
    this.localName = colon === -1 ? qname : qname.slice(colon + 1);
    this.namespaceURI = ns || null;
    this.value = value;
  }
}
const FAKE_DOC = {
  createTreeWalker(root) {
    const list = [];
    const walk = (n) => { for (const c of n.children) { list.push(c); walk(c); } };
    walk(root);
    let i = -1;
    return {
      get currentNode() { return list[i]; },
      nextNode() { i += 1; return i < list.length ? list[i] : null; },
    };
  },
};
class FakeElement {
  constructor(ns, qname, attrs, kids) {
    const colon = qname.indexOf(':');
    this.namespaceURI = ns;
    this.nodeName = qname;
    this.localName = colon === -1 ? qname : qname.slice(colon + 1);
    this.attributes = (attrs || []).map((a) => new FakeAttr(a[0], a[1], a[2]));
    this.children = [];
    this.parentNode = null;
    this.ownerDocument = FAKE_DOC;
    for (const kid of kids || []) { kid.parentNode = this; this.children.push(kid); }
  }
  removeAttributeNode(attr) { this.attributes = this.attributes.filter((a) => a !== attr); return attr; }
  remove() {
    const p = this.parentNode;
    if (p) p.children = p.children.filter((c) => c !== this);
    this.parentNode = null;
  }
  // Type selectors only, matched case-sensitively as in an XML document.
  querySelectorAll(selector) {
    const names = selector.split(',').map((s) => s.trim());
    const out = [];
    const walk = (n) => { for (const c of n.children) { if (names.indexOf(c.localName) !== -1) out.push(c); walk(c); } };
    walk(this);
    return out;
  }
}
globalThis.NodeFilter = { SHOW_ELEMENT: 1 };
const h = (ns, qname, attrs, kids) => new FakeElement(NS[ns], qname, attrs, kids);
const dump = (n) => [
  (n.namespaceURI === NS.svg ? '' : n.namespaceURI + ' ') + n.localName,
  Object.fromEntries(n.attributes.map((a) => [a.name, a.value])),
  n.children.map(dump),
];
"""

_SVG_CASES = r"""
const attack = h('svg', 'svg', [['onload', 'x()']], [
  h('xhtml', 'iframe', [['srcdoc', '<script>parent.pwned=1</script>']]),
  h('xhtml', 'iframe', [['src', 'javascript:parent.pwned=1']]),
  h('xhtml', 'base', [['href', 'http://evil.example/']]),
  h('xhtml', 'link', [['rel', 'stylesheet'], ['href', 'http://evil.example/x.css']]),
  h('svg', 'foreignobject', [], [h('xhtml', 'iframe', [['srcdoc', '<script>parent.pwned=1</script>']])]),
  h('svg', 'foreignObject', [], [h('xhtml', 'div', [])]),
  h('svg', 'script', [], []),
  h('svg', 'style', [], []),
  h('svg', 'a', [['id', 'link']], [
    h('svg', 'set', [['attributeName', 'href'], ['to', 'javascript:pwn()']]),
    h('svg', 'animate', [['attributeName', 'xlink:href'], ['values', 'javascript:pwn()']]),
    h('svg', 'text', [['x', '1']], []),
  ]),
  h('svg', 'rect', [
    ['id', 'box'],
    ['onclick', 'pwn()'],
    ['style', "background-image:image-set('http://evil.example/a.png' 1x)"],
    ['fill', 'u\\72 l(http://evil.example/f.svg#g)'],
    ['stroke', 'url( "http://evil.example/s.svg#g" )'],
  ]),
  h('svg', 'image', [['href', 'http://evil.example/i.png'], ['xlink:href', ' javascript:pwn()', NS.xlink]]),
  h('svg', 'use', [['href', 'data:image/svg+xml,<svg/>#a']]),
]);
const legit = h('svg', 'svg', [['width', '62pt'], ['viewBox', '0 0 62 44']], [
  h('svg', 'defs', [], [h('svg', 'linearGradient', [['id', 'l_0']], [h('svg', 'stop', [['offset', '0']])])]),
  h('svg', 'g', [['id', 'graph0'], ['class', 'graph'], ['transform', 'scale(1 1)']], [
    h('svg', 'title', [], []),
    h('svg', 'polygon', [['fill', 'url(#l_0)'], ['stroke', 'black'], ['points', '0,0 1,1']]),
    h('svg', 'g', [['id', 'node1'], ['class', 'node']], [
      h('svg', 'a', [['xlink:href', '#node1', NS.xlink]], [h('svg', 'text', [['x', '8'], ['font-family', 'Meiryo']], [])]),
      h('svg', 'use', [['href', ' #l_0']]),
    ]),
  ]),
]);
const before = JSON.stringify(dump(legit));
sanitizeSvg(attack);
sanitizeSvg(legit);
let rejectsHtmlRoot = false;
try {
  sanitizeSvg(h('xhtml', 'html', [], [h('xhtml', 'iframe', [['srcdoc', '<script>parent.pwned=1</script>']])]));
} catch (_err) {
  rejectsHtmlRoot = true;
}
console.log(JSON.stringify({ attack: dump(attack), legitUnchanged: JSON.stringify(dump(legit)) === before, rejectsHtmlRoot }));
"""


def _sanitizer_source() -> str:
    """sanitizeSvg plus the constants and helpers it uses, from diagram.js."""
    src = _read(STATIC / "diagram.js")
    parts = [
        m.group(0)
        for m in re.finditer(r"^const (?:SVG_NS|UNSAFE_SVG_ELEMENTS|SAFE_HREF) = .*?;$", src, re.M | re.S)
    ]
    for name in ("cssUnescape", "hasForeignUrl"):
        at = src.find("function %s(" % name)
        if at != -1:
            parts.append(_braced(src, at))
    parts.append(_braced(src, src.index("function sanitizeSvg(root)")))
    return "\n".join(parts)


@needs_node
def test_svg_sanitiser_strips_script_navigation_and_off_box_loads():
    got = _node(_SVG_DOM_SHIM + _sanitizer_source() + _SVG_CASES)
    tag, attrs, kids = got["attack"]
    assert tag == "svg" and attrs == {}, "the root's onload must go"
    # Nothing outside the SVG namespace, nothing that runs script or rewrites
    # an href: only the <a> (with its text), the rect, the image and the use.
    assert [k[0] for k in kids] == ["a", "rect", "image", "use"], kids
    link, rect, image, use = kids
    assert link == ["a", {"id": "link"}, [["text", {"x": "1"}, []]]]
    assert rect == ["rect", {"id": "box"}, []], "event handler, style and off-box url() attributes"
    assert image == ["image", {}, []], "no remote or javascript: href"
    assert use == ["use", {}, []], "no data: href"
    assert got["legitUnchanged"], "Graphviz output and same-document references must survive"
    assert got["rejectsHtmlRoot"], "a document whose root is not SVG is refused, not imported"


def test_sanitiser_runs_before_the_svg_is_imported():
    src = _read(STATIC / "diagram.js")
    body = _braced(src, src.index("async function render()"))
    assert body.index("sanitizeSvg(parsed);") < body.index("document.importNode(parsed, true)")


# ---- main.js: Load and Undo/Redo wait for the edit their click started ----------------
#
# A click on Load or Undo blurs the field being typed in (details, title, inline
# rename), which starts its commit. Load checked `dirty` before that commit
# landed, so with a quick click (a touchpad tap) the "Discard the unsaved
# changes?" question was skipped every time and the typing was lost to the file
# opened. Undo raced the commit on the server: when /undo won, the typing was
# applied on top and wiped the redo step of the edit Undo had just reverted.
# Both reproduced in Chromium against the running app.


def test_load_waits_for_pending_commits_before_checking_dirty():
    src = _read(STATIC / "main.js")
    body = _braced(src, src.index("async function actionLoad()"))
    assert "await flushPendingEdits();" in body
    assert body.index("await flushPendingEdits();") < body.index("store.state.dirty")
    assert body.index("await flushPendingEdits();") < body.index("pickPath('open')")


def test_undo_redo_wait_for_pending_commits():
    src = _read(STATIC / "main.js")
    body = _braced(src, src.index("async function actionHistory(kind)"))
    assert "await flushPendingEdits();" in body
    flush = body.index("await flushPendingEdits();")
    assert flush < body.index("store.state[able] === false"), "canUndo must include the commit"
    assert flush < body.index("api.post('/' + kind")


# ---- main.js: a metadata commit leaves a field typed in since alone --------------------
#
# Title, Tab, Date: the title's commit answered while the date was being typed,
# and its forced sync wrote the stored date back into the focused box, so the
# keystrokes after it produced "2026-01-016-12-24" -- committed as the
# document's date on the next blur (Chromium, title response delayed 150 ms).


def test_metadata_commit_does_not_overwrite_the_focused_field():
    src = _read(STATIC / "main.js")
    body = _braced(src, src.index("async function commitMetadata()"))
    ok_path = body[body.index("api.post('/metadata'") : body.index("} catch (err) {")]
    assert "syncMetadataInputs(true)" not in ok_path
    assert "syncMetadataInputs();" in ok_path
    sync = _braced(src, src.index("function syncMetadataInputs(force = false)"))
    assert "if (!force && el === document.activeElement) continue;" in sync


# ---- main.js: closing the tab warns about Title/Date typing too ------------------------
#
# F-7 made beforeunload warn about typed-but-uncommitted details fields and an
# open inline rename, but not the top bar: a new title typed into a saved
# document, then the tab closed or reloaded, was lost without a warning
# (Chromium: no beforeunload dialog for Title or Date, one for a details field).


def test_beforeunload_counts_uncommitted_title_and_date():
    src = _read(STATIC / "main.js")
    handler = _braced(src, src.index("window.addEventListener('beforeunload'"))
    assert "metadataChanged()" in handler
    assert "#details-root [data-dirty=\"true\"]" in handler


# ---- api.js: the server words its errors in the editor's language ----------------------
#
# The server localizes errors by ?lang= or Accept-Language, and the frontend
# sent neither, so the browser's OS locale decided: a Japanese Chrome with the
# editor switched to English showed "指定されたパスは許可されたフォルダーの外に
# あるか、無効です。" in the file dialog, an English one left the Japanese UI with
# English messages (reproduced in Chromium for PATH_REJECTED).

_API_HARNESS = r"""
(async () => {
  const seen = [];
  globalThis.window = {
    sessionStorage: { getItem: () => 'token', setItem() {}, removeItem() {} },
    location: { href: 'http://127.0.0.1/' },
    history: { replaceState() {} },
    dispatchEvent() {},
  };
  globalThis.document = { documentElement: { lang: '' } };
  globalThis.fetch = async (url, init) => {
    seen.push(init.headers['Accept-Language'] === undefined ? null : init.headers['Accept-Language']);
    return {
      ok: true,
      status: 200,
      headers: new Headers({ 'Content-Type': 'application/json' }),
      text: async () => '{"ok": true}',
    };
  };
  const { api } = await import(process.argv[1]);
  for (const lang of ['ja', 'en', '']) {
    document.documentElement.lang = lang;
    await api.get('/state');
    await api.download('POST', '/report/docx', {});
  }
  console.log(JSON.stringify(seen));
})();
"""


@needs_node
def test_api_requests_carry_the_editor_language():
    api_js = (STATIC / "api.js").as_uri()
    assert _node(_API_HARNESS, api_js) == ["ja", "ja", "en", "en", None, None]


def test_export_downloads_carry_the_editor_language():
    src = _read(STATIC / "main.js")
    body = _braced(src, src.index("async function fetchDownload(url)"))
    assert "headers['Accept-Language'] = language;" in body


# ---- details.js: a refused event-kind / house / transfer change is put back -----------
#
# With the PATCH failing (server stopped), the Event kind select kept showing
# "house" while the node stayed basic -- no dirty mark, no field error, and the
# next unrelated store update silently flipped it back (Chromium, PATCH aborted).


def test_details_extra_selects_revert_when_their_change_fails():
    src = _read(STATIC / "details.js")
    for select in ("transferSelect", "kindSelect", "houseSelect"):
        handler = re.search(
            r"extras\.%s\.addEventListener\('change', \(\) => \{(.*?)\n  \}\);" % select, src, re.S
        ).group(1)
        assert ".catch(revertExtras)" in handler, select
    body = re.search(r"const revertExtras = \(\) => \{(.*?)\n  \};", src, re.S).group(1)
    assert "updateExtras(node, false);" in body


# ---- api.js / main.js / store.js: client-side errors are in the editor's language ----
#
# With the Japanese UI and the server stopped, every action toasted "Could not
# reach the editor server. It may have been stopped in the terminal." in
# English (Chromium, all /api requests aborted); the same for a tab without a
# session, a non-JSON answer, a failed export and a panel that failed to render.

_API_I18N_HARNESS = r"""
(async () => {
  const out = {};
  let token = 'token';
  globalThis.window = {
    sessionStorage: { getItem: () => token, setItem() {}, removeItem() {} },
    location: { href: 'http://127.0.0.1/' },
    history: { replaceState() {} },
    dispatchEvent() {},
    // the shell's translator with the Japanese table from main.js
    ftaShell: {
      t: (key, vars) => (JA[key] || '[' + key + ']').replace(
        /\{(\w+)\}/g, (whole, name) => (vars && name in vars ? String(vars[name]) : whole)),
    },
  };
  globalThis.document = { documentElement: { lang: 'ja' } };
  const { api } = await import(process.argv[1]);
  const grab = async (fn) => { try { await fn(); return null; } catch (err) { return err.message; } };
  const answer = (status, type, body) => async () => ({
    ok: status < 400, status, headers: new Headers({ 'Content-Type': type }), text: async () => body,
  });
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch'); };
  out.network = await grab(() => api.get('/state'));
  globalThis.fetch = answer(502, 'text/html', '<html>proxy</html>');
  out.badResponse = await grab(() => api.get('/state'));
  globalThis.fetch = answer(500, 'application/json', '{"ok": false, "error": {}}');
  out.httpFailed = await grab(() => api.get('/state'));
  token = null;
  out.noSession = await grab(() => api.get('/state'));
  console.log(JSON.stringify(out));
})();
"""

_CLIENT_KEYS = ("api.noSession", "api.network", "api.badResponse", "api.httpFailed",
                "api.exportFailed", "store.panelFailed")


def _shell_strings(language: str) -> dict:
    """main.js's STRINGS table for one language, as {key: text}."""
    main = _read(STATIC / "main.js")
    strings = re.search(r"const STRINGS = \{(.*?)\n\};", main, re.S).group(1)
    en, ja = strings.split("\n  ja:", 1)
    table = en if language == "en" else ja
    return dict(re.findall(r"^    '([\w.]+)': '((?:[^'\\]|\\.)*)',?$", table, re.M))


@needs_node
def test_api_client_errors_are_translated():
    api_js = (STATIC / "api.js").as_uri()
    ja = _shell_strings("ja")
    harness = _API_I18N_HARNESS.replace("(async () => {", "const JA = %s;\n(async () => {" % json.dumps(ja), 1)
    expected = {
        "network": ja["api.network"],
        "badResponse": ja["api.badResponse"].replace("{status}", "502"),
        "httpFailed": ja["api.httpFailed"].replace("{status}", "500"),
        "noSession": ja["api.noSession"],
    }
    assert not any(text.isascii() for text in expected.values()), "Japanese text, read back from node"
    assert _node(harness, api_js) == expected


def test_client_error_keys_exist_in_both_languages_and_are_used():
    main = _read(STATIC / "main.js")
    strings = re.search(r"const STRINGS = \{(.*?)\n\};", main, re.S).group(1)
    en, ja = strings.split("\n  ja:", 1)
    for key in _CLIENT_KEYS:
        assert "    '%s': '" % key in en, key
        assert "    '%s': '" % key in ja, key
    download = _braced(main, main.index("async function fetchDownload(url)"))
    assert "t('api.network')" in download and "t('api.exportFailed'" in download
    assert "toast(detail.message || t('dialog.somethingWrong'), 'error'" in main
    assert "shell.t('store.panelFailed'" in _read(STATIC / "store.js")


# ---- IME: the Enter/Escape that confirm or cancel a conversion are the IME's ----------
#
# Chrome on macOS/Linux hands the Enter that confirms a Japanese conversion (and
# the Escape that cancels it) to the page as keydown with isComposing set. With a
# composition driven through CDP (Input.imeSetComposition) in Chromium, that
# Enter submitted the Add dialog and saved the Save As dialog under the half-typed
# name, committed the tree rename and left the details/Title field; Escape closed
# both dialogs (discarding the typing), cancelled the rename and reverted the
# field. keyCode 229 is the same key on platforms that report it that way.


@needs_node
def test_ime_key_detection():
    src = _read(STATIC / "dialogs.js")
    fn = _braced(src, src.index("export function isImeKey(event)")).replace("export ", "")
    cases = [
        {"key": "Enter", "isComposing": True, "keyCode": 229},
        {"key": "Enter", "isComposing": True, "keyCode": 13},
        {"key": "Process", "isComposing": False, "keyCode": 229},
        {"key": "Enter", "isComposing": False, "keyCode": 13},
        {"key": "Escape", "keyCode": 27},
        None,
    ]
    got = _node(fn + "\nconsole.log(JSON.stringify(%s.map((e) => isImeKey(e))));" % json.dumps(cases))
    assert got == [True, True, True, False, False, False]


def _guard_before(body: str, guard: str, *keys: str) -> None:
    assert guard in body, guard
    for key in keys:
        assert body.index(guard) < body.index(key), key


def test_enter_and_escape_handlers_leave_composition_to_the_ime():
    dialogs = _read(STATIC / "dialogs.js")
    modal = _braced(dialogs, dialogs.index("function onKeydown(event)"))
    _guard_before(modal, "if (isImeKey(event)) return;", "event.key === 'Escape'", "cfg.onEnter()")
    assert "if (event.key === 'Enter' && !isImeKey(event)) event.preventDefault();" in dialogs

    details = _read(STATIC / "details.js")
    field = details[details.index("control.addEventListener('keydown'"):]
    _guard_before(field, "if (isImeKey(event)) return;", "event.key === 'Enter'", "event.key === 'Escape'")

    tree = _read(STATIC / "tree.js")
    rename = tree[tree.index("if (target.closest('.fta-tree-rename')) {"):]
    _guard_before(rename, "if (isImeKey(event)) return;", "commitRename(true)", "cancelRename()")
    search = tree[tree.index("search.addEventListener('keydown'"):]
    _guard_before(search, "if (isImeKey(event)) return;", "event.key === 'Escape'", "event.key === 'Enter'")

    filedialog = _read(STATIC / "filedialog.js")
    keys = _braced(filedialog, filedialog.index("function onKeydown(event)"))
    _guard_before(keys, "if (isImeKey(event)) return;", "event.key === 'Escape'", "event.key === 'Enter'")

    main = _read(STATIC / "main.js")
    ime = "if (event.isComposing || event.keyCode === 229) return;"
    topbar = _braced(main, main.index("function wireTopbar()"))
    _guard_before(topbar, ime, "if (event.key === 'Enter') el.blur();")
    shortcuts = _braced(main, main.index("function onKeyDown(event)"))
    _guard_before(shortcuts, ime, "event.key === 'Escape'")


# ---- diagram.js: a new document is fitted, whatever the old view was -------------------
#
# Pan one document's diagram off the stage, then open another file: the new
# diagram kept the old transform and none of it was on screen (Chromium:
# visible fraction 0 after Open), so the panel looked empty.


def test_diagram_refits_on_a_new_document():
    src = _read(STATIC / "diagram.js")
    assert "window.addEventListener('fta:document', onDocument);" in src
    assert "window.removeEventListener('fta:document', onDocument);" in src
    body = re.search(r"const onDocument = \(\) => \{(.*?)\n  \};", src, re.S).group(1)
    for line in ("autoFit = true;", "resetView = true;", "schedule();"):
        assert line in body, line
    assert "if (resetView || autoFit ||" in src


# ---- tree.js: New / Open drop the old document's multi-selection ----------------------
#
# Ctrl-click two rows, then the root (lead = root), then open a file: ids such
# as root_0/root_1 recur from file to file, so both rows stayed selected in the
# newly opened tree and Delete asked "Delete these 2 nodes...?" about nodes the
# user never chose there (reproduced in Chromium).


def test_tree_drops_its_multi_selection_on_a_new_document():
    src = _read(STATIC / "tree.js")
    assert "window.addEventListener('fta:document', onDocument);" in src
    assert "window.removeEventListener('fta:document', onDocument);" in src
    body = _braced(src, src.index("function onDocument()"))
    assert "selection = new Set(lead ? [lead] : []);" in body
    assert "anchorId = lead;" in body
    assert "render();" in body
    main = _read(STATIC / "main.js")
    for fn in ("async function adoptDocument(payload)", "async function actionNew()"):
        assert "announceDocument();" in _braced(main, main.index(fn)), fn


# ---- tree.js: quick keyboard moves are applied one after another ---------------------
#
# Three quick Ctrl+Shift+Down on the first of four siblings left it second or
# third, never last: every press computed its target index from the same
# not-yet-updated tree, so presses were lost and each still cost an undo step
# (Chromium: B,C,A,D instead of B,C,D,A in 5 runs of 5).

_MOVE_HARNESS = r"""
const kids = { root: ['a', 'b', 'c', 'd'], a: [], b: [], c: [], d: [] };
const parentOf = (id) => Object.keys(kids).find((p) => kids[p].indexOf(id) !== -1) || null;
function rootId() { return 'root'; }
function parentIdOf(id) { return parentOf(id); }
function childIdsOf(id) { return (kids[id] || []).slice(); }
function movable(nodeId, newParentId) { return nodeId !== newParentId; }
function say() {}
function t(key) { return key; }
function fail(err) { throw err; }
let destroyed = false;
// The round trip: the tree the next press reads changes only when it ends.
function requestMove(id, newParentId, index) {
  return new Promise((resolve) => setTimeout(() => {
    const from = parentOf(id);
    kids[from] = kids[from].filter((x) => x !== id);
    const list = kids[newParentId];
    if (index === null || index === undefined || index > list.length) list.push(id);
    else list.splice(index, 0, id);
    resolve();
  }, 15));
}
"""


def _keyboard_move_source() -> str:
    src = _read(STATIC / "tree.js")
    parts = [_braced(src, src.index("function moveByKeyboard(id, direction)"))]
    decl = re.search(r"^\s*let keyboardMoves = .*?;$", src, re.M)
    if decl:
        parts.append(decl.group(0))
    at = src.find("function queueKeyboardMove(")
    if at != -1:
        parts.append(_braced(src, at))
    return "\n".join(parts)


@needs_node
def test_quick_keyboard_moves_each_count():
    src = _read(STATIC / "tree.js")
    keydown = _braced(src, src.index("host.addEventListener('keydown'"))
    handler = re.search(r"if \(direction\) \{(.*?)\}", keydown, re.S).group(1)
    call = "queueKeyboardMove" if "queueKeyboardMove(id, direction)" in handler else "moveByKeyboard"
    script = _MOVE_HARNESS + _keyboard_move_source() + (
        "\nfor (let i = 0; i < 3; i += 1) %s('a', 'down');"
        "\nsetTimeout(() => console.log(JSON.stringify(kids.root)), 400);" % call)
    assert _node(script) == ["b", "c", "d", "a"]


def test_save_waits_for_queued_keyboard_moves():
    src = _read(STATIC / "tree.js")
    body = _braced(src, src.index("function onFlush(event)"))
    assert "detail.promises.push(keyboardMoves);" in body


# ---- tree.js: rows are found by id whatever characters the id holds -------------------
#
# itemById spliced the id into a CSS selector, escaping only quotes. Ids come
# from the file: with a backslash the selector missed the row (focus fell to
# <body> after an inline rename), with a newline querySelector threw on every
# render ("A panel failed to update") and F2 could not rename the node.
# Reproduced in Chromium with a file holding such ids. The host below answers
# querySelector the way the browser parses that selector.

_ITEM_HOST = r"""
const items = ['root', 'back\\slash', 'new\nline', 'q"uote', 'plain'].map((id) => ({ dataset: { id } }));
function cssString(raw) {
  if (raw.indexOf('\n') !== -1) throw new SyntaxError('not a valid selector');
  return raw.replace(/\\([0-9a-fA-F]{1,6})\s?|\\([\s\S])/g,
    (_m, hex, ch) => (hex !== undefined ? String.fromCodePoint(parseInt(hex, 16)) : ch));
}
const host = {
  querySelectorAll(selector) { return selector === '.fta-tree-item' ? items : []; },
  querySelector(selector) {
    const m = /^\.fta-tree-item\[data-id="([\s\S]*)"\]$/.exec(selector);
    if (!m) throw new Error('unexpected selector ' + selector);
    const wanted = cssString(m[1]);
    return items.find((item) => item.dataset.id === wanted) || null;
  },
};
"""


@needs_node
def test_tree_finds_rows_whose_ids_hold_backslashes_or_newlines():
    src = _read(STATIC / "tree.js")
    fn = _braced(src, src.index("function itemById(id)"))
    script = _ITEM_HOST + fn + (
        "\nconsole.log(JSON.stringify(items.map((item) => {"
        " try { return itemById(item.dataset.id) === item; } catch (err) { return String(err.name); } })));")
    assert _node(script) == [True, True, True, True, True]


# ---- dialogs.js: parseProbability takes decimal text only ------------------------------
#
# The Add dialog and the Details panel parsed with Number(), which reads 0x1,
# 0b1 and 0o1 as 1 and 0x0 as 0 -- stored as a probability, although the
# server's float() refuses that text and the analysis tabs reject hex.


def _parse_probability_source() -> str:
    src = _read(STATIC / "dialogs.js")
    decl = re.search(r"^const DECIMAL_TEXT = .*;$", src, re.M)
    fn = re.search(r"export function parseProbability\(raw\) \{.*?\n\}", src, re.S).group(0)
    return (decl.group(0) + "\n" if decl else "") + fn.replace("export ", "")


@needs_node
def test_parse_probability_accepts_decimal_text_only():
    cases = ["1e-6", "1E-6", " 0.5 ", ".5", "+0.5", "-0", "1", "0", "1e-400",
             "0x1", "0x0", "0b1", "0o1", "0x10", "0,5", "50%", "5.", "Infinity", "NaN", "", "  ", "1_0"]
    script = (
        "const t = (k) => k;\n" + _parse_probability_source()
        + "\nconsole.log(JSON.stringify(" + json.dumps(cases) + ".map((c) => {"
        + " const r = parseProbability(c); return r.ok ? r.value : 'REJECT'; })));"
    )
    got = dict(zip(cases, _node(script)))
    assert got == {
        "1e-6": 1e-6, "1E-6": 1e-6, " 0.5 ": 0.5, ".5": 0.5, "+0.5": 0.5, "-0": 0, "1": 1, "0": 0,
        "1e-400": 0,
        "0x1": "REJECT", "0x0": "REJECT", "0b1": "REJECT", "0o1": "REJECT", "0x10": "REJECT",
        "0,5": "REJECT", "50%": "REJECT", "5.": "REJECT", "Infinity": "REJECT", "NaN": "REJECT",
        "": "REJECT", "  ": "REJECT", "1_0": "REJECT",
    }


# ---- details.js: a refused gate change is put back (F-26) -----------------------------
#
# With the PATCH failing, the Logic Gate select kept showing the refused AND on a
# node that stayed OR; choosing AND again fired no change, so it could not even
# be retried (Chromium, PATCH aborted). Typed text keeps its by-design behaviour.


def test_details_refused_gate_change_is_put_back():
    src = _read(STATIC / "details.js")
    body = _braced(src, src.index("function commitField(key)"))
    callbacks = body[body.index("send(patch).then("):].split("\n      () => {")
    assert len(callbacks) == 3, "a success and a failure callback"
    on_failure = callbacks[2]
    assert "if (field.spec.kind !== 'gate') return;" in on_failure
    assert "populate(key, displayValue(now, key));" in on_failure
    assert "updateExtras(now, false);" in on_failure


# ---- Add dialog stays open until the node is made (F-27) -------------------------------
#
# The dialog closed before POST /nodes was sent, so a refused POST (400
# INVALID_FIELD from the server, routed in Chromium) left only a toast: the typed
# name, probability, notes and links were gone. The dialog now posts through a
# `submit` hook from main.js and stays open, values intact, with the error at the
# field the server named (or under the form) until the POST succeeds.


def test_add_dialog_stays_open_until_the_node_is_made():
    dialogs = _read(STATIC / "dialogs.js")
    header = "export function openAddNodeDialog(parentId, options)"
    assert header in dialogs
    submit = _braced(dialogs, dialogs.index("function submit()", dialogs.index(header)))
    assert "if (submitting) return;" in submit, "no second POST while the first is on the wire"
    hook = submit[submit.index(".then(() => opts.submit(result))"):]
    assert submit.index("okButton.disabled = true;") < submit.index(".then(() => opts.submit(result))")
    assert "() => modal.close(result)," in hook
    refused = hook[hook.index("(err) => {"):]
    assert "modal.close(" not in refused, "a refused POST keeps the dialog open"
    assert "target.setError(message);" in refused and "setFormError(message);" in refused

    main = _read(STATIC / "main.js")
    add = _braced(main, main.index("async function actionAdd()"))
    assert "await fn(parentId, { submit })" in add
    assert add.index("await fn(parentId, { submit })") < add.index("store.applyMutation(result);")
    assert add.count("api.post('/nodes'") == 2, "the hook, and the fallback for a dialog without it"


# ---- Ctrl+S inside a modal is not the browser's "Save page as" (F-28) ---------------------
#
# With the Add dialog or a confirmation open, onKeyDown returned on modalOpen()
# before its Ctrl+S branch, so Ctrl+S and Ctrl+Shift+S reached the browser
# un-prevented (Chromium: defaultPrevented false after every handler).


def test_ctrl_s_in_a_modal_is_claimed():
    src = _read(STATIC / "main.js")
    body = _braced(src, src.index("function onKeyDown(event)"))
    branch = re.search(r"if \(modalOpen\(\)\) \{(.*?)\n  \}", body, re.S)
    assert branch, "the modal branch handles Ctrl+S before returning"
    assert "if (ctrl && !event.altKey && key === 's') event.preventDefault();" in branch.group(1)
    assert "return;" in branch.group(1)
    assert body.index("if (modalOpen()) {") < body.index("actionSave()")


# ---- symbols-style Render never falls back to native /render (F-29) ---------------------
#
# Standard-symbols style with nothing drawn yet (the /api/dot fetch failed):
# toPngBlob() gave null and Render went on to POST /api/render with style
# "symbols" -- native dot, which only has the placeholder shapes -- and
# downloaded that picture (Chromium, /api/render answered as Graphviz would).


def test_symbols_render_without_a_drawing_says_so():
    src = _read(STATIC / "main.js")
    body = _braced(src, src.index("async function actionRenderImage()"))
    branch = _braced(body, body.index("if (box && box.style === 'symbols'"))
    assert branch.rstrip()[:-1].rstrip().endswith("return;"), "no fall-through to /render"
    assert "'diagram.nothingToExport'" in branch and "'diagram.pngFailed'" in branch
    assert "diagramPanel.hasDiagram()" in branch
    diagram = _read(STATIC / "diagram.js")
    assert "hasDiagram: () => Boolean(exportSvgText)," in diagram


# ---- details.js: a success held back for a refused commit still lands (F-30) -----------
#
# Name, Tab, Type, Tab: the name PATCH succeeded but, a newer commit being queued
# behind it, its response was not installed; the type PATCH was then refused
# (404 routed in Chromium). The server had the new name and was dirty while the
# store kept the old name: the Name box and the tree reverted to it and the badge
# said "Saved". The last success held back is now installed when the newest
# commit fails, and the refused box still keeps its typing.

_SEND_HARNESS = r"""
const applied = [];
const store = { applyMutation: (result) => applied.push(result.tag) };
const api = {
  patch: (path, body) => new Promise((resolve, reject) => setTimeout(() => {
    if (body.refuse) reject(Object.assign(new Error('refused'), { code: 'NODE_NOT_FOUND', detail: {} }));
    else resolve({ tag: body.tag });
  }, 10)),
};
function currentId() { return 'n1'; }
function setBanner() {}
function t(key) { return key; }
function errorMessage(err, fallback) { return (err && err.message) || fallback; }
function showError() {}
function errorField() { return null; }
const fields = {};
function setFieldError() {}
"""


def _send_source() -> str:
    src = _read(STATIC / "details.js")
    decls = re.findall(r"^let (?:pending|sequence|heldBack) = .*;$", src, re.M)
    return "\n".join(decls) + "\n" + _braced(src, src.index("function send(patch)"))


@needs_node
@pytest.mark.parametrize(
    "commits, installed",
    [
        ([{"tag": "a"}, {"refuse": True}], ["a"]),  # the case above
        ([{"tag": "a"}, {"tag": "b"}], ["b"]),  # intermediate views still skipped
        ([{"tag": "a"}, {"refuse": True}, {"tag": "c"}], ["c"]),
        ([{"tag": "a"}, {"refuse": True}, {"refuse": True}], ["a"]),
        ([{"refuse": True}], []),
    ],
)
def test_details_installs_the_last_success_when_the_newest_commit_fails(commits, installed):
    script = _SEND_HARNESS + _send_source() + (
        "\nfor (const patch of %s) send(patch).catch(() => {});"
        "\nsetTimeout(() => console.log(JSON.stringify(applied)), 300);" % json.dumps(commits))
    assert _node(script) == installed


@needs_node
def test_details_refused_text_keeps_its_typing():
    src = _read(STATIC / "details.js")
    fn = _braced(src, src.index("function restoreTyping(key, nodeId, typed)"))
    script = r"""
const document = { activeElement: null };
const dirty = [];
function syncDirty(key) { dirty.push(key); }
function currentNode() { return { id: 'n1' }; }
const fields = {
  type: { spec: { kind: 'text' }, control: { value: 'Event' } },
  logicGate: { spec: { kind: 'gate' }, control: { value: 'OR' } },
};
""" + fn + r"""
restoreTyping('type', 'n1', 'Changed type');
restoreTyping('logicGate', 'n1', 'AND');
console.log(JSON.stringify([fields.type.control.value, fields.logicGate.control.value, dirty]));
"""
    assert _node(script) == ["Changed type", "OR", ["type"]]
    body = _braced(src, src.index("function commitField(key)"))
    on_failure = body[body.index("send(patch).then("):].split("\n      () => {")[2]
    assert "restoreTyping(key, nodeId, typed);" in on_failure


# ---- filedialog.js: a late first listing leaves the user's typing alone (F-32) ----------
#
# Save As focuses the name box and selects the stem once the first folder
# listing arrives. With the listing late (400 ms routed in Chromium) and the
# user already typing in the name box, that re-selection landed mid-word and
# the next keystrokes replaced the name: "typed_name.json" came out as
# "name.json". The GUI suite hit the same race and saved b2b_core_url.json.json.
# A failed first listing likewise moved the focus to Cancel, where the next
# Enter closed the dialog. The dialog's own start position still applies when
# the user is not typing (including after a keystroke pulled the focus in).

_FILE_INIT_HARNESS = r"""
const document = { activeElement: null };
function control(name) {
  return {
    name, value: '', selection: null,
    focus() { document.activeElement = this; },
    setSelectionRange(start, end) { this.selection = [start, end]; },
  };
}
const upButton = control('up');
const pathInput = control('path');
const list = control('list');
const nameInput = control('name');
const cancelButton = control('cancel');
const parts = [upButton, pathInput, list, nameInput, cancelButton];
const dialog = { contains: (node) => parts.includes(node) };
const api = { get: async () => ({ cwd: '/work', root: '/root' }) };
function isSessionError() { return false; }
function setMessage() {}
function errorText() { return 'failed'; }
let closed = false;
function close() { closed = true; }
const opts = {};
const [mode, listed, user] = SCENARIO;
nameInput.value = 'pump.json';
async function navigate() {
  await new Promise((resolve) => setTimeout(resolve, 20));
  // what the user did while the listing was on its way
  if (user === 'name') {
    nameInput.focus();
    nameInput.value = 'typed_name.json';
    nameInput.selection = [15, 15];
  }
  if (user === 'path') pathInput.focus();
  if (user === 'key') upButton.focus(); // a keystroke pulled the focus into the dialog
  return listed;
}
"""


@needs_node
@pytest.mark.parametrize(
    "scenario, expected",
    [
        (["save", True, None], ["name", "pump.json", [0, 4]]),
        (["save", True, "name"], ["name", "typed_name.json", [15, 15]]),
        (["save", True, "path"], ["path", "pump.json", None]),
        (["save", True, "key"], ["name", "pump.json", [0, 4]]),
        (["open", True, None], ["list", "pump.json", None]),
        (["open", True, "path"], ["path", "pump.json", None]),
        (["save", False, None], ["cancel", "pump.json", None]),
        (["save", False, "name"], ["name", "typed_name.json", [15, 15]]),
    ],
)
def test_file_dialog_first_listing_does_not_interrupt_typing(scenario, expected):
    src = _read(STATIC / "filedialog.js")
    init = _braced(src, src.index("(async () => {", src.index("document.body.appendChild(overlay);")))
    script = _FILE_INIT_HARNESS.replace("SCENARIO", json.dumps(scenario)) + (
        "\nconst run = %s);"
        "\nrun().then(() => console.log(JSON.stringify("
        "[document.activeElement && document.activeElement.name, nameInput.value, nameInput.selection])));"
        % init)
    assert _node(script) == expected


# ---- filedialog.js: a listing does not overwrite a path being typed (F-33) -------------
#
# Every successful listing wrote its folder into the path box. A path typed
# there while the first listing was on its way (held 400 ms in Chromium) was
# replaced mid-word and the rest of the typing appended to the folder:
# "/some/typed/folder" came out as "<sandbox>/rooted/folder". A path the user
# asked for (typed, then Enter or Go) is still shown as the folder it resolved to.

_NAVIGATE_HARNESS = r"""
let generation = 0;
let closed = false;
let cwd = '';
let parent = null;
let dirs = [];
let files = [];
let lastNavigateError = null;
const extensions = ['.json'];
const pathInput = { value: '' };
function setBusy() {}
function setMessage() {}
function t(key) { return key; }
function listQuery() { return ''; }
function matchesExtension() { return true; }
function renderList() {}
function isSessionError() { return false; }
function close() { closed = true; }
function errorText() { return 'failed'; }
const api = {
  get: () => new Promise((resolve) => setTimeout(
    () => resolve({ path: '/home/work', parent: '/home', dirs: [], files: [] }), 30)),
};
const [before, during] = SCENARIO;
pathInput.value = before;
"""


@needs_node
@pytest.mark.parametrize(
    "scenario, shown",
    [
        (["", None], "/home/work"),  # a listing nobody typed over
        (["", "/some/typ"], "/some/typ"),  # typing while the first listing loads
        (["work", None], "/home/work"),  # typed, then Enter: the resolved folder
        (["work", "work/sub"], "work/sub"),  # typed on after Enter
    ],
)
def test_file_dialog_listing_keeps_a_path_being_typed(scenario, shown):
    src = _read(STATIC / "filedialog.js")
    fn = _braced(src, src.index("async function navigate(target, quiet)"))
    script = _NAVIGATE_HARNESS.replace("SCENARIO", json.dumps(scenario)) + fn + r"""
const listed = navigate('work');
if (during !== null) setTimeout(() => { pathInput.value = during; }, 10);
listed.then((ok) => console.log(JSON.stringify([ok, cwd, pathInput.value])));
"""
    assert _node(script) == [True, "/home/work", shown]


# ---- dialogs.js: the link picker installs only its newest node list (F-31) -------------
#
# Select a node (GET /nodes for the old document, answering late) and press
# Alt+N: the list fetched for the new document arrived first and the late one
# then replaced it, so the picker offered Alpha, Beta, Gamma -- nodes of the
# previous document -- as link targets (Chromium, first response held 1.5 s).

_RELOAD_HARNESS = r"""
let choices = [];
const nameById = new Map();
function renderMatches() {}
function renderLists() {}
const statuses = [];
function setStatus(message, isError) { if (message) statuses.push(message); }
function errorMessage(err, fallback) { return (err && err.message) || fallback; }
function showError() {}
function t(key) { return key; }
const answers = [
  // the old document's list, late; then the new document's, at once
  () => new Promise((resolve) => setTimeout(() => resolve([{ id: 'root' }, { id: 'old_a' }]), 60)),
  () => Promise.resolve([{ id: 'root' }]),
  () => new Promise((_, reject) => setTimeout(() => reject(new Error('stale failure')), 60)),
  () => Promise.resolve([{ id: 'root' }, { id: 'new_b' }]),
];
let call = 0;
function fetchNodeList() { return answers[call++](); }
"""


@needs_node
def test_link_picker_keeps_only_the_newest_node_list():
    src = _read(STATIC / "dialogs.js")
    decl = re.search(r"^\s*let reloadSeq = 0;$", src, re.M)
    fn = _braced(src, src.index("async function reload()"))
    script = _RELOAD_HARNESS + (decl.group(0) if decl else "") + "\n" + fn + r"""
reload(); reload();
setTimeout(() => {
  const first = choices.map((c) => c.id);
  reload(); reload();
  setTimeout(() => console.log(JSON.stringify([first, choices.map((c) => c.id), statuses])), 150);
}, 150);
"""
    assert _node(script) == [["root"], ["root", "new_b"], []]


# ---- main.js: the tree panel is titled for the mode (DOC-29) ---------------------------
#
# Spec §2.1 (desktop parity, also USER_GUIDE.md / ETA_MODE.md): changing the
# mode relabels the tree panel "Fault Tree" <-> "Event Tree". The web panel
# read "Fault Tree" in ETA mode too.


def _shell_t_source(language: str) -> str:
    """main.js's STRINGS and t(), with the editor language fixed."""
    main = _read(STATIC / "main.js")
    strings = re.search(r"const STRINGS = \{(.*?)\n\};", main, re.S).group(0)
    return "%s\nlet language = %s;\n%s\n" % (
        strings, json.dumps(language), _braced(main, main.index("function t(key, vars)")))


@needs_node
@pytest.mark.parametrize(
    "language, fta, eta",
    [("en", "Fault Tree", "Event Tree"), ("ja", "フォルトツリー", "イベントツリー")],
)
def test_tree_panel_title_follows_the_mode(language, fta, eta):
    main = _read(STATIC / "main.js")
    fn = _braced(main, main.index("function syncTreeTitle(state)"))
    script = _shell_t_source(language) + r"""
const title = { dataset: { i18n: 'panel.tree' }, textContent: 'Fault Tree' };
const $ = (sel) => (sel === '#tree-panel-title' ? title : null);
""" + fn + r"""
const seen = [];
for (const state of [{ metadata: { mode: 'ETA' } }, { metadata: { mode: 'FTA' } }, {},
                     { metadata: { mode: 'ETA' } }]) {
  syncTreeTitle(state);
  seen.push([title.textContent, title.dataset.i18n]);
}
console.log(JSON.stringify(seen));
"""
    assert _node(script) == [
        [eta, "panel.treeEta"], [fta, "panel.tree"], [fta, "panel.tree"], [eta, "panel.treeEta"]]
    # Wired where the mode can change: every store update (a mode edit, New,
    # Open, Undo) runs renderShell, and so does a language switch -- which
    # translates [data-i18n] first, hence the key kept on the element.
    assert "syncTreeTitle(state);" in _braced(main, main.index("function renderShell(state)"))
    assert "store.subscribe(renderShell);" in main
    assert "if (store.state) renderShell(store.state);" in _braced(main, main.index("function applyLanguage()"))


# ---- main.js: the Graphviz capability row says what native dot is for (DOC-34) ---------
#
# Since 1.7.1 the screen is always drawn by the bundled WebAssembly Graphviz;
# a native `dot` only draws the 300-dpi PNG export of the compact style
# (diagram.js exportPng). The capability panel still said "Diagrams are drawn
# by the Graphviz installed on this machine" under "Diagram rendering", and
# the chip called a missing `dot` "Diagram quality limited".


@pytest.mark.parametrize("language", ["en", "ja"])
def test_graphviz_capability_text_matches_what_native_dot_does(language):
    strings = _shell_strings(language)
    catalog = _read(STATIC / "i18n" / "diagram.js")
    table = catalog.split("\n  ja:", 1)[0 if language == "en" else 1]
    compact = re.search(r"'diagram17\.styleCompact': '([^']*)'", table).group(1)
    for key in ("cap.dot.ok", "cap.dot.bad"):
        text = strings[key]
        assert "WebAssembly" in text and "PNG" in text and "300 dpi" in text, key
        assert compact in text, (key, "names the style the native export is for")
    assert "Diagrams are drawn by" not in strings["cap.dot.ok"]
    assert "で図を描画します" not in strings["cap.dot.ok"]
    for key in ("cap.dot.name", "cap.chip.graphviz", "cap.dot.fix"):
        assert "PNG" in strings[key], key
