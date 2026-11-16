// What-if tab (F4), review round 2 follow-up: two defects the code review found in tabs/whatif.js that section
// `whatif` does not cover (.division/reviews/F4-T2-code-2.md, REQUIRED CHANGES 1 and 2; F4-T2-code-1.md change 1).
//   node s_whatifr1.js <url> <label> <root>
//
// Case A  FN-58 / UI-15: "Reset after a typed value that is not committed yet". With two chips, committing the
//         typed value on mousedown (the blur) moved that event to the end of the factors list, so the chips swapped
//         under the pointer between mousedown and mouseup and the click was lost. Real mouse events, both chips,
//         the single chip, and Reset all.
// Case B  D8 rev 6: "an answer from before the last reset is dropped". A factor 50 is in flight (answers delayed by
//         300 ms), the chip Reset is clicked; the old answer must never show in whatif-top-whatif nor move
//         data-seq-applied. A MutationObserver on the page records every value of the cell and of the sequence.
//
// Every check name starts with whatifr1_caseA_ or whatifr1_caseB_.
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const TID = (id) => `[data-testid="${id}"]`;
const X = '×'; // the multiplication sign of "Pump E1 × 10"

// ---- the document: root OR [E1 (q 1e-3), E2 (q 2e-3)], both fixed ---------------------------------------------------
const leaf = (id, name, q) => ({ id, name, type: 'Event', logicGate: 'OR', probability: q, notes: '', links: [], children: [], quant: { model: 'fixed' } });
const twoDoc = () => ({
  title: 'What-if reset test', date: '2026-11-02', mode: 'FTA',
  tree: { id: 'root', name: 'Top event', type: 'Root', logicGate: 'OR', probability: 1.0, notes: '', links: [], children: [leaf('E1', 'Pump E1', 1e-3), leaf('E2', 'Pump E2', 2e-3)] },
});
/** R1 shape: root OR [G1 AND [A, B], C]; A and B (1e-3 each) are in a beta CCF group (beta 0.1); C is an independent event (1e-3). */
const groupDoc = () => ({
  title: 'What-if reset group test', date: '2026-11-02', mode: 'FTA', fileFormatVersion: 2,
  tree: {
    id: 'root', name: 'Top event', type: 'Root', logicGate: 'OR', probability: 1.0, notes: '', links: [],
    children: [
      { id: 'G1', name: 'Pumps fail', type: 'Event', logicGate: 'AND', probability: 1.0, notes: '', links: [], children: [leaf('A', 'Pump A', 1e-3), leaf('B', 'Pump B', 1e-3)] },
      leaf('C', 'Sensor C', 1e-3),
    ],
  },
  analysis: { ccfGroups: [{ id: 'g1', name: 'Feed pumps', model: 'beta', beta: 0.1, alpha: null, testing: null, members: ['A', 'B'], source: 'test' }] },
});
/** Top event of groupDoc for a factor fg on the group members and fc on C (the MCUB: the CCF set, the pair set, C). */
const groupTop = (fg, fc) => {
  const qt = Math.min(1, 1e-3 * fg);
  return union([0.1 * qt, (0.9 * qt) * (0.9 * qt), Math.min(1, 1e-3 * fc)]);
};
const union = (ps) => 1 - ps.reduce((acc, p) => acc * (1 - p), 1);
const close = (a, b, rel) => typeof a === 'number' && Number.isFinite(a) && typeof b === 'number' && (b === 0 ? a === 0 : Math.abs(a - b) <= rel * Math.abs(b));
const num = (c) => (c && c.value !== null && c.value !== '' ? Number(c.value) : null);

const CELLS = {
  topBaseline: 'whatif-top-baseline', topWhatif: 'whatif-top-whatif',
};

const readTab = (pg) => pg.evaluate((cells) => {
  const q = (id) => document.querySelector(`[data-testid="${id}"]`);
  const out = { root: null, cells: {}, slider: null, field: null, picker: null };
  const root = q('whatif-root');
  if (root) {
    const d = root.dataset;
    out.root = { state: d.state, factors: d.factors, pending: d.pending, seqSent: d.seqSent, seqApplied: d.seqApplied };
  }
  for (const [key, id] of Object.entries(cells)) {
    const e = q(id);
    out.cells[key] = e ? { value: e.dataset.value === undefined ? null : e.dataset.value } : null;
  }
  const sl = q('whatif-slider');
  if (sl) out.slider = { value: sl.value, factor: sl.dataset.factor === undefined ? null : sl.dataset.factor };
  const fi = q('whatif-factor-input');
  if (fi) out.field = { value: fi.value };
  const pk = q('whatif-picker');
  if (pk) out.picker = { value: pk.value, options: Array.from(pk.options).map((o) => ({ value: o.value, text: o.textContent })) };
  return out;
}, CELLS);

