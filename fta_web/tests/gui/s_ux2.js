// Protecting work (usability batch 2), with real mouse and keyboard input:
// the first-run hint and the folded AI panel, bundled examples as untitled
// copies, the Load dialog's other sources, the unsaved-changes prompt with
// "Save and continue", the remembered folder, importing a file from this
// computer (picker and drop), export wording, undo / redo feedback, a tab
// that fell behind another tab, the server-stopped banner and the rescue
// copy, the Update FTA preview, the Cut Sets wording for limits, and the
// "not connected" screen.   node s_ux2.js <url> <label> <root>
//
// No AI provider is ever called: the three /api/ai/update* routes are
// answered by this script.
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const EXAMPLES = path.join(L.REPO, 'fta_web', 'examples');

/** A small document file: a top event with `n` basic events under an OR gate. */
function treeFile(title, n) {
  const children = [];
  for (let i = 0; i < n; i += 1) {
    children.push({ id: 'root_' + i, name: title + ' event ' + i, type: 'Event', probability: 0.01, logicGate: 'OR', notes: '', links: [], children: [] });
  }
  return JSON.stringify({ title, date: '2026-10-12', mode: 'FTA', tree: { id: 'root', name: title + ' top', type: 'Root', probability: 1.0, logicGate: 'OR', notes: '', links: [], children } }, null, 2);
}

/** A tree without the values the engine derives, for comparing two copies of a document. */
function plain(node) {
  const out = {};
  for (const key of Object.keys(node).sort()) {
    if (key === 'children' || key === 'calculatedProbability') continue;
    out[key] = node[key];
  }
  out.children = (node.children || []).map(plain);
  return out;
}

