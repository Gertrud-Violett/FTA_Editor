// Grid tab, polish round R2 (F3): a refused cell value must not leave an orphan editor behind.
// node s_gridr2.js <url> <label> <root>
//
// While the cell editor holds a REFUSED value (error row shown, editor stays open), six things repaint the table body:
//   sort    a header sort click
//   unit    a change of the lambda unit select in the header
//   lang    a language switch (the fta:language event)
//   tab     leaving the Grid tab and coming back
//   sigfigs a change of the significant-figures select of the app header (ctx.onSigFigs)
//   columns a toggle in the Columns chooser of the Grid toolbar (onColumnToggle)
// Each must leave no editor, no error row and no is-editing cell behind, and a cell must open again afterwards
// (before the fix the editor pointed at detached nodes and openEditor() answered false until the next new document).
// Shots: gridr2-<path>-after, gridr2-<path>-edited (in FTA_GUI_OUT).
'use strict';
const L = require('./lib');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const TID = (id) => `[data-testid="${id}"]`;
const CELL = (nodeId, col) => `[data-testid="grid-cell"][data-node-id="${nodeId}"][data-column="${col}"]`;
const UNIT_FACTOR = { h: 1, y: 8760, FIT: 1e9 };

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

/** What the grid shows of an open or orphan editor. */
const editorState = (page) => page.evaluate(() => ({
  errors: document.querySelectorAll('[data-testid="grid-cell-error"]').length,
  errorRows: document.querySelectorAll('tr.grid-error-row').length,
  inputs: document.querySelectorAll('[data-testid="grid-input"]').length,
  editing: document.querySelectorAll('td.is-editing').length,
  rows: document.querySelectorAll('[data-testid="grid-row"]').length,
}));

