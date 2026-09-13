/**
 * dialogs.js -- the modal layer, the shared `--fta-*` design tokens, and the
 * links editor that both the add-node dialog and the details form use.
 *
 * Three responsibilities, in this order:
 *
 *   1. `injectStyles()` plus the token sheet. Every colour this phase paints
 *      with is a CSS custom property declared on `:where(:root)` (specificity
 *      0), so `theme.css` can override any of them from a plain `:root` rule
 *      regardless of load order. Nothing here writes a colour into an element's
 *      inline style.
 *   2. The modal primitives: `confirmDialog`, `openAddNodeDialog`. Escape
 *      cancels, Enter confirms, Tab is trapped inside the dialog and focus
 *      returns to whatever triggered it.
 *   3. `createLinksEditor`, a port of the desktop dialog's link UI
 *      (src/FTA_Editor_UI.py:1270-1365): a searchable list of every node, an
 *      AND list and an OR list, each with Add/Remove buttons, entries rendered
 *      as `Name (id)`.
 *
 * P1 owns exactly three files, so the handful of helpers the other two both
 * need -- `el`, `showError`, the field validators -- live here rather than in a
 * fourth module. tree.js and details.js import from this file; nothing here
 * imports from them.
 */
import { api, ApiError } from './api.js';

/* ------------------------------------------------------------------ DOM ---- */

let _uid = 0;
/** A DOM id that is unique within the document, for label/aria wiring. */
export function uid(prefix) {
  _uid += 1;
  return (prefix || 'fta') + '-' + _uid;
}

function append(parent, children) {
  if (children === null || children === undefined || children === false) return;
  if (Array.isArray(children)) {
    for (const child of children) append(parent, child);
    return;
  }
  parent.appendChild(
    children instanceof Node ? children : document.createTextNode(String(children))
  );
}

/**
 * Build an element. `text` sets textContent, `dataset` sets data attributes,
 * `onclick`-style keys attach listeners, everything else becomes an attribute.
 * Deliberately never touches innerHTML: node names and notes are user data.
 */
export function el(tag, attrs, children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const key of Object.keys(attrs)) {
      const value = attrs[key];
      if (value === null || value === undefined || value === false) continue;
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = String(value);
      else if (key === 'dataset') Object.assign(node.dataset, value);
      else if (key.slice(0, 2) === 'on' && typeof value === 'function') {
        node.addEventListener(key.slice(2).toLowerCase(), value);
      } else if (value === true) node.setAttribute(key, '');
      else node.setAttribute(key, String(value));
    }
  }
  append(node, children);
  return node;
}

/** Remove every child of `node`. */
export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

/**
 * Insert a stylesheet once per id. Prepended to <head> so a linked theme.css
 * wins on ties; the tokens are additionally declared at specificity 0.
 */
export function injectStyles(id, css) {
  if (typeof document === 'undefined' || !document.head) return;
  if (document.getElementById(id)) return;
  const style = el('style', { id: id, type: 'text/css', text: css });
  document.head.insertBefore(style, document.head.firstChild);
}

/* --------------------------------------------------------------- tokens ---- */

/**
 * Depth backgrounds, verbatim from the desktop editor
 * (src/FTA_Editor_UI.py:179). Eight colours, cycled by `depth % 8` with the
 * *uncapped* depth -- the desktop's `min(depth, 3)` is not reproduced.
 */
const DEPTH_LIGHT = [
  '#d0f0e0', '#ffe4b5', '#e6e6fa', '#c8d6e5',
  '#f5f5dc', '#e0ffff', '#ffe4e1', '#f0f8ff',
];

/** Dark-theme counterparts: same hues, dropped to a legible-under-light-text L. */
const DEPTH_DARK = [
  '#16342a', '#3b2c14', '#2b2740', '#1e2c3a',
  '#33301f', '#14313a', '#3a2325', '#1b2735',
];

/** The number of depth colours in the cycle; tree.js needs it for `% 8`. */
export const DEPTH_LEVELS = DEPTH_LIGHT.length;

function depthVars(colors) {
  return colors.map((c, i) => '  --fta-depth-' + i + ': ' + c + ';').join('\n');
}

