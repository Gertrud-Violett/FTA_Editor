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
 * P5 adds the editing surface on top of that: drag to re-parent, inline rename,
 * multi-select, and a search filter.
 *
 * WHAT CHANGED IN P5, AND WHY
 * ===========================
 * P1 said "the panel is a pure view over the store: it never calls the API".
 * That is no longer true and could not stay true: a rename, a re-parent and a
 * multi-node delete are edits, and routing them through another module would
 * mean inventing a second command bus for no gain. So this file now imports
 * api.js -- and every one of those calls goes through a normal mutating
 * endpoint, which means every one of them lands in the server's undo stack and
 * Ctrl+Z steps back through them like any other edit.
 *
 * DRAG, AND ITS KEYBOARD EQUIVALENT
 * ---------------------------------
 * Dragging a row onto another row re-parents it; dragging onto the top or
 * bottom quarter of a row drops it *between* siblings instead. The indicator
 * is live: an illegal drop (onto the dragged node itself, into its own
 * subtree, or beside the root, which has no parent to be a sibling in) paints
 * red and refuses the drop, during the drag rather than as an error afterwards.
 * The same cycle check the server runs (tree_ops.would_create_cycle) is
 * mirrored here so the refusal is instant and local; the server still runs it,
 * and its CYCLE_REJECTED is still surfaced if the two ever disagree.
 *
 * A drag-only re-parent would be unusable without a mouse, so the same four
 * moves are bound to Ctrl+Shift+arrows on the focused row -- the outline-editor
 * convention:
 *
 *   Ctrl+Shift+Up / Down    re-order among siblings
 *   Ctrl+Shift+Right        indent: become the last child of the sibling above
 *   Ctrl+Shift+Left         outdent: become the next sibling of the parent
 *
 * Each refusal says why (no sibling above, already directly under the root)
 * rather than doing nothing.
 *
 * SELECTION
 * ---------
 * The store holds one id -- the *lead* selection every other panel follows.
 * This panel holds the wider set, because nothing else needs it. Ctrl/Cmd-click
 * toggles, Shift-click takes the range over the *visible* order (the order rows
 * are painted in, which is what the user is pointing at), Ctrl+Space toggles
 * from the keyboard and Shift+Arrow extends. When another module moves the
 * store's selection -- details.js, an undo, a freshly added node -- the set
 * collapses back to that single node, because a multi-selection nobody else
 * knows about must not silently outlive the click that made it.
 *
 * SEARCH
 * ------
 * Typing filters to matching rows *plus their ancestors*, so a match is never
 * orphaned from its path; everything else is hidden. The expansion state in
 * force when the search started is snapshotted and restored when the box is
 * cleared, so filtering never costs the user the shape of the tree they had
 * arranged. The snapshot is deliberately not persisted while filtering, so a
 * reload mid-search comes back to the pre-search shape rather than to the
 * filter's scaffolding.
 *
 * EVERY STRING GOES THROUGH THE SHELL CATALOG
 * -------------------------------------------
 * `t()` below reaches window.ftaShell.t, i.e. main.js's STRINGS table. Nothing
 * in this file is written in English: Japanese lands next phase and has to be a
 * data change in that one table, not a hunt through the modules.
 */
import { store } from './store.js';
import { api } from './api.js';
import {
  DEPTH_LEVELS,
  clear,
  confirmDialog,
  el,
  ensureBaseStyles,
  injectStyles,
  sanitizeName,
  showError as dialogShowError,
  uid,
} from './dialogs.js';

const STORAGE_KEY = 'fta.tree.expanded.v1';
const MARK = '✖';

/** How long a drag has to hover a collapsed branch before it springs open. */
const HOVER_EXPAND_MS = 650;

/** Keystrokes are cheap; a filter pass over the whole tree is not. */
const SEARCH_DEBOUNCE_MS = 120;

/** Fraction of a row's height that counts as "between siblings" at each edge. */
const EDGE_ZONE = 0.28;

