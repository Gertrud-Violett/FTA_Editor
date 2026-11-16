// Final-review fixes (feature FR, task X4), in a real browser.
//   node s_finalfix.js <url> <label> <root>
//
// Case ccf_undo   The marks of a selected CCF group follow its member list through Undo and Redo.
//                 A document with a beta group of three members (A, B, C). Selecting the group in the CCF tab marks the
//                 three members in the tree (`.fta-tree-row.is-highlighted`). Removing C with the chip button of the tab
//                 marks two (the marks follow: existing behaviour). Undo brings C back, so the marks must be A, B and C
//                 again; Redo removes C, so they must be A and B. The tab used to repaint the new member list after Undo
//                 and Redo but leave the old marks (afterData did not call highlightGroup).
//                 Shots finalfix-ccf-undo-marks (A, B, C marked) and finalfix-ccf-redo-marks (A, B marked, C not).
// Case ccf_hidden_race  A PATCH (member removal) and a POST (create from the selection) are held by a route; the CCF tab is
//                 left; the answer is released. No tree or diagram mark may appear while the tab is hidden; showing the tab
//                 again brings the marks of the selected group back.
// Case ccf_collapse  With a group selected the user closes G2 (no member's ancestor) and G1 (the members' branch); a rename and a
//                 beta edit (no change of the member list) must leave both closed. (Only the member's own branch reopens
//                 on the current tree: revealAll opens ancestors of the marked ids, never another branch.)
// Case whatif_shots  Two evidence shots of the What-if tab (F4-ui-1 advice), default pane 1100 x 800, light theme:
//                 finalfix-whatif-nofactors (no factor set) and finalfix-whatif-afterreset (a factor, then Reset all). They
//                 are not decoration: the states they show are asserted (banner absent, data-factors 0, the what-if top
//                 event equal to the baseline and to the headline, the picker focused after Reset all).
// The screenshots go to the output folder of the run (lib.js shot).
//
// Every check name starts with finalfix_.
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const TID = (id) => `[data-testid="${id}"]`;

// ---- documents --------------------------------------------------------------------------------------------------
const leaf = (id, name, q) => ({ id, name, type: 'Event', logicGate: 'OR', probability: q, notes: '', links: [], children: [], quant: { model: 'fixed' } });

/** root OR [ G1 AND [Pump A, Pump B, Pump C] (same q, so the beta group of the three is applied), Pump D, G2 AND [Valve E, Valve F] (no group) ]. */
const ccfDoc = () => ({
  title: 'Final fixes: CCF undo', date: '2026-11-02', mode: 'FTA', fileFormatVersion: 2,
  tree: {
    id: 'root', name: 'Top event', type: 'Root', logicGate: 'OR', probability: 1.0, notes: '', links: [],
    children: [
      { id: 'G1', name: 'Pumps fail', type: 'Event', logicGate: 'AND', probability: 1.0, notes: '', links: [], children: [leaf('A', 'Pump A', 1e-3), leaf('B', 'Pump B', 1e-3), leaf('C', 'Pump C', 1e-3)] },
      leaf('D', 'Pump D', 1e-3),
      { id: 'G2', name: 'Valves fail', type: 'Event', logicGate: 'AND', probability: 1.0, notes: '', links: [], children: [leaf('E', 'Valve E', 1e-3), leaf('F', 'Valve F', 1e-3)] },
    ],
  },
  analysis: { ccfGroups: [{ id: 'g1', name: 'Feed pumps', model: 'beta', beta: 0.1, alpha: null, testing: null, members: ['A', 'B', 'C'], source: 'test' }] },
});

/** root OR [E1 (q 1e-3), E2 (q 2e-3)], both fixed: the top event is 1 - (1 - q1)(1 - q2). */
const twoDoc = () => ({
  title: 'Final fixes: What-if shots', date: '2026-11-02', mode: 'FTA',
  tree: { id: 'root', name: 'Top event', type: 'Root', logicGate: 'OR', probability: 1.0, notes: '', links: [], children: [leaf('E1', 'Pump E1', 1e-3), leaf('E2', 'Pump E2', 2e-3)] },
});
const union = (ps) => 1 - ps.reduce((acc, p) => acc * (1 - p), 1);
const close = (a, b, rel) => typeof a === 'number' && Number.isFinite(a) && typeof b === 'number' && (b === 0 ? a === 0 : Math.abs(a - b) <= rel * Math.abs(b));
const num = (c) => (c && c.value !== null && c.value !== '' ? Number(c.value) : null);

