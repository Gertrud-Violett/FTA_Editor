/**
 * tabs/fmea.js -- the FMEA import tab (1.7, workstream C).
 *
 * 1. File: "Choose file…" opens the server-side file dialog
 *    (ctx.pickPath({mode: 'open', extensions: ['.csv', '.xlsx']})); a path can
 *    also be typed. POST /api/fmea/preview {path, sheet?} returns the sheet
 *    names, columns, the first 50 rows and a suggested column mapping.
 * 2. Columns: one select per import field, pre-filled from the suggestion.
 * 3. Target and values: the parent node (default: the selected node), the λ
 *    unit, "update existing rows", and the editable occurrence-rank ->
 *    probability table (the document's analysis.fmeaOccurrenceTable, with a
 *    reset to the AIAG default). Import sends POST /api/fmea/import; the
 *    server makes it one undo step and saves an edited table into the
 *    document in that same step.
 *
 * The result lists created/updated/unchanged counts and every skipped row
 * with its reason, and highlights the imported nodes in the tree and diagram
 * (ctx.highlight(ids, 'fmea')).
 */
import { clear, el, injectStyles } from '../dialogs.js';
import strings from '../i18n/fmea.js';

export const id = 'fmea';
export const advanced = true;

const FIELDS = Object.freeze([
  'id', 'item', 'mode', 'cause', 'severity', 'occurrence', 'detection', 'rpn', 'lambda',
]);
const KEY_FIELDS = Object.freeze(['id', 'item', 'mode']);
const UNITS = Object.freeze(['h', 'y', 'FIT']);
const RANKS = Object.freeze(['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']);
const MAX_SKIPPED_SHOWN = 200;

/** Mirrors engine.AIAG_OCCURRENCE_TABLE; the server's copy wins once previewed. */
const AIAG_DEFAULT = Object.freeze({
  1: 1e-7, 2: 1e-6, 3: 1e-5, 4: 1e-4, 5: 5e-4, 6: 2e-3, 7: 1e-2, 8: 2e-2, 9: 5e-2, 10: 1e-1,
});

const TEMPLATE_CSV =
  '﻿FMEA ID,Item,Failure Mode,Cause,Severity,Occurrence,Detection,RPN,Failure rate (/h)\r\n' +
  'F-001,Pump,Fails to start,Motor winding burnout,8,3,4,96,1.0e-6\r\n' +
  'F-002,Relief valve,Stuck closed,Corrosion,9,2,5,90,\r\n' +
  'F-003,Pressure sensor,No output,Connector fretting,6,4,3,72,5.0e-7\r\n';