const TREE_CSS = `
/* The search highlight is the one colour this file owns rather than borrows.
   Declared at specificity 0 in all three theme states, exactly like the token
   sheet in dialogs.js, so theme.css can still override it. */
:where(:root) { --fta-tree-hit-bg: rgba(255, 214, 0, 0.55); }
@media (prefers-color-scheme: dark) {
  :where(:root:not([data-theme="light"]):not(.theme-light):not(.light)) {
    --fta-tree-hit-bg: rgba(255, 214, 0, 0.30);
  }
}
:where([data-theme="dark"], .theme-dark, html.dark, body.dark) {
  --fta-tree-hit-bg: rgba(255, 214, 0, 0.30);
}

/* #tree-root is itself a flex column (.panel__body--flush in app.css), so the
   panel claims the free space as a flex item; height:100% is the fallback for
   any container that is not one. */
.fta-tree-panel {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  height: 100%;
  min-height: 0;
}
.fta-tree-toolbar {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem;
  border-bottom: 1px solid var(--fta-border);
  background: var(--fta-surface);
}
.fta-tree-search {
  flex: 1 1 auto;
  min-width: 0;
  font: inherit;
  font-size: 0.85rem;
  padding: 0.2rem 0.4rem;
  color: var(--fta-fg);
  background: var(--fta-surface);
  border: 1px solid var(--fta-border);
  border-radius: var(--fta-radius);
}
.fta-tree-search:focus-visible {
  outline: 2px solid var(--fta-focus-ring);
  outline-offset: -1px;
}
.fta-tree-search-clear {
  flex: 0 0 auto;
  font: inherit;
  line-height: 1;
  padding: 0.2rem 0.45rem;
  cursor: pointer;
  color: var(--fta-muted-fg);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--fta-radius);
}
.fta-tree-search-clear:hover { color: var(--fta-fg); border-color: var(--fta-border); }
.fta-tree-status {
  flex: 0 0 auto;
  font-size: 0.72rem;
  color: var(--fta-muted-fg);
  white-space: nowrap;
}
.fta-tree-hint {
  margin: 0;
  padding: 0.25rem 0.45rem;
  font-size: 0.72rem;
  line-height: 1.35;
  color: var(--fta-muted-fg);
  border-bottom: 1px solid var(--fta-border);
  display: none;
}
/* The hint is a reminder, not decoration: it appears while the panel has focus
   and stays out of the way otherwise. aria-describedby points at it either way,
   so a screen reader hears it on the tree regardless of this rule. */
.fta-tree-panel:focus-within .fta-tree-hint { display: block; }

.fta-tree {
  overflow: auto;
  flex: 1 1 auto;
  min-height: 0;
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
/* The matched run inside a label. Colour is left to the row so a zero-probability
   or full-probability row keeps its own foreground; only the ground changes. */
.fta-tree-hit {
  color: inherit;
  background: var(--fta-tree-hit-bg, rgba(255, 214, 0, 0.55));
  border-radius: 2px;
}
.fta-tree-rename {
  flex: 1 1 auto;
  min-width: 4rem;
  font: inherit;
  color: var(--fta-fg);
  background: var(--fta-surface);
  border: 1px solid var(--fta-focus-ring);
  border-radius: 3px;
  padding: 0 0.2rem;
  -webkit-user-select: text;
  user-select: text;
}

.fta-tree-row:hover { box-shadow: inset 0 0 0 100vmax var(--fta-tree-hover-tint); }
.fta-tree-item[aria-selected="true"] > .fta-tree-row {
  box-shadow:
    inset 0 0 0 100vmax var(--fta-tree-selected-tint),
    inset 3px 0 0 0 var(--fta-tree-selected-outline);
  outline: 2px solid var(--fta-tree-selected-outline);
  outline-offset: -2px;
}
/* The lead row -- the one the store points at and the one Shift-click ranges
   from -- keeps a solid outline; the rest of a multi-selection is tinted only,
   so "which one is the anchor" stays readable. */
.fta-tree-item[aria-selected="true"]:not([data-lead="1"]) > .fta-tree-row {
  outline-style: dashed;
}
.fta-tree-item:focus { outline: none; }
.fta-tree-item:focus > .fta-tree-row {
  outline: 2px dashed var(--fta-focus-ring);
  outline-offset: -2px;
}

/* ---- drag and drop -----------------------------------------------------
   Declared after the selection rules and qualified with .is-dragging so the
   indicator always wins over a selected row's box-shadow while a drag is in
   flight, without reaching for !important. */
.fta-tree-item.is-drag-source > .fta-tree-row { opacity: 0.45; }
.fta-tree.is-dragging .fta-tree-item > .fta-tree-row.is-drop-into {
  outline: 2px solid var(--fta-accent);
  outline-offset: -2px;
  box-shadow: inset 0 0 0 100vmax var(--fta-tree-selected-tint);
}
.fta-tree.is-dragging .fta-tree-item > .fta-tree-row.is-drop-before {
  box-shadow: inset 0 3px 0 0 var(--fta-accent);
}
.fta-tree.is-dragging .fta-tree-item > .fta-tree-row.is-drop-after {
  box-shadow: inset 0 -3px 0 0 var(--fta-accent);
}
.fta-tree.is-dragging .fta-tree-item > .fta-tree-row.is-drop-bad.is-drop-into {
  outline-color: var(--fta-danger-fg);
  box-shadow: inset 0 0 0 100vmax var(--fta-danger-bg);
}
.fta-tree.is-dragging .fta-tree-item > .fta-tree-row.is-drop-bad.is-drop-before {
  box-shadow: inset 0 3px 0 0 var(--fta-danger-fg);
}
.fta-tree.is-dragging .fta-tree-item > .fta-tree-row.is-drop-bad.is-drop-after {
  box-shadow: inset 0 -3px 0 0 var(--fta-danger-fg);
}
`;

/* ------------------------------------------------------------ shell glue -- */

/**
 * Translate through main.js's STRINGS table. Never hardcode English here: a
 * literal in this file is invisible to the language switch, and a key with no
 * entry renders as "tree.something" on screen -- which is the failure this
 * indirection exists to make obvious rather than silent.
 */
function t(key, vars) {
  const shell = window.ftaShell;
  if (shell && typeof shell.t === 'function') {
    try {
      return shell.t(key, vars);
    } catch (_err) {
      /* fall through to the key, which is at least identifiable */
    }
  }
  return key;
}

/** A short confirmation or refusal. Goes to the shell's toast + status line. */
function say(message, kind) {
  const shell = window.ftaShell;
  if (shell && typeof shell.toast === 'function') {
    shell.toast(message, kind || 'info');
    return;
  }
  window.dispatchEvent(
    new CustomEvent('fta:toast', { detail: { message: message, kind: kind || 'info' } })
  );
}

/**
 * Surface a failure. ApiError.message is the server's own explanation and is
 * the only account the user gets, so it is never swallowed.
 */
function fail(err) {
  const shell = window.ftaShell;
  if (shell && typeof shell.showError === 'function') {
    shell.showError(err);
    return;
  }
  dialogShowError(err);
}

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

