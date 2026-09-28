/**
 * tabs/uncertainty.js -- the Uncertainty (Monte Carlo) tab (1.7, workstream A).
 *
 * POST /api/analysis/uncertainty {n, seed?, timeLimit}. A run can take tens of
 * seconds, so it never starts by itself: the Run button is disabled while one
 * is in flight and an elapsed-time ticker shows progress. The server allows
 * one run at a time (409 BUSY otherwise). Results: summary statistics and an
 * inline SVG histogram (theme tokens only, so dark mode just works) with the
 * point estimate and the 5th/95th percentiles marked.
 *
 * The samples and seed inputs start from the document's `analysis.mc`;
 * "Save as document defaults" writes them back through POST
 * /api/analysis/settings (undoable). A blank seed saves "random".
 */
import cat from '../i18n/unc.js';
import {
  clear,
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

export const id = 'uncertainty';
export const advanced = true;

const SVG_NS = 'http://www.w3.org/2000/svg';
const MAX_N = 100000;
const MAX_TIME = 60;

function svg(tag, attrs, text) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  }
  if (text !== undefined) node.textContent = text;
  return node;
}

export function mount(panel, ctx) {
  ensureStyles();
  const t = translator(ctx);
  const fmt = (v) => ctx.fmt.prob(v);

  let result = null;
  let running = false;
  let stale = false;
  let startedAt = 0;
  let ticker = null;

  const root = el('div', { class: 'anl anl-uncertainty', dataset: { tab: 'uncertainty' } });
  const runBtn = el('button', { type: 'button', class: 'btn btn--primary', dataset: { role: 'run' } });
  const inN = el('input', { type: 'text', inputmode: 'numeric', dataset: { field: 'n' } });
  const inSeed = el('input', { type: 'text', inputmode: 'numeric', dataset: { field: 'seed' } });
  const inTime = el('input', { type: 'text', inputmode: 'decimal', value: '30', dataset: { field: 'timeLimit' } });
  const lblN = el('label', null, [el('span'), inN]);
  const lblSeed = el('label', null, [el('span'), inSeed]);
  const lblTime = el('label', null, [el('span'), inTime]);
  const saveBtn = el('button', { type: 'button', class: 'btn', dataset: { role: 'save-defaults' } });
  const edited = new Set(); // inputs typed in since they were filled from the document
  const status = el('span', { class: 'anl-note', 'aria-live': 'polite' });
  const toolbar = el('div', { class: 'anl-toolbar' }, [runBtn, lblN, lblSeed, saveBtn, lblTime, el('span', { class: 'anl-grow' }), status]);
  const message = el('p', { class: 'anl-empty' });
  const stats = el('div', { class: 'anl-statgrid' });
  const meta = el('p', { class: 'anl-note' });
  const warnings = el('ul', { class: 'anl-warnings' });
  const chartBox = el('div');
  panel.appendChild(root);

  function defaults() {
    const analysis = (ctx.store.state && ctx.store.state.analysis) || {};
    const mc = analysis.mc || {};
    return { n: Math.min(MAX_N, Number(mc.n) || 10000), seed: mc.seed };
  }

  function readInputs() {
    const n = parseNumber(inN.value);
    const seed = parseNumber(inSeed.value);
    const time = parseNumber(inTime.value);
    const badN = Number.isNaN(n) || (n !== null && (!Number.isInteger(n) || n < 1 || n > MAX_N));
    const badSeed = Number.isNaN(seed) || (seed !== null && (!Number.isInteger(seed) || seed < 0));
    const badTime = Number.isNaN(time) || (time !== null && (time <= 0 || time > MAX_TIME));
    inN.classList.toggle('anl-invalid', badN);
    inSeed.classList.toggle('anl-invalid', badSeed);
    inTime.classList.toggle('anl-invalid', badTime);
    if (badN || badSeed || badTime) return null;
    const body = { n: n === null ? defaults().n : n };
    if (seed !== null) body.seed = seed;
    else if (defaults().seed !== null && defaults().seed !== undefined) body.seed = defaults().seed;
    body.timeLimit = time === null ? 30 : time;
    return body;
  }

  /** Save samples and seed as `analysis.mc` (undoable). */
  async function saveDefaults() {
    const n = parseNumber(inN.value);
    const seed = parseNumber(inSeed.value);
    const badN = Number.isNaN(n) || (n !== null && (!Number.isInteger(n) || n < 1 || n > MAX_N));
    const badSeed = Number.isNaN(seed) || (seed !== null && (!Number.isInteger(seed) || seed < 0));
    inN.classList.toggle('anl-invalid', badN);
    inSeed.classList.toggle('anl-invalid', badSeed);
    if (badN || badSeed) return;
    const mc = { seed }; // null = random (the default)
    if (n !== null) mc.n = n;
    saveBtn.disabled = true;
    try {
      const res = await ctx.api.post('/analysis/settings', { mc });
      ctx.store.applyMutation(res);
      edited.clear();
      ctx.toast(t('unc.savedDefaults'), 'ok');
    } catch (err) {
      reportError(ctx, err);
    } finally {
      saveBtn.disabled = running;
      paintToolbar();
    }
  }

  function tick() {
    const s = ((performance.now() - startedAt) / 1000).toFixed(1);
    status.textContent = t('unc.elapsed', { s });
  }

  async function run() {
    if (running) return;
    if (isEta(ctx)) {
      paint();
      return;
    }
    const body = readInputs();
    if (!body) return;
    running = true;
    startedAt = performance.now();
    ticker = setInterval(tick, 200);
    paintToolbar();
    tick();
    try {
      result = await ctx.api.post('/analysis/uncertainty', body);
      stale = false;
    } catch (err) {
      reportError(ctx, err);
    } finally {
      running = false;
      clearInterval(ticker);
      ticker = null;
      paint();
    }
  }

  function paintToolbar() {
    runBtn.textContent = running ? t('anl.running') : t('anl.run');
    runBtn.disabled = running;
    runBtn.setAttribute('aria-busy', running ? 'true' : 'false');
    for (const input of [inN, inSeed, inTime]) input.disabled = running;
    saveBtn.disabled = running;
    saveBtn.textContent = t('unc.saveDefaults');
    saveBtn.title = t('unc.saveDefaultsTitle');
    lblN.firstChild.textContent = t('unc.n');
    lblSeed.firstChild.textContent = t('unc.seed');
    lblSeed.title = t('unc.seedTitle');
    lblTime.firstChild.textContent = t('unc.timeLimit');
    const d = defaults();
    inN.placeholder = String(d.n);
    const docSeed = d.seed === null || d.seed === undefined ? '' : String(d.seed);
    inSeed.placeholder = docSeed || t('unc.seedPlaceholder');
    // Prefilled from the document until the user types (and again after an
    // undo or a save changes the document value).
    if (!edited.has(inN) && document.activeElement !== inN) inN.value = String(d.n);
    if (!edited.has(inSeed) && document.activeElement !== inSeed) inSeed.value = docSeed;
    if (!running) status.textContent = '';
  }

  function stat(label, value, key) {
    return el('div', { class: 'anl-stat', dataset: { stat: key } }, [label + ' ', el('b', { text: value })]);
  }

  function paintStats() {
    clear(stats);
    if (!result) return;
    stats.append(
      stat(t('unc.stat.mean'), fmt(result.mean), 'mean'),
      stat(t('unc.stat.median'), fmt(result.median), 'median'),
      stat(t('unc.stat.p05'), fmt(result.p05), 'p05'),
      stat(t('unc.stat.p95'), fmt(result.p95), 'p95'),
      stat(t('unc.stat.std'), fmt(result.std), 'std'),
      stat(t('unc.stat.point'), fmt(result.pointEstimate), 'point')
    );
  }

  function chart() {
    const hist = result && result.histogram;
    if (!hist || !hist.counts || !hist.counts.length) return null;
    const W = 640;
    const H = 220;
    const L = 12;
    const R = 12;
    const T = 22;
    const B = 34;
    const w = W - L - R;
    const h = H - T - B;
    const counts = hist.counts;
    const edges = hist.edges;
    const lo = edges[0];
    const hi = edges[edges.length - 1];
    const maxCount = Math.max(1, ...counts);
    const logBins = Boolean(hist.logBins) && lo > 0;
    const xOf = (v) => {
      if (!(hi > lo)) return L + w / 2;
      let f = logBins ? (Math.log(v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo)) : (v - lo) / (hi - lo);
      if (!Number.isFinite(f)) f = 0;
      return L + Math.min(1, Math.max(0, f)) * w;
    };
    const root = svg('svg', {
      class: 'anl-chart',
      viewBox: '0 0 ' + W + ' ' + H,
      role: 'img',
      'aria-label': t('unc.chart'),
      preserveAspectRatio: 'xMidYMid meet',
    });
    root.appendChild(svg('title', null, t('unc.chart') + (logBins ? ' (' + t('unc.logScale') + ')' : '')));
    const barW = w / counts.length;
    counts.forEach((count, i) => {
      if (!count) return;
      const bh = (count / maxCount) * h;
      root.appendChild(svg('rect', {
        class: 'bar',
        x: (L + i * barW + 0.5).toFixed(2),
        y: (T + h - bh).toFixed(2),
        width: Math.max(0.5, barW - 1).toFixed(2),
        height: bh.toFixed(2),
      }, undefined)).appendChild(svg('title', null, fmt(edges[i]) + ' – ' + fmt(edges[i + 1]) + ': ' + count));
    });
    root.appendChild(svg('line', { class: 'axis', x1: L, y1: T + h + 0.5, x2: L + w, y2: T + h + 0.5 }));
    // Ticks: both ends and three inner positions (edges are on the bin grid).
    const tickIdx = [0, Math.round(counts.length / 4), Math.round(counts.length / 2), Math.round((3 * counts.length) / 4), counts.length];
    const used = new Set();
    for (const i of tickIdx) {
      if (used.has(i) || edges[i] === undefined) continue;
      used.add(i);
      const x = L + i * barW;
      root.appendChild(svg('line', { class: 'axis', x1: x, y1: T + h, x2: x, y2: T + h + 4 }));
      const anchor = i === 0 ? 'start' : i === counts.length ? 'end' : 'middle';
      root.appendChild(svg('text', { class: 'tick', x, y: T + h + 17, 'text-anchor': anchor }, fmt(edges[i])));
    }
    if (logBins) {
      root.appendChild(svg('text', { class: 'tick', x: L + w, y: H - 2, 'text-anchor': 'end' }, t('unc.logScale')));
    }
    for (const key of ['p05', 'p95']) {
      const v = result[key];
      if (v === null || v === undefined) continue;
      const x = xOf(v);
      root.appendChild(svg('line', { class: 'pct', x1: x, y1: T, x2: x, y2: T + h }));
    }
    const point = result.pointEstimate;
    if (point !== null && point !== undefined) {
      const x = xOf(point);
      root.appendChild(svg('line', { class: 'marker', x1: x, y1: T - 4, x2: x, y2: T + h }));
      const anchor = x > L + w * 0.75 ? 'end' : x < L + w * 0.25 ? 'start' : 'middle';
      root.appendChild(svg('text', { class: 'marker-label', x, y: T - 8, 'text-anchor': anchor },
        t('unc.point') + ' ' + fmt(point)));
    }
    return root;
  }

  function paint() {
    clear(root);
    if (isEta(ctx)) {
      root.appendChild(etaNotice(ctx));
      return;
    }
    root.append(toolbar, message, stats, meta, warnings, chartBox);
    paintToolbar();
    message.hidden = Boolean(result);
    message.textContent = t('unc.notRun');
    paintStats();
    meta.hidden = !result;
    const extra = [];
    if (result) {
      extra.push(t(result.method === 'tree' ? 'unc.method.tree' : 'unc.method.cutsets'));
      extra.push(t('unc.completed', {
        completed: result.completed,
        requested: result.requested,
        seed: result.seed,
        s: (result.elapsedMs / 1000).toFixed(1),
      }));
      if (stale) extra.push(t('unc.staleNote'));
      meta.textContent = extra.join(' · ');
    }
    const list = result ? (result.warnings || []).slice() : [];
    renderWarnings(ctx, warnings, list);
    if (result) {
      const certain = (result.certainEvents || []).length;
      if (certain && (result.uncertainEvents || []).length) {
        warnings.appendChild(el('li', { text: t('unc.certain', { n: certain }) }));
      }
      if (result.truncatedByTime) warnings.appendChild(el('li', { text: t('unc.truncatedByTime') }));
      warnings.hidden = warnings.childNodes.length === 0;
    }
    clear(chartBox);
    const figure = result ? chart() : null;
    if (figure) chartBox.appendChild(figure);
  }

  runBtn.addEventListener('click', () => run());
  saveBtn.addEventListener('click', () => saveDefaults());
  for (const input of [inN, inSeed]) input.addEventListener('input', () => edited.add(input));
  for (const input of [inN, inSeed, inTime]) {
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        run();
      }
    });
  }

  const repaint = () => {
    if (!running) paint();
    else paintToolbar();
  };
  window.addEventListener('fta:language', repaint);
  const unSig = ctx.onSigFigs(repaint);

  paint();

  return {
    activate() {
      if (!running) paint();
    },
    deactivate() {},
    onStale() {
      if (result) stale = true;
      if (!running) paint();
    },
    dispose() {
      if (ticker) clearInterval(ticker);
      window.removeEventListener('fta:language', repaint);
      if (typeof unSig === 'function') unSig();
      root.remove();
    },
  };
}

export default mount;
