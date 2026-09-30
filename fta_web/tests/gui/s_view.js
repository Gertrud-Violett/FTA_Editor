// Look & feel: every tab in en/light and ja/dark (screenshots), window sizes,
// keyboard-only flows, drag & drop, the AI panel without credentials.
// node s_view.js <url> <label> <root>
'use strict';
const L = require('./lib');
const { compareCore, flatten } = require('./b2b');

const TABS = ['details', 'quant', 'cutsets', 'importance', 'uncertainty', 'validation', 'trace', 'fmea', 'report'];

async function openCore(app, root, label) {
  const res = await app.api('post', '/file/open', { path: L.coreFile(root, label) });
  await app.page.evaluate(() => window.ftaShell.refresh());
  return res;
}

async function main(url, label, root) {
  L.setSection('view[' + label + ']');
  let app = await L.openApp(url, { prefs: { 'fta.advanced': '1' }, viewport: { width: 1600, height: 1000 } });
  let { page } = app;
  await openCore(app, root, label);
  let st = await app.api('get', '/state');
  const byName = (name) => flatten(st.tree).find((n) => n.name === name);
  await app.selectTreeNode(byName('Pump C fails').id);

  // ---- every tab, en/light then ja/dark ----------------------------------------------
  for (const [lang, theme] of [['en', 'light'], ['ja', 'dark']]) {
    await app.setLanguage(lang);
    await app.setTheme(theme);
    for (const id of TABS) {
      await app.clickTab(id);
      await page.waitForTimeout(id === 'cutsets' || id === 'importance' || id === 'validation' ? 1200 : 500);
      if (id === 'uncertainty') {
        await page.locator('#tabpanel-uncertainty button[data-role="run"]').click();
        await page.waitForSelector('#tabpanel-uncertainty [data-stat="mean"]', { timeout: 60000 });
      }
      const ok = await page.evaluate((tid) => {
        const p = document.getElementById('tabpanel-' + tid);
        return !p.hidden && p.textContent.trim().length > 0 && !/could not be loaded|読み込めません/.test(p.textContent);
      }, id);
      L.check(`${lang}/${theme}: ${id} tab renders`, ok);
      await app.shot(`tab_${id}_${lang}_${theme}_${label}`);
    }
    const raw = await page.evaluate(() => {
      const m = document.body.innerText.match(/\b(?:anl|cutsets|imp|unc|val|trace|fmea|report|gate|diagram17|tab|headline|quant|ai|tree|details|dialog|links|msg)\.[a-zA-Z0-9_.]+\b/g);
      return m ? Array.from(new Set(m)) : [];
    });
    L.check(`${lang}: no raw i18n keys on screen`, raw.length === 0, raw);
  }
  await compareCore(app, 'ja/dark');
  await app.setLanguage('en');
  await app.setTheme('light');

  // ---- keyboard-only: tab strip arrows, Home/End ----------------------------------------
  await page.locator('#tab-details').focus();
  await page.keyboard.press('ArrowRight');
  let act = await page.evaluate(() => document.activeElement.id);
  L.check('tab strip: ArrowRight moves to Quantification', act === 'tab-quant' && await page.evaluate(() => !document.getElementById('tabpanel-quant').hidden), act);
  await page.keyboard.press('End');
  act = await page.evaluate(() => document.activeElement.id);
  L.check('tab strip: End goes to Report', act === 'tab-report', act);
  await page.keyboard.press('Home');
  await page.keyboard.press('ArrowLeft');
  act = await page.evaluate(() => document.activeElement.id);
  L.check('tab strip: ArrowLeft from the first wraps to the last', act === 'tab-report', act);
  await app.setAdvanced(false);
  await page.locator('#tab-details').focus();
  await page.keyboard.press('ArrowRight');
  act = await page.evaluate(() => document.activeElement.id);
  L.check('basic mode: ArrowRight skips hidden tabs (Details -> Validation)', act === 'tab-validation', act);
  await app.setAdvanced(true);

  // keyboard-only tree navigation + Enter select + F2 rename + Escape cancel
  await page.locator('#tree-root li.fta-tree-item[data-id="' + st.tree.id + '"] > .fta-tree-row').click();
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('ArrowDown');
  let sel = await app.selectedId();
  L.check('tree: ArrowDown x2 selects the second child in visible order', sel === byName('Pump A fails').id, sel);
  await page.keyboard.press('F2');
  await page.keyboard.type(' (renamed)');
  await page.keyboard.press('Escape');
  st = await app.api('get', '/state');
  L.check('tree: F2 + Escape does not rename', !!byName('Pump A fails'), flatten(st.tree).map((n) => n.name));
  await page.keyboard.press('F2');
  await page.keyboard.press('End');
  await page.keyboard.type(' X');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
  st = await app.api('get', '/state');
  L.check('tree: F2 + type + Enter renames on the server', !!byName('Pump A fails X'), flatten(st.tree).map((n) => n.name));
  await page.keyboard.press('Control+Z');
  await page.waitForTimeout(500);
  st = await app.api('get', '/state');
  L.check('Ctrl+Z (focus in tree) undoes the rename', !!byName('Pump A fails'));
  await compareCore(app, 'after keyboard rename + undo');

  // ---- drag & drop in the tree (real mouse) -----------------------------------------------
  const src = byName('Operator error (late)');
  const dst = byName('Power loss');
  const a = await page.locator('#tree-root li.fta-tree-item[data-id="' + src.id + '"] > .fta-tree-row').boundingBox();
  const b = await page.locator('#tree-root li.fta-tree-item[data-id="' + dst.id + '"] > .fta-tree-row').boundingBox();
  await page.locator('#tree-root li.fta-tree-item[data-id="' + src.id + '"] > .fta-tree-row').dragTo(
    page.locator('#tree-root li.fta-tree-item[data-id="' + dst.id + '"] > .fta-tree-row'), { targetPosition: { x: 30, y: b.height / 2 } });
  void a;
  await page.waitForTimeout(800);
  st = await app.api('get', '/state');
  const moved = flatten(st.tree).find((n) => n.name === 'Operator error (late)');
  const parent = flatten(st.tree).find((n) => (n.children || []).some((c) => c.id === moved.id));
  L.check('drag & drop re-parents Operator error under Power loss (server)', parent && parent.name === 'Power loss', parent && parent.name);
  await compareCore(app, 'after drag & drop');
  await page.locator('#btn-undo').click();
  await page.waitForTimeout(600);
  st = await app.api('get', '/state');
  L.check('undo button reverts the drag', st.tree.children.some((c) => c.name === 'Operator error (late)'));
  await compareCore(app, 'after drag undo');

  // ---- AI panel with no credentials ----------------------------------------------------------
  const mark = app.errMark();
  const invite = await page.evaluate(() => { const r = document.getElementById('ai-root'); return r.textContent.slice(0, 200); });
  L.info('AI panel', invite);
  const aiState = await app.api('get', '/state');
  L.check('server reports aiConfigured=false (isolated home)', aiState.aiConfigured === false, aiState.aiConfigured);
  const inputBox = page.locator('#ai-root textarea');
  if (await inputBox.count()) {
    await inputBox.click();
    await page.keyboard.type('Why is the top event so high?');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(1500);
  }
  const analyze = page.locator('#ai-root button', { hasText: /Analyze FTA/ });
  if (await analyze.count() && await analyze.isEnabled()) { await analyze.click(); await page.waitForTimeout(1500); }
  const log = await page.evaluate(() => Array.from(document.querySelectorAll('#ai-root .chat-msg')).map((m) => m.dataset.role + ': ' + m.textContent.slice(0, 120)));
  L.info('AI log', log);
  const aiErrs = app.errorsSince(mark);
  L.check('AI without credentials: fails gracefully (no console errors, a message in the log)', aiErrs.filter((e) => e.type !== 'http').length === 0 && log.length >= 1, { aiErrs, log });
  // settings dialog opens and closes with Escape
  await page.locator('#btn-ai-settings').click();
  await page.waitForTimeout(600);
  const dlg = await page.locator('.fta-modal').count();
  L.check('AI settings dialog opens', dlg > 0);
  await app.shot('ai_settings_nocreds_' + label);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  L.check('AI settings closes on Escape', (await page.locator('.fta-modal').count()) === 0);
  L.check('no console errors from the AI panel', app.errorsSince(mark).filter((e) => e.type !== 'http').length === 0, app.errorsSince(mark));
  L.info('AI http errors (deliberately provoked, expected 4xx)', app.errorsSince(mark).filter((e) => e.type === 'http').map((e) => e.text.slice(0, 160)));
  const before = app.errors.length;
  void before;
  await app.context.close();

  // ---- window sizes ---------------------------------------------------------------------
  for (const vp of [{ width: 1920, height: 1080 }, { width: 1366, height: 768 }, { width: 900, height: 800 }, { width: 420, height: 860 }]) {
    app = await L.openApp(url, { prefs: { 'fta.advanced': '1' }, viewport: vp });
    page = app.page;
    await openCore(app, root, label);
    await app.waitDiagram();
    const lay = await page.evaluate(() => {
      const se = document.scrollingElement;
      const vis = (sel) => { const e = document.querySelector(sel); if (!e) return false; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
      return {
        hScroll: se.scrollWidth > window.innerWidth + 1,
        scrollWidth: se.scrollWidth,
        innerWidth: window.innerWidth,
        tree: vis('#tree-root'), diagram: vis('#diagram-root'), details: vis('#details-root'), bar: vis('.actionbar'), headline: vis('#headline-value'),
      };
    });
    L.check(`${vp.width}x${vp.height}: no horizontal page scroll`, !lay.hScroll, lay);
    L.check(`${vp.width}x${vp.height}: tree, diagram, details, action bar and headline visible`, lay.tree && lay.diagram && lay.details && lay.bar && lay.headline, lay);
    // select a node by clicking the tree and see Details follow
    const id = flatten((await app.api('get', '/state')).tree)[2].id;
    await app.selectTreeNode(id);
    const det = await app.details();
    L.check(`${vp.width}x${vp.height}: click in the tree drives Details`, det.id === id, det.id);
    await compareCore(app, `${vp.width}x${vp.height}`);
    await app.shot(`size_${vp.width}x${vp.height}_${label}`);
    const e2 = app.errorsSince(0);
    L.check(`${vp.width}x${vp.height}: no console errors`, e2.length === 0, e2);
    await app.context.close();
  }
}

L.runSection('view', main);