const CSS = `
.fmea-tab { display: flex; flex-direction: column; gap: 0.6rem; font-size: 0.85rem; color: var(--fta-fg); }
.fmea-intro, .fmea-hint { margin: 0; color: var(--fta-muted-fg); font-size: 0.8rem; }
.fmea-section { border: 1px solid var(--fta-border); border-radius: var(--fta-radius); padding: 0.5rem 0.6rem;
  display: flex; flex-direction: column; gap: 0.45rem; background: var(--fta-surface); }
.fmea-section h3 { margin: 0; font-size: 0.85rem; font-weight: 600; }
.fmea-row { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem 0.6rem; }
.fmea-tab input[type="text"], .fmea-tab select {
  font: inherit; color: var(--fta-fg); background: var(--fta-surface); border: 1px solid var(--fta-border);
  border-radius: var(--fta-radius); padding: 0.15rem 0.35rem; }
.fmea-tab input.is-invalid { border-color: var(--fta-danger-fg); background: var(--fta-danger-bg); }
.fmea-path { flex: 1 1 18rem; min-width: 12rem; }
.fmea-tab button { font: inherit; cursor: pointer; color: var(--fta-fg); background: var(--fta-surface-2, var(--fta-surface));
  border: 1px solid var(--fta-border); border-radius: var(--fta-radius); padding: 0.2rem 0.65rem; }
.fmea-tab button:not(.fmea-primary):hover:not(:disabled) { background: var(--fta-surface-hover, var(--fta-surface)); }
.fmea-tab button.fmea-primary:hover:not(:disabled) { filter: brightness(1.1); }
.fmea-tab button:disabled { opacity: 0.55; cursor: default; }
.fmea-tab button.fmea-primary { background: var(--fta-accent); color: var(--fta-accent-fg, #fff); border-color: var(--fta-accent); }
.fmea-tab a.fmea-template { color: var(--fta-accent); cursor: pointer; }
.fmea-msg { margin: 0; font-size: 0.8rem; }
.fmea-msg.is-error { color: var(--fta-danger-fg); }
.fmea-msg.is-busy { color: var(--fta-muted-fg); }
.fmea-msg.is-warn { color: var(--fta-warn-fg, #9a5d00); }
.fmea-preview { max-height: 14rem; overflow: auto; border: 1px solid var(--fta-border); border-radius: var(--fta-radius); }
.fmea-preview table, .fmea-occ table { border-collapse: collapse; }
.fmea-preview th, .fmea-preview td, .fmea-occ th, .fmea-occ td { border-bottom: 1px solid var(--fta-border);
  padding: 0.15rem 0.45rem; text-align: left; white-space: nowrap; }
.fmea-preview th { position: sticky; top: 0; background: var(--fta-surface-2, var(--fta-surface)); }
.fmea-preview th.is-mapped { color: var(--fta-accent); }
.fmea-preview td.fmea-rowno { color: var(--fta-muted-fg); }
.fmea-map { display: grid; grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr)); gap: 0.35rem 0.8rem; }
.fmea-map label { display: flex; align-items: center; justify-content: space-between; gap: 0.4rem; }
.fmea-map select { max-width: 10rem; }
.fmea-columns { display: flex; flex-wrap: wrap; gap: 0.8rem; align-items: flex-start; }
.fmea-options { display: flex; flex-direction: column; gap: 0.45rem; flex: 1 1 18rem; }
.fmea-options label { display: inline-flex; align-items: center; gap: 0.4rem; }
.fmea-parent { max-width: 24rem; }
.fmea-occ { display: flex; flex-direction: column; gap: 0.35rem; }
.fmea-occ h3 { margin: 0; font-size: 0.85rem; font-weight: 600; }
.fmea-occ-grid { display: grid; grid-template-columns: repeat(5, auto); gap: 0.3rem 0.6rem; justify-content: start; }
.fmea-occ-cell { display: inline-flex; align-items: center; gap: 0.3rem; }
.fmea-occ-rank { min-width: 1.4rem; text-align: right; color: var(--fta-muted-fg); font-variant-numeric: tabular-nums; }
.fmea-occ input { width: 5.6rem; }
.fmea-result { display: flex; flex-direction: column; gap: 0.35rem; }
.fmea-skipped { margin: 0; padding-left: 1.2rem; max-height: 10rem; overflow: auto; }
.fmea-skipped li { margin: 0.1rem 0; }
`;

/** Divide a λ typed in this unit by the divisor to get a rate per hour. */
const UNIT_DIVISOR = Object.freeze({ h: 1, y: 8760, FIT: 1e9 });
/** A failure rate above this (per hour) is almost certainly in the wrong unit. */
export const LAMBDA_HIGH_PER_HOUR = 1e-2;

/** A preview cell as a number (numbers, '1.0e-6', ' 120 ', '1,5'), else NaN. */
export function cellNumber(value) {
  if (typeof value === 'number') return value;
  const text = String(value === null || value === undefined ? '' : value).trim().replace(',', '.');
  if (!text) return NaN;
  const num = Number(text);
  return Number.isFinite(num) ? num : NaN;
}

/**
 * Plausibility of the chosen λ unit for the mapped λ values (the preview rows).
 * Returns {high, differs}: high = {max, perHour, suggest} when the largest
 * value converted with the chosen unit exceeds LAMBDA_HIGH_PER_HOUR (suggest: FIT for
 * values >= 1, else /y; null when that is already the unit), differs = the
 * server's suggested unit when it is not the chosen one. Advisory only: the
 * import is never blocked (120 FIT stored as 120/h gives q = 1 silently).
 */
