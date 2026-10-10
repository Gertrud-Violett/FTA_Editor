"""Regressions from the 2026-10 review of the 1.7 analysis tabs and their i18n.

Each bug was reproduced in a real browser against the running app first; the
checks here follow test_frontend_b2b.py: pure JS logic runs under Node when it
is on PATH (extracted from the module source), DOM wiring is pinned at source
level.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STATIC = REPO / "fta_web" / "static" / "js"
TABS = STATIC / "tabs"

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _node(script: str):
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def _function(src: str, name: str) -> str:
    """The source of `[export] function name(...) {...}` (top level), export dropped."""
    match = re.search(r"^(?:export )?function %s\(.*?\n\}" % re.escape(name), src, re.S | re.M)
    assert match, "function %s not found" % name
    return match.group(0).replace("export ", "", 1)


def _block(src: str, start: str) -> str:
    """The body of the first `<start> {` ... matching `}` (brace counting)."""
    at = src.index(start)
    i = src.index("{", at + len(start) - 1)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i + 1:j]
    raise AssertionError("unbalanced block after %r" % start)


# ---- FMEA: the occurrence table on screen is the open document's ---------------------
# Import sends the table the tab shows and the server saves it into the open
# document. The tab kept the table of the document it was previewed in, so
# after Open, Import overwrote the new document's calibrated table (rank 5:
# 0.003 -> 0.0005) and the imported events got the old table's values.

@needs_node
def test_fmea_document_occ_table():
    src = _read(TABS / "fmea.js")
    code = re.search(r"const AIAG_DEFAULT = Object\.freeze\(\{.*?\}\);", src, re.S).group(0)
    code += "\n" + _function(src, "documentOccTable")
    cases = [
        {"fmeaOccurrenceTable": {"1": 1e-7, "5": 0.003}},
        {"missionTime": 10},
        None,
    ]
    got = _node(code + "\nconsole.log(JSON.stringify(%s.map((a) => documentOccTable(a))));" % json.dumps(cases))
    assert got[0] == {"1": 1e-7, "5": 0.003}
    assert got[1]["5"] == 5e-4 and len(got[1]) == 10
    assert got[2] == got[1]
    # a copy: editing the tab's table must not edit the store's analysis block
    script = code + ("\nconst a = {fmeaOccurrenceTable: {'5': 0.003}}; const t = documentOccTable(a); t['5'] = 1;"
                     "\nconsole.log(JSON.stringify(a.fmeaOccurrenceTable['5']));")
    assert _node(script) == 0.003


def test_fmea_new_document_resets_document_state():
    src = _read(TABS / "fmea.js")
    assert "window.addEventListener('fta:document', onDocument);" in src
    assert "window.removeEventListener('fta:document', onDocument);" in src
    body = _block(src, "function onDocument()")
    assert "state.occ = documentOccTable(store.state && store.state.analysis);" in body
    assert "state.occTouched = false;" in body
    assert "state.parentExplicit = false;" in body, "the old document's import target must not stick"
    assert "state.result = null;" in body, "the old document's created/updated ids must not stay"
    assert "renderAll();" in body


def test_fmea_follows_the_document_table_until_edited():
    src = _read(TABS / "fmea.js")
    sync = _block(src, "function syncOccWithDocument()")
    assert sync.strip().startswith("if (state.occTouched) return;"), "a table the user is editing stays"
    assert "documentOccTable(store.state && store.state.analysis)" in sync
    assert "paintOccInputs();" in sync
    on_stale = _block(src, "    onStale()")
    assert "syncOccWithDocument();" in on_stale, "an undo that changes the document's table repaints it"


# ---- FMEA: "Import under" shows the node Import will use ------------------------------
# The select was filled when the tab painted and never followed the tree. With
# the tab open, a click on another tree node left it showing "Top (root)" while
# Import (defaultParent(): the selection, until the user picks a parent) added
# the events under the clicked node.

def test_fmea_parent_select_follows_the_tree_selection():
    src = _read(TABS / "fmea.js")
    body = _block(src, "const unsubscribe = store.subscribe(() =>")
    assert "store.selectedId === seenSelection" in body
    assert "if (!state.parentExplicit) fillParentSelect();" in body, "an explicit pick still sticks"
    assert "if (typeof unsubscribe === 'function') unsubscribe();" in _block(src, "    dispose()")
    fill = _block(src, "function fillParentSelect()")
    assert "const chosen = defaultParent();" in fill and "state.parentId = chosen;" in fill
    run = _block(src, "async function runImport()")
    # the jump onto an imported event must not move the select afterwards
    assert run.index("state.parentExplicit = true;") < run.index("ctx.jumpTo(")


# ---- FMEA: the newest preview wins -------------------------------------------------------
# Loading a.csv and then b.csv before a.csv answered: the slower a.csv answer
# replaced b.csv's preview, mapping and path, and Import would read a.csv.

def test_fmea_older_preview_answer_is_dropped():
    src = _read(TABS / "fmea.js")
    body = _block(src, "async function loadPreview(path, sheet, fresh)")
    assert body.index("const mine = ++previewSeq;") < body.index("await ctx.api.post('/fmea/preview', body);")
    after = body[body.index("await ctx.api.post('/fmea/preview', body);"):]
    assert after.index("if (mine !== previewSeq) return;") < after.index("state.preview = res;")
    catch = _block(body, "} catch (err)")
    assert "if (mine !== previewSeq) return;" in catch
    final = _block(body, "} finally")
    assert "if (mine === previewSeq) {" in final, "only the newest load clears busy and repaints"


# ---- Uncertainty: a run that overlapped an edit is stale -------------------------------
# The server samples the tree as it is when the request arrives (a deep copy,
# outside the lock), so editing during a run is allowed. onStale only marked
# an existing result, and the answer then set stale = false: a run started
# before the edit was shown as current (point estimate 0.301 next to a
# headline of 0.4006), with no "the tree has changed" note.

def test_uncertainty_run_overlapping_an_edit_is_stale():
    src = _read(TABS / "uncertainty.js")
    run = _block(src, "async function run()")
    snap = run.index("const sampled = ctx.store.state || {};")
    assert snap < run.index("await ctx.api.post('/analysis/uncertainty', body)"), \
        "the tree must be noted before the request"
    assert "stale = now.tree !== sampled.tree || now.analysis !== sampled.analysis;" in run
    assert "stale = false;" not in run, "an answer must not clear staleness unconditionally"


# ---- Uncertainty: a seed the browser cannot hold exactly is refused --------------------
# 9007199254740993 ran as seed 9007199254740992 (a different, silently changed
# seed); 1e20 came back as the server's English 400 instead of the field's own
# invalid marker.

@needs_node
def test_uncertainty_seed_must_be_a_safe_integer():
    src = _read(TABS / "uncertainty.js")
    common = _read(TABS / "analysis_common.js")
    code = _function(common, "parseNumber") + "\n" + _function(src, "seedIsValid")
    cases = ["", "0", "42", "9007199254740991", "9007199254740992", "9007199254740993",
             "99999999999999999999", "-1", "1.5", "abc"]
    script = code + "\nconsole.log(JSON.stringify(%s.map((c) => seedIsValid(parseNumber(c)))));"
    got = _node(script % json.dumps(cases))
    assert dict(zip(cases, got)) == {
        "": True, "0": True, "42": True, "9007199254740991": True,
        "9007199254740992": False, "9007199254740993": False, "99999999999999999999": False,
        "-1": False, "1.5": False, "abc": False,
    }
    for name in ("function readInputs()", "async function saveDefaults()"):
        assert "const badSeed = !seedIsValid(seed);" in _block(src, name), name


# ---- Importance: stale FV values never colour the changed tree -------------------------
# With the tab visible, an edit left the diagram and the tree bars coloured by
# the previous run's FV until the debounced re-run answered -- and for good
# when that re-run failed (a gate made 10-of-25 voting: 422), while the tab
# itself said the results were stale.

def test_importance_overlay_is_cleared_while_stale():
    src = _read(TABS / "importance.js")
    guard = re.search(r"function applyOverlay\(\) \{.*?if \((.*?)\) \{", src, re.S).group(1)
    assert "stale" in guard.split("||")[3], guard
    body = _block(src, "    onStale()")
    assert body.index("stale = true;") < body.index("applyOverlay();") < body.index("if (active && justActivated)"), \
        "cleared on every stale signal, not only right after activation"


# ---- Cut Sets: the first run after New / Open uses the new document's limits ----------
# onDocument cleared `edited` and called run(), which read the limit inputs
# before anything refilled them: a max order typed (not saved) for the old
# document ran on the new one -- 1 of 2 cut sets and "Truncated by max order"
# under an input that by then showed the document's 6.

def test_cutsets_new_document_refills_limits_before_running():
    src = _read(TABS / "cutsets.js")
    body = _block(src, "const onDocument = () =>")
    assert body.index("edited.clear();") < body.index("paint();") < body.index("if (active) run();")
    toolbar = _block(src, "function paintToolbar()")
    assert "if (!edited.has(input) && document.activeElement !== input) {" in toolbar
    run = _block(src, "async function run()")
    assert run.index("const payload = limitsBody();") < run.index("paintToolbar();"), \
        "run() reads the inputs before it repaints them, so they must be current already"


# ---- Cut Sets: a selected row stays on the same cut set after a re-run ---------------
# "Keep the selection if the same cut set is still there" compared ranks: the
# user picked {B3} (rank 1), an edit made it rank 2, and the re-run moved the
# selection and the tree/diagram highlight to {B1, B2}, now rank 1.

@needs_node
def test_cut_set_key_is_the_event_set():
    src = _read(TABS / "cutsets.js")
    rows = [
        {"rank": 1, "events": [{"id": "b"}, {"id": "a"}]},
        {"rank": 7, "events": [{"id": "a"}, {"id": "b"}]},
        {"rank": 2, "events": [{"id": "a"}]},
        {"rank": 3, "events": []},
        {"rank": 4, "events": [{"id": "a_b"}]},
    ]
    got = _node(_function(src, "cutSetKey") + "\nconsole.log(JSON.stringify(%s.map(cutSetKey)));" % json.dumps(rows))
    assert got[0] == got[1], "same events in another order and rank"
    assert len(set(got)) == 4 and got[3] == ""


def test_cutsets_reselects_by_cut_set_not_rank():
    src = _read(TABS / "cutsets.js")
    run = _block(src, "async function run()")
    assert "result.cutSets.find((cs) => cutSetKey(cs) === selectedKey)" in run
    assert "cs.rank === selectedRank" not in run
    assert "selectedKey = cutSetKey(row);" in _block(src, "function highlightRow(row)")
    assert "selectedKey = null;" in _block(src, "function unselect()")


# ---- Cut Sets: "Show 0" does not claim the top event cannot occur ---------------------
# With Show = 0 the table was empty and the tab said "No cut sets: the top event
# cannot occur with these settings." under a summary of "0 of 2 cut sets".

@needs_node
def test_cutsets_empty_message():
    src = _read(TABS / "cutsets.js")
    cases = [
        None,
        {"cutSets": [], "total": 0, "returned": 0},
        {"cutSets": [], "total": 2, "returned": 0},
        {"cutSets": [{"rank": 1, "events": []}], "total": 1, "returned": 1},
    ]
    got = _node(_function(src, "emptyMessageKey")
                + "\nconsole.log(JSON.stringify(%s.map(emptyMessageKey)));" % json.dumps(cases))
    assert got == ["cutsets.notRun", "cutsets.none", None, None]
    paint = _block(src, "function paint()")
    assert "const empty = emptyMessageKey(result);" in paint and "message.hidden = !empty;" in paint


# ---- Validation: the truncation reason is in words, in the UI language ----------------
# lint's CUTSETS_TRUNCATED reason is the raw limit list ("count, order"); the
# Japanese message read "カットセットの一覧が途中で打ち切られました (order)。".
# The Cut Sets tab already labels the same limits through anl.by.*.

@needs_node
def test_validation_truncation_reason_is_translated():
    src = _read(TABS / "validation.js")
    ja = {"anl.by.order": "最大次数", "anl.by.count": "最大件数", "anl.by.cutoff": "カットオフ"}
    script = _function(src, "truncationReasonText") + (
        "\nconst ja = %s; const tr = (k) => (k in ja ? ja[k] : null);"
        "\nconsole.log(JSON.stringify(['count, order', 'cutoff', 'limits', ''].map((r) => truncationReasonText(r, tr))));"
    ) % json.dumps(ja, ensure_ascii=False)
    assert _node(script) == ["最大件数, 最大次数", "カットオフ", "limits", ""]
    body = _block(src, "function displayParams(issue)")
    assert "if (issue.code === 'CUTSETS_TRUNCATED' && typeof out.reason === 'string')" in body
    assert "out.reason = truncationReasonText(out.reason, lookup);" in body
    # every limit lint can name has a label in both languages
    cat = _read(STATIC / "i18n" / "cutsets.js")
    for token in ("order", "count", "cutoff"):
        assert cat.count("'anl.by.%s'" % token) == 2, token


# ---- Cut Sets / Importance: an answer that crossed an edit is stale --------------------
# onStale marks the results stale and debounces a re-run (700 ms). An answer
# already in flight that lands before that re-run started set stale = false:
# the pre-edit results showed as current (Importance also coloured the changed
# tree with them), for good when the re-run then failed (422).

@pytest.mark.parametrize("tab,endpoint", [("cutsets", "'/analysis/cutsets', payload"),
                                          ("importance", "'/analysis/importance', {}")])
def test_answer_that_crossed_an_edit_is_stale(tab, endpoint):
    src = _read(TABS / (tab + ".js"))
    run = _block(src, "async function run()")
    assert run.index("const asked = ctx.store.state || {};") < run.index("await ctx.api.post(%s)" % endpoint)
    assert "stale = now.tree !== asked.tree || now.analysis !== asked.analysis;" in run
    assert "stale = false;" not in run
