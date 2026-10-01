// More B2B: hide zero, λ units, document defaults, headline marker, RRW ∞,
// trace filters, Escape in the top bar, stale checks after undo/new.
// node s_more.js <url> <label> <root>
'use strict';
const L = require('./lib');
const { compareCore, flatten } = require('./b2b');

async function main(url, label, root) {
  L.setSection('more[' + label + ']');
  const app = await L.openApp(url, { prefs: { 'fta.advanced': '1' }, viewport: { width: 1600, height: 1050 } });
  const { page } = app;
  await app.api('post', '/file/open', { path: L.coreFile(root, label) });
  await page.evaluate(() => window.ftaShell.refresh());
  let st = await app.api('get', '/state');
  const byName = (name) => flatten(st.tree).find((n) => n.name === name);

  // ---- Escape in the title box discards typing ----------------------------------------
  await page.locator('#title-input').click();
  await page.keyboard.press('Control+A');
  await page.keyboard.type('Typo title');
  await page.keyboard.press('Escape');
  await page.locator('#tree-root .fta-tree-search').click(); // blur
  await page.waitForTimeout(400);
  st = await app.api('get', '/state');
  L.check('title: Escape restores the stored title (nothing committed)', st.metadata.title === 'Cooling loss B2B' && (await page.locator('#title-input').inputValue()) === 'Cooling loss B2B', st.metadata.title);

  // ---- Hide Zero: a zero-probability event disappears from tree and diagram ----------------
  const zero = (await app.api('post', '/nodes', { parentId: byName('Power loss').id, name: 'Impossible event', probability: 0 })).nodeId;
  await page.evaluate(() => window.ftaShell.refresh());
  st = await app.api('get', '/state');
  L.check('server flags the zero node', (st.zeroNodes || []).map(String).includes(String(zero)), st.zeroNodes);
  await page.locator('#hide-zero').click();
  await app.waitDiagram();
  const hz = await page.evaluate((id) => ({
    tree: !!document.querySelector('#tree-root li.fta-tree-item[data-id="' + id + '"]') && document.querySelector('#tree-root li.fta-tree-item[data-id="' + id + '"]').offsetParent !== null,
    diagramTexts: Array.from(document.querySelectorAll('#diagram-root svg text')).map((t) => t.textContent).join('|'),
  }), zero);
  L.check('Hide Zero hides the zero node in the tree', !hz.tree, hz.tree);
  L.check('Hide Zero hides it in the diagram', !/Impossible event/.test(hz.diagramTexts));
  await compareCore(app, 'hide zero on');
  await page.locator('#hide-zero').click();
  await app.waitDiagram();
  await compareCore(app, 'hide zero off');
  await app.api('del', '/nodes/' + zero);
  await page.evaluate(() => window.ftaShell.refresh());
  st = await app.api('get', '/state');

  // ---- λ unit display on the Quant tab ---------------------------------------------------
  const pcId = byName('Pump C fails').id;
  await app.api('patch', '/nodes/' + pcId, { quant: { model: 'rate', lambda: 5e-6 } });
  await page.evaluate(() => window.ftaShell.refresh());
  await app.selectTreeNode(pcId);
  await app.clickTab('quant');
  await page.waitForSelector('#tabpanel-quant input[data-field="lambda"]');
  for (const [unit, factor] of [['h', 1], ['y', 8760], ['FIT', 1e9]]) {
    await page.locator('#tabpanel-quant select[data-field="lambdaUnit"]').selectOption(unit);
    await page.waitForTimeout(300);
    const shown = await page.locator('#tabpanel-quant input[data-field="lambda"]').inputValue();
    const row = await page.evaluate((id) => { const tr = document.querySelector('#tabpanel-quant [data-section="events"] tbody tr[data-id="' + id + '"]'); return tr ? tr.children[2].textContent : null; }, pcId);
    const want = 5e-6 * factor;
    L.check(`λ shown in ${unit}: field ${shown}, table ${row} == 5e-6/h × ${factor}`, Math.abs(Number(shown) - want) / want < 1e-9 && Math.abs(Number(row) - want) / want < 1e-9, { shown, row, want });
  }
  await page.locator('#tabpanel-quant select[data-field="lambdaUnit"]').selectOption('h');
  // standby model fields
  await page.locator('#tabpanel-quant select[data-field="model"]').selectOption('standby');
  await page.waitForSelector('#tabpanel-quant input[data-field="tau"]');
  const tau = page.locator('#tabpanel-quant input[data-field="tau"]');
  await tau.click();
  await page.keyboard.type('720');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(700);
  const view = await app.api('get', '/nodes/' + pcId);
  const d = await page.evaluate(() => { const x = document.querySelector('#tabpanel-quant .anl-derived'); return { q: x.querySelector('b').textContent, f: x.querySelector('.anl-mono').textContent }; });
  L.check(`standby: derived q ${d.q} / formula == quantDerived`, d.q === L.fmt(view.node.quantDerived.q, 3) && d.f === view.node.quantDerived.formula, { d, qd: view.node.quantDerived });
  await compareCore(app, 'standby model');

  // ---- Cut sets: save document defaults; truncation shows on the headline marker -----------
  await app.clickTab('cutsets');
  await page.waitForSelector('#tabpanel-cutsets tbody tr');
  const ord = page.locator('#tabpanel-cutsets input[data-limit="maxOrder"]');
  await ord.click();
  await page.keyboard.type('1');
  await page.locator('#tabpanel-cutsets button[data-role="save-defaults"]').click();
  await page.waitForTimeout(800);
  st = await app.api('get', '/state');
  L.check('Save as document defaults stored maxOrder 1', st.analysis.cutsets.maxOrder === 1, st.analysis.cutsets);
  await page.locator('#tabpanel-cutsets button[data-role="run"]').click();
  await page.waitForTimeout(1200);
  const cs = await app.api('post', '/analysis/cutsets', { limit: 500 });
  const badge = await page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-cutsets .anl-summary .anl-badge')).map((b) => b.textContent));
  L.check(`truncated badge shown iff API truncated (${cs.truncated})`, badge.some((b) => /truncated/i.test(b)) === Boolean(cs.truncated), { badge, t: cs.truncated, by: cs.truncatedBy });
  const rowsN = await page.evaluate(() => document.querySelectorAll('#tabpanel-cutsets tbody tr').length);
  L.check('rows with maxOrder 1 == API', rowsN === cs.returned, { rowsN, r: cs.returned });
  await page.waitForTimeout(800);
  const summary = await app.api('get', '/analysis/summary');
  const head = await app.headline();
  const wantMarker = summary.headlineMethod === 'mcub' && (summary.truncatedBy || []).some((b) => b !== 'time' && b !== 'error');
  L.check(`headline ≈ marker ${head.marker} == summary (method ${summary.headlineMethod}, truncatedBy ${JSON.stringify(summary.truncatedBy)})`, head.marker === wantMarker, { head, summary: { m: summary.headlineMethod, t: summary.truncated, by: summary.truncatedBy, capped: summary.capped } });
  await compareCore(app, 'maxOrder 1');
  // undo the defaults with Ctrl+Z from the tab strip: inputs follow the document again
  await page.locator('#tab-cutsets').focus();
  await page.keyboard.press('Control+Z');
  await page.waitForTimeout(1200);
  st = await app.api('get', '/state');
  const ordNow = await ord.inputValue();
  L.check('Ctrl+Z restores maxOrder and the input follows', String(st.analysis.cutsets.maxOrder) === ordNow && st.analysis.cutsets.maxOrder !== 1, { ordNow, doc: st.analysis.cutsets });

  // ---- Uncertainty: save defaults ------------------------------------------------------
  await app.clickTab('uncertainty');
  const nIn = page.locator('#tabpanel-uncertainty input[data-field="n"]');
  await nIn.click();
  await page.keyboard.type('2500');
  const seedIn = page.locator('#tabpanel-uncertainty input[data-field="seed"]');
  await seedIn.click();
  await page.keyboard.type('7');
  await page.locator('#tabpanel-uncertainty button[data-role="save-defaults"]').click();
  await page.waitForTimeout(700);
  st = await app.api('get', '/state');
  L.check('Uncertainty defaults stored (n 2500, seed 7)', st.analysis.mc.n === 2500 && st.analysis.mc.seed === 7, st.analysis.mc);

  // ---- Importance: RRW ∞ for a single-point failure ------------------------------------------
  await app.clickTab('importance');
  await page.waitForSelector('#tabpanel-importance tbody tr');
  await page.waitForTimeout(600);
  const imp = await app.api('post', '/analysis/importance', {});
  const inf = imp.events.filter((e) => e.rrwInfinite).map((e) => e.id);
  const guiInf = await page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-importance tbody tr')).filter((tr) => tr.children[5].textContent === '∞').map((tr) => tr.dataset.id));
  L.check(`RRW ∞ rows == API rrwInfinite (${inf.length})`, JSON.stringify(guiInf.sort()) === JSON.stringify(inf.sort()), { guiInf, inf });

  // ---- New with the FV overlay on: no colour left over; background tabs reset ----------------
  const box = page.locator('#tabpanel-importance input[data-role="fv-overlay"]');
  if (!(await box.isChecked())) await box.click();
  await page.waitForTimeout(400);
  await page.keyboard.press('Alt+N');
  await page.waitForTimeout(400);
  if (await page.locator('.fta-modal').count()) await page.locator('.fta-modal .fta-btn.is-primary').click();
  await page.waitForTimeout(1500);
  const after = await page.evaluate(async () => {
    const { store } = await import('/static/js/store.js');
    return {
      overlay: store.overlay,
      rows: document.querySelectorAll('#tabpanel-importance tbody tr').length,
      colored: document.querySelectorAll('#diagram-root svg g.has-overlay').length,
    };
  });
  const impNew = await app.api('post', '/analysis/importance', {});
  const wantVals = {};
  for (const e of impNew.events) if (e.fv !== null && e.fv !== undefined) wantVals[e.id] = e.fv;
  L.check('New: importance re-ran on the new doc (rows and FV colours == API, nothing stale)', after.rows === impNew.events.length && JSON.stringify(after.overlay && after.overlay.values) === JSON.stringify(wantVals), { after, api: impNew.events });
  await app.clickTab('cutsets');
  await page.waitForTimeout(1200);
  const csRows = await page.evaluate(() => document.querySelectorAll('#tabpanel-cutsets tbody tr').length);
  const cs0 = await app.api('post', '/analysis/cutsets', { limit: 500 });
  L.check('New: Cut Sets tab shows the new document (no old rows)', csRows === cs0.returned, { csRows, api: cs0.returned });
  await app.clickTab('trace');
  await page.waitForTimeout(400);
  const trRows = await page.evaluate(() => document.querySelectorAll('#tabpanel-trace tbody tr').length);
  L.check('New: Traceability shows one row (the root)', trRows === 1, trRows);
  await compareCore(app, 'after New');
  // undo is not possible after New (history reset) -> info toast, no error
  const m = app.errMark();
  await page.locator('#tab-trace').focus();
  await page.keyboard.press('Control+Z');
  await page.waitForTimeout(500);
  const toasts = await page.evaluate(() => Array.from(document.querySelectorAll('#toasts .toast')).map((t) => t.className + ':' + t.textContent));
  L.info('Ctrl+Z right after New', toasts.slice(-1));
  L.check('Ctrl+Z with nothing to undo: no console error', app.errorsSince(m).filter((e) => e.type !== 'http').length === 0, app.errorsSince(m));

  const errs = app.errorsSince(0).filter((e) => !(e.type === 'http' || /409 \(CONFLICT\)/.test(e.text)));
  L.check('no console errors in the more run (apart from the provoked nothing-to-undo)', errs.length === 0, errs);
  L.info('http errors in the more run', app.errorsSince(0).filter((e) => e.type === 'http').map((e) => e.text.slice(0, 140)));
  await app.context.close();
}

L.runSection('more', main);
