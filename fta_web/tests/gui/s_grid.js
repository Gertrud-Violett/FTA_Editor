// Grid tab (F3): UI-9, UI-10, UI-12, FN-46, FN-47, FN-50, FN-51 (header unit), PERF-6, PERF-7.
// node s_grid.js <url> <label> <root>
//
// Written from .division/features/F3/DESIGN.md (the data-testid hooks and the en/ja texts are
// the ones of its section 7 and 8) before the Grid tab exists. It builds its own documents through
// the API and opens the performance fixtures from the sandbox root; it does not need the file
// that section `core` saves.
//
// Criterion -> check map (BRIEF criteria of F3):
//   1  Grid tab, headers en/ja with units, q read-only on a rate row ..... criterion1_*
//   2  sort by any column, filter by text, one row in many ............... criterion2_*
//   3  summary after a paste: 3 good and 2 bad rows ...................... criterion3_*
//   4  every input of fixtures/number_inputs.json, columns q lambda T tau mu:
//        typed in the existing field (Details for q, Quantification tab for the others),
//        typed in the grid cell, pasted into the grid ..................... criterion4_*
//        (the beta / alpha_k checks in the CCF tab are added when F2 / F2A are merged)
//   5  sort + filter + 3 x 3 block on the intended ids, stale paste,
//        edit then paste (no 409), one Ctrl+Z after a 50-row paste ......... criterion5_*
//   6  FN-50 rows decided in the browser (and, through the browser, the id / q / invalid-cell
//        rows decided by the server) ...................................... criterion6_*
//   7  FN-51: the header unit picker /h /y FIT ............................ criterion7_*
//   9  PERF-6 -> PERF-6.json, 10 PERF-7 -> PERF-7.json ..................... criterion9_*, criterion10_*
//   also: grid shortcuts, grid headers fit, focus selects a cell, empty state, screenshots.
//
// Where the Grid tab does not exist yet, the checks that need it FAIL with the reason and the
// section ends; the typed-in-the-existing-field half of criterion 4 runs regardless, because the
// existing fields exist today (it keeps the vector file honest).
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');
const L = require('./lib');

const FIX = path.join(L.REPO, 'fta_web', 'tests', 'fixtures');
const VECTORS = JSON.parse(fs.readFileSync(path.join(FIX, 'number_inputs.json'), 'utf8'));
const PERF_BOUNDS = { PERF6: 2000, PERF7: 1000 }; // ms, provisional (SPEC 4)
const RUNS = 5;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const sha256 = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const median = (xs) => { const s = xs.slice().sort((a, b) => a - b); const n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; };

// ---- hooks (DESIGN section 8) ---------------------------------------------------------------
const TID = (id) => `[data-testid="${id}"]`;
const CELL = (nodeId, col) => `[data-testid="grid-cell"][data-node-id="${nodeId}"][data-column="${col}"]`;
const ROWS = TID('grid-row');
const COLUMN_ORDER = ['id', 'name', 'model', 'lambda', 'T', 'tau', 'mu', 'q', 'source', 'tags'];
const HEADERS = {
  en: { id: 'ID', name: 'Name', model: 'Model', lambda: 'λ', T: 'T (h)', tau: 'τ (h)', mu: 'μ (/h)', q: 'q (dimensionless)', source: 'Source', tags: 'Tags' },
  ja: { id: 'ID番号', name: '名前', model: 'モデル', lambda: 'λ', T: 'T (h)', tau: 'τ (h)', mu: 'μ (/h)', q: 'q (無次元)', source: '出典', tags: 'タグ' },
};
const UNIT_TEXT = { T: 'h', tau: 'h', mu: '/h', q: { en: 'dimensionless', ja: '無次元' } };
const MODEL_NAMES = {
  en: { fixed: 'Fixed probability', rate: 'Failure rate', standby: 'Periodically tested standby', repairable: 'Repairable' },
  ja: { fixed: '固定確率', rate: '故障率', standby: '定期試験される待機系', repairable: '修理可能' },
};
const STALE_TEXT = 'The analysis changed; paste again';
const LAMBDA_FACTOR = { h: 1, y: 8760, FIT: 1e9 };

/** formatPlain of tabs/analysis_common.js (numbers that are not probabilities). */
function plain(value) {
  if (value === null || value === undefined || value === '') return '';
  const num = Number(value);
  if (!Number.isFinite(num)) return '';
  if (num !== 0 && (Math.abs(num) < 1e-3 || Math.abs(num) >= 1e7)) return num.toExponential(6).replace(/\.?0+e/, 'e').replace('e+', 'e');
  return String(Number(num.toPrecision(10)));
}
const squash = (s) => String(s).replace(/[▲▼]/g, '').replace(/\s+/g, '');
const close = (a, b) => {
  if (a === null || a === undefined || b === null || b === undefined) return (a === null || a === undefined) && (b === null || b === undefined);
  return a === b || Math.abs(a - b) <= 1e-12 * Math.max(Math.abs(a), Math.abs(b));
};

/** Poll `fn` until it answers something truthy; null after `timeout` ms. */
async function until(fn, timeout = 3000, step = 25) {
  const t0 = Date.now();
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() - t0 > timeout) return null;
    await sleep(step);
  }
}

// ---- page-side helpers ----------------------------------------------------------------------
const nodeOf = (page, id) => page.evaluate(async (i) => {
  const { store } = await import('/static/js/store.js');
  const n = store.findNode(i);
  if (!n) return null;
  return {
    name: n.name,
    probability: n.probability,
    quant: n.quant ? JSON.parse(JSON.stringify(n.quant)) : null,
    trace: n.trace ? JSON.parse(JSON.stringify(n.trace)) : null,
  };
}, id);

/** PATCH a node from the page and merge the answer into the page's store (no reload). */
const pagePatch = (page, id, body) => page.evaluate(async ([i, b]) => {
  const token = sessionStorage.getItem('fta.session.token');
  const { store } = await import('/static/js/store.js');
  const r = await fetch('/api/nodes/' + encodeURIComponent(i), {
    method: 'PATCH',
    headers: { 'X-FTA-Token': token, 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(b),
  });
  const j = await r.json();
  if (!r.ok || j.ok === false) throw new Error('PATCH ' + i + ' -> ' + r.status + ' ' + JSON.stringify(j).slice(0, 200));
  store.applyMutation(j);
}, [id, body]);

const pageSelect = (page, id) => page.evaluate(async (i) => { (await import('/static/js/store.js')).store.select(i); }, id);
const refreshShell = (page) => page.evaluate(() => window.ftaShell.refresh());

/** The quant value (or probability for q) as the page's store holds it; undefined -> null. */
function storedOf(node, col) {
  if (!node) return undefined;
  if (col === 'q') return node.probability;
  const v = node.quant ? node.quant[col] : undefined;
  return v === undefined ? null : v;
}

async function settledHeadline(page, quietMs) {
  let last = null;
  let since = Date.now();
  for (;;) {
    const now = await page.evaluate(() => document.getElementById('headline-value').textContent.trim());
    if (now !== last) { last = now; since = Date.now(); }
    if (Date.now() - since >= (quietMs || 1500) && now !== '' && now !== '—') return now;
    await sleep(100);
  }
}

/** Open a file the way the Load action does (as tests/perf/baseline_browser.js). */
async function openInPage(page, file) {
  await page.evaluate(async (p) => {
    const token = sessionStorage.getItem('fta.session.token');
    const { store } = await import('/static/js/store.js');
    const r = await fetch('/api/file/open', {
      method: 'POST',
      headers: { 'X-FTA-Token': token, 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ path: p, force: true }),
    });
    const payload = await r.json();
    if (!r.ok || payload.ok === false) throw new Error('open failed: ' + JSON.stringify(payload).slice(0, 300));
    delete payload.ok;
    store.setState({ ...(store.state || {}), ...payload });
    window.dispatchEvent(new CustomEvent('fta:document'));
    store.select(store.state.tree.id);
  }, file);
}

// ---- grid helpers ---------------------------------------------------------------------------
async function openGrid(app) {
  await app.clickTab('grid');
  await app.page.waitForSelector(TID('grid-root'), { timeout: 10000 });
  await app.page.waitForSelector(TID('grid-table'), { timeout: 10000 });
}
const rowOrder = (page) => page.evaluate(() => Array.from(document.querySelectorAll('[data-testid="grid-row"]')).map((r) => r.dataset.nodeId));
const cellText = (page, id, col) => page.evaluate((s) => { const c = document.querySelector(s); return c ? c.textContent.trim() : null; }, CELL(id, col));
const cellRaw = (page, id, col) => page.evaluate((s) => { const c = document.querySelector(s); return c ? c.dataset.raw : null; }, CELL(id, col));
const gridCount = (page) => page.evaluate(() => { const c = document.querySelector('[data-testid="grid-count"]'); return c ? { shown: Number(c.dataset.shown), total: Number(c.dataset.total) } : null; });

async function setFilter(app, text) {
  await app.page.locator(TID('grid-filter')).fill(text);
  await sleep(350); // 120 ms debounce + repaint
}
async function setSort(app, col, dir) {
  const btn = app.page.locator(`${TID('grid-sort')}[data-column="${col}"]`);
  for (let i = 0; i < 3; i += 1) {
    const cur = await app.page.locator(`${TID('grid-th')}[data-column="${col}"]`).getAttribute('aria-sort');
    if (cur === dir) return true;
    await btn.click();
    await sleep(80);
  }
  return false;
}
async function setHidden(app, hideKeys) {
  const { page } = app;
  const btn = page.locator(TID('grid-columns-button'));
  await btn.click();
  for (const col of ['model', 'lambda', 'T', 'tau', 'mu', 'q', 'source', 'tags']) {
    const box = page.locator(`${TID('grid-column-toggle')}[data-column="${col}"]`);
    if (!(await box.count())) continue;
    const shown = await box.isChecked();
    const wantShown = !hideKeys.includes(col);
    if (shown !== wantShown) await box.click();
  }
  if ((await btn.getAttribute('aria-expanded')) === 'true') await page.keyboard.press('Escape');
  await sleep(100);
}
async function setLambdaUnit(app, unit) {
  await app.page.locator(TID('grid-lambda-unit')).selectOption(unit);
  await sleep(120);
}

/**
 * Click the anchor cell, then dispatch a synthetic paste event on it (DESIGN 5.1) and wait for the
 * summary to be redrawn and the paste to finish. Returns {ticked}. `click: false` focuses the anchor
 * without scrolling anything (a pane too small to show the cell: a click would scroll the page).
 */
async function doPaste(app, anchorSel, text, { wait = true, click = true } = {}) {
  if (click) await app.page.locator(anchorSel).click();
  else await app.page.evaluate((s) => document.querySelector(s).focus({ preventScroll: true }), anchorSel);
  return app.page.evaluate(async ([selector, clip, waitFor]) => {
    const target = document.querySelector(selector);
    const sum = document.querySelector('[data-testid="grid-summary"]');
    const root = document.querySelector('[data-testid="grid-root"]');
    let ticked = false;
    const obs = new MutationObserver(() => { ticked = true; });
    obs.observe(sum, { childList: true, subtree: true, characterData: true, attributes: true });
    const dt = new DataTransfer();
    dt.setData('text/plain', clip);
    const t0 = performance.now();
    target.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
    if (waitFor) {
      const limit = t0 + 8000;
      while (!ticked && performance.now() < limit) await new Promise((r) => setTimeout(r, 10));
      while (root.dataset.state === 'pasting' && performance.now() < limit) await new Promise((r) => setTimeout(r, 10));
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    } else {
      await new Promise((r) => setTimeout(r, 200));
    }
    obs.disconnect();
    return { ticked, ms: performance.now() - t0 };
  }, [anchorSel, text, wait]);
}

const readSummary = (page) => page.evaluate(() => {
  const q = (s) => document.querySelector(s);
  const applied = q('[data-testid="grid-summary-applied"]');
  const refusedCount = q('[data-testid="grid-summary-refused-count"]');
  const err = q('[data-testid="grid-summary-error"]');
  const msg = q('[data-testid="grid-message"]');
  return {
    applied: applied ? Number(applied.dataset.count) : null,
    appliedText: applied ? applied.textContent.trim() : '',
    refused: refusedCount ? Number(refusedCount.dataset.count) : null,
    refusedText: refusedCount ? refusedCount.textContent.trim() : '',
    items: Array.from(document.querySelectorAll('[data-testid="grid-summary-refused-item"]')).map((li) => ({
      clipRow: Number(li.dataset.clipRow), column: li.dataset.column, code: li.dataset.code, text: li.textContent.trim().replace(/\s+/g, ' '),
    })),
    error: err ? { code: err.dataset.code, text: err.textContent.trim() } : null,
    message: msg ? { text: msg.textContent.trim(), code: msg.dataset.code || '' } : null,
    text: (q('[data-testid="grid-summary"]') || { textContent: '' }).textContent.trim().replace(/\s+/g, ' '),
  };
});

/**
 * Dispatch a paste and return at once (pasteFinish waits for the outcome). With click: false the paste
 * goes to the cell that is already selected, e.g. the cell that has just been edited.
 */
