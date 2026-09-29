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
import html
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
    def unpad(dot):
        dot = re.sub(r" +</FONT>", "</FONT>", dot)
        return re.sub(r'(<FONT POINT-SIZE="[0-9]+">) +', r"\1", dot)

    assert unpad(strip.sub("P", new)) == unpad(strip.sub("P", old))


def test_padding_is_proportional_and_split_evenly_around_the_text(legacy):
    """Each row: box-scale spaces + one per two characters, centred."""
    for scale in (0, 4, 8):
        dot, _ = build_dot_text2(legacy, sig_figs=3, scale=scale)
        rows = re.findall(r'POINT-SIZE="(?:9|12|14)">( *)([^<]*?)( *)</FONT>', dot)
        assert rows
        for lead, text, trail in rows:
            total = len(lead) + len(trail)
            plain = html.unescape(text)
            assert total == scale + (len(plain) + 1) // 2, (scale, plain)
            # even split: never more than one space of imbalance
            assert len(trail) - len(lead) in (0, 1)
        if scale == 0:
            # scale 0 used to mean "no padding" and spilled in the browser;
            # the proportional part now always applies.
            assert any(lead for lead, _, _ in rows)


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
    assert re.search(r"^\s{2}root -> root__gate \[weight=100\];$", dot, re.M)
    assert re.search(r"^\s{2}root__gate -> k;$", dot, re.M)
    assert re.search(r"^\s{2}k -> k__gate \[weight=100\];$", dot, re.M)
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


# ---- colour contrast (WCAG: 4.5:1 text, 3:1 graphics) -------------------------------

_NAMED = {"white": "#ffffff", "black": "#000000", "blue": "#0000ff", "pink": "#ffc0cb",
          "lightblue": "#add8e6", "lightyellow": "#ffffe0"}


