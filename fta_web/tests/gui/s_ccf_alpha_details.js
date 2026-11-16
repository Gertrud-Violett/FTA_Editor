// F2A rework R1: the Details panel of a member of an applied ALPHA group (FN-41, FN-22).
// Defect found by the feature review: Details computed the beta split with beta = Number(null) = 0 and read
// "Independent part 0.00100" and "CCF event 0" where the diagram shows "indep. 9.55e-4". Details must show the
// server's Q_1 as the independent part and the server's subset events (never "CCF event 0"). Beta stays as it was.
//   node s_ccf_alpha_details.js <url> <label> <root>
'use strict';
const fs = require('fs');
const path = require('path');
const L = require('./lib');

function leaf(id, name) {
  return { id, name, type: 'Event', probability: 1e-3, logicGate: 'OR', notes: '', links: [], children: [] };
}

function documentText() {
  const tree = Object.assign(leaf('root', 'Cooling loss'), {
    type: 'Root', probability: 1.0, children: ['A', 'B', 'C'].map((id) => leaf(id, 'Valve ' + id)),
  });
  return JSON.stringify({ title: 'CCF alpha details', date: '2026-11-02', mode: 'FTA', tree }, null, 2);
}

// The expected numbers, from the formulas (m = 3, Q_t = 1e-3, alpha 0.955 / 0.034 / 0.011, sum 1):
//   staggered     Q_k = alpha_k / C(m-1, k-1) * Q_t                                   (NUREG/CR-5485 Eq. 5.6 p. 40)
//   non-staggered Q_k = k / C(m-1, k-1) * alpha_k / alpha_t * Q_t, alpha_t = sum k alpha_k = 1.056   (Eq. 5.7-5.9 p. 41)
const QT = 1e-3;
const ALPHA = [0.955, 0.034, 0.011];
const choose = (_n, k) => [1, 2, 1][k]; // C(2, k) for k = 0..2: all that m = 3 needs
function qk(scheme, k) {
  const alphaT = ALPHA.reduce((s, a, i) => s + (i + 1) * a, 0);
  return scheme === 'staggered'
    ? ALPHA[k - 1] / choose(2, k - 1) * QT
    : k / choose(2, k - 1) * (ALPHA[k - 1] / alphaT) * QT;
}

