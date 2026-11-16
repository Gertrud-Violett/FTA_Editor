// F2 acceptance (T0 part C): CCF groups, beta factor, in a real browser with
// real mouse and keyboard input. Criteria 17-23 and 24 (text) of the F2 brief;
// the steps are numbered as in DESIGN.md section 14 and every selector is the
// one of section 12. Written before the feature exists: every check in here
// fails while the CCF tab, the badges and the headline phrases are missing.
//   node s_ccf.js <url> <label> <root>
//
// The tree is built here (a document written into the sandbox root and opened
// through the API); the group "Relief valves" is made by the API, every other
// group by the GUI. No AI provider is called.
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

// ---- the document -----------------------------------------------------------------
function leaf(id, name, probability) {
  return { id, name, type: 'Event', probability, logicGate: 'OR', notes: '', links: [], children: [] };
}
function gate(id, name, logicGate, children) {
  return Object.assign(leaf(id, name, 1.0), { type: 'Gate', logicGate, children });
}

/**
 * Loss of cooling (OR): Pumps fail (AND: Pump A, Pump B), Valves fail (AND:
 * Valve C 1e-3, Valve D 2e-3), Sensors fail (AND: Sensor E, Sensor F), Pump C.
 * Valve D differs from Valve C, so a group of the two is not applied.
 */
function documentText(mode) {
  const tree = Object.assign(leaf('root', 'Loss of cooling', 1.0), {
    type: 'Root',
    children: [
      gate('P', 'Pumps fail', 'AND', [leaf('A', 'Pump A', 1e-3), leaf('B', 'Pump B', 1e-3)]),
      gate('V', 'Valves fail', 'AND', [leaf('C', 'Valve C', 1e-3), leaf('D', 'Valve D', 2e-3)]),
      gate('S', 'Sensors fail', 'AND', [leaf('E', 'Sensor E', 1e-3), leaf('F', 'Sensor F', 1e-3)]),
      leaf('X', 'Pump C', 1e-3),
    ],
  });
  return JSON.stringify({ title: 'CCF GUI', date: '2026-10-26', mode: mode || 'FTA', tree }, null, 2);
}

/** Root OR of 2,100 leaves (q 1e-4), one group of the first two: more cut sets than the summary cap. */
function capDocumentText() {
  const kids = [];
  for (let i = 0; i < 2100; i += 1) kids.push(leaf('L' + i, 'Leaf ' + i, 1e-4));
  const tree = Object.assign(leaf('root', 'Capped top', 1.0), { type: 'Root', children: kids });
  return JSON.stringify({
    title: 'CCF cap', date: '2026-10-26', mode: 'FTA', fileFormatVersion: 2, tree,
    analysis: {
      ccfGroups: [{ id: 'g1', name: 'Cap pair', model: 'beta', beta: 0.1, alpha: null, testing: null, members: ['L0', 'L1'], source: 'cap test' }],
    },
  }, null, 1);
}

// ---- texts (DESIGN section 13.1, flat catalog) ----------------------------------
const T = {
  en: {
    tab: 'CCF groups',
    cols: ['Name', 'Model', 'Parameters', 'Members', 'Source', 'Status'],
    model: 'Beta factor',
    applied: 'Applied',
    notApplied: (reason) => 'Not applied: ' + reason,
    eta: 'Not applied: ETA mode',
    betaLabel: 'β (dimensionless, 0 to 1)',
    betaErr: 'β must be a number from 0 to 1 (for example 0.1 or 10%).',
    badgeOff: (name) => 'CCF: ' + name + ' (off)',
    etaTab: 'CCF groups are not applied in ETA (event tree) mode. They stay in the file.',
    includes1: 'MCUB, includes CCF (1 group)',
    includes2: 'MCUB, includes CCF (2 groups)',
    notApplied1: '1 CCF group not applied',
    notApplied2: '2 CCF groups not applied',
    incomplete: 'incomplete, CCF not included',
    walk: (reason) => 'tree walk, without CCF; cut sets cut short (' + reason + ')',
    reasons: { time: 'time', error: 'error', cap: 'summary cap' },
    na: 'n/a (CCF)',
    mcubNote: '(MCUB, includes CCF)',
    needsAdvanced: 'Switch on Advanced in the top bar to open the CCF groups tab.',
    note: 'Check CCF results with a qualified engineer before use.',
    assume: {
      model: 'Beta-factor model: Q_1 = (1 − β)·Q_t is the independent part of each member and Q_m = β·Q_t is one event failing all m members (NUREG/CR-4780 Vol. 2, Table C-1 p. C-5 and Eq. C.10-C.13 p. C-6; NUREG/CR-5485, Eq. 5.11-5.13 p. 42).',
      qt: 'A member\'s probability is its total failure probability Q_t at mission time.',
      beta: 'Beta factor: the CCF event fails all members together.',
      split: 'The split is applied to Q_t; splitting λ instead agrees only to first order in λT (NASA/SP-2011-3421, p. D-20).',
      headline: 'The headline is the min-cut upper bound; the formulas in the sources use the rare-event approximation.',
      sampling: 'β and α are not sampled in Monte Carlo.',
    },
  },
  ja: {
    tab: 'CCF グループ',
    cols: ['名前', 'モデル', 'パラメータ', 'メンバー', '出典', '状態'],
    model: 'ベータファクター',
    applied: '適用中',
    notApplied: (reason) => '未適用: ' + reason,
    betaLabel: 'β（無次元、0 から 1）',
    betaErr: 'β は 0 から 1 までの数値で入力してください（例: 0.1 または 10%）。',
    includes1: 'MCUB、CCF を含む（1 グループ）',
    notApplied1: 'CCF グループ 1 件が未適用',
    incomplete: '不完全、CCF は含まれていません',
    walk: (reason) => 'ツリー計算（CCF なし）、カットセットが途中で打ち切られました（' + reason + '）',
    reasons: { time: '時間', error: 'エラー', cap: 'サマリー上限' },
    needsAdvanced: 'CCF グループタブを開くには、上部バーの「詳細機能」をオンにしてください。',
    note: 'CCF の結果は、使用前に有資格の技術者が確認してください。',
    assume: {
      model: 'ベータファクターモデル: Q_1 = (1 − β)·Q_t が各メンバーの独立部分、Q_m = β·Q_t が全 m メンバーを同時に故障させる 1 つの事象です（NUREG/CR-4780 Vol. 2 表 C-1 p. C-5、式 C.10-C.13 p. C-6、NUREG/CR-5485 式 5.11-5.13 p. 42）。',
      qt: 'メンバーの確率は、ミッション時間における全故障確率 Q_t です。',
      beta: 'ベータファクター: CCF 事象は全メンバーを同時に故障させます。',
      split: '分割は Q_t に適用します。λ を分割した場合は、λT の一次の範囲でのみ一致します（NASA/SP-2011-3421 p. D-20）。',
      headline: '頂上事象の値は最小カット上限（MCUB）です。出典の式はレアイベント近似を用いています。',
      sampling: 'モンテカルロでは β と α はサンプリングしません。',
    },
  },
};

