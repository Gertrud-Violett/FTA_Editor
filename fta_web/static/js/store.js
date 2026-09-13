/**
 * store.js -- the single client-side copy of the document, plus a subscription
 * list. No fetching, no DOM: modules read from here and re-render on notify.
 *
 * CONTRACT
 * ========
 *   store.state                last /api/state payload (ok-stripped) or null
 *   store.selectedId           string | null
 *   store.subscribe(fn)        fn(state); returns an unsubscribe function
 *   store.setState(payload)    replace the full state
 *   store.applyMutation(res)   merge a mutation response into the state
 *   store.select(id)
 *   store.findNode(id)         -> node object | null
 *   store.flat()               -> [{id, name, depth, node}] in pre-order
 *   store.parentOf(id)         -> the PARENT NODE OBJECT | null
 *
 * TWO THINGS WORTH READING TWICE
 * ------------------------------
 * 1. parentOf(id) returns the parent *node*, mirroring findNode(id). When an
 *    endpoint wants an id, pass `store.parentOf(id)?.id` -- or use the
 *    parentIdOf(id) convenience below.
 *
 * 2. subscribe(fn) invokes fn immediately with the current state when one is
 *    already loaded. That means a module can register and do its first render
 *    in one step, and it cannot miss the initial state by subscribing late.
 *    Subscribe after your container exists.
 *
 * State shape (from fta_web/state.py AppState.to_dict):
 *   tree, metadata {title, date, mode}, dirty, currentPath, nativeDot,
 *   aiConfigured, canUndo, canRedo, language, zeroNodes
 *
 * Node shape (from the vendored FTACore):
 *   {id, name, type, probability, calculatedProbability, logicGate, notes,
 *    links: [{target_id, relation}], children: []}
 */

export const ROOT_ID = 'root';

/**
 * Keys a mutating endpoint may return. Every mutating route in routes/tree.py
 * returns the first five; /metadata, /new, /undo and /redo also return
 * `metadata`, and /new returns `currentPath`. Merging the wider set keeps the
 * top bar honest after an undo without a second round trip.
 */
const MUTATION_KEYS = Object.freeze([
  'tree',
  'zeroNodes',
  'dirty',
  'canUndo',
  'canRedo',
  'metadata',
  'currentPath',
  'language',
  'nativeDot',
  'aiConfigured',
]);

const listeners = new Set();

function childrenOf(node) {
  return node && Array.isArray(node.children) ? node.children : [];
}

function walkFind(node, wanted) {
  if (!node || typeof node !== 'object') return null;
  if (String(node.id) === wanted) return node;
  for (const child of childrenOf(node)) {
    const hit = walkFind(child, wanted);
    if (hit) return hit;
  }
  return null;
}

/**
 * Report a listener that threw without letting it take the app down. A render
 * bug in one panel must not stop the others from updating; it is surfaced as a
 * visible error (main.js listens for fta:error), never swallowed.
 */
function reportListenerError(err) {
  // eslint-disable-next-line no-console
  console.error('[store] a subscriber threw during notify:', err);
  try {
    window.dispatchEvent(
      new CustomEvent('fta:error', {
        detail: {
          message: 'A panel failed to update: ' + (err && err.message ? err.message : err),
          code: 'RENDER_FAILED',
        },
      })
    );
  } catch (_err) {
    /* nothing further we can do */
  }
}

function notify() {
  for (const fn of Array.from(listeners)) {
    try {
      fn(store.state);
    } catch (err) {
      reportListenerError(err);
    }
  }
}

