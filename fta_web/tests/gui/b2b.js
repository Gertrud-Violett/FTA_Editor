// b2bgui/b2b.js -- GUI-vs-API comparators shared by the suite.
'use strict';
const L = require('./lib');

/** Read the diagram's DOT idMap for the current settings (same call the panel makes). */
async function dotIdMap(app) {
  return app.page.evaluate(async () => {
    const { api } = await import('/static/js/api.js');
    let s = {};
    try { s = JSON.parse(localStorage.getItem('fta.diagram.settings') || '{}'); } catch (_e) { /* */ }
    const style = s.style || 'symbols';
    const rankdir = s.rankdir || 'LR';
    const res = await api.get('/dot?style=' + style + '&rankdir=' + rankdir + '&sigFigs=3');
    return { idMap: res.idMap || {}, style, rankdir };
  });
}

function flatten(tree) {
  const out = [];
  const walk = (n) => { if (!n) return; out.push(n); for (const c of n.children || []) walk(c); };
  walk(tree);
  return out;
}

/**
 * Whether the root shows the headline instead of its own tree-walk value
 * (1.7.3): the headline is the MCUB and the summary's own caps did not cut it
 * short. The same rule as engine.root_headline and main.js rootHeadline().
 */
function rootShowsHeadline(summary, mode) {
  return mode !== 'ETA' && !!summary && summary.headlineMethod === 'mcub' && !summary.capped &&
    typeof summary.headline === 'number' && Number.isFinite(summary.headline);
}

/**
 * Parse the numbers a diagram label shows. compact: P / P_calc; symbols: Q on a
 * gate, q on an event (q and Q only where an event's two values differ).
 * On a root that shows the headline, `calc` is the headline, `mcub` is true
 * and `walk` is the tree-walk value printed beside it.
 */
function labelNumbers(texts) {
  const joined = texts.join(' | ');
  const out = {};
  out.mcub = /\(MCUB\)/.test(joined);
  const w = /tree walk\s+([^\s|]+)/.exec(joined);
  if (w) out.walk = w[1];
  let m = /P_calc:\s*([^\s|]+)/.exec(joined);
  if (m) out.calc = m[1];
  m = /(?:^|[\s|])P:\s*([^\s|]+)/.exec(joined);
  if (m) out.base = m[1];
  m = /(?:^|[\s|])Q=\s*([^\s|]+)/.exec(joined);
  if (m) out.calc = m[1];
  m = /(?:^|[\s|])q=\s*([^\s|]+)/.exec(joined);
  if (m) {
    out.base = m[1];
    // symbols: an event whose calculated value is its own shows "q=" alone
    // (the box used to say "q=0.01 | Q=0.01"). That one number is both.
    if (out.calc === undefined) out.calc = m[1];
  }
  return out;
}

/**
 * Compare everything always on screen (headline, details, diagram) with the
 * API. Returns a snapshot of the GUI values for dev-vs-exe comparison.
 */