def _luminance(colour):
    hexa = _NAMED.get(colour, colour).lstrip("#")
    channels = [int(hexa[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.fixture
def linked(rich):
    """The rich tree plus an OR- and an AND-link (dashed edges)."""
    data = rich.get_data()
    data["children"][0]["links"] = [{"target_id": "x0", "relation": "OR"}]
    data["children"][1]["links"] = [{"target_id": "i0", "relation": "AND"}]
    rich.recalculate_probabilities()
    return rich


def _link_colours(dot):
    return re.findall(r'-> \S+ \[style=dashed,.*color="([^"]+)"\];', dot)


@pytest.mark.parametrize("style", ["compact", "symbols"])
def test_link_colour_is_readable_on_the_dark_background(linked, style):
    from fta_web.diagram_dot import DARK_BG

    light, _ = build_dot_text2(linked, style=style)
    dark, _ = build_dot_text2(linked, style=style, dark=True)
    light_colours, dark_colours = set(_link_colours(light)), set(_link_colours(dark))
    assert len(_link_colours(dark)) == 2
    assert light_colours == {"blue"}  # 1.6's colour, unchanged in light mode
    assert len(dark_colours) == 1 and dark_colours != light_colours
    assert _contrast(dark_colours.pop(), DARK_BG) >= 4.5
    assert _contrast("blue", "white") >= 4.5


def _default_attr(dot, kind, attr):
    m = re.search(r"^\s{2}%s \[(.*)\];$" % kind, dot, re.M)
    found = re.search(r'\b%s="([^"]+)"' % attr, m.group(1)) if m else None
    return found.group(1) if found else None


@pytest.mark.parametrize("dark", [False, True])
def test_every_symbols_colour_meets_contrast(linked, dark):
    """Text 4.5:1 on whatever it sits on; outlines, fills and edges 3:1 on the
    background (a shape counts as visible when its outline *or* fill is)."""
    dot, _ = build_dot_text2(linked, style="symbols", dark=dark)
    bg = re.search(r'bgcolor="([^"]+)"', dot).group(1)
    node_fg = _default_attr(dot, "node", "fontcolor")
    node_line = _default_attr(dot, "node", "color")
    edge_line = _default_attr(dot, "edge", "color")
    checked = 0
    for name, attrs in re.findall(r"^\s{2}([A-Za-z0-9_]+) \[(.*)\];$", dot, re.M):
        if name in ("graph", "node", "edge"):
            continue
        get = lambda a, d=None: (re.findall(r'\b%s="([^"]+)"' % a, attrs) or [d])[-1]  # noqa: E731
        fill = get("fillcolor", bg) if "filled" in attrs else bg
        outline = get("color", node_line)
        assert max(_contrast(outline, bg), _contrast(fill, bg)) >= 3.0, (name, outline, fill)
        if 'label=""' not in attrs:
            assert _contrast(get("fontcolor", node_fg), fill) >= 4.5, (name, attrs)
        if "fta-gate-transfer" in attrs:
            assert _contrast(fill, bg) >= 3.0, ("transfer fill", fill)
        checked += 1
    assert checked > 10
    for src, dst, attrs in _TREE_EDGE.findall(dot):
        if "invis" in (attrs or ""):
            continue
        colour = (re.findall(r'color="([^"]+)"', attrs or "") or [edge_line])[-1]
        need = 4.5 if "dashed" in (attrs or "") else 3.0
        assert _contrast(colour, bg) >= need, (src, dst, colour)


@pytest.mark.parametrize("dark", [False, True])
def test_compact_colours_meet_contrast(linked, dark):
    dot, _ = build_dot_text2(linked, style="compact", dark=dark)
    bg = re.search(r'bgcolor="([^"]+)"', dot).group(1)
    for fill in set(re.findall(r'BGCOLOR="([^"]+)"', dot)):
        # Light mode: the black cell border outlines the box. Dark mode: that
        # border is invisible, so the fill itself must stand out.
        assert _contrast(fill, bg) >= 3.0 or not dark
        assert _contrast("black", fill) >= 4.5  # the box text is black
    for src, dst, attrs in _TREE_EDGE.findall(dot):
        if "invis" in (attrs or ""):
            continue
        colour = re.findall(r'color="([^"]+)"', attrs or "")[-1]
        assert _contrast(colour, bg) >= (4.5 if "dashed" in attrs else 3.0), (src, dst, colour)


def test_transfer_children_edges_are_visible(rich):
    rich.find_node_by_id("t")["children"] = [_leaf("tc", "Ignored", 0.5)]
    rich.recalculate_probabilities()
    for dark in (False, True):
        dot, _ = build_dot_text2(rich, style="symbols", dark=dark)
        bg = re.search(r'bgcolor="([^"]+)"', dot).group(1)
        colour = re.search(r'-> tc \[style=dotted, color="([^"]+)"\]', dot).group(1)
        assert _contrast(colour, bg) >= 3.0


# ---- symbols: each gate / event symbol hangs straight off its own box ---------------


@pytest.mark.parametrize("rankdir", ["LR", "TB"])
def test_symbol_shares_a_group_with_its_box(rich, rankdir):
    from fta_web.diagram_dot import SYMBOL_EDGE_WEIGHT

    dot, id_map = build_dot_text2(rich, style="symbols", rankdir=rankdir)
    pairs = 0
    for name, node_id in id_map.items():
        if not (name.endswith("__gate") or name.endswith("__event")):
            continue
        box = sanitize_id(node_id)
        assert 'group="%s"' % box in _attrs_of(dot, name)
        assert 'group="%s"' % box in _attrs_of(dot, box)
        assert re.search(r"^\s{2}%s -> %s \[weight=%d\];$" % (box, name, SYMBOL_EDGE_WEIGHT),
                         dot, re.M), name
        pairs += 1
    assert pairs == len([n for n in id_map if "__" in n]) > 10


def test_compact_style_has_no_groups(rich):
    dot, _ = build_dot_text2(rich, style="compact")
    assert "group=" not in dot and "weight=" not in dot


@needs_graphviz
@pytest.mark.parametrize("style", ["compact", "symbols"])
@pytest.mark.parametrize("rankdir", ["LR", "TB"])
def test_native_dot_parses_dark_links_and_groups(linked, style, rankdir):
    dot, _ = build_dot_text2(linked, style=style, rankdir=rankdir, dark=True)
    done = subprocess.run(["dot", "-Tsvg"], input=dot.encode("utf-8"), capture_output=True,
                          timeout=60)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    svg = done.stdout.decode("utf-8", "replace")
    from fta_web.diagram_dot import DARK_LINK_COLOR

    assert DARK_LINK_COLOR in svg and 'stroke="blue"' not in svg


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