const LIGHT_TOKENS = `
${depthVars(DEPTH_LIGHT)}
  --fta-fg: #14181c;
  --fta-muted-fg: #5b6670;
  --fta-surface: #ffffff;
  --fta-surface-2: #f4f6f8;
  --fta-border: #c9d1d9;
  --fta-accent: #1a73e8;
  --fta-accent-fg: #ffffff;
  --fta-focus-ring: #1a73e8;
  --fta-overlay: rgba(16, 20, 24, 0.45);
  --fta-shadow: 0 12px 32px rgba(16, 20, 24, 0.28);
  --fta-danger-fg: #8c1d18;
  --fta-danger-bg: #fdecea;
  --fta-danger-border: #f2b8b5;
  --fta-notice-fg: #0b3d2c;
  --fta-notice-bg: #e6f4ec;
  --fta-notice-border: #a8d5bd;
  --fta-tree-fg: #14181c;
  --fta-tree-zero-fg: #0000ff;
  --fta-tree-full-fg: #c62828;
  --fta-tree-selected-outline: #1a73e8;
  --fta-tree-selected-tint: rgba(26, 115, 232, 0.20);
  --fta-tree-hover-tint: rgba(16, 20, 24, 0.07);
  --fta-tree-twisty-fg: #3c4a54;
  --fta-tree-empty-bg: transparent;
`;

const DARK_TOKENS = `
${depthVars(DEPTH_DARK)}
  --fta-fg: #e6e9ec;
  --fta-muted-fg: #9aa5ae;
  --fta-surface: #1b1f23;
  --fta-surface-2: #23282d;
  --fta-border: #3a424a;
  --fta-accent: #8ab4f8;
  --fta-accent-fg: #10151a;
  --fta-focus-ring: #8ab4f8;
  --fta-overlay: rgba(0, 0, 0, 0.62);
  --fta-shadow: 0 12px 32px rgba(0, 0, 0, 0.55);
  --fta-danger-fg: #ffb4ab;
  --fta-danger-bg: #3b1f1d;
  --fta-danger-border: #6b3a36;
  --fta-notice-fg: #a8d5bd;
  --fta-notice-bg: #16302a;
  --fta-notice-border: #2f5c4c;
  --fta-tree-fg: #e6e9ec;
  --fta-tree-zero-fg: #8ab4f8;
  --fta-tree-full-fg: #ff8a80;
  --fta-tree-selected-outline: #8ab4f8;
  --fta-tree-selected-tint: rgba(138, 180, 248, 0.22);
  --fta-tree-hover-tint: rgba(255, 255, 255, 0.08);
  --fta-tree-twisty-fg: #b6c0c9;
  --fta-tree-empty-bg: transparent;
`;

/* Tokens that do not change between themes. */
const SHARED_TOKENS = `
  --fta-radius: 6px;
  --fta-tree-indent: 16px;
  --fta-tree-mark-width: 1.3em;
  --fta-tree-full-weight: 700;
  --fta-tree-mark-fg: currentColor;
`;

const TOKEN_CSS = `
:where(:root) {
${SHARED_TOKENS}${LIGHT_TOKENS}}

@media (prefers-color-scheme: dark) {
  :where(:root:not([data-theme="light"]):not(.theme-light):not(.light)) {
${DARK_TOKENS}  }
}

:where([data-theme="dark"], .theme-dark, html.dark, body.dark) {
${DARK_TOKENS}}
`;

/* ------------------------------------------------------------ chrome CSS ---- */

