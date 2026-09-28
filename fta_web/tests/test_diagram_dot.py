"""
fta_web/diagram_dot.py -- the 1.7 DOT builder behind GET /api/dot.

Pins the contracts the browser relies on:

* compact style on a legacy tree emits exactly the DOT node names (and tree
  edges) of the 1.6 pipeline, so click-to-select by ``<title>`` still works;
* probabilities go through numfmt.format_prob at the requested sig figs;
* every gate type / event kind gets its shape and ``class`` in the symbols
  style, gate/event symbols are ``<sid>__gate`` / ``<sid>__event``;
* rankdir LR/TB is honoured (ports follow it), hide_zero is honoured;
* ``id_map`` maps every emitted DOT node name to its tree node id;
* native ``dot`` parses every variant (when it is on PATH).
"""
import re
import shutil
import subprocess

import pytest

from FTA_Editor_core import FTACore  # noqa: E402  (conftest puts core on sys.path)
from json_viewer import sanitize_id  # noqa: E402

from fta_web.diagram_dot import GATE_SHAPES, EVENT_SHAPES, build_dot_text2
from fta_web.engine import WebCore
from fta_web.rendering import build_dot_text

HAS_DOT = shutil.which("dot") is not None
needs_graphviz = pytest.mark.skipif(not HAS_DOT, reason="requires a native Graphviz 'dot'")

_NODE_DEF = re.compile(r"^\s{2}([A-Za-z0-9_]+) \[", re.M)
_TREE_EDGE = re.compile(r"^\s{2}([A-Za-z0-9_]+)(?::[nsew])? -> ([A-Za-z0-9_]+)(?::[nsew])?(?: \[(.*)\])?;$", re.M)


def _leaf(nid, name, p, **extra):
    node = {"id": nid, "name": name, "type": "Event", "probability": p,
            "logicGate": "OR", "notes": "", "links": [], "children": []}
    node.update(extra)
    return node


@pytest.fixture
def legacy():
    core = FTACore()
    core.set_metadata(title="Legacy", date="2026-01-01")
    core.add_node_to_data("root", _leaf("root_0", "Seal leak", 1.234e-7))
    core.add_node_to_data("root", _leaf("root_1", "Pump & motor", 0.5, logicGate="AND"))
    core.add_node_to_data("root_1", _leaf("a.b", "Dotted id", 0.25))
    core.add_node_to_data("root_1", _leaf("ノード", "Japanese id", 0.0))
    data = core.get_data()
    data["children"][0]["links"] = [{"target_id": "a.b", "relation": "OR"}]
    core.recalculate_probabilities()
    return core


@pytest.fixture
def rich():
    core = WebCore()
    core.set_metadata(title="Rich", date="2026-01-01")
    add = core.add_node_to_data
    add("root", _leaf("k", "Vote", 1.0, gateType="KOFN", k=2))
    for j in range(3):
        add("k", _leaf("k%d" % j, "Pump %d" % j, 1e-3))
    add("root", _leaf("x", "Exclusive", 1.0, gateType="XOR"))
    add("x", _leaf("x0", "A", 0.1))
    add("x", _leaf("x1", "B", 0.2, eventKind="undeveloped"))
    add("root", _leaf("i", "Inhibit", 1.0, gateType="INHIBIT", logicGate="AND"))
    add("i", _leaf("i0", "Demand", 0.01))
    add("i", _leaf("i1", "Condition", 0.5, eventKind="conditioning"))
    add("root", _leaf("pa", "Sequence", 1.0, gateType="PAND", logicGate="AND"))
    add("pa", _leaf("pa0", "First", 0.1))
    add("pa", _leaf("pa1", "House on", 0.2, eventKind="house", houseState=True))
    add("root", _leaf("t", "See vote", 1.0, gateType="TRANSFER", transferTo="k"))
    add("root", _leaf("h", "House off", 0.3, eventKind="house", houseState=False))
    add("root", _leaf("and1", "Plain AND", 1.0, gateType="AND", logicGate="AND"))
    add("and1", _leaf("and1_0", "Only", 0.5))
    core.recalculate_probabilities()
    return core


def _node_names(dot):
    return set(_NODE_DEF.findall(dot)) - {"graph", "node", "edge"}


def _tree_edges(dot):
    return {(a, b) for a, b, attrs in _TREE_EDGE.findall(dot)
            if "invis" not in (attrs or "") and "dashed" not in (attrs or "")}


def _attrs_of(dot, name):
    m = re.search(r"^\s{2}%s \[(.*)\];$" % re.escape(name), dot, re.M)
    assert m, "no definition for %s" % name
    return m.group(1)


