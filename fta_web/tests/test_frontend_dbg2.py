"""Frontend regressions from the 1.7 debugging pass (frontend, UX, i18n, a11y).

Source-level pins, in the style of test_diagram_click_select.py, plus one
behavioural check of ``parseNumber`` that runs under Node when it is on PATH.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from fta_web import engine
from fta_web.routes import analysis as analysis_routes

REPO = Path(__file__).resolve().parents[2]
STATIC = REPO / "fta_web" / "static" / "js"
TABS = STATIC / "tabs"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---- Uncertainty tab: n is shown as stored, validated per action ------------------

def test_uncertainty_limits_match_the_server():
    src = _read(TABS / "uncertainty.js")
    run_max = int(re.search(r"const RUN_MAX_N = (\d+);", src).group(1))
    save_max = int(re.search(r"const SAVE_MAX_N = (\d+);", src).group(1))
    assert run_max == analysis_routes.MAX_MC_N
    assert save_max == engine.MAX_MC_N


def test_uncertainty_defaults_do_not_clamp_the_document_value():
    src = _read(TABS / "uncertainty.js")
    body = re.search(r"function defaults\(\) \{(.*?)\n  \}", src, re.S).group(1)
    assert "Math.min" not in body, "clamping on display makes Save lower a larger stored n"


def test_uncertainty_run_max_message_is_translated():
    cat = _read(STATIC / "i18n" / "unc.js")
    assert cat.count("'unc.runMax'") == 2


# ---- index.html: the date field's pattern must compile with the /v flag ------------

def test_date_pattern_is_valid_under_the_v_flag():
    html = _read(REPO / "fta_web" / "templates" / "index.html")
    pattern = re.search(r'id="date-input"[^>]*pattern="([^"]*)"', html, re.S).group(1)
    # In a /v character class '/', '-', '(', ')', '[', ']', '{', '}', '|' must be escaped.
    cls = re.search(r"\[(.*?)\]", pattern).group(1)
    unescaped = re.findall(r"(?<!\\)[/()\[\]{}|]", cls)
    assert not unescaped, pattern
    assert re.search(r"(?<!\\)-(?!$)", cls.replace("0-9", "")) is None, pattern


# ---- New / Open reset the analysis tabs ----------------------------------------------

def test_main_announces_a_new_document():
    src = _read(STATIC / "main.js")
    assert src.count("announceDocument();") >= 3  # New, forced New, adoptDocument
    assert "'analysis'" in re.search(r"const DOCUMENT_KEYS = \[(.*?)\];", src).group(1)


@pytest.mark.parametrize("tab", ["cutsets", "importance", "uncertainty", "validation"])
def test_tabs_listen_for_a_new_document(tab):
    src = _read(TABS / (tab + ".js"))
    assert "addEventListener('fta:document'" in src
    assert "removeEventListener('fta:document'" in src


# ---- Diagram -----------------------------------------------------------------------

def test_symbols_png_never_uses_native_dot():
    diagram = _read(STATIC / "diagram.js")
    assert "effectiveBoxSettings().style !== 'symbols'" in diagram
    main = _read(STATIC / "main.js")
    body = re.search(r"async function actionRenderImage\(\) \{(.*?)\n\}", main, re.S).group(1)
    assert "box.style === 'symbols'" in body
    for key in ("style: box.style", "rankdir: box.rankdir", "sigFigs: box.sigFigs"):
        assert key in body, key


def test_diagram_refits_until_the_user_zooms():
    src = _read(STATIC / "diagram.js")
    assert "let autoFit = true;" in src
    assert "resetView || autoFit ||" in src
    assert "new ResizeObserver" in src


def test_diagram_popover_relabels_on_language_switch():
    src = _read(STATIC / "diagram.js")
    assert "relabelPopover();" in re.search(r"const onLanguage = \(\) => \{(.*?)\};", src).group(1)
    assert "'Diagram font'" not in src and "'Diagram box scale'" not in src


# ---- Quantification: every control has a label -------------------------------------

def test_quant_grid_labels_are_tied_to_controls():
    src = _read(TABS / "quant.js")
    assert "for: controlId(control)" in src
    assert "for: controlId(input)" in src


# ---- parseNumber, executed ---------------------------------------------------------

def _parse_number_source() -> str:
    src = _read(TABS / "analysis_common.js")
    return re.search(r"export function parseNumber\(raw\) \{.*?\n\}", src, re.S).group(0).replace("export ", "")


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_parse_number_behaviour():
    cases = ["1e-6", " 2 ", "1,5", "0,001", "-4", "", "5,000", "1,000,000", "1.5,2", "0x10", "abc", "Infinity", ".5", "3."]
    script = _parse_number_source() + "\nconsole.log(JSON.stringify(%s.map((c) => { const v = parseNumber(c); return Number.isNaN(v) ? 'NaN' : v; })));" % json.dumps(cases)
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    got = dict(zip(cases, json.loads(out)))
    assert got == {
        "1e-6": 1e-6, " 2 ": 2, "1,5": 1.5, "0,001": 0.001, "-4": -4, "": None,
        "5,000": "NaN", "1,000,000": "NaN", "1.5,2": "NaN", "0x10": "NaN", "abc": "NaN",
        "Infinity": "NaN", ".5": 0.5, "3.": 3,
    }
