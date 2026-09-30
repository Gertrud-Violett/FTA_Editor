// Misc GUI: Save As without extension, splitter keys, OS dark theme, sig-fig
// select by keyboard, basic-mode advanced gate chip, session-less tab.
// node s_misc.js <url> <label> <root>
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');
const { compareCore, flatten } = require('./b2b');

async function main(url, label, root) {
  L.setSection('misc[' + label + ']');
  let app = await L.openApp(url, { prefs: { 'fta.advanced': '1' }, viewport: { width: 1500, height: 950 } });
  let page = app.page;
  await app.api('post', '/file/open', { path: L.coreFile(root, label) });
  await page.evaluate(() => window.ftaShell.refresh());
  let st = await app.api('get', '/state');

  // Save As with a bare name -> .json added
  try { fs.unlinkSync(path.join(root, 'noext_' + label + '.json')); } catch (_e) { /* */ }
  await page.locator('.actionbar [data-action="save-as"]').click();
  await page.locator('.fta-filedialog').waitFor({ state: 'visible' });
  await page.locator('.fta-filedialog .fdlg-name').fill('noext_' + label);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(1000);
  st = await app.api('get', '/state');
  L.check('Save As "noext" writes noext.json', /noext_[^\\/]*\.json$/.test(st.currentPath || '') && fs.existsSync(path.join(root, 'noext_' + label + '.json')), st.currentPath);
  const pathShown = await page.locator('#statusline-path').textContent();
  L.check('status line shows the saved path', pathShown === st.currentPath, { pathShown, cp: st.currentPath });

  // splitter keyboard: ArrowRight widens the tree panel
  const w0 = (await page.locator('#tree-panel').boundingBox()).width;
  await page.locator('[data-splitter="tree"]').focus();
  for (let i = 0; i < 5; i += 1) await page.keyboard.press('ArrowRight');
  const w1 = (await page.locator('#tree-panel').boundingBox()).width;
  L.check(`tree splitter: ArrowRight x5 widens the tree (${Math.round(w0)} -> ${Math.round(w1)})`, w1 > w0 + 10, { w0, w1 });
  await compareCore(app, 'after splitter');

  // sig figs select by keyboard
  await page.locator('#sigfig-select').focus();
  await page.keyboard.press('ArrowDown');
  await page.waitForTimeout(300);
  const sfNow = await app.sf();
  L.check('sig figs select: ArrowDown moves 3 -> 4 and applies', sfNow === 4, sfNow);
  await compareCore(app, 'sig figs 4 by keyboard');
  await app.setSigFigs(3);

  // basic mode: an advanced gate is shown read-only with a chip
  const pumps = flatten(st.tree).find((n) => n.name === 'Pumps fail');
  await app.setAdvanced(false);
  await app.selectTreeNode(pumps.id);
  const g = await page.evaluate(() => {
    const s = document.querySelector('#details-root .fta-details-form select');
    const chip = document.querySelector('#details-root .fta-details-adv');
    return { disabled: s.disabled, value: s.value, chip: !!chip && !chip.hidden };
  });
  L.check('basic: KOFN gate read-only with the advanced chip, value kept', g.disabled && g.value === 'KOFN' && g.chip, g);
  // switching to basic while an advanced tab is open falls back to Details
  await app.setAdvanced(true);
  await app.clickTab('importance');
  await app.setAdvanced(false);
  const shown = await page.evaluate(() => Array.from(document.querySelectorAll('#bottom-tabs [role=tab][aria-selected=true]')).map((b) => b.dataset.tab));
  L.check('basic while on Importance: falls back to Details', JSON.stringify(shown) === '["details"]', shown);
  const ov = await page.evaluate(async () => (await import('/static/js/store.js')).store.overlay);
  L.check('basic: no FV overlay left', ov === null, ov);
  await app.setAdvanced(true);
  const back = await page.evaluate(() => Array.from(document.querySelectorAll('#bottom-tabs [role=tab][aria-selected=true]')).map((b) => b.dataset.tab));
  L.check('advanced again: the Importance tab comes back', JSON.stringify(back) === '["importance"]', back);
  const errs = app.errorsSince(0);
  L.check('no console errors (misc)', errs.length === 0, errs);
  await app.context.close();

  // OS dark theme with the theme toggle on "system"
  app = await L.openApp(url, { prefs: { 'fta.theme': 'system', 'fta.advanced': '1' }, colorScheme: 'dark' });
  page = app.page;
  await app.waitDiagram();
  const dark = await page.evaluate(() => ({
    attr: document.documentElement.getAttribute('data-theme'),
    bg: getComputedStyle(document.body).backgroundColor,
    svgBg: (() => { const p = document.querySelector('#diagram-root svg polygon'); return p ? p.getAttribute('fill') : null; })(),
  }));
  L.check('theme "system" + OS dark: dark page and dark diagram background', dark.attr === null && /rgb\((\d{1,2}), (\d{1,2}), (\d{1,2})\)/.test(dark.bg) && dark.svgBg && dark.svgBg.toLowerCase() !== '#ffffff' && dark.svgBg.toLowerCase() !== 'white', dark);
  await app.shot('misc_system_dark_' + label);
  await app.context.close();

  // a tab opened without the token: one clear blocking screen, no request storm
  const b = await L.getBrowser();
  const ctx = await b.newContext();
  const p2 = await ctx.newPage();
  const reqs = [];
  const errs2 = [];
  p2.on('request', (r) => { if (r.url().includes('/api/')) reqs.push(r.url()); });
  p2.on('console', (m) => { if (m.type() === 'error') errs2.push(m.text()); });
  await p2.goto(new URL(url).origin + '/');
  await p2.waitForTimeout(1500);
  const blocked = await p2.evaluate(() => !document.getElementById('blocking-overlay').hidden);
  L.check('tab without a session: blocking screen shown, no API request sent', blocked && reqs.length === 0, { blocked, reqs });
  L.check('tab without a session: no console errors', errs2.length === 0, errs2);
  await ctx.close();
}

L.runSection('misc', main);
