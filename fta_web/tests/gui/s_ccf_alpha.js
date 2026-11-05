// F2A acceptance (T0): CCF groups, alpha factor (groups of 2 to 4), in a real browser with real
// mouse and keyboard input. BRIEF criterion 6 (UI-8) and the GUI part of criterion 9 (UI-18). The
// numbered checks are those of DESIGN.md section 9 ("GUI checks for criterion 6"); every selector is
// the one of DESIGN 7.8. Written before the feature exists: the alpha checks fail while the model
// select, the alpha fields and the testing selector are missing.
//   node s_ccf_alpha.js <url> <label> <root>
//
// The tree is built here (a document written into the sandbox root and opened through the API).
// Groups are made by the GUI where the check is about creating them, by the API otherwise. No AI
// provider is called. Request listener: every POST / PATCH / DELETE to /api/ccf/groups is recorded.
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

// The shared vector file of FN-46 (the same text typed into a field and into the grid must read the same).
const VECTORS = JSON.parse(fs.readFileSync(path.join(L.REPO, 'fta_web', 'tests', 'fixtures', 'number_inputs.json'), 'utf8'));

// ---- the document -----------------------------------------------------------------
function leaf(id, name, probability) {
  return { id, name, type: 'Event', probability, logicGate: 'OR', notes: '', links: [], children: [] };
}
function gate(id, name, logicGate, children, extra) {
  return Object.assign(leaf(id, name, 1.0), { type: 'Gate', logicGate, children }, extra || {});
}

/**
 * Cooling loss (OR): Voting (2-of-3 over Valve A, B, C), Pair (AND: Valve D, Valve E), Valve F, Valve G.
 * All seven leaves have q 1e-3, so any selection of them can form a group (FN-33: identical members).
 */
function documentText(mode) {
  const names = { A: 'Valve A', B: 'Valve B', C: 'Valve C', D: 'Valve D', E: 'Valve E', F: 'Valve F', G: 'Valve G' };
  const l = (id) => leaf(id, names[id], 1e-3);
  const tree = Object.assign(leaf('root', 'Cooling loss', 1.0), {
    type: 'Root',
    children: [
      gate('V', 'Voting', 'OR', [l('A'), l('B'), l('C')], { gateType: 'KOFN', k: 2 }),
      gate('P', 'Pair', 'AND', [l('D'), l('E')]),
      l('F'),
      l('G'),
    ],
  });
  return JSON.stringify({ title: 'CCF alpha GUI', date: '2026-10-28', mode: mode || 'FTA', tree }, null, 2);
}

// ---- texts (DESIGN sections 4.2, 5, 6) ---------------------------------------------
const T = {
  en: {
    modelAlpha: 'Alpha factor',
    modelCell: 'Alpha factor',
    label: (k) => 'α' + k + ' (dimensionless, 0 to 1)',
    err: (k) => 'α' + k + ' must be a number from 0 to 1 (for example 0.05 or 5%).',
    hint: 'e.g. 0.05 or 5%',
    sumNone: 'Sum of α: —',
    sumOk: (s) => 'Sum of α: ' + s,
    sumNormalised: (s) => 'Sum of α: ' + s + '. Each α is divided by the sum.',
    sumBad: (s) => 'Sum of α: ' + s + '. It must be 1 (a difference up to 0.001 is corrected).',
    size: (n) => 'The alpha-factor model needs 2 to 4 members; this group has ' + n + '.',
    sizeReason: 'alpha-factor model needs 2 to 4 members',
    resize: (n, c) => 'Members: ' + n + ', α values stored: ' + c + '. Check the fields and save the α values.',
    help: (n) => 'α_k is the fraction of failure events in which exactly k members fail. Enter α1 to α' + n + '; they should add up to 1 (NUREG/CR-5485 p. 40).',
    testingHelp: 'Staggered: the components behind the α values were tested one after another at different times. Non-staggered: they were all tested at the same time. Choose the scheme that matches the source of your α values (NUREG/CR-5485 p. 40; NASA/SP-2011-3421 pp. 7-9, 7-14).',
    testingSaveFail: 'The testing scheme could not be saved:',
    placeholder: 'Choose a testing scheme',
    staggered: 'Staggered testing',
    nonStaggered: 'Non-staggered testing',
    applied: 'Applied',
    notApplied: (r) => 'Not applied: ' + r,
    noScheme: 'Not applied: testing scheme missing',
    eta: 'Not applied: ETA mode',
    badSum: 'Not applied: α values add up to 1.01, not 1',
    normalised: 'Warning: α values add up to 1.0005; divided by the sum',
    lengthMismatch: 'Not applied: α values: 3, members: 2',
    subset: (g, names) => 'CCF: ' + g + ' (' + names.join(' + ') + ')',
    assumeAlpha: 'Alpha-factor model: Q_k is the probability of each CCF event that fails exactly k of the group\'s members; staggered Q_k = α_k / C(m-1, k-1) · Q_t (NUREG/CR-5485 Eq. 5.6 p. 40); non-staggered Q_k = k / C(m-1, k-1) · (α_k / α_t) · Q_t with α_t = Σ k·α_k (Eq. 5.7-5.9 p. 41; NUREG/CR-4780 Vol. 2 Eq. C.23-C.24 pp. C-10/C-11).',
  },
  ja: {
    modelAlpha: 'アルファファクター',
    modelCell: 'アルファファクター',
    label: (k) => 'α' + k + '（無次元、0 から 1）',
    err: (k) => 'α' + k + ' は 0 から 1 までの数値で入力してください（例: 0.05 または 5%）。',
    hint: '例: 0.05 または 5%',
    size: (n) => 'アルファファクターモデルにはメンバーが 2 件から 4 件必要です。このグループは ' + n + ' 件です。',
    sizeReason: 'アルファファクターモデルにはメンバーが 2 件から 4 件必要',
    help: (n) => 'α_k は、ちょうど k 個のメンバーが故障する事象の割合です。α1 から α' + n + ' までを入力します。合計は 1 になるはずです（NUREG/CR-5485 p. 40）。',
    testingHelp: '時間差試験: α の値の元になったデータで、部品を時間をずらして順に試験した場合。同時試験: すべての部品を同時に試験した場合。α の値の出典に合う方式を選んでください（NUREG/CR-5485 p. 40、NASA/SP-2011-3421 pp. 7-9, 7-14）。',
    sumNone: 'α の合計: —',
    sumOk: (s) => 'α の合計: ' + s,
    sumNormalised: (s) => 'α の合計: ' + s + '。各 α を合計で割って使用します。',
    sumBad: (s) => 'α の合計: ' + s + '。1 でなければなりません（0.001 までの差は補正されます）。',
    placeholder: '試験方式を選んでください',
    staggered: '時間差試験',
    nonStaggered: '同時試験',
    applied: '適用中',
    notApplied: (r) => '未適用: ' + r,
    noScheme: '未適用: 試験方式が未指定',
    eta: '未適用: ETA モード',
    subset: (g, names) => 'CCF: ' + g + '（' + names.join(' + ') + '）',
    assumeAlpha: 'アルファファクターモデル: Q_k は、与えられたメンバーのうちちょうど k 個を故障させる各 CCF 事象の確率です。時間差試験では Q_k = α_k / C(m-1, k-1) · Q_t（NUREG/CR-5485 式 5.6 p. 40）、同時試験では α_t = Σ k·α_k として Q_k = k / C(m-1, k-1) · (α_k / α_t) · Q_t（式 5.7-5.9 p. 41、NUREG/CR-4780 Vol. 2 式 C.23-C.24 pp. C-10/C-11）です。',
  },
};

const sameList = (a, b) => JSON.stringify(a) === JSON.stringify(b);

