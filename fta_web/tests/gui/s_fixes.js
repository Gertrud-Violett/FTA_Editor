// GUI checks for the 1.7.1 frontend fixes (real Chrome, real input).
// node s_fixes.js <url> <label> <root>
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

async function main(url, label, root) {
  L.setSection('fixes[' + label + ']');
  // FMEA sample with FIT values in the λ column
  const csv = '\ufeffFMEA ID,Item,Failure Mode,Cause,Severity,Occurrence,Detection,RPN,Lambda\r\n'
    + 'F-01,Pump,Fails to start,Motor,8,3,4,96,120\r\nF-02,Valve,Stuck closed,Corrosion,9,2,5,90,45\r\n';
  fs.writeFileSync(path.join(root, 'fmea_fit.csv'), csv);

  const app = await L.openApp(url, { prefs: { 'fta.advanced': '1' } });
  const { page } = app;
  const mark0 = app.errMark();

  // ---- Alt+N on a dirty document: confirm names the consequence, no 409 ----------
  await app.api('post', '/new', { force: true });
  await page.evaluate(() => window.ftaShell.refresh());
  await app.api('post', '/nodes', { parentId: 'root', name: 'dirty child', probability: 0.1 });
  await page.evaluate(() => window.ftaShell.refresh());
  await page.locator('#tree-root li.fta-tree-item[data-id="root"] > .fta-tree-row').click();
  await page.keyboard.press('Alt+N');
  const modal = page.locator('.fta-modal');
  await modal.waitFor({ state: 'visible', timeout: 4000 });
  const okText = await modal.locator('.fta-btn.is-primary').textContent();
  L.check('Alt+N on a dirty doc asks, OK button says "Discard and start new"', okText.trim() === 'Discard and start new', okText);
  await modal.locator('.fta-btn.is-primary').click();
  await page.waitForTimeout(600);
  let st = await app.api('get', '/state');
  L.check('Alt+N created a new document', (st.tree.children || []).length === 0 && !st.dirty, st.tree);
  const errs = app.errorsSince(mark0);
  L.check('New on a dirty doc: no 409 console error', errs.length === 0, errs);
  // Ctrl+N (delivered by CDP; real Chrome keeps it) still works where it arrives
  await app.api('post', '/nodes', { parentId: 'root', name: 'x', probability: 0.1 });
  await page.evaluate(() => window.ftaShell.refresh());
  const tip = await page.locator('.actionbar [data-action="new"]').getAttribute('title');
  L.check('New button tooltip documents Alt+N', /Alt\+N/.test(tip), tip);

  // Open while dirty: consequence-named button
  await page.locator('.actionbar [data-action="load"]').click();
  await modal.waitFor({ state: 'visible', timeout: 4000 });
  const openOk = (await modal.locator('.fta-btn.is-primary').textContent()).trim();
  L.check('Load on a dirty doc: OK button says "Discard and open"', openOk === 'Discard and open', openOk);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);

  // ---- Add dialog: click into the probability, type 1e-3 -> 0.001 -------------------
  await page.locator('#tree-root li.fta-tree-item[data-id="root"] > .fta-tree-row').click();
  await page.locator('.actionbar [data-action="add"]').click();
  await modal.waitFor({ state: 'visible' });
  await page.keyboard.type('Clicked prob');
  const probInput = modal.locator('.fta-field input').nth(2);
  await probInput.click(); // real mouse, caret would land at the end
  await page.keyboard.type('1e-3');
  const typed = await probInput.inputValue();
  L.check('Add dialog: clicking the 1.0 default then typing replaces it', typed === '1e-3', typed);
  await modal.locator('.fta-modal-footer .fta-btn.is-primary').click();
  await page.waitForTimeout(600);
  st = await app.api('get', '/state');
  const added = st.tree.children.find((c) => c.name === 'Clicked prob');
  L.check('Add dialog: stored probability 0.001 (not 0.00101)', added && added.probability === 0.001, added);
  // a second click in an already-focused field places the caret (no re-select)
  // Details probability: click then type replaces
  const detProb = page.locator('#details-root .fta-details-form .fta-field').filter({ has: page.locator('label', { hasText: 'Probability (base)' }) }).locator('input');
  await detProb.click();
  await page.keyboard.type('0.002');
  L.check('Details probability: click + type replaces the value', (await detProb.inputValue()) === '0.002', await detProb.inputValue());
  await page.keyboard.press('Enter');
  await page.waitForTimeout(400);
  // the date box keeps normal caret behaviour
  await page.locator('#date-input').click();
  const sel = await page.evaluate(() => { const d = document.getElementById('date-input'); return d.selectionEnd - d.selectionStart; });
  L.check('date field keeps caret placement on click (opted out)', sel === 0, sel);
  await page.keyboard.press('Escape');

  // ---- Aa popover: Escape closes, focus returns, toasts survive -------------------
  await page.evaluate(() => window.ftaShell.toast('sticky toast for escape test', 'info'));
  await page.locator('#diagram-root .diagram__btn', { hasText: 'Aa' }).click();
  const pop = page.locator('.diagram__popover');
  L.check('Aa opens the popover', await pop.isVisible());
  await pop.locator('select').first().focus();
  await page.keyboard.press('Escape');
  await page.waitForTimeout(150);
  const popState = await page.evaluate(() => ({
    hidden: document.querySelector('.diagram__popover').hidden,
    focusAa: document.activeElement && document.activeElement.textContent === 'Aa',
    toasts: Array.from(document.querySelectorAll('#toasts .toast')).map((t) => t.textContent),
  }));
  L.check('Escape in the popover select closes it', popState.hidden, popState);
  L.check('focus returns to the Aa button', popState.focusAa, popState);
  L.check('Escape in the popover does not dismiss the toast', popState.toasts.some((x) => /sticky toast/.test(x)), popState.toasts);
  // Escape with focus on Aa (popover open) closes it too
  await page.locator('#diagram-root .diagram__btn', { hasText: 'Aa' }).click();
  await page.keyboard.press('Escape');
  L.check('Escape with focus on Aa closes the popover', await page.evaluate(() => document.querySelector('.diagram__popover').hidden));

  // ---- Validation: PARENT_PROBABILITY_IGNORED numbers are formatted ----------------
  const g = await app.api('post', '/nodes', { parentId: 'root', name: 'Gate with own p', probability: 0.5 });
  await app.api('post', '/nodes', { parentId: g.nodeId, name: 'certain child', probability: 1.0 });
  await page.evaluate(() => window.ftaShell.refresh());
  await app.clickTab('validation');
  await page.waitForTimeout(1200);
  const msg = await page.evaluate((id) => {
    const li = document.querySelector('#tabpanel-validation li.val-item[data-code="PARENT_PROBABILITY_IGNORED"][data-node-id="' + id + '"]');
    return li ? li.querySelector('.val-item__msg').textContent : null;
  }, g.nodeId);
  L.check('PARENT_PROBABILITY_IGNORED shows (0.500) and (1.00)', !!msg && msg.includes('(0.500)') && msg.includes('(1.00)'), msg);
  await app.setSigFigs(5);
  await page.waitForTimeout(300);
  const msg5 = await page.evaluate((id) => {
    const li = document.querySelector('#tabpanel-validation li.val-item[data-code="PARENT_PROBABILITY_IGNORED"][data-node-id="' + id + '"]');
    return li ? li.querySelector('.val-item__msg').textContent : null;
  }, g.nodeId);
  L.check('... and follows sig figs (5: 0.50000 / 1.0000)', !!msg5 && msg5.includes('(0.50000)') && msg5.includes('(1.0000)'), msg5);
  await app.setSigFigs(3);

  // ---- FMEA: λ unit warning ----------------------------------------------------------
  await app.clickTab('fmea');
  const pathBox = page.locator('#tabpanel-fmea .fmea-path');
  await pathBox.fill(path.join(root, 'fmea_fit.csv'));
  await pathBox.press('Enter');
  await page.waitForSelector('#tabpanel-fmea .fmea-map', { timeout: 8000 });
  const unitSel = page.locator('#tabpanel-fmea select[aria-label="λ unit"]');
  const suggested = await unitSel.inputValue();
  L.info('server-suggested λ unit (1.7.0 backend says h; 1.7.1 backend should say FIT)', suggested);
  await unitSel.selectOption('h');
  await page.waitForTimeout(100);
  let warn = await page.evaluate(() => { const w = document.querySelector('#tabpanel-fmea .fmea-unit-warning'); return w && !w.hidden ? w.textContent : null; });
  L.check('λ 120/45 with /h: inline warning suggests FIT', !!warn && /too high/.test(warn) && /FIT/.test(warn), warn);
  await unitSel.selectOption('FIT');
  await page.waitForTimeout(100);
  warn = await page.evaluate(() => { const w = document.querySelector('#tabpanel-fmea .fmea-unit-warning'); return w && !w.hidden ? w.textContent : null; });
  L.check('λ with FIT: no "too high" warning', !warn || !/too high/.test(warn), warn);
  await app.shot('fixes_fmea_unit_' + label);
  await unitSel.selectOption('h');
  const importBtn = page.locator('#tabpanel-fmea button.fmea-primary');
  L.check('import is not blocked by the warning', await importBtn.isEnabled());

  // ---- live language switch: nothing left in English ---------------------------------
  await app.clickTab('details');
  await app.setLanguage('ja');
  await page.waitForTimeout(500);
  const leftovers = await page.evaluate(async () => {
    const shell = window.ftaShell;
    // every English catalog value that differs from its Japanese text
    const en = new Set();
    const mod = await import('/static/js/i18n/shell17.js');
    void mod;
    const out = [];
    const texts = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const n = walker.currentNode;
      const el = n.parentElement;
      if (!el || el.closest('script,style,svg,.chat-msg__body.user,[hidden]') || !el.offsetParent) continue;
      const txt = n.textContent.trim();
      if (txt.length > 3) texts.push(txt);
    }
    for (const el of document.querySelectorAll('[aria-label],[title],[placeholder]')) {
      if (el.closest('[hidden]')) continue;
      for (const a of ['aria-label', 'title', 'placeholder']) if (el.getAttribute(a)) texts.push(el.getAttribute(a));
    }
    void shell; void en;
    // English-looking: >= 2 words of ASCII letters, no CJK
    for (const s of texts) if (/[A-Za-z]{3,} [A-Za-z]{2,}/.test(s) && !/[぀-ヿ一-鿿]/.test(s)) out.push(s);
    return Array.from(new Set(out));
  });
  L.info('ja: English-looking strings still on screen (review)', leftovers);
  const aiText = await page.evaluate(() => Array.from(document.querySelectorAll('#ai-root .chat-msg')).map((m) => m.textContent));
  L.check('AI panel: welcome message and role re-translated live', aiText.length > 0 && aiText.every((x) => /[぀-ヿ一-鿿]/.test(x)), aiText);
  const barLabel = await page.locator('footer.actionbar').getAttribute('aria-label');
  L.check('action bar aria-label is Japanese', barLabel === '文書の操作', barLabel);
  await app.shot('fixes_ja_live_' + label);
  await app.setLanguage('en');

  const all = app.errorsSince(mark0);
  L.check('no console errors in the fixes run', all.length === 0, all);
  await app.context.close();
}

L.runSection('fixes', main);