async function run(url, label, root) {
  L.setSection('ux2[' + label + ']');
  const origin = new URL(url).origin;
  const fileA = 'ux2_a_' + label + '.json';
  const sub = 'ux2_sub_' + label;
  fs.writeFileSync(path.join(root, fileA), treeFile('Ux2A', 2));
  fs.mkdirSync(path.join(root, sub), { recursive: true });
  fs.writeFileSync(path.join(root, sub, 'inner.json'), treeFile('Inner', 1));
  const outside = path.join(L.OUT, 'ux2_outside_' + label + '.json'); // not in the sandbox root
  fs.writeFileSync(outside, treeFile('Outside', 3));

  const app = await L.openApp(url, { viewport: { width: 1600, height: 1000 } });
  const { page } = app;

  const toasts = () => page.evaluate(() => Array.from(document.querySelectorAll('#toasts .toast__body')).map((t) => t.textContent));
  const clearToasts = () => page.evaluate(() => document.getElementById('toasts').replaceChildren());
  const state = async () => app.api('get', '/state');
  const rows = () => page.locator('#tree-root li.fta-tree-item').count();
  const row = (id) => page.locator('#tree-root li.fta-tree-item[data-id="' + id + '"] > .fta-tree-row');
  const refresh = async () => { await page.evaluate(() => window.ftaShell.refresh()); await page.waitForTimeout(300); };
  const freshDoc = async () => {
    await app.api('post', '/new', { force: true });
    await page.reload();
    await L.waitBoot(page);
    await app.waitDiagram();
  };
  const prompt = page.locator('.fta-modal[data-kind="choice"]');
  const fileDialog = page.locator('.fta-filedialog');
  const visible = (sel) => page.locator(sel).isVisible();
  const waitFor = async (fn, timeout) => {
    const t0 = Date.now();
    for (;;) {
      if (await fn()) return true;
      if (Date.now() - t0 > (timeout || 8000)) return false;
      await page.waitForTimeout(100);
    }
  };

  await app.api('post', '/prefs', { aiPanelCollapsed: false });

  // ---- 27: a new analysis says how to begin ------------------------------------------------
  await freshDoc();
  L.check('first run: the hint is shown on a new, untouched analysis', await visible('#first-run'));
  const hintButtons = await page.locator('#first-run .firstrun__actions button').allTextContents();
  L.check('first run: "Name your top event" and "Open an example"', JSON.stringify(hintButtons) === JSON.stringify(['Name your top event', 'Open an example']), hintButtons);
  await page.locator('#first-run-name').click();
  await page.waitForTimeout(300);
  const nameFocus = await page.evaluate(() => {
    const a = document.activeElement;
    const inDetails = Boolean(a.closest('#details-root .fta-details-form'));
    return { inDetails, tag: a.tagName, all: a.selectionStart === 0 && a.selectionEnd === a.value.length && a.value.length > 0, value: a.value };
  });
  L.check('first run: "Name your top event" puts the caret in the Name box, the name selected', nameFocus.inDetails && nameFocus.tag === 'INPUT' && nameFocus.all, nameFocus);
  await page.keyboard.type('Loss of cooling');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
  let st = await state();
  L.check('first run: typing there names the top event', st.tree.name === 'Loss of cooling', st.tree.name);
  L.check('first run: the hint goes with the first edit', !(await visible('#first-run')));
  await freshDoc();
  await page.locator('#first-run-dismiss').click();
  L.check('first run: the hint can be closed', !(await visible('#first-run')));
  await page.reload(); await L.waitBoot(page); await app.waitDiagram();

  // ---- 27: the AI panel folds, and the server remembers it -------------------------------
  const aiWidth = () => page.evaluate(() => document.getElementById('ai-panel').getBoundingClientRect().width);
  const wideAi = await aiWidth();
  await page.locator('#btn-ai-collapse').click();
  await page.waitForTimeout(400);
  const folded = { w: await aiWidth(), expanded: await page.getAttribute('#btn-ai-collapse', 'aria-expanded'), title: await page.getAttribute('#btn-ai-collapse', 'title'), chat: await visible('#ai-root') };
  L.check('AI panel: the button folds it to a strip', folded.w < 60 && wideAi > 200 && folded.expanded === 'false' && /Show/.test(folded.title) && !folded.chat, { wideAi, folded });
  L.check('AI panel: the choice is stored on the server', (await state()).prefs.aiPanelCollapsed === true);
  await page.reload(); await L.waitBoot(page); await page.waitForTimeout(400);
  L.check('AI panel: still folded after a reload', (await aiWidth()) < 60, await aiWidth());
  await page.locator('#btn-ai-collapse').click();
  await page.waitForTimeout(400);
  L.check('AI panel: the button opens it again, at the width it had', Math.abs((await aiWidth()) - wideAi) < 1 && await visible('#ai-root') && (await state()).prefs.aiPanelCollapsed === false, await aiWidth());

  // ---- 21 + 25: an example opens as an untitled copy -------------------------------------
  const bundled = fs.readdirSync(EXAMPLES).filter((f) => f.endsWith('.json')).sort();
  const before = Object.fromEntries(bundled.map((f) => [f, fs.readFileSync(path.join(EXAMPLES, f), 'utf8')]));
  await page.locator('#first-run-example').click();
  const list = page.locator('.fta-modal[data-kind="list"]');
  await list.waitFor({ state: 'visible' });
  const offered = await list.locator('.fta-choice').evaluateAll((els) => els.map((e) => e.dataset.value));
  const fromApi = (await app.api('get', '/examples')).examples.map((e) => e.name);
  L.check('examples: the list is the server\'s, one row per bundled file', JSON.stringify(offered) === JSON.stringify(fromApi) && offered.length >= 3 && offered.includes('sampleFTA.json'), { offered, fromApi });
  await app.shot('ux2_examples_' + label);
  await list.locator('.fta-choice[data-value="sampleFTA.json"]').click();
  await list.waitFor({ state: 'detached' });
  await page.waitForTimeout(800);
  st = await state();
  L.check('examples: opened with no path and no unsaved changes', st.currentPath === null && st.dirty === false && st.tree.children.length > 0, { p: st.currentPath, d: st.dirty });
  L.check('examples: the status line says there is no file; the tab is "Untitled"', (await page.textContent('#statusline-file')) === 'No file' && (await page.title()) === 'Untitled - FTA Editor', await page.title());
  L.check('examples: the toast says it is an untitled copy', (await toasts()).some((t) => /untitled copy/.test(t)), await toasts());
  let mark = app.errMark();
  await page.keyboard.press('Control+s');
  await fileDialog.waitFor({ state: 'visible' });
  L.check('examples: Save goes to Save As', (await fileDialog.locator('.fta-modal-title').textContent()) === 'Save Analysis As');
  L.check('examples: Save on a document with no file asks no doomed request (no 409)', app.errorsSince(mark).length === 0, app.errorsSince(mark));
  await page.keyboard.press('Escape');
  await fileDialog.waitFor({ state: 'detached' });
  // an edit, then a real save: it lands in the sandbox root, the bundled file is untouched
  await row(String(st.tree.id)).click();
  await app.addViaDialog({ name: 'Added to the example', probability: '0.5' });
  await page.keyboard.press('Control+s');
  await fileDialog.waitFor({ state: 'visible' });
  await page.waitForTimeout(500);
  const savedCopy = 'ux2_example_copy_' + label + '.json';
  await fileDialog.locator('.fdlg-name').fill(savedCopy);
  await fileDialog.locator('.fta-btn.is-primary').click();
  await fileDialog.waitFor({ state: 'detached' });
  await page.waitForTimeout(600);
  st = await state();
  const after = Object.fromEntries(bundled.map((f) => [f, fs.readFileSync(path.join(EXAMPLES, f), 'utf8')]));
  L.check('examples: the saved copy is in the sandbox root and the bundled files are byte-identical',
    path.resolve(st.currentPath) === path.resolve(root, savedCopy) && fs.existsSync(path.join(root, savedCopy)) && JSON.stringify(after) === JSON.stringify(before), st.currentPath);

  // ---- 25: the Load dialog's other sources, and a refusal that says what to do -------------
  await page.locator('.actionbar [data-action="load"]').click();
  await fileDialog.waitFor({ state: 'visible' });
  await page.waitForTimeout(500);
  const sources = await fileDialog.locator('.fdlg-sources button').evaluateAll((bs) => bs.map((b) => [b.dataset.source, b.textContent]));
  L.check('Load dialog: "Open an example…" and "A file on this computer…"', JSON.stringify(sources) === JSON.stringify([['example', 'Open an example…'], ['import', 'A file on this computer…']]), sources);
  await fileDialog.locator('.fdlg-path').fill(path.resolve(root, '..'));
  await page.keyboard.press('Enter');
  await page.waitForTimeout(600);
  const refusal = await fileDialog.locator('.fdlg-message').textContent();
  L.check('Load dialog: a path outside the root says how to start the editor on another folder, and how to open one file anyway',
    refusal.includes(path.resolve(root)) && /--root "<folder>"/.test(refusal) && /A file on this computer/.test(refusal), refusal);
  await fileDialog.locator('[data-source="example"]').click();
  await list.waitFor({ state: 'visible' });
  L.check('Load dialog: "Open an example…" leads to the list', await fileDialog.count() === 0 && await list.locator('.fta-choice').count() === offered.length);
  await page.keyboard.press('Escape');
  await list.waitFor({ state: 'detached' });

  // ---- 29: unsaved changes -> Cancel / Discard / Save and continue -------------------------
  await app.api('post', '/new', { force: true });
  await app.api('post', '/nodes', { parentId: 'root', name: 'Unsaved work', probability: 0.1 });
  await refresh();
  await clearToasts();
  await page.locator('.actionbar [data-action="new"]').click();
  await prompt.waitFor({ state: 'visible' });
  const three = await prompt.locator('.fta-modal-footer button').evaluateAll((bs) => bs.map((b) => [b.dataset.role, b.textContent.trim(), document.activeElement === b]));
  L.check('New on unsaved changes: Cancel, "Discard and start new", "Save and continue" (focused)',
    JSON.stringify(three) === JSON.stringify([['cancel', 'Cancel', false], ['discard', 'Discard and start new', false], ['save', 'Save and continue', true]]), three);
  await app.shot('ux2_unsaved_' + label);
  await page.keyboard.press('Escape');
  await prompt.waitFor({ state: 'detached' });
  st = await state();
  L.check('New: Escape keeps the document', st.tree.children.length === 1 && st.dirty === true);
  // Save and continue, then cancel the Save As dialog: New does not happen
  await page.locator('.actionbar [data-action="new"]').click();
  await prompt.waitFor({ state: 'visible' });
  await page.keyboard.press('Enter'); // the focus is on Save and continue
  await fileDialog.waitFor({ state: 'visible' });
  await page.waitForTimeout(400);
  await page.keyboard.press('Escape');
  await fileDialog.waitFor({ state: 'detached' });
  await page.waitForTimeout(400);
  st = await state();
  L.check('Save and continue, save cancelled: the document is kept and nothing else happens',
    st.tree.children.length === 1 && st.dirty === true && (await toasts()).some((t) => /was not saved/.test(t)), await toasts());
  // Save and continue, saved: New goes ahead
  await page.locator('.actionbar [data-action="new"]').click();
  await prompt.waitFor({ state: 'visible' });
  await prompt.locator('[data-role="save"]').click();
  await fileDialog.waitFor({ state: 'visible' });
  await page.waitForTimeout(500);
  const savedFirst = 'ux2_saved_first_' + label + '.json';
  await fileDialog.locator('.fdlg-name').fill(savedFirst);
  await fileDialog.locator('.fta-btn.is-primary').click();
  await fileDialog.waitFor({ state: 'detached' });
  await page.waitForTimeout(900);
  st = await state();
  const onDisk = fs.existsSync(path.join(root, savedFirst)) ? JSON.parse(fs.readFileSync(path.join(root, savedFirst), 'utf8')) : null;
  L.check('Save and continue, saved: the file has the work and the new analysis is open',
    onDisk && onDisk.tree.children[0].name === 'Unsaved work' && st.tree.children.length === 0 && st.currentPath === null && st.dirty === false, { st: st.tree.children.length, p: st.currentPath });
  // Load asks the same way
  await app.api('post', '/nodes', { parentId: 'root', name: 'More work', probability: 0.1 });
  await refresh();
  await page.locator('.actionbar [data-action="load"]').click();
  await prompt.waitFor({ state: 'visible' });
  const loadAsk = await prompt.locator('.fta-modal-footer button').evaluateAll((bs) => bs.map((b) => b.textContent.trim()));
  L.check('Load on unsaved changes: Cancel, "Discard and open", "Save and continue"', JSON.stringify(loadAsk) === JSON.stringify(['Cancel', 'Discard and open', 'Save and continue']), loadAsk);
  await prompt.locator('[data-role="cancel"]').click();
  await page.waitForTimeout(300);
  L.check('Load: Cancel opens no file dialog and keeps the document', await fileDialog.count() === 0 && (await state()).tree.children.length === 1);

  // ---- 26: the file dialog starts in the folder last used ------------------------------------
  await app.api('post', '/file/open', { path: path.join(root, sub, 'inner.json') });
  await app.api('post', '/new', { force: true });
  await refresh();
  await page.locator('.actionbar [data-action="load"]').click();
  await fileDialog.waitFor({ state: 'visible' });
  await fileDialog.locator('.fdlg-row', { hasText: 'inner.json' }).waitFor({ state: 'visible' });
  const where = await fileDialog.locator('.fdlg-location').textContent();
  L.check('last folder: Load on a document with no file starts where the last file was opened', path.resolve(where.trim()) === path.resolve(root, sub), where);
  await page.keyboard.press('Escape');
  await fileDialog.waitFor({ state: 'detached' });
  // back to the root, which is where the sections after this one expect to start
  await app.api('post', '/file/open', { path: path.join(root, fileA) });
  await app.api('post', '/new', { force: true });
  L.check('last folder: follows the next open', path.resolve((await app.api('get', '/fs/home')).cwd) === path.resolve(root));
  await refresh();

  // ---- 28: a file from this computer (picker), and exports that say what they are -------------
  await clearToasts();
  await page.locator('.actionbar [data-action="load"]').click();
  await fileDialog.waitFor({ state: 'visible' });
  const [chooser] = await Promise.all([page.waitForEvent('filechooser'), fileDialog.locator('[data-source="import"]').click()]);
  await chooser.setFiles(outside);
  await waitFor(async () => (await rows()) === 4);
  st = await state();
  L.check('import (picker): the file opens as an untitled document with unsaved changes',
    st.tree.name === 'Outside top' && st.currentPath === null && st.dirty === true && (await toasts()).some((t) => /copy of ux2_outside/.test(t)), { p: st.currentPath, d: st.dirty, t: await toasts() });
  const group = await page.evaluate(() => {
    const g = document.querySelector('.actionbar__group');
    return { label: document.getElementById('export-label').textContent, role: g.getAttribute('role'), named: g.getAttribute('aria-labelledby'), actions: Array.from(g.querySelectorAll('[data-action]')).map((b) => b.dataset.action) };
  });
  L.check('exports: the four download buttons are a group labelled "Export:"', group.label === 'Export:' && group.role === 'group' && group.named === 'export-label' && JSON.stringify(group.actions) === '["json","xml","excel","render"]', group);
  await clearToasts();
  const [dlUntitled] = await Promise.all([page.waitForEvent('download'), page.locator('.actionbar [data-action="json"]').click()]);
  await page.waitForTimeout(400);
  let said = (await toasts()).join(' | ');
  L.check('export of an unsaved document: "a copy", the download folder, and that it is not a save', /Downloaded a copy as /.test(said) && /browser saves downloads/.test(said) && /not saved by this/.test(said) && (await state()).dirty === true, said);
  await dlUntitled.cancel().catch(() => {});
  await app.api('post', '/file/open', { path: path.join(root, fileA) });
  await refresh();
  await clearToasts();
  const [dlNamed] = await Promise.all([page.waitForEvent('download'), page.locator('.actionbar [data-action="xml"]').click()]);
  await page.waitForTimeout(400);
  said = (await toasts()).join(' | ');
  L.check('export of a saved document: names the copy and says the open file is unchanged', said.includes(dlNamed.suggestedFilename()) && said.includes('The open file (' + fileA + ') is unchanged'), said);
  await dlNamed.cancel().catch(() => {});

  // ---- 28: a .json dropped on the tree panel -------------------------------------------------
  const dropText = treeFile('Dropped', 4);
  const drop = (selector, name) => page.evaluate(([sel, text, fileName]) => {
    const data = new DataTransfer();
    data.items.add(new File([text], fileName, { type: 'application/json' }));
    const target = document.querySelector(sel);
    const fire = (type) => { const e = new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: data }); target.dispatchEvent(e); return e.defaultPrevented; };
    fire('dragenter');
    const over = fire('dragover');
    const zone = !document.getElementById('tree-dropzone').hidden;
    const dropped = fire('drop');
    return { over, zone, dropped, zoneAfter: !document.getElementById('tree-dropzone').hidden };
  }, [selector, dropText, name]);
  await clearToasts();
  let dropped = await drop('#diagram-root', 'dropped.json');
  await page.waitForTimeout(500);
  L.check('drop outside the tree panel: taken from the browser (the page is not replaced) and nothing opens',
    dropped.over && dropped.dropped && !dropped.zone && (await state()).tree.name === 'Ux2A top', dropped);
  dropped = await drop('#tree-root', 'notes.txt');
  await page.waitForTimeout(400);
  L.check('drop of another file type: refused in words', (await toasts()).some((t) => /not a \.json analysis file/.test(t)) && (await state()).tree.name === 'Ux2A top', await toasts());
  dropped = await drop('#tree-root', 'dropped.json');
  await waitFor(async () => (await rows()) === 5);
  st = await state();
  L.check('drop on the tree panel: the zone shows while dragging, and the file opens as an untitled copy',
    dropped.zone && !dropped.zoneAfter && st.tree.name === 'Dropped top' && st.currentPath === null && st.dirty === true, { dropped, n: st.tree.name });
  // dropped on a document with unsaved changes: the same question as Load
  dropped = await drop('#tree-root', 'dropped.json');
  await prompt.waitFor({ state: 'visible' });
  L.check('drop on unsaved changes: asks first, with "Save and continue"', (await prompt.locator('[data-role="save"]').count()) === 1 && (await prompt.locator('[data-role="discard"]').textContent()).trim() === 'Discard and open');
  await prompt.locator('[data-role="cancel"]').click();
  await page.waitForTimeout(300);

  // ---- 24: undo and redo say what they did and select the node ---------------------------------
  await app.api('post', '/new', { force: true });
  let made = await app.api('post', '/nodes', { parentId: 'root', name: 'Pump A', probability: 0.01 });
  const pumpA = made.nodeId;
  made = await app.api('post', '/nodes', { parentId: pumpA, name: 'Seal leak', probability: 0.02 });
  const seal = made.nodeId;
  await refresh();
  await row(seal).click();
  await page.keyboard.press('Delete');
  await page.locator('.fta-modal').waitFor({ state: 'visible' });
  await page.locator('.fta-modal-footer .fta-btn.is-primary').click();
  await waitFor(async () => (await rows()) === 2);
  await clearToasts();
  await page.keyboard.press('Control+z');
  await waitFor(async () => (await rows()) === 3);
  await page.waitForTimeout(200);
  L.check('undo of a delete: the toast names it, and the node that came back is selected',
    (await toasts()).includes('Undid: deleting "Seal leak"') && (await app.selectedId()) === seal, { t: await toasts(), s: await app.selectedId() });
  await clearToasts();
  await page.keyboard.press('Control+y');
  await waitFor(async () => (await rows()) === 2);
  await page.waitForTimeout(200);
  L.check('redo of a delete: the toast names it, and the former parent is selected (not the top event)',
    (await toasts()).includes('Redid: deleting "Seal leak"') && (await app.selectedId()) === pumpA, { t: await toasts(), s: await app.selectedId() });
  await row(pumpA).click();
  await app.editDetailsField('Name', 'Pump A fails', 'enter');
  await row('root').click();
  await clearToasts();
  await page.keyboard.press('Control+z');
  await page.waitForTimeout(600);
  L.check('undo of a rename: the toast names the node and the field, and the node is selected',
    (await toasts()).includes('Undid: a change to "Pump A" (name)') && (await app.selectedId()) === pumpA, { t: await toasts(), s: await app.selectedId() });

  // ---- 17: a tab that fell behind another tab ----------------------------------------------------
  const focusTab = () => page.evaluate(() => window.dispatchEvent(new Event('focus')));
  await app.api('post', '/new', { force: true });
  await refresh();
  await clearToasts();
  await app.api('post', '/nodes', { parentId: 'root', name: 'Made elsewhere', probability: 0.3 }); // "the other tab"
  await page.waitForTimeout(600);
  L.check('second tab: behind until it is looked at (no polling of the document)', (await rows()) === 1 && (await page.textContent('#dirty-text')) === 'Saved');
  await focusTab();
  await waitFor(async () => (await rows()) === 2);
  L.check('second tab: on focus it shows the current tree, says "Unsaved changes" and tells why',
    (await rows()) === 2 && (await page.textContent('#dirty-text')) === 'Unsaved changes' && (await toasts()).some((t) => /changed in another tab or window/.test(t)), await toasts());
  // with a dialog open the document is not swapped under it
  await row('root').click();
  await page.locator('.actionbar [data-action="add"]').click();
  const addModal = page.locator('.fta-modal');
  await addModal.waitFor({ state: 'visible' });
  await page.keyboard.type('Typed here');
  await app.api('post', '/nodes', { parentId: 'root', name: 'Made elsewhere 2', probability: 0.3 });
  await focusTab();
  await page.waitForTimeout(1800);
  L.check('second tab: not reloaded while a dialog is open, and what was typed is still there',
    (await rows()) === 2 && (await addModal.locator('.fta-field input').nth(0).inputValue()) === 'Typed here', await rows());
  await page.keyboard.press('Escape');
  await addModal.waitFor({ state: 'detached' });
  L.check('second tab: reloaded once the dialog is closed', await waitFor(async () => (await rows()) === 3, 5000), await rows());
  // the other tab saved: only the badge and the file name change, with no "changed" toast
  await clearToasts();
  const savedElsewhere = 'ux2_saved_elsewhere_' + label + '.json';
  await app.api('post', '/file/save-as', { path: path.join(root, savedElsewhere) });
  await focusTab();
  await waitFor(async () => (await page.textContent('#dirty-text')) === 'Saved');
  L.check('second tab: a save in the other tab reaches the badge and the file name, without a reload notice',
    (await page.textContent('#dirty-text')) === 'Saved' && (await page.textContent('#statusline-file')) === savedElsewhere && !(await toasts()).some((t) => /another tab/.test(t)), await toasts());
  // another document opened elsewhere
  await clearToasts();
  await app.api('post', '/file/open', { path: path.join(root, fileA) });
  await focusTab();
  await waitFor(async () => (await page.textContent('#statusline-file')) === fileA);
  L.check('second tab: another analysis opened elsewhere is shown, and said to be another one',
    (await page.textContent('#statusline-file')) === fileA && (await toasts()).some((t) => /Another analysis was opened/.test(t)) && (await app.selectedId()) === 'root', await toasts());
  // this tab's own edits are not taken for somebody else's
  await clearToasts();
  await row('root').click();
  await app.addViaDialog({ name: 'Mine', probability: '0.5' });
  await page.keyboard.press('Control+s');
  await page.waitForTimeout(600);
  await focusTab();
  await page.waitForTimeout(1200);
  L.check('second tab: this tab\'s own edit and save raise no "changed elsewhere" notice', !(await toasts()).some((t) => /another tab/.test(t)) && (await page.textContent('#dirty-text')) === 'Saved', await toasts());

  // ---- 22: Cut Sets when a limit leaves nothing --------------------------------------------------
  await app.api('post', '/new', { force: true });
  await app.api('post', '/nodes', { parentId: 'root', name: 'Pump A', probability: 0.01 });
  await app.api('post', '/nodes', { parentId: 'root', name: 'Pump B', probability: 0.02 });
  await app.api('patch', '/nodes/root', { logicGate: 'AND' });
  await refresh();
  await app.setAdvanced(true);
  await app.clickTab('cutsets');
  const cs = page.locator('#tabpanel-cutsets');
  await cs.locator('.anl-table').waitFor({ state: 'visible' });
  const runOnly = cs.locator('[data-role="run-only"]');
  const order = cs.locator('input[data-limit="maxOrder"]');
  const docOrder = await order.inputValue();
  L.check('cut sets: no "this run only" mark while the limits are the document\'s', !(await runOnly.isVisible()) && !(await cs.locator('[data-role="reset-limits"]').isVisible()));
  await order.click();
  await page.keyboard.press('Control+a');
  await page.keyboard.type('1');
  L.check('cut sets: a typed limit is marked "This run only", with Reset', (await runOnly.isVisible()) && (await runOnly.textContent()) === 'This run only' && await cs.locator('[data-role="reset-limits"]').isVisible());
  await page.keyboard.press('Enter');
  await waitFor(async () => /within these limits/.test(await cs.locator('.anl-empty').textContent()));
  const none = { message: await cs.locator('.anl-empty').textContent(), summary: await cs.locator('.anl-summary').textContent() };
  L.check('cut sets: "none within these limits (max order)", not "the top event cannot occur"',
    /No cut sets within these limits \(max order\)/.test(none.message) && !/cannot occur with these settings/.test(none.message), none);
  L.check('cut sets: no bound of 0 and no "0 of 0" beside it; the tree walk stays', !/Min-cut upper bound|Rare-event|of 0 cut sets/.test(none.summary) && /Tree walk/.test(none.summary), none);
  await app.shot('ux2_cutsets_' + label);
  await cs.locator('[data-role="reset-limits"]').click();
  await cs.locator('.anl-table').waitFor({ state: 'visible' });
  const back = { order: await order.inputValue(), summary: await cs.locator('.anl-summary').textContent(), mark: await runOnly.isVisible() };
  L.check('cut sets: Reset goes back to the document limits and runs again', back.order === docOrder && /1 of 1 cut sets/.test(back.summary) && /Min-cut upper bound/.test(back.summary) && !back.mark, back);
  await app.clickTab('details');
  await app.setAdvanced(false);

  // ---- 20: Update FTA asks, shows what it would do, and waits for Apply -------------------------
  const calls = { update: [], apply: [], discard: [] };
  await page.route('**/api/state', async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    body.aiConfigured = true;
    body.capabilities.aiConfigured = true;
    await route.fulfill({ response: res, json: body });
  });
  const summary = { added: [{ id: 'root_9', name: 'Common-cause failure' }], changed: [{ id: 'root_0', name: 'Pump A' }], removed: [{ id: 'root_1', name: 'Pump B' }] };
  await page.route('**/api/ai/update', async (route) => {
    calls.update.push(route.request().postDataJSON());
    await route.fulfill({ json: { ok: true, preview: true, updateId: 'gui-' + calls.update.length, reply: 'Here is my version.', mergedFields: 0, updateSummary: summary } });
  });
  await page.route('**/api/ai/update/discard', async (route) => {
    calls.discard.push(route.request().postDataJSON());
    await route.fulfill({ json: { ok: true, discarded: true } });
  });
  await page.route('**/api/ai/update/apply', async (route) => {
    calls.apply.push(route.request().postDataJSON());
    // what the server answers after installing: here, the tree with Pump B removed
    const now = await app.api('get', '/state');
    const tree = JSON.parse(JSON.stringify(now.tree));
    tree.children = tree.children.filter((c) => c.name !== 'Pump B');
    await route.fulfill({ json: { ok: true, mergedFields: 0, updateSummary: summary, tree, zeroNodes: [], dirty: true, canUndo: true, canRedo: false, analysis: now.analysis, sessionWarnings: [], revision: now.revision, documentSerial: now.documentSerial } });
  });
  await refresh();
  const updateBtn = page.locator('#ai-root button', { hasText: 'Update FTA' });
  const revBefore = (await state()).revision;
  await updateBtn.click();
  await prompt.waitFor({ state: 'visible' });
  L.check('Update FTA: asks before anything is sent', calls.update.length === 0 && /sent to the AI provider/.test(await prompt.locator('.fta-modal-message').textContent()));
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  L.check('Update FTA: Cancel sends nothing', calls.update.length === 0 && (await page.locator('#ai-root .chat-update').count()) === 0);
  await updateBtn.click();
  await prompt.waitFor({ state: 'visible' });
  await prompt.locator('[data-role="ask"]').click();
  const card = page.locator('#ai-root .chat-update').last();
  await card.waitFor({ state: 'visible' });
  const lines = await card.locator('.chat-update__line').allTextContents();
  L.check('Update FTA: the request asks for a preview', JSON.stringify(calls.update) === '[{"preview":true}]', calls.update);
  L.check('Update FTA: the card lists what would be added, changed and removed, by name',
    JSON.stringify(lines) === JSON.stringify(['Added (1): Common-cause failure', 'Changed (1): Pump A', 'Removed (1): Pump B']), lines);
  L.check('Update FTA: nothing is applied yet', (await state()).revision === revBefore && (await rows()) === 3 && /not applied yet/.test(await card.textContent()));
  await app.shot('ux2_update_preview_' + label);
  await card.locator('[data-role="discard-update"]').click();
  await page.waitForTimeout(400);
  L.check('Update FTA: Discard drops it on the server and freezes the card',
    JSON.stringify(calls.discard) === '[{"id":"gui-1"}]' && (await card.getAttribute('data-retired')) === 'true' && await card.locator('[data-role="apply-update"]').isDisabled() && calls.apply.length === 0 && (await rows()) === 3, calls);
  await updateBtn.click();
  await prompt.waitFor({ state: 'visible' });
  await prompt.locator('[data-role="ask"]').click();
  const card2 = page.locator('#ai-root .chat-update').last();
  await card2.locator('[data-role="apply-update"]:not([disabled])').waitFor({ state: 'visible' });
  await card2.locator('[data-role="apply-update"]').click();
  await waitFor(async () => (await rows()) === 2);
  L.check('Update FTA: Apply installs it through /update/apply with the preview\'s id',
    JSON.stringify(calls.apply) === '[{"id":"gui-2"}]' && (await rows()) === 2 && (await card2.getAttribute('data-retired')) === 'true', calls);
  for (const pattern of ['**/api/ai/update', '**/api/ai/update/discard', '**/api/ai/update/apply', '**/api/state']) await page.unroute(pattern);
  await refresh();

  // ---- 19: the server stops answering --------------------------------------------------------------
  await app.api('post', '/file/open', { path: path.join(root, fileA) });
  await refresh();
  await row('root').click();
  await app.addViaDialog({ name: 'Not saved yet', probability: '0.25' });
  const held = await state();
  await clearToasts();
  L.check('server banner: not shown while the server answers', !(await visible('#server-banner')));
  let refusedCalls = 0;
  await page.route('**/api/**', (route) => { refusedCalls += 1; return route.abort('connectionrefused'); });
  const up = await waitFor(async () => visible('#server-banner'), 12000);
  const bannerText = up ? await page.textContent('#server-banner-text') : '';
  L.check('server banner: appears when the server cannot be reached, and says there are unsaved changes', up && /not answering/.test(bannerText) && /unsaved changes/.test(bannerText), bannerText);
  await app.shot('ux2_server_stopped_' + label);
  const [rescue] = await Promise.all([page.waitForEvent('download'), page.locator('#server-banner-rescue').click()]);
  const rescuePath = path.join(L.OUT, 'ux2_rescue_' + label + '.json');
  await rescue.saveAs(rescuePath);
  const copy = JSON.parse(fs.readFileSync(rescuePath, 'utf8'));
  L.check('rescue copy: a .json named after the file, holding the document this tab shows, unsaved edit included',
    /^ux2_a_.*-rescue-\d{8}-\d{4}\.json$/.test(rescue.suggestedFilename()) && JSON.stringify(Object.keys(copy)) === '["title","date","mode","tree","analysis"]'
    && JSON.stringify(plain(copy.tree)) === JSON.stringify(plain(held.tree)) && copy.tree.children.some((c) => c.name === 'Not saved yet'), Object.keys(copy));
  const callsAtBanner = refusedCalls;
  await page.waitForTimeout(3000);
  L.check('server banner: stays up for as long as the server is away', await visible('#server-banner'));
  L.check('server banner: while the server is away the page asks at its usual pace, not in a loop', refusedCalls - callsAtBanner <= 3, refusedCalls - callsAtBanner);
  // "Try again" while the server is still away: the banner stays
  await page.locator('#server-banner-retry').click();
  await page.waitForTimeout(600);
  L.check('server banner: "Try again" with the server still away leaves it up', await visible('#server-banner'));
  await page.unroute('**/api/**');
  // The next ping may clear the banner before the click lands; either is fine.
  await page.locator('#server-banner-retry').click({ timeout: 1500 }).catch(() => {});
  const down = await waitFor(async () => !(await visible('#server-banner')), 12000);
  L.check('server banner: goes when the server answers again, and says so', down && (await toasts()).some((t) => /answering again/.test(t)), await toasts());
  // the rescue copy is a file the editor opens: same tree, same settings
  const opened = await page.evaluate(async ([text]) => {
    const form = new FormData();
    form.append('file', new File([text], 'rescue.json', { type: 'application/json' }));
    const r = await fetch('/api/import/json', { method: 'POST', headers: { 'X-FTA-Token': sessionStorage.getItem('fta.session.token') }, body: form });
    return { status: r.status, json: await r.json() };
  }, [fs.readFileSync(rescuePath, 'utf8')]);
  L.check('rescue copy: opens through the import endpoint as the same document',
    opened.status === 200 && JSON.stringify(plain(opened.json.tree)) === JSON.stringify(plain(held.tree)) && JSON.stringify(opened.json.metadata) === JSON.stringify(held.metadata)
    && JSON.stringify(opened.json.analysis) === JSON.stringify(held.analysis), opened.status);
  await refresh();

  // ---- 18: a tab that is not connected ---------------------------------------------------------------
  const bare = await app.context.newPage();
  await bare.goto(origin + '/');
  await bare.locator('#blocking-overlay:not([hidden])').waitFor({ state: 'visible' });
  const screen = { title: (await bare.textContent('#overlay-title')).trim(), body: await bare.locator('#overlay-body').innerText(), cmd: (await bare.textContent('#overlay-cmd')).trim(), rescue: await bare.locator('#overlay-rescue').isVisible() };
  L.check('no session: plain words, no "session key"', screen.title === 'This tab is not connected to the editor' && /only works in the tab it opens itself/.test(screen.body) && !/session key|one-time/i.test(screen.body), screen);
  const packaged = (await bare.getAttribute('#blocking-overlay', 'data-packaged')) === '1';
  L.check('no session: the command to start it again comes from the server and fits how it was started',
    packaged ? (/\S/.test(screen.cmd) && !/[\\/]/.test(screen.cmd) && !/run\.py/.test(screen.cmd) && /double-click/.test(screen.body)) : screen.cmd === 'uv run python fta_web/run.py', screen);
  L.check('no session: no rescue copy is offered where there is no document', !screen.rescue);
  await bare.screenshot({ path: path.join(L.OUT, 'ux2_no_session_' + label + '.png') });
  await bare.close();
  // a working tab whose session ends keeps its document within reach
  const second = await app.context.newPage();
  await second.goto(url);
  await L.waitBoot(second);
  await second.route('**/api/revision', (route) => route.fulfill({ status: 403, json: { ok: false, error: { code: 'FORBIDDEN', message: 'Invalid session token.', detail: { reason: 'invalid_token' } } } }));
  await second.evaluate(() => window.dispatchEvent(new Event('focus')));
  await second.locator('#blocking-overlay:not([hidden])').waitFor({ state: 'visible' });
  const offer = await second.locator('#overlay-rescue-btn').isVisible();
  const [lost] = await Promise.all([second.waitForEvent('download'), second.locator('#overlay-rescue-btn').click()]);
  L.check('session ended in a working tab: the screen offers the rescue copy, and it downloads', offer && /-rescue-\d{8}-\d{4}\.json$/.test(lost.suggestedFilename()) && /downloaded/i.test(await second.textContent('#overlay-rescue-done')), lost.suggestedFilename());
  await lost.cancel().catch(() => {});
  await second.close();

  // ---- Japanese: the new strings are translated ----------------------------------------------------
  await freshDoc();
  await app.setLanguage('ja');
  const ja = await page.evaluate(() => ({
    hint: document.querySelector('#first-run .firstrun__title').textContent,
    buttons: Array.from(document.querySelectorAll('#first-run .firstrun__actions button')).map((b) => b.textContent),
    exportLabel: document.getElementById('export-label').textContent,
    collapse: document.getElementById('btn-ai-collapse').title,
    rawKeys: (document.body.innerText.match(/\b(?:rescue|stale|examples|import|firstrun|history|confirm)\.[a-zA-Z0-9.]+\b/g) || []),
  }));
  L.check('Japanese: the hint, the export label and the AI panel button are translated; no raw key on screen',
    ja.hint === 'ここから始めます' && ja.buttons[0] === '頂上事象に名前を付ける' && ja.exportLabel === 'エクスポート:' && /AIアシスタント/.test(ja.collapse) && ja.rawKeys.length === 0, ja);
  await app.api('post', '/nodes', { parentId: 'root', name: 'x', probability: 0.1 });
  await refresh();
  await page.locator('.actionbar [data-action="new"]').click();
  await prompt.waitFor({ state: 'visible' });
  const jaAsk = await prompt.locator('.fta-modal-footer button').allTextContents();
  L.check('Japanese: the unsaved-changes prompt', JSON.stringify(jaAsk) === JSON.stringify(['キャンセル', '破棄して新規作成', '保存して続行']), jaAsk);
  await page.keyboard.press('Escape');
  await app.setLanguage('en');

  // leave the shared server as the next sections expect it: a new document, the root as last folder
  await app.api('post', '/file/open', { path: path.join(root, fileA) });
  await app.api('post', '/new', { force: true });
  await app.api('post', '/prefs', { aiPanelCollapsed: false });
}

L.runSection('ux2', run);
