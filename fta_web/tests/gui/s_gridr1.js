// Grid tab, polish round R1 (F3): the refusal box of a cell, the ETA text, the paste hint, the failed-paste sentence.
// node s_gridr1.js <url> <label> <root>
//
//   1  the refusal message of an edited cell does not cover the row below (en and ja, 1600x1000 and a narrow pane)
//   2  "Pasting is not available in ETA mode" goes when the mode changes (ETA -> FTA, also while the tab is away)
//   3  the Ctrl+V hint is not shown over an empty grid; it is shown with rows and a selected cell
//   5  "The paste failed: <error> Nothing was applied." reads as sentences whether or not the error ends with a full stop
// Shots: gridr1-error-<lang>-<wide|narrow>, gridr1-eta-cleared, gridr1-empty-nohint (in FTA_GUI_OUT).
'use strict';
const L = require('./lib');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const TID = (id) => `[data-testid="${id}"]`;
const CELL = (nodeId, col) => `[data-testid="grid-cell"][data-node-id="${nodeId}"][data-column="${col}"]`;

async function until(fn, timeout = 3000, step = 25) {
  const t0 = Date.now();
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() - t0 > timeout) return null;
    await sleep(step);
  }
}

const refreshShell = (page) => page.evaluate(() => window.ftaShell.refresh());

async function addNode(app, parentId, name, extra) {
  const r = await app.api('post', '/nodes', Object.assign({ parentId, name, probability: 1 }, extra || {}));
  if (r.__error) throw new Error('POST /nodes ' + name + ': ' + JSON.stringify(r));
  return r.nodeId;
}

/** Five basic events in tree order: Pump A, Valve X (fixed), Pump B, C, D (rate). */
async function buildDoc(app) {
  await app.api('post', '/new', { force: true });
  const ids = {};
  for (const [i, letter] of ['A', 'B', 'C', 'D'].entries()) {
    if (i === 1) ids.X = await addNode(app, 'root', 'Valve X', { probability: 0.012345, quant: { model: 'fixed' } });
    ids[letter] = await addNode(app, 'root', 'Pump ' + letter, { probability: 0.5, quant: { model: 'rate', lambda: 2e-5 * (i + 1), T: 100 * (i + 1) } });
  }
  return ids;
}

async function openGrid(app) {
  await app.clickTab('grid');
  await app.page.waitForSelector(TID('grid-root'), { timeout: 10000 });
  await app.page.waitForSelector(`${TID('grid-table')}, ${TID('grid-empty')}`, { timeout: 10000 });
}

/** Answer the page's periodic GET /api/revision with what it already holds, so nothing redraws by itself. */
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

/** A synthetic paste on a cell (as the grid's own GUI section does) and a wait until the paste is over. */
async function doPaste(page, selector, clip) {
  await page.locator(selector).click();
  await page.evaluate(async ([sel, text]) => {
    const target = document.querySelector(sel);
    const root = document.querySelector('[data-testid="grid-root"]');
    const dt = new DataTransfer();
    dt.setData('text/plain', text);
    target.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
    const limit = performance.now() + 6000;
    await new Promise((r) => setTimeout(r, 60));
    while (root.dataset.state === 'pasting' && performance.now() < limit) await new Promise((r) => setTimeout(r, 20));
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  }, [selector, clip]);
}

const summaryState = (page) => page.evaluate(() => {
  const q = (s) => document.querySelector(s);
  const err = q('[data-testid="grid-summary-error"]');
  const msg = q('[data-testid="grid-message"]');
  const empty = q('[data-testid="grid-summary-empty"]');
  return {
    error: err ? { code: err.dataset.code, text: err.textContent.trim() } : null,
    message: msg ? msg.textContent.trim() : null,
    messageCode: msg ? msg.dataset.code || '' : null,
    emptyShown: Boolean(empty) && !empty.hidden && empty.getClientRects().length > 0,
    emptyText: empty ? empty.textContent.trim() : null,
  };
});