async function main(url, label, root) {
  L.setSection('gridr2[' + label + ']');
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

  /** A fresh document with the five basic events, the Grid tab open, English, unit /h. */
  const fresh = async () => {
    const ids = await buildDoc(app);
    await refreshShell(page);
    await app.setAdvanced(true);
    await openGrid(app);
    await app.setLanguage('en');
    const sel = page.locator(TID('grid-lambda-unit'));
    if ((await sel.inputValue()) !== 'h') await sel.selectOption('h');
    const ok = await until(async () => (await page.locator(TID('grid-row')).count()) === 5, 6000);
    if (!ok) throw new Error('the grid does not show the 5 basic events: ' + (await page.locator(TID('grid-row')).count()));
    await page.locator(TID('grid-filter')).fill('');
    await sleep(300);
    return ids;
  };

  /** Open the lambda cell of a row with Enter; true when the editor is there. */
  const openLambda = async (id) => {
    await page.locator(CELL(id, 'lambda')).click();
    await page.keyboard.press('Enter');
    return Boolean(await until(async () => (await page.locator(TID('grid-input')).count()) > 0, 2500));
  };

  /** Type a refused value and press Enter: the error row shows and the editor stays open. */
  const refuse = async (tag, id) => {
    const opened = await openLambda(id);
    if (!opened) { L.check(`${tag}: (setup) the lambda cell opens`, false); return false; }
    await page.locator(TID('grid-input')).fill('abc');
    await page.keyboard.press('Enter');
    const shown = await until(async () => (await page.locator(TID('grid-cell-error')).count()) > 0, 3000);
    const s = await editorState(page);
    const ok = Boolean(shown) && s.inputs === 1 && s.errorRows === 1;
    L.check(`${tag}: (setup) the refused 'abc' shows grid-cell-error and keeps the editor open`, ok, s);
    return ok;
  };

  /** After the path action: nothing of the editor is left, the rows are there, and a cell edits again. */
  const judge = async (tag, id, unit) => {
    await sleep(250);
    const s = await editorState(page);
    L.check(`${tag}: no grid-cell-error is left after the action`, s.errors === 0, s);
    L.check(`${tag}: no tr.grid-error-row is left after the action`, s.errorRows === 0, s);
    L.check(`${tag}: no grid-input is left after the action`, s.inputs === 0, s);
    L.check(`${tag}: no td.is-editing is left after the action`, s.editing === 0, s);
    L.check(`${tag}: the table still shows the 5 rows`, s.rows === 5, s);

    const reopened = await openLambda(id);
    L.check(`${tag}: a lambda cell can be opened again (the editor is not stuck on detached nodes)`, reopened, await editorState(page));
    if (!reopened) return;
    await page.locator(TID('grid-input')).fill('3e-5');
    await page.keyboard.press('Enter');
    const want = 3e-5 / UNIT_FACTOR[unit];
    const close = (v) => typeof v === 'number' && Math.abs(v - want) <= Math.abs(want) * 1e-9;
    const stored = await until(async () => close((await app.api('get', '/nodes/' + id)).node.quant.lambda), 4000);
    const got = (await app.api('get', '/nodes/' + id)).node.quant.lambda;
    L.check(`${tag}: the edited lambda reaches the server (typed 3e-5 in unit ${unit} -> ${want} per hour)`, Boolean(stored), got);
    await sleep(250);
    const e = await editorState(page);
    L.check(`${tag}: after the successful commit no editor, error or is-editing cell remains`, e.errors === 0 && e.errorRows === 0 && e.inputs === 0 && e.editing === 0, e);
  };

  // ---- 1: a header sort click ---------------------------------------------------------------------
  await phase('sort', async () => {
    const tag = 'gridr2 sort';
    const ids = await fresh();
    if (!(await refuse(tag, ids.B))) return;
    await page.locator(`${TID('grid-sort')}[data-column="lambda"]`).click();
    await sleep(200);
    await app.shot('gridr2-sort-after', { locator: '#details-panel' });
    const aria = await page.locator(`${TID('grid-th')}[data-column="lambda"]`).getAttribute('aria-sort');
    L.check(`${tag}: (setup) the sort took effect (aria-sort ascending on lambda)`, aria === 'ascending', aria);
    await judge(tag, ids.C, 'h');
    await app.shot('gridr2-sort-edited', { locator: '#details-panel' });
  });

  // ---- 2: a change of the lambda unit -------------------------------------------------------------
  await phase('unit', async () => {
    const tag = 'gridr2 unit';
    const ids = await fresh();
    try {
      if (!(await refuse(tag, ids.B))) return;
      await page.locator(TID('grid-lambda-unit')).selectOption('y');
      await sleep(200);
      await app.shot('gridr2-unit-after', { locator: '#details-panel' });
      const now = await page.locator(TID('grid-lambda-unit')).inputValue();
      L.check(`${tag}: (setup) the unit select now says /y`, now === 'y', now);
      await judge(tag, ids.C, 'y');
      await app.shot('gridr2-unit-edited', { locator: '#details-panel' });
    } finally {
      const sel = page.locator(TID('grid-lambda-unit'));
      if ((await sel.count()) && (await sel.inputValue()) !== 'h') await sel.selectOption('h');
    }
  });

  // ---- 3: a language switch -----------------------------------------------------------------------
  await phase('lang', async () => {
    const tag = 'gridr2 lang';
    const ids = await fresh();
    try {
      if (!(await refuse(tag, ids.B))) return;
      await app.setLanguage('ja'); // the real language button of the header
      await sleep(250);
      await app.shot('gridr2-lang-after', { locator: '#details-panel' });
      const lang = await page.evaluate(() => window.ftaShell.language);
      L.check(`${tag}: (setup) the language is now ja`, lang === 'ja', lang);
      await judge(tag, ids.C, 'h');
      await app.shot('gridr2-lang-edited', { locator: '#details-panel' });
    } finally {
      await app.setLanguage('en');
    }
  });

  // ---- 4: leaving the Grid tab and coming back ------------------------------------------------------
  await phase('tab', async () => {
    const tag = 'gridr2 tab';
    const ids = await fresh();
    if (!(await refuse(tag, ids.B))) return;
    await app.clickTab('quant');
    await sleep(300);
    await app.clickTab('grid');
    await page.waitForSelector(TID('grid-table'), { timeout: 6000 });
    await sleep(200);
    await app.shot('gridr2-tab-after', { locator: '#details-panel' });
    await judge(tag, ids.C, 'h');
    await app.shot('gridr2-tab-edited', { locator: '#details-panel' });
  });

  // ---- 5: a change of the significant figures (header select) ---------------------------------------
  await phase('sigfigs', async () => {
    const tag = 'gridr2 sigfigs';
    const ids = await fresh();
    const sig = page.locator('#sigfig-select');
    const before = await sig.inputValue();
    try {
      if (!(await refuse(tag, ids.B))) return;
      const target = before === '5' ? '4' : '5';
      await app.setSigFigs(target); // the real select of the header
      await sleep(250);
      await app.shot('gridr2-sigfigs-after', { locator: '#details-panel' });
      const now = await sig.inputValue();
      const stored = await page.evaluate(() => localStorage.getItem('fta.sigFigs'));
      L.check(`${tag}: (setup) the sig. figs select changed from ${before} to ${target}`, now === target && now !== before && stored === target, { now, stored });
      await judge(tag, ids.C, 'h');
      await app.shot('gridr2-sigfigs-edited', { locator: '#details-panel' });
    } finally {
      if ((await sig.inputValue()) !== before) await app.setSigFigs(before);
    }
  });

  // ---- 6: a toggle in the column chooser ------------------------------------------------------------
  await phase('columns', async () => {
    const tag = 'gridr2 columns';
    const ids = await fresh();
    const TH = (col) => `${TID('grid-th')}[data-column="${col}"]`;
    const btn = page.locator(TID('grid-columns-button'));
    const box = page.locator(`${TID('grid-column-toggle')}[data-column="source"]`);
    try {
      if ((await page.locator(TH('source')).count()) !== 1) throw new Error('(setup) the source column is not shown at the start');
      if (!(await refuse(tag, ids.B))) return;
      await btn.click(); // the real Columns button of the toolbar
      const open = await until(async () => (await btn.getAttribute('aria-expanded')) === 'true' && (await box.count()) === 1, 3000);
      L.check(`${tag}: (setup) the Columns chooser opens with a source toggle`, Boolean(open));
      if (!open) return;
      await box.click(); // hide the source column
      await sleep(250);
      await app.shot('gridr2-columns-after', { locator: '#details-panel' });
      const gone = await until(async () => (await page.locator(TH('source')).count()) === 0, 2000);
      L.check(`${tag}: (setup) the source column header is gone and lambda is still there`, Boolean(gone) && (await page.locator(TH('lambda')).count()) === 1);
      if ((await btn.getAttribute('aria-expanded')) === 'true') await page.keyboard.press('Escape');
      await judge(tag, ids.C, 'h');
      await app.shot('gridr2-columns-edited', { locator: '#details-panel' });
    } finally {
      // show the column again and clear the stored choice, so later phases start from the default
      if ((await btn.count()) && (await page.locator(TH('source')).count()) === 0) {
        if ((await btn.getAttribute('aria-expanded')) !== 'true') await btn.click();
        if (await box.count()) await box.click();
        if ((await btn.getAttribute('aria-expanded')) === 'true') await page.keyboard.press('Escape');
      }
      await page.evaluate(() => localStorage.removeItem('fta.gridHidden'));
    }
  });

  const errs = app.errorsSince(0);
  L.check('no console errors in the gridr2 run', errs.length === 0, errs);
  await app.context.close();
  if (failures.length) L.info('phases that threw', failures);
}

L.runSection('gridr2', main);
