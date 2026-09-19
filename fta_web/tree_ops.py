"""
Pure tree manipulation helpers over an ``FTACore`` instance.

Everything here takes ``core`` as its first argument and touches nothing else:
no Flask, no AppState, no globals. That keeps the desktop-parity rules -- id
format, depth numbering, move legality -- testable without a request context
and without a Tk main loop.

These functions replace logic the desktop editor kept inside its Tkinter
widgets (``desktop/src/FTA_Editor_UI.py``), which read structure off the treeview
rather than off the data. The data is the source of truth here.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

ROOT_ID = "root"


def _children(node: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A node's children list, tolerating None/missing (as the core does)."""
    if not isinstance(node, dict):
        return []
    return node.get("children") or []


def top_level_id(core) -> Optional[str]:
    """The id of the loaded tree's top-level node, or None if there is no tree.

    Normally ``ROOT_ID``; read off the data rather than assumed, so guards
    that protect "the root" protect whatever node is actually on top.
    """
    data = core.get_data()
    if not isinstance(data, dict) or data.get("id") is None:
        return None
    return str(data.get("id"))


def all_ids(core) -> set:
    """Every node id in the tree, as strings."""
    ids: set = set()

    def walk(node: Dict[str, Any]) -> None:
        ids.add(str(node.get("id")))
        for child in _children(node):
            walk(child)

    data = core.get_data()
    if isinstance(data, dict):
        walk(data)
    return ids


def next_child_id(core, parent_id: str) -> str:
    """Generate the id for a new child of ``parent_id``.

    The starting point is the desktop editor's generator, ported from
    ``desktop/src/FTA_Editor_UI.py`` lines 1414-1424 (``add_node``) with the
    children read from the data structure instead of
    ``Treeview.get_children()``:

        scan the parent's existing children for ids shaped ``<parent_id>_<n>``,
        take the maximum ``n``, and return ``<parent_id>_{n+1}``

    So the first child of ``root`` is ``root_0``, and gaps among the current
    siblings are never reused: children ``root_0``/``root_5`` yield
    ``root_6``. Ids that do not start with ``<parent_id>_``, and ids whose
    trailing segment is not an integer, are ignored -- exactly as the
    ``int()``/``ValueError`` guard does upstream.

    Then, unlike the desktop editor, the candidate is stepped past any id that
    exists **anywhere** in the tree, not only among the siblings. The desktop
    editor only ever asks the treeview for direct children, so a child that
    was moved elsewhere (``root_1`` now living under ``root_0``) or a
    hand-edited file that reuses an id in another branch would make it mint a
    duplicate -- and a duplicate id is what its treeview crashes on and what
    turns a link into a pointer to the wrong node. Stepping past taken ids
    changes nothing for a tree the desktop editor built itself, because there
    every ``<parent_id>_<n>`` is a direct child of ``parent_id``.

    An id that has been *deleted* is not in the tree and so may be handed out
    again; that is safe only because ``routes/tree.py`` strips every link into
    a deleted subtree at delete time (see ``strip_links_to``).

    This is the same shape ``FTACore._normalize_node`` invents for an id-less
    node (``f"{parent_id}_{idx}"``), so ids generated here survive a
    save/load round-trip through either tool unchanged.

    An unknown ``parent_id`` has no children, so it yields ``<parent_id>_0``;
    callers that care validate the parent first.
    """
    parent_id = str(parent_id)
    prefix = f"{parent_id}_"
    max_index = -1

    for child in _children(core.find_node_by_id(parent_id)):
        child_id = str(child.get("id", ""))
        if child_id.startswith(prefix):
            try:
                index = int(child_id.split("_")[-1])
            except ValueError:
                continue
            max_index = max(max_index, index)

    taken = all_ids(core)
    index = max_index + 1
    while f"{parent_id}_{index}" in taken:
        index += 1
    return f"{parent_id}_{index}"


def subtree_ids(core, node_id: str) -> set:
    """``node_id`` plus every id below it, as strings. Empty if not found."""
    root = core.find_node_by_id(node_id)
    ids: set = set()

    def walk(node: Dict[str, Any]) -> None:
        ids.add(str(node.get("id")))
        for child in _children(node):
            walk(child)

    if isinstance(root, dict):
        walk(root)
    return ids


def strip_links_to(core, target_ids) -> List[Dict[str, Any]]:
    """Remove every link in the tree whose ``target_id`` is in ``target_ids``.

    Returns the removed links as ``[{"nodeId", "targetId", "relation"}, ...]``
    in pre-order of the node that held them, so the caller can report what
    changed. Links are edited in place on the live tree; call under the lock.
    """
    targets = {str(t) for t in target_ids}
    removed: List[Dict[str, Any]] = []

    def walk(node: Dict[str, Any]) -> None:
        links = node.get("links")
        if isinstance(links, list) and links:
            kept = []
            for link in links:
                target = link.get("target_id") if isinstance(link, dict) else None
                if target is not None and str(target) in targets:
                    removed.append(
                        {
                            "nodeId": str(node.get("id")),
                            "targetId": str(target),
                            "relation": (link.get("relation") or "OR").upper(),
                        }
                    )
                else:
                    kept.append(link)
            if len(kept) != len(links):
                node["links"] = kept
        for child in _children(node):
            walk(child)

    data = core.get_data()
    if isinstance(data, dict):
        walk(data)
    return removed


