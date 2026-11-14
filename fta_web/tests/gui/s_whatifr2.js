// What-if tab (F4) x other features: cross checks after the merge of F2A, F3 and F4 (feature FR, task X1).
//   node s_whatifr2.js <url> <label> <root>
//
// Every case is one function in CASES (name, function); the runner calls them in order, each on a freshly opened
// document, and a case that throws is reported as one failed check. A later task adds a case by appending one
// entry to CASES; the helpers below (openTab, giveFactor, read, message ...) are shared by all cases.
//
// Case gridPaste  F3 + F4 (PLAN section 6): a what-if factor is set, then a Grid paste that changes the document
//                 revision. Coming back to the What-if tab every factor is 1 (no banner, no chip, data-factors 0),
//                 the what-if top event is the new baseline (the headline, the same float) and the message
//                 "The document changed, so the factors were reset to 1." is shown (data-code DOCUMENT_CHANGED).
// Cases caution_*  X3 (CR-20261102-whatif-caution.md, FR DESIGN revision 2, sections 2 and 8.2, G1 to G12): a badge `whatif-caution-badge` in the empty
//                 corner cell of the values table and the line `whatif-caution` in flow under the table, fed by `cautions` of POST /api/whatif.
//                 Nothing is pinned or laid over a number. Check names start whatifr2_caution_<case>_.
//   ccfone     G1/G2  CCF_Q_ONE (R1 at q 0.5, factor 2), the exact string en and ja, badge in view at scrollTop 0, no role/aria-live,
//                     a language switch repaints without a request
//   position   G3     every rect above the line is identical with and without the caution (0 px); badge in the head row; the line is static
//                     below the table; elementFromPoint finds the numbers
//   oneline    G4     CCF_HIGH_Q, STANDBY_LARGE_LT, CUTSETS_TRUNCATED and a two-caution form, en and ja: one text line when scrolled into view (shots)
//   badge      G4b    click, Enter and Space on the badge give the line focus; no request, no change of the factor
//   multi      G5     several cautions: first text + "(and N more)", the rest hidden, the badge title, server order (shots)
//   boundary   G6     q 0.005 x 2 (Q_t 0.01) has none, x 2.0000001 has; field 1 and Reset all remove banner, badge and line in the same task; per-event Reset too
//   cutoff     G7     the cutoff note and the caution are two things (cutoff only, cutoff + order, order only)
//   nofactor   G8     no factor, no caution; a document change (Grid paste) removes it
//   states     G9     loading, empty, ETA: none; a failed answer keeps badge and line with the error line
//   minpane    G10    the 140 px pane: same rects, nothing pinned, badge reachable (shots)
//   stacked    G11    the stacked shell and a 440 px window (shots)
//   texts      G12    no raw key, no FN-64 wording, all four cautions and the badge, en and ja
//   focus      -      keyboard to the badge and the line (shots with the ring); the focus goes to the picker when the caution is removed under it
//   oldserver  -      an entry without limit (older server) and an unknown code (newer server), by stubbing the answer
// Cases caution_notapplied_*  Y3 (CR-20261104-whatif-group-not-applied.md, FR DESIGN section 10, G13 to G16): CCF_NOT_APPLIED, first in the order,
//                 text "CCF group not applied at baseline; CCF not included" (en) / the ja string of whatifcaution.js; a factor other than 1 on a
//                 member of a group that is not applied at baseline (R1 shape, B at 2e-3: the members differ).
//   notapplied G13    the exact string en and ja, data-codes, badge title, the what-if number is the members scaled alone (no CCF event) (shots)
//   two        G14    CCF_NOT_APPLIED + a standby event: data-codes order, first text then "(and 1 more)" / "（ほか 1 件）", the rest hidden (shots)
//   position   G15    default pane and 140 px pane: every rect above the line identical with and without the caution (0 px), badge in the head row
//   reset      G16    a factor on a non-member gives none; the field back to 1 / Reset all / the per-event Reset remove badge and line in the same task
// The screenshots go to the output folder of the run (lib.js shot): whatifr2-caution-*.png.
//
// Every check name starts with whatifr2_.
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const TID = (id) => `[data-testid="${id}"]`;
const CELL = (nodeId, col) => `[data-testid="grid-cell"][data-node-id="${nodeId}"][data-column="${col}"]`;
const STALE_EN = 'The document changed, so the factors were reset to 1.';

// ---- documents --------------------------------------------------------------------------------------------------
const leaf = (id, name, q) => ({ id, name, type: 'Event', logicGate: 'OR', probability: q, notes: '', links: [], children: [], quant: { model: 'fixed' } });
/** root OR [E1 (q 1e-3), E2 (q 2e-3)], both fixed: the top event is 1 - (1 - q1)(1 - q2). */
const twoDoc = () => ({
  title: 'What-if cross check', date: '2026-11-02', mode: 'FTA',
  tree: { id: 'root', name: 'Top event', type: 'Root', logicGate: 'OR', probability: 1.0, notes: '', links: [], children: [leaf('E1', 'Pump E1', 1e-3), leaf('E2', 'Pump E2', 2e-3)] },
});
const union = (ps) => 1 - ps.reduce((acc, p) => acc * (1 - p), 1);
const close = (a, b, rel) => typeof a === 'number' && Number.isFinite(a) && typeof b === 'number' && (b === 0 ? a === 0 : Math.abs(a - b) <= rel * Math.abs(b));
const num = (c) => (c && c.value !== null && c.value !== '' ? Number(c.value) : null);
const norm = (s) => String(s).replace(/\s+/g, ' ').trim();

// ---- X3: documents, strings ---------------------------------------------------------------------------------------
const gate = (id, name, kind, children) => ({ id, name, type: 'Event', logicGate: kind, probability: 1.0, notes: '', links: [], children });
const pump = (id, q) => leaf(id, 'Pump ' + id, q);
const standbyLeaf = (id, name, lambda, tau) => ({ id, name, type: 'Event', logicGate: 'OR', probability: 0, notes: '', links: [], children: [], quant: { model: 'standby', lambda, tau } });
const betaGroup = (id, name, members) => ({ id, name, model: 'beta', beta: 0.1, alpha: null, testing: null, members, source: 'test' });
/** root OR [children]; `groups` are CCF groups, `analysis` the other analysis settings. */
const wrapDoc = (title, children, groups, analysis) => {
  const doc = { title, date: '2026-11-02', mode: 'FTA' };
  if (groups) doc.fileFormatVersion = 2;
  doc.tree = { id: 'root', name: 'Top event', type: 'Root', logicGate: 'OR', probability: 1.0, notes: '', links: [], children };
  const an = Object.assign({}, groups ? { ccfGroups: groups } : {}, analysis || {});
  if (Object.keys(an).length) doc.analysis = an;
  return doc;
};
/** AND [ OR [A 0.01, B 0.1], OR [X 0 (OR link to A), C 0.1] ]: A is reached twice, so the headline is the MCUB. */
const repeatedTree = () => gate('RT', 'Both branches', 'AND', [
  gate('RG1', 'Branch 1', 'OR', [pump('A', 0.01), pump('B', 0.1)]),
  gate('RG2', 'Branch 2', 'OR', [Object.assign(pump('X', 0), { links: [{ target_id: 'A', relation: 'OR' }] }), pump('C', 0.1)]),
]);
/** The same with a third branch OR [D, E]: cut sets of order 2 ({A, D}, {A, E}) and 3, so that a cutoff and an order limit both drop sets. */
const threeTree = () => gate('RT', 'Three branches', 'AND', [
  gate('RG1', 'Branch 1', 'OR', [pump('A', 0.01), pump('B', 0.1)]),
  gate('RG2', 'Branch 2', 'OR', [Object.assign(pump('X', 0), { links: [{ target_id: 'A', relation: 'OR' }] }), pump('C', 0.1)]),
  gate('RG3', 'Branch 3', 'OR', [pump('D', 0.1), pump('E', 0.1)]),
]);
/** FR DESIGN section 4, word for word (an independent copy: the pytest file holds the other). */
const T = {
  en: {
    ccfOne: 'A CCF member is at probability 1. Typed into the document, the group would not be applied.',
    ccfHigh: 'A CCF member\'s probability is above {limit}. Check the CCF result.',
    standby: 'A scaled standby event has λτ above {limit}, where the λτ/2 approximation is poor.',
    cutsets: 'Cut sets are limited by max order or max count; some may be missing from the what-if number.',
    more: '(and {n} more)',
    badge: 'Caution',
    cutoffNote: 'cut sets from nominal values',
    // Y3 (CR-20261104, FR DESIGN 10.4): the CR's own English text
    notApplied: 'CCF group not applied at baseline; CCF not included',
  },
  ja: {
    ccfOne: 'CCF グループのメンバーの確率が 1 です。文書に入力するとグループは適用されなくなります。',
    ccfHigh: 'CCF グループのメンバーの確率が {limit} を超えています。CCF の結果を確認してください。',
    standby: '倍率をかけた待機系事象の λτ が {limit} を超えており、λτ/2 近似の精度が低下します。',
    cutsets: '最大次数または最大件数でカットセットが制限されており、一部のカットセットが What-if 値に含まれない場合があります。',
    more: '（ほか {n} 件）',
    badge: '注意',
    cutoffNote: 'カットセットは公称値から求めています',
    notApplied: 'ベースラインで CCF グループが適用されていないため、CCF は含まれません。',
  },
};
const KEY_OF = { CCF_NOT_APPLIED: 'notApplied', CCF_Q_ONE: 'ccfOne', CCF_HIGH_Q: 'ccfHigh', STANDBY_LARGE_LT: 'standby', CUTSETS_TRUNCATED: 'cutsets' };
/** The five codes in server order (Y3: CCF_NOT_APPLIED first). */
const ORDER5 = ['CCF_NOT_APPLIED', 'CCF_Q_ONE', 'CCF_HIGH_Q', 'STANDBY_LARGE_LT', 'CUTSETS_TRUNCATED'];
/** The text of one caution (the threshold filled in: 0.01 for CCF_HIGH_Q, 0.2 for STANDBY_LARGE_LT). */
const textOf = (code, lang) => T[lang][KEY_OF[code]].replace('{limit}', code === 'CCF_HIGH_Q' ? '0.01' : '0.2');
/** The visible line for these codes (server order): the first text and, for two or more, one space and "(and N more)". */
/** en: one space before "(and N more)"; ja: none before "（ほか N 件）" (text lens, round 1). */
const lineOf = (codes, lang) => textOf(codes[0], lang) + (codes.length > 1 ? (lang === 'ja' ? '' : ' ') + T[lang].more.replace('{n}', String(codes.length - 1)) : '');
const restOf = (codes, lang) => codes.slice(1).map((c) => textOf(c, lang)).join(' ');
const FN64_EN = /\b(comply|complies|compliant|compliance|conform|conforms|conformity|certified|certification)\b/i;
const FN64_JA = ['準拠', '適合', '認証'];

const CELLS = { topBaseline: 'whatif-top-baseline', topWhatif: 'whatif-top-whatif' };

const readTab = (pg) => pg.evaluate((cells) => {
  const q = (id) => document.querySelector(`[data-testid="${id}"]`);
  const out = { root: null, cells: {}, picker: null };
  const root = q('whatif-root');
  if (root) {
    const d = root.dataset;
    out.root = { state: d.state, factors: d.factors, pending: d.pending, seqSent: d.seqSent, seqApplied: d.seqApplied };
  }
  for (const [key, id] of Object.entries(cells)) {
    const e = q(id);
    out.cells[key] = e ? { value: e.dataset.value === undefined ? null : e.dataset.value } : null;
  }
  const pk = q('whatif-picker');
  if (pk) out.picker = { value: pk.value };
  return out;
}, CELLS);

const settledPred = (r) => Boolean(r.root) && r.root.state === 'ready' && r.root.pending === '0' && r.root.seqApplied === r.root.seqSent
  && ['topBaseline', 'topWhatif'].every((k) => r.cells[k] && r.cells[k].value !== null && r.cells[k].value !== '');

