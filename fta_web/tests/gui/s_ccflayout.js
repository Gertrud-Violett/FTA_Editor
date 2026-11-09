// F2 tree layout (T6 round 1, ui lens): the CCF badge in a tree row gives up
// space before the node name does. For the member rows of a small document
// (applied group and a not-applied group, en and ja) and of the 301-node
// fixture with ten groups, the name (.fta-tree-label) must not be truncated at
// the default 1600 x 1000 layout, and the badge must carry its full text in its
// title. A document without a group keeps its tree rows as they were.
// The 301-node rows sit three levels deep; whether their names fit depends on the
// font, so there the room is measured: a name that fits must not be cut, and a name
// that cannot fit next to the smallest badge may be cut, with the badge shrunk too and the row used up.
//   node s_ccflayout.js <url> <label> <root>
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const FIXTURE = path.join(L.REPO, 'fta_web', 'tests', 'fixtures', 'perf_ccf_301.json');

function leaf(id, name, probability) {
  return { id, name, type: 'Event', probability, logicGate: 'OR', notes: '', links: [], children: [] };
}
function gate(id, name, logicGate, children) {
  return Object.assign(leaf(id, name, 1.0), { type: 'Gate', logicGate, children });
}

/** Two pump members of an applied group, two valve members of a group that is not applied. */
function documentText() {
  const tree = Object.assign(leaf('root', 'Loss of cooling', 1.0), {
    type: 'Root',
    children: [
      gate('P', 'Pumps fail', 'AND', [leaf('A', 'Pump A', 1e-3), leaf('B', 'Pump B', 1e-3)]),
      gate('V', 'Valves fail', 'AND', [leaf('C', 'Valve C', 1e-3), leaf('D', 'Valve D', 2e-3)]),
      leaf('X', 'Pump C', 1e-3),
    ],
  });
  return JSON.stringify({ title: 'CCF layout', date: '2026-10-28', mode: 'FTA', tree }, null, 2);
}