const norm = (s) => String(s === null || s === undefined ? '' : s).replace(/[ \s]+/g, ' ').trim();

async function run(url, label, root) {
  L.setSection('ccf[' + label + ']');
  const file = 'ccf_gui_' + label + '.json';
  const capFile = 'ccf_cap_' + label + '.json';
  const etaFile = 'ccf_gui_eta_' + label + '.json';
  fs.writeFileSync(path.join(root, file), documentText('FTA'));

  const app = await L.openApp(url, { viewport: { width: 1600, height: 1000 }, prefs: { 'fta.advanced': '1' } });
  const { page } = app;
  page.setDefaultTimeout(5000);
  const patches = [];
  let rows = [];
  let feedId = null;
  let reliefId = null;
  let feedBase = '';
  let nodes = null;
  let h = null;
  let sf = 3;
  /** One block of the run: an exception (UI missing) is one FAIL and the run goes on. */
  const part = async (name, fn, cleanup) => {
    try { await fn(); } catch (e) { L.check(name + ': did not complete', false, String((e && e.message) || e).split(String.fromCharCode(10))[0].slice(0, 300)); }
    if (cleanup) { try { await cleanup(); } catch (_e) { /* best effort */ } }
  };
  page.on('request', (r) => { if (r.method() === 'PATCH' && r.url().includes('/api/ccf/groups')) patches.push(r.url()); });

  // ---- helpers -----------------------------------------------------------------------
  const waitFor = async (fn, timeout) => {
    const t0 = Date.now();
    for (;;) {
      let v = false;
      try { v = await fn(); } catch (_e) { v = false; }
      if (v) return true;
      if (Date.now() - t0 > (timeout || 8000)) return false;
      await page.waitForTimeout(100);
    }
  };
  const groups = async () => ((await app.api('get', '/ccf/groups')).groups) || [];
  const byName = async (name) => (await groups()).find((g) => g.name === name);
  const gidOf = async (name) => { const g = await byName(name); return g ? g.id : null; };
  const rev = async () => (await app.api('get', '/revision')).revision;
  const brief = (gs) => JSON.stringify((gs || []).map((g) => ({ id: g.id, name: g.name, beta: g.beta, source: g.source, members: g.members })));
  const row = (id) => page.locator('#tree-root li.fta-tree-item[data-id="' + id + '"] > .fta-tree-row');
  const groupRow = (gid) => page.locator('#tabpanel-ccf [data-role="groups"] tbody tr[data-id="' + gid + '"]');
  const editor = page.locator('#tabpanel-ccf [data-section="editor"]');
  const toasts = () => page.evaluate(() => Array.from(document.querySelectorAll('#toasts .toast__body')).map((t) => t.textContent));
  const reload = async () => {
    await page.reload();
    await L.waitBoot(page);
    await app.waitDiagram();
    await page.waitForTimeout(500);
  };
  const openDoc = async (name) => {
    await app.api('post', '/new', { force: true });
    const opened = await app.api('post', '/file/open', { path: path.join(root, name), force: true });
    if (opened.__error) throw new Error('could not open ' + name + ': ' + opened.status + ' ' + opened.code);
    await reload();
  };
  const readRows = () => page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-ccf [data-role="groups"] tbody tr[data-id]')).map((tr) => {
    const o = { id: tr.dataset.id, selected: tr.classList.contains('is-selected') };
    for (const td of tr.querySelectorAll('td[data-col]')) o[td.dataset.col] = td.textContent.replace(/[ \s]+/g, ' ').trim();
    const st = tr.querySelector('[data-status]');
    o.kind = st ? st.dataset.status : null;
    const rs = tr.querySelector('.ccf-status__reason');
    o.reason = rs ? rs.textContent.replace(/[ \s]+/g, ' ').trim() : null;
    return o;
  }));
  const readHeads = () => page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-ccf [data-role="groups"] thead th')).map((th) => th.textContent.replace(/[ \s]+/g, ' ').trim()));
  const readHeadline = () => page.evaluate(() => {
    const q = (s) => document.querySelector(s);
    const vis = (e) => Boolean(e) && !e.hidden && e.offsetParent !== null;
    const t = (s) => { const e = q(s); return e ? e.textContent.replace(/[ \s]+/g, ' ').trim() : null; };
    return {
      ccf: t('#headline-ccf'), ccfVisible: vis(q('#headline-ccf')),
      note: t('#headline-ccf-note'), noteVisible: vis(q('#headline-ccf-note')),
      walkLabel: t('#headline-walk .headline__walk-label'), walkValue: t('#headline-walk .headline__walk-value'),
      walkVisible: vis(q('#headline-walk')),
      value: t('#headline-value'), valueTitle: q('#headline-value') ? q('#headline-value').getAttribute('title') : null,
      badgeVisible: vis(q('#headline-badge')),
    };
  });
  const readCcfDetails = () => page.evaluate(() => {
    const r = document.querySelector('#details-root .fta-details-ccf');
    if (!r) return null;
    const o = { shown: !r.hidden && r.offsetParent !== null, text: r.textContent.replace(/[ \s]+/g, ' ').trim() };
    r.querySelectorAll('[data-ccf]').forEach((e) => { o[e.dataset.ccf] = e.textContent.replace(/[ \s]+/g, ' ').trim(); });
    return o;
  });
  const treeBadges = () => page.evaluate(() => Array.from(document.querySelectorAll('#tree-root li.fta-tree-item[data-id] .fta-tree-ccf[data-group]')).map((b) => ({
    id: b.closest('li.fta-tree-item').dataset.id, group: b.dataset.group, text: b.textContent.replace(/[ \s]+/g, ' ').trim(), off: b.classList.contains('is-off'),
  })));
  const selectLeaves = async (ids) => {
    await row(ids[0]).click();
    for (const id of ids.slice(1)) await row(id).click({ modifiers: ['Control'] });
    await page.waitForTimeout(200);
  };
  const openCcfTab = async () => {
    await app.clickTab('ccf');
    await page.waitForSelector('#tabpanel-ccf .anl-ccf[data-tab="ccf"]', { timeout: 8000 });
    await page.waitForTimeout(300);
  };
  const selectGroupRow = async (gid) => {
    await groupRow(gid).click();
    await page.waitForSelector('#tabpanel-ccf [data-section="editor"] input[data-field="name"]', { timeout: 5000 });
    await page.waitForTimeout(150);
  };
  const commit = async (field, value) => {
    const input = editor.locator('input[data-field="' + field + '"]');
    await input.click();
    await page.keyboard.press('Control+A');
    await page.keyboard.type(String(value), { delay: 3 });
    await page.keyboard.press('Enter');
  };
  const undoClick = async () => { await page.locator('#btn-undo').click(); await page.waitForTimeout(400); };
  /** Fill the open draft: name, beta, source (typed, nothing committed until Create). */
  const fillDraft = async (name, beta, source) => {
    const nameInput = editor.locator('input[data-field="name"]');
    await nameInput.click();
    await page.keyboard.press('Control+A');
    await page.keyboard.type(name, { delay: 3 });
    const betaInput = editor.locator('input[data-field="beta"]');
    await betaInput.click();
    await page.keyboard.type(beta, { delay: 3 });
    if (source) {
      const src = editor.locator('input[data-field="source"]');
      await src.click();
      await page.keyboard.type(source, { delay: 3 });
    }
  };

  const errBelow = () => page.evaluate(() => {
    const input = document.querySelector('#tabpanel-ccf [data-section="editor"] input[data-field="beta"]');
    const p = document.querySelector('#tabpanel-ccf [data-section="editor"] p[data-error="beta"]');
    if (!input || !p) return null;
    const a = input.getBoundingClientRect();
    const b = p.getBoundingClientRect();
    const shown = !p.hidden && b.height > 0 && getComputedStyle(p).visibility !== 'hidden';
    return { text: p.textContent.replace(/[ \s]+/g, ' ').trim(), shown, below: b.top >= a.bottom - 2 && b.top - a.bottom < 80 && b.left < a.right && b.right > a.left, invalid: input.getAttribute('aria-invalid') === 'true', value: input.value };
  });
  const readAssume = () => page.evaluate(() => {
    const o = {};
    document.querySelectorAll('#tabpanel-ccf [data-section="assumptions"] li[data-assumption]').forEach((li) => { o[li.dataset.assumption] = li.textContent.replace(/[ \s]+/g, ' ').trim(); });
    const n = document.querySelector('#tabpanel-ccf [data-section="assumptions"] [data-role="ccf-note"], #tabpanel-ccf [data-role="ccf-note"]');
    o.__note = n ? n.textContent.replace(/[ \s]+/g, ' ').trim() : null;
    return o;
  });
  const checkAssume = async (lang) => {
    const got = await readAssume();
    for (const key of ['model', 'qt', 'beta', 'split', 'headline', 'sampling']) {
      L.check('step 8: assumption "' + key + '" reads as the catalog (' + lang + ')', got[key] === T[lang].assume[key], { got: got[key], want: T[lang].assume[key] });
    }
    L.check('step 8: the FN-67 note reads "' + T[lang].note + '" (' + lang + ')', got.__note === T[lang].note, got.__note);
  };
  // ---- fixture state: the document, and the group "Relief valves" (by API) --------------
  await openDoc(file);
  const created = await app.api('post', '/ccf/groups', { name: 'Relief valves', model: 'beta', beta: 0.2, members: ['C', 'D'], source: '' });
  L.check('setup: API created the group "Relief valves"', !created.__error && created.group && created.group.name === 'Relief valves', created.__error ? created : undefined);
  await reload();
  reliefId = await gidOf('Relief valves');
  L.check('setup: the group has an id', Boolean(reliefId), reliefId);
  sf = await app.sf();

  // ---- step 1 (17): columns and both statuses ---------------------------------------
  await part('step 1', async () => {
    await app.clickTab('quant'); // a neighbour tab first, so the CCF tab is mounted lazily from cold
    const tabBtn = await page.evaluate(() => { const b = document.getElementById('tab-ccf'); return b ? { text: b.textContent.trim(), shown: !b.hidden && b.offsetParent !== null, unavailable: b.classList.contains('is-unavailable') } : null; });
    L.check('step 1: the "CCF groups" tab exists in Advanced mode, not greyed', Boolean(tabBtn) && tabBtn.text === T.en.tab && tabBtn.shown && !tabBtn.unavailable, tabBtn);
    const order = await page.evaluate(() => Array.from(document.querySelectorAll('#bottom-tabs .tabstrip__tab')).filter((b) => !b.hidden).map((b) => b.id));
    const iq = order.indexOf('tab-quant');
    L.check('step 1: the tab sits between Quantification and Cut Sets', iq >= 0 && order[iq + 1] === 'tab-ccf' && order[iq + 2] === 'tab-cutsets', order);
    await openCcfTab();
    const heads = await readHeads();
    L.check('step 1: columns are Name, Model, Parameters, Members, Source, Status', JSON.stringify(heads) === JSON.stringify(T.en.cols), heads);
    rows = await readRows();
    const rel = rows.find((r) => r.id === reliefId);
    L.check('step 1: Relief valves row: name, model, parameters, members, source', Boolean(rel) && rel.name === 'Relief valves' && rel.model === T.en.model && rel.params === 'β = 0.2' && rel.members === 'Valve C, Valve D' && rel.source === '—', rel);
    const relApi = await byName('Relief valves');
    L.check('step 1: the API says not applied, reason in en and ja', relApi && relApi.status && relApi.status.applied === false && relApi.status.reason && relApi.status.reason.en === '"Valve D" differs from "Valve C"' && typeof relApi.status.reason.ja === 'string' && relApi.status.reason.ja.length > 0, relApi && relApi.status);
    L.check('step 1: status of Relief valves reads Not applied: "Valve D" differs from "Valve C"',
      Boolean(rel) && rel.kind === 'not-applied' && rel.status === 'Not applied: "Valve D" differs from "Valve C"' && rel.reason === '"Valve D" differs from "Valve C"', rel);

  });

  // ---- step 2 (18): create from the selection, then each edit is ONE undo step ----------
  await part('step 2', async () => {
    await selectLeaves(['A', 'B']);
    const newBtn = page.locator('#tabpanel-ccf [data-role="new"]');
    const newState = await newBtn.evaluate((b) => ({ disabled: b.disabled || b.getAttribute('aria-disabled') === 'true' }));
    L.check('step 2: "New group from selection" is enabled with two basic events selected', newState.disabled === false, newState);
    const rev0 = await rev();
    await newBtn.click();
    await editor.locator('input[data-field="name"]').waitFor({ state: 'visible', timeout: 5000 });
    const draft = await page.evaluate(() => {
      const ed = document.querySelector('#tabpanel-ccf [data-section="editor"]');
      const create = ed.querySelector('[data-role="create"]');
      return {
        name: ed.querySelector('input[data-field="name"]').value,
        beta: ed.querySelector('input[data-field="beta"]').value,
        members: Array.from(ed.querySelectorAll('[data-role="members"] li[data-member]')).map((li) => li.dataset.member),
        createDisabled: Boolean(create) && (create.disabled || create.getAttribute('aria-disabled') === 'true'),
      };
  });
  L.check('step 2: the draft is prefilled (name, members A and B) with an empty beta and Create disabled', draft.name !== '' && draft.beta === '' && JSON.stringify(draft.members) === '["A","B"]' && draft.createDisabled === true, draft);
  L.check('step 2: opening the draft changes nothing on the server', (await rev()) === rev0 && (await groups()).length === 1, { rev0 });
  await app.shot('ccf_editor_draft');
  await fillDraft('Feed pumps', '0.1', 'test');
  await page.waitForTimeout(200);
  const createReady = await editor.locator('[data-role="create"]').evaluate((b) => !(b.disabled || b.getAttribute('aria-disabled') === 'true'));
  L.check('step 2: Create is enabled once the name and a valid beta are in', createReady);
  await editor.locator('[data-role="create"]').click();
  const gotFeed = await waitFor(async () => Boolean(await byName('Feed pumps')));
  const feed = await byName('Feed pumps');
  feedId = feed ? feed.id : null;
  L.check('step 2: Create makes the group (name, beta 0.1, members A and B, source)', gotFeed && feed.beta === 0.1 && JSON.stringify(feed.members) === '["A","B"]' && feed.source === 'test' && feed.model === 'beta', feed);
  L.check('step 2: creating is one revision', (await rev()) === rev0 + 1, { rev0, now: await rev() });
  await undoClick();
  L.check('step 2: one Undo removes the group', await waitFor(async () => !(await byName('Feed pumps'))) && (await groups()).length === 1);
  await page.locator('#btn-redo').click();
  L.check('step 2: Redo brings it back', await waitFor(async () => Boolean(await byName('Feed pumps'))));
  feedBase = brief(await groups());

  // each edit is exactly ONE undo step (revision +1; one Undo restores; checked against the API)
  const oneStep = async (what, action, post) => {
    const before = brief(await groups());
    const r0 = await rev();
    await action();
    const moved = await waitFor(async () => (await rev()) > r0);
    await page.waitForTimeout(300);
    const r1 = await rev();
    const after = await groups();
    L.check('step 2: ' + what + ' changes the group', moved && post(after), { after: brief(after) });
    L.check('step 2: ' + what + ' is one revision (+1)', r1 === r0 + 1, { r0, r1 });
    await undoClick();
    const restored = await waitFor(async () => brief(await groups()) === before);
    L.check('step 2: one Undo undoes ' + what + ' completely', restored, { now: brief(await groups()), before });
    return restored;
  };
  const feedOf = (gs) => gs.find((g) => g.id === feedId) || {};
  await openCcfTab();
  await selectGroupRow(feedId);
  await oneStep('editing the name (Enter)', () => commit('name', 'Feed pumps 2'), (gs) => feedOf(gs).name === 'Feed pumps 2');
  await selectGroupRow(feedId);
  await oneStep('editing beta to 0.2', () => commit('beta', '0.2'), (gs) => feedOf(gs).beta === 0.2);
  await selectGroupRow(feedId);
  await oneStep('editing the source', () => commit('source', 'handbook p. 5'), (gs) => feedOf(gs).source === 'handbook p. 5');
  await selectGroupRow(feedId);
  await oneStep('adding a member (Add selected events)', async () => {
    await row('X').click();
    await page.locator('#tabpanel-ccf [data-role="add-selected"]').click();
  }, (gs) => JSON.stringify(feedOf(gs).members) === '["A","B","X"]');
  await selectGroupRow(feedId);
  await oneStep('removing a member (chip button)', async () => {
    await editor.locator('[data-role="members"] li[data-member="B"] button[data-role="remove-member"]').click();
  }, (gs) => JSON.stringify(feedOf(gs).members) === '["A"]');
  await selectGroupRow(feedId);
  await oneStep('deleting the group', async () => {
    await editor.locator('[data-role="delete"]').click();
  }, (gs) => !gs.some((g) => g.id === feedId));
  L.check('step 2: the group is back to its first state after the six steps', brief(await groups()) === feedBase, { now: brief(await groups()) });

  });

  // ---- step 1 again, with both statuses on screen -----------------------------------
  await part('step 1 (both statuses)', async () => {
    await openCcfTab();
    rows = await readRows();
    const feedRow = rows.find((r) => r.id === feedId);
    L.check('step 1: Feed pumps reads Applied, Relief valves reads Not applied (both statuses)',
      Boolean(feedRow) && feedRow.kind === 'applied' && feedRow.status === T.en.applied && rows.some((r) => r.id === reliefId && r.kind === 'not-applied'), rows);
    L.check('step 1: Feed pumps row: parameters β = 0.1, members Pump A, Pump B, source test', Boolean(feedRow) && feedRow.params === 'β = 0.1' && feedRow.members === 'Pump A, Pump B' && feedRow.source === 'test', feedRow);
    await app.shot('ccf_tab_advanced');

  });

  // ---- step 3 (19): badges, highlight ------------------------------------------------
  await part('step 3', async () => {
    await app.settle(600);
    const badges = await treeBadges();
    const feedBadges = badges.filter((b) => b.group === feedId);
    L.check('step 3: two tree badges "CCF: Feed pumps" (on Pump A and Pump B)', feedBadges.length === 2 && feedBadges.every((b) => b.text === 'CCF: Feed pumps' && !b.off) && JSON.stringify(feedBadges.map((b) => b.id).sort()) === '["A","B"]', badges);
    const offBadges = badges.filter((b) => b.group === reliefId);
    L.check('step 3: the not-applied group gets "off" badges on Valve C and Valve D', offBadges.length === 2 && offBadges.every((b) => b.off && b.text === T.en.badgeOff('Relief valves')), badges);
    await app.waitDiagram();
    nodes = await app.diagramNodes();
    const dBadge = (nodes || []).filter((n) => n.texts.join(' ').includes('CCF: Feed pumps'));
    L.check('step 3: the diagram shows the badge "CCF: Feed pumps" on 2 boxes', dBadge.length === 2, (nodes || []).map((n) => n.texts.join(' | ')).slice(0, 8));
    await app.clickTab('cutsets');
    await page.waitForSelector('#tabpanel-cutsets tbody tr[data-rank]', { timeout: 15000 });
    await app.settle(400);
    const evs = await page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-cutsets tr[data-rank] .anl-event[data-ccf-group][data-ccf-role]')).map((e) => ({ group: e.dataset.ccfGroup, role: e.dataset.ccfRole, text: e.textContent.replace(/[ \s]+/g, ' ').trim() })));
    const ccfEv = evs.find((e) => e.role === 'event');
    L.check('step 3: the cut set row carries the CCF event labelled "CCF: Feed pumps"', Boolean(ccfEv) && ccfEv.group === feedId && ccfEv.text === 'CCF: Feed pumps', evs);
    L.check('step 3: members are labelled "(independent part)"', evs.some((e) => e.role === 'independent' && e.text === 'Pump A (independent part)') && evs.some((e) => e.role === 'independent' && e.text === 'Pump B (independent part)'), evs);
    await page.locator('#tabpanel-cutsets tr[data-rank]').filter({ has: page.locator('.anl-event[data-ccf-role="event"]') }).first().click();
    await page.waitForTimeout(500);
    const hl = await page.evaluate(() => ({
      tree: Array.from(document.querySelectorAll('#tree-root .fta-tree-row.is-highlighted')).map((r) => r.closest('li.fta-tree-item').dataset.id).sort(),
      // PM fix T0R1 (2026-10-28): the symbols style draws a box <sid> and an event symbol <sid>__event per leaf,
      // and the 1.8.1 highlight marks both; count the boxes and allow only their own event symbols besides them.
      diagram: Array.from(document.querySelectorAll('#diagram-root g.node.is-highlighted')).map((g) => ({
        title: ((g.querySelector('title') || {}).textContent || '').trim(),
        texts: Array.from(g.querySelectorAll('text')).map((t) => t.textContent.replace(/ /g, ' ').trim()).filter(Boolean).join(' '),
      })),
    }));
    L.check('step 3: the CCF cut set highlights both members in the tree (2 rows: A and B)', hl.tree.length === 2 && JSON.stringify(hl.tree) === '["A","B"]', hl);
    const hlBoxes = hl.diagram.filter((n) => !/__(event|gate)$/.test(n.title));
    const hlBoxTitles = new Set(hlBoxes.map((n) => n.title));
    L.check('step 3: ... and 2 boxes in the diagram (Pump A and Pump B; any other highlighted node is the event symbol of one of them)',
      hlBoxes.length === 2 && hlBoxes.some((n) => n.texts.includes('Pump A')) && hlBoxes.some((n) => n.texts.includes('Pump B'))
        && hl.diagram.every((n) => hlBoxTitles.has(n.title) || (n.title.endsWith('__event') && hlBoxTitles.has(n.title.slice(0, -'__event'.length)))), hl);
    await app.shot('ccf_highlight');

  });

  // ---- step 4 (20): headline, complete ---------------------------------------------
  await part('step 4 (complete)', async () => {
    await waitFor(async () => { h = await readHeadline(); return h.ccf === T.en.includes1; }, 10000);
    L.check('step 4: with one applied group the headline reads "MCUB, includes CCF (1 group)"', h.ccf === T.en.includes1 && h.ccfVisible, h);
    L.check('step 4: ... and "1 CCF group not applied" beside it', h.note === T.en.notApplied1 && h.noteVisible, h);
    const sumA = await app.api('get', '/analysis/summary');
    L.check('step 4: API summary: headlineMethod mcub, ccfIncomplete false', sumA.headlineMethod === 'mcub' && sumA.ccfIncomplete === false, { m: sumA.headlineMethod, i: sumA.ccfIncomplete });
    L.check('step 4: the headline number is the MCUB of the API', sumA.headlineMethod === 'mcub' && h.ccf === T.en.includes1 && h.value === L.fmt(sumA.headline, sf), { h: h.value, api: L.fmt(sumA.headline, sf), m: sumA.headlineMethod });
    const made = await app.api('post', '/ccf/groups', { name: 'Sensor pair', model: 'beta', beta: 0.1, members: ['E', 'F'], source: '' });
    L.check('step 4: a second applied group (Sensor E, Sensor F, beta 0.1) is made by the API', !made.__error, made.__error ? made : undefined);
    await reload();
    await waitFor(async () => { h = await readHeadline(); return h.ccf === T.en.includes2; }, 10000);
    L.check('step 4: with two applied groups the headline reads "MCUB, includes CCF (2 groups)"', h.ccf === T.en.includes2 && h.ccfVisible, h);
    L.check('step 4: the unlabelled MCUB badge is hidden and the value has no title', h.ccf === T.en.includes2 && h.badgeVisible === false && !h.valueTitle, h);
    L.check('step 4: "1 CCF group not applied" stays (Relief valves)', h.note === T.en.notApplied1, h);
    await app.shot('ccf_headline_complete');
    await page.setViewportSize({ width: 900, height: 1000 });
    await page.waitForTimeout(500);
    const narrow = await page.evaluate(() => {
      const el = document.getElementById('headline');
      const r = el.getBoundingClientRect();
      return { right: Math.round(r.right), width: Math.round(r.width), clipped: el.scrollWidth > el.clientWidth + 1, height: Math.round(r.height), ccf: (document.getElementById('headline-ccf') || { textContent: '' }).textContent.trim() };
  });
  L.check('step 4: in a 900 px window the headline wraps and is not clipped', narrow.right <= 900 && narrow.clipped === false && narrow.ccf === T.en.includes2, narrow);
  await app.shot('ccf_headline_narrow');
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.waitForTimeout(300);
  // the second group leaves again, so the rest of the run has the two groups of the design
  const sensorId = await gidOf('Sensor pair');
  const del = await app.api('del', '/ccf/groups/' + sensorId);
  L.check('step 4: the second group is removed again (API)', !del.__error, del.__error ? del : undefined);
  await reload();

  });

  // ---- step 5 (21): Details of Pump A ---------------------------------------------------
  await part('step 5', async () => {
    await app.clickTab('details');
    await app.selectTreeNode('A');
    await waitFor(async () => { const d = await readCcfDetails(); return d && d.shown && d.qt; }, 8000);
    const dA = await readCcfDetails();
    L.check('step 5: Details of Pump A shows the CCF group row', Boolean(dA) && dA.shown && dA.text.includes('CCF group: Feed pumps'), dA);
    L.check('step 5: Q_t reads 1e-3 (' + L.fmt(1e-3, sf) + ')', Boolean(dA) && dA.qt === L.fmt(1e-3, sf), dA);
    L.check('step 5: the independent part reads 9e-4 (' + L.fmt(9e-4, sf) + ') beside it', Boolean(dA) && dA.independent === L.fmt(9e-4, sf), dA);
    L.check('step 5: the CCF event reads 1e-4 (' + L.fmt(1e-4, sf) + ')', Boolean(dA) && dA.event === L.fmt(1e-4, sf), dA);
    await app.shot('ccf_details_A');
    await app.selectTreeNode('C');
    await waitFor(async () => { const d = await readCcfDetails(); return d && d.shown && d.status; }, 8000);
    const dC = await readCcfDetails();
    L.check('step 5: a member of a not-applied group shows the reason instead', Boolean(dC) && dC.shown && /not applied/i.test(dC.status || '') && /differs from/.test(dC.status || ''), dC);
    await app.selectTreeNode('P');
    await app.settle(600);
    const gP = await app.details();
    const sumB = await app.api('get', '/analysis/summary');
    const gv = sumB.ccfGates && sumB.ccfGates.P;
    L.check('step 5 (FN-66): the gate above the members shows its MCUB including CCF, noted', Boolean(gv) && gv.method === 'mcub' && gP.calc === L.fmt(gv.value, sf) && gP.calcNote.includes(T.en.mcubNote), { calc: gP.calc, note: gP.calcNote, gv });

  });

  // ---- step 10 (FN-22): diagram box of Pump A ----------------------------------------------
  await part('step 10', async () => {
    await app.waitDiagram();
    nodes = await app.diagramNodes();
    const boxA = (nodes || []).find((n) => n.texts.join(' ').includes('Pump A'));
    const boxText = boxA ? boxA.texts.join(' ') : '';
    L.check('step 10: the diagram box of Pump A contains "(indep. "', boxText.includes('(indep. '), boxText);
    L.check('step 10: ... and the independent part ' + L.fmt(9e-4, 3), boxText.includes('indep. ' + L.fmt(9e-4, 3)), boxText);
    L.check('step 10: ... and the badge CCF: Feed pumps', boxText.includes('CCF: Feed pumps'), boxText);

  });

  // ---- step 6 (22): the beta field ---------------------------------------------------------
  await part('step 6', async () => {
    await openCcfTab();
    await selectGroupRow(feedId);
    const betaInfo = await page.evaluate(() => {
      const input = document.querySelector('#tabpanel-ccf [data-section="editor"] input[data-field="beta"]');
      const lab = input && input.id ? document.querySelector('label[for="' + input.id + '"]') : null;
      return { label: lab ? lab.textContent.trim() : null, value: input ? input.value : null };
  });
  L.check('step 6: the beta field is labelled "β (dimensionless, 0 to 1)"', betaInfo.label === T.en.betaLabel, betaInfo);
  const r6 = await rev();
  const p6 = patches.length;
  for (const bad of ['1.5', 'abc']) {
    await commit('beta', bad);
    await page.waitForTimeout(400);
    const e = await errBelow();
    L.check('step 6: "' + bad + '" shows the message next to the field (en)', Boolean(e) && e.shown && e.text === T.en.betaErr && e.below && e.invalid, e);
    L.check('step 6: "' + bad + '" sends no request and changes nothing', patches.length === p6 && (await rev()) === r6 && (await byName('Feed pumps')).beta === 0.1, { patches: patches.length - p6 });
    if (bad === '1.5') await app.shot('ccf_beta_error_en');
    await editor.locator('input[data-field="beta"]').press('Escape');
    await page.waitForTimeout(200);
  }
  const afterEsc = await errBelow();
  L.check('step 6: Escape restores the saved value 0.1 and clears the message', Boolean(afterEsc) && afterEsc.value === '0.1' && !afterEsc.shown, afterEsc);
  await commit('beta', '5%');
  await waitFor(async () => (await byName('Feed pumps')).beta === 0.05);
  await page.waitForTimeout(300);
  const e5 = await errBelow();
  L.check('step 6: "5%" is read as 0.05 (API beta 0.05)', (await byName('Feed pumps')).beta === 0.05, await byName('Feed pumps'));
  L.check('step 6: ... and the field shows 0.05', Boolean(e5) && e5.value === '0.05' && !e5.shown, e5);
  await undoClick();
  L.check('step 6: one Undo restores beta 0.1', await waitFor(async () => (await byName('Feed pumps')).beta === 0.1));

  });

  // ---- step 7 (23), first part: the Validation issue lands on the group ----------------------
  await part('step 7 (jump)', async () => {
    await app.clickTab('validation');
    await page.waitForSelector('#tabpanel-validation li.val-item', { timeout: 15000 });
    await app.settle(600);
    const item = page.locator('#tabpanel-validation li.val-item[data-code="CCF_MEMBERS_DIFFER"][data-group="' + reliefId + '"]');
    L.check('step 7: Validation lists CCF_MEMBERS_DIFFER with data-group', (await item.count()) === 1, await page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-validation li.val-item')).map((l) => l.dataset.code)));
    await item.locator('.val-item__node').click();
    const landed = await waitFor(async () => page.evaluate(() => {
      const tab = document.getElementById('tab-ccf');
      return tab && tab.getAttribute('aria-selected') === 'true';
    }));
    await page.waitForTimeout(400);
    const selRow = await readRows();
    L.check('step 7: clicking the issue opens the CCF tab', landed);
    L.check('step 7: ... with the group row selected', selRow.some((r) => r.id === reliefId && r.selected), selRow);
    await app.shot('ccf_validation_jump');

  });

  // ---- step 8 (24, text): the Assumptions box, en and ja ---------------------------------------
  await part('step 8', async () => {
    await checkAssume('en');

  });

  // ---- ja pass: columns, statuses, beta messages, assumptions, headline ------------------------
  await part('ja pass', async () => {
    await app.setLanguage('ja');
    await page.waitForTimeout(500);
    await openCcfTab();
    await checkAssume('ja');
    const jaTab = await page.evaluate(() => document.getElementById('tab-ccf').textContent.trim());
    L.check('ja step 1: the tab is named "CCF グループ"', jaTab === T.ja.tab, jaTab);
    L.check('ja step 1: columns in Japanese', JSON.stringify(await readHeads()) === JSON.stringify(T.ja.cols), await readHeads());
    rows = await readRows();
    const apiNow = await groups();
    const relJa = apiNow.find((g) => g.id === reliefId).status.reason.ja;
    const rJa = rows.find((r) => r.id === reliefId);
    const fJa = rows.find((r) => r.id === feedId);
    L.check('ja step 1: statuses in Japanese (適用中 and 未適用: <reason>)', Boolean(rJa) && Boolean(fJa) && fJa.status === T.ja.applied && rJa.status === T.ja.notApplied(norm(relJa)) && rJa.model === T.ja.model, { rJa, fJa, relJa });
    await selectGroupRow(feedId);
    const betaJa = await page.evaluate(() => {
      const input = document.querySelector('#tabpanel-ccf [data-section="editor"] input[data-field="beta"]');
      const lab = input && input.id ? document.querySelector('label[for="' + input.id + '"]') : null;
      return lab ? lab.textContent.trim() : null;
  });
  L.check('ja step 6: the beta label reads "β（無次元、0 から 1）"', betaJa === T.ja.betaLabel, betaJa);
  const pj = patches.length;
  for (const bad of ['1.5', 'abc']) {
    await commit('beta', bad);
    await page.waitForTimeout(400);
    const e = await errBelow();
    L.check('ja step 6: "' + bad + '" shows the message next to the field (ja)', Boolean(e) && e.shown && e.text === T.ja.betaErr && e.below, e);
    L.check('ja step 6: "' + bad + '" sends no request', patches.length === pj, { patches: patches.length - pj });
    if (bad === '1.5') await app.shot('ccf_beta_error_ja');
    await editor.locator('input[data-field="beta"]').press('Escape');
    await page.waitForTimeout(200);
  }
  h = await readHeadline();
  L.check('ja step 4: the headline reads "MCUB、CCF を含む（1 グループ）" and "CCF グループ 1 件が未適用"', h.ccf === T.ja.includes1 && h.note === T.ja.notApplied1, h);
  await app.setLanguage('en');
  await page.waitForTimeout(400);

  }, async () => { await app.setLanguage('en'); });

  // ---- step 9: Basic mode -------------------------------------------------------------------------
  await part('step 9', async () => {
    await app.setAdvanced(false);
    await page.waitForTimeout(500);
    const basicTab = await page.evaluate(() => { const b = document.getElementById('tab-ccf'); return Boolean(b) && (b.hidden || b.offsetParent === null); });
    L.check('step 9: in Basic mode the CCF tab is hidden', basicTab);
    const basicBadges = await treeBadges();
    L.check('step 9: tree badges are shown in Basic mode', basicBadges.filter((b) => b.group === feedId).length === 2, basicBadges);
    await app.clickTab('details');
    await app.selectTreeNode('A');
    await waitFor(async () => { const d = await readCcfDetails(); return d && d.shown; }, 8000);
    const basicDet = await readCcfDetails();
    L.check('step 9: the Details CCF row is shown in Basic mode', Boolean(basicDet) && basicDet.shown && basicDet.qt === L.fmt(1e-3, sf), basicDet);
    h = await readHeadline();
    L.check('step 9: the CCF headline text is shown in Basic mode', h.ccfVisible && h.ccf === T.en.includes1, h);
    await app.shot('ccf_basic');
    await app.clickTab('validation');
    await page.waitForSelector('#tabpanel-validation li.val-item[data-code="CCF_MEMBERS_DIFFER"]', { timeout: 15000 });
    await app.settle(400);
    await page.evaluate(() => document.getElementById('toasts').replaceChildren());
    await page.locator('#tabpanel-validation li.val-item[data-code="CCF_MEMBERS_DIFFER"] .val-item__node').click();
    const toastOk = await waitFor(async () => (await toasts()).some((t) => t === T.en.needsAdvanced), 4000);
    L.check('step 9: in Basic mode the Validation jump gives the toast "Switch on Advanced ..." and nothing else', toastOk, await toasts());
    await app.setAdvanced(true);
    await page.waitForTimeout(400);

  }, async () => { await app.setAdvanced(true); });

  // ---- step 7, second part: ETA mode -------------------------------------------------------------------
  await part('step 7 (ETA)', async () => {
    const etaSet = await app.api('post', '/metadata', { mode: 'ETA' });
    L.check('step 7: mode set to ETA through /api/metadata', !etaSet.__error, etaSet.__error ? etaSet : undefined);
    await reload();
    const etaTab = await page.evaluate(() => { const b = document.getElementById('tab-ccf'); return b ? { unavailable: b.classList.contains('is-unavailable'), data: b.dataset.unavailable || null, title: b.title || '' } : null; });
    L.check('step 7: the CCF tab is greyed in ETA mode with the reason as its title', Boolean(etaTab) && etaTab.unavailable && etaTab.data === 'eta' && etaTab.title === T.en.etaTab, etaTab);
    await openCcfTab();
    rows = await readRows();
    L.check('step 7: both statuses read "Not applied: ETA mode"', rows.length === 2 && rows.every((r) => r.kind === 'not-applied' && r.status === T.en.eta), rows);
    await app.shot('ccf_tab_eta');
    await waitFor(async () => (await readHeadline()).note === T.en.notApplied2, 8000);
    h = await readHeadline();
    L.check('step 7: the headline notes "2 CCF groups not applied"', h.note === T.en.notApplied2 && h.noteVisible, h);
    await app.clickTab('validation');
    await page.waitForTimeout(1500);
    const etaCodes = await page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-validation li.val-item')).map((l) => l.dataset.code));
    const etaApi = await app.api('get', '/analysis/validate');
    const etaApiCodes = etaApi.__error ? [] : (etaApi.issues || []).map((i) => i.code);
    L.check('step 7: the Validation tab lists no CCF issue in ETA mode', !etaCodes.some((c) => /^CCF_/.test(c)) && !etaApiCodes.some((c) => /^CCF_/.test(c)), { etaCodes, etaApiCodes });
    const saved = await app.api('post', '/file/save-as', { path: path.join(root, etaFile) });
    L.check('step 7: Save works in ETA mode', !saved.__error, saved.__error ? saved : undefined);
    let doc = null;
    try { doc = JSON.parse(fs.readFileSync(path.join(root, etaFile), 'utf8')); } catch (_e) { doc = null; }
    const savedGroups = doc && doc.analysis && doc.analysis.ccfGroups;
    L.check('step 7: the saved file keeps both groups (ccfGroups, fileFormatVersion 2)', Array.isArray(savedGroups) && savedGroups.length === 2 && doc.fileFormatVersion === 2 && savedGroups.some((g) => g.name === 'Feed pumps' && g.beta === 0.1) && savedGroups.some((g) => g.name === 'Relief valves' && g.beta === 0.2), { n: Array.isArray(savedGroups) ? savedGroups.length : null, v: doc && doc.fileFormatVersion });
    const back = await app.api('post', '/metadata', { mode: 'FTA' });
    L.check('step 7: back to FTA mode', !back.__error, back.__error ? back : undefined);

  }, async () => { await app.api('post', '/metadata', { mode: 'FTA' }); });

  // ---- step 4, second part: a real incomplete headline (summary cap) --------------------------------
  await part('step 4 (incomplete)', async () => {
    fs.writeFileSync(path.join(root, capFile), capDocumentText());
    await openDoc(capFile);
    await waitFor(async () => (await readHeadline()).ccf === T.en.incomplete, 20000);
    h = await readHeadline();
    const capApi = await app.api('get', '/analysis/summary');
    L.check('step 4: API summary of the 2,100-leaf file: incomplete, ccfIncomplete, reason summary cap', capApi.headlineMethod === 'incomplete' && capApi.ccfIncomplete === true && capApi.ccfIncompleteReason === 'summary cap' && capApi.headline === null, { m: capApi.headlineMethod, r: capApi.ccfIncompleteReason, h: capApi.headline });
    L.check('step 4: the headline reads "incomplete, CCF not included" with "—" for the value', h.ccf === T.en.incomplete && h.value === '—', h);
    L.check('step 4: ... and "tree walk, without CCF; cut sets cut short (summary cap)"', h.walkVisible && h.walkLabel === T.en.walk(T.en.reasons.cap), h);
    L.check('step 4: ... followed by the tree-walk value of the API', h.walkValue === L.fmt(capApi.treeWalk, sf), { gui: h.walkValue, api: L.fmt(capApi.treeWalk, sf) });
    await app.shot('ccf_headline_incomplete');
    await app.clickTab('details');
    await app.selectTreeNode('root');
    await app.settle(600);
    const dRoot = await app.details();
    L.check('step 4: the gate above a member shows "n/a (CCF)" in Details (never its tree-walk value)', dRoot.calc === T.en.na, dRoot.calc);
    const rootProb = await page.evaluate(() => { const e = document.querySelector('#tree-root li.fta-tree-item[data-id="root"] > .fta-tree-row .fta-tree-prob'); return e ? e.textContent.trim() : null; });
    L.check('step 4: ... and on its tree row', rootProb === T.en.na, rootProb);
    // reason time and error: the payload of DESIGN 11.2 through ftaShell.setHeadline (a literal budget cannot fire on a small tree)
    for (const reason of ['time', 'error']) {
      const got = await page.evaluate(async (r) => {
        const { store } = await import('/static/js/store.js');
        window.ftaShell.setHeadline({
          value: null, method: 'incomplete', ccfApplied: 1, ccfNotApplied: 0, ccfIncomplete: true, ccfReason: r,
          walk: 0.0123, ccfGates: {}, ccf: { applied: [{ id: 'g1', name: 'Cap pair' }], notApplied: [] }, tree: store.state.tree,
        });
        const t = (s) => { const e = document.querySelector(s); return e ? e.textContent.replace(/[ \s]+/g, ' ').trim() : null; };
        return { ccf: t('#headline-ccf'), label: t('#headline-walk .headline__walk-label'), walk: t('#headline-walk .headline__walk-value'), value: t('#headline-value') };
      }, reason);
      L.check('step 4: reason ' + reason + ' reads "' + T.en.walk(T.en.reasons[reason]) + '"', got.ccf === T.en.incomplete && got.label === T.en.walk(T.en.reasons[reason]) && got.walk === L.fmt(0.0123, sf) && got.value === '—', got);
    }
    await app.setLanguage('ja');
    await page.waitForTimeout(300);
    const gotJa = await page.evaluate(() => { const t = (s) => { const e = document.querySelector(s); return e ? e.textContent.replace(/[ \s]+/g, ' ').trim() : null; }; return { ccf: t('#headline-ccf'), label: t('#headline-walk .headline__walk-label') }; });
    L.check('ja step 4: the incomplete headline and the reason "エラー" in Japanese', gotJa.ccf === T.ja.incomplete && gotJa.label === T.ja.walk(T.ja.reasons.error), gotJa);
    await app.setLanguage('en');

  }, async () => { await app.setLanguage('en'); });

  // ---- step 12 (FN-24 GUI): the Uncertainty tab says beta and alpha are not sampled -------------------
  // DESIGN 11 / 12 give no selector for the note (it sits "under the result"), so the check reads the
  // text of the whole #tabpanel-uncertainty; the run button, n field and [data-stat="mean"] are the
  // ids the other sections (s_tabs.js, s_i18n.js) already use.
  await part('step 12 (FN-24 GUI)', async () => {
    await openDoc(file);
    const made12 = await app.api('post', '/ccf/groups', { name: 'Feed pumps', model: 'beta', beta: 0.1, members: ['A', 'B'], source: 'test' });
    L.check('step 12: the group Feed pumps is made by the API (applied)', !made12.__error, made12.__error ? made12 : undefined);
    await reload();
    const mcText = async () => {
      await app.clickTab('uncertainty');
      const nIn = page.locator('#tabpanel-uncertainty input[data-field="n"]');
      await nIn.click();
      await page.keyboard.press('Control+A');
      await page.keyboard.type('500');
      await page.locator('#tabpanel-uncertainty button[data-role="run"]').click();
      await page.waitForSelector('#tabpanel-uncertainty [data-stat="mean"]', { timeout: 60000 });
      await page.waitForTimeout(300);
      return page.evaluate(() => document.getElementById('tabpanel-uncertainty').textContent.replace(/[ \s]+/g, ' ').trim());
    };
    const textEn = await mcText();
    L.check('step 12: after a Monte Carlo run the Uncertainty tab reads "' + T.en.assume.sampling + '" (en)', textEn.includes(T.en.assume.sampling), textEn.slice(0, 400));
    await app.shot('ccf_uncertainty_note');
    await app.setLanguage('ja');
    await page.waitForTimeout(500);
    const textJa = await mcText();
    L.check('ja step 12: after a Monte Carlo run the Uncertainty tab reads "' + T.ja.assume.sampling + '" (ja)', textJa.includes(T.ja.assume.sampling), textJa.slice(0, 400));
    await app.setLanguage('en');
    await page.waitForTimeout(300);
  }, async () => { await app.setLanguage('en'); });

  // ---- step 11: console ---------------------------------------------------------------------------
  const errs = app.errorsSince(0);
  L.check('step 11: no console errors, page errors or failed /api requests in the whole run', errs.length === 0, errs.slice(0, 5));
  await app.context.close();
}

L.runSection('ccf', run);