async function pasteStart(app, anchorSel, text, { click = true } = {}) {
  if (click) await app.page.locator(anchorSel).click();
  await app.page.evaluate(([selector, clip]) => {
    const target = document.querySelector(selector);
    const sum = document.querySelector('[data-testid="grid-summary"]');
    const st = { ticked: false, obs: null };
    st.obs = new MutationObserver(() => { st.ticked = true; });
    st.obs.observe(sum, { childList: true, subtree: true, characterData: true, attributes: true });
    window.__pasteWatch = st;
    const dt = new DataTransfer();
    dt.setData('text/plain', clip);
    target.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
  }, [anchorSel, text]);
}
async function pasteFinish(app) {
  return app.page.evaluate(async () => {
    const st = window.__pasteWatch;
    const root = document.querySelector('[data-testid="grid-root"]');
    const limit = performance.now() + 8000;
    while (!st.ticked && performance.now() < limit) await new Promise((r) => setTimeout(r, 10));
    while (root.dataset.state === 'pasting' && performance.now() < limit) await new Promise((r) => setTimeout(r, 10));
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    st.obs.disconnect();
    return st.ticked;
  });
}

/**
 * Hold the answer of every PATCH /api/nodes/<id> until release(): the request goes to the server, which
 * applies it, and the page gets the answer only after release() (DESIGN 5.1, the in-flight cases).
 */
async function holdPatches(page) {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  let reached;
  const reachedPromise = new Promise((resolve) => { reached = resolve; });
  const handler = async (route) => {
    if (route.request().method() !== 'PATCH') { await route.continue(); return; }
    const response = await route.fetch();
    reached();
    await gate;
    await route.fulfill({ response });
  };
  await page.route('**/api/nodes/*', handler);
  return {
    reached: reachedPromise,
    release,
    async stop() { release(); await page.unroute('**/api/nodes/*', handler); },
  };
}

/** Answer the page's periodic GET /api/revision with the revision it already holds, so it cannot redraw by itself. */
async function stubRevisionPoll(page) {
  const held = await page.evaluate(async () => {
    const { store } = await import('/static/js/store.js');
    const s = store.state || {};
    return { revision: s.revision, documentSerial: s.documentSerial, dirty: Boolean(s.dirty), currentPath: s.currentPath || null };
  });
  const handler = (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(Object.assign({ ok: true }, held)) });
  await page.route('**/api/revision', handler);
  return { async stop() { await page.unroute('**/api/revision', handler); } };
}

// ---- documents ------------------------------------------------------------------------------
async function addNode(app, parentId, name, extra) {
  const r = await app.api('post', '/nodes', Object.assign({ parentId, name, probability: 1 }, extra || {}));
  if (r.__error) throw new Error('POST /nodes ' + name + ': ' + JSON.stringify(r));
  return r.nodeId;
}
const nodeCount = async (app) => {
  const st = await app.api('get', '/state');
  let n = 0;
  const walk = (x) => { n += 1; (x.children || []).forEach(walk); };
  walk(st.tree);
  return n;
};

/** Eleven basic events: Pump A..H (rate), Valve X (fixed), Valve Y (standby), Motor Z (repairable). */
const PUMPS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];
const KEEP = new Set(['A', 'C', 'E']);
async function buildMain(app) {
  await app.api('post', '/new', { force: true });
  const ids = {};
  const cooling = await addNode(app, 'root', 'Cooling loop', { logicGate: 'OR' });
  const drive = await addNode(app, 'root', 'Drive train', { logicGate: 'OR' });
  const pump = (letter) => {
    const i = PUMPS.indexOf(letter);
    return { probability: 0.5, quant: { model: 'rate', lambda: 2e-5 * (i + 1), T: 100 * (i + 1), source: KEEP.has(letter) ? 'keep' : undefined } };
  };
  for (const letter of ['H', 'C', 'F', 'A']) ids[letter] = await addNode(app, cooling, 'Pump ' + letter, pump(letter));
  for (const letter of ['B', 'D', 'G', 'E']) ids[letter] = await addNode(app, drive, 'Pump ' + letter, pump(letter));
  ids.X = await addNode(app, 'root', 'Valve X', { probability: 0.012345, quant: { model: 'fixed', source: 'vendor-zeta-9' } });
  ids.Y = await addNode(app, 'root', 'Valve Y', { probability: 0.5, quant: { model: 'standby', lambda: 1e-4, tau: 500 } });
  ids.Z = await addNode(app, 'root', 'Motor Z', { probability: 0.5, quant: { model: 'repairable', lambda: 1e-4, mu: 0.2 } });
  await app.api('patch', '/nodes/' + ids.A, { trace: { tags: ['hydraulic', 'main'] } });
  await refreshShell(app.page);
  return ids;
}
/** Put every pump back to its start values (and names) through the page, one PATCH each. */
async function resetPumps(app, ids) {
  for (const letter of PUMPS) {
    const i = PUMPS.indexOf(letter);
    await pagePatch(app.page, ids[letter], {
      name: 'Pump ' + letter,
      quant: { model: 'rate', lambda: 2e-5 * (i + 1), T: 100 * (i + 1), source: KEEP.has(letter) ? 'keep' : null },
    });
  }
  await sleep(150);
}

// ---- criterion 4: one input, three paths ----------------------------------------------------
const NUM_COLS = ['q', 'lambda', 'T', 'tau', 'mu'];
const NUM_NODE = { q: 'fixed', lambda: 'rate', T: 'rate', tau: 'standby', mu: 'repairable' };
const SENT = { q: 0.77, lambda: 0.0077, T: 777, tau: 777, mu: 0.77 };

async function buildNumbers(app) {
  await app.api('post', '/new', { force: true });
  const ids = {};
  ids.fixed = await addNode(app, 'root', 'Num fixed', { probability: 0.5, quant: { model: 'fixed' } });
  ids.rate = await addNode(app, 'root', 'Num rate', { probability: 0.5, quant: { model: 'rate', lambda: SENT.lambda, T: SENT.T } });
  ids.standby = await addNode(app, 'root', 'Num standby', { probability: 0.5, quant: { model: 'standby', lambda: SENT.lambda, tau: SENT.tau } });
  ids.repairable = await addNode(app, 'root', 'Num repairable', { probability: 0.5, quant: { model: 'repairable', lambda: SENT.lambda, mu: SENT.mu } });
  await refreshShell(app.page);
  return ids;
}
async function resetSentinel(page, id, col) {
  await pagePatch(page, id, col === 'q' ? { probability: SENT.q } : { quant: { [col]: SENT[col] } });
}
const isSentinel = (node, col) => close(storedOf(node, col), SENT[col]);

/** What came of one input: 'refused' | 'accepted' (+ value) | 'unchanged' | 'none'. */
function verdict(want, text, route, got) {
  const blank = text.trim() === '';
  if (route === 'paste' && blank) return got.kind === 'unchanged' ? null : `blank cell pasted: expected unchanged, got ${got.kind}`;
  if (!want.ok) return got.kind === 'refused' ? null : `expected refused, got ${got.kind}${got.kind === 'accepted' ? ' ' + JSON.stringify(got.value) : ''}`;
  if (got.kind !== 'accepted') return `expected ${JSON.stringify(want.value)}, got ${got.kind}`;
  return close(got.value, want.value) ? null : `expected ${JSON.stringify(want.value)}, stored ${JSON.stringify(got.value)}`;
}

/** Route 1: type into the field that exists today. */
async function typeIntoField(app, ids, col, text, field) {
  const { page } = app;
  const id = ids[NUM_NODE[col]];
  await resetSentinel(page, id, col);
  const shown = col === 'q' ? String(SENT.q) : plain(SENT[col]);
  let ready = await until(async () => (await field.inputValue()) === shown, 800);
  if (!ready) {
    // a refused text stays in the box (it is never lost): put the stored value back by hand
    await field.fill(shown);
    await field.press('Tab');
    ready = await until(async () => (await field.inputValue()) === shown, 2500);
  }
  if (!ready) return { kind: 'none', note: 'field never showed the starting value' };
  await field.click();
  await field.fill(text);
  await page.keyboard.press('Enter');
  const r = await until(async () => {
    if ((await field.getAttribute('aria-invalid')) === 'true') return 'refused';
    const node = await nodeOf(page, id);
    if (!isSentinel(node, col)) return { accepted: storedOf(node, col) };
    return null;
  }, 2500);
  if (r === 'refused') return { kind: 'refused' };
  if (r) return { kind: 'accepted', value: r.accepted };
  return { kind: 'none' };
}

/** Route 2: type into the grid cell (Enter opens the editor, Enter commits). */
async function typeIntoCell(app, ids, col, text) {
  const { page } = app;
  const id = ids[NUM_NODE[col]];
  await resetSentinel(page, id, col);
  const ready = await until(async () => {
    const raw = await cellRaw(page, id, col);
    return raw !== null && close(Number(raw), SENT[col]);
  }, 3000);
  if (!ready) return { kind: 'none', note: 'cell never showed the starting value' };
  await page.locator(CELL(id, col)).click();
  await page.keyboard.press('Enter');
  const input = page.locator(TID('grid-input'));
  if (!(await until(async () => (await input.count()) > 0, 2000))) return { kind: 'none', note: 'no editor opened' };
  await input.fill(text);
  await page.keyboard.press('Enter');
  const r = await until(async () => {
    if ((await input.count()) && (await input.getAttribute('aria-invalid')) === 'true') return 'refused';
    const node = await nodeOf(page, id);
    if (!isSentinel(node, col)) return { accepted: storedOf(node, col) };
    return null;
  }, 2500);
  if (await input.count()) await page.keyboard.press('Escape');
  await until(async () => (await input.count()) === 0, 1500);
  if (r === 'refused') return { kind: 'refused' };
  if (r) return { kind: 'accepted', value: r.accepted };
  return { kind: 'none' };
}

/** Route 3: paste the text into the cell (a one-cell clipboard). */
async function pasteIntoCell(app, ids, col, text) {
  const { page } = app;
  const id = ids[NUM_NODE[col]];
  await resetSentinel(page, id, col);
  const ready = await until(async () => {
    const raw = await cellRaw(page, id, col);
    return raw !== null && close(Number(raw), SENT[col]);
  }, 3000);
  if (!ready) return { kind: 'none', note: 'cell never showed the starting value' };
  const blank = text.trim() === '';
  await doPaste(app, CELL(id, col), text, { wait: !blank });
  if (blank) {
    const node = await nodeOf(page, id);
    return isSentinel(node, col) ? { kind: 'unchanged' } : { kind: 'accepted', value: storedOf(node, col) };
  }
  const summary = await readSummary(page);
  const node = await nodeOf(page, id);
  if (summary.items.some((i) => i.column === col)) return { kind: 'refused' };
  if (!isSentinel(node, col)) return { kind: 'accepted', value: storedOf(node, col) };
  return { kind: 'none', summary: summary.text.slice(0, 120) };
}

async function runVectors(app, ids, route, gridAvailable) {
  const { page } = app;
  await page.evaluate(() => { try { localStorage.setItem('fta.lambdaUnit', 'h'); } catch (_e) { /* */ } });
  for (const col of NUM_COLS) {
    const bad = [];
    let field = null;
    if (route === 'field') {
      if (col === 'q') {
        await app.clickTab('details');
        await pageSelect(page, ids.fixed);
        await page.waitForFunction((i) => { const c = document.querySelector('#details-root .fta-details-meta code'); return c && c.textContent === i; }, ids.fixed, { timeout: 8000 });
        field = page.locator('#details-root .fta-details-form .fta-field').filter({ has: page.locator('label', { hasText: 'Probability (base)' }) }).first().locator('input').first();
      } else {
        await app.clickTab('quant');
        await pageSelect(page, ids[NUM_NODE[col]]);
        await page.waitForSelector(`#tabpanel-quant input[data-field="${col}"]`, { timeout: 8000 });
        field = page.locator(`#tabpanel-quant input[data-field="${col}"]`);
      }
    } else {
      await openGrid(app);
    }
    for (const item of VECTORS.inputs) {
      let got;
      try {
        if (route === 'field') got = await typeIntoField(app, ids, col, item.text, field);
        else if (route === 'cell') got = await typeIntoCell(app, ids, col, item.text);
        else got = await pasteIntoCell(app, ids, col, item.text);
      } catch (e) {
        got = { kind: 'none', note: String(e.message).slice(0, 100) };
      }
      const why = verdict(item.expect[col], item.text, route, got);
      if (why) bad.push({ text: item.text, why, note: got.note });
    }
    const label = { field: col === 'q' ? 'typed in the Details panel' : 'typed in the Quantification tab', cell: 'typed in the grid cell', paste: 'pasted into the grid' }[route];
    L.check(`criterion4_${route}: ${col} ${label}: all ${VECTORS.inputs.length} inputs give the expected result`, bad.length === 0, bad.slice(0, 6));
  }
  void gridAvailable;
}

// ---- performance ----------------------------------------------------------------------------
function gitHead() {
  try { return execFileSync('git', ['rev-parse', 'HEAD'], { cwd: L.REPO, encoding: 'utf8' }).trim(); } catch (_e) { return 'unknown'; }
}
function perfOutDir() {
  return path.resolve(process.env.FTA_PERF_OUT_DIR || path.join(L.REPO, '.division', 'artifacts', 'perf'));
}
function writePerf(name, data) {
  const dir = perfOutDir();
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, name + '.json'), JSON.stringify(data, null, 2) + '\n');
}

