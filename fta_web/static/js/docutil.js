/**
 * docutil.js -- two questions about the document the page holds, answered
 * without the server and without the DOM.
 *
 *   buildRescueDocument(state)   the document as the file Load reads
 *   rescueFilename(state, date)  a name for that file
 *   describeStep(before, after)  what an undo or a redo did, and which node
 *                                to select afterwards
 *
 * Pure functions on the `/api/state` shape (see store.js), so they can be
 * run under node by the tests (fta_web/tests/test_ux_batch_2.py) exactly as
 * the page runs them.
 *
 * WHY THE PAGE BUILDS A FILE ITSELF
 * ---------------------------------
 * Save writes through the server. When the server has been closed (the
 * terminal window shut, the machine put to sleep and the process killed) the
 * page still shows the tree and every edit since the last save, and there was
 * no way to get them out: each button answered "could not reach the server".
 * The page holds the whole document, so it can hand it to the browser as a
 * download. The shape is the one `FTACore.save_to_json` writes -- title, date,
 * mode, tree, analysis -- so the file opens with Load like any other.
 *
 * WHY UNDO IS DESCRIBED FROM A COMPARISON
 * ---------------------------------------
 * The server's undo stack holds snapshots, not labels, and a snapshot is
 * pushed from some twenty places in five route modules. Comparing the tree
 * before and after the step says the same thing for every one of them,
 * including edits made by the AI and by an import, and it cannot go out of
 * step with the code that made the edit.
 */

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function childrenOf(node) {
  // A hand-edited file can hold null among the children.
  return node && Array.isArray(node.children) ? node.children.filter(isObject) : [];
}

/* ------------------------------------------------------------- rescue copy -- */

/**
 * The document in `state` as the object Save writes to a file.
 * @returns {{title: string, date: string, mode: string, tree: object, analysis?: object}|null}
 *          null when the page holds no tree.
 */
export function buildRescueDocument(state) {
  if (!isObject(state) || !isObject(state.tree)) return null;
  const meta = isObject(state.metadata) ? state.metadata : {};
  const out = {
    title: meta.title == null ? '' : String(meta.title),
    date: meta.date == null ? '' : String(meta.date),
    mode: String(meta.mode || 'FTA').toUpperCase() === 'ETA' ? 'ETA' : 'FTA',
    // A copy through JSON: what is written is exactly what JSON can hold.
    tree: JSON.parse(JSON.stringify(state.tree)),
  };
  if (isObject(state.analysis)) out.analysis = JSON.parse(JSON.stringify(state.analysis));
  return out;
}

/**
 * The rescue copy as file text. Indented, as Save writes it: the loader
 * takes a file that ends in two closing braces on one line for an old
 * double-wrapped format and cannot read it (see routes/files.py).
 */
export function rescueText(state) {
  const doc = buildRescueDocument(state);
  return doc ? JSON.stringify(doc, null, 2) + '\n' : null;
}

function pad2(n) {
  return (n < 10 ? '0' : '') + n;
}

