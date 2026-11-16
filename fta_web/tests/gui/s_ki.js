// The known issues of 1.8.0, fixed (1.8.1), with real mouse and keyboard
// input: the number reader refusing a number too small for a double; the
// unsaved-changes prompt raised by the server when another tab changed the
// document; the recovery copy offered at start-up (Restore opens an
// untitled, modified copy; Discard deletes it); "Change folder..." in the
// file dialog, where a dialog can be opened and where it cannot; Stop in
// the assistant telling the editor to abandon the request; the Japanese
// strings.   node s_ki.js <url> <label> <root>
//
// No AI provider is ever called: /api/ai/chat and /api/ai/cancel are
// answered by this script. No native folder dialog is ever opened: the
// server run.mjs starts has it switched off (FTA_EDITOR_NO_FOLDER_PICKER),
// and where the page is shown the "available" state, /api/fs/home and
// /api/fs/root/choose are answered by this script too.
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

/** A small document file: a top event with `n` basic events under an OR gate. */
function treeFile(title, n) {
  const children = [];
  for (let i = 0; i < n; i += 1) {
    children.push({ id: 'root_' + i, name: title + ' event ' + i, type: 'Event', probability: 0.01, logicGate: 'OR', notes: '', links: [], children: [] });
  }
  return JSON.stringify({ title, date: '2026-10-12', mode: 'FTA', tree: { id: 'root', name: title + ' top', type: 'Root', probability: 1.0, logicGate: 'OR', notes: '', links: [], children } }, null, 2);
}

