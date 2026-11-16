// The editor version in the UI (feature R191, task T0), in a real browser.
//   node s_version.js <url> <label> <root>
//
// CR-20261115-version-in-ui: the browser tab reads "<file name> - FTA Editor <version>" (with "● " in front while unsaved)
// and a small muted "v<version>" is the last item of the top bar. BRIEF criteria 2 to 4:
//   identity   TOOL_VERSION is read from <repo>/fta_web/report_docx.py of the tree under test (never from the API). In en and ja,
//              Basic and Advanced, FTA and ETA, after load and after every language switch: document.title ends with
//              " - FTA Editor <version>" and there is exactly one #app-version, shown, with the text "v<version>".
//   placement  at 1100, MIN_WIDTH and SMALLEST_TESTED_WIDTH (see the constants), en and ja, Basic and Advanced: #app-version is inside the top bar, the last
//              (right-most) item of the row it sits on, on one line (no wrap, not clipped), not focusable and not a button, and no other
//              element of the bar overlaps it.
//   no shift   (Director ruling 1a) measured from the layout: the bar is laid out with the version shown, then with display:none
//              injected by this test, then shown again. No control changes its row or its height and the bar's height, top and
//              width do not change. The controls in the version's OWN row (the row it ends; at 900 px and below that row may
//              hold the headline) may move left by at most the version's margin box plus one gap, and #title-input may become
//              narrower by at most that much. A control that is not in that row does not move or change size. Nothing else
//              moves or changes size.
//   sweep      (Director ruling 1c) at every width 900 to 1920 px in 10 px steps (height 800), en and ja, Basic and Advanced (one
//              page per language and mode, resized), the version is SHOWN IN FULL (visible, one line, not clipped, last item of
//              its row, ruling 1a holds) or HIDDEN IN FULL (display:none, visibility:hidden or a zero box: no painted text, not
//              focusable, no box over a control), never partly clipped, and no existing control changes its row and the bar
//              height is the same as with display:none injected. Non-vacuity: shown in full at 1100 and 1920 (en, Basic) and at
//              1100 in every language and mode; the number of widths where it shows is reported with L.info. At 1100, 900 and
//              420 the "shown" checks below apply where the version shows and "hidden in full" where it does not.
//   tab title  (ruling 1c) document.title ends with ' - FTA Editor <version>' at every swept width and at every width of the
//              placement loop, whether the top-bar version is shown or hidden (version_sweep_* and version_tabtitle_*).
//   look       the computed text colour against the effective top-bar background (alpha handled) is at least 4.5:1 in the
//              light and the dark theme (and the system theme under a dark OS), en and ja; the colour is one of the muted text
//              tokens of the theme (--text-dim or --text-faint) and the text is not larger than a top-bar label.
// Nothing here pins a pixel size or a font metric (Linux CI draws with DejaVu Sans, Windows with Segoe UI): every number
// is read from the layout of the run itself.
// Four shots (en and ja, 1100 and MIN_WIDTH, named version-<lang>-<width>.png) are taken after all the assertions, with the
// pointer moved away and nothing focused. Environment: FTA_VERSION_SHOTS=<dir> sets where they go; otherwise
// <main folder>/.division/artifacts/release-1.9.1/ui (the main folder is found through git), otherwise the run's output folder.
//
// Every check name starts with version_.
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const L = require('./lib');

// The minimum width at which the full "no layout shift" rule is checked. SPEC defines no minimum supported width. The app's own
// responsive breakpoint is `@media (max-width: 900px)` in app.css and 900 is the narrowest size of s_treeclick.js, so 900 is
// the minimum here; the shots are 1100 and MIN_WIDTH. One constant: change it here only.
//
// The narrowest window any existing GUI test opens the whole shell at is 420 x 860 (s_view.js:156: 1920, 1366, 900 and 420; it
// checks no horizontal page scroll and that the panels and the headline are visible, not the top bar; s_whatifr2.js uses 440).
// SMALLEST_TESTED_WIDTH is checked too, but WITHOUT the strict no-shift rule: measured on a made-up front end (the version
// after #capabilities-host), the strict rule holds at 420 in English and fails in Japanese, where the last row (capabilities +
// end group) is full to the edge, so any version item there makes the bar a row taller. Keeping every control in place at 420
// would need a bespoke responsive re-ordering of existing controls. There the checks are: one #app-version, text, inside the
// bar, right-most of its row, one line, not focusable, no overlap, and no sideways scroll added by the version.
const MIN_WIDTH = 900;
const SMALLEST_TESTED_WIDTH = 420;
const WIDE_WIDTH = 1100;
const HEIGHT = 800;
const TOL = 1; // px of sub-pixel noise in layout comparisons
const MIN_CONTRAST = 4.5; // WCAG AA for normal text

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const first = (e) => String((e && e.message) || e).split('\n')[0].slice(0, 400);

/** TOOL_VERSION of the tree under test (the repo this suite sits in), read from the source file, not from the server. */
function toolVersion() {
  const text = fs.readFileSync(path.join(L.REPO, 'fta_web', 'report_docx.py'), 'utf8');
  const m = /^TOOL_VERSION\s*=\s*["']([^"']+)["']/m.exec(text);
  return m ? m[1] : null;
}