# ---- compact / legacy parity ---------------------------------------------------


def test_compact_legacy_node_names_and_edges_match_the_16_pipeline(legacy):
    old = build_dot_text(legacy)
    new, id_map = build_dot_text2(legacy)
    assert _node_names(new) == _node_names(old)
    assert _tree_edges(new) == _tree_edges(old)
    # Same header, same graph attributes, same LR ports.
    assert new.split("\n")[:11] == old.split("\n")[:11]
    assert re.search(r"root:e -> root_0:w", new)
    assert set(id_map) == _node_names(new)


def test_compact_legacy_is_identical_apart_from_the_probability_text(legacy):
    old = build_dot_text(legacy)
    new, _ = build_dot_text2(legacy, sig_figs=2)
    strip = re.compile(r"P:[^ |<]+ \| P_calc:[^ <]+")
    # Trailing padding differs on purpose (1.7 pads in proportion to the
    # row's length so browser fonts do not overflow the box).
    unpad = re.compile(r" +</FONT>")
    assert (unpad.sub("</FONT>", strip.sub("P", new))
            == unpad.sub("</FONT>", strip.sub("P", old)))


def test_padding_grows_with_the_row_length_and_respects_scale_zero(legacy):
    dot, _ = build_dot_text2(legacy, sig_figs=3)
    rows = re.findall(r'POINT-SIZE="9">([^<]*?)( *)</FONT>', dot)
    assert rows
    for text, pad in rows:
        # base box-scale padding (4) plus one space per two characters
        assert len(pad) >= 4 + len(text.rstrip()) // 2
    bare, _ = build_dot_text2(legacy, scale=0)
    assert not re.search(r" +</FONT>", bare)


def test_sig_figs_reach_the_labels(legacy):
    three, _ = build_dot_text2(legacy, sig_figs=3)
    five, _ = build_dot_text2(legacy, sig_figs=5)
    assert "P:1.23e-7" in three and "P:0.500" in three
    assert "P:1.2340e-7" in five and "P:0.50000" in five
    assert ".1E" not in three and "1.2E-07" not in three


def test_compact_gate_labels_for_17_gates(rich):
    dot, _ = build_dot_text2(rich)
    assert "Gate: 2/3 |" in dot
    assert "Gate: XOR |" in dot
    assert "Gate: INHIBIT |" in dot
    assert "Gate: PAND |" in dot
    assert "Gate: TRANSFER→Vote |" in dot
    assert "House: ON |" in dot and "House: OFF |" in dot
    assert "Undeveloped |" in dot and "Conditioning |" in dot


def test_names_are_escaped_in_both_styles(legacy):
    for style in ("compact", "symbols"):
        dot, _ = build_dot_text2(legacy, style=style)
        assert "Pump &amp; motor" in dot
        assert "Pump & motor" not in dot


# ---- symbols ------------------------------------------------------------------------


EXPECTED_GATES = {
    "root": "or", "k": "kofn", "x": "xor", "i": "inhibit",
    "pa": "pand", "t": "transfer", "and1": "and",
}
EXPECTED_EVENTS = {
    "k0": "basic", "x0": "basic", "x1": "undeveloped", "i0": "basic",
    "pa0": "basic", "pa1": "house", "h": "house", "and1_0": "basic",
}


def test_symbols_gate_nodes_have_shapes_and_classes(rich):
    dot, id_map = build_dot_text2(rich, style="symbols")
    for nid, kind in EXPECTED_GATES.items():
        attrs = _attrs_of(dot, nid + "__gate")
        assert 'class="fta-gate fta-gate-%s"' % kind in attrs
        shape = GATE_SHAPES[kind.upper()][0]
        assert "shape=%s" % shape in attrs
        assert id_map[nid + "__gate"] == nid
        assert 'class="fta-box"' in _attrs_of(dot, nid)
    assert 'label="2/3"' in _attrs_of(dot, "k__gate")


def test_symbols_event_nodes_have_shapes_and_classes(rich):
    dot, id_map = build_dot_text2(rich, style="symbols")
    for nid, kind in EXPECTED_EVENTS.items():
        attrs = _attrs_of(dot, nid + "__event")
        assert 'class="fta-event fta-event-%s"' % kind in attrs
        assert "shape=%s" % EVENT_SHAPES[kind] in attrs
        assert id_map[nid + "__event"] == nid
    assert 'label="ON"' in _attrs_of(dot, "pa1__event")
    assert 'label="OFF"' in _attrs_of(dot, "h__event")
    # A conditioning event under INHIBIT is the ellipse itself.
    cond = _attrs_of(dot, "i1")
    assert "shape=ellipse" in cond and "fta-event-conditioning" in cond
    assert "i1__event" not in dot
    assert re.search(r"^\s{2}i__gate -> i1;$", dot, re.M)


