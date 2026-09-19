"""
FTA JSON Viewer - Renders fault tree diagrams using Graphviz
Copyright (c) makkiblog.com - BSD-2 License
"""

import json
import argparse
import hashlib
import html
import shutil
import subprocess
from pathlib import Path
import re
import tempfile
import os
from datetime import datetime

_ID_UNSAFE = re.compile(r'[^0-9A-Za-z_]')

def sanitize_id(s):
    """A DOT identifier for node id ``s``, distinct for distinct ids.

    Replacing every unsafe character with ``_`` alone is lossy (``a.b`` and
    ``a b`` collapse into one DOT node and their edges cross-wire), so an id
    that needed any replacement also gets a short hash of the original
    appended. Ids that are already plain ASCII words come back unchanged,
    which is what the frontend's click-to-select mapping relies on.
    """
    raw = str(s)
    safe = _ID_UNSAFE.sub('_', raw)
    if safe == raw:
        return safe
    return f"{safe}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:8]}"

def node_label(node, font_size=14, small_font_size=9, cellpadding=6, pad_spaces=4):
    """The HTML-like table label for one node.

    ``pad_spaces`` trailing space characters are appended to both text rows
    (see the bottom of this function): every attempt so far to compute a
    numeric box width ourselves -- a per-character estimate, an explicit
    ``WIDTH`` on the cell -- was still wrong, because it depended on
    guessing the same thing that is actually unknowable in advance: how wide
    *this* text renders in whichever font the browser (or a native ``dot``)
    actually resolves the requested font name to. Appended spaces sidestep
    that guess entirely -- they are measured by the SAME engine, in the SAME
    font, at the SAME size as the visible text, so whatever that engine's
    systematic error is, it applies equally to the padding, and the box
    simply grows by however much extra room ``pad_spaces`` characters need.
    It is an invisible fudge factor rather than a calculation, but a
    fudge factor that automatically tracks the very metrics that were
    causing the mismatch, and it is directly adjustable (diagram.js's box
    scale control) when auto-detection still is not enough.
    """
    name = node.get("name")
    if name is None:
        name = node.get("id", "")
    p = node.get("probability")
    cp = node.get("calculatedProbability")
    gate = node.get("logicGate", "")

    p_str = f"{p:.1E}" if p is not None else "N/A"
    cp_str = f"{cp:.1E}" if cp is not None else "N/A"

    # Show gate type with probabilities, all on same line
    gate_str = f"Gate: {gate} | " if gate else ""

    # The label below is Graphviz' HTML-like syntax, i.e. XML: a name such as
    # "Pressure > 5 bar & T < 50" must be escaped or the whole diagram fails
    # to parse (and, in the browser, an unescaped name can smuggle markup
    # into the SVG). Quotes are left alone -- they are harmless in text
    # content and this keeps the output readable.
    name = html.escape(str(name), quote=False)
    gate_str = html.escape(str(gate_str), quote=False)

    # Color coding based on calculated probability
    if cp == 1.0:
        bgcolor = "pink"
    elif cp == 0.0:
        bgcolor = "lightblue"
    elif cp is not None and cp >= 0.7:
        bgcolor = "lightyellow"
    else:
        bgcolor = "white"

    # CELLPADDING gives the text room on every side; HEIGHT is only a
    # *minimum* (Graphviz still grows a cell to fit its font, so this never
    # clips anything, it just sizes the box). The padding spaces (see the
    # docstring above) go inside the same <FONT> run as the visible text so
    # they are measured at the same size, in the same (guessed) font.
    name_height = max(1, round(font_size * 1.7))
    meta_height = max(1, round(small_font_size * 2.0))
    meta_text = f'{gate_str}P:{p_str} | P_calc:{cp_str}'
    pad = ' ' * max(0, int(pad_spaces))
    return f'''<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="{cellpadding}" BGCOLOR="{bgcolor}">
        <TR><TD HEIGHT="{name_height}"><FONT POINT-SIZE="{font_size}">{name}{pad}</FONT></TD></TR>
        <TR><TD HEIGHT="{meta_height}"><FONT POINT-SIZE="{small_font_size}">{meta_text}{pad}</FONT></TD></TR>
    </TABLE>>'''