async function main(url, label, root) {
  L.setSection('whatifr2[' + label + ']');
  const twoName = `whatifr2_two_${label}.json`;
  fs.writeFileSync(path.join(root, twoName), JSON.stringify(twoDoc(), null, 2));

  const app = await L.openApp(url, { viewport: { width: 1400, height: 900 }, prefs: { 'fta.advanced': '1' } });
  const { page } = app;
  page.setDefaultTimeout(8000);
  page.on('dialog', (d) => { d.accept().catch(() => {}); });
  const posts = []; // the body of every POST /api/whatif this page sent
  page.on('request', (r) => { if (r.method() === 'POST' && /\/api\/whatif(\?|$)/.test(r.url())) posts.push(r.postData() || ''); });
  const written = []; // the documents the caution cases wrote into the sandbox root

  // ---- helpers shared by the cases ------------------------------------------------------------------------------
  const read = () => readTab(page);
  const waitRead = async (pred, timeout = 8000) => {
    const t0 = Date.now();
    let r;
    for (;;) {
      r = await read();
      let ok = false;
      try { ok = Boolean(pred(r)); } catch (_e) { ok = false; }
      if (ok) return { ok: true, r };
      if (Date.now() - t0 > timeout) return { ok: false, r };
      await sleep(60);
    }
  };
  const until = async (fn, timeout = 3000, step = 25) => {
    const t0 = Date.now();
    for (;;) {
      const v = await fn();
      if (v) return v;
      if (Date.now() - t0 > timeout) return null;
      await sleep(step);
    }
  };
  const headline = async () => (await app.api('get', '/analysis/summary')).headline;
  const chips = () => page.locator(TID('whatif-chip')).count();
  const bannerCount = () => page.locator(TID('whatif-banner')).count();
  const message = () => page.evaluate(() => { const m = document.querySelector('[data-testid="whatif-message"]'); return m ? { text: m.textContent.replace(/\s+/g, ' ').trim(), code: m.dataset.code || '' } : null; });

  const openDoc = async (name) => {
    await app.api('post', '/new', { force: true });
    const opened = await app.api('post', '/file/open', { path: path.join(root, name), force: true });
    if (opened.__error) throw new Error(`could not open ${name}: ${opened.status} ${opened.code}`);
    await page.evaluate(() => localStorage.removeItem('fta.bottomTab'));
    await page.reload();
    await L.waitBoot(page);
    await app.waitDiagram(60000);
    await page.waitForTimeout(600);
  };
  const showWhatif = async () => {
    await app.setAdvanced(true);
    await page.locator('#tab-whatif').click();
    await page.locator(TID('whatif-root')).waitFor({ state: 'visible' });
  };
  /** Open the document, show the What-if tab and wait until it has its baseline. */
  const openTab = async (name = twoName) => {
    await openDoc(name);
    await showWhatif();
    const w = await waitRead(settledPred, 20000);
    if (!w.ok) throw new Error('the What-if tab did not settle: ' + JSON.stringify(w.r.root));
    return w.r;
  };
  /** Give `id` a factor through the picker and the field; wait until `factorsAfter` entries and the top event `wantTop`. */
  const giveFactor = async (id, text, factorsAfter, wantTop, rel = 1e-9) => {
    await page.locator(TID('whatif-picker')).selectOption(id);
    const f = page.locator(TID('whatif-factor-input'));
    await f.fill(String(text));
    await f.press('Enter');
    const w = await waitRead((r) => settledPred(r) && r.root.factors === String(factorsAfter) && close(num(r.cells.topWhatif), wantTop, rel), 8000);
    if (!w.ok) throw new Error(`the factor ${text} on ${id} was not applied: ` + JSON.stringify(w.r.root));
    return w.r;
  };
  const openGrid = async () => {
    await app.clickTab('grid');
    await page.waitForSelector(TID('grid-root'), { timeout: 10000 });
    await page.waitForSelector(`${TID('grid-table')}, ${TID('grid-empty')}`, { timeout: 10000 });
  };
  /** A synthetic paste on a Grid cell (as the Grid sections do) and a wait until the paste is over. */
  const gridPaste = async (selector, clip) => {
    await page.locator(selector).click();
    await page.evaluate(async ([sel, text]) => {
      const target = document.querySelector(sel);
      const grid = document.querySelector('[data-testid="grid-root"]');
      const dt = new DataTransfer();
      dt.setData('text/plain', text);
      target.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
      const limit = performance.now() + 6000;
      await new Promise((r) => setTimeout(r, 60));
      while (grid.dataset.state === 'pasting' && performance.now() < limit) await new Promise((r) => setTimeout(r, 20));
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    }, [selector, clip]);
  };
  const revision = async () => (await app.api('get', '/revision')).revision;

  // ---- the cases ------------------------------------------------------------------------------------------------

  // F3 + F4: a factor, then a Grid paste that changes the revision.
  const caseGridPaste = async () => {
    const T = 'whatifr2_gridPaste_';
    const q1 = 1e-3;
    const q2Before = 2e-3;
    const q2After = 5e-3;
    const r0 = await openTab();
    const baseline0 = r0.cells.topBaseline.value;
    L.check(`${T}precondition_baseline: the baseline is 1 - (1 - 1e-3)(1 - 2e-3) = ${union([q1, q2Before])}`, close(num(r0.cells.topBaseline), union([q1, q2Before]), 1e-9), r0.cells);

    await giveFactor('E1', '10', 1, union([10 * q1, q2Before]));
    const withFactor = await giveFactor('E2', '20', 2, union([10 * q1, 20 * q2Before]));
    L.check(`${T}precondition_factor: the factors 10 on E1 and 20 on E2 are applied (banner shown, two chips, data-factors 2, what-if top event ${union([10 * q1, 20 * q2Before])})`,
      withFactor.root.factors === '2' && (await bannerCount()) === 1 && (await chips()) === 2 && withFactor.cells.topWhatif.value !== baseline0, { root: withFactor.root, top: withFactor.cells });

    // the Grid: paste a new q into E2 (a different value, so the revision moves)
    const revBefore = await revision();
    await openGrid();
    const cell = CELL('E2', 'q');
    const found = await until(async () => (await page.locator(cell).count()) === 1, 6000);
    L.check(`${T}precondition_grid: the Grid shows the q cell of E2`, Boolean(found), await page.locator(TID('grid-cell')).count());
    if (!found) return;
    await gridPaste(cell, String(q2After));
    const revAfter = await revision();
    const e2 = await app.api('get', '/nodes/E2');
    L.check(`${T}paste_changed_document: the paste set q of E2 to ${q2After} and the revision moved (${revBefore} -> ${revAfter})`,
      e2.node && e2.node.probability === q2After && revAfter !== revBefore, { node: e2.node && e2.node.probability, revBefore, revAfter });

    // back to the What-if tab
    await page.locator('#tab-whatif').click();
    await page.locator(TID('whatif-root')).waitFor({ state: 'visible' });
    const w = await waitRead((r) => settledPred(r) && r.root.factors === '0', 10000);
    const h = await headline();
    const r = w.r;
    L.check(`${T}factors_reset: every factor is back to 1 (data-factors 0, no banner, no chip, neither E1 nor E2 has a factor)`, w.ok && (await bannerCount()) === 0 && (await chips()) === 0, r.root);
    L.check(`${T}top_is_baseline: the what-if top event is the new baseline, the same float as the headline (${h}), and the baseline moved with the paste`,
      w.ok && r.cells.topWhatif.value === r.cells.topBaseline.value && r.cells.topBaseline.value === String(h) && r.cells.topBaseline.value !== baseline0 && close(h, union([q1, q2After]), 1e-9),
      { whatif: r.cells.topWhatif && r.cells.topWhatif.value, baseline: r.cells.topBaseline && r.cells.topBaseline.value, headline: h, before: baseline0 });
    const m = await message();
    L.check(`${T}message: the message "${STALE_EN}" is shown (data-code DOCUMENT_CHANGED)`, Boolean(m) && m.code === 'DOCUMENT_CHANGED' && norm(m.text) === STALE_EN, m);
  };

  // =====================================================================================================================
  // X3: the What-if caution line (CR-20261102-whatif-caution.md; FR DESIGN sections 2 and 8.2). Cases G1 to G12.
  // A badge in the empty corner cell of the table head and one line in flow under the table (design revision 2). The line names the first caution and counts the rest. The
  // server decides (cautions in POST /api/whatif); these cases drive the real tab, so a number is right only when it
  // shows. The strings below are an independent copy of FR DESIGN section 4 (the pytest file holds the other).
  // =====================================================================================================================
  const CAUTION_DOCS = {
    /** R1 shape: root OR [G1 AND [A, B]], beta group g1 (0.1); A and B fixed q. Optionally an independent event Z. */
    ccf: (key, q, withZ = false) => ({ name: `whatifr2_${key}_${label}.json`, doc: wrapDoc('Caution ' + key, [gate('G1', 'Pumps fail', 'AND', [pump('A', q), pump('B', q)])].concat(withZ ? [pump('Z', 1e-3)] : []), [betaGroup('g1', 'Feed pumps', ['A', 'B'])]) }),
    /** root OR [S standby (lambda 0.05, tau 2: lambda tau 0.1), OTH]. */
    standby: (key) => ({ name: `whatifr2_${key}_${label}.json`, doc: wrapDoc('Caution ' + key, [standbyLeaf('S', 'Standby S', 0.05, 2), pump('OTH', 1e-3)]) }),
    /** Repeated event A (X links to it): an MCUB headline. `cutsets` are the document's limits. */
    repeated: (key, cutsets) => ({ name: `whatifr2_${key}_${label}.json`, doc: wrapDoc('Caution ' + key, [repeatedTree()], null, { cutsets }) }),
    /** Three branches, A reached twice: cut sets of order 2 and 3, so that a cutoff and an order limit both drop sets. */
    three: (key, cutsets) => ({ name: `whatifr2_${key}_${label}.json`, doc: wrapDoc('Caution ' + key, [threeTree()], null, { cutsets }) }),
    /** One document that can fire all four codes: g1 (A, B at 0.5), g2 (D, E at 0.05), a standby S, maxOrder 1. */
    all: (key) => ({
      name: `whatifr2_${key}_${label}.json`,
      doc: wrapDoc('Caution ' + key, [gate('G1', 'Pumps fail', 'AND', [pump('A', 0.5), pump('B', 0.5)]), gate('G2', 'Valves fail', 'AND', [pump('D', 0.05), pump('E', 0.05)]), standbyLeaf('S', 'Standby S', 0.05, 2)],
        [betaGroup('g1', 'Feed pumps', ['A', 'B']), betaGroup('g2', 'Valves', ['D', 'E'])], { cutsets: { maxOrder: 1 } }),
    }),
    /** Y3: R1 shape but B at 2e-3, so the members differ and g1 (A, B) is NOT applied at baseline (FN-33); an independent event Z. */
    notApplied: (key) => ({ name: `whatifr2_${key}_${label}.json`, doc: wrapDoc('Caution ' + key, [gate('G1', 'Pumps fail', 'AND', [pump('A', 1e-3), pump('B', 2e-3)]), pump('Z', 1e-3)], [betaGroup('g1', 'Feed pumps', ['A', 'B'])]) }),
    /** The same with a standby event S (lambda 0.05, tau 2): CCF_NOT_APPLIED and STANDBY_LARGE_LT can fire together. */
    notAppliedStandby: (key) => ({ name: `whatifr2_${key}_${label}.json`, doc: wrapDoc('Caution ' + key, [gate('G1', 'Pumps fail', 'AND', [pump('A', 1e-3), pump('B', 2e-3)]), standbyLeaf('S', 'Standby S', 0.05, 2)], [betaGroup('g1', 'Feed pumps', ['A', 'B'])]) }),
    /** `all` plus g3 on F (1e-3) and H (2e-3), which differ: g3 is not applied. All five codes can fire. */
    all5: (key) => ({
      name: `whatifr2_${key}_${label}.json`,
      doc: wrapDoc('Caution ' + key, [gate('G1', 'Pumps fail', 'AND', [pump('A', 0.5), pump('B', 0.5)]), gate('G2', 'Valves fail', 'AND', [pump('D', 0.05), pump('E', 0.05)]), gate('G3', 'Fans fail', 'AND', [pump('F', 1e-3), pump('H', 2e-3)]), standbyLeaf('S', 'Standby S', 0.05, 2)],
        [betaGroup('g1', 'Feed pumps', ['A', 'B']), betaGroup('g2', 'Valves', ['D', 'E']), betaGroup('g3', 'Fans', ['F', 'H'])], { cutsets: { maxOrder: 1 } }),
    }),
  };
  const writeDoc = (spec) => { fs.writeFileSync(path.join(root, spec.name), JSON.stringify(spec.doc, null, 2)); written.push(spec.name); return spec.name; };

  /** The requests of POST /api/whatif this page sent (body parsed), in order. */
  const sent = () => posts.map((b) => { try { return JSON.parse(b); } catch (_e) { return null; } });
  /** Pick `id`, type `text` in the factor field, press Enter and wait until the request that carries it is answered (the
   *  tab settled, `count` entries). The text is committed exactly as typed. */
  const applyFactor = async (id, text, count) => {
    const mark = posts.length;
    await page.locator(TID('whatif-picker')).selectOption(id);
    const f = page.locator(TID('whatif-factor-input'));
    await f.fill(String(text));
    await f.press('Enter');
    const want = Number(text);
    const r = await until(async () => {
      const all = sent();
      if (all.length <= mark || !all[all.length - 1] || !all[all.length - 1].factors) return false;
      const got = all[all.length - 1].factors[id];
      if (want === 1 ? !(got === undefined || got === 1) : got !== want) return false;
      const reading = await read();
      return settledPred(reading) && reading.root.factors === String(count) ? reading : false;
    }, 12000, 60);
    if (!r) throw new Error(`the factor ${text} on ${id} was not answered (${count} entries): ` + JSON.stringify(await read().then((x) => x.root)));
    return r;
  };
  /** Everything the checks read about the badge and the line, in one round trip. */
  const readCaution = () => page.evaluate(() => {
    const q = (id) => document.querySelector(`[data-testid="${id}"]`);
    const rect = (e) => { if (!e) return null; const b = e.getBoundingClientRect(); return { left: b.left, top: b.top, right: b.right, bottom: b.bottom, w: b.width, h: b.height }; };
    const live = (e) => Boolean(e.closest('[aria-live],[role="status"]'));
    const c = q('whatif-caution');
    const b = q('whatif-caution-badge');
    const rootEl = q('whatif-root');
    const text = q('whatif-caution-text');
    const rest = q('whatif-caution-rest');
    return {
      present: Boolean(c), count: document.querySelectorAll('[data-testid="whatif-caution"]').length, badgeCount: document.querySelectorAll('[data-testid="whatif-caution-badge"]').length,
      id: c ? c.id : null, codes: c && c.dataset.codes !== undefined ? c.dataset.codes : null, n: c && c.dataset.count !== undefined ? c.dataset.count : null,
      text: text ? text.textContent : null, rest: rest ? rest.textContent : null, restHidden: rest ? rest.classList.contains('visually-hidden') : null,
      title: c ? c.getAttribute('title') : null, role: c ? c.getAttribute('role') : null, ariaLive: c ? c.getAttribute('aria-live') : null, liveAncestor: c ? live(c) : null,
      tabindex: c ? c.getAttribute('tabindex') : null, position: c ? getComputedStyle(c).position : null,
      badge: b ? {
        tag: b.tagName, type: b.getAttribute('type'), text: b.textContent.replace(/\s+/g, ' ').trim(), title: b.getAttribute('title'), n: b.dataset.count === undefined ? null : b.dataset.count,
        describedby: b.getAttribute('aria-describedby'), controls: b.getAttribute('aria-controls'), role: b.getAttribute('role'), ariaLive: b.getAttribute('aria-live'), liveAncestor: live(b),
        inHeadCorner: Boolean(b.closest('thead')) && b.parentElement.tagName === 'TD' && b.closest('tr').firstElementChild === b.parentElement,
      } : null,
      rootCodes: rootEl && rootEl.dataset.cautions !== undefined ? rootEl.dataset.cautions : null,
      rect: rect(c), textRect: rect(text), badgeRect: rect(b), sw: c ? c.scrollWidth : null, cw: c ? c.clientWidth : null,
    };
  });
  const waitCaution = async (pred, timeout = 6000) => {
    const t0 = Date.now();
    let c;
    for (;;) {
      c = await readCaution();
      let ok = false;
      try { ok = Boolean(pred(c)); } catch (_e) { ok = false; }
      if (ok) return { ok: true, c };
      if (Date.now() - t0 > timeout) return { ok: false, c };
      await sleep(50);
    }
  };
  const geom = () => page.evaluate(() => {
    const q = (id) => document.querySelector(`[data-testid="${id}"]`);
    const rect = (e) => { if (!e) return null; const b = e.getBoundingClientRect(); return { left: b.left, top: b.top, right: b.right, bottom: b.bottom, w: b.width, h: b.height }; };
    const panel = document.getElementById('tabpanel-whatif');
    const rootEl = q('whatif-root');
    const values = q('whatif-values');
    return {
      panel: rect(panel), root: rect(rootEl), slot: rect(q('whatif-banner-slot')), picker: rect(q('whatif-picker')), controls: rect(q('whatif-controls')), slider: rect(q('whatif-slider')),
      values: rect(values), head: values ? rect(values.querySelector('thead tr')) : null, cells: values ? Array.from(values.querySelectorAll('td, th')).map(rect) : [],
      colHeaders: values ? Array.from(values.querySelectorAll('th[scope="col"]')).map(rect) : [], top: rect(q('whatif-top-whatif')), ratio: rect(q('whatif-ratio')),
      caution: rect(q('whatif-caution')), badge: rect(q('whatif-caution-badge')), error: rect(q('whatif-error')), status: rect(rootEl ? rootEl.querySelector('.wi-status') : null),
      scroll: { panelTop: panel.scrollTop, rootTop: rootEl ? rootEl.scrollTop : null, panelSW: panel.scrollWidth, panelCW: panel.clientWidth, rootSW: rootEl ? rootEl.scrollWidth : null, rootCW: rootEl ? rootEl.clientWidth : null },
      vp: { w: window.innerWidth, h: window.innerHeight },
    };
  });
  const insideBox = (inner, outer, tol = 1) => Boolean(inner) && Boolean(outer) && inner.left >= outer.left - tol && inner.right <= outer.right + tol && inner.top >= outer.top - tol && inner.bottom <= outer.bottom + tol;
  /** Heights that are an impossible number when the element is missing, so that a check fails and does not throw. */
  const H = (r) => (r ? r.h : Infinity);
  /** The text is on the line: the line scrolls to nothing and the text box ends inside it. */
  const onLine = (c) => Boolean(c.rect) && Boolean(c.textRect) && c.sw <= c.cw && c.textRect.right <= c.rect.right + 1;
  /** Intersection area of two rects (Infinity when one is missing, so that a "no overlap" check fails). */
  const area = (a, b) => (!a || !b ? Infinity : Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)));
  const NO_AREA = 0.5; // px squared: sub-pixel rounding of two touching boxes
  const exactRect = (a, b) => Boolean(a) && Boolean(b) && ['left', 'top', 'w', 'h'].every((k) => Math.abs(a[k] - b[k]) <= 0.01);
  const exactRects = (a, b) => a.length === b.length && a.every((r, i) => exactRect(r, b[i]));
  const noSideways = (g) => g.scroll.rootSW <= g.scroll.rootCW && g.scroll.panelSW <= g.scroll.panelCW;
  /** The word on the badge: the text of the button without a leading "!" of its round mark. */
  const badgeWord = (b) => (b ? b.text.replace(/^!\s*/, '') : null);
  const scrollTop0 = () => page.evaluate(() => { for (const e of [document.getElementById('tabpanel-whatif'), document.querySelector('[data-testid="whatif-root"]')]) e.scrollTop = 0; });
  const scrollTo = (testid) => page.evaluate((id) => { const e = document.querySelector(`[data-testid="${id}"]`); if (e) e.scrollIntoView({ block: 'nearest' }); }, testid);
  /** A real click on the badge; nothing when there is none (the check that says so has failed already). */
  const clickBadge = async () => { const l = page.locator(TID('whatif-caution-badge')); if ((await l.count()) === 1) await l.click(); };
  /** The element at the centre of `testid` is that element or one of its descendants (nothing is laid over it). */
  const hitsItself = (testid) => page.evaluate((id) => {
    const e = document.querySelector(`[data-testid="${id}"]`);
    if (!e) return false;
    const b = e.getBoundingClientRect();
    const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
    return Boolean(hit) && (hit === e || e.contains(hit));
  }, testid);

  /** The viewport and the saved pane sizes for the next openTab (which reloads the page); layout null = the defaults. */
  const prepare = async (viewport, layout) => {
    await page.setViewportSize(viewport);
    await page.evaluate((v) => { if (v === null) localStorage.removeItem('fta.layout'); else localStorage.setItem('fta.layout', JSON.stringify(v)); }, layout);
  };
  const DEFAULT_VP = { width: 1100, height: 800 };
  const shots = []; // every screenshot this section writes (the names are listed at the end of the run)
  const shot = (name) => { shots.push(name); return app.shot(name, { locator: '#details-panel' }); };

  /** The badge and the line show exactly `codes` (server order) in `lang`: ids, data attributes, texts, the rest, the title. */
  const checkCaution = async (tag, codes, lang) => {
    const w = await waitCaution((c) => c.present && Boolean(c.badge) && c.codes === codes.join(',') && c.text === lineOf(codes, lang));
    const c = w.c;
    const k = codes.length;
    const b = c.badge;
    L.check(`${tag}: whatif-caution is shown once with data-codes "${codes.join(',')}" and data-count ${k}, and whatif-root data-cautions is the same`,
      w.ok && c.count === 1 && c.codes === codes.join(',') && c.n === String(k) && c.rootCodes === codes.join(','), c);
    L.check(`${tag}: whatif-caution-text reads exactly "${lineOf(codes, lang)}"`, c.text === lineOf(codes, lang), c.text);
    L.check(`${tag}: the line has no role, no aria-live, no title, tabindex -1 and no live ancestor (role="status" or aria-live)`,
      c.role === null && c.ariaLive === null && c.liveAncestor === false && c.title === null && c.tabindex === '-1', { role: c.role, ariaLive: c.ariaLive, liveAncestor: c.liveAncestor, title: c.title, tabindex: c.tabindex });
    L.check(`${tag}: whatif-caution-badge is shown once, a button in the empty corner cell of the table head, reading "${T[lang].badge}", data-count ${k}`,
      c.badgeCount === 1 && Boolean(b) && b.tag === 'BUTTON' && b.type === 'button' && b.inHeadCorner && badgeWord(b) === T[lang].badge && b.n === String(k), b);
    L.check(`${tag}: the badge has aria-describedby and aria-controls pointing at the line (${c.id}), and no role, no aria-live, no live ancestor`,
      Boolean(b) && Boolean(c.id) && b.describedby === c.id && b.controls === c.id && b.role === null && b.ariaLive === null && b.liveAncestor === false, b);
    L.check(`${tag}: the title of the badge is ${k === 1 ? 'the text' : `all ${k} texts, one per line`}`, Boolean(b) && b.title === codes.map((x) => textOf(x, lang)).join('\n'), b && b.title);
    if (k === 1) {
      L.check(`${tag}: one caution has no "(and N more)" and no hidden rest`, c.present && c.text !== null && c.rest === null && !/\(and \d+ more\)|（ほか \d+ 件）/.test(c.text), { text: c.text, rest: c.rest });
    } else {
      L.check(`${tag}: the other ${k - 1} texts are in the hidden whatif-caution-rest, joined with a space`, c.rest === restOf(codes, lang) && c.restHidden === true, { rest: c.rest, hidden: c.restHidden });
      if (lang === 'ja') {
        L.check(`${tag}: in Japanese no space stands before the suffix (the text has no "。 （" and ends with "（ほか ${k - 1} 件）")`, typeof c.text === 'string' && !c.text.includes('。 （') && c.text.endsWith('（ほか ' + (k - 1) + ' 件）') && c.text.includes('。（ほか'), c.text);
      } else {
        L.check(`${tag}: in English one space stands before "(and ${k - 1} more)"`, typeof c.text === 'string' && c.text === textOf(codes[0], 'en') + ' (and ' + (k - 1) + ' more)', c.text);
      }
    }
    return c;
  };
  const checkAbsent = async (tag) => {
    const w = await waitCaution((c) => !c.present && !c.badge);
    const c = w.c;
    L.check(`${tag}: there is no whatif-caution and no whatif-caution-badge, and whatif-root has no data-cautions`, w.ok && c.count === 0 && c.badgeCount === 0 && c.rootCodes === null, c);
  };
  /** No raw catalog key and no unreplaced placeholder in the tab, and nothing of FN-64 in the texts shown (badge and line). */
  const checkTexts = async (tag, lang) => {
    const hits = await page.evaluate(() => {
      const reKey = /whatif\.[a-zA-Z.]+/;
      const rePlaceholder = /\{[A-Za-z]+\}/;
      const out = { keys: [], placeholders: [], texts: [] };
      const test = (text, where) => {
        if (reKey.test(text)) out.keys.push(where + text.trim().slice(0, 80));
        if (rePlaceholder.test(text)) out.placeholders.push(where + text.trim().slice(0, 80));
      };
      const panel = document.getElementById('tabpanel-whatif');
      const walker = document.createTreeWalker(panel, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) test(walker.currentNode.nodeValue, '');
      for (const e of [panel].concat(Array.from(panel.querySelectorAll('*')))) for (const a of ['title', 'aria-label', 'aria-valuetext', 'placeholder']) { const v = e.getAttribute(a); if (v) test(v, a + '='); }
      for (const id of ['whatif-caution', 'whatif-caution-badge']) {
        const e = document.querySelector(`[data-testid="${id}"]`);
        if (e) { out.texts.push(e.textContent); if (e.title) out.texts.push(e.title); }
      }
      return out;
    });
    L.check(`${tag}: no raw "whatif.*" key and no unreplaced {placeholder} in the tab, its titles and aria texts (badge and line included)`, hits.keys.length === 0 && hits.placeholders.length === 0, { keys: hits.keys.slice(0, 4), placeholders: hits.placeholders.slice(0, 4) });
    const words = hits.texts.filter((s) => FN64_EN.test(s) || FN64_JA.some((w) => s.includes(w)));
    L.check(`${tag}: nothing in the badge and caution texts says compliance, conformity or certification (${lang})`, hits.texts.length >= 3 && words.length === 0, { texts: hits.texts, words });
  };

  // G1 and G2: the Q_t = 1 caution, en and ja, no new request for the language switch
  const caseCautionCcfOne = async () => {
    const T1 = 'whatifr2_caution_ccfone_';
    await prepare(DEFAULT_VP, null);
    await openTab(writeDoc(CAUTION_DOCS.ccf('ccfone', 0.5)));
    await checkAbsent(T1 + 'nominal');
    await applyFactor('A', '2', 1);
    const en = await checkCaution(T1 + 'en', ['CCF_Q_ONE'], 'en');
    L.check(T1 + 'en_text_is_design_string: the visible text is the English string of whatif.caution.ccfOne', en.text === T.en.ccfOne, en.text);
    const ge = await geom();
    L.check(T1 + 'en_badge_visible: the badge is visible without scrolling (inside the tab panel at scrollTop 0)', ge.scroll.rootTop === 0 && insideBox(ge.badge, ge.panel), { badge: ge.badge, panel: ge.panel, scroll: ge.scroll });
    await shot('whatifr2-caution-ccfone-en-default');

    const mark = posts.length;
    await app.setLanguage('ja');
    await app.setTheme('dark');
    await sleep(400);
    const ja = await checkCaution(T1 + 'ja', ['CCF_Q_ONE'], 'ja');
    L.check(T1 + 'ja_text_is_design_string: the visible text is the Japanese string of whatif.caution.ccfOne', ja.text === T.ja.ccfOne, ja.text);
    L.check(T1 + 'language_switch_no_request: switching the language repainted badge and line and sent no POST /api/whatif', posts.length === mark, posts.length - mark);
    await shot('whatifr2-caution-ccfone-ja-default');
    await app.setTheme('light');
    await app.setLanguage('en');
    await sleep(300);
    const back = await checkCaution(T1 + 'en_again', ['CCF_Q_ONE'], 'en');
    L.check(T1 + 'en_again_same_element: back in English the text is the English string again', back.text === T.en.ccfOne, back.text);
  };

  // G3: nothing above the line moves, nothing is laid over a number (default pane)
  const caseCautionPosition = async () => {
    const T3 = 'whatifr2_caution_position_';
    await prepare(DEFAULT_VP, null);
    await openTab(writeDoc(CAUTION_DOCS.ccf('position', 1e-3)));
    await applyFactor('A', '5', 1); // Q_t 0.005: below 0.01, no caution
    await checkAbsent(T3 + 'quiet');
    const before = await geom();
    await applyFactor('A', '20', 1); // Q_t 0.02: above 0.01
    const c = await checkCaution(T3 + 'fires', ['CCF_HIGH_Q'], 'en');
    const after = await geom();
    for (const k of ['panel', 'root', 'slot', 'controls', 'slider', 'values', 'head', 'top', 'ratio', 'picker']) {
      L.check(`${T3}${k}_identical: the rect of ${k} is the same with and without the caution (0 px difference)`, exactRect(before[k], after[k]), { before: before[k], after: after[k] });
    }
    L.check(T3 + 'cells_identical: every cell of the table (head corner included) has the same rect with and without the caution', before.cells.length >= 12 && exactRects(before.cells, after.cells), { before: before.cells.length, after: after.cells.length });
    L.check(T3 + 'not_scrolled: whatif-root and the panel keep scrollTop 0 (before and after), and there is no sideways overflow', before.scroll.rootTop === 0 && after.scroll.panelTop === 0 && after.scroll.rootTop === 0 && noSideways(after), { before: before.scroll, after: after.scroll });
    const badge = after.badge;
    L.check(T3 + 'badge_in_head_row: the badge lies inside the head row of the table (so inside whatif-values), at most 20 px high', insideBox(badge, after.head, 0.5) && insideBox(badge, after.values, 0.5) && H(badge) <= 20.01, { badge, head: after.head });
    L.check(T3 + 'badge_visible: the badge is fully inside the tab panel without scrolling', insideBox(badge, after.panel), { badge, panel: after.panel });
    L.check(T3 + 'badge_clear_of_numbers: the badge intersects none of the three column headers, whatif-top-whatif or whatif-ratio',
      after.colHeaders.length === 3 && after.colHeaders.every((r) => area(badge, r) <= NO_AREA) && area(badge, after.top) <= NO_AREA && area(badge, after.ratio) <= NO_AREA, { badge, cols: after.colHeaders, top: after.top, ratio: after.ratio });
    L.check(T3 + 'line_static_below_table: the line is position static (nothing pinned) and starts at or below the bottom of whatif-values', c.position === 'static' && Boolean(after.caution) && after.caution.top >= after.values.bottom - 0.5, { position: c.position, caution: after.caution, values: after.values });
    L.check(T3 + 'line_clear_of_cells: the line overlaps no cell of the table', after.cells.length > 0 && after.cells.every((r) => area(after.caution, r) <= NO_AREA), { caution: after.caution });
    L.check(T3 + 'no_sideways_overflow: whatif-root scrollWidth <= clientWidth', after.scroll.rootSW <= after.scroll.rootCW, after.scroll);
    for (const id of ['whatif-top-whatif', 'whatif-ratio', 'whatif-slider']) {
      L.check(`${T3}${id.replace('whatif-', '')}_not_covered: elementFromPoint at the centre of ${id} returns it (or a descendant)`, await hitsItself(id), id);
    }
  };

  // G4: each text is one text line at the default pane (scrolled into view), en and ja; the badge at scrollTop 0
  const caseCautionOneLine = async () => {
    const T4 = 'whatifr2_caution_oneline_';
    const sets = [
      ['ccfhigh', () => CAUTION_DOCS.ccf('oneline_high', 0.005), 'A', '2.0000001', ['CCF_HIGH_Q']],
      ['standby', () => CAUTION_DOCS.standby('oneline_standby'), 'S', '2.0000001', ['STANDBY_LARGE_LT']],
      ['cutsets', () => CAUTION_DOCS.repeated('oneline_cutsets', { maxOrder: 1 }), 'A', '10', ['CUTSETS_TRUNCATED']],
      ['two', () => CAUTION_DOCS.all('oneline_two'), 'A', '2', ['CCF_Q_ONE', 'CUTSETS_TRUNCATED']],
    ];
    for (const [tag, make, id, text, codes] of sets) {
      await prepare(DEFAULT_VP, null);
      await openTab(writeDoc(make()));
      await applyFactor(id, text, 1);
      for (const lang of ['en', 'ja']) {
        if (lang === 'ja') { await app.setLanguage('ja'); await sleep(300); }
        const c = await checkCaution(`${T4}${tag}_${lang}`, codes, lang);
        if (tag === 'ccfhigh' && lang === 'ja') {
          await scrollTop0();
          const g0 = await geom();
          L.check(`${T4}badge_ja_visible: at scrollTop 0 the badge "${T.ja.badge}" is visible inside the panel`, g0.scroll.rootTop === 0 && insideBox(g0.badge, g0.panel), { badge: g0.badge, panel: g0.panel });
          await shot('whatifr2-caution-badge-ja-default');
        }
        await scrollTo('whatif-caution');
        await sleep(100);
        const g = await geom();
        const c2 = await readCaution();
        L.check(`${T4}${tag}_${lang}_one_line: the line is one text line (at most 17 px high) after scrolling it into view, and the text does not run past it`, H(g.caution) <= 17 && onLine(c2), { h: H(g.caution), sw: c2.sw, cw: c2.cw });
        L.check(`${T4}${tag}_${lang}_limit_filled: the threshold is in the text (${tag === 'ccfhigh' ? '0.01' : tag === 'standby' ? '0.2' : 'no placeholder'}), no "{limit}" is left`, typeof c.text === 'string' && !c.text.includes('{') && (tag === 'cutsets' || tag === 'two' || c.text.includes(tag === 'ccfhigh' ? '0.01' : '0.2')), c.text);
        await shot(`whatifr2-caution-${tag}-${lang}-default-line`);
        await scrollTop0();
      }
      await app.setLanguage('en');
    }
  };

  // G4b: the badge takes you to the line: click, Enter, Space; no request, no change of the factor
  const caseCautionBadge = async () => {
    const T4b = 'whatifr2_caution_badge_';
    await prepare(DEFAULT_VP, null);
    await openTab(writeDoc(CAUTION_DOCS.ccf('badge', 0.5)));
    await applyFactor('A', '2', 1);
    await checkCaution(T4b + 'shown', ['CCF_Q_ONE'], 'en');
    if ((await readCaution()).badgeCount !== 1) return; // nothing to activate: the check above has failed
    const state = () => page.evaluate(() => ({ field: document.querySelector('[data-testid="whatif-factor-input"]').value, slider: document.querySelector('[data-testid="whatif-slider"]').dataset.factor, factors: document.querySelector('[data-testid="whatif-root"]').dataset.factors }));
    const active = () => page.evaluate(() => { const a = document.activeElement; return a ? { testid: a.getAttribute('data-testid') || '', id: a.id || '', tag: a.tagName } : null; });
    const base = await state();
    const mark = posts.length;

    // click
    await scrollTop0();
    await clickBadge();
    await sleep(250);
    let a = await active();
    let g = await geom();
    L.check(T4b + 'click_focus_line: a click on the badge gives the line focus (document.activeElement is whatif-caution)', Boolean(a) && a.testid === 'whatif-caution', a);
    L.check(T4b + 'click_line_in_panel: the line is inside the panel rect afterwards (scrolled with block nearest)', insideBox(g.caution, g.panel), { caution: g.caution, panel: g.panel });
    // Shift+Tab leaves the line towards the controls (the badge or a control before the line)
    await page.keyboard.press('Shift+Tab');
    const back = await page.evaluate(() => { const a = document.activeElement; const line = document.querySelector('[data-testid="whatif-caution"]'); return { moved: a !== line, before: Boolean(a) && Boolean(line) && Boolean(line.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_PRECEDING), testid: a ? a.getAttribute('data-testid') : null }; });
    L.check(T4b + 'shift_tab_back: Shift+Tab from the line moves focus to an element before it (the badge or a control)', back.moved && back.before, back);
    // Shift+Tab from the badge reaches the controls
    await page.locator(TID('whatif-caution-badge')).focus();
    await page.keyboard.press('Shift+Tab');
    const toControls = await page.evaluate(() => { const a = document.activeElement; const c = document.querySelector('[data-testid="whatif-controls"]'); return { inControls: Boolean(a) && Boolean(c) && c.contains(a), testid: a ? a.getAttribute('data-testid') : null }; });
    L.check(T4b + 'shift_tab_from_badge: Shift+Tab from the badge moves focus to the control before it (inside whatif-controls)', toControls.inControls, toControls);

    // Enter and Space, with the keyboard focus on the badge
    for (const [name, key] of [['enter', 'Enter'], ['space', 'Space']]) {
      await scrollTop0();
      await page.locator(TID('whatif-caution-badge')).focus();
      await sleep(100);
      const marked = posts.length;
      await page.keyboard.press(key);
      await sleep(400);
      a = await active();
      g = await geom();
      const s = await state();
      L.check(`${T4b}${name}_focus_line: ${key} on the badge gives the line focus and the line is inside the panel rect`, Boolean(a) && a.testid === 'whatif-caution' && insideBox(g.caution, g.panel), { active: a, caution: g.caution, panel: g.panel });
      L.check(`${T4b}${name}_no_change: ${key} on the badge sent no request and changed neither the factor nor the field (${JSON.stringify(base)})`, posts.length === marked && JSON.stringify(s) === JSON.stringify(base), { posts: posts.length - marked, state: s, base });
    }
    L.check(T4b + 'no_request_at_all: no POST /api/whatif was sent by the click, Enter or Space', posts.length === mark, posts.length - mark);
    const t = await readCaution();
    L.check(T4b + 'title: the badge title is the text of the caution (one caution)', Boolean(t.badge) && t.badge.title === T.en.ccfOne, t.badge);
  };

  // G5: several cautions: the first text, "(and N more)", the rest hidden, the badge title; server order
  const caseCautionMulti = async () => {
    const T5 = 'whatifr2_caution_multi_';
    await prepare(DEFAULT_VP, null);
    await openTab(writeDoc(CAUTION_DOCS.all('multi')));
    await applyFactor('A', '2', 1); // g1 at Q_t 1 -> Q_ONE; maxOrder 1 -> CUTSETS_TRUNCATED
    await checkCaution(T5 + 'two', ['CCF_Q_ONE', 'CUTSETS_TRUNCATED'], 'en');
    await applyFactor('S', '2.0000001', 2);
    await checkCaution(T5 + 'three', ['CCF_Q_ONE', 'STANDBY_LARGE_LT', 'CUTSETS_TRUNCATED'], 'en');
    await applyFactor('D', '1.2', 3);
    const four = await checkCaution(T5 + 'four_en', ['CCF_Q_ONE', 'CCF_HIGH_Q', 'STANDBY_LARGE_LT', 'CUTSETS_TRUNCATED'], 'en');
    await scrollTo('whatif-caution');
    await sleep(100);
    L.check(T5 + 'four_one_line: with four cautions the line is still one text line (at most 17 px)', H((await geom()).caution) <= 17, four.rect);
    await shot('whatifr2-caution-multi-en-default');
    await app.setLanguage('ja');
    await sleep(300);
    await checkCaution(T5 + 'four_ja', ['CCF_Q_ONE', 'CCF_HIGH_Q', 'STANDBY_LARGE_LT', 'CUTSETS_TRUNCATED'], 'ja');
    L.check(T5 + 'four_ja_one_line: in Japanese too the line is at most 17 px high', H((await geom()).caution) <= 17, (await geom()).caution);
    await shot('whatifr2-caution-multi-ja-default');
    await app.setLanguage('en');
    await sleep(200);
    // taking the first caution away moves the next one up: the line names the new first
    await applyFactor('A', '1', 2);
    await checkCaution(T5 + 'after_first_removed', ['CCF_HIGH_Q', 'STANDBY_LARGE_LT', 'CUTSETS_TRUNCATED'], 'en');
  };

  // G6: the boundary in the UI, and the ways back to nothing
  const caseCautionBoundary = async () => {
    const T6 = 'whatifr2_caution_boundary_';
    await prepare(DEFAULT_VP, null);
    await openTab(writeDoc(CAUTION_DOCS.ccf('boundary', 0.005)));
    await applyFactor('A', '2', 1); // Q_t = 0.005 * 2 = 0.01 exactly: not above
    await checkAbsent(T6 + 'two_is_not_above');
    await applyFactor('A', '2.0000001', 1);
    await checkCaution(T6 + 'just_above', ['CCF_HIGH_Q'], 'en');
    // back to 1 with the field: banner, badge and line go in the same task, before any answer
    const syncField = await page.evaluate(() => {
      const q = (id) => document.querySelector(`[data-testid="${id}"]`);
      const f = q('whatif-factor-input');
      f.value = '1';
      f.dispatchEvent(new Event('input', { bubbles: true }));
      f.dispatchEvent(new Event('change', { bubbles: true }));
      return { banner: document.querySelectorAll('[data-testid="whatif-banner"]').length, caution: document.querySelectorAll('[data-testid="whatif-caution"]').length, badge: document.querySelectorAll('[data-testid="whatif-caution-badge"]').length, codes: q('whatif-root').dataset.cautions === undefined ? null : q('whatif-root').dataset.cautions };
    });
    L.check(T6 + 'field_back_to_1_at_once: typing 1 in the field removes banner, badge and line in the same task (no answer needed)', syncField.banner === 0 && syncField.caution === 0 && syncField.badge === 0 && syncField.codes === null, syncField);
    await waitRead((r) => settledPred(r) && r.root.factors === '0', 8000);
    await checkAbsent(T6 + 'field_back_to_1');
    // Reset all: the same
    await applyFactor('A', '2.0000001', 1);
    await checkCaution(T6 + 'again', ['CCF_HIGH_Q'], 'en');
    const sync = await page.evaluate(() => {
      const q = (id) => document.querySelector(`[data-testid="${id}"]`);
      q('whatif-reset-all').click();
      return { banner: document.querySelectorAll('[data-testid="whatif-banner"]').length, caution: document.querySelectorAll('[data-testid="whatif-caution"]').length, badge: document.querySelectorAll('[data-testid="whatif-caution-badge"]').length, codes: q('whatif-root').dataset.cautions === undefined ? null : q('whatif-root').dataset.cautions };
    });
    L.check(T6 + 'reset_all_at_once: Reset all removes banner, badge and line in the same task (no answer needed)', sync.banner === 0 && sync.caution === 0 && sync.badge === 0 && sync.codes === null, sync);
    await waitRead((r) => settledPred(r) && r.root.factors === '0', 8000);
    await checkAbsent(T6 + 'reset_all_settled');
    // the Reset of the one scaled event
    await applyFactor('A', '2.0000001', 1);
    await checkCaution(T6 + 'third', ['CCF_HIGH_Q'], 'en');
    await page.locator(TID('whatif-reset-event') + '[data-node-id="A"]').click();
    const w = await waitRead((r) => settledPred(r) && r.root.factors === '0', 8000);
    L.check(T6 + 'reset_event_settled: the per-event Reset removed the only entry', w.ok, w.r.root);
    await checkAbsent(T6 + 'reset_event');
  };

  // G7: the cutoff note and the caution are two different things
  const caseCautionCutoff = async () => {
    const T7 = 'whatifr2_caution_cutoff_';
    await prepare(DEFAULT_VP, null);
    // cutoff only: the note badge, no caution
    const cutoffOnly = CAUTION_DOCS.ccf('cutoff_only', 1e-3);
    cutoffOnly.doc.analysis.cutsets = { cutoff: 1e-6 };
    await openTab(writeDoc(cutoffOnly));
    await applyFactor('A', '5', 1);
    const cutoffBadge = await page.evaluate(() => {
      const b = document.querySelector('[data-testid="whatif-cutoff-note"]');
      return { count: document.querySelectorAll('[data-testid="whatif-cutoff-note"]').length, text: b ? b.textContent : null, note: document.querySelector('[data-testid="whatif-root"]').dataset.note || null };
    });
    L.check(T7 + 'only_cutoff_note: a cutoff alone gives the badge "cut sets from nominal values" (data-note cutsets_from_nominal)', cutoffBadge.count === 1 && cutoffBadge.text === T.en.cutoffNote && cutoffBadge.note === 'cutsets_from_nominal', cutoffBadge);
    const none = await readCaution();
    L.check(T7 + 'only_cutoff_no_line: no whatif-caution and no caution badge for the cutoff alone', none.present === false && none.badgeCount === 0, none);
    // cutoff and an order limit: both, with different texts
    await prepare(DEFAULT_VP, null);
    await openTab(writeDoc(CAUTION_DOCS.three('cutoff_order', { maxOrder: 2, cutoff: 1e-2 })));
    await applyFactor('B', '2', 1);
    const both = await checkCaution(T7 + 'both', ['CUTSETS_TRUNCATED'], 'en');
    const badge = page.locator(TID('whatif-cutoff-note'));
    const badgeText = (await badge.count()) === 1 ? (await badge.textContent()) : null;
    L.check(T7 + 'both_texts_differ: the cutoff note is still in the notes row and the line names the order limit, in other words', badgeText === T.en.cutoffNote && both.text === T.en.cutsets && badgeText !== both.text, { badge: badgeText, line: both.text });
    // an order limit only: the caution, no note
    await prepare(DEFAULT_VP, null);
    await openTab(writeDoc(CAUTION_DOCS.repeated('order_only', { maxOrder: 1 })));
    await applyFactor('A', '10', 1);
    await checkCaution(T7 + 'order_only', ['CUTSETS_TRUNCATED'], 'en');
    L.check(T7 + 'order_only_no_note: no cutoff note when there is no cutoff', (await page.locator(TID('whatif-cutoff-note')).count()) === 0, await page.locator(TID('whatif-cutoff-note')).count());
  };

  // G8: no factor, no caution; a document change takes it away
  const caseCautionNoFactor = async () => {
    const T8 = 'whatifr2_caution_nofactor_';
    await prepare(DEFAULT_VP, null);
    // the document of G1 at nominal: the group is at 0.5 (above 0.01) and the tab must not warn by being opened
    const name = writeDoc(CAUTION_DOCS.ccf('nofactor', 0.5, true));
    await openTab(name);
    await checkAbsent(T8 + 'opened');
    L.check(T8 + 'opened_nominal: the tab is at nominal (data-factors 0, no banner)', (await read()).root.factors === '0' && (await bannerCount()) === 0, (await read()).root);
    await applyFactor('A', '2', 1);
    await checkCaution(T8 + 'with_factor', ['CCF_Q_ONE'], 'en');
    // a document change (a Grid paste into Z) resets the factors and so the caution
    await openGrid();
    const cell = CELL('Z', 'q');
    const found = await until(async () => (await page.locator(cell).count()) === 1, 6000);
    L.check(T8 + 'grid_ready: the Grid shows the q cell of Z', Boolean(found), await page.locator(TID('grid-cell')).count());
    if (!found) return;
    await gridPaste(cell, '0.002');
    await page.locator('#tab-whatif').click();
    await page.locator(TID('whatif-root')).waitFor({ state: 'visible' });
    const w = await waitRead((r) => settledPred(r) && r.root.factors === '0', 10000);
    L.check(T8 + 'after_change_factors_reset: the paste reset every factor (data-factors 0, no banner)', w.ok && (await bannerCount()) === 0, w.r.root);
    await checkAbsent(T8 + 'after_change');
    // and a quiet factor on the same document gives no caution (Z only)
    await applyFactor('Z', '2', 1);
    await checkAbsent(T8 + 'other_event');
  };

  // G9: no caution without an answer; the last answer's caution stays in an error
  const caseCautionStates = async () => {
    const T9 = 'whatifr2_caution_states_';
    await prepare(DEFAULT_VP, null);
    // loading: the first answer is held back; never unrouted (an unroute while a handler sleeps crashes the run), the delay is switched off
    const name = writeDoc(CAUTION_DOCS.ccf('states', 0.5));
    let delayMs = 2500;
    const slow = async (route) => { if (delayMs) { const d = delayMs; delayMs = 0; await sleep(d); } await route.continue().catch(() => {}); };
    await page.route('**/api/whatif', slow);
    await openDoc(name);
    await showWhatif();
    const loading = await waitRead((r) => r.root && r.root.state === 'loading', 4000);
    const l0 = await readCaution();
    L.check(T9 + 'loading: while the first answer is on its way (data-state loading) there is no badge and no caution line', loading.ok && l0.present === false && l0.badgeCount === 0, { root: loading.r.root, caution: l0 });
    const ready = await waitRead(settledPred, 15000);
    const l1 = await readCaution();
    L.check(T9 + 'loading_then_ready: the numbers arrive and there is still no badge and no line (no factor)', ready.ok && l1.present === false && l1.badgeCount === 0, ready.r.root);

    // an answer with a caution, then a 500: badge and line stay, beside the error line
    await applyFactor('A', '2', 1);
    await checkCaution(T9 + 'before_error', ['CCF_Q_ONE'], 'en');
    let fail = true;
    const boom = async (route) => (fail ? route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ ok: false, error: { code: 'INTERNAL_ERROR', message: 'Boom', detail: {} } }) }) : route.fallback());
    await page.route('**/api/whatif', boom);
    await page.locator(TID('whatif-picker')).selectOption('A');
    const f = page.locator(TID('whatif-factor-input'));
    await f.fill('3');
    await f.press('Enter');
    const err = await waitRead((r) => r.root && r.root.state === 'error', 8000);
    const c = await readCaution();
    const g = await geom();
    L.check(T9 + 'error_keeps_caution: after a failed answer (data-state error) the badge, the line of the last answer and the error line are all there', err.ok && c.present && c.codes === 'CCF_Q_ONE' && Boolean(c.badge) && Boolean(g.error) && g.error.h > 0, { state: err.r.root, caution: c.codes, badge: Boolean(c.badge), error: g.error });
    fail = false;
    await f.fill('2');
    await f.press('Enter');
    const healed = await waitRead((r) => settledPred(r) && r.root.state === 'ready', 8000);
    L.check(T9 + 'error_healed: the next input retries, the error goes and the caution is the new answer\'s', healed.ok && (await page.locator(TID('whatif-error')).count()) === 0, healed.r.root);
    await checkCaution(T9 + 'after_error', ['CCF_Q_ONE'], 'en');

    // ETA: the panel shows the ETA notice and every factor, badge and line are gone
    await page.locator('#mode-select').selectOption('ETA');
    const eta = await waitRead((r) => r.root && r.root.state === 'eta', 8000);
    const e0 = await readCaution();
    L.check(T9 + 'eta: in ETA mode (data-state eta) there is no badge and no caution line, no data-cautions', eta.ok && e0.present === false && e0.badgeCount === 0 && e0.rootCodes === null, { root: eta.r.root, caution: e0 });
    await page.locator('#mode-select').selectOption('FTA');
    await waitRead((r) => settledPred(r) && r.root.factors === '0', 10000);
    await checkAbsent(T9 + 'back_in_fta');

    // empty: a tree with no basic event
    await app.api('post', '/new', { force: true });
    await page.reload();
    await L.waitBoot(page);
    await app.waitDiagram(60000);
    await showWhatif();
    const empty = await waitRead((r) => r.root && r.root.state === 'empty', 8000);
    const m0 = await readCaution();
    L.check(T9 + 'empty: with no basic event (data-state empty) there is no badge and no caution line', empty.ok && m0.present === false && m0.badgeCount === 0, empty.r.root);
  };

  /** Keyboard focus on the badge, Enter: the line has the focus and lies inside the panel (the 140 px pane shows it by scrolling). */
  const enterOnBadge = async (tag) => {
    if ((await readCaution()).badgeCount !== 1) return;
    await page.locator(TID('whatif-caution-badge')).focus();
    await page.keyboard.press('Enter');
    await sleep(300);
    const a = await page.evaluate(() => { const e = document.activeElement; return e ? e.getAttribute('data-testid') : null; });
    const g = await geom();
    L.check(`${tag}_enter_on_badge: Enter on the focused badge gives the line the focus and the line lies inside the panel`, a === 'whatif-caution' && insideBox(g.caution, g.panel), { active: a, caution: g.caution, panel: g.panel });
  };

  // G10: the 140 px minimum pane
  const caseCautionMinPane = async () => {
    const T10 = 'whatifr2_caution_minpane_';
    await prepare(DEFAULT_VP, { tree: 320, ai: 340, details: 140, analysis: 140 });
    await openTab(writeDoc(CAUTION_DOCS.ccf('minpane', 1e-3)));
    await applyFactor('A', '5', 1); // no caution
    await checkAbsent(T10 + 'quiet');
    const h = await page.evaluate(() => document.getElementById('details-panel').getBoundingClientRect().height);
    L.check(T10 + 'setup: the bottom panel is 140 px high', h >= 139 && h <= 142, h);
    await scrollTop0();
    await sleep(150);
    const before = await geom();
    await applyFactor('A', '20', 1); // the caution fires
    const c = await checkCaution(T10 + 'en', ['CCF_HIGH_Q'], 'en');
    await scrollTop0();
    await sleep(150);
    const g = await geom();
    L.check(T10 + 'slot_and_picker: the banner slot and the picker lie inside the tab panel', insideBox(g.slot, g.panel) && insideBox(g.picker, g.panel), { panel: g.panel, slot: g.slot, picker: g.picker });
    for (const k of ['slot', 'controls', 'slider', 'values', 'head', 'picker']) {
      L.check(`${T10}${k}_identical: the rect of ${k} is the same with and without the caution (0 px difference)`, exactRect(before[k], g[k]), { before: before[k], after: g[k] });
    }
    L.check(T10 + 'nothing_pinned: the line is position static and the status strip has the same height with and without the caution', c.position === 'static' && Boolean(g.status) && Boolean(before.status) && Math.abs(g.status.h - before.status.h) <= 0.01, { position: c.position, before: before.status, after: g.status });
    L.check(T10 + 'no_sideways_overflow: no sideways overflow of the panel or whatif-root', noSideways(g), g.scroll);
    await scrollTo('whatif-caution-badge');
    await sleep(150);
    const gb = await geom();
    L.check(T10 + 'badge_reachable: after scrollIntoView the badge lies inside the tab panel', insideBox(gb.badge, gb.panel), { badge: gb.badge, panel: gb.panel });
    await shot('whatifr2-caution-minpane-badge');
    await enterOnBadge(T10 + 'en');
    await shot('whatifr2-caution-minpane-line');
    await scrollTo('whatif-slider');
    await sleep(150);
    const gs = await geom();
    L.check(T10 + 'slider_reachable: the slider is reachable by scrolling (inside the panel after scrollIntoView)', insideBox(gs.slider, gs.panel), { panel: gs.panel, slider: gs.slider });
    await scrollTo('whatif-top-whatif');
    await sleep(150);
    const gt = await geom();
    L.check(T10 + 'top_reachable: the what-if top event is reachable by scrolling and nothing covers it', insideBox(gt.top, gt.panel) && (await hitsItself('whatif-top-whatif')), { panel: gt.panel, top: gt.top });
    await scrollTop0();
    await shot('whatifr2-caution-minpane');
    await app.setLanguage('ja');
    await sleep(300);
    await checkCaution(T10 + 'ja', ['CCF_HIGH_Q'], 'ja');
    await shot('whatifr2-caution-minpane-ja');
    await scrollTop0();
    await scrollTo('whatif-caution-badge');
    await sleep(150);
    await shot('whatifr2-caution-minpane-badge-ja');
    await enterOnBadge(T10 + 'ja');
    await shot('whatifr2-caution-minpane-line-ja');
    await app.setLanguage('en');
  };

  // G11: the stacked shell (<= 900 px)
  const caseCautionStacked = async () => {
    const T11 = 'whatifr2_caution_stacked_';
    await prepare(DEFAULT_VP, null);
    await openTab(writeDoc(CAUTION_DOCS.all('stacked')));
    await applyFactor('A', '2', 1);
    await applyFactor('S', '2.0000001', 2);
    await page.setViewportSize({ width: 800, height: 900 });
    await sleep(500);
    await page.evaluate(() => document.getElementById('details-panel').scrollIntoView());
    await sleep(250);
    await checkCaution(T11 + 'en', ['CCF_Q_ONE', 'STANDBY_LARGE_LT', 'CUTSETS_TRUNCATED'], 'en');
    await scrollTo('whatif-caution-badge');
    await sleep(150);
    const gb = await geom();
    L.check(T11 + 'badge_inside_panel: after scrollIntoView the badge lies inside the tab panel', insideBox(gb.badge, gb.panel), { badge: gb.badge, panel: gb.panel });
    await clickBadge();
    await sleep(250);
    const g = await geom();
    L.check(T11 + 'line_inside_panel: after a click on the badge the line lies inside the tab panel', insideBox(g.caution, g.panel), { panel: g.panel, caution: g.caution });
    L.check(T11 + 'no_sideways_overflow: no sideways overflow', noSideways(g), g.scroll);
    L.check(T11 + 'line_clear_of_cells: the line wraps as it needs and overlaps no cell of the table', g.cells.length > 0 && g.cells.every((r) => area(g.caution, r) <= NO_AREA), { caution: g.caution });
    await shot('whatifr2-caution-narrow');
    await app.setLanguage('ja');
    await sleep(300);
    await checkCaution(T11 + 'ja', ['CCF_Q_ONE', 'STANDBY_LARGE_LT', 'CUTSETS_TRUNCATED'], 'ja');
    await clickBadge();
    await sleep(250);
    const gj = await geom();
    L.check(T11 + 'ja_line_inside_panel: in Japanese too the line is inside the panel after a click on the badge, no sideways overflow, no overlap with a cell', insideBox(gj.caution, gj.panel) && noSideways(gj) && gj.cells.every((r) => area(gj.caution, r) <= NO_AREA), { caution: gj.caution, panel: gj.panel, scroll: gj.scroll });
    await shot('whatifr2-caution-narrow-ja');
    await app.setLanguage('en');
    // a really narrow window: the line wraps in flow, nothing is cut or covered
    await page.setViewportSize({ width: 440, height: 900 });
    await sleep(500);
    await page.evaluate(() => document.getElementById('details-panel').scrollIntoView());
    await sleep(250);
    await scrollTo('whatif-caution');
    await sleep(150);
    const gn = await geom();
    const cn = await readCaution();
    L.check(T11 + 'narrow_440: at 440 px wide the line has no sideways overflow, covers no cell and its text is not cut (the line scrolls to nothing)', noSideways(gn) && gn.cells.every((r) => area(gn.caution, r) <= NO_AREA) && cn.sw <= cn.cw, { caution: gn.caution, scroll: gn.scroll, sw: cn.sw, cw: cn.cw });
    // the line wrapped, the badge in the corner cell, no overflow: the badge is put at the top of the pane so that the table and the line show together
    for (const lang of ['en', 'ja']) {
      if (lang === 'ja') { await app.setLanguage('ja'); await sleep(300); }
      await page.evaluate(() => { const b = document.querySelector('[data-testid="whatif-caution-badge"]'); if (b) b.scrollIntoView({ block: 'start' }); });
      await sleep(200);
      const w = await geom();
      const cw = await readCaution();
      L.check(`${T11}narrow_440_${lang}_wraps: at 440 px the ${lang} line wraps to two or more lines (at least 30 px high), has no sideways overflow and the badge sits in the head corner`, H(w.caution) >= 30 && noSideways(w) && Boolean(cw.badge) && cw.badge.inHeadCorner, { caution: w.caution, scroll: w.scroll, badge: cw.badge && cw.badge.inHeadCorner });
      L.info(`narrow 440 ${lang}: badge and line both inside the panel: ${insideBox(w.badge, w.panel) && insideBox(w.caution, w.panel)}`, { badge: w.badge, caution: w.caution, panel: w.panel });
      await shot(lang === 'en' ? 'whatifr2-caution-narrow-440' : 'whatifr2-caution-narrow-440-ja');
      // the same pane with the whole wrapped line in view (the badge has scrolled out above it)
      await page.evaluate(() => { const l = document.querySelector('[data-testid="whatif-caution"]'); if (l) l.scrollIntoView({ block: 'end' }); });
      await sleep(200);
      await shot(lang === 'en' ? 'whatifr2-caution-narrow-440-line' : 'whatifr2-caution-narrow-440-line-ja');
    }
    await app.setLanguage('en');
    await page.setViewportSize(DEFAULT_VP);
  };

  // G12: no raw keys, no FN-64 wording, every caution in en and ja
  const caseCautionTexts = async () => {
    const T12 = 'whatifr2_caution_texts_';
    await prepare(DEFAULT_VP, null);
    await openTab(writeDoc(CAUTION_DOCS.all5('texts')));
    await applyFactor('A', '2', 1);
    await applyFactor('S', '2.0000001', 2);
    await applyFactor('D', '1.2', 3);
    const FOUR = ORDER5.slice(1);
    await checkCaution(T12 + 'all_four_en', FOUR, 'en');
    await checkTexts(T12 + 'en', 'en');
    await app.setLanguage('ja');
    await sleep(300);
    await checkCaution(T12 + 'all_four_ja', FOUR, 'ja');
    await checkTexts(T12 + 'ja', 'ja');
    await app.setLanguage('en');
    // Y3: the fifth caution (a factor on F, a member of g3, which is not applied) joins, first in the order: the badge title holds all five texts
    await applyFactor('F', '2', 4);
    await checkCaution(T12 + 'all_five_en', ORDER5, 'en');
    await checkTexts(T12 + 'five_en', 'en');
    await app.setLanguage('ja');
    await sleep(300);
    await checkCaution(T12 + 'all_five_ja', ORDER5, 'ja');
    await checkTexts(T12 + 'five_ja', 'ja');
    const five = await readCaution();
    L.check(T12 + 'five_ja_notapplied_text_is_catalog_string: the first text of the line and of the badge title is the Japanese CCF_NOT_APPLIED string, with no raw key', Boolean(five.badge) && five.text.startsWith(T.ja.notApplied) && five.badge.title.split('\n')[0] === T.ja.notApplied && !/whatif\.caution/.test(five.badge.title + five.text), { text: five.text, title: five.badge && five.badge.title });
    await app.setLanguage('en');
  };

  // Focus: the keyboard path to the badge and the line (shots with the ring), and where the focus goes when the caution is removed under it
  const caseCautionFocus = async () => {
    const TF = 'whatifr2_caution_focus_';
    const activeId = () => page.evaluate(() => { const e = document.activeElement; return e ? (e.getAttribute('data-testid') || e.tagName) : null; });
    await prepare(DEFAULT_VP, null);
    await openTab(writeDoc(CAUTION_DOCS.ccf('focus', 0.005)));
    await applyFactor('A', '2.0000001', 1);
    await checkCaution(TF + 'shown', ['CCF_HIGH_Q'], 'en');
    if ((await readCaution()).badgeCount !== 1) return;

    // keyboard only: the factor field, Tab to the badge, Enter to the line
    const keyboardToBadge = async () => {
      await scrollTop0();
      await page.locator(TID('whatif-factor-input')).focus();
      await page.keyboard.press('Tab');
      await sleep(150);
    };
    await keyboardToBadge();
    L.check(TF + 'tab_reaches_badge: Tab from the factor field moves the focus to the badge', (await activeId()) === 'whatif-caution-badge', await activeId());
    await shot('whatifr2-caution-focus-badge');
    await page.keyboard.press('Enter');
    await sleep(300);
    L.check(TF + 'enter_reaches_line: Enter on the badge moves the focus to the line', (await activeId()) === 'whatif-caution', await activeId());
    await shot('whatifr2-caution-focus-line');
    // the same in the dark theme (the theme button takes the focus, so the keyboard path is walked again)
    await app.setTheme('dark');
    await keyboardToBadge();
    await page.keyboard.press('Enter');
    await sleep(300);
    L.check(TF + 'dark_enter_reaches_line: in the dark theme the same keyboard path ends on the line', (await activeId()) === 'whatif-caution', await activeId());
    await shot('whatifr2-caution-focus-line-dark');
    await app.setTheme('light');

    // the caution goes while the badge or the line has the focus: the focus goes to the picker, never to the page body
    const clearUnder = async (target, how) => {
      // make sure a caution is there (the factor 2.0000001 on q 0.005 is above 0.01), then focus the target and change the field in script
      if (!(await readCaution()).present) await applyFactor('A', '2.0000001', 1); // (when the factor is still on, the caution is there)
      await waitCaution((c) => c.present && Boolean(c.badge));
      await page.evaluate((id) => document.querySelector(`[data-testid="${id}"]`).focus(), target);
      const before = await activeId();
      const value = how === 'one' ? '1' : '2'; // 1: the entry is dropped; 2: Q_t 0.01 exactly, an answer without a caution
      const now = await page.evaluate((v) => {
        const f = document.querySelector('[data-testid="whatif-factor-input"]');
        f.value = v;
        f.dispatchEvent(new Event('input', { bubbles: true }));
        f.dispatchEvent(new Event('change', { bubbles: true }));
        const e = document.activeElement;
        return e ? (e.getAttribute('data-testid') || e.tagName) : null;
      }, value);
      await waitRead((r) => settledPred(r) && r.root.factors === (how === 'one' ? '0' : '1'), 8000);
      await waitCaution((c) => !c.present && !c.badge);
      await sleep(200);
      const after = await activeId();
      return { before, now, after };
    };
    for (const [target, how, name] of [['whatif-caution-badge', 'one', 'badge_factor_to_1'], ['whatif-caution', 'one', 'line_factor_to_1'], ['whatif-caution-badge', 'two', 'badge_late_answer'], ['whatif-caution', 'two', 'line_late_answer']]) {
      const r = await clearUnder(target, how);
      L.check(`${TF}${name}: the ${target === 'whatif-caution' ? 'line' : 'badge'} had the focus and the caution went (${how === 'one' ? 'factor typed back to 1' : 'an answer without a caution'}): the focus is on whatif-picker, not on the page body`, r.before === target && r.after === 'whatif-picker', r);
    }
  };

  // The tab and an answer it does not know: no limit (an older server), an unknown code (a newer one). The answer is changed on its way to the page.
  const caseCautionOldServer = async () => {
    const TO = 'whatifr2_caution_oldserver_';
    await prepare(DEFAULT_VP, null);
    let tamper = null;
    // never unrouted; the change is switched off with the flag
    const route = async (r) => {
      if (!tamper) { await r.fallback(); return; }
      const response = await r.fetch();
      const json = await response.json();
      await r.fulfill({ response, json: tamper(json) });
    };
    await page.route('**/api/whatif', route);
    await openTab(writeDoc(CAUTION_DOCS.ccf('oldserver', 0.005)));

    // 1: no "limit" in the entry: the tab fills the placeholder with its own constant (0.01)
    tamper = (j) => { j.cautions = (j.cautions || []).map((c) => { const o = Object.assign({}, c); delete o.limit; return o; }); return j; };
    await applyFactor('A', '2.0000001', 1);
    const a = await waitCaution((c) => c.present);
    L.check(TO + 'limit_fallback' + ': an entry without "limit" shows the English text with 0.01 filled in, never "{limit}"', a.ok && a.c.text === textOf('CCF_HIGH_Q', 'en') && !a.c.text.includes('{'), a.c.text);
    await app.setLanguage('ja');
    await sleep(300);
    const aj = await readCaution();
    L.check(TO + 'limit_fallback_ja: in Japanese too (0.01 filled in)', aj.text === textOf('CCF_HIGH_Q', 'ja') && !aj.text.includes('{'), aj.text);
    await app.setLanguage('en');

    // 2: an unknown code before the known one: not shown in the text, kept in data-codes, no raw key
    tamper = (j) => { j.cautions = [{ code: 'FUTURE_CODE', detail: 1 }].concat((j.cautions || []).map((c) => { const o = Object.assign({}, c); delete o.limit; return o; })); return j; };
    await applyFactor('A', '2.00000011', 1);
    const b = await waitCaution((c) => c.present && c.codes !== null && c.codes.includes('FUTURE_CODE'));
    L.check(TO + 'unknown_code_kept: an unknown code stays in data-codes (FUTURE_CODE,CCF_HIGH_Q) and in data-cautions of the root', b.ok && b.c.codes === 'FUTURE_CODE,CCF_HIGH_Q' && b.c.rootCodes === 'FUTURE_CODE,CCF_HIGH_Q', b.c);
    L.check(TO + 'unknown_code_not_shown: the visible text is the known caution (not the unknown code), no key, no placeholder, no "undefined"', typeof b.c.text === 'string' && b.c.text.startsWith(textOf('CCF_HIGH_Q', 'en')) && !/FUTURE|undefined|whatif\.caution|\{/.test(b.c.text), b.c.text);
    const raw = await page.evaluate(() => {
      const panel = document.getElementById('tabpanel-whatif');
      const bad = [];
      const walker = document.createTreeWalker(panel, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) if (/whatif\.[a-zA-Z.]+|\{[A-Za-z]+\}|undefined/.test(walker.currentNode.nodeValue)) bad.push(walker.currentNode.nodeValue.trim().slice(0, 80));
      for (const e of Array.from(panel.querySelectorAll('[title]'))) if (/whatif\.[a-zA-Z.]+|\{[A-Za-z]+\}|undefined|FUTURE/.test(e.title)) bad.push('title=' + e.title.slice(0, 80));
      return bad;
    });
    L.check(TO + 'unknown_code_no_raw_text: no raw key, placeholder, "undefined" or unknown code in the texts or titles of the tab', raw.length === 0, raw);

    // 3: only an unknown code: the tab does not break and shows no raw text (a line without text or none at all is the tab's choice)
    tamper = (j) => { j.cautions = [{ code: 'FUTURE_CODE' }]; return j; };
    await applyFactor('A', '2.00000012', 1);
    await sleep(300);
    const c = await readCaution();
    const raw2 = await page.evaluate(() => { const t = document.getElementById('tabpanel-whatif').textContent; return /whatif\.caution|undefined|\{limit\}|FUTURE/.test(t) ? t.slice(0, 200) : null; });
    L.check(TO + 'only_unknown_code: with only an unknown code the tab stays usable (state ready) and shows no raw key, placeholder or code', (await read()).root.state === 'ready' && raw2 === null && (c.text === null || c.text === ''), { state: (await read()).root.state, text: c.text, raw: raw2 });
    tamper = null;
  };

  // =====================================================================================================================
  // Y3: CCF_NOT_APPLIED (CR-20261104-whatif-group-not-applied.md; FR DESIGN section 10). Cases G13 to G16.
  // A factor other than 1 on a member of a CCF group that is not applied at baseline: the what-if scales that member alone and the CCF
  // event is missing from the number. Same badge, same line, same mechanism; the code is first in the order.
  // =====================================================================================================================
  /** The literal strings of the CR / FR DESIGN 10.4 (not read from T, so that a wrong T fails too). */
  const NA_EN = 'CCF group not applied at baseline; CCF not included';
  const NA_JA = 'ベースラインで CCF グループが適用されていないため、CCF は含まれません。';
  /** The page's answers to POST /api/whatif are passed through `tamper` (null = untouched). Never unrouted (see case states). */
  const installTamper = async () => {
    const state = { tamper: null };
    await page.route('**/api/whatif', async (r) => {
      if (!state.tamper) { await r.fallback(); return; }
      const response = await r.fetch();
      const json = await response.json();
      await r.fulfill({ response, json: state.tamper(json) });
    });
    return state;
  };

  // G13: the string, en and ja; the number is the members scaled alone
  const caseCautionNotApplied = async () => {
    const T13 = 'whatifr2_caution_notapplied_';
    await prepare(DEFAULT_VP, null);
    await openTab(writeDoc(CAUTION_DOCS.notApplied('notapplied')));
    await checkAbsent(T13 + 'nominal');
    const reading = await applyFactor('A', '2', 1);
    // the group is not applied: the top event is OR[A' AND B, Z] with A' = 2e-3, B = 2e-3 -- no CCF event, no group-mate scaled
    const alone = union([2e-3 * 2e-3, 1e-3]);
    L.check(T13 + 'number_is_member_alone: the what-if top event is the members scaled alone (A 2e-3, B 2e-3 unchanged, Z 1e-3: ' + alone + '), without a CCF event',
      close(num(reading.cells.topWhatif), alone, 1e-9), reading.cells);
    const en = await checkCaution(T13 + 'en', ['CCF_NOT_APPLIED'], 'en');
    L.check(T13 + 'en_text_is_the_cr_string: the visible text is exactly "' + NA_EN + '" and data-codes is CCF_NOT_APPLIED', en.text === NA_EN && en.codes === 'CCF_NOT_APPLIED' && T.en.notApplied === NA_EN, { text: en.text, codes: en.codes });
    L.check(T13 + 'en_badge_title: the badge title is that one text', Boolean(en.badge) && en.badge.title === NA_EN, en.badge && en.badge.title);
    const ge = await geom();
    L.check(T13 + 'en_badge_visible: the badge is visible without scrolling (inside the tab panel at scrollTop 0)', ge.scroll.rootTop === 0 && insideBox(ge.badge, ge.panel), { badge: ge.badge, panel: ge.panel, scroll: ge.scroll });
    await shot('whatifr2-caution-notapplied-en-default');

    const mark = posts.length;
    await app.setLanguage('ja');
    await app.setTheme('dark');
    await sleep(400);
    const ja = await checkCaution(T13 + 'ja', ['CCF_NOT_APPLIED'], 'ja');
    L.check(T13 + 'ja_text_is_the_catalog_string: the visible text is exactly the Japanese string of whatif.caution.ccfNotApplied and the badge title is the same', ja.text === NA_JA && T.ja.notApplied === NA_JA && Boolean(ja.badge) && ja.badge.title === NA_JA, { text: ja.text, title: ja.badge && ja.badge.title });
    L.check(T13 + 'ja_no_request: switching the language repainted badge and line and sent no POST /api/whatif', posts.length === mark, posts.length - mark);
    await scrollTo('whatif-caution');
    await sleep(100);
    const gj = await geom();
    L.check(T13 + 'ja_one_line: the Japanese line is one text line (at most 17 px high) when scrolled into view', H(gj.caution) <= 17, gj.caution);
    await scrollTop0();
    await sleep(100);
    const gb = await geom();
    L.check(T13 + 'ja_badge_visible: at scrollTop 0 the badge is inside the tab panel', gb.scroll.rootTop === 0 && insideBox(gb.badge, gb.panel), { badge: gb.badge, panel: gb.panel });
    await shot('whatifr2-caution-notapplied-ja-default');
    await app.setTheme('light');
    await app.setLanguage('en');
    await sleep(300);
    await checkTexts(T13 + 'texts', 'en');
    // the other member and a factor on both members give the same one caution
    await applyFactor('B', '3', 2);
    const both = await checkCaution(T13 + 'both_members', ['CCF_NOT_APPLIED'], 'en');
    L.check(T13 + 'no_other_ccf_code: with both members scaled the line is still the one CCF_NOT_APPLIED (no CCF_Q_ONE, no CCF_HIGH_Q)', both.codes === 'CCF_NOT_APPLIED', both.codes);
  };

  // G14: with a second caution: the first text, then "(and 1 more)" / "（ほか 1 件）"
  const caseCautionNotAppliedTwo = async () => {
    const T14 = 'whatifr2_caution_notapplied_two_';
    await prepare(DEFAULT_VP, null);
    await openTab(writeDoc(CAUTION_DOCS.notAppliedStandby('notapplied_two')));
    await applyFactor('S', '2.0000001', 1); // lambda' tau just above 0.2: the standby caution alone
    await checkCaution(T14 + 'standby_only', ['STANDBY_LARGE_LT'], 'en');
    await applyFactor('A', '2', 2);
    const en = await checkCaution(T14 + 'en', ['CCF_NOT_APPLIED', 'STANDBY_LARGE_LT'], 'en');
    L.check(T14 + 'en_order_and_suffix: data-codes is "CCF_NOT_APPLIED,STANDBY_LARGE_LT"; the visible text is "' + NA_EN + ' (and 1 more)"; the rest holds the standby text',
      en.codes === 'CCF_NOT_APPLIED,STANDBY_LARGE_LT' && en.text === NA_EN + ' (and 1 more)' && en.rest === textOf('STANDBY_LARGE_LT', 'en'), { codes: en.codes, text: en.text, rest: en.rest });
    L.check(T14 + 'en_badge_title: the badge title lists both texts, the not-applied one first, one per line', Boolean(en.badge) && en.badge.title === NA_EN + '\n' + textOf('STANDBY_LARGE_LT', 'en'), en.badge && en.badge.title);
    await scrollTo('whatif-caution');
    await sleep(100);
    L.check(T14 + 'en_one_line: the line is one text line (at most 17 px high)', H((await geom()).caution) <= 17, (await geom()).caution);
    await shot('whatifr2-caution-notapplied-two-en-default');
    await app.setLanguage('ja');
    await sleep(300);
    const ja = await checkCaution(T14 + 'ja', ['CCF_NOT_APPLIED', 'STANDBY_LARGE_LT'], 'ja');
    L.check(T14 + 'ja_suffix: the visible Japanese text is the not-applied string and "（ほか 1 件）" with no space between', ja.text === NA_JA + '（ほか 1 件）' && ja.rest === textOf('STANDBY_LARGE_LT', 'ja'), { text: ja.text, rest: ja.rest });
    await scrollTo('whatif-caution');
    await sleep(100);
    L.check(T14 + 'ja_one_line: in Japanese the line is at most 17 px high', H((await geom()).caution) <= 17, (await geom()).caution);
    await shot('whatifr2-caution-notapplied-two-ja-default');
    await app.setLanguage('en');
    await sleep(200);
    // taking the not-applied caution away (back to 1 on A) leaves the standby one, which is the new first
    await applyFactor('A', '1', 1);
    await checkCaution(T14 + 'after_first_removed', ['STANDBY_LARGE_LT'], 'en');
  };

  // G15: nothing above the line moves, default pane and the 140 px pane, for this code (rects with and without the caution)
  const caseCautionNotAppliedPosition = async () => {
    const T15 = 'whatifr2_caution_notapplied_position_';
    const tamperState = await installTamper();
    const stripCautions = (j) => { j.cautions = []; return j; };
    for (const [phase, viewport, layout] of [['default', DEFAULT_VP, null], ['minpane', DEFAULT_VP, { tree: 320, ai: 340, details: 140, analysis: 140 }]]) {
      const P = T15 + phase + '_';
      tamperState.tamper = null;
      await prepare(viewport, layout);
      await openTab(writeDoc(CAUTION_DOCS.notApplied('notapplied_pos_' + phase)));
      if (phase === 'minpane') {
        const h = await page.evaluate(() => document.getElementById('details-panel').getBoundingClientRect().height);
        L.check(P + 'setup: the bottom panel is 140 px high', h >= 139 && h <= 142, h);
      }
      // the same document and the same numbers, once with the answer's cautions removed (no caution shown) and once as the server answers
      tamperState.tamper = stripCautions;
      await applyFactor('A', '5', 1);
      await checkAbsent(P + 'quiet');
      await scrollTop0();
      await sleep(150);
      const before = await geom();
      tamperState.tamper = null;
      await applyFactor('A', '6', 1); // same format, other digits: the real answer
      const c = await checkCaution(P + 'fires', ['CCF_NOT_APPLIED'], 'en');
      await scrollTop0();
      await sleep(150);
      const after = await geom();
      const keys = phase === 'default' ? ['panel', 'root', 'slot', 'controls', 'slider', 'values', 'head', 'top', 'ratio', 'picker'] : ['slot', 'controls', 'slider', 'values', 'head', 'picker'];
      for (const k of keys) {
        L.check(`${P}${k}_identical: the rect of ${k} is the same with and without the caution (0 px difference)`, exactRect(before[k], after[k]), { before: before[k], after: after[k] });
      }
      if (phase === 'default') {
        L.check(P + 'cells_identical: every cell of the table (head corner included) has the same rect with and without the caution', before.cells.length >= 12 && exactRects(before.cells, after.cells), { before: before.cells.length, after: after.cells.length });
        L.check(P + 'not_scrolled: whatif-root and the panel keep scrollTop 0 and there is no sideways overflow', before.scroll.rootTop === 0 && after.scroll.panelTop === 0 && after.scroll.rootTop === 0 && noSideways(after), { before: before.scroll, after: after.scroll });
        const badge = after.badge;
        L.check(P + 'badge_in_head_row: the badge lies inside the head row of the table, at most 20 px high, and fully inside the tab panel', insideBox(badge, after.head, 0.5) && insideBox(badge, after.values, 0.5) && H(badge) <= 20.01 && insideBox(badge, after.panel), { badge, head: after.head, panel: after.panel });
        L.check(P + 'badge_clear_of_numbers: the badge intersects none of the three column headers, whatif-top-whatif or whatif-ratio',
          after.colHeaders.length === 3 && after.colHeaders.every((r) => area(badge, r) <= NO_AREA) && area(badge, after.top) <= NO_AREA && area(badge, after.ratio) <= NO_AREA, { badge, cols: after.colHeaders });
        L.check(P + 'line_static_below_table: the line is position static and starts at or below the bottom of whatif-values, over no cell', c.position === 'static' && Boolean(after.caution) && after.caution.top >= after.values.bottom - 0.5 && after.cells.every((r) => area(after.caution, r) <= NO_AREA), { position: c.position, caution: after.caution, values: after.values });
        for (const id of ['whatif-top-whatif', 'whatif-ratio', 'whatif-slider']) {
          L.check(`${P}${id.replace('whatif-', '')}_not_covered: elementFromPoint at the centre of ${id} returns it (or a descendant)`, await hitsItself(id), id);
        }
      } else {
        L.check(P + 'slot_and_picker: the banner slot and the picker lie inside the tab panel', insideBox(after.slot, after.panel) && insideBox(after.picker, after.panel), { panel: after.panel, slot: after.slot, picker: after.picker });
        L.check(P + 'nothing_pinned: the line is position static and the status strip has the same height with and without the caution', c.position === 'static' && Boolean(after.status) && Boolean(before.status) && Math.abs(after.status.h - before.status.h) <= 0.01, { position: c.position, before: before.status, after: after.status });
        L.check(P + 'no_sideways_overflow: no sideways overflow of the panel or whatif-root', noSideways(after), after.scroll);
        await scrollTo('whatif-caution-badge');
        await sleep(150);
        const gb = await geom();
        L.check(P + 'badge_reachable: after scrollIntoView the badge lies inside the tab panel', insideBox(gb.badge, gb.panel), { badge: gb.badge, panel: gb.panel });
        await enterOnBadge(P + 'en');
        // four shots, each after asserting its state: the badge and then the line scrolled into view, en and ja
        for (const lang of ['en', 'ja']) {
          const text = lang === 'ja' ? NA_JA : NA_EN;
          const sfx = lang === 'ja' ? '-ja' : '';
          if (lang === 'ja') { await app.setLanguage('ja'); await sleep(300); }
          await scrollTop0();
          await scrollTo('whatif-caution-badge');
          await sleep(150);
          const gB = await geom();
          const cB = await readCaution();
          L.check(`${P}badge_${lang}_shot_state: the badge (word "${T[lang].badge}") lies inside the tab panel after scrollIntoView and the line text is the catalog string`, insideBox(gB.badge, gB.panel) && Boolean(cB.badge) && badgeWord(cB.badge) === T[lang].badge && cB.text === text && cB.codes === 'CCF_NOT_APPLIED', { badge: gB.badge, panel: gB.panel, text: cB.text });
          await shot('whatifr2-caution-notapplied-minpane-badge' + sfx);
          await scrollTo('whatif-caution');
          await sleep(150);
          const gL = await geom();
          const cL = await readCaution();
          L.check(`${P}line_${lang}_shot_state: the line lies inside the tab panel after scrollIntoView, its text is the catalog string, no sideways overflow, no overlap with a table cell`, insideBox(gL.caution, gL.panel) && cL.text === text && noSideways(gL) && gL.cells.every((r) => area(gL.caution, r) <= NO_AREA) && cL.sw <= cL.cw, { caution: gL.caution, panel: gL.panel, text: cL.text, scroll: gL.scroll });
          await shot('whatifr2-caution-notapplied-minpane-line' + sfx);
        }
        await app.setLanguage('en');
        await sleep(300);
        await scrollTop0();
        await shot('whatifr2-caution-notapplied-minpane');
      }
      if (phase === 'default') await shot('whatifr2-caution-notapplied-position');
    }
    tamperState.tamper = null;

    // the narrow window (440 px, stacked shell): the Japanese line wraps in flow, nothing is cut or covered
    const N = T15 + 'narrow440_ja_';
    await prepare(DEFAULT_VP, null);
    await openTab(writeDoc(CAUTION_DOCS.notApplied('notapplied_pos_narrow')));
    await applyFactor('A', '2', 1);
    await page.setViewportSize({ width: 440, height: 900 });
    await sleep(500);
    await page.evaluate(() => document.getElementById('details-panel').scrollIntoView());
    await sleep(250);
    await app.setLanguage('ja');
    await sleep(300);
    await page.evaluate(() => { const l = document.querySelector('[data-testid="whatif-caution"]'); if (l) l.scrollIntoView({ block: 'end' }); });
    await sleep(200);
    const gn = await geom();
    const cn = await readCaution();
    L.check(N + 'state: at 440 px the Japanese line shows the catalog string, lies inside the tab panel, has no sideways overflow and covers no cell', cn.text === NA_JA && cn.codes === 'CCF_NOT_APPLIED' && insideBox(gn.caution, gn.panel) && noSideways(gn) && cn.sw <= cn.cw && gn.cells.every((r) => area(gn.caution, r) <= NO_AREA), { text: cn.text, caution: gn.caution, panel: gn.panel, scroll: gn.scroll });
    await shot('whatifr2-caution-notapplied-narrow-440-line-ja');
    await app.setLanguage('en');
    await page.setViewportSize(DEFAULT_VP);
  };

  // G16: the ways back to nothing remove badge and line at once; a non-member never fires it
  const caseCautionNotAppliedReset = async () => {
    const T16 = 'whatifr2_caution_notapplied_reset_';
    await prepare(DEFAULT_VP, null);
    await openTab(writeDoc(CAUTION_DOCS.notApplied('notapplied_reset')));
    await applyFactor('Z', '5', 1); // an independent event: not a member of g1
    await checkAbsent(T16 + 'non_member');
    await applyFactor('A', '2', 2);
    await checkCaution(T16 + 'member', ['CCF_NOT_APPLIED'], 'en');
    // the field back to 1 (A is the picked event) while Z stays scaled: the tab keeps the last answer's caution until the server answers
    // (it clears at once only when no factor is left, DESIGN 1.5), so wait for the answer, then it is gone
    await page.evaluate(() => {
      const f = document.querySelector('[data-testid="whatif-factor-input"]');
      f.value = '1';
      f.dispatchEvent(new Event('input', { bubbles: true }));
      f.dispatchEvent(new Event('change', { bubbles: true }));
    });
    const settled = await waitRead((r) => settledPred(r) && r.root.factors === '1', 8000);
    L.check(T16 + 'field_back_to_1_settled: after the answer one factor (Z) is left', settled.ok, settled.r.root);
    await checkAbsent(T16 + 'field_back_to_1');
    // the only factor back to 1: nothing is left, so badge and line go in the same task, before any answer
    await page.locator(TID('whatif-reset-all')).click();
    await waitRead((r) => settledPred(r) && r.root.factors === '0', 8000);
    await applyFactor('A', '2', 1);
    await checkCaution(T16 + 'only_factor', ['CCF_NOT_APPLIED'], 'en');
    const afterField = await page.evaluate(() => {
      const f = document.querySelector('[data-testid="whatif-factor-input"]');
      f.value = '1';
      f.dispatchEvent(new Event('input', { bubbles: true }));
      f.dispatchEvent(new Event('change', { bubbles: true }));
      const q = (id) => document.querySelector(`[data-testid="${id}"]`);
      return { caution: document.querySelectorAll('[data-testid="whatif-caution"]').length, badge: document.querySelectorAll('[data-testid="whatif-caution-badge"]').length, codes: q('whatif-root').dataset.cautions === undefined ? null : q('whatif-root').dataset.cautions };
    });
    L.check(T16 + 'field_back_to_1_at_once: typing 1 in the only factor removes badge and line in the same task (no answer needed)', afterField.caution === 0 && afterField.badge === 0 && afterField.codes === null, afterField);
    await waitRead((r) => settledPred(r) && r.root.factors === '0', 8000);
    await checkAbsent(T16 + 'only_factor_settled');
    // Reset all
    await applyFactor('A', '2', 1);
    await checkCaution(T16 + 'again', ['CCF_NOT_APPLIED'], 'en');
    const sync = await page.evaluate(() => {
      const q = (id) => document.querySelector(`[data-testid="${id}"]`);
      q('whatif-reset-all').click();
      return { banner: document.querySelectorAll('[data-testid="whatif-banner"]').length, caution: document.querySelectorAll('[data-testid="whatif-caution"]').length, badge: document.querySelectorAll('[data-testid="whatif-caution-badge"]').length, codes: q('whatif-root').dataset.cautions === undefined ? null : q('whatif-root').dataset.cautions };
    });
    L.check(T16 + 'reset_all_at_once: Reset all removes banner, badge and line in the same task (no answer needed)', sync.banner === 0 && sync.caution === 0 && sync.badge === 0 && sync.codes === null, sync);
    await waitRead((r) => settledPred(r) && r.root.factors === '0', 8000);
    await checkAbsent(T16 + 'reset_all_settled');
    // the other member, then the Reset of that one event
    await applyFactor('B', '3', 1);
    await checkCaution(T16 + 'other_member', ['CCF_NOT_APPLIED'], 'en');
    await page.locator(TID('whatif-reset-event') + '[data-node-id="B"]').click();
    const w = await waitRead((r) => settledPred(r) && r.root.factors === '0', 8000);
    L.check(T16 + 'reset_event_settled: the per-event Reset removed the only entry', w.ok, w.r.root);
    await checkAbsent(T16 + 'reset_event');
  };

  /** Append a case here: [short name, async function]. Each starts from a document it opens itself. */
  const CASES = [
    ['gridPaste', caseGridPaste],
    ['caution_ccfone', caseCautionCcfOne],
    ['caution_position', caseCautionPosition],
    ['caution_oneline', caseCautionOneLine],
    ['caution_badge', caseCautionBadge],
    ['caution_multi', caseCautionMulti],
    ['caution_boundary', caseCautionBoundary],
    ['caution_cutoff', caseCautionCutoff],
    ['caution_nofactor', caseCautionNoFactor],
    ['caution_states', caseCautionStates],
    ['caution_minpane', caseCautionMinPane],
    ['caution_stacked', caseCautionStacked],
    ['caution_texts', caseCautionTexts],
    ['caution_focus', caseCautionFocus],
    ['caution_oldserver', caseCautionOldServer],
    ['caution_notapplied', caseCautionNotApplied],
    ['caution_notapplied_two', caseCautionNotAppliedTwo],
    ['caution_notapplied_position', caseCautionNotAppliedPosition],
    ['caution_notapplied_reset', caseCautionNotAppliedReset],
  ];

  for (const [name, fn] of CASES) {
    try { await fn(); } catch (e) {
      L.check(`whatifr2_${name}: did not complete`, false, String((e && e.message) || e).split('\n')[0].slice(0, 400));
    }
  }

  // Allowed: exactly the failure case G9 causes -- the stubbed 500 "Boom" of POST /api/whatif and the browser's own resource line for it.
  const errs = app.errorsSince(0, [/^500 POST \/api\/whatif .*Boom/, /^Failed to load resource: the server responded with a status of 500 /]);
  L.check('whatifr2_console: no console errors in the whatifr2 run (only the stubbed 500 of case caution_states excepted)', errs.length === 0, errs.slice(0, 5));
  await app.api('post', '/new', { force: true });
  fs.rmSync(path.join(root, twoName), { force: true });
  for (const name of written) fs.rmSync(path.join(root, name), { force: true });
  L.info('SHOTS written by whatifr2: ' + JSON.stringify(Array.from(new Set(shots)).sort()));
  await app.context.close();
}

L.runSection('whatifr2', main);
