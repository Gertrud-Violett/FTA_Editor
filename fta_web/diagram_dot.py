"""
DOT generation with the 1.7 diagram options: gate symbols, layout direction
and significant figures.

:func:`build_dot_text2` is what ``GET /api/dot`` and ``POST /api/render`` call.
``rendering.build_dot_text`` (the 1.6 pipeline) is left as it was, for the
CLI-parity tests and anything else that still wants the vendored output.

What it reuses, and what it does not
------------------------------------
``json_viewer.gather_nodes`` (which nodes and edges exist, ``hide_zero``,
link resolution) and ``json_viewer.sanitize_id`` (the DOT node name for a
tree id) are imported and called unchanged. ``json_viewer.build_dot`` and
``node_label`` are *not* called, because they hard-code ``rankdir=LR``, the
``:e -> :w`` ports and the ``.1E`` probability format. Their layout rules --
traversal order, a ``rank=same`` subgraph per depth chained with invisible
edges, dashed blue links -- are reproduced here, so a legacy tree in the
``compact`` style lays out exactly as in 1.6. The title/date header and the
font/scale sanitisers come from ``rendering``.

Styles
------
``compact``
    The 1.6 boxes (an HTML-like two-row table, the D12 trailing-space padding,
    D13 escaping, the probability colour code). The meta row now reads
    ``Gate: <gate> | P:<q> | P_calc:<Q>`` with probabilities through
    ``numfmt.format_prob(sig_figs)`` and the 1.7 gate shown as ``2/3`` (KOFN),
    ``XOR``, ``INHIBIT``, ``PAND`` or ``TRANSFER→<target name>``. A leaf has
    no gate, so (since 1.7.1) a basic event reads ``P:<q> | P_calc:<Q>``
    (1.6 showed its default ``Gate: OR``) and a leaf with a non-basic
    ``eventKind`` shows ``House: ON|OFF``, ``Undeveloped`` or
    ``Conditioning`` in front instead.

``symbols``
    Standard fault-tree drawing. Every node is a description rectangle
    (``class="fta-box"``) named by its plain sanitised id. Under it:

    * a node with children gets a gate symbol node ``<sid>__gate``
      (``class="fta-gate fta-gate-<type>"``);
    * a leaf gets an event symbol node ``<sid>__event``
      (``class="fta-event fta-event-<kind>"``);
    * a ``TRANSFER`` node (with or without children) gets a transfer triangle
      ``<sid>__gate`` (``fta-gate-transfer``); its children are still drawn,
      dotted, because the engine ignores them;
    * a ``conditioning`` leaf is drawn as the ellipse itself (no rectangle),
      hanging off its INHIBIT gate, as in NUREG-0492.

    The box reads the name, then one bold row with the numbers: ``Q=<Q>`` for
    a gate, ``q=<q>`` for an event whose calculated value is its own, and
    ``q=<q> | Q=<Q>`` only where the two differ.

    Native Graphviz only has polygons, so the shapes are approximations (see
    :data:`GATE_SHAPES` / :data:`EVENT_SHAPES`); the browser replaces them with
    true IEC 61025 / NUREG-0492 paths (``static/js/fta_symbols.js``), keyed by
    the classes above. Gate and event symbols point toward the parent: up in
    ``TB``, left in ``LR`` (Graphviz ``orientation=90``).

Layout
------
``rankdir`` ``LR`` (1.6 default) or ``TB``. Tree edges use compass ports that
follow it: ``:e -> :w`` for LR (as 1.6), ``:s -> :n`` for TB.

The top event's box
-------------------
Every box shows its node's ``calculatedProbability``, the tree walk's value.
For a tree with repeated events or an XOR gate the headline is the min-cut
upper bound instead, and the top box used to disagree with the top bar. When
``build_dot_text2`` is given such a headline (``root_headline``, from
``engine.root_headline``), the **root's** label shows it, marked, with the
tree-walk value beside it::

    compact   P:1 | P_calc:0.0684 (MCUB) | tree walk 0.0349
    symbols   Q=0.0684 (MCUB)
              tree walk 0.0349

Every other node keeps its tree-walk value: a cut-set value per gate would
cost one expansion per gate, and it is a different quantity -- the tree-walk
numbers are the ones that combine along the edges drawn. Without a headline
(``None``: no repeated events, ETA mode, cut sets capped or failed) the
output is what it always was, byte for byte.

``id_map``
----------
DOT node name -> tree node id for **every** node emitted, plain and
synthetic. A plain id keeps exactly the name ``sanitize_id`` gives it (1.6
click-to-select and the 1.6 JS mirror keep working without the map); the
synthetic names are ``<sid>__gate`` / ``<sid>__event``, suffixed ``_2``,
``_3`` ... in the (pathological) case that such a name is already taken by a
real node id.
"""
from __future__ import annotations

