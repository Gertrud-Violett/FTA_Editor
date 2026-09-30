// 300-node tree responsiveness. node s_big.js <url> <label> <root>
'use strict';
const L = require('./lib');
const { compareCore, flatten } = require('./b2b');

async function main(url, label) {
  L.setSection('big[' + label + ']');
  const app = await L.openApp(url, { prefs: { 'fta.advanced': '1' }, viewport: { width: 1600, height: 1000 } });
  const { page } = app;
  const dotCalls = [];
  page.on('request', (r) => { if (r.url().includes('/api/dot')) dotCalls.push(Date.now()); });
  // ~300 nodes: 6 subsystems x 7 modules x 6 components (+ gates)
  await app.api('post', '/new', { force: true });
  let count = 1;
  for (let i = 0; i < 6; i += 1) {
    const g = (await app.api('post', '/nodes', { parentId: 'root', name: 'Subsystem ' + i + ' failure with a rather long descriptive name', probability: 1, logicGate: i % 2 ? 'AND' : 'OR' })).nodeId;
    count += 1;
    for (let j = 0; j < 7; j += 1) {
      const g2 = (await app.api('post', '/nodes', { parentId: g, name: 'Module ' + i + '.' + j, probability: 1, logicGate: (i + j) % 2 ? 'AND' : 'OR' })).nodeId;
      count += 1;
      for (let m = 0; m < 6; m += 1) {
        await app.api('post', '/nodes', { parentId: g2, name: 'Component ' + i + '.' + j + '.' + m, probability: 1e-3 * (m + 1) });
        count += 1;
      }
    }
  }
  L.info('nodes', count);
  let t0 = Date.now();
  await page.evaluate(() => window.ftaShell.refresh());
  await app.waitDiagram(60000);
  L.info('refresh + diagram render (ms)', Date.now() - t0);
  const st = await app.api('get', '/state');
  // expand all and click a deep row
  const target = flatten(st.tree).find((n) => n.name === 'Component 3.4.2');
  await page.evaluate(async (id) => { const { store } = await import('/static/js/store.js'); store.jumpTo(id); }, target.id);
  await page.waitForTimeout(800);
  const nDot0 = dotCalls.length;
  const other = flatten(st.tree).find((n) => n.name === 'Component 3.4.3');
  t0 = Date.now();
  await page.locator('#tree-root li.fta-tree-item[data-id="' + other.id + '"] > .fta-tree-row').click();
  await page.waitForFunction((id) => document.querySelector('#details-root .fta-details-meta code').textContent === id, other.id);
  const selMs = Date.now() - t0;
  await page.waitForTimeout(1500);
  const dotOnSelect = dotCalls.length - nDot0;
  L.check(`300 nodes: click -> Details updated in ${selMs} ms (< 500)`, selMs < 500, selMs);
  L.check(`selecting a node does not re-fetch/re-layout the diagram (/api/dot calls: ${dotOnSelect})`, dotOnSelect === 0, dotOnSelect);
  // edit through details: diagram follows
  t0 = Date.now();
  await app.editDetailsField('Probability (base)', '0.25', 'enter');
  await app.waitDiagram(60000);
  L.info('edit -> diagram re-rendered (ms)', Date.now() - t0);
  await compareCore(app, '300 nodes after edit', { wait: 1500 });
  // add through the dialog
  t0 = Date.now();
  await app.addViaDialog({ name: 'Late addition', probability: '0.001' });
  const addMs = Date.now() - t0;
  L.check(`300 nodes: Add dialog round trip ${addMs} ms (< 3000)`, addMs < 3000, addMs);
  // tabs on a big tree
  for (const tab of ['cutsets', 'importance', 'validation', 'trace', 'quant']) {
    t0 = Date.now();
    await app.clickTab(tab);
    const sel = { cutsets: '#tabpanel-cutsets tbody tr', importance: '#tabpanel-importance tbody tr', validation: '#tabpanel-validation .val__chip', trace: '#tabpanel-trace tbody tr', quant: '#tabpanel-quant [data-section="events"] tbody tr' }[tab];
    await page.waitForSelector(sel, { timeout: 60000 });
    L.info(`${tab} tab first paint (ms)`, Date.now() - t0);
  }
  const cs = await app.api('post', '/analysis/cutsets', { limit: 500 });
  const rows = await page.evaluate(() => document.querySelectorAll('#tabpanel-cutsets tbody tr').length);
  L.check(`300 nodes: Cut Sets rows == API returned (${cs.returned})`, rows === cs.returned, { rows, returned: cs.returned, total: cs.total });
  // typing in the tree search stays responsive
  t0 = Date.now();
  await page.locator('#tree-root .fta-tree-search').fill('Component 5.6');
  await page.waitForFunction(() => document.querySelectorAll('#tree-root li.fta-tree-item').length < 20);
  L.info('tree search filter (ms)', Date.now() - t0);
  await page.locator('#tree-root .fta-tree-search').fill('');
  await app.shot('big_300_' + label);
  const errs = app.errorsSince(0);
  L.check('no console errors on the big tree', errs.length === 0, errs);
  await app.context.close();
}

L.runSection('big', main);