const CHROME_CSS = `
.fta-toasts {
  position: fixed;
  right: 1rem;
  bottom: 1rem;
  z-index: 10000;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-width: min(28rem, calc(100vw - 2rem));
}
.fta-toast {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.6rem 0.7rem;
  border: 1px solid var(--fta-danger-border);
  border-radius: var(--fta-radius);
  background: var(--fta-danger-bg);
  color: var(--fta-danger-fg);
  box-shadow: var(--fta-shadow);
  font-size: 0.875rem;
  line-height: 1.35;
}
.fta-toast.is-notice {
  border-color: var(--fta-notice-border);
  background: var(--fta-notice-bg);
  color: var(--fta-notice-fg);
}
.fta-toast-body { flex: 1 1 auto; overflow-wrap: anywhere; }
.fta-toast-code {
  display: block;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.75rem;
  opacity: 0.8;
}
.fta-toast-close {
  flex: 0 0 auto;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  padding: 0 0.15rem;
}

.fta-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 9000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background: var(--fta-overlay);
}
.fta-modal {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  width: min(46rem, 100%);
  max-height: calc(100vh - 2rem);
  padding: 1rem;
  border: 1px solid var(--fta-border);
  border-radius: var(--fta-radius);
  background: var(--fta-surface);
  color: var(--fta-fg);
  box-shadow: var(--fta-shadow);
}
.fta-modal.is-small { width: min(28rem, 100%); }
.fta-modal-title { margin: 0; font-size: 1.05rem; }
.fta-modal-body { overflow: auto; display: flex; flex-direction: column; gap: 0.6rem; }
.fta-modal-footer { display: flex; justify-content: flex-end; gap: 0.5rem; }
.fta-modal-message { margin: 0; line-height: 1.45; overflow-wrap: anywhere; }

.fta-btn {
  padding: 0.35rem 0.8rem;
  border: 1px solid var(--fta-border);
  border-radius: var(--fta-radius);
  background: var(--fta-surface-2);
  color: var(--fta-fg);
  font: inherit;
  cursor: pointer;
}
.fta-btn:hover { border-color: var(--fta-accent); }
.fta-btn.is-primary {
  background: var(--fta-accent);
  border-color: var(--fta-accent);
  color: var(--fta-accent-fg);
}
.fta-btn.is-tiny { padding: 0.15rem 0.45rem; font-size: 0.8rem; }
.fta-btn:focus-visible,
.fta-field input:focus-visible,
.fta-field select:focus-visible,
.fta-field textarea:focus-visible,
.fta-links select:focus-visible,
.fta-links input:focus-visible {
  outline: 2px solid var(--fta-focus-ring);
  outline-offset: 1px;
}

.fta-field { display: flex; flex-direction: column; gap: 0.2rem; }
.fta-field > label { font-size: 0.8rem; color: var(--fta-muted-fg); }
.fta-field input,
.fta-field select,
.fta-field textarea {
  padding: 0.3rem 0.4rem;
  border: 1px solid var(--fta-border);
  border-radius: var(--fta-radius);
  background: var(--fta-surface);
  color: var(--fta-fg);
  font: inherit;
}
.fta-field textarea { min-height: 5rem; resize: vertical; }
.fta-field-error {
  margin: 0;
  font-size: 0.78rem;
  color: var(--fta-danger-fg);
}
.fta-field-error[hidden] { display: none; }
.fta-field input[aria-invalid="true"],
.fta-field select[aria-invalid="true"],
.fta-field textarea[aria-invalid="true"] { border-color: var(--fta-danger-border); }
.fta-row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }

.fta-links { display: flex; flex-direction: column; gap: 0.5rem; }
.fta-links fieldset {
  margin: 0;
  padding: 0.5rem;
  border: 1px solid var(--fta-border);
  border-radius: var(--fta-radius);
}
.fta-links legend { padding: 0 0.3rem; font-size: 0.8rem; color: var(--fta-muted-fg); }
.fta-links select,
.fta-links input {
  width: 100%;
  padding: 0.25rem;
  border: 1px solid var(--fta-border);
  border-radius: var(--fta-radius);
  background: var(--fta-surface);
  color: var(--fta-fg);
  font: inherit;
  font-size: 0.85rem;
}
.fta-links-picker { display: flex; gap: 0.5rem; align-items: flex-start; }
.fta-links-picker > select { flex: 1 1 auto; min-width: 0; }
.fta-links-buttons { display: flex; flex-direction: column; gap: 0.3rem; flex: 0 0 auto; }
.fta-links-status {
  margin: 0;
  min-height: 1.1em;
  font-size: 0.78rem;
  color: var(--fta-muted-fg);
}
.fta-links-status.is-error { color: var(--fta-danger-fg); }
`;

