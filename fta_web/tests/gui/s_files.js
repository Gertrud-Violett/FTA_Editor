// FMEA import + Report docx + Excel export back-to-back.
// node s_files.js <url> <label> <root>
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');
const { flatten } = require('./b2b');

async function main(url, label, root) {
  L.setSection('files[' + label + ']');
  L.writeFmeaCsv(root); // lib.js FMEA_CSV: 3 good rows, a blank row, a bad row
  fs.writeFileSync(path.join(root, 'notes.txt'), 'not an fmea');

  const app = await L.openApp(url, { prefs: { 'fta.advanced': '1', 'fta.sigFigs': '4' }, viewport: { width: 1600, height: 1050 } });
  const { page } = app;
  const sf = 4;

  // open the GUI-built file
  await page.locator('.actionbar [data-action="load"]').click();
  await page.waitForTimeout(300);
  if (await page.locator('.fta-modal:not(.fta-filedialog)').count()) await page.locator('.fta-modal:not(.fta-filedialog) .fta-btn.is-primary').click();
  await page.locator('.fta-filedialog').waitFor({ state: 'visible' });
  await page.locator('.fta-filedialog .fdlg-row').first().waitFor({ state: 'visible' });
  await page.waitForTimeout(300);
  const openList = await page.$$eval('.fta-filedialog .fdlg-row__name', (els) => els.map((e) => e.textContent));
  L.check('Open dialog lists .json only (no csv/txt)', openList.some((n) => n.endsWith('.json')) && !openList.some((n) => /\.(csv|txt)$/.test(n)), openList);
  await page.locator('.fta-filedialog .fdlg-row', { hasText: 'b2b_core_' + label + '.json' }).dblclick();
  await page.waitForTimeout(1000);
  let st = await app.api('get', '/state');
  const pumps = flatten(st.tree).find((n) => n.name === 'Pumps fail');

  // ---- FMEA import through the file dialog -------------------------------------------
  await app.selectTreeNode(pumps.id);
  await app.clickTab('fmea');
  await page.locator('#tabpanel-fmea button', { hasText: /Choose file/ }).click();
  await page.locator('.fta-filedialog').waitFor({ state: 'visible' });
  await page.waitForTimeout(300);
  const fmeaList = await page.$$eval('.fta-filedialog .fdlg-row__name', (els) => els.map((e) => e.textContent));
  L.check('FMEA dialog lists the CSV, not json/txt', fmeaList.includes('b2b_fmea.csv') && !fmeaList.some((n) => /\.(json|txt)$/.test(n)), fmeaList);
  await app.shot('files_fmea_dialog_' + label);
  await page.locator('.fta-filedialog .fdlg-row', { hasText: 'b2b_fmea.csv' }).dblclick();
  await page.waitForSelector('#tabpanel-fmea .fmea-map', { timeout: 8000 });
  const parentShown = await page.locator('#tabpanel-fmea select.fmea-parent').inputValue();
  L.check('FMEA target parent defaults to the selected node', parentShown === pumps.id, parentShown);
  const warnShown = await page.evaluate(() => { const w = document.querySelector('#tabpanel-fmea .fmea-unit-warning'); return w && !w.hidden ? w.textContent : ''; });
  L.check('plausible per-hour λ: no unit warning', !/too high/.test(warnShown), warnShown);
  const [resp] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/fmea/import')),
    page.locator('#tabpanel-fmea button.fmea-primary').click(),
  ]);
  const imp = await resp.json();
  await page.waitForTimeout(600);
  const resultText = await page.locator('#tabpanel-fmea .fmea-result .fmea-msg').first().textContent();
  const nums = (resultText.match(/\d+/g) || []).map(Number);
  const want = [imp.created.length, imp.updated.length, (imp.unchanged || []).length, (imp.skipped || []).length];
  L.check(`FMEA result counts ${JSON.stringify(nums)} == API created/updated/unchanged/skipped ${JSON.stringify(want)}`, JSON.stringify(nums.slice(-4)) === JSON.stringify(want), { resultText, want });
  st = await app.api('get', '/state');
  const fm = flatten(st.tree).filter((n) => n.fmea);
  L.check('FMEA: created nodes present in the server tree with their FMEA ids', imp.created.every((id) => fm.some((n) => String(n.id) === String(id))) && fm.length === imp.created.length, { created: imp.created, fm: fm.map((n) => n.fmea.id) });
  const skippedItems = await page.$$eval('#tabpanel-fmea .fmea-skipped li', (els) => els.length);
  L.check('FMEA skipped list length == API skipped', skippedItems === Math.min(200, (imp.skipped || []).length), { skippedItems, api: (imp.skipped || []).length });
  const hl = await page.evaluate(() => Array.from(document.querySelectorAll('#tree-root li.fta-tree-item.is-highlighted')).map((li) => li.dataset.id).sort());
  L.check('imported nodes highlighted in the tree', JSON.stringify(hl) === JSON.stringify(imp.created.map(String).sort()), { hl, created: imp.created });
  // re-import with update: unchanged
  const [resp2] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/fmea/import')),
    page.locator('#tabpanel-fmea button.fmea-primary').click(),
  ]);
  const imp2 = await resp2.json();
  await page.waitForTimeout(600);
  const t2 = await page.locator('#tabpanel-fmea .fmea-result .fmea-msg').first().textContent();
  const n2 = (t2.match(/\d+/g) || []).map(Number).slice(-4);
  L.check('FMEA re-import counts == API (nothing new)', JSON.stringify(n2) === JSON.stringify([imp2.created.length, imp2.updated.length, (imp2.unchanged || []).length, (imp2.skipped || []).length]) && imp2.created.length === 0, { t2, imp2: { c: imp2.created, u: imp2.updated, un: imp2.unchanged } });
  await app.shot('files_fmea_imported_' + label);

  // ---- Report docx + Excel -------------------------------------------------------------------
  await app.clickTab('report');
  await page.waitForSelector('[data-report-generate]');
  // make sure the analysis sections are on
  for (const s of ['headline', 'cutsets', 'importance', 'events']) {
    const b = page.locator('[data-section="' + s + '"]');
    if (!(await b.isChecked())) await b.click();
  }
  const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 90000 }), page.locator('[data-report-generate]').click()]);
  const docxPath = path.join(L.OUT, 'files_report_' + label + '.docx');
  await dl.saveAs(docxPath);
  const [dx] = await Promise.all([page.waitForEvent('download', { timeout: 60000 }), page.locator('[data-report-xlsx]').click()]);
  const xlsxPath = path.join(L.OUT, 'files_export_' + label + '.xlsx');
  await dx.saveAs(xlsxPath);
  L.check('docx and xlsx downloaded', fs.statSync(docxPath).size > 5000 && fs.statSync(xlsxPath).size > 3000, { docx: fs.statSync(docxPath).size, xlsx: fs.statSync(xlsxPath).size });
  // the "save again" link must still work after another export
  const [dcsv] = await Promise.all([page.waitForEvent('download', { timeout: 30000 }), page.locator('[data-report-csv]').click()]);
  await dcsv.saveAs(path.join(L.OUT, 'files_events_' + label + '.csv'));
  const again = await page.evaluate(async () => {
    const a = document.querySelector('[data-report-link]');
    if (!a || a.hidden) return { shown: false };
    try { const r = await fetch(a.href); const b = await r.blob(); return { shown: true, ok: true, size: b.size, text: a.textContent }; } catch (e) { return { shown: true, ok: false, err: String(e), text: a.textContent }; }
  });
  L.check('"Save … again" link still downloads the report after exporting Excel/CSV', again.shown && again.ok && again.size > 5000, again);

  const parsed = L.parseExports(docxPath, xlsxPath);
  const summary = await app.api('get', '/analysis/summary');
  const cs = await app.api('post', '/analysis/cutsets', { limit: 50 });
  const impApi = await app.api('post', '/analysis/importance', {});
  st = await app.api('get', '/state');
  const docxH = parsed.docx.headline;
  L.check(`docx headline ${docxH && docxH.value} == summary.headline @${sf}sf ${L.fmt(summary.headline, sf)}`, docxH && docxH.value === L.fmt(summary.headline, sf), docxH);
  const csTable = parsed.docx.tables.find((t) => /cut sets|カットセット/i.test(t.heading || ''));
  const csBad = [];
  cs.cutSets.slice(0, 50).forEach((c, i) => {
    const r = csTable && csTable.rows[i + 1];
    const want = [String(c.rank), c.events.map((e) => e.name || e.id).join(' · '), String(c.order), L.fmt(c.probability, sf), (c.share * 100).toFixed(1) + '%'];
    if (!r || JSON.stringify(r) !== JSON.stringify(want)) csBad.push({ r, want });
  });
  L.check(`docx cut-set table == API (${cs.cutSets.length} rows)`, csTable && csBad.length === 0 && csTable.rows.length - 1 === Math.min(50, cs.cutSets.length), csBad.slice(0, 3));
  const impTable = parsed.docx.tables.find((t) => /importance|重要度/i.test(t.heading || ''));
  const impBad = [];
  impApi.events.slice(0, 30).forEach((e, i) => {
    const r = impTable && impTable.rows[i + 1];
    const want = [String(e.id), e.name, L.fmt(e.q, sf), L.fmt(e.fv, sf), L.fmt(e.birnbaum, sf), L.fmt(e.raw, sf), e.rrwInfinite && e.rrw === null ? '∞' : L.fmt(e.rrw, sf), String(e.cutSetCount)];
    if (!r || JSON.stringify(r) !== JSON.stringify(want)) impBad.push({ r, want });
  });
  L.check(`docx importance table == API (${impApi.events.length} rows)`, impTable && impBad.length === 0, impBad.slice(0, 3));
  // Excel Events sheet: calculated probability per node == tree (exact numbers)
  const nodes = flatten(st.tree);
  const xBad = [];
  for (const n of nodes) {
    const r = (parsed.xlsx.events || []).find((x) => String(x.Id) === String(n.id));
    if (!r || Number(r['Calculated probability']) !== n.calculatedProbability || Number(r['Base probability']) !== n.probability) xBad.push({ id: n.id, r: r && { c: r['Calculated probability'], b: r['Base probability'] }, api: { c: n.calculatedProbability, b: n.probability } });
  }
  L.check(`xlsx Events sheet probabilities == API tree exactly (${nodes.length} nodes)`, xBad.length === 0 && (parsed.xlsx.events || []).length === nodes.length, xBad.slice(0, 3));
  L.check(`xlsx number format follows sig figs (${sf}): ${parsed.xlsx.calcFormat}`, /0\.0{3}E\+00|0\.000E/.test(parsed.xlsx.calcFormat || ''), parsed.xlsx.calcFormat);
  const an = parsed.xlsx.analysis || {};
  L.check('xlsx Analysis headline / tree walk / MCUB == summary exactly', Number(an['Top event (headline)']) === summary.headline && Number(an['Tree walk']) === summary.treeWalk && Number(an.MCUB) === summary.mcub, { an, summary: { h: summary.headline, tw: summary.treeWalk, m: summary.mcub } });
  // the action-bar Excel button gives the same workbook data
  const [dx2] = await Promise.all([page.waitForEvent('download', { timeout: 60000 }), page.locator('.actionbar [data-action="excel"]').click()]);
  const xlsx2 = path.join(L.OUT, 'files_export_bar_' + label + '.xlsx');
  await dx2.saveAs(xlsx2);
  const parsed2 = L.parseExports(docxPath, xlsx2);
  L.check('action-bar Excel == Report-tab Excel (events + analysis)', JSON.stringify(parsed2.xlsx.events) === JSON.stringify(parsed.xlsx.events) && JSON.stringify(parsed2.xlsx.analysis) === JSON.stringify(parsed.xlsx.analysis));

  const errs = app.errorsSince(0);
  L.check('no console errors in the files run', errs.length === 0, errs);
  fs.writeFileSync(path.join(L.OUT, 'files_' + label + '.json'), JSON.stringify({ docx: parsed.docx, xlsx: parsed.xlsx.analysis, fmea: { nums, n2 } }, null, 1));
  await app.context.close();
}

L.runSection('files', main);
