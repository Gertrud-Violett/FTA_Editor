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
import { formatProb, getSigFigs, parseNumberText } from './numfmt.js';
import { BASIC_GATES, GATE_TYPES, projectLogicGate } from './schema.js';
import gateCatalog from './i18n/gate.js';

// Workstream B: gate/event strings live in i18n/gate.js. Registered here (the
// shell exists by the time the panels are dynamically imported) and also
// consulted directly by t() below, so a missing shell never shows raw keys.
try {
  if (typeof window !== 'undefined' && window.ftaShell && window.ftaShell.registerStrings) {
    window.ftaShell.registerStrings(gateCatalog);
  }
} catch (_err) {
  /* strings fall back to the catalog itself */
}

/* ----------------------------------------------------------------- i18n ---- */

/*
 * English fallbacks for every key this file and details.js use. main.js owns
 * the real table; this module can be imported before `window.ftaShell` exists
 * (and is unit-testable without it), so a missing shell must not render keys.
 */
const FALLBACK = {
  'dialog.title': 'Dialog',
  'dialog.confirmTitle': 'Confirm',
  'dialog.ok': 'OK',
  'dialog.cancel': 'Cancel',
  'dialog.dismiss': 'Dismiss',
  'dialog.somethingWrong': 'Something went wrong.',
  'dialog.addNode': 'Add Node',
  'dialog.addNodeUnder': 'Add Node under "{name}"',
  'dialog.addNoSelection':
    'No node is selected, so the new node goes under the top event. To add it elsewhere, cancel and select a node first.',
  'dialog.addAnother': 'OK and add another',
  'dialog.addAnotherTitle': 'Create this node and keep the dialog open for the next one (Ctrl+Enter)',
  'dialog.addedOne': 'Added "{name}". Type the next one, or press Escape to finish.',
  'dialog.probabilityRequired':
    'Enter a probability from 0 to 1. For an event that will get children of its own the value is not used: enter 1.',
  'dialog.probabilityPlaceholder': '0 to 1, e.g. 1e-3, 0.5% or 1/1000',
  'dialog.nameRequired': 'Name is required.',
  'dialog.typeRequired': 'Type must not be empty.',
  'dialog.probabilityRange': 'Probability must be a number between 0.0 and 1.0.',
  'dialog.gateNot':
    'NOT gates are not supported: the probability engine has no NOT '
    + 'semantics and would score the node as OR. Use AND or OR.',
  'dialog.gateInvalid': 'Logic gate must be AND or OR.',
  'dialog.gateUnsupported': '{gate} (unsupported)',

  'details.aria': 'Node details',
  'details.name': 'Name',
  'details.type': 'Type',
  'details.probability': 'Probability',
  'details.probabilityBase': 'Probability (base)',
  'details.logicGate': 'Logic Gate',
  'details.notes': 'Notes',
  'details.links': 'Links',
  'details.empty': 'Select a node in the tree to edit it.',
  'details.nodeId': 'Node ID',
  'details.calculated': 'Calculated probability',
  'details.zeroFlag': '✖ zero probability',
  'details.saveFailed': 'Could not save the change.',

  'links.search': 'Search Events',
  'links.searchPlaceholder': 'Filter by name or id',
  'links.matching': 'Matching events',
  'links.noMatch': 'No matching events',
  'links.section': '{relation} Links',
  'links.listAria': '{relation} links',
  'links.add': 'Add →',
  'links.addTitle': 'Add the selected events as {relation} links',
  'links.remove': '← Remove',
  'links.removeTitle': 'Remove the selected {relation} links',
  'links.self': 'A node cannot link to itself.',
  'links.duplicate': 'Already linked with that relation.',
  'links.selectFirst': 'Select one or more events above first.',
  'links.added': 'Added {n} {relation} link(s).',
  'links.skippedSelf': 'Skipped the node itself.',
  'links.skippedDuplicate': 'Skipped {n} already linked.',
  'links.selectToRemove': 'Select one or more {relation} links to remove.',
  'links.removed': 'Removed {n} {relation} link(s).',
  'links.saveFailed': 'Could not save the links.',
  'links.loadFailed': 'Could not load the node list.',
};

function interpolate(text, vars) {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (whole, name) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : whole
  );
}

/**
 * Translate through the shell when it is there, else through FALLBACK. The
 * shell returns the key itself for an unknown key, which is also routed to
 * FALLBACK so a stale table never shows `dialog.ok` to the user.
 */
