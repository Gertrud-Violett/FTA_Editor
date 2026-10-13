// Analysis, diagram and AI (usability batch 3), with real mouse and keyboard
// input: the gate and probability on tree rows, the multi-selection (header,
// keyboard move, drag, delete, each one undo step), the diagram's settings
// button, 100%, bringing a selected node into view, the exports (file name,
// toast, the importance overlay with its legend, light colours from the dark
// theme), the bottom panel's height per tab and its enlarge button, Copy CSV
// on Importance, uncertainty for all events, the rare-event note, ETA mode,
// the quieter toasts, and the assistant: Stop, a message given back, error
// replies, suggestion cards, the reload and the setup dialog.
//   node s_ux3.js <url> <label> <root>
//
// No AI provider is ever called: every /api/ai/* request the page makes here
// is answered by this script.
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

function leaf(id, name, probability) {
  return { id, name, type: 'Event', probability, logicGate: 'OR', notes: '', links: [], children: [] };
}

/** Top (OR) -> Pumps fail (AND: Pump A, Pump B), Valve sticks, Operator error (q = 1), Sensor fails. */
function documentText(title, mode) {
  const pumps = Object.assign(leaf('root_0', 'Pumps fail', 1.0), {
    type: 'Gate', logicGate: 'AND', children: [leaf('root_0_0', 'Pump A', 0.1), leaf('root_0_1', 'Pump B', 0.2)],
  });
  const tree = Object.assign(leaf('root', 'Loss of cooling', 1.0), {
    type: 'Root',
    children: [pumps, leaf('root_1', 'Valve sticks', 0.05), leaf('root_2', 'Operator error', 1.0), leaf('root_3', 'Sensor fails', 0.3)],
  });
  return JSON.stringify({ title, date: '2026-10-12', mode: mode || 'FTA', tree }, null, 2);
}

