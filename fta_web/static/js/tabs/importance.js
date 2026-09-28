/**
 * tabs/importance.js -- the Importance tab (1.7, workstream A).
 *
 * POST /api/analysis/importance (document cut-set limits) and a table of
 * FV / Birnbaum / RAW / RRW per event, sortable by any measure. "Colour
 * diagram by FV" publishes ctx.setOverlay({kind: 'fv', values: {id: fv}});
 * turning it off, or leaving the tab, clears the overlay. A row click selects
 * the event (ctx.jumpTo).
 */
import cat from '../i18n/imp.js';
import {
  clear,
  debounce,
  el,
  ensureStyles,
  etaNotice,
  isEta,
  renderWarnings,
  reportError,
  translator,
} from './analysis_common.js';

window.ftaShell?.registerStrings?.(cat);

export const id = 'importance';
export const advanced = true;

const STALE_DELAY_MS = 700;
const OVERLAY_KEY = 'fta.importance.fvOverlay';

/** Column definitions; `label` null means a translated header. */
const MEASURES = [
  { key: 'fv', label: 'FV' },
  { key: 'birnbaum', label: 'Birnbaum' },
  { key: 'raw', label: 'RAW' },
  { key: 'rrw', label: 'RRW' },
];

function readOverlayPref() {
  try {
    return window.localStorage.getItem(OVERLAY_KEY) === '1';
  } catch (_err) {
    return false;
  }
}

function writeOverlayPref(on) {
  try {
    window.localStorage.setItem(OVERLAY_KEY, on ? '1' : '0');
  } catch (_err) {
    /* not persisted */
  }
}

