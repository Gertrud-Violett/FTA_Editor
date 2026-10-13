"""The editing flow (usability work order, batch 1).

One block per item of the work order, by its number there. A pure function is
run in node where node is installed: the number reader as the module it is,
the others cut out of their file and run against small stand-ins for the
store and the browser. What only exists as wiring is checked in the source,
and the whole flow is driven in a real browser by ``tests/gui/s_ux1.js``.
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

from fta_web import fsbrowser  # noqa: E402
from fta_web.diagram_dot import (  # noqa: E402
    COMPACT_META_PT,
    SYMBOLS_NAME_PT,
    SYMBOLS_PROB_PT,
    build_dot_text2,
)
from fta_web.engine import WebCore  # noqa: E402
from fta_web.state import reset_state  # noqa: E402

STATIC = REPO / "fta_web" / "static" / "js"
CSS = REPO / "fta_web" / "static" / "css" / "app.css"
INDEX = REPO / "fta_web" / "templates" / "index.html"
EXAMPLES = REPO / "fta_web" / "examples"

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
    """One function of a module, as plain script text."""
    return _braced(src, src.index(header))


def _node(script: str, module: bool = False):
    """Run `script` under node, read from stdin; its stdout as JSON."""
    args = ["node", "--input-type=module", "-"] if module else ["node", "-"]
    out = subprocess.run(args, input=script, capture_output=True, text=True, encoding="utf-8",
                         check=True, timeout=60).stdout
    return json.loads(out)


# ---- 42: the number reader ---------------------------------------------------------------
#
# The browser reads what people type and sends a plain number; the server's
# validator is the one it always was.

def _parse_numbers(texts):
    script = (
        "import { parseNumberText } from %s;\n" % json.dumps((STATIC / "numfmt.js").as_uri())
        + "const input = %s;\n" % json.dumps(texts)
        + "console.log(JSON.stringify(input.map((t) => { const r = parseNumberText(t);"
          " return r.ok ? [r.value, r.text, r.changed] : null; })));"
    )
    return dict(zip(texts, _node(script, module=True)))


@needs_node
def test_42_percent_fraction_comma_and_full_width_digits_are_read():
    got = _parse_numbers(["5%", "0.5 %", "0.7%", "1e-3%", "1/1000", "3 / 4", "0,05", "1,5e-3",
                          "０．０５", "５％", "１／１０", "１ｅ－３", "１ｅー３", "0,005"])
    assert got == {
        "5%": [0.05, "0.05", True],
        "0.5 %": [0.005, "0.005", True],
        # the exponent moves; 0.7 / 100 in floating point is 0.006999999999999999
        "0.7%": [0.007, "0.007", True],
        "1e-3%": [1e-05, "0.00001", True],
        "1/1000": [0.001, "0.001", True],
        "3 / 4": [0.75, "0.75", True],
        "0,05": [0.05, "0.05", True],
        "1,5e-3": [0.0015, "1.5e-3", True],
        "０．０５": [0.05, "0.05", True],
        "５％": [0.05, "0.05", True],
        "１／１０": [0.1, "0.1", True],
        "１ｅ－３": [0.001, "1e-3", True],
        "１ｅー３": [0.001, "1e-3", True],  # the long-vowel mark an IME gives for a minus
        "0,005": [0.005, "0.005", True],  # a leading zero is no thousands group
    }


@needs_node
def test_42_plain_decimals_are_left_exactly_as_typed():
    got = _parse_numbers(["0.5", " 0.5 ", "1e-6", "1E-6", ".5", "+0.5", "-0", "1", "0"])
    assert all(row is not None and row[2] is False for row in got.values()), got
    assert got["1E-6"] == [1e-06, "1E-6", False] and got[" 0.5 "] == [0.5, "0.5", False]


@needs_node
def test_42_what_is_ambiguous_or_not_a_number_is_refused():
    refused = ["1,000", "12,500", "1,000,000", "1.000,5", "1/0", "1/2/3", "5%%", "%", "/", "1/",
               "0x1", "0b1", "1_0", "abc", "", "  ", "Infinity", "NaN", "1 000", "５ ０"]
    got = _parse_numbers(refused)
    assert got == {text: None for text in refused}


def test_42_the_dialogs_and_details_use_the_reader_and_the_server_is_untouched():
    dialogs = _read(STATIC / "dialogs.js")
    parse = _function(dialogs, "export function parseProbability(raw)")
    assert "parseNumberText(raw)" in parse and "read.value < 0 || read.value > 1" in parse
    assert "text: read.text, changed: read.changed" in parse
    # the Add dialog shows what was understood on leaving the box
    add = _function(dialogs, "export function openAddNodeDialog(parentId, options)")
    assert "if (read.ok && read.changed) probabilityField.control.value = read.text;" in add
    # Details sends the number, and then shows the stored value
    details = _read(STATIC / "details.js")
    assert "return parseProbability(raw);" in details
    assert "populate(key, displayValue(now, key));" in details


@pytest.fixture
def client():
    flask = pytest.importorskip("flask")
    from fta_web.routes.tree import tree_bp

    reset_state()
    app = flask.Flask(__name__)
    app.register_blueprint(tree_bp)
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


@pytest.mark.parametrize("value", ["5%", "0,05", "1/1000", "abc", ""])
def test_42_the_server_still_refuses_the_typed_forms(client, value):
    """Normalising is the browser's job. The API takes numbers, as before."""
    response = client.post("/api/nodes", json={"parentId": "root", "name": "x", "probability": value})
    assert response.status_code == 400
    assert response.get_json()["error"]["detail"]["field"] == "probability"