import copy
import html
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

try:  # normal package import: ``import fta_web.diagram_dot``
    from . import config  # noqa: F401  (puts fta_web/core on sys.path)
    from .numfmt import clamp_sig_figs, format_prob
    from .rendering import (
        DEFAULT_FONT,
        DEFAULT_SCALE,
        _escape_label,
        clamp_scale,
        sanitize_font_name,
        xml_safe,
    )
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import config  # type: ignore[no-redef]  # noqa: F401
    from numfmt import clamp_sig_figs, format_prob  # type: ignore[no-redef]
    from rendering import (  # type: ignore[no-redef]
        DEFAULT_FONT,
        DEFAULT_SCALE,
        _escape_label,
        clamp_scale,
        sanitize_font_name,
        xml_safe,
    )

from json_viewer import gather_nodes, sanitize_id  # noqa: E402

STYLES = ("compact", "symbols")
RANKDIRS = ("LR", "TB")
DEFAULT_STYLE = "compact"
DEFAULT_RANKDIR = "LR"

GATE_TYPES = ("AND", "OR", "KOFN", "XOR", "INHIBIT", "PAND", "TRANSFER")
EVENT_KINDS = ("basic", "house", "undeveloped", "conditioning")

#: gate type -> (Graphviz shape, extra attributes) for the native
#: approximation. Pointing toward the parent, the "house" pentagon is the
#: nearest polygon to the AND dome, the triangle to the OR shield (whose
#: variants XOR/KOFN add a second periphery or a k/n label), the hexagon *is*
#: the INHIBIT symbol, and the transfer triangle is filled to tell it from OR.
GATE_SHAPES: Dict[str, Tuple[str, str]] = {
    "AND": ("house", ""),
    "PAND": ("house", "peripheries=2"),
    "OR": ("triangle", ""),
    "XOR": ("triangle", "peripheries=2"),
    "KOFN": ("triangle", ""),
    "INHIBIT": ("hexagon", ""),
    "TRANSFER": ("triangle", 'style=filled, fillcolor="{muted}"'),
}

#: event kind -> Graphviz shape. These are the standard symbols already.
EVENT_SHAPES: Dict[str, str] = {
    "basic": "circle",
    "undeveloped": "diamond",
    "house": "house",
    "conditioning": "ellipse",
}

_GATE_LABEL = {"PAND": "PAND", "INHIBIT": "INH", "TRANSFER": ""}

#: Dark-mode diagram background, and the theme colours drawn on it (or on
#: white). Every one is checked for contrast in test_diagram_dot.py.
DARK_BG = "#1b1f23"
LIGHT_LINK_COLOR = "blue"
DARK_LINK_COLOR = "#6cb6ff"
LIGHT_MUTED = "#8c959f"
DARK_MUTED = "#8b949e"

#: How the root's label marks the MCUB headline and the tree-walk value it
#: shows beside it. Plain ASCII in both languages, like ``P_calc`` and
#: ``Gate:``; the diagram panel's caption explains them (en/ja).
MCUB_MARK = "MCUB"
TREE_WALK_MARK = "tree walk"

#: Type sizes, in points. A fitted diagram of a real tree is drawn at 30-50 %,
#: where the 9 pt probability row of 1.7 came out about 4 px high. In the
#: symbols style the row with the numbers is now the largest in the box, and
#: bold: a box is as wide as its name, so the larger number costs height
#: only. The compact style keeps its 1.6 text and only grows its meta row.
SYMBOLS_NAME_PT = 12
SYMBOLS_PROB_PT = 14
SYMBOLS_EXTRA_PT = 9
COMPACT_META_PT = 11

#: Weight of the box -> gate/event-symbol edge in the symbols style (tree
#: edges keep Graphviz' default 1): the symbol hangs straight off its box.
SYMBOL_EDGE_WEIGHT = 100