/** "<file or title>-rescue-20261012-0931.json". */
export function rescueFilename(state, when) {
  const date = when instanceof Date ? when : new Date();
  let stem = '';
  const current = isObject(state) && state.currentPath ? String(state.currentPath) : '';
  if (current) {
    const parts = current.split(/[\\/]/).filter(Boolean);
    const name = parts.length ? parts[parts.length - 1] : '';
    const dot = name.lastIndexOf('.');
    stem = dot > 0 ? name.slice(0, dot) : name;
  }
  if (!stem) {
    const meta = isObject(state) && isObject(state.metadata) ? state.metadata : {};
    stem = String(meta.title || '').trim();
  }
  // Characters Windows refuses in a file name are replaced, not dropped.
  stem = stem.replace(/[<>:"/\\|?*\x00-\x1f]/g, '_').replace(/\s+/g, ' ').trim().slice(0, 80);
  const stamp =
    date.getFullYear() + pad2(date.getMonth() + 1) + pad2(date.getDate()) +
    '-' + pad2(date.getHours()) + pad2(date.getMinutes());
  return (stem || 'fta_analysis') + '-rescue-' + stamp + '.json';
}

/* ---------------------------------------------------------- undo and redo -- */

/** Node keys that are not the node's own content. */
const NOT_OWN = new Set(['children', 'calculatedProbability']);

function indexTree(tree) {
  const map = new Map();
  const walk = (node, parentId, position) => {
    if (!isObject(node)) return;
    const id = String(node.id);
    // The first node with an id wins, as in the server's own lookups.
    if (!map.has(id)) map.set(id, { node, parentId, position });
    childrenOf(node).forEach((child, i) => walk(child, id, i));
  };
  walk(tree, null, 0);
  return map;
}

function nameOf(entry, id) {
  const name = entry && entry.node && entry.node.name;
  return name == null || name === '' ? String(id) : String(name);
}

/** The own keys of a node whose values differ between two versions of it. */
function changedFields(a, b) {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  const out = [];
  for (const key of keys) {
    if (NOT_OWN.has(key)) continue;
    if (JSON.stringify(a[key] === undefined ? null : a[key]) !== JSON.stringify(b[key] === undefined ? null : b[key])) {
      out.push(key);
    }
  }
  return out;
}

/** The ids of `ids` whose parent is not in `ids` too: the tops of what moved. */
function topmost(ids, index) {
  const set = new Set(ids);
  return ids.filter((id) => {
    const entry = index.get(id);
    return !entry || entry.parentId === null || !set.has(entry.parentId);
  });
}

/** Which child changed place, given the old and new order of the same ids. */
function movedWithin(before, after) {
  for (const id of after) {
    const a = before.filter((x) => x !== id);
    const b = after.filter((x) => x !== id);
    if (a.length === b.length && a.every((x, i) => x === b[i])) return id;
  }
  return after.find((id, i) => before[i] !== id) || null;
}

/**
 * What changed between two states of the document.
 *
 * @returns {{kind: string, names: string[], count: number, added: number,
 *            removed: number, fields: string[], parentName: string|null,
 *            selectId: string|null}}
 *
 * `kind` is one of
 *   'added'     nodes are in the tree that were not (count, names)
 *   'removed'   nodes are gone (count, names)
 *   'replaced'  both (added, removed): an AI rewrite or an import
 *   'moved'     one node has another parent or another place (names[0],
 *               parentName)
 *   'changed'   fields of existing nodes differ (count, names, fields)
 *   'metadata'  the title, date or mode (fields)
 *   'settings'  the analysis settings
 *   'none'      nothing this comparison can see
 *
 * `selectId` is the node to select afterwards: the node concerned when it
 * exists, the former parent of a node that is gone, null to leave the
 * selection alone.
 */
export function describeStep(before, after) {
  const out = {
    kind: 'none', names: [], count: 0, added: 0, removed: 0, fields: [], parentName: null, selectId: null,
  };
  const a = indexTree(isObject(before) ? before.tree : null);
  const b = indexTree(isObject(after) ? after.tree : null);

  const added = [...b.keys()].filter((id) => !a.has(id));
  const removed = [...a.keys()].filter((id) => !b.has(id));

  if (added.length && removed.length) {
    out.kind = 'replaced';
    out.added = added.length;
    out.removed = removed.length;
    out.selectId = topmost(added, b)[0] || null;
    return out;
  }
  if (added.length) {
    const tops = topmost(added, b);
    out.kind = 'added';
    out.count = added.length;
    out.added = added.length;
    out.names = tops.map((id) => nameOf(b.get(id), id));
    out.selectId = tops[0] || null;
    return out;
  }
  if (removed.length) {
    const tops = topmost(removed, a);
    out.kind = 'removed';
    out.count = removed.length;
    out.removed = removed.length;
    out.names = tops.map((id) => nameOf(a.get(id), id));
    // The former parent, if it is still there; else the nearest ancestor that is.
    let parent = tops.length ? a.get(tops[0]).parentId : null;
    while (parent !== null && !b.has(parent)) parent = a.get(parent) ? a.get(parent).parentId : null;
    out.selectId = parent;
    return out;
  }

  // The same nodes on both sides. A node under another parent has moved.
  const reparented = [...b.keys()].filter((id) => a.get(id).parentId !== b.get(id).parentId);
  if (reparented.length) {
    const id = topmost(reparented, b)[0] || reparented[0];
    out.kind = 'moved';
    out.count = 1;
    out.names = [nameOf(b.get(id), id)];
    const parentId = b.get(id).parentId;
    out.parentName = parentId === null ? null : nameOf(b.get(parentId), parentId);
    out.selectId = id;
    return out;
  }
  for (const [id, entry] of b) {
    const was = childrenOf(a.get(id).node).map((c) => String(c.id));
    const now = childrenOf(entry.node).map((c) => String(c.id));
    if (was.length !== now.length || was.every((x, i) => x === now[i])) continue;
    const moved = movedWithin(was, now);
    if (!moved) continue;
    out.kind = 'moved';
    out.count = 1;
    out.names = [nameOf(b.get(moved), moved)];
    out.parentName = nameOf(entry, id);
    out.selectId = moved;
    return out;
  }

  const changed = [];
  const fields = new Set();
  for (const [id, entry] of b) {
    const diff = changedFields(a.get(id).node, entry.node);
    if (!diff.length) continue;
    changed.push(id);
    diff.forEach((key) => fields.add(key));
  }
  if (changed.length) {
    out.kind = 'changed';
    out.count = changed.length;
    out.names = changed.map((id) => nameOf(b.get(id), id));
    out.fields = [...fields];
    out.selectId = changed[0];
    return out;
  }

  const metaA = isObject(before) && isObject(before.metadata) ? before.metadata : {};
  const metaB = isObject(after) && isObject(after.metadata) ? after.metadata : {};
  const metaFields = ['title', 'date', 'mode'].filter((key) => String(metaA[key] || '') !== String(metaB[key] || ''));
  if (metaFields.length) {
    out.kind = 'metadata';
    out.fields = metaFields;
    return out;
  }
  const analysisA = isObject(before) ? before.analysis : null;
  const analysisB = isObject(after) ? after.analysis : null;
  if (JSON.stringify(analysisA === undefined ? null : analysisA) !== JSON.stringify(analysisB === undefined ? null : analysisB)) {
    out.kind = 'settings';
  }
  return out;
}