def test_42_details_warns_before_an_invalid_entry_is_dropped():
    details = _read(STATIC / "details.js")
    update = _function(details, "function update()")
    assert update.index("if (switched && renderedId !== null) warnDropped();") < update.index("clearErrors();")
    warn = _function(details, "function warnDropped()")
    assert "control.dataset.dirty !== 'true' || control.getAttribute('aria-invalid') !== 'true'" in warn
    assert "t('details.notSaved'" in warn and "value: control.value" in warn


# ---- 3: the Add dialog's probability starts empty and is required -------------------------

def test_3_the_probability_starts_empty_and_enter_cannot_skip_it():
    dialogs = _read(STATIC / "dialogs.js")
    add = _function(dialogs, "export function openAddNodeDialog(parentId, options)")
    box = add[add.index("const probabilityField = field("):add.index("const advancedGates")]
    assert "value: ''," in box and "required: true," in box and "'1.0'" not in add
    # Enter in Name with no probability moves on; it does not submit
    enter = add[add.index("onEnter: (event) => {"):add.index("onCtrlEnter:")]
    assert enter.index("probabilityField.control.focus();") < enter.index("submit(false);")
    assert "event.target === nameField.control" in enter
    submit = _function(add, "function submit(another)")
    assert submit.index("t('dialog.probabilityRequired')") < submit.index("parseProbability(")


def test_3_the_api_default_is_unchanged(client):
    """A node made without a probability is still valid and still 1.0."""
    response = client.post("/api/nodes", json={"parentId": "root", "name": "No number"})
    assert response.status_code in (200, 201)
    payload = response.get_json()
    made = [c for c in payload["tree"]["children"] if c["id"] == payload["nodeId"]][0]
    assert made["probability"] == 1.0


# ---- 1: Add keeps the parent selected; OK and add another -------------------------------

def test_1_add_keeps_the_parent_selected_and_reveals_the_child():
    main = _read(STATIC / "main.js")
    add = _function(main, "async function actionAdd()")
    assert "store.select(result.nodeId)" not in add
    adopt = add[add.index("const adopt = (result, name, quiet) => {"):add.index("const submit = (values, how) => {")]
    assert "store.applyMutation(result);" in adopt and "revealNode(result.nodeId);" in adopt
    # the only selection Add makes is the parent, when nothing was selected
    assert re.findall(r"store\.select\(([^)]*)\)", add) == ["parentId"]
    assert "new CustomEvent('fta:reveal', { detail: { id: String(id) } })" in main
    tree = _read(STATIC / "tree.js")
    reveal = _function(tree, "function onReveal(event)")
    assert "revealAll([wanted]);" in reveal and "revealedId = wanted;" in reveal and "scrollToRow(wanted);" in reveal
    assert "(id === revealedId ? ' is-new' : '')" in tree
    assert "window.addEventListener('fta:reveal', onReveal);" in tree
    assert "window.removeEventListener('fta:reveal', onReveal);" in tree


def test_1_ok_and_add_another():
    dialogs = _read(STATIC / "dialogs.js")
    add = _function(dialogs, "export function openAddNodeDialog(parentId, options)")
    assert "onCtrlEnter: () => submit(canAddAnother)," in add
    assert "text: t('dialog.addAnother')," in add
    assert "if (canAddAnother) modal.footer.appendChild(anotherButton);" in add
    reset = _function(add, "function resetForNext(name)")
    for line in ("nameField.control.value = '';", "probabilityField.control.value = '';",
                 "notesField.control.value = '';", "linksEditor.setLinks([]);", "nameField.control.focus();"):
        assert line in reset
    assert "typeField" not in reset and "gateField" not in reset, "type and gate carry over"
    # Ctrl+Enter reaches the dialog from every control, before the plain-Enter rule
    modal = _function(dialogs, "function onKeydown(event)")
    assert modal.index("cfg.onCtrlEnter(event);") < modal.index("cfg.onEnter(event);")
    # the shell adopts that node at once; an OK node only when the dialog is gone
    main = _read(STATIC / "main.js")
    submit = _function(main, "async function actionAdd()")
    hook = submit[submit.index("const submit = (values, how) => {"):submit.index("const fields = await fn(")]
    assert "adopt(result, values.name, true);" in hook
    assert "if (result && posting === last) adopt(result, last.name, false);" in submit


def test_1_a_closed_dialog_gives_the_focus_to_the_trees_lead_row():
    restore = _function(_read(STATIC / "dialogs.js"), "export function restoreFocus(trigger)")
    assert "host.querySelector('[role=\"treeitem\"][tabindex=\"0\"]')" in restore
    assert restore.index("lead.focus();") < restore.index("host.focus();")