export function t(key, vars) {
  const shell = typeof window !== 'undefined' ? window.ftaShell : null;
  if (shell && typeof shell.t === 'function') {
    try {
      const text = shell.t(key, vars);
      if (text !== key || !FALLBACK[key]) return text;
    } catch (_err) {
      /* fall through */
    }
  }
  let text = FALLBACK[key];
  if (text === undefined) {
    const lang = shell && shell.language === 'ja' ? 'ja' : 'en';
    text = (gateCatalog[lang] && gateCatalog[lang][key]) || (gateCatalog.en && gateCatalog.en[key]);
  }
  return text === undefined ? key : interpolate(text, vars);
}

function shell() {
  return typeof window !== 'undefined' ? window.ftaShell : null;
}

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

/**
 * True for a key the IME is still using. The Enter that confirms a Japanese
 * conversion and the Escape that cancels it reach the page as keydown with
 * isComposing set (Chrome on macOS and Linux; keyCode 229 elsewhere), and
 * must not submit, close, commit or revert anything.
 */
export function isImeKey(event) {
  return Boolean(event) && (event.isComposing === true || event.keyCode === 229);
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
  --fta-surface-hover: #eef2f6;
  --fta-canvas: #ffffff;
  --fta-border: #c9d1d9;
  --fta-accent: #1a73e8;
  --fta-accent-fg: #ffffff;
  --fta-focus-ring: #1a73e8;
  --fta-overlay: rgba(16, 20, 24, 0.45);
  --fta-shadow: 0 12px 32px rgba(16, 20, 24, 0.28);
  --fta-danger-fg: #8c1d18;
  --fta-danger-bg: #fdecea;
  --fta-danger-border: #f2b8b5;
  --fta-warn-fg: #9a5d00;
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
  --fta-surface-hover: #2a313f;
  --fta-canvas: #1b1f23;
  --fta-border: #3a424a;
  --fta-accent: #8ab4f8;
  --fta-accent-fg: #10151a;
  --fta-focus-ring: #8ab4f8;
  --fta-overlay: rgba(0, 0, 0, 0.62);
  --fta-shadow: 0 12px 32px rgba(0, 0, 0, 0.55);
  --fta-danger-fg: #ffb4ab;
  --fta-danger-bg: #3b1f1d;
  --fta-danger-border: #6b3a36;
  --fta-warn-fg: #e0a144;
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
.fta-modal-footer { display: flex; justify-content: flex-end; gap: 0.5rem; flex-wrap: wrap; }
.fta-modal-message { margin: 0; line-height: 1.45; overflow-wrap: anywhere; }
.fta-modal-details { margin: 0; padding-left: 1.2rem; line-height: 1.45; overflow-wrap: anywhere; }
/* A button that throws work away, beside one that keeps it. */
.fta-btn.is-danger { color: var(--fta-danger-fg); border-color: var(--fta-danger-border); }
.fta-btn.is-danger:hover { background: var(--fta-danger-bg); }
/* choiceList: one row per thing to pick. */
.fta-choice-list { display: flex; flex-direction: column; gap: 0.3rem; margin: 0; padding: 0; list-style: none; }
.fta-choice {
  display: flex; flex-direction: column; align-items: flex-start; gap: 0.1rem;
  width: 100%; padding: 0.45rem 0.6rem; text-align: left;
  border: 1px solid var(--fta-border); border-radius: var(--fta-radius);
  background: var(--fta-surface); color: var(--fta-fg); font: inherit; cursor: pointer;
}
.fta-choice:hover { border-color: var(--fta-accent); background: var(--fta-surface-hover); }
.fta-choice:focus-visible { outline: 2px solid var(--fta-focus-ring); outline-offset: 1px; }
.fta-choice__label { font-weight: 600; overflow-wrap: anywhere; }
.fta-choice__note { font-size: 0.8rem; color: var(--fta-muted-fg); overflow-wrap: anywhere; }

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
.fta-dialog-note {
  margin: 0;
  padding: 6px 8px;
  border: 1px solid var(--fta-border);
  border-radius: var(--fta-radius);
  background: var(--fta-surface);
  font-size: 0.82rem;
}
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
  return fallback || t('dialog.somethingWrong');
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
    'aria-label': t('dialog.dismiss'),
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
 *
 * Routed through the shell's toast when it exists so the message shares the
 * status line, the auto-dismiss timer and Escape; the private host below is
 * only for a page that runs this module without main.js.
 */
export function showError(err, fallback) {
  const message = errorMessage(err, fallback);
  const code = errorCode(err);
  const sh = shell();
  if (sh && typeof sh.toast === 'function') {
    sh.toast(message, 'error', code);
    return;
  }
  toast(message, 'error', code, 0);
}

/** Transient confirmation, e.g. "Added 2 AND link(s)". */
export function showNotice(message) {
  const sh = shell();
  if (sh && typeof sh.toast === 'function') {
    sh.toast(message, 'ok');
    return;
  }
  toast(message, 'notice', null, 4000);
}

/* ------------------------------------------------------------- validation ---- */

/** AND/OR only: link relations and the basic gate select. See schema.js. */
export const GATES = BASIC_GATES;

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
export function validateGate(value, options) {
  const gate = normalizeGate(value);
  if (gate === 'NOT') {
    return { ok: false, message: t('dialog.gateNot') };
  }
  const advanced = !!(options && options.advanced);
  const allowed = advanced ? GATE_TYPES : GATES;
  if (allowed.indexOf(gate) === -1) {
    return { ok: false, message: t(advanced ? 'gate.invalidAdvanced' : 'dialog.gateInvalid') };
  }
  return { ok: true, value: gate };
}

/** True when the Advanced switch in the top bar is on. */
export function isAdvancedMode() {
  try {
    const s = shell();
    return !!(s && typeof s.advanced === 'function' && s.advanced());
  } catch (_err) {
    return false;
  }
}

/** Localised display name of a gate type (`AND`, `k-out-of-n`, ...). */
export function gateLabel(gate) {
  const key = 'gate.' + normalizeGate(gate);
  const text = t(key);
  return text === key ? normalizeGate(gate) : text;
}

/**
 * Fill `select` with the gates for the mode. Basic: AND/OR. Advanced: every
 * GATE_TYPES entry, localised. A stored value outside the list is shown as a
 * disabled option (never silently rewritten).
 */
export function fillGateOptions(select, value, advanced) {
  clear(select);
  const list = advanced ? GATE_TYPES : GATES;
  for (const gate of list) {
    select.appendChild(el('option', { value: gate, text: advanced ? gateLabel(gate) : gate }));
  }
  const current = normalizeGate(value);
  if (list.indexOf(current) === -1) {
    const known = GATE_TYPES.indexOf(current) !== -1;
    select.insertBefore(
      el('option', {
        value: current,
        disabled: true,
        text: known
          ? gateLabel(current) + ' (' + t('gate.advancedChip') + ')'
          : t('dialog.gateUnsupported', { gate: current }),
        dataset: { unsupported: 'true' },
      }),
      select.firstChild
    );
  }
  select.value = current;
  return select;
}

/**
 * Mirror of `routes/tree.py::_validate_probability`, after numfmt.js has read
 * what was typed: "5%", "0,05", "1/1000" and full-width digits are the plain
 * decimal they mean (parseNumberText). The server is sent the number and
 * accepts what it always did. `text` is that decimal as text, for the field
 * to show; `changed` says it is not what was typed.
 */
export function parseProbability(raw) {
  const bad = () => ({ ok: false, message: t('dialog.probabilityRange') });
  const read = parseNumberText(raw);
  if (!read.ok) return bad();
  if (read.value < 0 || read.value > 1) return bad();
  return { ok: true, value: read.value, text: read.text, changed: read.changed };
}

/** Trim to the shape `sanitize_name` produces, so the field shows what will be stored. */
export function sanitizeName(value) {
  return String(value === null || value === undefined ? '' : value)
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Display form of a probability at the user's significant-figure preference
 * (numfmt.js). Rounding to six decimals used to show 1e-7 as "0".
 */
export function formatProbability(value) {
  return formatProb(value, getSigFigs());
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
  const search = el('input', { type: 'search', id: searchId });
  const searchLabel = el('label', { for: searchId });
  const matches = el('select', { multiple: true, size: '8' });
  const status = el('p', { class: 'fta-links-status', role: 'status' });

  const sections = {};
  for (const relation of GATES) {
    const list = el('select', { multiple: true, size: '5' });
    const addBtn = el('button', { type: 'button', class: 'fta-btn is-tiny' });
    const removeBtn = el('button', { type: 'button', class: 'fta-btn is-tiny' });
    const legend = el('legend');
    addBtn.addEventListener('click', () => addSelected(relation));
    removeBtn.addEventListener('click', () => removeSelected(relation));
    sections[relation] = { list: list, addBtn: addBtn, removeBtn: removeBtn, legend: legend, node: null };
    sections[relation].node = el('fieldset', {}, [
      legend,
      el('div', { class: 'fta-links-picker' }, [
        list,
        el('div', { class: 'fta-links-buttons' }, [addBtn, removeBtn]),
      ]),
    ]);
  }

  const element = el('div', { class: 'fta-links' }, [
    el('div', { class: 'fta-field' }, [searchLabel, search]),
    matches,
    status,
    sections.AND.node,
    sections.OR.node,
  ]);

  /** Apply the current language to every static label; safe to call again. */
  function relabel() {
    searchLabel.textContent = t('links.search');
    search.placeholder = t('links.searchPlaceholder');
    matches.setAttribute('aria-label', t('links.matching'));
    for (const relation of GATES) {
      const section = sections[relation];
      const vars = { relation: relation };
      section.list.setAttribute('aria-label', t('links.listAria', vars));
      section.addBtn.textContent = t('links.add');
      section.addBtn.title = t('links.addTitle', vars);
      section.removeBtn.textContent = t('links.remove');
      section.removeBtn.title = t('links.removeTitle', vars);
      section.legend.textContent = t('links.section', vars);
    }
    renderMatches();
  }

  search.addEventListener('input', renderMatches);
  // Enter in the search box must not submit or confirm the surrounding dialog.
  search.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !isImeKey(event)) event.preventDefault();
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
      matches.appendChild(el('option', { value: '', disabled: true, text: t('links.noMatch') }));
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
      setStatus(errorMessage(err, t('links.saveFailed')), true);
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
        ? t('links.self')
        : skippedDuplicate
          ? t('links.duplicate')
          : t('links.selectFirst');
      renderLists();
      setStatus(why, true);
      return;
    }
    let message = t('links.added', { n: added, relation: relation });
    if (skippedSelf) message += ' ' + t('links.skippedSelf');
    if (skippedDuplicate) message += ' ' + t('links.skippedDuplicate', { n: skippedDuplicate });
    commit(previous, message);
  }

  function removeSelected(relation) {
    const list = sections[relation].list;
    const targets = selectedValues(list);
    if (!targets.length) {
      setStatus(t('links.selectToRemove', { relation: relation }), true);
      return;
    }
    const previous = links.map((link) => ({ ...link }));
    links = links.filter(
      (link) => !(link.relation === relation && targets.indexOf(link.target_id) !== -1)
    );
    commit(previous, t('links.removed', { n: targets.length, relation: relation }));
  }

  /** Bumped by every reload(), so only the newest request's answer counts. */
  let reloadSeq = 0;

  /** (Re)load the node list from the API. Failures are reported inline. */
  async function reload() {
    // An older list answering last (New/Open while it was on the wire)
    // offered the previous document's nodes as link targets.
    const mine = ++reloadSeq;
    try {
      const list = await fetchNodeList();
      if (mine !== reloadSeq) return;
      choices = list;
      nameById.clear();
      for (const choice of choices) nameById.set(String(choice.id), choice.name);
      renderMatches();
      renderLists();
      setStatus('', false);
    } catch (err) {
      if (mine !== reloadSeq) return;
      setStatus(errorMessage(err, t('links.loadFailed')), true);
      showError(err, t('links.loadFailed'));
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

  relabel();
  renderLists();

  return {
    element: element,
    reload: reload,
    relabel: relabel,
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
 * Give focus back to the element that opened a dialog. A tree row trigger is
 * re-rendered on every store change, so when it is gone the tree's lead row
 * (or, with no rows, the tree panel host) takes focus instead of letting it
 * drop to <body>.
 */
export function restoreFocus(trigger) {
  if (trigger && typeof trigger.focus === 'function' && trigger.isConnected) {
    trigger.focus();
    return;
  }
  const host = document.getElementById('tree-root');
  if (!host) return;
  // The tree's lead row (its one tab stop) rather than the panel around it:
  // from the panel itself no arrow key or shortcut of the tree works.
  const lead = host.querySelector('[role="treeitem"][tabindex="0"]');
  if (lead && typeof lead.focus === 'function') lead.focus();
  else if (typeof host.focus === 'function') host.focus();
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
    [el('h2', { class: 'fta-modal-title', id: titleId, text: cfg.title || t('dialog.title') }), body, footer]
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
    restoreFocus(trigger);
    settle(value);
  }

  function onKeydown(event) {
    // Only the top-most modal reacts, so a stacked dialog cannot close the one
    // underneath it with a single Escape.
    const overlays = document.querySelectorAll('.fta-modal-overlay');
    if (overlays.length && overlays[overlays.length - 1] !== overlay) return;
    // Confirming or cancelling a conversion: the IME's key, not the dialog's.
    if (isImeKey(event)) return;
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
    // Ctrl+Enter is the dialog's second action (Add: "OK and add another").
    // It works from every control, a textarea and a button included, since
    // neither has a use of its own for it.
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && typeof cfg.onCtrlEnter === 'function') {
      event.preventDefault();
      cfg.onCtrlEnter(event);
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
      cfg.onEnter(event);
    }
  }

  document.addEventListener('keydown', onKeydown, true);
  document.body.appendChild(overlay);

  return { overlay: overlay, dialog: dialog, body: body, footer: footer, done: done, close: close };
}

/**
 * Yes/no confirmation. Resolves true for OK, false for Cancel or Escape.
 * `confirmLabel` names the OK button; `okLabel` is accepted as an alias
 * because main.js's delete confirmation passes that spelling.
 *
 * `focusCancel` opens with the focus on Cancel, for a confirmation whose OK
 * destroys something: Enter and Space then cancel, and deleting takes a
 * deliberate Tab or click. (Enter on a focused button is that button's own
 * click; see createModal.)
 */
export function confirmDialog(message, options) {
  const opts = options || {};
  const modal = createModal({
    title: opts.title || t('dialog.confirmTitle'),
    small: true,
    cancelValue: false,
    onEnter: () => modal.close(true),
  });

  modal.body.appendChild(el('p', { class: 'fta-modal-message', text: String(message) }));

  const cancel = el('button', {
    type: 'button',
    class: 'fta-btn',
    text: opts.cancelLabel || t('dialog.cancel'),
    onclick: () => modal.close(false),
  });
  const confirm = el('button', {
    type: 'button',
    class: 'fta-btn is-primary',
    text: opts.confirmLabel || opts.okLabel || t('dialog.ok'),
    onclick: () => modal.close(true),
  });
  modal.footer.appendChild(cancel);
  modal.footer.appendChild(confirm);
  if (opts.focusCancel) cancel.focus();
  else confirm.focus();

  return modal.done.then((value) => value === true);
}

/**
 * A question with more than two answers. Resolves with the `value` of the
 * button pressed; Cancel and Escape resolve `cancelValue` (null by default).
 *
 *   choiceDialog(message, {
 *     title, cancelLabel, cancelValue,
 *     details: ['line', ...],          // a list under the message
 *     buttons: [{value, label, role?, primary?, danger?, focus?}],
 *   })
 *
 * Cancel comes first and the buttons follow in the order given. The one
 * marked `focus` opens with the focus (Cancel when none is), so Enter does
 * that and nothing else: the unsaved-changes prompts put it on "Save and
 * continue", where a stray Enter keeps the work. Each button carries
 * data-role (`role`, else its value) so a test can name it.
 */
export function choiceDialog(message, options) {
  const opts = options || {};
  const cancelValue = opts.cancelValue === undefined ? null : opts.cancelValue;
  const modal = createModal({
    title: opts.title || t('dialog.confirmTitle'),
    small: !opts.wide,
    cancelValue: cancelValue,
  });
  modal.dialog.dataset.kind = 'choice';

  modal.body.appendChild(el('p', { class: 'fta-modal-message', text: String(message) }));
  const details = Array.isArray(opts.details) ? opts.details.filter(Boolean) : [];
  if (details.length) {
    modal.body.appendChild(
      el('ul', { class: 'fta-modal-details' }, details.map((line) => el('li', { text: String(line) })))
    );
  }

  const cancel = el('button', {
    type: 'button',
    class: 'fta-btn',
    dataset: { role: 'cancel' },
    text: opts.cancelLabel || t('dialog.cancel'),
    onclick: () => modal.close(cancelValue),
  });
  modal.footer.appendChild(cancel);
  let first = cancel;
  for (const spec of Array.isArray(opts.buttons) ? opts.buttons : []) {
    const button = el('button', {
      type: 'button',
      class: 'fta-btn' + (spec.primary ? ' is-primary' : '') + (spec.danger ? ' is-danger' : ''),
      dataset: { role: String(spec.role || spec.value) },
      text: String(spec.label),
      onclick: () => modal.close(spec.value),
    });
    modal.footer.appendChild(button);
    if (spec.focus) first = button;
  }
  first.focus();
  return modal.done;
}

/**
 * Pick one of a list. Resolves with the chosen item's `value`, or null for
 * Cancel and Escape.
 *
 *   choiceList({title, message, empty, items: [{value, label, note?}]})
 *
 * Arrow keys move between the rows; Enter and Space choose (they are
 * buttons).
 */
export function choiceList(options) {
  const opts = options || {};
  const items = Array.isArray(opts.items) ? opts.items : [];
  const modal = createModal({ title: opts.title || t('dialog.title'), small: false, cancelValue: null });
  modal.dialog.dataset.kind = 'list';

  if (opts.message) modal.body.appendChild(el('p', { class: 'fta-modal-message', text: String(opts.message) }));
  const rows = items.map((item) =>
    el('button', {
      type: 'button',
      class: 'fta-choice',
      dataset: { value: String(item.value) },
      onclick: () => modal.close(item.value),
    }, [
      el('span', { class: 'fta-choice__label', text: String(item.label) }),
      item.note ? el('span', { class: 'fta-choice__note', text: String(item.note) }) : null,
    ])
  );
  if (rows.length) {
    const list = el('ul', { class: 'fta-choice-list' }, rows.map((row) => el('li', null, [row])));
    list.addEventListener('keydown', (event) => {
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
      const at = rows.indexOf(document.activeElement);
      if (at < 0) return;
      event.preventDefault();
      const next = rows[Math.min(rows.length - 1, Math.max(0, at + (event.key === 'ArrowDown' ? 1 : -1)))];
      next.focus();
    });
    modal.body.appendChild(list);
  } else if (opts.empty) {
    modal.body.appendChild(el('p', { class: 'fta-modal-message', text: String(opts.empty) }));
  }

  const cancel = el('button', {
    type: 'button',
    class: 'fta-btn',
    dataset: { role: 'cancel' },
    text: opts.cancelLabel || t('dialog.cancel'),
    onclick: () => modal.close(null),
  });
  modal.footer.appendChild(cancel);
  (rows[0] || cancel).focus();
  return modal.done;
}

/* ------------------------------------------------- numeric field focusing ---- */

/**
 * Numeric fields: the ones that hold a value the user usually replaces
 * rather than edits (a probability, λ, a limit). Tab already selects a
 * field's text; this makes a mouse click do the same. data-keep-caret opts a
 * field out (the top bar's date is edited piecewise).
 */
export const SELECT_ON_FOCUS = [
  'input[inputmode="decimal"]',
  'input[inputmode="numeric"]',
  'input[type="number"]',
].map((sel) => sel + ':not([data-keep-caret])').join(', ');

let selectOnFocusInstalled = false;

/**
 * Select a numeric field's whole value when a mouse click focuses it, so
 * typing replaces the value. The Add dialog's probability used to start as
 * "1.0"; clicking into it left the caret at the end and typing 1e-3 stored
 * "1.01e-3" = 0.00101, and the same goes for any field that shows a stored
 * number. A click into a field that already has focus still
 * places the caret, and a drag that selects part of the text is kept.
 * Installed once, on the document, for every present and future field.
 */
export function installSelectOnFocus(doc) {
  const root = doc || document;
  if (selectOnFocusInstalled) return;
  selectOnFocusInstalled = true;
  let pending = null;
  root.addEventListener('mousedown', (event) => {
    const input = event.target instanceof Element ? event.target.closest(SELECT_ON_FOCUS) : null;
    pending = input && input !== root.activeElement && !input.readOnly && !input.disabled ? input : null;
  }, true);
  root.addEventListener('mouseup', (event) => {
    const input = pending;
    pending = null;
    if (!input || root.activeElement !== input) return;
    let partial = false;
    try {
      partial = input.selectionStart !== null && input.selectionStart !== input.selectionEnd;
    } catch (_err) {
      partial = false; // type=number has no selection API
    }
    if (partial) return;
    event.preventDefault(); // keep the mouseup from collapsing the selection to a caret
    try {
      input.select();
    } catch (_err) {
      /* nothing selectable */
    }
  }, true);
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

/**
 * A gate select. `createGateSelect('OR')` offers AND and OR only (basic mode,
 * divergence D5); `createGateSelect({value, advanced: true})` offers every
 * 1.7 gate type. NOT is never offered. A hand-edited file can carry an
 * unsupported gate: it is shown disabled, so the user sees what is stored
 * instead of a silently rewritten value.
 */
export function createGateSelect(opts) {
  const options = opts && typeof opts === 'object' ? opts : { value: opts };
  return fillGateOptions(el('select'), options.value, !!options.advanced);
}

/**
 * Collect the field values for a new child of `parentId`.
 *
 * Resolves with `{name, type, probability, logicGate, notes, links, gateType?}` or null if
 * the dialog was cancelled. No id is included and none may be sent: ids are
 * assigned server-side by `next_child_id` (routes/tree.py::create_node).
 *
 * `options.submit(fields, how)`, when given, creates the node: the dialog awaits it
 * and stays open, with everything typed, until it resolves; a rejection is
 * shown at the field the server named (or under the form) for another try.
 *
 * With `submit` there is a second button, "OK and add another" (Ctrl+Enter):
 * `how.another` is then true, and once the node exists the dialog clears the
 * name, probability, notes and links and waits for the next sibling. Type and
 * gate are kept, since a run of siblings usually shares them.
 *
 * The probability starts empty and has to be typed. It used to start at 1.0,
 * and Enter in the Name box made a certain event of every node; now Enter
 * there moves on to the empty Probability box instead of submitting.
 */
/** A dialog title names the parent as the user knows it; the id is the fallback. */
const PARENT_LABEL_CHARS = 48;

function parentLabel(id, name) {
  const text = String(name === null || name === undefined ? '' : name).trim() || String(id);
  return text.length > PARENT_LABEL_CHARS ? text.slice(0, PARENT_LABEL_CHARS - 1) + '…' : text;
}

export function openAddNodeDialog(parentId, options) {
  const opts = options && typeof options === 'object' ? options : {};
  const parent = parentId === undefined || parentId === null ? null : String(parentId);

  const nameField = field(t('details.name'), el('input', { type: 'text', value: '' }));
  const typeField = field(t('details.type'), el('input', { type: 'text', value: 'Event' }));
  const probabilityField = field(
    t('details.probability'),
    el('input', {
      type: 'text',
      inputmode: 'decimal',
      value: '',
      required: true,
      'aria-required': 'true',
      placeholder: t('dialog.probabilityPlaceholder'),
    })
  );
  const advancedGates = isAdvancedMode();
  const gateField = field(t('details.logicGate'), createGateSelect({ value: 'OR', advanced: advancedGates }));
  const notesField = field(t('details.notes'), el('textarea', { rows: '4' }));

  const linksEditor = createLinksEditor({ selfId: null, links: [] });
  const formError = el('p', { class: 'fta-field-error', role: 'alert', hidden: true });
  // "Added X" after OK-and-add-another: the only sign, inside the dialog, that
  // the cleared form is a new one and the last node was made.
  const addedNote = el('p', { class: 'fta-dialog-note', role: 'status', hidden: true });
  const canAddAnother = typeof opts.submit === 'function';

  const modal = createModal({
    title: parent ? t('dialog.addNodeUnder', { name: parentLabel(parent, opts.parentName) }) : t('dialog.addNode'),
    cancelValue: null,
    onEnter: (event) => {
      // Enter in Name with no probability yet: go and type one. Submitting
      // here only bounced back with "required", one keystroke later.
      if (
        event && event.target === nameField.control &&
        sanitizeName(nameField.control.value) &&
        String(probabilityField.control.value || '').trim() === ''
      ) {
        probabilityField.control.focus();
        return;
      }
      submit(false);
    },
    onCtrlEnter: () => submit(canAddAnother),
  });

  // Adding with nothing selected is allowed, but never silent: an id like
  // root_0_0 in the title read as "root", and a node that went to the top
  // event unasked looked like a bug.
  if (opts.noSelection) {
    modal.body.appendChild(el('p', { class: 'fta-dialog-note', text: t('dialog.addNoSelection') }));
  }
  modal.body.appendChild(addedNote);
  modal.body.appendChild(nameField.element);
  modal.body.appendChild(
    el('div', { class: 'fta-row-2' }, [typeField.element, probabilityField.element])
  );
  modal.body.appendChild(el('div', { class: 'fta-row-2' }, [gateField.element]));
  modal.body.appendChild(notesField.element);
  modal.body.appendChild(linksEditor.element);
  modal.body.appendChild(formError);

  modal.footer.appendChild(
    el('button', {
      type: 'button',
      class: 'fta-btn',
      text: t('dialog.cancel'),
      onclick: () => modal.close(null),
    })
  );
  const anotherButton = el('button', {
    type: 'button',
    class: 'fta-btn',
    text: t('dialog.addAnother'),
    title: t('dialog.addAnotherTitle'),
    dataset: { role: 'add-another' },
    onclick: () => submit(true),
  });
  if (canAddAnother) modal.footer.appendChild(anotherButton);
  const okButton = el('button', {
    type: 'button',
    class: 'fta-btn is-primary',
    text: t('dialog.ok'),
    onclick: () => submit(false),
  });
  modal.footer.appendChild(okButton);

  // A complaint about a box goes away as soon as the box is typed in again;
  // it used to stay under a corrected value until the next OK.
  for (const one of [nameField, typeField, probabilityField, notesField]) {
    one.control.addEventListener('input', () => one.setError(''));
  }
  gateField.control.addEventListener('change', () => gateField.setError(''));

  // Show what "5%" or "0,05" was read as before it is sent, not after.
  probabilityField.control.addEventListener('blur', () => {
    const read = parseProbability(probabilityField.control.value);
    if (read.ok && read.changed) probabilityField.control.value = read.text;
  });

  /** The server's field names, mapped to this dialog's controls. */
  const fieldFor = {
    name: nameField,
    type: typeField,
    probability: probabilityField,
    logicGate: gateField,
    gateType: gateField,
    notes: notesField,
  };

  function setFormError(message) {
    formError.textContent = message || '';
    formError.hidden = !message;
  }

  let submitting = false;

  function setBusy(on) {
    submitting = on;
    okButton.disabled = on;
    anotherButton.disabled = on;
  }

  /** The node was made and another is wanted: an empty form for a sibling. */
  function resetForNext(name) {
    nameField.control.value = '';
    probabilityField.control.value = '';
    notesField.control.value = '';
    linksEditor.setLinks([]);
    linksEditor.reload(); // the node just made can be linked to now
    addedNote.textContent = t('dialog.addedOne', { name: name });
    addedNote.hidden = false;
    nameField.control.focus();
  }

  function submit(another) {
    if (submitting) return;
    nameField.setError('');
    typeField.setError('');
    probabilityField.setError('');
    gateField.setError('');
    notesField.setError('');
    setFormError('');

    const name = sanitizeName(nameField.control.value);
    if (!name) {
      nameField.setError(t('dialog.nameRequired'));
      nameField.control.focus();
      return;
    }
    const type = String(typeField.control.value || '').trim();
    if (!type) {
      typeField.setError(t('dialog.typeRequired'));
      typeField.control.focus();
      return;
    }
    if (String(probabilityField.control.value || '').trim() === '') {
      probabilityField.setError(t('dialog.probabilityRequired'));
      probabilityField.control.focus();
      return;
    }
    const probability = parseProbability(probabilityField.control.value);
    if (!probability.ok) {
      probabilityField.setError(probability.message);
      probabilityField.control.focus();
      return;
    }
    const gate = validateGate(gateField.control.value, { advanced: advancedGates });
    if (!gate.ok) {
      gateField.setError(gate.message);
      gateField.control.focus();
      return;
    }

    const result = {
      name: name,
      type: type,
      probability: probability.value,
      logicGate: projectLogicGate(gate.value),
      notes: String(notesField.control.value || ''),
      links: linksEditor.getLinks(),
    };
    // 1.7 gates travel as gateType; the server projects logicGate from it.
    if (GATES.indexOf(gate.value) === -1) result.gateType = gate.value;
    if (typeof opts.submit !== 'function') {
      modal.close(result);
      return;
    }
    // The caller creates the node. Closing first lost everything typed when
    // the server refused it, so the dialog waits, and says why on a refusal.
    setBusy(true);
    Promise.resolve()
      .then(() => opts.submit(result, { another: !!another }))
      .then(
        () => {
          if (!another) {
            modal.close(result);
            return;
          }
          setBusy(false);
          resetForNext(name);
        },
        (err) => {
          setBusy(false);
          const message = errorMessage(err, t('dialog.somethingWrong'));
          const named = errorField(err);
          const target = named && Object.prototype.hasOwnProperty.call(fieldFor, named) ? fieldFor[named] : null;
          if (target) {
            target.setError(message);
            target.control.focus();
          } else {
            setFormError(message);
          }
        }
      );
  }

  linksEditor.reload();
  nameField.control.focus();
  nameField.control.select();

  return modal.done.then((value) => (value === undefined ? null : value));
}
