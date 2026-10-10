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