async function perf7(url, root) {
  const file = path.join(root, 'perf_grid_500.json');
  const runs = [];
  let browser = '';
  for (let i = 0; i < RUNS + 1; i += 1) { // the first run is the discarded warm-up
    const app = await L.openApp(url, { prefs: { 'fta.advanced': '1', 'fta.sigFigs': '6' }, viewport: { width: 1600, height: 1000 } });
    try {
      browser = app.context.browser().version();
      await openInPage(app.page, file);
      await settledHeadline(app.page, 1500);
      await app.page.evaluate(() => {
        window.__p7 = { t0: null, t1: null };
        const state = window.__p7;
        const tab = document.getElementById('tab-grid');
        tab.addEventListener('click', () => { if (state.t0 === null) state.t0 = performance.now(); }, true);
        state.done = new Promise((resolve) => {
          let waiting = false;
          const check = () => {
            if (waiting || state.t0 === null) return;
            if (document.querySelectorAll('[data-testid="grid-row"]').length !== 500) return;
            waiting = true;
            requestAnimationFrame(() => { state.t1 = performance.now(); observer.disconnect(); resolve(true); });
          };
          const observer = new MutationObserver(check);
          observer.observe(document.body, { childList: true, subtree: true });
          setTimeout(() => resolve(false), 20000);
        });
      });
      await app.page.locator('#tab-grid').click();
      const ok = await app.page.evaluate(() => window.__p7.done);
      const ms = await app.page.evaluate(() => (window.__p7.t1 === null ? null : window.__p7.t1 - window.__p7.t0));
      if (!ok || ms === null) throw new Error('the 500 grid rows were not drawn within 20 s');
      if (i > 0) runs.push(ms);
      console.log(`INFO PERF-7 run ${i}${i === 0 ? ' (warm-up, discarded)' : ''}: ${ms.toFixed(1)} ms`);
    } finally {
      await app.context.close();
    }
  }
  return { runs, browser, med: median(runs) };
}

async function perf6(app, root, tsv) {
  const { page } = app;
  const file = path.join(root, 'perf_grid_500.json');
  await openInPage(page, file);
  const h0 = await settledHeadline(page, 1500);
  await openGrid(app);
  await setLambdaUnit(app, 'y');
  await setHidden(app, ['tau', 'mu', 'q']);
  const anchor = CELL('E00_00', 'lambda');
  await page.waitForSelector(anchor, { timeout: 10000 });

  async function timedPaste(finalHeadline) {
    await page.locator(anchor).click();
    return page.evaluate(async ([selector, clip, target]) => {
      const cell = document.querySelector(selector);
      const head = document.getElementById('headline-value');
      let t1 = null;
      let waiting = false;
      const done = new Promise((resolve) => {
        const check = () => {
          if (waiting) return;
          const applied = document.querySelector('[data-testid="grid-summary-applied"]');
          if (!applied || applied.dataset.count !== '500') return;
          if (target && head.textContent.trim() !== target) return;
          waiting = true;
          requestAnimationFrame(() => { t1 = performance.now(); observer.disconnect(); resolve(true); });
        };
        const observer = new MutationObserver(check);
        observer.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['data-count'] });
        setTimeout(() => resolve(false), 20000);
      });
      const dt = new DataTransfer();
      dt.setData('text/plain', clip);
      const t0 = performance.now();
      cell.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
      const ok = await done;
      return { ok, ms: t1 === null ? null : t1 - t0 };
    }, [anchor, tsv, finalHeadline || null]);
  }

  // Warm-up (discarded): learn the headline the finished document shows.
  const warm = await timedPaste(null);
  if (!warm.ok) throw new Error('PERF-6 warm-up: the summary never showed 500 rows applied');
  const finished = await settledHeadline(page, 1500);
  if (finished === h0) throw new Error('PERF-6: the headline did not change (' + h0 + '); the paste changed nothing');
  console.log(`INFO PERF-6 warm-up (discarded): ${warm.ms.toFixed(1)} ms; headline ${h0} -> ${finished}`);
  const runs = [];
  for (let i = 0; i < RUNS; i += 1) {
    await openInPage(page, file);
    const back = await settledHeadline(page, 1500);
    if (back !== h0) throw new Error(`PERF-6: reopening gave headline ${back}, not ${h0}`);
    await page.waitForSelector(anchor, { timeout: 10000 });
    const res = await timedPaste(finished);
    if (!res.ok) throw new Error('PERF-6 run ' + (i + 1) + ': summary 500 and the final headline were not both shown within 20 s');
    runs.push(res.ms);
    console.log(`INFO PERF-6 run ${i + 1}: ${res.ms.toFixed(1)} ms`);
  }
  return { runs, med: median(runs), h0, finished };
}