/** Where the four shots go (see the header). */
function shotDir() {
  if (process.env.FTA_VERSION_SHOTS) return path.resolve(process.env.FTA_VERSION_SHOTS);
  try {
    const common = execFileSync('git', ['-C', L.REPO, 'rev-parse', '--path-format=absolute', '--git-common-dir'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
    const main = path.dirname(path.resolve(common));
    if (fs.existsSync(path.join(main, '.division'))) return path.join(main, '.division', 'artifacts', 'release-1.9.1', 'ui');
  } catch (_e) { /* no git, or not a clone: fall back to the output folder */ }
  return L.OUT;
}

const leaf = (id, name, q) => ({ id, name, type: 'Event', logicGate: 'OR', probability: q, notes: '', links: [], children: [], quant: { model: 'fixed' } });
const smallDoc = () => ({
  title: 'Version in the UI', date: '2026-11-15', mode: 'FTA',
  tree: { id: 'root', name: 'Top event', type: 'Root', logicGate: 'OR', probability: 1.0, notes: '', links: [], children: [leaf('E1', 'Pump E1', 1e-3), leaf('E2', 'Pump E2', 2e-3)] },
});

/**
 * One in-page measurement of the top bar: the layout with #app-version shown, with display:none injected on it, and shown
 * again; the facts about the span; the contrast data. Everything is read from the page, nothing is assumed.
 */
const measureBar = (pg) => pg.evaluate(() => {
  const bar = document.querySelector('header.topbar');
  const spans = Array.from(document.querySelectorAll('#app-version'));
  const span = spans[0] || null;
  const out = { bar: Boolean(bar), count: spans.length, present: Boolean(bar && span), innerWidth: window.innerWidth, title: document.title };
  if (!out.present) return out;

  const shown = (e) => {
    const cs = getComputedStyle(e);
    const r = e.getBoundingClientRect();
    return cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0;
  };
  const box = (e) => { const r = e.getBoundingClientRect(); return { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height }; };
  const others = Array.from(bar.querySelectorAll('*')).filter((e) => e !== span && !span.contains(e));
  const label = (e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\s+/).join('.') : '');
  const interactive = new Set(['BUTTON', 'INPUT', 'SELECT', 'LABEL', 'TEXTAREA', 'A']);
  out.meta = others.map((e) => ({
    label: label(e),
    id: e.id || '',
    containsSpan: e.contains(span),
    containsTitle: Boolean(document.getElementById('title-input')) && e.contains(document.getElementById('title-input')),
    leafish: interactive.has(e.tagName) || !Array.from(e.children).some((c) => c !== span && shown(c)),
  }));
  const snap = () => ({
    bar: box(bar),
    barScroll: { scrollWidth: bar.scrollWidth, clientWidth: bar.clientWidth },
    doc: { scrollWidth: document.scrollingElement.scrollWidth, innerWidth: window.innerWidth },
    items: others.map((e) => Object.assign({ vis: shown(e) }, box(e))),
  });

  out.shown = snap();

  // facts about the span in the shown layout
  const cs = getComputedStyle(span);
  const sr = span.getBoundingClientRect();
  const range = document.createRange();
  range.selectNodeContents(span);
  const lineTops = Array.from(new Set(Array.from(range.getClientRects()).filter((r) => r.width > 0).map((r) => Math.round(r.top))));
  const parentCs = getComputedStyle(span.parentElement);
  const gap = (s) => { const g = parseFloat(s.columnGap); return Number.isFinite(g) ? g : 0; };
  const cx = sr.left + sr.width / 2;
  const cy = sr.top + sr.height / 2;
  const hit = document.elementFromPoint(cx, cy);
  const barBox = box(bar);
  out.span = {
    text: span.textContent.trim(),
    rawText: span.textContent,
    tag: span.tagName.toLowerCase(),
    shown: shown(span),
    box: box(span),
    marginBox: sr.width + (parseFloat(cs.marginLeft) || 0) + (parseFloat(cs.marginRight) || 0),
    barGap: gap(getComputedStyle(bar)),
    parentGap: gap(parentCs),
    lineCount: lineTops.length,
    clipped: span.scrollWidth > span.clientWidth + 1,
    whiteSpace: cs.whiteSpace,
    insideBar: bar.contains(span) && sr.left >= barBox.left - 0.5 && sr.right <= barBox.right + 0.5 && sr.top >= barBox.top - 0.5 && sr.bottom <= barBox.bottom + 0.5,
    tabindex: span.getAttribute('tabindex'),
    role: span.getAttribute('role'),
    interactiveAncestor: Boolean(span.closest('button, a, label, summary, input, select, [role="button"], [role="link"], [tabindex]')),
    hitIsSelf: Boolean(hit) && (hit === span || span.contains(hit)),
    fontSize: parseFloat(cs.fontSize),
    labelFontSize: (() => { const l = bar.querySelector('.topbar__label'); return l ? parseFloat(getComputedStyle(l).fontSize) : null; })(),
  };
  // Director ruling 1c: facts that tell "shown in full" from "hidden in full" from a partly clipped string
  const textRects = Array.from(range.getClientRects()).filter((r) => r.width > 0 && r.height > 0);
  out.span.hasBox = span.getClientRects().length > 0;
  out.span.displayNone = cs.display === 'none';
  out.span.visibilityHidden = cs.visibility === 'hidden';
  out.span.zeroBox = sr.width <= 0 || sr.height <= 0;
  out.span.overflowX = cs.overflowX;
  // text painted outside the span's own box (a width or max-width that cuts it with overflow visible)
  // (or outside the box of an ancestor that clips: the bar or a group between it and the span)
  const clippers = [];
  for (let a = span.parentElement; a && bar.contains(a); a = a.parentElement) {
    const acs = getComputedStyle(a);
    if (a === bar || acs.overflowX !== 'visible' || acs.overflowY !== 'visible') clippers.push(a.getBoundingClientRect());
    if (a === bar) break;
  }
  out.span.textOutside = textRects.some((r) => r.right > sr.right + 0.5 || r.left < sr.left - 0.5 || r.bottom > sr.bottom + 0.5 || r.top < sr.top - 0.5
    || clippers.some((c) => r.right > c.right + 0.5 || r.left < c.left - 0.5));
  // not shown by the test above, but the text is still painted: not hidden in full (a zero box with overflow visible)
  out.span.leak = !out.span.shown && !out.span.displayNone && !out.span.visibilityHidden && textRects.length > 0 && cs.overflowX === 'visible';
  // focus: a span that can take focus is a defect
  span.focus();
  out.span.focusable = document.activeElement === span;
  if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur();

  // overlap with any other element of the bar that does not contain the span, and the row the span sits on
  const rects = others.map((e, i) => ({ e, i, r: e.getBoundingClientRect() }));
  out.overlaps = rects
    .filter(({ e, r }) => shown(e) && !e.contains(span) && Math.min(r.right, sr.right) - Math.max(r.left, sr.left) > 0.5 && Math.min(r.bottom, sr.bottom) - Math.max(r.top, sr.top) > 0.5)
    .map(({ e }) => label(e));
  const TOL_PAGE = 1; // page.evaluate serialises this function: the module's TOL is not visible here
  const row = rects.filter(({ e, i, r }) => out.meta[i].leafish && shown(e) && !e.contains(span)
    && ((r.top + r.bottom) / 2 >= sr.top - TOL_PAGE && (r.top + r.bottom) / 2 <= sr.bottom + TOL_PAGE
      || (sr.top + sr.bottom) / 2 >= r.top && (sr.top + sr.bottom) / 2 <= r.bottom));
  out.row = { count: row.length, idx: row.map(({ i }) => i), rightEdgeOfOthers: row.length ? Math.max(...row.map(({ r }) => r.right)) : null, beyond: row.filter(({ r }) => r.right > sr.left + 1).map(({ e }) => label(e)) };

  // with the span removed from the layout (display:none, injected here), and restored
  const had = span.getAttribute('style');
  span.style.setProperty('display', 'none', 'important');
  out.hidden = snap();
  if (had === null) span.removeAttribute('style'); else span.setAttribute('style', had);
  out.again = snap();
  return out;
}).catch((e) => ({ error: String((e && e.message) || e) }));

/** Contrast and token facts for the current theme and language. */
const measureLook = (pg) => pg.evaluate(() => {
  const span = document.getElementById('app-version');
  if (!span) return { present: false };
  const canvas = document.createElement('canvas');
  canvas.width = 1; canvas.height = 1;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  const parse = (s) => {
    const m = /^rgba?\(([^)]+)\)$/.exec(String(s).trim());
    if (m) {
      const p = m[1].split(/[\s,/]+/).filter(Boolean).map((x) => (x.endsWith('%') ? Number(x.slice(0, -1)) / 100 : Number(x)));
      if (p.length >= 3 && p.every((x) => Number.isFinite(x))) return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
    }
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = '#000';
    ctx.fillStyle = s;
    ctx.fillRect(0, 0, 1, 1);
    const d = ctx.getImageData(0, 0, 1, 1).data;
    return { r: d[0], g: d[1], b: d[2], a: d[3] / 255 };
  };
  const over = (top, under) => ({
    r: top.r * top.a + under.r * (1 - top.a),
    g: top.g * top.a + under.g * (1 - top.a),
    b: top.b * top.a + under.b * (1 - top.a),
    a: 1,
  });
  const lin = (v) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const lum = (c) => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  const problems = [];
  // background: the layers from the span up to the first opaque one, composed over each other
  const layers = [];
  let el = span;
  let opaque = false;
  while (el) {
    const cs = getComputedStyle(el);
    if (el !== span && Number(cs.opacity) < 1) problems.push('an ancestor has opacity < 1: ' + el.tagName);
    const bg = parse(cs.backgroundColor);
    if (cs.backgroundImage !== 'none' && (el === span || !opaque)) problems.push('a background image on ' + el.tagName + (el.id ? '#' + el.id : '') + ' below the opaque layer');
    layers.push(bg);
    if (bg.a >= 0.999) { opaque = true; break; }
    el = el.parentElement;
  }
  let bgc = opaque ? layers[layers.length - 1] : { r: 255, g: 255, b: 255, a: 1 };
  for (let i = layers.length - (opaque ? 2 : 1); i >= 0; i -= 1) bgc = over(layers[i], bgc);
  const scs = getComputedStyle(span);
  const fg = parse(scs.color);
  const alpha = fg.a * Number(scs.opacity);
  const text = over({ r: fg.r, g: fg.g, b: fg.b, a: alpha }, bgc);
  const l1 = lum(text);
  const l2 = lum(bgc);
  const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  const probe = (token) => {
    const p = document.createElement('span');
    p.style.color = 'var(' + token + ')';
    document.body.appendChild(p);
    const c = getComputedStyle(p).color;
    p.remove();
    return c;
  };
  const theme = document.documentElement.getAttribute('data-theme');
  return {
    present: true,
    ratio,
    problems,
    text: 'rgb(' + [text.r, text.g, text.b].map(Math.round).join(',') + ')',
    background: 'rgb(' + [bgc.r, bgc.g, bgc.b].map(Math.round).join(',') + ')',
    spanColor: scs.color,
    spanOpacity: Number(scs.opacity),
    tokens: { dim: probe('--text-dim'), faint: probe('--text-faint'), main: probe('--text') },
    theme,
    dark: window.matchMedia('(prefers-color-scheme: dark)').matches,
  };
}).catch((e) => ({ error: String((e && e.message) || e) }));