def gather_nodes(root, hide_zero=False):
    nodes = {}
    edges = []
    
    def find_node_in_tree(tree_root, target_id):
        """Find a node anywhere in the tree by ID"""
        if tree_root.get("id") == target_id:
            return tree_root
        for child in tree_root.get("children", []):
            result = find_node_in_tree(child, target_id)
            if result:
                return result
        return None
    
    # First pass: traverse tree structure only to establish nodes and parent-child edges
    def traverse_tree_structure(node):
        nid = node.get("id")
        if nid in nodes:
            return  # Already processed
        
        # Skip nodes with zero calculated probability if hide_zero is True
        if hide_zero and node.get("calculatedProbability") == 0.0:
            return
            
        nodes[nid] = node
        
        # Process children in original order (depth-first)
        for child in node.get("children", []):
            # Skip zero probability children if hide_zero is True
            if hide_zero and child.get("calculatedProbability") == 0.0:
                continue
            edges.append((nid, child.get("id"), child.get("logicGate", "")))
            traverse_tree_structure(child)  # Recurse into child
    
    # Second pass: process all links after tree structure is established
    def process_all_links(node):
        nid = node.get("id")
        if nid not in nodes:
            return  # Node was filtered out
            
        # Process links for this node
        for link in node.get("links", []):
            target_id = link.get("target_id")
            if target_id:
                # Find target node in the tree
                target_node = find_node_in_tree(root, target_id)
                if target_node:
                    # Add target node if not already processed and not filtered
                    if target_id not in nodes and not (hide_zero and target_node.get("calculatedProbability") == 0.0):
                        nodes[target_id] = target_node
                    
                    # Add link edge if target exists in nodes
                    if target_id in nodes:
                        edges.append((nid, target_id, link.get("relation", ""), True))
        
        # Process links for children
        for child in node.get("children", []):
            process_all_links(child)
    
    # Execute both passes
    traverse_tree_structure(root)
    process_all_links(root)
    
    return nodes, edges