# ---- 2: the top event is selected at start-up ---------------------------------------------

def test_2_boot_selects_the_top_event():
    boot = _function(_read(STATIC / "main.js"), "async function boot()")
    assert boot.index("store.setState(state);") < boot.index("if (!store.selectedId) store.select(rootId());")
    assert boot.index("if (!store.selectedId) store.select(rootId());") < boot.index("await loadPanels();")


# ---- 4: a leaf that gains its first child -------------------------------------------------

_FIRST_CHILD_STUBS = """
const shown = [];
let eta = false;
let tree = null;
const isEtaMode = () => eta;
const store = { findNode: (id) => (tree && tree[id]) || null };
const t = (key, vars) => key + ' ' + JSON.stringify(vars);
const formatProb = (v) => 'p' + v;
const getSigFigs = () => 3;
const toast = (message, kind, code, options) => shown.push([message, kind, !!(options && options.action)]);
const showInValidation = () => ({ action: { label: 'Show in Validation', onClick() {} } });
"""


@needs_node
def test_4_first_child_warning_rule():
    fn = _function(_read(STATIC / "main.js"), "function firstChildWarning(parentId)")
    script = _FIRST_CHILD_STUBS + fn + """
tree = {
  leaf: { name: 'Leaf', probability: 0.05, children: [] },
  one: { name: 'Default', probability: 1, children: [] },
  gate: { name: 'Gate', probability: 0.05, children: [{}] },
  nameless: { probability: 0.25 },
  text: { name: 'Text', probability: 'abc', children: [] },
};
const out = {};
for (const id of ['leaf', 'one', 'gate', 'nameless', 'text', 'missing']) out[id] = typeof firstChildWarning(id);
eta = true;
out.etaLeaf = typeof firstChildWarning('leaf');
eta = false;
const warn = firstChildWarning('leaf');
out.before = shown.length;   // nothing is shown until the change went through
warn();
out.shown = shown;
console.log(JSON.stringify(out));
"""
    got = _node(script)
    assert got["leaf"] == "function" and got["nameless"] == "function"
    # 1 is the untouched default; a node with children already ignores its own value
    assert got["one"] == got["gate"] == got["text"] == got["missing"] == "object"
    assert got["etaLeaf"] == "object", "an event tree uses every node's probability"
    assert got["before"] == 0
    assert got["shown"] == [['msg.firstChild {"name":"Leaf","p":"p0.05"}', "warn", True]]


def test_4_add_move_and_drag_all_ask_before_the_change():
    main = _read(STATIC / "main.js")
    add = _function(main, "async function actionAdd()")
    adopt = add[add.index("const adopt = (result, name, quiet) => {"):add.index("const submit = (values, how) => {")]
    assert adopt.index("firstChildWarning(parentId)") < adopt.index("store.applyMutation(result);") < adopt.index("if (warn) warn();")
    assert "firstChildWarning," in main[main.index("window.ftaShell = {"):]
    # tree.js: one function serves the keyboard moves and the drop
    tree = _read(STATIC / "tree.js")
    move = _function(tree, "async function requestMove(id, newParentId, index, sameParent)")
    assert move.index("shell.firstChildWarning(String(newParentId))") < move.index("api.post(")
    assert "!sameParent && shell" in move, "a re-order among siblings gives nobody a first child"
    assert move.index("store.applyMutation(result);") < move.index("if (warn) warn();")
    assert tree.count("requestMove(") >= 6


def test_4_details_greys_the_base_probability_of_a_node_with_children():
    details = _read(STATIC / "details.js")
    extras = _function(details, "function updateExtras(node, force)")
    assert "const unused = !model && n > 0 && store.metadata().mode !== 'ETA';" in extras
    assert "prob.parentNode.classList.toggle('is-unused', unused);" in extras
    assert "t('details.probabilityUnused')" in extras
    assert "prob.readOnly = !!model;" in extras, "greyed, not locked: the value stays editable"
    assert ".fta-details .fta-field.is-unused input { color: var(--fta-muted-fg); }" in details


# ---- 5: double-click ------------------------------------------------------------------------

def test_5_double_click_is_read_from_the_click_count():
    tree = _read(STATIC / "tree.js")
    assert "addEventListener('dblclick'" not in tree
    click = _braced(tree, tree.index("host.addEventListener('click', (event) => {"))
    second = _braced(click, click.index("if (event.detail === 2"))
    assert "if (target.closest('.fta-tree-label')) startRename(id);" in second
    assert "else if (item.hasAttribute('aria-expanded')) toggle(id);" in second
    # after the twisty (two clicks there are two toggles), before the selection
    assert click.index("target.closest('.fta-tree-twisty')") < click.index("event.detail === 2") < click.index("setSelection([id], id);")
    assert "!event.ctrlKey && !event.metaKey && !event.shiftKey" in click


# ---- 6: Ctrl+Z with a dropdown focused ------------------------------------------------------