/** The problems of one placement measurement (shown vs display:none vs shown again). */
function shiftProblems(m) {
  const probs = [];
  const A = m.shown;
  const H = m.hidden;
  const B = m.again;
  const gap = Math.max(m.span.barGap, m.span.parentGap);
  const maxShift = m.span.marginBox + gap + TOL;
  const same = (x, y) => Math.abs(x - y) <= TOL;
  if (!same(A.bar.height, H.bar.height)) probs.push('bar height ' + H.bar.height + ' -> ' + A.bar.height);
  if (!same(A.bar.top, H.bar.top)) probs.push('bar top ' + H.bar.top + ' -> ' + A.bar.top);
  if (!same(A.bar.width, H.bar.width)) probs.push('bar width ' + H.bar.width + ' -> ' + A.bar.width);
  if (A.items.length !== H.items.length) { probs.push('the element lists differ'); return probs; }
  const titleIdx = m.meta.findIndex((x) => x.id === 'title-input');
  const t = titleIdx >= 0 ? H.items[titleIdx] : null;
  if (!t || !t.vis) { probs.push('#title-input is not visible in the bar'); return probs; }
  // the span's own row, measured: the leaf items found in its vertical band (m.row.idx) and the span itself give the band of the
  // row in the shown layout; an item belongs to the row when its whole vertical extent lies inside that band.
  // Ruling 1c: a version that is hidden in full (display:none, or inside a hidden ancestor) takes no room at all: there is no row and
  // every control must keep its box; a hidden version that still has a box in the layout (visibility:hidden, a zero-size box) has
  // the row it sits in, found from its top edge.
  let rowTop = null;
  let rowBottom = null;
  if (m.span.shown) {
    if (!m.row || !Array.isArray(m.row.idx) || m.row.idx.length === 0) { probs.push('the row of the version has no other item to measure'); return probs; }
    const rowItems = m.row.idx.map((k) => A.items[k]).filter((x) => x && x.vis);
    rowTop = Math.min(m.span.box.top, ...rowItems.map((x) => x.top));
    rowBottom = Math.max(m.span.box.bottom, ...rowItems.map((x) => x.bottom));
  }
  for (let i = 0; i < A.items.length; i += 1) {
    const a = A.items[i];
    const h = H.items[i];
    const meta = m.meta[i];
    if (a.vis !== h.vis) { probs.push(meta.label + ' became ' + (a.vis ? 'visible' : 'hidden')); continue; }
    if (!h.vis) continue;
    const isTitle = i === titleIdx;
    // vertical: no control changes its row or its height
    if (!same(a.top, h.top)) probs.push(meta.label + ' top ' + h.top.toFixed(1) + ' -> ' + a.top.toFixed(1));
    if (!same(a.height, h.height)) probs.push(meta.label + ' height ' + h.height.toFixed(1) + ' -> ' + a.height.toFixed(1));
    // width: only the title field (and what holds it or the version) may change, and only by the version's room (ruling 1a)
    const dW = a.width - h.width;
    if (isTitle) {
      if (dW > TOL || dW < -maxShift) probs.push('#title-input width ' + h.width.toFixed(1) + ' -> ' + a.width.toFixed(1) + ' (allowed: narrower by at most ' + maxShift.toFixed(1) + ')');
    } else if (meta.containsTitle || meta.containsSpan) {
      if (Math.abs(dW) > maxShift) probs.push(meta.label + ' width ' + h.width.toFixed(1) + ' -> ' + a.width.toFixed(1));
    } else if (Math.abs(dW) > TOL) {
      probs.push(meta.label + ' width ' + h.width.toFixed(1) + ' -> ' + a.width.toFixed(1));
    }
    // horizontal (ruling 1a): only the controls in the version's own row may move, and only to the left, by at most the version's
    // box plus one gap; a control that is not in that row does not move at all
    const dL = a.left - h.left;
    const inRow = m.span.shown ? (a.top >= rowTop - TOL && a.bottom <= rowBottom + TOL)
      : (m.span.hasBox && !m.span.displayNone && m.span.box.top >= a.top - TOL && m.span.box.top <= a.bottom + TOL);
    if (inRow) {
      if (dL > TOL || dL < -maxShift) probs.push(meta.label + ' left ' + h.left.toFixed(1) + ' -> ' + a.left.toFixed(1) + ' (allowed: left by at most ' + maxShift.toFixed(1) + ', it is in the row of the version)');
    } else if (Math.abs(dL) > TOL) {
      probs.push(meta.label + ' left ' + h.left.toFixed(1) + ' -> ' + a.left.toFixed(1) + ' (not in the row of the version: it must not move)');
    }
  }
  // restoring the span restores the layout (the test itself leaves nothing behind)
  for (let i = 0; i < A.items.length; i += 1) {
    const a = A.items[i];
    const b = B.items[i];
    if (a.vis !== b.vis || Math.abs(a.left - b.left) > TOL || Math.abs(a.top - b.top) > TOL || Math.abs(a.width - b.width) > TOL || Math.abs(a.height - b.height) > TOL) {
      probs.push(m.meta[i].label + ' did not return to its box after the injected display:none was removed');
      break;
    }
  }
  return probs;
}

