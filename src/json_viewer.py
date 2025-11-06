"""
FTA JSON Viewer - Renders fault tree diagrams using Graphviz
Copyright (c) makkiblog.com - BSD-2 License
"""

import json
import argparse
import shutil
import subprocess
from pathlib import Path
import re
import tempfile
import os
from datetime import datetime

def sanitize_id(s):
    return re.sub(r'[^0-9A-Za-z_]', '_', str(s))

def node_label(node):
    name = node.get("name", node.get("id", ""))
    p = node.get("probability")
    cp = node.get("calculatedProbability")
    gate = node.get("logicGate", "")
    
    p_str = f"{p:.3f}" if p is not None else "N/A"
    cp_str = f"{cp:.3f}" if cp is not None else "N/A"
    
    # Show gate type with probabilities, all on same line
    gate_str = f"Gate: {gate} | " if gate else ""
    
    # Color coding based on calculated probability
    if cp == 1.0:
        bgcolor = "pink"
    elif cp == 0.0:
        bgcolor = "lightblue"
    elif cp is not None and cp >= 0.7:
        bgcolor = "lightyellow"
    else:
        bgcolor = "white"
    
    return f'''<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" BGCOLOR="{bgcolor}">
        <TR><TD HEIGHT="24">{name}</TD></TR>
        <TR><TD HEIGHT="18"><FONT POINT-SIZE="9">{gate_str}P:{p_str} | P_calc:{cp_str}</FONT></TD></TR>
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

def build_dot(nodes, edges):
    lines = [
        'digraph G {',
        '  rankdir=LR;',
        '  graph [nodesep=0.12, ranksep=0.5, margin=0.05, overlap=false];',  # Remove splines=true to allow per-edge override
        '  node [shape=none, fontname="timesnewroman"];',
        '  edge [fontname="timesnewroman", arrowsize=0.6];'
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
            lines.append(f'  {sanitize_id(nid)} [label={node_label(nodes[nid])}];')

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
            
            # Link edges with polyline splines for sharp right-angle turns
            lines.append(f'  {src_id} -> {tgt_id} [style=dashed, constraint=false, splines=polyline, penwidth=1.5, color="blue"];')
        else:
            # Tree edges: use straight lines with splines=line for direct connections
            lines.append(f'  {src_id}:e -> {tgt_id}:w [style=solid, splines=line, penwidth=1.5, color="black"];')

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
    dot_lines.insert(4, f'  fontname="timesnewroman";')
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