def build_dot(nodes, edges, font_name="Noto Sans CJK JP", scale=4, dark=False):
    """Build the DOT source for ``nodes``/``edges``.

    ``font_name`` is trusted by the time it gets here -- callers reaching this
    from a network request (``fta_web/rendering.py``) must sanitize it first,
    since it is interpolated directly into ``fontname="..."`` attributes.
    ``scale`` is the number of blank space characters appended to every
    node's text (see ``node_label``'s docstring for why spaces rather than a
    computed width): the box has no size of its own, it just wraps its
    label, so more invisible trailing padding is what grows the box.
    ``dark`` swaps the page background and the tree connectors (lines and
    their arrowheads, which Graphviz colors the same as the edge) for a dark
    theme. The node boxes themselves are left alone: their fill is always one
    of a few light, pastel colours (see ``node_label``), which stays readable
    with the (also unchanged) black label text whichever theme surrounds it.
    """
    font_size = 14
    small_font_size = 9
    cellpadding = 6
    pad_spaces = max(0, round(scale))
    nodesep = 0.12
    ranksep = 0.5
    margin = 0.05
    bgcolor = "#1b1f23" if dark else "white"
    edge_color = "white" if dark else "black"
    lines = [
        'digraph G {',
        '  rankdir=LR;',
        f'  graph [nodesep={nodesep}, ranksep={ranksep}, margin={margin}, overlap=false, bgcolor="{bgcolor}"];',  # Remove splines=true to allow per-edge override
        f'  node [shape=none, fontname="{font_name}"];',
        f'  edge [fontname="{font_name}", arrowsize=0.6, color="{edge_color}"];'
    ]

    # Build parent-child relationships (only for structural edges, not links)
    children_map = {}
    parent_map = {}
    tree_edges = set()  # Track which edges are tree edges
    
    for e in edges:
        if len(e) <= 3:  # Parent-child edge, not a link
            parent, child = e[0], e[1]
            children_map.setdefault(parent, []).append(child)
            parent_map[child] = parent
            tree_edges.add((e[0], e[1]))  # Mark as tree edge

    # Calculate node depth based on tree structure only
    depths = {}
    def calc_depth(node_id):
        if node_id in depths:
            return depths[node_id]
        if node_id not in parent_map:
            depths[node_id] = 0
            return 0
        depths[node_id] = calc_depth(parent_map[node_id]) + 1
        return depths[node_id]

    for nid in nodes:
        calc_depth(nid)

    # Use tree structure traversal to determine node order, ignoring links
    nodes_by_depth = {}
    traversal_order = []
    
    def assign_traversal_order(node):
        nid = node.get("id")
        if nid not in nodes:
            return
            
        traversal_order.append(nid)
        depth = depths.get(nid, 0)
        if depth not in nodes_by_depth:
            nodes_by_depth[depth] = []
        nodes_by_depth[depth].append(nid)
        
        # Process children in order - this preserves tree structure
        for child in node.get("children", []):
            assign_traversal_order(child)
    
    # Find root node and traverse tree structure only
    root_nodes = [nid for nid in nodes.keys() if nid not in parent_map]
    for root_nid in root_nodes:
        if root_nid in nodes:
            assign_traversal_order(nodes[root_nid])

    # Create nodes in traversal order
    for nid in traversal_order:
        if nid in nodes:
            label = node_label(nodes[nid], font_size, small_font_size, cellpadding, pad_spaces)
            lines.append(f'  {sanitize_id(nid)} [label={label}];')

    # Align nodes at same depth using invisible edges to preserve order
    for depth in sorted(nodes_by_depth.keys()):
        depth_nodes = nodes_by_depth[depth]
        if len(depth_nodes) > 1:
            lines.append(f'  subgraph depth_{depth} {{')
            lines.append('    rank=same;')
            # Create invisible edges in traversal order to maintain positioning
            for i in range(len(depth_nodes) - 1):
                lines.append(f'    {sanitize_id(depth_nodes[i])} -> {sanitize_id(depth_nodes[i+1])} [style=invis];')
            lines.append('  }')

    # Create edges with different styles for tree vs link connections
    link_counter = {}  # Track multiple links to same target for offset
    
    for e in edges:
        src_id = sanitize_id(e[0])
        tgt_id = sanitize_id(e[1])
        
        # Check if this is a tree edge or link edge by checking the original edge structure
        is_link_edge = len(e) > 3 and e[3] is True  # Link edges have 4th element as True
        
        if is_link_edge:
            # Link edges: use polyline splines with sharp angles
            edge_key = (src_id, tgt_id)
            if edge_key not in link_counter:
                link_counter[edge_key] = 0
            else:
                link_counter[edge_key] += 1
            
            # Link edges with polyline splines for sharp right-angle turns.
            # Kept blue in both themes: it is already readable on a dark
            # background, and its colour is how a link is told apart from a
            # tree edge, so tying it to the dark/light swap would remove that
            # distinction rather than just re-theming it.
            lines.append(f'  {src_id} -> {tgt_id} [style=dashed, constraint=false, splines=polyline, penwidth=1.5, color="blue"];')
        else:
            # Tree edges: use straight lines with splines=line for direct connections
            lines.append(f'  {src_id}:e -> {tgt_id}:w [style=solid, splines=line, penwidth=1.5, color="{edge_color}"];')

    lines.append('}')
    return "\n".join(lines)