async function run(url, label, root) {
  L.setSection('ccf_alpha_details[' + label + ']');
  const file = 'ccf_alpha_details_' + label + '.json';
  fs.writeFileSync(path.join(root, file), documentText());
  const app = await L.openApp(url, { viewport: { width: 1600, height: 1000 } });
  const { page } = app;
  page.setDefaultTimeout(5000);
  const sf = 3;
  const part = async (name, fn) => {
    try { await fn(); } catch (e) { L.check(name + ': did not complete', false, String((e && e.message) || e).split('\n')[0].slice(0, 300)); }
  };
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
  const read = () => page.evaluate(() => {
    const r = document.querySelector('#details-root .fta-details-ccf');
    if (!r) return null;
    const txt = (e) => e.textContent.replace(/[ \s]+/g, ' ').trim();
    const o = { shown: !r.hidden && r.offsetParent !== null, text: txt(r), events: [] };
    r.querySelectorAll('[data-ccf]').forEach((e) => {
      if (e.dataset.ccf === 'event') o.events.push(txt(e));
      else o[e.dataset.ccf] = txt(e);
    });
    o.eventLabels = Array.from(r.querySelectorAll('.fta-details-ccf__line')).filter((l) => l.querySelector('[data-ccf="event"]')).map((l) => txt(l.firstElementChild));
    return o;
  });
  const showMember = async (lang) => {
    await app.setLanguage(lang);
    await app.clickTab('details');
    await app.selectTreeNode('B'); // another node first, so the panel repaints for A
    await app.selectTreeNode('A');
    await waitFor(async () => { const d = await read(); return d && d.shown && d.independent; }, 8000);
    return read();
  };
  const reload = async () => {
    await page.reload();
    await L.waitBoot(page);
    await app.waitDiagram();
  };

  let gid = null;
  await part('setup', async () => {
    await app.api('post', '/new', { force: true });
    const opened = await app.api('post', '/file/open', { path: path.join(root, file), force: true });
    if (opened.__error) throw new Error('could not open ' + file);
    const made = await app.api('post', '/ccf/groups', { name: 'Valves', model: 'alpha', alpha: ALPHA, testing: 'staggered', members: ['A', 'B', 'C'], source: '' });
    if (made.__error) throw new Error('could not create the group');
    gid = ((await app.api('get', '/ccf/groups')).groups[0] || {}).id;
    await reload();
  });

  for (const scheme of ['staggered', 'nonStaggered']) {
    await part(scheme, async () => {
      if (scheme !== 'staggered') {
        await app.api('patch', '/ccf/groups/' + gid, { testing: scheme });
        await reload();
      }
      const q1 = qk(scheme, 1);
      const events = [qk(scheme, 2), qk(scheme, 2), qk(scheme, 3)]; // A+B, A+C, A+B+C (size ascending, then group order)
      for (const lang of ['en', 'ja']) {
        const tag = scheme + ' ' + lang + ': ';
        const d = await showMember(lang);
        // textContent has no space between label and value, so the zero reads "CCF event0" / "CCF 事象0"
        const bad = lang === 'en' ? /CCF event\s*0(?![.\de])/ : /CCF 事象\s*0(?![.\de])/;
        L.check(tag + 'Details shows the CCF block of the member', Boolean(d) && d.shown && d.qt === L.fmt(QT, sf), d);
        L.check(tag + 'the independent part is the server Q_1 (' + L.fmt(q1, sf) + ')', Boolean(d) && d.independent === L.fmt(q1, sf), d);
        L.check(tag + 'the independent part is not the beta-null artefact (Q_t ' + L.fmt(QT, sf) + ')', Boolean(d) && d.independent !== L.fmt(QT, sf), d);
        L.check(tag + 'the subset events show the server Q_k (' + events.map((q) => L.fmt(q, sf)).join(', ') + ')',
          Boolean(d) && JSON.stringify(d.events) === JSON.stringify(events.map((q) => L.fmt(q, sf))), d);
        L.check(tag + 'the event lines name the members of each subset',
          Boolean(d) && d.eventLabels.length === 3 && d.eventLabels[0].includes('Valve A') && d.eventLabels[0].includes('Valve B')
            && !d.eventLabels[0].includes('Valve C') && d.eventLabels[2].includes('Valve C'), d);
        L.check(tag + 'no "CCF event 0" line', Boolean(d) && !bad.test(d.text) && !d.events.includes('0'), d);
        if (scheme === 'staggered') await app.shot('ccf_alpha_details_' + lang);
      }
    });
  }

  // Beta is unchanged: one group, the independent part (1 - beta) Q_t and the one CCF event beta Q_t.
  await part('beta', async () => {
    const r = await app.api('patch', '/ccf/groups/' + gid, { model: 'beta', beta: 0.1, alpha: null, testing: null });
    if (r.__error) throw new Error('could not switch the group to beta');
    await reload();
    const d = await showMember('en');
    L.check('beta: the independent part reads 9e-4 (' + L.fmt(9e-4, sf) + ')', Boolean(d) && d.independent === L.fmt(9e-4, sf), d);
    L.check('beta: the single CCF event reads 1e-4 (' + L.fmt(1e-4, sf) + ')', Boolean(d) && d.events.length === 1 && d.events[0] === L.fmt(1e-4, sf), d);
  });

  const errs = app.errorsSince(0, []);
  L.check('whole run: no console errors, page errors or failed /api requests', errs.length === 0, errs.slice(0, 5));
  await app.context.close();
}

L.runSection('ccf_alpha_details', run);