/** The geometry of the open refusal box against the rows around it. */
const errorGeometry = (page) => page.evaluate(() => {
  const rect = (e) => { const b = e.getBoundingClientRect(); return { left: b.left, top: b.top, right: b.right, bottom: b.bottom, width: b.width, height: b.height }; };
  const err = document.querySelector('[data-testid="grid-cell-error"]');
  if (!err) return null;
  const rows = Array.from(document.querySelectorAll('[data-testid="grid-row"]'));
  const editing = rows.find((tr) => tr.querySelector('td.is-editing'));
  if (!editing) return { error: rect(err), editing: null };
  const at = rows.indexOf(editing);
  const below = rows[at + 1] || null;
  const e = rect(err);
  const overlaps = rows.filter((tr) => {
    const r = tr.getBoundingClientRect();
    return Math.min(e.right, r.right) - Math.max(e.left, r.left) > 0.5 && Math.min(e.bottom, r.bottom) - Math.max(e.top, r.top) > 0.5;
  }).map((tr) => tr.dataset.nodeId);
  // is every cell of the row below the topmost thing at its centre (nothing is laid over it)?
  const scroll = document.querySelector('[data-testid="grid-scroll"]');
  const covered = [];
  if (below) {
    const box = scroll.getBoundingClientRect();
    for (const td of Array.from(below.cells)) {
      const r = td.getBoundingClientRect();
      const x = r.left + r.width / 2;
      const y = r.top + r.height / 2;
      if (x < box.left || x > box.right || y < box.top || y > box.bottom) continue; // clipped by the scrolling box
      const hit = document.elementFromPoint(x, y);
      if (!(hit && td.contains(hit))) covered.push(td.dataset.column);
    }
  }
  const cell = editing.querySelector('td.is-editing');
  const table = document.querySelector('[data-testid="grid-table"]');
  return {
    error: e,
    editRow: rect(editing),
    cell: rect(cell),
    below: below ? rect(below) : null,
    belowId: below ? below.dataset.nodeId : null,
    scroll: rect(scroll),
    table: rect(table),
    overlaps,
    covered,
    text: err.textContent.trim(),
    role: err.getAttribute('role'),
    narrow: document.querySelector('[data-testid="grid-root"]').hasAttribute('data-narrow'),
  };
});

async function setLayout(app, value) {
  const { page } = app;
  await page.evaluate((v) => localStorage.setItem('fta.layout', JSON.stringify(v)), value);
  const onDialog = (d) => { d.accept().catch(() => {}); };
  page.on('dialog', onDialog);
  try {
    await page.reload();
    await L.waitBoot(page);
    await app.waitDiagram();
  } finally { page.off('dialog', onDialog); }
  await openGrid(app);
  await sleep(400);
}

