// F2 performance budgets (criterion 29, PERF-3): the 301-node tree of F0 with
// ten beta-factor CCF groups (fixtures/perf_ccf_301.json), in a real browser.
// Click to Details under 500 ms, the Add dialog round trip under 3,000 ms, the
// CCF row of a member visible, the first paint of the Cut Sets, Validation and
// CCF groups tabs. The budgets depend on the machine, as in s_big.js.
//   node s_big_ccf.js <url> <label> <root>
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');
const { flatten } = require('./b2b');

const FIXTURE = path.join(L.REPO, 'fta_web', 'tests', 'fixtures', 'perf_ccf_301.json');

async function main(url, label, root) {
  L.setSection('bigccf[' + label + ']');
  const name = 'perf_ccf_301_' + label + '.json';
  fs.copyFileSync(FIXTURE, path.join(root, name));
  const app = await L.openApp(url, { prefs: { 'fta.advanced': '1' }, viewport: { width: 1600, height: 1000 } });
  const { page } = app;
  page.setDefaultTimeout(8000);
  const part = async (what, fn) => {
    try { await fn(); } catch (e) { L.check(what + ': did not complete', false, String((e && e.message) || e).split(String.fromCharCode(10))[0].slice(0, 300)); }
  };

  await app.api('post', '/new', { force: true });
  const opened = await app.api('post', '/file/open', { path: path.join(root, name), force: true });
  L.check('the 301-node CCF fixture opens', !opened.__error, opened.__error ? { status: opened.status, code: opened.code } : undefined);
  let t0 = Date.now();
  await page.reload();
  await L.waitBoot(page);
  await app.waitDiagram(60000);
  L.info('open + first diagram render (ms)', Date.now() - t0);
  const st = await app.api('get', '/state');
  const ids = new Set(flatten(st.tree).map((n) => String(n.id)));
  L.check('the fixture has its 301 nodes', ids.size === 301, ids.size);
  const grp = await app.api('get', '/ccf/groups');
  const members = new Set();
  for (const g of grp.groups || []) for (const m of g.members || []) members.add(m);
  L.check('the API lists the ten groups of the fixture, all applied', (grp.groups || []).length === 10 && grp.groups.every((g) => g.status && g.status.applied === true), (grp.groups || []).length);
  await page.waitForTimeout(1500); // the headline and the CCF state of this tree are loaded

  const selectAndTime = async (id, extraWait) => {
    await page.evaluate(async (nid) => { const { store } = await import('/static/js/store.js'); store.jumpTo(nid); }, id);
    await page.waitForTimeout(extraWait || 600);
    const t = Date.now();
    await page.locator('#tree-root li.fta-tree-item[data-id="' + id + '"] > .fta-tree-row').click();
    await page.waitForFunction((nid) => { const c = document.querySelector('#details-root .fta-details-meta code'); return c && c.textContent === nid; }, id);
    return Date.now() - t;
  };

  await part('click to Details', async () => {
    const ms1 = await selectAndTime('C0_1_3');
    const ms2 = await selectAndTime('C0_1_4');
    L.check(`301 nodes: click on a non-member -> Details updated in ${ms1} ms (< 500)`, ms1 < 500, ms1);
    L.check(`301 nodes: a second click -> Details updated in ${ms2} ms (< 500)`, ms2 < 500, ms2);
  });

  await part('member row', async () => {
    L.check('C0_1_0 is a member of a group', members.has('C0_1_0'), [...members].slice(0, 3));
    const ms = await selectAndTime('C0_1_0');
    L.check(`301 nodes: click on a member -> Details updated in ${ms} ms (< 500)`, ms < 500, ms);
    const t = Date.now();
    await page.waitForSelector('#details-root .fta-details-ccf [data-ccf="qt"]', { state: 'visible', timeout: 3000 });
    const shownMs = ms + (Date.now() - t);
    const ccf = await page.evaluate(() => {
      const r = document.querySelector('#details-root .fta-details-ccf');
      const o = { shown: Boolean(r) && !r.hidden && r.offsetParent !== null };
      if (r) r.querySelectorAll('[data-ccf]').forEach((e) => { o[e.dataset.ccf] = e.textContent.trim(); });
      return o;
    });
    L.check('301 nodes: the CCF row is visible for a member of a group (Q_t, independent part)', ccf.shown && Boolean(ccf.qt) && Boolean(ccf.independent) && ccf.qt !== '—', ccf);
    L.check(`301 nodes: ... within 500 ms of the click (${shownMs} ms)`, shownMs < 500, shownMs);
    await selectAndTime('C0_1_3');
    const hidden = await page.evaluate(() => { const r = document.querySelector('#details-root .fta-details-ccf'); return !r || r.hidden || r.offsetParent === null; });
    L.check('301 nodes: the CCF row is not shown for a non-member', hidden);
  });

  await part('Add dialog', async () => {
    await selectAndTime('M0_0');
    t0 = Date.now();
    await app.addViaDialog({ name: 'Late addition', probability: '0.001' });
    const addMs = Date.now() - t0;
    L.check(`301 nodes: Add dialog round trip ${addMs} ms (< 3000)`, addMs < 3000, addMs);
  });

  for (const [tab, sel] of [
    ['cutsets', '#tabpanel-cutsets tbody tr[data-rank]'],
    ['validation', '#tabpanel-validation .val__chip'],
    ['ccf', '#tabpanel-ccf [data-role="groups"] tbody tr[data-id]'],
  ]) {
    await part(tab + ' tab', async () => {
      t0 = Date.now();
      await app.clickTab(tab);
      await page.waitForSelector(sel, { timeout: 60000 });
      L.info(`${tab} tab first paint (ms)`, Date.now() - t0);
      L.check(`301 nodes: the ${tab} tab paints`, true);
    });
  }
  await part('CCF tab rows', async () => {
    const n = await page.evaluate(() => document.querySelectorAll('#tabpanel-ccf [data-role="groups"] tbody tr[data-id]').length);
    L.check('301 nodes: the CCF groups tab lists the ten groups', n === 10, n);
  });
  await part('Cut Sets rows', async () => {
    await app.clickTab('cutsets');
    await page.waitForSelector('#tabpanel-cutsets tbody tr[data-rank]', { timeout: 60000 });
    const events = await page.evaluate(() => new Set(Array.from(document.querySelectorAll('#tabpanel-cutsets .anl-event[data-ccf-role="event"]')).map((e) => e.dataset.ccfGroup)).size);
    L.check('301 nodes: the Cut Sets tab shows CCF events', events > 0, events);
  });
  await app.shot('big_ccf_301_' + label);
  const errs = app.errorsSince(0);
  L.check('no console errors on the big CCF tree', errs.length === 0, errs.slice(0, 5));
  await app.context.close();
}

L.runSection('bigccf', main);
