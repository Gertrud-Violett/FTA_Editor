// The editing flow (usability batch 1), with real mouse and keyboard input:
// adding several nodes in a row, the required probability and the number
// forms it reads, the first-child warning, double-click, Ctrl+Z from a
// dropdown, Edit, delete confirmations, search, tree state per file, and the
// diagram's click / zoom / jump.   node s_ux1.js <url> <label> <root>
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

/** A document file: root -> `branches` gates of two leaves each, plus `leaves` leaves. */
function treeFile(title, branches, leaves) {
  const children = [];
  for (let b = 0; b < branches; b += 1) {
    children.push({
      id: 'root_' + b, name: title + ' branch ' + b, type: 'Event', probability: 1.0, logicGate: 'OR', notes: '', links: [],
      children: [0, 1].map((k) => ({ id: 'root_' + b + '_' + k, name: title + ' leaf ' + b + '.' + k, type: 'Event', probability: 0.01, logicGate: 'OR', notes: '', links: [], children: [] })),
    });
  }
  for (let i = 0; i < leaves; i += 1) {
    const n = branches + i;
    children.push({ id: 'root_' + n, name: title + ' event ' + n, type: 'Event', probability: 0.001, logicGate: 'OR', notes: '', links: [], children: [] });
  }
  return JSON.stringify({ title, date: '2026-10-12', mode: 'FTA', tree: { id: 'root', name: title + ' top', type: 'Root', probability: 1.0, logicGate: 'OR', notes: '', links: [], children } });
}

