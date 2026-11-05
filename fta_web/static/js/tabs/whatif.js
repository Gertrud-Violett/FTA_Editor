/**
 * tabs/whatif.js -- the What-if tab (F4): "what if this valve fails ten times as often?"
 *
 * The user picks one basic event, moves a logarithmic slider (1/100 to 100) or types a
 * factor, and sees the main parameter, q, the baseline top event, the what-if top event
 * and their ratio, live. Nothing is written to the document: the factors live only in
 * this file (a Map), every request is POST /api/whatif {revision, documentSerial,
 * factors}, and the server keeps nothing. While any factor is not 1 a banner says
 * "What-if values, not saved" and offers Reset per event and Reset all.
 *
 * Resets (FN-58). A change of `revision` or `documentSerial` in the store -- an edit, undo,
 * redo, a mode switch, New, Open, Import, an example, an edit made in another browser tab
 * and loaded by the shell -- sets every factor back to 1; the tab subscribes at mount, so
 * a tab in the background resets too. The server's 409 STALE_REVISION to the next request
 * does the same and asks the shell to read the document again (window.ftaShell.checkServer).
 * A hidden tab sends nothing: it asks once when it is shown again.
 *
 * Requests: one in flight, the newest input is asked for next, a 50 ms trailing debounce (and at
 * least one request every 200 ms during a continuous drag). An answer is applied unless a reset
 * happened since it was sent or the picked event has no row in it; an answer that is only older
 * than the newest input is applied too, so the top event moves while the slider is dragged, and
 * `data-pending` stays 1 until the newest input has been answered.
 */
import cat from '../i18n/whatif.js';
import cat2 from '../i18n/whatifcaution.js';
import { injectStyles } from '../dialogs.js';
import {
  clear,
  el,
  ensureStyles,
  etaNotice,
  formatPlain,
  isEta,
  nodeName,
  numberParser,
  translator,
} from './analysis_common.js';
import { LAMBDA_LABELS, LAMBDA_UNITS, readLambdaUnit } from './quant.js';

window.ftaShell?.registerStrings?.(cat);
window.ftaShell?.registerStrings?.(cat2);

export const id = 'whatif';
export const advanced = true;

const MIN_POS = -200;
const MAX_POS = 200;
/** A decade of the slider, in positions (PageUp / PageDown). */
const DECADE = 100;
const MIN_FACTOR = 0.01;
const MAX_FACTOR = 100;
const DEBOUNCE_MS = 50;
/** A continuous drag still sends a request at least this often. */
const MAX_WAIT_MS = 200;
const PENDING_DOT_MS = 150;
const CHIP_NAME_CH = 16;
const TIMES = '×';
const DASH = '—';
const TICKS = ['1/100', '1/10', '1', '10', '100'];
const UNIT_KEYS = { h: 'per_hour', y: 'per_year', FIT: 'fit' };
/** The caution codes of the server (`cautions` in POST /api/whatif) and the key of the text of each. */
const CAUTION_KEYS = {
  CCF_NOT_APPLIED: 'whatif.caution.ccfNotApplied',
  CCF_Q_ONE: 'whatif.caution.ccfOne',
  CCF_HIGH_Q: 'whatif.caution.ccfHigh',
  STANDBY_LARGE_LT: 'whatif.caution.standby',
  CUTSETS_TRUNCATED: 'whatif.caution.cutsets',
};
/** The limit in a text when an older server sends none: the thresholds of ccf.HIGH_Q and the engine's 0.2. */
const CAUTION_LIMITS = { CCF_HIGH_Q: 0.01, STANDBY_LARGE_LT: 0.2 };