/** The root's id, or null when nothing is loaded. */
function rootId() {
  const root = treeRoot();
  return root ? String(root.id) : null;
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

/** The parent's id, or null for the root / an unknown node. */
function parentIdOf(nodeId) {
  try {
    return store.parentIdOf(String(nodeId));
  } catch (_err) {
    return null;
  }
}

/** The ids of a node's direct children, in order. */
function childIdsOf(nodeId) {
  if (nodeId === null || nodeId === undefined) return [];
  let kids = [];
  try {
    kids = store.childrenOf(String(nodeId)) || [];
  } catch (_err) {
    kids = [];
  }
  return kids.filter(Boolean).map((child) => String(child.id));
}

/** The node's display name, or its id when it has none. */
function nameOf(nodeId) {
  const node = store.findNode(String(nodeId));
  const name = node && node.name ? sanitizeName(node.name) : '';
  return name || String(nodeId);
}

/** Every id inside `nodeId`'s subtree, including `nodeId` itself. */
function subtreeIds(nodeId) {
  const out = new Set();
  const walk = (node) => {
    if (!node || typeof node !== 'object') return;
    out.add(String(node.id));
    const kids = Array.isArray(node.children) ? node.children : [];
    for (const child of kids) walk(child);
  };
  walk(store.findNode(String(nodeId)));
  return out;
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

  /* ---- chrome ---- */

  let panel = container.querySelector(':scope > .fta-tree-panel');
  if (panel) clear(panel);
  else {
    panel = el('div', { class: 'fta-tree-panel' });
    container.appendChild(panel);
  }

  const hintId = uid('fta-tree-hint');
  const search = el('input', {
    type: 'search',
    class: 'fta-tree-search',
    autocomplete: 'off',
    spellcheck: 'false',
  });
  const clearSearch = el('button', {
    type: 'button',
    class: 'fta-tree-search-clear',
    text: '×',
    hidden: true,
  });
  const status = el('span', { class: 'fta-tree-status', role: 'status', 'aria-live': 'polite' });
  const toolbar = el('div', { class: 'fta-tree-toolbar' }, [search, clearSearch, status]);
  const hint = el('p', { class: 'fta-tree-hint', id: hintId });
  const host = el('div', {
    class: 'fta-tree',
    role: 'tree',
    'aria-multiselectable': 'true',
    'aria-describedby': hintId,
  });
  panel.append(toolbar, hint, host);

  /** Re-read every string in the chrome. Called on boot and on a language flip. */
  function applyStrings() {
    host.setAttribute('aria-label', t('tree.ariaLabel'));
    search.setAttribute('aria-label', t('tree.searchLabel'));
    search.placeholder = t('tree.searchPlaceholder');
    clearSearch.setAttribute('aria-label', t('tree.searchClear'));
    clearSearch.title = t('tree.searchClear');
    hint.textContent = t('tree.hint');
  }
  applyStrings();

  /* ---- panel state ---- */

  let expanded = readExpanded();
  let seeded = expanded !== null;
  let lastSelected = null;
  // Ids that had children at the previous render. A node that becomes a branch
  // after the panel is up -- a child was just added to a leaf -- opens itself,
  // so the new node is visible without hunting for a twisty. Seeded silently on
  // the first render so a page reload never overrides a persisted collapse.
  let knownBranches = null;

  /** The wider selection. Always contains the store's lead id when there is one. */
  let selection = new Set();
  /** Where a Shift-click or Shift+Arrow range starts from. */
  let anchorId = null;

  /** {id, value, selStart, selEnd} while a row is being renamed, else null. */
  let editing = null;

  /** The active filter, '' when off, plus the expansion snapshot it displaced. */
  let query = '';
  let snapshot = null;

  /** {id, blocked:Set} while a row is being dragged, else null. */
  let dragging = null;
  /** {id, mode, valid} -- what the indicator is currently painting. */
  let dropAt = null;
  let hoverTimer = 0;
  let hoverId = null;

  let searchTimer = 0;
  let destroyed = false;

  function isExpanded(id) {
    return expanded ? expanded.has(String(id)) : true;
  }

  function setExpanded(id, open) {
    if (!expanded) expanded = new Set();
    if (open) expanded.add(String(id));
    else expanded.delete(String(id));
    // While a filter is on, the expansion set is scaffolding for the filter and
    // is thrown away when the box is cleared; persisting it would leak the
    // filter's shape into the next page load.
    if (!query) writeExpanded(expanded);
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

  /* ---- selection ---------------------------------------------------------
     store.selectedId is the lead every other panel follows; `selection` is the
     wider set only this panel knows about. Both are set together so they can
     never disagree. */

  function setSelection(ids, lead) {
    const next = new Set();
    for (const id of ids) if (id !== null && id !== undefined) next.add(String(id));
    const leadId = lead === null || lead === undefined ? null : String(lead);
    if (leadId) next.add(leadId);
    selection = next;
    if (leadId) anchorId = leadId;

    const before =
      store.selectedId === null || store.selectedId === undefined
        ? null
        : String(store.selectedId);
    if (leadId && leadId !== before) {
      // store.select notifies, which renders with the set already in place.
      select(leadId);
    } else {
      render();
    }
  }

  /** Ids between two rows in *visible* order -- what a Shift-click points at. */
  function rangeIds(fromId, toId) {
    const ids = itemNodes().map((item) => item.dataset.id);
    const a = ids.indexOf(String(fromId));
    const b = ids.indexOf(String(toId));
    if (a === -1 || b === -1) return [String(toId)];
    const lo = Math.min(a, b);
    const hi = Math.max(a, b);
    return ids.slice(lo, hi + 1);
  }

  function toggleSelected(id) {
    const key = String(id);
    const next = new Set(selection);
    if (next.has(key) && next.size > 1) {
      next.delete(key);
      // The lead has to stay inside the set, so hand it to a survivor.
      const survivor = key === String(store.selectedId) ? Array.from(next)[0] : store.selectedId;
      setSelection(next, survivor);
      anchorId = String(survivor);
      return;
    }
    next.add(key);
    setSelection(next, key);
  }

  /* ---- search ------------------------------------------------------------ */

  function matchesQuery(node, needle) {
    const name = String(node && node.name ? node.name : '').toLowerCase();
    if (name.indexOf(needle) !== -1) return true;
    // Ids are how the details panel and every error message name a node, so a
    // search that cannot find "root_0_2" would be missing the obvious case.
    return String(node && node.id ? node.id : '').toLowerCase().indexOf(needle) !== -1;
  }

  /**
   * Which rows survive the filter: every match, plus every ancestor of a match
   * so no hit is ever orphaned from its path back to the root.
   */
  function computeFilter(root) {
    if (!query || !root) return null;
    const needle = query.toLowerCase();
    const matches = new Set();
    const visible = new Set();

    const walk = (node, trail) => {
      if (!node || typeof node !== 'object') return;
      const id = String(node.id);
      const here = trail.concat(id);
      if (matchesQuery(node, needle)) {
        matches.add(id);
        for (const step of here) visible.add(step);
      }
      const kids = Array.isArray(node.children) ? node.children : [];
      for (const child of kids) walk(child, here);
    };
    walk(root, []);
    return { matches: matches, visible: visible };
  }

  function setQuery(raw) {
    const next = String(raw === null || raw === undefined ? '' : raw).trim();
    if (next === query) return;

    if (!query && next) {
      // Entering a filter: remember the shape of the tree so clearing can put
      // it back exactly, including collapses made minutes earlier.
      snapshot = { expanded: new Set(expanded || []), seeded: seeded };
    } else if (query && !next && snapshot) {
      expanded = new Set(snapshot.expanded);
      seeded = snapshot.seeded;
      snapshot = null;
      writeExpanded(expanded);
    }

    query = next;
    clearSearch.hidden = query === '';
    if (search.value.trim() !== query) search.value = query;
    render();
  }

  /* ---- rendering ---------------------------------------------------------- */

  /** The label, with the matched run wrapped so it can be highlighted. */
  function labelContent(name) {
    if (!query) return [name];
    const needle = query.toLowerCase();
    const hay = name.toLowerCase();
    const at = hay.indexOf(needle);
    if (at === -1 || !needle) return [name];
    return [
      name.slice(0, at),
      el('span', { class: 'fta-tree-hit', text: name.slice(at, at + needle.length) }),
      name.slice(at + needle.length),
    ];
  }

  function buildItem(node, depth, ctx) {
    const id = String(node.id);
    if (ctx.filter && !ctx.filter.visible.has(id)) return null;

    const level = ctx.depths.has(id) ? ctx.depths.get(id) : depth;
    let children = Array.isArray(node.children) ? node.children.filter(Boolean) : [];
    if (ctx.filter) children = children.filter((child) => ctx.filter.visible.has(String(child.id)));
    const hasChildren = children.length > 0;
    const open = hasChildren && isExpanded(id);
    const isZero = ctx.zeros.has(id);
    // `probability` is the *base* value; calculatedProbability is not consulted
    // here, exactly as in _apply_zero_marks.
    const isFull = Number(node.probability) === 1;
    const name = sanitizeName(node.name);
    const isSelected = selection.has(id);
    const isLead = id === ctx.selectedId;
    const isEditing = Boolean(editing && editing.id === id);

    const item = el('li', {
      class: 'fta-tree-item',
      role: 'treeitem',
      tabindex: '-1',
      draggable: isEditing || id === ctx.rootId ? 'false' : 'true',
      'aria-level': String(level + 1),
      'aria-selected': isSelected ? 'true' : 'false',
      'aria-label': name + (isZero ? t('tree.zeroAria') : ''),
      dataset: {
        id: id,
        depth: String(((level % DEPTH_LEVELS) + DEPTH_LEVELS) % DEPTH_LEVELS),
        lead: isLead ? '1' : '0',
      },
    });
    item.style.setProperty('--fta-level', String(Math.max(0, level)));
    if (hasChildren) item.setAttribute('aria-expanded', open ? 'true' : 'false');

    const rowClass = 'fta-tree-row' + (isFull ? ' is-full' : isZero ? ' is-zero' : '');
    const label = isEditing
      ? el('input', {
          type: 'text',
          class: 'fta-tree-rename',
          value: editing.value,
          'aria-label': t('tree.renameLabel', { name: name }),
          autocomplete: 'off',
          spellcheck: 'false',
        })
      : el('span', { class: 'fta-tree-label' }, labelContent(name));

    item.appendChild(
      el('div', { class: rowClass }, [
        el('span', {
          class: 'fta-tree-twisty',
          'aria-hidden': 'true',
          text: hasChildren ? (open ? '▾' : '▸') : '',
        }),
        label,
        el('span', {
          class: 'fta-tree-mark',
          'aria-hidden': 'true',
          title: isZero ? t('tree.zeroTitle') : null,
          text: isZero ? MARK : '',
        }),
      ])
    );

    if (open) {
      const group = el('ul', { role: 'group' });
      for (const child of children) {
        const built = buildItem(child, level + 1, ctx);
        if (built) group.appendChild(built);
      }
      item.appendChild(group);
    }
    return item;
  }

  function render() {
    if (destroyed) return;
    const root = treeRoot();
    const scrollTop = host.scrollTop;
    const active = document.activeElement;
    const focusedId =
      active && host.contains(active) && active.dataset ? active.dataset.id || null : null;

    // Capture the caret before the input is thrown away, so a re-render landing
    // mid-rename (a diagram refresh, another panel's update) does not move it.
    const liveInput = host.querySelector('.fta-tree-rename');
    if (editing && liveInput) {
      editing.value = liveInput.value;
      editing.selStart = liveInput.selectionStart;
      editing.selEnd = liveInput.selectionEnd;
    }

    clear(host);

    if (!root) {
      status.textContent = '';
      host.appendChild(el('p', { class: 'fta-tree-empty', text: t('tree.empty') }));
      return;
    }

    // A node that has gone away -- deleted here, or undone elsewhere -- must not
    // linger in the selection and re-appear the next time an id is reused.
    if (selection.size) {
      const alive = new Set();
      for (const id of selection) if (store.findNode(id)) alive.add(id);
      selection = alive;
    }
    const selectedId =
      store.selectedId === null || store.selectedId === undefined
        ? null
        : String(store.selectedId);
    if (selectedId) selection.add(selectedId);
    if (editing && !store.findNode(editing.id)) editing = null;

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
      if (changed && !query) writeExpanded(expanded);
    }
    knownBranches = branches;

    const filter = computeFilter(root);
    if (filter) {
      // Ancestors of a hit are force-opened so the hit is actually on screen.
      // Not persisted: setExpanded() skips the write while a filter is on, and
      // clearing the box restores the snapshot over all of it.
      if (!expanded) expanded = new Set();
      for (const id of filter.visible) if (!filter.matches.has(id)) expanded.add(id);
    }

    const ctx = {
      depths: depthMap(),
      zeros: zeroNodeSet(),
      selectedId: selectedId,
      rootId: String(root.id),
      filter: filter,
    };

    if (filter && !filter.matches.size) {
      // An empty list under a search box is a shrug. Say what happened.
      renderStatus(filter);
      host.appendChild(el('p', { class: 'fta-tree-empty', text: t('tree.searchNone', { q: query }) }));
      return;
    }

    const list = el('ul', { role: 'none' });
    const built = buildItem(root, 0, ctx);
    if (built) list.appendChild(built);
    host.appendChild(list);

    renderStatus(filter);

    // Roving tabindex: the lead row is the panel's single tab stop.
    const items = itemNodes();
    let stop = items.find((item) => item.dataset.lead === '1');
    if (!stop) stop = items[0];
    if (stop) stop.tabIndex = 0;

    host.scrollTop = scrollTop;

    if (editing) {
      const input = host.querySelector('.fta-tree-rename');
      if (input) {
        input.focus();
        const at = editing.selStart === undefined ? input.value.length : editing.selStart;
        const to = editing.selEnd === undefined ? input.value.length : editing.selEnd;
        try {
          input.setSelectionRange(at, to);
        } catch (_err) {
          /* a browser that refuses the range still has the text and the focus */
        }
        host.scrollTop = scrollTop;
      }
    } else if (focusedId) {
      const restored = itemById(focusedId) || stop;
      if (restored) {
        restored.tabIndex = 0;
        restored.focus({ preventScroll: true });
        host.scrollTop = scrollTop;
      }
    }

    // A drag survives a re-render (a spring-loaded branch opening under the
    // pointer is exactly that), so the indicator is repainted onto the new rows.
    host.classList.toggle('is-dragging', Boolean(dragging));
    if (dragging) {
      const source = itemById(dragging.id);
      if (source) source.classList.add('is-drag-source');
      paintDrop();
    }
  }

  /** The line beside the search box: match count, or how many rows are selected. */
  function renderStatus(filter) {
    if (filter) {
      // Announced through aria-live, so it carries the count even when the
      // panel below is showing the "nothing matches" message.
      status.textContent = t('tree.searchMatches', {
        n: filter.matches.size,
        total: store.flat().length,
      });
      return;
    }
    status.textContent = selection.size > 1 ? t('tree.selected', { n: selection.size }) : '';
  }

  function itemNodes() {
    return Array.from(host.querySelectorAll('.fta-tree-item'));
  }

  function itemById(id) {
    return host.querySelector('.fta-tree-item[data-id="' + String(id).replace(/"/g, '\\"') + '"]');
  }

  function rowOf(item) {
    return item ? item.querySelector(':scope > .fta-tree-row') : null;
  }

  function focusItem(item, alsoSelect) {
    if (!item) return;
    for (const other of itemNodes()) other.tabIndex = -1;
    item.tabIndex = 0;
    item.focus();
    if (alsoSelect) setSelection([item.dataset.id], item.dataset.id);
  }

  function focusById(id) {
    const item = itemById(id);
    if (item) focusItem(item, false);
  }

  /* ---- inline rename ------------------------------------------------------ */

  function startRename(id) {
    const node = store.findNode(String(id));
    if (!node) return;
    editing = { id: String(id), value: sanitizeName(node.name), selStart: 0, selEnd: undefined };
    render();
    const input = host.querySelector('.fta-tree-rename');
    if (input) input.select();
  }

  function cancelRename() {
    if (!editing) return;
    const id = editing.id;
    editing = null;
    render();
    focusById(id);
  }

  /**
   * Commit the editor's text.
   *
   * An empty name is refused *here*: PATCH /api/nodes/<id> runs the value
   * through the core's sanitize_name, which happily turns "   " into "", and a
   * nameless row is unusable -- it cannot be read in the tree, picked in a link
   * dropdown, or found by search. So the client does not send it.
   *
   * @param {boolean} keepOpen true from Enter (the user is still typing and can
   *   fix an empty name in place, and the focus belongs back on the row), false
   *   from a blur -- the editor is going away, an empty value silently reverts
   *   rather than trapping the focus, and the focus is left wherever the click
   *   that caused the blur put it.
   */
  async function commitRename(keepOpen) {
    if (!editing) return;
    const input = host.querySelector('.fta-tree-rename');
    const raw = input ? input.value : editing.value;
    const id = editing.id;
    const name = sanitizeName(raw);
    const node = store.findNode(id);

    if (!name) {
      say(t('tree.renameEmpty'), 'warn');
      if (keepOpen && input) {
        editing.value = raw;
        input.focus();
        return;
      }
      cancelRename();
      return;
    }

    editing = null;
    if (node && sanitizeName(node.name) === name) {
      // Nothing changed: sending it would cost an undo step for no edit.
      render();
      if (keepOpen) focusById(id);
      return;
    }

    try {
      const result = await api.patch('/nodes/' + encodeURIComponent(id), { name: name });
      store.applyMutation(result);
      say(t('tree.renamed', { name: name }), 'ok');
    } catch (err) {
      fail(err);
    }
    render();
    // Only Enter takes the focus back to the row. A blur means the user is
    // already somewhere else, and yanking the focus back after the round trip
    // would land in whatever they had just clicked on.
    if (keepOpen) focusById(id);
  }

  /* ---- moving ------------------------------------------------------------- */

  /**
   * The client-side mirror of tree_ops.would_create_cycle: a node may not land
   * inside its own subtree. Checked here so an illegal drop reads as illegal
   * *during* the drag; the server checks it again and its CYCLE_REJECTED is
   * surfaced verbatim if the two ever disagree.
   */
  function movable(nodeId, newParentId) {
    if (!nodeId || !newParentId) return false;
    if (String(nodeId) === String(newParentId)) return false;
    return !subtreeIds(nodeId).has(String(newParentId));
  }

  /**
   * POST the move. `index` is the position in the new parent's child list
   * *after* the node has been detached (tree_ops.move_node), which is what the
   * callers below compute; null appends.
   */
  async function requestMove(id, newParentId, index, sameParent) {
    if (!expanded) expanded = new Set();
    expanded.add(String(newParentId)); // land somewhere the user can see
    if (!query) writeExpanded(expanded);

    try {
      const result = await api.post('/nodes/' + encodeURIComponent(id) + '/move', {
        newParentId: String(newParentId),
        index: index === null || index === undefined ? null : index,
      });
      store.applyMutation(result);
      setSelection([id], id);
      say(
        sameParent
          ? t('tree.reordered', { name: nameOf(id), parent: nameOf(newParentId) })
          : t('tree.moved', { name: nameOf(id), parent: nameOf(newParentId) }),
        'ok'
      );
    } catch (err) {
      fail(err);
    }
    render();
    focusById(id);
  }

  /**
   * The keyboard equivalent of a drag: the outline-editor moves, on the focused
   * row. Every refusal explains itself instead of doing nothing.
   */
  function moveByKeyboard(id, direction) {
    const nodeId = String(id);
    if (!nodeId || nodeId === rootId()) {
      say(t('tree.moveRootRefused'), 'warn');
      return;
    }
    const parent = parentIdOf(nodeId);
    if (!parent) {
      say(t('tree.moveRootRefused'), 'warn');
      return;
    }
    const siblings = childIdsOf(parent);
    const at = siblings.indexOf(nodeId);

    if (direction === 'up' || direction === 'down') {
      const to = direction === 'up' ? at - 1 : at + 1;
      if (to < 0 || to >= siblings.length) {
        say(t('tree.moveNoRoom'), 'info');
        return;
      }
      // Post-detach indices: moving up inserts before the previous sibling
      // (at - 1); moving down inserts after the next one, which has shifted
      // into this node's old slot, so it is at + 1 either way.
      requestMove(nodeId, parent, to, true);
      return;
    }

    if (direction === 'in') {
      if (at <= 0) {
        say(t('tree.moveNoIndent'), 'info');
        return;
      }
      const newParent = siblings[at - 1];
      if (!movable(nodeId, newParent)) {
        say(t('tree.moveInvalid'), 'warn');
        return;
      }
      requestMove(nodeId, newParent, null, false);
      return;
    }

    // 'out': become the parent's next sibling.
    const grandparent = parentIdOf(parent);
    if (!grandparent) {
      say(t('tree.moveNoOutdent'), 'info');
      return;
    }
    const parentAt = childIdsOf(grandparent).indexOf(parent);
    requestMove(nodeId, grandparent, parentAt < 0 ? null : parentAt + 1, false);
  }

  /* ---- drag and drop ------------------------------------------------------ */

  function clearHoverTimer() {
    if (hoverTimer) window.clearTimeout(hoverTimer);
    hoverTimer = 0;
    hoverId = null;
  }

  function clearDropPaint() {
    for (const row of host.querySelectorAll('.fta-tree-row')) {
      row.classList.remove('is-drop-into', 'is-drop-before', 'is-drop-after', 'is-drop-bad');
    }
  }

  function paintDrop() {
    clearDropPaint();
    if (!dropAt) return;
    const row = rowOf(itemById(dropAt.id));
    if (!row) return;
    row.classList.add('is-drop-' + dropAt.mode);
    if (!dropAt.valid) row.classList.add('is-drop-bad');
  }

  function endDrag() {
    clearHoverTimer();
    clearDropPaint();
    dropAt = null;
    if (dragging) {
      const source = itemById(dragging.id);
      if (source) source.classList.remove('is-drag-source');
    }
    dragging = null;
    host.classList.remove('is-dragging');
  }

  /** Where in the row the pointer is: between siblings, or onto the node. */
  function dropModeFor(row, event) {
    const rect = row.getBoundingClientRect();
    const height = rect.height || 1;
    const offset = (event.clientY - rect.top) / height;
    if (offset < EDGE_ZONE) return 'before';
    if (offset > 1 - EDGE_ZONE) return 'after';
    return 'into';
  }

  /**
   * Is this drop legal? Answered locally so the indicator can say so during the
   * drag rather than the server saying so after it.
   */
  function dropIsValid(targetId, mode) {
    if (!dragging) return false;
    if (targetId === dragging.id) return false;
    // Between siblings means "into the target's parent". The root has none, so
    // there is no position beside it to drop into.
    const parent = mode === 'into' ? targetId : parentIdOf(targetId);
    if (!parent) return false;
    // `blocked` is the dragged subtree, cached at dragstart: dragover fires
    // continuously and re-walking the subtree on each one would be wasteful.
    return !dragging.blocked.has(String(parent));
  }

  /** The post-detach index a between-siblings drop resolves to. */
  function dropIndex(targetId, mode) {
    const parent = parentIdOf(targetId);
    const siblings = childIdsOf(parent);
    let insertAt = siblings.indexOf(targetId) + (mode === 'after' ? 1 : 0);
    const from = siblings.indexOf(dragging.id);
    // move_node detaches before it inserts, so every position after the node's
    // own slot shifts down by one.
    if (from !== -1 && from < insertAt) insertAt -= 1;
    return { parent: parent, index: insertAt, from: from };
  }

  host.addEventListener('dragstart', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const item = target.closest('.fta-tree-item');
    if (!item || !host.contains(item)) return;
    const id = item.dataset.id;
    if (editing || id === rootId()) {
      event.preventDefault();
      return;
    }
    dragging = { id: id, blocked: subtreeIds(id) };
    host.classList.add('is-dragging');
    item.classList.add('is-drag-source');
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move';
      // Firefox starts no drag at all without payload.
      try {
        event.dataTransfer.setData('text/plain', id);
      } catch (_err) {
        /* a browser that refuses the payload still fires the drag events */
      }
      const row = rowOf(item);
      if (row && typeof event.dataTransfer.setDragImage === 'function') {
        // Just the row: the default image would be the whole subtree.
        event.dataTransfer.setDragImage(row, 12, row.offsetHeight / 2);
      }
    }
  });

  host.addEventListener('dragover', (event) => {
    if (!dragging) return;
    const target = event.target;
    if (!(target instanceof Element)) return;
    const item = target.closest('.fta-tree-item');
    if (!item || !host.contains(item)) return;
    const row = rowOf(item);
    if (!row) return;

    const id = item.dataset.id;
    const mode = dropModeFor(row, event);
    const valid = dropIsValid(id, mode);

    if (valid) {
      // Only a legal drop gets preventDefault, so an illegal one shows the
      // browser's own "no drop" cursor and cannot be released at all.
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
    } else if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'none';
    }

    if (!dropAt || dropAt.id !== id || dropAt.mode !== mode || dropAt.valid !== valid) {
      dropAt = { id: id, mode: mode, valid: valid };
      paintDrop();
    }

    // Spring-loaded folders: hovering a collapsed branch opens it, so a drop
    // deep inside a closed subtree is reachable without letting go first.
    const canSpring = valid && mode === 'into' && item.getAttribute('aria-expanded') === 'false';
    if (!canSpring) {
      clearHoverTimer();
      return;
    }
    if (hoverId === id) return;
    clearHoverTimer();
    hoverId = id;
    hoverTimer = window.setTimeout(() => {
      hoverTimer = 0;
      if (dragging) setExpanded(id, true);
    }, HOVER_EXPAND_MS);
  });

  host.addEventListener('dragleave', (event) => {
    if (!dragging) return;
    const to = event.relatedTarget;
    if (to instanceof Node && host.contains(to)) return;
    clearHoverTimer();
    dropAt = null;
    clearDropPaint();
  });

  host.addEventListener('drop', (event) => {
    if (!dragging || !dropAt || !dropAt.valid) {
      endDrag();
      return;
    }
    event.preventDefault();
    const id = dragging.id;
    const target = dropAt.id;
    const mode = dropAt.mode;
    // Resolved before endDrag(), which clears the drag state these read.
    const wasParent = parentIdOf(id);
    const spot = mode === 'into' ? null : dropIndex(target, mode);
    endDrag();

    if (mode === 'into') {
      const siblings = childIdsOf(target);
      if (wasParent === target && siblings[siblings.length - 1] === id) return; // no-op
      requestMove(id, target, null, wasParent === target);
      return;
    }
    if (spot.from !== -1 && spot.from === spot.index) return; // dropped where it already is
    requestMove(id, spot.parent, spot.index, spot.from !== -1);
  });

  host.addEventListener('dragend', endDrag);

  /* ---- multi-node delete --------------------------------------------------
     Claimed from the shell through its cancelable `fta:action` event, so the
     button bar, Ctrl+D and the Delete key all end up here without this module
     having to re-implement any of them. */

  /**
   * What a delete of the current selection would actually remove: the root
   * filtered out (DELETE /api/nodes/root is a 400 ROOT_PROTECTED and refusing
   * it here is friendlier than showing the user that error), and any node whose
   * ancestor is also selected dropped, because deleting the ancestor takes the
   * whole subtree with it and the second request would 404.
   */
  function deletableSelection() {
    const root = rootId();
    const ids = Array.from(selection).filter((id) => id !== root && store.findNode(id));
    const chosen = new Set(ids);
    return ids.filter((id) => !ancestorsOf(id).some((parent) => chosen.has(parent)));
  }

  async function deleteMany(ids) {
    const parent = parentIdOf(ids[0]) || rootId();
    const only = ids.length === 1 ? nameOf(ids[0]) : null;
    const proceed = await confirmDialog(
      only ? t('confirm.delete', { name: only }) : t('tree.confirmDeleteMany', { n: ids.length }),
      { title: t('btn.delete'), confirmLabel: t('btn.delete') }
    );
    if (!proceed) return;

    // One request per node, because the API has no batch delete -- so this is
    // N undo steps, not one, and the message says so rather than letting the
    // user discover it at the third Ctrl+Z.
    let done = 0;
    for (const id of ids) {
      try {
        store.applyMutation(await api.del('/nodes/' + encodeURIComponent(id)));
        done += 1;
      } catch (err) {
        fail(err);
        break;
      }
    }
    selection = new Set();
    setSelection([parent], parent);
    if (done !== ids.length) say(t('tree.deletePartial', { done: done, total: ids.length }), 'warn');
    else if (only) say(t('msg.deleted', { name: only }), 'ok');
    else say(t('tree.deletedMany', { n: done }), 'ok');
  }

  function onAction(event) {
    const detail = (event && event.detail) || {};
    if (detail.action !== 'delete') return;
    // One selected node stays with the shell: it already confirms, reports and
    // re-selects, and two code paths for the same delete is one too many.
    if (selection.size <= 1) return;

    // A multi-selection is this panel's, even when it prunes down to a single
    // node -- otherwise a selection whose lead happens to be the root would be
    // refused wholesale by the shell's root guard with the rest still selected.
    event.preventDefault();
    const ids = deletableSelection();
    if (!ids.length) {
      say(t('tree.rootKept'), 'warn');
      return;
    }
    deleteMany(ids);
  }

  /* ---- interaction -------------------------------------------------------- */

  host.addEventListener('click', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (target.closest('.fta-tree-rename')) return;
    const item = target.closest('.fta-tree-item');
    if (!item || !host.contains(item)) return;
    if (target.closest('.fta-tree-twisty') && item.hasAttribute('aria-expanded')) {
      toggle(item.dataset.id);
      return;
    }
    const id = item.dataset.id;
    focusItem(item, false);

    if (event.ctrlKey || event.metaKey) {
      toggleSelected(id);
      return;
    }
    if (event.shiftKey) {
      setSelection(rangeIds(anchorId || store.selectedId || id, id), id);
      // The anchor stays put so a second Shift-click re-ranges from the same
      // place, which is what every list in every file manager does.
      anchorId = String(anchorId || store.selectedId || id);
      return;
    }
    setSelection([id], id);
  });

  host.addEventListener('dblclick', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (target.closest('.fta-tree-rename')) return;
    const item = target.closest('.fta-tree-item');
    if (!item || !host.contains(item)) return;
    // A double-click on the *label* renames; anywhere else on the row keeps its
    // P1 meaning of expand/collapse.
    if (target.closest('.fta-tree-label')) {
      event.preventDefault();
      startRename(item.dataset.id);
      return;
    }
    if (item.hasAttribute('aria-expanded')) toggle(item.dataset.id);
  });

  host.addEventListener('keydown', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;

    if (target.closest('.fta-tree-rename')) {
      if (event.key === 'Enter') {
        event.preventDefault();
        event.stopPropagation();
        commitRename(true);
      } else if (event.key === 'Escape') {
        // Stopped here so the shell's Escape handler does not also fire and
        // dismiss a toast the user was reading.
        event.preventDefault();
        event.stopPropagation();
        cancelRename();
      }
      return;
    }

    const item = target.closest('.fta-tree-item');
    if (!item) return;
    const items = itemNodes();
    const index = items.indexOf(item);
    const id = item.dataset.id;
    const expandedNow = item.getAttribute('aria-expanded');
    const ctrl = event.ctrlKey || event.metaKey;

    // The keyboard equivalent of a drag. Checked before the selection keys so
    // Ctrl+Shift+Arrow is a move, not a range extension.
    if (ctrl && event.shiftKey) {
      const moves = {
        ArrowUp: 'up',
        ArrowDown: 'down',
        ArrowRight: 'in',
        ArrowLeft: 'out',
      };
      const direction = moves[event.key];
      if (direction) {
        event.preventDefault();
        moveByKeyboard(id, direction);
        return;
      }
    }

    switch (event.key) {
      case 'F2':
        event.preventDefault();
        startRename(id);
        break;
      case 'ArrowDown':
      case 'ArrowUp': {
        event.preventDefault();
        const next =
          event.key === 'ArrowDown'
            ? items[Math.min(index + 1, items.length - 1)]
            : items[Math.max(index - 1, 0)];
        if (!next) break;
        if (event.shiftKey) {
          const from = anchorId || id;
          focusItem(next, false);
          setSelection(rangeIds(from, next.dataset.id), next.dataset.id);
          anchorId = String(from);
        } else if (ctrl) {
          focusItem(next, false); // move the focus, leave the selection alone
        } else {
          focusItem(next, true);
        }
        break;
      }
      case 'ArrowRight':
        event.preventDefault();
        if (expandedNow === 'false') toggle(id);
        else if (expandedNow === 'true') focusItem(items[index + 1], true);
        break;
      case 'ArrowLeft': {
        event.preventDefault();
        if (expandedNow === 'true') {
          toggle(id);
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
        event.preventDefault();
        setSelection([id], id);
        break;
      case ' ':
        event.preventDefault();
        if (ctrl) toggleSelected(id);
        else setSelection([id], id);
        break;
      default:
        break;
    }
  });

  host.addEventListener(
    'blur',
    (event) => {
      const target = event.target;
      if (!(target instanceof Element) || !target.classList.contains('fta-tree-rename')) return;
      // Clicking away commits, the way every other field in this app does --
      // except an empty name, which reverts rather than trapping the focus.
      if (editing) commitRename(false);
    },
    true
  );

  /* ---- search wiring ------------------------------------------------------ */

  search.addEventListener('input', () => {
    if (searchTimer) window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      searchTimer = 0;
      setQuery(search.value);
    }, SEARCH_DEBOUNCE_MS);
  });

  search.addEventListener('search', () => setQuery(search.value));

  search.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      if (search.value) {
        search.value = '';
        setQuery('');
      } else {
        const stop = itemNodes().find((item) => item.dataset.lead === '1') || itemNodes()[0];
        focusItem(stop, false);
      }
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'Enter') {
      // Straight from the box into the results, without reaching for the mouse.
      const first = itemNodes()[0];
      if (first) {
        event.preventDefault();
        focusItem(first, false);
      }
    }
  });

  clearSearch.addEventListener('click', () => {
    search.value = '';
    setQuery('');
    search.focus();
  });

  /** Ctrl+F, routed from the shell. */
  function onFind(event) {
    if (event && event.cancelable) event.preventDefault();
    search.focus();
    search.select();
  }

  function onLanguage() {
    applyStrings();
    render();
  }

  /* ---- store wiring ---- */

  const unsubscribe = store.subscribe(() => {
    const selectedId =
      store.selectedId === null || store.selectedId === undefined
        ? null
        : String(store.selectedId);
    if (selectedId && selectedId !== lastSelected) {
      // A selection made elsewhere -- details.js, an undo, a freshly added
      // child -- is a single-node selection: a wider one this panel never told
      // anybody about must not silently survive it.
      if (!selection.has(selectedId)) {
        selection = new Set([selectedId]);
        anchorId = selectedId;
      }
      // Reveal it.
      let changed = false;
      if (!expanded) expanded = new Set();
      for (const ancestor of ancestorsOf(selectedId)) {
        if (!expanded.has(ancestor)) {
          expanded.add(ancestor);
          changed = true;
        }
      }
      if (changed && !query) writeExpanded(expanded);
    }
    lastSelected = selectedId;
    render();
  });

  window.addEventListener('fta:action', onAction);
  window.addEventListener('fta:find', onFind);
  window.addEventListener('fta:language', onLanguage);

  render();

  return {
    refresh: render,
    destroy() {
      destroyed = true;
      if (typeof unsubscribe === 'function') unsubscribe();
      window.removeEventListener('fta:action', onAction);
      window.removeEventListener('fta:find', onFind);
      window.removeEventListener('fta:language', onLanguage);
      if (searchTimer) window.clearTimeout(searchTimer);
      clearHoverTimer();
      clear(panel);
      if (panel.parentNode === container) container.removeChild(panel);
    },
  };
}