async function run(url, label, root) {
  L.setSection('ccf_alpha[' + label + ']');
  const file = 'ccf_alpha_gui_' + label + '.json';
  fs.writeFileSync(path.join(root, file), documentText('FTA'));

  const app = await L.openApp(url, { viewport: { width: 1600, height: 1000 }, prefs: { 'fta.advanced': '1' } });
  const { page } = app;
  page.setDefaultTimeout(5000);
  /** Every change request to the CCF endpoints: {method, url, body}. */
  const reqs = [];
  /** One block of the run: an exception (UI missing) is one FAIL and the run goes on. */
  const part = async (name, fn, cleanup) => {
    try { await fn(); } catch (e) { L.check(name + ': did not complete', false, String((e && e.message) || e).split(String.fromCharCode(10))[0].slice(0, 300)); }
    if (cleanup) { try { await cleanup(); } catch (_e) { /* best effort */ } }
  };
  page.on('request', (r) => {
    if (['POST', 'PATCH', 'DELETE'].includes(r.method()) && r.url().includes('/api/ccf/groups')) {
      let body = null;
      try { body = r.postDataJSON(); } catch (_e) { body = null; }
      reqs.push({ method: r.method(), url: r.url(), body });
    }
  });

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
  const stored = (g) => (g ? JSON.stringify({ model: g.model, beta: g.beta, alpha: g.alpha, testing: g.testing, members: g.members }) : null);
  const rev = async () => (await app.api('get', '/revision')).revision;
  const row = (id) => page.locator('#tree-root li.fta-tree-item[data-id="' + id + '"] > .fta-tree-row');
  const groupRow = (gid) => page.locator('#tabpanel-ccf [data-role="groups"] tbody tr[data-id="' + gid + '"]');
  const editor = page.locator('#tabpanel-ccf [data-section="editor"]');
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
  const mk = async (name, members, alpha, testing, extra) => {
    const body = Object.assign({ name, model: 'alpha', alpha, members, source: '' }, testing ? { testing } : {}, extra || {});
    const r = await app.api('post', '/ccf/groups', body);
    if (r.__error) throw new Error('could not create ' + name + ': ' + JSON.stringify(r));
    return r.group.id;
  };
  const readRows = () => page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-ccf [data-role="groups"] tbody tr[data-id]')).map((tr) => {
    const o = { id: tr.dataset.id, selected: tr.classList.contains('is-selected') };
    for (const td of tr.querySelectorAll('td[data-col]')) o[td.dataset.col] = td.textContent.replace(/[ \s]+/g, ' ').trim();
    o.warnings = Array.from(tr.querySelectorAll('.ccf-status__warning')).map((w) => w.textContent.replace(/[ \s]+/g, ' ').trim());
    return o;
  }));
  const rowOf = async (gid) => (await readRows()).find((r) => r.id === gid);
  const openCcfTab = async () => {
    await app.clickTab('ccf');
    await page.waitForSelector('#tabpanel-ccf .anl-ccf[data-tab="ccf"]', { timeout: 8000 });
    await page.waitForTimeout(300);
  };
  const selectLeaves = async (ids) => {
    await row(ids[0]).click();
    for (const id of ids.slice(1)) await row(id).click({ modifiers: ['Control'] });
    await page.waitForTimeout(200);
  };
  const selectGroupRow = async (gid) => {
    await groupRow(gid).click();
    await page.waitForSelector('#tabpanel-ccf [data-section="editor"] input[data-field="name"]', { timeout: 5000 });
    await page.waitForTimeout(250);
  };
  /** Open a draft from a leaf selection. */
  const openDraft = async (ids) => {
    const cancel = editor.locator('[data-role="cancel"]');
    if (await cancel.count()) { await cancel.click(); await page.waitForTimeout(150); }
    await selectLeaves(ids);
    await page.locator('#tabpanel-ccf [data-role="new"]').click();
    await editor.locator('input[data-field="name"]').waitFor({ state: 'visible', timeout: 5000 });
  };
  const chooseModel = async (value) => { await editor.locator('select[data-field="model"]').selectOption(value); await page.waitForTimeout(250); };
  /** Type into a field; key 'Tab' only validates, 'Enter' commits / saves. */
  const typeInto = async (field, value, key) => {
    const input = editor.locator('input[data-field="' + field + '"]');
    await input.click();
    await page.keyboard.press('Control+A');
    if (String(value) === '') await page.keyboard.press('Delete');
    else await page.keyboard.type(String(value), { delay: 3 });
    if (key) await page.keyboard.press(key);
    await page.waitForTimeout(150);
  };
  const fillAlpha = async (values, key) => {
    for (let i = 0; i < values.length; i += 1) await typeInto('alpha' + (i + 1), values[i], i === values.length - 1 ? (key || 'Tab') : 'Tab');
  };
  const undoClick = async () => { await page.locator('#btn-undo').click(); await page.waitForTimeout(450); };
  const redoClick = async () => { await page.locator('#btn-redo').click(); await page.waitForTimeout(450); };

  /** The editor of the CCF tab as the user sees it. */
  const readEditor = () => page.evaluate(() => {
    const ed = document.querySelector('#tabpanel-ccf [data-section="editor"]');
    if (!ed) return null;
    const txt = (e) => (e ? e.textContent.replace(/[ \s]+/g, ' ').trim() : null);
    const vis = (e) => Boolean(e) && !e.hidden && e.offsetParent !== null;
    const q = (s) => ed.querySelector(s);
    const model = q('select[data-field="model"]');
    const testing = q('select[data-field="testing"]');
    const fieldset = q('fieldset[data-section="alpha"]');
    const inputs = Array.from(ed.querySelectorAll('input[data-field^="alpha"]')).map((i) => {
      const lab = i.id ? document.querySelector('label[for="' + i.id + '"]') : null;
      const err = ed.querySelector('p[data-error="' + i.dataset.field + '"]');
      return {
        field: i.dataset.field, value: i.value, label: lab ? txt(lab) : null, placeholder: i.getAttribute('placeholder'),
        describedby: i.getAttribute('aria-describedby') || '', errId: err ? err.id : null, invalid: i.getAttribute('aria-invalid') === 'true',
      };
    });
    const sum = q('p[data-role="alpha-sum"]');
    const used = q('p[data-role="alpha-used"]');
    const save = q('button[data-role="alpha-save"]');
    const status = q('p[data-role="group-status"]');
    const create = q('[data-role="create"]');
    const alphaHelp = q('p[data-role="alpha-help"]');
    const testingHelp = q('p[data-role="testing-help"]');
    return {
      modelValue: model ? model.value : null,
      modelOptions: model ? Array.from(model.options).map((o) => o.value) : null,
      modelDisabled: model ? model.disabled : null,
      beta: q('input[data-field="beta"]') ? q('input[data-field="beta"]').value : null,
      hasBetaInput: Boolean(q('input[data-field="beta"]')),
      hasFieldset: Boolean(fieldset),
      hasTesting: Boolean(testing),
      testingValue: testing ? testing.value : null,
      testingOptions: testing ? Array.from(testing.options).map((o) => o.value) : null,
      testingSelectedText: testing && testing.selectedOptions[0] ? testing.selectedOptions[0].textContent.trim() : null,
      testingOptionTexts: testing ? Array.from(testing.options).map((o) => o.textContent.trim()) : null,
      legend: fieldset ? txt(fieldset.querySelector('legend[data-role="alpha-legend"]')) : null,
      inputs,
      sumText: txt(sum), sumClass: sum ? sum.className : null,
      usedVisible: vis(used), usedText: txt(used),
      sizeText: txt(q('p[data-role="alpha-size"]')),
      resizeText: txt(q('p[data-role="alpha-resize"]')),
      hasSave: Boolean(save), saveDisabled: save ? (save.disabled || save.getAttribute('aria-disabled') === 'true') : null, saveText: txt(save),
      statusText: txt(status),
      statusWarnings: status ? Array.from(status.querySelectorAll('.ccf-status__warning')).map((w) => txt(w)) : [],
      createDisabled: create ? (create.disabled || create.getAttribute('aria-disabled') === 'true') : null,
      alphaHelpText: txt(alphaHelp), alphaHelpId: alphaHelp ? alphaHelp.id : null,
      testingHelpText: txt(testingHelp), testingHelpId: testingHelp ? testingHelp.id : null,
      testingErrId: q('p[data-error="testing"]') ? q('p[data-error="testing"]').id : null,
      focus: document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.field || null : null,
    };
  });
  /** The error paragraph of alpha<k>: text, visible, directly below the input. */
  const alphaErr = (k) => page.evaluate((kk) => {
    const input = document.querySelector('#tabpanel-ccf [data-section="editor"] input[data-field="alpha' + kk + '"]');
    const p = document.querySelector('#tabpanel-ccf [data-section="editor"] p[data-error="alpha' + kk + '"]');
    if (!input || !p) return null;
    const a = input.getBoundingClientRect();
    const b = p.getBoundingClientRect();
    const shown = !p.hidden && b.height > 0 && getComputedStyle(p).visibility !== 'hidden';
    return { text: p.textContent.replace(/[ \s]+/g, ' ').trim(), shown, below: b.top >= a.bottom - 2 && b.top - a.bottom < 80, invalid: input.getAttribute('aria-invalid') === 'true', value: input.value, alert: p.getAttribute('role') === 'alert' };
  }, k);
  /** Does the editor show what the server has for group `gid` (no stale editor)? */
  const editorAgrees = async (gid) => {
    const g = (await groups()).find((x) => x.id === gid);
    const r = await rowOf(gid);
    const e = await readEditor();
    if (!g || !e) return { ok: false, why: 'group or editor missing', g: Boolean(g), e: Boolean(e) };
    const why = [];
    if (e.modelValue !== g.model) why.push('model ' + e.modelValue + ' vs ' + g.model);
    if (g.model === 'alpha') {
      const want = (g.members || []).length >= 2 && g.members.length <= 4 ? g.members.length : 0;
      if (e.inputs.length !== want) why.push('alpha inputs ' + e.inputs.length + ' vs ' + want);
      for (let i = 0; i < e.inputs.length; i += 1) {
        const w = Array.isArray(g.alpha) && g.alpha[i] !== undefined ? String(g.alpha[i]) : '';
        if (e.inputs[i].value !== w) why.push('alpha' + (i + 1) + ' ' + e.inputs[i].value + ' vs ' + w);
      }
      if (e.testingValue !== (g.testing || '')) why.push('testing ' + e.testingValue + ' vs ' + g.testing);
    } else {
      if (e.hasTesting || e.hasFieldset) why.push('beta group shows alpha parts');
      if (e.beta !== String(g.beta)) why.push('beta ' + e.beta + ' vs ' + g.beta);
    }
    // the row's cell and the editor's line may separate the badge and the warning lines differently
    if (r && String(e.statusText).replace(/\s+/g, '') !== String(r.status).replace(/\s+/g, '')) why.push('status line "' + e.statusText + '" vs row "' + r.status + '"');
    if (r && !sameList(e.statusWarnings, r.warnings)) why.push('warning lines ' + JSON.stringify(e.statusWarnings) + ' vs ' + JSON.stringify(r.warnings));
    return { ok: why.length === 0, why };
  };
  const checkAgrees = async (what, gid) => {
    let res = null;
    await waitFor(async () => { res = await editorAgrees(gid); return res.ok; }, 4000);
    L.check(what + ': the editor shows what the server has (model, alpha fields, testing select, status line)', res && res.ok, res && res.why);
  };
  const jsonOf = (g) => stored(g);

  // ===== check 1: draft from 3 selected leaves ======================================
  await part('check 1', async () => {
    await openDoc(file);
    await openCcfTab();
    await openDraft(['A', 'B', 'C']);
    let e = await readEditor();
    L.check('check 1: the model select offers beta and alpha, default beta', Boolean(e) && sameList(e.modelOptions, ['beta', 'alpha']) && e.modelValue === 'beta' && e.modelDisabled === false, e);
    L.check('check 1: the beta draft has the beta field and no alpha fieldset and no testing select', e.hasBetaInput && !e.hasFieldset && !e.hasTesting, e);
    await chooseModel('alpha');
    e = await readEditor();
    L.check('check 1: choosing alpha shows exactly 3 inputs alpha1..alpha3 and no beta input',
      e.inputs.length === 3 && sameList(e.inputs.map((i) => i.field), ['alpha1', 'alpha2', 'alpha3']) && !e.hasBetaInput, e.inputs);
    L.check('check 1: the labels read "α1 (dimensionless, 0 to 1)" ... (en)', e.inputs.every((i, n) => i.label === T.en.label(n + 1)), e.inputs.map((i) => i.label));
    L.check('check 1: the fieldset legend reads "α values"', e.legend === 'α values', e.legend);
    const modelText = await page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-ccf [data-section="editor"] select[data-field="model"] option')).map((o) => o.textContent.trim()));
    L.check('check 1: the alpha option of the model select reads "Alpha factor"', modelText[1] === T.en.modelAlpha, modelText);
    await app.shot('ccf_alpha_draft_en');
    await app.setLanguage('ja');
    await page.waitForTimeout(500);
    e = await readEditor();
    L.check('check 1: the labels read "α1（無次元、0 から 1）" ... (ja)', Boolean(e) && e.inputs.length === 3 && e.inputs.every((i, n) => i.label === T.ja.label(n + 1)), e && e.inputs.map((i) => i.label));
    const modelJa = await page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-ccf [data-section="editor"] select[data-field="model"] option')).map((o) => o.textContent.trim()));
    L.check('check 1: the alpha option reads "アルファファクター" (ja)', modelJa[1] === T.ja.modelAlpha, modelJa);
    await app.shot('ccf_alpha_draft_ja');
    await app.setLanguage('en');
    await page.waitForTimeout(400);
  }, async () => { await app.setLanguage('en'); });

  // ===== check 2: field counts =======================================================
  await part('check 2', async () => {
    await openCcfTab();
    for (const [ids, n] of [[['D', 'E'], 2], [['A', 'B', 'C', 'D'], 4]]) {
      await openDraft(ids);
      await chooseModel('alpha');
      const e = await readEditor();
      L.check('check 2: ' + ids.length + ' members give ' + n + ' alpha inputs', e.inputs.length === n && e.hasFieldset, e.inputs.map((i) => i.field));
    }
    await openDraft(['A', 'B', 'C', 'D', 'E']);
    await chooseModel('alpha');
    const e = await readEditor();
    L.check('check 2: 5 members give no alpha input', e.inputs.length === 0, e.inputs.length);
    L.check('check 2: ... the size message "The alpha-factor model needs 2 to 4 members; this group has 5."', e.sizeText === T.en.size(5), e.sizeText);
    L.check('check 2: ... and Create is disabled', e.createDisabled === true, e);
    L.check('check 2: ... while the testing select stays', e.hasTesting === true, e);
    await app.setLanguage('ja');
    await page.waitForTimeout(400);
    const eJa5 = await readEditor();
    L.check('check 2: the size message reads "' + T.ja.size(5) + '" (ja)', Boolean(eJa5) && eJa5.sizeText === T.ja.size(5), eJa5 && eJa5.sizeText);
    await app.setLanguage('en');
    await page.waitForTimeout(300);
    await openDraft(['D', 'E']);
    await chooseModel('alpha');
    await editor.locator('[data-role="members"] li[data-member="E"] button[data-role="remove-member"]').click();
    await page.waitForTimeout(250);
    const one = await readEditor();
    L.check('check 2: a draft left with 1 member gives no input, the size message and Create disabled', one.inputs.length === 0 && one.sizeText === T.en.size(1) && one.createDisabled === true, one);
  }, async () => { await app.setLanguage('en'); });

  // ===== check 3: the testing select in a draft =======================================
  await part('check 3', async () => {
    await openCcfTab();
    await openDraft(['A', 'B', 'C']);
    await chooseModel('alpha');
    const e = await readEditor();
    L.check('check 3: the select has the options "", staggered, nonStaggered', Boolean(e) && e.hasTesting && sameList(e.testingOptions, ['', 'staggered', 'nonStaggered']), e && e.testingOptions);
    L.check('check 3: nothing is preselected: value "" and the text "Choose a testing scheme"', e.testingValue === '' && e.testingSelectedText === T.en.placeholder, e);
    L.check('check 3: the option texts read Staggered testing / Non-staggered testing', e.testingOptionTexts[1] === T.en.staggered && e.testingOptionTexts[2] === T.en.nonStaggered, e.testingOptionTexts);
    L.check('check 3: the testing help reads as the catalog', e.testingHelpText === T.en.testingHelp, e.testingHelpText);
    L.check('check 3: the testing help describes the source of the alpha values, not the plant of the user (no "members are tested")', !/members are tested/.test(e.testingHelpText || ''), e.testingHelpText);
    await app.setLanguage('ja');
    await page.waitForTimeout(400);
    const ej = await readEditor();
    L.check('check 3: (ja) nothing is preselected: value "" and the text "' + T.ja.placeholder + '"', Boolean(ej) && ej.hasTesting && ej.testingValue === '' && ej.testingSelectedText === T.ja.placeholder, ej && ej.testingSelectedText);
    L.check('check 3: (ja) the option texts read ' + T.ja.staggered + ' / ' + T.ja.nonStaggered, Boolean(ej) && ej.hasTesting && ej.testingOptionTexts[1] === T.ja.staggered && ej.testingOptionTexts[2] === T.ja.nonStaggered, ej && ej.testingOptionTexts);
    L.check('check 3: (ja) the testing help reads as the catalog', Boolean(ej) && ej.testingHelpText === T.ja.testingHelp, ej && ej.testingHelpText);
    await app.setLanguage('en');
    await page.waitForTimeout(300);
  }, async () => { await app.setLanguage('en'); });

  // ===== check 4: read errors =========================================================
  await part('check 4', async () => {
    await openCcfTab();
    await openDraft(['A', 'B', 'C']);
    await chooseModel('alpha');
    const n0 = reqs.length;
    for (const bad of ['abc', '1.5', '-0.1', '']) {
      if (bad === '') await typeInto('alpha2', '0.5', 'Tab');
      await typeInto('alpha2', bad, 'Tab');
      const err = await alphaErr(2);
      L.check('check 4: "' + bad + '" in alpha2 shows "' + T.en.err(2) + '" right under the field with aria-invalid', Boolean(err) && err.shown && err.text === T.en.err(2) && err.below && err.invalid && err.alert, err);
      L.check('check 4: "' + bad + '" sends no request', reqs.length === n0, reqs.slice(n0));
      if (bad === '1.5') await app.shot('ccf_alpha_error_en');
    }
    await typeInto('alpha2', '5%', 'Tab');
    const ok = await alphaErr(2);
    L.check('check 4: "5%" is read as 0.05 and the field shows 0.05, no error', Boolean(ok) && ok.value === '0.05' && !ok.shown && !ok.invalid, ok);
    const e = await readEditor();
    L.check('check 4: the placeholder of the alpha fields is "e.g. 0.05 or 5%"', e.inputs.every((i) => i.placeholder === T.en.hint), e.inputs.map((i) => i.placeholder));
    await app.setLanguage('ja');
    await page.waitForTimeout(400);
    await typeInto('alpha3', 'abc', 'Tab');
    const errJa = await alphaErr(3);
    L.check('check 4: the error reads "' + T.ja.err(3) + '" (ja)', Boolean(errJa) && errJa.shown && errJa.text === T.ja.err(3), errJa);
    const ja = await readEditor();
    L.check('check 4: the placeholder reads "例: 0.05 または 5%" (ja)', ja.inputs.every((i) => i.placeholder === T.ja.hint), ja.inputs.map((i) => i.placeholder));
    await app.setLanguage('en');
    await page.waitForTimeout(400);
    L.check('check 4: no request was sent by any of the above', reqs.length === n0, reqs.slice(n0));
  }, async () => { await app.setLanguage('en'); });

  // ===== check 4 (FN-46 table): every input of number_inputs.json into alpha1 ==========
  await part('check 4 (FN-46 table)', async () => {
    await openCcfTab();
    await openDraft(['A', 'B', 'C']);
    await chooseModel('alpha');
    const n0 = reqs.length;
    const bad = [];
    for (const item of VECTORS.inputs) {
      const want = item.expect.alpha_k;
      await typeInto('alpha1', item.text, 'Tab');
      const got = await alphaErr(1);
      if (!got) { bad.push({ text: item.text, why: 'no alpha1 field or error paragraph' }); break; }
      if (want.ok) {
        const shown = Number(got.value);
        const close = got.value.trim() !== '' && Number.isFinite(shown) && Math.abs(shown - want.value) <= 1e-12 * Math.abs(want.value);
        if (got.shown || got.invalid || !close) bad.push({ text: item.text, want, got });
      } else if (!(got.shown && got.invalid && got.text === T.en.err(1))) {
        bad.push({ text: item.text, want, got });
      }
    }
    L.check('check 4 (FN-46 table): all ' + VECTORS.inputs.length + ' inputs of fixtures/number_inputs.json give the alpha_k result in alpha1 (accepted: no error, value shown within 1e-12; refused: the error text and aria-invalid)', bad.length === 0, bad.slice(0, 6));
    L.check('check 4 (FN-46 table): no request was sent', reqs.length === n0, reqs.slice(n0));
  });

  // ===== check 5: the live sum, four states ===========================================
  await part('check 5', async () => {
    await openCcfTab();
    await openDraft(['D', 'E']);
    await chooseModel('alpha');
    let e = await readEditor();
    L.check('check 5: state none (empty fields): "Sum of α: —"', e.sumText === T.en.sumNone, e.sumText);
    await openDraft(['A', 'B', 'C']);
    await chooseModel('alpha');
    await typeInto('alpha1', '0.955');
    await typeInto('alpha2', '0.034');
    e = await readEditor();
    L.check('check 5: state none with only 2 of 3 values: "Sum of α: —"', e.sumText === T.en.sumNone, e.sumText);
    await typeInto('alpha3', '0.011');
    e = await readEditor();
    L.check('check 5: state ok (0.955, 0.034, 0.011): "Sum of α: 1" (live, nothing committed yet)', e.sumText === T.en.sumOk('1') && !e.usedVisible, e);
    await openDraft(['D', 'E']);
    await chooseModel('alpha');
    await typeInto('alpha1', '0.9');
    await typeInto('alpha2', '0.1005');
    e = await readEditor();
    L.check('check 5: state normalised (0.9, 0.1005): "Sum of α: 1.0005. Each α is divided by the sum." and the values used are listed',
      e.sumText === T.en.sumNormalised('1.0005') && e.usedVisible && /^Values used: /.test(e.usedText || '') && /ccf-sum--note/.test(e.sumClass || ''), e);
    await typeInto('alpha2', '0.2');
    e = await readEditor();
    L.check('check 5: state bad (0.9, 0.2): "Sum of α: 1.1. It must be 1 ..." with class ccf-sum--bad, used values hidden',
      e.sumText === T.en.sumBad('1.1') && /ccf-sum--bad/.test(e.sumClass || '') && !e.usedVisible, e);
    await typeInto('name', 'Bad sum draft');
    e = await readEditor();
    L.check('check 5: a bad sum is not an input error: Create is enabled once the name is typed', e.createDisabled === false && e.inputs.every((i) => !i.invalid), e);
    await app.shot('ccf_alpha_sum_bad');
    await app.setLanguage('ja');
    await page.waitForTimeout(400);
    e = await readEditor();
    L.check('check 5: the bad sum reads "' + T.ja.sumBad('1.1') + '" (ja)', Boolean(e) && e.sumText === T.ja.sumBad('1.1'), e && e.sumText);
    await app.setLanguage('en');
    await page.waitForTimeout(300);
  }, async () => { await app.setLanguage('en'); });

  // ===== check 6: create a 3-member group without a scheme ===========================
  let reliefId = null;
  await part('check 6', async () => {
    await openDoc(file);
    await openCcfTab();
    await openDraft(['A', 'B', 'C']);
    await chooseModel('alpha');
    await typeInto('name', 'Relief valves');
    await fillAlpha(['0.955', '0.034', '0.011']);
    const e = await readEditor();
    L.check('check 6: Create is enabled with a name and three valid alpha values and NO scheme', e.createDisabled === false && e.testingValue === '', e);
    const n0 = reqs.length;
    const rev0 = await rev();
    await editor.locator('[data-role="create"]').click();
    const got = await waitFor(async () => Boolean(await byName('Relief valves')));
    const g = await byName('Relief valves');
    reliefId = g ? g.id : null;
    L.check('check 6: Create makes the alpha group: model alpha, alpha list, testing null, members A B C, beta null',
      got && g.model === 'alpha' && sameList(g.alpha, [0.955, 0.034, 0.011]) && g.testing === null && sameList(g.members, ['A', 'B', 'C']) && g.beta === null, g);
    L.check('check 6: one POST without a "testing" key, and one revision', reqs.length === n0 + 1 && reqs[n0].method === 'POST' && !('testing' in (reqs[n0].body || {})) && (await rev()) === rev0 + 1, reqs.slice(n0));
    await page.waitForTimeout(300);
    const r = await rowOf(reliefId);
    L.check('check 6: the row status reads exactly "Not applied: testing scheme missing"', Boolean(r) && r.status === T.en.noScheme, r);
    L.check('check 6: the Model cell reads "Alpha factor" and the Parameters cell "α = (0.955, 0.034, 0.011)"', Boolean(r) && r.model === T.en.modelCell && r.params === 'α = (0.955, 0.034, 0.011)', r);
    await app.setLanguage('ja');
    await page.waitForTimeout(400);
    const rj = await rowOf(reliefId);
    L.check('check 6: the status reads "未適用: 試験方式が未指定" (ja)', Boolean(rj) && rj.status === T.ja.noScheme, rj);
    L.check('check 6: the Model cell reads "アルファファクター" (ja)', Boolean(rj) && rj.model === T.ja.modelCell, rj);
    await app.setLanguage('en');
    await page.waitForTimeout(300);
    // after a reload the editor of the stored group shows the placeholder
    await reload();
    await openCcfTab();
    await selectGroupRow(reliefId);
    const after = await readEditor();
    L.check('check 3: after reload the existing group with a null scheme shows the placeholder selected (nothing preselected)', after.testingValue === '' && after.testingSelectedText === T.en.placeholder, after);
    L.check('check 6: the editor status line reads "Not applied: testing scheme missing"', after.statusText === T.en.noScheme, after.statusText);
  }, async () => { await app.setLanguage('en'); });

  // ===== check 7: choose a scheme; undo / redo ========================================
  await part('check 7', async () => {
    if (!reliefId) throw new Error('no group from check 6');
    await openCcfTab();
    await selectGroupRow(reliefId);
    const select = () => editor.locator('select[data-field="testing"]');
    const choose = async (value, what, expectStatus, expectTesting) => {
      const n0 = reqs.length;
      const r0 = await rev();
      await select().selectOption(value);
      await waitFor(async () => (await rev()) > r0);
      await page.waitForTimeout(400);
      const g = await byName('Relief valves');
      L.check('check 7: ' + what + ' sends one PATCH and stores ' + JSON.stringify(expectTesting), reqs.length === n0 + 1 && reqs[n0].method === 'PATCH' && g.testing === expectTesting, { reqs: reqs.slice(n0), testing: g && g.testing });
      const r = await rowOf(reliefId);
      L.check('check 7: ' + what + ': the row status reads "' + expectStatus + '"', Boolean(r) && r.status === expectStatus, r);
      await checkAgrees('check 7 (' + what + ')', reliefId);
    };
    await choose('staggered', 'choosing Staggered testing', T.en.applied, 'staggered');
    await choose('nonStaggered', 'choosing Non-staggered testing', T.en.applied, 'nonStaggered');
    await choose('', 'choosing the placeholder', T.en.noScheme, null);
    await choose('staggered', 'choosing Staggered testing again', T.en.applied, 'staggered');
    await undoClick();
    L.check('check 7: Undo returns to no scheme (GET)', await waitFor(async () => (await byName('Relief valves')).testing === null));
    await checkAgrees('check 7 (after Undo)', reliefId);
    await redoClick();
    L.check('check 7: Redo brings staggered back (GET)', await waitFor(async () => (await byName('Relief valves')).testing === 'staggered'));
    await checkAgrees('check 7 (after Redo)', reliefId);
    await app.shot('ccf_alpha_applied_en');
    await app.setLanguage('ja');
    await page.waitForTimeout(500);
    const rja = await rowOf(reliefId);
    const eja = await readEditor();
    L.check('check 7: (ja) the applied row reads "' + T.ja.applied + '"', Boolean(rja) && rja.status === T.ja.applied, rja);
    L.check('check 7: (ja) the editor status line reads "' + T.ja.applied + '" and the testing select shows ' + T.ja.staggered, Boolean(eja) && eja.statusText === T.ja.applied && eja.testingSelectedText === T.ja.staggered, eja && { status: eja.statusText, testing: eja.testingSelectedText });
    await app.setLanguage('en');
    await page.waitForTimeout(300);
  }, async () => { await app.setLanguage('en'); });

  // ===== checks 8 and 9: normalised and bad-sum groups ================================
  await part('checks 8 and 9', async () => {
    const normId = await mk('Normalised pair', ['D', 'E'], [0.9005, 0.1], 'staggered');
    await reload();
    await openCcfTab();
    let r = await rowOf(normId);
    L.check('check 8: the sum-1.0005 group reads Applied with a "Warning:" line carrying the sum',
      Boolean(r) && r.status.startsWith(T.en.applied) && r.warnings.length === 1 && r.warnings[0] === T.en.normalised, r);
    await selectGroupRow(normId);
    let e = await readEditor();
    L.check('check 8: the editor status line shows the same warning', e.statusText.startsWith(T.en.applied) && sameList(e.statusWarnings, [T.en.normalised]), e);
    L.check('check 8: the editor shows the sum note and the values used', e.sumText === T.en.sumNormalised('1.0005') && e.usedVisible, e);
    // bad sum: made by the GUI, with a scheme chosen in the draft
    await openDraft(['F', 'G']);
    await chooseModel('alpha');
    await typeInto('name', 'Bad sum pair');
    await fillAlpha(['0.9', '0.11']);
    await editor.locator('select[data-field="testing"]').selectOption('nonStaggered');
    const n0 = reqs.length;
    await editor.locator('[data-role="create"]').click();
    await waitFor(async () => Boolean(await byName('Bad sum pair')));
    const g = await byName('Bad sum pair');
    L.check('check 9: the bad-sum group is created (Create enabled) with testing nonStaggered sent with the POST', Boolean(g) && g.testing === 'nonStaggered' && reqs.length === n0 + 1 && reqs[n0].body.testing === 'nonStaggered', g);
    await page.waitForTimeout(300);
    r = await rowOf(g.id);
    L.check('check 9: the row reads "Not applied: α values add up to 1.01, not 1"', Boolean(r) && r.status === T.en.badSum, r);
    await app.api('del', '/ccf/groups/' + g.id);
    await app.api('del', '/ccf/groups/' + normId);
  });

  // ===== check 10: member changes, the save button, blur sends nothing ==================
  await part('check 10', async () => {
    await reload();
    await openCcfTab();
    const gid = reliefId;
    await selectGroupRow(gid);
    const before = await byName('Relief valves');
    let e = await readEditor();
    L.check('check 10: an alpha group always has the "Save α values" button, disabled while nothing changed', e.hasSave && e.saveDisabled === true && e.saveText === 'Save α values', e);
    // blur only validates
    const n0 = reqs.length;
    await typeInto('alpha1', '0.9', 'Tab');
    await page.waitForTimeout(300);
    L.check('check 10: editing alpha1 and leaving the field sends no request', reqs.length === n0, reqs.slice(n0));
    e = await readEditor();
    L.check('check 10: ... and the save button is enabled now', e.saveDisabled === false, e);
    await editor.locator('input[data-field="alpha1"]').press('Escape');
    await typeInto('alpha1', '0.955', 'Tab');
    // remove one member
    await editor.locator('[data-role="members"] li[data-member="C"] button[data-role="remove-member"]').click();
    await waitFor(async () => sameList((await byName('Relief valves')).members, ['A', 'B']));
    await page.waitForTimeout(400);
    const afterRemove = await byName('Relief valves');
    L.check('check 10: removing a member leaves the stored alpha as it was (GET before / after)', sameList(afterRemove.alpha, before.alpha) && sameList(afterRemove.members, ['A', 'B']), afterRemove);
    e = await readEditor();
    L.check('check 10: 2 fields remain and keep alpha1 = 0.955, alpha2 = 0.034', e.inputs.length === 2 && e.inputs[0].value === '0.955' && e.inputs[1].value === '0.034', e.inputs);
    L.check('check 10: the resize hint reads "Members: 2, α values stored: 3. ..."', e.resizeText === T.en.resize(2, 3), e.resizeText);
    L.check('check 10: the save button is enabled (the stored length differs)', e.hasSave && e.saveDisabled === false, e);
    let r = await rowOf(gid);
    L.check('check 10: the row status reads "Not applied: α values: 3, members: 2"', Boolean(r) && r.status === T.en.lengthMismatch, r);
    await app.shot('ccf_alpha_resize_en');
    // fix the values and save with the button
    await typeInto('alpha1', '0.9', 'Tab');
    await typeInto('alpha2', '0.1', 'Tab');
    const n1 = reqs.length;
    await editor.locator('button[data-role="alpha-save"]').click();
    await waitFor(async () => sameList((await byName('Relief valves')).alpha, [0.9, 0.1]));
    await page.waitForTimeout(300);
    L.check('check 10: one click on Save α values sends exactly one PATCH with the two values', reqs.length === n1 + 1 && reqs[n1].method === 'PATCH' && sameList(reqs[n1].body.alpha, [0.9, 0.1]), reqs.slice(n1));
    r = await rowOf(gid);
    L.check('check 10: the row reads Applied again', Boolean(r) && r.status === T.en.applied, r);
    await checkAgrees('check 10 (after save)', gid);
    // add the member back
    await row('C').click();
    await page.locator('#tabpanel-ccf [data-role="add-selected"]').click();
    await waitFor(async () => sameList((await byName('Relief valves')).members, ['A', 'B', 'C']));
    await page.waitForTimeout(400);
    const afterAdd = await byName('Relief valves');
    e = await readEditor();
    L.check('check 10: adding the member back leaves the stored alpha as it was ([0.9, 0.1])', sameList(afterAdd.alpha, [0.9, 0.1]), afterAdd);
    L.check('check 10: 3 fields, alpha3 empty, the hint shown and the save button disabled until alpha3 is valid', e.inputs.length === 3 && e.inputs[2].value === '' && Boolean(e.resizeText) && e.saveDisabled === true, e);
    // a server refusal with detail.index marks that field
    await page.route('**/api/ccf/groups/*', async (route) => {
      if (route.request().method() === 'PATCH') {
        await route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ ok: false, error: { code: 'INVALID_FIELD', message: "'alpha' item 1 must be a number from 0 to 1.", detail: { field: 'alpha', index: 1 } } }) });
      } else { await route.continue(); }
    });
    await typeInto('alpha3', '0.05', 'Tab');
    await editor.locator('button[data-role="alpha-save"]').click();
    await page.waitForTimeout(600);
    const refused = await alphaErr(2);
    L.check('check 10: a refusal INVALID_FIELD with detail.index 1 marks alpha2 (error text and aria-invalid)', Boolean(refused) && refused.shown && refused.invalid && refused.text.length > 0, refused);
    await page.unroute('**/api/ccf/groups/*');
    // a refusal of alpha WITHOUT detail.index shows in p[data-error="alpha"] under the fieldset
    const refuse = async (detail, message) => page.route('**/api/ccf/groups/*', async (route) => {
      if (route.request().method() === 'PATCH') {
        await route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ ok: false, error: { code: 'INVALID_FIELD', message, detail } }) });
      } else { await route.continue(); }
    });
    const readError = (kind) => page.evaluate((k) => {
      const p = document.querySelector('#tabpanel-ccf [data-section="editor"] p[data-error="' + k + '"]');
      return p ? { text: p.textContent.replace(/[ \s]+/g, ' ').trim(), shown: !p.hidden && p.getBoundingClientRect().height > 0 } : null;
    }, kind);
    await refuse({ field: 'alpha' }, 'The alpha values were refused by the stub.');
    await typeInto('alpha3', '0.05', 'Tab');
    await editor.locator('button[data-role="alpha-save"]').click();
    await page.waitForTimeout(600);
    const groupLevel = await readError('alpha');
    L.check('check 10: a refusal INVALID_FIELD for alpha without detail.index shows its text in p[data-error="alpha"]', Boolean(groupLevel) && groupLevel.shown && groupLevel.text.length > 0, groupLevel);
    await page.unroute('**/api/ccf/groups/*');
    // a refusal of testing shows in p[data-error="testing"] with the catalog prefix
    await reload();
    await openCcfTab();
    await selectGroupRow(gid);
    await refuse({ field: 'testing' }, 'The testing value was refused by the stub.');
    await editor.locator('select[data-field="testing"]').selectOption('nonStaggered');
    await page.waitForTimeout(600);
    const testingErr = await readError('testing');
    L.check('check 10: a refusal of testing shows "' + T.en.testingSaveFail + ' ..." in p[data-error="testing"]', Boolean(testingErr) && testingErr.shown && testingErr.text.startsWith(T.en.testingSaveFail), testingErr);
    await page.unroute('**/api/ccf/groups/*');
    await reload();
    await openCcfTab();
    await selectGroupRow(gid);
    // Enter in the last field saves the whole list in one PATCH
    await typeInto('alpha2', '0.05', 'Tab');
    const n2 = reqs.length;
    await typeInto('alpha3', '0.05', 'Enter');
    await waitFor(async () => sameList((await byName('Relief valves')).alpha, [0.9, 0.05, 0.05]));
    await page.waitForTimeout(300);
    L.check('check 10: Enter in an alpha field saves the whole list in exactly one PATCH', reqs.length === n2 + 1 && reqs[n2].method === 'PATCH' && sameList(reqs[n2].body.alpha, [0.9, 0.05, 0.05]), reqs.slice(n2));
    await checkAgrees('check 10 (after Enter)', gid);
    r = await rowOf(gid);
    L.check('check 10: the row reads Applied', Boolean(r) && r.status === T.en.applied, r);
  }, async () => { try { await page.unroute('**/api/ccf/groups/*'); } catch (_e) { /* not routed */ } });

  // ===== check 11: model switch is local until the parameters are committed =============
  await part('check 11', async () => {
    const gid = reliefId;
    await reload();
    await openCcfTab();
    await selectGroupRow(gid);
    const base = jsonOf(await byName('Relief valves'));
    const rowBefore = await rowOf(gid);
    const n0 = reqs.length;
    await chooseModel('beta');
    let e = await readEditor();
    L.check('check 11: choosing beta sends NO request', reqs.length === n0, reqs.slice(n0));
    L.check('check 11: ... the table row is unchanged', sameList(await rowOf(gid), rowBefore) || JSON.stringify(await rowOf(gid)) === JSON.stringify(rowBefore), await rowOf(gid));
    L.check('check 11: ... the beta field appears (empty) and the alpha fieldset and the testing select are removed', e.hasBetaInput && e.beta === '' && !e.hasFieldset && !e.hasTesting, e);
    L.check('check 11: ... the server still has the alpha group', jsonOf(await byName('Relief valves')) === base);
    // Escape in the select discards the local change
    await editor.locator('select[data-field="model"]').focus();
    await page.keyboard.press('Escape');
    await page.waitForTimeout(250);
    e = await readEditor();
    L.check('check 11: Escape in the model select discards the local change (alpha block back, select shows alpha)', e.modelValue === 'alpha' && e.hasFieldset && !e.hasBetaInput, e);
    await chooseModel('beta');
    await chooseModel('alpha');
    e = await readEditor();
    L.check('check 11: choosing the stored model again discards it too', e.modelValue === 'alpha' && e.hasFieldset && reqs.length === n0, e);
    // commit beta: one PATCH {model: beta, beta}
    await chooseModel('beta');
    const r0 = await rev();
    await typeInto('beta', '0.1', 'Enter');
    await waitFor(async () => (await byName('Relief valves')).model === 'beta');
    await page.waitForTimeout(300);
    const g = await byName('Relief valves');
    L.check('check 11: committing a valid beta sends one PATCH {model: "beta", beta: 0.1}', reqs.length === n0 + 1 && reqs[n0].method === 'PATCH' && reqs[n0].body.model === 'beta' && reqs[n0].body.beta === 0.1, reqs.slice(n0));
    L.check('check 11: ... the group is beta with alpha and testing null, one undo step', g.model === 'beta' && g.beta === 0.1 && g.alpha === null && g.testing === null && (await rev()) === r0 + 1, g);
    await checkAgrees('check 11 (beta committed)', gid);
    await undoClick();
    L.check('check 11: Undo restores the alpha group (GET equality)', await waitFor(async () => jsonOf(await byName('Relief valves')) === base));
    await checkAgrees('check 11 (Undo restores the alpha block)', gid);
    await redoClick();
    L.check('check 11: Redo gives the beta group again', await waitFor(async () => (await byName('Relief valves')).model === 'beta'));
    await checkAgrees('check 11 (Redo shows the beta block)', gid);
    // back to alpha: local until Save α values; the scheme chosen in the local block goes with the switch
    const n1 = reqs.length;
    await chooseModel('alpha');
    L.check('check 11: choosing alpha on the beta group sends NO request', reqs.length === n1, reqs.slice(n1));
    e = await readEditor();
    L.check('check 11: ... three empty alpha fields (the member count) and the testing placeholder', e.inputs.length === 3 && e.inputs.every((i) => i.value === '') && e.testingValue === '', e);
    await fillAlpha(['0.9', '0.05', '0.05']);
    await editor.locator('select[data-field="testing"]').selectOption('staggered');
    await page.waitForTimeout(300);
    L.check('check 11: choosing a scheme in the local block sends nothing either', reqs.length === n1, reqs.slice(n1));
    await editor.locator('button[data-role="alpha-save"]').click();
    await waitFor(async () => (await byName('Relief valves')).model === 'alpha');
    await page.waitForTimeout(300);
    const back = await byName('Relief valves');
    L.check('check 11: Save α values sends one PATCH {model: "alpha", alpha, testing}', reqs.length === n1 + 1 && reqs[n1].body.model === 'alpha' && sameList(reqs[n1].body.alpha, [0.9, 0.05, 0.05]), reqs.slice(n1));
    L.check('check 11: ... the group is alpha again with beta null and the scheme', back.model === 'alpha' && back.beta === null && back.testing === 'staggered', back);
    await checkAgrees('check 11 (alpha saved)', gid);
    await undoClick();
    L.check('check 11: Undo goes back to the beta group', await waitFor(async () => (await byName('Relief valves')).model === 'beta'));
    await checkAgrees('check 11 (Undo shows the beta block)', gid);
    // leave the document as it was: alpha, staggered
    await app.api('patch', '/ccf/groups/' + gid, { model: 'alpha', alpha: [0.955, 0.034, 0.011], testing: 'staggered' });
    await reload();
  });

  // ===== check 12: undo / redo keep the editor in step ================================
  await part('check 12', async () => {
    const gid = reliefId;
    await openCcfTab();
    await selectGroupRow(gid);
    const step = async (what, action) => {
      const before = jsonOf(await byName('Relief valves'));
      const r0 = await rev();
      await action();
      await waitFor(async () => (await rev()) > r0);
      await page.waitForTimeout(400);
      const after = jsonOf(await byName('Relief valves'));
      L.check('check 12: ' + what + ' is exactly one revision', (await rev()) === r0 + 1, { r0, now: await rev() });
      await checkAgrees('check 12 (' + what + ')', gid);
      await undoClick();
      L.check('check 12: one Undo undoes ' + what + ' (GET equality)', await waitFor(async () => jsonOf(await byName('Relief valves')) === before));
      await checkAgrees('check 12 (' + what + ', after Undo)', gid);
      await redoClick();
      L.check('check 12: Redo redoes ' + what + ' (GET equality)', await waitFor(async () => jsonOf(await byName('Relief valves')) === after));
      await checkAgrees('check 12 (' + what + ', after Redo)', gid);
    };
    await step('an alpha save', async () => {
      await fillAlpha(['0.9', '0.06', '0.04'], 'Tab');
      await editor.locator('button[data-role="alpha-save"]').click();
    });
    await step('a testing change', async () => { await editor.locator('select[data-field="testing"]').selectOption('nonStaggered'); });
    await step('a member change (remove)', async () => {
      await editor.locator('[data-role="members"] li[data-member="C"] button[data-role="remove-member"]').click();
    });
    // Tab from alpha1 to alpha2 does not rebuild the editor: text typed into alpha2 survives
    await selectGroupRow(gid);
    await editor.locator('input[data-field="alpha1"]').click();
    await page.keyboard.press('Tab');
    await page.keyboard.type('0.07', { delay: 5 });
    await page.waitForTimeout(700);
    const e = await readEditor();
    L.check('check 12: after Tab from alpha1 the typed text in alpha2 survives and alpha2 keeps the focus', Boolean(e) && e.inputs[1] && e.inputs[1].value.endsWith('0.07') && e.focus === 'alpha2', e && { alpha2: e.inputs[1] && e.inputs[1].value, focus: e.focus });
    await page.keyboard.press('Escape');
    // creating through the GUI: one undo removes it, one redo brings it back
    await openCcfTab();
    await openDraft(['F', 'G']);
    await chooseModel('alpha');
    await typeInto('name', 'Undo pair');
    await fillAlpha(['0.9', '0.1']);
    const r0 = await rev();
    await editor.locator('[data-role="create"]').click();
    await waitFor(async () => Boolean(await byName('Undo pair')));
    L.check('check 12: creating is one revision', (await rev()) === r0 + 1);
    await undoClick();
    L.check('check 12: one Undo removes the created group', await waitFor(async () => !(await byName('Undo pair'))));
    // no stale editor: after the Undo the editor does not show the removed group any more
    const staleName = await waitFor(async () => {
      const shown = await editor.locator('input[data-field="name"]').count() ? await editor.locator('input[data-field="name"]').inputValue() : null;
      return shown !== 'Undo pair';
    }, 4000);
    L.check('check 12: after the Undo of the create the editor does not show the removed group (no stale editor)', staleName);
    const rowsAfterUndo = await readRows();
    L.check('check 12: ... and the table has no row for it', !rowsAfterUndo.some((r) => r.name === 'Undo pair'), rowsAfterUndo.map((r) => r.id));
    await redoClick();
    L.check('check 12: one Redo brings it back', await waitFor(async () => Boolean(await byName('Undo pair'))));
    const pair = await byName('Undo pair');
    if (pair) {
      await selectGroupRow(pair.id);
      await checkAgrees('check 12 (create, after Redo)', pair.id);
    }
    if (pair) await app.api('del', '/ccf/groups/' + pair.id);
    // restore the 3-member group for the checks that follow
    await app.api('patch', '/ccf/groups/' + gid, { members: ['A', 'B', 'C'], alpha: [0.955, 0.034, 0.011], testing: 'staggered' });
    await reload();
  });

  // ===== check 13: cut sets and highlight =============================================
  await part('check 13', async () => {
    const gid = reliefId;
    const cur = await byName('Relief valves');
    L.check('check 13: setup: the 3-member group is applied', cur && cur.status && cur.status.applied === true, cur && cur.status);
    await app.clickTab('cutsets');
    await page.waitForSelector('#tabpanel-cutsets tbody tr[data-rank]', { timeout: 15000 });
    await app.settle(400);
    const readEvents = () => page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-cutsets tr[data-rank] .anl-event--ccf[data-ccf-role="event"][data-ccf-group]')).map((e) => ({ group: e.dataset.ccfGroup, text: e.textContent.replace(/[ \s]+/g, ' ').trim() })));
    const evs = await readEvents();
    const labels = Array.from(new Set(evs.map((e) => e.text))).sort();
    const want = [
      T.en.subset('Relief valves', ['Valve A', 'Valve B']), T.en.subset('Relief valves', ['Valve A', 'Valve C']),
      T.en.subset('Relief valves', ['Valve B', 'Valve C']), T.en.subset('Relief valves', ['Valve A', 'Valve B', 'Valve C']),
    ].sort();
    L.check('check 13: the cut sets carry 4 CCF labels "CCF: Relief valves (Valve A + Valve B)" ...', sameList(labels, want) && evs.every((e) => e.group === gid), labels);
    const highlight = async (rowText) => {
      await page.locator('#tabpanel-cutsets tr[data-rank]').filter({ has: page.locator('.anl-event--ccf[data-ccf-role="event"]', { hasText: rowText }) }).first().click();
      await page.waitForTimeout(500);
      return page.evaluate(() => ({
        tree: Array.from(document.querySelectorAll('#tree-root .fta-tree-row.is-highlighted')).map((r) => r.closest('li.fta-tree-item').dataset.id).sort(),
        diagram: Array.from(document.querySelectorAll('#diagram-root g.node.is-highlighted')).map((g) => ((g.querySelector('title') || {}).textContent || '').trim()).filter((t) => !/__(event|gate)$/.test(t)),
      }));
    };
    let hl = await highlight('(Valve A + Valve B)');
    L.check('check 13: clicking the pair row A + B highlights exactly 2 members in the tree (A, B)', sameList(hl.tree, ['A', 'B']), hl);
    L.check('check 13: ... and 2 boxes in the diagram', hl.diagram.length === 2, hl);
    hl = await highlight('(Valve A + Valve B + Valve C)');
    L.check('check 13: the triple row highlights 3 members (A, B, C)', sameList(hl.tree, ['A', 'B', 'C']) && hl.diagram.length === 3, hl);
    await app.shot('ccf_alpha_highlight');
    await app.setLanguage('ja');
    await page.waitForTimeout(500);
    await app.clickTab('cutsets');
    await page.waitForSelector('#tabpanel-cutsets tbody tr[data-rank]', { timeout: 15000 });
    await app.settle(400);
    const jaLabels = Array.from(new Set((await readEvents()).map((e) => e.text))).sort();
    const jaWant = [
      T.ja.subset('Relief valves', ['Valve A', 'Valve B']), T.ja.subset('Relief valves', ['Valve A', 'Valve C']),
      T.ja.subset('Relief valves', ['Valve B', 'Valve C']), T.ja.subset('Relief valves', ['Valve A', 'Valve B', 'Valve C']),
    ].sort();
    L.check('check 13: the labels read "CCF: Relief valves（Valve A + Valve B）" ... (ja)', sameList(jaLabels, jaWant), jaLabels);
    await app.setLanguage('en');
    await page.waitForTimeout(300);
  }, async () => { await app.setLanguage('en'); });

  // ===== check 14: the alpha assumption ===============================================
  await part('check 14', async () => {
    await openCcfTab();
    const readAssume = () => page.evaluate(() => {
      const li = document.querySelector('#tabpanel-ccf [data-section="assumptions"] li[data-assumption="alpha"]');
      return li ? li.textContent.replace(/[ \s]+/g, ' ').trim() : null;
    });
    L.check('check 14: with an alpha group the seventh assumption reads as the catalog (en)', (await readAssume()) === T.en.assumeAlpha, await readAssume());
    await app.setLanguage('ja');
    await page.waitForTimeout(500);
    L.check('check 14: ... and in Japanese', (await readAssume()) === T.ja.assumeAlpha, await readAssume());
    await app.setLanguage('en');
    await page.waitForTimeout(300);
    const six = await page.evaluate(() => Array.from(document.querySelectorAll('#tabpanel-ccf [data-section="assumptions"] li[data-assumption]')).map((l) => l.dataset.assumption));
    L.check('check 14: the six F2 assumptions stay beside it', ['model', 'qt', 'beta', 'split', 'headline', 'sampling'].every((k) => six.includes(k)), six);
    // with only a beta group the alpha bullet goes
    for (const g of await groups()) await app.api('del', '/ccf/groups/' + g.id);
    await mk('Feed pumps', ['D', 'E'], null, null, { model: 'beta', beta: 0.1, alpha: undefined });
    await reload();
    await openCcfTab();
    L.check('check 14: with only a beta group there is no alpha assumption', (await readAssume()) === null, await readAssume());
  }, async () => { await app.setLanguage('en'); });

  // ===== check 18: the editor of a beta group =========================================
  await part('check 18', async () => {
    await openCcfTab();
    const feed = await byName('Feed pumps');
    await selectGroupRow(feed.id);
    const e = await readEditor();
    L.check('check 18: the beta editor has the model select with 2 options (beta, alpha), value beta', sameList(e.modelOptions, ['beta', 'alpha']) && e.modelValue === 'beta', e);
    L.check('check 18: ... the beta input with 0.1 and the group status line "Applied"', e.hasBetaInput && e.beta === '0.1' && e.statusText === T.en.applied, e);
    L.check('check 18: ... and NO testing select, NO alpha fieldset, no alpha/testing help paragraphs', !e.hasTesting && !e.hasFieldset && e.alphaHelpText === null && e.testingHelpText === null, e);
    const f2 = await page.evaluate(() => {
      const ed = document.querySelector('#tabpanel-ccf [data-section="editor"]');
      return ['input[data-field="name"]', 'input[data-field="source"]', '[data-role="members"]', '[data-role="delete"]', 'p[data-error="beta"]'].map((s) => [s, Boolean(ed.querySelector(s))]);
    });
    L.check('check 18: the F2 selectors still resolve', f2.every((p) => p[1]), f2);
    await app.shot('ccf_beta_editor_with_model_select');
  });

  // ===== checks 19, 17: help, aria, warning lines; arrow keys ===========================
  let helpId = null;
  await part('checks 19 and 17', async () => {
    for (const g of await groups()) await app.api('del', '/ccf/groups/' + g.id);
    helpId = await mk('Help valves', ['A', 'B', 'C'], [0.9555, 0.034, 0.011], 'staggered');
    await reload();
    await openCcfTab();
    await selectGroupRow(helpId);
    let e = await readEditor();
    L.check('check 19: p[data-role="alpha-help"] reads the help with the member count filled (3)', e.alphaHelpText === T.en.help(3), e.alphaHelpText);
    L.check('check 19: p[data-role="testing-help"] reads the testing help', e.testingHelpText === T.en.testingHelp, e.testingHelpText);
    L.check('check 19: every alpha input is described by the help paragraph and by its own error paragraph',
      e.inputs.length === 3 && e.inputs.every((i) => i.errId && i.describedby.split(/\s+/).includes(i.errId) && i.describedby.split(/\s+/).includes(e.alphaHelpId)), e.inputs);
    L.check('check 19: the testing select is described by its help and its error paragraph', Boolean(e.testingHelpId) && Boolean(e.testingErrId), e);
    const sel = await page.evaluate(() => { const s = document.querySelector('#tabpanel-ccf [data-section="editor"] select[data-field="testing"]'); return s ? (s.getAttribute('aria-describedby') || '') : ''; });
    L.check('check 19: ... (aria-describedby of the select)', sel.split(/\s+/).includes(e.testingHelpId) && sel.split(/\s+/).includes(e.testingErrId), sel);
    L.check('check 19: the editor status shows its warning as .ccf-status__warning (sum 1.0005)', e.statusWarnings.length === 1 && e.statusWarnings[0].startsWith('Warning:'), e.statusWarnings);
    L.check('check 19: the legend has data-role="alpha-legend" and the placeholder is "e.g. 0.05 or 5%"', e.legend === 'α values' && e.inputs.every((i) => i.placeholder === T.en.hint), e);
    await app.setLanguage('ja');
    await page.waitForTimeout(500);
    e = await readEditor();
    L.check('check 19: the placeholder reads "例: 0.05 または 5%" (ja)', Boolean(e) && e.inputs.length === 3 && e.inputs.every((i) => i.placeholder === T.ja.hint), e && e.inputs.map((i) => i.placeholder));
    L.check('check 19: (ja) the alpha help and the testing help read as the catalog', Boolean(e) && e.alphaHelpText === T.ja.help(3) && e.testingHelpText === T.ja.testingHelp, e && { alpha: e.alphaHelpText, testing: e.testingHelpText });
    await app.setLanguage('en');
    await page.waitForTimeout(300);

    // check 17: arrow keys on the closed model select
    for (const [what, gid] of [['the 3-member group', helpId]]) {
      await selectGroupRow(gid);
      const before = JSON.stringify(await groups());
      const n0 = reqs.length;
      await editor.locator('select[data-field="model"]').focus();
      await page.keyboard.press('ArrowDown');
      await page.keyboard.press('ArrowUp');
      await page.keyboard.press('ArrowDown');
      await page.waitForTimeout(500);
      L.check('check 17: ArrowDown / ArrowUp on the closed model select of ' + what + ' send no request', reqs.length === n0, reqs.slice(n0));
      L.check('check 17: ... and GET is unchanged for ' + what, JSON.stringify(await groups()) === before);
      await page.keyboard.press('Escape');
    }
    await app.api('del', '/ccf/groups/' + helpId);
    const five = await mk('Five valves', ['A', 'B', 'C', 'D', 'E'], [0.9, 0.04, 0.03, 0.02, 0.01], 'staggered');
    await reload();
    await openCcfTab();
    await selectGroupRow(five);
    const rFive = await rowOf(five);
    const eFive = await readEditor();
    L.check('check 2: a stored 5-member group shows "Not applied: alpha-factor model needs 2 to 4 members" and the size message, no input', Boolean(rFive) && rFive.status === T.en.notApplied(T.en.sizeReason) && eFive.inputs.length === 0 && eFive.sizeText === T.en.size(5), { rFive, size: eFive.sizeText });
    const before5 = JSON.stringify(await groups());
    const n5 = reqs.length;
    await editor.locator('select[data-field="model"]').focus();
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('ArrowUp');
    await page.waitForTimeout(500);
    L.check('check 17: arrow keys on the model select of the 5-member group send no request and GET is unchanged', reqs.length === n5 && JSON.stringify(await groups()) === before5, reqs.slice(n5));
    await app.api('del', '/ccf/groups/' + five);
  }, async () => { await app.setLanguage('en'); });

  // ===== check 15: ETA mode ============================================================
  await part('check 15', async () => {
    for (const g of await groups()) await app.api('del', '/ccf/groups/' + g.id);
    const a = await mk('Eta alpha', ['A', 'B', 'C'], [0.955, 0.034, 0.011], 'staggered');
    const b = await mk('Eta pair', ['D', 'E'], [0.9, 0.1], 'nonStaggered');
    const set = await app.api('post', '/metadata', { mode: 'ETA' });
    L.check('check 15: mode set to ETA', !set.__error, set.__error ? set : undefined);
    await reload();
    await openCcfTab();
    const rows = await readRows();
    L.check('check 15: all statuses read "Not applied: ETA mode"', rows.length === 2 && rows.every((r) => r.status === T.en.eta), rows);
    await app.setLanguage('ja');
    await page.waitForTimeout(500);
    const rowsJa = await readRows();
    L.check('check 15: (ja) all statuses read "' + T.ja.eta + '"', rowsJa.length === 2 && rowsJa.every((r) => r.status === T.ja.eta), rowsJa);
    await app.setLanguage('en');
    await page.waitForTimeout(300);
    await selectGroupRow(a);
    const e = await readEditor();
    L.check('check 15: the alpha editor is still usable: three alpha inputs, the testing select and the save button', e.inputs.length === 3 && e.hasTesting && e.hasSave, e);
    const n0 = reqs.length;
    await typeInto('alpha1', '0.9', 'Tab');
    await typeInto('alpha2', '0.05', 'Tab');
    await typeInto('alpha3', '0.05', 'Tab');
    await editor.locator('button[data-role="alpha-save"]').click();
    await waitFor(async () => sameList((await byName('Eta alpha')).alpha, [0.9, 0.05, 0.05]));
    L.check('check 15: ... and a save works in ETA mode', sameList((await byName('Eta alpha')).alpha, [0.9, 0.05, 0.05]) && reqs.length === n0 + 1, reqs.slice(n0));
    const back = await app.api('post', '/metadata', { mode: 'FTA' });
    L.check('check 15: back to FTA mode', !back.__error, back.__error ? back : undefined);
    await app.api('del', '/ccf/groups/' + a);
    await app.api('del', '/ccf/groups/' + b);
  }, async () => { await app.setLanguage('en'); await app.api('post', '/metadata', { mode: 'FTA' }); });

  // ===== check 16: Basic mode, tab order, screenshots ===================================
  await part('check 16', async () => {
    await reload();
    const g3 = await mk('Shot valves', ['A', 'B', 'C'], [0.955, 0.034, 0.011], 'staggered');
    await reload();
    await openCcfTab();
    const order = await page.evaluate(() => Array.from(document.querySelectorAll('#bottom-tabs .tabstrip__tab')).filter((b) => !b.hidden).map((b) => b.id));
    const iq = order.indexOf('tab-quant');
    L.check('check 16: the tab order is unchanged: the CCF tab sits between Quantification and Cut Sets', iq >= 0 && order[iq + 1] === 'tab-ccf' && order[iq + 2] === 'tab-cutsets', order);
    await selectGroupRow(g3);
    await app.shot('ccf_alpha_editor_m3_en');
    await app.setLanguage('ja');
    await page.waitForTimeout(500);
    await app.shot('ccf_alpha_editor_m3_ja');
    await app.setLanguage('en');
    await page.waitForTimeout(300);
    await app.setAdvanced(false);
    await page.waitForTimeout(500);
    const hidden = await page.evaluate(() => { const b = document.getElementById('tab-ccf'); return Boolean(b) && (b.hidden || b.offsetParent === null); });
    L.check('check 16: in Basic mode the CCF tab is hidden', hidden);
    await app.setAdvanced(true);
    await page.waitForTimeout(400);
  }, async () => { await app.setLanguage('en'); await app.setAdvanced(true); });

  // ===== console ========================================================================
  const errs = app.errorsSince(0, [/status of 400/, /^400 PATCH \/api\/ccf\/groups/]);
  L.check('whole run: no console errors, page errors or failed /api requests (except the stubbed 400 of check 10)', errs.length === 0, errs.slice(0, 5));
  await app.context.close();
}

L.runSection('ccf_alpha', run);