/** Install the tokens and the modal/form chrome. Idempotent. */
export function ensureBaseStyles() {
  injectStyles('fta-tokens', TOKEN_CSS);
  injectStyles('fta-chrome', CHROME_CSS);
}
ensureBaseStyles();

/* ---------------------------------------------------------------- errors ---- */

/** True for anything shaped like the api.js ApiError. */
export function isApiError(err) {
  if (typeof ApiError === 'function' && err instanceof ApiError) return true;
  return !!err && typeof err.code === 'string' && typeof err.message === 'string';
}

/** The most useful human-readable string available for a thrown value. */
export function errorMessage(err, fallback) {
  if (isApiError(err)) return err.message;
  if (err && typeof err.message === 'string' && err.message) return err.message;
  if (typeof err === 'string' && err) return err;
  return fallback || 'Something went wrong.';
}

/** The stable error code, when there is one (`INVALID_FIELD`, ...). */
export function errorCode(err) {
  return isApiError(err) ? err.code : null;
}

/**
 * The field an INVALID_FIELD error blames, if the server named one.
 * `detail` carries `{field: "probability"}` / `{field: "links", index: 2}`.
 */
export function errorField(err) {
  const detail = err && err.detail;
  if (detail && typeof detail.field === 'string') return detail.field;
  return null;
}

function toastHost() {
  let host = document.querySelector('.fta-toasts');
  if (!host) {
    host = el('div', { class: 'fta-toasts' });
    document.body.appendChild(host);
  }
  return host;
}

function toast(message, kind, code, timeout) {
  ensureBaseStyles();
  if (typeof document === 'undefined' || !document.body) return;
  const host = toastHost();
  const close = el('button', {
    type: 'button',
    class: 'fta-toast-close',
    'aria-label': 'Dismiss',
    text: '×',
  });
  const box = el(
    'div',
    { class: 'fta-toast' + (kind === 'notice' ? ' is-notice' : ''), role: 'alert' },
    [
      el('div', { class: 'fta-toast-body' }, [
        el('span', { text: message }),
        code ? el('span', { class: 'fta-toast-code', text: code }) : null,
      ]),
      close,
    ]
  );
  const remove = () => {
    if (box.parentNode) box.parentNode.removeChild(box);
  };
  close.addEventListener('click', remove);
  host.appendChild(box);
  if (timeout) setTimeout(remove, timeout);
}

/**
 * Surface a failure. Never swallow an ApiError: the message the server wrote
 * is the only explanation the user gets.
 */
export function showError(err, fallback) {
  toast(errorMessage(err, fallback), 'error', errorCode(err), 0);
}

/** Transient confirmation, e.g. "Added 2 AND link(s)". */
export function showNotice(message) {
  toast(message, 'notice', null, 4000);
}

/* ------------------------------------------------------------- validation ---- */

export const GATES = ['AND', 'OR'];

/**
 * Normalise a stored gate for display. Empty/missing means OR, matching
 * `FTACore._normalize_node` and `routes/tree.py::_validate_gate`.
 */
export function normalizeGate(value) {
  const gate = String(value === null || value === undefined ? '' : value)
    .trim()
    .toUpperCase();
  return gate === '' ? 'OR' : gate;
}

/**
 * Validate a gate the way the server does. NOT is refused rather than accepted
 * and quietly scored as OR -- divergence D5, fta_web/core/DIVERGENCE.md.
 */
export function validateGate(value) {
  const gate = normalizeGate(value);
  if (gate === 'NOT') {
    return {
      ok: false,
      message:
        'NOT gates are not supported: the probability engine has no NOT ' +
        'semantics and would score the node as OR. Use AND or OR.',
    };
  }
  if (GATES.indexOf(gate) === -1) {
    return { ok: false, message: "Logic gate must be 'AND' or 'OR'." };
  }
  return { ok: true, value: gate };
}

const PROBABILITY_MESSAGE = 'Probability must be a number between 0.0 and 1.0.';

/** Mirror of `routes/tree.py::_validate_probability`. */
export function parseProbability(raw) {
  const text = String(raw === null || raw === undefined ? '' : raw).trim();
  if (text === '') return { ok: false, message: PROBABILITY_MESSAGE };
  const value = Number(text);
  if (!Number.isFinite(value)) return { ok: false, message: PROBABILITY_MESSAGE };
  if (value < 0 || value > 1) return { ok: false, message: PROBABILITY_MESSAGE };
  return { ok: true, value: value };
}