def _gate_type(node: Dict[str, Any]) -> str:
    """The node's effective gate: ``gateType`` when valid, else ``logicGate``."""
    raw = node.get("gateType")
    if isinstance(raw, str) and raw.strip().upper() in GATE_TYPES:
        return raw.strip().upper()
    gate = node.get("logicGate")
    gate = str(gate).strip().upper() if gate else "OR"
    return gate if gate in ("AND", "OR") else gate


def _event_kind(node: Dict[str, Any]) -> str:
    raw = node.get("eventKind")
    if isinstance(raw, str) and raw.strip().lower() in EVENT_KINDS:
        return raw.strip().lower()
    return "basic"


def _k_of_n(node: Dict[str, Any]) -> str:
    n = len(node.get("children") or [])
    k = node.get("k")
    if isinstance(k, float) and k.is_integer():
        k = int(k)
    if isinstance(k, bool) or not isinstance(k, int):
        k = "?"
    return "%s/%d" % (k, n)


def _bgcolor(cp: Any) -> str:
    """json_viewer.node_label's probability colour code, unchanged."""
    if cp == 1.0:
        return "pink"
    if cp == 0.0:
        return "lightblue"
    if cp is not None and isinstance(cp, (int, float)) and cp >= 0.7:
        return "lightyellow"
    return "white"