async function run(url, label, root) {
  L.setSection('ki[' + label + ']');
  const fileA = 'ki_a_' + label + '.json';
  const sub = 'ki_sub_' + label;
  fs.writeFileSync(path.join(root, fileA), treeFile('KiA', 2));
  fs.mkdirSync(path.join(root, sub), { recursive: true });
  fs.writeFileSync(path.join(root, sub, 'inner.json'), treeFile('KiInner', 1));

  const app = await L.openApp(url, { viewport: { width: 1600, height: 1000 } });
  const { page } = app;

  const toasts = () => page.evaluate(() => Array.from(document.querySelectorAll('#toasts .toast__body')).map((t) => t.textContent));
  const clearToasts = () => page.evaluate(() => document.getElementById('toasts').replaceChildren());
  const state = async () => app.api('get', '/state');
  const rows = () => page.locator('#tree-root li.fta-tree-item').count();
  const refresh = async () => { await page.evaluate(() => window.ftaShell.refresh()); await page.waitForTimeout(300); };
  const freshDoc = async () => {
    await app.api('post', '/new', { force: true });
    await page.reload();
    await L.waitBoot(page);
    await app.waitDiagram();
  };
  const prompt = page.locator('.fta-modal[data-kind="choice"]');
  const fileDialog = page.locator('.fta-filedialog');
  const waitFor = async (fn, timeout) => {
    const t0 = Date.now();
    for (;;) {
      if (await fn()) return true;
      if (Date.now() - t0 > (timeout || 8000)) return false;
      await page.waitForTimeout(100);
    }
  };
  const names = async () => ((await state()).tree.children || []).map((c) => c.name);

  await freshDoc();

  // ---- 7: a number too small for a double ----------------------------------------------------------
  await page.locator('.actionbar [data-action="add"]').click();
  const modal = page.locator('.fta-modal').last();
  await modal.waitFor({ state: 'visible' });
  const pIn = modal.locator('input[inputmode="decimal"]');
  await modal.locator('.fta-field input').nth(0).fill('Tiny');
  await pIn.fill('1e-400');
  await pIn.press('Enter');
  await page.waitForTimeout(300);
  const tiny = { open: await modal.count(), errors: await modal.locator('.fta-field-error:not([hidden])').allTextContents(), made: (await names()).length };
  L.check('number: "1e-400" is refused in the Add dialog and makes nothing (it was read as 0)',
    tiny.open === 1 && tiny.errors.length === 1 && tiny.made === 0, tiny);
  await pIn.fill('-0');
  await pIn.press('Tab');
  L.check('number: "-0" is shown as 0 on leaving the box', (await pIn.inputValue()) === '0', await pIn.inputValue());
  await pIn.fill('1e-300');
  await modal.locator('.fta-modal-footer .fta-btn.is-primary').click();
  await modal.waitFor({ state: 'detached', timeout: 5000 });
  const small = (await state()).tree.children.map((c) => [c.name, c.probability]);
  L.check('number: "1e-300" is still a number', JSON.stringify(small) === JSON.stringify([['Tiny', 1e-300]]), small);

  // ---- 2: the server refuses to replace what another tab changed -------------------------------------
  await freshDoc();
  await clearToasts();
  const markGuard = app.errMark();
  await app.api('post', '/nodes', { parentId: 'root', name: 'Typed in the other tab', probability: 0.3 }); // "the other tab"
  L.check('guard: this tab still shows a saved, empty analysis', (await rows()) === 1 && (await page.textContent('#dirty-text')) === 'Saved');
  await page.locator('.actionbar [data-action="load"]').click();
  await fileDialog.waitFor({ state: 'visible' });
  L.check('guard: a tab that knows of no changes is not asked before the file dialog', (await prompt.count()) === 0);
  await fileDialog.locator('.fdlg-row', { hasText: fileA }).waitFor({ state: 'visible' });
  await fileDialog.locator('.fdlg-row', { hasText: fileA }).dblclick();
  await prompt.waitFor({ state: 'visible', timeout: 5000 });
  const asked = { buttons: await prompt.locator('.fta-modal-footer button').allTextContents(), names: await names(), dirty: await page.textContent('#dirty-text') };
  L.check('guard: the server refused, and the unsaved-changes prompt is shown after all',
    JSON.stringify(asked.buttons) === JSON.stringify(['Cancel', 'Discard and open', 'Save and continue']) && asked.dirty === 'Unsaved changes', asked);
  L.check('guard: the other tab\'s work is still there while the prompt is up', JSON.stringify(asked.names) === JSON.stringify(['Typed in the other tab']), asked.names);
  L.check('guard: and it is shown behind the prompt (the tree was read again)',
    (await rows()) === 2 && (await page.locator('#tree-root li.fta-tree-item > .fta-tree-row', { hasText: 'Typed in the other tab' }).count()) === 1, await rows());
  await app.shot('ki_guard_prompt_' + label);
  await prompt.locator('.fta-modal-footer [data-role="cancel"]').click();
  await page.waitForTimeout(300);
  L.check('guard: Cancel keeps the document', JSON.stringify(await names()) === JSON.stringify(['Typed in the other tab']) && (await state()).dirty === true);

  // again, and this time Discard: the request is sent once more, with the flag
  const sent = [];
  const onRequest = (request) => { if (/\/api\/file\/open$/.test(request.url())) sent.push(request.postDataJSON()); };
  page.on('request', onRequest);
  await app.api('post', '/new', { force: true });
  await refresh();
  await app.api('post', '/nodes', { parentId: 'root', name: 'Typed in the other tab', probability: 0.3 });
  await page.locator('.actionbar [data-action="load"]').click();
  await fileDialog.waitFor({ state: 'visible' });
  await fileDialog.locator('.fdlg-row', { hasText: fileA }).waitFor({ state: 'visible' });
  await fileDialog.locator('.fdlg-row', { hasText: fileA }).dblclick();
  await prompt.waitFor({ state: 'visible', timeout: 5000 });
  await prompt.locator('.fta-modal-footer [data-role="discard"]').click();
  await waitFor(async () => (await rows()) === 3, 5000);
  page.off('request', onRequest);
  L.check('guard: "Discard and open" opens the file', (await rows()) === 3 && ((await state()).currentPath || '').endsWith(fileA), (await state()).currentPath);
  L.check('guard: the first request carried no flag and the second one did',
    sent.length === 2 && sent[0].force === undefined && sent[1].force === true, sent);
  const guardErrors = app.errorsSince(markGuard, [/409/, /UNSAVED_CHANGES/, /unsaved changes/i]);
  L.check('guard: the only console errors were the two refused requests', guardErrors.length === 0, guardErrors);

  // ---- 5: the recovery copy ----------------------------------------------------------------------------
  const home = process.env.FTA_GUI_HOME || '';
  const recoveryDir = home ? path.join(home, '.fta_editor', 'recovery') : '';
  if (!home || !fs.existsSync(recoveryDir)) {
    for (const name of ['the offer at start-up', 'Restore', 'Discard', 'Restore over unsaved work', 'Japanese']) {
      L.skip('recovery: ' + name, 'the home folder of this server is not known (FTA_GUI_HOME); run.mjs sets it for a server it starts');
    }
  } else {
    const original = path.join(root, 'ki_orig_' + label + '.json');
    fs.writeFileSync(original, treeFile('KiOriginal', 1));
    const originalBytes = fs.readFileSync(original);
    /** What an editor that ended without saving leaves: the copy and its sidecar, and no lock. */
    const plant = (id, title, n) => {
      fs.writeFileSync(path.join(recoveryDir, id + '.json'), treeFile(title, n));
      fs.writeFileSync(path.join(recoveryDir, id + '.meta.json'), JSON.stringify({
        version: 1, session: id, title, originalPath: original, savedAt: '2026-10-11T09:30:00',
      }));
    };
    const planted = (id) => fs.readdirSync(recoveryDir).filter((f) => f.startsWith(id));
    const offer = page.locator('#recovery-offer');

    plant('00000000000000a1', 'Ki recovered', 3);
    await freshDoc();
    await offer.waitFor({ state: 'visible', timeout: 5000 });
    const shown = {
      title: await offer.locator('.firstrun__title').textContent(),
      text: await offer.locator('#recovery-text').textContent(),
      restore: await page.locator('#recovery-restore').textContent(),
      discard: await page.locator('#recovery-discard').textContent(),
      hint: await page.locator('#first-run').isVisible(),
      above: await page.evaluate(() => document.getElementById('recovery-offer').getBoundingClientRect().top < document.getElementById('first-run').getBoundingClientRect().top),
    };
    L.check('recovery: a copy left by an editor that did not end cleanly is offered above "Start here"',
      shown.title === 'Unsaved work found' && shown.hint && shown.above && shown.discard === 'Discard it', shown);
    L.check('recovery: the button says the date and the title, the text says where it had been opened from',
      /^Restore unsaved work from .*2026.*\(Ki recovered\)$/.test(shown.restore) && /11/.test(shown.restore) && shown.text.includes(original) && /does not change that file/.test(shown.text), shown);
    await app.shot('ki_recovery_offer_' + label);

    await clearToasts();
    await page.locator('#recovery-restore').click();
    await waitFor(async () => (await rows()) === 4, 5000);
    const restored = await state();
    L.check('recovery: Restore opens it untitled and modified',
      restored.currentPath === null && restored.dirty === true && restored.metadata.title === 'Ki recovered' && restored.tree.children.length === 3
      && (await page.textContent('#dirty-text')) === 'Unsaved changes', { path: restored.currentPath, dirty: restored.dirty, title: restored.metadata.title });
    L.check('recovery: it says so, and the offer goes', (await toasts()).some((t) => /Restored "Ki recovered" as an untitled copy/.test(t)) && !(await offer.isVisible()), await toasts());
    L.check('recovery: the copy that was restored is gone, and the file it came from is untouched',
      planted('00000000000000a1').length === 0 && fs.readFileSync(original).equals(originalBytes), planted('00000000000000a1'));
    L.check('recovery: the restored work has a copy of its own (this editor\'s)',
      await waitFor(async () => fs.readdirSync(recoveryDir).filter((f) => /^[0-9a-f]{16}\.json$/.test(f)).length === 1, 5000), fs.readdirSync(recoveryDir));
    await page.keyboard.press('Control+s');
    await fileDialog.waitFor({ state: 'visible', timeout: 5000 });
    L.check('recovery: Save goes to Save As', (await fileDialog.locator('.fta-modal-title').textContent()) === 'Save Analysis As');
    await page.keyboard.press('Escape');
    await fileDialog.waitFor({ state: 'detached' });

    // over unsaved work (the restored document is unsaved): asked first
    plant('00000000000000a2', 'Ki second', 1);
    await page.reload();
    await L.waitBoot(page);
    await offer.waitFor({ state: 'visible', timeout: 5000 });
    L.check('recovery: offered beside a document that is being worked on too', !(await page.locator('#first-run').isVisible()) && /\(Ki second\)$/.test(await page.locator('#recovery-restore').textContent()));
    await page.locator('#recovery-restore').click();
    await prompt.waitFor({ state: 'visible', timeout: 5000 });
    await prompt.locator('.fta-modal-footer [data-role="cancel"]').click();
    await page.waitForTimeout(300);
    L.check('recovery: Restore over unsaved work asks first, and Cancel keeps both',
      (await state()).metadata.title === 'Ki recovered' && planted('00000000000000a2').length === 2 && (await offer.isVisible()));

    // Discard
    await clearToasts();
    await page.locator('#recovery-discard').click();
    const confirm = page.locator('.fta-modal').last();
    await confirm.waitFor({ state: 'visible' });
    const confirmText = await confirm.locator('.fta-modal-message').textContent();
    const confirmButtons = await confirm.locator('.fta-modal-footer button').allTextContents();
    L.check('recovery: Discard asks, naming what goes', /Discard the unsaved work from .*\(Ki second\)\?/.test(confirmText) && confirmButtons.includes('Discard the copy'), { confirmText, confirmButtons });
    await confirm.locator('.fta-modal-footer button', { hasText: 'Discard the copy' }).click();
    await waitFor(async () => !(await offer.isVisible()), 5000);
    L.check('recovery: the copy is deleted, the offer goes and the document is untouched',
      planted('00000000000000a2').length === 0 && !(await offer.isVisible()) && (await state()).metadata.title === 'Ki recovered'
      && (await toasts()).some((t) => /recovery copy was deleted/.test(t)), await toasts());

    // Japanese
    plant('00000000000000a3', 'Ki 三番目', 1);
    await freshDoc();
    await offer.waitFor({ state: 'visible', timeout: 5000 });
    await app.setLanguage('ja');
    const ja = {
      title: await offer.locator('.firstrun__title').textContent(),
      restore: await page.locator('#recovery-restore').textContent(),
      discard: await page.locator('#recovery-discard').textContent(),
      text: await offer.locator('#recovery-text').textContent(),
      rawKeys: (await page.evaluate(() => document.body.innerText)).match(/\b(?:recovery|file\.changeRoot)\.[a-zA-Z0-9.]+\b/g) || [],
    };
    L.check('Japanese: the recovery offer',
      ja.title === '保存されていない作業が見つかりました' && /の未保存の作業を復元（Ki 三番目）$/.test(ja.restore) && ja.discard === '破棄する' && ja.text.includes(original) && ja.rawKeys.length === 0, ja);
    await app.shot('ki_recovery_offer_ja_' + label);
    await app.setLanguage('en');
    const left = await app.api('post', '/recovery/discard', { id: '00000000000000a3' });
    L.check('recovery: the copy can be discarded through the API too', left.discarded === true && planted('00000000000000a3').length === 0, left);
    fs.rmSync(original, { force: true });
  }

  // ---- Save As confirmed before the folder has been listed (found by the WebKit run) -----------------------
  // A name typed and Enter pressed while the first listing was still on its
  // way did nothing, and nothing said so. The listing is held back here.
  await freshDoc();
  await app.api('post', '/nodes', { parentId: 'root', name: 'Saved early', probability: 0.1 });
  await refresh();
  let releaseList = null;
  await page.route('**/api/fs/list**', async (route) => {
    await new Promise((resolve) => { releaseList = resolve; });
    await route.continue();
  });
  const early = 'ki_early_' + label;
  await page.locator('.actionbar [data-action="save-as"]').click();
  await fileDialog.waitFor({ state: 'visible' });
  await fileDialog.locator('.fdlg-name').fill(early);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
  await waitFor(async () => releaseList !== null, 3000);
  L.check('Save As: Enter before the folder is listed saves nothing yet, and the dialog waits',
    (await fileDialog.count()) === 1 && (await state()).currentPath === null && releaseList !== null);
  releaseList();
  const savedEarly = await waitFor(async () => (((await state()).currentPath) || '').endsWith(early + '.json'), 5000);
  const earlyPath = (await state()).currentPath || '';
  L.check('Save As: and the save goes ahead when the listing has landed',
    savedEarly && fs.existsSync(earlyPath) && (await fileDialog.count()) === 0 && (await page.textContent('#dirty-text')) === 'Saved', earlyPath);
  await page.unroute('**/api/fs/list**');
  if (earlyPath) fs.rmSync(earlyPath, { force: true });

  // ---- 6: "Change folder..." ---------------------------------------------------------------------------
  await freshDoc();
  const realHome = await app.api('get', '/fs/home');
  L.check('folder: this server cannot open a folder dialog, and says so', realHome.canChooseRoot === false && /--root "<folder>"/.test(realHome.relaunch || ''), realHome);
  const refusedByServer = await app.api('post', '/fs/root/choose', { path: path.resolve(root, '..') });
  L.check('folder: a request that names a folder is refused', refusedByServer.status === 400 && refusedByServer.code === 'INVALID_FIELD', refusedByServer);
  const unavailable = await app.api('post', '/fs/root/choose');
  L.check('folder: without a dialog the endpoint answers 501 with the command', unavailable.status === 501 && unavailable.code === 'PICKER_UNAVAILABLE' && /--root "<folder>"/.test((unavailable.detail || {}).relaunch || ''), unavailable);
  L.check('folder: the root is what it was', (await app.api('get', '/fs/home')).root === realHome.root);

  const changeButton = fileDialog.locator('[data-role="change-root"]');
  const message = fileDialog.locator('.fdlg-message');
  await page.locator('.actionbar [data-action="load"]').click();
  await fileDialog.waitFor({ state: 'visible' });
  await fileDialog.locator('.fdlg-row', { hasText: fileA }).waitFor({ state: 'visible' });
  L.check('folder: the file dialog has a "Change folder…" button', (await changeButton.textContent()) === 'Change folder…' && await changeButton.isEnabled());
  let chooseRequests = 0;
  const countChoose = (request) => { if (/\/api\/fs\/root\/choose/.test(request.url())) chooseRequests += 1; };
  page.on('request', countChoose);
  await changeButton.click();
  await page.waitForTimeout(300);
  const noDialog = await message.textContent();
  L.check('folder: where no dialog can be opened, the button gives the command to start the editor on another folder (nothing is sent)',
    /cannot be opened on this computer/.test(noDialog) && /--root "<folder>"/.test(noDialog) && chooseRequests === 0, { noDialog, chooseRequests });
  await app.shot('ki_change_folder_unavailable_' + label);
  page.off('request', countChoose);
  await page.keyboard.press('Escape');
  await fileDialog.waitFor({ state: 'detached' });

  // The same dialog on a machine that can open one. The two requests are
  // answered here: no folder dialog exists in this test.
  const chosen = path.join(root, sub);
  const chooseCalls = [];
  let chooseAnswer = null;
  await page.route('**/api/fs/home', async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    body.canChooseRoot = true;
    await route.fulfill({ response: res, json: body });
  });
  await page.route('**/api/fs/root/choose', async (route) => {
    chooseCalls.push({ body: route.request().postData(), url: route.request().url() });
    await chooseAnswer(route);
  });
  await page.locator('.actionbar [data-action="load"]').click();
  await fileDialog.waitFor({ state: 'visible' });
  await fileDialog.locator('.fdlg-row', { hasText: fileA }).waitFor({ state: 'visible' });
  await app.shot('ki_change_folder_button_' + label);

  // a path outside the folder: the refusal offers the button
  await fileDialog.locator('.fdlg-path').fill(path.resolve(root, '..'));
  await page.keyboard.press('Enter');
  await page.waitForTimeout(600);
  const here = fileDialog.locator('[data-role="change-root-here"]');
  const refusal = await message.textContent();
  L.check('folder: a path outside the folder points at "Change folder…" (not at a restart), with the button under it',
    refusal.includes(path.resolve(root)) && /use "Change folder…"/.test(refusal) && !/--root/.test(refusal) && await here.isVisible(), refusal);
  await app.shot('ki_outside_root_refusal_' + label);

  // the person closes the dialog
  let releaseChoose = null;
  chooseAnswer = (route) => new Promise((resolve) => {
    releaseChoose = async (json) => { await route.fulfill({ json }); resolve(); };
  });
  await here.click();
  await waitFor(async () => releaseChoose !== null, 3000);
  const waiting = { text: await message.textContent(), disabled: await changeButton.isDisabled() };
  L.check('folder: while the dialog is open the page says where to look, and the button waits',
    /folder chooser has opened on this computer/.test(waiting.text) && waiting.disabled, waiting);
  await releaseChoose({ ok: true, changed: false, cancelled: true, root });
  await waitFor(async () => /No folder was chosen/.test(await message.textContent()), 3000);
  L.check('folder: a closed dialog changes nothing and says so', /No folder was chosen/.test(await message.textContent()) && await changeButton.isEnabled(), await message.textContent());
  L.check('folder: the request carried no path (no body at all)',
    chooseCalls.length === 1 && (chooseCalls[0].body === null || chooseCalls[0].body === '' || chooseCalls[0].body === '{}') && !/[?&](path|root)=/.test(chooseCalls[0].url), chooseCalls);

  // the person picks a folder
  chooseAnswer = (route) => route.fulfill({ json: { ok: true, changed: true, cancelled: false, root: chosen, currentPath: null, dirty: false, documentUntitled: false } });
  await changeButton.click();
  await fileDialog.locator('.fdlg-row', { hasText: 'inner.json' }).waitFor({ state: 'visible', timeout: 5000 });
  const moved = { text: await message.textContent(), where: await fileDialog.locator('.fdlg-path').inputValue() };
  L.check('folder: after a choice the dialog shows the new folder and says the editor works there',
    moved.text.includes('now reads and writes in ' + chosen) && path.resolve(moved.where) === path.resolve(chosen), moved);
  await page.keyboard.press('Escape');
  await fileDialog.waitFor({ state: 'detached' });

  // a document outside the folder that was picked becomes untitled
  await page.unroute('**/api/fs/root/choose');
  await app.api('post', '/file/open', { path: path.join(root, fileA), force: true });
  await refresh();
  await clearToasts();
  const shellSays = async () => page.evaluate(async () => (await import('/static/js/store.js')).store.state.currentPath);
  L.check('folder: (a document with a file is open)', ((await shellSays()) || '').endsWith(fileA));
  await page.route('**/api/fs/root/choose', async (route) => {
    await route.fulfill({ json: { ok: true, changed: true, cancelled: false, root: chosen, currentPath: null, dirty: false, documentUntitled: true } });
  });
  await page.locator('.actionbar [data-action="load"]').click();
  await fileDialog.waitFor({ state: 'visible' });
  await changeButton.click();
  await waitFor(async () => /now untitled/.test(await message.textContent()), 5000);
  L.check('folder: a document outside the new folder is said to be untitled now, in the dialog and in a message',
    /now untitled: use Save As/.test(await message.textContent()) && (await toasts()).some((t) => /now untitled/.test(t)) && (await shellSays()) === null, await toasts());
  await page.keyboard.press('Escape');
  await fileDialog.waitFor({ state: 'detached' });

  // the editor turns out not to be able to open one after all (501)
  await page.unroute('**/api/fs/root/choose');
  const mark501 = app.errMark();
  await page.route('**/api/fs/root/choose', async (route) => {
    await route.fulfill({ status: 501, json: { ok: false, error: { code: 'PICKER_UNAVAILABLE', message: 'x', detail: { reason: 'helper_failed', relaunch: 'fta_editor.exe --root "<folder>"' } } } });
  });
  await page.locator('.actionbar [data-action="load"]').click();
  await fileDialog.waitFor({ state: 'visible' });
  await changeButton.click();
  await waitFor(async () => /cannot be opened/.test(await message.textContent()), 5000);
  L.check('folder: a 501 from the editor falls back to the command it names',
    /fta_editor\.exe --root "<folder>"/.test(await message.textContent()), await message.textContent());
  L.check('folder: the only console error was the 501', app.errorsSince(mark501, [/501/, /PICKER_UNAVAILABLE/, /Not Implemented/i]).length === 0, app.errorsSince(mark501, [/501/, /PICKER_UNAVAILABLE/, /Not Implemented/i]));
  await page.keyboard.press('Escape');
  await fileDialog.waitFor({ state: 'detached' });
  await app.setLanguage('ja');
  await page.locator('.actionbar [data-action="load"]').click();
  await fileDialog.waitFor({ state: 'visible' });
  L.check('Japanese: the "Change folder…" button', (await changeButton.textContent()) === 'フォルダーを変更…', await changeButton.textContent());
  await page.keyboard.press('Escape');
  await fileDialog.waitFor({ state: 'detached' });
  await app.setLanguage('en');
  await page.unroute('**/api/fs/root/choose');
  await page.unroute('**/api/fs/home');
  L.check('folder: after all of it the server\'s root is what it was', (await app.api('get', '/fs/home')).root === realHome.root);

  // ---- 4: Stop tells the editor to abandon the request ---------------------------------------------------
  await app.api('post', '/new', { force: true });
  const chatCalls = [];
  const cancelCalls = [];
  let chatRelease = null;
  let cancelAnswer = (route) => route.fulfill({ json: { ok: true, cancelled: true } });
  await page.route('**/api/state', async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    body.aiConfigured = true;
    body.capabilities.aiConfigured = true;
    await route.fulfill({ response: res, json: body });
  });
  await page.route('**/api/ai/conversation', async (route) => {
    await route.fulfill({ json: { ok: true, messages: [], changes: [], pendingUpdate: null } });
  });
  await page.route('**/api/ai/chat', async (route) => {
    chatCalls.push(route.request().postDataJSON());
    await new Promise((resolve) => { chatRelease = async () => { await route.fulfill({ json: { ok: true, reply: 'Too late.', changes: [] } }); resolve(); }; });
  });
  await page.route('**/api/ai/cancel', async (route) => {
    cancelCalls.push(route.request().postDataJSON());
    await cancelAnswer(route);
  });
  await page.reload();
  await L.waitBoot(page);
  await app.waitDiagram();
  const chat = page.locator('#ai-root');
  const input = chat.locator('.chat__input');
  const stop = chat.locator('[data-role="stop"]');
  await input.fill('What fails first?');
  await chat.locator('.chat__send').click();
  await stop.waitFor({ state: 'visible' });
  await stop.click();
  await waitFor(async () => cancelCalls.length === 1, 3000);
  const stopped = {
    chat: chatCalls.map((c) => typeof c.requestId), cancel: cancelCalls,
    same: chatCalls.length === 1 && cancelCalls.length === 1 && chatCalls[0].requestId === cancelCalls[0].requestId,
    said: await chat.locator('.chat-msg', { hasText: 'Stopped waiting. The request was abandoned' }).count(),
    old: await chat.locator('.chat-msg', { hasText: 'may be refused as busy' }).count(),
    text: await input.inputValue(),
  };
  L.check('assistant: Stop asks the editor to abandon exactly the request it stopped',
    stopped.same && typeof chatCalls[0].requestId === 'string' && chatCalls[0].requestId.length >= 8, stopped);
  L.check('assistant: the message says a new request can be sent, and the typed text is back',
    stopped.said === 1 && stopped.old === 0 && stopped.text === 'What fails first?', stopped);
  await chatRelease();
  await page.waitForTimeout(300);
  L.check('assistant: the late answer is not shown', (await chat.locator('.chat-msg', { hasText: 'Too late.' }).count()) === 0);

  // the editor cannot be told (it has stopped): a second line says what that means
  const markStop = app.errMark();
  cancelAnswer = (route) => route.abort('connectionrefused');
  await chat.locator('.chat__send').click();
  await stop.waitFor({ state: 'visible' });
  await stop.click();
  const told = await waitFor(async () => (await chat.locator('.chat-msg', { hasText: 'could not be told to abandon' }).count()) === 1, 4000);
  L.check('assistant: when the editor cannot be told, the page says a new request may still be refused', told && chatCalls.length === 2 && chatCalls[1].requestId !== chatCalls[0].requestId, chatCalls.map((c) => c.requestId));
  await chatRelease();
  await page.waitForTimeout(300);
  await page.unroute('**/api/ai/cancel');
  await page.unroute('**/api/ai/chat');
  await page.unroute('**/api/ai/conversation');
  await page.unroute('**/api/state');
  const stray = app.errorsSince(markStop, [/api\/ai\/cancel/, /Failed to load resource/, /net::ERR/, /NetworkError/, /Load failed/, /could not be reached/, /not answering/]);
  L.check('assistant: no other console error', stray.length === 0, stray);

  // leave the shared server as the next sections expect it
  await app.api('post', '/new', { force: true });
  await app.api('post', '/prefs', { aiPanelCollapsed: false });
  fs.rmSync(path.join(root, sub), { recursive: true, force: true });
  fs.rmSync(path.join(root, fileA), { force: true });
}

L.runSection('ki', run);
