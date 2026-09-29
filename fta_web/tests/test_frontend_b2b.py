"""Frontend regressions from the 1.7.1 GUI back-to-back pass (real Chrome).

Each bug found by driving the GUI and comparing what it shows with what the
API computes gets a check here. Pure JS logic is executed under Node when it
is on PATH (extracted from the module source, as test_frontend_dbg2.py does
for parseNumber); DOM wiring is pinned at source level.
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


# ---- Diagram: fitting never enlarges past 100% ----------------------------------------

def _fit_source() -> str:
    src = _read(STATIC / "diagram.js")
    consts = "\n".join(
        re.search(r"^const %s = [^;]+;" % name, src, re.M).group(0)
        for name in ("ZOOM_MIN", "ZOOM_MAX", "FIT_MAX", "FIT_MARGIN_PX")
    )
    fn = re.search(r"export function fitScale\(.*?\n\}", src, re.S).group(0).replace("export ", "")
    return consts + "\n" + fn


@needs_node
def test_fit_scale_never_enlarges_a_small_diagram():
    # A one-node document (~150 x 60 pt) on a 2542 x 1261 window used to fit
    # at ~675%, drawing the title in giant letters.
    cases = [
        [1800, 700, 150, 60],     # tiny diagram, huge stage -> capped at 1
        [600, 400, 1200, 800],    # big diagram -> shrinks
        [0, 0, 100, 100],         # collapsed stage -> ZOOM_MIN, not negative
        [800, 600, 776, 100],     # exactly fits -> 1
    ]
    script = _fit_source() + "\nconsole.log(JSON.stringify(%s.map((c) => fitScale(...c))));" % json.dumps(cases)
    got = _node(script)
    assert got[0] == 1
    assert got[1] == pytest.approx(min((600 - 24) / 1200, (400 - 24) / 800))
    assert got[2] == pytest.approx(0.1)
    assert got[3] == 1


def test_selection_does_not_relayout_the_diagram():
    src = _read(STATIC / "diagram.js")
    body = re.search(r"const unsubscribe = store\.subscribe\(\(\) => \{(.*?)\n  \}\);", src, re.S).group(1)
    assert "markSelection();" in body
    # schedule() (a /api/dot fetch + a full WASM layout) only for a new state object
    assert body.index("if (store.state === renderedState) return;") < body.index("schedule();")


def test_diagram_meta_says_what_drew_the_picture():
    src = _read(STATIC / "diagram.js")
    assert "t('diagram.rendererNative'" not in src, "the on-screen SVG is never drawn by system Graphviz"
    assert "'diagram17.pngNative'" in src
    main = _read(STATIC / "main.js")
    assert "if (!diagramPanel) {\n    $('#diagram-meta').textContent" in main


def test_fit_uses_the_capped_scale_everywhere():
    src = _read(STATIC / "diagram.js")
    body = re.search(r"  function fit\(\) \{(.*?)\n  \}", src, re.S).group(1)
    assert "fitScale(rect.width, rect.height, w, h)" in body
    assert "ZOOM_MAX" not in body, "fit() must not re-derive its own (uncapped) clamp"


# ---- Tree: the keyboard hint never changes the layout under a mouse press ------------

def test_tree_hint_is_keyboard_only_and_out_of_the_layout():
    src = _read(STATIC / "tree.js")
    # 1.7.0: shown on any focus-within -> a click on a bottom row hit the hint
    assert ".fta-tree-panel:focus-within .fta-tree-hint" not in src
    assert ".fta-tree-panel.is-kbd:focus-within .fta-tree-hint { display: block; }" in src
    hint_css = re.search(r"\.fta-tree-hint \{(.*?)\}", src, re.S).group(1)
    assert "position: absolute;" in hint_css
    assert "pointer-events: none;" in hint_css
    assert "trackModality(panel, host, hint);" in src
    body = re.search(r"function trackModality\(panel, list, hint\) \{(.*?)\n\}", src, re.S).group(1)
    assert "addEventListener('pointerdown', () => show(false), true)" in body
    assert "addEventListener('keydown', () => show(true), true)" in body


# ---- Validation: probability params always follow the sig-fig setting ---------------

def _validation_format_source() -> str:
    src = _read(TABS / "validation.js")
    parts = [
        re.search(r"export const PROBABILITY_PARAMS = [^;]+;", src).group(0),
        re.search(r"export const RATE_PARAMS = [^;]+;", src).group(0),
        re.search(r"export function formatNumberParam\(.*?\n\}", src, re.S).group(0),
    ]
    return "\n".join(p.replace("export ", "") for p in parts)


@needs_node
def test_validation_number_params_formatting():
    fmt = ("(v) => { const n = Number(v); if (n === 0) return '0'; const m = Math.abs(n); "
           "if (m < 1e-3 || m >= 1e4) return n.toExponential(2).replace('e+', 'e'); return n.toPrecision(3); }")
    cases = [["calculated", 1], ["probability", 0.16], ["probability", 0], ["sum", 2],
             ["q", 1], ["lambdaTau", 0.25], ["n", 3], ["k", 5], ["lambda", 120], ["lambda", 4.5e-6]]
    script = _validation_format_source() + (
        "\nconst fmt = %s;\nconsole.log(JSON.stringify(%s.map(([k, v]) => formatNumberParam(k, v, fmt, 3))));"
        % (fmt, json.dumps(cases)))
    got = _node(script)
    # PARENT_PROBABILITY_IGNORED used to read "(1)" next to "(0.160)"
    assert got == ["1.00", "0.160", "0", "2.00", "1.00", "0.250", "3", "5", "1.20e2", "4.50e-6"]


def test_rate_implausible_is_translated_and_advanced():
    cat = _read(STATIC / "i18n" / "val.js")
    for key in ("'val.code.RATE_IMPLAUSIBLE'", "'val.fix.RATE_IMPLAUSIBLE'"):
        assert cat.count(key) == 2, key  # en + ja
    src = _read(TABS / "validation.js")
    codes = re.search(r"const ADVANCED_CODES = new Set\(\[(.*?)\]\);", src, re.S).group(1)
    assert "'RATE_IMPLAUSIBLE'" in codes


# ---- FMEA: the λ unit plausibility warning ------------------------------------------

@needs_node
def test_fmea_lambda_unit_check():
    src = _read(TABS / "fmea.js")
    parts = [
        re.search(r"const UNIT_DIVISOR = [^;]+;", src).group(0),
        re.search(r"export const LAMBDA_HIGH_PER_HOUR = [^;]+;", src).group(0),
        re.search(r"export function cellNumber\(.*?\n\}", src, re.S).group(0),
        re.search(r"export function lambdaUnitCheck\(.*?\n\}", src, re.S).group(0),
    ]
    code = "\n".join(p.replace("export ", "") for p in parts)
    cases = [
        [["120", 45, ""], "h", "FIT"],       # the sample CSV: FIT read as /h
        [["120", "45"], "FIT", "FIT"],       # right unit: nothing
        [["1.0e-6", "5e-7"], "h", "h"],      # per-hour rates: nothing
        [["0.5", "0.2"], "h", "y"],          # per-year values read as /h
        [["0.5"], "y", "y"],                 # 0.5/y = 5.7e-5/h: fine
        [["2e-3"], "h", "y"],                # plausible value, but the server suggests /y
    ]
    got = _node(code + "\nconsole.log(JSON.stringify(%s.map((c) => lambdaUnitCheck(...c))));" % json.dumps(cases))
    assert got[0]["high"]["suggest"] == "FIT" and got[0]["high"]["max"] == 120
    assert got[1] == {"high": None, "differs": None}
    assert got[2] == {"high": None, "differs": None}
    assert got[3]["high"]["suggest"] == "y" and got[3]["differs"] == "y"
    assert got[4] == {"high": None, "differs": None}
    assert got[5] == {"high": None, "differs": "y"}


def test_fmea_unit_warning_is_wired_and_translated():
    src = _read(TABS / "fmea.js")
    assert "paintUnitWarning();" in src
    assert "if (field === 'lambda') paintUnitWarning();" in src
    cat = _read(STATIC / "i18n" / "fmea.js")
    for key in ("fmea.lambdaHighH", "fmea.lambdaHigh", "fmea.lambdaHighSuggest", "fmea.unitDiffers"):
        assert cat.count("'%s'" % key) == 2, key


# ---- Shortcuts: Alt+N is the browser-safe New ----------------------------------------

def test_alt_n_starts_a_new_analysis():
    src = _read(STATIC / "main.js")
    body = re.search(r"function onKeyDown\(event\) \{(.*?)\n\}", src, re.S).group(1)
    alt = re.search(r"if \(event\.altKey && !ctrl && !event\.shiftKey && "
                    r"\(key === 'n' \|\| event\.code === 'KeyN'\)\) \{(.*?)\}", body, re.S)
    assert alt and "event.preventDefault();" in alt.group(1) and "actionNew();" in alt.group(1)
    # every Ctrl shortcut that acts also calls preventDefault
    switch = re.search(r"switch \(key\) \{(.*?)\n  \}", body, re.S).group(1)
    cases = re.findall(r"case '(\w)':(.*?)break;", switch, re.S)
    assert {c[0] for c in cases} >= {"n", "a", "e", "d", "z", "y"}
    for key, code in cases:
        assert "event.preventDefault();" in code, key
    assert "'tip.new': 'New analysis (Alt+N)'" in src
    assert "'tip.new': '新規解析 (Alt+N)'" in src
    assert 'title="New analysis (Alt+N)"' in _read(REPO / "fta_web" / "templates" / "index.html")


# ---- Numeric fields select their value on a click ------------------------------------

def test_numeric_fields_select_on_click():
    dialogs = _read(STATIC / "dialogs.js")
    assert "export function installSelectOnFocus(doc)" in dialogs
    prob = re.search(r"const probabilityField = field\((.*?)\n  \);", dialogs, re.S).group(1)
    assert "inputmode: 'decimal'" in prob
    assert "modules.dialogs.installSelectOnFocus(document);" in _read(STATIC / "main.js")
    details = _read(STATIC / "details.js")
    assert "spec.key === 'probability') control = el('input', { type: 'text', inputmode: 'decimal' })" in details
    assert "data-keep-caret" in _read(REPO / "fta_web" / "templates" / "index.html")


# ---- New / Open confirmations ----------------------------------------------------------

def test_new_asks_before_posting_when_dirty():
    src = _read(STATIC / "main.js")
    body = re.search(r"async function actionNew\(\) \{(.*?)\n\}", src, re.S).group(1)
    assert body.index("store.state.dirty") < body.index("api.post('/new'"), \
        "a dirty document is confirmed before the first POST (no refused 409 in the console)"
    assert "await flushPendingEdits();" in body


def test_discard_confirmations_name_the_consequence():
    src = _read(STATIC / "main.js")
    for key in ("confirm.discardNewOk", "confirm.discardOpenOk"):
        assert src.count("    '%s': " % key) == 2, key  # en + ja catalog entries
    assert "confirmLabel: t('confirm.discardNewOk')" in src
    assert "confirmLabel: t('confirm.discardOpenOk')" in src


# ---- Diagram Aa popover closes on Escape ----------------------------------------------

def test_diagram_popover_closes_on_escape():
    src = _read(STATIC / "diagram.js")
    handler = re.search(r"popover\.addEventListener\('keydown', \(ev\) => \{(.*?)\n  \}\);", src, re.S).group(1)
    assert "ev.key !== 'Escape'" in handler and "ev.stopPropagation();" in handler
    assert "closePopover(true);" in handler
    assert "window.addEventListener('fta:escape', onShellEscape);" in src
    assert "window.removeEventListener('fta:escape', onShellEscape);" in src


# ---- Live language switch ---------------------------------------------------------------

def test_chat_log_relabels_on_language_switch():
    src = _read(STATIC / "chat.js")
    on_lang = re.search(r"const onLanguage = \(\) => \{(.*?)\};", src, re.S).group(1)
    assert "relabelLog();" in on_lang
    assert "say('system', 'ai.msg.welcome');" in src
    assert "addMessage('system', t(" not in src, "catalog messages must go through say()"


def test_no_untranslated_static_labels():
    html = _read(REPO / "fta_web" / "templates" / "index.html")
    for tag in re.findall(r"<[a-zA-Z][^>]*>", html):
        if re.search(r'\baria-label="', tag):
            assert "data-i18n-aria=" in tag, tag
        if re.search(r'\stitle="', tag):
            assert "data-i18n-title=" in tag, tag
    assert "close.setAttribute('aria-label', 'Dismiss')" not in _read(STATIC / "main.js")


# ---- Report tab: "Save … again" survives other exports ---------------------------------

def test_report_save_again_url_is_not_revoked_by_other_exports():
    src = _read(TABS / "report.js")
    offer = re.search(r"const offer = \(blob, name, keep\) => \{(.*?)\n  \};", src, re.S).group(1)
    # only a newer REPORT replaces (and revokes) the link's URL
    assert "if (keep) {" in offer and "URL.revokeObjectURL(reportUrl)" in offer
    assert "saveAgain.href = offer(blob, name, true);" in src
    # Excel / CSV downloads must not pass keep
    assert src.count("offer(blob, name);") == 2
    assert "labels.push([saveAgain" not in src, "one link label, not one per generated report"
