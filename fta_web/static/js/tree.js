/**
 * tree.js -- the fault tree panel.
 *
 * Reproduces the desktop Treeview's visual language
 * (src/FTA_Editor_UI.py:165-196 and :1555-1587):
 *
 *   * eight cycling per-depth background colours, applied with the **uncapped**
 *     depth. The desktop defines 20 tag levels but then selects them with
 *     `min(depth, 3)` in two of its four code paths, so most of the palette was
 *     unreachable; here `depth % 8` is used everywhere.
 *   * a `✖` marker column for every node id in `state.zeroNodes`,
 *   * blue text for those zero-probability nodes,
 *   * bold red text for nodes whose *base* `probability` is exactly 1.0, which
 *     wins over the blue when a node is both (the desktop's if/elif order).
 *
 * P1 scope is render + select + expand/collapse. Inline rename, drag to
 * re-parent, multi-select and search belong to P5 and are deliberately absent.
 *
 * The panel is a pure view over the store: it never calls the API. Selecting
 * publishes through `store.select(id)` and every repaint is driven by a store
 * notification, so selection survives any re-render.
 */
import { store } from './store.js';
import { DEPTH_LEVELS, clear, el, ensureBaseStyles, injectStyles, sanitizeName } from './dialogs.js';

const STORAGE_KEY = 'fta.tree.expanded.v1';
const MARK = '✖';

const TREE_CSS = `
.fta-tree {
  overflow: auto;
  height: 100%;
  color: var(--fta-tree-fg);
  font-size: 0.9rem;
  line-height: 1.45;
}
.fta-tree ul { list-style: none; margin: 0; padding: 0; }
.fta-tree-empty {
  margin: 0;
  padding: 0.75rem;
  color: var(--fta-muted-fg);
  font-size: 0.875rem;
}
.fta-tree-row {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding-block: 0.15rem;
  padding-right: 0.35rem;
  padding-left: calc(0.35rem + var(--fta-level, 0) * var(--fta-tree-indent));
  background: var(--fta-tree-empty-bg);
  color: var(--fta-tree-fg);
  cursor: default;
  white-space: nowrap;
  -webkit-user-select: none;
  user-select: none;
}
.fta-tree-item[data-depth="0"] > .fta-tree-row { background: var(--fta-depth-0); }
.fta-tree-item[data-depth="1"] > .fta-tree-row { background: var(--fta-depth-1); }
.fta-tree-item[data-depth="2"] > .fta-tree-row { background: var(--fta-depth-2); }
.fta-tree-item[data-depth="3"] > .fta-tree-row { background: var(--fta-depth-3); }
.fta-tree-item[data-depth="4"] > .fta-tree-row { background: var(--fta-depth-4); }
.fta-tree-item[data-depth="5"] > .fta-tree-row { background: var(--fta-depth-5); }
.fta-tree-item[data-depth="6"] > .fta-tree-row { background: var(--fta-depth-6); }
.fta-tree-item[data-depth="7"] > .fta-tree-row { background: var(--fta-depth-7); }

/* Blue for zero probability, bold red for a base probability of exactly 1.0.
   Red is listed last on purpose: a node that is both is red, matching the
   desktop's "if is_full_prob ... elif is_zero" ordering. */
.fta-tree-row.is-zero { color: var(--fta-tree-zero-fg); }
.fta-tree-row.is-full {
  color: var(--fta-tree-full-fg);
  font-weight: var(--fta-tree-full-weight);
}

.fta-tree-twisty {
  flex: 0 0 1em;
  text-align: center;
  color: var(--fta-tree-twisty-fg);
  cursor: pointer;
  font-size: 0.8em;
}
.fta-tree-label { flex: 1 1 auto; overflow: hidden; text-overflow: ellipsis; }
.fta-tree-mark {
  flex: 0 0 var(--fta-tree-mark-width);
  text-align: center;
  color: var(--fta-tree-mark-fg);
}

.fta-tree-row:hover { box-shadow: inset 0 0 0 100vmax var(--fta-tree-hover-tint); }
.fta-tree-item[aria-selected="true"] > .fta-tree-row {
  box-shadow:
    inset 0 0 0 100vmax var(--fta-tree-selected-tint),
    inset 3px 0 0 0 var(--fta-tree-selected-outline);
  outline: 2px solid var(--fta-tree-selected-outline);
  outline-offset: -2px;
}
.fta-tree-item:focus { outline: none; }
.fta-tree-item:focus > .fta-tree-row {
  outline: 2px dashed var(--fta-focus-ring);
  outline-offset: -2px;
}
`;