export function mount(panel, ctx) {
  ensureStyles();
  const t = translator(ctx);
  const fmt = (v) => ctx.fmt.prob(v);

  let active = false;
  let result = null;
  let running = false;
  let seq = 0;
  let hasRun = false;
  let stale = false;
  let sortKey = 'fv';
  let sortDesc = true;
  let overlayOn = readOverlayPref();

  const root = el('div', { class: 'anl anl-importance', dataset: { tab: 'importance' } });
  const runBtn = el('button', { type: 'button', class: 'btn btn--primary', dataset: { role: 'run' } });
  const overlayBox = el('input', { type: 'checkbox', dataset: { role: 'fv-overlay' } });
  const overlayLabel = el('label', null, [overlayBox, el('span')]);
  const status = el('span', { class: 'anl-note', 'aria-live': 'polite' });
  const toolbar = el('div', { class: 'anl-toolbar' }, [runBtn, overlayLabel, el('span', { class: 'anl-grow' }), status]);
  const basis = el('p', { class: 'anl-note' });
  const warnings = el('ul', { class: 'anl-warnings' });
  const message = el('p', { class: 'anl-empty' });
  const tableWrap = el('div', { class: 'anl-tablewrap' });
  const hint = el('p', { class: 'anl-note' });
  panel.appendChild(root);

  function applyOverlay() {
    if (!active || !overlayOn || !result || isEta(ctx)) {
      ctx.setOverlay(null);
      return;
    }
    const values = {};
    for (const row of result.events || []) {
      if (row.fv !== null && row.fv !== undefined) values[row.id] = row.fv;
    }
    ctx.setOverlay({ kind: 'fv', values });
  }

  async function run() {
    if (isEta(ctx)) {
      paint();
      return;
    }
    const mine = ++seq;
    running = true;
    paintToolbar();
    try {
      const res = await ctx.api.post('/analysis/importance', {});
      if (mine !== seq) return;
      result = res;
      hasRun = true;
      stale = false;
    } catch (err) {
      if (mine !== seq) return;
      reportError(ctx, err);
    } finally {
      if (mine === seq) {
        running = false;
        paint();
        applyOverlay();
      }
    }
  }
  const runSoon = debounce(run, STALE_DELAY_MS);

  function paintToolbar() {
    runBtn.textContent = running ? t('anl.running') : t('anl.run');
    runBtn.disabled = running;
    overlayBox.checked = overlayOn;
    overlayLabel.lastChild.textContent = t('imp.colorFv');
    overlayLabel.title = t('imp.colorFvTitle');
    status.textContent = '';
  }

  function sortedRows() {
    const rows = ((result && result.events) || []).slice();
    const value = (row) => {
      if (sortKey === 'rrw' && row.rrwInfinite) return Infinity;
      const v = row[sortKey];
      return v === null || v === undefined ? -Infinity : v;
    };
    rows.sort((a, b) => {
      const d = value(a) - value(b);
      if (d !== 0 && !Number.isNaN(d)) return sortDesc ? -d : d;
      return String(a.name).localeCompare(String(b.name));
    });
    return rows;
  }

  function paintTable() {
    clear(tableWrap);
    const rows = sortedRows();
    tableWrap.hidden = rows.length === 0;
    if (!rows.length) return;
    const table = el('table', { class: 'anl-table' });
    const headCells = [
      el('th', { text: t('imp.col.event') }),
      el('th', { class: 'num', text: 'q', title: t('imp.title.q') }),
    ];
    for (const m of MEASURES) {
      const sorted = sortKey === m.key;
      headCells.push(el('th', {
        class: 'num is-sortable' + (sorted ? ' is-sorted' : ''),
        text: m.label + (sorted ? (sortDesc ? ' ▼' : ' ▲') : ''),
        title: t('imp.title.' + m.key),
        tabindex: '0',
        role: 'button',
        'aria-sort': sorted ? (sortDesc ? 'descending' : 'ascending') : 'none',
        dataset: { sort: m.key },
      }));
    }
    headCells.push(el('th', { class: 'num', text: t('imp.col.cutSets') }));
    table.appendChild(el('thead', null, [el('tr', null, headCells)]));
    const tbody = el('tbody');
    const selected = ctx.store.selectedId;
    for (const row of rows) {
      const fvPct = row.fv === null || row.fv === undefined ? 0 : row.fv * 100;
      const rrw = row.rrwInfinite
        ? el('td', { class: 'num', text: '∞', title: t('imp.infiniteTitle') })
        : el('td', { class: 'num', text: fmt(row.rrw) });
      tbody.appendChild(el('tr', {
        tabindex: '0',
        dataset: { id: row.id },
        class: row.id === selected ? 'is-selected' : null,
      }, [
        el('td', { text: row.name || row.id, title: row.id }),
        el('td', { class: 'num', text: fmt(row.q) }),
        el('td', { class: 'num anl-bar' }, [
          el('span', { class: 'anl-bar__fill', style: 'width:' + fvPct + '%' }),
          el('span', { class: 'anl-bar__text', text: fmt(row.fv) }),
        ]),
        el('td', { class: 'num', text: fmt(row.birnbaum) }),
        el('td', { class: 'num', text: fmt(row.raw) }),
        rrw,
        el('td', { class: 'num', text: String(row.cutSetCount) }),
      ]));
    }
    table.appendChild(tbody);
    tableWrap.appendChild(table);
  }

  function paint() {
    clear(root);
    if (isEta(ctx)) {
      root.appendChild(etaNotice(ctx));
      return;
    }
    root.append(toolbar, basis, warnings, message, tableWrap, hint);
    paintToolbar();
    const rows = (result && result.events) || [];
    basis.hidden = !result;
    if (result) {
      basis.textContent = t('imp.basis', { q: fmt(result.topValue), n: result.cutSetTotal })
        + (result.truncated ? ' ' + t('imp.truncated') : '')
        + (stale ? ' ' + t('anl.staleNote') : '');
    }
    renderWarnings(ctx, warnings, result ? result.warnings : []);
    message.hidden = rows.length > 0;
    message.textContent = result ? t('imp.none') : t('imp.notRun');
    hint.hidden = rows.length === 0;
    hint.textContent = t('imp.hint');
    paintTable();
  }

  // ---- events -----------------------------------------------------------
  function onHeader(event) {
    const th = event.target instanceof Element ? event.target.closest('th[data-sort]') : null;
    if (!th) return false;
    if (sortKey === th.dataset.sort) sortDesc = !sortDesc;
    else {
      sortKey = th.dataset.sort;
      sortDesc = true;
    }
    paintTable();
    const again = tableWrap.querySelector('th[data-sort="' + sortKey + '"]');
    if (again && event.type === 'keydown') again.focus();
    return true;
  }

  function onRow(event) {
    const tr = event.target instanceof Element ? event.target.closest('tr[data-id]') : null;
    if (!tr) return;
    ctx.jumpTo(tr.dataset.id);
    for (const other of tableWrap.querySelectorAll('tr[data-id]')) {
      other.classList.toggle('is-selected', other === tr);
    }
  }

  tableWrap.addEventListener('click', (event) => {
    if (!onHeader(event)) onRow(event);
  });
  tableWrap.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    if (!onHeader(event)) onRow(event);
  });
  runBtn.addEventListener('click', () => {
    runSoon.cancel();
    run();
  });
  overlayBox.addEventListener('change', () => {
    overlayOn = overlayBox.checked;
    writeOverlayPref(overlayOn);
    applyOverlay();
  });

  const repaint = () => paint();
  window.addEventListener('fta:language', repaint);
  const unSig = ctx.onSigFigs(repaint);

  paint();

  return {
    activate() {
      active = true;
      if (!hasRun && !running) run();
      else {
        paint();
        applyOverlay();
      }
    },
    deactivate() {
      active = false;
      runSoon.cancel();
      ctx.setOverlay(null);
    },
    onStale() {
      if (!hasRun) return;
      stale = true;
      paint();
      if (active) runSoon();
    },
    dispose() {
      runSoon.cancel();
      window.removeEventListener('fta:language', repaint);
      if (typeof unSig === 'function') unSig();
      ctx.setOverlay(null);
      root.remove();
    },
  };
}

export default mount;
