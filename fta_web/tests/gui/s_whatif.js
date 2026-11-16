// What-if tab (F4): UI-14, UI-15, FN-53 (GUI outputs), FN-55/56 (as shown), FN-58, FN-70 (the factor field),
// PERF-8 (browser), UI-18 / FN-64 (the strings as shown).   node s_whatif.js <url> <label> <root>
//
// Written from .division/features/F4/DESIGN.md (rev 3) before any F4 code exists: every `data-testid`, number
// format, state and text below is the one DESIGN sections 2 to 7 name, and every expected number is a hand
// calculation of SPEC 4.5 / 7.4 (R1) / FN-55 / FN-56. The pytest side is fta_web/tests/acceptance/whatif/.
//
// Checks by BRIEF criterion (check names start with the tag):
//   criterion1_ui14      the tab (placement, hooks), the picker, the slider and the field, the seven numbers
//                        for R1 (factor 10 on A: 1.00809919e-4 -> 1.080919e-3, relative 1e-9) and for a rate event
//                        (lambda 1e-5 /h, T 1000 h, f 10: q 0.0951626, relative 1e-6), the lambda unit, the slider
//                        mapping and keys (PageUp/PageDown, Home/End), the field parser, IME, Escape, repaint
//                        without a request, the geometry at 1100x800 / stacked / minimum pane
//   criterion2_ui15      the banner text and its slot (44 px, no layout shift), chips, Reset per event, Reset all,
//                        focus, the live region, aria-busy, 20 chips
//   criterion3_fn53      Save, Save As, the recovery copy, Copy CSV (Cut Sets, Importance), the events CSV, DOCX,
//                        Excel, the diagram SVG, canUndo / modified flag / revision, and no other request
//                        carries a factor (the AI context itself is built on the server: pytest)
//   criterion4_fn55      "clamped to 1" (fixed q 0.5 x 10 -> 1), the group note and the group-wide factor
//   criterion5_fn56      the method line, "cut sets from nominal values", the incomplete note
//   criterion6_fn58      every trigger in the GUI (Reset all, undo, redo, mode switch, a title edit, Open, Import,
//                        an example, New, a Details edit), the two-browser-tab check (focus path and 409 path),
//                        the message lifetime, the hidden-tab rule, Basic mode
//   criterion8_perf8     the browser timing on perf_ccf_301.json -> the "browser" block of .division/artifacts/perf/PERF-8.json
//                        (read if present, "browser" set, "inProcess" and every other key kept, written back)
//   criterion9_text      the en and ja texts of DESIGN section 6 as shown, no raw key anywhere
//   shots                whatif-ready-en-light, whatif-ready-ja-dark, whatif-chips2, whatif-group, whatif-clamped,
//                        whatif-cutoff, whatif-incomplete, whatif-loading, whatif-empty, whatif-eta, whatif-error,
//                        whatif-refusal-en, whatif-refusal-ja, whatif-minpane, whatif-narrow, whatif-basic
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const FIXTURE = path.join(L.REPO, 'fta_web', 'tests', 'fixtures', 'perf_ccf_301.json');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const TID = (id) => `[data-testid="${id}"]`;
const X = '\u00d7'; // the multiplication sign of "Valve A × 10"

// ---- the strings of DESIGN section 6 (and the reused ones) ---------------------------------------------
const T = {
  en: {
    tab: 'What-if',
    aria: 'What-if analysis',
    banner: 'What-if values, not saved',
    reset: 'Reset',
    resetAll: 'Reset all',
    resetAllTitle: 'Set every factor back to 1',
    event: 'Event',
    factor: 'Factor',
    factorTitle: 'Factor on the main parameter, from 1/100 to 100 (logarithmic scale)',
    nominal: 'Nominal',
    whatif: 'What-if',
    ratio: 'Ratio',
    paramQ: 'Main parameter q',
    lambda: 'Failure rate λ',
    q: 'Probability q',
    top: 'Top event',
    mcub: 'Method: min-cut upper bound (MCUB)',
    walk: 'Method: tree walk',
    clamped: 'clamped to 1',
    cutoff: 'cut sets from nominal values',
    incomplete: 'The top event is incomplete (the cut sets could not be finished), so there is no what-if top event.',
    loading: 'Computing the baseline…',
    empty: 'The tree has no basic events yet. Add some to try factors.',
    stale: 'The document changed, so the factors were reset to 1.',
    failed: (code) => `The what-if could not be computed: ${code}`,
    ratioTitle: 'What-if top event divided by the baseline top event',
    baselineTitle: 'Baseline: the top event of the document with no factor',
    ratioNone: 'No ratio: the baseline is 0.',
    cutoffTitle: 'The cut sets were found with the nominal probabilities and the cutoff of this document. Sets below the cutoff are not part of the what-if number.',
    range: 'Enter a number from 0.01 to 100.',
    eta: 'This analysis is not available in ETA (event tree) mode.',
    etaTab: 'Not available for an event tree (ETA mode): this analysis works on the gates of a fault tree. Switch Mode to FTA to use it.',
    factorValue: (f) => `factor ${f}`,
    resetEvent: (n) => `Reset the factor of ${n} to 1`,
    group: (g, m) => `This event is in the CCF group "${g}". The factor applies to every member: ${m}.`,
    notEvaluable: (n) => `${n} has a missing parameter, so its factor cannot be applied.`,
  },
  ja: {
    tab: 'What-if 分析',
    aria: 'What-if 分析',
    banner: 'What-if の値（保存されません）',
    reset: 'リセット',
    resetAll: 'すべてリセット',
    resetAllTitle: 'すべての倍率を 1 に戻します',
    event: '事象',
    factor: '倍率',
    factorTitle: '主パラメータにかける倍率（1/100 から 100、対数目盛）',
    nominal: '公称値',
    whatif: 'What-if 値',
    ratio: '比',
    paramQ: '主パラメータ q',
    lambda: '故障率 λ',
    q: '確率 q',
    top: '頂上事象',
    mcub: '手法: 最小カット上限（MCUB）',
    walk: '手法: ツリー計算',
    clamped: '1 に制限',
    cutoff: 'カットセットは公称値から求めています',
    incomplete: '頂上事象が不完全なため（カットセットを最後まで求められませんでした）、What-if の頂上事象はありません。',
    loading: 'ベースラインを計算中…',
    empty: 'ツリーに基本事象がありません。基本事象を追加すると倍率を試せます。',
    stale: '文書が変更されたため、倍率を 1 に戻しました。',
    failed: (code) => `What-if を計算できませんでした: ${code}`,
    ratioTitle: 'What-if の頂上事象をベースラインの頂上事象で割った値',
    baselineTitle: 'ベースライン: 倍率をかけない文書の頂上事象',
    ratioNone: 'ベースラインが 0 のため、比は求められません。',
    cutoffTitle: 'カットセットは公称値の確率とこの文書のカットオフで求めています。カットオフ未満のカットセットは What-if 値に含まれません。',
    range: '0.01 から 100 までの数値を入力してください。',
    eta: 'この解析は ETA(イベントツリー)モードでは使用できません。',
    etaTab: 'イベントツリー（ETA モード）では使用できません。この解析はフォールトツリーのゲートを対象とします。使用するにはモードを FTA に切り替えてください。',
    factorValue: (f) => `倍率 ${f}`,
    resetEvent: (n) => `${n} の倍率を 1 に戻す`,
    group: (g, m) => `この事象は CCF グループ「${g}」のメンバーです。倍率は全メンバー（${m}）にかかります。`,
    notEvaluable: (n) => `${n} はパラメータが不足しているため、倍率をかけられません。`,
  },
};

// ---- the documents (the F2 test builders, in JS) -------------------------------------------------------------
const leaf = (id, name, q, quant) => ({ id, name, type: 'Event', logicGate: 'OR', probability: q, notes: '', links: [], children: [], quant: quant || { model: 'fixed' } });
const gateOf = (id, name, kind, children, extra) => Object.assign({ id, name, type: 'Event', logicGate: kind, probability: 1.0, notes: '', links: [], children }, extra || {});
const topOf = (children) => gateOf('root', 'Top event', 'OR', children, { type: 'Root' });
const pump = (id, q) => leaf(id, 'Pump ' + id, q === undefined ? 1e-3 : q);
const rateQuant = (lambda, hours) => ({ model: 'rate', lambda, T: hours });
const betaGroup = () => ({ id: 'g1', name: 'Feed pumps', model: 'beta', beta: 0.1, alpha: null, testing: null, members: ['A', 'B'], source: 'test' });
function docOf(tree, { groups, analysis } = {}) {
  const doc = { title: 'What-if test', date: '2026-11-02', mode: 'FTA' };
  if (groups) doc.fileFormatVersion = 2;
  doc.tree = tree;
  const an = Object.assign({}, analysis || {});
  if (groups) an.ccfGroups = groups;
  if (Object.keys(an).length) doc.analysis = an;
  return doc;
}
/** R1 (SPEC 7.4): root OR [G1 AND [A, B], C], A and B 1e-3, beta group of A and B (0.1). */
const r1Doc = (analysis) => docOf(topOf([gateOf('G1', 'Pumps fail', 'AND', [pump('A'), pump('B')]), leaf('C', 'Sensor C', 0)]), { groups: [betaGroup()], analysis });
/** root OR [RATE rate (1e-5 /h, 1000 h), OTH fixed 1e-3]: a tree-walk headline. */
const rateDoc = () => docOf(topOf([leaf('RATE', 'Rate event', 0, rateQuant(1e-5, 1000)), leaf('OTH', 'Other event', 1e-3)]));
/** root OR [FIX fixed 0.5, OTH fixed 1e-3]: a factor of 10 on FIX gives q 1 (clamped). */
const clampDoc = () => docOf(topOf([leaf('FIX', 'Fixed event', 0.5), leaf('OTH', 'Other event', 1e-3)]));
/** R1 plus a rate event P: a group member, an independent rate event and a zero event. */
const mixedDoc = () => docOf(topOf([gateOf('G1', 'Pumps fail', 'AND', [pump('A'), pump('B')]), leaf('P', 'Rate event P', 0, rateQuant(1e-5, 1000)), leaf('C', 'Sensor C', 0)]), { groups: [betaGroup()] });
/** BAD is a rate event without lambda: its factor cannot be applied. */
const badDoc = () => docOf(topOf([leaf('OK', 'Fine event', 1e-3), leaf('BAD', 'Broken event', 1e-3, { model: 'rate', T: 1000 })]));
/** twenty events with long names (the chips strip must not grow the banner slot). */
const manyDoc = () => docOf(topOf(Array.from({ length: 20 }, (_v, i) => {
  const n = String(i + 1).padStart(2, '0');
  return leaf('E' + n, 'Cooling water circulation pump motor winding insulation failure number ' + n, 1e-3);
})));

// ---- expected numbers (hand calculations) --------------------------------------------------------------------
const union = (ps) => 1 - ps.reduce((acc, p) => acc * (1 - p), 1);
/** R1 top event for a factor f on A and B (beta 0.1, Q_t = 1e-3 f). */
function r1Top(f) {
  const qt = Math.min(1, 1e-3 * f);
  return union([0.1 * qt, (0.9 * qt) * (0.9 * qt)]);
}
const R1 = { baseline: 1.00809919e-4, f10: 1.080919e-3, ratio: 10.72234766898285 };
const RATE = { q: -Math.expm1(-1e-5 * 1000), q10: -Math.expm1(-1e-4 * 1000) }; // 0.00995017 and 0.0951626
const treeWalkOr = (qs) => union(qs);
/** The mixed document (R1 plus the rate event P) with P x 0.5 and A, B x 10: cut sets {CCF 1e-3}, {A', B' 8.1e-5}, {P 0.0049875...}; the exact value is 0.006063048701314162; the float form 0.006063048701314133 computed here is within relative 1e-9 of it, the tolerance the checks use. */
const MIXED_P05_A10 = union([1e-3, 8.1e-5, -Math.expm1(-5e-6 * 1000)]);

