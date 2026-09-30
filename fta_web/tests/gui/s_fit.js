// Auto-fit never enlarges past 100% (lead's finding). node s_fit.js <url> [label]
'use strict';
const L = require('./lib');

async function zoomPct(app) {
  return app.page.evaluate(() => parseInt(document.querySelector('#diagram-root .diagram__zoom').textContent, 10));
}

async function run(url, label) {
  L.setSection('fit[' + label + ']');
  const app = await L.openApp(url, { viewport: { width: 2542, height: 1261 } });
  const { page } = app;
  await app.api('post', '/new', { force: true });
  await page.evaluate(() => window.ftaShell.refresh());
  await app.waitDiagram();
  let z = await zoomPct(app);
  L.check('1-node doc on 2542x1261: auto-fit zoom <= 100%', z <= 100, z);
  // Fit button: same rule
  await page.locator('#diagram-root .diagram__btn', { hasText: '⤢' }).click();
  await page.waitForTimeout(200);
  z = await zoomPct(app);
  L.check('Fit button on a 1-node doc: zoom <= 100%', z <= 100, z);
  // Ctrl+0 in the stage
  await page.locator('#diagram-root .diagram__stage').click({ position: { x: 5, y: 5 } });
  await page.keyboard.press('Control+0');
  await page.waitForTimeout(200);
  z = await zoomPct(app);
  L.check('Ctrl+0 on a 1-node doc: zoom <= 100%', z <= 100, z);
  // title text size on screen: the graph label must not be giant
  const fontPx = await page.evaluate(() => {
    const svg = document.querySelector('#diagram-root .diagram__canvas svg');
    const texts = Array.from(svg.querySelectorAll('text'));
    return Math.max(...texts.map((t) => t.getBoundingClientRect().height));
  });
  L.check('largest diagram text is < 40px tall on screen', fontPx < 40, fontPx);
  await app.shot('fit_1node_' + label);
  // manual zoom in still works beyond 100%
  for (let i = 0; i < 5; i += 1) await page.locator('#diagram-root .diagram__btn', { hasText: '+' }).click();
  z = await zoomPct(app);
  L.check('+ button still zooms past 100%', z > 100, z);
  // a big tree still shrinks to fit
  await page.evaluate(async () => {
    const { api } = await import('/static/js/api.js');
    for (let i = 0; i < 25; i += 1) await api.post('/nodes', { parentId: 'root', name: 'Event number ' + i, probability: 0.01 });
    await window.ftaShell.refresh();
  });
  await page.locator('#diagram-root .diagram__btn', { hasText: '⤢' }).click();
  await app.waitDiagram();
  z = await zoomPct(app);
  L.check('26-node tree: fit shrinks below 100%', z < 100, z);
  const errs = app.errorsSince(0);
  L.check('no console errors', errs.length === 0, errs);
  await app.context.close();
}

L.runSection('fit', run);