def render_with_dot(dot_text, out_path: Path, high_quality=False):
    """Render DOT text to PNG image using Graphviz"""
    dot_cmd = shutil.which("dot")
    if not dot_cmd:
        raise FileNotFoundError(
            "Graphviz 'dot' not found. Install from https://graphviz.org/download/ and add to PATH."
        )
    
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".dot", encoding="utf-8") as tf:
            tf.write(dot_text)
            tmp = tf.name
        
        if high_quality:
            # Use higher DPI and antialiasing for better text quality
            subprocess.run([
                dot_cmd, "-Tpng", 
                "-Gdpi=300",  # High DPI for better quality
                "-Gfontsize=14",  # Slightly larger base font
                "-Nfontsize=12",  # Node font size
                "-Efontsize=9",  # Edge font size
                "-o", str(out_path), tmp
            ], check=True)
        else:
            # Normal resolution for fast preview
            subprocess.run([dot_cmd, "-Tpng", "-o", str(out_path), tmp], check=True)
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except Exception:
                pass

def main():
    ap = argparse.ArgumentParser(prog="jsonViewer")
    ap.add_argument("-i", "--input", default="sampleFTA.json", help="input json file (FTA)")
    ap.add_argument("-o", "--output", default="fta_diagram.png", help="output image (png)")
    ap.add_argument("--dot", default="fta_diagram.dot", help="write DOT file")
    ap.add_argument("--no-render", action="store_true", help="only write .dot, do not call Graphviz")
    ap.add_argument("--title", default="", help="diagram title (if not in JSON)")
    ap.add_argument("--hide-zero", action="store_true", help="hide nodes with zero calculated probability")
    ap.add_argument("--high-quality", action="store_true", help="render with high DPI for better quality (slower)")
    args = ap.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"Input not found: {in_path}")
        return

    try:
        raw_data = json.loads(in_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        return
    except Exception as e:
        print(f"Error reading file: {e}")
        return
    
    # Handle both direct tree format and metadata wrapper format
    if "tree" in raw_data:
        # New format with metadata wrapper (from UI)
        data = raw_data["tree"]
        title = raw_data.get("title", args.title or "FTA Diagram")
        date = raw_data.get("date", datetime.now().strftime("%Y-%m-%d"))
    elif "metadata" in raw_data:
        # Legacy metadata format
        data = raw_data.get("tree", raw_data)
        title = raw_data.get("metadata", {}).get("title", args.title or "FTA Diagram")
        date = raw_data.get("metadata", {}).get("date", datetime.now().strftime("%Y-%m-%d"))
    else:
        # Direct tree format (legacy)
        data = raw_data
        title = args.title or "FTA Diagram"
        date = datetime.now().strftime("%Y-%m-%d")
    
    if not data:
        print("No tree data found in JSON file")
        return
    
    nodes, edges = gather_nodes(data, hide_zero=args.hide_zero)
    if not nodes:
        print("No nodes found in tree data")
        return
        
    dot_text = build_dot(nodes, edges)

    # Add title and date to DOT
    dot_lines = dot_text.split('\n')
    dot_lines.insert(1, f'  labelloc="t";')
    dot_lines.insert(2, f'  label="{title}\\nDate: {date}";')
    dot_lines.insert(3, f'  fontsize=14;')
    dot_lines.insert(4, f'  fontname="Noto Sans CJK JP";')
    dot_text = '\n'.join(dot_lines)

    dot_path = Path(args.dot)
    dot_path.write_text(dot_text, encoding="utf-8")
    print(f"Wrote DOT file: {dot_path}")

    if args.no_render:
        print("Skipping rendering. Use Graphviz 'dot' to render the .dot file.")
        return

    try:
        out_path = Path(args.output)
        render_with_dot(dot_text, out_path, high_quality=args.high_quality)
        print(f"Rendered image: {out_path}")
    except Exception as e:
        print(f"Rendering failed: {e}")
        print(f"To render manually: dot -Tpng -o {args.output} {dot_path}")

if __name__ == "__main__":
    main()