// ---- small helpers ---------------------------------------------------------------------------------------------
const norm = (s) => String(s === null || s === undefined ? '' : s).replace(/\s+/g, ' ').trim();
const num = (c) => (c && c.value !== null && c.value !== '' ? Number(c.value) : null);
const close = (a, b, rel) => typeof a === 'number' && Number.isFinite(a) && typeof b === 'number' && (b === 0 ? a === 0 : Math.abs(a - b) <= rel * Math.abs(b));
const TIMESTAMP = /\d{4}-\d\d-\d\d[ T]\d\d:\d\d(:\d\d(\.\d+)?)?/g;
const mask = (s) => String(s).replace(TIMESTAMP, '<time>');
const overlap = (a, b) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0.5 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0.5;
const insideBox = (inner, outer, tol = 1) => Boolean(inner) && Boolean(outer) && inner.left >= outer.left - tol && inner.right <= outer.right + tol && inner.top >= outer.top - tol && inner.bottom <= outer.bottom + tol;
const median = (xs) => { const s = xs.slice().sort((a, b) => a - b); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

const CELLS = {
  paramNominal: 'whatif-param-nominal', paramWhatif: 'whatif-param-whatif', qNominal: 'whatif-q-nominal', qWhatif: 'whatif-q-whatif',
  topBaseline: 'whatif-top-baseline', topWhatif: 'whatif-top-whatif', ratio: 'whatif-ratio',
};
const SIX = ['paramNominal', 'paramWhatif', 'qNominal', 'qWhatif', 'topBaseline', 'topWhatif'];

/** Everything a check reads from the tab, in one round trip. */
const readTab = (pg) => pg.evaluate((cells) => {
  const q = (id) => document.querySelector(`[data-testid="${id}"]`);
  const text = (e) => (e ? e.textContent.replace(/\s+/g, ' ').trim() : null);
  const out = { root: null, cells: {}, slider: null, field: null, picker: null };
  const root = q('whatif-root');
  if (root) {
    const d = root.dataset;
    out.root = { state: d.state, method: d.method, note: d.note, factors: d.factors, pending: d.pending, revision: d.revision, seqSent: d.seqSent, seqApplied: d.seqApplied, ariaBusy: root.getAttribute('aria-busy') };
  }
  for (const [key, id] of Object.entries(cells)) {
    const e = q(id);
    out.cells[key] = e ? { value: e.dataset.value === undefined ? null : e.dataset.value, text: e.dataset.text === undefined ? null : e.dataset.text, unit: e.dataset.unit === undefined ? null : e.dataset.unit, unitLabel: e.dataset.unitLabel === undefined ? null : e.dataset.unitLabel, param: e.dataset.param === undefined ? null : e.dataset.param, shown: text(e) } : null;
  }
  const sl = q('whatif-slider');
  if (sl) out.slider = { value: sl.value, factor: sl.dataset.factor === undefined ? null : sl.dataset.factor, disabled: sl.disabled, valuetext: sl.getAttribute('aria-valuetext'), label: sl.getAttribute('aria-label'), title: sl.getAttribute('title'), min: sl.min, max: sl.max, step: sl.step };
  const fi = q('whatif-factor-input');
  if (fi) out.field = { value: fi.value, disabled: fi.disabled, invalid: fi.getAttribute('aria-invalid'), describedby: fi.getAttribute('aria-describedby'), label: fi.getAttribute('aria-label') };
  const pk = q('whatif-picker');
  if (pk) out.picker = { value: pk.value, disabled: pk.disabled, label: pk.labels && pk.labels[0] ? text(pk.labels[0]) : null, options: Array.from(pk.options).map((o) => ({ value: o.value, text: o.textContent })) };
  return out;
}, CELLS);

const settledPred = (r) => Boolean(r.root) && r.root.state === 'ready' && r.root.pending === '0' && r.root.seqApplied === r.root.seqSent
  && SIX.every((k) => r.cells[k] && r.cells[k].value !== null && r.cells[k].value !== '');

async function main(url, label, root) {
  L.setSection('whatif[' + label + ']');
  const names = {};
  const put = (key, doc) => { names[key] = `whatif_${key}_${label}.json`; fs.writeFileSync(path.join(root, names[key]), JSON.stringify(doc, null, 2)); };
  put('r1', r1Doc());
  put('r1cutoff', r1Doc({ cutsets: { cutoff: 1e-6 } }));
  put('rate', rateDoc());
  put('clamp', clampDoc());
  put('mixed', mixedDoc());
  put('bad', badDoc());
  put('many', manyDoc());
  names.perf = `whatif_perf_${label}.json`;
  fs.copyFileSync(FIXTURE, path.join(root, names.perf));

  const app = await L.openApp(url, { viewport: { width: 1100, height: 800 }, prefs: { 'fta.advanced': '1' } });
  const { page } = app;
  page.setDefaultTimeout(8000);
  page.on('dialog', (d) => { d.accept().catch(() => {}); }); // a beforeunload prompt of a document with changes
  const requests = []; // every request this page made: the methods and bodies
  page.on('request', (r) => requests.push({ method: r.method(), url: r.url(), body: r.postData() || '' }));
  const whatifPosts = () => requests.filter((r) => r.method === 'POST' && /\/api\/whatif(\?|$)/.test(r.url)).length;

  const part = async (name, fn) => {
    try { await fn(); } catch (e) { L.check(`${name}: did not complete`, false, String((e && e.message) || e).split('\n')[0].slice(0, 400)); }
  };
  const until = async (fn, timeout = 8000, step = 50) => {
    const t0 = Date.now();
    for (;;) {
      const v = await fn();
      if (v) return v;
      if (Date.now() - t0 > timeout) return null;
      await sleep(step);
    }
  };
  const read = (pg) => readTab(pg || page);
  /** Poll the tab until pred(read) holds; {ok, r} with the last reading. */
  const waitRead = async (pred, timeout = 8000, pg) => {
    const t0 = Date.now();
    let r;
    for (;;) {
      r = await read(pg);
      let ok = false;
      try { ok = Boolean(pred(r)); } catch (_e) { ok = false; }
      if (ok) return { ok: true, r };
      if (Date.now() - t0 > timeout) return { ok: false, r };
      await sleep(60);
    }
  };
  const headline = async () => (await app.api('get', '/analysis/summary')).headline;
  const active = () => page.evaluate(() => { const a = document.activeElement; return a ? { id: a.id || '', testid: a.getAttribute('data-testid') || '', tag: a.tagName } : null; });
  const chips = () => page.locator(TID('whatif-chip')).count();
  const bannerCount = () => page.locator(TID('whatif-banner')).count();
  const message = () => page.evaluate(() => { const m = document.querySelector('[data-testid="whatif-message"]'); return m ? { text: m.textContent.replace(/\s+/g, ' ').trim(), code: m.dataset.code || '', role: m.getAttribute('role') } : null; });
  const docState = async () => {
    const server = await app.api('get', '/state');
    const rev = await app.api('get', '/revision');
    const inPage = await page.evaluate(async () => { const { store } = await import('/static/js/store.js'); const s = store.state || {}; return { revision: s.revision, documentSerial: s.documentSerial, dirty: Boolean(s.dirty), canUndo: Boolean(s.canUndo), canRedo: Boolean(s.canRedo) }; });
    return { server: { revision: rev.revision, documentSerial: rev.documentSerial, dirty: Boolean(server.dirty), canUndo: Boolean(server.canUndo), canRedo: Boolean(server.canRedo) }, page: inPage };
  };
  /** Raw catalog keys (whatif.*, tab.whatif) and unreplaced placeholders ({name}, {f}, {group}, {members}, {error}) in the text nodes, titles and aria texts of the tab, its button and its chips. */
  const rawKeys = () => page.evaluate(() => {
    const reKey = /whatif\.[a-zA-Z.]+|tab\.whatif/;
    const rePlaceholder = /\{[A-Za-z]+\}/;
    const keys = [];
    const placeholders = [];
    const test = (text, where) => {
      if (reKey.test(text)) keys.push(where + text.trim().slice(0, 80));
      if (rePlaceholder.test(text)) placeholders.push(where + text.trim().slice(0, 80));
    };
    const scan = (node) => {
      if (!node) return;
      const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) test(walker.currentNode.nodeValue, '');
      for (const e of [node].concat(Array.from(node.querySelectorAll('*')))) {
        for (const a of ['title', 'aria-label', 'aria-valuetext', 'placeholder']) {
          const v = e.getAttribute(a);
          if (v) test(v, a + '=');
        }
      }
    };
    scan(document.getElementById('tabpanel-whatif'));
    scan(document.getElementById('tab-whatif'));
    return { keys, placeholders };
  });
  const checkNoRawKeys = async (tag) => {
    const hits = await rawKeys();
    L.check(`criterion9_text: ${tag}: no raw catalog key in the What-if tab, its button, titles or aria texts`, hits.keys.length === 0, hits.keys.slice(0, 5));
    L.check(`criterion9_text: ${tag}: no unreplaced placeholder ({name}, {f}, {group}, {members}, {error}) in the same texts`, hits.placeholders.length === 0, hits.placeholders.slice(0, 5));
  };
  /** The header and row labels of whatif-values, read from its th cells (DESIGN 5.9: `<th scope>`): scope="col" and scope="row". */
  const tableLabels = () => page.evaluate(() => {
    const values = document.querySelector('[data-testid="whatif-values"]');
    const own = (th) => { const c = th.cloneNode(true); c.querySelectorAll('[data-testid="whatif-pending"],.unit').forEach((x) => x.remove()); return c.textContent.replace(/\s+/g, ' ').trim(); };
    const cols = Array.from(values.querySelectorAll('th[scope="col"]')).map((th) => ({ text: own(th), title: th.getAttribute('title') })).filter((c) => c.text !== '');
    const rows = Array.from(values.querySelectorAll('th[scope="row"]')).map((th) => ({ text: own(th), title: th.getAttribute('title') }));
    return { cols, rows };
  });
  /** Exact column headers, row labels, the two titles on them and the root's aria-label, in `lang` (DESIGN 5.6, 6). */
  const checkTableTexts = async (tag, lang, firstRow) => {
    const s = T[lang];
    const tl = await tableLabels();
    const rootAria = await page.locator(TID('whatif-root')).getAttribute('aria-label');
    L.check(`criterion9_text: ${tag} (${lang}): the column headers (th scope=col) read exactly "${s.nominal}", "${s.whatif}", "${s.ratio}"`, JSON.stringify(tl.cols.map((c) => c.text)) === JSON.stringify([s.nominal, s.whatif, s.ratio]), tl.cols);
    L.check(`criterion9_text: ${tag} (${lang}): the row labels (th scope=row) read exactly "${s[firstRow]}", "${s.q}", "${s.top}"`, JSON.stringify(tl.rows.map((c) => c.text)) === JSON.stringify([s[firstRow], s.q, s.top]), tl.rows);
    L.check(`criterion9_text: ${tag} (${lang}): the Ratio header has the title "${s.ratioTitle}"`, tl.cols.length === 3 && tl.cols[2].title === s.ratioTitle, tl.cols);
    L.check(`criterion9_text: ${tag} (${lang}): the top-event row label has the title "${s.baselineTitle}"`, tl.rows.length === 3 && tl.rows[2].title === s.baselineTitle, tl.rows);
    L.check(`criterion9_text: ${tag} (${lang}): whatif-root has the aria-label "${s.aria}"`, rootAria === s.aria, rootAria);
  };

  // ---- actions -------------------------------------------------------------------------------------------------
  const openDoc = async (name) => {
    await app.api('post', '/new', { force: true });
    const opened = await app.api('post', '/file/open', { path: path.join(root, name), force: true });
    if (opened.__error) throw new Error(`could not open ${name}: ${opened.status} ${opened.code}`);
    // the host restores the selected tab at boot: without this the What-if tab would ask for its first
    // answer before a part has installed its route stub
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
  const pick = async (id) => { await page.locator(TID('whatif-picker')).selectOption(id); };
  const setField = async (text) => {
    const f = page.locator(TID('whatif-factor-input'));
    await f.fill(String(text));
    await f.press('Enter');
  };
  const slideTo = (pos) => page.evaluate((p) => {
    const s = document.querySelector('[data-testid="whatif-slider"]');
    s.value = String(p);
    s.dispatchEvent(new Event('input', { bubbles: true }));
  }, pos);
  const key = async (name) => { await page.keyboard.press(name); await sleep(70); };
  /** Open the tab on `name` and wait for the first answer. */
  const openTab = async (name, timeout = 20000) => {
    await openDoc(name);
    await showWhatif();
    const w = await waitRead(settledPred, timeout);
    if (!w.ok) throw new Error('the What-if tab did not settle: ' + JSON.stringify(w.r.root));
    return w.r;
  };
  /** Give the picked (or the given) event a factor and wait until it is applied. */
  const armFactor = async (id, text = '3') => {
    const r0 = await read();
    const target = id || (r0.picker && r0.picker.options.length ? r0.picker.options[0].value : null);
    if (!target) throw new Error('no basic event to give a factor');
    if (r0.picker.value !== target) await pick(target);
    await setField(text);
    const w = await waitRead((r) => settledPred(r) && r.root.factors !== '0', 8000);
    if (!w.ok) throw new Error('the factor was not applied: ' + JSON.stringify(w.r.root));
    return target;
  };
  const geometry = () => page.evaluate(() => {
    const q = (id) => document.querySelector(`[data-testid="${id}"]`);
    const rect = (e) => { if (!e) return null; const b = e.getBoundingClientRect(); return { left: b.left, top: b.top, right: b.right, bottom: b.bottom, w: b.width, h: b.height }; };
    const panel = document.getElementById('tabpanel-whatif');
    const rootEl = q('whatif-root');
    return {
      panel: rect(panel), root: rect(rootEl), slot: rect(q('whatif-banner-slot')), banner: rect(q('whatif-banner')), picker: rect(q('whatif-picker')),
      controls: rect(q('whatif-controls')), slider: rect(q('whatif-slider')), top: rect(q('whatif-top-whatif')), ratio: rect(q('whatif-ratio')),
      resetAll: rect(q('whatif-reset-all')), resetEvent: rect(q('whatif-reset-event')),
      scroll: { panelTop: panel.scrollTop, rootTop: rootEl ? rootEl.scrollTop : null, panelSW: panel.scrollWidth, panelCW: panel.clientWidth, rootSW: rootEl ? rootEl.scrollWidth : null, rootCW: rootEl ? rootEl.clientWidth : null },
      vp: { w: window.innerWidth, h: window.innerHeight },
    };
  });
  const setLayout = async (value) => {
    await page.evaluate((v) => { if (v === null) localStorage.removeItem('fta.layout'); else localStorage.setItem('fta.layout', JSON.stringify(v)); }, value);
    await page.reload();
    await L.waitBoot(page);
    await app.waitDiagram(60000);
    await page.waitForTimeout(500);
  };
  /** Two chips (P x 0.5 and A x 10, A last so the picker shows the group member) on the mixed document. */
  const makeTwoChips = async (tag) => {
    await armFactor('P', '0.5');
    await armFactor('A', '10');
    const w = await waitRead((r) => settledPred(r) && r.root.factors === '2' && close(num(r.cells.topWhatif), MIXED_P05_A10, 1e-9), 8000);
    L.check(`criterion1_ui14 [${tag}]: a group factor (A x 10) and an independent factor (P x 0.5) together: the what-if top event is 0.006063048701 = 1 - (1 - 1e-3)(1 - 8.1e-5)(1 - 0.0049875) (relative 1e-9)`, w.ok, { root: w.r.root, top: w.r.cells.topWhatif, want: MIXED_P05_A10 });
  };
  /** After a reset: every factor 1, no banner, and the what-if top event is the headline, the same float. */
  const expectNominal = async (tag, msg) => {
    const w = await waitRead((r) => settledPred(r) && r.root.factors === '0', 10000);
    const h = await headline();
    const r = w.r;
    L.check(`${tag}: every factor is back to 1 (data-factors 0, no banner, no chip)`, w.ok && (await bannerCount()) === 0 && (await chips()) === 0, r.root);
    L.check(`${tag}: the what-if top event is the headline, the same float (${r.cells.topWhatif && r.cells.topWhatif.value})`,
      w.ok && r.cells.topWhatif.value === r.cells.topBaseline.value && r.cells.topBaseline.value === String(h), { whatif: r.cells.topWhatif && r.cells.topWhatif.value, baseline: r.cells.topBaseline && r.cells.topBaseline.value, headline: h });
    if (msg !== undefined) {
      const m = await message();
      if (msg === null) L.check(`${tag}: a reset the user asked for leaves no message`, Boolean(m) && m.text === '' && m.code === '', m);
      else L.check(`${tag}: the message "${T.en.stale}" is shown (data-code ${msg})`, Boolean(m) && m.code === msg && norm(m.text) === T.en.stale, m);
    }
    return r;
  };
  /** Dialog helpers of the Load action. */
  const openLoadDialog = async () => {
    await page.locator('.actionbar [data-action="load"]').click();
    await page.waitForTimeout(300);
    await L.discardIfAsked(page);
    await page.locator('.fta-filedialog').waitFor({ state: 'visible' });
    await page.waitForTimeout(300);
  };

  // =====================================================================================================================
  // criterion 1: the tab exists, after Uncertainty and before Validation
  // =====================================================================================================================
  await part('criterion1 tab', async () => {
    await openDoc(names.r1);
    const info = await page.evaluate(() => {
      const b = document.getElementById('tab-whatif');
      const p = document.getElementById('tabpanel-whatif');
      return {
        button: b ? { text: b.textContent.trim(), testid: b.getAttribute('data-testid'), role: b.getAttribute('role'), controls: b.getAttribute('aria-controls'), hidden: b.hidden } : null,
        panel: p ? { testid: p.getAttribute('data-testid'), role: p.getAttribute('role'), labelledby: p.getAttribute('aria-labelledby') } : null,
        order: Array.from(document.querySelectorAll('#bottom-tabs .tabstrip__tab')).filter((x) => !x.hidden).map((x) => x.id),
      };
    });
    L.check('criterion1_ui14: #tab-whatif exists, shown in Advanced mode, reads "What-if", with data-testid="tab-whatif"',
      Boolean(info.button) && !info.button.hidden && info.button.text === T.en.tab && info.button.testid === 'tab-whatif' && info.button.role === 'tab' && info.button.controls === 'tabpanel-whatif', info.button);
    L.check('criterion1_ui14: #tabpanel-whatif is a tabpanel with data-testid="tabpanel-whatif" labelled by the tab',
      Boolean(info.panel) && info.panel.testid === 'tabpanel-whatif' && info.panel.role === 'tabpanel' && info.panel.labelledby === 'tab-whatif', info.panel);
    const at = info.order.indexOf('tab-whatif');
    L.check('criterion1_ui14: the tab sits after Uncertainty and before Validation', at > 0 && info.order[at - 1] === 'tab-uncertainty' && info.order[at + 1] === 'tab-validation', info.order);
    await page.locator('#tab-uncertainty').focus();
    await page.keyboard.press('ArrowRight');
    let act = await active();
    L.check('criterion1_ui14: ArrowRight from Uncertainty moves to What-if and shows its panel', act && act.id === 'tab-whatif' && (await page.evaluate(() => !document.getElementById('tabpanel-whatif').hidden)), act);
    await page.keyboard.press('ArrowRight');
    act = await active();
    L.check('criterion1_ui14: ArrowRight from What-if moves to Validation', act && act.id === 'tab-validation', act);
  });

  // =====================================================================================================================
  // criterion 1 and 4: R1, factor 10 on A -> the seven numbers, the group
  // =====================================================================================================================
  await part('criterion1 R1', async () => {
    const r0 = await openTab(names.r1);
    const h = await headline();
    L.check('criterion1_ui14: R1 opens with the picker on the first basic event (A) and the slider at 1', r0.picker.value === 'A' && r0.slider.value === '0' && Number(r0.slider.factor) === 1, { picker: r0.picker.value, slider: r0.slider });
    L.check('criterion1_ui14: R1 at factor 1: baseline 1.00809919e-4 (relative 1e-9)', close(num(r0.cells.topBaseline), R1.baseline, 1e-9), r0.cells.topBaseline);
    L.check('criterion1_ui14: R1 at factor 1: the what-if top event is the baseline and the headline, the same float', r0.cells.topWhatif.value === r0.cells.topBaseline.value && r0.cells.topBaseline.value === String(h), { whatif: r0.cells.topWhatif.value, baseline: r0.cells.topBaseline.value, headline: h });
    L.check('criterion1_ui14: R1 at factor 1: the ratio is 1, nothing is shown as changed (no banner, data-factors 0)', num(r0.cells.ratio) === 1 && r0.root.factors === '0' && (await bannerCount()) === 0, { ratio: r0.cells.ratio, root: r0.root });
    L.check('criterion1_ui14: R1: the method is the MCUB (data-method mcub, the sentence "Method: min-cut upper bound (MCUB)")',
      r0.root.method === 'mcub' && norm(await page.locator(TID('whatif-method')).textContent()) === T.en.mcub, r0.root);

    await setField('10');
    const w = await waitRead((r) => settledPred(r) && close(num(r.cells.topWhatif), R1.f10, 1e-9), 8000);
    const r = w.r;
    L.check('criterion1_ui14: factor 10 on A (R1): the seven values arrive (settled)', w.ok, r.root);
    L.check('criterion1_ui14: R1 f=10: main parameter q 1e-3 -> 1e-2 (data-param q, no unit)',
      close(num(r.cells.paramNominal), 1e-3, 1e-9) && close(num(r.cells.paramWhatif), 1e-2, 1e-9) && r.cells.paramNominal.param === 'q' && r.cells.paramWhatif.unit === 'none', { n: r.cells.paramNominal, w: r.cells.paramWhatif });
    L.check('criterion1_ui14: R1 f=10: probability q (the member total Q_t) 1e-3 -> 1e-2', close(num(r.cells.qNominal), 1e-3, 1e-9) && close(num(r.cells.qWhatif), 1e-2, 1e-9), { n: r.cells.qNominal, w: r.cells.qWhatif });
    L.check('criterion1_ui14: R1 f=10: baseline top event 1.00809919e-4 (relative 1e-9)', close(num(r.cells.topBaseline), R1.baseline, 1e-9), r.cells.topBaseline);
    L.check('criterion1_ui14: R1 f=10: what-if top event 1.080919e-3 (relative 1e-9)', close(num(r.cells.topWhatif), R1.f10, 1e-9), r.cells.topWhatif);
    L.check('criterion1_ui14: R1 f=10: the ratio is what-if / baseline = 10.7223 (relative 1e-9)', close(num(r.cells.ratio), R1.ratio, 1e-9), r.cells.ratio);
    L.check('criterion1_ui14: R1 f=10: the baseline did not move (it is still the headline of the document)', r.cells.topBaseline.value === String(await headline()), r.cells.topBaseline);
    const bad = [];
    for (const k of Object.keys(CELLS)) {
      const c = r.cells[k];
      if (!c) { bad.push(k + ' missing'); continue; }
      if (c.text !== L.fmt(Number(c.value), 3)) bad.push({ k, text: c.text, want: L.fmt(Number(c.value), 3) });
      if (!c.shown.startsWith(c.text)) bad.push({ k, shown: c.shown, text: c.text });
    }
    L.check('criterion1_ui14: every number is shown as ctx.fmt.prob at 3 significant figures (data-text) and the visible text starts with it', bad.length === 0, bad.slice(0, 4));
    await checkTableTexts('R1', 'en', 'paramQ');
    L.check('criterion1_ui14: the slider is at 10 (value 100, data-factor 10) and the field reads 10', r.slider.value === '100' && Number(r.slider.factor) === 10 && r.field.value === '10', { slider: r.slider, field: r.field.value });
    L.check('criterion1_ui14: the slider is a range from -200 to 200 in steps of 1, labelled "Factor", aria-valuetext "factor 10", with its title',
      r.slider.min === '-200' && r.slider.max === '200' && r.slider.step === '1' && r.slider.label === T.en.factor && r.slider.valuetext === T.en.factorValue(10) && r.slider.title === T.en.factorTitle, r.slider);
    L.check('criterion1_ui14: the field is labelled "Factor"; the picker has the label "Event"', r.field.label === T.en.factor && r.picker.label === T.en.event, { field: r.field.label, picker: r.picker.label });
    const ticks = norm(await page.locator(TID('whatif-controls')).innerText());
    L.check('criterion1_ui14: the tick labels 1/100, 1/10, 1, 10, 100 sit under the slider', ['1/100', '1/10', '100'].every((s) => ticks.includes(s)), ticks);

    // the group (FN-55): one entry for A and B, both rows scaled, the note names the group and the members
    const note = await page.locator(TID('whatif-group-note')).first();
    L.check('criterion4_fn55: R1 A is in the CCF group: the note names the group and lists both members (data-group-id g1)',
      (await note.count()) === 1 && norm(await note.textContent()) === T.en.group('Feed pumps', 'Pump A, Pump B') && (await note.getAttribute('data-group-id')) === 'g1', await note.count() ? norm(await note.textContent()) : null);
    L.check('criterion4_fn55: one chip for the group (A), data-factor 10, data-factors 1', (await chips()) === 1 && r.root.factors === '1' && (await page.locator(TID('whatif-chip')).first().getAttribute('data-node-id')) === 'A' && (await page.locator(TID('whatif-chip')).first().getAttribute('data-factor')) === '10', r.root);
    const optA = r.picker.options.find((o) => o.value === 'A');
    L.check('criterion1_ui14: the picker marks an event with a factor: "... × 10" (U+00D7)', Boolean(optA) && optA.text.includes(' ' + X + ' 10') && !/ x 10/.test(optA.text), optA);
    await checkNoRawKeys('R1 en');
    await app.shot('whatif-ready-en-light', { locator: '#details-panel' });

    // B shows the group's factor; changing B replaces the group's entry and scales both members
    await pick('B');
    const wb = await waitRead((r2) => settledPred(r2) && r2.picker.value === 'B' && Number(r2.slider.factor) === 10, 8000);
    L.check('criterion4_fn55: the slider of the group-mate B shows the group factor 10 and the same numbers (A and B move together)',
      wb.ok && close(num(wb.r.cells.paramWhatif), 1e-2, 1e-9) && close(num(wb.r.cells.qWhatif), 1e-2, 1e-9) && wb.r.root.factors === '1', wb.r);
    await app.shot('whatif-group', { locator: '#details-panel' });
    await setField('5');
    const w5 = await waitRead((r2) => settledPred(r2) && close(num(r2.cells.topWhatif), r1Top(5), 1e-9), 8000);
    L.check('criterion4_fn55: factor 5 on B replaces the group entry: still one chip, now on B; the top event is the beta model with both members at 5e-3 (relative 1e-9)',
      w5.ok && w5.r.root.factors === '1' && (await chips()) === 1 && (await page.locator(TID('whatif-chip')).first().getAttribute('data-node-id')) === 'B', { top: w5.r.cells.topWhatif, want: r1Top(5), root: w5.r.root });
    await setField('1');
    const w1 = await waitRead((r2) => settledPred(r2) && r2.root.factors === '0', 8000);
    L.check('criterion2_ui15: setting the factor back to 1 with the field removes the banner and the chip', w1.ok && (await bannerCount()) === 0 && (await chips()) === 0 && w1.r.cells.topWhatif.value === w1.r.cells.topBaseline.value, w1.r.root);
  });

  // =====================================================================================================================
  // criterion 1: a rate event (lambda, unit), the slider mapping and keys, the field parser
  // =====================================================================================================================
  await part('criterion1 rate event', async () => {
    const r0 = await openTab(names.rate);
    L.check('criterion1_ui14: rate document: the picker starts on the rate event and the first row is "Failure rate λ"',
      r0.picker.value === 'RATE' && norm(await page.locator(TID('whatif-values')).innerText()).includes(T.en.lambda), r0.picker.value);
    L.check('criterion1_ui14: rate: the method is the tree walk ("Method: tree walk")', r0.root.method === 'treeWalk' && norm(await page.locator(TID('whatif-method')).textContent()) === T.en.walk, r0.root);
    const baseline = treeWalkOr([RATE.q, 1e-3]);
    L.check('criterion1_ui14: rate at factor 1: baseline top event = 1 - (1 - q)(1 - 1e-3) (relative 1e-9)', close(num(r0.cells.topBaseline), baseline, 1e-9), r0.cells.topBaseline);
    await setField('10');
    const w = await waitRead((r) => settledPred(r) && close(num(r.cells.qWhatif), RATE.q10, 1e-6), 8000);
    const r = w.r;
    L.check('criterion1_ui14: rate f=10: the values arrive', w.ok, r.root);
    L.check('criterion1_ui14: rate f=10: lambda 1e-5 /h -> 1e-4 /h (data-param lambda, data-unit per_hour, data-value per hour)',
      close(num(r.cells.paramNominal), 1e-5, 1e-9) && close(num(r.cells.paramWhatif), 1e-4, 1e-9) && r.cells.paramNominal.param === 'lambda' && r.cells.paramNominal.unit === 'per_hour' && r.cells.paramWhatif.unit === 'per_hour', { n: r.cells.paramNominal, w: r.cells.paramWhatif });
    L.check('criterion1_ui14: rate f=10 (T 1000 h): q 0.00995017 -> 0.0951626 (relative 1e-6)', close(num(r.cells.qNominal), RATE.q, 1e-6) && close(num(r.cells.qWhatif), 0.0951626, 1e-6), { n: r.cells.qNominal, w: r.cells.qWhatif });
    L.check('criterion1_ui14: rate f=10: top event 1 - (1 - q)(1 - 1e-3) before and after, ratio = what-if / baseline (relative 1e-9)',
      close(num(r.cells.topWhatif), treeWalkOr([RATE.q10, 1e-3]), 1e-9) && close(num(r.cells.ratio), treeWalkOr([RATE.q10, 1e-3]) / baseline, 1e-9), { top: r.cells.topWhatif, ratio: r.cells.ratio });
    L.check('criterion1_ui14: lambda cells read like the Quantification tab in /h: data-text 1e-5 and 1e-4, the unit /h in its own element, data-unit-label /h',
      r.cells.paramNominal.text === '1e-5' && r.cells.paramWhatif.text === '1e-4' && r.cells.paramNominal.unitLabel === '/h' && r.cells.paramNominal.shown.startsWith('1e-5') && r.cells.paramNominal.shown.includes('/h') && /^[0-9]+(\.[0-9]+)?(e-?[0-9]+)?$/.test(r.cells.paramWhatif.text), r.cells.paramNominal);
    await checkTableTexts('rate event', 'en', 'lambda');
    L.check('criterion4_fn55: rate: no group note and no "clamped to 1" (a rate never clamps)', (await page.locator(TID('whatif-group-note')).count()) === 0 && (await page.locator(TID('whatif-clamped')).count()) === 0);

    // the lambda unit chosen elsewhere shows when the tab is shown again; data-value stays per hour
    for (const [unit, nominalText, unitKey, unitLabel] of [['FIT', '10000', 'fit', 'FIT'], ['y', '0.0876', 'per_year', '/y']]) {
      await page.evaluate((u) => localStorage.setItem('fta.lambdaUnit', u), unit);
      await app.clickTab('details');
      await app.clickTab('whatif');
      const wu = await waitRead((x) => settledPred(x) && x.cells.paramNominal.unit === unitKey, 8000);
      const c = wu.r.cells.paramNominal;
      L.check(`criterion1_ui14: lambda unit ${unit}: 1e-5 /h reads ${nominalText} (data-text), data-unit ${unitKey}, data-unit-label ${unitLabel}, data-value unchanged (per hour)`,
        wu.ok && c.text === nominalText && c.unit === unitKey && c.unitLabel === unitLabel && close(num(c), 1e-5, 1e-9) && wu.r.cells.paramWhatif.unit === unitKey && close(num(wu.r.cells.paramWhatif), 1e-4, 1e-9), c);
    }
    await page.evaluate(() => localStorage.removeItem('fta.lambdaUnit'));
    await app.clickTab('details');
    await app.clickTab('whatif');
    await waitRead((x) => settledPred(x) && x.cells.paramNominal.unit === 'per_hour', 8000);

    // slider mapping and keys (DESIGN 5.4)
    await page.locator(TID('whatif-reset-all')).click();
    await waitRead((x) => settledPred(x) && x.root.factors === '0', 8000);
    const slider = page.locator(TID('whatif-slider'));
    await slider.focus();
    const steps = [['Home', -200, 0.01], ['PageUp', -100, 0.1], ['PageUp', 0, 1], ['PageUp', 100, 10], ['PageUp', 200, 100], ['PageUp', 200, 100], ['PageDown', 100, 10], ['PageDown', 0, 1], ['PageDown', -100, 0.1], ['End', 200, 100]];
    const trail = [];
    for (const [k, pos, f] of steps) {
      await key(k);
      const s = (await read()).slider;
      trail.push({ k, value: s.value, factor: s.factor });
    }
    L.check('criterion1_ui14: Home/End give 1/100 and 100; PageUp/PageDown move one decade (0 -> 100 -> 200 -> 100 -> 0 -> -100) so 0.1, 1, 10 and 100 are exact',
      steps.every(([_k, pos, f], i) => trail[i].value === String(pos) && Number(trail[i].factor) === f), trail);
    await key('Home'); await key('PageUp'); await key('PageUp'); // -200 -> -100 -> 0
    await key('ArrowRight');
    let s = (await read()).slider;
    L.check('criterion1_ui14: ArrowRight at position 0 gives position 1 and factor 1.023 (four significant digits)', s.value === '1' && s.factor === '1.023', s);
    await key('ArrowLeft');
    s = (await read()).slider;
    L.check('criterion1_ui14: ArrowLeft back to position 0 is exactly factor 1 (no entry, no banner)', s.value === '0' && Number(s.factor) === 1, s);
    await slideTo(50);
    let rr = (await waitRead((x) => x.slider.value === '50' && x.field.value === '3.162', 3000)).r;
    L.check('criterion1_ui14: position 50 is factor 3.162 and the field shows 3.162', rr.slider.factor === '3.162' && rr.field.value === '3.162', { slider: rr.slider, field: rr.field.value });
    await slideTo(100);
    rr = (await waitRead((x) => x.slider.value === '100', 3000)).r;
    L.check('criterion1_ui14: position 100 is exactly 10 (aria-valuetext "factor 10")', Number(rr.slider.factor) === 10 && rr.slider.valuetext === T.en.factorValue(10), rr.slider);
    await slideTo(-100);
    rr = (await waitRead((x) => x.slider.value === '-100', 3000)).r;
    L.check('criterion1_ui14: position -100 is exactly 0.1; the field shows 0.1', Number(rr.slider.factor) === 0.1 && rr.field.value === '0.1', { slider: rr.slider, field: rr.field.value });
    await slideTo(0);
    await waitRead((x) => settledPred(x) && x.root.factors === '0', 8000);

    // the field: accepted forms keep the typed value, the slider goes to the nearest position
    const accepted = [['1e1', 10, '100'], ['.5', 0.5, '-30'], ['1,5', 1.5, '18'], ['1.122', 1.122, '5'], ['0.01', 0.01, '-200'], ['100', 100, '200']];
    for (const [typed, f, pos] of accepted) {
      await setField(typed);
      const wa = await waitRead((x) => x.slider && Number(x.slider.factor) === f, 3000);
      L.check(`criterion1_ui14: the field accepts "${typed}" as ${f} (no error, slider at ${pos}, the typed value is kept exactly)`,
        wa.ok && wa.r.field.invalid !== 'true' && wa.r.slider.value === pos && (await page.locator(TID('whatif-factor-error')).count()) === 0, { slider: wa.r.slider, field: wa.r.field });
    }
    await page.locator(TID('whatif-reset-all')).click();
    await waitRead((x) => settledPred(x) && x.root.factors === '0', 8000);

    // refused forms: error text, aria-invalid, nothing changes, nothing is sent
    await setField('10');
    await waitRead((x) => settledPred(x) && x.root.factors === '1', 8000);
    const refusals = ['abc', '0', '101', '0.009', '', '1,500', '5,000', '0x1f', '1/10', '10%'];
    const bad = [];
    for (const typed of refusals) {
      const before = whatifPosts();
      await page.locator(TID('whatif-factor-input')).fill(typed);
      await page.locator(TID('whatif-factor-input')).press('Enter');
      await sleep(250);
      const st = await read();
      const err = page.locator(TID('whatif-factor-error'));
      const errText = (await err.count()) ? norm(await err.first().textContent()) : null;
      const role = (await err.count()) ? await err.first().getAttribute('role') : null;
      const ok = errText === T.en.range && role === 'alert' && st.field.invalid === 'true' && Boolean(st.field.describedby) && st.root.factors === '1' && Number(st.slider.factor) === 10 && whatifPosts() === before;
      if (!ok) bad.push({ typed, errText, role, invalid: st.field.invalid, describedby: st.field.describedby, factors: st.root.factors, factor: st.slider.factor, sent: whatifPosts() - before });
      await page.locator(TID('whatif-factor-input')).press('Escape');
      await sleep(80);
    }
    L.check(`criterion1_ui14: ${refusals.length} refused entries (abc, 0, 101, 0.009, blank, 1,500, 5,000, 0x1f, 1/10, 10%) each show "Enter a number from 0.01 to 100." (role alert, aria-invalid, aria-describedby), keep the factor 10 and send nothing`, bad.length === 0, bad.slice(0, 3));
    // the refusal shots, en and ja
    for (const lang of ['en', 'ja']) {
      await app.setLanguage(lang);
      await page.locator(TID('whatif-factor-input')).fill('abc');
      await page.locator(TID('whatif-factor-input')).press('Enter');
      await sleep(250);
      const errText = norm(await page.locator(TID('whatif-factor-error')).first().textContent());
      L.check(`criterion9_text: the refusal reads "${T[lang].range}" (${lang})`, errText === T[lang].range, errText);
      await checkNoRawKeys(`refusal ${lang}`);
      await app.shot(lang === 'en' ? 'whatif-refusal-en' : 'whatif-refusal-ja', { locator: '#details-panel' });
      await page.locator(TID('whatif-factor-input')).press('Escape');
      await sleep(100);
    }
    await app.setLanguage('en');

    // Escape restores the value and does not dismiss a toast; Enter during IME composition does not commit
    await page.evaluate(() => window.ftaShell.toast('Probe toast for the Escape check', 'info'));
    await sleep(150);
    const toastsBefore = await page.locator('#toasts .toast').count();
    await page.locator(TID('whatif-factor-input')).fill('7');
    await page.locator(TID('whatif-factor-input')).press('Escape');
    await sleep(150);
    const afterEsc = await read();
    L.check('criterion1_ui14: Escape in the field puts the factor back (10), clears the error, and does not dismiss a toast',
      afterEsc.field.value === '10' && afterEsc.field.invalid !== 'true' && toastsBefore >= 1 && (await page.locator('#toasts .toast').count()) === toastsBefore, { field: afterEsc.field, toastsBefore });
    const sentBefore = whatifPosts();
    await page.locator(TID('whatif-factor-input')).focus();
    await page.locator(TID('whatif-factor-input')).fill('8');
    const ime = await page.evaluate(() => {
      const f = document.querySelector('[data-testid="whatif-factor-input"]');
      const fire = (init) => { const ev = new KeyboardEvent('keydown', Object.assign({ key: 'Enter', bubbles: true, cancelable: true }, init)); f.dispatchEvent(ev); return ev.defaultPrevented; };
      const a = fire({ isComposing: true });
      const b = fire({ keyCode: 229 });
      return { prevented: [a, b], stillFocused: document.activeElement === f, value: f.value };
    });
    await sleep(300);
    const afterIme = await read();
    L.check('criterion1_ui14: Enter during IME composition (isComposing, keyCode 229) does not commit, blur or prevent the key: the factor stays 10 and nothing is sent',
      ime.stillFocused && ime.value === '8' && ime.prevented.every((p) => p === false) && afterIme.root.factors === '1' && Number(afterIme.slider.factor) === 10 && whatifPosts() === sentBefore, { ime, slider: afterIme.slider });
    await page.locator(TID('whatif-factor-input')).press('Enter');
    const afterEnter = await waitRead((x) => x.slider && Number(x.slider.factor) === 8, 3000);
    L.check('criterion1_ui14: a real Enter commits the 8', afterEnter.ok, afterEnter.r.slider);

    // a language switch and the sig-fig preference repaint from the last answer, without a request
    await waitRead((x) => settledPred(x), 5000);
    const posts0 = whatifPosts();
    await app.setSigFigs(5);
    await sleep(300);
    const sf5 = await read();
    L.check('criterion1_ui14: the significant-figure preference repaints the numbers without a request (5 figures)',
      whatifPosts() === posts0 && sf5.cells.topWhatif.text === L.fmt(Number(sf5.cells.topWhatif.value), 5) && sf5.cells.qWhatif.text === L.fmt(Number(sf5.cells.qWhatif.value), 5), { text: sf5.cells.topWhatif.text, want: L.fmt(Number(sf5.cells.topWhatif.value), 5), sent: whatifPosts() - posts0 });
    await app.setSigFigs(3);
    await app.setLanguage('ja');
    await sleep(300);
    L.check('criterion9_text: a language switch repaints the tab (banner, button) without a request',
      whatifPosts() === posts0 && norm(await page.locator(TID('whatif-banner-text')).textContent()) === T.ja.banner && norm(await page.locator('#tab-whatif').textContent()) === T.ja.tab, { sent: whatifPosts() - posts0 });
    L.check('criterion9_text: ja: the tree-walk method sentence "手法: ツリー計算"', norm(await page.locator(TID('whatif-method')).textContent()) === T.ja.walk, norm(await page.locator(TID('whatif-method')).textContent()));
    await checkTableTexts('rate event', 'ja', 'lambda');
    await checkNoRawKeys('rate event ja');
    await app.setLanguage('en');
  });

  // =====================================================================================================================
  // criterion 2: the banner, chips, Reset per event, Reset all, the slot, focus, the live region
  // =====================================================================================================================
  await part('criterion2 banner', async () => {
    await openTab(names.mixed);
    const probe = () => page.evaluate(() => {
      const q = (id) => document.querySelector(`[data-testid="${id}"]`);
      const slot = q('whatif-banner-slot');
      const live = q('whatif-banner-live');
      return {
        slotH: slot ? slot.getBoundingClientRect().height : null, controlsTop: q('whatif-controls').getBoundingClientRect().top, sliderTop: q('whatif-slider').getBoundingClientRect().top,
        pickerTop: q('whatif-picker').getBoundingClientRect().top, banners: document.querySelectorAll('[data-testid="whatif-banner"]').length,
        liveText: live ? live.textContent.replace(/\s+/g, ' ').trim() : null, liveRole: live ? live.getAttribute('role') : null, liveAria: live ? live.getAttribute('aria-live') : null,
      };
    });
    const p0 = await probe();
    L.check('criterion2_ui15: no factor: no banner, the banner slot is there and 44 px high, the live region is empty', p0.banners === 0 && Math.abs(p0.slotH - 44) <= 0.5 && p0.liveText === '', p0);
    L.check('criterion2_ui15: the live region is role="status" aria-live="polite"', p0.liveRole === 'status' && p0.liveAria === 'polite', p0);

    await armFactor('P', '0.5');
    const p1 = await probe();
    const banner = page.locator(TID('whatif-banner-text'));
    L.check('criterion2_ui15: with a factor != 1 the banner says exactly "What-if values, not saved"', (await bannerCount()) === 1 && norm(await banner.textContent()) === T.en.banner, await banner.count() ? norm(await banner.textContent()) : null);
    L.check('criterion2_ui15: the live region holds that text once (and the banner itself is not a live region)', p1.liveText === T.en.banner && (await page.locator(TID('whatif-banner')).evaluate((e) => !e.closest('[aria-live],[role="status"]'))), p1);
    L.check('criterion2_ui15: one chip for P with its Reset button (data-node-id P, data-factor 0.5); Reset all is there', (await chips()) === 1 && (await page.locator(TID('whatif-reset-event') + '[data-node-id="P"]').count()) === 1 && (await page.locator(TID('whatif-chip')).first().getAttribute('data-factor')) === '0.5' && (await page.locator(TID('whatif-reset-all')).count()) === 1);
    await armFactor('A', '10');
    const two = await waitRead((x) => settledPred(x) && x.root.factors === '2' && close(num(x.cells.topWhatif), MIXED_P05_A10, 1e-9), 8000);
    L.check('criterion2_ui15: two chips (P x 0.5 set first, then A x 10): the what-if top event is 0.006063048701 (relative 1e-9)', two.ok, { top: two.r.cells.topWhatif, want: MIXED_P05_A10 });
    const p2 = await probe();
    const g2 = await geometry();
    const chipIds = await page.locator(TID('whatif-chip')).evaluateAll((es) => es.map((e) => e.dataset.nodeId));
    L.check('criterion2_ui15: two chips, one per event with a factor (A and P)', (await chips()) === 2 && chipIds.slice().sort().join() === 'A,P', chipIds);
    L.check('criterion2_ui15: the slot stays 44 px with 0, 1 and 2 chips and the controls and the slider do not move (no layout shift)',
      [p0, p1, p2].every((p) => Math.abs(p.slotH - 44) <= 0.5) && [p1, p2].every((p) => Math.abs(p.controlsTop - p0.controlsTop) <= 0.5 && Math.abs(p.sliderTop - p0.sliderTop) <= 0.5 && Math.abs(p.pickerTop - p0.pickerTop) <= 0.5), { p0, p1, p2 });
    L.check('criterion2_ui15: Reset all and the first Reset button lie inside the banner slot and do not overlap each other', insideBox(g2.resetAll, g2.slot) && insideBox(g2.resetEvent, g2.slot) && !overlap(g2.resetAll, g2.resetEvent), { slot: g2.slot, all: g2.resetAll, one: g2.resetEvent });
    L.check('criterion2_ui15: the whole banner lies inside the slot', insideBox(g2.banner, g2.slot), { banner: g2.banner, slot: g2.slot });
    const inLive = await page.evaluate(() => ['whatif-chip', 'whatif-top-whatif', 'whatif-ratio', 'whatif-q-whatif', 'whatif-param-whatif', 'whatif-banner'].filter((id) => Array.from(document.querySelectorAll(`[data-testid="${id}"]`)).some((e) => e.closest('[aria-live],[role="status"]'))));
    L.check('criterion2_ui15: no chip and no number is inside a live region', inLive.length === 0, inLive);
    const busy = await page.evaluate(() => ({ root: document.querySelector('[data-testid="whatif-root"]').hasAttribute('aria-busy'), values: document.querySelector('[data-testid="whatif-values"]').getAttribute('aria-busy') }));
    L.check('criterion2_ui15: aria-busy is never on whatif-root, and settled whatif-values is not busy', busy.root === false && (busy.values === null || busy.values === 'false'), busy);
    const picked = await read();
    L.check('criterion2_ui15: the picker marks both events: "... × 0.5" and "... × 10"', picked.picker.options.find((o) => o.value === 'P').text.includes(' ' + X + ' 0.5') && picked.picker.options.find((o) => o.value === 'A').text.includes(' ' + X + ' 10'), picked.picker.options);
    const chipLabel = await page.locator(TID('whatif-chip')).first().getAttribute('aria-label');
    const chipBtn = await page.locator(TID('whatif-reset-event') + '[data-node-id="P"]');
    L.check('criterion2_ui15: a chip is a labelled group ("Rate event P factor 0.5") and its button reads "Reset" with the label "Reset the factor of Rate event P to 1"',
      chipLabel === `Rate event P ${T.en.factorValue(0.5)}` && norm(await chipBtn.textContent()) === T.en.reset && (await chipBtn.getAttribute('aria-label')) === T.en.resetEvent('Rate event P'), { chipLabel, label: await chipBtn.getAttribute('aria-label') });
    L.check('criterion2_ui15: Reset all reads "Reset all" and has the title "Set every factor back to 1"', norm(await page.locator(TID('whatif-reset-all')).textContent()) === T.en.resetAll && (await page.locator(TID('whatif-reset-all')).getAttribute('title')) === T.en.resetAllTitle);
    await checkNoRawKeys('two chips en');
    await app.shot('whatif-chips2', { locator: '#details-panel' });

    // Reset per event: P goes, A stays; focus goes to the picker
    await chipBtn.click();
    const wr = await waitRead((x) => settledPred(x) && x.root.factors === '1', 8000);
    const afterOne = await active();
    L.check('criterion2_ui15: Reset on the chip of P removes only P (one chip left, on A, data-factors 1), and focus goes to the picker',
      wr.ok && (await chips()) === 1 && (await page.locator(TID('whatif-chip')).first().getAttribute('data-node-id')) === 'A' && afterOne && afterOne.testid === 'whatif-picker', { root: wr.r.root, active: afterOne });
    const pMid = await probe();
    L.check('criterion2_ui15: after Reset per event the controls have not moved', Math.abs(pMid.controlsTop - p0.controlsTop) <= 0.5 && Math.abs(pMid.slotH - 44) <= 0.5, pMid);
    // Reset all
    await page.locator('#title-input').focus(); // so that the move of focus to the picker is the tab's doing
    await page.locator(TID('whatif-reset-all')).click();
    const wa = await waitRead((x) => settledPred(x) && x.root.factors === '0', 8000);
    const afterAll = await active();
    const p3 = await probe();
    const h = await headline();
    L.check('criterion2_ui15: Reset all: the banner is gone, data-factors 0, no chip, the picked slider is back at 1 (position 0), the live region is empty',
      wa.ok && (await bannerCount()) === 0 && (await chips()) === 0 && wa.r.slider.value === '0' && Number(wa.r.slider.factor) === 1 && p3.liveText === '', { root: wa.r.root, slider: wa.r.slider, live: p3.liveText });
    L.check('criterion2_ui15: Reset all moves focus to the picker', afterAll && afterAll.testid === 'whatif-picker', afterAll);
    L.check('criterion2_ui15: Reset all: the controls and the slider are where they were before the first factor (the slot is always 44 px)', Math.abs(p3.controlsTop - p0.controlsTop) <= 0.5 && Math.abs(p3.sliderTop - p0.sliderTop) <= 0.5 && Math.abs(p3.slotH - 44) <= 0.5, { p0, p3 });
    L.check('criterion6_fn58: Reset all: the what-if top event is the headline, the same float', wa.r.cells.topWhatif.value === wa.r.cells.topBaseline.value && wa.r.cells.topBaseline.value === String(h), { whatif: wa.r.cells.topWhatif.value, headline: h });
    const msg = await message();
    L.check('criterion6_fn58: a reset the user asked for leaves no message (whatif-message exists and is empty)', Boolean(msg) && msg.text === '' && msg.code === '', msg);
    // the same two factors in the other order give the same number
    await armFactor('A', '10');
    await armFactor('P', '0.5');
    const rev = await waitRead((x) => settledPred(x) && x.root.factors === '2' && close(num(x.cells.topWhatif), MIXED_P05_A10, 1e-9), 8000);
    L.check('criterion2_ui15: A x 10 first, then P x 0.5: the same what-if top event 0.006063048701 (relative 1e-9)', rev.ok, { top: rev.r.cells.topWhatif, want: MIXED_P05_A10 });
    await page.locator(TID('whatif-reset-all')).click();
    await waitRead((x) => settledPred(x) && x.root.factors === '0', 8000);

    // pending: a slow answer shows data-pending, aria-busy on the table only, the dot after 150 ms, and does not dim the numbers
    const slow = async (route) => { await sleep(900); await route.continue().catch(() => {}); }; // may outlive the unroute below
    await page.route('**/api/whatif', slow);
    try {
      await setField('10');
      await sleep(300);
      const pend = await page.evaluate(() => {
        const root = document.querySelector('[data-testid="whatif-root"]');
        const values = document.querySelector('[data-testid="whatif-values"]');
        const cell = document.querySelector('[data-testid="whatif-top-whatif"]');
        return { pending: root.dataset.pending, rootBusy: root.hasAttribute('aria-busy'), valuesBusy: values.getAttribute('aria-busy'), dot: document.querySelectorAll('[data-testid="whatif-pending"]').length, opacity: getComputedStyle(cell).opacity, valuesOpacity: getComputedStyle(values).opacity };
      });
      L.check('criterion2_ui15: while an answer is on its way data-pending is 1, aria-busy is true on whatif-values only, the pending dot shows after 150 ms, the numbers are not dimmed',
        pend.pending === '1' && pend.rootBusy === false && pend.valuesBusy === 'true' && pend.dot === 1 && pend.opacity === '1' && pend.valuesOpacity === '1', pend);
    } finally { await page.unroute('**/api/whatif', slow); }
    const done = await waitRead((x) => settledPred(x) && x.root.factors === '1', 8000);
    const busyAfter = await page.locator(TID('whatif-values')).getAttribute('aria-busy');
    L.check('criterion2_ui15: after the answer the table is settled again (data-pending 0, no pending dot, aria-busy gone)', done.ok && (await page.locator(TID('whatif-pending')).count()) === 0 && (busyAfter === null || busyAfter === 'false'), { root: done.r.root, busyAfter });
    await page.locator(TID('whatif-reset-all')).click();
    await waitRead((x) => settledPred(x) && x.root.factors === '0', 8000);
  });

  await part('criterion2 twenty chips', async () => {
    await openTab(names.many);
    const base = await geometry();
    const baseControls = base.controls.top;
    for (let i = 1; i <= 20; i += 1) {
      const id = 'E' + String(i).padStart(2, '0');
      await pick(id);
      await setField(String(2 + (i % 8)));
      await sleep(130);
    }
    const w = await waitRead((x) => settledPred(x) && x.root.factors === '20', 15000);
    const g = await geometry();
    L.check('criterion2_ui15: twenty events with long names: twenty entries (data-factors 20)', w.ok, w.r.root);
    L.check('criterion2_ui15: twenty chips do not change the slot (44 px) or move the controls, and the banner stays inside the slot', Math.abs(g.slot.h - 44) <= 0.5 && Math.abs(g.controls.top - baseControls) <= 0.5 && insideBox(g.banner, g.slot), { slot: g.slot, controls: g.controls.top, base: baseControls, banner: g.banner });
    L.check('criterion2_ui15: twenty chips cause no sideways overflow (whatif-root and the panel scrollWidth <= clientWidth)', g.scroll.rootSW <= g.scroll.rootCW && g.scroll.panelSW <= g.scroll.panelCW, g.scroll);
    L.check('criterion2_ui15: Reset all is still inside the slot with twenty chips', insideBox(g.resetAll, g.slot), { all: g.resetAll, slot: g.slot });
    await page.locator(TID('whatif-reset-all')).click();
    const wr = await waitRead((x) => settledPred(x) && x.root.factors === '0', 10000);
    L.check('criterion2_ui15: Reset all clears twenty entries at once', wr.ok && (await bannerCount()) === 0 && (await chips()) === 0, wr.r.root);
  });

  // =====================================================================================================================
  // criterion 4 / 5: clamp, cutoff note, incomplete, not evaluable, empty, ETA, error, loading
  // =====================================================================================================================
  await part('criterion4 clamped to 1', async () => {
    await openTab(names.clamp);
    await setField('10');
    const w = await waitRead((x) => settledPred(x) && close(num(x.cells.qWhatif), 1, 1e-12), 8000);
    const r = w.r;
    L.check('criterion4_fn55: fixed q 0.5, f 10: the main parameter is 5, q is 1', w.ok && close(num(r.cells.paramNominal), 0.5, 1e-9) && close(num(r.cells.paramWhatif), 5, 1e-9) && close(num(r.cells.qNominal), 0.5, 1e-9) && num(r.cells.qWhatif) === 1, r.cells);
    const clamped = page.locator(TID('whatif-clamped'));
    L.check('criterion4_fn55: "clamped to 1" is shown beside the what-if q', (await clamped.count()) === 1 && norm(await clamped.textContent()) === T.en.clamped, await clamped.count() ? norm(await clamped.textContent()) : null);
    L.check('criterion4_fn55: f 10 on FIX: the top event is 1 (the clamped q) and the ratio is what-if / baseline', num(r.cells.topWhatif) === 1 && close(num(r.cells.ratio), 1 / treeWalkOr([0.5, 1e-3]), 1e-9), { top: r.cells.topWhatif, ratio: r.cells.ratio });
    await app.shot('whatif-clamped', { locator: '#details-panel' });
    await app.setLanguage('ja');
    await sleep(250);
    L.check('criterion9_text: "clamped to 1" in Japanese: 1 に制限', norm(await page.locator(TID('whatif-clamped')).textContent()) === T.ja.clamped);
    await checkNoRawKeys('clamped ja');
    await app.setLanguage('en');
    await setField('0.01');
    const w2 = await waitRead((x) => settledPred(x) && close(num(x.cells.qWhatif), 0.005, 1e-9), 8000);
    L.check('criterion4_fn55: f 0.01 on q 0.5 gives q 0.005 and no "clamped to 1"', w2.ok && close(num(w2.r.cells.paramWhatif), 0.005, 1e-9) && (await clamped.count()) === 0, w2.r.cells.qWhatif);
  });

  await part('criterion5 cutoff note', async () => {
    await openTab(names.r1cutoff);
    const r0 = await read();
    L.check('criterion5_fn56: cutoff 1e-6, factor 1: baseline 1e-4 (relative 1e-9); the what-if top event is the headline',
      close(num(r0.cells.topBaseline), 1e-4, 1e-9) && r0.cells.topWhatif.value === r0.cells.topBaseline.value, r0.cells.topBaseline);
    await setField('10');
    const w = await waitRead((x) => settledPred(x) && close(num(x.cells.topWhatif), 1e-3, 1e-9), 8000);
    L.check('criterion5_fn56: cutoff 1e-6, f 10 on A: the what-if top event is 1e-3 (the cut sets come from nominal values), not 1.080919e-3', w.ok, w.r.cells.topWhatif);
    const note = page.locator(TID('whatif-cutoff-note'));
    L.check('criterion5_fn56: the note "cut sets from nominal values" is shown (data-note cutsets_from_nominal)', (await note.count()) === 1 && norm(await note.textContent()) === T.en.cutoff && w.r.root.note === 'cutsets_from_nominal', { root: w.r.root });
    L.check('criterion9_text: the cutoff note carries its explanation as a title, exactly (en)', (await note.getAttribute('title')) === T.en.cutoffTitle, await note.getAttribute('title'));
    await app.shot('whatif-cutoff', { locator: '#details-panel' });
    await app.setLanguage('ja');
    await sleep(250);
    L.check('criterion9_text: the cutoff note in Japanese', norm(await note.textContent()) === T.ja.cutoff);
    L.check('criterion9_text: the cutoff note title, exactly (ja)', (await note.getAttribute('title')) === T.ja.cutoffTitle, await note.getAttribute('title'));
    await checkNoRawKeys('cutoff ja');
    await app.setLanguage('en');
    // the plain R1 has no note
    await openTab(names.r1);
    await setField('10');
    const wp = await waitRead((x) => settledPred(x) && close(num(x.cells.topWhatif), R1.f10, 1e-9), 8000);
    L.check('criterion5_fn56: R1 without a cutoff has no "cut sets from nominal values" note', wp.ok && (await page.locator(TID('whatif-cutoff-note')).count()) === 0 && !wp.r.root.note, wp.r.root);
  });

  await part('criterion5 incomplete', async () => {
    await openTab(names.r1);
    // The server cannot be made to cut the cut sets short from here (pytest does, with SUMMARY_LIMITS); the page is
    // given the answer DESIGN 3.2 defines for method "incomplete" and must show no number and the note.
    const stub = async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      Object.assign(body, { method: 'incomplete', baseline: null, whatIf: null, ratio: null, note: 'incomplete' });
      await route.fulfill({ response: res, json: body });
    };
    await page.route('**/api/whatif', stub);
    try {
      await setField('10');
      const w = await waitRead((x) => x.root && x.root.state === 'ready' && x.root.method === 'incomplete' && x.root.pending === '0', 8000);
      const r = w.r;
      L.check('criterion5_fn56: incomplete: data-method incomplete, data-note incomplete', w.ok && r.root.note === 'incomplete', r.root);
      L.check('criterion5_fn56: incomplete: no top event and no ratio are shown ("—", empty data-value)',
        ['topBaseline', 'topWhatif', 'ratio'].every((k) => r.cells[k] && r.cells[k].value === '' && r.cells[k].text === '—'), r.cells);
      const sentence = page.locator(TID('whatif-incomplete-note'));
      L.check('criterion5_fn56: the incomplete sentence is shown', (await sentence.count()) === 1 && norm(await sentence.textContent()) === T.en.incomplete, await sentence.count() ? norm(await sentence.textContent()) : null);
      L.check('criterion5_fn56: incomplete: no cutoff note', (await page.locator(TID('whatif-cutoff-note')).count()) === 0);
      await app.shot('whatif-incomplete', { locator: '#details-panel' });
      await app.setLanguage('ja');
      await sleep(250);
      L.check('criterion9_text: the incomplete sentence in Japanese', norm(await sentence.textContent()) === T.ja.incomplete);
      await checkNoRawKeys('incomplete ja');
      await app.setLanguage('en');
    } finally { await page.unroute('**/api/whatif', stub); }
  });

  await part('criterion1 ratio none', async () => {
    await openTab(names.r1);
    // A baseline of 0 cannot be made from here either (pytest does it by underflow): the page is given the DESIGN 3.2 answers
    // "baseline 0, what-if above 0, ratio null" and "ratio null because the quotient was not finite" and must print the em dash,
    // with the tooltip whatif.ratioNone for the first and without it for the second.
    let answer = { baseline: 0, whatIf: 1e-3, ratio: null };
    const stub = async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      Object.assign(body, answer);
      await route.fulfill({ response: res, json: body });
    };
    const ratioInfo = () => page.evaluate(() => {
      const c = document.querySelector('[data-testid="whatif-ratio"]');
      const t = c.getAttribute('title') || (c.querySelector('[title]') ? c.querySelector('[title]').getAttribute('title') : null) || (c.closest('[title]') ? c.closest('[title]').getAttribute('title') : null);
      return { value: c.dataset.value, text: c.dataset.text, shown: c.textContent.replace(/\s+/g, ' ').trim(), title: t };
    });
    await page.route('**/api/whatif', stub);
    try {
      for (const lang of ['en', 'ja']) {
        await app.setLanguage(lang);
        answer = { baseline: 0, whatIf: 1e-3, ratio: null };
        await setField(lang === 'en' ? '10' : '9');
        const w = await waitRead((x) => x.root && x.root.state === 'ready' && x.root.pending === '0' && x.cells.topBaseline && x.cells.topBaseline.value === '0', 8000);
        const info = await ratioInfo();
        L.check(`criterion9_text: baseline 0 and ratio null: the ratio cell shows "—" with an empty data-value and the tooltip "${T[lang].ratioNone}" (${lang})`, w.ok && info.value === '' && info.text === '—' && info.shown.startsWith('—') && info.title === T[lang].ratioNone, info);
      }
      await app.setLanguage('en');
      answer = { baseline: 1e-4, whatIf: 1e-3, ratio: null };
      await setField('8');
      const w2 = await waitRead((x) => x.root && x.root.state === 'ready' && x.root.pending === '0' && x.cells.topBaseline && x.cells.topBaseline.value === '0.0001', 8000);
      const info2 = await ratioInfo();
      L.check('criterion1_ui14: a ratio that is null with a baseline above 0 (not finite) also shows "—", without the "baseline is 0" tooltip', w2.ok && info2.value === '' && info2.text === '—' && info2.title !== T.en.ratioNone, info2);
      await checkNoRawKeys('ratio none');
    } finally { await page.unroute('**/api/whatif', stub); await app.setLanguage('en'); }
  });

  await part('criterion4 not evaluable', async () => {
    await openTab(names.bad);
    await pick('BAD');
    const w = await waitRead((x) => x.root && x.root.state === 'ready' && x.picker.value === 'BAD' && x.root.pending === '0', 8000);
    const note = page.locator(TID('whatif-not-evaluable'));
    L.check('criterion4_fn55: an event with a missing parameter: the sentence "{name} has a missing parameter, so its factor cannot be applied." is shown, the slider and the field are disabled',
      w.ok && (await note.count()) === 1 && norm(await note.textContent()) === T.en.notEvaluable('Broken event') && w.r.slider.disabled === true && w.r.field.disabled === true, { slider: w.r.slider, field: w.r.field, text: await note.count() ? norm(await note.textContent()) : null });
    await checkNoRawKeys('not evaluable en');
    await app.setLanguage('ja');
    await sleep(250);
    L.check('criterion9_text: the not-evaluable sentence in Japanese', (await note.count()) === 1 && norm(await note.textContent()) === T.ja.notEvaluable('Broken event'), await note.count() ? norm(await note.textContent()) : null);
    await checkNoRawKeys('not evaluable ja');
    await app.setLanguage('en');
    await pick('OK');
    const w2 = await waitRead((x) => x.root && x.root.state === 'ready' && x.picker.value === 'OK' && x.slider.disabled === false && x.root.pending === '0', 8000);
    L.check('criterion4_fn55: the other event is usable', w2.ok && (await note.count()) === 0, w2.r.slider);
  });

  await part('states: loading', async () => {
    await openDoc(names.r1);
    let first = true;
    const delayed = async (route) => { if (first) { first = false; await sleep(3500); } await route.continue().catch(() => {}); };
    await page.route('**/api/whatif', delayed);
    try {
      await showWhatif();
      const loading = await waitRead((x) => x.root && x.root.state === 'loading', 3000);
      const block = page.locator(TID('whatif-loading'));
      L.check('states: before the first answer data-state is loading with the sentence "Computing the baseline…" and the controls are disabled',
        loading.ok && (await block.count()) === 1 && norm(await block.textContent()) === T.en.loading && (!loading.r.slider || loading.r.slider.disabled === true) && (!loading.r.field || loading.r.field.disabled === true), loading.r);
      await app.shot('whatif-loading', { locator: '#details-panel' });
      await app.setLanguage('ja'); // while the answer is still on its way
      await sleep(200);
      const stillLoading = await read();
      L.check('criterion9_text: the loading sentence in Japanese (switched while loading)', stillLoading.root.state === 'loading' && norm(await block.textContent()) === T.ja.loading, { state: stillLoading.root.state, text: await block.count() ? norm(await block.textContent()) : null });
      await app.setLanguage('en');
      const ready = await waitRead(settledPred, 10000);
      L.check('states: then the numbers arrive and the loading block is gone', ready.ok && (await block.count()) === 0, ready.r.root);
    } finally { await page.unroute('**/api/whatif', delayed); }
  });

  await part('states: error', async () => {
    await openTab(names.r1);
    await setField('10');
    await waitRead((x) => settledPred(x) && x.root.factors === '1', 8000);
    const boom = async (route) => route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ ok: false, error: { code: 'INTERNAL_ERROR', message: 'Boom', detail: {} } }) });
    await page.route('**/api/whatif', boom);
    try {
      await setField('5');
      const w = await waitRead((x) => x.root && x.root.state === 'error', 6000);
      const err = page.locator(TID('whatif-error'));
      L.check('states: a failed answer: data-state error, whatif-error (role alert, data-code INTERNAL_ERROR) reading exactly "The what-if could not be computed: INTERNAL_ERROR" ({error} is the error code, not the server message "Boom")',
        w.ok && (await err.count()) === 1 && (await err.getAttribute('role')) === 'alert' && (await err.getAttribute('data-code')) === 'INTERNAL_ERROR' && norm(await err.textContent()) === T.en.failed('INTERNAL_ERROR'), await err.count() ? norm(await err.textContent()) : null);
      await checkNoRawKeys('error en');
      L.check('states: the factors are kept and the controls stay enabled in the error state', w.r.root.factors === '1' && w.r.slider.disabled === false && w.r.field.disabled === false, { root: w.r.root, slider: w.r.slider });
      await app.shot('whatif-error', { locator: '#details-panel' });
      await app.setLanguage('ja');
      await sleep(250);
      L.check('criterion9_text: the error sentence in Japanese reads exactly "What-if を計算できませんでした: INTERNAL_ERROR"', norm(await err.textContent()) === T.ja.failed('INTERNAL_ERROR'), norm(await err.textContent()));
      await checkNoRawKeys('error ja');
      await app.setLanguage('en');
    } finally { await page.unroute('**/api/whatif', boom); }
    // no answer at all: {error} is NETWORK_ERROR
    const gone = async (route) => route.abort('failed');
    await page.route('**/api/whatif', gone);
    try {
      await setField('6');
      const wn = await waitRead((x) => x.root && x.root.state === 'error', 6000);
      const errN = page.locator(TID('whatif-error'));
      L.check('states: a request that gets no answer: whatif-error reads exactly "The what-if could not be computed: NETWORK_ERROR"', wn.ok && (await errN.count()) === 1 && (await errN.getAttribute('data-code')) === 'NETWORK_ERROR' && norm(await errN.textContent()) === T.en.failed('NETWORK_ERROR'), (await errN.count()) ? norm(await errN.textContent()) : null);
    } finally { await page.unroute('**/api/whatif', gone); }
    await setField('4');
    const back = await waitRead((x) => settledPred(x) && Number(x.slider.factor) === 4, 8000);
    L.check('states: the next input retries and the error goes', back.ok && (await page.locator(TID('whatif-error')).count()) === 0, back.r.root);
  });

  await part('states: empty and ETA', async () => {
    await openTab(names.r1);
    await armFactor('A', '10');
    // ETA: the tab is greyed with the reason, its panel shows the existing ETA notice
    await page.locator('#mode-select').selectOption('ETA');
    const eta = await waitRead((x) => x.root && x.root.state === 'eta', 8000);
    const tab = await page.evaluate(() => { const b = document.getElementById('tab-whatif'); return { unavailable: b.classList.contains('is-unavailable'), data: b.dataset.unavailable || null, title: b.title || '' }; });
    L.check('states: in ETA mode the What-if tab is greyed with the reason as its title', tab.unavailable && tab.data === 'eta' && tab.title === T.en.etaTab, tab);
    const notice = page.locator(TID('whatif-eta'));
    L.check('states: data-state eta shows the ETA notice and every factor is gone', eta.ok && (await notice.count()) === 1 && norm(await notice.textContent()) === T.en.eta && eta.r.root.factors === '0' && (await bannerCount()) === 0, eta.r.root);
    await app.shot('whatif-eta', { locator: '#details-panel' });
    await app.setLanguage('ja');
    await sleep(250);
    L.check('criterion9_text: the ETA notice in Japanese', norm(await notice.textContent()) === T.ja.eta, norm(await notice.textContent()));
    L.check('criterion9_text: the greyed tab\'s title (tab.etaUnavailable) in Japanese after the language switch (host.js applyMode runs on fta:language)', (await page.locator('#tab-whatif').getAttribute('title')) === T.ja.etaTab, await page.locator('#tab-whatif').getAttribute('title'));
    await app.setLanguage('en');
    await page.locator('#mode-select').selectOption('FTA');
    const back = await waitRead((x) => settledPred(x) && x.root.factors === '0', 10000);
    L.check('states: back in FTA the tab shows numbers again and is no longer greyed', back.ok && (await page.evaluate(() => !document.getElementById('tab-whatif').classList.contains('is-unavailable'))), back.r.root);

    // empty: a tree with no basic event
    await app.api('post', '/new', { force: true });
    await page.reload();
    await L.waitBoot(page);
    await app.waitDiagram(60000);
    await showWhatif();
    const empty = await waitRead((x) => x.root && x.root.state === 'empty', 8000);
    const block = page.locator(TID('whatif-empty'));
    L.check('states: a tree with no basic event: data-state empty and the sentence "The tree has no basic events yet. Add some to try factors."', empty.ok && (await block.count()) === 1 && norm(await block.textContent()) === T.en.empty, empty.r.root);
    await app.shot('whatif-empty', { locator: '#details-panel' });
    await app.setLanguage('ja');
    await sleep(250);
    L.check('criterion9_text: the empty sentence in Japanese', norm(await block.textContent()) === T.ja.empty);
    await checkNoRawKeys('empty ja');
    await app.setLanguage('en');
  });

  // =====================================================================================================================
  // criterion 9: the Japanese texts, dark theme, with chips and the group note
  // =====================================================================================================================
  await part('criterion9 Japanese', async () => {
    await openTab(names.r1);
    await armFactor('A', '10');
    await app.setLanguage('ja');
    await app.setTheme('dark');
    await sleep(300);
    const r = await read();
    const note = page.locator(TID('whatif-group-note'));
    const noteText = norm(await note.textContent());
    L.check('criterion9_text: ja: the tab button, the banner and the Reset buttons', norm(await page.locator('#tab-whatif').textContent()) === T.ja.tab && norm(await page.locator(TID('whatif-banner-text')).textContent()) === T.ja.banner
      && norm(await page.locator(TID('whatif-reset-all')).textContent()) === T.ja.resetAll && norm(await page.locator(TID('whatif-reset-event')).first().textContent()) === T.ja.reset
      && (await page.locator(TID('whatif-reset-all')).getAttribute('title')) === T.ja.resetAllTitle && (await page.locator(TID('whatif-reset-event')).first().getAttribute('aria-label')) === T.ja.resetEvent('Pump A'), null);
    L.check('criterion9_text: ja: the picker label, the slider label and value text, the slider title', r.picker.label === T.ja.event && r.slider.label === T.ja.factor && r.slider.valuetext === T.ja.factorValue(10) && r.slider.title === T.ja.factorTitle, { picker: r.picker.label, slider: r.slider });
    await checkTableTexts('R1', 'ja', 'paramQ');
    L.check('criterion9_text: ja: the method sentence', norm(await page.locator(TID('whatif-method')).textContent()) === T.ja.mcub);
    L.check('criterion9_text: ja: the group note reads exactly, members joined with ", "', noteText === T.ja.group('Feed pumps', 'Pump A, Pump B'), noteText);
    await checkNoRawKeys('ready ja');
    await app.shot('whatif-ready-ja-dark', { locator: '#details-panel' });
    await app.setTheme('light');
    await app.setLanguage('en');
  });

  // =====================================================================================================================
  // criterion 3: FN-53 in the GUI -- the recovery copy, then Save / CSV / DOCX / Excel / SVG with a factor active
  // =====================================================================================================================
  await part('criterion3 recovery copy', async () => {
    const home = process.env.FTA_GUI_HOME || '';
    const dir = home ? path.join(home, '.fta_editor', 'recovery') : '';
    if (!home || !fs.existsSync(dir)) {
      L.skip('criterion3_fn53: the recovery copy is byte-identical with a factor active', 'the home folder of this server is not known (FTA_GUI_HOME); run.mjs sets it for a server it starts');
      return;
    }
    const findCopy = (needle) => {
      const hits = fs.readdirSync(dir).filter((f) => /^[0-9a-f]{16}\.json$/.test(f)).map((f) => path.join(dir, f)).filter((f) => fs.readFileSync(f, 'utf8').includes(needle));
      return hits.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0] || null;
    };
    await openTab(names.r1);
    await app.api('patch', '/nodes/C', { name: 'Sensor C, recovery check' });
    await page.evaluate(() => window.ftaShell.refresh());
    const copyFile = await until(() => findCopy('Sensor C, recovery check'), 9000, 300);
    L.check('criterion3_fn53: (setup) the modified document has a recovery copy', Boolean(copyFile), fs.readdirSync(dir));
    if (!copyFile) return;
    await showWhatif();
    await waitRead(settledPred, 15000);
    const s0 = await docState();
    const before = fs.readFileSync(copyFile);
    await armFactor('A', '10');
    const w = await waitRead((x) => settledPred(x) && close(num(x.cells.topWhatif), R1.f10, 1e-9), 8000);
    L.check('criterion3_fn53: (setup) factor 10 is active', w.ok, w.r.cells.topWhatif);
    await sleep(3800); // longer than the writer's 2 s debounce
    const s1 = await docState();
    const after = fs.readFileSync(findCopy('Sensor C, recovery check') || copyFile);
    L.check('criterion3_fn53: the recovery copy is byte-identical with factor 10 active', Buffer.compare(before, after) === 0 && !/whatif|"factor/i.test(after.toString('utf8')), { before: before.length, after: after.length });
    L.check('criterion3_fn53: with factor 10 active revision, documentSerial, the modified flag, canUndo and canRedo are unchanged (server and page)', JSON.stringify(s0) === JSON.stringify(s1) && s0.server.dirty === true, { s0, s1 });
    // guard: a real edit does change the copy
    await app.api('patch', '/nodes/C', { name: 'Sensor C, recovery check two' });
    await page.evaluate(() => window.ftaShell.refresh());
    const changed = await until(() => { const f = findCopy('recovery check two'); return f && Buffer.compare(fs.readFileSync(f), before) !== 0; }, 9000, 300);
    L.check('criterion3_fn53: (guard) a real edit does change the recovery copy, so the comparison could have failed', Boolean(changed));
  });

  await part('criterion3 outputs', async () => {
    const chromium = L.BROWSER === 'chromium';
    const mark = requests.length;
    await openTab(names.r1);
    await app.api('patch', '/nodes/C', { name: 'Sensor C, checked' });
    await page.evaluate(() => window.ftaShell.refresh());
    await page.waitForTimeout(500);
    const download = async (locator, tag, name, timeout) => {
      const [d] = await Promise.all([page.waitForEvent('download', { timeout: timeout || 60000 }), locator.click()]);
      const file = path.join(L.OUT, `whatif_${label}_${tag}_${name}`);
      await d.saveAs(file);
      return file;
    };
    const capture = async (tag) => {
      const out = {};
      for (const tab of ['cutsets', 'importance']) {
        await app.clickTab(tab);
        await page.waitForSelector(tab === 'cutsets' ? '#tabpanel-cutsets tbody tr[data-rank]' : '#tabpanel-importance .anl-table tbody tr', { timeout: 20000 });
        await page.waitForTimeout(300);
        await page.locator(`#tabpanel-${tab} [data-role="copy"]`).click();
        await page.waitForTimeout(300);
        out['copy_' + tab] = chromium ? await page.evaluate(() => navigator.clipboard.readText()) : null;
      }
      await app.clickTab('report');
      await page.waitForSelector('[data-report-generate]');
      for (const s of ['headline', 'cutsets', 'importance', 'events']) {
        const b = page.locator('[data-section="' + s + '"]');
        if (!(await b.isChecked())) await b.click();
      }
      const docx = await download(page.locator('[data-report-generate]'), tag, 'report.docx');
      const xlsx = await download(page.locator('[data-report-xlsx]'), tag, 'export.xlsx');
      const csv = await download(page.locator('[data-report-csv]'), tag, 'events.csv', 30000);
      out.csv = fs.readFileSync(csv);
      out.parsed = mask(JSON.stringify(L.parseExports(docx, xlsx)));
      const svg = await download(page.locator('#diagram-root .diagram__btn', { hasText: 'SVG' }), tag, 'diagram.svg', 30000);
      out.svg = mask(fs.readFileSync(svg, 'utf8'));
      return out;
    };
    const save = async () => {
      await page.locator('.actionbar [data-action="save"]').click();
      await until(async () => (await page.textContent('#dirty-text')) === 'Saved', 6000);
      await page.waitForTimeout(300);
      return fs.readFileSync(path.join(root, names.r1));
    };

    const savedBefore = await save();
    const before = await capture('before');
    const s0 = await docState();
    L.check('criterion3_fn53: (setup) Save wrote the document (A has q 1e-3, nothing of a factor)', JSON.parse(savedBefore.toString('utf8')).tree.children[0].children[0].probability === 1e-3, savedBefore.length);
    if (chromium) L.check('criterion3_fn53: (setup) both Copy CSV texts are real tables', before.copy_cutsets.split(/\r?\n/).length > 2 && before.copy_importance.split(/\r?\n/).length > 2, [before.copy_cutsets.slice(0, 80), before.copy_importance.slice(0, 80)]);
    else L.skip('criterion3_fn53: Copy CSV texts are equal', L.BROWSER + ': a script may not read the clipboard in this engine');

    await app.clickTab('whatif');
    await waitRead(settledPred, 15000);
    await armFactor('A', '10');
    const w = await waitRead((x) => settledPred(x) && close(num(x.cells.topWhatif), R1.f10, 1e-9), 8000);
    L.check('criterion3_fn53: (setup) factor 10 on A is active: the what-if top event is 1.080919e-3', w.ok, w.r.cells.topWhatif);
    const s1 = await docState();
    L.check('criterion3_fn53: with factor 10 active revision, documentSerial, the modified flag, canUndo and canRedo are unchanged (server and page)', JSON.stringify(s0) === JSON.stringify(s1), { s0, s1 });
    const savedAfter = await save();
    const after = await capture('after');
    L.check('criterion3_fn53: Save with factor 10 active writes the same bytes as before', Buffer.compare(savedBefore, savedAfter) === 0 && !/whatif|"factor/i.test(savedAfter.toString('utf8')), { before: savedBefore.length, after: savedAfter.length });
    if (chromium) {
      L.check('criterion3_fn53: Copy CSV (Cut Sets) is byte-identical', after.copy_cutsets === before.copy_cutsets, [before.copy_cutsets.slice(0, 160), after.copy_cutsets.slice(0, 160)]);
      L.check('criterion3_fn53: Copy CSV (Importance) is byte-identical', after.copy_importance === before.copy_importance, [before.copy_importance.slice(0, 160), after.copy_importance.slice(0, 160)]);
    }
    L.check('criterion3_fn53: the events CSV download is byte-identical', Buffer.compare(before.csv, after.csv) === 0 && before.csv.length > 50, { before: before.csv.length, after: after.csv.length });
    L.check('criterion3_fn53: DOCX text and Excel cell values are equal (creation timestamps masked)', before.parsed === after.parsed && before.parsed.length > 500, { before: before.parsed.length, after: after.parsed.length });
    L.check('criterion3_fn53: the exported diagram SVG is equal (creation timestamps masked)', before.svg === after.svg && before.svg.length > 500 && !after.svg.includes('1.08e-3') && !after.svg.includes('1.080919'), { before: before.svg.length, after: after.svg.length });
    // Save As writes a fresh file: the same bytes as the Save before the slider moved
    const copyName = `whatif_r1_copy_${label}.json`;
    await page.locator('.actionbar [data-action="save-as"]').click();
    await page.locator('.fta-filedialog').waitFor({ state: 'visible' });
    await page.locator('.fta-filedialog .fdlg-name').fill(copyName);
    await page.keyboard.press('Enter');
    await page.locator('.fta-filedialog').waitFor({ state: 'detached' });
    await page.waitForTimeout(600);
    const copyPath = path.join(root, copyName);
    L.check('criterion3_fn53: Save As with factor 10 active writes the same bytes as the Save before', fs.existsSync(copyPath) && Buffer.compare(fs.readFileSync(copyPath), savedBefore) === 0, fs.existsSync(copyPath) ? fs.readFileSync(copyPath).length : null);
    fs.rmSync(copyPath, { force: true });
    const s2 = await docState();
    L.check('criterion3_fn53: after Save, Save As and all the exports the revision, documentSerial and canUndo are still those of before the slider moved', s2.server.revision === s0.server.revision && s2.server.documentSerial === s0.server.documentSerial && s2.server.canUndo === s0.server.canUndo && s2.page.revision === s0.page.revision, { s0, s2 });
    // the factor is still there: Save and the exports are not document changes (DESIGN 2.4)
    await app.clickTab('whatif');
    const still = await waitRead((x) => settledPred(x) && x.root.factors === '1' && close(num(x.cells.topWhatif), R1.f10, 1e-9), 10000);
    L.check('criterion6_fn58: Save, Save As and the exports are not reset triggers: the factor 10 and its banner are still there', still.ok && (await bannerCount()) === 1, still.r.root);
    // no other request carried a factor (D1: only POST /api/whatif does); the AI context is built on the server (pytest)
    const offenders = requests.slice(mark).filter((r) => /\/api\//.test(r.url) && !/\/api\/whatif(\?|$)/.test(r.url) && /"factors?"\s*:/.test(r.body));
    L.check('criterion3_fn53: no request other than POST /api/whatif carries a factor (so no export, save or AI call can see one)', offenders.length === 0, offenders.slice(0, 3).map((r) => r.method + ' ' + r.url.replace(/^.*\/api/, '/api')));
    L.check('criterion3_fn53: the factor travelled only in POST /api/whatif bodies, as {revision, documentSerial, factors}', requests.slice(mark).filter((r) => r.method === 'POST' && /\/api\/whatif(\?|$)/.test(r.url)).every((r) => { const b = JSON.parse(r.body); return typeof b.revision === 'number' && typeof b.documentSerial === 'number' && b.factors && typeof b.factors === 'object'; }));
  });

  // =====================================================================================================================
  // criterion 6: FN-58 triggers in the GUI
  // =====================================================================================================================
  await part('criterion6 triggers', async () => {
    await openTab(names.mixed);

    // Reset all (user)
    await armFactor('P', '3');
    await page.locator(TID('whatif-reset-all')).click();
    await expectNominal('criterion6_fn58 Reset all', null);

    // a document change seen while the tab is open: focus stays where it was (the title box)
    await armFactor('P', '3');
    await page.locator('#title-input').focus();
    await page.evaluate(() => { const t = document.getElementById('title-input'); t.value = 'What-if title edit'; t.dispatchEvent(new Event('change', { bubbles: true })); });
    await expectNominal('criterion6_fn58 title edit', 'DOCUMENT_CHANGED');
    const act = await active();
    L.check('criterion6_fn58: a reset caused by a document change never moves focus (the title box keeps it)', act && act.id === 'title-input', act);

    // undo, redo
    await armFactor('P', '3');
    await page.locator('#btn-undo').click();
    await expectNominal('criterion6_fn58 undo', 'DOCUMENT_CHANGED');
    await armFactor('P', '3');
    await page.locator('#btn-redo').click();
    await expectNominal('criterion6_fn58 redo', 'DOCUMENT_CHANGED');

    // a mode switch: FTA -> ETA -> FTA
    await armFactor('P', '3');
    await page.locator('#mode-select').selectOption('ETA');
    const eta = await waitRead((x) => x.root && x.root.state === 'eta' && x.root.factors === '0', 8000);
    L.check('criterion6_fn58 mode switch: ETA resets every factor and shows the ETA state', eta.ok && (await bannerCount()) === 0, eta.r.root);
    await page.locator('#mode-select').selectOption('FTA');
    await expectNominal('criterion6_fn58 mode switch back to FTA');

    // Open (the Load dialog), an example, Import (the picker), New
    await armFactor('P', '3');
    await openLoadDialog();
    await page.locator('.fta-filedialog .fdlg-row', { hasText: names.r1 }).dblclick();
    await page.waitForTimeout(800);
    const opened = await expectNominal('criterion6_fn58 Open', 'DOCUMENT_CHANGED');
    L.check('criterion6_fn58 Open: the opened document is R1 (baseline 1.00809919e-4)', close(num(opened.cells.topBaseline), R1.baseline, 1e-9), opened.cells.topBaseline);

    await armFactor('A', '3');
    await openLoadDialog();
    await page.locator('.fta-filedialog [data-source="example"]').click();
    const list = page.locator('.fta-modal[data-kind="list"]');
    await list.waitFor({ state: 'visible' });
    await list.locator('.fta-choice[data-value="sampleFTA.json"]').click();
    await list.waitFor({ state: 'detached' });
    await page.waitForTimeout(800);
    await expectNominal('criterion6_fn58 example', 'DOCUMENT_CHANGED');

    await armFactor();
    await openLoadDialog();
    const [chooser] = await Promise.all([page.waitForEvent('filechooser'), page.locator('.fta-filedialog [data-source="import"]').click()]);
    await chooser.setFiles(path.join(root, names.mixed));
    await page.waitForTimeout(1000);
    await expectNominal('criterion6_fn58 Import', 'DOCUMENT_CHANGED');

    await armFactor('A', '3');
    await page.locator('.actionbar [data-action="new"]').click();
    await page.waitForTimeout(300);
    await L.discardIfAsked(page);
    const empty = await waitRead((x) => x.root && x.root.state === 'empty' && x.root.factors === '0', 8000);
    L.check('criterion6_fn58 New: every factor is gone and the tab shows the empty state', empty.ok && (await bannerCount()) === 0, empty.r.root);
    await checkNoRawKeys('after the triggers');
  });

  await part('criterion6 hidden tab', async () => {
    await openTab(names.mixed);
    await armFactor('A', '3');
    await app.clickTab('details');
    await app.selectTreeNode('C');
    const c0 = whatifPosts();
    const focusOf = () => page.evaluate(() => {
      const a = document.activeElement;
      const field = a && a.closest ? a.closest('.fta-field') : null;
      const label = field ? field.querySelector('label') : null;
      return a ? { tag: a.tagName, id: a.id || '', field: label ? label.textContent.trim() : '', inWhatif: Boolean(a.closest && a.closest('#tabpanel-whatif')) } : null;
    });
    await app.editDetailsField('Name', 'Sensor C edited while hidden', 'enter');
    const focusBefore = await focusOf();
    await page.waitForTimeout(1200);
    const focusAfter = await focusOf();
    const c1 = whatifPosts();
    L.check('criterion6_fn58: a Details edit with the What-if tab mounted (factor reset in the background) leaves document.activeElement where it was, and not in the What-if panel', JSON.stringify(focusBefore) === JSON.stringify(focusAfter) && focusAfter.inWhatif === false, { focusBefore, focusAfter });
    const named = await app.api('get', '/nodes/C');
    L.check('criterion6_fn58: a Details edit while the What-if tab is mounted but hidden sends no what-if request (0 requests)', c1 === c0 && named.node && named.node.name === 'Sensor C edited while hidden', { sent: c1 - c0, name: named.node && named.node.name });
    await app.clickTab('whatif');
    const w = await waitRead((x) => settledPred(x) && x.root.factors === '0', 10000);
    const c2 = whatifPosts();
    L.check('criterion6_fn58: shown again, the tab sends one request, its factors are 1, and the message says the document changed', w.ok && c2 - c1 === 1, { sent: c2 - c1, root: w.r.root });
    await expectNominal('criterion6_fn58 hidden-tab edit', 'DOCUMENT_CHANGED');
  });

  await part('criterion6 message lifetime and two tabs', async () => {
    await openTab(names.mixed);
    const page2 = await app.context.newPage();
    try {
      await page2.goto(url);
      await L.waitBoot(page2);
      await page2.locator('#tab-details').click(); // tab 2 boots on the tab restored from storage, What-if here
      const rowC = page2.locator('#tree-root li.fta-tree-item[data-id="C"] > .fta-tree-row');
      await rowC.waitFor({ state: 'visible' });
      const editInTab2 = async (value) => {
        const before = (await app.api('get', '/revision')).revision;
        await rowC.click();
        const field = page2.locator('#details-root .fta-details-form .fta-field').filter({ has: page2.locator('label', { hasText: 'Name' }) }).first();
        const control = field.locator('input,textarea').first();
        await control.click();
        await page2.keyboard.press('Control+A');
        await page2.keyboard.type(value, { delay: 3 });
        await page2.keyboard.press('Enter');
        const rose = await until(async () => (await app.api('get', '/revision')).revision !== before, 6000);
        if (!rose) throw new Error('the edit in the second tab did not reach the server');
      };

      // path A: the focus event of the shell (D7)
      await armFactor('A', '10');
      await editInTab2('Sensor C, edited in tab 2');
      await page.bringToFront();
      await page.evaluate(() => window.dispatchEvent(new Event('focus')));
      const reset = await waitRead((x) => x.root && x.root.factors === '0', 3000);
      L.check('criterion6_fn58 two tabs: an edit in tab 2 resets tab 1 within 3 s of its focus (data-factors 0, no banner)', reset.ok && (await bannerCount()) === 0, reset.r.root);
      const m1 = await message();
      L.check('criterion6_fn58 two tabs: tab 1 says so: whatif-message data-code DOCUMENT_CHANGED, "The document changed, so the factors were reset to 1."', Boolean(m1) && m1.code === 'DOCUMENT_CHANGED' && norm(m1.text) === T.en.stale && m1.role === 'status', m1);
      await sleep(1000);
      const m1b = await message();
      L.check('criterion6_fn58 two tabs: the message is still there 1 s later (a store notification does not clear it)', Boolean(m1b) && m1b.code === 'DOCUMENT_CHANGED' && norm(m1b.text) === T.en.stale, m1b);
      await expectNominal('criterion6_fn58 two tabs (focus path)');
      await app.setLanguage('ja');
      await sleep(250);
      const mJa = await message();
      await app.setLanguage('en');
      await sleep(250);
      const mEn = await message();
      L.check('criterion6_fn58 two tabs: a language switch translates the message and does not clear it', Boolean(mJa) && norm(mJa.text) === T.ja.stale && Boolean(mEn) && norm(mEn.text) === T.en.stale, { mJa, mEn });
      await checkNoRawKeys('stale message');
      await pick('P');
      await sleep(250);
      const m2 = await message();
      L.check('criterion6_fn58 message lifetime: a picker change clears the message', Boolean(m2) && m2.text === '' && m2.code === '', m2);

      // path B: no focus event; the next slider move meets 409 STALE_REVISION
      await armFactor('P', '4');
      const marker = requests.length;
      await editInTab2('Sensor C, edited in tab 2 again');
      await slideTo(100);
      const reset2 = await waitRead((x) => x.root && x.root.factors === '0' && x.root.state !== 'loading', 8000);
      const sent = requests.slice(marker).filter((r) => r.method === 'POST' && /\/api\/whatif(\?|$)/.test(r.url)).length;
      await sleep(1200); // the shell's reload (ftaShell.checkServer) has happened by now
      const m3 = await message();
      L.check('criterion6_fn58 two tabs: without a focus event the next slider move meets 409 STALE_REVISION: the factors are 1 and the message has data-code STALE_REVISION', reset2.ok && sent >= 1 && Boolean(m3) && m3.code === 'STALE_REVISION' && norm(m3.text) === T.en.stale, { root: reset2.r.root, sent, m3 });
      await expectNominal('criterion6_fn58 two tabs (409 path)');
      const m3b = await message();
      L.check('criterion6_fn58 two tabs: the STALE_REVISION message survives the shell\'s reload', Boolean(m3b) && m3b.code === 'STALE_REVISION', m3b);
      await setField('2');
      await waitRead((x) => settledPred(x) && x.root.factors === '1', 8000);
      const m4 = await message();
      L.check('criterion6_fn58 message lifetime: the next factor input clears the message', Boolean(m4) && m4.text === '' && m4.code === '', m4);
      const edited = (await app.api('get', '/nodes/C')).node;
      L.check('criterion6_fn58 two tabs: (guard) the edits of tab 2 are in the document', edited && /edited in tab 2 again/.test(edited.name), edited && edited.name);
    } finally { await page2.close(); }
  });

  await part('criterion6 Basic mode', async () => {
    await openTab(names.mixed);
    await armFactor('A', '3');
    const marker = whatifPosts();
    await app.setAdvanced(false);
    await sleep(500);
    const hidden = await page.evaluate(() => { const b = document.getElementById('tab-whatif'); return { hidden: b.hidden, aria: b.getAttribute('aria-hidden'), shown: Array.from(document.querySelectorAll('#bottom-tabs [role=tab][aria-selected=true]')).map((x) => x.dataset.tab) }; });
    L.check('criterion6_fn58 Basic mode: #tab-whatif is hidden (hidden, aria-hidden true) and the panel falls back to Details', hidden.hidden && hidden.aria === 'true' && JSON.stringify(hidden.shown) === '["details"]', hidden);
    await page.locator('#tab-details').focus();
    await page.keyboard.press('ArrowRight');
    const act = await active();
    L.check('criterion6_fn58 Basic mode: ArrowRight from Details reaches Validation (the What-if tab is skipped)', act && act.id === 'tab-validation', act);
    await app.shot('whatif-basic');
    await sleep(600);
    L.check('criterion6_fn58 Basic mode: no what-if request while the tab is hidden', whatifPosts() === marker, whatifPosts() - marker);
    await app.setAdvanced(true);
    await app.clickTab('whatif');
    const back = await waitRead((x) => settledPred(x) && x.root.factors === '1', 8000);
    L.check('criterion6_fn58 Basic mode: switching Advanced off and on is not a document change: the chip and the banner are back', back.ok && (await bannerCount()) === 1 && (await chips()) === 1, back.r.root);
  });

  // =====================================================================================================================
  // geometry (UI-14 layout budget, DESIGN 5.0): default panes at 1100x800, stacked shell, minimum pane
  // =====================================================================================================================
  await part('criterion1 geometry', async () => {
    await page.setViewportSize({ width: 1100, height: 800 });
    await openDoc(names.mixed);
    await setLayout(null);
    await showWhatif();
    await waitRead(settledPred, 15000);
    await makeTwoChips("1100x800");
    await sleep(300);
    const g = await geometry();
    const inV = (b) => Boolean(b) && b.left >= -1 && b.top >= -1 && b.right <= g.vp.w + 1 && b.bottom <= g.vp.h + 1;
    L.check('criterion1_ui14 [1100x800, default panes]: the slider, the what-if top event, the ratio and the banner lie inside the tab panel without scrolling',
      insideBox(g.slider, g.panel) && insideBox(g.top, g.panel) && insideBox(g.ratio, g.panel) && insideBox(g.banner, g.panel), { panel: g.panel, slider: g.slider, top: g.top, ratio: g.ratio, banner: g.banner });
    L.check('criterion1_ui14 [1100x800, default panes]: the panel and whatif-root are not scrolled (scrollTop 0) and have no sideways overflow', g.scroll.panelTop === 0 && g.scroll.rootTop === 0 && g.scroll.rootSW <= g.scroll.rootCW && g.scroll.panelSW <= g.scroll.panelCW, g.scroll);
    L.check('criterion1_ui14 [1100x800, default panes]: the same controls are inside the window', [g.slider, g.top, g.ratio, g.banner, g.picker].every(inV), { slider: g.slider, top: g.top, vp: g.vp });
    L.check('criterion4_fn55 [1100x800]: the group note is shown with two chips', (await page.locator(TID('whatif-group-note')).count()) === 1 && (await chips()) === 2);
    await app.shot('whatif-chips2', { locator: '#details-panel' });

    // the stacked shell (<= 900 px)
    await page.setViewportSize({ width: 800, height: 900 });
    await sleep(500);
    await page.evaluate(() => document.getElementById('details-panel').scrollIntoView());
    await sleep(250);
    // DESIGN 5.0: the stacked panel is shorter than the tab, so the rects are measured after scrolling each control in
    for (const [hook, field] of [['whatif-banner', 'banner'], ['whatif-slider', 'slider'], ['whatif-top-whatif', 'top'], ['whatif-ratio', 'ratio']]) {
      await page.evaluate((id) => document.querySelector(`[data-testid="${id}"]`).scrollIntoView({ block: 'nearest' }), hook);
      await sleep(150);
      const gs = await geometry();
      L.check(`criterion1_ui14 [800x900, stacked]: ${field} is reachable by scrolling (inside the tab panel after scrollIntoView)`, insideBox(gs[field], gs.panel), { panel: gs.panel, [field]: gs[field] });
    }
    await page.evaluate(() => { for (const e of [document.getElementById('tabpanel-whatif'), document.querySelector('[data-testid="whatif-root"]')]) e.scrollTop = 0; });
    await sleep(150);
    const gs = await geometry();
    L.check('criterion1_ui14 [800x900, stacked]: the banner slot and the picker lie inside the tab panel', insideBox(gs.slot, gs.panel) && insideBox(gs.picker, gs.panel), { panel: gs.panel, slot: gs.slot, picker: gs.picker });
    L.check('criterion1_ui14 [800x900, stacked]: no sideways overflow', gs.scroll.rootSW <= gs.scroll.rootCW && gs.scroll.panelSW <= gs.scroll.panelCW, gs.scroll);
    await app.shot('whatif-narrow', { locator: '#details-panel' });

    // the 140 px minimum pane: the banner slot and the picker are in view, the rest is reached by scrolling, never sideways
    await page.setViewportSize({ width: 1100, height: 800 });
    await setLayout({ tree: 320, ai: 340, details: 140, analysis: 140 });
    await showWhatif();
    await waitRead(settledPred, 15000);
    await makeTwoChips("minimum pane");
    await sleep(300);
    const h = await page.evaluate(() => document.getElementById('details-panel').getBoundingClientRect().height);
    L.check('criterion1_ui14 [minimum pane]: (setup) the bottom panel is 140 px high', h >= 139 && h <= 142, h);
    // the test's own fill and select scrolled the tab; the guarantee is for the tab at its top
    await page.evaluate(() => { for (const e of [document.getElementById('tabpanel-whatif'), document.querySelector('[data-testid="whatif-root"]')]) e.scrollTop = 0; });
    await sleep(150);
    const gm = await geometry();
    L.check('criterion1_ui14 [minimum pane]: the banner slot and the picker lie inside the tab panel', insideBox(gm.slot, gm.panel) && insideBox(gm.picker, gm.panel), { panel: gm.panel, slot: gm.slot, picker: gm.picker });
    L.check('criterion1_ui14 [minimum pane]: no sideways overflow', gm.scroll.rootSW <= gm.scroll.rootCW && gm.scroll.panelSW <= gm.scroll.panelCW, gm.scroll);
    await page.evaluate(() => document.querySelector('[data-testid="whatif-slider"]').scrollIntoView({ block: 'nearest' }));
    await sleep(150);
    const gr = await geometry();
    L.check('criterion1_ui14 [minimum pane]: the slider is reachable by scrolling (inside the panel after scrollIntoView)', insideBox(gr.slider, gr.panel), { panel: gr.panel, slider: gr.slider });
    await page.evaluate(() => document.querySelector('[data-testid="whatif-top-whatif"]').scrollIntoView({ block: 'nearest' }));
    await sleep(150);
    const gt = await geometry();
    L.check('criterion1_ui14 [minimum pane]: the what-if top event is reachable by scrolling', insideBox(gt.top, gt.panel), { panel: gt.panel, top: gt.top });
    await page.evaluate(() => { for (const e of [document.getElementById('tabpanel-whatif'), document.querySelector('[data-testid="whatif-root"]')]) e.scrollTop = 0; });
    await app.shot('whatif-minpane', { locator: '#details-panel' });
    await setLayout(null);
  });

  // =====================================================================================================================
  // criterion 8: the browser timing on the 301-event fixture
  // =====================================================================================================================
  await part('criterion8 PERF-8 browser', async () => {
    const BOUND_MS = 500;
    const RUNS = 8;
    const EVENT = 'C0_1_0'; // a member of group G1 of the fixture
    await openDoc(names.perf);
    const tFirst = Date.now();
    await showWhatif();
    const first = await waitRead(settledPred, 30000);
    const firstMs = Date.now() - tFirst;
    L.check('criterion8_perf8: (setup) the tab shows numbers for the 301-event fixture with its baseline computed (MCUB)', first.ok && first.r.root.method === 'mcub', first.r.root);
    L.info('PERF-8 first answer after the tab was opened (baseline built), ms', firstMs);
    await pick(EVENT);
    const picked = await waitRead((x) => settledPred(x) && x.picker.value === EVENT, 15000);
    L.check(`criterion8_perf8: (setup) ${EVENT} is picked`, picked.ok, picked.r.picker && picked.r.picker.value);
    const fields = await app.api('get', '/revision');
    const answer = await app.api('post', '/whatif', { revision: fields.revision, documentSerial: fields.documentSerial, factors: { [EVENT]: 10 } });
    if (answer.__error || typeof answer.whatIf !== 'number') throw new Error('the reference answer for factor 10 failed: ' + JSON.stringify(answer).slice(0, 200));
    const expected = answer.whatIf;
    const timed = () => page.evaluate(async ({ positions, want }) => {
      const slider = document.querySelector('[data-testid="whatif-slider"]');
      let t1 = null;
      let finish;
      const done = new Promise((resolve) => { finish = resolve; });
      const hit = () => {
        const c = document.querySelector('[data-testid="whatif-top-whatif"]');
        if (!c || c.dataset.value === undefined || c.dataset.value === '') return false;
        return Math.abs(Number(c.dataset.value) - want) <= 1e-12 * Math.abs(want);
      };
      const obs = new MutationObserver(() => { if (t1 === null && hit()) { t1 = performance.now(); obs.disconnect(); finish(true); } });
      obs.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['data-value'], characterData: true });
      const timer = setTimeout(() => { obs.disconnect(); finish(false); }, 5000);
      let t0 = null;
      for (let i = 0; i < positions.length; i += 1) {
        slider.value = String(positions[i]);
        t0 = performance.now(); // the last movement is the one that counts
        slider.dispatchEvent(new Event('input', { bubbles: true }));
        if (i < positions.length - 1) await new Promise((r) => setTimeout(r, 15));
      }
      const ok = await done;
      clearTimeout(timer);
      return { ok, ms: ok ? t1 - t0 : null };
    }, { positions: [60, 70, 80, 90, 100], want: expected });
    const runs = [];
    let warmup = null;
    for (let i = 0; i < RUNS + 1; i += 1) {
      if ((await bannerCount()) > 0) await page.locator(TID('whatif-reset-all')).click();
      const nominal = await waitRead((x) => settledPred(x) && x.root.factors === '0', 10000);
      if (!nominal.ok) throw new Error('the tab did not return to nominal before run ' + i);
      await sleep(150);
      const res = await timed();
      if (!res.ok) throw new Error(`run ${i}: the what-if top event ${expected} was not shown within 5 s`);
      if (i === 0) warmup = res.ms; else runs.push(res.ms);
      console.log(`INFO PERF-8 browser run ${i}${i === 0 ? ' (warm-up, discarded)' : ''}: ${res.ms.toFixed(1)} ms`);
      await waitRead(settledPred, 10000);
    }
    const data = {
      what: 'the What-if tab shows the what-if top event on the 301-event fixture with ten beta groups, measured from the last slider input event to the mutation of whatif-top-whatif data-value',
      fixture: 'fta_web/tests/fixtures/perf_ccf_301.json',
      protocol: `baseline computed; ${RUNS} runs of a slider burst (positions 60 to 100, 15 ms apart) on ${EVENT} ending at factor 10, after one discarded warm-up; Reset all between runs`,
      event: EVENT, factor: 10, boundMs: BOUND_MS, runs: RUNS,
      runsMs: runs, minMs: Math.min(...runs), medianMs: median(runs), maxMs: Math.max(...runs), warmupMs: warmup,
      firstAnswerAfterOpenMs: firstMs,
      browser: app.context.browser().version(), engine: L.BROWSER, platform: process.platform, node: process.version,
    };
    const dir = path.resolve(process.env.FTA_PERF_OUT_DIR || path.join(L.REPO, '.division', 'artifacts', 'perf'));
    fs.mkdirSync(dir, { recursive: true });
    // PERF-8.json is shared with test_perf.py (key "inProcess"): read it if it is there, set "browser", keep every other key
    const file = path.join(dir, 'PERF-8.json');
    let merged = {};
    if (fs.existsSync(file)) {
      try { merged = JSON.parse(fs.readFileSync(file, 'utf8')); } catch (_e) { merged = {}; }
      if (!merged || typeof merged !== 'object' || Array.isArray(merged)) merged = {};
    }
    merged.id = 'PERF-8';
    merged.browser = data;
    const ordered = {};
    for (const k of Object.keys(merged).sort()) ordered[k] = merged[k]; // top-level keys sorted like test_perf.py; nested blocks untouched
    fs.writeFileSync(file, JSON.stringify(ordered, null, 2) + '\n');
    L.check(`criterion8_perf8: the browser shows the what-if top event within ${BOUND_MS} ms of the last slider movement in every one of ${RUNS} runs (slowest ${data.maxMs.toFixed(1)} ms, median ${data.medianMs.toFixed(1)} ms; the "browser" block of PERF-8.json written)`, data.maxMs <= BOUND_MS, runs);
  });

  // Allowed: exactly the failures this section causes -- the stubbed 500 "Boom" and the aborted request of POST /api/whatif, and the
  // 409 STALE_REVISION of the stale-tab check -- and the browser's own resource lines for them (which carry no URL).
  const errs = app.errorsSince(0, [
    /^500 POST \/api\/whatif .*Boom/, /^409 POST \/api\/whatif .*STALE_REVISION/,
    /^Failed to load resource: the server responded with a status of (409|500) /, /^Failed to load resource: net::ERR_FAILED/,
  ]);
  L.check('no console errors in the whatif run (only the stubbed 500, the aborted request and the 409 STALE_REVISION of the stale-tab check excepted)', errs.length === 0, errs.slice(0, 5));
  await app.api('post', '/new', { force: true });
  for (const name of Object.values(names)) fs.rmSync(path.join(root, name), { force: true });
  await app.context.close();
}

L.runSection('whatif', main);