/** Ruling 1c: the version is SHOWN IN FULL: visible, one line box, not clipped (neither by its own box nor painted outside it). */
const shownInFull = (sp) => sp.shown && sp.lineCount === 1 && !sp.clipped && !sp.textOutside && sp.hitIsSelf;
/** Ruling 1c: the version is HIDDEN IN FULL: no visible box, no painted text, not focusable, no box overlapping a control. */
const hiddenInFull = (m) => !m.span.shown && !m.span.leak && !m.span.focusable && m.overlaps.length === 0;

/**
 * Ruling 1c, one width of the sweep: everything that must hold at that width, as a list of problems (empty = fine).
 * Shown: shown in full, last item of its row, inside the bar, not focusable, no overlap. Hidden: hidden in full. Either way no
 * control changes its row and the bar keeps its height (shiftProblems), and the version text is in the DOM.
 */
function sweepProblems(m, vtext, suffix) {
  if (m.error) return ['not measured: ' + m.error];
  // Ruling 1c: the tab title carries the version at every width, whether the top-bar version is shown or hidden
  const titleProb = typeof m.title === 'string' && m.title.endsWith(suffix) ? [] : ['the tab title ' + JSON.stringify(m.title) + ' does not end with ' + JSON.stringify(suffix)];
  if (!m.present || m.count !== 1) return titleProb.concat(['no single #app-version in the top bar (count ' + m.count + ')']);
  const sp = m.span;
  const probs = titleProb;
  if (sp.text !== vtext) probs.push('text ' + JSON.stringify(sp.text) + ' is not ' + vtext);
  if (sp.shown) {
    if (!shownInFull(sp)) probs.push('shown but not in full (lines ' + sp.lineCount + ', clipped ' + sp.clipped + ', text outside its box ' + sp.textOutside + ', hit self ' + sp.hitIsSelf + ')');
    if (!sp.insideBar) probs.push('not inside the top bar');
    if (!(m.row.count >= 1 && m.row.beyond.length === 0)) probs.push('not the last item of its row (beyond: ' + JSON.stringify(m.row.beyond) + ')');
    if (m.overlaps.length) probs.push('overlaps ' + JSON.stringify(m.overlaps));
    if (sp.focusable || sp.tabindex !== null || sp.role !== null || sp.interactiveAncestor) probs.push('focusable or interactive');
  } else if (!hiddenInFull(m)) {
    probs.push('hidden but not in full (painted text ' + sp.leak + ', focusable ' + sp.focusable + ', overlaps ' + JSON.stringify(m.overlaps) + ')');
  }
  for (const p of shiftProblems(m).slice(0, 6)) probs.push(p);
  return probs;
}