/** Trim to the shape `sanitize_name` produces, so the field shows what will be stored. */
export function sanitizeName(value) {
  return String(value === null || value === undefined ? '' : value)
    .replace(/\s+/g, ' ')
    .trim();
}

/** Round for display the way the engine rounds internally (6 decimals). */
export function formatProbability(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return String(Math.round(number * 1e6) / 1e6);
}

/** `Name (id)`, exactly as the desktop dialog renders a link target. */
export function linkLabel(id, name) {
  const key = String(id);
  return (name === null || name === undefined || name === '' ? key : name) + ' (' + key + ')';
}

/* ------------------------------------------------------------- node list ---- */

function nodesFrom(payload) {
  if (Array.isArray(payload)) return payload;
  if (payload && Array.isArray(payload.nodes)) return payload.nodes;
  return [];
}

/**
 * Every node, flat and in pre-order, from `GET /api/nodes`
 * ({"nodes": [{"id", "name", "depth"}, ...]}).
 */
export async function fetchNodeList() {
  return nodesFrom(await api.get('/nodes'));
}

/* ----------------------------------------------------------- links editor ---- */

/**
 * The desktop's link UI (src/FTA_Editor_UI.py:1270-1365) as a DOM component.
 *
 * options:
 *   selfId   -- node id that may not be linked to (null while adding)
 *   links    -- initial [{target_id, relation}]
 *   onChange -- called with the new array after every add/remove; may return a
 *               promise, and may reject to have the change rolled back
 */