const CSS = `
.anl-whatif { position: relative; gap: 6px; }
.anl-whatif [hidden] { display: none !important; }
.anl-whatif .wi-slot { flex: 0 0 44px; height: 44px; box-sizing: border-box; overflow: hidden; }
.anl-whatif .wi-slot :focus-visible, .anl-whatif .wi-chips :focus-visible { outline-offset: -2px; }
.anl-whatif .wi-banner { box-sizing: border-box; height: 44px; display: grid; grid-template-rows: 20px 20px;
  padding: 2px 8px; background: var(--warn-soft); color: var(--warn); border-radius: var(--r-sm, 5px); min-width: 0; }
.anl-whatif .wi-banner__row { display: flex; align-items: center; gap: 8px; height: 20px; min-width: 0; }
.anl-whatif .wi-banner__text { flex: 1 1 auto; min-width: 0; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.anl-whatif .wi-banner .btn { min-height: 0; height: 20px; padding: 0 6px; font-size: var(--fs-xs, 11px); flex: 0 0 auto; }
.anl-whatif .wi-chips { display: flex; flex-wrap: wrap; align-content: flex-start; gap: 2px 4px; overflow-y: auto; max-height: 20px;
  min-width: 0; scrollbar-width: thin; }
.anl-whatif .wi-chip { display: inline-flex; align-items: center; box-sizing: border-box; height: 20px; padding: 0 2px 0 7px; gap: 3px;
  background: var(--surface); color: var(--text); border: 1px solid var(--border); border-radius: 999px;
  font-size: var(--fs-xs, 11px); white-space: nowrap; max-width: 100%; }
.anl-whatif .wi-chip__name { display: inline-block; max-width: ${CHIP_NAME_CH}ch; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; }
.anl-whatif .wi-chip .btn { min-height: 0; height: 16px; padding: 0 5px; font-size: var(--fs-xs, 11px); border-radius: 999px; }
.anl-whatif .wi-main { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.anl-whatif .wi-controls { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.anl-whatif .wi-row { display: flex; align-items: center; gap: 6px; min-height: 26px; min-width: 0; }
.anl-whatif .wi-label { flex: 0 0 auto; min-width: 6ch; color: var(--text-dim); }
.anl-whatif .wi-row select { flex: 1 1 auto; min-width: 0; height: 26px; min-height: 0; padding: 0 6px; text-overflow: ellipsis; }
.anl-whatif .wi-factor { display: grid; grid-template-columns: minmax(6ch, auto) minmax(0, 1fr) auto 8ch; grid-template-rows: 24px 12px;
  column-gap: 6px; align-items: center; min-width: 0; }
.anl-whatif .wi-factor input[type="range"] { grid-column: 2; grid-row: 1; width: 100%; margin: 0; height: 24px; min-width: 0;
  accent-color: var(--accent); }
.anl-whatif .wi-factor input[type="text"] { grid-column: 4; grid-row: 1; width: 100%; box-sizing: border-box; height: 24px; min-height: 0;
  padding: 0 6px; text-align: right; font-variant-numeric: tabular-nums; }
.anl-whatif .wi-factor .wi-label { grid-column: 1; grid-row: 1; }
.anl-whatif .wi-times { grid-column: 3; grid-row: 1; color: var(--text-dim); }
.anl-whatif .wi-ticks { grid-column: 2; grid-row: 2; position: relative; height: 12px; font-size: 10px; line-height: 12px; color: var(--text-dim); }
.anl-whatif .wi-ticks span { position: absolute; top: 0; transform: translateX(-50%); white-space: nowrap; }
/* The refusal of the field takes the place of the tick labels: the table does not move when it appears. */
.anl-whatif .wi-factor-error { grid-column: 1 / -1; grid-row: 2; margin: 0; text-align: right; color: var(--danger);
  font-size: var(--fs-xs, 11px); line-height: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.anl-whatif .wi-factor.is-invalid .wi-ticks { visibility: hidden; }
.anl-whatif .wi-values { width: 100%; table-layout: fixed; border-collapse: collapse; font-variant-numeric: tabular-nums; }
.anl-whatif .wi-values th, .anl-whatif .wi-values td { padding: 0 6px; line-height: 20px; border-bottom: 1px solid var(--border);
  text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.anl-whatif .wi-values th[scope="row"] { text-align: left; font-weight: 400; color: var(--text-dim); }
.anl-whatif .wi-values thead th { color: var(--text-dim); font-weight: 600; }
.anl-whatif .wi-values col.wi-c0 { width: 35%; }
.anl-whatif .wi-values col.wi-c1 { width: 23%; }
.anl-whatif .wi-values col.wi-c2 { width: 25%; }
.anl-whatif .wi-values col.wi-c3 { width: 17%; }
.anl-whatif .wi-values td.wi-wrap { white-space: normal; }
.anl-whatif .wi-values .unit { margin-left: 1px; color: var(--text-dim); font-size: var(--fs-xs, 11px); }
.anl-whatif .wi-clamped { display: inline-block; margin-left: 4px; padding: 0 5px; border-radius: 999px; font-size: var(--fs-xs, 11px);
  line-height: 16px; background: var(--warn-soft); color: var(--warn); white-space: nowrap; }
.anl-whatif .wi-pending { display: inline-block; width: 6px; height: 6px; margin-left: 5px; border-radius: 50%; background: var(--accent); }
.anl-whatif .wi-notes { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; min-width: 0; }
.anl-whatif td[data-testid="whatif-top-whatif"], .anl-whatif td[data-testid="whatif-ratio"] { font-weight: 700; color: var(--text); }
/* The message and the error line are drawn as a status strip at the bottom edge of the tab, so that they
   are in view without scrolling; empty, the strip has no height. */
.anl-whatif .wi-status { position: sticky; bottom: 0; z-index: 2; display: flex; flex-direction: column; gap: 1px; padding: 1px 0;
  background: var(--surface); border-top: 1px solid var(--border); }
.anl-whatif .wi-status.is-empty { height: 0; padding: 0; border: 0; margin-top: -6px; overflow: hidden; }
/* The caution (X3): a small badge in the empty corner cell of the table head (same 20 px row, nothing moves) and the full
   line in flow under the table (nothing is pinned or overlaid). */
.anl-whatif .wi-values td.wi-corner { text-align: left; }
.anl-whatif .wi-caution-badge { display: flex; align-items: center; gap: 4px; box-sizing: border-box; width: fit-content;
  height: 18px; margin: 1px 0; padding: 0 6px; max-width: 100%; overflow: hidden; white-space: nowrap;
  font: inherit; font-size: var(--fs-xs, 11px); line-height: 16px; font-weight: 600; cursor: pointer;
  color: var(--warn); background: var(--warn-soft); border: 1px solid var(--warn); border-radius: 999px; }
.anl-whatif .wi-caution-badge::before { content: '!'; content: '!' / ''; display: inline-flex; align-items: center; justify-content: center;
  flex: 0 0 auto; box-sizing: border-box; width: 12px; height: 12px; border: 1px solid currentColor; border-radius: 50%;
  font-size: 9px; line-height: 10px; font-weight: 700; }
.anl-whatif .wi-caution-badge:focus-visible, .anl-whatif .wi-caution:focus-visible { outline-offset: -2px; }
.anl-whatif .wi-caution { margin: 0; color: var(--warn); font-size: var(--fs-xs, 11px); line-height: 16px; }
.anl-whatif .wi-message { margin: 0; color: var(--warn); line-height: 16px; font-size: var(--fs-xs, 11px); }
.anl-whatif .wi-message:empty { height: 0; overflow: hidden; }
/* With no banner the message takes the place of the banner: the slot is empty then and the message
   never coexists with a banner (the next factor input clears it). It costs no height. */
.anl-whatif .wi-message--slot { box-sizing: border-box; height: 44px; display: flex; align-items: center; padding: 2px 8px;
  background: var(--warn-soft); color: var(--warn); border-radius: var(--r-sm, 5px); font-size: var(--fs-sm, 12.5px); font-weight: 600; overflow: hidden; }
.anl-whatif .anl-error { margin: 0; line-height: 16px; font-size: var(--fs-xs, 11px); }
`;

function isLeaf(node) {
  return Boolean(node) && !(Array.isArray(node.children) && node.children.length);
}

/** The basic events of the tree in pre-order: a leaf, not the root, not a house event, not a TRANSFER. */
function basicEvents(tree) {
  const out = [];
  const seen = new Set();
  const walk = (node) => {
    if (!node || typeof node !== 'object') return;
    if (node !== tree && isLeaf(node)
      && String(node.gateType || '').toUpperCase() !== 'TRANSFER'
      && String(node.eventKind || '').toLowerCase() !== 'house') {
      const key = String(node.id);
      if (!seen.has(key)) {
        seen.add(key);
        out.push({ id: key, name: node.name ? String(node.name) : key });
      }
    }
    if (Array.isArray(node.children)) for (const child of node.children) walk(child);
  };
  walk(tree);
  return out;
}

/** The slider position of a factor: 100 * log10(f), whole, inside the range. */
export function positionOf(factor) {
  if (!(factor > 0)) return 0;
  const pos = Math.round(100 * Math.log10(factor));
  return Math.max(MIN_POS, Math.min(MAX_POS, pos));
}

/** The factor of a slider position: exactly 1 at 0, four significant digits elsewhere. */
export function factorOfPosition(pos) {
  return pos === 0 ? 1 : Number((10 ** (pos / 100)).toPrecision(4));
}

/** A factor as shown in the field and in the picker: four significant digits. */
function factorText(factor) {
  return String(Number(Number(factor).toPrecision(4)));
}

/** Write a text only when it differs: a live region must not be rewritten with the same words. */
function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

/** Set a data attribute (or remove it with null) only when it differs. */
function setData(node, key, value) {
  if (value === null) {
    if (node.dataset[key] !== undefined) delete node.dataset[key];
  } else if (node.dataset[key] !== value) {
    node.dataset[key] = value;
  }
}

let controlSeq = 0;
function controlId(prefix) {
  controlSeq += 1;
  return prefix + '-' + controlSeq;
}