async function main(url, label, root) {
  L.setSection('version[' + label + ']');
  const V = toolVersion();
  L.check('version_source: TOOL_VERSION is read from fta_web/report_docx.py of the tree under test and looks like a version', typeof V === 'string' && /^\d+\.\d+\.\d+/.test(V), V);
  const docName = 'version_doc_' + label + '.json';
  const stem = 'version_doc_' + label;
  fs.writeFileSync(path.join(root, docName), JSON.stringify(smallDoc(), null, 2));
  const suffix = ' - FTA Editor ' + V;
  const vtext = 'v' + V;

  const app = await L.openApp(url, { viewport: { width: WIDE_WIDTH, height: HEIGHT }, colorScheme: 'light', prefs: { 'fta.advanced': '0', 'fta.theme': 'light', 'fta.language': 'en' } });
  const { page } = app;
  page.setDefaultTimeout(8000);
  page.on('dialog', (d) => { d.accept().catch(() => {}); });
  const errMark = app.errMark();
  const waitFor = async (fn, timeout = 2500) => {
    const t0 = Date.now();
    for (;;) {
      let v = false;
      try { v = await fn(); } catch (_e) { v = false; }
      if (v) return true;
      if (Date.now() - t0 > timeout) return false;
      await sleep(60);
    }
  };
  const settle = async (ms = 350) => { await page.waitForTimeout(ms); };
  const openDoc = async () => {
    await app.api('post', '/new', { force: true });
    const opened = await app.api('post', '/file/open', { path: path.join(root, docName), force: true });
    if (opened.__error) throw new Error('could not open ' + docName + ': ' + opened.status + ' ' + opened.code);
    await page.reload();
    await L.waitBoot(page);
    await app.waitDiagram(60000);
    await page.waitForTimeout(500);
  };
  const readIdentity = () => page.evaluate(() => {
    const spans = Array.from(document.querySelectorAll('#app-version'));
    const sel = document.getElementById('mode-select');
    const toggle = document.getElementById('advanced-toggle');
    return {
      title: document.title,
      lang: window.ftaShell.language,
      mode: sel ? sel.value : null,
      advanced: toggle ? toggle.checked : null,
      spans: spans.map((e) => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return { text: e.textContent.trim(), shown: cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0 }; }),
    };
  });
  const titleOk = (s) => typeof V === 'string' && s.title.endsWith(suffix) && s.title.length > suffix.length
    && (s.title.startsWith(stem) || s.title.startsWith('● ' + stem));
  const spanOk = (s) => typeof V === 'string' && s.spans.length === 1 && s.spans[0].text === vtext && s.spans[0].shown;

  try {
    await openDoc();

    // ================================================================================================================
    // identity: title and span after load, and in every combination of language, Basic/Advanced and FTA/ETA
    // ================================================================================================================
    const afterLoad = async () => { await waitFor(async () => (await readIdentity()).title.endsWith(suffix)); return readIdentity(); };
    const s0 = await afterLoad();
    L.check('version_title_after_load: after load document.title is "<file name> - FTA Editor ' + V + '" (the file name and the unsaved marker stay)', titleOk(s0), s0);
    L.check('version_span_after_load: after load there is exactly one shown #app-version with the text v' + V, spanOk(s0), s0);

    for (const lang of ['en', 'ja']) {
      await app.setLanguage(lang);
      for (const advanced of [false, true]) {
        await app.setAdvanced(advanced);
        for (const mode of ['FTA', 'ETA']) {
          await page.locator('#mode-select').selectOption(mode);
          await settle();
          const tag = lang + '_' + (advanced ? 'advanced' : 'basic') + '_' + mode.toLowerCase();
          await waitFor(async () => (await readIdentity()).title.endsWith(suffix));
          const s = await readIdentity();
          L.check('version_setup_' + tag + ': the language, Basic/Advanced and mode are what the case says', s.lang === lang && s.advanced === advanced && s.mode === mode, s);
          L.check('version_title_' + tag + ': document.title ends with " - FTA Editor ' + V + '" after the switch', titleOk(s), s.title);
          L.check('version_span_' + tag + ': exactly one shown #app-version, text v' + V, spanOk(s), s.spans);
        }
      }
      await page.locator('#mode-select').selectOption('FTA');
      await settle();
    }
    // and back from ja to en: the title follows the language switch in both directions
    await app.setLanguage('en');
    await waitFor(async () => (await readIdentity()).lang === 'en' && (await readIdentity()).title.endsWith(suffix));
    const sBack = await readIdentity();
    L.check('version_title_back_to_en: after switching from ja back to en the language is en and document.title ends with " - FTA Editor ' + V + '"', sBack.lang === 'en' && titleOk(sBack), sBack);
    L.check('version_span_back_to_en: after switching back to en there is exactly one shown #app-version, text v' + V, spanOk(sBack), sBack.spans);
    await app.setAdvanced(true);

    // ================================================================================================================
    // placement and layout: 1100, MIN_WIDTH and SMALLEST_TESTED_WIDTH, en and ja, Basic and Advanced
    // ================================================================================================================
    for (const width of [WIDE_WIDTH, MIN_WIDTH, SMALLEST_TESTED_WIDTH]) {
      await page.setViewportSize({ width, height: HEIGHT });
      // a fresh page at this width: the top bar of the app can stay wider than a narrow window after a switch to ETA and back
      // (an existing behaviour that is not this feature's), so the layout is measured from a clean load
      await page.reload();
      await L.waitBoot(page);
      await app.waitDiagram(60000);
      await page.waitForTimeout(500);
      for (const lang of ['en', 'ja']) {
        await app.setLanguage(lang);
        for (const advanced of [true, false]) {
          await app.setAdvanced(advanced);
          await settle(500);
          const tag = lang + '_' + width + '_' + (advanced ? 'advanced' : 'basic');
          const m = await measureBar(page);
          if (m.error) { L.check('version_measure_' + tag + ': the bar was measured', false, m.error); continue; }
          L.check('version_measure_' + tag + ': the window is ' + width + ' px wide and the top bar exists', m.innerWidth === width && m.bar, { innerWidth: m.innerWidth, bar: m.bar });
          L.check('version_count_' + tag + ': exactly one #app-version inside header.topbar', m.count === 1 && m.present, { count: m.count, present: m.present });
          if (!m.present) {
            for (const name of ['inbar', 'rightmost', 'oneline', 'notfocusable', 'nooverlap', 'noshift']) L.check('version_' + name + '_' + tag + ': nothing to measure, #app-version is missing', false, 'no #app-version in the top bar');
            continue;
          }
          const sp = m.span;
          // Director ruling 1c: at every width the version is shown in full or hidden in full; at WIDE_WIDTH it must be shown (no
          // vacuous pass by hiding it); at MIN_WIDTH and SMALLEST_TESTED_WIDTH the "shown" checks below apply where it shows
          L.check('version_text_' + tag + ': the text is v' + V + (width === WIDE_WIDTH ? ' and the version is shown' : ' (shown, or hidden in full)'),
            typeof V === 'string' && sp.text === vtext && (sp.shown || width !== WIDE_WIDTH), { text: sp.text, shown: sp.shown });
          L.check('version_tabtitle_' + tag + ': document.title ends with " - FTA Editor ' + V + '" whether the top-bar version is shown or hidden (ruling 1c)',
            typeof V === 'string' && typeof m.title === 'string' && m.title.endsWith(suffix), { title: m.title, shown: sp.shown });
          L.check('version_fullorhidden_' + tag + ': the version is shown in full (visible, not clipped) or hidden in full (display:none, visibility:hidden or a zero box; no painted text, not focusable, no box over a control), never a partly clipped string',
            shownInFull(sp) || hiddenInFull(m), { shown: sp.shown, clipped: sp.clipped, textOutside: sp.textOutside, lines: sp.lineCount, leak: sp.leak, focusable: sp.focusable, overlaps: m.overlaps });
          L.check('version_inbar_' + tag + ': #app-version lies inside the top bar rect (where it shows)', !sp.shown || sp.insideBar, { span: sp.box, bar: m.shown.bar });
          L.check('version_rightmost_' + tag + ': where shown, the version is the last item of its row (the row has at least one other item and none of them ends right of the version\'s left edge)',
            !sp.shown || (m.row.count >= 1 && m.row.beyond.length === 0), m.row);
          L.check('version_oneline_' + tag + ': where shown, the text is one line box, not clipped', !sp.shown || (sp.lineCount === 1 && !sp.clipped && !sp.textOutside && sp.hitIsSelf), { lines: sp.lineCount, clipped: sp.clipped, textOutside: sp.textOutside, whiteSpace: sp.whiteSpace, hitIsSelf: sp.hitIsSelf });
          L.check('version_notfocusable_' + tag + ': not focusable, no tabindex, no role, not a button, link, label or input, not inside one',
            !sp.focusable && sp.tabindex === null && sp.role === null && sp.tag !== 'button' && sp.tag !== 'a' && !sp.interactiveAncestor, { focusable: sp.focusable, tabindex: sp.tabindex, role: sp.role, tag: sp.tag, interactiveAncestor: sp.interactiveAncestor });
          L.check('version_nooverlap_' + tag + ': no other element of the bar overlaps #app-version', m.overlaps.length === 0, m.overlaps);
          const visibleBefore = m.hidden.items.filter((x) => x.vis).length;
          const probs = shiftProblems(m);
          if (width >= MIN_WIDTH) {
            L.check('version_noshift_' + tag + ': no layout shift under ruling 1a (shown vs display:none injected: no control changes row or height, the bar height is the same, only the controls in the own row of the version move left by at most the version box plus one gap, #title-input narrows by at most that, nothing else moves or resizes)',
              visibleBefore >= 10 && probs.length === 0, { visibleControls: visibleBefore, problems: probs.slice(0, 8) });
          } else {
            L.info('version_noshift_' + tag + ' is reported, not asserted, below MIN_WIDTH (see the constants)', { visibleControls: visibleBefore, problems: probs.slice(0, 4) });
          }
          // the version adds no horizontal scroll: the page and the bar are no wider with it than without it
          L.check('version_noscroll_' + tag + ': the version adds no sideways scroll to the bar or the page',
            m.shown.barScroll.scrollWidth <= Math.max(m.shown.barScroll.clientWidth, m.hidden.barScroll.scrollWidth) + TOL
            && m.shown.doc.scrollWidth <= Math.max(m.shown.doc.innerWidth, m.hidden.doc.scrollWidth) + TOL, { shown: { barScroll: m.shown.barScroll, doc: m.shown.doc }, hidden: { barScroll: m.hidden.barScroll, doc: m.hidden.doc } });
        }
      }
    }

    // ================================================================================================================
    // sweep (Director ruling 1c): 900 to 1920 px in 10 px steps, en and ja, Basic and Advanced
    // ================================================================================================================
    // One page per language and mode, resized (the layout with the version shown against display:none injected, at each width).
    // At every width the version is shown in full or hidden in full, no existing control changes its row, the bar height is the
    // same, and where it shows ruling 1a holds. Non-vacuity: shown in full at 1100 and at 1920 in en Basic; the number of widths
    // where it shows is reported per language and mode.
    const SWEEP_FROM = 900;
    const SWEEP_TO = 1920;
    const SWEEP_STEP = 10;
    const settleLayout = () => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 30)))));
    for (const lang of ['en', 'ja']) {
      for (const advanced of [false, true]) {
        const mode = advanced ? 'advanced' : 'basic';
        const stag = lang + '_' + mode;
        await page.setViewportSize({ width: SWEEP_FROM, height: HEIGHT });
        await page.reload();
        await L.waitBoot(page);
        await app.waitDiagram(60000);
        await app.setLanguage(lang);
        await app.setAdvanced(advanced);
        await settle(400);
        let shownCount = 0;
        let total = 0;
        const shownAt = {};
        for (let width = SWEEP_FROM; width <= SWEEP_TO; width += SWEEP_STEP) {
          await page.setViewportSize({ width, height: HEIGHT });
          await settleLayout();
          const m = await measureBar(page);
          const probs = sweepProblems(m, vtext, suffix);
          if (!m.error && m.innerWidth !== width) probs.push('the window is ' + m.innerWidth + ' px wide, not ' + width);
          const full = !m.error && m.present && m.span.shown && shownInFull(m.span);
          total += 1;
          if (full) shownCount += 1;
          shownAt[width] = full;
          L.check('version_sweep_' + stag + '_' + width + ': the version is shown in full or hidden in full, no control changes its row, the bar height is unchanged (ruling 1c), and ruling 1a holds where it shows',
            probs.length === 0, { width, shown: m.span ? m.span.shown : null, bar: m.shown ? m.shown.bar.height : null, barWithout: m.hidden ? m.hidden.bar.height : null, problems: probs.slice(0, 8) });
        }
        L.info('version_sweep_' + stag + ': the version is shown in full at ' + shownCount + ' of ' + total + ' widths (' + SWEEP_FROM + ' to ' + SWEEP_TO + ' px, step ' + SWEEP_STEP + ')');
        L.check('version_sweep_shows_' + stag + ': the version is shown in full at at least one width of the sweep (a version that is always hidden fails)', shownCount >= 1, { shownCount, total });
        if (lang === 'en' && !advanced) {
          L.check('version_sweep_nonvacuous_' + stag + ': the version is shown in full at ' + WIDE_WIDTH + ' and at ' + SWEEP_TO + ' (en, Basic)',
            shownAt[WIDE_WIDTH] === true && shownAt[SWEEP_TO] === true, { at1100: shownAt[WIDE_WIDTH], at1920: shownAt[SWEEP_TO] });
        }
      }
    }

    // ================================================================================================================
    // look: contrast in every theme, the muted token, small
    // ================================================================================================================
    await page.setViewportSize({ width: WIDE_WIDTH, height: HEIGHT });
    const lookAt = async (tag, themeName) => {
      for (const lang of ['en', 'ja']) {
        await app.setLanguage(lang);
        await settle(250);
        const k = await measureLook(page);
        const name = tag + '_' + lang;
        if (k.error) { L.check('version_contrast_' + name + ': measured', false, k.error); continue; }
        if (!k.present) { L.check('version_contrast_' + name + ': #app-version exists to be measured', false, 'no #app-version'); continue; }
        L.check('version_contrast_' + name + ': text against the top-bar background is at least ' + MIN_CONTRAST + ':1 (' + themeName + ')',
          k.problems.length === 0 && k.ratio >= MIN_CONTRAST, { ratio: k.ratio, text: k.text, background: k.background, problems: k.problems });
        L.check('version_muted_' + name + ': the colour is the muted token (--text-dim or --text-faint) of the theme, not the main text colour',
          (k.spanColor === k.tokens.dim || k.spanColor === k.tokens.faint) && k.spanColor !== k.tokens.main, { spanColor: k.spanColor, tokens: k.tokens });
      }
    };
    const readTheme = () => page.evaluate(() => ({
      dataTheme: document.documentElement.getAttribute('data-theme'),
      stored: localStorage.getItem('fta.theme'),
      osDark: window.matchMedia('(prefers-color-scheme: dark)').matches,
    }));
    /** Reload with a stored theme choice (null = none, the system theme) under an emulated OS scheme. */
    const reloadWith = async (scheme, stored) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.evaluate((s) => { if (s === null) localStorage.removeItem('fta.theme'); else localStorage.setItem('fta.theme', s); }, stored);
      await page.reload();
      await L.waitBoot(page);
      await app.waitDiagram(60000);
      await settle(400);
    };
    // the toggle must really have switched: a theme that did not change fails here, before anything is measured
    for (const theme of ['light', 'dark']) {
      await app.setTheme(theme);
      await settle(200);
      const t = await readTheme();
      L.check('version_theme_' + theme + '_set: after the toggle <html data-theme> is ' + theme, t.dataTheme === theme, t);
      await lookAt(theme, theme + ' theme');
    }
    // the system theme under a dark OS: no data-theme on <html>, the prefers-color-scheme block of theme.css applies
    await reloadWith('dark', null);
    const sysT = await readTheme();
    // (the app stores the system choice as the string "system", or nothing: both mean "follow the OS")
    L.check('version_system_dark_no_theme_attr: with the system choice <html> has no data-theme', sysT.dataTheme === null && (sysT.stored === null || sysT.stored === 'system'), sysT);
    L.check('version_system_dark_os_is_dark: the emulated OS scheme is dark', sysT.osDark === true, sysT);
    await lookAt('system_dark', 'system theme, dark OS');
    // an explicit light theme under a dark OS must stay light
    await reloadWith('dark', 'light');
    const lightT = await readTheme();
    L.check('version_light_under_dark_os_set: with the stored choice light under a dark OS <html data-theme> is light and the OS is dark', lightT.dataTheme === 'light' && lightT.osDark === true, lightT);
    await lookAt('light_dark_os', 'light theme under a dark OS');
    await reloadWith('light', 'light');
    await app.setLanguage('en');
    const small = await measureBar(page);
    L.check('version_small: the version text is not larger than a top-bar label',
      small.present && Number.isFinite(small.span.labelFontSize) && small.span.fontSize <= small.span.labelFontSize + 0.01, small.present ? { font: small.span.fontSize, label: small.span.labelFontSize } : 'no #app-version');
  } catch (e) {
    L.check('version_run: did not complete', false, first(e));
  }

  // ================================================================================================================
  // shots, after the assertions: en and ja at 1100 and at MIN_WIDTH
  // ================================================================================================================
  const dir = shotDir();
  const shots = [];
  try {
    fs.mkdirSync(dir, { recursive: true });
    await app.setAdvanced(true);
    for (const width of [WIDE_WIDTH, MIN_WIDTH]) {
      await page.setViewportSize({ width, height: HEIGHT });
      for (const lang of ['en', 'ja']) {
        await app.setLanguage(lang);
        // no hover or focus highlight in the shot: the pointer goes to the empty corner and nothing keeps the focus
        await page.mouse.move(0, 0);
        await page.evaluate(() => { if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur(); });
        await page.waitForTimeout(500);
        const file = path.join(dir, 'version-' + lang + '-' + width + '.png');
        await page.screenshot({ path: file, fullPage: false });
        shots.push(file);
      }
    }
  } catch (e) {
    L.check('version_shots_taken: the four shots were written', false, first(e));
  }
  L.check('version_shots_written: four non-empty shots (en and ja at ' + WIDE_WIDTH + ' and ' + MIN_WIDTH + ')',
    shots.length === 4 && shots.every((f) => fs.existsSync(f) && fs.statSync(f).size > 1000), shots);
  L.info('SHOTS written by version: ' + JSON.stringify(shots));

  const errs = app.errorsSince(errMark, []);
  L.check('version_console: no console errors in the version run', errs.length === 0, errs.slice(0, 5));
  try { await app.api('post', '/new', { force: true }); } catch (_e) { /* */ }
  fs.rmSync(path.join(root, docName), { force: true });
  await app.context.close();
}

L.runSection('version', main);