async function compareCore(app, label, opts = {}) {
  const sf = await app.sf();
  await app.settle(opts.wait);
  await app.waitDiagram();
  const st = await app.api('get', '/state');
  const summary = await app.api('get', '/analysis/summary');
  const adv = await app.page.evaluate(() => window.ftaShell.advanced());
  const mode = st.metadata && st.metadata.mode;
  const nodes = flatten(st.tree);
  const byId = new Map(nodes.map((n) => [String(n.id), n]));
  const snap = { label, sf, headline: null, details: null, diagram: {} };
  const rootId = st.tree ? String(st.tree.id) : null;
  const rootMcub = rootShowsHeadline(summary, mode);

  // headline
  const head = await app.headline();
  snap.headline = head.value;
  const expectHead = mode === 'ETA' ? st.tree.calculatedProbability : summary.headline;
  L.check(`${label}: headline ${head.value} == API ${mode === 'ETA' ? 'root' : 'summary.headline'} @${sf}sf (${L.fmt(expectHead, sf)})`,
    L.sameAtSf(head.value, expectHead, sf), { head, headline: summary.headline, method: summary.headlineMethod });
  const wantBadge = adv && mode !== 'ETA' && summary.headlineMethod === 'mcub';
  L.check(`${label}: MCUB badge ${head.badge ? 'shown' : 'hidden'} (method=${summary.headlineMethod}, advanced=${adv})`,
    head.badge === wantBadge, { head, method: summary.headlineMethod });
  if (wantBadge) {
    L.check(`${label}: MCUB badge tooltip carries tree-walk ${L.fmt(summary.treeWalk, sf)}`,
      head.badgeTitle.includes(L.fmt(summary.treeWalk, sf)), head.badgeTitle);
  }

  // details
  const sel = await app.selectedId();
  const det = await app.details();
  if (sel && byId.has(String(sel))) {
    const n = byId.get(String(sel));
    const calc = n.calculatedProbability === undefined || n.calculatedProbability === null ? n.probability : n.calculatedProbability;
    snap.details = { id: det.id, calc: det.calc };
    L.check(`${label}: Details id ${det.id} == selection ${sel}`, det.id === String(sel), det);
    if (rootMcub && String(sel) === rootId) {
      // The root shows the headline, labelled, with its tree-walk value.
      snap.details.note = det.calcNote;
      L.check(`${label}: Details (root) ${det.calc} == API summary.headline ${L.fmt(summary.headline, sf)}`, L.sameAtSf(det.calc, summary.headline, sf), { det: det.calc, api: summary.headline });
      L.check(`${label}: Details (root) says MCUB and tree walk ${L.fmt(calc, sf)}`, /MCUB/.test(det.calcNote) && det.calcNote.includes(L.fmt(calc, sf)), det.calcNote);
    } else {
      L.check(`${label}: Details calculated ${det.calc} == API ${L.fmt(calc, sf)} (${sel})`, L.sameAtSf(det.calc, calc, sf), { det: det.calc, api: calc });
      L.check(`${label}: Details has no MCUB note off the top event (${sel})`, det.calcNote === '', det.calcNote);
    }
    const zero = (st.zeroNodes || []).map(String).includes(String(sel));
    L.check(`${label}: Details zero flag == zeroNodes (${zero})`, det.zero === zero, { det: det.zero, zero });
  }

  // diagram
  const dn = await app.diagramNodes();
  if (!opts.skipDiagram) {
    L.check(`${label}: diagram rendered`, Array.isArray(dn) && dn.length > 0, dn && dn.length);
    const { idMap } = await dotIdMap(app);
    const hideZero = await app.page.evaluate(() => document.documentElement.dataset.hideZero === '1');
    const seen = new Set();
    const bad = [];
    for (const g of dn || []) {
      const id = idMap[g.title];
      if (!id) continue;
      if (/\bfta-(gate|event)\b/.test(g.cls) && !/fta-event-conditioning/.test(g.cls)) continue; // symbol node
      const n = byId.get(String(id));
      if (!n) { bad.push({ title: g.title, why: 'no such node' }); continue; }
      seen.add(String(id));
      const nums = labelNumbers(g.texts);
      if (nums.calc === undefined) { bad.push({ id, why: 'no calc number', texts: g.texts }); continue; }
      if (rootMcub && String(id) === rootId) {
        // The top box: the headline, marked MCUB, and the root's tree walk.
        if (!nums.mcub) bad.push({ id, why: 'root not marked MCUB', texts: g.texts });
        if (nums.calc !== L.fmt(summary.headline, sf)) bad.push({ id, calc: nums.calc, headline: L.fmt(summary.headline, sf) });
        if (nums.walk !== L.fmt(n.calculatedProbability, sf)) bad.push({ id, walk: nums.walk, api: L.fmt(n.calculatedProbability, sf) });
      } else {
        // Every other node (and the root of a tree-walk headline): its own value.
        if (nums.mcub || nums.walk !== undefined) bad.push({ id, why: 'MCUB mark off the top event', texts: g.texts });
        if (nums.calc !== L.fmt(n.calculatedProbability, sf)) bad.push({ id, calc: nums.calc, api: L.fmt(n.calculatedProbability, sf) });
      }
      if (nums.base !== undefined && nums.base !== L.fmt(n.probability, sf)) bad.push({ id, base: nums.base, api: L.fmt(n.probability, sf) });
      snap.diagram[id] = nums;
    }
    const zeros = new Set((st.zeroNodes || []).map(String));
    // Hide Zero removes a zero node together with its subtree (tree and diagram alike)
    if (hideZero) {
      const addSub = (n) => { zeros.add(String(n.id)); for (const c of n.children || []) addSub(c); };
      for (const n of nodes) if ((st.zeroNodes || []).map(String).includes(String(n.id))) addSub(n);
    }
    const missing = nodes.map((n) => String(n.id)).filter((id) => !seen.has(id) && !(hideZero && zeros.has(id)));
    L.check(`${label}: diagram numbers == API for ${seen.size} nodes @${sf}sf (root: ${rootMcub ? 'headline, MCUB' : 'tree walk'})`, bad.length === 0, bad.slice(0, 6));
    const caption = await app.page.evaluate(() => {
      const c = document.querySelector('#diagram-root .diagram__caption');
      return c ? { shown: !c.hidden && c.offsetParent !== null, text: c.textContent } : null;
    });
    const rootDrawn = rootId !== null && seen.has(rootId);
    L.check(`${label}: diagram caption ${rootMcub && rootDrawn ? 'explains the MCUB top box' : 'hidden'}`,
      !!caption && caption.shown === (rootMcub && rootDrawn) && (!caption.shown || /MCUB/.test(caption.text)), caption);
    L.check(`${label}: every node drawn in the diagram`, missing.length === 0, missing);
    const selG = (dn || []).filter((g) => g.selected).map((g) => idMap[g.title]);
    if (sel) L.check(`${label}: diagram selection == store selection`, selG.includes(String(sel)) && new Set(selG).size === 1, { selG, sel });
  }
  return { snap, st, summary };
}

module.exports = { compareCore, dotIdMap, flatten, labelNumbers, rootShowsHeadline };
