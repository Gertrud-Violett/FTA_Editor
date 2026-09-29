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


def test_fit_uses_the_capped_scale_everywhere():
    src = _read(STATIC / "diagram.js")
    body = re.search(r"  function fit\(\) \{(.*?)\n  \}", src, re.S).group(1)
    assert "fitScale(rect.width, rect.height, w, h)" in body
    assert "ZOOM_MAX" not in body, "fit() must not re-derive its own (uncapped) clamp"