class _Ctx:
    """What every label/shape helper needs, computed once per call."""

    def __init__(self, data, sig_figs, pad, dark, rankdir, font_name, root_headline=None,
                 eta=False):
        self.sig_figs = sig_figs
        # An event tree: a branch point is not a gate, so no gate text
        # (compact) and no gate or event symbol (symbols) is drawn for it.
        self.eta = bool(eta)
        # The root node object and the MCUB headline its label shows instead
        # of its tree-walk value (None: every label is the tree walk's).
        self.root = data if isinstance(data, dict) and data else None
        self.root_headline = root_headline if self.root is not None else None
        self.pad = pad
        self.dark = dark
        self.rankdir = rankdir
        self.font_name = font_name
        self.names: Dict[str, str] = {}
        self._index(data)
        self.fg = "white" if dark else "black"
        self.bg = DARK_BG if dark else "white"
        # Non-text graphics (the transfer fill, a transfer's dotted ignored
        # children) need >= 3:1 against the background (WCAG 1.4.11): the
        # 1.7.0 greys were 2.7:1 (dark) and 1.5:1 (light) and all but vanished.
        self.muted = DARK_MUTED if dark else LIGHT_MUTED
        # Cross-link edges and their arrowheads. Pure blue is 2.2:1 on the dark
        # background; the light blue is ~8:1 there. Light mode keeps 1.6's blue.
        self.link = DARK_LINK_COLOR if dark else LIGHT_LINK_COLOR
        # Tree edge ports: they must follow the layout direction or every
        # edge doubles back around its own node.
        # LR keeps 1.6's east->west ports; TB uses none (Graphviz then picks
        # the nearest side, which for TB is bottom->top, and draws straighter
        # edges than a forced :s->:n pair does).
        self.out_port, self.in_port = (":e", ":w") if rankdir == "LR" else ("", "")

    def _index(self, data):
        stack = [data] if isinstance(data, dict) and data else []
        while stack:
            node = stack.pop()
            nid = str(node.get("id"))
            if nid not in self.names:
                name = node.get("name")
                self.names[nid] = str(name if name is not None else nid)
            stack.extend(c for c in (node.get("children") or []) if isinstance(c, dict))

    def prob(self, value: Any) -> str:
        if value is None:
            return "N/A"
        return format_prob(value, self.sig_figs)

    def headline_for(self, node: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        """``("<headline> (MCUB)", "tree walk <Q>")`` for the root when the
        headline is the MCUB, else None. By identity: a second node carrying
        the root's id (a hand-edited file) is not the top event."""
        if self.root_headline is None or node is not self.root:
            return None
        return ("%s (%s)" % (self.prob(self.root_headline.get("value")), MCUB_MARK),
                "%s %s" % (TREE_WALK_MARK, self.prob(node.get("calculatedProbability"))))

    def gate_text(self, node: Dict[str, Any]) -> str:
        """``Gate: ...`` value for the compact meta row (unescaped)."""
        gate = _gate_type(node)
        if gate == "KOFN":
            return _k_of_n(node)
        if gate == "TRANSFER":
            target = node.get("transferTo")
            name = self.names.get(str(target)) if target not in (None, "") else None
            return "TRANSFER→" + (name if name is not None else "?")
        return gate

    def kind_text(self, node: Dict[str, Any]) -> Optional[str]:
        """A leaf's event-kind marker, or None for a basic (or non-leaf) node."""
        if node.get("children"):
            return None
        kind = _event_kind(node)
        if kind == "house":
            return "House: " + ("ON" if node.get("houseState") is True else "OFF")
        if kind == "undeveloped":
            return "Undeveloped"
        if kind == "conditioning":
            return "Conditioning"
        return None


# ---- labels ------------------------------------------------------------------


def _compact_label(node: Dict[str, Any], ctx: _Ctx) -> str:
    """json_viewer.node_label with 1.7 gates and sig-fig probabilities."""
    name = node.get("name")
    if name is None:
        name = node.get("id", "")
    cp = node.get("calculatedProbability")
    p_str = ctx.prob(node.get("probability"))
    cp_str = ctx.prob(cp)
    kind = ctx.kind_text(node)
    is_transfer = _gate_type(node) == "TRANSFER"
    if ctx.eta:
        # ETA mode: the stored logicGate is the FTA default and plays no part
        # in the calculation, so "Gate: OR" on an event tree said nothing true.
        head = ""
    elif kind is not None and not is_transfer:
        head = kind + " | "
    elif (node.get("children") or is_transfer) and (node.get("logicGate")
                                                    or node.get("gateType")):
        head = "Gate: " + ctx.gate_text(node) + " | "
    else:
        # A leaf event has no gate: 1.6 showed its default "Gate: OR" (1.7.1
        # drops it; the symbols style never drew a gate for a leaf either).
        head = ""
    # xml_safe: a character XML forbids would make the label unparseable.
    name_plain = xml_safe(name)
    head = xml_safe(head)
    marked = ctx.headline_for(node)
    if marked is not None:
        cp_str = "%s | %s" % marked
    meta_plain = f"{head}P:{p_str} | P_calc:{cp_str}"
    name = html.escape(name_plain, quote=False)
    head = html.escape(head, quote=False)
    meta_text = f"{head}P:{p_str} | P_calc:{cp_str}"
    font_size, small_font_size, cellpadding = 14, COMPACT_META_PT, 6
    name_height = max(1, round(font_size * 1.7))
    meta_height = max(1, round(small_font_size * 2.0))
    return f'''<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="{cellpadding}" BGCOLOR="{_bgcolor(cp)}">
        <TR><TD HEIGHT="{name_height}"><FONT POINT-SIZE="{font_size}">{_padded(name_plain, name, ctx.pad)}</FONT></TD></TR>
        <TR><TD HEIGHT="{meta_height}"><FONT POINT-SIZE="{small_font_size}">{_padded(meta_plain, meta_text, ctx.pad)}</FONT></TD></TR>
    </TABLE>>'''


def _box_label(node: Dict[str, Any], ctx: _Ctx) -> str:
    """Description rectangle of the symbols style: name over q / Q."""
    name = node.get("name")
    if name is None:
        name = node.get("id", "")
    name_plain = xml_safe(name)
    name = html.escape(name_plain, quote=False)
    extra = []
    if _gate_type(node) == "TRANSFER":
        extra.append(html.escape(xml_safe(ctx.gate_text(node)), quote=False))
    kind = ctx.kind_text(node)
    if kind and _gate_type(node) != "TRANSFER":
        extra.append(html.escape(kind, quote=False))
    marked = ctx.headline_for(node)
    calc = marked[0] if marked is not None else ctx.prob(node.get("calculatedProbability"))
    base = ctx.prob(node.get("probability"))
    if ctx.eta:
        # Every node of an event tree has its own branch probability (q) and
        # the probability of the path down to it (Q).
        probs = ("q=%s" % base) if base == calc else "q=%s | Q=%s" % (base, calc)
    elif node.get("children") and _gate_type(node) != "TRANSFER":
        probs = "Q=%s" % calc
    elif base == calc:
        # An event's calculated value is its own: "q=0.01 | Q=0.01" said the
        # same number twice, in the smallest type of the box. A leaf whose two
        # values do differ (an event with links) still shows both.
        probs = "q=%s" % base
    else:
        probs = "q=%s | Q=%s" % (base, calc)
    lines = [f'<FONT POINT-SIZE="{SYMBOLS_NAME_PT}">{_padded(name_plain, name, ctx.pad)}</FONT>']
    for text in extra:
        lines.append(f'<FONT POINT-SIZE="{SYMBOLS_EXTRA_PT}">'
                     f'{_padded(html.unescape(text), text, ctx.pad)}</FONT>')
    # The number is what the diagram is read for: the largest row, and bold. <B> goes outside <FONT>, so the row is still one FONT element
    # with nothing but its text inside, which is what every label reader
    # (tests, the back-to-back suite) matches.
    lines.append(f'<B><FONT POINT-SIZE="{SYMBOLS_PROB_PT}">'
                 f'{_padded(probs, html.escape(probs, quote=False), ctx.pad)}</FONT></B>')
    if marked is not None:
        lines.append(f'<FONT POINT-SIZE="{SYMBOLS_EXTRA_PT}">'
                     f'{_padded(marked[1], marked[1], ctx.pad)}</FONT>')
    return "<" + "<BR/>".join(lines) + ">"


def _padded(plain: str, escaped: str, pad: str) -> str:
    """One label row with padding split evenly before and after the text.

    Graphviz sizes a cell from its own font metrics, but the browser draws
    the text with the real (usually wider) UI font. Measured in 1.7:
    Graphviz (WASM, and native SVG when it cannot resolve the font) sizes
    text with Times-like metrics, ~20-25% narrower than Meiryo or Segoe UI,
    while a padding space is only ~0.25 em. The shortfall grows with the
    row's length, so every row gets one space per two characters, plus the
    user's box-scale spaces on top (scale 0 therefore no longer spills).

    Graphviz writes the spaces as non-breaking spaces with
    ``xml:space="preserve"`` and a start anchor, so leading spaces render.
    Splitting the padding evenly keeps the text centred in its box; 1.6's
    trailing-only padding pushed it left by half the padding.
    """
    total = len(pad) + (len(plain) + 1) // 2
    lead = total // 2
    return " " * lead + escaped + " " * (total - lead)


# ---- graph skeleton ------------------------------------------------------------


def _token(name: str) -> str:
    """``name`` (``[0-9A-Za-z_]`` only) as one DOT ID token.

    Unquoted, DOT reads a name that starts with a digit as a number: ``1a``
    -- or ``1_1_<hash>``, ``sanitize_id``'s answer for ``1.1`` -- splits into
    ``1`` and ``a`` ("badly delimited number"), so the diagram gained a stray
    node ``1`` on the parent's edge while the real box floated unconnected.
    Such a name is quoted; an all-digit name is a DOT numeral and every other
    name a DOT ID, so those stay as they were (the ``<title>`` Graphviz
    writes is the name either way).
    """
    if name and (name.isdigit() or not name[0].isdigit()):
        return name
    return '"%s"' % name


class _Names:
    """Allocates DOT node names. Plain ids keep ``sanitize_id``'s answer.

    ``plain``/``synthetic`` return the name as a DOT token (see
    :func:`_token`); ``id_map`` and ``taken`` hold the bare names, which is
    what the SVG ``<title>`` carries.
    """

    def __init__(self, plain_ids):
        self.taken = {sanitize_id(nid) for nid in plain_ids}
        self.id_map: Dict[str, str] = {}

    def plain(self, nid) -> str:
        name = sanitize_id(nid)
        self.id_map.setdefault(name, str(nid))
        return _token(name)

    def synthetic(self, nid, suffix: str) -> str:
        base = sanitize_id(nid) + suffix
        name, n = base, 1
        while name in self.taken:
            n += 1
            name = "%s_%d" % (base, n)
        self.taken.add(name)
        self.id_map[name] = str(nid)
        return _token(name)


def _layout(nodes, edges):
    """json_viewer.build_dot's traversal order and per-depth grouping."""
    parent_map: Dict[Any, Any] = {}
    for e in edges:
        if len(e) <= 3:
            parent_map[e[1]] = e[0]

    depths: Dict[Any, int] = {}

    def calc_depth(nid):
        # Iterative: a deep tree must not hit the recursion limit here.
        chain = []
        on_chain = set()
        cur = nid
        while cur not in depths and cur in parent_map and cur not in on_chain:
            chain.append(cur)
            on_chain.add(cur)
            cur = parent_map[cur]
        if cur in on_chain:  # duplicate ids made a parent loop; treat as a root
            depths[cur] = 0
            chain = chain[: chain.index(cur)]
        base = depths.setdefault(cur, 0) if cur not in parent_map else depths[cur]
        for offset, item in enumerate(reversed(chain), start=1):
            depths[item] = base + offset
        return depths[nid]

    for nid in nodes:
        calc_depth(nid)

    order: List[Any] = []
    by_depth: Dict[int, List[Any]] = {}
    seen = set()

    def visit(root):
        stack = [root]
        while stack:
            node = stack.pop()
            nid = node.get("id")
            if nid not in nodes:
                continue
            order.append(nid)
            by_depth.setdefault(depths.get(nid, 0), []).append(nid)
            if nid in seen:  # json_viewer would re-append too; mirror, but stop
                continue
            seen.add(nid)
            stack.extend(reversed(node.get("children", []) or []))

    for nid in [n for n in nodes.keys() if n not in parent_map]:
        visit(nodes[nid])
    return order, by_depth, parent_map


def _header(lines: List[str], title: str, date: str, font_name: str, dark: bool) -> None:
    """rendering.build_dot_text's title/date lines, at the same positions."""
    lines.insert(1, '  labelloc="t";')
    lines.insert(2, f'  label="{_escape_label(title)}\\nDate: {_escape_label(date)}";')
    lines.insert(3, '  fontsize=14;')
    lines.insert(4, f'  fontname="{font_name}";')
    lines.insert(5, f'  fontcolor="{"white" if dark else "black"}";')


def _link_lines(edges, names: _Names, ctx: _Ctx) -> List[str]:
    out = []
    for e in edges:
        if len(e) > 3 and e[3] is True:
            out.append(
                f'  {names.plain(e[0])} -> {names.plain(e[1])} [style=dashed, '
                f'constraint=false, splines=polyline, penwidth=1.5, color="{ctx.link}"];'
            )
    return out


def _rank_lines(by_depth, names: _Names, name_for=None) -> List[str]:
    out = []
    for depth in sorted(by_depth):
        group = [nid for nid in by_depth[depth] if name_for is None or name_for(nid)]
        if len(group) > 1:
            out.append(f'  subgraph depth_{depth} {{')
            out.append('    rank=same;')
            for a, b in zip(group, group[1:]):
                out.append(f'    {names.plain(a)} -> {names.plain(b)} [style=invis];')
            out.append('  }')
    return out


def _compact(nodes, edges, ctx: _Ctx, names: _Names) -> List[str]:
    order, by_depth, _parents = _layout(nodes, edges)
    lines = [
        'digraph G {',
        f'  rankdir={ctx.rankdir};',
        f'  graph [nodesep=0.12, ranksep=0.5, margin=0.05, overlap=false, bgcolor="{ctx.bg}"];',
        f'  node [shape=none, fontname="{ctx.font_name}"];',
        f'  edge [fontname="{ctx.font_name}", arrowsize=0.6, color="{ctx.fg}"];',
    ]
    for nid in order:
        lines.append(f'  {names.plain(nid)} [label={_compact_label(nodes[nid], ctx)}];')
    lines.extend(_rank_lines(by_depth, names))
    for e in edges:
        if len(e) > 3 and e[3] is True:
            continue
        lines.append(
            f'  {names.plain(e[0])}{ctx.out_port} -> {names.plain(e[1])}{ctx.in_port} '
            f'[style=solid, splines=line, penwidth=1.5, color="{ctx.fg}"];'
        )
    lines.extend(_link_lines(edges, names, ctx))
    lines.append('}')
    return lines


def _symbols(nodes, edges, ctx: _Ctx, names: _Names) -> List[str]:
    order, by_depth, parent_map = _layout(nodes, edges)
    orient = ", orientation=90" if ctx.rankdir == "LR" else ""
    lines = [
        'digraph G {',
        f'  rankdir={ctx.rankdir};',
        f'  graph [nodesep=0.25, ranksep=0.3, margin=0.05, overlap=false, splines=ortho, bgcolor="{ctx.bg}"];',
        f'  node [fontname="{ctx.font_name}", color="{ctx.fg}", fontcolor="{ctx.fg}", penwidth=1.2];',
        f'  edge [fontname="{ctx.font_name}", dir=none, color="{ctx.fg}", penwidth=1.2];',
    ]

    def is_conditioning(nid) -> bool:
        if ctx.eta:
            return False
        node = nodes[nid]
        if node.get("children") or _gate_type(node) == "TRANSFER":
            return False
        if _event_kind(node) != "conditioning":
            return False
        parent = nodes.get(parent_map.get(nid))
        return bool(parent) and _gate_type(parent) == "INHIBIT"

    # attach[nid] = the DOT name a tree edge *from* nid starts at.
    attach: Dict[Any, str] = {}
    body: List[str] = []
    emitted = set()
    for nid in order:
        if nid in emitted:
            continue
        emitted.add(nid)
        node = nodes[nid]
        box = names.plain(nid)
        group = sanitize_id(nid)  # the bare name, inside the quoted attribute
        cp = node.get("calculatedProbability")
        gate = _gate_type(node)
        if is_conditioning(nid):
            body.append(
                f'  {box} [shape=ellipse, class="fta-event fta-event-conditioning", '
                f'style=filled, fillcolor="{_bgcolor(cp)}", fontcolor="black", '
                f'margin="0.12,0.04", label={_box_label(node, ctx)}];'
            )
            attach[nid] = box
            continue
        if ctx.eta:
            # An event tree: the boxes are joined directly. A gate symbol
            # under each branch point claimed an AND/OR that is not there.
            body.append(
                f'  {box} [shape=box, class="fta-box", style=filled, '
                f'fillcolor="{_bgcolor(cp)}", '
                f'fontcolor="black", margin="0.2,0.05", label={_box_label(node, ctx)}];'
            )
            attach[nid] = box
            continue
        # The box and its gate/event symbol share a group, and the edge between
        # them is heavy, so Graphviz keeps the symbol straight under (TB) /
        # beside (LR) its own box instead of drifting toward a neighbour's.
        body.append(
            f'  {box} [shape=box, class="fta-box", group="{group}", style=filled, '
            f'fillcolor="{_bgcolor(cp)}", '
            f'fontcolor="black", margin="0.2,0.05", label={_box_label(node, ctx)}];'
        )
        if gate == "TRANSFER" or node.get("children"):
            sym = names.synthetic(nid, "__gate")
            shape, extra = GATE_SHAPES.get(gate, GATE_SHAPES["OR"])
            gate_class = gate.lower() if gate in GATE_TYPES else "or"
            label = _k_of_n(node) if gate == "KOFN" else _GATE_LABEL.get(gate, gate)
            attrs = [
                f'shape={shape}',
                f'class="fta-gate fta-gate-{gate_class}"',
                f'group="{group}"',
                'width=0.55, height=0.55, fixedsize=true, fontsize=9',
                f'fillcolor="{ctx.bg}", style=filled',
                f'label="{_escape_label(label)}"',
            ]
            if extra:
                attrs.append(extra.format(muted=ctx.muted))
            body.append(f'  {sym} [{", ".join(attrs)}{orient}];')
        else:
            kind = _event_kind(node)
            sym = names.synthetic(nid, "__event")
            shape = EVENT_SHAPES[kind]
            size = "0.4" if kind != "house" else "0.45"
            label = ""
            if kind == "house":
                label = "ON" if node.get("houseState") is True else "OFF"
            body.append(
                f'  {sym} [shape={shape}, class="fta-event fta-event-{kind}", group="{group}", '
                f'width={size}, height={size}, fixedsize=true, fontsize=8, '
                f'style=filled, fillcolor="{ctx.bg}", label="{label}"{orient}];'
            )
        body.append(f'  {box} -> {sym} [weight={SYMBOL_EDGE_WEIGHT}];')
        attach[nid] = sym

    lines.extend(body)
    lines.extend(_rank_lines(by_depth, names, name_for=lambda n: not is_conditioning(n)))
    for e in edges:
        if len(e) > 3 and e[3] is True:
            continue
        parent = nodes.get(e[0])
        src = attach.get(e[0], names.plain(e[0]))
        style = ""
        if parent is not None and _gate_type(parent) == "TRANSFER":
            # The engine ignores a transfer gate's own children.
            style = f' [style=dotted, color="{ctx.muted}"]'
        lines.append(f'  {src} -> {names.plain(e[1])}{style};')
    lines.extend(_link_lines(edges, names, ctx))
    lines.append('}')
    return lines


def build_dot_text2(
    core,
    hide_zero: bool = False,
    font_name: str = DEFAULT_FONT,
    scale: float = DEFAULT_SCALE,
    dark: bool = False,
    style: str = DEFAULT_STYLE,
    rankdir: str = DEFAULT_RANKDIR,
    sig_figs: int = 3,
    root_headline: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, str]]:
    """``(dot_text, id_map)`` for the tree held by ``core``. Caller holds the
    lock, or passes a detached copy (:class:`DocView`).

    ``root_headline`` is ``engine.root_headline``'s answer for this same
    tree, computed by the caller (:func:`document_dot` does both from one
    snapshot): the root's label then shows the MCUB headline and its
    tree-walk value. None leaves every label as the tree walk's.
    """
    style = style if style in STYLES else DEFAULT_STYLE
    rankdir = rankdir if rankdir in RANKDIRS else DEFAULT_RANKDIR
    sig_figs = clamp_sig_figs(sig_figs)
    font_name = sanitize_font_name(font_name)
    pad = " " * max(0, clamp_scale(scale))

    data = core.get_data() or {}
    metadata = core.get_metadata() or {}
    title = metadata.get("title") or "FTA Diagram"
    date = metadata.get("date") or datetime.now().strftime("%Y-%m-%d")

    if data:
        nodes, edges = gather_nodes(data, hide_zero=hide_zero)
    else:
        nodes, edges = {}, []

    eta = str(metadata.get("mode") or "").strip().upper() == "ETA"
    ctx = _Ctx(data, sig_figs, pad, dark, rankdir, font_name, root_headline, eta=eta)
    names = _Names(nodes.keys())
    if style == "symbols":
        lines = _symbols(nodes, edges, ctx, names)
    else:
        lines = _compact(nodes, edges, ctx, names)
    _header(lines, title, date, font_name, dark)
    for nid in nodes:  # every emitted node, even one only reached by a link
        names.plain(nid)
    return "\n".join(lines), dict(names.id_map)