@needs_node
def test_6_history_shortcuts_work_from_a_select_and_nothing_else_does():
    main = _read(STATIC / "main.js")
    script = (
        re.search(r"const NON_TEXT_INPUTS = new Set\(\[.*?\]\);", main, re.S).group(0) + "\n"
        + _function(main, "function isTextEntry(el)") + "\n"
        + _function(main, "function blocksShortcut(el, event)") + """
const select = { tagName: 'SELECT' };
const text = { tagName: 'INPUT', type: 'text' };
const area = { tagName: 'TEXTAREA' };
const box = { tagName: 'INPUT', type: 'checkbox' };
const row = { tagName: 'LI' };
const key = (k, extra) => Object.assign({ key: k, ctrlKey: true }, extra || {});
console.log(JSON.stringify({
  selectZ: blocksShortcut(select, key('z')),
  selectShiftZ: blocksShortcut(select, key('Z', { shiftKey: true })),
  selectY: blocksShortcut(select, key('y')),
  selectMetaZ: blocksShortcut(select, { key: 'z', metaKey: true }),
  selectA: blocksShortcut(select, key('a')),
  selectD: blocksShortcut(select, key('d')),
  selectAltZ: blocksShortcut(select, key('z', { altKey: true })),
  selectPlainZ: blocksShortcut(select, { key: 'z' }),
  selectDelete: blocksShortcut(select, { key: 'Delete' }),
  textZ: blocksShortcut(text, key('z')),
  areaZ: blocksShortcut(area, key('z')),
  boxZ: blocksShortcut(box, key('z')),
  rowA: blocksShortcut(row, key('a')),
  nothing: blocksShortcut(null, key('z')),
}));
""")
    assert _node(script) == {
        "selectZ": False, "selectShiftZ": False, "selectY": False, "selectMetaZ": False,
        "selectA": True, "selectD": True, "selectAltZ": True, "selectPlainZ": True, "selectDelete": True,
        "textZ": True, "areaZ": True,  # a text field keeps its own undo
        "boxZ": False, "rowA": False, "nothing": False,
    }


def test_6_only_the_shortcut_guard_changed():
    main = _read(STATIC / "main.js")
    keys = _function(main, "function onKeyDown(event)")
    assert "if (blocksShortcut(event.target, event)) return;" in keys
    assert "isTextEntry(event.target)" not in keys
    # a save still blurs a focused <select> like any other field
    assert "if (active && isTextEntry(active) && typeof active.blur === 'function')" in main
    assert "if (tag === 'TEXTAREA' || tag === 'SELECT') return true;" in _function(main, "function isTextEntry(el)")


# ---- 7: the tree's open / closed state belongs to the file --------------------------------

def _expansion_source() -> str:
    tree = _read(STATIC / "tree.js")
    consts = "\n".join(re.search(r"^const %s = [^;]+;" % name, tree, re.M).group(0)
                       for name in ("EXPANDED_KEY", "EXPANDED_FILES_MAX"))
    functions = "\n".join(_function(tree, header) for header in (
        "function documentKey()", "function expandedStorage(key)", "function readExpandedTable(key)",
        "function writeExpandedTable(key, table)", "function readExpanded(key)",
        "function writeExpanded(key, expanded)"))
    return """
function storage() {
  const data = {};
  return { data, getItem: (k) => (k in data ? data[k] : null), setItem: (k, v) => { data[k] = String(v); } };
}
const window = { localStorage: storage(), sessionStorage: storage() };
const store = { state: null };
""" + consts + "\n" + functions + "\n"


@needs_node
def test_7_expansion_is_kept_per_file():
    script = _expansion_source() + """
const out = {};
out.unknown = readExpanded('C:/a.json');
writeExpanded('C:/a.json', new Set(['root']));
writeExpanded('C:/b.json', new Set(['root', 'root_0']));
out.a = Array.from(readExpanded('C:/a.json'));
out.b = Array.from(readExpanded('C:/b.json'));
out.keysOf = Object.keys(window.localStorage.data);
// the unsaved document: its own slot, in this tab only
writeExpanded('', new Set(['root', 'root_1']));
out.untitled = Array.from(readExpanded(''));
out.untitledInLocal = (window.localStorage.data[EXPANDED_KEY] || '').includes('root_1');
out.untitledInSession = (window.sessionStorage.data[EXPANDED_KEY] || '').includes('root_1');
writeExpanded('', null);
out.forgotten = readExpanded('');
// the document key follows the loaded file
store.state = { currentPath: 'C:/a.json' }; out.keyFile = documentKey();
store.state = { currentPath: null }; out.keyNone = documentKey();
store.state = null; out.keyBoot = documentKey();
// the oldest file drops out; writing a file again makes it the newest
for (let i = 0; i < EXPANDED_FILES_MAX; i += 1) {
  if (i === 5) writeExpanded('C:/a.json', new Set(['again']));
  writeExpanded('C:/file' + i + '.json', new Set(['root']));
}
const table = JSON.parse(window.localStorage.data[EXPANDED_KEY]);
out.count = Object.keys(table).length;
out.bDropped = readExpanded('C:/b.json');
out.aKept = Array.from(readExpanded('C:/a.json') || []);
// a corrupt value is the default, not a crash
window.localStorage.data[EXPANDED_KEY] = '[1, 2';
out.corrupt = readExpanded('C:/a.json');
window.localStorage.data[EXPANDED_KEY] = '["root"]';
out.oldShape = readExpanded('C:/a.json');
console.log(JSON.stringify(out));
"""
    got = _node(script)
    assert got["unknown"] is None
    assert got["a"] == ["root"] and got["b"] == ["root", "root_0"]
    assert got["keysOf"] == ["fta.tree.expanded.v2"]
    assert got["untitled"] == ["root", "root_1"]
    assert got["untitledInSession"] is True and got["untitledInLocal"] is False
    assert got["forgotten"] is None
    assert (got["keyFile"], got["keyNone"], got["keyBoot"]) == ("C:/a.json", "", "")
    assert got["count"] == 40 and got["bDropped"] is None and got["aKept"] == ["again"]
    assert got["corrupt"] is None and got["oldShape"] is None


