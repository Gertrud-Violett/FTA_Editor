// F2A T3 round 1: keyboard behaviour of the alpha editor in a real browser (BRIEF criterion 6, DESIGN 7.3 and 7.7).
// The reviewers' findings that s_ccf_alpha.js (protected) does not cover:
//   (a) the focus stays in the editor after Save (click and Enter), and stays in the field when Enter has nothing to save;
//   (b) Escape in an alpha field updates the sum line and the Save state at once, without a blur;
//   (c) Escape restores the last SAVED text, also after a valid blur that sent nothing;
//   (d) a PATCH response that arrives while an alpha field has the focus updates the status line, keeps the typed text and the focus;
//   (e) typed alpha text survives a repaint that changes only the testing scheme;
//   (f) removing a member of an alpha or a beta group takes its highlight away in the tree and the diagram.
//   node s_ccf_alpha_kbd.js <url> <label> <root>
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

function leaf(id, name) {
  return { id, name, type: 'Event', probability: 1e-3, logicGate: 'OR', notes: '', links: [], children: [] };
}

function documentText() {
  const tree = Object.assign(leaf('root', 'Cooling loss'), {
    type: 'Root', probability: 1.0, children: ['A', 'B', 'C'].map((id) => leaf(id, 'Valve ' + id)),
  });
  return JSON.stringify({ title: 'CCF alpha keyboard', date: '2026-11-02', mode: 'FTA', tree }, null, 2);
}