const CELLS = { topBaseline: 'whatif-top-baseline', topWhatif: 'whatif-top-whatif' };
const readTab = (pg) => pg.evaluate((cells) => {
  const q = (id) => document.querySelector(`[data-testid="${id}"]`);
  const out = { root: null, cells: {} };
  const root = q('whatif-root');
  if (root) {
    const d = root.dataset;
    out.root = { state: d.state, factors: d.factors, pending: d.pending, seqSent: d.seqSent, seqApplied: d.seqApplied };
  }
  for (const [key, id] of Object.entries(cells)) {
    const e = q(id);
    out.cells[key] = e ? { value: e.dataset.value === undefined ? null : e.dataset.value } : null;
  }
  return out;
}, CELLS);
const settledPred = (r) => Boolean(r.root) && r.root.state === 'ready' && r.root.pending === '0' && r.root.seqApplied === r.root.seqSent
  && ['topBaseline', 'topWhatif'].every((k) => r.cells[k] && r.cells[k].value !== null && r.cells[k].value !== '');

async function main(url, label, root) {
  L.setSection('finalfix[' + label + ']');
  const ccfName = `finalfix_ccf_${label}.json`;
  const twoName = `finalfix_two_${label}.json`;
  fs.writeFileSync(path.join(root, ccfName), JSON.stringify(ccfDoc(), null, 2));
  fs.writeFileSync(path.join(root, twoName), JSON.stringify(twoDoc(), null, 2));

  const app = await L.openApp(url, { viewport: { width: 1100, height: 800 }, colorScheme: 'light', prefs: { 'fta.advanced': '1', 'fta.theme': 'light' } });
  const { page } = app;
  page.setDefaultTimeout(8000);
  page.on('dialog', (d) => { d.accept().catch(() => {}); });
  const shots = [];

  // ---- helpers ---------------------------------------------------------------------------------------------------
  const waitFor = async (fn, timeout = 8000) => {
    const t0 = Date.now();
    for (;;) {
      let v = false;
      try { v = await fn(); } catch (_e) { v = false; }
      if (v) return true;
      if (Date.now() - t0 > timeout) return false;
      await sleep(80);
    }
  };
  const waitRead = async (pred, timeout = 8000) => {
    const t0 = Date.now();
    let r;
    for (;;) {
      r = await readTab(page);
      let ok = false;
      try { ok = Boolean(pred(r)); } catch (_e) { ok = false; }
      if (ok) return { ok: true, r };
      if (Date.now() - t0 > timeout) return { ok: false, r };
      await sleep(60);
    }
  };
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
  const groupsApi = async () => ((await app.api('get', '/ccf/groups')).groups) || [];
  const membersApi = async () => { const g = (await groupsApi()).find((x) => x.id === 'g1'); return g ? g.members.slice() : null; };
  /** The ids of the tree rows that carry the mark `is-highlighted`, sorted. */
  const marks = () => page.evaluate(() => Array.from(document.querySelectorAll('#tree-root .fta-tree-row.is-highlighted')).map((r) => r.closest('li.fta-tree-item').dataset.id).sort());
  const chips = () => page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-ccf [data-section="editor"] [data-role="members"] li[data-member]')).map((li) => li.dataset.member));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const active = () => page.evaluate(() => { const a = document.activeElement; return a ? { id: a.id || '', testid: a.getAttribute('data-testid') || '', tag: a.tagName } : null; });
  const shot = async (name) => { shots.push(name); return app.shot(name); };
  const headline = async () => (await app.api('get', '/analysis/summary')).headline;

  // ================================================================================================================
  // ccf_undo: the marks follow the member list through Undo and Redo
  // ================================================================================================================
  const caseCcfUndo = async () => {
    const T = 'finalfix_ccf_undo_';
    await openDoc(ccfName);
    await app.clickTab('ccf');
    await page.waitForSelector('#tabpanel-ccf .anl-ccf[data-tab="ccf"]', { timeout: 8000 });
    await page.waitForTimeout(300);
    L.check(`${T}precondition_group: the document has the group of three (A, B, C)`, same(await membersApi(), ['A', 'B', 'C']), await groupsApi());

    // select the group: the tree marks its three members
    await page.locator('#tabpanel-ccf [data-role="groups"] tbody tr[data-id="g1"]').click();
    await page.waitForSelector('#tabpanel-ccf [data-section="editor"] input[data-field="name"]', { timeout: 5000 });
    await page.waitForTimeout(300);
    L.check(`${T}select_marks_three: selecting the group marks Pump A, Pump B and Pump C in the tree`, same(await marks(), ['A', 'B', 'C']), await marks());
    L.check(`${T}select_chips_three: the editor lists the three members as chips`, same(await chips(), ['A', 'B', 'C']), await chips());

    // remove C with the chip button of the tab: the marks follow (existing behaviour)
    await page.locator('#tabpanel-ccf [data-section="editor"] [data-role="members"] li[data-member="C"] button[data-role="remove-member"]').click();
    const removed = await waitFor(async () => same(await membersApi(), ['A', 'B']) && same(await chips(), ['A', 'B']));
    await page.waitForTimeout(300);
    L.check(`${T}remove_changed_group: removing C leaves the group with A and B (API and chips)`, removed, { api: await membersApi(), chips: await chips() });
    L.check(`${T}remove_marks_two: the tree marks follow the removal (Pump A and Pump B only)`, same(await marks(), ['A', 'B']), await marks());

    // Undo: C is back in the group, so C must be marked again
    await page.locator('#btn-undo').click();
    const undone = await waitFor(async () => same(await membersApi(), ['A', 'B', 'C']) && same(await chips(), ['A', 'B', 'C']));
    await page.waitForTimeout(500);
    const selectedAfterUndo = await page.evaluate(() => { const tr = document.querySelector('#tabpanel-ccf [data-role="groups"] tbody tr[data-id="g1"]'); return Boolean(tr) && tr.classList.contains('is-selected'); });
    L.check(`${T}undo_restored_group: Undo gives the group its three members back (API and chips) and the group stays selected`, undone && selectedAfterUndo, { api: await membersApi(), chips: await chips(), selectedAfterUndo });
    const afterUndo = await marks();
    await shot('finalfix-ccf-undo-marks');
    L.check(`${T}undo_marks_three: after Undo the tree marks the three members again (the removed Pump C is marked)`, same(afterUndo, ['A', 'B', 'C']), afterUndo);

    // Redo: C is out again, so C must not be marked
    await page.locator('#btn-redo').click();
    const redone = await waitFor(async () => same(await membersApi(), ['A', 'B']) && same(await chips(), ['A', 'B']));
    await page.waitForTimeout(500);
    L.check(`${T}redo_removed_again: Redo removes C again (API and chips)`, redone, { api: await membersApi(), chips: await chips() });
    const afterRedo = await marks();
    await shot('finalfix-ccf-redo-marks');
    L.check(`${T}redo_marks_two: after Redo the tree marks two members (Pump A and Pump B)`, same(afterRedo, ['A', 'B']), afterRedo);

    // a second round, so that the fix is not a one-off: Undo once more
    await page.locator('#btn-undo').click();
    const undone2 = await waitFor(async () => same(await membersApi(), ['A', 'B', 'C']) && same(await chips(), ['A', 'B', 'C']));
    await page.waitForTimeout(500);
    L.check(`${T}undo_again_marks_three: a second Undo marks the three members again`, undone2 && same(await marks(), ['A', 'B', 'C']), { undone2, marks: await marks() });
  };

  // ================================================================================================================
  // whatif_shots: no factors, and after Reset all
  // ================================================================================================================
  const caseWhatifShots = async () => {
    const T = 'finalfix_whatif_';
    const q1 = 1e-3;
    const q2 = 2e-3;
    await openDoc(twoName);
    await app.setAdvanced(true);
    await page.locator('#tab-whatif').click();
    await page.locator(TID('whatif-root')).waitFor({ state: 'visible' });
    const w0 = await waitRead(settledPred, 20000);
    L.check(`${T}nofactors_settled: the What-if tab has its baseline`, w0.ok, w0.r.root);
    if (!w0.ok) return;
    const h0 = await headline();
    await page.waitForTimeout(300);
    await shot('finalfix-whatif-nofactors');
    L.check(`${T}nofactors_state: no factor set: banner absent, no chip, data-factors 0`, w0.r.root.factors === '0' && (await page.locator(TID('whatif-banner')).count()) === 0 && (await page.locator(TID('whatif-chip')).count()) === 0, w0.r.root);
    L.check(`${T}nofactors_values: the what-if top event equals the baseline, the headline and 1 - (1 - 1e-3)(1 - 2e-3)`,
      w0.r.cells.topWhatif.value === w0.r.cells.topBaseline.value && w0.r.cells.topBaseline.value === String(h0) && close(num(w0.r.cells.topBaseline), union([q1, q2]), 1e-9),
      { whatif: w0.r.cells.topWhatif.value, baseline: w0.r.cells.topBaseline.value, headline: h0 });
    L.check(`${T}nofactors_pane: the shot is taken at the default pane (1100 x 800) in the light theme`,
      await page.evaluate(() => window.innerWidth === 1100 && window.innerHeight === 800 && document.documentElement.getAttribute('data-theme') === 'light'),
      await page.evaluate(() => ({ w: window.innerWidth, h: window.innerHeight, theme: document.documentElement.getAttribute('data-theme') })));

    // a factor on E1, then Reset all
    await page.locator(TID('whatif-picker')).selectOption('E1');
    const f = page.locator(TID('whatif-factor-input'));
    await f.fill('10');
    await f.press('Enter');
    const w1 = await waitRead((r) => settledPred(r) && r.root.factors === '1' && close(num(r.cells.topWhatif), union([10 * q1, q2]), 1e-9), 8000);
    L.check(`${T}precondition_factor: the factor 10 on E1 is applied (banner shown, data-factors 1, what-if top event ${union([10 * q1, q2])})`, w1.ok && (await page.locator(TID('whatif-banner')).count()) === 1, w1.r);
    await page.locator('#title-input').focus(); // so that the move of focus to the picker is the tab's doing
    await page.locator(TID('whatif-reset-all')).click();
    const w2 = await waitRead((r) => settledPred(r) && r.root.factors === '0', 8000);
    await page.waitForTimeout(300);
    const focus = await active();
    const h2 = await headline();
    await shot('finalfix-whatif-afterreset');
    L.check(`${T}afterreset_state: after Reset all the banner is absent, no chip, data-factors 0`, w2.ok && (await page.locator(TID('whatif-banner')).count()) === 0 && (await page.locator(TID('whatif-chip')).count()) === 0, w2.r.root);
    L.check(`${T}afterreset_values: the what-if top event equals the baseline and the headline again (the same float)`,
      w2.ok && w2.r.cells.topWhatif.value === w2.r.cells.topBaseline.value && w2.r.cells.topBaseline.value === String(h2) && w2.r.cells.topBaseline.value === w0.r.cells.topBaseline.value,
      { whatif: w2.r.cells.topWhatif && w2.r.cells.topWhatif.value, baseline: w2.r.cells.topBaseline && w2.r.cells.topBaseline.value, headline: h2, first: w0.r.cells.topBaseline.value });
    L.check(`${T}afterreset_focus: Reset all leaves the focus on the picker`, Boolean(focus) && focus.testid === 'whatif-picker', focus);
  };

  // ================================================================================================================
  // ccf_hidden_race: an answer that arrives after the tab was left must not paint marks (round 1 of the ui lens)
  // ================================================================================================================
  const diagramMarks = () => page.evaluate(() => document.querySelectorAll('#diagram-root g.node.is-highlighted').length);
  /** Hold every request of `method` that matches `pattern` until `release()`; `held` counts them. */
  const hold = async (method, pattern) => {
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    const state = { held: 0, release: () => release() };
    await page.route(pattern, async (route) => {
      if (route.request().method() !== method) { await route.fallback(); return; }
      state.held += 1;
      await gate;
      await route.continue().catch(() => {});
    });
    return state;
  };
  const showCcf = async () => {
    await app.clickTab('ccf');
    await page.waitForSelector('#tabpanel-ccf .anl-ccf[data-tab="ccf"]', { timeout: 8000 });
    await page.waitForTimeout(300);
  };
  const selectGroup = async (gid) => {
    await page.locator(`#tabpanel-ccf [data-role="groups"] tbody tr[data-id="${gid}"]`).click();
    await page.waitForSelector('#tabpanel-ccf [data-section="editor"] input[data-field="name"]', { timeout: 5000 });
    await page.waitForTimeout(300);
  };

  const caseCcfHiddenRace = async () => {
    const T = 'finalfix_ccf_race_';
    // --- a member removal (PATCH) answered after the tab was left
    await openDoc(ccfName);
    await showCcf();
    await selectGroup('g1');
    L.check(`${T}patch_precondition_marks: with the tab shown and the group selected the tree marks A, B, C`, same(await marks(), ['A', 'B', 'C']), await marks());
    const patch = await hold('PATCH', '**/api/ccf/groups/g1');
    await page.locator('#tabpanel-ccf [data-section="editor"] [data-role="members"] li[data-member="C"] button[data-role="remove-member"]').click();
    const held = await waitFor(async () => patch.held === 1);
    L.check(`${T}patch_precondition_held: the PATCH that removes C is on hold and the server still has A, B, C`, held && same(await membersApi(), ['A', 'B', 'C']), { held: patch.held, api: await membersApi() });
    await app.clickTab('quant');
    await page.waitForTimeout(400);
    L.check(`${T}patch_precondition_cleared: leaving the CCF tab clears the marks (tree and diagram)`, same(await marks(), []) && (await diagramMarks()) === 0, { tree: await marks(), diagram: await diagramMarks() });
    patch.release();
    const done = await waitFor(async () => same(await membersApi(), ['A', 'B']));
    await page.waitForTimeout(700);
    const treeAfter = await marks();
    const diagramAfter = await diagramMarks();
    L.check(`${T}patch_answered: the held PATCH was answered (the server has A, B)`, done, await membersApi());
    L.check(`${T}patch_no_marks_while_hidden: the answer of the PATCH paints no marks while the CCF tab is hidden (tree and diagram)`, same(treeAfter, []) && diagramAfter === 0, { tree: treeAfter, diagram: diagramAfter });
    await showCcf();
    L.check(`${T}patch_marks_return: showing the tab again marks the two members of the selected group (A, B)`, same(await marks(), ['A', 'B']), await marks());
    await page.unrouteAll({ behavior: 'ignoreErrors' });

    // --- a group created from the selection (POST) answered after the tab was left
    await openDoc(ccfName);
    await showCcf();
    await page.locator('#tree-root li.fta-tree-item[data-id="D"] > .fta-tree-row').click();
    await page.locator('#tree-root li.fta-tree-item[data-id="E"] > .fta-tree-row').click({ modifiers: ['Control'] });
    await page.waitForTimeout(200);
    await page.locator('#tabpanel-ccf [data-role="new"]').click();
    const nameInput = page.locator('#tabpanel-ccf [data-section="editor"] input[data-field="name"]');
    await nameInput.waitFor({ state: 'visible' });
    await nameInput.fill('Late pair');
    await page.locator('#tabpanel-ccf [data-section="editor"] input[data-field="beta"]').fill('0.1');
    await page.waitForTimeout(200);
    const post = await hold('POST', '**/api/ccf/groups');
    await page.locator('#tabpanel-ccf [data-section="editor"] [data-role="create"]').click();
    const heldPost = await waitFor(async () => post.held === 1);
    L.check(`${T}post_precondition_held: the POST that creates the group is on hold and the server has one group`, heldPost && (await groupsApi()).length === 1, { held: post.held, groups: (await groupsApi()).length });
    await app.clickTab('quant');
    await page.waitForTimeout(400);
    post.release();
    const created = await waitFor(async () => (await groupsApi()).length === 2);
    await page.waitForTimeout(700);
    const treeAfterPost = await marks();
    const diagramAfterPost = await diagramMarks();
    L.check(`${T}post_answered: the held POST was answered (the server has the second group)`, created, (await groupsApi()).length);
    L.check(`${T}post_no_marks_while_hidden: the answer of the POST paints no marks while the CCF tab is hidden (tree and diagram)`, same(treeAfterPost, []) && diagramAfterPost === 0, { tree: treeAfterPost, diagram: diagramAfterPost });
    await showCcf();
    L.check(`${T}post_marks_return: showing the tab again marks the members of the new group (D, E)`, same(await marks(), ['D', 'E']), await marks());
    await page.unrouteAll({ behavior: 'ignoreErrors' });
  };

  // ================================================================================================================
  // ccf_collapse: an edit that does not change the member list leaves the tree as the user left it
  // ================================================================================================================
  const treeOpen = (id) => page.evaluate((i) => { const li = document.querySelector(`#tree-root li.fta-tree-item[data-id="${i}"]`); return li ? li.getAttribute('aria-expanded') : null; }, id);
  const setOpen = async (id, want) => {
    if ((await treeOpen(id)) !== String(want)) {
      await page.locator(`#tree-root li.fta-tree-item[data-id="${id}"] > .fta-tree-row .fta-tree-twisty`).click();
      await page.waitForTimeout(250);
    }
    return (await treeOpen(id)) === String(want);
  };
  const commit = async (field, value) => {
    const input = page.locator(`#tabpanel-ccf [data-section="editor"] input[data-field="${field}"]`);
    await input.click();
    await page.keyboard.press('Control+A');
    await page.keyboard.type(String(value), { delay: 3 });
    await page.keyboard.press('Enter');
  };

  const caseCcfCollapse = async () => {
    const T = 'finalfix_ccf_collapse_';
    await openDoc(ccfName);
    await showCcf();
    L.check(`${T}precondition_open: both branches are open to start with`, (await setOpen('G1', true)) && (await setOpen('G2', true)), { g1: await treeOpen('G1'), g2: await treeOpen('G2') });
    await selectGroup('g1');
    L.check(`${T}precondition_marks: the group is selected and the tree marks A, B, C`, same(await marks(), ['A', 'B', 'C']), await marks());
    // the user closes the branch of Valves (no member of the group) and the branch of the members
    const closedOther = await setOpen('G2', false);
    const closedMembers = await setOpen('G1', false);
    L.check(`${T}precondition_closed: the user closed G2 (not an ancestor of a member) and G1 (the members' branch)`, closedOther && closedMembers, { g1: await treeOpen('G1'), g2: await treeOpen('G2') });

    // an edit that leaves the member list alone: the name, then beta
    await commit('name', 'Feed pumps 2');
    const renamed = await waitFor(async () => ((await groupsApi()).find((g) => g.id === 'g1') || {}).name === 'Feed pumps 2');
    await page.waitForTimeout(700);
    L.check(`${T}rename_done: the rename reached the server and the group is still selected`, renamed && same(await chips(), ['A', 'B', 'C']), { chips: await chips() });
    L.check(`${T}rename_other_branch: after the rename the branch that is no member's ancestor (G2) is still closed`, (await treeOpen('G2')) === 'false', await treeOpen('G2'));
    L.check(`${T}rename_member_branch: after the rename the branch the user closed (G1, the members' branch) is still closed`, (await treeOpen('G1')) === 'false', await treeOpen('G1'));
    await commit('beta', '0.2');
    const betaDone = await waitFor(async () => ((await groupsApi()).find((g) => g.id === 'g1') || {}).beta === 0.2);
    await page.waitForTimeout(700);
    L.check(`${T}beta_done: the beta edit reached the server`, betaDone, (await groupsApi()).map((g) => g.beta));
    L.check(`${T}beta_other_branch: after the beta edit G2 is still closed`, (await treeOpen('G2')) === 'false', await treeOpen('G2'));
    L.check(`${T}beta_member_branch: after the beta edit G1 is still closed`, (await treeOpen('G1')) === 'false', await treeOpen('G1'));
  };

  for (const [name, fn] of [['ccf_undo', caseCcfUndo], ['ccf_hidden_race', caseCcfHiddenRace], ['ccf_collapse', caseCcfCollapse], ['whatif_shots', caseWhatifShots]]) {
    try { await fn(); } catch (e) {
      L.check(`finalfix_${name}: did not complete`, false, String((e && e.message) || e).split('\n')[0].slice(0, 400));
    }
  }

  const errs = app.errorsSince(0, []);
  L.check('finalfix_console: no console errors in the finalfix run', errs.length === 0, errs.slice(0, 5));
  await app.api('post', '/new', { force: true });
  for (const name of [ccfName, twoName]) fs.rmSync(path.join(root, name), { force: true });
  L.info('SHOTS written by finalfix: ' + JSON.stringify(shots.slice().sort()));
  await app.context.close();
}

L.runSection('finalfix', main);
