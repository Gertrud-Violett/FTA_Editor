/**
 * tabs/cutsets.js -- the Cut Sets tab (1.7, workstream A).
 *
 * POST /api/analysis/cutsets with optional per-run limits. The limit inputs
 * start from the document's `analysis.cutsets` (blank also means the document
 * value); "Save as document defaults" writes them back through POST
 * /api/analysis/settings (undoable), which Importance and the headline use. Runs on first show and again, debounced,
 * whenever the tree changes while the tab is visible. A row click lights its
 * events up in the tree and the diagram through ctx.highlight(ids,
 * 'cutsets'); leaving the tab clears that highlight.
 */
import cat from '../i18n/cutsets.js';
import {
  clear,
  copyText,
  debounce,
  el,
  ensureStyles,
  etaNotice,
  isEta,
  parseNumber,
  renderWarnings,
  reportError,
  translator,
} from './analysis_common.js';

window.ftaShell?.registerStrings?.(cat);

export const id = 'cutsets';
export const advanced = true;

const SOURCE = 'cutsets';
const STALE_DELAY_MS = 700;

export function mount(panel, ctx) {
  ensureStyles();
  const t = translator(ctx);
  const fmt = (v) => ctx.fmt.prob(v);

  let active = false;
  let result = null;
  let selectedRank = null;
  let running = false;
  let seq = 0;
  let hasRun = false;
  let stale = false;

  // ---- skeleton ---------------------------------------------------------
  const root = el('div', { class: 'anl anl-cutsets', dataset: { tab: 'cutsets' } });
  const runBtn = el('button', { type: 'button', class: 'btn btn--primary', dataset: { role: 'run' } });
  const inOrder = el('input', { type: 'text', inputmode: 'numeric', dataset: { limit: 'maxOrder' } });
  const inCount = el('input', { type: 'text', inputmode: 'numeric', dataset: { limit: 'maxCount' } });
  const inCutoff = el('input', { type: 'text', inputmode: 'decimal', dataset: { limit: 'cutoff' } });
  const inLimit = el('input', { type: 'text', inputmode: 'numeric', value: '500', dataset: { limit: 'limit' } });
  const lblOrder = el('label', null, [el('span'), inOrder]);
  const lblCount = el('label', null, [el('span'), inCount]);
  const lblCutoff = el('label', null, [el('span'), inCutoff]);
  const lblLimit = el('label', null, [el('span'), inLimit]);
  const copyBtn = el('button', { type: 'button', class: 'btn', dataset: { role: 'copy' } });
  const saveBtn = el('button', { type: 'button', class: 'btn', dataset: { role: 'save-defaults' } });
  // Inputs the user has typed in since they were last filled from the document.
  const edited = new Set();
  const status = el('span', { class: 'anl-note', 'aria-live': 'polite' });
  const toolbar = el('div', { class: 'anl-toolbar' }, [
    runBtn, lblOrder, lblCount, lblCutoff, saveBtn, lblLimit, el('span', { class: 'anl-grow' }), status, copyBtn,
  ]);
  const summary = el('div', { class: 'anl-summary', 'aria-live': 'polite' });
  const warnings = el('ul', { class: 'anl-warnings' });
  const message = el('p', { class: 'anl-empty' });
  const tableWrap = el('div', { class: 'anl-tablewrap' });
  const hint = el('p', { class: 'anl-note' });
  const body = el('div', { class: 'anl', style: 'padding:0;overflow:visible;height:auto;flex:1 1 auto' }, [
    toolbar, summary, warnings, message, tableWrap, hint,
  ]);
  panel.appendChild(root);

  function limitsBody() {
    const out = {};
    const pairs = [
      ['maxOrder', inOrder],
      ['maxCount', inCount],
      ['cutoff', inCutoff],
      ['limit', inLimit],
    ];
    let ok = true;
    for (const [key, input] of pairs) {
      const value = parseNumber(input.value);
      input.classList.toggle('anl-invalid', Number.isNaN(value));
      if (Number.isNaN(value)) ok = false;
      else if (value !== null) out[key] = value;
    }
    return ok ? out : null;
  }

  // ---- running ----------------------------------------------------------
  async function run() {
    if (isEta(ctx)) {
      paint();
      return;
    }
    const payload = limitsBody();
    if (!payload) return;
    const mine = ++seq;
    running = true;
    paintToolbar();
    try {
      const res = await ctx.api.post('/analysis/cutsets', payload);
      if (mine !== seq) return;
      result = res;
      hasRun = true;
      stale = false;
      // Keep the selection if the same cut set is still there.
      if (selectedRank !== null) {
        const row = result.cutSets.find((cs) => cs.rank === selectedRank);
        if (row) highlightRow(row);
        else unselect();
      }
    } catch (err) {
      if (mine !== seq) return;
      reportError(ctx, err);
    } finally {
      if (mine === seq) {
        running = false;
        paint();
      }
    }
  }
  const runSoon = debounce(run, STALE_DELAY_MS);

  function highlightRow(row) {
    selectedRank = row.rank;
    ctx.highlight(row.events.map((e) => e.id), SOURCE);
  }

  function unselect() {
    selectedRank = null;
    ctx.clearHighlight(SOURCE);
  }

  // ---- painting -----------------------------------------------------------
  function docLimits() {
    const analysis = ctx.store.state && ctx.store.state.analysis;
    return (analysis && analysis.cutsets) || {};
  }

  /** Save the three limit inputs as `analysis.cutsets` (undoable). */
  async function saveDefaults() {
    const payload = limitsBody();
    if (!payload) return;
    const cut = {};
    for (const key of ['maxOrder', 'maxCount', 'cutoff']) {
      if (payload[key] !== undefined) cut[key] = payload[key];
    }
    if (!Object.keys(cut).length) return;
    saveBtn.disabled = true;
    try {
      const res = await ctx.api.post('/analysis/settings', { cutsets: cut });
      ctx.store.applyMutation(res);
      edited.clear();
      ctx.toast(t('cutsets.savedDefaults'), 'ok');
    } catch (err) {
      reportError(ctx, err);
    } finally {
      saveBtn.disabled = false;
      paintToolbar();
    }
  }

  function paintToolbar() {
    runBtn.textContent = running ? t('anl.running') : t('anl.run');
    runBtn.disabled = running;
    saveBtn.textContent = t('cutsets.saveDefaults');
    saveBtn.title = t('cutsets.saveDefaultsTitle');
    copyBtn.textContent = t('cutsets.copyCsv');
    copyBtn.disabled = !result || !result.cutSets || !result.cutSets.length;
    const doc = docLimits();
    const labels = [
      [lblOrder, 'cutsets.maxOrder', inOrder, doc.maxOrder],
      [lblCount, 'cutsets.maxCount', inCount, doc.maxCount],
      [lblCutoff, 'cutsets.cutoff', inCutoff, doc.cutoff],
    ];
    for (const [label, key, input, value] of labels) {
      label.firstChild.textContent = t(key);
      const shown = value === undefined ? '' : String(value);
      input.placeholder = shown;
      // Prefilled from the document until the user types (and again after an
      // undo or a save changes the document value).
      if (!edited.has(input) && document.activeElement !== input) {
        input.value = shown;
        input.classList.remove('anl-invalid');
      }
      input.title = t('cutsets.docDefault', { value: shown });
    }
    lblLimit.firstChild.textContent = t('cutsets.limit');
    lblLimit.title = t('cutsets.limitTitle');
    status.textContent = result && !running ? t('anl.elapsed', { ms: Math.round(result.elapsedMs) }) : '';
  }

  function badge(text, kind, title) {
    return el('span', { class: 'anl-badge' + (kind ? ' anl-badge--' + kind : ''), text, title: title || null });
  }

  function stat(label, value) {
    return el('span', { class: 'anl-stat' }, [label + ' ', el('b', { text: value })]);
  }

  function paintSummary() {
    clear(summary);
    if (!result) return;
    summary.append(
      stat(t('cutsets.mcub'), fmt(result.mcub)),
      stat(t('cutsets.rare'), fmt(result.rareEvent)),
      stat(t('cutsets.treeWalk'), fmt(result.treeWalk)),
      el('span', { class: 'anl-stat', text: t('cutsets.count', { shown: result.returned, total: result.total }) })
    );
    if (result.truncated) {
      const by = (result.truncatedBy || []).map((b) => t('anl.by.' + b)).join(', ');
      summary.appendChild(badge(t('cutsets.truncated'), 'warn', t('cutsets.truncatedTitle', { by })));
    }
    const repeated = result.repeatedEvents || [];
    if (repeated.length) {
      const names = repeated.map((e) => e.name || e.id).join(', ');
      summary.appendChild(badge(t('cutsets.repeated', { n: repeated.length }), 'info',
        t('cutsets.repeatedTitle', { names })));
    }
    if (result.nonCoherent) summary.appendChild(badge(t('cutsets.nonCoherent'), 'warn'));
    const approx = result.approximations || [];
    if (approx.length) summary.appendChild(badge(t('cutsets.approx', { n: approx.length }), 'warn'));
    if (approx.some((a) => a && a.code === 'PAND_APPROX')) {
      // Cut sets expand PAND as plain AND (no 1/n!): conservative, and it is
      // what the MCUB headline then uses.
      summary.appendChild(badge(t('cutsets.pandAsAnd'), 'warn', t('cutsets.pandAsAndTitle')));
    }
    if (stale) summary.appendChild(badge(t('anl.staleNote'), null));
  }

  function paintTable() {
    clear(tableWrap);
    const rows = (result && result.cutSets) || [];
    tableWrap.hidden = rows.length === 0;
    if (!rows.length) return;
    const table = el('table', { class: 'anl-table' });
    const head = el('tr', null, [
      el('th', { class: 'num', text: t('cutsets.col.rank') }),
      el('th', { class: 'num', text: t('cutsets.col.order') }),
      el('th', { text: t('cutsets.col.events') }),
      el('th', { class: 'num', text: t('cutsets.col.prob') }),
      el('th', { text: t('cutsets.col.share') }),
    ]);
    table.appendChild(el('thead', null, [head]));
    const tbody = el('tbody');
    const maxShare = rows.reduce((m, r) => Math.max(m, r.share || 0), 0) || 1;
    for (const row of rows) {
      const events = el('div', { class: 'anl-events' });
      if (!row.events.length) events.appendChild(el('span', { class: 'anl-note', text: t('cutsets.emptySet') }));
      for (const ev of row.events) {
        events.appendChild(el('span', { class: 'anl-event', text: ev.name || ev.id, title: ev.id + '  q=' + fmt(ev.q) }));
      }
      const pct = (row.share || 0) * 100;
      const fill = el('span', { class: 'anl-bar__fill', style: 'width:' + ((row.share || 0) / maxShare) * 100 + '%' });
      const tr = el('tr', {
        tabindex: '0',
        class: row.rank === selectedRank ? 'is-selected' : null,
        dataset: { rank: String(row.rank) },
        'aria-selected': row.rank === selectedRank ? 'true' : 'false',
      }, [
        el('td', { class: 'num', text: String(row.rank) }),
        el('td', { class: 'num', text: String(row.order) }),
        el('td', null, [events]),
        el('td', { class: 'num', text: fmt(row.probability) }),
        el('td', { class: 'anl-bar' }, [fill, el('span', { class: 'anl-bar__text', text: pct.toFixed(pct >= 10 ? 1 : 2) + '%' })]),
      ]);
      tbody.appendChild(tr);
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
    root.appendChild(body);
    paintToolbar();
    paintSummary();
    renderWarnings(ctx, warnings, result ? result.warnings : []);
    const rows = (result && result.cutSets) || [];
    message.hidden = rows.length > 0;
    message.textContent = !result ? t('cutsets.notRun') : t('cutsets.none');
    hint.hidden = rows.length === 0;
    hint.textContent = t('cutsets.hint');
    paintTable();
  }

  // ---- events -----------------------------------------------------------
  function rowFrom(event) {
    const tr = event.target instanceof Element ? event.target.closest('tr[data-rank]') : null;
    if (!tr || !result) return null;
    return result.cutSets.find((cs) => String(cs.rank) === tr.dataset.rank) || null;
  }

  function choose(row) {
    if (!row) return;
    if (selectedRank === row.rank) unselect();
    else highlightRow(row);
    for (const tr of tableWrap.querySelectorAll('tr[data-rank]')) {
      const on = tr.dataset.rank === String(selectedRank);
      tr.classList.toggle('is-selected', on);
      tr.setAttribute('aria-selected', on ? 'true' : 'false');
    }
  }

  tableWrap.addEventListener('click', (event) => choose(rowFrom(event)));
  tableWrap.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const row = rowFrom(event);
    if (!row) return;
    event.preventDefault();
    choose(row);
  });
  runBtn.addEventListener('click', () => {
    runSoon.cancel();
    run();
  });
  saveBtn.addEventListener('click', () => saveDefaults());
  for (const input of [inOrder, inCount, inCutoff]) {
    input.addEventListener('input', () => edited.add(input));
  }
  for (const input of [inOrder, inCount, inCutoff, inLimit]) {
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        run();
      }
    });
  }
  copyBtn.addEventListener('click', async () => {
    if (!result || !result.cutSets) return;
    const quote = (s) => '"' + String(s).replace(/"/g, '""') + '"';
    const lines = [
      [t('cutsets.col.rank'), t('cutsets.col.order'), t('cutsets.col.prob'), t('cutsets.col.share'), t('cutsets.col.events')]
        .map(quote).join(','),
    ];
    for (const row of result.cutSets) {
      lines.push([
        row.rank,
        row.order,
        row.probability,
        row.share,
        quote(row.events.map((e) => e.name || e.id).join(' ; ')),
      ].join(','));
    }
    const ok = await copyText(lines.join('\r\n') + '\r\n');
    if (ok) ctx.toast(t('cutsets.copied', { n: result.cutSets.length }), 'info');
    else ctx.toast(t('cutsets.copyFailed'), 'error');
  });

  const repaint = () => paint();
  window.addEventListener('fta:language', repaint);
  const unSig = ctx.onSigFigs(repaint);

  paint();

  return {
    activate() {
      active = true;
      if (!hasRun && !running) run();
      else paint();
    },
    deactivate() {
      active = false;
      runSoon.cancel();
      unselect();
      for (const tr of tableWrap.querySelectorAll('tr.is-selected')) tr.classList.remove('is-selected');
    },
    onStale() {
      if (!hasRun) {
        if (!isEta(ctx) && root.contains(toolbar)) paintToolbar(); // document limits may have changed
        return;
      }
      stale = true;
      paint();
      if (active) runSoon();
    },
    dispose() {
      runSoon.cancel();
      window.removeEventListener('fta:language', repaint);
      if (typeof unSig === 'function') unSig();
      unselect();
      root.remove();
    },
  };
}

export default mount;