export function createLinksEditor(options) {
  ensureBaseStyles();
  const opts = options || {};
  let selfId = opts.selfId === undefined || opts.selfId === null ? null : String(opts.selfId);
  let links = normaliseLinks(opts.links);
  let choices = [];
  const nameById = new Map();

  const searchId = uid('fta-link-search');
  const search = el('input', { type: 'search', id: searchId, placeholder: 'Filter by name or id' });
  const matches = el('select', {
    multiple: true,
    size: '8',
    'aria-label': 'Matching events',
  });
  const status = el('p', { class: 'fta-links-status', role: 'status' });

  const sections = {};
  for (const relation of GATES) {
    const list = el('select', { multiple: true, size: '5', 'aria-label': relation + ' links' });
    const addBtn = el('button', {
      type: 'button',
      class: 'fta-btn is-tiny',
      text: 'Add →',
      title: 'Add the selected events as ' + relation + ' links',
    });
    const removeBtn = el('button', {
      type: 'button',
      class: 'fta-btn is-tiny',
      text: '← Remove',
      title: 'Remove the selected ' + relation + ' links',
    });
    addBtn.addEventListener('click', () => addSelected(relation));
    removeBtn.addEventListener('click', () => removeSelected(relation));
    sections[relation] = { list: list, node: null };
    sections[relation].node = el('fieldset', {}, [
      el('legend', { text: relation + ' Links' }),
      el('div', { class: 'fta-links-picker' }, [
        list,
        el('div', { class: 'fta-links-buttons' }, [addBtn, removeBtn]),
      ]),
    ]);
  }

  const element = el('div', { class: 'fta-links' }, [
    el('div', { class: 'fta-field' }, [
      el('label', { for: searchId, text: 'Search Events' }),
      search,
    ]),
    matches,
    status,
    sections.AND.node,
    sections.OR.node,
  ]);

  search.addEventListener('input', renderMatches);
  // Enter in the search box must not submit or confirm the surrounding dialog.
  search.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') event.preventDefault();
  });

  function normaliseLinks(raw) {
    if (!Array.isArray(raw)) return [];
    const out = [];
    for (const link of raw) {
      if (!link) continue;
      const target = link.target_id !== undefined ? link.target_id : link.targetId;
      if (target === undefined || target === null || String(target) === '') continue;
      const relation = normalizeGate(link.relation);
      out.push({
        target_id: String(target),
        relation: GATES.indexOf(relation) === -1 ? 'OR' : relation,
      });
    }
    return out;
  }

  function setStatus(message, isError) {
    status.textContent = message || '';
    status.classList.toggle('is-error', !!isError);
  }

  function renderMatches() {
    const query = search.value.trim().toLowerCase();
    clear(matches);
    for (const choice of choices) {
      const id = String(choice.id);
      const label = linkLabel(id, choice.name);
      if (query && label.toLowerCase().indexOf(query) === -1) continue;
      matches.appendChild(el('option', { value: id, text: label }));
    }
    if (!matches.options.length) {
      matches.appendChild(el('option', { value: '', disabled: true, text: 'No matching events' }));
    }
  }

  function renderLists() {
    for (const relation of GATES) {
      const list = sections[relation].list;
      clear(list);
      for (const link of links) {
        if (link.relation !== relation) continue;
        list.appendChild(
          el('option', {
            value: link.target_id,
            text: linkLabel(link.target_id, nameById.get(link.target_id)),
          })
        );
      }
    }
  }

  function selectedValues(select) {
    const values = [];
    for (const option of Array.from(select.selectedOptions || [])) {
      if (option.value) values.push(option.value);
    }
    return values;
  }

  async function commit(previous, message) {
    renderLists();
    if (typeof opts.onChange !== 'function') {
      setStatus(message, false);
      return;
    }
    try {
      await opts.onChange(getLinks());
      setStatus(message, false);
    } catch (err) {
      links = previous;
      renderLists();
      setStatus(errorMessage(err, 'Could not save the links.'), true);
    }
  }

  function addSelected(relation) {
    const previous = links.map((link) => ({ ...link }));
    let added = 0;
    let skippedSelf = 0;
    let skippedDuplicate = 0;
    for (const targetId of selectedValues(matches)) {
      if (selfId !== null && targetId === selfId) {
        skippedSelf += 1;
        continue;
      }
      const exists = links.some(
        (link) => link.target_id === targetId && link.relation === relation
      );
      if (exists) {
        skippedDuplicate += 1;
        continue;
      }
      links.push({ target_id: targetId, relation: relation });
      added += 1;
    }
    matches.selectedIndex = -1;

    if (!added) {
      const why = skippedSelf
        ? 'A node cannot link to itself.'
        : skippedDuplicate
          ? 'Already linked with that relation.'
          : 'Select one or more events above first.';
      renderLists();
      setStatus(why, true);
      return;
    }
    let message = 'Added ' + added + ' ' + relation + ' link(s).';
    if (skippedSelf) message += ' Skipped the node itself.';
    if (skippedDuplicate) message += ' Skipped ' + skippedDuplicate + ' already linked.';
    commit(previous, message);
  }

  function removeSelected(relation) {
    const list = sections[relation].list;
    const targets = selectedValues(list);
    if (!targets.length) {
      setStatus('Select one or more ' + relation + ' links to remove.', true);
      return;
    }
    const previous = links.map((link) => ({ ...link }));
    links = links.filter(
      (link) => !(link.relation === relation && targets.indexOf(link.target_id) !== -1)
    );
    commit(previous, 'Removed ' + targets.length + ' ' + relation + ' link(s).');
  }

  /** (Re)load the node list from the API. Failures are reported inline. */
  async function reload() {
    try {
      choices = await fetchNodeList();
      nameById.clear();
      for (const choice of choices) nameById.set(String(choice.id), choice.name);
      renderMatches();
      renderLists();
      setStatus('', false);
    } catch (err) {
      setStatus(errorMessage(err, 'Could not load the node list.'), true);
      showError(err, 'Could not load the node list.');
    }
  }

  function getLinks() {
    return links.map((link) => ({ target_id: link.target_id, relation: link.relation }));
  }

  function setLinks(raw) {
    links = normaliseLinks(raw);
    renderLists();
  }

  function setSelfId(id) {
    selfId = id === undefined || id === null ? null : String(id);
  }

  renderMatches();
  renderLists();

  return {
    element: element,
    reload: reload,
    getLinks: getLinks,
    setLinks: setLinks,
    setSelfId: setSelfId,
    setStatus: setStatus,
  };
}

/* ------------------------------------------------------------------ modal ---- */

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

