/**
 * tabs/grid.js -- the Grid tab (F3): every basic event in one table.
 *
 * One row per basic event (the same rows, in the same order, as the Quantification
 * tab's table) and the columns id, name, model, λ, T, τ, μ, q, source, tags. The
 * headers name their units: λ in the unit picked in its header (/h, /y or FIT, kept
 * in localStorage `fta.lambdaUnit` like the Quantification tab; stored per hour),
 * T and τ in hours, μ per hour, q dimensionless. q is editable only for the fixed
 * model and is shown with the significant-figures preference. Tags are shown and
 * typed separated by "; ".
 *
 * SORT AND FILTER
 *   Any column sorts (first click ascending, then it toggles; ties keep tree order,
 *   empty cells come last). The filter keeps the rows whose displayed text, in any
 *   visible column, contains the typed text (debounced).
 *
 * EDITING
 *   A cell is plain text until Enter, F2 or a double click opens an editor. The text
 *   is read by the field's own reader -- parseProbability for q, numberParser for
 *   λ, T, τ and μ (this file reads no number itself) -- and sent as one
 *   `PATCH /api/nodes/<id>`, exactly as the Quantification tab does. Writes go through
 *   one serialised chain, and `fta:flush` (Save, exports) gets its tail.
 *
 * LAYOUT
 *   `grid-root` is a size container; the CSS grid inside it (`grid-layout`) puts the
 *   summary of the last paste beside the table when the pane is wide and under the
 *   toolbar when it is narrow (see the stylesheet below).
 *
 * PASTE (FN-47, FN-50, FN-51)
 *   A paste on a cell fills from the selected cell rightwards over the visible columns
 *   and downwards over the displayed rows (grid_paste.js decides the mapping; the cells
 *   are read by the readers below, which call the fields' own parsers). One
 *   `POST /api/grid/paste` carries the node id of every row with the revision and
 *   document serial the grid was drawn from; the answer is one undo step. A paste waits
 *   behind the typed edits on the same chain, so it is never sent before them.
 */
import cat from '../i18n/grid.js';
import quantCat from '../i18n/quant.js';
import { clear, el, injectStyles, parseProbability, sanitizeName } from '../dialogs.js';
import {
  debounce,
  ensureStyles,
  etaNotice,
  formatPlain,
  isEta,
  numberParser,
  reportError,
  translator,
} from './analysis_common.js';
import { endSentence, MAX_PASTE_ROWS, parseClipboard, planPaste } from './grid_paste.js';
import { invalidKey, LAMBDA_LABELS, LAMBDA_UNITS, readLambdaUnit, writeLambdaUnit } from './quant.js';

window.ftaShell?.registerStrings?.(cat);

export const id = 'grid';
export const advanced = true;

/** The columns, in the order of the table (the API keys). */
const COLUMNS = Object.freeze(['id', 'name', 'model', 'lambda', 'T', 'tau', 'mu', 'q', 'source', 'tags']);
/** id and name cannot be hidden. */
const ALWAYS_SHOWN = Object.freeze(['id', 'name']);
const MODELS = Object.freeze(['fixed', 'rate', 'standby', 'repairable']);
/** The parameters each model uses; the others are shown empty and cannot be edited. */
const USED = Object.freeze({
  fixed: [],
  rate: ['lambda', 'T'],
  standby: ['lambda', 'tau'],
  repairable: ['lambda', 'mu'],
});
const NUMERIC = Object.freeze(['lambda', 'T', 'tau', 'mu', 'q']);
/** Column widths in ch, each at least as wide as its longest header in en and ja. */
const WIDTHS = Object.freeze({ id: 11, name: 22, model: 24, lambda: 15, T: 10, tau: 10, mu: 11, q: 21, source: 22, tags: 22 });
const HIDDEN_KEY = 'fta.gridHidden';
const FILTER_MS = 120;
/** Tags are typed with "; " (and the full-width separators of a Japanese keyboard). */
const TAG_SEPARATORS = /[;；、]/;

/**
 * The reader of each numeric column that takes text: the Quantification tab's own
 * numberParser, with the same bounds. A blank cell clears the field (null).
 */
const NUMBER_READERS = Object.freeze({
  lambda: { read: numberParser(0), bounds: { min: 0 } },
  mu: { read: numberParser(0), bounds: { min: 0 } },
  T: { read: numberParser(0, { exclusive: true }), bounds: { min: 0, exclusive: true } },
  tau: { read: numberParser(0, { exclusive: true }), bounds: { min: 0, exclusive: true } },
});

