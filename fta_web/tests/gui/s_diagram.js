// Diagram: compact/symbols x LR/TB -- numbers equal the API and each other,
// real-mouse click on every shape selects its node, zoom/fit, dark theme.
// node s_diagram.js <url> <label> <root>
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');
const { compareCore, dotIdMap, flatten, labelNumbers } = require('./b2b');

async function setStyle(page, style, rankdir) {
  await page.locator('#diagram-root .diagram__btn', { hasText: 'Aa' }).click();
  const pop = page.locator('.diagram__popover');
  await pop.locator('select').nth(0).selectOption(style);
  await pop.locator('select').nth(1).selectOption(rankdir);
  await page.keyboard.press('Escape');
}

async function main(url, label, root) {
  L.setSection('diagram[' + label + ']');
  const app = await L.openApp(url, { prefs: { 'fta.advanced': '1' }, viewport: { width: 1700, height: 1000 } });
  const { page } = app;
  const res = await app.api('post', '/file/open', { path: L.coreFile(root, label) });
  L.check('opened core file', !res.__error, res);
  await page.evaluate(() => window.ftaShell.refresh());
  const st = await app.api('get', '/state');
  const nodes = flatten(st.tree);
  const perStyle = {};
  for (const [style, rankdir] of [['compact', 'LR'], ['compact', 'TB'], ['symbols', 'LR'], ['symbols', 'TB']]) {
    await setStyle(page, style, rankdir);
    await app.waitDiagram();
    const tag = style + '/' + rankdir;
    await compareCore(app, tag);
    const { idMap } = await dotIdMap(app);
    const dn = await app.diagramNodes();
    const nums = {};
    for (const g of dn) {
      const id = idMap[g.title];
      if (!id || (/\bfta-(gate|event)\b/.test(g.cls) && !/conditioning/.test(g.cls))) continue;
      nums[id] = labelNumbers(g.texts).calc;
    }
    perStyle[tag] = nums;
    // click every node shape (main box AND gate symbols) with the real mouse
    const targets = await page.evaluate(() => {
      const out = [];
      document.querySelectorAll('#diagram-root .diagram__canvas svg g.node').forEach((g, i) => {
        const shape = g.querySelector('polygon, ellipse, path, rect');
        const r = (shape || g).getBoundingClientRect();
        const stage = document.querySelector('#diagram-root .diagram__stage').getBoundingClientRect();
        const cx = r.left + r.width / 2;
        const cy = r.top + Math.min(r.height / 2, 12);
        if (cx > stage.left && cx < stage.right && cy > stage.top && cy < stage.bottom) out.push({ i, title: g.querySelector('title').textContent.trim(), x: cx, y: cy, cls: g.getAttribute('class') });
      });
      return out;
    });
    const bad = [];
    for (const tg of targets) {
      const want = idMap[tg.title];
      if (!want) continue;
      // start from another node so a no-op click is detected
      await page.evaluate(async () => { const { store } = await import('/static/js/store.js'); store.select(null); });
      await page.mouse.click(tg.x, tg.y);
      await page.waitForTimeout(60);
      const sel = await app.selectedId();
      if (sel !== want) bad.push({ tg, want, sel });
    }
    L.check(`${tag}: real-mouse click on ${targets.length} shapes selects the mapped node`, bad.length === 0 && targets.length > 0, bad.slice(0, 4));
    await app.shot(`diagram_${style}_${rankdir}_${label}`, { locator: '#diagram-root' });
  }
  // symbols and compact show the same numbers
  const tags = Object.keys(perStyle);
  const ref = perStyle[tags[0]];
  const mism = [];
  for (const tg of tags.slice(1)) for (const id of Object.keys(ref)) if (perStyle[tg][id] !== ref[id]) mism.push({ tg, id, a: ref[id], b: perStyle[tg][id] });
  L.check(`compact vs symbols (LR/TB) show identical P_calc/Q for ${Object.keys(ref).length} nodes`, mism.length === 0 && Object.keys(ref).length === nodes.length, mism.slice(0, 4));

  fs.writeFileSync(path.join(L.OUT, 'diagram_' + label + '.json'), JSON.stringify(perStyle, null, 1));
  // pan must not select; zoom buttons; ctrl+wheel; fit
  await setStyle(page, 'compact', 'LR');
  await app.waitDiagram();
  const zoom = () => page.evaluate(() => parseInt(document.querySelector('#diagram-root .diagram__zoom').textContent, 10));
  const z0 = await zoom();
  await page.locator('#diagram-root .diagram__btn', { hasText: '+' }).click();
  const z1 = await zoom();
  L.check('zoom + button increases zoom', z1 > z0, { z0, z1 });
  const stage = await page.locator('#diagram-root .diagram__stage').boundingBox();
  await page.mouse.move(stage.x + stage.width / 2, stage.y + stage.height / 2);
  await page.keyboard.down('Control');
  await page.mouse.wheel(0, 300);
  await page.keyboard.up('Control');
  await page.waitForTimeout(150);
  const z2 = await zoom();
  L.check('Ctrl+wheel down zooms out', z2 < z1, { z1, z2 });
  const before = await app.selectedId();
  const g = await page.evaluate(() => { const r = document.querySelector('#diagram-root svg g.node polygon').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  await page.mouse.move(g.x, g.y);
  await page.mouse.down();
  await page.mouse.move(g.x + 60, g.y + 40, { steps: 5 });
  await page.mouse.up();
  L.check('a drag (pan) that starts on a node does not select it', (await app.selectedId()) === before, { before, now: await app.selectedId() });
  await page.locator('#diagram-root .diagram__btn', { hasText: '⤢' }).click();
  const zf = await zoom();
  L.check('Fit brings the zoom back to <= 100%', zf <= 100, zf);

  // dark theme re-renders the diagram with a dark background
  await app.setTheme('dark');
  await app.waitDiagram();
  const bg = await page.evaluate(() => { const p = document.querySelector('#diagram-root svg polygon'); return p ? p.getAttribute('fill') : null; });
  L.info('dark diagram background polygon fill', bg);
  await compareCore(app, 'dark theme');
  await app.shot('diagram_dark_' + label, { locator: '#diagram-root' });
  await app.setTheme('light');

  // hide zero: zero nodes vanish from the diagram and the tree
  const errs = app.errorsSince(0);
  L.check('no console errors in the diagram run', errs.length === 0, errs);
  await app.context.close();
}

L.runSection('diagram', main);