def depth_of(core, node_id: str) -> int:
    """Depth of a node below the root. Root is 0; -1 if the node is not found.

    Replaces ``desktop/src/FTA_Editor_UI.py`` lines 1613-1619 (``_get_depth``), which
    walked ``Treeview.parent()`` until it hit ``'root'``.

    The depth is **uncapped**. The desktop editor applies ``min(depth + 1, 3)``
    in two of its four tag-selection sites while defining 20 colour levels; the
    uncapped number is the useful one and the capping, if any, belongs in the
    renderer.
    """
    target = str(node_id)

    def walk(node: Dict[str, Any], depth: int) -> int:
        if str(node.get("id")) == target:
            return depth
        for child in _children(node):
            found = walk(child, depth + 1)
            if found != -1:
                return found
        return -1

    data = core.get_data()
    if not isinstance(data, dict):
        return -1
    return walk(data, 0)


def find_parent_id(core, node_id: str) -> Optional[str]:
    """Id of the node whose children contain ``node_id``.

    None for the root (it has no parent) and for an unknown id.
    """
    target = str(node_id)

    def walk(node: Dict[str, Any]) -> Optional[str]:
        for child in _children(node):
            if str(child.get("id")) == target:
                return str(node.get("id"))
            found = walk(child)
            if found is not None:
                return found
        return None

    data = core.get_data()
    if not isinstance(data, dict):
        return None
    return walk(data)


def _is_descendant_of(core, node_id: str, potential_ancestor_id: str) -> bool:
    """True if ``node_id`` sits anywhere in ``potential_ancestor_id``'s subtree.

    Same signature and recursion as
    ``AI_agent_handler.AIAgentHandler._is_descendant_of`` (vendored core, line
    833), reimplemented here only so tree_ops does not have to instantiate an
    AI handler to ask a structural question.
    """
    ancestor = core.find_node_by_id(potential_ancestor_id)
    if not ancestor:
        return False

    for child in _children(ancestor):
        if str(child.get("id")) == str(node_id):
            return True
        if _is_descendant_of(core, node_id, child.get("id")):
            return True

    return False


def would_create_cycle(core, node_id: str, new_parent_id: str) -> bool:
    """True if re-parenting ``node_id`` under ``new_parent_id`` would loop.

    Follows ``AIAgentHandler._would_create_circular_reference`` (vendored core,
    line 827) -- self-move first, then a descendant test -- with one deliberate
    correction. The vendored version asks
    ``_is_descendant_of(core, node_id, potential_parent_id)``: "is the node
    already inside the target's subtree". That is the wrong direction. It
    rejects legal promotions (moving a grandchild up under its grandparent, or
    re-ordering within its current parent) while letting the one genuinely
    corrupting move through: dropping a node inside its *own* subtree, which
    detaches that subtree from the tree and makes it self-referential.

    So the arguments are ordered the other way here -- is the **new parent** a
    descendant of the node being moved -- which is the check the vendored code
    was reaching for. The vendored file is left untouched; nothing in the web
    app calls its move path.

    Note this is about the ``children`` hierarchy only. Cycles through
    ``links`` are legal and stay legal: the probability engine's ``visiting``
    set already handles them, and rejecting them would refuse trees the desktop
    editor accepts.
    """
    node_id = str(node_id)
    new_parent_id = str(new_parent_id)

    if new_parent_id == node_id:
        return True
    if core.find_node_by_id(node_id) is None:
        return False
    return _is_descendant_of(core, new_parent_id, node_id)


def move_node(
    core,
    node_id: str,
    new_parent_id: str,
    index: Optional[int] = None,
) -> Tuple[bool, Optional[str]]:
    """Re-parent a node, preserving its subtree.

    Returns ``(True, None)`` or ``(False, reason)``. Rejects moving the root,
    an unknown node, a move to an unknown parent, and any move into the node's
    own descendant (or onto itself).

    ``index`` is the position in the new parent's children list *after* the
    node has been detached, so a same-parent move re-orders as a
    remove-then-insert. It is clamped to ``[0, len(children)]``; None appends,
    which is what the desktop editor's ``insert(parent, 'end', ...)`` does.
    """
    node_id = str(node_id)
    new_parent_id = str(new_parent_id)

    if node_id == ROOT_ID or node_id == top_level_id(core):
        return False, "The root node cannot be moved"

    node = core.find_node_by_id(node_id)
    if node is None:
        return False, f"Node '{node_id}' not found"

    if core.find_node_by_id(new_parent_id) is None:
        return False, f"New parent '{new_parent_id}' not found"

    if would_create_cycle(core, node_id, new_parent_id):
        return False, "Cannot move a node into itself or one of its descendants"

    # Detach. delete_node_from_data rebinds `children` on every node it walks,
    # so the new parent's list must be re-read afterwards, not cached.
    core.delete_node_from_data(node_id)

    new_parent = core.find_node_by_id(new_parent_id)
    if new_parent is None:  # pragma: no cover - guarded by the cycle check
        return False, f"New parent '{new_parent_id}' disappeared during move"

    siblings = new_parent.setdefault("children", [])
    if siblings is None:
        siblings = new_parent["children"] = []

    if index is None:
        siblings.append(node)
    else:
        position = max(0, min(int(index), len(siblings)))
        siblings.insert(position, node)

    return True, None


def collect_flat(core) -> List[Dict[str, Any]]:
    """Every node as ``{"id", "name", "depth"}`` in pre-order (parent, then
    children left to right) -- the order the desktop treeview displays."""
    flat: List[Dict[str, Any]] = []

    def walk(node: Dict[str, Any], depth: int) -> None:
        flat.append(
            {
                "id": str(node.get("id")),
                "name": node.get("name", ""),
                "depth": depth,
            }
        )
        for child in _children(node):
            walk(child, depth + 1)

    data = core.get_data()
    if isinstance(data, dict):
        walk(data, 0)
    return flat
