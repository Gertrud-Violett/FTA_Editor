// Tab strip (feature FY, task Y2), in a real browser.
//   node s_tabstrip.js <url> <label> <root>
//
// Two defects of the final UI review (round 1, required changes 1 and 2):
//   1. A selected tab (click, ArrowLeft/Right, Home/End, programmatic select) was left cut off at the edge of the
//      scrolling strip #bottom-tabs. It must be brought fully into view (host.js revealTab: scrollIntoView nearest), and
//      neither the page nor a tab panel may scroll because of it.
//   2. In ETA mode the Grid tab must be greyed like CCF and What-if: class is-unavailable, data-unavailable="eta" and the
//      title of the existing key tab.etaUnavailable (the same text as #tab-whatif). Back in FTA nothing of it is left.
//
// Cases (each in en and ja, Advanced on, 1100 x 800, a small document):
//   scroll    Home then 7x ArrowRight leaves #tab-whatif inside the strip (aria-selected only there, focus on it, the visible
//             tab order unchanged); a click on the last, partly cut off tab brings it in; a programmatic select (openTab)
//             does; End then Home (first tab inside, scrollLeft 0). window.scrollY and panel scrollTop never change.
//   eta       the seven greyed tabs (quant, cutsets, importance, uncertainty, ccf, whatif, grid), the Grid title, a click on
//             Grid shows the .anl-eta notice, ArrowRight still works.
//   fta_back  no greying left, in particular none on Grid.
// And once, in Basic mode: Grid hidden, selection works, no page scroll.
// The preconditions (the strip really overflows; at scrollLeft 0 the What-if tab is cut off) are checks of their own, so the
// tests cannot pass on a layout where the defect cannot show.
// In ja the labels are shorter: What-if fits at scrollLeft 0 and the tab cut off there is Validation, so the ja walk is Home
// then 8x ArrowRight to Validation (the tab that is cut off is found from the geometry, not assumed).
// Shots: tabstrip-after-home-7right-en, tabstrip-after-home-8right-ja, tabstrip-eta-en, tabstrip-eta-ja. Each is taken
// after its assertions.
//
// Every check name starts with tabstrip_.
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const ETA_TEXT = {
  en: 'Not available for an event tree (ETA mode): this analysis works on the gates of a fault tree. Switch Mode to FTA to use it.',
  ja: 'イベントツリー（ETA モード）では使用できません。この解析はフォールトツリーのゲートを対象とします。使用するにはモードを FTA に切り替えてください。',
};
const GREYED = ['cutsets', 'grid', 'importance', 'quant', 'uncertainty', 'ccf', 'whatif'].sort();
const TOL = 1; // px

const leaf = (id, name, q) => ({ id, name, type: 'Event', logicGate: 'OR', probability: q, notes: '', links: [], children: [], quant: { model: 'fixed' } });
const smallDoc = () => ({
  title: 'Tab strip', date: '2026-11-04', mode: 'FTA',
  tree: { id: 'root', name: 'Top event', type: 'Root', logicGate: 'OR', probability: 1.0, notes: '', links: [], children: [leaf('E1', 'Pump E1', 1e-3), leaf('E2', 'Pump E2', 2e-3)] },
});

