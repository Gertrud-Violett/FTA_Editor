// No stale values after undo / redo / open: every panel (visible or not)
// equals the server. node s_stale.js <url> <label> <root>
'use strict';
const L = require('./lib');
const { compareCore, flatten } = require('./b2b');

async function main(url, label, root) {
  L.setSection('stale[' + label + ']');
  const app = await L.openApp(url, { prefs: { 'fta.advanced': '1' }, viewport: { width: 1600, height: 1050 } });
  const { page } = app;
  await app.api('post', '/file/open', { path: L.coreFile(root, label) });
  await page.evaluate(() => window.ftaShell.refresh());
  let st = await app.api('get', '/state');
  const byName = (name) => flatten(st.tree).find((n) => n.name === name);
  const pb = byName('Pump B fails');

  // Quant tab visible: change the model through the form, then undo from the keyboard
  await app.selectTreeNode(pb.id);
  await app.clickTab('quant');
  await page.waitForSelector('#tabpanel-quant select[data-field="model"]');
  await page.locator('#tabpanel-quant select[data-field="model"]').selectOption('repairable');
  await page.waitForSelector('#tabpanel-quant input[data-field="mu"]');
  const lam = page.locator('#tabpanel-quant input[data-field="lambda"]');
  await lam.click();
  await page.keyboard.type('1e-4');
  await page.keyboard.press('Enter');
  const mttr = page.locator('#tabpanel-quant input[data-field="mttr"]');
  await mttr.click();
  await page.keyboard.type('24');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(800);
  let view = await app.api('get', '/nodes/' + pb.id);
  const readQ = () => page.evaluate(() => {
    const d = document.querySelector('#tabpanel-quant .anl-derived');
    const model = document.querySelector('#tabpanel-quant select[data-field="model"]');
    return { q: d ? d.querySelector('b').textContent : null, f: d ? d.querySelector('.anl-mono').textContent : null, model: model ? model.value : null };
  });
  let q = await readQ();
  L.check(`repairable: form q ${q.q} == quantDerived ${L.fmt(view.node.quantDerived.q, 3)}`, q.q === L.fmt(view.node.quantDerived.q, 3) && q.f === view.node.quantDerived.formula && q.model === 'repairable', { q, qd: view.node.quantDerived });
  await compareCore(app, 'repairable');
  // undo x3 (mttr, lambda, model) with focus on the tab strip
  await page.locator('#tab-quant').focus();
  for (let i = 0; i < 3; i += 1) { await page.keyboard.press('Control+Z'); await page.waitForTimeout(400); }
  await page.waitForTimeout(600);
  view = await app.api('get', '/nodes/' + pb.id);
  q = await readQ();
  const model = (view.node.quant && view.node.quant.model) || 'fixed';
  L.check(`after 3x Ctrl+Z: Quant form model ${q.model} == server ${model}, q == quantDerived`, q.model === model && q.q === L.fmt(view.node.quantDerived.q, 3), { q, model, qd: view.node.quantDerived });
  await compareCore(app, 'after 3x undo (quant)');
  // redo x3 with Ctrl+Y
  for (let i = 0; i < 3; i += 1) { await page.keyboard.press('Control+Y'); await page.waitForTimeout(400); }
  await page.waitForTimeout(600);
  view = await app.api('get', '/nodes/' + pb.id);
  q = await readQ();
  L.check('after 3x Ctrl+Y: Quant form back to repairable == server', q.model === 'repairable' && view.node.quant.model === 'repairable' && q.q === L.fmt(view.node.quantDerived.q, 3), { q, s: view.node.quant });
  await compareCore(app, 'after 3x redo (quant)');

  // Details fields follow an undo (not focused)
  await app.clickTab('details');
  await app.editDetailsField('Name', 'Pump B fails (renamed)', 'enter');
  await app.editDetailsField('Notes', 'a note', 'tab');
  await page.locator('#tab-details').focus();
  await page.keyboard.press('Control+Z');
  await page.keyboard.press('Control+Z');
  await page.waitForTimeout(700);
  st = await app.api('get', '/state');
  const det = await app.details();
  const pbNow = flatten(st.tree).find((n) => n.id === pb.id);
  L.check('Details name/notes after 2x undo == server', det.fields.Name.value === pbNow.name && det.fields.Notes.value === (pbNow.notes || ''), { det: det.fields, name: pbNow.name, notes: pbNow.notes });

  // title follows undo
  await page.locator('#title-input').click();
  await page.keyboard.press('Control+A');
  await page.keyboard.type('Temporary title');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
  await page.locator('#tab-details').focus();
  await page.keyboard.press('Control+Z');
  await page.waitForTimeout(600);
  st = await app.api('get', '/state');
  L.check('title input after undo == server title', (await page.locator('#title-input').inputValue()) === st.metadata.title && st.metadata.title === 'Cooling loss B2B', { gui: await page.locator('#title-input').inputValue(), srv: st.metadata.title });

  // Validation tab in the background: delete a linked node -> LINKS_REMOVED; badge & list
  const pa = byName('Pump A fails');
  await app.selectTreeNode(pa.id);
  await page.locator('.actionbar [data-action="delete"]').click();
  await page.locator('.fta-modal .fta-btn.is-primary').click();
  await page.waitForTimeout(1200);
  const val = await app.api('get', '/analysis/validate');
  const badge = await page.evaluate(() => { const b = document.querySelector('#tab-validation .tabstrip__badge'); return b && !b.hidden ? { n: b.textContent, kind: b.dataset.kind } : null; });
  const c = val.counts;
  const want = c.error ? { n: String(c.error), kind: 'error' } : c.warning ? { n: String(c.warning), kind: 'warn' } : null;
  L.check('after delete: Validation badge == API counts', JSON.stringify(badge) === JSON.stringify(want), { badge, want, codes: val.issues.map((i) => i.code) });
  const toastAction = page.locator('#toasts .toast__action');
  if (await toastAction.count()) await toastAction.first().click();
  else await app.clickTab('validation');
  await page.waitForTimeout(1200);
  const list = await page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-validation li.val-item')).map((li) => li.dataset.code));
  L.check('Validation list == API after delete (incl. LINKS_REMOVED)', JSON.stringify(list.slice().sort()) === JSON.stringify(val.issues.map((i) => i.code).sort()), { list, api: val.issues.map((i) => i.code) });
  // dismiss session notices: list and badge agree
  const dismiss = page.locator('#tabpanel-validation .val__dismiss');
  const dismissedMsgs = new Set();
  if (await dismiss.isVisible()) {
    for (const i of val.issues) if (i.code === 'LINKS_REMOVED' || i.code === 'LOAD_REPAIR') dismissedMsgs.add(i.message);
    await dismiss.click();
    await page.waitForTimeout(300);
    const shownWarn = await page.evaluate(() => document.querySelectorAll('#tabpanel-validation li.val-item--warning').length);
    const shownErr = await page.evaluate(() => document.querySelectorAll('#tabpanel-validation li.val-item--error').length);
    const b2 = await page.evaluate(() => { const b = document.querySelector('#tab-validation .tabstrip__badge'); return b && !b.hidden ? { n: b.textContent, kind: b.dataset.kind } : null; });
    const want2 = shownErr ? { n: String(shownErr), kind: 'error' } : shownWarn ? { n: String(shownWarn), kind: 'warn' } : null;
    L.check('after "Dismiss session notices": tab badge == what the list shows', JSON.stringify(b2) === JSON.stringify(want2), { b2, want2, shownWarn, shownErr });
  }
  await page.locator('#tab-validation').focus();
  await page.keyboard.press('Control+Z');
  await page.waitForTimeout(1500);
  await compareCore(app, 'after undo delete');
  const val3 = await app.api('get', '/analysis/validate');
  const list3 = await page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-validation li.val-item')).map((li) => li.dataset.code));
  const want3 = val3.issues.filter((i) => !dismissedMsgs.has(i.message)).map((i) => i.code).sort();
  L.check('undo delete: Validation list refreshed == API minus dismissed notices', JSON.stringify(list3.slice().sort()) === JSON.stringify(want3), { list3, want3, api: val3.issues.map((i) => i.code) });
  const b3 = await page.evaluate(() => { const b = document.querySelector('#tab-validation .tabstrip__badge'); return b && !b.hidden ? { n: b.textContent, kind: b.dataset.kind } : null; });
  L.check('undo delete: badge agrees with the list', (b3 === null) === (want3.length === 0), { b3, want3 });

  const errs = app.errorsSince(0);
  L.check('no console errors in the stale run', errs.length === 0, errs);
  await app.context.close();
}

L.runSection('stale', main);