async function run(url, label, root) {
  L.setSection('ux3[' + label + ']');
  const fileA = 'ux3_a_' + label + '.json';
  fs.writeFileSync(path.join(root, fileA), documentText('Ux3A'));

  const app = await L.openApp(url, { viewport: { width: 1600, height: 1000 }, prefs: { 'fta.advanced': '1' } });
  const { page } = app;

  const toasts = () => page.evaluate(() => Array.from(document.querySelectorAll('#toasts .toast__body')).map((t) => t.textContent));
  const clearToasts = () => page.evaluate(() => document.getElementById('toasts').replaceChildren());
  const state = async () => app.api('get', '/state');
  const row = (id) => page.locator('#tree-root li.fta-tree-item[data-id="' + id + '"] > .fta-tree-row');
  const kids = async (id) => {
    const find = (n) => (String(n.id) === id ? n : (n.children || []).map(find).find(Boolean));
    return (find((await state()).tree).children || []).map((c) => String(c.id));
  };
  const meta = () => page.textContent('#details-meta');
  const prompt = page.locator('.fta-modal[data-kind="choice"]');
  const waitFor = async (fn, timeout) => {
    const t0 = Date.now();
    for (;;) {
      if (await fn()) return true;
      if (Date.now() - t0 > (timeout || 8000)) return false;
      await page.waitForTimeout(100);
    }
  };
  const openA = async () => {
    await app.api('post', '/new', { force: true });
    const opened = await app.api('post', '/file/open', { path: path.join(root, fileA) });
    if (opened.__error) throw new Error('could not open ' + fileA + ': ' + JSON.stringify(opened));
    await page.reload();
    await L.waitBoot(page);
    await app.waitDiagram();
    await page.waitForTimeout(500);
  };
  const download = async (locator) => {
    const [dl] = await Promise.all([page.waitForEvent('download'), locator.click()]);
    const file = path.join(L.OUT, 'ux3_' + label + '_' + dl.suggestedFilename());
    await dl.saveAs(file);
    return { name: dl.suggestedFilename(), file };
  };

  await app.api('post', '/prefs', { aiPanelCollapsed: false });
  // A document nobody has seen, so every branch starts open.
  fs.writeFileSync(path.join(root, fileA), documentText('Ux3A'));
  await openA();

  // ---- 41: a row says what it is and what it is worth -----------------------------------
  const rowInfo = (id) => page.evaluate((nid) => {
    const r = document.querySelector('#tree-root li.fta-tree-item[data-id="' + nid + '"] > .fta-tree-row');
    const gate = r.querySelector('.fta-tree-gate');
    const prob = r.querySelector('.fta-tree-prob');
    return { gate: gate ? gate.textContent : null, prob: prob ? prob.textContent : null, full: r.classList.contains('is-full'), color: getComputedStyle(r).color, weight: getComputedStyle(r.querySelector('.fta-tree-label')).fontWeight };
  }, id);
  const st0 = await state();
  const pumps = st0.tree.children[0];
  const info = { root: await rowInfo('root'), gate: await rowInfo('root_0'), leaf: await rowInfo('root_1'), certain: await rowInfo('root_2') };
  L.check('tree rows: a node with inputs shows its gate', info.root.gate === 'OR' && info.gate.gate === 'AND' && info.leaf.gate === null, info);
  L.check('tree rows: the probability is on the row (calculated for a gate, its own for an event)',
    info.gate.prob === L.fmt(pumps.calculatedProbability, 3) && info.leaf.prob === L.fmt(0.05, 3), info);
  L.check('tree rows: a gate with a base probability of 1 is not red and bold', !info.gate.full && !info.root.full && info.gate.color === info.leaf.color && info.gate.weight === info.leaf.weight, info);
  L.check('tree rows: an event that is certain still is', info.certain.full && info.certain.color !== info.leaf.color, info);
  await app.shot('ux3_tree_rows_' + label);

  // ---- smaller: the header names the node; Type offers the usual values -----------------------
  await row('root_1').click();
  await page.waitForTimeout(200);
  L.check('header: the selected node by name, its id in the tooltip', (await meta()) === 'Selected: Valve sticks' && /root_1/.test(await page.getAttribute('#details-meta', 'title')), await meta());
  const typeList = await page.evaluate(() => {
    const field = Array.from(document.querySelectorAll('#details-root .fta-field')).find((f) => f.querySelector('label') && f.querySelector('label').textContent.trim() === 'Type');
    const input = field.querySelector('input');
    const list = input.list;
    return { has: Boolean(list), options: list ? Array.from(list.options).map((o) => o.value) : [] };
  });
  L.check('Details: Type offers Event, Gate and Intermediate (still free text)', typeList.has && JSON.stringify(typeList.options) === '["Event","Gate","Intermediate"]', typeList);

  // ---- 44: several rows selected act as one ------------------------------------------------
  await row('root_1').click();
  await row('root_2').click({ modifiers: ['Control'] });
  await page.waitForTimeout(200);
  L.check('multi-select: the header says how many are selected', (await meta()) === '2 selected', await meta());
  await app.shot('ux3_multi_select_' + label);
  const orderBefore = await kids('root');
  await page.keyboard.press('Control+Shift+ArrowDown');
  await waitFor(async () => (await toasts()).some((t) => /Moved 2 nodes/.test(t)));
  L.check('multi-select: Ctrl+Shift+Down moves the block', JSON.stringify(await kids('root')) === '["root_0","root_3","root_1","root_2"]', await kids('root'));
  L.check('multi-select: the block is still selected after the move', (await meta()) === '2 selected', await meta());
  L.check('multi-select: the toast says one Undo takes it back', (await toasts()).some((t) => /Moved 2 nodes/.test(t) && /One Undo/.test(t)), await toasts());
  await page.keyboard.press('Control+z');
  await waitFor(async () => JSON.stringify(await kids('root')) === JSON.stringify(orderBefore));
  L.check('multi-select: one Ctrl+Z puts both back', JSON.stringify(await kids('root')) === JSON.stringify(orderBefore) && (await state()).canUndo === false, { kids: await kids('root') });

  await row('root_1').click();
  await row('root_2').click({ modifiers: ['Control'] });
  await row('root_1').dragTo(row('root_0'));
  await waitFor(async () => (await toasts()).some((t) => /Moved 2 nodes under "Pumps fail"/.test(t)));
  L.check('multi-select: dragging one selected row onto a node moves all of them under it',
    JSON.stringify(await kids('root_0')) === '["root_0_0","root_0_1","root_1","root_2"]' && JSON.stringify(await kids('root')) === '["root_0","root_3"]', { under: await kids('root_0'), top: await kids('root') });
  await page.keyboard.press('Control+z');
  await waitFor(async () => (await kids('root')).length === 4);
  L.check('multi-select: that drag is one undo step', JSON.stringify(await kids('root')) === JSON.stringify(orderBefore) && (await state()).canUndo === false, await kids('root'));

  await row('root_1').click();
  await row('root_3').click({ modifiers: ['Control'] });
  await page.keyboard.press('Delete');
  const confirm = page.locator('.fta-modal');
  await confirm.waitFor({ state: 'visible' });
  await confirm.locator('.fta-btn.is-primary').click();
  await waitFor(async () => (await toasts()).some((t) => /Deleted 2 nodes/.test(t)));
  L.check('multi-select: Delete removes every selected node', JSON.stringify(await kids('root')) === '["root_0","root_2"]', await kids('root'));
  L.check('multi-select: the toast says one Undo brings them back', (await toasts()).some((t) => /Deleted 2 nodes\. One Undo/.test(t)), await toasts());
  await page.keyboard.press('Control+z');
  await waitFor(async () => (await kids('root')).length === 4);
  L.check('multi-select: one Ctrl+Z brings both back, where they were', JSON.stringify(await kids('root')) === JSON.stringify(orderBefore) && (await state()).canUndo === false, await kids('root'));

  // ---- smaller: a notice carries no raw code ------------------------------------------------
  await page.waitForTimeout(500);
  await clearToasts();
  await row('root').click();
  await page.keyboard.press('Delete');
  await page.waitForTimeout(300);
  const rootToast = await page.evaluate(() => { const t = document.querySelector('#toasts .toast[data-code]'); return t ? { text: t.textContent, code: t.dataset.code, tag: Boolean(t.querySelector('.toast__code')) } : null; });
  L.check('toast: "the root cannot be deleted" has no ROOT_PROTECTED line (the code stays on the element)',
    !!rootToast && !/ROOT_PROTECTED/.test(rootToast.text) && rootToast.code === 'ROOT_PROTECTED' && !rootToast.tag, rootToast);
  const toastPlace = await page.evaluate(() => {
    const t = document.getElementById('toasts').getBoundingClientRect();
    const ai = document.getElementById('ai-panel').getBoundingClientRect();
    return { toastRight: t.right, aiLeft: ai.left };
  });
  L.check('toast: it is beside the AI panel, not over its Send button', toastPlace.toastRight <= toastPlace.aiLeft, toastPlace);
  await clearToasts();

  // ---- 48: a title needs no "Metadata updated." ---------------------------------------------
  await page.locator('#title-input').fill('Ux3A renamed');
  await page.keyboard.press('Enter');
  await waitFor(async () => (await state()).metadata.title === 'Ux3A renamed');
  await page.waitForTimeout(300);
  L.check('title: saved without a toast', (await toasts()).length === 0, await toasts());

  // ---- 30: the settings are behind a button that says so --------------------------------------
  const settings = page.locator('#diagram-root [data-role="diagram-settings"]');
  L.check('diagram: the button is "Settings", titled "Diagram settings"', /Settings/.test(await settings.textContent()) && (await settings.getAttribute('title')) === 'Diagram settings', await settings.textContent());
  await settings.click();
  const pop = page.locator('.diagram__popover');
  const popText = await pop.textContent();
  L.check('diagram: the popover is "Diagram settings" with Style, Layout, Font and "Box padding (0-30)"',
    /^Diagram settings/.test(popText) && /Style/.test(popText) && /Layout/.test(popText) && /Box padding \(0-30\)/.test(popText) && !/Box scale|Font & box size/.test(popText), popText.slice(0, 80));
  await app.shot('ux3_diagram_settings_' + label);
  await page.keyboard.press('Escape');

  // ---- 35: 100%, and a selected node comes into view ----------------------------------------
  const zoom = () => page.textContent('#diagram-root .diagram__zoom');
  const inView = (id) => page.evaluate(async (nid) => {
    const { api } = await import('/static/js/api.js');
    const stage = document.querySelector('#diagram-root .diagram__stage').getBoundingClientRect();
    const g = document.querySelector('#diagram-root g.node.is-selected');
    if (!g) return { found: false };
    const b = g.getBoundingClientRect();
    return { found: true, inside: b.left >= stage.left && b.right <= stage.right && b.top >= stage.top && b.bottom <= stage.bottom, nid, api: Boolean(api) };
  }, id);
  await row('root').click();
  const plus = page.locator('#diagram-root .diagram__btn', { hasText: '+' });
  for (let i = 0; i < 14; i += 1) await plus.click();
  await page.waitForTimeout(200);
  const zoomed = await zoom();
  await row('root_0_1').click();
  await page.waitForTimeout(300);
  const seen = await inView('root_0_1');
  L.check('diagram: a row picked in the tree is brought onto the stage of a zoomed diagram', seen.found && seen.inside && (await zoom()) === zoomed, { seen, zoomed });
  await row('root_3').click();
  await page.waitForTimeout(300);
  L.check('diagram: and the next one too, the zoom untouched', (await inView('root_3')).inside && (await zoom()) === zoomed, await inView('root_3'));
  await page.locator('#diagram-root .diagram__btn[data-i18n-title="diagram3.actualSize"]').click();
  await page.waitForTimeout(200);
  L.check('diagram: 1:1 sets 100%', (await zoom()) === '100%', await zoom());
  await page.locator('#diagram-root .diagram__btn[data-i18n-title="diagram.zoomOut"]').click();
  await page.locator('#diagram-root .diagram__btn[data-i18n-title="diagram.zoomOut"]').click();
  await row('root_0_0').click();
  await page.locator('#diagram-root .diagram__btn[data-i18n-title="diagram3.toSelection"]').click();
  await page.waitForTimeout(200);
  const centred = await page.evaluate(() => {
    const stage = document.querySelector('#diagram-root .diagram__stage').getBoundingClientRect();
    const b = document.querySelector('#diagram-root g.node.is-selected').getBoundingClientRect();
    return { dx: Math.abs((b.left + b.right) / 2 - (stage.left + stage.right) / 2), dy: Math.abs((b.top + b.bottom) / 2 - (stage.top + stage.bottom) / 2) };
  });
  L.check('diagram: "show the selected node" centres it at 100%', centred.dx < 2 && centred.dy < 2 && (await zoom()) === '100%', { centred, zoom: await zoom() });
  await page.locator('#diagram-root .diagram__btn[data-i18n-title="diagram.fit"]').click();

  // ---- 36: the bottom panel is taller for a table, and can be enlarged ---------------------------
  const heights = () => page.evaluate(() => ({
    bottom: Math.round(document.getElementById('details-panel').getBoundingClientRect().height),
    diagram: Math.round(document.getElementById('diagram-panel').getBoundingClientRect().height),
  }));
  await app.clickTab('details');
  await page.waitForTimeout(200);
  const onDetails = await heights();
  await app.clickTab('importance');
  await page.locator('#tabpanel-importance .anl-table').waitFor({ state: 'visible' });
  await page.waitForTimeout(300);
  const onImportance = await heights();
  L.check('bottom panel: taller on an analysis tab than on Details', onDetails.bottom === 260 && onImportance.bottom > 350 && onImportance.diagram >= 240, { onDetails, onImportance });
  const maxBtn = page.locator('#btn-bottom-max');
  await maxBtn.click();
  await page.waitForTimeout(300);
  const enlarged = await heights();
  L.check('bottom panel: enlarged, with a strip of diagram left', enlarged.bottom > onImportance.bottom + 100 && enlarged.diagram >= 240 && (await maxBtn.getAttribute('aria-pressed')) === 'true', enlarged);
  await app.shot('ux3_bottom_enlarged_' + label);
  await maxBtn.click();
  await page.waitForTimeout(300);
  L.check('bottom panel: and back', (await heights()).bottom === onImportance.bottom && (await maxBtn.getAttribute('aria-pressed')) === 'false', await heights());
  await app.clickTab('details');
  await page.waitForTimeout(200);
  L.check('bottom panel: Details has its own height again', (await heights()).bottom === onDetails.bottom, await heights());

  // ---- 40: Copy CSV on Importance ------------------------------------------------------------------
  await app.clickTab('importance');
  await page.locator('#tabpanel-importance .anl-table').waitFor({ state: 'visible' });
  await clearToasts();
  await page.locator('#tabpanel-importance [data-role="copy"]').click();
  await page.waitForTimeout(300);
  const csv = await page.evaluate(() => navigator.clipboard.readText());
  const csvLines = csv.trim().split('\r\n');
  const shownRows = await page.locator('#tabpanel-importance .anl-table tbody tr').count();
  L.check('importance: Copy CSV puts the table on the clipboard', csvLines[0] === 'Event,id,q,FV,Birnbaum,RAW,RRW,Cut sets' && csvLines.length === shownRows + 1 && /^Operator error,root_2,1,/.test(csvLines[1]), csvLines.slice(0, 2));
  L.check('importance: and says so', (await toasts()).some((t) => new RegExp('Copied ' + shownRows + ' rows').test(t)), await toasts());

  // ---- 13 + 39: the overlay is in the export, with a legend, under the document's name ------------
  await page.locator('#tabpanel-importance [data-role="fv-overlay"]').check();
  await page.waitForTimeout(500);
  await clearToasts();
  const svg = await download(page.locator('#diagram-root .diagram__btn', { hasText: 'SVG' }));
  const svgText = fs.readFileSync(svg.file, 'utf8');
  L.check('export: the file is named after the document, not fta_diagram', svg.name === 'ux3_a_' + label + '.svg', svg.name);
  L.check('export: a toast says what was downloaded', (await toasts()).some((t) => t.includes('Downloaded a copy as ' + svg.name)), await toasts());
  L.check('export: the SVG has the importance colours and the legend', (svgText.match(/style="fill: rgb/g) || []).length >= 4 && /fta-legend-key/.test(svgText) && /Fussell-Vesely importance/.test(svgText) && /fta-overlay-scale/.test(svgText), svgText.length);
  L.check('export: the selection outline is not in the file', !/is-selected/.test(svgText));
  const png = await download(page.locator('#diagram-root .diagram__btn', { hasText: 'PNG' }));
  L.check('export: the PNG has the same name stem and is a PNG', png.name === 'ux3_a_' + label + '.png' && fs.readFileSync(png.file).slice(1, 4).toString() === 'PNG', png.name);
  fs.copyFileSync(png.file, path.join(L.OUT, 'ux3_fv_export_' + label + '.png'));
  const render = await download(page.locator('.actionbar [data-action="render"]'));
  L.check('export: Render gives the same name as the diagram\'s own PNG button', render.name === png.name, render.name);
  await page.locator('#tabpanel-importance [data-role="fv-overlay"]').uncheck();
  await page.waitForTimeout(300);
  const plain = fs.readFileSync((await download(page.locator('#diagram-root .diagram__btn', { hasText: 'SVG' }))).file, 'utf8');
  L.check('export: without the overlay there is no legend and no fill', !/fta-legend-key/.test(plain) && !/style="fill: rgb/.test(plain));

  // ---- 14: a dark screen still exports light --------------------------------------------------------
  await app.setTheme('dark');
  await page.waitForTimeout(1200);
  await app.waitDiagram();
  const screenDark = await page.evaluate(() => document.querySelector('#diagram-root .diagram__canvas svg').outerHTML.includes('#1b1f23'));
  const darkSvg = fs.readFileSync((await download(page.locator('#diagram-root .diagram__btn', { hasText: 'SVG' }))).file, 'utf8');
  L.check('dark theme: the preview is dark, the exported SVG is in the light colours', screenDark && !darkSvg.includes('#1b1f23') && /fill="white"/.test(darkSvg) && /Loss of cooling/.test(darkSvg), { screenDark });
  const darkPng = await download(page.locator('#diagram-root .diagram__btn', { hasText: 'PNG' }));
  fs.copyFileSync(darkPng.file, path.join(L.OUT, 'ux3_dark_export_' + label + '.png'));
  const corner = await page.evaluate(async (b64) => {
    const img = new Image();
    img.src = 'data:image/png;base64,' + b64;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = img.width; c.height = img.height;
    const ctx = c.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(img, 0, 0);
    const at = (x, y) => Array.from(ctx.getImageData(x, y, 1, 1).data.slice(0, 3));
    return [at(2, 2), at(img.width - 3, 2), at(2, img.height - 3), at(img.width - 3, img.height - 3)];
  }, fs.readFileSync(darkPng.file).toString('base64'));
  L.check('dark theme: the exported PNG is white in every corner', corner.every((p) => p.every((v) => v >= 250)), corner);
  await app.setTheme('light');
  await page.waitForTimeout(800);
  await app.waitDiagram();

  // ---- 13: the report can colour its diagram --------------------------------------------------------
  await app.clickTab('report');
  await page.locator('#tabpanel-report [data-report-generate]').waitFor({ state: 'visible' });
  const fvBox = page.locator('#tabpanel-report [data-report-fv]');
  L.check('report: there is an option to colour the diagram by importance', (await fvBox.count()) === 1 && !(await fvBox.isChecked()) && /Fussell-Vesely/.test(await page.locator('#tabpanel-report').textContent()));
  if (await page.locator('#tabpanel-report [data-report-generate]').isEnabled()) {
    const sent = [];
    let importanceCalls = 0;
    const onRequest = (req) => { if (/\/api\/analysis\/importance$/.test(req.url())) importanceCalls += 1; };
    page.on('request', onRequest);
    await page.route('**/api/report/docx', async (route) => {
      sent.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', headers: { 'Content-Disposition': 'attachment; filename="ux3_report.docx"' }, body: 'PK-not-a-real-report' });
    });
    const pngSize = async (b64) => page.evaluate(async (data) => { const img = new Image(); img.src = 'data:image/png;base64,' + data; await img.decode(); return { w: img.width, h: img.height }; }, b64);
    await Promise.all([page.waitForEvent('download'), page.locator('#tabpanel-report [data-report-generate]').click()]);
    await fvBox.check();
    await Promise.all([page.waitForEvent('download'), page.locator('#tabpanel-report [data-report-generate]').click()]);
    const sizes = [await pngSize(sent[0].diagramPng), await pngSize(sent[1].diagramPng)];
    L.check('report: plain by default; with the option the picture carries the legend (it is taller) and importance was computed',
      sent.length === 2 && importanceCalls === 1 && sizes[1].h > sizes[0].h + 60 && sizes[1].w >= sizes[0].w, { sizes, importanceCalls });
    await fvBox.uncheck();
    page.off('request', onRequest);
    await page.unroute('**/api/report/docx');
  } else {
    L.info('report: Word export is not installed here, the request was not checked');
  }

  // ---- smaller: the rare-event sum says what it is ---------------------------------------------------
  await app.clickTab('cutsets');
  await page.locator('#tabpanel-cutsets .anl-table').waitFor({ state: 'visible' });
  const rare = await page.evaluate(() => {
    const s = document.querySelector('#tabpanel-cutsets [data-stat="rare"]');
    return s ? { text: s.textContent, title: s.title, over: Boolean(s.querySelector('[data-role="rare-over"]')) } : null;
  });
  L.check('cut sets: a rare-event sum above 1 is marked as a sum, not a probability', !!rare && rare.over && /not a probability/.test(rare.text) && /upper bound/.test(rare.title) && Number((/Rare-event\s+([0-9.]+)/.exec(rare.text) || [])[1]) > 1, rare);

  // ---- 38: uncertainty for every event at once ----------------------------------------------------------
  await app.clickTab('uncertainty');
  const unc = page.locator('#tabpanel-uncertainty');
  await unc.locator('[data-role="run"]').waitFor({ state: 'visible' });
  await unc.locator('[data-field="n"]').fill('2000');
  await unc.locator('[data-field="seed"]').fill('7');
  await unc.locator('[data-role="run"]').click();
  await unc.locator('[data-stat="std"]').waitFor({ state: 'visible', timeout: 20000 });
  const flat = { chart: await unc.locator('svg.anl-chart').count(), note: await unc.locator('[data-role="no-spread"]').isVisible(), std: await unc.locator('[data-stat="std"] b').textContent() };
  L.check('uncertainty: with no distribution there is no chart, and a sentence says why', flat.chart === 0 && flat.note && L.parseNum(flat.std) === 0, flat);
  const applyAll = unc.locator('[data-role="apply-all"]');
  L.check('uncertainty: one button gives every event without one a lognormal EF=3', /EF=3/.test(await applyAll.textContent()) && (await applyAll.getAttribute('data-count')) === '5' && await applyAll.isEnabled(), await applyAll.textContent());
  await clearToasts();
  const undoBefore = (await state()).canUndo;
  await applyAll.click();
  await waitFor(async () => (await toasts()).some((t) => /Gave 5 basic event/.test(t)));
  const withUnc = [];
  const walk = (n) => { if (!(n.children || []).length && n.quant && n.quant.unc) withUnc.push([n.id, n.quant.unc.dist, n.quant.unc.ef]); (n.children || []).forEach(walk); };
  walk((await state()).tree);
  L.check('uncertainty: all five events have it', withUnc.length === 5 && withUnc.every((u) => u[1] === 'lognormal' && u[2] === 3), withUnc);
  L.check('uncertainty: the button has nothing left to do', await applyAll.isDisabled() && (await applyAll.getAttribute('data-count')) === '0');
  await unc.locator('[data-role="run"]').click();
  await waitFor(async () => (await unc.locator('svg.anl-chart').count()) === 1, 20000);
  L.check('uncertainty: now there is a spread, and a chart', (await unc.locator('svg.anl-chart').count()) === 1 && !(await unc.locator('[data-role="no-spread"]').isVisible()) && L.parseNum(await unc.locator('[data-stat="std"] b').textContent()) > 0);
  await app.shot('ux3_uncertainty_' + label);
  await page.locator('#btn-undo').click();
  await page.waitForTimeout(600);
  const left = [];
  const walk2 = (n) => { if (n.quant && n.quant.unc) left.push(n.id); (n.children || []).forEach(walk2); };
  walk2((await state()).tree);
  L.check('uncertainty: one Undo takes all of it back', left.length === 0 && (await state()).canUndo === undoBefore, left);

  // ---- 37: an event tree is called one -------------------------------------------------------------------
  await app.clickTab('details');
  await clearToasts();
  await page.locator('#mode-select').selectOption('ETA');
  await waitFor(async () => (await state()).metadata.mode === 'ETA');
  await page.waitForTimeout(900);
  await app.waitDiagram();
  const eta = await page.evaluate(() => ({
    label: document.querySelector('#headline .headline__label').textContent,
    title: document.getElementById('headline').title,
    tabs: ['quant', 'cutsets', 'importance', 'uncertainty'].map((id) => { const b = document.getElementById('tab-' + id); return [b.classList.contains('is-unavailable'), b.title]; }),
    others: ['details', 'validation', 'trace', 'fmea', 'report'].map((id) => document.getElementById('tab-' + id).classList.contains('is-unavailable')),
    gates: document.querySelectorAll('#diagram-root g.node.fta-gate, #diagram-root g.node.fta-event').length,
    boxes: document.querySelectorAll('#diagram-root g.node').length,
    chips: document.querySelectorAll('#tree-root .fta-tree-gate').length,
    probs: document.querySelectorAll('#tree-root .fta-tree-prob').length,
    analyze: Array.from(document.querySelectorAll('#ai-root .chat__action')).map((b) => b.textContent),
    placeholder: document.querySelector('#ai-root .chat__input').placeholder,
  }));
  L.check('ETA: the headline is the initiating event', eta.label === 'Initiating event:' && /initiating event/.test(eta.title), eta.label);
  L.check('ETA: the four fault-tree tabs are greyed and say why', eta.tabs.every((x) => x[0] && /Not available for an event tree/.test(x[1])) && eta.others.every((x) => !x), eta.tabs);
  L.check('ETA: the diagram draws boxes only, no gate or event symbols', eta.gates === 0 && eta.boxes === 7, { gates: eta.gates, boxes: eta.boxes });
  L.check('ETA: tree rows have no gate chip, and still a probability', eta.chips === 0 && eta.probs === 7, { chips: eta.chips, probs: eta.probs });
  L.check('ETA: the assistant says ETA and "event tree"', eta.analyze.includes('Analyze ETA') && eta.analyze.includes('Update ETA') && /event tree/.test(eta.placeholder), eta.analyze);
  L.check('ETA: the switch is announced by name, not as "Metadata updated."', (await toasts()).some((t) => /^Switched to ETA \(event tree\)/.test(t)) && !(await toasts()).some((t) => /Metadata updated/.test(t)), await toasts());
  await app.shot('ux3_eta_' + label);
  await app.clickTab('cutsets');
  await page.waitForTimeout(300);
  L.check('ETA: a greyed tab still opens and shows the notice', await page.locator('#tabpanel-cutsets .anl-eta').isVisible());
  await app.clickTab('details');
  await clearToasts();
  await page.locator('#mode-select').selectOption('FTA');
  await waitFor(async () => (await state()).metadata.mode === 'FTA');
  await page.waitForTimeout(900);
  await app.waitDiagram();
  const fta = await page.evaluate(() => ({
    label: document.querySelector('#headline .headline__label').textContent,
    off: document.querySelectorAll('#bottom-tabs .is-unavailable').length,
    gates: document.querySelectorAll('#diagram-root g.node.fta-gate').length,
    analyze: Array.from(document.querySelectorAll('#ai-root .chat__action')).map((b) => b.textContent),
  }));
  L.check('FTA again: top event, all tabs, gate symbols, "Analyze FTA"', fta.label === 'Top event:' && fta.off === 0 && fta.gates === 2 && fta.analyze.includes('Analyze FTA') && (await toasts()).some((t) => /^Switched to FTA/.test(t)), fta);

  // ---- 48: the assistant, not set up ----------------------------------------------------------------------
  const chat = page.locator('#ai-root');
  L.check('assistant: the switch is "Formatted", not "MD"', (await chat.locator('.chat__md').textContent()) === 'Formatted');
  await chat.locator('.chat__action', { hasText: 'Analyze FTA' }).click({ force: true });
  await chat.locator('.chat__action', { hasText: 'Analyze FTA' }).click({ force: true });
  await chat.locator('.chat__action', { hasText: 'Update FTA' }).click({ force: true });
  await page.waitForTimeout(300);
  L.check('assistant: "no provider yet" is said once, however often a button is pressed', (await chat.locator('.chat-msg[data-kind="not-configured"]').count()) === 1 && (await chat.locator('.chat-msg', { hasText: 'No provider is set up yet' }).count()) === 1);

  // ---- 47: the setup dialog -----------------------------------------------------------------------------------
  await page.locator('#btn-ai-settings').click();
  const setup = page.locator('.fta-modal');
  await setup.locator('.aiset-form').waitFor({ state: 'visible' });
  const picked = await setup.evaluate((m) => {
    const on = m.querySelector('.aiset-provider__radio:checked');
    const cards = Array.from(m.querySelectorAll('.aiset-provider')).map((c) => ({ name: c.querySelector('.aiset-provider__name').textContent, hint: (c.querySelector('.aiset-provider__hint') || {}).textContent || '' }));
    return { value: on ? on.value : null, cards, disclosure: (m.querySelector('[data-role="disclosure"]') || {}).textContent || '' };
  });
  const copilot = picked.cards.find((c) => /Copilot|Azure/i.test(c.name));
  L.check('AI setup: Google Gemini is ticked when nothing is configured', /gemini|google/i.test(picked.value || ''), picked.value);
  L.check('AI setup: one line says the tree is sent to the chosen provider', /whole tree/.test(picked.disclosure) && /sent to the provider you choose/.test(picked.disclosure), picked.disclosure);
  L.check('AI setup: Microsoft Copilot says what it needs', !!copilot && /Azure OpenAI resource of your own/.test(copilot.hint), copilot);
  await app.shot('ux3_ai_setup_' + label);
  await page.keyboard.press('Escape');
  await setup.waitFor({ state: 'detached' });

  // ---- 45 + 46: the assistant, set up (every request answered here) ---------------------------------------
  const calls = { chat: [], conversation: 0 };
  let chatAnswer = null; // set per step: an async (route) => {...}
  let saved = { ok: true, messages: [], changes: [], pendingUpdate: null };
  await page.route('**/api/state', async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    body.aiConfigured = true;
    body.capabilities.aiConfigured = true;
    await route.fulfill({ response: res, json: body });
  });
  await page.route('**/api/ai/chat', async (route) => {
    calls.chat.push(route.request().postDataJSON());
    await chatAnswer(route);
  });
  await page.route('**/api/ai/conversation', async (route) => {
    if (route.request().method() !== 'GET') { await route.fulfill({ json: { ok: true, cleared: true, changes: [] } }); return; }
    calls.conversation += 1;
    await route.fulfill({ json: saved });
  });
  await page.reload();
  await L.waitBoot(page);
  await app.waitDiagram();
  const input = chat.locator('.chat__input');
  const send = chat.locator('.chat__send');
  const stop = chat.locator('[data-role="stop"]');
  L.check('assistant: a reload asks the server for the conversation', calls.conversation >= 1 && (await chat.locator('.chat-msg[data-restored]').count()) === 0, calls.conversation);

  // Stop: the answer never comes while we wait.
  let release = null;
  chatAnswer = (route) => new Promise((resolve) => { release = async () => { await route.fulfill({ json: { ok: true, reply: 'Too late.', changes: [] } }); resolve(); }; });
  await input.fill('What fails first?');
  await send.click();
  await stop.waitFor({ state: 'visible' });
  L.check('assistant: while it waits there is a Stop button', (await stop.textContent()) === 'Stop' && (await input.inputValue()) === '');
  await stop.click();
  await page.waitForTimeout(200);
  const stopped = { text: await input.inputValue(), busy: await chat.locator('.chat').getAttribute('data-busy'), said: await chat.locator('.chat-msg', { hasText: 'Stopped waiting' }).count(), stop: await stop.isVisible() };
  L.check('assistant: Stop gives the panel and the typed message back', stopped.text === 'What fails first?' && stopped.busy === 'false' && stopped.said === 1 && !stopped.stop, stopped);
  await release();
  await page.waitForTimeout(300);
  L.check('assistant: an answer that arrives after Stop is not shown', (await chat.locator('.chat-msg', { hasText: 'Too late.' }).count()) === 0);

  // A request that fails gives the text back.
  chatAnswer = (route) => route.fulfill({ status: 502, json: { ok: false, error: { code: 'AI_CALL_FAILED', message: 'The provider could not be reached.' } } });
  await input.fill('Second try');
  const markFail = app.errMark();
  await send.click();
  await chat.locator('.chat-msg--error', { hasText: 'could not be reached' }).waitFor({ state: 'visible' });
  L.check('assistant: a failed send puts the message back in the box', (await input.inputValue()) === 'Second try');
  // The provider's own failure, reported as a reply.
  chatAnswer = (route) => route.fulfill({ json: { ok: true, reply: 'AI Error: quota exceeded for this key', changes: [] } });
  await send.click();
  const errRow = chat.locator('.chat-msg[data-kind="ai-error"]');
  await errRow.waitFor({ state: 'visible' });
  L.check('assistant: an "AI Error:" reply is drawn as an error, and the message is kept', (await errRow.getAttribute('data-role')) === 'error' && /quota exceeded/.test(await errRow.textContent()) && !/AI Error:/.test(await errRow.locator('.chat-msg__body').textContent()) && (await input.inputValue()) === 'Second try');
  L.check('assistant: the only console errors were the refused request', app.errorsSince(markFail, [/502/, /AI_CALL_FAILED/, /could not be reached/]).length === 0, app.errorsSince(markFail, [/502/, /AI_CALL_FAILED/, /could not be reached/]));

  // A reply with suggestions: names, links, readable fields.
  const changes = [
    { index: 0, changeType: 'edit', targetId: 'root_1', description: 'Raise the valve probability', data: { probability: 0.5, notes: 'Field data 2025' } },
    { index: 1, changeType: 'add', targetId: 'root_0', description: 'Add a common cause', data: { id: 'ccf', name: 'Common-cause failure', type: 'Event', probability: 0.001 } },
  ];
  chatAnswer = (route) => route.fulfill({ json: { ok: true, reply: 'Two **suggestions**.', changes } });
  await send.click();
  const card = chat.locator('.chat-changes').last();
  await card.waitFor({ state: 'visible' });
  const cardInfo = await card.evaluate((c) => ({
    titles: Array.from(c.querySelectorAll('.chat-changes__text')).map((e) => e.textContent),
    targets: Array.from(c.querySelectorAll('.chat-changes__target')).map((e) => e.textContent),
    links: Array.from(c.querySelectorAll('.chat-link')).map((e) => [e.textContent, e.dataset.node]),
    fields: Array.from(c.querySelectorAll('.chat-changes__field')).map((e) => e.textContent),
    raw: c.querySelectorAll('pre').length,
  }));
  L.check('suggestions: each says what it does in a word, not [EDIT]', JSON.stringify(cardInfo.titles) === JSON.stringify(['Change: Raise the valve probability', 'Add: Add a common cause']), cardInfo.titles);
  L.check('suggestions: the node is named, as a link', JSON.stringify(cardInfo.targets) === JSON.stringify(['Node: Valve sticks', 'Under: Pumps fail']) && JSON.stringify(cardInfo.links) === JSON.stringify([['Valve sticks', 'root_1'], ['Pumps fail', 'root_0']]), cardInfo);
  L.check('suggestions: the changes are readable, old to new, with no raw JSON',
    cardInfo.raw === 0 && cardInfo.fields.includes('probability: 0.05 → 0.5') && cardInfo.fields.includes('name: Common-cause failure') && !cardInfo.fields.some((f) => /^id:/.test(f)), cardInfo.fields);
  await row('root').click();
  await card.locator('.chat-link', { hasText: 'Valve sticks' }).click();
  await page.waitForTimeout(300);
  L.check('suggestions: the link selects the node', (await app.selectedId()) === 'root_1' && (await meta()) === 'Selected: Valve sticks', await app.selectedId());
  await app.shot('ux3_suggestion_card_' + label);

  // After a reload the conversation and the card are there again.
  saved = {
    ok: true,
    messages: [
      { role: 'user', kind: 'chat', content: 'What fails first?' },
      { role: 'assistant', kind: 'chat', content: 'The **valve**, most likely.' },
      { role: 'user', kind: 'analyze' },
      { role: 'assistant', kind: 'analyze', content: 'Two suggestions.' },
      { role: 'user', kind: 'update' },
      { role: 'assistant', kind: 'update' },
    ],
    changes,
    pendingUpdate: null,
  };
  await page.reload();
  await L.waitBoot(page);
  await app.waitDiagram();
  await chat.locator('.chat-changes').waitFor({ state: 'visible' });
  const restored = await chat.evaluate((c) => ({
    rows: Array.from(c.querySelectorAll('.chat-msg[data-restored]')).map((r) => [r.dataset.role, r.querySelector('.chat-msg__body').textContent]),
    bold: c.querySelector('.chat-msg[data-restored][data-role="assistant"] strong') ? c.querySelector('.chat-msg[data-restored][data-role="assistant"] strong').textContent : null,
    note: c.querySelectorAll('.chat-msg[data-kind="restored"]').length,
    cards: c.querySelectorAll('.chat-changes').length,
    live: c.querySelector('.chat-changes').dataset.retired !== 'true',
  }));
  L.check('reload: the conversation is painted again, in order',
    JSON.stringify(restored.rows) === JSON.stringify([
      ['user', 'What fails first?'], ['assistant', 'The valve, most likely.'],
      ['user', 'Analyze this FTA and provide suggestions.'], ['assistant', 'Two suggestions.'],
      ['user', 'Update this FTA with your suggestions, preserving the original JSON structure.'], ['system', 'The assistant answered with a rewritten tree.'],
    ]) && restored.note === 1, restored.rows);
  L.check('reload: replies are formatted as before, and the pending suggestions are back as a live card', restored.bold === 'valve' && restored.cards === 1 && restored.live, restored);
  await app.shot('ux3_chat_reloaded_' + label);

  // New: the card was for the other document.
  await page.locator('.actionbar [data-action="new"]').click();
  await page.waitForTimeout(400);
  await L.discardIfAsked(page);
  await waitFor(async () => (await state()).currentPath === null);
  await page.waitForTimeout(400);
  const retired = await chat.locator('.chat-changes').first().evaluate((c) => ({ retired: c.dataset.retired, status: c.querySelector('.chat-changes__status').textContent, disabled: Array.from(c.querySelectorAll('button.btn')).every((b) => b.disabled) }));
  L.check('suggestions: New retires the card made for the other analysis', retired.retired === 'true' && /another analysis/.test(retired.status) && retired.disabled, retired);
  await page.unroute('**/api/ai/chat');
  await page.unroute('**/api/ai/conversation');
  await page.unroute('**/api/state');

  // ---- Japanese ------------------------------------------------------------------------------------------------
  await openA();
  await app.setLanguage('ja');
  await page.waitForTimeout(500);
  await row('root_1').click();
  await row('root_2').click({ modifiers: ['Control'] });
  await app.clickTab('importance');
  await page.locator('#tabpanel-importance .anl-table').waitFor({ state: 'visible' });
  const ja = await page.evaluate(() => ({
    settings: document.querySelector('#diagram-root [data-role="diagram-settings"]').textContent,
    meta: document.getElementById('details-meta').textContent,
    copy: document.querySelector('#tabpanel-importance [data-role="copy"]').textContent,
    md: document.querySelector('#ai-root .chat__md').textContent,
    max: document.getElementById('btn-bottom-max').title,
    gate: document.querySelector('#tree-root .fta-tree-gate').title,
  }));
  L.check('ja: the new texts are Japanese', /設定/.test(ja.settings) && ja.meta === '2 件を選択中' && ja.copy === 'CSV をコピー' && ja.md === '整形表示' && /広げる/.test(ja.max) && /ゲート/.test(ja.gate), ja);
  await page.locator('#mode-select').selectOption('ETA');
  await page.waitForTimeout(900);
  const jaEta = await page.evaluate(() => ({ label: document.querySelector('#headline .headline__label').textContent, tab: document.getElementById('tab-cutsets').title, analyze: document.querySelector('#ai-root .chat__action').textContent }));
  L.check('ja: ETA wording too', jaEta.label === '起因事象:' && /イベントツリー/.test(jaEta.tab) && jaEta.analyze === 'ETA解析', jaEta);
  await app.shot('ux3_ja_' + label);
  await page.keyboard.press('Control+z');
  await page.waitForTimeout(600);
  await app.setLanguage('en');
  await app.clickTab('details');
  await app.api('post', '/new', { force: true });

  const errs = app.errorsSince(0, [/502/, /AI_CALL_FAILED/, /could not be reached/]);
  L.check('no console errors in the whole section', errs.length === 0, errs.slice(0, 5));
  await app.context.close();
}

L.runSection('ux3', run);