function focusableIn(root) {
  return Array.from(root.querySelectorAll(FOCUSABLE)).filter(
    (node) => node.getClientRects().length > 0
  );
}

/**
 * A modal dialog. Returns `{dialog, body, footer, done, close}` where `done`
 * resolves with whatever `close(value)` was given.
 *
 * Escape closes with `cancelValue`. Tab is trapped. The element that had focus
 * when the modal opened gets it back on close. There is deliberately no
 * click-outside-to-dismiss: the add dialog holds unsaved typing.
 */
function createModal(config) {
  ensureBaseStyles();
  const cfg = config || {};
  const trigger = document.activeElement;
  const titleId = uid('fta-modal-title');

  const body = el('div', { class: 'fta-modal-body' });
  const footer = el('div', { class: 'fta-modal-footer' });
  const dialog = el(
    'div',
    {
      class: 'fta-modal' + (cfg.small ? ' is-small' : ''),
      role: 'dialog',
      'aria-modal': 'true',
      'aria-labelledby': titleId,
      tabindex: '-1',
    },
    [el('h2', { class: 'fta-modal-title', id: titleId, text: cfg.title || 'Dialog' }), body, footer]
  );
  const overlay = el('div', { class: 'fta-modal-overlay' }, [dialog]);

  let settle;
  const done = new Promise((resolve) => {
    settle = resolve;
  });
  let closed = false;

  function close(value) {
    if (closed) return;
    closed = true;
    document.removeEventListener('keydown', onKeydown, true);
    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    if (trigger && typeof trigger.focus === 'function' && trigger.isConnected) {
      trigger.focus();
    }
    settle(value);
  }

  function onKeydown(event) {
    // Only the top-most modal reacts, so a stacked dialog cannot close the one
    // underneath it with a single Escape.
    const overlays = document.querySelectorAll('.fta-modal-overlay');
    if (overlays.length && overlays[overlays.length - 1] !== overlay) return;
    if (!overlay.contains(event.target) && event.key !== 'Escape') {
      // Focus escaped the dialog (browser chrome, a stray programmatic focus):
      // pull it back rather than letting the page behind take keystrokes.
      const first = focusableIn(dialog)[0] || dialog;
      first.focus();
      event.preventDefault();
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      close(cfg.cancelValue === undefined ? null : cfg.cancelValue);
      return;
    }
    if (event.key === 'Tab') {
      const items = focusableIn(dialog);
      if (!items.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      const outside = !dialog.contains(active);
      if (event.shiftKey && (outside || active === first)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (outside || active === last)) {
        event.preventDefault();
        first.focus();
      }
      return;
    }
    if (event.key === 'Enter' && typeof cfg.onEnter === 'function') {
      const target = event.target;
      const tag = target && target.tagName ? target.tagName.toLowerCase() : '';
      // A textarea keeps Enter for newlines; a button keeps it for its click.
      if (tag === 'textarea' || tag === 'button' || (target && target.dataset && target.dataset.noEnter)) {
        return;
      }
      event.preventDefault();
      cfg.onEnter();
    }
  }

  document.addEventListener('keydown', onKeydown, true);
  document.body.appendChild(overlay);

  return { overlay: overlay, dialog: dialog, body: body, footer: footer, done: done, close: close };
}

/**
 * Yes/no confirmation. Resolves true for OK, false for Cancel or Escape.
 */
export function confirmDialog(message, options) {
  const opts = options || {};
  const modal = createModal({
    title: opts.title || 'Confirm',
    small: true,
    cancelValue: false,
    onEnter: () => modal.close(true),
  });

  modal.body.appendChild(el('p', { class: 'fta-modal-message', text: String(message) }));

  const cancel = el('button', {
    type: 'button',
    class: 'fta-btn',
    text: opts.cancelLabel || 'Cancel',
    onclick: () => modal.close(false),
  });
  const confirm = el('button', {
    type: 'button',
    class: 'fta-btn is-primary',
    text: opts.confirmLabel || 'OK',
    onclick: () => modal.close(true),
  });
  modal.footer.appendChild(cancel);
  modal.footer.appendChild(confirm);
  confirm.focus();

  return modal.done.then((value) => value === true);
}

/* -------------------------------------------------------- add node dialog ---- */

function field(labelText, control) {
  const id = uid('fta-field');
  control.id = id;
  const error = el('p', { class: 'fta-field-error', hidden: true });
  error.id = id + '-error';
  control.setAttribute('aria-describedby', error.id);
  const wrapper = el('div', { class: 'fta-field' }, [
    el('label', { for: id, text: labelText }),
    control,
    error,
  ]);
  return {
    element: wrapper,
    control: control,
    setError: (message) => {
      error.textContent = message || '';
      error.hidden = !message;
      control.setAttribute('aria-invalid', message ? 'true' : 'false');
    },
  };
}

/** A select offering AND and OR, and nothing else. See divergence D5. */
export function createGateSelect(value) {
  const select = el('select');
  for (const gate of GATES) select.appendChild(el('option', { value: gate, text: gate }));
  const current = normalizeGate(value);
  if (GATES.indexOf(current) === -1) {
    // A hand-edited file can carry an unsupported gate (NOT). Show it, disabled,
    // so the user sees what is stored instead of a silently rewritten value.
    select.insertBefore(
      el('option', { value: current, disabled: true, text: current + ' (unsupported)' }),
      select.firstChild
    );
  }
  select.value = current;
  return select;
}

/**
 * Collect the field values for a new child of `parentId`.
 *
 * Resolves with `{name, type, probability, logicGate, notes, links}` or null if
 * the dialog was cancelled. No id is included and none may be sent: ids are
 * assigned server-side by `next_child_id` (routes/tree.py::create_node).
 */
export function openAddNodeDialog(parentId) {
  const parent = parentId === undefined || parentId === null ? null : String(parentId);

  const nameField = field('Name', el('input', { type: 'text', value: '' }));
  const typeField = field('Type', el('input', { type: 'text', value: 'Event' }));
  const probabilityField = field(
    'Probability',
    el('input', { type: 'text', inputmode: 'decimal', value: '1.0' })
  );
  const gateField = field('Logic Gate', createGateSelect('OR'));
  const notesField = field('Notes', el('textarea', { rows: '4' }));

  const linksEditor = createLinksEditor({ selfId: null, links: [] });

  const modal = createModal({
    title: parent ? 'Add Node under ' + parent : 'Add Node',
    cancelValue: null,
    onEnter: () => submit(),
  });

  modal.body.appendChild(nameField.element);
  modal.body.appendChild(
    el('div', { class: 'fta-row-2' }, [typeField.element, probabilityField.element])
  );
  modal.body.appendChild(el('div', { class: 'fta-row-2' }, [gateField.element]));
  modal.body.appendChild(notesField.element);
  modal.body.appendChild(linksEditor.element);

  modal.footer.appendChild(
    el('button', {
      type: 'button',
      class: 'fta-btn',
      text: 'Cancel',
      onclick: () => modal.close(null),
    })
  );
  modal.footer.appendChild(
    el('button', { type: 'button', class: 'fta-btn is-primary', text: 'OK', onclick: () => submit() })
  );

  function submit() {
    nameField.setError('');
    typeField.setError('');
    probabilityField.setError('');
    gateField.setError('');

    const name = sanitizeName(nameField.control.value);
    if (!name) {
      nameField.setError('Name is required.');
      nameField.control.focus();
      return;
    }
    const type = String(typeField.control.value || '').trim();
    if (!type) {
      typeField.setError("'type' must be a non-empty string.");
      typeField.control.focus();
      return;
    }
    const probability = parseProbability(probabilityField.control.value);
    if (!probability.ok) {
      probabilityField.setError(probability.message);
      probabilityField.control.focus();
      return;
    }
    const gate = validateGate(gateField.control.value);
    if (!gate.ok) {
      gateField.setError(gate.message);
      gateField.control.focus();
      return;
    }

    modal.close({
      name: name,
      type: type,
      probability: probability.value,
      logicGate: gate.value,
      notes: String(notesField.control.value || ''),
      links: linksEditor.getLinks(),
    });
  }

  linksEditor.reload();
  nameField.control.focus();
  nameField.control.select();

  return modal.done.then((value) => (value === undefined ? null : value));
}