/* --------------------------------------------------------------- store I/O -- */

/**
 * The root node. `store.state` mirrors the API payload, whose tree lives under
 * `tree`; a store that exposes the tree directly is tolerated too.
 */
function treeRoot() {
  const state = store.state;
  if (!state || typeof state !== 'object') return null;
  const tree = state.tree;
  if (tree && typeof tree === 'object' && tree.id !== undefined) return tree;
  if (state.id !== undefined) return state;
  return null;
}

/** Ids the engine reports as zero-probability, as a Set of strings. */
function zeroNodeSet() {
  const state = store.state;
  const raw = state && state.zeroNodes;
  return new Set(Array.isArray(raw) ? raw.map(String) : []);
}

/** id -> depth, from `store.flat()`. Falls back to the recursion depth. */
function depthMap() {
  const map = new Map();
  let flat = [];
  try {
    flat = store.flat() || [];
  } catch (err) {
    flat = [];
  }
  for (const entry of flat) {
    if (!entry || entry.id === undefined || entry.id === null) continue;
    if (typeof entry.depth === 'number') map.set(String(entry.id), entry.depth);
  }
  return map;
}

/** Parent ids from the node up to (and including) the root. */
function ancestorsOf(nodeId) {
  const chain = [];
  let current = String(nodeId);
  for (let guard = 0; guard < 1000; guard += 1) {
    let parent = null;
    try {
      parent = store.parentOf(current);
    } catch (err) {
      parent = null;
    }
    if (parent === null || parent === undefined) break;
    const parentId =
      typeof parent === 'object'
        ? parent.id === undefined || parent.id === null
          ? null
          : String(parent.id)
        : String(parent);
    if (!parentId || chain.indexOf(parentId) !== -1) break;
    chain.push(parentId);
    current = parentId;
  }
  return chain;
}

/* ------------------------------------------------------ expansion, persisted -- */

function readExpanded() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === null) return null;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return new Set(parsed.map(String));
  } catch (err) {
    /* private mode, quota, corrupt value: fall back to the default */
  }
  return null;
}

function writeExpanded(expanded) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(expanded)));
  } catch (err) {
    /* persistence is a convenience, never a correctness requirement */
  }
}

/** Every id that currently has at least one child. */
function branchIds(node, into) {
  const children = Array.isArray(node.children) ? node.children : [];
  if (children.length) into.add(String(node.id));
  for (const child of children) if (child) branchIds(child, into);
  return into;
}

/* ------------------------------------------------------------------ panel --- */

/**
 * Mount the tree panel inside `container`.
 *
 * Non-destructive: an existing heading in the container is left alone and the
 * panel is appended (or reused, if this is a re-init).
 */
