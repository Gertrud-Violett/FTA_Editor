// Live language switch audit: mount every tab in English, switch to Japanese
// with the globe button, then look for English UI text left on screen
// (text, aria-label, title, placeholder), tab by tab. And back.
// node s_i18n.js <url> <label> <root>
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const TABS = ['details', 'quant', 'cutsets', 'importance', 'uncertainty', 'validation', 'trace', 'fmea', 'report'];

async function englishLeft(page, userTexts) {
  return page.evaluate((user) => {
    const out = new Set();
    const isVisible = (el) => !!el && el.getClientRects().length > 0 && !el.closest('[hidden]');
    const consider = (s, where) => {
      const txt = String(s || '').replace(/\s+/g, ' ').trim();
      if (!txt || user.some((u) => txt.includes(u))) return;
      if (/[぀-ヿ一-鿿]/.test(txt)) return;
      // English-looking: two or more words of 3+ letters (FTA/MCUB/λ/units excluded by length)
      if (/\b[A-Za-z]{3,}\b.*\b[A-Za-z]{3,}\b/.test(txt)) out.add(where + ': ' + txt.slice(0, 90));
    };
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const n = walker.currentNode;
      const el = n.parentElement;
      if (!el || el.closest('script,style,#diagram-root svg,.chat-msg--user,.chat-msg--assistant') || !isVisible(el)) continue;
      consider(n.textContent, 'text');
    }
    for (const el of document.querySelectorAll('[aria-label],[title],[placeholder]')) {
      if (!isVisible(el) || el.closest('#diagram-root svg')) continue;
      consider(el.getAttribute('aria-label'), 'aria');
      consider(el.getAttribute('title'), 'title');
      consider(el.getAttribute('placeholder'), 'placeholder');
    }
    return Array.from(out);
  }, userTexts);
}

async function main(url, label, root) {
  L.setSection('i18n[' + label + ']');
  const app = await L.openApp(url, { prefs: { 'fta.advanced': '1' }, viewport: { width: 1700, height: 1050 } });
  const { page } = app;
  await app.api('post', '/file/open', { path: L.coreFile(root, label) });
  await page.evaluate(() => window.ftaShell.refresh());
  const st = await app.api('get', '/state');
  const user = [];
  const walk = (n) => { user.push(n.name); if (n.notes) user.push(n.notes); for (const c of n.children || []) walk(c); };
  walk(st.tree);
  // the FMEA sheet s_files imports (written here too, so this section runs on its own)
  L.writeFmeaCsv(root);
  for (const cell of fs.readFileSync(path.join(root, 'b2b_fmea.csv'), 'utf8').split(/[\r\n,]+/)) if (cell.trim()) user.push(cell.trim());
  user.push(st.metadata.title, 'Cooling loss B2B', 'Graphviz', 'MCUB', 'b2b_', 'Gate: ', 'FMEA', 'Fussell', 'Birnbaum', 'Google Gemini', 'Monte Carlo', 'YYYY', 'WASM', 'REQ-');
  // mount everything in English first (incl. an uncertainty run and an FMEA preview)
  for (const id of TABS) {
    await app.clickTab(id);
    await page.waitForTimeout(700);
  }
  await app.clickTab('uncertainty');
  await page.locator('#tabpanel-uncertainty button[data-role="run"]').click();
  await page.waitForSelector('#tabpanel-uncertainty [data-stat="mean"]', { timeout: 60000 });
  await app.clickTab('fmea');
  const pathBox = page.locator('#tabpanel-fmea .fmea-path');
  await pathBox.fill(path.join(root, 'b2b_fmea.csv'));
  await pathBox.press('Enter');
  await page.waitForSelector('#tabpanel-fmea .fmea-map', { timeout: 8000 }).catch(() => {});
  await app.clickTab('details');
  // live switch
  await app.setLanguage('ja');
  await page.waitForTimeout(600);
  const report = {};
  for (const id of TABS) {
    await app.clickTab(id);
    await page.waitForTimeout(id === 'validation' ? 1200 : 500);
    report[id] = await englishLeft(page, user);
  }
  // the diagram popover
  await page.locator('#diagram-root .diagram__btn', { hasText: 'Aa' }).click();
  report.popover = (await englishLeft(page, user)).filter((s) => /Font|Style|Layout|Box|scale|Close|Detected/i.test(s));
  await page.keyboard.press('Escape');
  const all = Object.entries(report).filter(([, v]) => v.length);
  for (const [k, v] of all) L.info('ja after live switch, English left in ' + k, v);
  L.check('ja live switch: no English UI text left in any tab', all.length === 0, all.map(([k, v]) => k + ':' + v.length));
  await app.shot('i18n_live_ja_' + label);
  // and back to English: no Japanese left
  await app.setLanguage('en');
  await page.waitForTimeout(500);
  const jaLeft = [];
  for (const id of TABS) {
    await app.clickTab(id);
    await page.waitForTimeout(400);
    const left = await page.evaluate(() => {
      const out = new Set();
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        const el = walker.currentNode.parentElement;
        if (!el || el.getClientRects().length === 0 || el.closest('[hidden]')) continue;
        const txt = walker.currentNode.textContent.trim();
        if (/[぀-ヿ一-鿿]/.test(txt)) out.add(txt.slice(0, 80));
      }
      return Array.from(out);
    });
    if (left.length) jaLeft.push({ id, left });
  }
  L.check('en after switching back: no Japanese left', jaLeft.length === 0, jaLeft);
  const errs = app.errorsSince(0);
  L.check('no console errors in the i18n run', errs.length === 0, errs);
  await app.context.close();
}

L.runSection('i18n', main);
