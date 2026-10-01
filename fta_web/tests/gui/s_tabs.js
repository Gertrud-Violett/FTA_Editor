// Analysis tabs back-to-back: every value the tab shows vs the API.
// Uses the GUI-built file from s_core (b2b_core_<label>.json).
// node s_tabs.js <url> <label> <root>
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');
const { compareCore, flatten } = require('./b2b');

const pctText = (share) => { const p = (share || 0) * 100; return p.toFixed(p >= 10 ? 1 : 2) + '%'; };

async function readCutsetsTab(page) {
  return page.evaluate(() => {
    const p = document.getElementById('tabpanel-cutsets');
    const rows = Array.from(p.querySelectorAll('tbody tr[data-rank]')).map((tr) => {
      const td = tr.querySelectorAll('td');
      return {
        rank: td[0].textContent, order: td[1].textContent,
        events: Array.from(td[2].querySelectorAll('.anl-event')).map((e) => e.textContent),
        prob: td[3].textContent, share: td[4].textContent,
      };
    });
    const stats = Array.from(p.querySelectorAll('.anl-summary .anl-stat')).map((s) => s.textContent);
    return { rows, stats };
  });
}

async function readImportanceTab(page) {
  return page.evaluate(() => {
    const p = document.getElementById('tabpanel-importance');
    return {
      rows: Array.from(p.querySelectorAll('tbody tr[data-id]')).map((tr) => {
        const td = tr.querySelectorAll('td');
        return { id: tr.dataset.id, name: td[0].textContent, q: td[1].textContent, fv: td[2].textContent, birnbaum: td[3].textContent, raw: td[4].textContent, rrw: td[5].textContent, n: td[6].textContent };
      }),
      basis: (p.querySelector('p.anl-note') || {}).textContent || '',
    };
  });
}