export function initTree(container) {
  if (!container) throw new Error('initTree(container): container is required');
  ensureBaseStyles();
  injectStyles('fta-tree-css', TREE_CSS);

  let host = container.querySelector(':scope > .fta-tree');
  if (!host) {
    host = el('div', {
      class: 'fta-tree',
      role: 'tree',
      'aria-label': 'Fault tree',
    });
    container.appendChild(host);
  }

  let expanded = readExpanded();
  let seeded = expanded !== null;
  let lastSelected = null;
  // Ids that had children at the previous render. A node that becomes a branch
  // after the panel is up -- a child was just added to a leaf -- opens itself,
  // so the new node is visible without hunting for a twisty. Seeded silently on
  // the first render so a page reload never overrides a persisted collapse.
  let knownBranches = null;

  function isExpanded(id) {
    return expanded ? expanded.has(String(id)) : true;
  }

  function setExpanded(id, open) {
    if (!expanded) expanded = new Set();
    if (open) expanded.add(String(id));
    else expanded.delete(String(id));
    writeExpanded(expanded);
    render();
  }

  function toggle(id) {
    setExpanded(id, !isExpanded(id));
  }

  function select(id) {
    if (id === null || id === undefined) return;
    try {
      store.select(String(id));
    } catch (err) {
      /* a store that rejects the id simply leaves the selection alone */
    }
  }

  /* ---- rendering ---- */

  function buildItem(node, depth, depths, zeros, selectedId) {
    const id = String(node.id);
    const level = depths.has(id) ? depths.get(id) : depth;
    const children = Array.isArray(node.children) ? node.children.filter(Boolean) : [];
    const hasChildren = children.length > 0;
    const open = hasChildren && isExpanded(id);
    const isZero = zeros.has(id);
    // `probability` is the *base* value; calculatedProbability is not consulted
    // here, exactly as in _apply_zero_marks.
    const isFull = Number(node.probability) === 1;
    const name = sanitizeName(node.name);

    const item = el('li', {
      class: 'fta-tree-item',
      role: 'treeitem',
      tabindex: '-1',
      'aria-level': String(level + 1),
      'aria-selected': id === selectedId ? 'true' : 'false',
      'aria-label': name + (isZero ? ', zero probability' : ''),
      dataset: { id: id, depth: String(((level % DEPTH_LEVELS) + DEPTH_LEVELS) % DEPTH_LEVELS) },
    });
    item.style.setProperty('--fta-level', String(Math.max(0, level)));
    if (hasChildren) item.setAttribute('aria-expanded', open ? 'true' : 'false');

    const rowClass =
      'fta-tree-row' + (isFull ? ' is-full' : isZero ? ' is-zero' : '');
    item.appendChild(
      el('div', { class: rowClass }, [
        el('span', {
          class: 'fta-tree-twisty',
          'aria-hidden': 'true',
          text: hasChildren ? (open ? '▾' : '▸') : '',
        }),
        el('span', { class: 'fta-tree-label', text: name }),
        el('span', {
          class: 'fta-tree-mark',
          'aria-hidden': 'true',
          title: isZero ? 'Zero probability' : null,
          text: isZero ? MARK : '',
        }),
      ])
    );

    if (open) {
      const group = el('ul', { role: 'group' });
      for (const child of children) {
        group.appendChild(buildItem(child, level + 1, depths, zeros, selectedId));
      }
      item.appendChild(group);
    }
    return item;
  }

  function render() {
    const root = treeRoot();
    const scrollTop = host.scrollTop;
    const active = document.activeElement;
    const focusedId =
      active && host.contains(active) && active.dataset ? active.dataset.id || null : null;

    clear(host);

    if (!root) {
      host.appendChild(el('p', { class: 'fta-tree-empty', text: 'No analysis loaded.' }));
      return;
    }

    const branches = branchIds(root, new Set());
    if (!seeded) {
      // First run in this browser: start with every branch open rather than a
      // single collapsed root, then persist whatever the user does next.
      expanded = new Set(branches);
      seeded = true;
      writeExpanded(expanded);
    } else if (knownBranches) {
      let changed = false;
      for (const id of branches) {
        if (!knownBranches.has(id) && !expanded.has(id)) {
          expanded.add(id);
          changed = true;
        }
      }
      if (changed) writeExpanded(expanded);
    }
    knownBranches = branches;

    const depths = depthMap();
    const zeros = zeroNodeSet();
    const selectedId =
      store.selectedId === null || store.selectedId === undefined
        ? null
        : String(store.selectedId);

    const list = el('ul', { role: 'none' });
    list.appendChild(buildItem(root, 0, depths, zeros, selectedId));
    host.appendChild(list);

    // Roving tabindex: the selected row is the panel's single tab stop.
    const items = itemNodes();
    let stop = items.find((item) => item.getAttribute('aria-selected') === 'true');
    if (!stop) stop = items[0];
    if (stop) stop.tabIndex = 0;

    host.scrollTop = scrollTop;
    if (focusedId) {
      const restored = itemById(focusedId) || stop;
      if (restored) {
        restored.tabIndex = 0;
        restored.focus({ preventScroll: true });
        host.scrollTop = scrollTop;
      }
    }
  }

  function itemNodes() {
    return Array.from(host.querySelectorAll('.fta-tree-item'));
  }

  function itemById(id) {
    return host.querySelector('.fta-tree-item[data-id="' + String(id).replace(/"/g, '\\"') + '"]');
  }

  function focusItem(item, alsoSelect) {
    if (!item) return;
    for (const other of itemNodes()) other.tabIndex = -1;
    item.tabIndex = 0;
    item.focus();
    if (alsoSelect) select(item.dataset.id);
  }

  /* ---- interaction ---- */

  host.addEventListener('click', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const item = target.closest('.fta-tree-item');
    if (!item || !host.contains(item)) return;
    if (target.closest('.fta-tree-twisty') && item.hasAttribute('aria-expanded')) {
      toggle(item.dataset.id);
      return;
    }
    focusItem(item, false);
    select(item.dataset.id);
  });

  host.addEventListener('dblclick', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const item = target.closest('.fta-tree-item');
    if (item && host.contains(item) && item.hasAttribute('aria-expanded')) {
      toggle(item.dataset.id);
    }
  });

  host.addEventListener('keydown', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const item = target.closest('.fta-tree-item');
    if (!item) return;
    const items = itemNodes();
    const index = items.indexOf(item);
    const expandedNow = item.getAttribute('aria-expanded');

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        focusItem(items[Math.min(index + 1, items.length - 1)], true);
        break;
      case 'ArrowUp':
        event.preventDefault();
        focusItem(items[Math.max(index - 1, 0)], true);
        break;
      case 'ArrowRight':
        event.preventDefault();
        if (expandedNow === 'false') toggle(item.dataset.id);
        else if (expandedNow === 'true') focusItem(items[index + 1], true);
        break;
      case 'ArrowLeft': {
        event.preventDefault();
        if (expandedNow === 'true') {
          toggle(item.dataset.id);
          break;
        }
        const parent = item.parentElement ? item.parentElement.closest('.fta-tree-item') : null;
        if (parent) focusItem(parent, true);
        break;
      }
      case 'Home':
        event.preventDefault();
        focusItem(items[0], true);
        break;
      case 'End':
        event.preventDefault();
        focusItem(items[items.length - 1], true);
        break;
      case 'Enter':
      case ' ':
        event.preventDefault();
        select(item.dataset.id);
        break;
      default:
        break;
    }
  });

  /* ---- store wiring ---- */

  const unsubscribe = store.subscribe(() => {
    const selectedId =
      store.selectedId === null || store.selectedId === undefined
        ? null
        : String(store.selectedId);
    if (selectedId && selectedId !== lastSelected) {
      // Reveal a selection made elsewhere (a freshly added child, an undo).
      let changed = false;
      if (!expanded) expanded = new Set();
      for (const ancestor of ancestorsOf(selectedId)) {
        if (!expanded.has(ancestor)) {
          expanded.add(ancestor);
          changed = true;
        }
      }
      if (changed) writeExpanded(expanded);
    }
    lastSelected = selectedId;
    render();
  });

  render();

  return {
    refresh: render,
    destroy() {
      if (typeof unsubscribe === 'function') unsubscribe();
      clear(host);
      if (host.parentNode === container) container.removeChild(host);
    },
  };
}