/** Everything the checks read, in one evaluate: geometry of the strip and its tabs, selection, focus, scroll positions. */
const readGeom = (pg) => pg.evaluate(() => {
  const strip = document.getElementById('bottom-tabs');
  const sr = strip.getBoundingClientRect();
  const tabs = Array.from(strip.querySelectorAll('[role="tab"]'));
  const rect = (b) => { const r = b.getBoundingClientRect(); return { left: r.left, right: r.right, width: r.width }; };
  const visible = tabs.filter((b) => !b.hidden && b.offsetParent !== null);
  const a = document.activeElement;
  return {
    strip: { left: sr.left, right: sr.right, scrollLeft: strip.scrollLeft, scrollWidth: strip.scrollWidth, clientWidth: strip.clientWidth, scrollTop: strip.scrollTop },
    order: visible.map((b) => b.dataset.tab),
    rects: Object.fromEntries(visible.map((b) => [b.dataset.tab, rect(b)])),
    selected: tabs.filter((b) => b.getAttribute('aria-selected') === 'true').map((b) => b.dataset.tab),
    active: a ? (a.dataset && a.dataset.tab) || a.id || a.tagName : null,
    scrollY: window.scrollY,
    scrollX: window.scrollX,
    docTop: document.scrollingElement ? document.scrollingElement.scrollTop : 0,
    panels: Object.fromEntries(Array.from(document.querySelectorAll('[role="tabpanel"]')).map((p) => [p.id, p.scrollTop])),
    parentTop: strip.parentElement ? strip.parentElement.scrollTop : 0,
  };
});
const inside = (g, id) => Boolean(g.rects[id]) && g.rects[id].left >= g.strip.left - TOL && g.rects[id].right <= g.strip.right + TOL;
const samePos = (a, b) => a.scrollY === b.scrollY && a.scrollX === b.scrollX && a.docTop === b.docTop && a.parentTop === b.parentTop && JSON.stringify(a.panels) === JSON.stringify(b.panels);
const brief = (g) => ({ strip: g.strip, order: g.order, whatif: g.rects.whatif, selected: g.selected, active: g.active, scrollY: g.scrollY });