async function run(url, label, root) {
  L.setSection('ux1[' + label + ']');
  const fileA = 'ux1_a_' + label + '.json';
  const fileB = 'ux1_b_' + label + '.json';
  const fileLong = 'ux1_long_' + label + '.json';
  fs.writeFileSync(path.join(root, fileA), treeFile('Alpha', 2, 1));
  fs.writeFileSync(path.join(root, fileB), treeFile('Beta', 2, 1));
  fs.writeFileSync(path.join(root, fileLong), treeFile('Long', 1, 44));

  const app = await L.openApp(url, { viewport: { width: 1600, height: 1000 } });
  const { page } = app;

  const toasts = () => page.evaluate(() => Array.from(document.querySelectorAll('#toasts .toast__body')).map((t) => t.textContent));
  const clearToasts = () => page.evaluate(() => document.getElementById('toasts').replaceChildren());
  const tree = async () => (await app.api('get', '/state')).tree;
  const row = (id) => page.locator('#tree-root li.fta-tree-item[data-id="' + id + '"] > .fta-tree-row');
  const expandedAttr = (id) => page.getAttribute('#tree-root li.fta-tree-item[data-id="' + id + '"]', 'aria-expanded');
  const focusInfo = () => page.evaluate(() => {
    const a = document.activeElement;
    return { tag: a.tagName, cls: a.className, id: a.dataset ? a.dataset.id || null : null, text: (a.textContent || '').trim().slice(0, 40), inputmode: a.getAttribute('inputmode') };
  });
  const freshDoc = async () => {
    await app.api('post', '/new', { force: true });
    await page.reload();
    await L.waitBoot(page);
    await app.waitDiagram();
  };
  const openFile = async (name) => {
    await page.locator('.actionbar [data-action="load"]').click();
    await page.locator('.fta-filedialog').waitFor({ state: 'visible' });
    await page.waitForTimeout(400);
    await page.locator('.fta-filedialog .fdlg-row', { hasText: name }).dblclick();
    await page.locator('.fta-filedialog').waitFor({ state: 'detached' });
    await page.waitForTimeout(600);
    await app.waitDiagram();
  };
  const probBox = () => page.locator('#details-root .fta-details-form input[inputmode="decimal"]');

  // ---- start-up: the top event is selected ---------------------------------------------
  await freshDoc();
  let st = await app.api('get', '/state');
  const rootId = String(st.tree.id);
  L.check('start-up: the top event is selected', (await app.selectedId()) === rootId, await app.selectedId());
  L.check('start-up: Details shows the top event, not "select a node"', (await app.details()).id === rootId && await page.locator('#details-root .fta-details-form').isVisible());
  L.check('tab title of an unsaved, unchanged document', (await page.title()) === 'Untitled - FTA Editor', await page.title());
  const bar0 = await page.evaluate(() => ({ h: document.querySelector('.topbar').getBoundingClientRect().height, pill: document.getElementById('dirty').getBoundingClientRect().width }));

  // ---- the Add dialog -------------------------------------------------------------------
  await page.locator('.actionbar [data-action="add"]').click();
  const modal = page.locator('.fta-modal');
  await modal.waitFor({ state: 'visible' });
  const pIn = modal.locator('input[inputmode="decimal"]');
  L.check('Add: the title names the parent', /RootEvent/.test(await modal.locator('.fta-modal-title').textContent()), await modal.locator('.fta-modal-title').textContent());
  L.check('Add: the probability starts empty and is required', (await pIn.inputValue()) === '' && (await pIn.getAttribute('aria-required')) === 'true', await pIn.inputValue());
  await page.keyboard.type('First');
  await page.keyboard.press('Enter');
  L.check('Add: Enter in Name moves to the empty Probability box', (await focusInfo()).inputmode === 'decimal' && await modal.count() === 1, await focusInfo());
  await page.keyboard.press('Enter');
  const required = await modal.locator('.fta-field-error:not([hidden])').allTextContents();
  L.check('Add: Enter with no probability says it is required and makes nothing',
    required.length === 1 && /probability/i.test(required[0]) && ((await tree()).children || []).length === 0, required);
  await page.keyboard.type('5%');
  L.check('Add: the complaint goes as soon as the box is typed in', await modal.locator('.fta-field-error:not([hidden])').count() === 0);
  await page.keyboard.press('Tab');
  L.check('Add: "5%" is shown as 0.05 on leaving the box', (await pIn.inputValue()) === '0.05', await pIn.inputValue());
  await page.keyboard.press('Control+Enter');
  await page.waitForFunction(() => { const n = document.querySelector('.fta-modal .fta-dialog-note[role="status"]'); return n && !n.hidden; }, null, { timeout: 5000 });
  const afterAnother = { open: await modal.count(), note: await modal.locator(".fta-dialog-note[role=\"status\"]").textContent(), name: await modal.locator('.fta-field input').nth(0).inputValue(), prob: await pIn.inputValue(), focus: await focusInfo() };
  L.check('Add: Ctrl+Enter makes the node and keeps the dialog open, cleared, caret in Name',
    afterAnother.open === 1 && /First/.test(afterAnother.note) && afterAnother.name === '' && afterAnother.prob === '' && afterAnother.focus.tag === 'INPUT' && afterAnother.focus.inputmode === null, afterAnother);
  L.check('Add: the node made by Ctrl+Enter is already in the tree behind the dialog', await row('root_0').count() === 1);
  await page.keyboard.type('Second');
  await pIn.fill('０．２'); // full-width digits and point
  await modal.locator('.fta-modal-footer [data-role="add-another"]').waitFor({ state: 'visible' });
  await modal.locator('.fta-modal-footer .fta-btn.is-primary').click();
  await modal.waitFor({ state: 'detached' });
  await page.waitForTimeout(400);
  // twice more, one dialog each: the second must not nest under the first
  const third = await app.addViaDialog({ name: 'Third', probability: '1/1000' });
  const fourth = await app.addViaDialog({ name: 'Fourth', probability: '0,25', useKeyboard: true });
  st = await app.api('get', '/state');
  const kids = st.tree.children.map((c) => [c.name, c.probability, (c.children || []).length]);
  L.check('Add four times with the top event selected: four siblings, none nested',
    JSON.stringify(kids) === JSON.stringify([['First', 0.05, 0], ['Second', 0.2, 0], ['Third', 0.001, 0], ['Fourth', 0.25, 0]]), kids);
  L.check('"5%", full-width "０．２", "1/1000" and "0,25" were accepted as 0.05, 0.2, 0.001, 0.25',
    JSON.stringify(kids.map((k) => k[1])) === '[0.05,0.2,0.001,0.25]', kids);
  L.check('Add: the selection is still the parent', (await app.selectedId()) === rootId, await app.selectedId());
  L.check('Add: the newest row is marked as new and in view', await row(fourth).evaluate((r) => {
    const host = r.closest('.fta-tree').getBoundingClientRect();
    const b = r.getBoundingClientRect();
    return r.classList.contains('is-new') && b.top >= host.top && b.bottom <= host.bottom;
  }));
  const ids = { first: 'root_0', second: 'root_1', third, fourth };

  // ---- the top bar does not wrap on the first edit; the tab title ---------------------------
  const bar1 = await page.evaluate(() => ({ h: document.querySelector('.topbar').getBoundingClientRect().height, pill: document.getElementById('dirty').getBoundingClientRect().width, text: document.getElementById('dirty-text').textContent }));
  L.check('top bar keeps its height on the first edit', bar1.h === bar0.h && bar1.text === 'Unsaved changes', { bar0, bar1 });
  L.check('the Saved / Unsaved pill has one width', Math.abs(bar1.pill - bar0.pill) < 0.5, { bar0, bar1 });
  L.check('tab title marks unsaved changes', (await page.title()) === '● Untitled - FTA Editor', await page.title());
  L.check('the "all features" chip is the tick alone, the words in its tooltip', await page.evaluate(() => {
    const b = document.getElementById('btn-capabilities');
    return b.dataset.state !== 'ok' || (b.getBoundingClientRect().width < 60 && b.title.length > 10);
  }));

  // ---- first child: the parent's own probability stops counting ------------------------------
  await clearToasts();
  await app.selectTreeNode(ids.first);
  const grand = await app.addViaDialog({ name: 'Grandchild', probability: '0.5' });
  await page.waitForTimeout(300);
  let seen = await toasts();
  const warned = seen.filter((t) => /First/.test(t) && /no longer used/.test(t));
  L.check('first child (Add): a warning names the parent and its probability, with "Show in Validation"',
    warned.length === 1 && /0\.0500/.test(warned[0]) && /Show in Validation/.test(warned[0]), seen);
  const unused = await page.evaluate(() => {
    const input = document.querySelector('#details-root .fta-details-form input[inputmode="decimal"]');
    const field = input.closest('.fta-field');
    const note = field.querySelector('.fta-details-note');
    return { cls: field.classList.contains('is-unused'), note: note && !note.hidden ? note.textContent : '', readOnly: input.readOnly };
  });
  L.check('Details greys "Probability (base)" of a node with children and says why', unused.cls && /Not used/.test(unused.note) && !unused.readOnly, unused);
  await page.locator('#toasts .toast__action').first().click();
  await page.waitForTimeout(600);
  L.check('"Show in Validation" opens the Validation tab, which lists the ignored probability',
    await page.locator('#tab-validation').getAttribute('aria-selected') === 'true'
      && await page.locator('#tabpanel-validation li.val-item[data-code="PARENT_PROBABILITY_IGNORED"]').count() === 1);
  await app.clickTab('details');
  // the same through a move: Fourth indented under Third (a leaf with 0.001)
  await clearToasts();
  await row(ids.fourth).click();
  await page.keyboard.press('Control+Shift+ArrowRight');
  await page.waitForTimeout(600);
  seen = await toasts();
  L.check('first child (keyboard move): the same warning', seen.some((t) => /Third/.test(t) && /no longer used/.test(t)), seen);
  await page.keyboard.press('Control+z');
  await page.waitForTimeout(500);
  // a second child of a node that already has one: no warning
  await clearToasts();
  await app.selectTreeNode(ids.first);
  await app.addViaDialog({ name: 'Grandchild 2', probability: '0.5' });
  await page.waitForTimeout(300);
  seen = await toasts();
  L.check('a second child does not warn again', !seen.some((t) => /no longer used/.test(t)), seen);

  // ---- Ctrl+Shift+Up / Down at either end -----------------------------------------------------
  await clearToasts();
  await row(ids.first).click();
  await page.keyboard.press('Control+Shift+ArrowUp');
  await page.waitForTimeout(250);
  const up = await toasts();
  await clearToasts();
  await row(ids.fourth).click();
  await page.keyboard.press('Control+Shift+ArrowDown');
  await page.waitForTimeout(250);
  const down = await toasts();
  L.check('Ctrl+Shift+Up on the first child says "first", Down on the last says "last"',
    up.length === 1 && /first/.test(up[0]) && !/last|end/.test(up[0]) && down.length === 1 && /last/.test(down[0]), { up, down });

  // ---- double-click ----------------------------------------------------------------------------
  await row(rootId).click(); // so the double-click starts on a row that is not selected yet
  await row(ids.second).locator('.fta-tree-label').dblclick();
  L.check('double-click on a label opens the rename box', await page.locator('#tree-root .fta-tree-rename').count() === 1);
  await page.keyboard.press('Control+A');
  await page.keyboard.type('Second renamed');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
  L.check('double-click renames', (await tree()).children[1].name === 'Second renamed', (await tree()).children[1].name);
  await row(rootId).click();
  const wasOpen = await expandedAttr(ids.first);
  const box = await row(ids.first).boundingBox();
  await page.mouse.dblclick(box.x + box.width - 12, box.y + box.height / 2);
  await page.waitForTimeout(200);
  const nowOpen = await expandedAttr(ids.first);
  L.check('double-click beside the label collapses the branch', wasOpen === 'true' && nowOpen === 'false', { wasOpen, nowOpen });
  await page.mouse.dblclick(box.x + box.width - 12, box.y + box.height / 2);
  await page.waitForTimeout(200);
  L.check('and opens it again', (await expandedAttr(ids.first)) === 'true');

  // ---- Ctrl+Z with the gate dropdown still focused ------------------------------------------------
  await app.selectTreeNode(ids.first);
  const gate = page.locator('#details-root .fta-details-form select').first();
  await gate.focus();
  await gate.selectOption('AND');
  await page.waitForTimeout(400);
  const gateSet = (await tree()).children[0].logicGate;
  await gate.focus();
  await page.keyboard.press('Control+z');
  await page.waitForTimeout(500);
  const gateUndone = (await tree()).children[0].logicGate || 'OR';
  await gate.focus();
  await page.keyboard.press('Control+y');
  await page.waitForTimeout(500);
  const gateRedone = (await tree()).children[0].logicGate;
  L.check('Ctrl+Z and Ctrl+Y work with the gate dropdown focused', gateSet === 'AND' && gateUndone === 'OR' && gateRedone === 'AND', { gateSet, gateUndone, gateRedone });
  await gate.focus();
  await page.keyboard.press('Control+a');
  await page.waitForTimeout(250);
  L.check('other shortcuts still leave a focused dropdown alone (Ctrl+A opens no dialog)', await modal.count() === 0);
  await page.keyboard.press('Control+z');
  await page.waitForTimeout(400);

  // ---- Edit, and Enter in a Details field ---------------------------------------------------------
  await clearToasts();
  await row(ids.third).click();
  await page.locator('.actionbar [data-action="edit"]').click();
  await page.waitForTimeout(250);
  const editFocus = await page.evaluate(() => {
    const a = document.activeElement;
    return { tag: a.tagName, inDetails: !!a.closest('#details-root'), value: a.value, start: a.selectionStart, end: a.selectionEnd };
  });
  L.check('Edit puts the caret in the Name box with the name selected, and shows no toast',
    editFocus.inDetails && editFocus.value === 'Third' && editFocus.start === 0 && editFocus.end === 5 && (await toasts()).length === 0, editFocus);
  await page.keyboard.type('Third edited');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
  let focus = await focusInfo();
  L.check('Enter in a Details field saves and returns the focus to the node\'s tree row',
    (await tree()).children[2].name === 'Third edited' && focus.tag === 'LI' && focus.id === ids.third, focus);
  await page.keyboard.press('F2');
  L.check('so a tree key works at once (F2 renames)', await page.locator('#tree-root .fta-tree-rename').count() === 1);
  await page.keyboard.press('Escape');
  // a value that is refused keeps the caret
  await probBox().click();
  await page.keyboard.press('Control+A');
  await page.keyboard.type('0.5.1');
  await page.keyboard.press('Enter');
  focus = await focusInfo();
  L.check('Enter on a refused value keeps the caret in the box', focus.inputmode === 'decimal' && await page.locator('#details-root .fta-field-error:not([hidden])').count() === 1, focus);
  await clearToasts();
  await row(ids.second).click();
  await page.waitForTimeout(300);
  seen = await toasts();
  L.check('selecting another node says the refused entry was dropped, with its text',
    seen.length === 1 && /0\.5\.1/.test(seen[0]) && /Third edited/.test(seen[0]) && /not saved/.test(seen[0]), seen);
  await app.editDetailsField('Probability (base)', '５％', 'enter');
  await page.waitForTimeout(300);
  L.check('Details: full-width "５％" is stored as 0.05 and shown as 0.05',
    (await tree()).children[1].probability === 0.05 && (await probBox().inputValue()) === '0.05', await probBox().inputValue());

  // ---- delete confirmations ----------------------------------------------------------------------
  await row(ids.first).click();
  await page.keyboard.press('Delete');
  await modal.waitFor({ state: 'visible' });
  const ask = { text: await modal.locator('.fta-modal-message').textContent(), focus: (await focusInfo()).text };
  L.check('Delete confirmation counts the nodes and puts the focus on Cancel', /3 nodes/.test(ask.text) && ask.focus === 'Cancel', ask);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(300);
  L.check('Enter in the Delete confirmation cancels', await modal.count() === 0 && (await tree()).children[0].name === 'First');
  await row(ids.second).click();
  await page.keyboard.press('Delete');
  await modal.waitFor({ state: 'visible' });
  const askLeaf = await modal.locator('.fta-modal-message').textContent();
  await modal.locator('.fta-btn.is-primary').click();
  await page.waitForTimeout(500);
  L.check('a leaf is asked about by name alone, and the Delete button deletes it',
    !/nodes|beneath/.test(askLeaf) && /Second renamed/.test(askLeaf) && !(await tree()).children.some((c) => c.name === 'Second renamed'), askLeaf);
  await row(ids.first).click();
  await row(ids.third).click({ modifiers: ['Control'] });
  await page.keyboard.press('Delete');
  await modal.waitFor({ state: 'visible' });
  const askMany = { text: await modal.locator('.fta-modal-message').textContent(), focus: (await focusInfo()).text };
  L.check('a multi-selection is counted too (2 chosen, 4 nodes in all), focus on Cancel', /2 nodes/.test(askMany.text) && /4 nodes/.test(askMany.text) && askMany.focus === 'Cancel', askMany);
  await page.keyboard.press('Escape');
  await row(rootId).click();

  // ---- search: Enter steps through the matches ------------------------------------------------------
  const search = page.locator('#tree-root .fta-tree-search');
  await search.click();
  await page.keyboard.type('grandchild');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(200);
  const hit1 = await app.selectedId();
  await page.keyboard.press('Enter');
  await page.waitForTimeout(200);
  const hit2 = await app.selectedId();
  await page.keyboard.press('Enter');
  await page.waitForTimeout(200);
  const hit3 = await app.selectedId();
  focus = await focusInfo();
  const names = {};
  for (const n of (await tree()).children[0].children) names[n.id] = n.name;
  L.check('Enter in the search box selects the first match, then the next, and wraps round',
    names[hit1] === 'Grandchild' && names[hit2] === 'Grandchild 2' && hit3 === hit1 && hit1 === grand, { hit1, hit2, hit3, names });
  L.check('the caret stays in the search box', /fta-tree-search/.test(focus.cls), focus);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);

  // ---- the tree's open / closed state belongs to the file --------------------------------------------
  await app.api('post', '/new', { force: true });
  await page.evaluate(() => window.ftaShell.refresh());
  await openFile(fileA);
  L.check('status line: file name first, then the folder', await page.evaluate((name) =>
    document.getElementById('statusline-file').textContent === name && document.getElementById('statusline-path').textContent.length > 0, fileA));
  L.check('tab title names the file', (await page.title()) === fileA + ' - FTA Editor', await page.title());
  L.check('opening a file selects its top event', (await app.selectedId()) === 'root');
  await row('root_0').locator('.fta-tree-twisty').click();
  await page.waitForTimeout(150);
  const aClosed = await expandedAttr('root_0');
  await openFile(fileB);
  const bState = { root_0: await expandedAttr('root_0'), root_1: await expandedAttr('root_1') };
  L.check('a branch collapsed in one file is open in the next (same ids)', aClosed === 'false' && bState.root_0 === 'true' && bState.root_1 === 'true', { aClosed, bState });
  await row('root_1').locator('.fta-tree-twisty').click();
  await page.waitForTimeout(150);
  await openFile(fileA);
  const aBack = { root_0: await expandedAttr('root_0'), root_1: await expandedAttr('root_1') };
  L.check('and each file comes back as it was left', aBack.root_0 === 'false' && aBack.root_1 === 'true', aBack);
  await page.reload();
  await L.waitBoot(page);
  L.check('the state survives a reload of the page', (await expandedAttr('root_0')) === 'false' && (await expandedAttr('root_1')) === 'true');
  await row('root_0').locator('.fta-tree-twisty').click();

  // ---- the diagram: click, zoom, wheel, jump ---------------------------------------------------------
  await openFile(fileLong);
  const stageBox = await page.locator('#diagram-root .diagram__stage').boundingBox();
  const nodeBox = (id) => page.evaluate((wanted) => {
    for (const g of document.querySelectorAll('#diagram-root .diagram__canvas g.node')) {
      const title = g.querySelector('title');
      if (title && title.textContent.trim() === wanted) { const r = g.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; }
    }
    return null;
  }, id);
  const inStage = (b) => !!b && b.x >= stageBox.x - 0.5 && b.y >= stageBox.y - 0.5 && b.x + b.w <= stageBox.x + stageBox.width + 0.5 && b.y + b.h <= stageBox.y + stageBox.height + 0.5;
  const transform = () => page.evaluate(() => document.querySelector('#diagram-root .diagram__canvas').style.transform);
  const zoom = () => page.evaluate(() => parseInt(document.querySelector('#diagram-root .diagram__zoom').textContent, 10));
  const rowInView = (id) => page.evaluate((wanted) => {
    const host = document.querySelector('#tree-root .fta-tree');
    const item = Array.from(host.querySelectorAll('.fta-tree-item')).find((i) => i.dataset.id === wanted);
    if (!item) return { found: false };
    const r = item.querySelector(':scope > .fta-tree-row').getBoundingClientRect();
    const h = host.getBoundingClientRect();
    return { found: true, inView: r.top >= h.top - 0.5 && r.bottom <= h.bottom + 0.5, scrollTop: host.scrollTop, overflows: host.scrollHeight > host.clientHeight };
  }, id);

  const lastId = 'root_44';
  const before = await rowInView(lastId);
  const target = await nodeBox(lastId);
  await page.mouse.click(target.x + target.w / 2, target.y + target.h / 2);
  await page.waitForTimeout(400);
  const after = await rowInView(lastId);
  L.check('a click on a diagram node scrolls its tree row into view',
    before.overflows && !before.inView && (await app.selectedId()) === lastId && after.inView && after.scrollTop > 0, { before, after });

  // jump to a node that is fully on the stage: nothing moves, the fit stays
  const fitted = await transform();
  await page.evaluate(async () => (await import('/static/js/store.js')).store.jumpTo('root_3'));
  await page.waitForTimeout(300);
  L.check('jumping to a node already in view does not pan the diagram', (await transform()) === fitted && inStage(await nodeBox('root_3')), { fitted, now: await transform() });
  await page.setViewportSize({ width: 1500, height: 900 });
  await page.waitForTimeout(500);
  L.check('and auto-fit is still on afterwards (the diagram re-fits on a resize)', (await transform()) !== fitted, await transform());
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.waitForTimeout(500);

  // + from the toolbar: about the selected node, which stays on the stage
  await row('root_20').scrollIntoViewIfNeeded();
  await row('root_20').click();
  const z0 = await zoom();
  for (let i = 0; i < 10; i += 1) await page.locator('#diagram-root .diagram__btn', { hasText: '+' }).click();
  await page.waitForTimeout(200);
  const zoomed = { z0, z1: await zoom(), box: await nodeBox('root_20') };
  L.check('ten presses of + keep the selected node on the stage', zoomed.z1 > zoomed.z0 * 2 && inStage(zoomed.box), zoomed);
  // now a node far away is off the stage: a jump brings it in
  const far = await nodeBox('root_44');
  const panned0 = await transform();
  await page.evaluate(async () => (await import('/static/js/store.js')).store.jumpTo('root_44'));
  await page.waitForTimeout(300);
  L.check('jumping to a node off the stage brings it into view', !inStage(far) && (await transform()) !== panned0 && inStage(await nodeBox('root_44')), { far, now: await nodeBox('root_44') });
  await page.locator('#diagram-root .diagram__btn', { hasText: '⤢' }).click();
  await page.waitForTimeout(200);

  // with nothing of the selection to hold on to, + zooms about the middle
  await page.locator('#diagram-root .diagram__btn', { hasText: '−' }).click();
  await page.waitForTimeout(100);
  const part = await page.evaluate(() => {
    const s = document.querySelector('#diagram-root .diagram__stage').getBoundingClientRect();
    const g = document.querySelector('#diagram-root .diagram__canvas svg').getBoundingClientRect();
    const w = Math.max(0, Math.min(s.right, g.right) - Math.max(s.left, g.left));
    const h = Math.max(0, Math.min(s.bottom, g.bottom) - Math.max(s.top, g.top));
    return (w * h) / (g.width * g.height);
  });
  L.check('the - button keeps the whole diagram on the stage', part > 0.99, part);
  await page.locator('#diagram-root .diagram__btn', { hasText: '⤢' }).click();
  await page.waitForTimeout(200);

  // the plain wheel zooms about the cursor
  const zw0 = await zoom();
  const under = await nodeBox('root_10');
  await page.mouse.move(under.x + under.w / 2, under.y + under.h / 2);
  await page.mouse.wheel(0, -100);
  await page.mouse.wheel(0, -100);
  await page.mouse.wheel(0, -100);
  await page.waitForTimeout(200);
  const underNow = await nodeBox('root_10');
  const moved = Math.hypot(underNow.x + underNow.w / 2 - (under.x + under.w / 2), underNow.y + underNow.h / 2 - (under.y + under.h / 2));
  L.check('a plain wheel (no Ctrl) zooms in, holding the node under the cursor', (await zoom()) > zw0 && moved < 2, { zw0, z: await zoom(), moved });
  await page.mouse.wheel(0, 100);
  await page.waitForTimeout(150);
  const zw2 = await zoom();
  await page.mouse.wheel(0, 100);
  await page.waitForTimeout(150);
  L.check('and out again', (await zoom()) < zw2, { zw2, z: await zoom() });
  await page.locator('#diagram-root .diagram__btn', { hasText: '⤢' }).click();

  // ---- the diagram's numbers: bold, larger, no doubled q | Q -----------------------------------------
  const labels = await page.evaluate(() => Array.from(document.querySelectorAll('#diagram-root .diagram__canvas g.node.fta-box')).map((g) => {
    const texts = Array.from(g.querySelectorAll('text'));
    const num = texts.find((t) => /^[qQ]=/.test(t.textContent.trim()));
    const name = texts[0];
    return num ? { text: num.textContent.trim(), bold: num.getAttribute('font-weight') === 'bold', size: Number(num.getAttribute('font-size')), nameSize: Number(name.getAttribute('font-size')) } : null;
  }));
  L.check('symbols diagram: every box has a bold number row at least as large as its name',
    labels.length === 48 && labels.every((l) => l && l.bold && l.size >= l.nameSize), labels.filter((l) => !l || !l.bold || l.size < l.nameSize).slice(0, 4));
  L.check('symbols diagram: an event shows q once, a gate Q, never the same number twice',
    labels.filter((l) => /^q=[^|]+$/.test(l.text)).length === 44 + 2 && labels.filter((l) => /^Q=[^|]+$/.test(l.text)).length === 2 && !labels.some((l) => /\|/.test(l.text)), labels.slice(0, 5));

  // ---- the Open dialog: a path that is not there ----------------------------------------------------
  const mark = app.errMark();
  await page.locator('.actionbar [data-action="load"]').click();
  await page.locator('.fta-filedialog').waitFor({ state: 'visible' });
  await page.waitForTimeout(400);
  const pathBox = page.locator('.fta-filedialog .fdlg-path');
  await pathBox.fill('no_such_folder_' + label);
  await pathBox.press('Enter');
  await page.waitForTimeout(500);
  const said = await page.locator('.fta-filedialog').innerText();
  L.check('Open: a folder that does not exist is "Folder not found", not an extension error',
    /Folder not found/.test(said) && said.includes('no_such_folder_' + label) && !/saves/.test(said), said.slice(-200));
  await pathBox.fill('no_such_file_' + label + '.json');
  await pathBox.press('Enter');
  await page.waitForTimeout(500);
  L.check('Open: a file that does not exist is "File not found"', /File not found/.test(await page.locator('.fta-filedialog').innerText()));
  await pathBox.fill(fileA); // relative to the folder on screen
  await pathBox.press('Enter');
  await page.locator('.fta-filedialog').waitFor({ state: 'detached' });
  await page.waitForTimeout(600);
  st = await app.api('get', '/state');
  L.check('Open: a bare file name is read against the folder on screen', path.basename(st.currentPath || '') === fileA, st.currentPath);

  await app.shot('ux1_' + label);
  // Listing a typed path that is not a folder is refused by design: 404 when
  // nothing is there (twice above), 400 when it is a file (the one opened).
  // Each shows up twice, as the browser's console line and as the response.
  const errs = app.errorsSince(0, [/status of 40[04]/, /40[04] GET \/api\/fs\/list/]);
  const refused = app.errorsSince(mark).map((e) => (/40[04]/.exec(e.text) || [''])[0]).sort().join(' ');
  // (Twice in Chromium. Firefox writes no console line for a refused request,
  // so there each shows up once, as the response; either count is taken for
  // an engine other than Chromium.)
  const refusedAsExpected = refused === '400 400 404 404 404 404' || (L.BROWSER !== 'chromium' && refused === '400 404 404');
  L.check('no console errors in the editing flow (but for the three refused listings)', errs.length === 0 && refusedAsExpected, { errs, refused });
  await app.context.close();
}

L.runSection('ux1', run);