def test_7_a_new_document_loads_its_own_state_and_save_as_keeps_the_one_on_screen():
    tree = _read(STATIC / "tree.js")
    assert "fta.tree.expanded.v1" not in tree.replace("(v1 was one list", "")
    document = _function(tree, "function onDocument()")
    for line in ("docKey = documentKey();", "if (docKey === '') writeExpanded(docKey, null);",
                 "expanded = readExpanded(docKey);", "seeded = expanded !== null;", "knownBranches = null;"):
        assert line in document, line
    # between the store showing a new path and fta:document, nothing is written
    assert tree.count("!keyInDoubt") >= 4
    subscriber = _braced(tree, tree.index("const unsubscribe = store.subscribe(() => {"))
    doubt = _braced(subscriber, subscriber.index("if (documentKey() !== docKey && !keyInDoubt)"))
    assert "Promise.resolve().then(() => {" in doubt and "if (expanded && !query) saveExpanded();" in doubt
    assert "const saveExpanded = () => writeExpanded(docKey, expanded);" in tree


# ---- 8: a selection made elsewhere scrolls its row into view ------------------------------

def test_8_a_new_selection_is_scrolled_into_view():
    tree = _read(STATIC / "tree.js")
    subscriber = _braced(tree, tree.index("const unsubscribe = store.subscribe(() => {"))
    assert "const moved = Boolean(selectedId) && selectedId !== lastSelected;" in subscriber
    assert subscriber.index("render();") < subscriber.index("if (moved && !editing) scrollToRow(selectedId);")
    scroll = _function(tree, "function scrollToRow(id)")
    assert "row.scrollIntoView({ block: 'nearest', inline: 'nearest' });" in scroll


# ---- 9: first / last --------------------------------------------------------------------------

def test_9_each_end_of_the_sibling_list_has_its_own_sentence():
    tree = _read(STATIC / "tree.js")
    assert "say(t(direction === 'up' ? 'tree.moveNoRoomUp' : 'tree.moveNoRoomDown'), 'info');" in tree
    catalog = _read(STATIC / "i18n" / "ux1.js")
    assert "'tree.moveNoRoomUp': 'It is already the first of its siblings.'," in catalog
    assert "'tree.moveNoRoomDown': 'It is already the last of its siblings.'," in catalog
    assert "tree.moveNoRoom'" not in _read(STATIC / "main.js")
    assert "'./i18n/ux1.js'," in _read(STATIC / "main.js")


# ---- 10, 11, 34: the diagram's jump, zoom buttons and wheel ------------------------------

def test_10_a_jump_to_a_node_in_view_moves_nothing():
    jump = _function(_read(STATIC / "diagram.js"), "function jumpTo(id)")
    assert "if (inView) return;" in jump
    assert jump.index("if (inView) return;") < jump.index("autoFit = false;") < jump.index("applyTransform();")
    assert "box.left >= view.left && box.right <= view.right" in jump
    assert "box.top >= view.top && box.bottom <= view.bottom" in jump


def test_11_the_zoom_buttons_hold_the_selected_node_or_the_middle():
    diagram = _read(STATIC / "diagram.js")
    anchor = _function(diagram, "function zoomAnchor()")
    assert "svgEl.querySelector('g.node.is-selected')" in anchor
    assert "return { x: view.left + view.width / 2, y: view.top + view.height / 2 };" in anchor
    zoom = _function(diagram, "function zoomBy(factor, originX, originY)")
    assert "typeof originX === 'number' ? { x: originX, y: originY } : zoomAnchor();" in zoom
    assert "tx = px - ((px - tx) * next) / scale;" in zoom
    assert "if (typeof originX === 'number') {" not in zoom, "there is always a point held still"