// ---- main -----------------------------------------------------------------------------------
async function main(url, label, root) {
  L.setSection('grid[' + label + ']');
  for (const name of ['perf_grid_500.json', 'perf_grid_500_paste.tsv']) fs.copyFileSync(path.join(FIX, name), path.join(root, name));

  const app = await L.openApp(url, { prefs: { 'fta.advanced': '0' }, viewport: { width: 1600, height: 1000 } });
  const { page } = app;
  page.setDefaultTimeout(8000);
  const posts = [];
  page.on('request', (r) => { if (r.method() === 'POST' && r.url().includes('/api/grid/paste')) posts.push(Date.now()); });
  const phaseFailures = [];
  const phase = async (name, fn) => {
    try { await fn(); } catch (e) {
      phaseFailures.push(name);
      L.check(`${name}: finished without an exception`, false, String((e && e.stack) || e).slice(0, 600));
    }
  };

  // ---- the Grid tab exists (criterion 1) -------------------------------------------------------
  const tabCount = await page.locator('#tab-grid').count();
  L.check('criterion1_tab: the Grid tab button exists (#tab-grid)', tabCount === 1, tabCount);
  let gridAvailable = false;
  if (tabCount === 1) {
    const hiddenInBasic = !(await page.locator('#tab-grid').isVisible());
    L.check('criterion1_tab: the Grid tab is an Advanced tab (hidden in basic mode)', hiddenInBasic);
    await app.setAdvanced(true);
    const visible = await page.locator('#tab-grid').isVisible();
    L.check('criterion1_tab: the Grid tab is shown once Advanced is on', visible);
    gridAvailable = visible;
  } else {
    await app.setAdvanced(true);
  }

  // ---- criterion 4, first half: the fields that exist today -------------------------------------
  let numIds = null;
  await phase('criterion4_field', async () => {
    numIds = await buildNumbers(app);
    await runVectors(app, numIds, 'field', gridAvailable);
  });

  if (!gridAvailable) {
    const needs = [
      'criterion1: headers in en and ja with units, q read-only on a rate row, tags separated by "; "',
      'criterion2: sort by any column and filter by text',
      'criterion3: summary after a paste of 3 good and 2 bad rows',
      'criterion4_cell: every input typed into the grid cell',
      'criterion4_paste: every input pasted into the grid',
      'criterion5: sort + filter + 3x3 paste, stale paste, edit then paste, one Ctrl+Z after 50 rows',
      'criterion6: the FN-50 paste cases',
      'criterion7: the header unit picker (/h, /y, FIT)',
      'criterion9: PERF-6 timing (PERF-6.json)',
      'criterion10: PERF-7 timing (PERF-7.json)',
      'grid shortcuts, grid headers fit, grid summary in view (wide, 1100x800 with toolbar check T, 800x900, narrow pane with T, minimum pane 140 px wide and narrow: grid-root 72 px, toolbar <= 28 px, T, title/applied heights and budget, S line clipping, stale-paste message and error inside grid-root; grid-columns-open and grid-narrow shots), grid paste after own edit, grid paste after foreign write, focus selects a cell',
      'grid eta: the paste is answered with MODE_UNSUPPORTED, no "analysis changed" text, nothing applied, the ETA notice replaces the table (grid-eta shot)',
      'grid empty state in en and ja (grid-empty shot)',
    ];
    for (const name of needs) L.check(`${name} (needs the Grid tab)`, false, 'there is no Grid tab (#tab-grid) in this build');
    const errs = app.errorsSince(0);
    L.check('no console errors in the grid run', errs.length === 0, errs);
    await app.context.close();
    return;
  }

  // ---- criterion 4, second half: the grid cell and the paste -------------------------------------
  await phase('criterion4_cell', async () => { await runVectors(app, numIds, 'cell', true); });
  await phase('criterion4_paste', async () => { await runVectors(app, numIds, 'paste', true); });

  // ---- the main document ---------------------------------------------------------------------
  let ids = null;
  await phase('setup', async () => {
    ids = await buildMain(app);
    await openGrid(app);
    const ok = await until(async () => { const c = await gridCount(page); return c && c.total === 11 && c.shown === 11; }, 6000);
    L.check('setup: the grid shows the 11 basic events (and no gate)', Boolean(ok), await gridCount(page));
  });
  if (!ids) { await app.context.close(); return; }

  // ---- criterion 1 --------------------------------------------------------------------------------
  await phase('criterion1', async () => {
    const readHeaders = () => page.evaluate(() => Array.from(document.querySelectorAll('[data-testid="grid-th"]')).map((th) => ({
      col: th.dataset.column, text: th.textContent, unit: th.dataset.unit, sort: th.getAttribute('aria-sort'),
      unitEl: (th.querySelector('[data-testid="grid-unit"]') || { textContent: null }).textContent,
    })));
    for (const lang of ['en', 'ja']) {
      await app.setLanguage(lang);
      await sleep(200);
      const heads = await readHeaders();
      L.check(`criterion1_headers[${lang}]: ten columns in the order id name model λ T τ μ q source tags`, JSON.stringify(heads.map((h) => h.col)) === JSON.stringify(COLUMN_ORDER), heads.map((h) => h.col));
      const bad = [];
      for (const h of heads) {
        const want = HEADERS[lang][h.col];
        if (h.col === 'lambda') {
          if (!squash(h.text).startsWith(squash(want))) bad.push({ col: h.col, text: h.text });
        } else if (squash(h.text) !== squash(want)) bad.push({ col: h.col, text: h.text, want });
      }
      L.check(`criterion1_headers[${lang}]: header texts name their units (${COLUMN_ORDER.map((c) => HEADERS[lang][c]).join(' | ')})`, bad.length === 0, bad);
      const units = {};
      for (const h of heads) if (h.unitEl !== null) units[h.col] = String(h.unitEl).replace(/[()（）\s]/g, '');
      const wantUnits = { T: UNIT_TEXT.T, tau: UNIT_TEXT.tau, mu: UNIT_TEXT.mu, q: UNIT_TEXT.q[lang] };
      L.check(`criterion1_units[${lang}]: T and τ in h, μ in /h, q dimensionless (grid-unit)`, JSON.stringify(units) === JSON.stringify(wantUnits), units);
      const lam = await page.evaluate(() => {
        const sel = document.querySelector('[data-testid="grid-lambda-unit"]');
        return sel ? { value: sel.value, options: Array.from(sel.options).map((o) => o.value), label: sel.selectedOptions[0].textContent.trim() } : null;
      });
      L.check(`criterion1_lambda[${lang}]: λ header holds a unit picker /h /y FIT, /h by default`, lam && lam.value === 'h' && JSON.stringify(lam.options) === '["h","y","FIT"]' && lam.label === '/h', lam);
      const modelNames = {};
      for (const key of ['rate', 'fixed']) modelNames[key] = await cellText(page, key === 'rate' ? ids.A : ids.X, 'model');
      L.check(`criterion1_model[${lang}]: the model column shows the Quantification tab's model names`, modelNames.rate === MODEL_NAMES[lang].rate && modelNames.fixed === MODEL_NAMES[lang].fixed, modelNames);
    }
    await app.setLanguage('en');

    // q read-only on a rate row, editable on a fixed row
    const qRate = await page.evaluate((s) => { const c = document.querySelector(s); return c ? { ro: c.dataset.readonly, aria: c.getAttribute('aria-readonly') } : null; }, CELL(ids.A, 'q'));
    L.check('criterion1_q: q is read-only on a rate row (data-readonly, aria-readonly)', qRate && qRate.ro === 'true' && qRate.aria === 'true', qRate);
    await page.locator(CELL(ids.A, 'q')).click();
    await page.keyboard.press('Enter');
    await sleep(250);
    L.check('criterion1_q: Enter on the q cell of a rate row opens no editor', (await page.locator(TID('grid-input')).count()) === 0);
    const qFixed = await page.evaluate((s) => { const c = document.querySelector(s); return c ? { ro: c.dataset.readonly || null, aria: c.getAttribute('aria-readonly') } : null; }, CELL(ids.X, 'q'));
    L.check('criterion1_q: q is editable on a fixed row', qFixed && qFixed.ro !== 'true' && qFixed.aria !== 'true', qFixed);
    await page.locator(CELL(ids.X, 'q')).click();
    await page.keyboard.press('Enter');
    L.check('criterion1_q: Enter on the q cell of a fixed row opens the editor', Boolean(await until(async () => (await page.locator(TID('grid-input')).count()) > 0, 1500)));
    await page.keyboard.press('Escape');
    await sleep(150);

    // q follows the significant-figures preference
    const bad = [];
    for (const sf of [2, 4, 6]) {
      await app.setSigFigs(sf);
      await sleep(200);
      const apiX = (await app.api('get', '/nodes/' + ids.X)).node;
      const apiA = (await app.api('get', '/nodes/' + ids.A)).node;
      const shownX = await cellText(page, ids.X, 'q');
      const shownA = await cellText(page, ids.A, 'q');
      if (shownX !== L.fmt(apiX.probability, sf)) bad.push({ sf, id: 'X', shownX, want: L.fmt(apiX.probability, sf) });
      if (shownA !== L.fmt(apiA.probability, sf)) bad.push({ sf, id: 'A', shownA, want: L.fmt(apiA.probability, sf) });
    }
    await app.setSigFigs(3);
    L.check('criterion1_q: q is shown with the significant-figures preference (2, 4, 6) on fixed and computed rows', bad.length === 0, bad);

    // unused cells, tags
    const unused = await page.evaluate(([x, a]) => {
      const get = (id, col) => { const c = document.querySelector(`[data-testid="grid-cell"][data-node-id="${id}"][data-column="${col}"]`); return c ? { unused: c.dataset.unused, ro: c.dataset.readonly, text: c.textContent.trim() } : null; };
      return { xLambda: get(x, 'lambda'), aTau: get(a, 'tau'), aT: get(a, 'T') };
    }, [ids.X, ids.A]);
    L.check('criterion1_unused: a field the model does not use is empty, read-only and marked (λ on fixed, τ on rate)',
      unused.xLambda && unused.xLambda.unused === 'true' && unused.xLambda.text === '' && unused.aTau && unused.aTau.unused === 'true' && unused.aTau.ro === 'true' && unused.aT && unused.aT.unused !== 'true', unused);
    L.check('criterion1_tags: tags are shown separated by "; "', (await cellText(page, ids.A, 'tags')) === 'hydraulic; main', await cellText(page, ids.A, 'tags'));
    L.check('criterion1_tags: data-raw of the tags cell is the "; "-joined list', (await cellRaw(page, ids.A, 'tags')) === 'hydraulic; main');
    // tags are entered separated by "; " (and the full-width separators of DESIGN 4.2)
    await page.locator(CELL(ids.B, 'tags')).click();
    await page.keyboard.press('Enter');
    const input = page.locator(TID('grid-input'));
    await input.waitFor({ state: 'visible', timeout: 3000 });
    await input.fill('x; y ；z、w ;; ');
    await page.keyboard.press('Enter');
    const tagsOk = await until(async () => { const n = await nodeOf(page, ids.B); return n && n.trace && JSON.stringify(n.trace.tags) === '["x","y","z","w"]'; }, 3000);
    L.check('criterion1_tags: tags typed with "; " (and the full-width ；and 、) are stored as a list', Boolean(tagsOk), await nodeOf(page, ids.B));
    await until(async () => (await input.count()) === 0, 1500);
    L.check('criterion1_tags: Enter commits and stays on the cell', await page.evaluate((s) => document.activeElement === document.querySelector(s), CELL(ids.B, 'tags')));
    await pagePatch(page, ids.B, { trace: { tags: null } });
    // the focus of a cell selects it (Tab then Ctrl+V works)
    await page.evaluate((s) => document.querySelector(s).focus(), CELL(ids.C, 'name'));
    await sleep(100);
    L.check('criterion1_focus: focusing a cell selects it (aria-selected)', (await page.locator(CELL(ids.C, 'name')).getAttribute('aria-selected')) === 'true');
    await app.shot('grid_en_light_' + label);
  });

  // ---- criterion 7 (FN-51) -------------------------------------------------------------------------
  await phase('criterion7', async () => {
    const expect = (unit) => plain(2e-5 * LAMBDA_FACTOR[unit]);
    const bad = [];
    for (const unit of ['y', 'FIT', 'h']) {
      await setLambdaUnit(app, unit);
      const head = await page.evaluate(() => { const th = document.querySelector('[data-testid="grid-th"][data-column="lambda"]'); const s = th.querySelector('select'); return { unit: th.dataset.unit, label: s ? s.selectedOptions[0].textContent.trim() : null }; });
      const text = await cellText(page, ids.A, 'lambda');
      const raw = Number(await cellRaw(page, ids.A, 'lambda'));
      const wantLabel = { h: '/h', y: '/y', FIT: 'FIT' }[unit];
      if (head.unit !== unit || head.label !== wantLabel) bad.push({ unit, head });
      if (text !== expect(unit)) bad.push({ unit, text, want: expect(unit) });
      if (!close(raw, 2e-5)) bad.push({ unit, raw, note: 'data-raw is always per hour' });
    }
    L.check('criterion7_picker: the λ header unit (/h, /y, FIT) scales the shown value; the stored value stays per hour', bad.length === 0, bad);
    // typed in the cell in the picked unit, stored per hour: 1 FIT = 1e-9 /h, 8.76 /y = 1e-3 /h
    const typed = async (unit, text) => {
      await setLambdaUnit(app, unit);
      await page.locator(CELL(ids.D, 'lambda')).click();
      await page.keyboard.press('Enter');
      const input = page.locator(TID('grid-input'));
      await input.waitFor({ state: 'visible', timeout: 3000 });
      await input.fill(text);
      await page.keyboard.press('Enter');
      await until(async () => (await input.count()) === 0, 2000);
      await sleep(150);
      return (await nodeOf(page, ids.D)).quant.lambda;
    };
    const fit = await typed('FIT', '1');
    L.check('criterion7_fit: 1 typed with the FIT header is stored as 1e-9 /h', close(fit, 1e-9), fit);
    const year = await typed('y', '8.76');
    L.check('criterion7_year: 8.76 typed with the /y header is stored as 1e-3 /h', close(year, 1e-3), year);
    // pasted in the picked unit
    await setLambdaUnit(app, 'FIT');
    await doPaste(app, CELL(ids.D, 'lambda'), '2000');
    L.check('criterion7_paste: 2000 pasted with the FIT header is stored as 2e-6 /h', close((await nodeOf(page, ids.D)).quant.lambda, 2e-6), (await nodeOf(page, ids.D)).quant.lambda);
    await setLambdaUnit(app, 'h');
  });

  // ---- criterion 2 -----------------------------------------------------------------------------------
  await phase('criterion2', async () => {
    const names = {};
    const st = await app.api('get', '/state');
    const walk = (n) => { names[String(n.id)] = n.name; (n.children || []).forEach(walk); };
    walk(st.tree);
    const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
    const bySortName = (dir) => Object.values(ids).map(String).sort((a, b) => dir * collator.compare(names[a], names[b]));

    L.check('criterion2_sort[name asc]: one click sorts ascending', await setSort(app, 'name', 'ascending'));
    L.check('criterion2_sort[name asc]: rows are in name order', JSON.stringify(await rowOrder(page)) === JSON.stringify(bySortName(1)), await rowOrder(page));
    L.check('criterion2_sort[name desc]: a second click sorts descending', await setSort(app, 'name', 'descending'));
    L.check('criterion2_sort[name desc]: rows are in reverse name order', JSON.stringify(await rowOrder(page)) === JSON.stringify(bySortName(-1)), await rowOrder(page));
    const indicator = await page.evaluate(() => Array.from(document.querySelectorAll('[data-testid="grid-th"]')).map((th) => [th.dataset.column, th.getAttribute('aria-sort')]));
    L.check('criterion2_sort: only the sorted column has aria-sort ascending/descending', indicator.filter(([, s]) => s !== 'none').length === 1 && indicator.find(([c]) => c === 'name')[1] === 'descending', indicator);

    // every column can be sorted
    const bad = [];
    for (const col of COLUMN_ORDER) {
      const ok = await setSort(app, col, 'ascending');
      if (!ok) { bad.push({ col, why: 'no aria-sort=ascending after clicking' }); continue; }
      const order = await rowOrder(page);
      if (order.length !== 11) bad.push({ col, why: 'rows ' + order.length });
      if (['lambda', 'T', 'tau', 'mu', 'q'].includes(col)) {
        const raws = [];
        for (const id of order) raws.push({ id, raw: await cellRaw(page, id, col), unused: await page.evaluate((s) => document.querySelector(s).dataset.unused === 'true' || document.querySelector(s).textContent.trim() === '', CELL(id, col)) });
        const filled = raws.filter((r) => !r.unused);
        const numbers = filled.map((r) => Number(r.raw));
        const sorted = numbers.every((v, i) => i === 0 || numbers[i - 1] <= v);
        const emptyLast = raws.slice(filled.length).every((r) => r.unused) && raws.slice(0, filled.length).every((r) => !r.unused);
        if (!sorted || !emptyLast) bad.push({ col, numbers, emptyLast });
        // and descending: empty cells stay last
        await setSort(app, col, 'descending');
        const rawsD = [];
        for (const id of await rowOrder(page)) rawsD.push({ id, raw: await cellRaw(page, id, col), unused: await page.evaluate((s) => document.querySelector(s).dataset.unused === 'true' || document.querySelector(s).textContent.trim() === '', CELL(id, col)) });
        const filledD = rawsD.filter((r) => !r.unused).map((r) => Number(r.raw));
        if (!filledD.every((v, i) => i === 0 || filledD[i - 1] >= v) || !rawsD.slice(filledD.length).every((r) => r.unused)) bad.push({ col, why: 'descending order or empty cells not last', filledD });
      }
    }
    L.check('criterion2_sort: every column sorts; numeric columns by value with empty and unused cells last in both directions', bad.length === 0, bad);
    await setSort(app, 'name', 'ascending');

    // filter
    const filt = async (text) => { await setFilter(app, text); return { rows: await rowOrder(page), count: await gridCount(page) }; };
    let r = await filt('pump');
    L.check('criterion2_filter: "pump" (any case) keeps the 8 pumps of 11', r.rows.length === 8 && r.count.shown === 8 && r.count.total === 11 && r.rows.every((id) => /^Pump /.test(names[id])), r);
    r = await filt('hydraulic');
    L.check('criterion2_filter: a text found only in the tags column finds one row in many', r.rows.length === 1 && r.rows[0] === ids.A, r);
    r = await filt('zeta-9');
    L.check('criterion2_filter: a text found only in the source column finds one row', r.rows.length === 1 && r.rows[0] === ids.X, r);
    r = await filt('zzzz-no-such');
    L.check('criterion2_filter: no match shows grid-nomatch and 0 of 11', r.rows.length === 0 && r.count.shown === 0 && (await page.locator(TID('grid-nomatch')).count()) === 1, r);
    r = await filt('  PUMP g ');
    L.check('criterion2_filter: the needle is trimmed and case-insensitive ("  PUMP g " finds Pump G)', r.rows.length === 1 && r.rows[0] === ids.G, r);
    r = await filt('');
    L.check('criterion2_filter: clearing the filter shows all 11 again', r.rows.length === 11 && r.count.shown === 11, r);
  });

  // ---- criterion 3 -----------------------------------------------------------------------------------
  await phase('criterion3', async () => {
    await resetPumps(app, ids);
    await setFilter(app, '');
    await setSort(app, 'name', 'ascending');
    await setHidden(app, ['tau', 'mu', 'q']);
    const order = await rowOrder(page);
    const [a, b, c, d, e] = ['A', 'B', 'C', 'D', 'E'].map((x) => ids[x]);
    L.check('criterion3_setup: rows A..E follow Motor Z in name order', JSON.stringify(order.slice(1, 6)) === JSON.stringify([a, b, c, d, e]), order);
    const text = ['1.1e-5\t111\tsheet-1', 'abc\t222\tsheet-2', '3.3e-5\t333\tsheet-3', '4.4e-5\t0\tsheet-4', '5.5e-5\t555\tsheet-5'].join('\n');
    await doPaste(app, CELL(a, 'lambda'), text);
    const s = await readSummary(page);
    L.check('criterion3_summary: 3 rows applied (grid-summary-applied data-count and text)', s.applied === 3 && /3/.test(s.appliedText) && /applied/i.test(s.appliedText), s);
    L.check('criterion3_summary: 2 rows refused (grid-summary-refused-count)', s.refused === 2 && /2/.test(s.refusedText), s);
    L.check('criterion3_summary: each refused row is listed with its clipboard row number and column', s.items.length === 2 && s.items[0].clipRow === 2 && s.items[0].column === 'lambda' && s.items[1].clipRow === 4 && s.items[1].column === 'T', s.items);
    L.check('criterion3_summary: each item reads "Clipboard row N, <column>: <message>" with a message', s.items.length === 2
      && /^Clipboard row 2, λ: \S.*/.test(s.items[0].text) && /^Clipboard row 4, T: \S.*/.test(s.items[1].text) && s.items.every((i) => i.text.replace(/^Clipboard row \d+, \S+: /, '').length > 3), s.items);
    const [na, nb, nc, nd, ne] = await Promise.all([a, b, c, d, e].map((id) => nodeOf(page, id)));
    L.check('criterion3_effect: the three good rows landed (A, C, E: λ, T, source)', close(na.quant.lambda, 1.1e-5) && na.quant.T === 111 && na.quant.source === 'sheet-1'
      && close(nc.quant.lambda, 3.3e-5) && nc.quant.T === 333 && nc.quant.source === 'sheet-3' && close(ne.quant.lambda, 5.5e-5) && ne.quant.T === 555 && ne.quant.source === 'sheet-5', { na, nc, ne });
    L.check('criterion3_effect: a bad row changes none of its cells (B keeps λ, T, source; D too)', close(nb.quant.lambda, 4e-5) && nb.quant.T === 200 && nb.quant.source == null
      && close(nd.quant.lambda, 8e-5) && nd.quant.T === 400 && nd.quant.source == null, { nb, nd });
    await app.shot('grid_paste_summary_' + label);
    // the summary follows the language
    await app.setLanguage('ja');
    await sleep(200);
    const sj = await readSummary(page);
    L.check('criterion3_language: the summary is redrawn in Japanese (クリップボードの 2 行目 ...)', sj.applied === 3 && sj.refused === 2 && sj.items.length === 2 && /^クリップボードの 2 行目、/.test(sj.items[0].text), sj);
    await app.setTheme('dark');
    await app.shot('grid_ja_dark_' + label);
    await app.setTheme('light');
    await app.setLanguage('en');
  });

  // ---- criterion 6: the paste cases of FN-50 ----------------------------------------------------------
  await phase('criterion6', async () => {
    await resetPumps(app, ids);
    await setFilter(app, '');
    await setSort(app, 'name', 'ascending');
    await setHidden(app, ['tau', 'mu', 'q']);
    const [A, B, C, D, E] = ['A', 'B', 'C', 'D', 'E'].map((x) => ids[x]);
    const nodes = async (...list) => Promise.all(list.map((id) => nodeOf(page, id)));

    // empty cell
    await doPaste(app, CELL(B, 'lambda'), '5e-5\t\tfrom-sheet');
    let [nb] = await nodes(B);
    L.check('criterion6_empty_cell: an empty cell leaves that cell unchanged (T keeps 200; λ and source set)', close(nb.quant.lambda, 5e-5) && nb.quant.T === 200 && nb.quant.source === 'from-sheet', nb);

    // trailing newline: LF and CRLF
    for (const [nl, name] of [['\n', 'LF'], ['\r\n', 'CRLF']]) {
      await doPaste(app, CELL(D, 'lambda'), '3e-5\t10\tsrc-nl' + nl);
      const s = await readSummary(page);
      const [nd, ne] = await nodes(D, E);
      L.check(`criterion6_trailing_newline[${name}]: ignored, no empty row (1 applied, 0 refused, next row untouched)`, s.applied === 1 && s.refused === 0 && s.items.length === 0 && close(nd.quant.lambda, 3e-5) && close(ne.quant.lambda, 1e-4), { s, nd, ne });
    }

    // Excel quoting
    const quoted = '"1e-5"\t10\t"line one\nline ""two""\tafter tab"\n"1\t2"\t20\tsrc-q';
    await doPaste(app, CELL(B, 'lambda'), quoted);
    let s = await readSummary(page);
    [nb] = await nodes(B);
    const [nc] = await nodes(C);
    L.check('criterion6_quoting: a quoted number is unquoted; doubled quotes, an embedded newline and tab are kept in a text column', close(nb.quant.lambda, 1e-5) && nb.quant.T === 10 && nb.quant.source === 'line one\nline "two"\tafter tab', nb);
    L.check('criterion6_quoting: a tab inside a numeric cell refuses the whole row (clipboard row 2, λ); its other cells are not applied',
      s.applied === 1 && s.refused === 1 && s.items.length === 1 && s.items[0].clipRow === 2 && s.items[0].column === 'lambda' && close(nc.quant.lambda, 6e-5) && nc.quant.T === 300 && nc.quant.source === 'keep', { s, nc });
    await resetPumps(app, ids);
    await doPaste(app, CELL(B, 'lambda'), '"1\n2"\t10\tsrc-nl');
    s = await readSummary(page);
    [nb] = await nodes(B);
    L.check('criterion6_quoting: a line break inside a numeric cell is refused (clipboard row 1, λ) and its row is not applied',
      s.applied === 0 && s.items.length === 1 && s.items[0].clipRow === 1 && s.items[0].column === 'lambda' && nb.quant.lambda === 4e-5 && nb.quant.T === 200 && nb.quant.source == null, { s: s.items, nb });

    // extra cells: visible columns are id name model λ T source tags; the 5th cell from λ is beyond
    await doPaste(app, CELL(D, 'lambda'), '1e-5\t10\tsrc-x\ttag-x\tEXTRA-1\n2e-5\t20\tsrc-y\ttag-y\tEXTRA-2');
    s = await readSummary(page);
    const [nd2, ne2] = await nodes(D, E);
    L.check('criterion6_extra_cells: cells beyond the last visible column are refused, reported once per row; the rest of each row applies',
      s.items.length === 2 && s.items.every((i) => i.column === '') && s.items[0].clipRow === 1 && s.items[1].clipRow === 2 && s.items[0].code === 'EXTRA_CELLS'
      && close(nd2.quant.lambda, 1e-5) && nd2.quant.source === 'src-x' && ne2.quant.source === 'src-y' && JSON.stringify(nd2.trace && nd2.trace.tags) === '["tag-x"]', { s: s.items, nd2, ne2 });

    // extra rows: filter to the pumps, anchor on the last one
    await setFilter(app, 'Pump');
    const total = await nodeCount(app);
    const totalEvents = (await gridCount(page)).total;
    await doPaste(app, CELL(ids.H, 'lambda'), '1e-5\t10\tlast-row\n2e-5\t20\tx\n3e-5\t30\ty');
    s = await readSummary(page);
    const [nh] = await nodes(ids.H);
    L.check('criterion6_extra_rows: rows past the last visible row are refused and reported (clipboard rows 2 and 3, EXTRA_ROW); the first row applies',
      s.applied === 1 && s.items.length === 2 && s.items[0].clipRow === 2 && s.items[1].clipRow === 3 && s.items.every((i) => i.code === 'EXTRA_ROW') && nh.quant.source === 'last-row', { s, nh });
    L.check('criterion6_extra_rows: no node is created', (await nodeCount(app)) === total && (await gridCount(page)).total === totalEvents, { total, now: await nodeCount(app) });

    // filtered-out row receives nothing (also the FN-47 sort + filter case): sources keep = A, C, E
    await resetPumps(app, ids);
    await setFilter(app, 'keep');
    const vis = await rowOrder(page);
    L.check('criterion6_filtered_row: the filter "keep" leaves Pump A, C, E in view', JSON.stringify(vis) === JSON.stringify([A, C, E]), vis);
    await doPaste(app, CELL(A, 'lambda'), '1e-5\t11\tfk-1\n2e-5\t22\tfk-2\n3e-5\t33\tfk-3');
    const [na3, nb3, nc3, nd3, ne3] = await nodes(A, B, C, D, E);
    L.check('criterion6_filtered_row: rows in view receive the three clipboard rows (A, C, E); B and D, filtered out, get nothing',
      nb3.quant.lambda === 4e-5 && nd3.quant.lambda === 8e-5 && nb3.quant.T === 200 && nd3.quant.T === 400
      && close(na3.quant.lambda, 1e-5) && na3.quant.source === 'fk-1' && close(nc3.quant.lambda, 2e-5) && nc3.quant.source === 'fk-2' && close(ne3.quant.lambda, 3e-5) && ne3.quant.source === 'fk-3', { na3, nb3, nc3, nd3, ne3 });
    await setFilter(app, '');

    // more than 2,000 rows: whole paste refused, nothing sent, nothing applied
    await resetPumps(app, ids);
    const before = posts.length;
    const big = Array.from({ length: 2001 }, () => '1e-5\t10\tbig').join('\n');
    await doPaste(app, CELL(A, 'lambda'), big);
    s = await readSummary(page);
    const [na4] = await nodes(A);
    L.check('criterion6_2000_rows: 2,001 clipboard rows are refused whole with a message (summary error TOO_MANY_ROWS)', s.error && s.error.code === 'TOO_MANY_ROWS' && /2,000/.test(s.error.text) && /2,?001/.test(s.error.text), s.error);
    L.check('criterion6_2000_rows: no request is made and nothing is applied', posts.length === before && na4.quant.source === 'keep' && na4.quant.lambda === 2e-5, { sent: posts.length - before, na4 });
    L.check('criterion6_2000_rows: the same message is on the message line at the top (grid-message)', Boolean(s.message && /2,000/.test(s.message.text)), s.message);

    // id / q / invalid cell: through the browser to the server, all columns visible
    await resetPumps(app, ids);
    await setHidden(app, []);
    await setSort(app, 'name', 'ascending');
    const qY = await cellText(page, ids.Y, 'q');
    const row = (cells) => COLUMN_ORDER.map((c) => cells[c] || '').join('\t');
    const text = [
      row({ id: ids.F, lambda: '3e-5' }),
      row({ id: 'not-this-row', lambda: '4e-5' }),
      row({ q: '0.9' }),
      row({ id: ids.X, q: '0.5' }),
      row({ q: qY }),
    ].join('\n');
    await doPaste(app, CELL(ids.F, 'id'), text);
    s = await readSummary(page);
    const [nf, ng, nh2, nx, ny] = await nodes(ids.F, ids.G, ids.H, ids.X, ids.Y);
    L.check('criterion6_id_column: an id equal to the row is ignored and the row applies; a different id refuses the row ("id does not match this row")',
      nf && close(nf.quant.lambda, 3e-5) && close(ng.quant.lambda, 1.4e-4) && s.items.some((i) => i.clipRow === 2 && i.column === 'id' && i.code === 'ID_MISMATCH' && /id does not match this row/.test(i.text)), { s: s.items, nf, ng });
    L.check('criterion6_q_non_fixed: a q different from the shown q on a non-fixed row refuses the row ("q is computed from the model")',
      s.items.some((i) => i.clipRow === 3 && i.column === 'q' && i.code === 'Q_COMPUTED' && /q is computed from the model/.test(i.text)) && close(nh2.quant.lambda, 1.6e-4), { s: s.items, nh2 });
    L.check('criterion6_q_fixed: q is applied on a fixed row (with its equal id ignored)', close(nx.probability, 0.5), nx);
    L.check('criterion6_q_non_fixed: a q equal to the shown q is ignored (neither applied nor refused)', !s.items.some((i) => i.clipRow === 5) && close(ny.quant.lambda, 1e-4), { s: s.items, ny, qY });
    L.check('criterion6_invalid_cell: 2 rows applied (clipboard rows 1 and 4), 2 refused (rows 2 and 3): valid rows apply when others are refused', s.applied === 2 && s.refused === 2, s);
    // a value for a field the model does not use
    await doPaste(app, CELL(ids.A, 'tau'), '5');
    s = await readSummary(page);
    L.check('criterion6_unused_field: a value for a field the model does not use refuses the row (τ on a rate row)', s.items.length === 1 && s.items[0].column === 'tau' && s.items[0].code === 'NOT_USED' && /τ is not used by the model of this row/.test(s.items[0].text), s.items);
    // id column anchor: equal id ignored while the name applies
    await doPaste(app, CELL(ids.A, 'id'), ids.A + '\tPump A2');
    const [na5] = await nodes(ids.A);
    L.check('criterion6_id_column: pasting from the id column: equal id ignored, the name cell applies', na5.name === 'Pump A2', na5);
    await app.api('patch', '/nodes/' + ids.A, { name: 'Pump A' });
    await refreshShell(page);
    // the model column: a key, the Quantification tab's name (en or ja), any case; anything else is refused
    await resetPumps(app, ids);
    await setSort(app, 'name', 'ascending');
    await doPaste(app, CELL(ids.B, 'model'), 'Repairable\n故障率\nSTANDBY\nbogus-model');
    s = await readSummary(page);
    const mm = await Promise.all([ids.B, ids.C, ids.D, ids.E].map((id) => nodeOf(page, id)));
    L.check('criterion6_model: a model name (en), a Japanese model name and a key in capitals are read; "bogus-model" is refused (clipboard row 4, model)',
      mm[0].quant.model === 'repairable' && mm[1].quant.model === 'rate' && mm[2].quant.model === 'standby' && mm[3].quant.model === 'rate'
      && s.items.length === 1 && s.items[0].clipRow === 4 && s.items[0].column === 'model' && /bogus-model/.test(s.items[0].text) && /not a model/.test(s.items[0].text), { models: mm.map((n) => n.quant.model), items: s.items });
    await resetPumps(app, ids);
    await setHidden(app, []);
  });

  // ---- criterion 5 -----------------------------------------------------------------------------------
  await phase('criterion5', async () => {
    await resetPumps(app, ids);
    await setFilter(app, '');
    await setHidden(app, ['tau', 'mu', 'q']);
    await setSort(app, 'name', 'descending');
    await setFilter(app, 'Pump');
    const order = await rowOrder(page);
    L.check('criterion5_block: sorted by name descending and filtered to the pumps, the rows are H G F E D C B A', JSON.stringify(order) === JSON.stringify(['H', 'G', 'F', 'E', 'D', 'C', 'B', 'A'].map((x) => ids[x])), order);
    await doPaste(app, CELL(ids.G, 'lambda'), '1e-5\t11\tblk-1\n2e-5\t22\tblk-2\n3e-5\t33\tblk-3');
    const s = await readSummary(page);
    const got = {};
    for (const x of PUMPS) got[x] = await nodeOf(page, ids[x]);
    const landed = (x, lam, t, src) => close(got[x].quant.lambda, lam) && got[x].quant.T === t && got[x].quant.source === src;
    L.check('criterion5_block: a 3 x 3 block pasted at Pump G lands on the three intended ids (G, F, E) and on no other',
      landed('G', 1e-5, 11, 'blk-1') && landed('F', 2e-5, 22, 'blk-2') && landed('E', 3e-5, 33, 'blk-3')
      && got.H.quant.source == null && got.D.quant.source == null && got.C.quant.source === 'keep' && close(got.H.quant.lambda, 1.6e-4) && close(got.D.quant.lambda, 8e-5) && s.applied === 3, { s: s.items, applied: s.applied, got: { G: got.G.quant, F: got.F.quant, E: got.E.quant } });
    await setFilter(app, '');
    await setSort(app, 'name', 'ascending');
    await resetPumps(app, ids);

    // grid paste after own edit: the edit's PATCH is held (after the server applied it) until the paste event has
    // been dispatched; the grid must send the revision of its own edit: no 409, rows applied.
    const mark409 = app.errMark();
    await setFilter(app, 'Pump');
    const editLambda = async (id, text) => {
      await page.locator(CELL(id, 'lambda')).click();
      await page.keyboard.press('Enter');
      const ed = page.locator(TID('grid-input'));
      await ed.waitFor({ state: 'visible', timeout: 3000 });
      await ed.fill(text);
      await page.keyboard.press('Enter'); // the PATCH starts here
    };
    const reachedServer = (hold) => Promise.race([hold.reached, sleep(6000).then(() => { throw new Error('the held edit never reached the server'); })]);
    // the selected cell stays on the edited cell: the paste starts there; its empty first cell keeps the edit
    const holdText = '\t77\timm-1\n8e-5\t88\timm-2';
    {
      const hold = await holdPatches(page);
      try {
        await editLambda(ids.B, '3e-5');
        await reachedServer(hold);
        await pasteStart(app, CELL(ids.B, 'lambda'), holdText, { click: false });
        hold.release();
        await pasteFinish(app);
      } finally { await hold.stop(); }
      const nb = await nodeOf(page, ids.B);
      const nc = await nodeOf(page, ids.C);
      const sEdit = await readSummary(page);
      L.check('grid paste after own edit: an edit still in flight when the paste is dispatched: no 409, 2 rows applied (STALE_REVISION never shown)',
        !sEdit.error && sEdit.applied === 2 && close(nb.quant.lambda, 3e-5) && nb.quant.T === 77 && nb.quant.source === 'imm-1' && close(nc.quant.lambda, 8e-5) && nc.quant.source === 'imm-2', { error: sEdit.error, applied: sEdit.applied, nb: nb.quant, nc: nc.quant });
      L.check('grid paste after own edit: no 409 reached the console', app.errorsSince(mark409, []).filter((e) => /409/.test(e.text)).length === 0, app.errorsSince(mark409, []));
    }
    await setFilter(app, '');

    // grid paste after foreign write: after the held PATCH reached the server, another party writes through the API
    await resetPumps(app, ids);
    await sleep(300);
    await setFilter(app, 'Pump');
    {
      const before = { B: await nodeOf(page, ids.B), C: await nodeOf(page, ids.C) };
      const hold = await holdPatches(page);
      let foreign = null;
      try {
        await editLambda(ids.B, '3e-5');
        await reachedServer(hold);
        foreign = await app.api('patch', '/nodes/' + ids.Z, { name: 'Motor Zed' }); // another party; the page is not told
        await pasteStart(app, CELL(ids.B, 'lambda'), holdText, { click: false });
        hold.release();
        await pasteFinish(app);
      } finally { await hold.stop(); }
      L.check('grid paste after foreign write: (setup) the other write was accepted', foreign && !foreign.__error, foreign);
      const sF = await readSummary(page);
      L.check('grid paste after foreign write: 409 STALE_REVISION with exactly "The analysis changed; paste again"', Boolean(sF.error) && sF.error.code === 'STALE_REVISION' && sF.error.text === STALE_TEXT, { error: sF.error, applied: sF.applied });
      const apiB = (await app.api('get', '/nodes/' + ids.B)).node;
      const apiC = (await app.api('get', '/nodes/' + ids.C)).node;
      L.check('grid paste after foreign write: nothing of the paste was applied (the earlier edit of λ stays)', close(apiB.quant.lambda, 3e-5) && apiB.quant.T === before.B.quant.T && apiB.quant.source == null && JSON.stringify(apiC.quant) === JSON.stringify(before.C.quant), { b: apiB.quant, c: apiC.quant });
    }
    await setFilter(app, '');

    // another party changes the document (the page's 5 s revision poll is stubbed so it cannot redraw by itself)
    await resetPumps(app, ids);
    await setSort(app, 'name', 'ascending');
    await setHidden(app, ['tau', 'mu', 'q']);
    await sleep(300);
    const pingStub = await stubRevisionPoll(page);
    try {
      const before = await nodeOf(page, ids.D);
      const rv = await app.api('patch', '/nodes/' + ids.Z, { name: 'Motor Zeta' }); // through Node: the page is not told
      L.check('criterion5_stale: the harness changed the document behind the page', !rv.__error, rv);
      await doPaste(app, CELL(ids.D, 'lambda'), '9e-5\t99\tstale-src');
      const s2 = await readSummary(page);
      L.check('criterion5_stale: the summary says exactly "The analysis changed; paste again" (STALE_REVISION)', Boolean(s2.error) && s2.error.code === 'STALE_REVISION' && s2.error.text === STALE_TEXT, s2.error);
      L.check('criterion5_stale: the same message is on the message line, with data-code STALE_REVISION', Boolean(s2.message) && s2.message.text === STALE_TEXT && s2.message.code === 'STALE_REVISION', s2.message);
      const after = await nodeOf(page, ids.D);
      const apiD = (await app.api('get', '/nodes/' + ids.D)).node;
      L.check('criterion5_stale: nothing was applied', JSON.stringify(after.quant) === JSON.stringify(before.quant) && apiD.quant.source == null && apiD.quant.lambda === 8e-5, { after: after.quant, apiD: apiD.quant });
      const redrawn = await until(async () => (await cellText(page, ids.Z, 'name')) === 'Motor Zeta', 4000);
      L.check('criterion5_stale: the grid redraws from the current document (the other change is visible)', Boolean(redrawn), await cellText(page, ids.Z, 'name'));
      await doPaste(app, CELL(ids.D, 'lambda'), '9e-5\t99\tstale-src');
      const s3 = await readSummary(page);
      L.check('criterion5_stale: pasting again after the redraw is applied', s3.applied === 1 && !s3.error && close((await nodeOf(page, ids.D)).quant.lambda, 9e-5), s3);
    } finally { await pingStub.stop(); }
  });

  // ---- the summary stays in view (DESIGN 2: pane geometry) -------------------------------------------------
  await phase('summary_in_view', async () => {
    await resetPumps(app, ids);
    await setFilter(app, '');
    await setSort(app, 'name', 'ascending');
    await setHidden(app, ['tau', 'mu', 'q']);
    const measure = () => page.evaluate(() => {
      const a = document.querySelector('[data-testid="grid-summary-applied"]');
      const panel = document.getElementById('tabpanel-grid');
      const root = document.querySelector('[data-testid="grid-root"]');
      const scroll = document.querySelector('[data-testid="grid-scroll"]');
      const ws = document.querySelector('.workspace');
      const pane = document.getElementById('details-panel');
      const toolbar = document.querySelector('[data-testid="grid-toolbar"]');
      const counts = document.querySelector('[data-testid="grid-summary-counts"]');
      const summary = document.querySelector('[data-testid="grid-summary"]');
      if (!panel || !root || !pane) return null;
      const box = (el) => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right }; };
      const shown = (el) => Boolean(el) && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
      // a line element: its rect, height and the scroll/client heights S compares (null when the element is absent)
      const line = (el) => {
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { shown: shown(el), top: r.top, bottom: r.bottom, left: r.left, right: r.right, h: r.height, sh: el.scrollHeight, ch: el.clientHeight, count: el.dataset.count === undefined ? null : Number(el.dataset.count) };
      };
      const byId = (id) => document.querySelector('[data-testid="' + id + '"]');
      const kidName = (k) => k.dataset.testid || (k.tagName.toLowerCase() + (k.className ? '.' + String(k.className).split(' ')[0] : ''));
      // every visible direct child of the toolbar (T), and the named toolbar parts the checks require
      const kids = toolbar ? Array.from(toolbar.children).filter(shown).map((k) => { const r = k.getBoundingClientRect(); return { id: kidName(k), top: r.top, bottom: r.bottom, left: r.left, right: r.right, w: r.width, h: r.height }; }) : [];
      const parts = {};
      for (const id of ['grid-filter', 'grid-count', 'grid-columns-button', 'grid-columns-hidden-count', 'grid-hint']) {
        const el = byId(id);
        parts[id] = el ? Object.assign(line(el), { inToolbar: Boolean(toolbar) && toolbar.contains(el) }) : null;
      }
      return {
        a: a ? box(a) : null, panel: box(panel), pane: box(pane), root: box(root), summary: summary ? box(summary) : null, table: scroll ? box(scroll) : null,
        toolbar: toolbar ? box(toolbar) : null, counts: counts ? box(counts) : null, vw: window.innerWidth, vh: window.innerHeight,
        scroll: { panel: panel.scrollTop, root: root.scrollTop, summary: summary ? summary.scrollTop : null, page: document.scrollingElement.scrollTop, workspace: ws ? ws.scrollTop : 0 },
        narrow: root.hasAttribute('data-narrow'),
        tbScroll: toolbar ? { sw: toolbar.scrollWidth, cw: toolbar.clientWidth } : null,
        kids,
        parts,
        lines: { applied: line(a), title: line(byId('grid-summary-title')), message: line(byId('grid-message')), error: line(byId('grid-summary-error')) },
      };
    });
    const inside = (m) => Boolean(m) && Boolean(m.a) && m.a.right > m.a.left && m.a.top >= 0 && m.a.bottom <= m.vh && m.a.left >= 0 && m.a.right <= m.vw
      && m.a.top >= m.panel.top - 1 && m.a.bottom <= m.panel.bottom + 1 && m.a.left >= m.panel.left - 1 && m.a.right <= m.panel.right + 1;
    const noScroll = (m) => Boolean(m) && m.scroll.panel === 0 && m.scroll.root === 0 && m.scroll.page === 0;
    const insideViewport = (b, m) => Boolean(b) && b.right > b.left && b.top >= 0 && b.bottom <= m.vh && b.left >= 0 && b.right <= m.vw;
    // inside the #details-panel rect (the whole bottom pane, tab strip included)
    const insidePane = (b, m) => Boolean(b) && b.top >= m.pane.top - 1 && b.bottom <= m.pane.bottom + 1 && b.left >= m.pane.left - 1 && b.right <= m.pane.right + 1;
    // inside a container rect (1 px tolerance): a line clipped by its container (bottom past the container's bottom) fails
    const insideBox = (b, c) => Boolean(b) && Boolean(c) && b.right > b.left && b.bottom > b.top
      && b.top >= c.top - 1 && b.bottom <= c.bottom + 1 && b.left >= c.left - 1 && b.right <= c.right + 1;
    // grid-root is the visible grid area (the #details-panel rect is taller: the tab strip and padding lie around it)
    const insideRoot = (b, m) => insideBox(b, m.root);
    // wide layout: the summary box itself must not clip the applied line, and must not be scrolled
    const insideSummary = (b, m) => insideBox(b, m.summary);
    const summaryNotScrolled = (m) => Boolean(m) && m.scroll.summary === 0;
    const r1 = (n) => Math.round(n * 10) / 10;
    // T (DESIGN 2, check "grid summary in view"): every visible child of grid-toolbar has a size and lies inside the
    // grid-toolbar rect (+-1 px), the named parts (filter, count, Columns button, the "n hidden" sign while columns
    // are hidden, and grid-hint when `hint`) are shown with a size, and grid-toolbar does not overflow sideways.
    // Returns the list of problems (empty = T holds).
    const tProblems = (m, { hint }) => {
      if (!m || !m.toolbar) return ['no grid-toolbar element'];
      const tb = m.toolbar;
      const p = [];
      if (!(tb.right > tb.left && tb.bottom > tb.top)) p.push('grid-toolbar has no size');
      if (!m.tbScroll || m.tbScroll.sw > m.tbScroll.cw) p.push(`grid-toolbar overflows sideways: scrollWidth ${m.tbScroll && m.tbScroll.sw} > clientWidth ${m.tbScroll && m.tbScroll.cw}`);
      if (!m.kids.length) p.push('grid-toolbar has no visible child');
      const within = (b) => b.top >= tb.top - 1 && b.bottom <= tb.bottom + 1 && b.left >= tb.left - 1 && b.right <= tb.right + 1;
      for (const k of m.kids) {
        if (!(k.w > 0 && k.h > 0)) p.push(`toolbar child ${k.id} has no size (${r1(k.w)} x ${r1(k.h)})`);
        else if (!within(k)) p.push(`toolbar child ${k.id} lies outside grid-toolbar: h ${r1(k.h)}, top ${r1(k.top - tb.top)}, bottom ${r1(k.bottom - tb.bottom)}, left ${r1(k.left - tb.left)}, right ${r1(k.right - tb.right)} (toolbar ${r1(tb.bottom - tb.top)} px high)`);
      }
      const need = ['grid-filter', 'grid-count', 'grid-columns-button', 'grid-columns-hidden-count'];
      if (hint) need.push('grid-hint');
      for (const id of need) {
        const e = m.parts[id];
        if (!e) { p.push(`${id} is missing${id === 'grid-hint' ? ' (a cell is selected in the wide layout, so the hint must be shown)' : id === 'grid-columns-hidden-count' ? ' (three columns are hidden)' : ''}`); continue; }
        if (!e.shown || !(e.right > e.left && e.bottom > e.top)) { p.push(`${id} is not shown with a size (shown ${e.shown}, ${r1(e.right - e.left)} x ${r1(e.h)})`); continue; }
        if (!e.inToolbar) p.push(`${id} is not inside grid-toolbar`);
        if (!within(e)) p.push(`${id} lies outside grid-toolbar: h ${r1(e.h)}, top ${r1(e.top - tb.top)}, bottom ${r1(e.bottom - tb.bottom)}, right ${r1(e.right - tb.right)}`);
        if (id === 'grid-columns-hidden-count' && !(e.count > 0)) p.push('grid-columns-hidden-count carries no data-count > 0');
      }
      return p;
    };
    // S: the line is present, shown, has a height, and its content fits (scrollHeight <= clientHeight + 1)
    const sProblems = (name, ln) => {
      if (!ln) return [`${name} is missing`];
      if (!ln.shown || !(ln.h > 0)) return [`${name} is not shown with a height (shown ${ln.shown}, h ${r1(ln.h)})`];
      return ln.sh <= ln.ch + 1 ? [] : [`${name} is clipped: scrollHeight ${ln.sh} > clientHeight ${ln.ch} + 1`];
    };
    const lineBox = (ln) => (ln ? { top: ln.top, bottom: ln.bottom, left: ln.left, right: ln.right } : null);
    /** Save fta.layout (the host's LAYOUT_KEY), reload, wait for boot, open the Grid tab. */
    const setLayout = async (app2, value) => {
      await page.evaluate((v) => localStorage.setItem('fta.layout', JSON.stringify(v)), value);
      const onDialog = (d) => { d.accept().catch(() => {}); }; // a beforeunload prompt of a dirty document
      page.on('dialog', onDialog);
      try {
        await page.reload();
        await L.waitBoot(page);
        await app2.waitDiagram();
      } finally { page.off('dialog', onDialog); }
      await openGrid(app2);
      await sleep(400);
    };

    // wide window, default panes: the wide layout, no data-narrow
    await doPaste(app, CELL(ids.A, 'lambda'), '2e-5\t100\tview-wide');
    const wide = await measure();
    L.check('grid summary in view [1600x1000]: the default pane is wide (no data-narrow) and the applied line is in view', Boolean(wide) && !wide.narrow && inside(wide), wide);

    // reviewer shot: the Columns chooser open (DESIGN 2 lists grid-columns-open)
    const colBtn = page.locator(TID('grid-columns-button'));
    await colBtn.click();
    const popOpen = await until(async () => (await colBtn.getAttribute('aria-expanded')) === 'true' && (await page.locator(TID('grid-columns-popover')).isVisible()), 3000);
    L.check('grid summary in view: the Columns chooser opens (grid-columns-popover visible, aria-expanded true) for the grid-columns-open shot', Boolean(popOpen));
    await app.shot('grid-columns-open', { locator: '#details-panel' });
    await page.keyboard.press('Escape');
    await sleep(150);

    // (a) 1100x800, default panes, AI pane open: no scrolling at all
    await page.setViewportSize({ width: 1100, height: 800 });
    await sleep(500);
    const aiWidth = await page.evaluate(() => document.getElementById('ai-panel').getBoundingClientRect().width);
    L.check('grid summary in view [1100x800]: (setup) the AI pane is open', aiWidth > 240, aiWidth);
    await doPaste(app, CELL(ids.A, 'lambda'), '2e-5\t100\tview-1100');
    const m1 = await measure();
    L.check('grid summary in view [1100x800]: after a paste the applied line is visible without any scrolling (panel, grid root, page)', inside(m1) && noScroll(m1), m1);
    // T: the paste anchor was clicked, so a cell is selected and the wide pane shows grid-hint
    const t1 = tProblems(m1, { hint: true });
    L.check('grid summary in view [1100x800]: T: every visible grid-toolbar child (filter, count, Columns, hidden-count sign, grid-hint) has a size and lies inside grid-toolbar (+-1 px), and grid-toolbar has no sideways overflow', t1.length === 0, t1);
    await app.shot('grid-summary-1100x800', { locator: '#details-panel' });

    // (b) 800x900: the stacked shell; bring the pane into view first
    await page.setViewportSize({ width: 800, height: 900 });
    await sleep(500);
    await page.evaluate(() => document.getElementById('details-panel').scrollIntoView());
    await sleep(200);
    await doPaste(app, CELL(ids.A, 'lambda'), '2e-5\t100\tview-800');
    const m2 = await measure();
    L.check('grid summary in view [800x900]: after scrolling the pane into view and a paste, the applied line is inside the viewport and the panel; panel, grid root and page scrollTop are 0', inside(m2) && noScroll(m2), m2);
    await app.shot('grid-summary-800x900', { locator: '#details-panel' });

    // (c) a pane narrower than 50.5em. The sizes are the host's own saved layout (main.js LAYOUT_KEY
    // 'fta.layout', read by loadLayout() at boot): written to localStorage, then the page is reloaded
    // (an inline --tree-w/--ai-w would be overwritten by applyLayout()). 1100x800, tree 200 px, AI 760 px:
    // the pane is about 318 px wide, 22 em, far under 50.5 em.
    const NARROW = { tree: 200, ai: 760, details: 260, analysis: null };
    await page.setViewportSize({ width: 1100, height: 800 });
    await setLayout(app, NARROW);
    const narrowPane = await page.evaluate(() => document.getElementById('details-panel').getBoundingClientRect().width);
    L.check('grid summary in view [narrow pane]: (setup) the saved layout gives a pane narrower than 400 px', narrowPane > 0 && narrowPane < 400, narrowPane);
    await doPaste(app, CELL(ids.A, 'lambda'), '2e-5\t100\tview-narrow\n3e-5\t200\tview-narrow-2');
    const m3 = await measure();
    L.check('grid summary in view [narrow pane]: grid-root carries data-narrow and the applied line and grid-toolbar are in view (viewport, #details-panel and grid-root rects, no scrolling)', Boolean(m3) && m3.narrow && inside(m3) && insidePane(m3.a, m3) && insideRoot(m3.a, m3) && insideViewport(m3.toolbar, m3) && insideRoot(m3.toolbar, m3) && noScroll(m3), m3);
    L.check('grid summary in view [narrow pane]: the counts line (grid-summary-counts) sits above the table (grid-scroll) in y', Boolean(m3) && m3.a && m3.table && m3.counts && m3.counts.bottom <= m3.table.top + 1 && m3.a.bottom <= m3.table.top + 1, m3);
    // T in the narrow layout (no grid-hint there): the hidden-count sign must not wrap or cover the counts line
    const t3 = tProblems(m3, { hint: false });
    L.check('grid summary in view [narrow pane]: T: every visible grid-toolbar child (filter, count, Columns, hidden-count sign) has a size and lies inside grid-toolbar (+-1 px), and grid-toolbar has no sideways overflow', t3.length === 0, t3);
    await app.shot('grid-narrow', { locator: '#details-panel' });

    // (d) the smallest pane: the bottom panel at its 140 px minimum (details and analysis both 140), wide and narrow.
    const smallest = async (label, layout, wantNarrow) => {
      await setLayout(app, layout);
      const h = await page.evaluate(() => document.getElementById('details-panel').getBoundingClientRect().height);
      L.check(`grid summary in view [minimum pane, ${label}]: (setup) the bottom panel is 140 px high`, h >= 139 && h <= 142, h);
      await doPaste(app, CELL(ids.A, 'lambda'), '2e-5\t100\tview-min\n3e-5\t200\tview-min-2', { click: false });
      const m = await measure();
      const tag = `grid summary in view [minimum pane, ${label}]`;
      L.check(`${tag}: the layout is ${wantNarrow ? 'narrow (grid-root[data-narrow])' : 'wide (no data-narrow)'}`, Boolean(m) && m.narrow === wantNarrow, m && m.narrow);
      if (!m) return;
      // both layouts: grid-root 72 +-1 px, toolbar <= 28 (+1), T, toolbar and applied inside grid-root, S on applied
      const rootH = m.root.bottom - m.root.top;
      L.check(`${tag}: grid-root is 72 px high (+-1)`, Math.abs(rootH - 72) <= 1, r1(rootH));
      const tbH = m.toolbar ? m.toolbar.bottom - m.toolbar.top : 0;
      L.check(`${tag}: grid-toolbar is at most 28 px high (+1) and not empty`, tbH > 0 && tbH <= 29, r1(tbH));
      const tD = tProblems(m, { hint: !wantNarrow });
      L.check(`${tag}: T: every visible grid-toolbar child ${wantNarrow ? '' : '(including grid-hint, a cell is selected) '}has a size and lies inside grid-toolbar (+-1 px), and grid-toolbar has no sideways overflow`, tD.length === 0, tD);
      L.check(`${tag}: grid-toolbar and, after a paste, grid-summary-applied are inside grid-root's rect (+-1 px)`, insideBox(m.toolbar, m.root) && insideBox(m.a, m.root), { root: m.root, toolbar: m.toolbar, applied: m.a });
      const sA = sProblems('grid-summary-applied', m.lines.applied);
      L.check(`${tag}: S: grid-summary-applied is not clipped (scrollHeight <= clientHeight + 1)`, sA.length === 0, sA);
      if (!wantNarrow) {
        // wide only: heights of the title and the applied line, the 72 px budget, the summary box, S on the title
        const ti = m.lines.title;
        const ap = m.lines.applied;
        const heights = ti && ap && m.toolbar ? { toolbar: r1(tbH), title: r1(ti.h), applied: r1(ap.h) } : null;
        L.check(`${tag}: grid-summary-title and grid-summary-applied are shown and each at most 19 px high`, Boolean(heights) && ti.shown && ap.shown && ti.h > 0 && ap.h > 0 && ti.h <= 19 && ap.h <= 19, heights);
        L.check(`${tag}: toolbar + title + applied heights add up to at most 72 px`, Boolean(heights) && tbH + ti.h + ap.h <= 72, heights);
        L.check(`${tag}: grid-summary-applied is inside grid-summary's rect and grid-summary.scrollTop is 0`, insideSummary(m.a, m) && summaryNotScrolled(m), { applied: m.a, summary: m.summary, scrollTop: m.scroll.summary });
        const sT = sProblems('grid-summary-title', ti);
        L.check(`${tag}: S: grid-summary-title is not clipped (scrollHeight <= clientHeight + 1)`, sT.length === 0, sT);
      }
      await app.shot(`grid-summary-min-${label}`, { locator: '#details-panel' });

      // a whole-paste failure (stale paste): grid-message and grid-summary-error inside grid-root, S on both.
      // The page's revision poll is stubbed so it cannot redraw before the measurement.
      const stub = await stubRevisionPoll(page);
      try {
        const rv = await app.api('patch', '/nodes/' + ids.Z, { name: 'Motor Zeta min-' + label }); // through Node: the page is not told
        L.check(`${tag}: (setup) the harness changed the document behind the page`, !rv.__error, rv);
        await doPaste(app, CELL(ids.A, 'lambda'), '2e-5\t100\tview-min-stale', { click: false });
        const f = await measure();
        const er = f && f.lines.error;
        const ms = f && f.lines.message;
        L.check(`${tag}: after a stale paste grid-message and grid-summary-error are both shown with a height`, Boolean(er) && Boolean(ms) && er.shown && ms.shown && er.h > 0 && ms.h > 0, f && f.lines);
        L.check(`${tag}: after a stale paste grid-message and grid-summary-error are inside grid-root's rect (+-1 px)`, Boolean(f) && insideBox(lineBox(ms), f.root) && insideBox(lineBox(er), f.root), f && { root: f.root, message: f.lines.message, error: f.lines.error });
        const sF = f ? sProblems('grid-message', ms).concat(sProblems('grid-summary-error', er)) : ['no measurement'];
        L.check(`${tag}: S: after a stale paste grid-message and grid-summary-error are not clipped (scrollHeight <= clientHeight + 1)`, sF.length === 0, sF);
        await app.shot(`grid-summary-min-${label}-stale`, { locator: '#details-panel' });
      } finally {
        await stub.stop();
        await app.api('patch', '/nodes/' + ids.Z, { name: 'Motor Zeta' });
      }
    };
    await smallest('wide', { tree: 320, ai: 340, details: 140, analysis: 140 }, false);
    await smallest('narrow', { tree: 200, ai: 760, details: 140, analysis: 140 }, true);

    // back to the default panes for the phases that follow
    await page.setViewportSize({ width: 1600, height: 1000 });
    await setLayout(app, { tree: 320, ai: 340, details: 260, analysis: null });
  });

  // ---- ETA mode: the panel shows the notice; a paste after the mode changed behind the page is not a stale paste ---
  await phase('eta', async () => {
    await resetPumps(app, ids);
    await setFilter(app, '');
    await setSort(app, 'name', 'ascending');
    await setHidden(app, ['tau', 'mu', 'q']);
    const pingStub = await stubRevisionPoll(page);
    try {
      const sw = await app.api('post', '/metadata', { mode: 'ETA' }); // the page is not told
      L.check('grid eta: (setup) the document was switched to ETA behind the page', !sw.__error, sw);
      await page.locator(CELL(ids.A, 'lambda')).click();
      const seen = await page.evaluate(async ([selector, clip]) => {
        const panel = document.getElementById('tabpanel-grid');
        const log = { error: null, message: null, texts: [] };
        const look = () => {
          const err = panel.querySelector('[data-testid="grid-summary-error"]');
          const msg = panel.querySelector('[data-testid="grid-message"]');
          if (err && !log.error) log.error = { code: err.dataset.code, text: err.textContent.trim() };
          if (msg && msg.textContent.trim() && !log.message) log.message = { code: msg.dataset.code || '', text: msg.textContent.trim() };
          log.texts.push(panel.textContent);
        };
        const obs = new MutationObserver(look);
        obs.observe(panel, { childList: true, subtree: true, characterData: true, attributes: true });
        const target = document.querySelector(selector);
        const dt = new DataTransfer();
        dt.setData('text/plain', clip);
        target.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
        const t0 = performance.now();
        while (performance.now() - t0 < 6000) {
          const root = document.querySelector('[data-testid="grid-root"]');
          if (root && root.dataset.state === 'eta') break;
          await new Promise((r) => setTimeout(r, 25));
        }
        look();
        obs.disconnect();
        return { error: log.error, message: log.message, stale: log.texts.some((t) => t.includes('The analysis changed')) };
      }, [CELL(ids.A, 'lambda'), '2e-5\t100\teta-src']);
      L.check('grid eta: the paste is answered with MODE_UNSUPPORTED and the ETA text "Pasting is not available in ETA mode. Nothing was applied."',
        Boolean(seen.error) && seen.error.code === 'MODE_UNSUPPORTED' && seen.error.text === 'Pasting is not available in ETA mode. Nothing was applied.', seen);
      L.check('grid eta: the message line carries the same text and data-code MODE_UNSUPPORTED', Boolean(seen.message) && seen.message.code === 'MODE_UNSUPPORTED', seen.message);
      L.check('grid eta: "The analysis changed; paste again" is never shown for it', seen.stale === false, seen);
      const apiA = (await app.api('get', '/nodes/' + ids.A)).node;
      L.check('grid eta: nothing was applied', apiA.quant.source === 'keep' && close(apiA.quant.lambda, 2e-5), apiA.quant);
    } finally { await pingStub.stop(); }
    await refreshShell(page);
    const etaState = await until(async () => page.evaluate(() => { const r = document.querySelector('[data-testid="grid-root"]'); return r && r.dataset.state === 'eta'; }), 5000);
    L.check('grid eta: after a redraw the panel shows the ETA notice and nothing else (data-state eta, no table)', Boolean(etaState) && (await page.locator('#tabpanel-grid .anl-eta').count()) > 0 && (await page.locator(TID('grid-table')).count()) === 0, await page.locator(TID('grid-table')).count());
    await app.shot('grid-eta', { locator: '#details-panel' });
    await app.api('post', '/metadata', { mode: 'FTA' });
    await refreshShell(page);
    const back = await until(async () => page.evaluate(() => { const r = document.querySelector('[data-testid="grid-root"]'); return r && r.dataset.state !== 'eta'; }), 5000);
    L.check('grid eta: back in FTA mode the grid is shown again', Boolean(back));
  });

  // ---- shortcuts, headers fit --------------------------------------------------------------------------
  await phase('shortcuts', async () => {
    await resetPumps(app, ids);
    await setFilter(app, '');
    const nodes0 = await nodeCount(app);
    const probe = async (combo) => {
      await page.locator(CELL(ids.C, 'name')).click();
      await page.keyboard.press(combo);
      await sleep(350);
      const modals = await page.locator('.fta-modal, .fta-modal-overlay').count();
      if (modals) { await page.keyboard.press('Escape'); await sleep(200); }
      return { modals, nodes: await nodeCount(app) };
    };
    const bad = [];
    for (const combo of ['Control+a', 'Control+d', 'Control+e']) {
      const r = await probe(combo);
      if (r.modals || r.nodes !== nodes0) bad.push({ combo, r });
    }
    L.check('grid shortcuts: with a cell focused, Ctrl+A, Ctrl+D and Ctrl+E add, delete or edit no tree node and open no dialog', bad.length === 0, bad);
    // Ctrl+Z reaches the shell: undo the last grid edit
    await page.locator(CELL(ids.C, 'name')).click();
    await page.keyboard.press('Enter');
    const input = page.locator(TID('grid-input'));
    await input.waitFor({ state: 'visible', timeout: 3000 });
    await input.fill('Pump C undone');
    await page.keyboard.press('Enter');
    await until(async () => (await nodeOf(page, ids.C)).name === 'Pump C undone', 3000);
    await until(async () => (await input.count()) === 0, 1500);
    await page.locator(CELL(ids.C, 'name')).click();
    await page.keyboard.press('Control+z');
    const undone = await until(async () => (await nodeOf(page, ids.C)).name === 'Pump C', 4000);
    L.check('grid shortcuts: Ctrl+Z from a focused cell reaches the shell and undoes the last edit', Boolean(undone), (await nodeOf(page, ids.C)).name);
    // Ctrl+S saves
    const target = path.join(root, 'grid_shortcuts_' + label + '.json');
    const saved = await app.api('post', '/file/save-as', { path: target });
    L.check('grid shortcuts: (setup) the document has a path to save to', !saved.__error, saved);
    await refreshShell(page);
    await sleep(300);
    await pagePatch(page, ids.C, { name: 'Pump C saved' });
    await page.locator(CELL(ids.C, 'name')).click();
    await page.keyboard.press('Control+s');
    const clean = await until(async () => (await app.api('get', '/revision')).dirty === false, 4000);
    L.check('grid shortcuts: Ctrl+S from a focused cell saves the document', Boolean(clean), await app.api('get', '/revision'));
    await pagePatch(page, ids.C, { name: 'Pump C' });
    // Ctrl+F reaches the shell's find
    await page.locator(CELL(ids.C, 'name')).click();
    await page.keyboard.press('Control+f');
    await sleep(250);
    const found = await page.evaluate(() => { const a = document.activeElement; return Boolean(a && a.closest('#tree-root') && a.matches('input')); });
    L.check('grid shortcuts: Ctrl+F from a focused cell focuses the tree search', found, await page.evaluate(() => document.activeElement && (document.activeElement.className || document.activeElement.tagName)));
    // Ctrl+A keeps its native meaning in the filter box and in the λ unit select
    const nodesNow = await nodeCount(app);
    const filterBox = page.locator(TID('grid-filter'));
    await filterBox.fill('some filter text');
    await filterBox.focus();
    await page.keyboard.press('Control+a');
    await sleep(250);
    const sel = await page.evaluate(() => { const f = document.querySelector('[data-testid="grid-filter"]'); return { start: f.selectionStart, end: f.selectionEnd, len: f.value.length, focused: document.activeElement === f }; });
    L.check('grid shortcuts: Ctrl+A in the filter box selects its text (native), no dialog opens', sel.focused && sel.start === 0 && sel.end === sel.len && (await page.locator('.fta-modal, .fta-modal-overlay').count()) === 0, sel);
    await filterBox.fill('');
    await sleep(300);
    await page.locator(`${TID('grid-lambda-unit')}`).focus();
    await page.keyboard.press('Control+a');
    await sleep(300);
    const modalsSel = await page.locator('.fta-modal, .fta-modal-overlay').count();
    if (modalsSel) { await page.keyboard.press('Escape'); await sleep(200); }
    L.check('grid shortcuts: Ctrl+A in the λ unit select adds no node and opens no dialog (native meaning kept)', modalsSel === 0 && (await nodeCount(app)) === nodesNow, { modalsSel });
    await page.locator(CELL(ids.C, 'name')).click();
  });

  await phase('headers_fit', async () => {
    await setHidden(app, []);
    await setFilter(app, '');
    for (const lang of ['en', 'ja']) {
      await app.setLanguage(lang);
      await sleep(250);
      const bad = [];
      let seen = 0;
      for (const sortCol of COLUMN_ORDER) { // each column sorted in turn (the indicator takes room)
        await setSort(app, sortCol, 'ascending');
        const widths = await page.evaluate(() => Array.from(document.querySelectorAll('[data-testid="grid-th"]')).map((th) => ({ col: th.dataset.column, sw: th.scrollWidth, cw: th.clientWidth })));
        seen += widths.length;
        for (const w of widths) if (w.sw > w.cw) bad.push({ sortedBy: sortCol, ...w });
        await setSort(app, sortCol, 'descending');
        const widthsD = await page.evaluate(() => Array.from(document.querySelectorAll('[data-testid="grid-th"]')).map((th) => ({ col: th.dataset.column, sw: th.scrollWidth, cw: th.clientWidth })));
        for (const w of widthsD) if (w.sw > w.cw) bad.push({ sortedBy: sortCol + ' desc', ...w });
      }
      L.check(`grid headers fit [${lang}]: with each column sorted in turn no header is wider than its cell (scrollWidth <= clientWidth)`, seen === 100 && bad.length === 0, bad.length ? bad.slice(0, 8) : seen);
    }
    await setSort(app, 'name', 'ascending');
    await app.setLanguage('en');
    // an error next to a cell (screenshot for the reviewer)
    await setHidden(app, []);
    await page.locator(CELL(ids.B, 'lambda')).click();
    await page.keyboard.press('Enter');
    const input = page.locator(TID('grid-input'));
    await input.waitFor({ state: 'visible', timeout: 3000 });
    await input.fill('abc');
    await page.keyboard.press('Enter');
    const err = await until(async () => (await page.locator(TID('grid-cell-error')).count()) > 0, 2000);
    L.check('criterion1_error: a refused reading shows its message next to the cell and keeps the editor open', Boolean(err) && (await input.getAttribute('aria-invalid')) === 'true' && (await page.locator(TID('grid-cell-error')).first().textContent()).trim().length > 3, await page.locator(TID('grid-cell-error')).count());
    await app.shot('grid_cell_error_' + label);
    await page.keyboard.press('Escape');
    await until(async () => (await input.count()) === 0, 1500);
  });

  // ---- the 50-row paste is one undo step ------------------------------------------------------------------
  await phase('criterion5_undo', async () => {
    const fixture = path.join(root, 'perf_grid_500.json');
    await openInPage(page, fixture);
    await settledHeadline(page, 1200);
    await openGrid(app);
    await setFilter(app, '');
    await setSort(app, 'id', 'ascending');
    await setLambdaUnit(app, 'y');
    await setHidden(app, ['tau', 'mu', 'q']);
    const snapshot = async () => {
      const st = await app.api('get', '/state');
      const out = {};
      const walk = (n) => { if (!(n.children || []).length) out[n.id] = JSON.stringify([n.quant, n.probability]); (n.children || []).forEach(walk); };
      walk(st.tree);
      return out;
    };
    const before = await snapshot();
    const lines = fs.readFileSync(path.join(FIX, 'perf_grid_500_paste.tsv'), 'utf8').split('\n').filter(Boolean).slice(0, 50);
    await doPaste(app, CELL('E00_00', 'lambda'), lines.map((l, i) => l.split('\t').map((c, j) => (j === 2 ? 'undo-' + i : c)).join('\t')).join('\n'));
    const s = await readSummary(page);
    const mid = await snapshot();
    const changed = Object.keys(before).filter((k) => before[k] !== mid[k]);
    L.check('criterion5_undo: a 50-row paste is applied (summary 50, 50 events changed)', s.applied === 50 && changed.length === 50, { applied: s.applied, changed: changed.length });
    await page.locator(CELL('E00_00', 'lambda')).click();
    await page.keyboard.press('Control+z');
    const restored = await until(async () => { const now = await snapshot(); return Object.keys(before).every((k) => before[k] === now[k]); }, 8000, 300);
    L.check('criterion5_undo: one Ctrl+Z restores all 50 rows', Boolean(restored));
    await setLambdaUnit(app, 'h');
    await setHidden(app, []);
  });

  // ---- empty state -----------------------------------------------------------------------------------------
  await phase('empty', async () => {
    await app.api('post', '/new', { force: true });
    await refreshShell(page);
    const t = await until(async () => page.locator(TID('grid-empty')).count(), 4000);
    const txt = t ? (await page.locator(TID('grid-empty')).first().textContent()).trim() : '';
    L.check('grid empty state: a tree with no basic events shows grid-empty with the Quantification tab text', txt === 'The tree has no basic events yet.', txt);
    await app.shot('grid-empty', { locator: '#details-panel' });
    await app.setLanguage('ja');
    await sleep(200);
    const tj = (await page.locator(TID('grid-empty')).first().textContent()).trim();
    L.check('grid empty state [ja]', tj === 'ツリーにはまだ基本事象がありません。', tj);
    await app.setLanguage('en');
  });

  const errs = app.errorsSince(0, [/409/, /STALE_REVISION/, /CONFLICT/]);
  L.check('no console errors in the grid run (the one deliberate 409 excepted)', errs.length === 0, errs);
  await app.context.close();

  // ---- performance (own page loads; after everything else) ------------------------------------------------------
  const tsv = fs.readFileSync(path.join(FIX, 'perf_grid_500_paste.tsv'), 'utf8');
  const fixtureSha = sha256(path.join(FIX, 'perf_grid_500.json'));
  const pasteSha = sha256(path.join(FIX, 'perf_grid_500_paste.tsv'));
  const commit = gitHead();
  const condition = 'GUI suite harness (lib.js), bundled Chromium unless FTA_GUI_CHANNEL is set, dev server, app loaded and fixture opened before timing, one discarded warm-up then the median of 5';

  await phase('criterion10', async () => {
    const r = await perf7(url, root);
    writePerf('PERF-7', {
      requirement: 'PERF-7', what: 'the Grid tab opens with the 500 rows of perf_grid_500.json drawn (first frame after 500 grid-row elements exist, from the click on the tab)',
      bound_ms: PERF_BOUNDS.PERF7, provisional: true, browser: r.browser, runs_ms: r.runs, median_ms: r.med, warmups: 1,
      fixture: { name: 'perf_grid_500.json', sha256: fixtureSha }, condition, commit,
    });
    L.check(`criterion10_perf7: PERF-7 median ${r.med.toFixed(0)} ms of ${RUNS} runs <= ${PERF_BOUNDS.PERF7} ms (provisional bound; PERF-7.json written)`, r.med <= PERF_BOUNDS.PERF7, r);
  });

  await phase('criterion9', async () => {
    const app2 = await L.openApp(url, { prefs: { 'fta.advanced': '1', 'fta.sigFigs': '6' }, viewport: { width: 1600, height: 1000 } });
    try {
      const r = await perf6(app2, root, tsv);
      writePerf('PERF-6', {
        requirement: 'PERF-6', what: 'paste perf_grid_500_paste.tsv (500 rows x lambda per year, T, source) into perf_grid_500.json; stop at the first frame showing both the final headline and a summary of 500 rows applied',
        bound_ms: PERF_BOUNDS.PERF6, provisional: true, browser: app2.context.browser().version(), runs_ms: r.runs, median_ms: r.med, warmups: 1,
        headline_before: r.h0, headline_after: r.finished,
        fixture: { name: 'perf_grid_500.json', sha256: fixtureSha }, paste: { name: 'perf_grid_500_paste.tsv', sha256: pasteSha }, condition, commit,
      });
      L.check(`criterion9_perf6: PERF-6 median ${r.med.toFixed(0)} ms of ${RUNS} runs <= ${PERF_BOUNDS.PERF6} ms (provisional bound; PERF-6.json written)`, r.med <= PERF_BOUNDS.PERF6, r);
      const errs2 = app2.errorsSince(0);
      L.check('no console errors in the PERF-6 run', errs2.length === 0, errs2);
    } finally {
      await app2.context.close();
    }
  });
  if (phaseFailures.length) L.info('phases that threw', phaseFailures);
}

L.runSection('grid', main);