async function main(url, label, root) {
  L.setSection('tabstrip[' + label + ']');
  const docName = `tabstrip_doc_${label}.json`;
  fs.writeFileSync(path.join(root, docName), JSON.stringify(smallDoc(), null, 2));

  const app = await L.openApp(url, { viewport: { width: 1100, height: 800 }, colorScheme: 'light', prefs: { 'fta.advanced': '1', 'fta.theme': 'light' } });
  const { page } = app;
  page.setDefaultTimeout(8000);
  page.on('dialog', (d) => { d.accept().catch(() => {}); });
  const shots = [];
  const shot = async (name) => { shots.push(name); return app.shot(name); };
  const geom = () => readGeom(page);
  const waitFor = async (fn, timeout = 6000) => {
    const t0 = Date.now();
    for (;;) {
      let v = false;
      try { v = await fn(); } catch (_e) { v = false; }
      if (v) return true;
      if (Date.now() - t0 > timeout) return false;
      await sleep(60);
    }
  };
  const key = async (k) => { await page.keyboard.press(k); await page.waitForTimeout(90); };
  const stripTo0 = async () => {
    await page.evaluate(() => { document.getElementById('bottom-tabs').scrollLeft = 0; });
    await page.waitForTimeout(80);
  };
  /** Put the focus on a tab without scrolling the strip (focus({preventScroll}) keeps the start state honest). */
  const focusTab = async (id) => { await page.evaluate((i) => document.getElementById('tab-' + i).focus({ preventScroll: true }), id); await page.waitForTimeout(60); };
  const titleOf = (id) => page.evaluate((i) => { const b = document.getElementById('tab-' + i); return b ? b.getAttribute('title') : null; }, id);
  const tabState = (id) => page.evaluate((i) => {
    const b = document.getElementById('tab-' + i);
    return b ? { cls: b.classList.contains('is-unavailable'), un: b.dataset.unavailable === undefined ? null : b.dataset.unavailable, hasTitle: b.hasAttribute('title'), title: b.getAttribute('title'), hidden: b.hidden } : null;
  }, id);
  const greyed = () => page.evaluate(() => Array.from(document.querySelectorAll('#bottom-tabs [role="tab"].is-unavailable')).map((b) => b.dataset.tab).sort());
  const openDoc = async () => {
    await app.api('post', '/new', { force: true });
    const opened = await app.api('post', '/file/open', { path: path.join(root, docName), force: true });
    if (opened.__error) throw new Error(`could not open ${docName}: ${opened.status} ${opened.code}`);
    await page.evaluate(() => localStorage.removeItem('fta.bottomTab'));
    await page.reload();
    await L.waitBoot(page);
    await app.waitDiagram(60000);
    await page.waitForTimeout(500);
  };
  const setMode = async (mode) => {
    await page.locator('#mode-select').selectOption(mode);
    const ok = await waitFor(async () => (await page.evaluate(() => document.getElementById('tab-whatif').classList.contains('is-unavailable'))) === (mode === 'ETA'));
    await page.waitForTimeout(500);
    return ok;
  };

  // ================================================================================================================
  // scroll: the selected tab is fully inside the strip
  // ================================================================================================================
  const caseScroll = async (lang) => {
    const T = `tabstrip_scroll_${lang}_`;
    await stripTo0();
    const g0 = await geom();
    L.check(`${T}precondition_overflow: at 1100 x 800 with Advanced on the strip scrolls sideways (scrollWidth > clientWidth)`, g0.strip.scrollWidth > g0.strip.clientWidth, g0.strip);
    L.check(`${T}precondition_order: the tabs in order are details, grid, quant, ccf, cutsets, importance, uncertainty, whatif, ... (Advanced on)`, g0.order.slice(0, 8).join() === 'details,grid,quant,ccf,cutsets,importance,uncertainty,whatif', g0.order);
    // The tab the old code left cut off at scrollLeft 0: in en it is What-if (the 8th tab: Home + 7x ArrowRight). In ja the
    // labels are shorter and What-if fits; the tab that is cut off there is the next one (Validation, Home + 8x ArrowRight).
    const cutAt0 = g0.order.filter((id) => g0.rects[id].left < g0.strip.right - 6 && g0.rects[id].right > g0.strip.right + TOL);
    const target = cutAt0.length === 1 ? cutAt0[0] : null;
    const n = target ? g0.order.indexOf(target) : 7;
    L.check(`${T}precondition_cut: at scrollLeft 0 one tab does not fit into the strip (the case the old code cut off): ${lang === 'en' ? 'What-if' : 'the first tab after What-if'}`,
      target !== null && target === (lang === 'en' ? 'whatif' : 'validation'), { cutAt0, strip: g0.strip, order: g0.order });
    if (!target) return;
    const T1 = `${T}home_${n}right_`;

    // ---- Home, then n x ArrowRight --------------------------------------------------------------------------------
    await focusTab('details');
    await key('Home');
    await stripTo0();
    const before = await geom();
    for (let i = 0; i < n; i += 1) await key('ArrowRight');
    await page.waitForTimeout(200);
    const g1 = await geom();
    L.check(`${T1}selected: Home then ${n}x ArrowRight selects ${target} (aria-selected only there) and focuses it`, g1.selected.join() === target && g1.active === target, brief(g1));
    L.check(`${T1}inside: #tab-${target} lies fully inside the #bottom-tabs rect (left >= strip left, right <= strip right, 1 px)`, inside(g1, target), { rect: g1.rects[target], strip: g1.strip });
    L.check(`${T1}order: the visible tab order did not change`, JSON.stringify(g1.order) === JSON.stringify(before.order), g1.order);
    L.check(`${T1}no_page_scroll: window.scrollY and the panels did not scroll`, samePos(before, g1), { before: before.scrollY, after: g1.scrollY, panels: g1.panels });
    await shot(`tabstrip-after-home-${n}right-${lang}`);

    // ---- a click on the last, partly cut off tab ------------------------------------------------------------------
    await focusTab('details');
    await key('Home');
    await stripTo0();
    const c0 = await geom();
    const cut = c0.order.filter((id) => c0.rects[id].left < c0.strip.right - 6 && c0.rects[id].right > c0.strip.right + TOL);
    L.check(`${T}click_precondition_cut: at scrollLeft 0 exactly one tab is partly cut off at the right edge, and it is not the first`, cut.length === 1 && cut[0] !== c0.order[0], { cut, strip: c0.strip, rects: c0.rects });
    if (cut.length) {
      const id = cut[0];
      const r = c0.rects[id];
      const x = (r.left + c0.strip.right) / 2; // the middle of the part that shows
      const y = await page.evaluate((i) => { const b = document.getElementById('tab-' + i).getBoundingClientRect(); return b.top + b.height / 2; }, id);
      const hit = await page.evaluate(([px, py]) => { const e = document.elementFromPoint(px, py); const b = e && e.closest('[role="tab"]'); return b ? b.dataset.tab : null; }, [x, y]);
      L.check(`${T}click_precondition_hit: the click point is on the visible part of ${id}`, hit === id, { id, hit, x, y });
      await page.mouse.click(x, y);
      await page.waitForTimeout(250);
      const c1 = await geom();
      L.check(`${T}click_selected: the click selects ${id}`, c1.selected.join() === id, brief(c1));
      L.check(`${T}click_inside: the clicked, partly cut off tab ${id} is fully inside the strip afterwards`, inside(c1, id), { rect: c1.rects[id], strip: c1.strip });
      L.check(`${T}click_no_page_scroll: window.scrollY and the panels did not scroll`, samePos(c0, c1), { before: c0.scrollY, after: c1.scrollY, panels: c1.panels });
      // a second click on the same, already selected tab, half visible again: it must be revealed too
      await stripTo0();
      const c2 = await geom();
      if (c2.rects[id].right > c2.strip.right + TOL) {
        const x2 = (c2.rects[id].left + c2.strip.right) / 2;
        // the bottom panel changes height with the tab shown, so the strip may have moved: read its y again
        const y = await page.evaluate((i) => { const b = document.getElementById('tab-' + i).getBoundingClientRect(); return b.top + b.height / 2; }, id);
        const hit2 = await page.evaluate(([px, py]) => { const e = document.elementFromPoint(px, py); const b = e && e.closest('[role="tab"]'); return b ? b.dataset.tab : (e ? e.tagName + '.' + e.className : null); }, [x2, y]);
        await page.mouse.click(x2, y);
        await page.waitForTimeout(250);
        const c3 = await geom();
        L.check(`${T}click_again_inside: a click on the already selected, half visible tab ${id} reveals it as well`, hit2 === id && c3.selected.join() === id && inside(c3, id), { hit2, selected: c3.selected, rect: c3.rects[id], strip: c3.strip });
      } else {
        L.check(`${T}click_again_inside: a click on the already selected, half visible tab ${id} reveals it as well`, false, 'the strip did not return to scrollLeft 0 with the tab cut off');
      }
    }

    // ---- programmatic select ----------------------------------------------------------------------------------------
    await focusTab('details');
    await page.evaluate(() => window.ftaShell.openTab('details'));
    await stripTo0();
    const p0 = await geom();
    await page.evaluate((i) => window.ftaShell.openTab(i), target);
    await page.waitForTimeout(250);
    const p1 = await geom();
    L.check(`${T}programmatic_inside: a programmatic select of ${target} (openTab) brings it fully inside the strip`, p1.selected.join() === target && inside(p1, target), { rect: p1.rects[target], strip: p1.strip, selected: p1.selected });
    L.check(`${T}programmatic_no_page_scroll: window.scrollY and the panels did not scroll`, samePos(p0, p1), { before: p0.scrollY, after: p1.scrollY, panels: p1.panels });

    // ---- End, then Home ---------------------------------------------------------------------------------------------
    await focusTab('whatif');
    const e0 = await geom();
    await key('End');
    await page.waitForTimeout(150);
    const e1 = await geom();
    const lastId = e1.order[e1.order.length - 1];
    L.check(`${T}end_inside: End selects the last tab (${lastId}) and it is fully inside the strip`, e1.selected.join() === lastId && inside(e1, lastId), { selected: e1.selected, rect: e1.rects[lastId], strip: e1.strip });
    await key('Home');
    await page.waitForTimeout(150);
    const e2 = await geom();
    const firstId = e2.order[0];
    L.check(`${T}home_inside: Home selects the first tab (${firstId}), fully inside the strip, with scrollLeft 0`, e2.selected.join() === firstId && inside(e2, firstId) && e2.strip.scrollLeft <= TOL, { selected: e2.selected, rect: e2.rects[firstId], strip: e2.strip });
    L.check(`${T}end_home_no_page_scroll: window.scrollY and the panels did not scroll through End and Home`, samePos(e0, e1) && samePos(e0, e2), { y: [e0.scrollY, e1.scrollY, e2.scrollY], panels: e2.panels });
  };

  // ================================================================================================================
  // eta: the seven greyed tabs, Grid included
  // ================================================================================================================
  const caseEta = async (lang) => {
    const T = `tabstrip_eta_${lang}_`;
    L.check(`${T}mode_switched: the mode select switches to ETA (What-if greyed)`, await setMode('ETA'));
    const grid = await tabState('grid');
    const ccf = await tabState('ccf');
    const wi = await tabState('whatif');
    L.check(`${T}grid_greyed: #tab-grid has .is-unavailable and data-unavailable="eta"`, Boolean(grid) && grid.cls && grid.un === 'eta', grid);
    L.check(`${T}ccf_whatif_greyed: #tab-ccf and #tab-whatif have .is-unavailable and data-unavailable="eta" (as before)`, Boolean(ccf && wi) && ccf.cls && ccf.un === 'eta' && wi.cls && wi.un === 'eta', { ccf, wi });
    L.check(`${T}grid_title: the Grid title is not empty and equals the What-if title`, Boolean(grid) && Boolean(grid.title) && Boolean(wi) && grid.title === wi.title, { grid: grid && grid.title, whatif: wi && wi.title });
    L.check(`${T}grid_title_text: the Grid title is the text of tab.etaUnavailable (${lang})`, Boolean(grid) && grid.title === ETA_TEXT[lang], { grid: grid && grid.title, want: ETA_TEXT[lang] });
    const list = await greyed();
    const details = await tabState('details');
    L.check(`${T}seven_greyed: exactly the seven tabs quant, cutsets, importance, uncertainty, ccf, whatif and grid are greyed`, list.length === 7 && list.join() === GREYED.join(), list);
    L.check(`${T}details_not_greyed: #tab-details is not greyed (no class, no data-unavailable)`, Boolean(details) && !details.cls && details.un === null, details);

    // the shot: strip at the left, Details selected, the pointer on Grid (its tooltip is the title logged above)
    await page.evaluate(() => window.ftaShell.openTab('details'));
    await stripTo0();
    await page.locator('#tab-grid').hover({ force: true });
    await page.waitForTimeout(700);
    await shot(`tabstrip-eta-${lang}`);

    // a greyed tab still opens and shows the notice, and the arrow keys still move on
    await page.locator('#tab-grid').click();
    const notice = await waitFor(async () => page.locator('#tabpanel-grid .anl-eta').isVisible());
    const gSel = await geom();
    L.check(`${T}grid_opens_notice: clicking the greyed Grid tab selects it and #tabpanel-grid shows .anl-eta`, notice && gSel.selected.join() === 'grid', { notice, selected: gSel.selected });
    await key('ArrowRight');
    const g2 = await geom();
    L.check(`${T}arrow_from_grid: ArrowRight from the greyed Grid tab selects the next tab (quant) and focuses it`, g2.selected.join() === 'quant' && g2.active === 'quant', brief(g2));
    await key('ArrowLeft');
    await key('ArrowLeft');
    const g3 = await geom();
    L.check(`${T}arrow_back: ArrowLeft twice goes through Grid to Details`, g3.selected.join() === 'details' && g3.active === 'details', brief(g3));
  };

  // ================================================================================================================
  // fta_back: no greying left
  // ================================================================================================================
  const caseBack = async (lang) => {
    const T = `tabstrip_fta_${lang}_`;
    await page.evaluate(() => window.ftaShell.openTab('details'));
    L.check(`${T}mode_switched: the mode select switches back to FTA (What-if not greyed)`, await setMode('FTA'));
    const grid = await tabState('grid');
    L.check(`${T}grid_clean: #tab-grid has no .is-unavailable, no title and no data-unavailable`, Boolean(grid) && !grid.cls && !grid.hasTitle && grid.un === null, grid);
    const list = await greyed();
    L.check(`${T}none_greyed: zero greyed tabs in the strip`, list.length === 0, list);
  };

  const errMark = app.errMark();
  try {
    await openDoc();
    await app.setAdvanced(true);
    for (const lang of ['en', 'ja']) {
      await app.setLanguage(lang);
      const cur = await page.evaluate(() => window.ftaShell.language);
      L.check(`tabstrip_language_${lang}: the language is ${lang}`, cur === lang, cur);
      for (const [name, fn] of [['scroll', caseScroll], ['eta', caseEta], ['fta', caseBack]]) {
        try { await fn(lang); } catch (e) {
          L.check(`tabstrip_${name}_${lang}: did not complete`, false, String((e && e.message) || e).split('\n')[0].slice(0, 400));
        }
      }
    }
  } catch (e) {
    L.check('tabstrip_advanced: did not complete', false, String((e && e.message) || e).split('\n')[0].slice(0, 400));
  }

  // ================================================================================================================
  // basic: Grid hidden, selection works, nothing scrolls
  // ================================================================================================================
  try {
    const T = 'tabstrip_basic_';
    await app.setLanguage('en');
    await app.setAdvanced(false);
    await page.waitForTimeout(300);
    await page.evaluate(() => window.ftaShell.openTab('details'));
    await stripTo0();
    const b0 = await geom();
    const gridTab = await tabState('grid');
    L.check(`${T}grid_hidden: with Advanced off the Grid tab is hidden and not in the visible order`, Boolean(gridTab) && gridTab.hidden && !b0.order.includes('grid') && !b0.order.includes('whatif'), { grid: gridTab, order: b0.order });
    L.check(`${T}strip_fits: the strip of Basic mode does not scroll sideways (the reveal has nothing to do)`, b0.strip.scrollWidth <= b0.strip.clientWidth + TOL, b0.strip);
    await focusTab('details');
    await key('ArrowRight');
    const b1 = await geom();
    L.check(`${T}arrow_selects: ArrowRight selects the next visible tab (${b0.order[1]}), focused and fully inside the strip`, b1.selected.join() === b0.order[1] && b1.active === b0.order[1] && inside(b1, b0.order[1]), brief(b1));
    await key('End');
    const b2 = await geom();
    const last = b2.order[b2.order.length - 1];
    L.check(`${T}end_selects: End selects the last visible tab (${last}), inside the strip`, b2.selected.join() === last && inside(b2, last), brief(b2));
    await key('Home');
    const b3 = await geom();
    L.check(`${T}home_selects: Home selects the first tab, scrollLeft stays 0`, b3.selected.join() === b0.order[0] && b3.strip.scrollLeft <= TOL, brief(b3));
    L.check(`${T}no_page_scroll: window.scrollY, the strip and the panels did not scroll`, samePos(b0, b1) && samePos(b0, b2) && samePos(b0, b3) && b3.strip.scrollTop === b0.strip.scrollTop, { y: [b0.scrollY, b1.scrollY, b2.scrollY, b3.scrollY] });
    await page.locator('#tab-validation').click();
    await page.waitForTimeout(200);
    const b4 = await geom();
    L.check(`${T}click_selects: a click selects Validation`, b4.selected.join() === 'validation' && samePos(b0, b4), brief(b4));
  } catch (e) {
    L.check('tabstrip_basic: did not complete', false, String((e && e.message) || e).split('\n')[0].slice(0, 400));
  }

  const errs = app.errorsSince(errMark, []);
  L.check('tabstrip_console: no console errors in the tabstrip run', errs.length === 0, errs.slice(0, 5));
  await app.api('post', '/new', { force: true });
  fs.rmSync(path.join(root, docName), { force: true });
  L.info('SHOTS written by tabstrip: ' + JSON.stringify(shots.slice().sort()));
  await app.context.close();
}

L.runSection('tabstrip', main);