def test_34_the_plain_wheel_zooms():
    diagram = _read(STATIC / "diagram.js")
    wheel = _braced(diagram, diagram.index("stage.addEventListener('wheel', (ev) => {"))
    assert "ctrlKey" not in wheel and "metaKey" not in wheel
    assert "if (!ev.deltaY) return;" in wheel and "ev.preventDefault();" in wheel
    assert "zoomBy(Math.pow(ZOOM_STEP, -notches), ev.clientX, ev.clientY);" in wheel
    assert "Math.max(-1, Math.min(1, ev.deltaY / WHEEL_NOTCH))" in wheel
    assert "{ passive: false }" in diagram[diagram.index("stage.addEventListener('wheel'"):][:1200]


# ---- 12: the top bar on the first edit -------------------------------------------------------

def test_12_the_saved_pill_has_one_width_and_the_ok_chip_is_small():
    css = _read(CSS)
    assert ".dirty::before { content: attr(data-saved); }" in css
    assert ".dirty::after { content: attr(data-unsaved); }" in css
    sizers = css[css.index(".dirty::before,\n.dirty::after {"):css.index(".dirty::before { content")]
    assert "visibility: hidden;" in sizers and "grid-column: 2;" in sizers and "grid-row: 1;" in sizers
    shell = _function(_read(STATIC / "main.js"), "function renderShell(state)")
    assert "badge.dataset.saved = t('status.saved');" in shell
    assert "badge.dataset.unsaved = t('status.unsaved');" in shell
    assert '.capbar__button[data-state="ok"] .capbar__text {' in css
    # the words stay for a screen reader and in the tooltip
    caps = _read(STATIC / "capabilities.js")
    assert "button.setAttribute('aria-label', t('cap.button') + ': ' + chip.text);" in caps
    assert "button.title = chip.text" in caps


# ---- 15: the Open dialog and a path that is not there ---------------------------------------