export function mount(panel, ctx) {
  ensureStyles();
  injectStyles('fta-whatif', CSS);
  const t = translator(ctx);

  // ---- state (DESIGN 2.1) ------------------------------------------------------------------
  const factors = new Map(); // nodeId -> f, only f != 1, as the user set it
  const groups = new Map(); // memberId -> {id, name, members}
  let pickedId = null;
  let seen = { revision: null, documentSerial: null };
  let result = null; // the last accepted response
  let state = 'loading'; // loading | ready | empty | eta | error
  let errorCode = null;
  let message = null; // {code}
  let seqSent = 0;
  let seqApplied = 0;
  let resetSeq = 0;
  let inputSeq = 0;
  let visible = false;
  let needsRefresh = true;
  let disposed = false;
  let timer = null;
  let timerSince = 0;
  let inFlight = false;
  let wantAgain = false;
  let dotTimer = null;
  let lastSelected = null;
  let fieldDirty = false;
  let invalidText = null; // the refusal under the field, or null
  let pickerSig = null;

  const version = () => {
    const st = ctx.store.state || {};
    return { revision: st.revision, documentSerial: st.documentSerial };
  };

  // ---- DOM (built once, updated in place) --------------------------------------------------
  const root = el('section', {
    class: 'anl anl-whatif',
    role: 'region',
    tabindex: '0',
    dataset: { tab: 'whatif', testid: 'whatif-root', state: 'loading', factors: '0', pending: '0', seqSent: '0', seqApplied: '0' },
  });
  const slot = el('div', { class: 'wi-slot', dataset: { testid: 'whatif-banner-slot' } });
  const live = el('div', { class: 'visually-hidden', role: 'status', 'aria-live': 'polite', dataset: { testid: 'whatif-banner-live' } });
  const main = el('div', { class: 'wi-main' });

  const pickerId = controlId('whatif-picker');
  const sliderId = controlId('whatif-slider');
  const pickerLabel = el('label', { class: 'wi-label', for: pickerId });
  const picker = el('select', { id: pickerId, dataset: { testid: 'whatif-picker' } });
  const factorLabel = el('label', { class: 'wi-label', for: sliderId });
  const slider = el('input', { type: 'range', id: sliderId, min: String(MIN_POS), max: String(MAX_POS), step: '1', value: '0', dataset: { testid: 'whatif-slider', factor: '1' } });
  const times = el('span', { class: 'wi-times', 'aria-hidden': 'true', text: TIMES });
  const field = el('input', { type: 'text', inputmode: 'decimal', autocomplete: 'off', dataset: { testid: 'whatif-factor-input' } });
  const ticks = el('div', { class: 'wi-ticks', 'aria-hidden': 'true' }, TICKS.map((label, i) => {
    const span = el('span', { text: label });
    span.style.left = 'calc(8px + (100% - 16px) * ' + i / (TICKS.length - 1) + ')';
    return span;
  }));
  const factorRow = el('div', { class: 'wi-factor' }, [factorLabel, slider, times, field, ticks]);
  const controls = el('div', { class: 'wi-controls', dataset: { testid: 'whatif-controls' } }, [
    el('div', { class: 'wi-row' }, [pickerLabel, picker]),
    factorRow,
  ]);
  let notEvaluableEl = null;
  let factorErrorEl = null;

  const pendingDot = el('span', { class: 'wi-pending', 'aria-hidden': 'true', dataset: { testid: 'whatif-pending' } });
  const colNominal = el('th', { scope: 'col' });
  const colWhatif = el('th', { scope: 'col' });
  const colWhatifText = el('span');
  colWhatif.appendChild(colWhatifText);
  const colRatio = el('th', { scope: 'col' });
  const rowParam = el('th', { scope: 'row' });
  const rowQ = el('th', { scope: 'row' });
  const rowTop = el('th', { scope: 'row' });
  const cell = (testid, extra) => el('td', { dataset: Object.assign({ testid }, extra || {}) });
  const cParamNominal = cell('whatif-param-nominal');
  const cParamWhatif = cell('whatif-param-whatif');
  const cQNominal = cell('whatif-q-nominal');
  const cQWhatif = cell('whatif-q-whatif');
  const cTopBaseline = cell('whatif-top-baseline');
  const cTopWhatif = cell('whatif-top-whatif');
  const cRatio = cell('whatif-ratio');
  // the empty corner cell of the head: it holds the caution badge while a caution shows
  const headCorner = el('td', { class: 'wi-corner' });
  const table = el('table', { class: 'wi-values', dataset: { testid: 'whatif-values' } }, [
    el('colgroup', null, ['wi-c0', 'wi-c1', 'wi-c2', 'wi-c3'].map((c) => el('col', { class: c }))),
    el('thead', null, [el('tr', null, [headCorner, colNominal, colWhatif, colRatio])]),
    el('tbody', null, [
      el('tr', null, [rowParam, cParamNominal, cParamWhatif, el('td')]),
      el('tr', null, [rowQ, cQNominal, cQWhatif, el('td')]),
      el('tr', null, [rowTop, cTopBaseline, cTopWhatif, cRatio]),
    ]),
  ]);
  let groupNoteEl = null;
  const methodEl = el('p', { class: 'anl-note', dataset: { testid: 'whatif-method' }, style: 'margin:0' });
  let cutoffEl = null;
  let incompleteEl = null;
  // the caution: the badge in the head corner and the line under the table, created and removed together
  let cautionBadge = null;
  let cautionEl = null;
  let cautionTextEl = null;
  let cautionRestEl = null;
  const notes = el('div', { class: 'wi-notes', dataset: { testid: 'whatif-notes' } }, [methodEl]);
  main.append(controls, table, notes);

  const messageEl = el('p', { class: 'wi-message', role: 'status', dataset: { testid: 'whatif-message' } });
  const status = el('div', { class: 'wi-status is-empty' }, [messageEl]);
  // What a sighted user sees in the banner slot while there is no banner: a copy of the message, hidden from
  // assistive technology. The live region itself (messageEl) never moves, so that it is announced.
  const messageCopy = el('div', { class: 'wi-message--slot', 'aria-hidden': 'true' });
  let errorEl = null;
  let blockEl = null;
  let blockKind = null;
  let restoreFocusEl = null; // the control that had focus when the controls were hidden
  root.append(slot, live, main, status);
  panel.appendChild(root);

  // ---- factors -------------------------------------------------------------------------------
  function factorOf(nodeId) {
    if (factors.has(nodeId)) return factors.get(nodeId);
    const group = groups.get(nodeId);
    if (group) {
      for (const member of group.members) if (factors.has(member)) return factors.get(member);
    }
    return 1;
  }

  /** A group has one entry: setting a member replaces the entries of all its members. */
  function setFactor(nodeId, factor) {
    const group = groups.get(nodeId);
    // An entry of nodeId itself stays where it is (a Map keeps the place of a key that is set again). That holds
    // for an event on its own and for the member that already holds the group's entry. When another member of
    // the group is set, the entry of the group moves to the end: the old member's entry is deleted and the new
    // one added. A Reset click that starts with the commit of a typed value therefore must not let that commit
    // repaint the chips: onMousedown keeps the field from blurring, and onClick commits it first.
    for (const member of group ? group.members : [nodeId]) if (member !== nodeId || factor === 1) factors.delete(member);
    if (factor !== 1) factors.set(nodeId, factor);
  }

  function rowOf(nodeId) {
    if (!result || !Array.isArray(result.events)) return null;
    return result.events.find((row) => row.id === nodeId) || null;
  }

  // ---- the picker ----------------------------------------------------------------------------
  const selectedBasic = (events) => {
    const sel = ctx.store.selectedId;
    return sel !== null && sel !== undefined && events.some((e) => e.id === String(sel)) ? String(sel) : null;
  };

  /**
   * Pick the event for the picker (DESIGN 2.7): the tree selection when it is a basic event
   * and is new to this tab (or `forceSelection`), else the event already picked while it
   * still exists, else the first basic event. @returns {boolean} true when the pick changed.
   */
  function primePicker(forceSelection = false) {
    const events = basicEvents(ctx.store.tree());
    const before = pickedId;
    const selected = ctx.store.selectedId === undefined ? null : ctx.store.selectedId;
    const bySelection = forceSelection || selected !== lastSelected ? selectedBasic(events) : null;
    lastSelected = selected;
    if (bySelection !== null) pickedId = bySelection;
    else if (pickedId === null || !events.some((e) => e.id === pickedId)) pickedId = events.length ? events[0].id : null;
    return pickedId !== before;
  }

  // ---- requests --------------------------------------------------------------------------------
  const pendingNow = () => timer !== null || inFlight || wantAgain;

  function buildBody() {
    const entries = Array.from(factors.entries());
    if (pickedId !== null && !factors.has(pickedId)) entries.push([pickedId, factorOf(pickedId)]);
    const v = version();
    // fromEntries: an event id such as __proto__ is an own key, not the prototype
    return { revision: v.revision, documentSerial: v.documentSerial, factors: Object.fromEntries(entries) };
  }

  function requestSoon(immediate) {
    if (disposed) return;
    if (!visible) {
      needsRefresh = true;
      return;
    }
    if (immediate) {
      if (timer !== null) clearTimeout(timer);
      timer = null;
      flush();
      return;
    }
    const now = Date.now();
    if (timer === null) timerSince = now;
    else clearTimeout(timer);
    timer = setTimeout(flush, Math.max(0, Math.min(DEBOUNCE_MS, timerSince + MAX_WAIT_MS - now)));
    paintPending();
  }

  function flush() {
    if (timer !== null) clearTimeout(timer);
    timer = null;
    if (disposed) return;
    if (!visible) {
      needsRefresh = true;
      paintPending();
      return;
    }
    if (state === 'eta' || state === 'empty' || pickedId === null) {
      paintPending();
      return;
    }
    if (inFlight) {
      wantAgain = true;
      paintPending();
      return;
    }
    send();
  }

  async function send() {
    const inputAtSend = inputSeq;
    const resetAtSend = resetSeq;
    seqSent += 1;
    const mine = seqSent;
    inFlight = true;
    wantAgain = false;
    paintPending();
    let payload = null;
    let failure = null;
    try {
      payload = await ctx.api.post('/whatif', buildBody());
    } catch (err) {
      failure = err || new Error('what-if request failed');
    }
    inFlight = false;
    if (disposed) return;
    if (resetAtSend === resetSeq) {
      if (failure) {
        // a failure of a request that a newer input has overtaken is not shown: the newer one tells
        if (inputAtSend === inputSeq) handleFailure(failure);
      } else if (pickedId === null || (payload && Array.isArray(payload.events) && payload.events.some((row) => row.id === pickedId))) {
        applyResult(payload, mine);
      }
    }
    if (wantAgain) {
      wantAgain = false;
      flush();
      return;
    }
    paintPending();
  }

  function applyResult(payload, seq) {
    result = payload;
    result.cautions = Array.isArray(payload.cautions) ? payload.cautions : [];
    seqApplied = seq;
    state = 'ready';
    errorCode = null;
    groups.clear();
    for (const group of Array.isArray(payload.groups) ? payload.groups : []) {
      const members = Array.isArray(group.members) ? group.members.map(String) : [];
      for (const member of members) groups.set(member, { id: group.id, name: group.name, members });
    }
    paint();
  }

  function handleFailure(err) {
    const code = err && err.code ? String(err.code) : 'ERROR';
    if (code === 'STALE_REVISION') {
      // Another browser tab changed the document: start again from 1, and ask the shell
      // to read the document (it does so when idle; the store notification then resets
      // once more without touching the message).
      resetAll({ documentChanged: true, code: 'STALE_REVISION', send: false });
      window.ftaShell?.checkServer?.();
      return;
    }
    if (code === 'MODE_UNSUPPORTED') {
      // Another tab switched to an event tree: show the notice, and let the shell read the document.
      state = 'eta';
      paint();
      window.ftaShell?.checkServer?.();
      return;
    }
    state = 'error';
    errorCode = code;
    paint();
  }

  // ---- resets (DESIGN 2.4) ---------------------------------------------------------------------
  function nominalize() {
    if (result) result.cautions = []; // at nominal values nothing is cautioned (the server says [] for factor 1 too)
    if (!result || !Array.isArray(result.events)) return;
    for (const row of result.events) {
      row.param = row.nominalParam;
      row.q = row.nominalQ;
      row.factor = 1;
      row.clamped = Boolean(row.clamped) && Number(row.nominalQ) >= 1;
    }
    result.whatIf = result.baseline;
    result.ratio = result.baseline === null || result.baseline === undefined ? null : 1;
  }

  function resetAll({ documentChanged = false, byUser = false, code = null, send: sendNow = true } = {}) {
    const dropped = factors.size;
    factors.clear();
    resetSeq += 1;
    inputSeq += 1;
    if (timer !== null) clearTimeout(timer);
    timer = null;
    wantAgain = false;
    fieldDirty = false;
    clearInvalid();
    if (documentChanged) {
      if (code) message = { code };
      else if (dropped > 0) message = { code: 'DOCUMENT_CHANGED' };
      result = null;
      groups.clear();
      seen = version();
      errorCode = null;
      primePicker();
      state = isEta(ctx) ? 'eta' : pickedId === null ? 'empty' : 'loading';
    } else {
      message = null;
      leaveError();
      nominalize();
    }
    paint();
    if (state === 'eta' || state === 'empty' || pickedId === null) {
      needsRefresh = false;
    } else if (!sendNow) {
      needsRefresh = true;
    } else if (visible) {
      needsRefresh = false;
      requestSoon(true);
    } else {
      needsRefresh = true;
    }
    if (byUser && !main.hidden) picker.focus();
  }

  // ---- the store (every notification, visible or not) ----------------------------------------
  function syncMode() {
    if (isEta(ctx)) {
      if (state !== 'eta') {
        state = 'eta';
        if (timer !== null) clearTimeout(timer);
        timer = null;
        wantAgain = false;
        resetSeq += 1;
      }
    } else if (state === 'eta') {
      state = pickedId === null ? 'empty' : 'loading';
      result = null;
      needsRefresh = true;
      if (visible && pickedId !== null) requestSoon(true);
    }
  }

  function onStore() {
    if (disposed) return;
    const v = version();
    if (v.revision !== seen.revision || v.documentSerial !== seen.documentSerial) {
      resetAll({ documentChanged: true });
      return;
    }
    syncMode();
    const events = basicEvents(ctx.store.tree());
    let moved = false;
    if (pickedId !== null && !events.some((e) => e.id === pickedId)) {
      moved = primePicker();
    } else if (pickedId === null && events.length) {
      moved = primePicker();
    }
    const selected = ctx.store.selectedId === undefined ? null : ctx.store.selectedId;
    if (visible && selected !== lastSelected) {
      // a basic event picked in the tree moves the picker; a hidden tab takes it when shown
      lastSelected = selected;
      const target = selectedBasic(events);
      if (target !== null && target !== pickedId) {
        pickedId = target;
        moved = true;
      }
    }
    if (events.length === 0 && state !== 'eta') {
      state = 'empty';
      result = null;
    } else if (state === 'empty' && events.length && pickedId !== null) {
      state = 'loading';
      needsRefresh = true;
    }
    if (moved) {
      inputSeq += 1;
      fieldDirty = false;
      clearInvalid();
      if (state !== 'eta' && state !== 'empty') requestSoon(true);
    } else if (visible && needsRefresh && state === 'loading' && pickedId !== null && !pendingNow()) {
      // e.g. after a 409 when the shell found nothing newer: ask again rather than wait
      needsRefresh = false;
      requestSoon(true);
    }
    paint();
  }

  function onDocument() {
    if (disposed) return;
    const v = version();
    if (v.revision !== seen.revision || v.documentSerial !== seen.documentSerial) resetAll({ documentChanged: true });
  }

  // ---- user input ----------------------------------------------------------------------------
  /** The next input retries: the failure of the last attempt is not shown any more. */
  function leaveError() {
    if (state === 'error') {
      state = 'ready';
      errorCode = null;
    }
  }

  function commitFactor(factor, { fromSlider = false } = {}) {
    message = null;
    leaveError();
    setFactor(pickedId, factor);
    inputSeq += 1;
    fieldDirty = false;
    clearInvalid();
    paint({ keepSlider: fromSlider });
    requestSoon(false);
  }

  const parseFactor = numberParser(MIN_FACTOR, { max: MAX_FACTOR, allowBlank: false },
    () => t('quant.invalidRange', { min: String(MIN_FACTOR), max: String(MAX_FACTOR) }));

  function commitField() {
    if (pickedId === null || field.disabled) return false;
    if (!fieldDirty && invalidText === null) {
      // nothing typed since the last commit (Enter has just committed, and blur follows): the value
      // in the field is only the display text, four digits, and must not replace the typed factor
      if (message !== null) {
        message = null;
        paintMessage();
      }
      return true;
    }
    const parsed = parseFactor(field.value);
    if (!parsed.ok) {
      markInvalid(parsed.message);
      return false;
    }
    clearInvalid();
    const factor = parsed.value;
    if (factor === factorOf(pickedId)) {
      message = null;
      fieldDirty = false;
      paint();
      return true;
    }
    commitFactor(factor);
    return true;
  }

  function markInvalid(text) {
    invalidText = text || ' ';
    paintFieldError();
  }

  function clearInvalid() {
    invalidText = null;
    paintFieldError();
  }

  function setPicked(nodeId) {
    if (nodeId === pickedId) return;
    pickedId = nodeId;
    message = null;
    leaveError();
    inputSeq += 1;
    fieldDirty = false;
    clearInvalid();
    paint();
    if (state !== 'eta' && state !== 'empty') requestSoon(true);
  }

  function onSliderInput() {
    if (pickedId === null) return;
    commitFactor(factorOfPosition(Number(slider.value)), { fromSlider: true });
  }

  function onKeydown(event) {
    if (event.isComposing || event.keyCode === 229) return; // IME composition
    if (event.target === field) {
      if (event.key === 'Enter') {
        event.preventDefault();
        if (commitField()) field.blur();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        fieldDirty = false;
        clearInvalid();
        paintControls();
      }
    } else if (event.target === slider && (event.key === 'PageUp' || event.key === 'PageDown')) {
      // One decade; the native step of a range input is 40 positions.
      event.preventDefault();
      if (slider.disabled || pickedId === null) return;
      const step = event.key === 'PageUp' ? DECADE : -DECADE;
      const pos = Math.max(MIN_POS, Math.min(MAX_POS, Number(slider.value) + step));
      slider.value = String(pos);
      commitFactor(factorOfPosition(pos), { fromSlider: true });
    }
  }

  /**
   * A press on a button of the tab while the field holds typed text: the browser would blur the field, the
   * blur would commit the value and repaint the chips before the click arrives, and the click could land on a
   * chip that moved. Keeping the focus where it is lets onClick do the commit first. Text selection in the
   * field and the slider are not buttons and are not touched; the keyboard path (Tab) blurs and commits as before.
   */
  function onMousedown(event) {
    if (fieldDirty && event.target instanceof Element && event.target.closest('button')) event.preventDefault();
  }

  function onClick(event) {
    const button = event.target instanceof Element ? event.target.closest('button') : null;
    if (!button || !root.contains(button)) return;
    const testid = button.dataset.testid;
    if (testid === 'whatif-caution-badge') {
      // read the whole line at once: bring it into view (the least scrolling) and move the focus to it
      if (cautionEl) {
        cautionEl.scrollIntoView({ block: 'nearest' });
        cautionEl.focus({ preventScroll: true });
      }
      return;
    }
    if (testid === 'whatif-reset-all' || testid === 'whatif-reset-event') {
      // a typed value that is not committed yet is committed in the designed order, before the reset; a field
      // that only shows the display text of the current factor (typed and typed back) commits nothing
      if (fieldDirty && field.value !== factorText(factorOf(pickedId))) commitField();
    }
    if (testid === 'whatif-reset-all') {
      resetAll({ byUser: true });
    } else if (testid === 'whatif-reset-event') {
      message = null;
      leaveError();
      setFactor(button.dataset.nodeId, 1);
      resetSeq += 1; // an answer on its way was asked for with this factor: it is from before the reset
      inputSeq += 1;
      fieldDirty = false;
      clearInvalid();
      paint();
      requestSoon(true);
      picker.focus();
    }
  }

  // ---- painting ------------------------------------------------------------------------------
  function paintLabels() {
    root.setAttribute('aria-label', t('whatif.aria'));
    pickerLabel.textContent = t('whatif.event');
    factorLabel.textContent = t('whatif.factor');
    slider.setAttribute('aria-label', t('whatif.factor'));
    slider.title = t('whatif.factorTitle');
    field.setAttribute('aria-label', t('whatif.factor'));
    colNominal.textContent = t('whatif.col.nominal');
    colWhatifText.textContent = t('whatif.col.whatif');
    colRatio.textContent = t('whatif.col.ratio');
    colRatio.title = t('whatif.ratioTitle');
    rowTop.textContent = t('headline.label');
    rowTop.title = t('whatif.baselineTitle');
    rowQ.textContent = t('quant.q');
  }

  function paintState() {
    root.dataset.state = state;
    const hide = !(state === 'ready' || state === 'error');
    if (hide && !main.hidden && main.contains(document.activeElement)) restoreFocusEl = document.activeElement;
    main.hidden = hide;
    const want = state === 'loading' || state === 'empty' || state === 'eta' ? state : null;
    if (blockEl && blockKind !== want) {
      blockEl.remove();
      blockEl = null;
      blockKind = null;
    }
    if (want && !blockEl) {
      blockEl = want === 'eta'
        ? etaNotice(ctx)
        : el('p', { class: 'anl-note', style: 'margin:0; padding:6px 2px' });
      blockEl.dataset.testid = 'whatif-' + want;
      blockKind = want;
      root.insertBefore(blockEl, main);
    }
    if (blockEl) {
      blockEl.textContent = want === 'eta' ? t('anl.eta') : t(want === 'loading' ? 'whatif.loading' : 'whatif.empty');
    }
  }

  function paintPicker() {
    const events = basicEvents(ctx.store.tree());
    const sig = events.map((e) => e.id).join('\u0001');
    if (sig !== pickerSig) {
      clear(picker);
      for (const e of events) picker.appendChild(el('option', { value: e.id }));
      pickerSig = sig;
    }
    events.forEach((e, i) => {
      const f = factorOf(e.id);
      const text = e.name + ' (' + e.id + ')' + (f !== 1 ? ' ' + TIMES + ' ' + factorText(f) : '');
      const option = picker.options[i];
      if (option && option.textContent !== text) option.textContent = text;
    });
    picker.disabled = events.length === 0;
    if (pickedId !== null && picker.value !== pickedId) picker.value = pickedId;
  }

  function paintControls({ keepSlider = false } = {}) {
    const f = pickedId === null ? 1 : factorOf(pickedId);
    const row = pickedId === null ? null : rowOf(pickedId);
    const notEvaluable = Boolean(row) && row.evaluable === false;
    const off = state === 'loading' || state === 'empty' || state === 'eta' || pickedId === null || notEvaluable;
    if (!keepSlider && slider.value !== String(positionOf(f))) slider.value = String(positionOf(f));
    slider.dataset.factor = String(f);
    slider.setAttribute('aria-valuetext', t('whatif.factorValue', { f: factorText(f) }));
    if (!fieldDirty) field.value = factorText(f);
    slider.disabled = off;
    field.disabled = off;
    if (notEvaluable) {
      if (!notEvaluableEl) {
        notEvaluableEl = el('p', { class: 'anl-note', style: 'margin:0', dataset: { testid: 'whatif-not-evaluable' } });
        controls.appendChild(notEvaluableEl);
      }
      notEvaluableEl.textContent = t('whatif.notEvaluable', { name: row.name || nodeName(ctx, pickedId) });
    } else if (notEvaluableEl) {
      notEvaluableEl.remove();
      notEvaluableEl = null;
    }
    paintFieldError();
  }

  function paintFieldError() {
    factorRow.classList.toggle('is-invalid', invalidText !== null);
    if (invalidText === null) {
      if (factorErrorEl) {
        factorErrorEl.remove();
        factorErrorEl = null;
      }
      field.removeAttribute('aria-invalid');
      field.removeAttribute('aria-describedby');
      field.classList.remove('anl-invalid');
      return;
    }
    if (!factorErrorEl) {
      factorErrorEl = el('p', { class: 'wi-factor-error', role: 'alert', id: controlId('whatif-factor-error'), dataset: { testid: 'whatif-factor-error' } });
      factorRow.appendChild(factorErrorEl);
    }
    setText(factorErrorEl, t('quant.invalidRange', { min: String(MIN_FACTOR), max: String(MAX_FACTOR) }));
    field.setAttribute('aria-invalid', 'true');
    field.setAttribute('aria-describedby', factorErrorEl.id);
    field.classList.add('anl-invalid');
  }

  // The banner and its chips are kept across repaints and updated in place, keyed by node id: a click on a
  // Reset button commits a typed value first (onClick) and repaints, and Tab to the button blurs the field,
  // which commits it too; a button replaced in between would never receive its click.
  let bannerEl = null;
  let bannerText = null;
  let resetAllBtn = null;
  let chipList = null;
  const chipEls = new Map(); // nodeId -> {chip, name, factor, button}

  function ensureBanner() {
    if (bannerEl) return;
    bannerText = el('span', { class: 'wi-banner__text', dataset: { testid: 'whatif-banner-text' } });
    resetAllBtn = el('button', { type: 'button', class: 'btn', dataset: { testid: 'whatif-reset-all' } });
    chipList = el('div', { class: 'wi-chips' });
    bannerEl = el('div', { class: 'wi-banner', dataset: { testid: 'whatif-banner' } }, [
      el('div', { class: 'wi-banner__row' }, [bannerText, resetAllBtn]),
      chipList,
    ]);
  }

  function makeChip(nodeId) {
    const name = el('span', { class: 'wi-chip__name' });
    const factor = el('span');
    const button = el('button', { type: 'button', class: 'btn', dataset: { testid: 'whatif-reset-event', nodeId } });
    const chip = el('div', { class: 'wi-chip', role: 'group', dataset: { testid: 'whatif-chip', nodeId } }, [name, factor, button]);
    return { chip, name, factor, button };
  }

  function paintBanner() {
    const entries = Array.from(factors.entries());
    setText(live, entries.length ? t('whatif.banner') : '');
    if (!entries.length) {
      if (bannerEl && bannerEl.parentNode) bannerEl.remove();
      for (const parts of chipEls.values()) parts.chip.remove();
      chipEls.clear();
      return;
    }
    ensureBanner();
    if (bannerEl.parentNode !== slot) slot.appendChild(bannerEl);
    setText(bannerText, t('whatif.banner'));
    setText(resetAllBtn, t('whatif.resetAll'));
    if (resetAllBtn.title !== t('whatif.resetAllTitle')) resetAllBtn.title = t('whatif.resetAllTitle');
    const wanted = new Set(entries.map(([nodeId]) => nodeId));
    for (const [nodeId, parts] of chipEls) {
      if (!wanted.has(nodeId)) {
        parts.chip.remove();
        chipEls.delete(nodeId);
      }
    }
    entries.forEach(([nodeId, factor], i) => {
      let parts = chipEls.get(nodeId);
      if (!parts) {
        parts = makeChip(nodeId);
        chipEls.set(nodeId, parts);
      }
      const name = nodeName(ctx, nodeId);
      const shown = factorText(factor);
      parts.chip.setAttribute('aria-label', name + ' ' + t('whatif.factorValue', { f: shown }));
      setData(parts.chip, 'factor', String(factor));
      setText(parts.name, name);
      if (parts.name.title !== name) parts.name.title = name;
      setText(parts.factor, TIMES + ' ' + shown);
      setText(parts.button, t('whatif.reset'));
      parts.button.setAttribute('aria-label', t('whatif.resetEvent', { name }));
      if (chipList.children[i] !== parts.chip) chipList.insertBefore(parts.chip, chipList.children[i] || null);
    });
  }

  /** Fill one number cell: data-value (raw), data-text (display), data-unit. */
  function setCell(node, number, kind) {
    const has = typeof number === 'number' && Number.isFinite(number);
    node.dataset.value = has ? String(number) : '';
    clear(node);
    if (kind === 'lambda') {
      const unit = readLambdaUnit();
      const text = has ? formatPlain(number * LAMBDA_UNITS[unit]) : DASH;
      node.dataset.param = 'lambda';
      node.dataset.unit = UNIT_KEYS[unit];
      node.dataset.unitLabel = LAMBDA_LABELS[unit];
      node.dataset.text = text;
      node.append(text);
      if (has) node.append(' ', el('span', { class: 'unit', text: LAMBDA_LABELS[unit] }));
      return;
    }
    const text = has ? ctx.fmt.prob(number) : DASH;
    if (kind === 'q') node.dataset.param = 'q';
    else delete node.dataset.param;
    node.dataset.unit = 'none';
    delete node.dataset.unitLabel;
    node.dataset.text = text;
    node.append(text);
  }

  function paintValues() {
    const row = pickedId === null ? null : rowOf(pickedId);
    const lambda = Boolean(row) && row.paramKey === 'lambda';
    const kind = lambda ? 'lambda' : 'q';
    table.dataset.eventId = pickedId === null ? '' : pickedId;
    rowParam.textContent = lambda ? t('quant.lambda') : t('whatif.row.paramQ');
    setCell(cParamNominal, row ? row.nominalParam : null, kind);
    setCell(cParamWhatif, row ? row.param : null, kind);
    setCell(cQNominal, row ? row.nominalQ : null, 'plain');
    setCell(cQWhatif, row ? row.q : null, 'plain');
    cQWhatif.classList.toggle('wi-wrap', Boolean(row && row.clamped));
    if (row && row.clamped) {
      cQWhatif.append(el('span', { class: 'wi-clamped', text: t('whatif.clamped'), dataset: { testid: 'whatif-clamped' } }));
    }
    setCell(cTopBaseline, result ? result.baseline : null, 'plain');
    setCell(cTopWhatif, result ? result.whatIf : null, 'plain');
    setCell(cRatio, result ? result.ratio : null, 'plain');
    const baselineZero = Boolean(result) && result.baseline === 0 && (result.ratio === null || result.ratio === undefined);
    if (baselineZero) cRatio.title = t('whatif.ratioNone');
    else cRatio.removeAttribute('title');
  }

  function paintNotes() {
    const method = result ? result.method : null;
    const groupInfo = pickedId === null ? null : groups.get(pickedId);
    const row = pickedId === null ? null : rowOf(pickedId);
    // the group sentence
    if (row && row.groupId && groupInfo) {
      if (!groupNoteEl) {
        groupNoteEl = el('p', { class: 'anl-note', style: 'margin:0', dataset: { testid: 'whatif-group-note' } });
        main.insertBefore(groupNoteEl, notes);
      }
      groupNoteEl.dataset.groupId = String(row.groupId);
      groupNoteEl.textContent = t('whatif.group', {
        group: groupInfo.name || groupInfo.id,
        members: groupInfo.members.map((member) => nodeName(ctx, member)).join(', '),
      });
    } else if (groupNoteEl) {
      groupNoteEl.remove();
      groupNoteEl = null;
    }
    // method, cutoff note, incomplete note
    methodEl.hidden = !(method === 'mcub' || method === 'treeWalk');
    if (!methodEl.hidden) {
      methodEl.dataset.method = method;
      methodEl.textContent = t(method === 'mcub' ? 'whatif.method.mcub' : 'whatif.method.treeWalk');
    }
    const note = result && result.note ? String(result.note) : null;
    if (note === 'cutsets_from_nominal') {
      if (!cutoffEl) {
        cutoffEl = el('span', { class: 'anl-badge anl-badge--info', dataset: { testid: 'whatif-cutoff-note' } });
        notes.appendChild(cutoffEl);
      }
      cutoffEl.dataset.note = note;
      cutoffEl.textContent = t('whatif.cutoffNote');
      cutoffEl.title = t('whatif.cutoffTitle');
    } else if (cutoffEl) {
      cutoffEl.remove();
      cutoffEl = null;
    }
    if (method === 'incomplete') {
      if (!incompleteEl) {
        incompleteEl = el('p', { class: 'anl-note', style: 'margin:0', dataset: { testid: 'whatif-incomplete-note' } });
        notes.appendChild(incompleteEl);
      }
      incompleteEl.textContent = t('whatif.incomplete');
    } else if (incompleteEl) {
      incompleteEl.remove();
      incompleteEl = null;
    }
  }

  /** The cautions of the answer on screen, in server order: none without a factor (the server says [] too), and none
   *  while there is no answer to show (loading, empty, ETA). The stale answer of an error keeps its cautions. */
  function activeCautions() {
    if (!(state === 'ready' || state === 'error') || !result || factors.size === 0) return [];
    return (Array.isArray(result.cautions) ? result.cautions : []).filter((c) => c && typeof c.code === 'string');
  }

  function cautionText(entry) {
    const key = CAUTION_KEYS[entry.code];
    if (!key) return null; // a code this tab does not know: not shown (it stays in data-codes)
    const limit = entry.limit !== undefined && entry.limit !== null ? entry.limit : CAUTION_LIMITS[entry.code];
    return t(key, { limit: String(limit) });
  }

  function removeCaution() {
    // when the badge or the line has the focus, it goes to the picker (not to the page body)
    const active = document.activeElement;
    const hadFocus = Boolean(active) && ((cautionBadge && active === cautionBadge) || (cautionEl && cautionEl.contains(active)));
    if (cautionBadge) {
      cautionBadge.remove();
      cautionBadge = null;
    }
    if (cautionEl) {
      cautionEl.remove();
      cautionEl = null;
      cautionTextEl = null;
      cautionRestEl = null;
    }
    if (hadFocus && !picker.disabled) picker.focus();
  }

  /**
   * The caution badge (head corner) and line (under the table): the text of the first caution, plus "(and N more)"
   * for the others, which the hidden span and the badge title carry in full. Updated in place so that a repaint
   * never takes the focus away from the line; both are removed when no caution shows.
   */
  function paintCaution() {
    const list = activeCautions();
    const items = list.map((entry) => ({ code: entry.code, text: cautionText(entry) })).filter((item) => item.text !== null);
    if (!items.length) {
      removeCaution();
      return;
    }
    const k = items.length;
    // one space before the suffix, none before a full-width one ("。（ほか N 件）")
    const more = k > 1 ? t('whatif.caution.more', { n: String(k - 1) }) : '';
    const visible = k > 1 ? items[0].text + (more.startsWith('（') ? '' : ' ') + more : items[0].text;
    const all = items.map((item) => item.text).join('\n');
    if (!cautionEl) {
      cautionTextEl = el('span', { dataset: { testid: 'whatif-caution-text' } });
      cautionEl = el('p', { class: 'wi-caution anl-note', tabindex: '-1', id: controlId('whatif-caution'), dataset: { testid: 'whatif-caution' } }, [cautionTextEl]);
      cautionBadge = el('button', { type: 'button', class: 'wi-caution-badge', dataset: { testid: 'whatif-caution-badge' } });
    }
    if (cautionEl.previousSibling !== table) main.insertBefore(cautionEl, table.nextSibling);
    if (cautionBadge.parentNode !== headCorner) headCorner.appendChild(cautionBadge);
    setText(cautionTextEl, visible);
    if (k > 1) {
      if (!cautionRestEl) {
        cautionRestEl = el('span', { class: 'visually-hidden', dataset: { testid: 'whatif-caution-rest' } });
        cautionEl.appendChild(cautionRestEl);
      }
      setText(cautionRestEl, items.slice(1).map((item) => item.text).join(' '));
    } else if (cautionRestEl) {
      cautionRestEl.remove();
      cautionRestEl = null;
    }
    setData(cautionEl, 'codes', list.map((entry) => entry.code).join(','));
    setData(cautionEl, 'count', String(k));
    setText(cautionBadge, t('whatif.caution.badge'));
    setData(cautionBadge, 'count', String(k));
    if (cautionBadge.title !== all) cautionBadge.title = all;
    if (cautionBadge.getAttribute('aria-describedby') !== cautionEl.id) {
      cautionBadge.setAttribute('aria-describedby', cautionEl.id);
      cautionBadge.setAttribute('aria-controls', cautionEl.id);
    }
  }

  function paintMessage() {
    // While there is no banner the message is drawn in the banner slot (messageCopy) and the live region
    // is visually hidden; with a banner it would show in the status strip.
    const inSlot = Boolean(message) && factors.size === 0;
    setData(messageEl, 'code', message ? message.code : null);
    setText(messageEl, message ? t('whatif.stale') : '');
    messageEl.classList.toggle('visually-hidden', inSlot);
    if (inSlot) {
      setText(messageCopy, t('whatif.stale'));
      if (messageCopy.parentNode !== slot) slot.appendChild(messageCopy);
    } else if (messageCopy.parentNode) {
      messageCopy.remove();
    }
    if (state === 'error') {
      if (!errorEl) {
        errorEl = el('p', { class: 'anl-error', role: 'alert', dataset: { testid: 'whatif-error' } });
        status.appendChild(errorEl);
      }
      setData(errorEl, 'code', errorCode || 'ERROR');
      setText(errorEl, t('whatif.failed', { error: errorCode || 'ERROR' }));
    } else if (errorEl) {
      errorEl.remove();
      errorEl = null;
    }
    status.classList.toggle('is-empty', !(message && !inSlot) && !errorEl);
  }

  function paintAttrs() {
    const d = root.dataset;
    d.factors = String(factors.size);
    if (result && result.method) d.method = String(result.method);
    else delete d.method;
    if (result && result.note) d.note = String(result.note);
    else delete d.note;
    const cautionCodes = activeCautions().map((entry) => entry.code).join(',');
    if (cautionCodes) d.cautions = cautionCodes;
    else delete d.cautions;
    if (result && result.revision !== undefined) d.revision = String(result.revision);
    else delete d.revision;
    paintPending();
  }

  function paintPending() {
    const pending = pendingNow();
    root.dataset.pending = pending ? '1' : '0';
    root.dataset.seqSent = String(seqSent);
    root.dataset.seqApplied = String(seqApplied);
    if (pending) {
      table.setAttribute('aria-busy', 'true');
      if (dotTimer === null && !pendingDot.isConnected) {
        dotTimer = setTimeout(() => {
          dotTimer = null;
          if (pendingNow()) colWhatif.appendChild(pendingDot);
        }, PENDING_DOT_MS);
      }
    } else {
      table.removeAttribute('aria-busy');
      if (dotTimer !== null) clearTimeout(dotTimer);
      dotTimer = null;
      pendingDot.remove();
    }
  }

  function paint(options) {
    if (disposed) return;
    paintLabels();
    paintState();
    paintPicker();
    paintControls(options);
    paintBanner();
    paintValues();
    paintNotes();
    paintCaution();
    paintMessage();
    paintAttrs();
    restoreFocus();
  }

  /**
   * A document-change reset hides the controls while the answer is on its way; the control that had
   * focus gets it back when they return, but only if nothing else took it meanwhile (a reset never
   * moves focus away from where the user is typing).
   */
  function restoreFocus() {
    if (!restoreFocusEl || main.hidden) return;
    const previous = restoreFocusEl;
    restoreFocusEl = null;
    const active = document.activeElement;
    if ((!active || active === document.body) && previous.isConnected && !previous.disabled) previous.focus();
  }

  // ---- wiring --------------------------------------------------------------------------------
  root.addEventListener('keydown', onKeydown);
  root.addEventListener('click', onClick);
  root.addEventListener('mousedown', onMousedown);
  slider.addEventListener('input', onSliderInput);
  field.addEventListener('input', () => {
    fieldDirty = true;
    if (invalidText !== null) clearInvalid();
  });
  field.addEventListener('change', () => {
    commitField();
  });
  picker.addEventListener('change', () => setPicked(picker.value || null));
  const onLanguage = () => paint();
  window.addEventListener('fta:language', onLanguage);
  window.addEventListener('fta:document', onDocument);
  const unSig = ctx.onSigFigs(() => paintValues());

  seen = version();
  primePicker(true);
  state = isEta(ctx) ? 'eta' : pickedId === null ? 'empty' : 'loading';
  const unsubscribe = ctx.store.subscribe(onStore);
  paint();

  return {
    activate() {
      visible = true;
      syncMode();
      const moved = primePicker();
      if (state !== 'eta' && pickedId === null) state = 'empty';
      if (moved) {
        inputSeq += 1;
        fieldDirty = false;
        clearInvalid();
      }
      paint();
      if (state === 'eta' || state === 'empty' || pickedId === null) return;
      if (needsRefresh || !result || moved) {
        needsRefresh = false;
        requestSoon(true);
      }
    },
    deactivate() {
      visible = false;
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
        needsRefresh = true;
      }
      paintPending();
    },
    onStale() {
      paint();
    },
    dispose() {
      disposed = true;
      if (timer !== null) clearTimeout(timer);
      if (dotTimer !== null) clearTimeout(dotTimer);
      window.removeEventListener('fta:language', onLanguage);
      window.removeEventListener('fta:document', onDocument);
      if (typeof unSig === 'function') unSig();
      if (typeof unsubscribe === 'function') unsubscribe();
      root.remove();
    },
  };
}

export default mount;
