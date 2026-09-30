// Core GUI flow, built entirely through the GUI, compared with the API after
// every action. node s_core.js <url> <label>   (writes core_<label>.json)
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');
const { compareCore } = require('./b2b');

async function main(url, label) {
  L.setSection('core[' + label + ']');
  const app = await L.openApp(url, { viewport: { width: 1600, height: 1000 } });
  const { page } = app;
  const snaps = [];
  const cmp = async (name, opts) => { const r = await compareCore(app, name, opts); snaps.push(r.snap); return r; };

  // ---- basic mode audit --------------------------------------------------------
  const tabs = await page.evaluate(() => Array.from(document.querySelectorAll('#bottom-tabs [role=tab]')).filter((b) => b.offsetParent !== null).map((b) => b.dataset.tab));
  L.check('default is basic: only Details + Validation tabs', JSON.stringify(tabs) === '["details","validation"]', tabs);

  // New through the button (confirm if the server says unsaved)
  await page.locator('.actionbar [data-action="new"]').click();
  await page.waitForTimeout(400);
  if (await page.locator('.fta-modal').count()) await page.locator('.fta-modal .fta-btn.is-primary').click();
  await page.waitForTimeout(500);
  let st = await app.api('get', '/state');
  L.check('New: server tree has one node', (st.tree.children || []).length === 0, st.tree);
  L.check('New: root selected in GUI', (await app.selectedId()) === String(st.tree.id));
  await cmp('after New');

  // Title + date through the top bar (type + Enter)
  await page.locator('#title-input').click();
  await page.keyboard.press('Control+A');
  await page.keyboard.type('Cooling loss B2B');
  await page.keyboard.press('Enter');
  await page.locator('#date-input').click();
  await page.keyboard.press('Control+A');
  await page.keyboard.type('2026-09-29');
  await page.keyboard.press('Tab');
  await page.waitForTimeout(500);
  st = await app.api('get', '/state');
  L.check('title/date committed to server', st.metadata.title === 'Cooling loss B2B' && st.metadata.date === '2026-09-29', st.metadata);

  // Rename root through Details (Enter)
  await app.selectTreeNode(st.tree.id);
  await app.editDetailsField('Name', 'Loss of cooling', 'enter');
  st = await app.api('get', '/state');
  L.check('Details rename root committed', st.tree.name === 'Loss of cooling', st.tree.name);

  // Gate select offers AND/OR only in basic mode
  const opts = await page.locator('#details-root .fta-details-form select').first().evaluate((s) => Array.from(s.options).map((o) => o.value));
  L.check('basic: Details gate select offers AND/OR only', JSON.stringify(opts) === '["AND","OR"]', opts);

  // Build: root(OR) -> Pumps fail(AND){Pump A .01, Pump B .02}, Power loss(OR){Grid 1e-3, Diesel .05}, Operator error 3e-3
  const ids = {};
  const rootId = String(st.tree.id);
  await app.selectTreeNode(rootId);
  ids.pumps = await app.addViaDialog({ name: 'Pumps fail', probability: '1.0', gate: 'AND' });
  await cmp('add Pumps fail');
  ids.pa = await app.addViaDialog({ name: 'Pump A fails', probability: '0.01' });
  await app.selectTreeNode(ids.pumps);
  ids.pb = await app.addViaDialog({ name: 'Pump B fails', probability: '0.02', useKeyboard: true });
  await cmp('add Pump B (keyboard Ctrl+A / Enter)');
  await app.selectTreeNode(rootId);
  ids.power = await app.addViaDialog({ name: 'Power loss', probability: '1' });
  ids.grid = await app.addViaDialog({ name: 'Grid failure', probability: '1e-3' });
  await app.selectTreeNode(ids.power);
  ids.diesel = await app.addViaDialog({ name: 'Diesel fails', probability: '0.05' });
  await app.selectTreeNode(rootId);
  ids.op = await app.addViaDialog({ name: 'Operator error', probability: '3e-3', notes: 'HEP from THERP' });
  let r = await cmp('tree built via Add dialog');
  const nodeIds = r.st.tree.children.map((c) => c.name);
  L.check('server tree shape == GUI build', JSON.stringify(nodeIds) === '["Pumps fail","Power loss","Operator error"]', nodeIds);

  // Details probability edit (Tab to commit)
  await app.selectTreeNode(ids.pa);
  await app.editDetailsField('Probability (base)', '0.015', 'tab');
  r = await cmp('edit Pump A q=0.015 (Tab)');
  L.check('Pump A probability stored as 0.015', r.st.tree.children[0].children[0].probability === 0.015, r.st.tree.children[0].children[0]);

  // invalid probability shows an error and is not sent
  const before = (await app.api('get', '/state')).tree;
  await app.editDetailsField('Probability (base)', '1.5', 'enter');
  const err = await page.locator('#details-root .fta-field-error:not([hidden])').count();
  const after = (await app.api('get', '/state')).tree;
  L.check('invalid probability 1.5: field error shown, nothing sent', err > 0 && JSON.stringify(before) === JSON.stringify(after), { err });
  // Escape (with the caret back in the field) reverts the box
  await page.locator('#details-root .fta-details-form .fta-field').filter({ has: page.locator('label', { hasText: 'Probability (base)' }) }).locator('input').click();
  await page.keyboard.press('Escape');
  const pv = await page.evaluate(() => {
    const f = Array.from(document.querySelectorAll('#details-root .fta-details-form .fta-field')).find((x) => /Probability \(base\)/.test(x.textContent));
    return f.querySelector('input').value;
  });
  L.check('Escape reverts the Details field to the stored value', pv === '0.015', pv);

  // gate change through Details select: Power loss OR -> AND
  await app.selectTreeNode(ids.power);
  await app.selectDetailsGate('AND');
  r = await cmp('Power loss gate OR->AND (Details select)');

  // Undo / redo through the keyboard (focus on the tree, not a field)
  await page.locator('#tree-root li.fta-tree-item[data-id="' + ids.power + '"] > .fta-tree-row').click();
  await page.keyboard.press('Control+Z');
  r = await cmp('Ctrl+Z (gate back to OR)');
  const pw = r.st.tree.children[1];
  L.check('undo restored OR on Power loss', (pw.logicGate || 'OR') === 'OR', pw.logicGate);
  await page.keyboard.press('Control+Y');
  r = await cmp('Ctrl+Y (gate AND again)');
  L.check('redo restored AND on Power loss', r.st.tree.children[1].logicGate === 'AND', r.st.tree.children[1].logicGate);
  // toolbar buttons
  await page.locator('#btn-undo').click();
  r = await cmp('undo button');
  await page.locator('#btn-redo').click();
  r = await cmp('redo button');

  // ---- sig figs 1..6 ------------------------------------------------------------
  await app.selectTreeNode(ids.pumps);
  for (const n of [1, 2, 4, 5, 6, 3]) {
    await app.setSigFigs(n);
    await cmp('sig figs ' + n);
  }

  // ---- switching to Advanced mid-edit ----------------------------------------------
  await app.selectTreeNode(ids.op);
  const probField = page.locator('#details-root .fta-details-form .fta-field').filter({ has: page.locator('label', { hasText: 'Probability (base)' }) }).locator('input');
  await probField.click();
  await page.keyboard.press('Control+A');
  await page.keyboard.type('0.004');
  await page.locator('label.switch').click(); // mid-edit: focus leaves the field
  await page.waitForTimeout(600);
  st = await app.api('get', '/state');
  L.check('Advanced switched mid-edit: typed value committed (blur)', st.tree.children[2].probability === 0.004, st.tree.children[2].probability);
  const tabs2 = await page.evaluate(() => Array.from(document.querySelectorAll('#bottom-tabs [role=tab]')).filter((b) => b.offsetParent !== null).map((b) => b.dataset.tab));
  L.check('advanced: all 9 tabs', tabs2.length === 9, tabs2);
  r = await cmp('advanced on');

  // Advanced: gate select offers all types; make Pumps a 2oo3 vote via Add + Details
  await app.selectTreeNode(ids.pumps);
  ids.pc = await app.addViaDialog({ name: 'Pump C fails', probability: '0.03' });
  await app.selectTreeNode(ids.pumps);
  await app.selectDetailsGate('KOFN');
  await page.waitForTimeout(400);
  const kval = await page.evaluate(() => {
    const k = document.querySelector('#details-root .fta-details-extras input[type=number]');
    return k ? { v: k.value, hidden: !!k.closest('[hidden]') } : null;
  });
  L.check('KOFN seeds k = majority (2 of 3) and shows the k box', kval && kval.v === '2' && !kval.hidden, kval);
  r = await cmp('Pumps -> 2oo3 (KOFN)');

  // repeated event through a link -> MCUB headline
  await app.selectTreeNode(ids.diesel);
  // links editor: search + add
  const linkSearch = page.locator('#details-root .fta-links input[type="search"], #details-root .fta-links input[type="text"]').first();
  await linkSearch.click();
  await linkSearch.type('Pump A', { delay: 5 });
  await page.waitForTimeout(400);
  const linkOpts = page.locator('#details-root .fta-links select').first();
  const optVals = await linkOpts.evaluate((s) => Array.from(s.options).map((o) => o.value + '|' + o.textContent));
  info('link candidates', optVals);
  if (await linkOpts.count()) {
    const target = optVals.find((v) => v.startsWith(ids.pa + '|'));
    if (target) await linkOpts.selectOption(ids.pa);
    await page.locator('#details-root .fta-links .fta-links-buttons button').first().click();
    await page.waitForTimeout(700);
  }
  st = await app.api('get', '/state');
  const dz = st.tree.children[1].children[1];
  L.check('link added through Details links editor', Array.isArray(dz.links) && dz.links.some((l) => l.target_id === ids.pa), dz.links);
  r = await cmp('with a link (repeated event)');
  info('summary method', { m: r.summary.headlineMethod, rep: r.summary.repeatedEvents, h: r.summary.headline, tw: r.summary.treeWalk });

  // ---- save as through the file dialog, new, open ------------------------------------
  await page.keyboard.press('Control+Shift+S');
  await page.locator('.fta-filedialog').waitFor({ state: 'visible' });
  const nameBox = page.locator('.fta-filedialog .fdlg-name');
  await nameBox.fill('b2b_core_' + label + '.json');
  await page.locator('.fta-filedialog .fta-btn.is-primary').click();
  await page.waitForTimeout(800);
  const replaceBtn = page.getByRole('button', { name: 'Replace' });
  if (await replaceBtn.count()) await replaceBtn.click(); // overwrite an earlier run's file
  await page.waitForTimeout(800);
  st = await app.api('get', '/state');
  L.check('Save As: server has a path and is clean', /b2b_core_/.test(st.currentPath || '') && !st.dirty, { p: st.currentPath, d: st.dirty });
  const dirtyTxt = await page.locator('#dirty-text').textContent();
  L.check('dirty badge says Saved after Save As', /Saved/.test(dirtyTxt), dirtyTxt);
  const savedTree = JSON.stringify(st.tree);
  const savedSummary = await app.api('get', '/analysis/summary');

  // edit then Ctrl+S (caret still in Details name)
  await app.selectTreeNode(ids.op);
  const nameField = page.locator('#details-root .fta-details-form .fta-field').filter({ has: page.locator('label', { hasText: 'Name' }) }).locator('input');
  await nameField.click();
  await page.keyboard.press('Control+A');
  await page.keyboard.type('Operator error (late)');
  await page.keyboard.press('Control+S');
  await page.waitForTimeout(900);
  st = await app.api('get', '/state');
  L.check('Ctrl+S with caret in Details saves the typed name', st.tree.children[2].name === 'Operator error (late)' && !st.dirty, { n: st.tree.children[2].name, d: st.dirty });

  // New (unsaved -> none, as it was just saved)
  await page.locator('.actionbar [data-action="new"]').click();
  await page.waitForTimeout(500);
  if (await page.locator('.fta-modal').count()) await page.locator('.fta-modal .fta-btn.is-primary').click();
  await page.waitForTimeout(600);
  await cmp('New after save');
  // stale everywhere? headline must be root 1.00
  // open through the Load button + file dialog (double-click the row)
  await page.locator('.actionbar [data-action="load"]').click();
  await page.locator('.fta-filedialog').waitFor({ state: 'visible' });
  await page.waitForTimeout(400);
  const row = page.locator('.fta-filedialog .fdlg-row', { hasText: 'b2b_core_' + label + '.json' });
  await row.dblclick();
  await page.waitForTimeout(1000);
  st = await app.api('get', '/state');
  L.check('Open: server loaded the saved file', /b2b_core_/.test(st.currentPath || '') && st.tree.children.length === 3, st.currentPath);
  await app.selectTreeNode(ids.pumps);
  r = await cmp('after Open');
  L.check('Open: summary equals the saved document summary (except edited name)', r.summary.headline === savedSummary.headline, { now: r.summary.headline, saved: savedSummary.headline });
  void savedTree;
  const titleNow = await page.locator('#title-input').inputValue();
  L.check('Open: title input shows the file title', titleNow === 'Cooling loss B2B', titleNow);

  // screenshot
  await app.shot('core_' + label);
  const errs = app.errorsSince(0);
  L.check('no console errors/warnings in the core flow', errs.length === 0, errs);
  fs.writeFileSync(path.join(L.OUT, 'core_' + label + '.json'), JSON.stringify({ ids, snaps }, null, 1));
  await app.context.close();
}

function info(m, x) { L.info(m, x); }

L.runSection('core', main);