async function main(url, label, root) {
  L.setSection('gridr1[' + label + ']');
  const app = await L.openApp(url, { prefs: { 'fta.advanced': '1' }, viewport: { width: 1600, height: 1000 } });
  const { page } = app;
  page.setDefaultTimeout(8000);
  const failures = [];
  const phase = async (name, fn) => {
    try { await fn(); } catch (e) {
      failures.push(name);
      L.check(`${name}: finished without an exception`, false, String((e && e.stack) || e).slice(0, 600));
    }
  };

  let ids = null;
  await phase('setup', async () => {
    ids = await buildDoc(app);
    await refreshShell(page);
    await app.setAdvanced(true);
    await openGrid(app);
    const ok = await until(async () => (await page.locator(TID('grid-row')).count()) === 5, 6000);
    L.check('setup: the grid shows the 5 basic events', Boolean(ok), await page.locator(TID('grid-row')).count());
  });
  if (!ids) { await app.context.close(); return; }

  // ---- 1: the refusal box leaves the row below uncovered --------------------------------------
  const refuse = async (tag, column, rowKey, typed) => {
    await page.locator(CELL(ids[rowKey], column)).click();
    await page.keyboard.press('Enter');
    const input = page.locator(TID('grid-input'));
    await input.waitFor({ state: 'visible', timeout: 3000 });
    await input.fill(typed);
    await page.keyboard.press('Enter');
    const shown = await until(async () => (await page.locator(TID('grid-cell-error')).count()) > 0, 3000);
    L.check(`${tag}: a refused reading shows grid-cell-error and keeps the editor open`, Boolean(shown) && (await input.getAttribute('aria-invalid')) === 'true');
    await sleep(150);
    return errorGeometry(page);
  };
  const judge = (tag, g) => {
    L.check(`${tag}: the message is a role=alert box with text`, Boolean(g) && g.role === 'alert' && g.text.length > 3, g && g.text);
    if (!g || !g.editRow) return;
    L.check(`${tag}: the message lies under the edited row, not over it (top >= row bottom - 1)`, g.error.top >= g.editRow.bottom - 1, { error: g.error, row: g.editRow });
    L.check(`${tag}: the message overlaps no row of the table`, g.overlaps.length === 0, g.overlaps);
    L.check(`${tag}: the row below starts under the message (no overlap in y)`, Boolean(g.below) && g.below.top >= g.error.bottom - 1, { error: g.error, below: g.below });
    L.check(`${tag}: every cell of the row below is the topmost thing at its centre (nothing laid over it)`, g.covered.length === 0, g.covered);
    L.check(`${tag}: the row below is fully visible in the table box`, Boolean(g.below) && g.below.top >= g.scroll.top - 1 && g.below.bottom <= g.scroll.bottom + 1, { below: g.below, scroll: g.scroll });
    L.check(`${tag}: the whole message lies inside the visible table box (not clipped at its right edge)`, g.error.right <= g.scroll.right + 1 && g.error.left >= g.scroll.left - 1, { error: g.error, scroll: g.scroll });
    L.check(`${tag}: the message starts at the edited cell or inside the table width`, g.error.left >= g.table.left - 1 && g.error.right <= g.table.right + 1, { error: g.error, table: g.table });
  };

  const runErrors = async (size) => {
    for (const lang of ['en', 'ja']) {
      await phase(`error ${lang} ${size}`, async () => {
        await app.setLanguage(lang);
        await sleep(200);
        await page.locator(TID('grid-filter')).fill('');
        const tag = `gridr1 cell error [${lang}, ${size}]`;
        const g = await refuse(tag, 'T', 'B', 'abc');
        judge(tag, g);
        L.check(`${tag}: the pane is ${size}`, Boolean(g) && g.narrow === (size === 'narrow'), g && g.narrow);
        await app.shot(`gridr1-error-${lang}-${size}`, { locator: '#details-panel' });
        // the last column of a fixed row: the box stays inside the table's width
        await page.keyboard.press('Escape');
        await sleep(100);
        L.check(`${tag}: Escape closes the editor and removes the message`, (await page.locator(TID('grid-cell-error')).count()) === 0 && (await page.locator(TID('grid-input')).count()) === 0);
        const g2 = await refuse(tag + ' q of the fixed row', 'q', 'X', 'abc');
        judge(tag + ' q of the fixed row', g2);
        await page.keyboard.press('Escape');
        await sleep(100);
        // a correction removes the message
        await refuse(tag + ' (then typing)', 'T', 'C', 'abc');
        await page.locator(TID('grid-input')).fill('150');
        L.check(`${tag}: typing again removes the message and the row it stood in`, (await page.locator(TID('grid-cell-error')).count()) === 0 && (await page.locator('tr.grid-error-row').count()) === 0);
        await page.keyboard.press('Escape');
        await sleep(100);
      });
    }
  };
  await runErrors('wide');

  // ---- 3: the paste hint --------------------------------------------------------------------------
  await phase('hint', async () => {
    await app.setLanguage('en');
    await page.locator(CELL(ids.A, 'name')).click();
    const withRows = await until(async () => page.evaluate(() => { const h = document.querySelector('[data-testid="grid-hint"]'); return Boolean(h) && !h.hidden && h.getClientRects().length > 0; }), 2000);
    L.check('gridr1 hint: with rows and a selected cell (wide pane) the Ctrl+V hint is shown', Boolean(withRows));
    const scrollTitle = await page.locator(TID('grid-scroll')).getAttribute('title');
    L.check('gridr1 hint: with rows the table box carries the hint as its title', /Ctrl\+V/.test(scrollTitle || ''), scrollTitle);
    // the cell is still selected when the document becomes empty
    await app.api('post', '/new', { force: true });
    await refreshShell(page);
    const emptied = await until(async () => page.locator(TID('grid-empty')).count(), 4000);
    L.check('gridr1 hint: (setup) the new document shows the empty state', Boolean(emptied));
    await sleep(200);
    const hidden = await page.evaluate(() => { const h = document.querySelector('[data-testid="grid-hint"]'); return { present: Boolean(h), shown: Boolean(h) && !h.hidden && h.getClientRects().length > 0 }; });
    L.check('gridr1 hint: an empty grid shows no Ctrl+V hint', hidden.shown === false, hidden);
    const title = await page.locator(TID('grid-scroll')).getAttribute('title');
    L.check('gridr1 hint: an empty grid has no hint tooltip either', !title, title);
    await app.shot('gridr1-empty-nohint', { locator: '#details-panel' });
    await app.setLanguage('ja');
    await sleep(200);
    const hiddenJa = await page.evaluate(() => { const h = document.querySelector('[data-testid="grid-hint"]'); return Boolean(h) && !h.hidden && h.getClientRects().length > 0; });
    L.check('gridr1 hint [ja]: an empty grid shows no Ctrl+V hint', hiddenJa === false);
    await app.setLanguage('en');
    // rows come back: the hint follows a selected cell again
    ids = await buildDoc(app);
    await refreshShell(page);
    await until(async () => (await page.locator(TID('grid-row')).count()) === 5, 6000);
    await page.locator(CELL(ids.A, 'name')).click();
    const back = await until(async () => page.evaluate(() => { const h = document.querySelector('[data-testid="grid-hint"]'); return Boolean(h) && !h.hidden && h.getClientRects().length > 0; }), 2000);
    L.check('gridr1 hint: with rows again and a selected cell the hint is shown', Boolean(back));
  });

  // ---- 2: the ETA text goes with the mode ---------------------------------------------------------
  const etaPaste = async () => {
    await page.locator(TID('grid-filter')).fill('');
    await sleep(300);
    const sw = await app.api('post', '/metadata', { mode: 'ETA' }); // behind the page
    if (sw.__error) throw new Error('metadata ETA: ' + JSON.stringify(sw));
    await doPaste(page, CELL(ids.A, 'lambda'), '2e-5');
    return summaryState(page);
  };
  await phase('eta', async () => {
    await app.setLanguage('en');
    const stub = await stubRevisionPoll(page);
    try {
      const s = await etaPaste();
      L.check('gridr1 eta: the paste is answered with the ETA text (data-code MODE_UNSUPPORTED) in the summary and on the message line',
        Boolean(s.error) && s.error.code === 'MODE_UNSUPPORTED' && /ETA mode/.test(s.error.text) && s.messageCode === 'MODE_UNSUPPORTED', s);
    } finally { await stub.stop(); }
    await refreshShell(page);
    const etaOn = await until(async () => page.evaluate(() => document.querySelector('[data-testid="grid-root"]').dataset.state === 'eta'), 5000);
    L.check('gridr1 eta: after a redraw the panel shows the ETA notice', Boolean(etaOn));
    await app.api('post', '/metadata', { mode: 'FTA' });
    await refreshShell(page);
    const back = await until(async () => page.evaluate(() => document.querySelector('[data-testid="grid-root"]').dataset.state !== 'eta'), 5000);
    L.check('gridr1 eta: back in FTA mode the grid is shown again', Boolean(back));
    await sleep(300);
    const s2 = await summaryState(page);
    L.check('gridr1 eta: ETA -> FTA: the summary no longer says "not available in ETA mode" (no grid-summary-error)', s2.error === null && !/ETA/.test(String(s2.message)), s2);
    L.check('gridr1 eta: ETA -> FTA: the message line is empty and the note before any paste is shown', s2.message === '' && s2.emptyShown && /Nothing pasted yet/.test(s2.emptyText), s2);
    await app.shot('gridr1-eta-cleared', { locator: '#details-panel' });
  });

  await phase('eta while the tab is away', async () => {
    const stub = await stubRevisionPoll(page);
    try {
      const s = await etaPaste();
      L.check('gridr1 eta away: (setup) the ETA text is shown after the paste', Boolean(s.error) && s.error.code === 'MODE_UNSUPPORTED', s);
    } finally { await stub.stop(); }
    await app.clickTab('quant'); // the grid is not the active tab now
    await refreshShell(page);
    await sleep(300);
    await app.api('post', '/metadata', { mode: 'FTA' });
    await refreshShell(page);
    await sleep(300);
    await app.clickTab('grid');
    await page.waitForSelector(TID('grid-table'), { timeout: 6000 });
    const s2 = await summaryState(page);
    L.check('gridr1 eta away: back on the Grid tab after the mode changed, the ETA text is gone', s2.error === null && s2.message === '' && s2.emptyShown, s2);
  });

  await phase('eta then a new document', async () => {
    const stub = await stubRevisionPoll(page);
    try {
      const s = await etaPaste();
      L.check('gridr1 eta doc: (setup) the ETA text is shown after the paste', Boolean(s.error) && s.error.code === 'MODE_UNSUPPORTED', s);
    } finally { await stub.stop(); }
    await app.api('post', '/new', { force: true }); // a new document is an FTA one
    await refreshShell(page);
    await sleep(400);
    const s2 = await summaryState(page);
    L.check('gridr1 eta doc: after a new document the ETA text is gone', s2.error === null && s2.message === '', s2);
    ids = await buildDoc(app);
    await refreshShell(page);
    await until(async () => (await page.locator(TID('grid-row')).count()) === 5, 6000);
  });

  // ---- 5: the failed-paste sentence --------------------------------------------------------------
  await phase('failed', async () => {
    const cases = [
      { error: 'Disk is full', en: 'The paste failed: Disk is full. Nothing was applied.', ja: '貼り付けに失敗しました: Disk is full。 何も適用されていません。' },
      { error: 'Disk is full.', en: 'The paste failed: Disk is full. Nothing was applied.', ja: '貼り付けに失敗しました: Disk is full. 何も適用されていません。' },
      { error: 'Disk is full!', en: 'The paste failed: Disk is full! Nothing was applied.', ja: '貼り付けに失敗しました: Disk is full! 何も適用されていません。' },
      { error: 'ディスクがいっぱいです', en: 'The paste failed: ディスクがいっぱいです. Nothing was applied.', ja: '貼り付けに失敗しました: ディスクがいっぱいです。 何も適用されていません。' },
      { error: 'ディスクがいっぱいです。', en: 'The paste failed: ディスクがいっぱいです。 Nothing was applied.', ja: '貼り付けに失敗しました: ディスクがいっぱいです。 何も適用されていません。' },
    ];
    let current = cases[0].error;
    const handler = (route) => route.fulfill({
      status: 500, contentType: 'application/json',
      body: JSON.stringify({ ok: false, error: { code: 'INTERNAL_ERROR', message: current, detail: {} } }),
    });
    await page.route('**/api/grid/paste', handler);
    try {
      for (const c of cases) {
        current = c.error;
        for (const lang of ['en', 'ja']) {
          await app.setLanguage(lang);
          await sleep(150);
          await doPaste(page, CELL(ids.A, 'lambda'), '3e-5');
          const s = await summaryState(page);
          L.check(`gridr1 failed [${lang}] error "${c.error}": the summary reads "${c[lang]}"`, Boolean(s.error) && s.error.code === 'PASTE_FAILED' && s.error.text === c[lang], s.error);
          L.check(`gridr1 failed [${lang}] error "${c.error}": the message line says the same`, s.message === c[lang], s.message);
        }
      }
      // a language switch redraws the same failure in the other language
      await app.setLanguage('en');
      await sleep(200);
      const again = await summaryState(page);
      L.check('gridr1 failed: switching the language redraws the sentence (ja -> en keeps the stored error, closed with a full stop)', Boolean(again.error) && again.error.text === cases[cases.length - 1].en, again.error);
    } finally { await page.unroute('**/api/grid/paste', handler); }
  });

  // ---- 1 again: a narrow pane -------------------------------------------------------------------------------
  await phase('narrow setup', async () => {
    await page.setViewportSize({ width: 1100, height: 800 });
    await setLayout(app, { tree: 200, ai: 760, details: 260, analysis: null });
    const isNarrow = await page.evaluate(() => document.querySelector('[data-testid="grid-root"]').hasAttribute('data-narrow'));
    L.check('gridr1 narrow: (setup) the pane is narrow (data-narrow)', isNarrow);
  });
  await runErrors('narrow');

  await phase('restore the layout', async () => {
    await page.setViewportSize({ width: 1600, height: 1000 });
    await setLayout(app, { tree: 320, ai: 340, details: 260, analysis: null });
    await app.setLanguage('en');
  });

  const errs = app.errorsSince(0, [/409/, /500/, /STALE_REVISION/, /CONFLICT/, /Failed to load resource/]);
  L.check('no console errors in the gridr1 run (the stubbed failures excepted)', errs.length === 0, errs);
  await app.context.close();
  if (failures.length) L.info('phases that threw', failures);
}

L.runSection('gridr1', main);
