// An edit made while a tab's FIRST analysis run is still in flight must not
// leave that tab showing results for the old tree. The /analysis responses are
// delayed with page.route so the race is deterministic.
// node s_race.js <url> <label> <root>
'use strict';
const L = require('./lib');
const { flatten } = require('./b2b');

async function main(url, label, root) {
  L.setSection('race[' + label + ']');
  for (const tab of ['cutsets', 'importance']) {
    const app = await L.openApp(url, { prefs: { 'fta.advanced': '1' } });
    const { page } = app;
    await app.api('post', '/file/open', { path: L.coreFile(root, label) });
    await page.evaluate(() => window.ftaShell.refresh());
    const st = await app.api('get', '/state');
    const pa = flatten(st.tree).find((n) => n.name === 'Pump A fails');
    await app.selectTreeNode(pa.id);
    let delayed = 0;
    await page.route('**/api/analysis/' + tab, async (route) => {
      delayed += 1;
      // the server answers at once (old tree); the answer reaches the page late
      const response = await route.fetch();
      if (delayed === 1) await new Promise((r) => setTimeout(r, 2500)); // only the first run is slow
      await route.fulfill({ response });
    });
    await app.clickTab(tab); // first run starts, answer delayed 2.5 s
    await page.waitForTimeout(300);
    // edit while the first answer is still on its way (through the Details form? it is hidden:
    // use the tree rename, which stays visible)
    await page.locator('#tree-root li.fta-tree-item[data-id="' + pa.id + '"] > .fta-tree-row .fta-tree-label').dblclick();
    await page.keyboard.press('Control+A');
    await page.keyboard.type('Pump A renamed mid-run');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(4500);
    const api = await app.api('post', '/analysis/' + tab, tab === 'cutsets' ? { limit: 500 } : {});
    const gui = await page.evaluate((t) => {
      if (t === 'cutsets') return Array.from(document.querySelectorAll('#tabpanel-cutsets .anl-event')).map((e) => e.textContent);
      return Array.from(document.querySelectorAll('#tabpanel-importance tbody tr td:first-child')).map((e) => e.textContent);
    }, tab);
    const wantHas = true;
    void wantHas;
    const names = tab === 'cutsets' ? api.cutSets.flatMap((c) => c.events.map((e) => e.name)) : api.events.map((e) => e.name);
    L.check(`${tab}: an edit during the first (slow) run is reflected once it lands`, gui.includes('Pump A renamed mid-run') && JSON.stringify(gui) === JSON.stringify(names), { gui: gui.slice(0, 6), api: names.slice(0, 6), requests: delayed });
    await page.unroute('**/api/analysis/' + tab);
    const errs = app.errorsSince(0);
    L.check(`${tab}: no console errors`, errs.length === 0, errs);
    await app.api('post', '/undo', {});
    await app.context.close();
  }
}

L.runSection('race', main);