async function run(url, label, root) {
  L.setSection('ccf_alpha_kbd[' + label + ']');
  const file = 'ccf_alpha_kbd_' + label + '.json';
  fs.writeFileSync(path.join(root, file), documentText());
  const app = await L.openApp(url, { viewport: { width: 1600, height: 1000 }, prefs: { 'fta.advanced': '1' } });
  const { page } = app;
  page.setDefaultTimeout(5000);
  const reqs = [];
  page.on('request', (r) => {
    if (['POST', 'PATCH', 'DELETE'].includes(r.method()) && r.url().includes('/api/ccf/groups')) reqs.push({ method: r.method(), body: r.postDataJSON() });
  });
  const part = async (name, fn, cleanup) => {
    try { await fn(); } catch (e) { L.check(name + ': did not complete', false, String((e && e.message) || e).split('\n')[0].slice(0, 300)); }
    if (cleanup) { try { await cleanup(); } catch (_e) { /* best effort */ } }
  };
  const waitFor = async (fn, timeout) => {
    const t0 = Date.now();
    for (;;) {
      let v = false;
      try { v = await fn(); } catch (_e) { v = false; }
      if (v) return true;
      if (Date.now() - t0 > (timeout || 8000)) return false;
      await page.waitForTimeout(100);
    }
  };
  const group = async () => ((await app.api('get', '/ccf/groups')).groups || [])[0];
  const editor = page.locator('#tabpanel-ccf [data-section="editor"]');
  const state = () => page.evaluate(() => {
    const ed = document.querySelector('#tabpanel-ccf [data-section="editor"]');
    const txt = (e) => (e ? e.textContent.replace(/\s+/g, ' ').trim() : null);
    const save = ed.querySelector('button[data-role="alpha-save"]');
    const a = document.activeElement;
    return {
      alpha: [1, 2, 3].map((k) => (ed.querySelector('input[data-field="alpha' + k + '"]') || {}).value),
      sum: txt(ed.querySelector('p[data-role="alpha-sum"]')),
      saveInactive: save ? save.disabled || save.getAttribute('aria-disabled') === 'true' : null,
      status: txt(ed.querySelector('p[data-role="group-status"]')),
      focus: a && a !== document.body ? (a.dataset.field || a.dataset.role || a.tagName) : 'BODY',
      inEditor: Boolean(a) && ed.contains(a),
    };
  });
  const typeInto = async (field, value, key) => {
    const input = editor.locator('input[data-field="' + field + '"]');
    await input.click();
    await page.keyboard.press('Control+A');
    await page.keyboard.type(String(value), { delay: 3 });
    if (key) await page.keyboard.press(key);
    await page.waitForTimeout(150);
  };

  await part('setup', async () => {
    await app.api('post', '/new', { force: true });
    const opened = await app.api('post', '/file/open', { path: path.join(root, file), force: true });
    if (opened.__error) throw new Error('could not open ' + file);
    const made = await app.api('post', '/ccf/groups', { name: 'Keys', model: 'alpha', alpha: [0.955, 0.034, 0.011], testing: 'staggered', members: ['A', 'B', 'C'], source: '' });
    if (made.__error) throw new Error('could not create the group');
    await page.reload();
    await L.waitBoot(page);
    await app.waitDiagram();
    await app.clickTab('ccf');
    await page.waitForSelector('#tabpanel-ccf [data-role="groups"] tbody tr[data-id]');
    await page.locator('#tabpanel-ccf [data-role="groups"] tbody tr[data-id]').first().click();
    await editor.locator('input[data-field="alpha1"]').waitFor({ state: 'visible' });
    await page.waitForTimeout(300);
  });

  // ===== (b) and (c): Escape ==========================================================
  await part('Escape', async () => {
    await typeInto('alpha2', '0.5');
    let s = await state();
    L.check('(b) before Escape the sum line is red-state text and Save is active', /^Sum of α: 1\.466\./.test(s.sum) && s.saveInactive === false, s);
    await page.keyboard.press('Escape');
    s = await state();
    L.check('(b) Escape restores 0.034 in alpha2 at once', s.alpha[1] === '0.034', s);
    L.check('(b) ... the sum line reads "Sum of α: 1" at once (no blur)', s.sum === 'Sum of α: 1', s);
    L.check('(b) ... and Save is inactive again', s.saveInactive === true, s);
    await typeInto('alpha2', '0.05', 'Tab');
    s = await state();
    L.check('(c) a valid text left with Tab sends nothing and shows the read value', s.alpha[1] === '0.05' && s.saveInactive === false, s);
    await typeInto('alpha2', '0.07');
    await page.keyboard.press('Escape');
    s = await state();
    L.check('(c) Escape after that restores the SAVED text 0.034, not the blurred 0.05', s.alpha[1] === '0.034', s);
    L.check('(c) ... and the sum and Save follow at once', s.sum === 'Sum of α: 1' && s.saveInactive === true, s);
    L.check('(b, c) no request was sent', reqs.length === 0, reqs);
    await page.keyboard.press('Tab');
  });

  // ===== (a): focus after Save and Enter =================================================
  await part('focus after save', async () => {
    await typeInto('alpha1', '0.95', 'Tab');
    await typeInto('alpha2', '0.039', 'Tab');
    const n0 = reqs.length;
    await editor.locator('button[data-role="alpha-save"]').click();
    await waitFor(async () => JSON.stringify((await group()).alpha) === JSON.stringify([0.95, 0.039, 0.011]));
    await page.waitForTimeout(500);
    let s = await state();
    L.check('(a) one click on Save sends one PATCH', reqs.length === n0 + 1, reqs.slice(n0));
    L.check('(a) after the click the focus is on the Save button (not the page)', s.focus === 'alpha-save' && s.inEditor, s);
    L.check('(a) ... the editor shows the saved values and Save is inactive', s.alpha.join() === '0.95,0.039,0.011' && s.saveInactive === true, s);
    // Enter in alpha2 with a change: saves, focus on Save
    await typeInto('alpha1', '0.955', 'Tab');
    const n1 = reqs.length;
    await typeInto('alpha2', '0.034', 'Enter');
    await waitFor(async () => JSON.stringify((await group()).alpha) === JSON.stringify([0.955, 0.034, 0.011]));
    await page.waitForTimeout(500);
    s = await state();
    L.check('(a) Enter in alpha2 sends one PATCH with the whole list', reqs.length === n1 + 1 && reqs[n1].body.alpha.join() === '0.955,0.034,0.011', reqs.slice(n1));
    L.check('(a) after Enter the focus is on the Save button (not the page)', s.focus === 'alpha-save' && s.inEditor, s);
    // Enter with nothing to save: the focus stays in the field
    const n2 = reqs.length;
    await editor.locator('input[data-field="alpha1"]').click();
    await page.keyboard.press('Enter');
    await page.waitForTimeout(300);
    s = await state();
    L.check('(a) Enter with nothing to save sends nothing and keeps the focus in alpha1', reqs.length === n2 && s.focus === 'alpha1', { reqs: reqs.slice(n2), s });
  });

  // ===== (d) and (e): a response while an alpha field has the focus =======================
  await part('response while typing', async () => {
    await page.route('**/api/ccf/groups/*', async (route) => {
      if (route.request().method() === 'PATCH') await new Promise((resolve) => setTimeout(resolve, 900));
      await route.continue();
    });
    await typeInto('alpha1', '0.9', 'Tab');
    await editor.locator('select[data-field="testing"]').selectOption('');
    await typeInto('alpha2', '0.04');
    const typed = (await state()).alpha[1];
    await waitFor(async () => (await group()).testing === null);
    await page.waitForTimeout(500);
    const s = await state();
    L.check('(d) the PATCH answered while alpha2 had the focus: the status line now reads "Not applied: testing scheme missing"', s.status === 'Not applied: testing scheme missing', s);
    L.check('(d) ... the typed text and the focus are still in alpha2 (the editor was not rebuilt)', s.alpha[1] === typed && s.focus === 'alpha2', { typed, s });
    await page.keyboard.press('Tab');
    await page.waitForTimeout(300);
    const after = await state();
    L.check('(e) after leaving the field the typed alpha values (0.9, 0.04) are still shown', after.alpha[0] === '0.9' && after.alpha[1] === '0.04' && after.alpha[2] === '0.011', after);
    L.check('(e) ... and the testing select reads the stored (empty) scheme', await editor.locator('select[data-field="testing"]').inputValue() === '');
    await page.unroute('**/api/ccf/groups/*');
    // a scheme chosen on a calm editor keeps the typed values too (the repaint is a rebuild this time)
    await editor.locator('select[data-field="testing"]').focus(); // selectOption does not move the focus: a rebuild needs it off the inputs
    await editor.locator('select[data-field="testing"]').selectOption('nonStaggered');
    await waitFor(async () => (await group()).testing === 'nonStaggered');
    await page.waitForTimeout(500);
    const kept = await state();
    L.check('(e) after a rebuild caused by the scheme the typed values (0.9, 0.04) are kept', kept.alpha[0] === '0.9' && kept.alpha[1] === '0.04' && kept.focus === 'testing', kept);
    L.check('(e) ... and the stored alpha was not changed by it', JSON.stringify((await group()).alpha) === JSON.stringify([0.955, 0.034, 0.011]));
  }, async () => { try { await page.unroute('**/api/ccf/groups/*'); } catch (_e) { /* not routed */ } });

  // ===== (f): the highlight follows the members after one is removed (UI review F2A-ui-1 advice) ==========
  const marked = () => page.evaluate(() => ({
    tree: Array.from(document.querySelectorAll('#tree-root li.fta-tree-item.is-highlighted')).map((li) => li.dataset.id).sort(),
    diagram: Array.from(document.querySelectorAll('#diagram-root g.node.is-highlighted')).map((g) => ((g.querySelector('title') || {}).textContent || '').trim()).filter((t) => !/__(event|gate)$/.test(t)).length,
  }));
  for (const model of ['alpha', 'beta']) {
    await part('(f) highlight after removing a member [' + model + ']', async () => {
      const old = await group();
      if (old) await app.api('del', '/ccf/groups/' + old.id);
      const body = model === 'alpha'
        ? { name: 'Marks', model, alpha: [0.955, 0.034, 0.011], testing: 'staggered', members: ['A', 'B', 'C'], source: '' }
        : { name: 'Marks', model, beta: 0.1, members: ['A', 'B', 'C'], source: '' };
      const made = await app.api('post', '/ccf/groups', body);
      if (made.__error) throw new Error('could not create the ' + model + ' group');
      await page.reload();
      await L.waitBoot(page);
      await app.waitDiagram();
      await app.clickTab('ccf');
      await page.waitForSelector('#tabpanel-ccf [data-role="groups"] tbody tr[data-id]');
      await page.locator('#tabpanel-ccf [data-role="groups"] tbody tr[data-id]').first().click();
      await editor.locator('li[data-member="B"] button[data-role="remove-member"]').waitFor({ state: 'visible' });
      await page.waitForTimeout(500);
      let m = await marked();
      L.check('(f) ' + model + ': selecting the group highlights its 3 members (A, B, C) in the tree and the diagram', m.tree.join() === 'A,B,C' && m.diagram === 3, m);
      await editor.locator('li[data-member="B"] button[data-role="remove-member"]').click();
      await waitFor(async () => (await group()).members.length === 2);
      await page.waitForTimeout(600);
      m = await marked();
      L.check('(f) ' + model + ': after removing B its highlight is gone and A and C keep theirs (tree and diagram)', m.tree.join() === 'A,C' && m.diagram === 2, m);
      await editor.locator('li[data-member="A"] button[data-role="remove-member"]').click();
      await waitFor(async () => (await group()).members.length === 1);
      await page.waitForTimeout(600);
      m = await marked();
      L.check('(f) ' + model + ': after removing A as well only C is highlighted', m.tree.join() === 'C' && m.diagram === 1, m);
    });
  }

  const errs = app.errorsSince(0, []);
  L.check('whole run: no console errors, page errors or failed /api requests', errs.length === 0, errs.slice(0, 5));
  await app.context.close();
}

L.runSection('ccf_alpha_kbd', run);