@pytest.fixture
def sandbox(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    return fsbrowser.resolve_root(root)


def test_15_a_missing_folder_is_a_404_and_a_file_is_a_400(sandbox):
    (sandbox / "doc.json").write_text("{}", encoding="utf-8")
    with pytest.raises(fsbrowser.PathRejected) as missing:
        fsbrowser.list_directory("nope", sandbox)
    with pytest.raises(fsbrowser.PathRejected) as a_file:
        fsbrowser.list_directory("doc.json", sandbox)
    assert (missing.value.reason, missing.value.status) == ("not_a_directory", 404)
    assert (a_file.value.reason, a_file.value.status) == ("not_a_directory", 400)


def test_15_the_dialog_tells_the_two_apart():
    dialog = _read(STATIC / "filedialog.js")
    go = _function(dialog, "async function goToPath(raw)")
    assert "const missing = err.status === 404;" in go
    branch = _braced(go, go.index("if (mode === 'open' && missing) {"))
    assert "'file.errFileNotFound' : 'file.errFolderNotFound'" in branch and "return;" in branch
    assert go.index("if (mode === 'open' && missing) {") < go.index("t('file.errExtension'")
    # a relative path is relative to the folder on screen; "~" is left to the server
    assert "if (cwd && !isAbsolutePath(value) && !/^~(?:[\\\\/]|$)/.test(value)) value = joinPath(cwd, value);" in go


@needs_node
def test_15_what_counts_as_an_absolute_path():
    dialog = _read(STATIC / "filedialog.js")
    script = _function(dialog, "function isAbsolutePath(path)") + """
console.log(JSON.stringify(['/x', '\\\\x', 'C:\\\\x', 'c:/x', 'C:x', '\\\\\\\\host\\\\share', 'x', 'sub/x.json', '~', '~/x', '', null]
  .map((p) => isAbsolutePath(p))));
"""
    assert _node(script) == [True, True, True, True, True, True, False, False, False, False, False, False]


def test_15_tilde_is_the_home_folder_and_stays_confined(tmp_path, monkeypatch):
    home = fsbrowser.resolve_root(tmp_path)
    (home / "docs").mkdir()
    monkeypatch.setattr(fsbrowser.Path, "home", classmethod(lambda cls: Path(str(home))))
    # the sandbox is the home folder (the default): "~" is the root itself
    assert fsbrowser.resolve_in_root("~", home) == home
    assert fsbrowser.resolve_in_root("~/docs/a.json", home) == home / "docs" / "a.json"
    assert fsbrowser.resolve_in_root("~\\docs", home) == home / "docs"
    assert fsbrowser.list_directory("~/docs", home)["path"] == str(home / "docs")
    # a sandbox elsewhere: home is outside it, and refused like any other path
    inner = fsbrowser.resolve_root(home / "docs")
    with pytest.raises(fsbrowser.PathRejected) as outside:
        fsbrowser.resolve_in_root("~", inner)
    assert outside.value.reason == "outside_root"
    with pytest.raises(fsbrowser.PathRejected) as climbing:
        fsbrowser.resolve_in_root("~/../x", home)
    assert climbing.value.reason == "traversal"
    # only the bare forms: "~name" is a file name, relative to the root
    assert fsbrowser.resolve_in_root("~backup.json", home) == home / "~backup.json"


# ---- 16: the file name in the status line and the tab title ---------------------------------

def test_16_the_status_line_names_the_file_first_and_the_tab_carries_it():
    html = _read(INDEX)
    assert html.index('id="statusline-file"') < html.index('id="statusline-path"') < html.index('id="statusline-msg"')
    css = _read(CSS)
    rule = _braced(css, css.index(".statusline__file {"))
    assert "flex: 0 0 auto;" in rule, "the file name never gives way"
    shell = _function(_read(STATIC / "main.js"), "function renderShell(state)")
    assert "const fileName = state.currentPath ? pathBaseName(state.currentPath) : '';" in shell
    assert "$('#statusline-file').textContent = fileName || t('status.noFile');" in shell
    assert "const tabTitle = (dirty ? '● ' : '') + docName + ' - ' + APP_NAME;" in shell
    assert "if (document.title !== tabTitle) document.title = tabTitle;" in shell
    assert "const APP_NAME = 'FTA Editor';" in _read(STATIC / "main.js")
    assert "<title>FTA Editor</title>" in html


# ---- 23: delete confirmations ------------------------------------------------------------------

def test_23_delete_counts_the_nodes_and_focuses_cancel():
    dialogs = _read(STATIC / "dialogs.js")
    confirm = _function(dialogs, "export function confirmDialog(message, options)")
    assert "if (opts.focusCancel) cancel.focus();\n  else confirm.focus();" in confirm
    # Enter on a focused button is that button's click, never the dialog's OK
    modal = _function(dialogs, "function onKeydown(event)")
    assert "if (tag === 'textarea' || tag === 'button'" in modal
    main = _function(_read(STATIC / "main.js"), "async function actionDelete()")
    assert "total > 1 ? t('confirm.deleteTree', { name, n: total }) : t('confirm.deleteLeaf', { name })" in main
    assert "focusCancel: true," in main
    many = _function(_read(STATIC / "tree.js"), "async function deleteMany(ids)")
    assert "for (const id of ids) total += subtreeIds(id).size;" in many
    assert "focusCancel: true," in many
    assert "t('tree.confirmDeleteManyTree', { n: ids.length, total: total })" in many
    # the discard prompts are not deletes and keep their focus (batch 2 reworks them)
    assert _read(STATIC / "main.js").count("focusCancel: true") == 1


# ---- 31: Edit ---------------------------------------------------------------------------------

def test_31_edit_focuses_and_selects_the_name():
    edit = _function(_read(STATIC / "main.js"), "async function actionEdit()")
    focused = _braced(edit, edit.index("if (name && !name.disabled && name.offsetParent !== null) {"))
    assert "name.focus();" in focused and "name.select();" in focused and "return;" in focused
    assert edit.index("openTab('details');") < edit.index("name.focus();") < edit.index("toast(t('msg.editInDetails'), 'info');")


# ---- 32: Enter in the search box ---------------------------------------------------------------

def test_32_enter_steps_through_the_matches():
    tree = _read(STATIC / "tree.js")
    keys = _braced(tree, tree.index("search.addEventListener('keydown', (event) => {"))
    enter = _braced(keys, keys.index("if (event.key === 'Enter') {"))
    assert "setQuery(search.value);" in enter and "stepToMatch(event.shiftKey ? -1 : 1);" in enter
    assert "focusItem(" not in enter, "the caret stays in the box"
    step = _function(tree, "function stepToMatch(step)")
    assert "if (searchFresh || at === -1) next = step > 0 ? 0 : ids.length - 1;" in step
    assert "else next = (at + step + ids.length) % ids.length;" in step
    assert "setSelection([id], id);" in step and "scrollToRow(id);" in step
    # a new query starts again from the first match
    assert "query = next;\n    searchFresh = true;" in _function(tree, "function setQuery(raw)")


# ---- 33: the diagram's numbers -------------------------------------------------------------------

def _core(name: str) -> WebCore:
    core = WebCore()
    ok, error = core.load_from_json(str(EXAMPLES / name))
    assert ok, error
    core.recalculate_probabilities()
    return core


def _symbol_rows(dot: str):
    """{node name: [(point size, bold, text), ...]} for the boxes of a symbols diagram."""
    out = {}
    for name, label in re.findall(r'(?m)^  (\w+) \[shape=(?:box|ellipse), class="fta-(?:box|event)[^\n]*label=<(.*)>\];$', dot):
        rows = []
        for bold_open, size, text, bold_close in re.findall(
                r'(<B>)?<FONT POINT-SIZE="(\d+)">([^<]*)</FONT>(</B>)?', label):
            assert bool(bold_open) == bool(bold_close)
            rows.append((int(size), bool(bold_open), text.strip()))
        out[name] = rows
    return out


def test_33_symbols_the_number_row_is_bold_and_the_largest():
    dot, _ = build_dot_text2(_core("challenger_fta_en.json"), style="symbols")
    boxes = _symbol_rows(dot)
    assert len(boxes) == 13
    assert SYMBOLS_PROB_PT >= SYMBOLS_NAME_PT > 9, "1.7 drew the numbers at 9 pt"
    for name, rows in boxes.items():
        assert rows[0][:2] == (SYMBOLS_NAME_PT, False), name
        numbers = [row for row in rows if re.match(r"[qQ]=", row[2])]
        assert len(numbers) == 1 and numbers[0][:2] == (SYMBOLS_PROB_PT, True), (name, rows)
        assert [row for row in rows if row[1]] == numbers, "only the number is bold"


def test_33_symbols_an_event_shows_its_number_once():
    core = _core("challenger_fta_en.json")
    dot, id_map = build_dot_text2(core, style="symbols")
    for name, rows in _symbol_rows(dot).items():
        node = core.find_node_by_id(id_map[name])
        text = [row[2] for row in rows if re.match(r"[qQ]=", row[2])][0]
        if node.get("children"):
            assert re.fullmatch(r"Q=\S+", text), (name, text)
        else:
            assert re.fullmatch(r"q=\S+", text), (name, text)
            assert node["calculatedProbability"] == node["probability"]


def test_33_symbols_a_leaf_whose_two_values_differ_still_shows_both():
    """An event with an AND link is its own value times its target's."""
    core = WebCore()
    core.set_data({
        "id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "probability": 1.0, "links": [],
        "children": [
            {"id": "a", "name": "Basic", "type": "Event", "probability": 0.5, "logicGate": "OR",
             "children": [], "links": []},
            {"id": "b", "name": "Linked", "type": "Event", "probability": 0.25, "logicGate": "AND",
             "children": [], "links": [{"target_id": "a", "relation": "AND"}]},
        ],
    })
    core.recalculate_probabilities()
    assert core.find_node_by_id("b")["calculatedProbability"] == 0.125
    rows = _symbol_rows(build_dot_text2(core, style="symbols")[0])
    assert [row[2] for row in rows["b"]][-1] == "q=0.250 | Q=0.125"
    assert [row[2] for row in rows["a"]][-1] == "q=0.500"


def test_33_compact_keeps_its_text_and_only_the_meta_type_grows():
    dot, _ = build_dot_text2(_core("challenger_fta_en.json"), style="compact")
    assert "<B>" not in dot
    sizes = re.findall(r'<FONT POINT-SIZE="(\d+)">', dot)
    assert sizes == ["14", str(COMPACT_META_PT)] * 13 and COMPACT_META_PT > 9
    # the meta row reads as it did: both numbers, for a leaf too
    metas = [text.strip() for text in re.findall(r'<FONT POINT-SIZE="%d">([^<]*)</FONT>' % COMPACT_META_PT, dot)]
    assert all(re.search(r"P:\S+ \| P_calc:\S+", text) for text in metas), metas
    assert "P:0.100 | P_calc:0.100" in metas


def test_33_the_label_readers_follow():
    """The GUI suite reads a lone q= as the node's calculated value too."""
    gui = _read(REPO / "fta_web" / "tests" / "gui" / "b2b.js")
    reader = _function(gui, "function labelNumbers(texts)")
    assert "if (out.calc === undefined) out.calc = m[1];" in reader


@needs_node
def test_33_the_gui_label_reader():
    gui = _read(REPO / "fta_web" / "tests" / "gui" / "b2b.js")
    script = _function(gui, "function labelNumbers(texts)") + """
console.log(JSON.stringify([
  ['Pump A', 'q=0.0100'],
  ['Gate', 'Q=0.140'],
  ['House', 'House: ON', 'q=0.250 | Q=1.00'],
  ['Top', 'Q=0.0684 (MCUB)', 'tree walk 0.0349'],
  ['Top', 'Gate: AND | P:1.00 | P_calc:0.0684 (MCUB) | tree walk 0.0349'],
  ['Leaf', 'P:0.100 | P_calc:0.100'],
].map(labelNumbers)));
"""
    assert _node(script) == [
        {"mcub": False, "base": "0.0100", "calc": "0.0100"},
        {"mcub": False, "calc": "0.140"},
        {"mcub": False, "calc": "1.00", "base": "0.250"},
        {"mcub": True, "walk": "0.0349", "calc": "0.0684"},
        {"mcub": True, "walk": "0.0349", "calc": "0.0684", "base": "1.00"},
        {"mcub": False, "calc": "0.100", "base": "0.100"},
    ]


# ---- 43: Enter in a Details field ---------------------------------------------------------------

def test_43_enter_commits_and_returns_the_focus_to_the_tree_row():
    details = _read(STATIC / "details.js")
    start = details.index("if (event.key === 'Enter' && field.spec.kind !== 'textarea') {")
    enter = _braced(details, start)
    refused = _braced(enter, enter.index("if (!validateField(key, control.value).ok) {"))
    assert "commitField(key);" in refused and "return;" in refused and "focus()" not in refused
    assert enter.index("validateField(key, control.value)") < enter.index("const row = treeLeadRow();")
    assert "if (row) row.focus();\n          else control.blur();" in enter
    lead = _function(details, "function treeLeadRow()")
    assert "tree.querySelector('[role=\"treeitem\"][tabindex=\"0\"]')" in lead
    # moving the focus is what commits: the blur listener is still the one path
    assert "control.addEventListener('blur', () => commitField(key));" in details