async function main(url, label, root) {
  L.setSection('tabs[' + label + ']');
  const app = await L.openApp(url, { prefs: { 'fta.advanced': '1' }, viewport: { width: 1600, height: 1050 } });
  const { page } = app;
  const snap = { label, cutsets: {}, importance: {}, unc: {}, quant: {}, validation: {}, trace: {} };

  // Open the GUI-built file through Load + file dialog
  await page.locator('.actionbar [data-action="load"]').click();
  await page.waitForTimeout(300);
  if (await page.locator('.fta-modal:not(.fta-filedialog)').count()) await page.locator('.fta-modal:not(.fta-filedialog) .fta-btn.is-primary').click();
  await page.locator('.fta-filedialog').waitFor({ state: 'visible' });
  await page.locator('.fta-filedialog .fdlg-row', { hasText: 'b2b_core_' + label + '.json' }).dblclick();
  await page.waitForTimeout(1000);
  let st = await app.api('get', '/state');
  L.check('opened the GUI-built core file', /b2b_core_/.test(st.currentPath || ''), st.currentPath);
  const byName = (s, name) => flatten(s.tree).find((n) => n.name === name);

  // ---- Quantification tab: rate model through the form --------------------------
  const pc = byName(st, 'Pump C fails');
  await app.selectTreeNode(pc.id);
  await app.clickTab('quant');
  await page.waitForSelector('#tabpanel-quant select[data-field="model"]', { timeout: 8000 });
  await page.locator('#tabpanel-quant select[data-field="model"]').selectOption('rate');
  await page.waitForSelector('#tabpanel-quant input[data-field="lambda"]', { timeout: 8000 });
  await page.locator('#tabpanel-quant select[data-field="lambdaUnit"]').selectOption('FIT');
  await page.waitForTimeout(300);
  const lam = page.locator('#tabpanel-quant input[data-field="lambda"]');
  await lam.click();
  await page.keyboard.press('Control+A');
  await page.keyboard.type('5000');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(700);
  await page.locator('#tabpanel-quant select[data-field="uncDist"]').selectOption('lognormal');
  await page.waitForTimeout(700);
  // mission time 1000 h through the doc section
  const mt = page.locator('#tabpanel-quant input[data-field="missionTime"]');
  await mt.click();
  await page.keyboard.press('Control+A');
  await page.keyboard.type('1000');
  await page.keyboard.press('Tab');
  await page.waitForTimeout(900);
  st = await app.api('get', '/state');
  const pcNow = byName(st, 'Pump C fails');
  L.check('quant form stored rate model λ=5000 FIT = 5e-6/h', pcNow.quant && pcNow.quant.model === 'rate' && Math.abs(pcNow.quant.lambda - 5e-6) < 1e-18, pcNow.quant);
  L.check('mission time stored as 1000 h', st.analysis && st.analysis.missionTime === 1000, st.analysis);
  const view = await app.api('get', '/nodes/' + pcNow.id);
  const qd = view.node.quantDerived;
  await page.waitForTimeout(400);
  const guiDerived = await page.evaluate(() => {
    const d = document.querySelector('#tabpanel-quant .anl-derived');
    return d ? { q: d.querySelector('b').textContent, formula: d.querySelector('.anl-mono').textContent } : null;
  });
  const sf = await app.sf();
  L.check(`Quant derived q ${guiDerived && guiDerived.q} == quantDerived.q ${L.fmt(qd.q, sf)}`, guiDerived && guiDerived.q === L.fmt(qd.q, sf), { guiDerived, qd });
  L.check('Quant formula == quantDerived.formula', guiDerived && guiDerived.formula === (qd.formula || ''), { guiDerived, qd });
  snap.quant = guiDerived;
  const qTable = await page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-quant [data-section="events"] tbody tr')).map((tr) => ({ id: tr.dataset.id, q: tr.lastElementChild.textContent, lam: tr.children[2].textContent })));
  const leaves = flatten(st.tree).filter((n) => !(n.children || []).length && n.id !== st.tree.id);
  const qBad = qTable.filter((r) => { const n = flatten(st.tree).find((x) => String(x.id) === r.id); return !n || r.q !== L.fmt(n.probability, sf); });
  L.check(`Quant events table q == node probability for ${qTable.length} events`, qTable.length === leaves.length && qBad.length === 0, { qBad, n: qTable.length, leaves: leaves.length });
  await compareCore(app, 'after quant edits');
  // details panel also shows the derived probability read-only
  await app.clickTab('details');
  const det = await app.details();
  const pf = det.fields['Probability (base)'];
  L.check('Details: derived probability read-only and == API at sig figs', pf && pf.readOnly && pf.value === L.fmt(pcNow.probability, sf), pf);

  // ---- Cut sets tab ------------------------------------------------------------------
  await app.clickTab('cutsets');
  await page.waitForSelector('#tabpanel-cutsets tbody tr[data-rank]', { timeout: 15000 });
  await app.settle(500);
  const csApi = await app.api('post', '/analysis/cutsets', { limit: 500 });
  let gui = await readCutsetsTab(page);
  const csBad = [];
  csApi.cutSets.forEach((cs, i) => {
    const r = gui.rows[i];
    const want = { rank: String(cs.rank), order: String(cs.order), events: cs.events.map((e) => e.name || e.id), prob: L.fmt(cs.probability, sf), share: pctText(cs.share) };
    if (!r || JSON.stringify(r) !== JSON.stringify(want)) csBad.push({ i, r, want });
  });
  L.check(`Cut Sets rows (order/events/probability/share) == API for ${csApi.cutSets.length} sets`, gui.rows.length === csApi.cutSets.length && csBad.length === 0, csBad.slice(0, 3));
  const statWant = [L.fmt(csApi.mcub, sf), L.fmt(csApi.rareEvent, sf), L.fmt(csApi.treeWalk, sf)];
  L.check('Cut Sets summary MCUB / rare / tree walk == API', statWant.every((v, i) => gui.stats[i] && gui.stats[i].endsWith(' ' + v)), { stats: gui.stats, statWant });
  snap.cutsets = gui;
  // click a row -> highlight in tree + diagram
  await page.locator('#tabpanel-cutsets tbody tr[data-rank="1"]').click();
  await page.waitForTimeout(400);
  const hl = await page.evaluate(() => ({
    tree: Array.from(document.querySelectorAll('#tree-root li.fta-tree-item.is-highlighted')).map((li) => li.dataset.id).sort(),
    diagram: Array.from(document.querySelectorAll('#diagram-root svg g.node.is-highlighted title')).map((t) => t.textContent),
  }));
  const wantIds = csApi.cutSets[0].events.map((e) => e.id).sort();
  L.check('cut-set row click highlights exactly its events in the tree', JSON.stringify(hl.tree) === JSON.stringify(wantIds), { hl, wantIds });
  L.check('... and in the diagram', hl.diagram.length >= wantIds.length, hl.diagram);
  await page.keyboard.press('Enter'); // keyboard toggles it off again (row has focus)
  // sig figs on the table
  for (const n of [2, 6]) {
    await app.setSigFigs(n);
    await page.waitForTimeout(200);
    gui = await readCutsetsTab(page);
    const ok = csApi.cutSets.every((cs, i) => gui.rows[i] && gui.rows[i].prob === L.fmt(cs.probability, n));
    L.check(`Cut Sets probabilities at ${n} sig figs == API`, ok, gui.rows.slice(0, 2));
  }
  await app.setSigFigs(3);

  // ---- Importance tab -----------------------------------------------------------------
  await app.clickTab('importance');
  await page.waitForSelector('#tabpanel-importance tbody tr[data-id]', { timeout: 15000 });
  await app.settle(400);
  const impApi = await app.api('post', '/analysis/importance', {});
  const imp = await readImportanceTab(page);
  const impBad = [];
  impApi.events.forEach((e, i) => {
    const r = imp.rows[i];
    const want = { id: e.id, name: e.name || e.id, q: L.fmt(e.q, 3), fv: L.fmt(e.fv, 3), birnbaum: L.fmt(e.birnbaum, 3), raw: L.fmt(e.raw, 3), rrw: e.rrwInfinite ? '∞' : L.fmt(e.rrw, 3), n: String(e.cutSetCount) };
    if (!r || JSON.stringify(r) !== JSON.stringify(want)) impBad.push({ i, r, want });
  });
  L.check(`Importance rows (q/FV/Birnbaum/RAW/RRW/#) == API for ${impApi.events.length} events, same order`, imp.rows.length === impApi.events.length && impBad.length === 0, impBad.slice(0, 3));
  L.check('Importance basis line shows top value and cut-set count', imp.basis.includes(L.fmt(impApi.topValue, 3)) && imp.basis.includes(String(impApi.cutSetTotal)), imp.basis);
  snap.importance = imp;
  // sort by RAW via header click
  await page.locator('#tabpanel-importance th[data-sort="raw"]').click();
  const rawOrder = await page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-importance tbody tr')).map((tr) => tr.dataset.id));
  const wantRaw = impApi.events.slice().sort((a, b) => (b.raw - a.raw) || String(a.name).localeCompare(String(b.name))).map((e) => e.id);
  L.check('Importance sorted by RAW (header click) == API values sorted', JSON.stringify(rawOrder) === JSON.stringify(wantRaw), { rawOrder, wantRaw });
  // FV overlay
  const box = page.locator('#tabpanel-importance input[data-role="fv-overlay"]');
  if (!(await box.isChecked())) await box.click();
  await page.waitForTimeout(500);
  const ov = await page.evaluate(async () => {
    const { store } = await import('/static/js/store.js');
    return {
      overlay: store.overlay,
      tree: Array.from(document.querySelectorAll('#tree-root .fta-tree-fv')).length,
      diagram: Array.from(document.querySelectorAll('#diagram-root svg g.node.has-overlay title')).map((t) => t.textContent),
    };
  });
  const fvWant = {};
  for (const e of impApi.events) if (e.fv !== null && e.fv !== undefined) fvWant[e.id] = e.fv;
  L.check('FV overlay values == API fv per event', ov.overlay && JSON.stringify(ov.overlay.values) === JSON.stringify(fvWant), { got: ov.overlay, fvWant });
  L.check('FV overlay colours the tree and the diagram', ov.tree > 0 && ov.diagram.length >= Object.keys(fvWant).length, ov);
  await box.click(); // off again

  // ---- Uncertainty tab (fixed seed) ----------------------------------------------------
  await app.clickTab('uncertainty');
  const nIn = page.locator('#tabpanel-uncertainty input[data-field="n"]');
  await nIn.click();
  await page.keyboard.press('Control+A');
  await page.keyboard.type('5000');
  const seedIn = page.locator('#tabpanel-uncertainty input[data-field="seed"]');
  await seedIn.click();
  await page.keyboard.press('Control+A');
  await page.keyboard.type('12345');
  await page.locator('#tabpanel-uncertainty button[data-role="run"]').click();
  await page.waitForSelector('#tabpanel-uncertainty [data-stat="mean"] b', { timeout: 60000 });
  await page.waitForTimeout(300);
  const uncGui = await page.evaluate(() => {
    const o = {};
    for (const s of document.querySelectorAll('#tabpanel-uncertainty [data-stat]')) o[s.dataset.stat] = s.querySelector('b').textContent;
    o.bars = document.querySelectorAll('#tabpanel-uncertainty .anl-chart rect.bar').length;
    o.meta = document.querySelector('#tabpanel-uncertainty .anl-summary, #tabpanel-uncertainty p.anl-note') ? Array.from(document.querySelectorAll('#tabpanel-uncertainty p.anl-note')).map((x) => x.textContent).join(' | ') : '';
    return o;
  });
  const uncApi = await app.api('post', '/analysis/uncertainty', { n: 5000, seed: 12345, timeLimit: 30 });
  const uncWant = { mean: uncApi.mean, median: uncApi.median, p05: uncApi.p05, p95: uncApi.p95, std: uncApi.std, point: uncApi.pointEstimate };
  const uncBad = Object.entries(uncWant).filter(([k, v]) => uncGui[k] !== L.fmt(v, 3));
  L.check('Uncertainty stats (seed 12345, n 5000) == API run with the same seed', uncBad.length === 0, { uncGui, uncWant: Object.fromEntries(Object.entries(uncWant).map(([k, v]) => [k, L.fmt(v, 3)])) });
  L.check('Uncertainty histogram bars == non-empty API bins', uncGui.bars === uncApi.histogram.counts.filter((c) => c > 0).length, { bars: uncGui.bars, api: uncApi.histogram.counts.filter((c) => c > 0).length });
  L.check('Uncertainty meta shows completed/requested/seed', uncGui.meta.includes(String(uncApi.completed)) && uncGui.meta.includes('12345'), uncGui.meta);
  snap.unc = uncGui;

  // ---- Validation list + badge -----------------------------------------------------------
  // provoke: an XOR gate over 3 inputs (error, via the Details gate select) and an
  // unquantified leaf added with the Add dialog's default 1.0 (warning)
  const pumps = byName(st, 'Pumps fail');
  await app.clickTab('details');
  await app.selectTreeNode(pumps.id);
  await app.selectDetailsGate('XOR');
  await page.waitForTimeout(400);
  await app.selectTreeNode(st.tree.id);
  await app.addViaDialog({ name: 'Unquantified event' });
  await page.waitForTimeout(400);
  await app.clickTab('validation');
  await page.waitForTimeout(1500);
  const valApi = await app.api('get', '/analysis/validate');
  const valGui = await page.evaluate(() => ({
    items: Array.from(document.querySelectorAll('#tabpanel-validation li.val-item')).map((li) => ({ code: li.dataset.code, node: li.dataset.nodeId || null, sev: (li.className.match(/val-item--(\w+)/) || [])[1] })),
    chips: Array.from(document.querySelectorAll('#tabpanel-validation .val__chip')).map((c) => c.textContent),
    badge: (() => { const b = document.querySelector('#tab-validation .tabstrip__badge'); return b && !b.hidden ? { n: b.textContent, kind: b.dataset.kind } : null; })(),
  }));
  L.check('provoked issues listed (XOR_ARITY error, DEFAULT_PROBABILITY warning)', valGui.items.some((i) => i.code === 'XOR_ARITY' && i.sev === 'error') && valGui.items.some((i) => i.code === 'DEFAULT_PROBABILITY'), valGui.items);
  const key = (x) => [x.sev, x.code, x.node].join('|');
  const apiItems = valApi.issues.map((i) => ({ code: i.code, node: i.nodeId === null || i.nodeId === undefined ? null : String(i.nodeId), sev: i.severity }));
  L.check(`Validation list == API issues (${apiItems.length})`, JSON.stringify(valGui.items.map(key).sort()) === JSON.stringify(apiItems.map(key).sort()), { gui: valGui.items, api: apiItems });
  const cnt = valApi.counts || {};
  L.check('Validation chips counts == API counts', valGui.chips.some((c) => c.endsWith(' ' + (cnt.error || 0))) && valGui.chips.some((c) => c.endsWith(' ' + (cnt.warning || 0))) && valGui.chips.some((c) => c.endsWith(' ' + (cnt.info || 0))), { chips: valGui.chips, cnt });
  const wantBadge = cnt.error ? { n: String(cnt.error), kind: 'error' } : cnt.warning ? { n: String(cnt.warning), kind: 'warn' } : null;
  L.check('Validation tab badge == API counts', JSON.stringify(valGui.badge) === JSON.stringify(wantBadge), { badge: valGui.badge, wantBadge });
  snap.validation = valGui;
  // undo both edits with Ctrl+Z from the tab strip (not a text field)
  await page.locator('#tab-validation').focus();
  await page.keyboard.press('Control+Z');
  await page.waitForTimeout(300);
  await page.keyboard.press('Control+Z');
  await page.waitForTimeout(1500);
  const valApi2 = await app.api('get', '/analysis/validate');
  const badge2 = await page.evaluate(() => { const b = document.querySelector('#tab-validation .tabstrip__badge'); return b && !b.hidden ? { n: b.textContent, kind: b.dataset.kind } : null; });
  const c2 = valApi2.counts || {};
  const want2 = c2.error ? { n: String(c2.error), kind: 'error' } : c2.warning ? { n: String(c2.warning), kind: 'warn' } : null;
  L.check('after Ctrl+Z: badge == API counts (no stale error)', JSON.stringify(badge2) === JSON.stringify(want2), { badge2, want2 });
  const items2 = await page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-validation li.val-item')).map((li) => li.dataset.code));
  L.check('after Ctrl+Z: visible Validation list refreshed', items2.length === valApi2.issues.length, { items2, api: valApi2.issues.map((i) => i.code) });

  // ---- Background tab staleness: edit on Details, then open Cut Sets / Importance -----------
  await app.clickTab('details');
  const pa = byName(st, 'Pump A fails');
  await app.selectTreeNode(pa.id);
  await app.editDetailsField('Probability (base)', '0.2', 'enter');
  await page.waitForTimeout(300);
  await app.clickTab('cutsets');
  await page.waitForTimeout(2500);
  const csApi2 = await app.api('post', '/analysis/cutsets', { limit: 500 });
  gui = await readCutsetsTab(page);
  const fresh = csApi2.cutSets.every((cs, i) => gui.rows[i] && gui.rows[i].prob === L.fmt(cs.probability, 3));
  L.check('Cut Sets tab refreshed after an edit made while it was hidden', fresh && gui.rows.length === csApi2.cutSets.length, { gui: gui.rows.slice(0, 2), api: csApi2.cutSets.slice(0, 2).map((c) => L.fmt(c.probability, 3)) });
  L.check('... and its summary MCUB too', gui.stats[0] && gui.stats[0].endsWith(' ' + L.fmt(csApi2.mcub, 3)), { stats: gui.stats, mcub: L.fmt(csApi2.mcub, 3) });
  await app.clickTab('importance');
  await page.waitForTimeout(2500);
  const impApi2 = await app.api('post', '/analysis/importance', {});
  const imp2 = await readImportanceTab(page);
  const impFresh = impApi2.events.every((e) => { const r = imp2.rows.find((x) => x.id === e.id); return r && r.fv === L.fmt(e.fv, 3); });
  L.check('Importance tab refreshed after a hidden-tab edit', impFresh, imp2.rows.slice(0, 3));
  await compareCore(app, 'after hidden-tab edit');

  // ---- Traceability: edit cells, compare with node trace ------------------------------------
  await app.clickTab('trace');
  await page.waitForSelector('#tabpanel-trace tbody tr', { timeout: 8000 });
  const editCell = async (id, field, value) => {
    const cell = page.locator('#tabpanel-trace tbody tr[data-id="' + id + '"] td[data-field="' + field + '"]');
    await cell.click();
    if (field === 'status') {
      await page.locator('#tabpanel-trace .trace-cell-select').selectOption(value);
    } else {
      await page.keyboard.type(value);
      await page.keyboard.press('Enter');
    }
    await page.waitForTimeout(600);
  };
  await editCell(pa.id, 'requirementId', 'REQ-001');
  await editCell(pa.id, 'tags', 'pump, mech');
  await editCell(pa.id, 'status', 'approved');
  await editCell(pumps.id, 'owner', 'Tanaka');
  st = await app.api('get', '/state');
  const traceGui = await page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-trace tbody tr')).map((tr) => {
    const o = { id: tr.dataset.id };
    for (const td of tr.querySelectorAll('td[data-field]')) {
      const f = td.dataset.field;
      if (f === 'tags') o[f] = Array.from(td.querySelectorAll('.trace-chip')).map((c) => c.textContent);
      else if (f === 'status') o[f] = td.querySelector('.trace-status') ? td.querySelector('.trace-status').className.replace(/.*trace-status--/, '') : '';
      else o[f] = td.textContent;
    }
    return o;
  }));
  const trBad = [];
  for (const n of flatten(st.tree)) {
    const tr = n.trace || {};
    const r = traceGui.find((x) => x.id === String(n.id));
    const want = { id: String(n.id), requirementId: tr.requirementId || '', testRef: tr.testRef || '', owner: tr.owner || '', status: tr.status || '', evidence: tr.evidence || '', tags: tr.tags || [] };
    if (!r || JSON.stringify(r) !== JSON.stringify(want)) trBad.push({ r, want });
  }
  L.check(`Traceability table == node trace fields for ${flatten(st.tree).length} nodes`, trBad.length === 0, trBad.slice(0, 3));
  const paTrace = byName(st, 'Pump A fails').trace || {};
  L.check('trace edits stored (REQ-001, [pump, mech], approved)', paTrace.requirementId === 'REQ-001' && JSON.stringify(paTrace.tags) === '["pump","mech"]' && paTrace.status === 'approved', paTrace);
  const cover = await page.locator('#tabpanel-trace .trace-summary').first().textContent();
  const total = flatten(st.tree).length;
  L.check('trace coverage summary counts == API', cover.includes(String(total)) && /1\b/.test(cover), cover);
  snap.trace = traceGui;

  // ---- ETA mode: tabs show the ETA notice; headline is the root value -----------------------------
  await page.locator('#mode-select').selectOption('ETA');
  await page.waitForTimeout(1500);
  st = await app.api('get', '/state');
  L.check('mode switched to ETA on the server', st.metadata.mode === 'ETA', st.metadata);
  await app.clickTab('cutsets');
  await page.waitForTimeout(300);
  const etaNote = await page.evaluate(() => !!document.querySelector('#tabpanel-cutsets .anl-eta'));
  L.check('Cut Sets tab shows the ETA notice', etaNote);
  await compareCore(app, 'ETA mode');
  await page.keyboard.press('Control+Z');
  await page.waitForTimeout(1200);
  st = await app.api('get', '/state');
  L.check('Ctrl+Z restores FTA mode', st.metadata.mode === 'FTA' && (await page.locator('#mode-select').inputValue()) === 'FTA', st.metadata.mode);
  await compareCore(app, 'back to FTA');

  const errs = app.errorsSince(0);
  L.check('no console errors in the tabs run', errs.length === 0, errs);
  fs.writeFileSync(path.join(L.OUT, 'tabs_' + label + '.json'), JSON.stringify(snap, null, 1));
  await app.context.close();
}

L.runSection('tabs', main);