# ---- the document's diagram, with the top event's headline ---------------------


class DocView:
    """A detached copy of what :func:`build_dot_text2` reads of a core."""

    def __init__(self, tree: Any, metadata: Dict[str, Any]):
        self._tree = tree
        self._metadata = metadata

    def get_data(self):
        return self._tree

    def get_metadata(self):
        return self._metadata


def document_dot(core, lock=None, **options
                 ) -> Tuple[str, Dict[str, str], Optional[Dict[str, Any]]]:
    """``(dot_text, id_map, root_headline)`` for ``core``'s document, the
    root labelled with the MCUB headline when that is the headline.

    The document is read once. A tree whose headline can only be the tree
    walk (no link, transfer or XOR: ``engine.may_need_cut_sets``) is drawn
    straight from ``core`` under ``lock``, as before 1.7.3. Any other is
    deep-copied under ``lock`` and the lock released; the headline
    (``engine.diagram_headline``: at most the summary's 2 s, remembered per
    document) and the DOT are then both computed from that one copy, so the
    label and the tree it sits on are the same document, and a slow cut-set
    expansion never holds the editor's lock.

    ``lock`` is ``state.lock``; None when the caller owns ``core`` (the CLI)
    or passes a detached copy.
    """
    try:
        from . import engine
    except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
        import engine  # type: ignore[no-redef]

    def read():
        metadata = dict(core.get_metadata() or {})
        tree = core.get_data() or {}
        if (engine.canonical_mode(metadata.get("mode")) == "ETA"
                or not engine.may_need_cut_sets(tree)):
            return build_dot_text2(core, **options), None
        return None, (copy.deepcopy(tree), metadata,
                      copy.deepcopy(getattr(core, "analysis", None)))

    if lock is not None:
        with lock:
            drawn, snapshot = read()
    else:
        drawn, snapshot = read()
    if drawn is not None:
        return drawn[0], drawn[1], None
    tree, metadata, analysis = snapshot
    headline = engine.diagram_headline(tree, analysis, metadata.get("mode"))
    dot, id_map = build_dot_text2(DocView(tree, metadata), root_headline=headline, **options)
    return dot, id_map, headline