export function lambdaUnitCheck(values, unit, suggested) {
  const nums = (values || []).map(cellNumber).filter((v) => Number.isFinite(v) && v > 0);
  const divisor = UNIT_DIVISOR[unit] || 1;
  let high = null;
  if (nums.length) {
    const max = Math.max(...nums);
    const perHour = max / divisor;
    if (perHour > LAMBDA_HIGH_PER_HOUR) {
      const guess = max >= 1 ? 'FIT' : 'y';
      high = { max, perHour, suggest: guess === unit ? null : guess };
    }
  }
  const differs = suggested && UNIT_DIVISOR[suggested] && suggested !== unit ? suggested : null;
  return { high, differs };
}

function registerStrings() {
  const shell = window.ftaShell;
  if (shell && typeof shell.registerStrings === 'function') shell.registerStrings(strings);
}

function cellText(value) {
  return value === null || value === undefined ? '' : String(value);
}

export function mount(panel, ctx) {
  registerStrings();
  injectStyles('fta-fmea-css', CSS);
  const t = (key, vars) => (ctx && typeof ctx.t === 'function' ? ctx.t(key, vars) : key);
  const store = ctx.store;

  const state = {
    path: '',
    preview: null, // /fmea/preview payload
    sheet: null,
    mapping: {},
    lambdaUnit: 'h',
    parentId: null,
    parentExplicit: false,
    update: true,
    occTouched: false,
    occ: { ...AIAG_DEFAULT },
    occDefault: { ...AIAG_DEFAULT },
    occInvalid: new Set(),
    busy: false,
    message: null, // {text, kind}
    result: null,
  };

  const root = el('div', { class: 'fmea-tab' });
  panel.appendChild(root);

  /* ---- helpers ---- */
  function setMessage(text, kind) {
    state.message = text ? { text, kind: kind || null } : null;
    paintMessage();
  }

  let messageEl = null;
  function paintMessage() {
    if (!messageEl) return;
    messageEl.textContent = state.message ? state.message.text : '';
    messageEl.className = 'fmea-msg' + (state.message && state.message.kind ? ' is-' + state.message.kind : '');
    messageEl.hidden = !state.message;
  }

  function errorText(err) {
    const code = err && err.code;
    if (code === 'EXPORT_UNAVAILABLE') return t('fmea.noOpenpyxl');
    if (code === 'MODE_UNSUPPORTED') return t('fmea.etaMode');
    return err && err.message ? err.message : String(err);
  }

  function parentCandidates() {
    let flat = [];
    try {
      flat = store.flat() || [];
    } catch (_err) {
      flat = [];
    }
    return flat.filter((entry) => {
      const node = entry.node || {};
      return String(node.gateType || '').toUpperCase() !== 'TRANSFER';
    });
  }

  function defaultParent() {
    const ids = parentCandidates().map((e) => e.id);
    const sel = store.selectedId === null || store.selectedId === undefined ? null : String(store.selectedId);
    // The user's own pick sticks; until then the target follows the selection.
    if (state.parentExplicit && state.parentId && ids.includes(state.parentId)) return state.parentId;
    if (sel && ids.includes(sel)) return sel;
    return ids[0] || null;
  }

  function keyMapped() {
    return KEY_FIELDS.some((f) => state.mapping[f]);
  }

  /* ---- file ---- */
  async function choose() {
    const path = await ctx.pickPath({
      mode: 'open',
      extensions: ['.csv', '.xlsx'],
      title: t('fmea.chooseTitle'),
    });
    if (path) await loadPreview(path, null, true);
  }

  async function loadPreview(path, sheet, fresh) {
    const target = String(path || '').trim();
    if (!target) return;
    state.busy = true;
    setMessage(t('fmea.loading'), 'busy');
    try {
      const body = { path: target };
      if (sheet) body.sheet = sheet;
      const res = await ctx.api.post('/fmea/preview', body);
      state.path = res.path || target;
      state.preview = res;
      state.sheet = res.sheet || null;
      state.mapping = { ...(res.suggestedMapping || {}) };
      state.lambdaUnit = UNITS.includes(res.suggestedLambdaUnit) ? res.suggestedLambdaUnit : 'h';
      if (fresh || !state.occTouched) {
        state.occ = { ...(res.occurrenceTable || AIAG_DEFAULT) };
        state.occInvalid = new Set();
      }
      if (res.defaultOccurrenceTable) state.occDefault = { ...res.defaultOccurrenceTable };
      state.result = null;
      state.message = null;
    } catch (err) {
      state.message = { text: errorText(err), kind: 'error' };
    } finally {
      state.busy = false;
      renderAll();
    }
  }

  function downloadTemplate(event) {
    if (event) event.preventDefault();
    const blob = new Blob([TEMPLATE_CSV], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = el('a', { href: url, download: 'fmea_template.csv' });
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  /* ---- import ---- */
  let importButton = null;
  function refreshImportButton() {
    if (!importButton) return;
    importButton.disabled =
      state.busy || !state.preview || !keyMapped() || state.occInvalid.size > 0 || !defaultParent();
    importButton.textContent = state.busy ? t('fmea.importing') : t('fmea.import');
  }

  async function runImport() {
    if (!state.preview || !keyMapped() || state.occInvalid.size) return;
    const parentId = defaultParent();
    if (!parentId) return;
    state.parentId = parentId;
    state.busy = true;
    refreshImportButton();
    try {
      const mapping = {};
      for (const f of FIELDS) if (state.mapping[f]) mapping[f] = state.mapping[f];
      const occurrenceTable = {};
      for (const r of RANKS) occurrenceTable[r] = Number(state.occ[r]);
      const body = {
        path: state.path,
        mapping,
        lambdaUnit: state.lambdaUnit,
        parentId,
        update: Boolean(state.update),
        occurrenceTable,
      };
      if (state.sheet) body.sheet = state.sheet;
      const res = await ctx.api.post('/fmea/import', body);
      if (res && res.tree) store.applyMutation(res);
      state.result = res;
      state.occTouched = false;
      // The jump below moves the selection onto an imported event; a re-import
      // must still land under the parent just used, not under that event.
      state.parentExplicit = true;
      const ids = [...(res.created || []), ...(res.updated || [])];
      if (ids.length) {
        ctx.highlight(ids, 'fmea');
        ctx.jumpTo((res.created && res.created[0]) || ids[0]);
      }
      if (res.changed) {
        ctx.toast(
          t('fmea.imported', { created: (res.created || []).length, updated: (res.updated || []).length }),
          'info'
        );
      }
      state.message = null;
    } catch (err) {
      state.message = { text: errorText(err), kind: 'error' };
      ctx.showError(err);
    } finally {
      state.busy = false;
      renderAll();
    }
  }

  /* ---- rendering ---- */
  function fileSection() {
    const chooseBtn = el('button', { type: 'button', text: t('fmea.choose'), onclick: () => choose() });
    const pathInput = el('input', {
      type: 'text',
      class: 'fmea-path',
      placeholder: t('fmea.pathPlaceholder'),
      'aria-label': t('fmea.pathLabel'),
      spellcheck: 'false',
      autocomplete: 'off',
    });
    pathInput.value = state.path;
    pathInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        loadPreview(pathInput.value, null, true);
      }
    });
    const loadBtn = el('button', {
      type: 'button',
      text: t('fmea.load'),
      onclick: () => loadPreview(pathInput.value, null, true),
    });
    const template = el('a', {
      class: 'fmea-template',
      href: '#',
      title: t('fmea.templateTitle'),
      text: t('fmea.template'),
      onclick: downloadTemplate,
    });
    const row = el('div', { class: 'fmea-row' }, [chooseBtn, pathInput, loadBtn, template]);
    const children = [el('h3', { text: t('fmea.step.file') }), row];

    const preview = state.preview;
    if (preview && Array.isArray(preview.sheets) && preview.sheets.length) {
      const sheetSelect = el(
        'select',
        { 'aria-label': t('fmea.sheet') },
        preview.sheets.map((name) => el('option', { value: name, text: name }))
      );
      sheetSelect.value = state.sheet || preview.sheets[0];
      sheetSelect.addEventListener('change', () => loadPreview(state.path, sheetSelect.value, false));
      children.push(el('div', { class: 'fmea-row' }, [el('label', {}, [t('fmea.sheet') + ' ', sheetSelect])]));
    }
    messageEl = el('p', { class: 'fmea-msg', role: 'status', 'aria-live': 'polite' });
    children.push(messageEl);
    if (preview) children.push(previewTable(preview));
    return el('section', { class: 'fmea-section' }, children);
  }

  function previewTable(preview) {
    const columns = preview.columns || [];
    const rows = preview.rows || [];
    const numbers = preview.rowNumbers || [];
    const summary = el('p', {
      class: 'fmea-hint',
      text: t('fmea.previewSummary', { file: preview.name || state.path, n: preview.rowCount || 0, shown: rows.length }),
    });
    if (!rows.length) return el('div', {}, [summary, el('p', { class: 'fmea-hint', text: t('fmea.noRows') })]);
    const mapped = new Set(Object.values(state.mapping));
    const head = el('tr', {}, [
      el('th', { text: t('fmea.previewRow') }),
      ...columns.map((c) => el('th', { class: mapped.has(c) ? 'is-mapped' : null, text: c })),
    ]);
    const body = rows.map((cells, i) =>
      el('tr', {}, [
        el('td', { class: 'fmea-rowno', text: cellText(numbers[i]) }),
        ...columns.map((_c, j) => el('td', { text: cellText(cells[j]) })),
      ])
    );
    const table = el('table', {}, [el('thead', {}, [head]), el('tbody', {}, body)]);
    return el('div', {}, [summary, el('div', { class: 'fmea-preview' }, [table])]);
  }

  function mappingSection() {
    const preview = state.preview;
    const columns = preview.columns || [];
    const grid = el(
      'div',
      { class: 'fmea-map' },
      FIELDS.map((field) => {
        const select = el('select', { dataset: { field } }, [
          el('option', { value: '', text: t('fmea.none') }),
          ...columns.map((c) => el('option', { value: c, text: c })),
        ]);
        select.value = state.mapping[field] || '';
        select.addEventListener('change', () => {
          if (select.value) state.mapping[field] = select.value;
          else delete state.mapping[field];
          // Mapped headers are tinted in the preview; repaint just that.
          for (const th of root.querySelectorAll('.fmea-preview th')) {
            th.classList.toggle('is-mapped', Object.values(state.mapping).includes(th.textContent));
          }
          keyHint.hidden = keyMapped();
          refreshImportButton();
          if (field === 'lambda') paintUnitWarning();
        });
        return el('label', {}, [t('fmea.field.' + field), select]);
      })
    );
    const keyHint = el('p', { class: 'fmea-msg is-error', text: t('fmea.keyHint') });
    keyHint.hidden = keyMapped();
    return el('section', { class: 'fmea-section' }, [el('h3', { text: t('fmea.step.mapping') }), grid, keyHint]);
  }

  function occTable() {
    const rows = RANKS.map((rank) => {
      const input = el('input', {
        type: 'text',
        inputmode: 'decimal',
        spellcheck: 'false',
        'aria-label': t('fmea.occProb') + ' ' + rank,
        dataset: { rank },
      });
      input.value = ctx.fmt.prob(state.occ[rank]);
      input.classList.toggle('is-invalid', state.occInvalid.has(rank));
      input.addEventListener('input', () => {
        const text = input.value.trim().replace(',', '.');
        const value = text === '' ? NaN : Number(text);
        const ok = Number.isFinite(value) && value >= 0 && value <= 1;
        input.classList.toggle('is-invalid', !ok);
        if (ok) {
          state.occ[rank] = value;
          state.occInvalid.delete(rank);
        } else {
          state.occInvalid.add(rank);
        }
        state.occTouched = true;
        input.title = ok ? '' : t('fmea.occInvalid', { rank });
        refreshImportButton();
      });
      input.addEventListener('blur', () => {
        if (!state.occInvalid.has(rank)) input.value = ctx.fmt.prob(state.occ[rank]);
      });
      return el('label', { class: 'fmea-occ-cell' }, [el('span', { class: 'fmea-occ-rank', text: rank }), input]);
    });
    const reset = el('button', {
      type: 'button',
      text: t('fmea.occReset'),
      onclick: () => {
        state.occ = { ...state.occDefault };
        state.occInvalid = new Set();
        state.occTouched = true;
        renderAll();
      },
    });
    return el('div', { class: 'fmea-occ' }, [
      el('h3', { text: t('fmea.occTitle') }),
      el('p', { class: 'fmea-hint', text: t('fmea.occHint') }),
      el('p', { class: 'fmea-hint', text: t('fmea.occRank') + ' → ' + t('fmea.occProb') }),
      el('div', { class: 'fmea-occ-grid' }, rows),
      el('div', { class: 'fmea-row' }, [reset]),
    ]);
  }

  /** The mapped λ column's preview values. */
  function lambdaValues() {
    const preview = state.preview;
    const column = state.mapping.lambda;
    if (!preview || !column) return [];
    const index = (preview.columns || []).indexOf(column);
    if (index < 0) return [];
    return (preview.rows || []).map((cells) => (Array.isArray(cells) ? cells[index] : undefined));
  }

  let unitWarning = null;
  function paintUnitWarning() {
    if (!unitWarning) return;
    const unit = state.lambdaUnit;
    const suggested = state.preview ? state.preview.suggestedLambdaUnit : null;
    const check = lambdaUnitCheck(lambdaValues(), unit, suggested);
    const unitLabel = (u) => t('fmea.unit.' + u);
    const lines = [];
    if (check.high) {
      const vars = { max: ctx.fmt.prob(check.high.max), perHour: ctx.fmt.prob(check.high.perHour), unit: unitLabel(unit) };
      let text = t(unit === 'h' ? 'fmea.lambdaHighH' : 'fmea.lambdaHigh', vars);
      if (check.high.suggest) text += ' ' + t('fmea.lambdaHighSuggest', { suggest: unitLabel(check.high.suggest) });
      lines.push(text);
    }
    if (check.differs && !(check.high && check.high.suggest === check.differs)) {
      lines.push(t('fmea.unitDiffers', { suggested: unitLabel(check.differs), chosen: unitLabel(unit) }));
    }
    unitWarning.textContent = lines.join(' ');
    unitWarning.hidden = !lines.length;
  }

  let parentSelect = null;
  function fillParentSelect() {
    if (!parentSelect) return;
    const chosen = defaultParent();
    clear(parentSelect);
    for (const entry of parentCandidates()) {
      const name = entry.name || entry.id;
      parentSelect.appendChild(
        el('option', {
          value: entry.id,
          text: '  '.repeat(Math.min(entry.depth || 0, 12)) + name + ' (' + entry.id + ')',
        })
      );
    }
    if (chosen) parentSelect.value = chosen;
    state.parentId = chosen;
  }

  function targetSection() {
    parentSelect = el('select', { class: 'fmea-parent', 'aria-label': t('fmea.parent') });
    fillParentSelect();
    parentSelect.addEventListener('change', () => {
      state.parentId = parentSelect.value;
      state.parentExplicit = true;
    });
    const unitSelect = el(
      'select',
      { 'aria-label': t('fmea.lambdaUnit') },
      UNITS.map((u) => el('option', { value: u, text: t('fmea.unit.' + u) }))
    );
    unitSelect.value = state.lambdaUnit;
    unitSelect.addEventListener('change', () => {
      state.lambdaUnit = unitSelect.value;
      paintUnitWarning();
    });
    unitWarning = el('p', { class: 'fmea-msg is-warn fmea-unit-warning', role: 'status', 'aria-live': 'polite' });
    paintUnitWarning();
    const update = el('input', { type: 'checkbox' });
    update.checked = state.update;
    update.addEventListener('change', () => {
      state.update = update.checked;
    });
    importButton = el('button', { type: 'button', class: 'fmea-primary', onclick: () => runImport() });
    refreshImportButton();

    const options = el('div', { class: 'fmea-options' }, [
      el('label', {}, [t('fmea.parent'), parentSelect]),
      el('p', { class: 'fmea-hint', text: t('fmea.parentHint') }),
      el('label', {}, [t('fmea.lambdaUnit'), unitSelect]),
      unitWarning,
      el('label', { title: t('fmea.updateHint') }, [update, t('fmea.update')]),
      el('p', { class: 'fmea-hint', text: t('fmea.updateHint') }),
      el('p', { class: 'fmea-hint', text: t('fmea.quantHint') }),
      el('div', { class: 'fmea-row' }, [importButton]),
    ]);
    return el('section', { class: 'fmea-section' }, [
      el('h3', { text: t('fmea.step.target') }),
      el('div', { class: 'fmea-columns' }, [options, occTable()]),
    ]);
  }

  function resultSection() {
    const res = state.result;
    const created = res.created || [];
    const updated = res.updated || [];
    const skipped = res.skipped || [];
    const children = [
      el('p', {
        class: 'fmea-msg',
        text: res.changed
          ? t('fmea.result', {
              created: created.length,
              updated: updated.length,
              unchanged: (res.unchanged || []).length,
              skipped: skipped.length,
            })
          : t('fmea.resultNothing') +
            ' ' +
            t('fmea.result', {
              created: created.length,
              updated: updated.length,
              unchanged: (res.unchanged || []).length,
              skipped: skipped.length,
            }),
      }),
    ];
    const ids = [...created, ...updated];
    if (ids.length) {
      children.push(
        el('div', { class: 'fmea-row' }, [
          el('button', {
            type: 'button',
            text: t('fmea.highlight'),
            onclick: () => ctx.highlight(ids, 'fmea'),
          }),
        ])
      );
    }
    if (skipped.length) {
      children.push(el('h3', { text: t('fmea.skippedTitle') }));
      children.push(
        el(
          'ul',
          { class: 'fmea-skipped' },
          skipped.slice(0, MAX_SKIPPED_SHOWN).map((s) => {
            const key = 'fmea.reason.' + s.reason;
            const vars = {
              field: s.field ? t('fmea.field.' + s.field) : '',
              value: cellText(s.value),
              id: cellText(s.fmeaId),
            };
            const text = t(key, vars);
            return el('li', {
              text: t('fmea.skippedRow', { row: s.row }) + ': ' + (text === key ? s.message || s.reason : text),
            });
          })
        )
      );
    }
    return el('section', { class: 'fmea-section fmea-result', role: 'status' }, children);
  }

  function renderAll() {
    clear(root);
    importButton = null;
    parentSelect = null;
    unitWarning = null;
    root.appendChild(el('p', { class: 'fmea-intro', text: t('fmea.intro') }));
    root.appendChild(fileSection());
    paintMessage();
    if (state.preview) {
      root.appendChild(mappingSection());
      root.appendChild(targetSection());
    }
    if (state.result) root.appendChild(resultSection());
  }

  function onLanguage() {
    renderAll();
  }
  const unSigFigs =
    typeof ctx.onSigFigs === 'function'
      ? ctx.onSigFigs(() => {
          for (const input of root.querySelectorAll('.fmea-occ input')) {
            const rank = input.dataset.rank;
            if (!state.occInvalid.has(rank)) input.value = ctx.fmt.prob(state.occ[rank]);
          }
        })
      : null;

  window.addEventListener('fta:language', onLanguage);
  renderAll();

  return {
    activate() {
      // The selected node may have changed while the tab was hidden.
      if (!state.busy) fillParentSelect();
    },
    deactivate() {},
    onStale() {
      fillParentSelect();
    },
    dispose() {
      window.removeEventListener('fta:language', onLanguage);
      if (typeof unSigFigs === 'function') unSigFigs();
      root.remove();
    },
  };
}

export default mount;