const settledPred = (r) => Boolean(r.root) && r.root.state === 'ready' && r.root.pending === '0' && r.root.seqApplied === r.root.seqSent
  && ['topBaseline', 'topWhatif'].every((k) => r.cells[k] && r.cells[k].value !== null && r.cells[k].value !== '');

async function main(url, label, root) {
  L.setSection('whatifr1[' + label + ']');
  const docName = `whatifr1_two_${label}.json`;
  const groupName = `whatifr1_group_${label}.json`;
  fs.writeFileSync(path.join(root, docName), JSON.stringify(twoDoc(), null, 2));
  fs.writeFileSync(path.join(root, groupName), JSON.stringify(groupDoc(), null, 2));

  const app = await L.openApp(url, { viewport: { width: 1100, height: 800 }, prefs: { 'fta.advanced': '1' } });
  const { page } = app;
  page.setDefaultTimeout(8000);
  page.on('dialog', (d) => { d.accept().catch(() => {}); });
  const posts = []; // the body of every POST /api/whatif this page sent
  page.on('request', (r) => { if (r.method() === 'POST' && /\/api\/whatif(\?|$)/.test(r.url())) posts.push(r.postData() || ''); });

  const part = async (name, fn) => {
    try { await fn(); } catch (e) { L.check(`${name}: did not complete`, false, String((e && e.message) || e).split('\n')[0].slice(0, 400)); }
  };
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
  const active = () => page.evaluate(() => { const a = document.activeElement; return a ? { id: a.id || '', testid: a.getAttribute('data-testid') || '', tag: a.tagName } : null; });
  const chipInfo = () => page.locator(TID('whatif-chip')).evaluateAll((es) => es.map((e) => ({ id: e.dataset.nodeId, factor: e.dataset.factor })));
  const bannerCount = () => page.locator(TID('whatif-banner')).count();

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
  const openTab = async (name = docName) => {
    await openDoc(name);
    await showWhatif();
    const w = await waitRead(settledPred, 20000);
    if (!w.ok) throw new Error('the What-if tab did not settle: ' + JSON.stringify(w.r.root));
    return w.r;
  };
  const pick = async (id) => { await page.locator(TID('whatif-picker')).selectOption(id); };
  const setField = async (text) => {
    const f = page.locator(TID('whatif-factor-input'));
    await f.fill(String(text));
    await f.press('Enter');
  };
  /** Give `id` a factor through the field and wait until the chip is there and the answer is applied. */
  const giveFactor = async (id, text, factorsAfter, wantTop, rel = 1e-9) => {
    await pick(id);
    await setField(text);
    const w = await waitRead((r) => settledPred(r) && r.root.factors === String(factorsAfter) && close(num(r.cells.topWhatif), wantTop, rel), 8000);
    if (!w.ok) throw new Error(`the factor ${text} on ${id} was not applied: ` + JSON.stringify(w.r.root));
    await sleep(150);
    return w.r;
  };
  /** A real mouse press and release on the centre of `loc`, with the pause of a human hand between them. */
  const realClick = async (loc, frac = 0.5) => {
    await loc.waitFor({ state: 'visible' });
    const box = await loc.boundingBox();
    if (!box) throw new Error('no box for the element to click');
    const x = box.x + box.width * frac;
    const y = box.y + box.height / 2;
    await page.mouse.move(x, y);
    await page.mouse.down();
    await sleep(60);
    await page.mouse.up();
  };
  const afterClick = async () => {
    await sleep(300);
    const w = await waitRead(settledPred, 8000);
    return w.r;
  };
  const optionHasFactor = (r, id) => { const o = r.picker.options.find((x) => x.value === id); return Boolean(o) && o.text.includes(' ' + X + ' '); };

  // =====================================================================================================================
  // Case A: Reset after a typed value that is not committed
  // =====================================================================================================================
  const TOP_E1_10_E2_20 = union([1e-2, 4e-2]);
  const TOP_E1_10 = union([1e-2, 2e-3]);

  /** Two chips (E1 x 10, E2 x 20), E1 picked, "55" typed in the field and NOT committed. */
  const twoChipsTyped = async (tag, init1 = '10', typedText = '55') => {
    await openTab();
    await giveFactor('E1', init1, 1, union([1e-3 * Number(init1), 2e-3]));
    const wantTop = union([1e-3 * Number(init1), 2e-3 * 20]);
    const r2 = await giveFactor('E2', '20', 2, wantTop);
    await pick('E1');
    const w = await waitRead((r) => settledPred(r) && r.root.factors === '2' && r.picker.value === 'E1' && Number(r.slider.factor) === Number(init1), 8000);
    await page.locator(TID('whatif-factor-input')).fill(typedText); // no Enter, no blur
    const chips = await chipInfo();
    const typed = await read();
    L.check(`whatifr1_caseA_${tag}_precondition: two chips E1 x ${init1} and E2 x 20 (what-if top event ${wantTop.toPrecision(6)}), E1 picked, "${typedText}" typed and not committed`,
      w.ok && close(num(r2.cells.topWhatif), wantTop, 1e-9) && JSON.stringify(chips) === JSON.stringify([{ id: 'E1', factor: init1 }, { id: 'E2', factor: '20' }])
      && typed.field.value === typedText && typed.root.factors === '2', { chips, field: typed.field.value, root: typed.root, top: r2.cells.topWhatif });
  };

  /** The four checks after a chip Reset on `clicked` with `kept` the other event and `keptFactor` its factor. */
  const checkChipReset = async (tag, clicked, kept, keptFactor) => {
    const r = await afterClick();
    const chips = await chipInfo();
    const act = await active();
    L.check(`whatifr1_caseA_${tag}_clicked_factor_is_1: the Reset of the chip of ${clicked} sets its factor back to 1 (its chip is gone, no "×" on it in the picker)`,
      !chips.some((c) => c.id === clicked) && !optionHasFactor(r, clicked), { chips, options: r.picker.options });
    L.check(`whatifr1_caseA_${tag}_data_factors_1: whatif-root data-factors is 1`, r.root.factors === '1', r.root);
    L.check(`whatifr1_caseA_${tag}_other_chip_kept: the chip of ${kept} stays with factor ${keptFactor}`, chips.length === 1 && chips[0].id === kept && Number(chips[0].factor) === keptFactor, chips);
    L.check(`whatifr1_caseA_${tag}_focus_picker: focus is on whatif-picker`, Boolean(act) && act.testid === 'whatif-picker', act);
  };

  await part('caseA two chips, Reset of E1', async () => {
    await twoChipsTyped('twochips_resetE1');
    await realClick(page.locator(TID('whatif-reset-event') + '[data-node-id="E1"]'));
    await checkChipReset('twochips_resetE1', 'E1', 'E2', 20);
  });

  await part('caseA two chips, Reset of E2', async () => {
    await twoChipsTyped('twochips_resetE2');
    await realClick(page.locator(TID('whatif-reset-event') + '[data-node-id="E2"]'));
    // the typed 55 on the picked E1 is committed by the click (the blur) and stays; E2 goes
    await checkChipReset('twochips_resetE2', 'E2', 'E1', 55);
  });

  await part('caseA two chips, Reset all', async () => {
    await twoChipsTyped('twochips_resetall');
    await realClick(page.locator(TID('whatif-reset-all')));
    const r = await afterClick();
    const act = await active();
    L.check('whatifr1_caseA_twochips_resetall_data_factors_0: Reset all with a typed value: data-factors 0, no banner, no chip',
      r.root.factors === '0' && (await bannerCount()) === 0 && (await chipInfo()).length === 0, { root: r.root, banner: await bannerCount() });
    L.check('whatifr1_caseA_twochips_resetall_nominal: the what-if top event is the baseline again', r.cells.topWhatif.value === r.cells.topBaseline.value, r.cells);
    L.check('whatifr1_caseA_twochips_resetall_focus_picker: focus is on whatif-picker', Boolean(act) && act.testid === 'whatif-picker', act);
  });

  /** One chip (E1 x 10), "55" typed and not committed. */
  const oneChipTyped = async (tag) => {
    await openTab();
    const r1 = await giveFactor('E1', '10', 1, TOP_E1_10);
    await page.locator(TID('whatif-factor-input')).fill('55');
    const chips = await chipInfo();
    const typed = await read();
    L.check(`whatifr1_caseA_${tag}_precondition: one chip E1 x 10 (top event 1 - (1 - 0.01)(1 - 0.002)), "55" typed and not committed`,
      close(num(r1.cells.topWhatif), TOP_E1_10, 1e-9) && JSON.stringify(chips) === JSON.stringify([{ id: 'E1', factor: '10' }]) && typed.field.value === '55' && typed.root.factors === '1', { chips, field: typed.field.value, root: typed.root });
  };

  await part('caseA single chip, Reset of E1', async () => {
    await oneChipTyped('onechip_resetE1');
    await realClick(page.locator(TID('whatif-reset-event') + '[data-node-id="E1"]'));
    const r = await afterClick();
    const act = await active();
    L.check('whatifr1_caseA_onechip_resetE1_data_factors_0: chip Reset with a typed value: data-factors 0, no banner, no chip', r.root.factors === '0' && (await bannerCount()) === 0 && (await chipInfo()).length === 0, { root: r.root, banner: await bannerCount() });
    L.check('whatifr1_caseA_onechip_resetE1_focus_picker: focus is on whatif-picker', Boolean(act) && act.testid === 'whatif-picker', act);
  });

  await part('caseA single chip, Reset all', async () => {
    await oneChipTyped('onechip_resetall');
    await realClick(page.locator(TID('whatif-reset-all')));
    const r = await afterClick();
    const act = await active();
    L.check('whatifr1_caseA_onechip_resetall_data_factors_0: Reset all with a typed value: data-factors 0, no banner, no chip', r.root.factors === '0' && (await bannerCount()) === 0 && (await chipInfo()).length === 0, { root: r.root, banner: await bannerCount() });
    L.check('whatifr1_caseA_onechip_resetall_focus_picker: focus is on whatif-picker', Boolean(act) && act.testid === 'whatif-picker', act);
  });

  // ---- (a) a typed value that widens the first chip: the second chip's Reset slides away from the pointer ----------------
  const widenCases = [['2', '0.125'], ['10', '0.01234']];
  for (const [init1, typedText] of widenCases) {
    for (const [fracName, frac] of [['centre', 0.5], ['q25', 0.25]]) {
      const tag = `widen_${init1}_${typedText.replace('.', 'p')}_${fracName}`;
      await part(`caseA widen ${init1} -> ${typedText}, Reset of E2 at ${fracName}`, async () => {
        await twoChipsTyped(tag, init1, typedText);
        await realClick(page.locator(TID('whatif-reset-event') + '[data-node-id="E2"]'), frac);
        // the typed value on the picked E1 is committed by the click and stays; E2 goes
        await checkChipReset(tag, 'E2', 'E1', Number(typedText));
      });
    }
  }

  // ---- (b) typed "1" on the picked E1: committing it removes E1's chip and E2's chip slides left ---------------------------
  await part('caseA typed 1, Reset of E2', async () => {
    await twoChipsTyped('typed1_resetE2', '10', '1');
    await realClick(page.locator(TID('whatif-reset-event') + '[data-node-id="E2"]'));
    const r = await afterClick();
    const act = await active();
    const chips = await chipInfo();
    L.check('whatifr1_caseA_typed1_resetE2_data_factors_0: typed 1 on E1 then Reset of E2: data-factors 0 (E1 committed as 1 is gone, E2 gone), no banner, no chip',
      r.root.factors === '0' && (await bannerCount()) === 0 && chips.length === 0, { root: r.root, chips, banner: await bannerCount() });
    L.check('whatifr1_caseA_typed1_resetE2_focus_picker: focus is on whatif-picker', Boolean(act) && act.testid === 'whatif-picker', act);
  });
  await part('caseA typed 1, Reset of E1', async () => {
    await twoChipsTyped('typed1_resetE1', '10', '1');
    await realClick(page.locator(TID('whatif-reset-event') + '[data-node-id="E1"]'));
    await checkChipReset('typed1_resetE1', 'E1', 'E2', 20);
  });

  // ---- (c) CCF group: chips [A x 10 (the group entry), C x 20], member B picked, 55 typed ---------------------------------
  const groupChipsTyped = async (tag) => {
    await openTab(groupName);
    await giveFactor('A', '10', 1, groupTop(10, 1), 1e-6);
    const r2 = await giveFactor('C', '20', 2, groupTop(10, 20), 1e-6);
    await pick('B'); // B shows the group's factor
    const w = await waitRead((r) => settledPred(r) && r.root.factors === '2' && r.picker.value === 'B' && Number(r.slider.factor) === 10, 8000);
    await page.locator(TID('whatif-factor-input')).fill('55'); // no Enter, no blur
    const chips = await chipInfo();
    const typed = await read();
    L.check(`whatifr1_caseA_${tag}_precondition: CCF group (A, B) with the entry on A x 10 and C x 20 (top event ${groupTop(10, 20).toPrecision(6)}), B picked showing factor 10, "55" typed and not committed`,
      w.ok && close(num(r2.cells.topWhatif), groupTop(10, 20), 1e-6) && JSON.stringify(chips) === JSON.stringify([{ id: 'A', factor: '10' }, { id: 'C', factor: '20' }])
      && typed.field.value === '55' && typed.root.factors === '2', { chips, field: typed.field.value, root: typed.root, top: r2.cells.topWhatif });
  };
  await part('caseA group, Reset of the group chip (A)', async () => {
    await groupChipsTyped('group_resetA');
    await realClick(page.locator(TID('whatif-reset-event') + '[data-node-id="A"]'));
    const r = await afterClick();
    const chips = await chipInfo();
    const act = await active();
    L.check('whatifr1_caseA_group_resetA_clicked_entry_gone: the Reset of the group chip removes the group entry (no chip on A or B, no "×" on A or B in the picker)',
      !chips.some((c) => c.id === 'A' || c.id === 'B') && !optionHasFactor(r, 'A') && !optionHasFactor(r, 'B'), { chips, options: r.picker.options });
    L.check('whatifr1_caseA_group_resetA_other_chip_kept: the chip of C stays with factor 20, data-factors is 1', r.root.factors === '1' && chips.length === 1 && chips[0].id === 'C' && Number(chips[0].factor) === 20, { root: r.root, chips });
    L.check('whatifr1_caseA_group_resetA_focus_picker: focus is on whatif-picker', Boolean(act) && act.testid === 'whatif-picker', act);
  });
  await part('caseA group, Reset of C', async () => {
    await groupChipsTyped('group_resetC');
    await realClick(page.locator(TID('whatif-reset-event') + '[data-node-id="C"]'));
    const r = await afterClick();
    const chips = await chipInfo();
    const act = await active();
    L.check('whatifr1_caseA_group_resetC_clicked_entry_gone: the Reset of the chip of C removes it (no chip on C, no "×" on C in the picker)', !chips.some((c) => c.id === 'C') && !optionHasFactor(r, 'C'), { chips, options: r.picker.options });
    L.check('whatifr1_caseA_group_resetC_other_chip_kept: the group entry stays (one chip, on A or B, carrying the typed 55), data-factors is 1',
      r.root.factors === '1' && chips.length === 1 && (chips[0].id === 'A' || chips[0].id === 'B') && Number(chips[0].factor) === 55, { root: r.root, chips });
    L.check('whatifr1_caseA_group_resetC_focus_picker: focus is on whatif-picker', Boolean(act) && act.testid === 'whatif-picker', act);
  });

  // ---- (d) an edit that leaves the field text equal to its display: no change event, the field stays "dirty" -----------------
  // Chips [E1 = typed factor with more digits than the field shows, E2 x 20], E1 picked. The text is edited and put back
  // (End, one digit, Backspace; or select all and retype the display). A Reset of E2 must not commit the display text
  // over the typed factor (DESIGN 5.4: the typed value is kept exactly).
  const dirtyTextCase = async (tag, factorText, route, how) => {
    await openTab();
    const f = Number(factorText);
    await giveFactor('E1', factorText, 1, union([1e-3 * f, 2e-3]));
    const r2 = await giveFactor('E2', '20', 2, union([1e-3 * f, 4e-2]));
    await pick('E1');
    await waitRead((r) => settledPred(r) && r.picker.value === 'E1' && r.root.factors === '2', 8000);
    const display = (await read()).field.value;
    const field = page.locator(TID('whatif-factor-input'));
    await field.focus();
    if (route === 'digit') {
      await page.keyboard.press('End');
      await page.keyboard.type('7');
      await page.keyboard.press('Backspace');
    } else {
      await page.keyboard.press('Control+A');
      await page.keyboard.type(display);
    }
    const mark = posts.length;
    const chips0 = await chipInfo();
    const typed = await read();
    L.check(`whatifr1_caseA_${tag}_precondition: chips E1 = ${factorText} and E2 = 20, E1 picked, the field shows "${display}" (not ${factorText}), edited by "${route}" and back to the same text`,
      close(num(r2.cells.topWhatif), union([1e-3 * f, 4e-2]), 1e-9) && JSON.stringify(chips0) === JSON.stringify([{ id: 'E1', factor: factorText }, { id: 'E2', factor: '20' }])
      && display !== factorText && typed.field.value === display && typed.root.factors === '2', { chips: chips0, display, field: typed.field.value, root: typed.root });
    if (how === 'mouse') {
      await realClick(page.locator(TID('whatif-reset-event') + '[data-node-id="E2"]'));
    } else {
      // keyboard only: Shift+Tab away from the field until E2's Reset has focus, then Space or Enter
      let reached = false;
      for (let i = 0; i < 12 && !reached; i += 1) {
        await page.keyboard.press('Shift+Tab');
        reached = await page.evaluate(() => { const a = document.activeElement; return Boolean(a) && a.getAttribute('data-testid') === 'whatif-reset-event' && a.getAttribute('data-node-id') === 'E2'; });
      }
      if (!reached) throw new Error('Shift+Tab never reached the Reset button of E2');
      await sleep(300);
      await page.keyboard.press(how === 'space' ? 'Space' : 'Enter');
    }
    const r = await afterClick();
    const chips = await chipInfo();
    const act = await active();
    const roundedBody = new RegExp('"E1"\\s*:\\s*' + String(Number(display)).replace('.', '\\.') + '(?![0-9.])');
    const sent = posts.slice(mark);
    L.check(`whatifr1_caseA_${tag}_clicked_gone: the Reset of E2 removes its chip, data-factors is 1`, !chips.some((c) => c.id === 'E2') && r.root.factors === '1', { chips, root: r.root });
    L.check(`whatifr1_caseA_${tag}_e1_factor_kept: the chip of E1 keeps data-factor ${factorText} (not the displayed ${display})`, chips.length === 1 && chips[0].id === 'E1' && chips[0].factor === factorText, chips);
    L.check(`whatifr1_caseA_${tag}_no_post_with_display_value: no POST /api/whatif after the edit carries E1 = ${Number(display)}`, !sent.some((b) => roundedBody.test(b)), sent);
    L.check(`whatifr1_caseA_${tag}_focus_picker: focus is on whatif-picker`, Boolean(act) && act.testid === 'whatif-picker', act);
  };
  await part('caseA dirty text 3.14159, digit and Backspace, mouse', async () => { await dirtyTextCase('dirty_3p14159_digit_mouse', '3.14159', 'digit', 'mouse'); });
  await part('caseA dirty text 1.00001, digit and Backspace, mouse', async () => { await dirtyTextCase('dirty_1p00001_digit_mouse', '1.00001', 'digit', 'mouse'); });
  await part('caseA dirty text 3.14159, select all and retype, mouse', async () => { await dirtyTextCase('dirty_3p14159_retype_mouse', '3.14159', 'retype', 'mouse'); });
  await part('caseA dirty text 3.14159, Shift+Tab then Space', async () => { await dirtyTextCase('dirty_3p14159_digit_space', '3.14159', 'digit', 'space'); });
  await part('caseA dirty text 3.14159, Shift+Tab then Enter', async () => { await dirtyTextCase('dirty_3p14159_digit_enter', '3.14159', 'digit', 'enter'); });

  // =====================================================================================================================
  // Case B: an answer in flight when a chip Reset is clicked is dropped
  // =====================================================================================================================
  await part('caseB stale answer after Reset per event', async () => {
    const r0 = await openTab();
    const baseline = r0.cells.topBaseline.value;
    let delayMs = 300;
    const released = []; // when each delayed answer was let through
    const delayed = async (route) => {
      if (delayMs) await sleep(delayMs);
      released.push(Date.now());
      await route.continue().catch(() => {});
    };
    // never unrouted (an unroute while a handler sleeps crashes the run): the delay is switched off instead
    await page.route('**/api/whatif', delayed);
    await page.evaluate(() => {
      const q = (id) => document.querySelector(`[data-testid="${id}"]`);
      const w = { log: [], phase: 'before', down: null };
      window.__whatifr1 = w;
      const snap = () => {
        const cell = q('whatif-top-whatif');
        const rootEl = q('whatif-root');
        return { v: cell ? (cell.dataset.value === undefined ? null : cell.dataset.value) : null, seqA: rootEl ? rootEl.dataset.seqApplied : null, seqS: rootEl ? rootEl.dataset.seqSent : null };
      };
      const first = snap();
      w.log.push({ phase: 'before', v: first.v, seqA: first.seqA, seqS: first.seqS, t: Date.now() });
      const mo = new MutationObserver(() => {
        const s = snap();
        const last = w.log[w.log.length - 1];
        if (s.v !== last.v || s.seqA !== last.seqA) w.log.push({ phase: w.phase, v: s.v, seqA: s.seqA, seqS: s.seqS, t: Date.now() });
      });
      mo.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });
      document.addEventListener('mousedown', () => {
        const s = snap();
        const rootEl = q('whatif-root');
        w.phase = 'after';
        w.down = { seqS: s.seqS, seqA: s.seqA, pending: rootEl ? rootEl.dataset.pending : null, chips: document.querySelectorAll('[data-testid="whatif-chip"]').length, t: Date.now() };
      }, true);
    });

    await page.locator(TID('whatif-picker')).selectOption('E1');
    await setField('50');
    // the request leaves after the tab's debounce: click only once it is on its way (sequence sent ahead of applied)
    await page.waitForFunction(() => {
      const el = document.querySelector('[data-testid="whatif-root"]');
      return Boolean(el) && Number(el.dataset.seqSent) > Number(el.dataset.seqApplied);
    }, null, { polling: 'raf', timeout: 5000 });
    const releasedAtDown = released.length;
    await realClick(page.locator(TID('whatif-reset-event') + '[data-node-id="E1"]'));
    const releasedAtUp = released.length;
    await sleep(1500); // the stale answer (300 ms) and the answer to the reset (another 300 ms) are both through
    const r = (await waitRead(settledPred, 8000)).r;
    delayMs = 0;
    const w = await page.evaluate(() => window.__whatifr1);
    const staleSeq = w.down ? w.down.seqS : null;
    const before = w.log.filter((e) => e.phase === 'before');
    const after = w.log.filter((e) => e.phase === 'after');

    L.check('whatifr1_caseB_precondition: the factor 50 was in flight at the click (one chip, data-pending 1, sequence sent ahead of applied) and no delayed answer had been let through between mousedown and mouseup',
      Boolean(w.down) && w.down.chips === 1 && w.down.pending === '1' && Number(w.down.seqS) > Number(w.down.seqA) && releasedAtDown === 0 && releasedAtUp === 0, { down: w.down, releasedAtDown, releasedAtUp });
    L.check('whatifr1_caseB_precondition_before_click: before the click the cell only ever showed the baseline value', before.every((e) => e.v === baseline), { baseline, before });
    const painted = after.filter((e) => e.v !== null && e.v !== '' && e.v !== baseline);
    L.check('whatifr1_caseB_top_never_old_answer: after the Reset, whatif-top-whatif data-value only ever has the baseline value (the answer of the factor 50 never shows)', painted.length === 0, { baseline, painted, after });
    const movedToStale = after.filter((e) => staleSeq !== null && e.seqA === staleSeq);
    L.check('whatifr1_caseB_seq_applied_not_old: after the Reset, data-seq-applied never moves to the sequence of the answer that was in flight (' + staleSeq + ')', Boolean(w.down) && movedToStale.length === 0, { staleSeq, movedToStale, after });
    const chips = await chipInfo();
    L.check('whatifr1_caseB_end_state: at the end data-factors is 0, there is no banner and no chip, and the top event is the baseline', r.root.factors === '0' && (await bannerCount()) === 0 && chips.length === 0 && r.cells.topWhatif.value === baseline, { root: r.root, chips, top: r.cells.topWhatif });
  });

  const errs = app.errorsSince(0, []);
  L.check('whatifr1: no console errors in the whatifr1 run', errs.length === 0, errs.slice(0, 5));
  await app.api('post', '/new', { force: true });
  fs.rmSync(path.join(root, docName), { force: true });
  fs.rmSync(path.join(root, groupName), { force: true });
  await app.context.close();
}

L.runSection('whatifr1', main);