def test_symbols_transfer_children_are_dotted_and_edges_run_through_gates(rich):
    dot, _ = build_dot_text2(rich, style="symbols")
    assert re.search(r"^\s{2}root -> root__gate;$", dot, re.M)
    assert re.search(r"^\s{2}root__gate -> k;$", dot, re.M)
    assert re.search(r"^\s{2}k -> k__gate;$", dot, re.M)
    assert re.search(r"^\s{2}k__gate -> k0;$", dot, re.M)
    assert "dir=none" in dot


def test_id_map_is_complete_and_plain_names_are_unchanged(rich, legacy):
    for core in (rich, legacy):
        for style in ("compact", "symbols"):
            dot, id_map = build_dot_text2(core, style=style)
            names = _node_names(dot)
            assert set(id_map) == names, style
            for name, nid in id_map.items():
                if "__" not in name:
                    assert sanitize_id(nid) == name
    _dot, id_map = build_dot_text2(legacy, style="symbols")
    assert id_map[sanitize_id("a.b")] == "a.b"


def test_synthetic_names_never_collide_with_real_ids():
    core = FTACore()
    core.add_node_to_data("root", _leaf("x", "X", 0.5))
    core.add_node_to_data("root", _leaf("x__event", "Clash", 0.5))
    core.recalculate_probabilities()
    dot, id_map = build_dot_text2(core, style="symbols")
    assert id_map["x__event"] == "x__event"
    assert id_map["x__event_2"] == "x"


# ---- rankdir / hide_zero ------------------------------------------------------------


@pytest.mark.parametrize("style", ["compact", "symbols"])
def test_rankdir_is_honoured(rich, style):
    lr, _ = build_dot_text2(rich, style=style, rankdir="LR")
    tb, _ = build_dot_text2(rich, style=style, rankdir="TB")
    assert "rankdir=LR;" in lr and "rankdir=TB;" in tb
    assert ":s ->" not in tb and ":e ->" not in tb  # TB: no LR ports
    if style == "compact":
        assert ":e -> " in lr
    else:
        assert "orientation=90" in lr and "orientation=90" not in tb


def test_bad_style_and_rankdir_fall_back(rich):
    dot, _ = build_dot_text2(rich, style="fancy", rankdir="RL")
    assert "rankdir=LR;" in dot and "fta-gate" not in dot


@pytest.mark.parametrize("style", ["compact", "symbols"])
def test_hide_zero(legacy, style):
    shown, shown_map = build_dot_text2(legacy, style=style)
    hidden, hidden_map = build_dot_text2(legacy, style=style, hide_zero=True)
    assert "Japanese id" in shown and "Japanese id" not in hidden
    assert "ノード" in shown_map.values() and "ノード" not in hidden_map.values()


def test_dark_mode_colours(rich):
    dot, _ = build_dot_text2(rich, style="symbols", dark=True)
    assert 'bgcolor="#1b1f23"' in dot and 'color="white"' in dot
    dot, _ = build_dot_text2(rich, style="compact", dark=True)
    assert 'fontcolor="white"' in dot


def test_empty_tree():
    class Empty:
        def get_data(self):
            return {}

        def get_metadata(self):
            return {}

    dot, id_map = build_dot_text2(Empty(), style="symbols")
    assert dot.startswith("digraph G {") and dot.rstrip().endswith("}")
    assert id_map == {}


# ---- native Graphviz parses every variant ----------------------------------------------


@needs_graphviz
@pytest.mark.parametrize("style", ["compact", "symbols"])
@pytest.mark.parametrize("rankdir", ["LR", "TB"])
@pytest.mark.parametrize("dark", [False, True])
def test_native_dot_parses_and_carries_classes(rich, style, rankdir, dark):
    dot, _ = build_dot_text2(rich, style=style, rankdir=rankdir, dark=dark, sig_figs=4)
    done = subprocess.run(
        ["dot", "-Tsvg"], input=dot.encode("utf-8"), capture_output=True, timeout=60
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    svg = done.stdout.decode("utf-8", "replace")
    assert "<svg" in svg
    if style == "symbols":
        assert "fta&#45;gate&#45;kofn" in svg or "fta-gate-kofn" in svg
        assert "fta&#45;event&#45;house" in svg or "fta-event-house" in svg
