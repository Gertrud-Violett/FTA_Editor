// Tree rows near the bottom of the panel select on the FIRST real click even
// when focus starts outside the tree (lead's finding: the focus hint used to
// shorten the list under the pressed button). node s_treeclick.js <url> <label> <root>
'use strict';
const path = require('path');
const L = require('./lib');

async function openSample(app, root) {
  const res = await app.api('post', '/file/open', { path: path.join(root, 'sampleFTA.json') });
  if (res.__error) throw new Error('open failed ' + JSON.stringify(res));
  await app.page.evaluate(() => window.ftaShell.refresh());
  await app.page.waitForTimeout(500);
}

async function visibleRows(page) {
  return page.evaluate(() => {
    const host = document.querySelector('#tree-root .fta-tree');
    const hr = host.getBoundingClientRect();
    return Array.from(host.querySelectorAll('li.fta-tree-item > .fta-tree-row'))
      .map((r) => ({ id: r.parentElement.dataset.id, rect: r.getBoundingClientRect().toJSON() }))
      .filter((x) => x.rect.top >= hr.top && x.rect.bottom <= hr.bottom && x.rect.height > 0)
      .map((x) => ({ id: x.id, y: x.rect.top + x.rect.height / 2, x: x.rect.left + Math.min(60, x.rect.width / 2) }));
  });
}

async function run(url, label, root, viewport) {
  L.setSection(`treeclick[${label} ${viewport.width}x${viewport.height}]`);
  const app = await L.openApp(url, { viewport });
  const { page } = app;
  await openSample(app, root);
  // expand everything so the list overflows
  await page.evaluate(() => {
    for (const li of document.querySelectorAll('#tree-root li.fta-tree-item[aria-expanded="false"]')) {
      li.querySelector('.fta-tree-twisty').click();
    }
  });
  await page.waitForTimeout(300);
  const rows = await visibleRows(page);
  L.check('several rows visible', rows.length >= 3, rows.length);
  const tail = rows.slice(-3);
  for (const target of tail.reverse()) {
    // focus starts OUTSIDE the tree: click the title box, then press Escape-free click elsewhere
    await page.locator('#title-input').click();
    await page.locator('#diagram-root .diagram__stage').click({ position: { x: 3, y: 3 } });
    const before = await app.selectedId();
    await page.mouse.move(target.x, target.y);
    await page.mouse.down();
    await page.waitForTimeout(80); // a human press lasts ~80 ms: long enough for a relayout
    await page.mouse.up();
    await page.waitForTimeout(250);
    const sel = await app.selectedId();
    const det = await app.details();
    L.check(`first click on bottom row ${target.id} selects it (was ${before})`, sel === target.id && det.id === target.id, { sel, det: det.id });
  }
  // hint: hidden for pointer focus, shown for keyboard focus
  let hint = await page.evaluate(() => getComputedStyle(document.querySelector('#tree-root .fta-tree-hint')).display);
  L.check('hint hidden after a mouse click in the tree', hint === 'none', hint);
  const h0 = await page.evaluate(() => document.querySelector('#tree-root .fta-tree').getBoundingClientRect().height);
  await page.keyboard.press('ArrowUp');
  await page.waitForTimeout(150);
  hint = await page.evaluate(() => getComputedStyle(document.querySelector('#tree-root .fta-tree-hint')).display);
  L.check('hint shown once the keyboard is used in the tree', hint === 'block', hint);
  const h1 = await page.evaluate(() => document.querySelector('#tree-root .fta-tree').getBoundingClientRect().height);
  L.check('showing the hint does not change the list height', Math.abs(h1 - h0) < 0.5, { h0, h1 });
  await page.keyboard.press('End');
  await page.waitForTimeout(200);
  const vis = await page.evaluate(() => {
    const host = document.querySelector('#tree-root .fta-tree');
    const hint = document.querySelector('#tree-root .fta-tree-hint');
    const f = document.activeElement.querySelector(':scope > .fta-tree-row') || document.activeElement;
    const a = f.getBoundingClientRect();
    const b = host.getBoundingClientRect();
    const h = hint.getBoundingClientRect();
    return { rowBottom: a.bottom, hintTop: h.top, listBottom: b.bottom, ok: a.bottom <= h.top + 1 && a.top >= b.top - 1 };
  });
  L.check('End: focused (last) row fully visible above the hint overlay', vis.ok, vis);
  // Tab from outside shows the hint (keyboard focus)
  await page.locator('#title-input').click();
  await page.locator('#tree-root .fta-tree-search').click();
  hint = await page.evaluate(() => getComputedStyle(document.querySelector('#tree-root .fta-tree-hint')).display);
  L.check('clicking the search box does not show the hint', hint === 'none', hint);
  await page.keyboard.press('Tab');
  await page.waitForTimeout(100);
  const act = await page.evaluate(() => document.activeElement && document.activeElement.className);
  hint = await page.evaluate(() => getComputedStyle(document.querySelector('#tree-root .fta-tree-hint')).display);
  L.info('after Tab focus on', act);
  // then a mouse click on the last visible row right after keyboard use
  const rows2 = await visibleRows(page);
  const last = rows2[rows2.length - 1];
  if (last) {
    await page.mouse.move(last.x, last.y);
    await page.mouse.down();
    await page.waitForTimeout(80);
    await page.mouse.up();
    await page.waitForTimeout(250);
  }
  // no row fully visible is a failure of this check, not an exception that
  // would skip the remaining window sizes
  L.check(`click on last row ${last ? last.id : '(none fully visible)'} right after keyboard use selects it`, !!last && (await app.selectedId()) === last.id, { selected: await app.selectedId(), visibleRows: rows2.length });
  const errs = app.errorsSince(0);
  L.check('no console errors', errs.length === 0, errs);
  await app.shot(`treeclick_${label}_${viewport.width}x${viewport.height}`);
  await app.context.close();
}

// The short window is 1366x600, not 560: with Linux fonts the top bar wraps to
// two lines at 1366 px, and at 560 px the tree list was ~70 px tall, fewer rows
// than this section needs and less than the three-line keyboard hint (56 px)
// covers. At 600 px Linux gets the ~112 px list Windows has at 560.
L.runSection('treeclick', async (url, label, root) => {
  for (const vp of [{ width: 1568, height: 778 }, { width: 1366, height: 600 }, { width: 900, height: 700 }]) {
    await run(url, label, root, vp);
  }
});