const CSS = `
.anl.anl-grid-tab { gap: 0; padding-top: 8px; padding-bottom: 8px; }
.grid-root { container-type: size; container-name: grid; box-sizing: border-box; flex: 1 1 auto; min-height: 0;
  width: 100%; height: 100%; margin: 0; padding: 0; border: 0; font-size: inherit; }
@media (max-width: 900px) { .grid-root { height: 18em; flex: none; } }
/* The layout. Narrow first (one column: toolbar, message, counts, table, refusal list); the wide rules
   at the end of this sheet put the summary beside the table. Both switch at 50.5em of grid-root. */
.grid-root .grid-layout { display: grid; box-sizing: border-box; width: 100%; height: 100%; margin: 0; padding: 0; border: 0;
  font-size: inherit; row-gap: 0; column-gap: 0; grid-template-columns: minmax(0, 1fr);
  grid-template-rows: auto auto auto minmax(0, 1fr) auto;
  grid-template-areas: "toolbar" "message" "counts" "table" "list"; }
.grid-root .grid-summary { display: contents; }
.grid-root .grid-line { display: block; box-sizing: border-box; height: 18px; line-height: 18px; margin: 0; padding: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.grid-root .grid-summary-title { display: none; font-weight: 600; color: var(--text-dim); }
.grid-root .grid-message { grid-area: message; color: var(--text-dim); }
.grid-root .grid-message:empty { display: none; }
.grid-root .grid-message[data-code] { color: var(--danger); }
.grid-root .grid-summary-counts, .grid-root .grid-summary-error, .grid-root .grid-summary-busy,
.grid-root .grid-summary-empty { grid-area: counts; }
.grid-root .grid-summary-empty { color: var(--text-dim); }
.grid-root .grid-summary-error { color: var(--danger); }
.grid-root .grid-summary-list { grid-area: list; margin: 0; padding: 0 0 0 1.6em; overflow: auto; max-height: 35cqh; min-height: 0; }
.grid-root .grid-summary-list:empty { display: none; }
.grid-root .grid-summary-list li { margin: 0 0 0.4em; }
.grid-root .grid-summary [hidden] { display: none !important; }
.grid-root .grid-summary-counts:empty { height: 0; }
.grid-root .grid-summary-applied, .grid-root .grid-summary-refused-count { display: inline; }
.grid-root .grid-summary-refused-count::before { content: " | "; white-space: pre; }

.grid-root .grid-toolbar { grid-area: toolbar; display: flex; flex-wrap: nowrap; align-items: center; gap: 0 8px;
  box-sizing: border-box; height: 28px; max-height: 28px; margin: 0; padding: 0; min-width: 0; }
.grid-root .grid-toolbar > * { max-height: 28px; }
.grid-root .grid-toolbar [hidden] { display: none !important; }
.grid-root .grid-filter { flex: 1 1 8em; min-width: 6em; max-width: 22em; height: 24px; box-sizing: border-box; margin: 0;
  font: inherit; color: var(--text); background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--r-sm, 5px); padding: 0 6px; }
.grid-root .grid-count { flex: 0 1 auto; min-width: 2em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--text-dim); }
.grid-root .grid-columns-wrap { position: relative; flex: none; display: inline-flex; align-items: center; }
.grid-root .grid-btn { flex: none; white-space: nowrap; height: 24px; box-sizing: border-box; margin: 0; padding: 0 8px; font: inherit;
  color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-sm, 5px); cursor: pointer; }
.grid-root .grid-btn:hover { background: var(--surface-hover); }
.grid-root .grid-btn:focus-visible, .grid-root .grid-filter:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
.grid-root .grid-columns-hidden-count { flex: none; white-space: nowrap; color: var(--text-dim); }
.grid-root .grid-hint { flex: 0 1000 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--text-dim); font-size: var(--fs-xs, 11px); }
.grid-root .grid-columns-popover { position: absolute; top: calc(100% + 2px); left: 0; z-index: 20; min-width: 12em;
  max-height: calc(100cqh - 32px); overflow: auto; box-sizing: border-box; padding: 4px 8px; display: flex; flex-direction: column;
  gap: 0; background: var(--surface); color: var(--text); border: 1px solid var(--border-strong, var(--border));
  border-radius: var(--r-sm, 5px); box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25); }
.grid-root .grid-columns-popover[hidden] { display: none; }
.grid-root .grid-columns-popover label { display: flex; align-items: center; gap: 6px; white-space: nowrap; line-height: 20px; }

.grid-root .grid-scroll { grid-area: table; min-width: 0; min-height: 0; overflow: auto; box-sizing: border-box;
  border: 1px solid var(--border); border-radius: var(--r-sm, 5px); background: var(--surface); }
.grid-root .grid-table { table-layout: fixed; border-collapse: separate; border-spacing: 0; width: auto; min-width: 100%; }
.grid-root .grid-table th, .grid-root .grid-table td { box-sizing: border-box; padding: 3px 8px; text-align: left;
  vertical-align: middle; border-bottom: 1px solid var(--border); }
.grid-root .grid-table th { white-space: nowrap; overflow: visible; }
.grid-root .grid-table td { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: cell; position: relative; }
.grid-root .grid-table td.num { text-align: right; }
.grid-root .grid-table tbody tr { cursor: default; }
.grid-root .grid-table tbody tr:hover { background: transparent; }
.grid-root .grid-table tbody tr:hover td:not(.grid-ro) { background: var(--surface-hover); }
.grid-root .grid-table td.grid-ro { color: var(--text-dim); cursor: default;
  background: color-mix(in srgb, var(--text) 6%, var(--surface)); }
.grid-root .grid-table td.grid-unused { background-image: repeating-linear-gradient(135deg, transparent 0 5px,
  color-mix(in srgb, var(--text) 14%, transparent) 5px 6px); }
.grid-root .grid-table td.grid-computed { font-style: italic; }
.grid-root .grid-table td.grid-dim { color: var(--text-dim); }
/* selected: a dashed outline and a tint; focused as well (the keyboard cursor): the solid focus ring */
.grid-root .grid-table td.is-selected-cell { outline: 2px dashed var(--text-dim); outline-offset: -2px;
  background-color: var(--accent-soft); }
.grid-root .grid-table td.is-selected-cell:focus { outline: 2px solid var(--focus); }
.grid-root .grid-table td.is-editing { overflow: visible; padding: 1px 2px; }
.grid-root .grid-sort { display: inline-flex; align-items: baseline; gap: 0; margin: 0; padding: 0; border: 0; background: none;
  font: inherit; font-weight: inherit; color: inherit; cursor: pointer; white-space: nowrap; }
.grid-root .grid-sort:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
.grid-root .grid-unit { margin-left: 0.3em; font-weight: 400; }
.grid-root .grid-sort-indicator { display: inline-block; min-width: 1em; margin-left: 0.2em; text-align: center; }
.grid-root .grid-lambda-unit { margin-left: 4px; height: 20px; font: inherit; color: var(--text); background: var(--surface);
  border: 1px solid var(--border); border-radius: var(--r-sm, 5px); padding: 0 2px; }
.grid-root .grid-input { width: 100%; box-sizing: border-box; height: 22px; margin: 0; font: inherit; color: var(--text);
  background: var(--surface); border: 1px solid var(--focus); border-radius: 3px; padding: 0 4px; }
.grid-root .grid-input.anl-invalid { border-color: var(--danger); }
/* The refusal of a typed cell sits in a row of its own right under the edited row: the rows below are
   pushed down, so none is covered. The box starts at the edited cell (margin-left is set in the code). */
.grid-root .grid-table tbody tr.grid-error-row { cursor: default; }
.grid-root .grid-table td.grid-error-cell { padding: 2px 0 4px; overflow: visible; white-space: normal; cursor: default;
  text-overflow: clip; }
.grid-root .grid-cell-error { display: block; box-sizing: border-box; width: max-content; min-width: 14em; max-width: min(26em, 100%);
  padding: 2px 6px; white-space: normal; color: var(--danger); background: var(--surface);
  border: 1px solid var(--danger); border-radius: 3px; font-size: var(--fs-xs, 11px); font-weight: 400; text-align: left; }
.grid-root .grid-empty { margin: 0; }
.grid-root .grid-empty, .grid-root .grid-nomatch td { padding: 10px 8px; color: var(--text-dim); }
.grid-root .grid-nomatch td { white-space: normal; text-align: left; cursor: default; }

@container grid (min-width: 50.5em) {
  .grid-root .grid-layout { grid-template-columns: minmax(30em, 1fr) 20em; column-gap: 0.5em;
    grid-template-rows: auto minmax(0, 1fr); grid-template-areas: "toolbar toolbar" "table summary"; }
  .grid-root .grid-summary { display: block; grid-area: summary; min-width: 0; min-height: 0; overflow: auto;
    box-sizing: border-box; padding: 0 0.6em; border: 1px solid var(--border); border-radius: var(--r-sm, 5px);
    background: var(--surface); }
  .grid-root .grid-summary-title { display: block; }
  .grid-root .grid-layout[data-message="1"] .grid-summary-title { display: none; }
  .grid-root .grid-summary-counts { height: auto; white-space: normal; overflow: visible; text-overflow: clip; }
  .grid-root .grid-summary-applied, .grid-root .grid-summary-refused-count { display: block; height: 18px; line-height: 18px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .grid-root .grid-summary-list { max-height: none; }
  .grid-root .grid-summary-refused-count::before { content: none; }
  .grid-root .grid-count { flex: none; }
}
/* the note before any paste is one 18 px line (the 140 px pane shows only that); with room it wraps */
@container grid (min-width: 50.5em) and (min-height: 9em) {
  .grid-root .grid-summary-empty { white-space: normal; height: auto; line-height: 1.4; padding: 2px 0; }
}
/* with room the failure texts are shown whole (they wrap); the sentence is in the summary error, so the
   message line, which repeats it for the status role, steps aside; the title stays. At the short pane both
   stay, one 18 px line each, as the 72 px budget needs. */
@container grid (min-height: 9em) {
  .grid-root .grid-message, .grid-root .grid-summary-error { white-space: normal; height: auto; min-height: 18px;
    overflow: visible; text-overflow: clip; line-height: 1.4; padding: 2px 0; }
  .grid-root .grid-message[data-code] { display: none; }
}
@container grid (min-width: 50.5em) and (min-height: 9em) {
  .grid-root .grid-layout[data-message="1"] .grid-summary-title { display: block; }
}
@container grid (max-width: 50.49em) { .grid-root .grid-hint { display: none; } }
`;

/** What a pasted model cell may say: the four keys and the Quantification tab's names (en and ja), lower case. */
const MODEL_WORDS = (() => {
  const words = new Map();
  for (const key of MODELS) {
    words.set(key, key);
    for (const lang of ['en', 'ja']) {
      const name = quantCat[lang] && quantCat[lang]['quant.model.' + key];
      if (name) words.set(String(name).split(':')[0].trim().toLowerCase(), key);
    }
  }
  return words;
})();

/** The order of the refusals in the summary: by clipboard row, then by column (a row-wide one last). */
const columnRank = (column) => (column === '' ? COLUMNS.length : COLUMNS.indexOf(column));

function isLeaf(node) {
  return !(node && Array.isArray(node.children) && node.children.length);
}

/** A leaf that is not a gate, a transfer or a house event (the Quantification tab's rule). */
function isBasicEvent(node) {
  if (!node || !isLeaf(node)) return false;
  if (String(node.gateType || '').toUpperCase() === 'TRANSFER') return false;
  return String(node.eventKind || '').toLowerCase() !== 'house';
}

