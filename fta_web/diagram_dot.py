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
    ``XOR``, ``INHIBIT``, ``PAND`` or ``TRANSFER→<target name>``. A leaf with
    a non-basic ``eventKind`` shows ``House: ON|OFF``, ``Undeveloped`` or
    ``Conditioning`` in place of the (meaningless) leaf gate.

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

    Native Graphviz only has polygons, so the shapes are approximations (see
    :data:`GATE_SHAPES` / :data:`EVENT_SHAPES`); the browser replaces them with
    true IEC 61025 / NUREG-0492 paths (``static/js/fta_symbols.js``), keyed by
    the classes above. Gate and event symbols point toward the parent: up in
    ``TB``, left in ``LR`` (Graphviz ``orientation=90``).

Layout
------
``rankdir`` ``LR`` (1.6 default) or ``TB``. Tree edges use compass ports that
follow it: ``:e -> :w`` for LR (as 1.6), ``:s -> :n`` for TB.

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

    def __init__(self, data, sig_figs, pad, dark, rankdir, font_name):
        self.sig_figs = sig_figs
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
    if kind is not None and not is_transfer:
        head = kind + " | "
    elif node.get("logicGate") or node.get("gateType"):
        head = "Gate: " + ctx.gate_text(node) + " | "
    else:
        head = ""
    name_plain = str(name)
    meta_plain = f"{head}P:{p_str} | P_calc:{cp_str}"
    name = html.escape(str(name), quote=False)
    head = html.escape(head, quote=False)
    meta_text = f"{head}P:{p_str} | P_calc:{cp_str}"
    font_size, small_font_size, cellpadding = 14, 9, 6
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
    name_plain = str(name)
    name = html.escape(str(name), quote=False)
    extra = []
    if _gate_type(node) == "TRANSFER":
        extra.append(html.escape(ctx.gate_text(node), quote=False))
    kind = ctx.kind_text(node)
    if kind and _gate_type(node) != "TRANSFER":
        extra.append(html.escape(kind, quote=False))
    probs = "q=%s | Q=%s" % (ctx.prob(node.get("probability")),
                             ctx.prob(node.get("calculatedProbability")))
    if node.get("children") and _gate_type(node) != "TRANSFER":
        probs = "Q=%s" % ctx.prob(node.get("calculatedProbability"))
    lines = [f'<FONT POINT-SIZE="12">{_padded(name_plain, name, ctx.pad)}</FONT>']
    for text in extra:
        lines.append(f'<FONT POINT-SIZE="9">{_padded(html.unescape(text), text, ctx.pad)}</FONT>')
    lines.append(f'<FONT POINT-SIZE="9">'
                 f'{_padded(probs, html.escape(probs, quote=False), ctx.pad)}</FONT>')
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


class _Names:
    """Allocates DOT node names. Plain ids keep ``sanitize_id``'s answer."""

    def __init__(self, plain_ids):
        self.taken = {sanitize_id(nid) for nid in plain_ids}
        self.id_map: Dict[str, str] = {}

    def plain(self, nid) -> str:
        name = sanitize_id(nid)
        self.id_map.setdefault(name, str(nid))
        return name

    def synthetic(self, nid, suffix: str) -> str:
        base = sanitize_id(nid) + suffix
        name, n = base, 1
        while name in self.taken:
            n += 1
            name = "%s_%d" % (base, n)
        self.taken.add(name)
        self.id_map[name] = str(nid)
        return name


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
        # The box and its gate/event symbol share a group, and the edge between
        # them is heavy, so Graphviz keeps the symbol straight under (TB) /
        # beside (LR) its own box instead of drifting toward a neighbour's.
        body.append(
            f'  {box} [shape=box, class="fta-box", group="{box}", style=filled, '
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
                f'group="{box}"',
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
                f'  {sym} [shape={shape}, class="fta-event fta-event-{kind}", group="{box}", '
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
) -> Tuple[str, Dict[str, str]]:
    """``(dot_text, id_map)`` for the tree held by ``core``. Caller holds the lock."""
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

    ctx = _Ctx(data, sig_figs, pad, dark, rankdir, font_name)
    names = _Names(nodes.keys())
    if style == "symbols":
        lines = _symbols(nodes, edges, ctx, names)
    else:
        lines = _compact(nodes, edges, ctx, names)
    _header(lines, title, date, font_name, dark)
    for nid in nodes:  # every emitted node, even one only reached by a link
        names.plain(nid)
    return "\n".join(lines), dict(names.id_map)