export const store = {
  /** @type {object|null} */
  state: null,

  /** @type {string|null} */
  selectedId: null,

  /**
   * @param {(state: object|null) => void} fn
   * @returns {() => void} unsubscribe
   */
  subscribe(fn) {
    if (typeof fn !== 'function') {
      throw new TypeError('store.subscribe expects a function');
    }
    listeners.add(fn);
    if (this.state !== null) {
      try {
        fn(this.state);
      } catch (err) {
        reportListenerError(err);
      }
    }
    return () => listeners.delete(fn);
  },

  /** Replace the whole state (the /api/state payload). */
  setState(payload) {
    this.state = payload && typeof payload === 'object' ? { ...payload } : null;
    this.reconcileSelection();
    notify();
    return this.state;
  },

  /**
   * Merge a mutation response. Only the keys the response actually carries are
   * touched, so a PATCH that returns no metadata cannot blank the top bar.
   */
  applyMutation(payload) {
    if (!payload || typeof payload !== 'object') return this.state;
    const next = { ...(this.state || {}) };
    for (const key of MUTATION_KEYS) {
      if (Object.prototype.hasOwnProperty.call(payload, key)) {
        next[key] = payload[key];
      }
    }
    this.state = next;
    this.reconcileSelection();
    notify();
    return this.state;
  },

  /** Select a node id (or null to clear). No-op when nothing changes. */
  select(id) {
    const next = id === null || id === undefined || id === '' ? null : String(id);
    if (next === this.selectedId) return this.selectedId;
    this.selectedId = next;
    notify();
    return this.selectedId;
  },

  /** The root of the loaded tree, or null. */
  tree() {
    return this.state && this.state.tree && typeof this.state.tree === 'object'
      ? this.state.tree
      : null;
  },

  /** Metadata, always an object so callers need no guard. */
  metadata() {
    const meta = this.state && this.state.metadata;
    return meta && typeof meta === 'object' ? meta : { title: '', date: '', mode: 'FTA' };
  },

  /** @returns {object|null} the node, by id. */
  findNode(id) {
    if (id === null || id === undefined || id === '') return null;
    return walkFind(this.tree(), String(id));
  },

  /** The currently selected node object, or null. */
  selectedNode() {
    return this.findNode(this.selectedId);
  },

  /** Pre-order flattening: parent, then children left to right. */
  flat() {
    const out = [];
    const walk = (node, depth) => {
      if (!node || typeof node !== 'object') return;
      out.push({ id: String(node.id), name: node.name == null ? '' : node.name, depth, node });
      for (const child of childrenOf(node)) walk(child, depth + 1);
    };
    walk(this.tree(), 0);
    return out;
  },

  /** @returns {object|null} the PARENT NODE of `id` (see the header note). */
  parentOf(id) {
    if (id === null || id === undefined || id === '') return null;
    const wanted = String(id);
    const walk = (node) => {
      for (const child of childrenOf(node)) {
        if (String(child.id) === wanted) return node;
        const hit = walk(child);
        if (hit) return hit;
      }
      return null;
    };
    const root = this.tree();
    if (!root || String(root.id) === wanted) return null;
    return walk(root);
  },

  /** Convenience for endpoints that want an id rather than a node. */
  parentIdOf(id) {
    const parent = this.parentOf(id);
    return parent ? String(parent.id) : null;
  },

  /** Direct children of `id`, as node objects. */
  childrenOf(id) {
    return childrenOf(this.findNode(id));
  },

  /** True when the server flagged this node as zero-probability. */
  isZero(id) {
    const zeros = this.state && Array.isArray(this.state.zeroNodes) ? this.state.zeroNodes : [];
    return zeros.map(String).includes(String(id));
  },

  /**
   * Keep selectedId pointing at a node that exists. After a delete or an undo
   * the previous selection can be gone; falling back to the root beats leaving
   * every panel rendering a node that is no longer in the tree.
   */
  reconcileSelection() {
    if (this.selectedId === null) return;
    if (this.findNode(this.selectedId)) return;
    const root = this.tree();
    this.selectedId = root ? String(root.id) : null;
  },

  /** Test/debug helper: drop every subscriber. */
  _resetListeners() {
    listeners.clear();
  },
};

export default store;
