"""
Click a node in the diagram -> it is selected in the tree and in node details.

Spec 6.8 / section "Beyond the desktop app": *"Click a node in the diagram ->
selects it in the tree, and vice versa. The desktop app cannot do this; it is
the main payoff of choosing SVG over PNG."*

``fta_web/static/js/diagram.js`` implements it by reading the ``<title>`` of
the ``<g class="node">`` under the click and mapping Graphviz' sanitized id
back to the real one. Two things can silently break that, and neither is
visible to any other test in this suite, so both are pinned here.

1. **Pointer capture taken on ``pointerdown``.** The panel also pans on drag.
   Until 1.6.4 it called ``stage.setPointerCapture()`` in the ``pointerdown``
   handler, which retargets the compatibility mouse events at the capture
   element: the ``click`` that follows was dispatched at the stage ``<div>``,
   ``ev.target.closest('g.node')`` found nothing, and click-to-select did
   nothing at all in Chromium-based browsers. Capture must only be taken once
   the pointer has moved far enough that the gesture is a pan.

2. **The id mapping.** ``sanitizeId`` in diagram.js is a hand-written mirror of
   ``json_viewer.sanitize_id``; if the two drift, ``<title>`` no longer matches
   any key in the map and every click resolves to nothing. ``test_core_fixes``
   covers the Python side alone -- this pins the agreement.
"""
import hashlib
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "fta_web" / "core"))

from json_viewer import sanitize_id  # noqa: E402

DIAGRAM_JS = (REPO_ROOT / "fta_web" / "static" / "js" / "diagram.js").read_text(encoding="utf-8")


def _handler_body(event):
    """The source of ``stage.addEventListener('<event>', (ev) => { ... })``.

    Brace-matched rather than regex-matched: the handlers contain braces of
    their own, and a non-greedy match would stop at the first one.
    """
    start = DIAGRAM_JS.index(f"stage.addEventListener('{event}'")
    open_brace = DIAGRAM_JS.index("{", DIAGRAM_JS.index("=>", start))
    depth = 0
    for i in range(open_brace, len(DIAGRAM_JS)):
        if DIAGRAM_JS[i] == "{":
            depth += 1
        elif DIAGRAM_JS[i] == "}":
            depth -= 1
            if depth == 0:
                return DIAGRAM_JS[open_brace : i + 1]
    raise AssertionError(f"unbalanced braces in the {event} handler")


def test_pointerdown_does_not_capture_the_pointer():
    """Capturing on press retargets the click and kills click-to-select."""
    assert "setPointerCapture" not in _handler_body("pointerdown")


def test_pointermove_captures_only_past_the_pan_slop():
    body = _handler_body("pointermove")
    assert "setPointerCapture" in body
    assert "PAN_SLOP_PX" in body
    assert re.search(r"const PAN_SLOP_PX\s*=\s*[1-9]", DIAGRAM_JS)


def test_pointerdown_remembers_the_pressed_node():
    """The press target is what a later click resolves against."""
    body = _handler_body("pointerdown")
    assert "closest('g.node')" in body
    assert "pressNode" in body


def test_click_handler_falls_back_to_the_pressed_node():
    body = _handler_body("click")
    assert "pressNode" in body
    assert "store.select(real)" in body


def _js_sanitize_id(value):
    """What diagram.js' ``sanitizeId`` computes, as Python."""
    raw = str(value)
    clean = re.sub(r"[^0-9A-Za-z_]", "_", raw)
    if clean == raw:
        return raw
    return clean + "_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def test_js_sanitize_id_mirrors_the_python_one():
    for nid in ["root", "root_0", "root_12", "a.b", "a b", "ノード", "n-1", "x/y", "", "1"]:
        assert _js_sanitize_id(nid) == sanitize_id(nid), nid


def test_js_sanitize_id_mirror_matches_the_shipped_source():
    """The mirror above is only worth anything if diagram.js still looks like it."""
    assert "function sanitizeId" in DIAGRAM_JS
    assert "replace(/[^0-9A-Za-z_]/g, '_')" in DIAGRAM_JS
    assert "sha1Hex(raw).slice(0, 8)" in DIAGRAM_JS