async function run(url, label, root) {
  L.setSection('ccflayout[' + label + ']');
  const file = 'ccf_layout_' + label + '.json';
  fs.writeFileSync(path.join(root, file), documentText());
  const big = 'ccf_layout_big_' + label + '.json';
  fs.copyFileSync(FIXTURE, path.join(root, big));

  const app = await L.openApp(url, { viewport: { width: 1600, height: 1000 }, prefs: { 'fta.advanced': '1' } });
  const { page } = app;
  page.setDefaultTimeout(8000);
  const part = async (name, fn) => {
    try { await fn(); } catch (e) { L.check(name + ': did not complete', false, String((e && e.message) || e).split(String.fromCharCode(10))[0].slice(0, 300)); }
  };
  const reload = async () => {
    await page.reload();
    await L.waitBoot(page);
    await app.waitDiagram(60000);
    await page.waitForTimeout(1500); // the CCF state of this tree is loaded
  };
  const openDoc = async (name) => {
    await app.api('post', '/new', { force: true });
    const opened = await app.api('post', '/file/open', { path: path.join(root, name), force: true });
    if (opened.__error) throw new Error('could not open ' + name + ': ' + opened.status + ' ' + opened.code);
    await reload();
  };
  /** Per row: is the name cut off, and does the badge keep its full text in its title. */
  const rowsInfo = (ids) => page.evaluate(async (list) => {
    const { store } = await import('/static/js/store.js');
    const px = (v) => parseFloat(v) || 0;
    const wOf = (e) => (e ? e.getBoundingClientRect().width : 0);
    const textW = (e) => { const rg = document.createRange(); rg.selectNodeContents(e); return rg.getBoundingClientRect().width; };
    /** The geometry the name has to fit into, measured: the row's content width less every
     *  other item of the row and the gaps, with each badge at the smallest width the design
     *  lets it shrink to ("CCF: " and the not-applied marker whole, the group name at its
     *  min-width, or the badge's own min-width if that is larger). The name fits when its
     *  text is no wider than that. This leaves out the label's own cap (tree.js
     *  .fta-tree-label.has-ccf max-width: calc(100% - 17ch)), which on DejaVu Sans keeps
     *  about 10 px more for the badge than its minimum; it only matters for a name close
     *  to the room, and then the check fails rather than passes. */
    const roomOf = (row, label, badges) => {
      const cs = getComputedStyle(row);
      const kids = Array.from(row.children);
      const content = row.clientWidth - px(cs.paddingLeft) - px(cs.paddingRight);
      const gaps = px(cs.columnGap) * Math.max(0, kids.length - 1);
      const others = kids.filter((k) => k !== label && !badges.includes(k)).reduce((a, k) => a + wOf(k), 0);
      const mins = badges.map((b) => {
        const s = getComputedStyle(b);
        const frame = px(s.borderLeftWidth) + px(s.borderRightWidth) + px(s.paddingLeft) + px(s.paddingRight);
        const pre = b.querySelector('.fta-tree-ccf-pre');
        const name = b.querySelector('.fta-tree-ccf-name');
        const post = b.querySelector('.fta-tree-ccf-post');
        const parts = pre || name || post ? wOf(pre) + wOf(post) + (name ? px(getComputedStyle(name).minWidth) : 0) : 0;
        const own = s.boxSizing === 'border-box' ? px(s.minWidth) : px(s.minWidth) + frame;
        return Math.max(frame + parts, own);
      });
      const badgeMin = mins.reduce((a, v) => a + v, 0);
      const free = content - gaps - others - badgeMin;
      const text = textW(label);
      const r = (v) => Math.round(v * 10) / 10;
      return {
        fits: text + 0.5 <= free, text: r(text), label: r(wOf(label)), free: r(free), content: r(content), others: r(others), gaps: r(gaps), badgeMin: r(badgeMin),
        // the row is used up: no free space is left beside its items
        slack: r(content - gaps - kids.reduce((a, k) => a + wOf(k), 0)),
        // the badge has given up space too: it is narrower than its full width (its whole text, or its
        // max-width if that is smaller), its group name shows an ellipsis, and "CCF: " (and the marker)
        // are whole inside it
        badgeGaveWay: badges.length > 0 && badges.every((b) => {
          const s = getComputedStyle(b);
          const frame = px(s.borderLeftWidth) + px(s.borderRightWidth) + px(s.paddingLeft) + px(s.paddingRight);
          const name = b.querySelector('.fta-tree-ccf-name');
          const box = b.getBoundingClientRect();
          const spans = Array.from(b.querySelectorAll('.fta-tree-ccf-pre, .fta-tree-ccf-post'));
          const whole = spans.filter((p) => p.textContent).every((p) => { const q = p.getBoundingClientRect(); return q.width > 0 && q.left >= box.left - 0.5 && q.right <= box.right + 0.5; });
          if (!name) return false;
          const natural = frame + spans.reduce((a, p) => a + wOf(p), 0) + textW(name);
          const maxW = s.maxWidth.endsWith('px') ? px(s.maxWidth) + (s.boxSizing === 'border-box' ? 0 : frame) : Infinity;
          const shrank = box.width < Math.min(natural, maxW) - 0.5;
          return shrank && textW(name) > wOf(name) + 0.01 && whole;
        }),
      };
    };
    const out = [];
    for (const id of list) {
      store.jumpTo(id);
      await new Promise((r) => setTimeout(r, 120));
      const item = document.querySelector('#tree-root li.fta-tree-item[data-id="' + id + '"]');
      const label = item && item.querySelector(':scope > .fta-tree-row .fta-tree-label');
      const badges = item ? Array.from(item.querySelectorAll(':scope > .fta-tree-row .fta-tree-ccf')) : [];
      out.push({
        id,
        text: label ? label.textContent : null,
        // scrollWidth is a rounded integer: a name cut by a fraction of a pixel still
        // gets its ellipsis, so the width of the text itself is compared too.
        cut: label ? (label.scrollWidth > label.clientWidth || (() => {
          const rg = document.createRange();
          rg.selectNodeContents(label);
          return rg.getBoundingClientRect().width > label.getBoundingClientRect().width + 0.01;
        })()) : null,
        badges: badges.map((b) => ({ text: b.textContent, title: b.title, off: b.classList.contains('is-off'), width: Math.round(b.getBoundingClientRect().width) })),
        room: label ? roomOf(item.querySelector(':scope > .fta-tree-row'), label, badges) : null,
      });
    }
    return out;
  }, ids);

  // ---- a small document, applied and not applied, en and ja -----------------------------
  await part('small document', async () => {
    await openDoc(file);
    const made = await app.api('post', '/ccf/groups', { name: 'Feed pumps', model: 'beta', beta: 0.1, members: ['A', 'B'], source: '' });
    const made2 = await app.api('post', '/ccf/groups', { name: 'Relief valves', model: 'beta', beta: 0.2, members: ['C', 'D'], source: '' });
    L.check('setup: both groups made by the API', !made.__error && !made2.__error, { made: made.__error, made2: made2.__error });
    await reload();
    for (const lang of ['en', 'ja']) {
      await app.setLanguage(lang);
      await page.waitForTimeout(600);
      const rows = await rowsInfo(['A', 'B', 'C', 'D']);
      for (const r of rows) {
        L.check('small document (' + lang + '): the name "' + r.text + '" of ' + r.id + ' is not cut off', r.cut === false, r);
        L.check('small document (' + lang + '): ' + r.id + ' has its badge, with the full text in the title', r.badges.length === 1 && r.badges[0].title.includes(r.badges[0].text.replace(/…$/, '')) && r.badges[0].title.length >= r.badges[0].text.length, r.badges);
      }
      L.check('small document (' + lang + '): the not-applied group shows the dashed (off) badge', rows[2].badges[0] && rows[2].badges[0].off && rows[3].badges[0] && rows[3].badges[0].off, rows);
      await app.shot('ccf_layout_small_' + lang);
    }
    await app.setLanguage('en');
  });

  // ---- a long group name: the name is ellipsized, "CCF: " and "(off)" stay visible (R4) -----
  await part('long group name', async () => {
    await openDoc(file);
    const longA = 'Feed pumps of the primary cooling loop, train one';
    const longB = 'Relief valves of the secondary cooling loop, train two';
    const made = await app.api('post', '/ccf/groups', { name: longA, model: 'beta', beta: 0.1, members: ['A', 'B'], source: '' });
    const made2 = await app.api('post', '/ccf/groups', { name: longB, model: 'beta', beta: 0.2, members: ['C', 'D'], source: '' });
    L.check('setup: both long-named groups made by the API', !made.__error && !made2.__error, { made: made.__error, made2: made2.__error });
    await reload();
    for (const lang of ['en', 'ja']) {
      await app.setLanguage(lang);
      await page.waitForTimeout(600);
      const rows = await page.evaluate(async (list) => {
        const { store } = await import('/static/js/store.js');
        const out = [];
        for (const id of list) {
          store.jumpTo(id);
          await new Promise((r) => setTimeout(r, 120));
          const b = document.querySelector('#tree-root li.fta-tree-item[data-id="' + id + '"] > .fta-tree-row .fta-tree-ccf');
          if (!b) { out.push({ id, badge: null }); continue; }
          const rect = b.getBoundingClientRect();
          const part = (cls) => { const p = b.querySelector('.' + cls); const r = p && p.getBoundingClientRect(); return r ? { text: p.textContent, left: r.left, right: r.right, width: r.width } : null; };
          const nameEl = b.querySelector('.fta-tree-ccf-name');
          out.push({
            id, text: b.textContent, title: b.title, off: b.classList.contains('is-off'),
            left: rect.left, right: rect.right,
            pre: part('fta-tree-ccf-pre'), name: part('fta-tree-ccf-name'), post: part('fta-tree-ccf-post'),
            nameCut: nameEl ? nameEl.scrollWidth > nameEl.clientWidth : null,
          });
        }
        return out;
      }, ['A', 'C']);
      const inside = (p, r) => p && p.width > 0 && p.left >= r.left - 0.5 && p.right <= r.right + 0.5;
      const [a, c] = rows;
      L.check('long name (' + lang + '): the badge text is the whole label, in the title too', rows.every((r) => r.text && r.title.includes(r.text)), rows);
      L.check('long name (' + lang + '): the applied badge keeps "CCF: " visible and cuts only the name', inside(a.pre, a) && a.nameCut === true, a);
      L.check('long name (' + lang + '): the not-applied badge shows its marker in full inside the badge', c.off && inside(c.post, c) && inside(c.pre, c) && /off|未適用/.test(c.post.text), c);
      L.check('long name (' + lang + '): the not-applied name is cut, with a readable part left', c.nameCut === true && c.name.width > 8, c);
      await app.shot('ccf_layout_long_' + lang);
    }
    await app.setLanguage('en');
  });

  // ---- the diagram badge keeps clear of the q row above it, in both styles (R4) ------------
  await part('diagram badge spacing', async () => {
    await openDoc(file);
    const made = await app.api('post', '/ccf/groups', { name: 'Feed pumps', model: 'beta', beta: 0.1, members: ['A', 'B'], source: '' });
    L.check('setup: the group is made by the API', !made.__error, made.__error);
    await reload();
    for (const style of ['symbols', 'compact']) {
      await page.locator('#diagram-root [data-role="diagram-settings"]').click();
      const pop = page.locator('.diagram__popover');
      await pop.locator('select').nth(0).selectOption(style);
      await page.keyboard.press('Escape');
      await app.waitDiagram();
      await page.waitForTimeout(500);
      const info = await page.evaluate(() => {
        const boxes = Array.from(document.querySelectorAll('#diagram-root svg g.node')).filter((g) => (g.textContent || '').includes('CCF: Feed pumps'));
        const g = boxes[0];
        if (!g) return { found: boxes.length };
        const rows = Array.from(g.querySelectorAll('text')).map((t) => { const r = t.getBoundingClientRect(); return { text: t.textContent.trim(), top: r.top, bottom: r.bottom, height: r.height }; }).filter((r) => r.text);
        const at = rows.findIndex((r) => r.text.includes('CCF: Feed pumps'));
        const prev = at > 0 ? rows[at - 1] : null;
        // The line spacing of the box itself: the gap between its first two rows (name over q).
        return { found: boxes.length, rows: rows.map((r) => r.text), gap: prev ? rows[at].top - prev.bottom : null, base: rows.length > 1 ? rows[1].top - rows[0].bottom : null, badgeHeight: rows[at] ? rows[at].height : null };
      });
      L.check('diagram badge (' + style + '): two boxes carry it and a gap above it can be measured', info.found === 2 && typeof info.gap === 'number', info);
      L.check('diagram badge (' + style + '): the badge row does not overlap the row above it (gap ' + (info.gap && info.gap.toFixed(1)) + ' px)', typeof info.gap === 'number' && info.gap >= 1, info);
      await app.shot('ccf_diagram_badge_' + style);
    }
    await page.locator('#diagram-root [data-role="diagram-settings"]').click();
    await page.locator('.diagram__popover').locator('select').nth(0).selectOption('symbols');
    await page.keyboard.press('Escape');
  });

  // ---- the 301-node fixture, ten groups --------------------------------------------------
  await part('301-node fixture', async () => {
    await openDoc(big);
    const grp = await app.api('get', '/ccf/groups');
    const members = [];
    for (const g of grp.groups || []) for (const m of g.members || []) members.push(m);
    const want = ['C0_1_0', 'C0_1_1', 'C0_1_2'];
    L.check('the fixture groups hold C0_1_0, C0_1_1 and C0_1_2', want.every((id) => members.includes(id)), members.slice(0, 5));
    const rows = await rowsInfo(want);
    for (const r of rows) {
      // The measured room decides the branch: whether the name fits depends on the font (Segoe UI on Windows: it fits
      // with room to spare; DejaVu Sans on Linux CI: "Component 0.1.0" is ~15% wider and the row of
      // the default 1600 x 1000 layout cannot hold it next to even the smallest badge). Where the
      // measured room holds the name, it must not be cut; where it cannot, the badge must have shrunk too
      // (below its full width, "CCF: " whole, its group name cut) and the row must be used up (no slack).
      const fits = Boolean(r.room && r.room.fits);
      L.info('301 nodes: ' + r.id + (fits ? ': the row has room for the whole name' : ': the row cannot hold the whole name next to the smallest badge'), r.room);
      L.check('301 nodes: the name "' + r.text + '" of ' + r.id + ' is not cut off where the row has room for it, and otherwise the badge shrank too and the row is used up',
        Boolean(r.room) && (fits ? r.cut === false : (r.room.badgeGaveWay === true && r.room.slack <= 1)), r);
      // With the Windows UI font (the shipped app) the row of the default layout holds the whole name, as
      // this test has always required there: the measured branch above must not hide a row that got narrower.
      if (process.platform === 'win32') L.check('301 nodes (Windows UI font): the row has room for the whole name "' + r.text + '" of ' + r.id, fits, r.room);
      L.check('301 nodes: ' + r.id + ' shows a badge', r.badges.length >= 1, r.badges);
    }
    await app.shot('ccf_layout_big');
  });

  // ---- a document without a group: no badge, nothing new in the rows -----------------------
  await part('no group', async () => {
    await openDoc(file);
    const rows = await rowsInfo(['A', 'C']);
    L.check('without a group: no CCF badge in the tree', rows.every((r) => r.badges.length === 0), rows);
    L.check('without a group: the names are not cut off', rows.every((r) => r.cut === false), rows);
  });

  // ---- ancestorsOfMembers (the waiting dash): transfer targets and linked members (R4) ----
  await part('ancestorsOfMembers', async () => {
    const util = await import(require('url').pathToFileURL(path.join(L.REPO, 'fta_web', 'static', 'js', 'ccf_util.js')).href);
    const leafN = (id, extra) => Object.assign({ id, children: [], links: [] }, extra || {});
    const tree = {
      id: 'root',
      children: [
        { id: 'G1', children: [leafN('A'), leafN('B')], links: [] },                    // plain parent of members
        { id: 'T', children: [], links: [], transferTo: 'G1' },                         // transfer to such a gate
        { id: 'TT', children: [], links: [], transferTo: 'T' },                         // transfer to a transfer (fixpoint)
        { id: 'TN', children: [], links: [], transferTo: 'no_such_node' },              // transfer to nothing: not a gate above a member
        leafN('X', { links: [{ target_id: 'A' }] }),                                    // leaf with a link to a member
        { id: 'G2', children: [leafN('M', { links: [{ target_id: 'Y' }] }), leafN('Y')], links: [] }, // member whose link points at a non-member
        { id: 'G3', children: [leafN('N', { links: [{ target_id: 'gone' }] })], links: [] },          // member whose link resolves nowhere
        { id: 'G4', children: [leafN('Z')], links: [] },                                // no member below
      ],
    };
    const analysis = { ccfGroups: [{ id: 'g1', name: 'Pumps', members: ['A', 'B'] }, { id: 'g2', name: 'Other', members: ['M', 'N'] }] };
    const got = Array.from(util.ancestorsOfMembers(tree, analysis)).sort();
    const want = ['G1', 'G2', 'G3', 'M', 'T', 'TT', 'X', 'root'].sort();
    // N has a link, but to nothing: it is not a gate (its value is its own).
    L.check('ancestorsOfMembers follows links, transferTo (to a fixpoint) and a member with a resolving link', JSON.stringify(got) === JSON.stringify(want), { got, want });
    L.check('ancestorsOfMembers: a transfer to a missing node, a member with a dead link and a node without members are not in it', !got.includes('TN') && !got.includes('N') && !got.includes('G4'), got);
    L.check('ancestorsOfMembers: a document without a group answers nothing', util.ancestorsOfMembers(tree, {}).size === 0, null);
  });

  const errs = app.errorsSince(0);
  L.check('no console errors', errs.length === 0, errs.slice(0, 5));
  await app.context.close();
}

L.runSection('ccflayout', run);