function finiteOrNull(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** True for a control that has its own text editing (the shell's isTextEntry test). */
function isTextEntry(target) {
  if (!target || !target.tagName) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (tag === 'INPUT') {
    const kind = String(target.type || 'text').toLowerCase();
    return !['button', 'checkbox', 'radio', 'submit', 'reset', 'range', 'color', 'file', 'image'].includes(kind);
  }
  return false;
}

function readHidden() {
  try {
    const stored = JSON.parse(window.localStorage.getItem(HIDDEN_KEY) || '[]');
    if (!Array.isArray(stored)) return new Set();
    return new Set(stored.filter((key) => COLUMNS.includes(key) && !ALWAYS_SHOWN.includes(key)));
  } catch (_err) {
    return new Set();
  }
}

function writeHidden(hidden) {
  try {
    window.localStorage.setItem(HIDDEN_KEY, JSON.stringify([...hidden]));
  } catch (_err) {
    /* not persisted */
  }
}

export function mount(panel, ctx) {
  ensureStyles();
  injectStyles('fta-grid-tab', CSS);
  const t = translator(ctx);
  const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

  const wrap = el('div', { class: 'anl anl-grid-tab', dataset: { tab: 'grid' } });
  const root = el('div', { class: 'grid-root', dataset: { testid: 'grid-root', state: 'ready' } });
  wrap.appendChild(root);
  panel.appendChild(wrap);

  // ---- state ----------------------------------------------------------------------------
  let active = false;
  let etaShown = null; // whether the ETA notice (not the table) is what the root holds
  let lambdaUnit = readLambdaUnit();
  const hidden = readHidden();
  let sort = null; // {col, dir} dir 1 ascending, -1 descending; null = tree order
  let needle = '';
  let selected = null; // {nodeId, col}
  let editor = null; // {nodeId, col, td, input, original, errorEl}
  let dirty = false; // the store changed while an editor was open
  let visible = COLUMNS.slice(); // visible column keys, in table order
  let order = []; // displayed node ids
  const rowEls = new Map(); // node id -> tr
  const recsById = new Map(); // node id -> row record of the last paint
  let chain = Promise.resolve();
  let seenTree = null;
  let seenAnalysis = null;
  let seenSerial;
  let emptyRows = false;
  let pasting = 0; // pastes queued or running
  let lastPaste = null; // {applied, refused} | {error: {code, key, vars}} | null
  let messageState = null; // {key, vars, code} shown on the message line
  const openJobs = new Set(); // pastes waiting on the chain (DESIGN 5.1: the revision bookkeeping)

  // ---- DOM (rebuilt when the ETA notice gives way to the table) -----------------------------
  let layout;
  let toolbar;
  let filterInput;
  let countEl;
  let colWrap;
  let colButton;
  let colPopover;
  let hiddenSign;
  let hintEl;
  let messageEl;
  let scrollEl;
  let table;
  let colgroup;
  let thead;
  let tbody;
  let emptyEl;
  let summaryEl;
  let titleEl;
  let summaryEmptyEl;
  let countsEl;
  let errorEl;
  let busyEl;
  let listEl;
  let popoverOpen = false;

  const setTid = (node, testid) => {
    node.setAttribute('data-testid', testid);
    return node;
  };

  function buildLayout() {
    clear(root);
    filterInput = setTid(el('input', { type: 'search', class: 'grid-filter', autocomplete: 'off', spellcheck: 'false' }), 'grid-filter');
    filterInput.value = needle;
    countEl = setTid(el('span', { class: 'grid-count' }), 'grid-count');
    colButton = setTid(el('button', { type: 'button', class: 'grid-btn', 'aria-expanded': 'false', 'aria-haspopup': 'true' }), 'grid-columns-button');
    colPopover = setTid(el('div', { class: 'grid-columns-popover', role: 'group', hidden: true }), 'grid-columns-popover');
    colWrap = el('span', { class: 'grid-columns-wrap' }, [colButton, colPopover]);
    hiddenSign = setTid(el('span', { class: 'grid-columns-hidden-count', hidden: true }), 'grid-columns-hidden-count');
    hintEl = setTid(el('span', { class: 'grid-hint', hidden: true }), 'grid-hint');
    toolbar = setTid(el('div', { class: 'anl-toolbar grid-toolbar' }, [filterInput, countEl, colWrap, hiddenSign, hintEl]), 'grid-toolbar');

    messageEl = setTid(el('div', { class: 'grid-line grid-message', role: 'status' }), 'grid-message');
    titleEl = setTid(el('div', { class: 'grid-line grid-summary-title' }), 'grid-summary-title');
    summaryEmptyEl = setTid(el('div', { class: 'grid-line grid-summary-empty' }), 'grid-summary-empty');
    // the counts, the failure and the busy line exist only while they are what the summary says
    errorEl = null;
    busyEl = null;
    countsEl = setTid(el('div', { class: 'grid-line grid-summary-counts', 'aria-live': 'polite' }), 'grid-summary-counts');
    listEl = setTid(el('ol', { class: 'grid-summary-list', hidden: true }), 'grid-summary-refused-list');
    summaryEl = setTid(el('aside', { class: 'grid-summary' }, [messageEl, titleEl, summaryEmptyEl, countsEl, listEl]), 'grid-summary');

    colgroup = el('colgroup');
    thead = el('thead');
    tbody = el('tbody');
    table = setTid(el('table', { class: 'anl-table grid-table', role: 'grid' }, [colgroup, thead, tbody]), 'grid-table');
    emptyEl = setTid(el('p', { class: 'grid-empty', hidden: true }), 'grid-empty');
    scrollEl = setTid(el('div', { class: 'grid-scroll' }, [table, emptyEl]), 'grid-scroll');

    layout = setTid(el('div', { class: 'grid-layout' }, [toolbar, scrollEl, summaryEl]), 'grid-layout');
    root.appendChild(layout);

    filterInput.addEventListener('input', onFilterInput);
    colButton.addEventListener('click', onColumnsButton);
    colWrap.addEventListener('keydown', onPopoverKey);
    colPopover.addEventListener('change', onColumnToggle);
    thead.addEventListener('click', onHeadClick);
    thead.addEventListener('change', onHeadChange);
    tbody.addEventListener('focusin', onCellFocus);
    tbody.addEventListener('dblclick', onCellDoubleClick);
    scrollEl.addEventListener('keydown', onCellKey);
    syncNarrow();
  }

  // ---- the ResizeObserver: data-narrow mirrors the container query -------------------------
  function syncNarrow() {
    const width = root.clientWidth;
    if (!width) return;
    const fontSize = Number(getComputedStyle(root).fontSize.slice(0, -2));
    const narrow = width < 50.5 * fontSize;
    if (narrow !== root.hasAttribute('data-narrow')) {
      if (narrow) root.setAttribute('data-narrow', '');
      else root.removeAttribute('data-narrow');
    }
    updateHint();
  }
  const resizeObserver = typeof ResizeObserver === 'function' ? new ResizeObserver(syncNarrow) : null;
  if (resizeObserver) resizeObserver.observe(root);

  function updateHint() {
    if (!hintEl) return;
    // shown only with a selected cell in a wide pane, and never over an empty grid (nothing to paste into)
    hintEl.hidden = !(selected && !emptyRows && !root.hasAttribute('data-narrow'));
  }

  // ---- strings --------------------------------------------------------------------------
  const colLabel = (col) => t('grid.col.' + col);
  const modelName = (model) => t('quant.model.' + model).split(':')[0];

  function paintStrings() {
    if (etaShown) return;
    filterInput.placeholder = t('grid.filterPlaceholder');
    filterInput.setAttribute('aria-label', t('grid.filterLabel'));
    colButton.textContent = t('grid.columns');
    colButton.title = t('grid.columnsTitle');
    colPopover.setAttribute('aria-label', t('grid.columns'));
    hintEl.textContent = t('grid.hint');
    scrollEl.title = t('grid.hint');
    table.setAttribute('aria-label', t('grid.tableLabel'));
    summaryEl.setAttribute('aria-label', t('grid.summary.title'));
    titleEl.textContent = t('grid.summary.title');
    summaryEmptyEl.textContent = t('grid.summary.empty');
    summaryEmptyEl.title = t('grid.summary.empty');
    clear(colPopover);
    for (const col of COLUMNS) {
      if (ALWAYS_SHOWN.includes(col)) continue;
      const box = setTid(el('input', { type: 'checkbox', dataset: { column: col } }), 'grid-column-toggle');
      box.checked = !hidden.has(col);
      colPopover.appendChild(el('label', null, [box, el('span', { text: colLabel(col) })]));
    }
    paintHiddenSign();
    renderMessage();
    renderSummary();
  }

  function paintHiddenSign() {
    hiddenSign.dataset.count = String(hidden.size);
    hiddenSign.textContent = t('grid.columnsHidden', { n: hidden.size });
    hiddenSign.hidden = hidden.size === 0;
  }

  // ---- the columns chooser ---------------------------------------------------------------
  function onColumnsButton() {
    setPopover(!popoverOpen);
  }

  function setPopover(open) {
    popoverOpen = open;
    colPopover.hidden = !open;
    colButton.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) {
      document.addEventListener('pointerdown', onOutside, true);
      document.addEventListener('focusin', onOutside, true);
      const first = colPopover.querySelector('input');
      if (first) first.focus();
    } else {
      document.removeEventListener('pointerdown', onOutside, true);
      document.removeEventListener('focusin', onOutside, true);
    }
  }

  function onOutside(event) {
    if (!popoverOpen || (event.target instanceof Node && colWrap.contains(event.target))) return;
    setPopover(false); // the click or focus that closed it keeps its own target
  }

  function onPopoverKey(event) {
    if (event.isComposing || event.keyCode === 229) return;
    if (event.key === 'Escape' && popoverOpen) {
      event.preventDefault();
      event.stopPropagation();
      setPopover(false);
      colButton.focus();
    }
  }

  function onColumnToggle(event) {
    const box = event.target;
    if (!(box instanceof HTMLInputElement) || !box.dataset.column) return;
    if (box.checked) hidden.delete(box.dataset.column);
    else hidden.add(box.dataset.column);
    writeHidden(hidden);
    paintHiddenSign();
    if (selected && hidden.has(selected.col)) selected = { nodeId: selected.nodeId, col: 'name' };
    paintHead();
    paintBody();
  }

  // ---- cell values -----------------------------------------------------------------------
  function collectRecs() {
    const tree = ctx.store.tree();
    const out = [];
    if (!tree) return out;
    const stack = [tree];
    const seen = new Set();
    while (stack.length) {
      const node = stack.pop();
      if (!node || typeof node !== 'object') continue;
      const children = Array.isArray(node.children) ? node.children : [];
      if (node !== tree && isBasicEvent(node) && !seen.has(String(node.id))) {
        seen.add(String(node.id));
        const quant = node.quant && typeof node.quant === 'object' ? node.quant : {};
        const trace = node.trace && typeof node.trace === 'object' ? node.trace : {};
        out.push({
          id: String(node.id),
          node,
          index: out.length,
          quant,
          model: MODELS.includes(quant.model) ? quant.model : 'fixed',
          tags: Array.isArray(trace.tags) ? trace.tags.map(String) : [],
          cells: null,
        });
      }
      for (let i = children.length - 1; i >= 0; i -= 1) stack.push(children[i]);
    }
    return out;
  }

  const analysis = () => (ctx.store.state && ctx.store.state.analysis) || {};

  /** What a cell shows: {text, raw, ro, unused, sort, cls, title}. `sort` null = empty (sorts last). */
  function describe(rec, col) {
    const { node, quant, model } = rec;
    switch (col) {
      case 'id':
        return { text: rec.id, raw: rec.id, ro: true, sort: rec.id };
      case 'name': {
        const name = node.name === null || node.name === undefined ? '' : String(node.name);
        return { text: name, raw: name, sort: name };
      }
      case 'model':
        return { text: modelName(model), raw: model, sort: MODELS.indexOf(model) };
      case 'lambda':
      case 'T':
      case 'tau':
      case 'mu': {
        if (!USED[model].includes(col)) {
          return { text: '', raw: '', ro: true, unused: true, sort: null, title: t('grid.unusedTitle') };
        }
        const stored = finiteOrNull(quant[col]);
        if (stored === null) {
          if (col === 'T') {
            return { text: '(' + formatPlain(analysis().missionTime) + ')', raw: '', sort: null, cls: 'grid-dim', title: t('grid.tDefaultTitle') };
          }
          return { text: '', raw: '', sort: null };
        }
        const shown = col === 'lambda' ? stored * LAMBDA_UNITS[lambdaUnit] : stored;
        return { text: formatPlain(shown), raw: String(stored), sort: stored };
      }
      case 'q': {
        const stored = finiteOrNull(node.probability);
        const fixed = model === 'fixed';
        return {
          text: stored === null ? '' : ctx.fmt.prob(stored),
          raw: stored === null ? '' : String(stored),
          ro: !fixed,
          cls: fixed ? '' : 'grid-computed',
          title: fixed ? '' : t('grid.qComputedTitle'),
          sort: stored,
        };
      }
      case 'source': {
        const source = quant.source === null || quant.source === undefined ? '' : String(quant.source);
        return { text: source, raw: source, sort: source };
      }
      default: {
        const tags = rec.tags.join('; ');
        return { text: tags, raw: tags, sort: tags };
      }
    }
  }

  const isEditable = (rec, col) => {
    if (col === 'id') return false;
    if (col === 'q') return rec.model === 'fixed';
    if (['lambda', 'T', 'tau', 'mu'].includes(col)) return USED[rec.model].includes(col);
    return true;
  };

  /** The text an editor starts with: full precision for numbers, never the rounded q. */
  function editorText(rec, col) {
    switch (col) {
      case 'name':
        return rec.node.name === null || rec.node.name === undefined ? '' : String(rec.node.name);
      case 'model':
        return rec.model;
      case 'lambda': {
        const stored = finiteOrNull(rec.quant.lambda);
        return stored === null ? '' : formatPlain(stored * LAMBDA_UNITS[lambdaUnit]);
      }
      case 'T':
      case 'tau':
      case 'mu':
        return formatPlain(rec.quant[col]);
      case 'q':
        return formatPlain(rec.node.probability);
      case 'source':
        return rec.quant.source === null || rec.quant.source === undefined ? '' : String(rec.quant.source);
      default:
        return rec.tags.join('; ');
    }
  }

  // ---- header ----------------------------------------------------------------------------
  function unitOf(col) {
    if (col === 'T' || col === 'tau') return 'h';
    if (col === 'mu') return '/h';
    if (col === 'q') return t('grid.unit.none');
    return '';
  }

  /** The column as the sort button names it: with its unit (λ with the unit picked in its header). */
  function sortLabel(col, label) {
    const unit = col === 'lambda' ? LAMBDA_LABELS[lambdaUnit] : unitOf(col);
    return unit ? label + ' (' + unit + ')' : label;
  }

  function paintHead() {
    visible = COLUMNS.filter((col) => !hidden.has(col));
    clear(colgroup);
    clear(thead);
    const tr = el('tr', { role: 'row' });
    let total = 0;
    for (const col of visible) {
      total += WIDTHS[col];
      colgroup.appendChild(el('col', { style: 'width:' + WIDTHS[col] + 'ch' }));
      const label = colLabel(col);
      const parts = [el('span', { class: 'grid-th-label', text: label })];
      const unit = unitOf(col);
      if (unit) {
        parts.push(setTid(el('span', { class: 'grid-unit', text: '(' + unit + ')', dataset: { column: col } }), 'grid-unit'));
      }
      parts.push(setTid(el('span', { class: 'grid-sort-indicator', 'aria-hidden': 'true', dataset: { column: col } }), 'grid-sort-indicator'));
      const button = setTid(el('button', {
        type: 'button',
        class: 'grid-sort',
        'aria-label': t('grid.sort', { column: sortLabel(col, label) }),
        dataset: { column: col },
      }, parts), 'grid-sort');
      const th = setTid(el('th', { scope: 'col', 'aria-sort': 'none', dataset: { column: col } }, [button]), 'grid-th');
      if (col === 'lambda') {
        const select = setTid(el('select', { class: 'grid-lambda-unit', title: t('grid.lambdaUnit'), 'aria-label': t('grid.lambdaUnit') },
          Object.keys(LAMBDA_UNITS).map((key) => el('option', { value: key, text: LAMBDA_LABELS[key] }))), 'grid-lambda-unit');
        select.value = lambdaUnit;
        th.dataset.unit = lambdaUnit;
        th.appendChild(select);
      } else if (unit) {
        th.dataset.unit = unit;
      }
      tr.appendChild(th);
    }
    thead.appendChild(tr);
    table.style.width = total + 'ch';
    updateSortMarks();
  }

  function updateSortMarks() {
    for (const th of thead.querySelectorAll('th')) {
      const on = Boolean(sort) && sort.col === th.dataset.column;
      th.setAttribute('aria-sort', on ? (sort.dir > 0 ? 'ascending' : 'descending') : 'none');
      const mark = th.querySelector('.grid-sort-indicator');
      if (mark) mark.textContent = on ? (sort.dir > 0 ? '▲' : '▼') : '';
    }
  }

  function onHeadClick(event) {
    const button = event.target instanceof Element ? event.target.closest('.grid-sort') : null;
    if (!button) return;
    const col = button.dataset.column;
    sort = sort && sort.col === col ? { col, dir: -sort.dir } : { col, dir: 1 };
    updateSortMarks();
    paintBody();
  }

  function onHeadChange(event) {
    const select = event.target;
    if (!(select instanceof HTMLSelectElement) || !select.classList.contains('grid-lambda-unit')) return;
    lambdaUnit = Object.prototype.hasOwnProperty.call(LAMBDA_UNITS, select.value) ? select.value : 'h';
    writeLambdaUnit(lambdaUnit);
    const th = select.closest('th');
    if (th) {
      th.dataset.unit = lambdaUnit;
      const button = th.querySelector('.grid-sort');
      if (button) button.setAttribute('aria-label', t('grid.sort', { column: sortLabel('lambda', colLabel('lambda')) }));
    }
    paintBody();
  }

  // ---- body ------------------------------------------------------------------------------
  function paintBody() {
    if (etaShown) return;
    // A repaint would leave an open (refused) editor on detached nodes: close it first.
    // Callers that must keep an open editor defer (dirty) and never get here; this paint
    // covers the dirty flag, so closeEditor must not paint a second time.
    if (editor) {
      dirty = false;
      closeEditor();
    }
    const hadFocus = tbody.contains(document.activeElement);
    const scrollTop = scrollEl.scrollTop;
    const scrollLeft = scrollEl.scrollLeft;
    const all = collectRecs();
    for (const rec of all) {
      rec.cells = {};
      for (const col of visible) rec.cells[col] = describe(rec, col);
    }

    const text = needle.trim().toLowerCase();
    let shown = all;
    if (text) {
      shown = all.filter((rec) => visible.some((col) => rec.cells[col].text.toLowerCase().includes(text)));
    }
    if (sort && visible.includes(sort.col)) {
      const { col, dir } = sort;
      shown = shown.slice().sort((a, b) => {
        const ka = a.cells[col].sort;
        const kb = b.cells[col].sort;
        const emptyA = ka === null || ka === '';
        const emptyB = kb === null || kb === '';
        if (emptyA || emptyB) return emptyA && emptyB ? a.index - b.index : emptyA ? 1 : -1;
        const cmp = typeof ka === 'number' ? ka - kb : collator.compare(ka, kb);
        return cmp === 0 ? a.index - b.index : dir * (cmp < 0 ? -1 : 1);
      });
    }

    recsById.clear();
    for (const rec of all) recsById.set(rec.id, rec);
    rowEls.clear();
    order = shown.map((rec) => rec.id);

    const frag = document.createDocumentFragment();
    for (const rec of shown) {
      const tr = document.createElement('tr');
      tr.setAttribute('role', 'row');
      tr.setAttribute('data-testid', 'grid-row');
      tr.setAttribute('data-node-id', rec.id);
      for (const col of visible) tr.appendChild(makeCell(rec, col));
      rowEls.set(rec.id, tr);
      frag.appendChild(tr);
    }
    if (all.length && !shown.length) {
      const row = document.createElement('tr');
      row.setAttribute('role', 'row');
      const cell = document.createElement('td');
      cell.setAttribute('colspan', String(visible.length));
      cell.setAttribute('data-testid', 'grid-nomatch');
      cell.className = 'grid-nomatch-cell';
      cell.textContent = t('grid.noMatch');
      row.className = 'grid-nomatch';
      row.appendChild(cell);
      frag.appendChild(row);
    }
    tbody.replaceChildren(frag);

    const empty = all.length === 0;
    table.hidden = empty;
    emptyEl.hidden = !empty;
    emptyEl.textContent = empty ? t('quant.tableEmpty') : '';
    emptyRows = empty;
    scrollEl.title = empty ? '' : t('grid.hint'); // no paste hint over an empty grid
    refreshRootState();
    const countText = t('grid.count', { shown: shown.length, total: all.length });
    countEl.textContent = countText;
    countEl.title = countText;
    countEl.dataset.shown = String(shown.length);
    countEl.dataset.total = String(all.length);

    // The selection survives a repaint while its row is still shown.
    if (selected && !(rowEls.has(selected.nodeId) && visible.includes(selected.col))) selected = null;
    markSelected();
    scrollEl.scrollTop = scrollTop;
    scrollEl.scrollLeft = scrollLeft;
    if (hadFocus && selected && !editor) focusSelected();
    updateHint();
  }

  function makeCell(rec, col) {
    const info = rec.cells[col];
    const td = document.createElement('td');
    td.setAttribute('role', 'gridcell');
    td.setAttribute('data-testid', 'grid-cell');
    td.setAttribute('data-node-id', rec.id);
    td.setAttribute('data-column', col);
    td.setAttribute('data-raw', info.raw);
    td.setAttribute('tabindex', '-1');
    td.setAttribute('aria-selected', 'false');
    td.textContent = info.text;
    const classes = [];
    if (NUMERIC.includes(col)) classes.push('num');
    if (info.cls) classes.push(info.cls);
    if (info.ro) {
      classes.push('grid-ro');
      td.setAttribute('data-readonly', 'true');
      td.setAttribute('aria-readonly', 'true');
    }
    if (info.unused) {
      classes.push('grid-unused');
      td.setAttribute('data-unused', 'true');
    }
    if (classes.length) td.className = classes.join(' ');
    const title = info.title || info.text;
    if (title) td.title = title;
    return td;
  }

  // ---- selection ---------------------------------------------------------------------------
  function cellOf(nodeId, col) {
    const tr = rowEls.get(nodeId);
    const index = visible.indexOf(col);
    return tr && index >= 0 ? tr.cells[index] || null : null;
  }

  /** Roving tabindex: the selected cell is the one tab stop; none selected = the first cell. */
  function markSelected() {
    for (const stop of tbody.querySelectorAll('td[tabindex="0"], td[aria-selected="true"]')) {
      stop.setAttribute('tabindex', '-1');
      stop.setAttribute('aria-selected', 'false');
      stop.classList.remove('is-selected-cell');
    }
    const td = selected ? cellOf(selected.nodeId, selected.col) : null;
    if (td) {
      td.setAttribute('tabindex', '0');
      td.setAttribute('aria-selected', 'true');
      td.classList.add('is-selected-cell');
    } else {
      const first = tbody.querySelector('td[data-testid="grid-cell"]');
      if (first) first.setAttribute('tabindex', '0');
    }
  }

  function setSelected(nodeId, col, { focus = false, scroll = false } = {}) {
    selected = { nodeId, col };
    markSelected();
    const td = cellOf(nodeId, col);
    if (td && focus) td.focus({ preventScroll: true });
    if (td && scroll) td.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    updateHint();
  }

  function focusSelected() {
    const td = selected ? cellOf(selected.nodeId, selected.col) : null;
    if (td) td.focus({ preventScroll: true });
  }

  function cellFromEvent(event) {
    return event.target instanceof Element ? event.target.closest('td[data-testid="grid-cell"]') : null;
  }

  function onCellFocus(event) {
    const td = cellFromEvent(event);
    if (!td || td !== event.target) return;
    if (selected && selected.nodeId === td.dataset.nodeId && selected.col === td.dataset.column) return;
    setSelected(td.dataset.nodeId, td.dataset.column);
  }

  function onCellDoubleClick(event) {
    const td = cellFromEvent(event);
    if (td) openEditor(td.dataset.nodeId, td.dataset.column);
    else if (selected) openEditor(selected.nodeId, selected.col);
  }

  function onCellKey(event) {
    if (event.isComposing || event.keyCode === 229) return;
    const td = cellFromEvent(event);
    if (!td || td !== event.target || event.altKey) return;
    const ctrl = event.ctrlKey || event.metaKey;
    const row = order.indexOf(td.dataset.nodeId);
    const colIndex = visible.indexOf(td.dataset.column);
    if (row < 0 || colIndex < 0) return;
    let nextRow = row;
    let nextCol = colIndex;
    switch (event.key) {
      case 'ArrowUp':
        nextRow -= 1;
        break;
      case 'ArrowDown':
        nextRow += 1;
        break;
      case 'ArrowLeft':
        nextCol -= 1;
        break;
      case 'ArrowRight':
        nextCol += 1;
        break;
      case 'Home':
        nextCol = 0;
        if (ctrl) nextRow = 0;
        break;
      case 'End':
        nextCol = visible.length - 1;
        if (ctrl) nextRow = order.length - 1;
        break;
      case 'Enter':
      case 'F2':
        if (ctrl) return;
        event.preventDefault();
        openEditor(td.dataset.nodeId, td.dataset.column);
        return;
      default:
        return;
    }
    event.preventDefault();
    nextRow = Math.max(0, Math.min(order.length - 1, nextRow));
    nextCol = Math.max(0, Math.min(visible.length - 1, nextCol));
    setSelected(order[nextRow], visible[nextCol], { focus: true, scroll: true });
  }

  /**
   * Ctrl+A, Ctrl+D and Ctrl+E would add, delete or edit the selected tree node in the
   * shell; from a cell (not from a text field) they do nothing here. Ctrl+Z, Ctrl+Y, Ctrl+S
   * and Ctrl+F are left to the shell.
   */
  function onRootKey(event) {
    if (event.isComposing || event.keyCode === 229) return;
    if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
    const key = String(event.key || '').toLowerCase();
    if (key !== 'a' && key !== 'd' && key !== 'e') return;
    if (isTextEntry(event.target)) return;
    event.preventDefault();
    event.stopPropagation();
  }
  root.addEventListener('keydown', onRootKey);
  root.addEventListener('paste', onPaste);

  // ---- filter ------------------------------------------------------------------------------
  const applyFilter = debounce(() => {
    needle = filterInput.value;
    if (editor) {
      dirty = true;
      return;
    }
    paintBody();
  }, FILTER_MS);

  function onFilterInput() {
    applyFilter();
  }

  // ---- editing -----------------------------------------------------------------------------
  function openEditor(nodeId, col, { text, error } = {}) {
    if (editor) return false;
    const rec = recsById.get(nodeId);
    const td = cellOf(nodeId, col);
    if (!rec || !td || !isEditable(rec, col)) return false;
    setSelected(nodeId, col);
    const startText = text === undefined ? editorText(rec, col) : text;
    let input;
    if (col === 'model') {
      input = el('select', null, MODELS.map((m) => el('option', { value: m, text: modelName(m) })));
      input.value = rec.model;
    } else {
      input = el('input', { type: 'text', autocomplete: 'off', spellcheck: 'false' });
      if (NUMERIC.includes(col)) input.setAttribute('inputmode', 'decimal');
      input.value = startText;
    }
    input.className = 'grid-input';
    setTid(input, 'grid-input');
    input.setAttribute('aria-label', t('grid.editLabel', { column: colLabel(col), name: rec.node.name || rec.id }));
    editor = { nodeId, col, td, input, original: editorText(rec, col), shown: td.textContent, errorEl: null, errorRow: null };
    td.classList.add('is-editing');
    td.removeAttribute('title');
    td.textContent = '';
    td.appendChild(input);
    input.addEventListener('keydown', onEditorKey);
    input.addEventListener('blur', onEditorBlur);
    input.addEventListener('input', onEditorInput);
    if (col === 'model') input.addEventListener('change', onEditorChange);
    input.focus();
    if (input.select && col !== 'model') input.select();
    if (error) showEditorError(error);
    return true;
  }

  function showEditorError(message) {
    if (!editor) return;
    const { input, td } = editor;
    input.classList.add('anl-invalid');
    input.setAttribute('aria-invalid', 'true');
    input.title = message;
    if (!editor.errorEl) {
      editor.errorEl = setTid(el('span', { class: 'grid-cell-error', role: 'alert' }), 'grid-cell-error');
      const cell = el('td', { class: 'grid-error-cell', colspan: String(visible.length) }, [editor.errorEl]);
      editor.errorRow = el('tr', { class: 'grid-error-row' }, [cell]);
      // keep the focus in the editor when the message is clicked
      editor.errorRow.addEventListener('mousedown', (event) => event.preventDefault());
      td.parentNode.after(editor.errorRow);
    }
    editor.errorEl.textContent = message;
    placeEditorError();
  }

  /** Start the box at the edited cell, kept inside the table's width; bring it into view. */
  function placeEditorError() {
    if (!editor || !editor.errorEl) return;
    const { td, errorEl } = editor;
    // wide enough for its text, never wider than what the scrolling box shows
    const view = scrollEl.clientWidth;
    errorEl.style.maxWidth = 'min(26em, ' + Math.max(80, view - 8) + 'px)';
    errorEl.style.marginLeft = '0px';
    const left = scrollEl.scrollLeft;
    const right = Math.min(table.clientWidth, left + view) - errorEl.offsetWidth - 2;
    errorEl.style.marginLeft = Math.max(0, Math.min(td.offsetLeft, right)) + 'px';
    // the row below the message is what the message must not hide: bring it into sight when the pane has room
    // for the edited row, the message and that row; otherwise the message itself
    const rowBelow = editor.errorRow.nextElementSibling;
    const box = scrollEl.getBoundingClientRect();
    const span = rowBelow ? rowBelow.getBoundingClientRect().bottom - td.getBoundingClientRect().top : Infinity;
    const rect = (rowBelow && span <= box.height ? rowBelow : errorEl).getBoundingClientRect();
    if (rect.bottom > box.bottom) scrollEl.scrollTop += rect.bottom - box.bottom;
    else if (rect.top < box.top) scrollEl.scrollTop -= box.top - rect.top;
  }

  function clearEditorError() {
    if (!editor || !editor.errorEl) return;
    editor.input.classList.remove('anl-invalid');
    editor.input.removeAttribute('aria-invalid');
    editor.input.removeAttribute('title');
    editor.errorRow.remove();
    editor.errorRow = null;
    editor.errorEl = null;
  }

  function onEditorInput() {
    clearEditorError();
  }

  /** Close the editor without sending anything; the cell shows what it showed. */
  function closeEditor() {
    const ed = editor;
    if (!ed) return;
    editor = null;
    ed.input.removeEventListener('blur', onEditorBlur);
    ed.td.classList.remove('is-editing');
    if (ed.errorRow) ed.errorRow.remove();
    ed.td.replaceChildren();
    ed.td.textContent = ed.shown;
    if (ed.shown) ed.td.title = ed.shown;
    if (dirty) {
      dirty = false;
      paintBody();
    }
  }

  /** Read the typed text with the field's own reader -> {ok, value} | {ok: false, message}. */
  function readText(col, typed) {
    if (col === 'model') return { ok: true, value: typed };
    if (col === 'name') {
      const name = sanitizeName(typed);
      return name ? { ok: true, value: name } : { ok: false, message: t('grid.err.nameEmpty') };
    }
    if (col === 'source') return { ok: true, value: typed.trim() === '' ? null : typed };
    if (col === 'tags') {
      const tags = [];
      for (const part of typed.split(TAG_SEPARATORS)) {
        const tag = part.trim();
        if (tag && !tags.includes(tag)) tags.push(tag);
      }
      return { ok: true, value: tags.length ? tags : null };
    }
    if (col === 'q') return parseProbability(typed);
    const { read, bounds } = NUMBER_READERS[col];
    const result = read(typed);
    if (result.ok) return result;
    return { ok: false, message: t(invalidKey(bounds), { min: bounds.min, max: Infinity }) };
  }

  function buildPatch(col, value) {
    switch (col) {
      case 'name':
        return { name: value };
      case 'q':
        return { probability: value };
      case 'tags':
        return { trace: { tags: value } };
      case 'lambda':
        return { quant: { lambda: value === null ? null : value / LAMBDA_UNITS[lambdaUnit] } };
      default:
        return { quant: { [col]: value } };
    }
  }

  /** Commit the open editor. True when it is closed (sent or unchanged), false when the text was refused. */
  function commitEditor() {
    const ed = editor;
    if (!ed) return true;
    const typed = ed.input.value;
    const unchanged = ed.col === 'model' || NUMERIC.includes(ed.col) || ed.col === 'tags'
      ? typed.trim() === ed.original.trim()
      : typed === ed.original;
    if (unchanged) {
      closeEditor();
      return true;
    }
    const result = readText(ed.col, typed);
    if (!result.ok) {
      showEditorError(result.message || '');
      return false;
    }
    closeEditor();
    send(ed.nodeId, ed.col, result.value, typed);
    return true;
  }

  function queue(task) {
    const run = chain.then(task);
    chain = run.then(() => undefined, () => undefined);
    return run;
  }

  /** One PATCH per edit (one undo step), in the order typed. */
  function send(nodeId, col, value, typed) {
    return queue(async () => {
      try {
        const res = await ctx.api.patch('/nodes/' + encodeURIComponent(nodeId), buildPatch(col, value));
        noteOwnWrite(res);
        ctx.store.applyMutation(res);
        if (!editor) revealSelected();
      } catch (err) {
        const message = err && err.message ? err.message : String(err);
        if (!openEditor(nodeId, col, { text: typed, error: message })) {
          reportError(ctx, new Error(t('grid.err.save', { error: message })));
        }
      }
    });
  }

  function moveSideways(step) {
    if (!selected) return;
    const index = visible.indexOf(selected.col) + step;
    if (index < 0 || index >= visible.length) {
      focusSelected();
      return;
    }
    setSelected(selected.nodeId, visible[index], { focus: true, scroll: true });
  }

  function onEditorKey(event) {
    if (event.isComposing || event.keyCode === 229) return;
    if (!editor) return;
    if (event.key === 'Enter') {
      event.preventDefault();
      if (commitEditor()) focusSelected();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      closeEditor();
      focusSelected();
    } else if (event.key === 'Tab') {
      event.preventDefault();
      if (commitEditor()) moveSideways(event.shiftKey ? -1 : 1);
    }
  }

  function onEditorBlur(event) {
    if (!editor || event.target !== editor.input) return;
    commitEditor();
  }

  function onEditorChange() {
    if (commitEditor()) focusSelected();
  }

  function onFlush(event) {
    const detail = event && event.detail;
    if (!detail || !Array.isArray(detail.promises)) return;
    if (editor) commitEditor();
    detail.promises.push(chain);
  }

  // ---- paste -----------------------------------------------------------------------------
  function refreshRootState() {
    if (etaShown) return;
    root.dataset.state = pasting > 0 ? 'pasting' : emptyRows ? 'empty' : 'ready';
    if (pasting > 0) root.setAttribute('aria-busy', 'true');
    else root.removeAttribute('aria-busy');
  }

  function setPasting(delta) {
    pasting = Math.max(0, pasting + delta);
    refreshRootState();
    renderSummary();
  }

  /** Keep the selected cell in sight after an edit moved its row (inside the table box only). */
  function revealSelected() {
    const td = selected && !etaShown ? cellOf(selected.nodeId, selected.col) : null;
    if (!td) return;
    const box = scrollEl.getBoundingClientRect();
    const rect = td.getBoundingClientRect();
    const head = thead.getBoundingClientRect().height;
    if (rect.top < box.top + head) scrollEl.scrollTop -= box.top + head - rect.top;
    else if (rect.bottom > box.bottom) scrollEl.scrollTop += rect.bottom - box.bottom;
  }

  /** The readers of the pasted cells: the fields' own parsers (FN-46); λ is divided by the header unit (FN-51). */
  function buildReaders() {
    const asText = (text) => ({ ok: true, value: text });
    const number = (col, factor) => (text) => {
      const result = NUMBER_READERS[col].read(text);
      if (!result.ok || result.value === null) return { ok: false };
      return { ok: true, value: factor ? result.value / factor : result.value };
    };
    return {
      id: (text) => ({ ok: true, value: text.trim() }),
      name: asText,
      source: asText,
      tags: asText,
      model: (text) => {
        const key = MODEL_WORDS.get(text.trim().toLowerCase());
        return key ? { ok: true, value: key } : { ok: false, code: 'UNKNOWN_MODEL' };
      },
      lambda: number('lambda', LAMBDA_UNITS[lambdaUnit]),
      mu: number('mu'),
      T: number('T'),
      tau: number('tau'),
      q: (text, row) => {
        const result = parseProbability(text);
        if (!result.ok) return { ok: false };
        // equal to the shown q of a computed row after rounding: ignored, neither applied nor refused
        if (row && row.model !== 'fixed' && row.probability !== null && ctx.fmt.prob(result.value) === ctx.fmt.prob(row.probability)) {
          return { ok: true, ignore: true };
        }
        return { ok: true, value: result.value };
      },
    };
  }

  function rowFor(nodeId) {
    const rec = recsById.get(nodeId);
    return rec ? { model: rec.model, probability: finiteOrNull(rec.node.probability) } : { model: 'fixed', probability: null };
  }

  /** The words of one refusal, in the language of the moment (the summary keeps codes, not text). */
  function refusalText(refusal) {
    const text = String(refusal.text === undefined ? '' : refusal.text);
    switch (refusal.code) {
      case 'EXTRA_ROW':
        return t('grid.refuse.extraRow');
      case 'EXTRA_CELLS':
        return t('grid.refuse.extraCells', { n: refusal.n });
      case 'CONTROL_CHAR':
        return t('grid.err.control');
      case 'UNKNOWN_MODEL':
        return t('grid.refuse.model', { value: text.trim() });
      case 'INVALID_CELL': {
        const again = readText(refusal.column, text);
        return again.ok ? '' : again.message || '';
      }
      case 'ID_MISMATCH':
        return t('grid.refuse.idMismatch');
      case 'Q_COMPUTED':
        return t('grid.refuse.qComputed');
      case 'NOT_USED':
        return t('grid.refuse.notUsed', { column: colLabel(refusal.column) });
      case 'NOT_BASIC_EVENT':
        return t('grid.refuse.notBasic');
      case 'INVALID_TEXT':
        return t('grid.refuse.text');
      default:
        return refusal.message || String(refusal.code || '');
    }
  }

  function sortRefusals(list) {
    return list
      .map((item, index) => ({ item, index }))
      .sort((a, b) => a.item.clipRow - b.item.clipRow || columnRank(a.item.column) - columnRank(b.item.column) || a.index - b.index)
      .map((entry) => entry.item);
  }

  /** `{errorKey}` is read again in the current language at each draw; any other `error` text is kept as it came. */
  function withErrorText(vars) {
    if (!vars || (!vars.errorKey && vars.error === undefined)) return vars;
    // the error is followed by "Nothing was applied.": it ends with a full stop of its own (kept) or gets one
    const error = vars.errorKey ? t(vars.errorKey) : vars.error;
    const language = String(document.documentElement.lang || '').toLowerCase() === 'ja' ? 'ja' : 'en';
    return Object.assign({}, vars, { error: endSentence(error, language) });
  }

  function renderMessage() {
    if (!messageEl || !layout) return;
    const text = messageState ? t(messageState.key, withErrorText(messageState.vars)) : '';
    messageEl.textContent = text;
    if (text) messageEl.title = text;
    else messageEl.removeAttribute('title');
    if (text && messageState.code) messageEl.setAttribute('data-code', messageState.code);
    else messageEl.removeAttribute('data-code');
    if (text) layout.setAttribute('data-message', '1');
    else layout.removeAttribute('data-message');
  }

  function showMessage(key, vars, code) {
    messageState = key ? { key, vars, code } : null;
    renderMessage();
  }

  /** The summary beside the grid: busy line, counts and refusals, a whole-paste failure, or the empty note. */
  function renderSummary() {
    if (!summaryEl || etaShown) return;
    const busy = pasting > 0;
    const done = !busy && lastPaste && !lastPaste.error ? lastPaste : null;
    const failed = !busy && lastPaste && lastPaste.error ? lastPaste.error : null;
    summaryEmptyEl.hidden = busy || Boolean(lastPaste);
    if (errorEl) errorEl.remove();
    errorEl = null;
    if (busyEl) busyEl.remove();
    busyEl = null;
    if (busy) {
      busyEl = setTid(el('div', { class: 'grid-line grid-summary-busy', text: t('grid.summary.busy') }), 'grid-summary-busy');
      busyEl.title = busyEl.textContent;
      summaryEl.insertBefore(busyEl, listEl);
    }
    if (failed) {
      const text = t(failed.key, withErrorText(failed.vars));
      errorEl = setTid(el('div', { class: 'grid-line grid-summary-error', role: 'alert', title: text, text, dataset: { code: failed.code } }), 'grid-summary-error');
      summaryEl.insertBefore(errorEl, listEl);
    }
    listEl.hidden = true;
    countsEl.replaceChildren();
    countsEl.removeAttribute('title');
    if (!done) return;
    const rows = new Set(done.refused.map((item) => item.clipRow)).size;
    const appliedEl = setTid(el('span', { class: 'grid-summary-applied', text: t('grid.summary.applied', { n: done.applied }), dataset: { count: String(done.applied) } }), 'grid-summary-applied');
    const refusedEl = setTid(el('span', { class: 'grid-summary-refused-count', text: rows ? t('grid.summary.refused', { n: rows }) : t('grid.summary.none'), dataset: { count: String(rows) } }), 'grid-summary-refused-count');
    countsEl.replaceChildren(appliedEl, refusedEl);
    countsEl.title = appliedEl.textContent + ' | ' + refusedEl.textContent;
    const items = document.createDocumentFragment();
    for (const item of done.refused) {
      const message = refusalText(item);
      const li = setTid(el('li', {
        dataset: { clipRow: String(item.clipRow), column: item.column, code: item.code },
        text: item.column
          ? t('grid.summary.refusedRow', { row: item.clipRow, column: colLabel(item.column), message })
          : t('grid.summary.refusedRowNoCol', { row: item.clipRow, message }),
      }), 'grid-summary-refused-item');
      items.appendChild(li);
    }
    listEl.replaceChildren(items);
    listEl.hidden = done.refused.length === 0;
  }

  /** A whole-paste failure: the summary error and the message line say the same, with the same code. */
  function failWhole(code, key, vars) {
    lastPaste = { error: { code, key, vars } };
    showMessage(key, vars, code);
    renderSummary();
  }

  /**
   * An answer to one of the grid's own writes (an edit or a paste): a paste still waiting must
   * have seen exactly this revision come from it (DESIGN 5.1). Any other revision is a change
   * the grid has not drawn, so that paste is marked foreign and is sent with the revision it was
   * built on, which the server answers with 409.
   */
  function noteOwnWrite(res) {
    if (!res || !Number.isInteger(res.revision)) return;
    for (const job of openJobs) {
      if (res.revision === job.r + 1) job.r = res.revision;
      else if (res.revision !== job.r) job.foreign = true;
    }
  }

  function onPaste(event) {
    if (etaShown || !layout) return;
    const target = event.target;
    if (!(target instanceof Element) || !scrollEl.contains(target) || target.closest('input, select, textarea')) return;
    event.preventDefault();
    showMessage(null);
    if (!selected || !rowEls.has(selected.nodeId) || !visible.includes(selected.col)) {
      showMessage('grid.msg.noAnchor');
      return;
    }
    const data = event.clipboardData;
    const text = data && typeof data.getData === 'function' ? data.getData('text/plain') : '';
    if (!text) {
      showMessage('grid.msg.noText');
      return;
    }
    const rows = parseClipboard(text);
    if (rows.length > MAX_PASTE_ROWS) {
      failWhole('TOO_MANY_ROWS', 'grid.summary.tooMany', { n: rows.length.toLocaleString('en-US') });
      return;
    }
    const plan = planPaste({
      rows,
      anchorRow: order.indexOf(selected.nodeId),
      anchorCol: visible.indexOf(selected.col),
      order: order.slice(),
      columns: visible.slice(),
      rowFor,
      read: buildReaders(),
      numeric: NUMERIC,
    });
    const st = ctx.store.state || {};
    const job = { r0: st.revision, r: st.revision, serial0: st.documentSerial, foreign: false };
    openJobs.add(job);
    setPasting(1);
    queue(() => runPaste(job, plan)).catch((err) => reportError(ctx, err));
  }

  /** One paste, on the chain: after the edits typed before it, before the ones typed after. */
  async function runPaste(job, plan) {
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      openJobs.delete(job);
      setPasting(-1);
    };
    try {
      if (!plan.requestRows.length) {
        lastPaste = { applied: 0, refused: sortRefusals(plan.refused) };
        return;
      }
      const st = ctx.store.state || {};
      // the store's pair only when nothing the grid has not drawn came in since the paste event
      const same = !job.foreign && st.revision === job.r && st.documentSerial === job.serial0;
      const body = {
        revision: same ? st.revision : job.r0,
        documentSerial: same ? st.documentSerial : job.serial0,
        rows: plan.requestRows,
      };
      let res;
      try {
        res = await ctx.api.post('/grid/paste', body);
      } catch (err) {
        openJobs.delete(job);
        const code = err && err.code;
        if (code === 'STALE_REVISION') {
          failWhole(code, 'grid.summary.stale');
          finish();
          try {
            await window.ftaShell.refresh(); // redraw from the current document; nothing was applied
          } catch (_err) {
            /* the next poll or paste will say */
          }
        } else if (code === 'MODE_UNSUPPORTED') {
          failWhole(code, 'grid.summary.eta');
        } else {
          // the server-unreachable text has a catalog key, so it follows a language switch
          const vars = err && err.code === 'NETWORK_ERROR'
            ? { errorKey: 'api.network' }
            : { error: err && err.message ? err.message : String(err) };
          failWhole('PASTE_FAILED', 'grid.summary.failed', vars);
        }
        return;
      }
      openJobs.delete(job);
      noteOwnWrite(res);
      lastPaste = { applied: Number(res.applied) || 0, refused: sortRefusals(plan.refused.concat(Array.isArray(res.refused) ? res.refused : [])) };
      ctx.store.applyMutation(res);
    } finally {
      finish();
    }
  }

  // ---- orchestration -----------------------------------------------------------------------
  function paintAll() {
    const eta = isEta(ctx);
    // a repaint replaces the rows: an editor still open (a refused value) would point at detached nodes
    // and block every later edit, so it closes first (language switch, re-entering the tab, mode change)
    closeEditor();
    if (eta) {
      etaShown = true;
      root.dataset.state = 'eta';
      root.removeAttribute('data-narrow');
      clear(root);
      layout = null;
      root.appendChild(etaNotice(ctx));
      return;
    }
    if (etaShown !== false || !layout) {
      etaShown = false;
      buildLayout();
    }
    paintStrings();
    paintHead();
    paintBody();
  }

  const modeOf = () => {
    try {
      return String(ctx.store.metadata().mode || '').toUpperCase();
    } catch (_err) {
      return '';
    }
  };
  let seenMode = modeOf();

  /** Forget the whole-paste failure "not available in ETA mode" (summary and message line). True when there was one. */
  function dropEtaFailure() {
    let dropped = false;
    if (lastPaste && lastPaste.error && lastPaste.error.code === 'MODE_UNSUPPORTED') {
      lastPaste = null;
      dropped = true;
    }
    if (messageState && messageState.code === 'MODE_UNSUPPORTED') {
      messageState = null;
      dropped = true;
    }
    return dropped;
  }

  function resetForDocument() {
    closeEditor();
    dirty = false;
    needle = '';
    if (filterInput) filterInput.value = '';
    selected = null;
    lastPaste = null;
    messageState = null;
    renderMessage();
    renderSummary();
    updateHint();
  }

  const unsubscribe = ctx.store.subscribe((state) => {
    const tree = state ? state.tree : null;
    const a = state ? state.analysis : null;
    const serial = state ? state.documentSerial : undefined;
    const replaced = seenSerial !== undefined && serial !== seenSerial;
    const changed = tree !== seenTree || a !== seenAnalysis || replaced;
    seenTree = tree;
    seenAnalysis = a;
    seenSerial = serial;
    // "not available in ETA mode" is about the mode the paste met: it goes when the mode or the document
    // changes, also while the tab is away (the next draw then does not bring it back)
    const mode = modeOf();
    const modeChanged = mode !== seenMode;
    seenMode = mode;
    const droppedEta = (modeChanged || replaced) && dropEtaFailure();
    if (!active) return;
    if (replaced) resetForDocument();
    else if (droppedEta && !etaShown && layout) {
      renderMessage();
      renderSummary();
    }
    if (isEta(ctx) !== Boolean(etaShown)) {
      paintAll();
      return;
    }
    if (!changed || etaShown) return;
    if (editor) {
      dirty = true;
      return;
    }
    paintBody();
  });

  const onLanguage = () => {
    if (active) paintAll();
  };
  window.addEventListener('fta:language', onLanguage);
  window.addEventListener('fta:flush', onFlush);
  const unSig = ctx.onSigFigs(() => {
    if (active && !etaShown) paintBody();
  });

  // The skeleton now (the panel is never empty); activate() draws the rows.
  etaShown = false;
  buildLayout();
  paintStrings();
  paintHead();

  return {
    activate() {
      active = true;
      seenTree = ctx.store.state ? ctx.store.state.tree : null;
      seenAnalysis = ctx.store.state ? ctx.store.state.analysis : null;
      seenSerial = ctx.store.state ? ctx.store.state.documentSerial : undefined;
      paintAll();
      syncNarrow();
    },
    deactivate() {
      if (editor) commitEditor();
      if (popoverOpen) setPopover(false);
      active = false;
    },
    onStale() {
      if (!active || etaShown) return;
      if (editor) dirty = true;
      else paintBody();
    },
    dispose() {
      applyFilter.cancel();
      root.removeEventListener('paste', onPaste);
      if (typeof unsubscribe === 'function') unsubscribe();
      if (typeof unSig === 'function') unSig();
      if (resizeObserver) resizeObserver.disconnect();
      if (popoverOpen) setPopover(false);
      window.removeEventListener('fta:language', onLanguage);
      window.removeEventListener('fta:flush', onFlush);
      wrap.remove();
    },
  };
}

export default mount;
