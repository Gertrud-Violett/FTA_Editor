// fta_web/tests/gui/lib.js -- shared helpers for the real-browser GUI suite.
//
// Drives a separate browser (bundled Chromium by default, FTA_GUI_CHANNEL=chrome
// for an installed Google Chrome) with real mouse/keyboard input and compares
// what the GUI shows against what the API computes. Every browser context is a
// fresh temporary profile (empty localStorage), never the user's own profile.
//
// Sections are run by run.mjs as `node s_<name>.js <url> <label> <root>`:
//   url    the bootstrap URL with the session token (http://127.0.0.1:<port>/?t=...)
//   label  names the files a run leaves in the sandbox root and in OUT
//   root   the server's file-sandbox root (a local directory: sections write
//          input files there and open what s_core saved)
'use strict';
const path = require('path');
const fs = require('fs');
const { execFileSync } = require('child_process');
const { chromium } = require('playwright');

const HERE = __dirname;
const REPO = path.resolve(HERE, '..', '..', '..');
const OUT = path.resolve(process.env.FTA_GUI_OUT || path.join(HERE, 'out'));
fs.mkdirSync(OUT, { recursive: true });

const results = [];
let fails = 0;
let section = '';

function setSection(name) {
  section = name;
  console.log('===== ' + name);
}

function check(name, ok, extra) {
  const full = (section ? section + ': ' : '') + name;
  if (!ok) fails += 1;
  results.push({ name: full, ok: Boolean(ok), extra: ok ? undefined : extra });
  console.log((ok ? 'PASS ' : 'FAIL ') + full + (extra !== undefined && !ok ? '  ' + JSON.stringify(extra).slice(0, 900) : ''));
  return Boolean(ok);
}

function info(msg, extra) {
  console.log('INFO ' + msg + (extra !== undefined ? '  ' + JSON.stringify(extra).slice(0, 900) : ''));
}

// ---- number formatting mirror (fta_web/numfmt.py / static/js/numfmt.js) ----
// Plain/exponent form is chosen from the ROUNDED magnitude (1.7.1), so
// 0.00099996 at 3 s.f. reads "0.00100", as in the DOCX and the CLI.
function fmt(v, sf) {
  if (v === null || v === undefined || v === '') return '—';
  const num = Number(v);
  if (!Number.isFinite(num)) return '—';
  if (num === 0) return '0';
  const d = Math.min(6, Math.max(1, Math.round(sf)));
  const exp = num.toExponential(d - 1);
  const mag = Math.abs(Number(exp));
  if (mag < 1e-3 || mag >= 1e4) return exp.replace('e+', 'e');
  const text = num.toPrecision(d);
  return text.indexOf('e') === -1 ? text : String(Number(text));
}

/** Parse a GUI probability string ("1.23e-5", "0.500", "0") to a number. */
function parseNum(s) {
  if (s === null || s === undefined) return NaN;
  const txt = String(s).replace(/[\u00a0\s]/g, '').replace(/[−]/g, '-');
  if (txt === '' || txt === '—') return NaN;
  return Number(txt);
}

/** GUI text equals the API value formatted at sf sig figs. */
function sameAtSf(guiText, apiValue, sf) {
  return String(guiText).trim() === fmt(apiValue, sf);
}

// ---- sandbox inputs -----------------------------------------------------------
/** The FMEA sheet s_files imports and s_i18n previews (written into the root). */
const FMEA_CSV = '\ufeffFMEA ID,Item,Failure Mode,Cause,Severity,Occurrence,Detection,RPN,Failure rate (/h)\r\n'
  + 'F-001,Pump,Fails to start,Motor winding burnout,8,3,4,96,1.0e-6\r\n'
  + 'F-002,Relief valve,Stuck closed,Corrosion,9,2,5,90,\r\n'
  + 'F-003,Pressure sensor,No output,Connector fretting,6,4,3,72,5.0e-7\r\n'
  + ',,,,,,,,\r\n'
  + 'F-004,Bad row,,,x,99,,,abc\r\n';

function writeFmeaCsv(root) {
  const file = path.join(root, 'b2b_fmea.csv');
  fs.writeFileSync(file, FMEA_CSV);
  return file;
}

/** The file s_core saves through the GUI; every later section opens it. */
function coreFile(root, label) {
  return path.join(root, 'b2b_core_' + label + '.json');
}

/**
 * Run parse_exports.py (python-docx / openpyxl) in the project environment.
 * Same `uv run` extras as the dev server, so uv never re-syncs the venv the
 * running server is using.
 */
function parseExports(docxPath, xlsxPath) {
  const out = execFileSync('uv', ['run', '--frozen', '--extra', 'all', '--extra', 'test', 'python',
    path.join(HERE, 'parse_exports.py'), docxPath, xlsxPath], {
    cwd: REPO,
    env: Object.assign({}, process.env, { PYTHONUTF8: '1' }),
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  });
  return JSON.parse(out);
}

// ---- browser -----------------------------------------------------------------
let browser = null;

/**
 * FTA_GUI_CHANNEL: unset/"chromium" = Playwright's bundled Chromium (new
 * headless mode); "chrome" / "msedge" = the installed branded browser.
 * FTA_GUI_HEADFUL=1 shows the window.
 */
async function getBrowser() {
  if (browser) return browser;
  const channel = process.env.FTA_GUI_CHANNEL || 'chromium';
  browser = await chromium.launch({
    channel,
    headless: process.env.FTA_GUI_HEADFUL !== '1',
    args: ['--no-first-run', '--no-default-browser-check', '--disable-features=Translate'],
  });
  return browser;
}

async function closeBrowser() {
  if (browser) await browser.close();
  browser = null;
}

/**
 * Open the app in a fresh context (its own temp profile: localStorage empty).
 * prefs are written to localStorage before the first boot only.
 */
async function openApp(url, { prefs, viewport, colorScheme, locale } = {}) {
  const b = await getBrowser();
  const context = await b.newContext({
    viewport: viewport || { width: 1600, height: 1000 },
    acceptDownloads: true,
    colorScheme: colorScheme || 'light',
    locale: locale || 'en-US',
    permissions: ['clipboard-read', 'clipboard-write'],
  });
  const page = await context.newPage();
  const errors = [];
  const expected = [];
  page.on('console', (m) => {
    const type = m.type();
    if (type !== 'error' && type !== 'warning') return;
    const text = m.text();
    errors.push({ type, text, at: Date.now() });
  });
  page.on('pageerror', (e) => errors.push({ type: 'pageerror', text: e.message, at: Date.now() }));
  page.on('response', async (r) => {
    if (r.status() < 400 || !r.url().includes('/api/')) return;
    let body = '';
    try { body = (await r.text()).slice(0, 300); } catch (_e) { /* */ }
    errors.push({ type: 'http', text: r.status() + ' ' + r.request().method() + ' ' + r.url().replace(/^.*\/api/, '/api') + ' ' + body, at: Date.now() });
  });
  const p = Object.assign({ 'fta.advanced': '0', 'fta.theme': 'light', 'fta.language': 'en', 'fta.sigFigs': '3' }, prefs || {});
  await page.addInitScript((pp) => {
    try {
      if (sessionStorage.getItem('b2b.init')) return;
      sessionStorage.setItem('b2b.init', '1');
      localStorage.clear();
      for (const [k, v] of Object.entries(pp)) localStorage.setItem(k, v);
    } catch (_e) { /* */ }
  }, p);
  await page.goto(url);
  await waitBoot(page);
  const app = makeApp(page, context, errors, expected);
  return app;
}

async function waitBoot(page) {
  await page.waitForFunction(() => !document.documentElement.hasAttribute('data-booting'), null, { timeout: 30000 });
}

function makeApp(page, context, errors, expected) {
  // API calls go from Node (not the page), so a deliberate 4xx made by the
  // harness never shows up in the page console the suite audits.
  const origin = new URL(page.url()).origin;
  let token = null;
  const api = async (method, pth, body) => {
    if (!token) token = await page.evaluate(() => sessionStorage.getItem('fta.session.token'));
    const init = { method: method === 'del' ? 'DELETE' : method.toUpperCase(), headers: { 'X-FTA-Token': token, Accept: 'application/json' } };
    if (method !== 'get' && method !== 'del') { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body === undefined ? {} : body); }
    const r = await fetch(origin + '/api' + pth, init);
    const j = await r.json().catch(() => null);
    if (!r.ok || !j || j.ok === false) return { __error: true, status: r.status, code: j && j.error && j.error.code, message: j && j.error && j.error.message, detail: j && j.error && j.error.detail };
    delete j.ok;
    return j;
  };

  /** Raw fetch (no api.js) so failures do not go through the session logic. */
  const rawFetch = async (method, pth, body) => page.evaluate(async ([m, pp, bb]) => {
    const token = sessionStorage.getItem('fta.session.token');
    const init = { method: m.toUpperCase(), headers: { 'X-FTA-Token': token, Accept: 'application/json' } };
    if (bb !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(bb); }
    const r = await fetch('/api' + pp, init);
    const text = await r.text();
    let json = null;
    try { json = JSON.parse(text); } catch (_e) { /* */ }
    return { status: r.status, json, text: json ? undefined : text.slice(0, 300) };
  }, [method, pth, body]);

  const app = {
    page,
    context,
    errors,
    api,
    rawFetch,
    /** Errors since mark, excluding ones matching an allowed regex list. */
    errorsSince(mark, allow) {
      return errors.slice(mark).filter((e) => !(allow || []).some((re) => re.test(e.text)));
    },
    errMark() { return errors.length; },
    async settle(ms) {
      // wait for debounces (headline 400ms, validation 600, diagram 150) + network idle
      await page.waitForTimeout(ms === undefined ? 900 : ms);
      try { await page.waitForLoadState('networkidle', { timeout: 5000 }); } catch (_e) { /* */ }
    },
    async sf() {
      return page.evaluate(() => Number(localStorage.getItem('fta.sigFigs') || '3'));
    },
    async storeState() {
      return page.evaluate(async () => {
        const { store } = await import('/static/js/store.js');
        return { state: store.state, selectedId: store.selectedId };
      });
    },
    async selectedId() {
      return page.evaluate(async () => (await import('/static/js/store.js')).store.selectedId);
    },
    // ---------- GUI readers -----------------------------------------------
    async headline() {
      return page.evaluate(() => {
        const b = document.getElementById('headline-badge');
        const m = document.getElementById('headline-marker');
        return {
          value: document.getElementById('headline-value').textContent.trim(),
          badge: !b.hidden && b.offsetParent !== null,
          badgeTitle: b.title || '',
          marker: !!m && !m.hidden && m.offsetParent !== null,
        };
      });
    },
    async details() {
      return page.evaluate(() => {
        const root = document.getElementById('details-root');
        const meta = root.querySelector('.fta-details-meta');
        const spans = meta ? meta.querySelectorAll(':scope > span') : [];
        const id = spans[0] ? spans[0].querySelector('code').textContent : null;
        const calc = spans[1] ? spans[1].querySelector('b').textContent : null;
        const form = root.querySelector('.fta-details-form');
        const inputs = form ? Array.from(form.querySelectorAll('.fta-field')) : [];
        const fields = {};
        for (const f of inputs) {
          const lab = f.querySelector('label');
          const c = f.querySelector('input,select,textarea');
          if (!lab || !c) continue;
          fields[lab.textContent.trim()] = { value: c.value, readOnly: !!c.readOnly, disabled: !!c.disabled, hidden: !!f.closest('[hidden]') };
        }
        const zero = meta ? meta.querySelector('.fta-details-flag') : null;
        return { id, calc, fields, zero: zero ? !zero.hidden : false, visible: root.offsetParent !== null };
      });
    },
    /** Diagram labels: [{title, id, texts:[...]}] (resolved via the page's idMap logic). */
    async diagramNodes() {
      return page.evaluate(() => {
        const svg = document.querySelector('#diagram-root .diagram__canvas svg');
        if (!svg) return null;
        const out = [];
        svg.querySelectorAll('g.node').forEach((g) => {
          const title = g.querySelector('title');
          const texts = Array.from(g.querySelectorAll('text')).map((t) => t.textContent.replace(/\u00a0/g, ' ').trim()).filter(Boolean);
          out.push({
            title: title ? title.textContent.trim() : '',
            texts,
            cls: g.getAttribute('class') || '',
            selected: g.classList.contains('is-selected'),
            highlighted: g.classList.contains('is-highlighted'),
            overlay: g.classList.contains('has-overlay'),
          });
        });
        return out;
      });
    },
    async waitDiagram(timeout) {
      // wait until the diagram's latest render landed (no pending timer) -- poll text stability
      let last = '';
      const t0 = Date.now();
      for (;;) {
        await page.waitForTimeout(250);
        const now = await page.evaluate(() => {
          const svg = document.querySelector('#diagram-root .diagram__canvas svg');
          return svg ? svg.textContent.length + ':' + svg.querySelectorAll('g.node').length + ':' + svg.textContent.slice(0, 2000) : '';
        });
        if (now && now === last) return;
        last = now;
        if (Date.now() - t0 > (timeout || 15000)) return;
      }
    },
    async shot(name, opts) {
      const file = path.join(OUT, name + '.png');
      if (opts && opts.locator) await page.locator(opts.locator).screenshot({ path: file });
      else await page.screenshot({ path: file, fullPage: false });
      return file;
    },
    // ---------- GUI actions (real input) -----------------------------------
    async clickTab(id) {
      await page.locator('#tab-' + id).click();
      await page.waitForTimeout(150);
    },
    async selectTreeNode(id) {
      const row = page.locator('#tree-root li.fta-tree-item[data-id="' + id + '"] > .fta-tree-row');
      await row.scrollIntoViewIfNeeded();
      await row.click();
      await page.waitForTimeout(120);
    },
    async setAdvanced(on) {
      const cur = await page.evaluate(() => document.getElementById('advanced-toggle').checked);
      if (cur !== on) await page.locator('label.switch').click();
      await page.waitForTimeout(200);
    },
    async setSigFigs(n) {
      await page.locator('#sigfig-select').selectOption(String(n));
      await page.waitForTimeout(100);
    },
    async setLanguage(lang) {
      const cur = await page.evaluate(() => window.ftaShell.language);
      if (cur !== lang) await page.locator('#btn-lang').click();
      await page.waitForTimeout(200);
    },
    async setTheme(theme) {
      for (let i = 0; i < 4; i += 1) {
        const cur = await page.evaluate(() => localStorage.getItem('fta.theme') || 'system');
        if (cur === theme) return;
        await page.locator('#btn-theme').click();
        await page.waitForTimeout(100);
      }
    },
    /** Add a child to the currently selected node through the Add dialog. */
    async addViaDialog({ name, type, probability, gate, notes, useKeyboard }) {
      if (useKeyboard) await page.keyboard.press('Control+a');
      else await page.locator('.actionbar [data-action="add"]').click();
      const modal = page.locator('.fta-modal');
      await modal.waitFor({ state: 'visible', timeout: 5000 });
      // name (first), type, probability, gate, notes
      const nameInput = modal.locator('.fta-field input').nth(0);
      await nameInput.fill('');
      await nameInput.type(name, { delay: 5 });
      if (type !== undefined) {
        const typeInput = modal.locator('.fta-field input').nth(1);
        await typeInput.fill(type);
      }
      if (probability !== undefined) {
        const pInput = modal.locator('.fta-field input').nth(2);
        await pInput.click({ clickCount: 3 });
        await pInput.fill(String(probability));
      }
      if (gate !== undefined) {
        await modal.locator('.fta-field select').first().selectOption(gate);
      }
      if (notes !== undefined) {
        await modal.locator('.fta-field textarea').first().fill(notes);
      }
      const before = await app.selectedId();
      if (useKeyboard) {
        await nameInput.focus();
        await page.keyboard.press('Enter');
      } else {
        await modal.locator('.fta-modal-footer .fta-btn.is-primary').click();
      }
      await modal.waitFor({ state: 'detached', timeout: 5000 });
      // Wait for the new selection (actionAdd selects the new node once POST
      // /nodes answers). Polled from here: page.waitForFunction treats the
      // Promise an async predicate returns as truthy and never waits, which
      // let this return the PREVIOUS selection whenever the server was slow.
      return app.waitSelectionChange(before, 5000);
    },
    /** Poll the store until the selection differs from `before`; returns it. */
    async waitSelectionChange(before, timeout) {
      const t0 = Date.now();
      for (;;) {
        const now = await app.selectedId();
        if (now && now !== before) return now;
        if (Date.now() - t0 > (timeout || 5000)) throw new Error('selection stayed ' + before + ' for ' + (timeout || 5000) + ' ms');
        await page.waitForTimeout(25);
      }
    },
    /** Edit a Details text field by label through real typing + Enter/blur. */
    async editDetailsField(labelText, value, how) {
      const field = page.locator('#details-root .fta-details-form .fta-field').filter({ has: page.locator('label', { hasText: labelText }) }).first();
      const control = field.locator('input,textarea').first();
      await control.click();
      await page.keyboard.press('Control+A');
      await page.keyboard.type(String(value), { delay: 3 });
      if (how === 'tab') await page.keyboard.press('Tab');
      else await page.keyboard.press('Enter');
      await page.waitForTimeout(250);
    },
    async selectDetailsGate(gate) {
      const sel = page.locator('#details-root .fta-details-form select').first();
      await sel.selectOption(gate);
      await page.waitForTimeout(300);
    },
  };
  return app;
}

function writeResults(file) {
  fs.writeFileSync(path.join(OUT, file), JSON.stringify({ fails, results }, null, 2));
}

/**
 * Entry point of every section: `node s_<name>.js <url> [label] [root]`.
 * Prints "FAILS <n>" last; exit code 1 on any failed check or exception.
 */
function runSection(name, fn) {
  const [url, label = 'dev', root = ''] = process.argv.slice(2);
  if (!url) {
    console.error('usage: node s_' + name + '.js <url-with-token> [label] [sandbox-root]   (or use run.mjs)');
    process.exit(2);
  }
  (async () => {
    await fn(url, label, root);
    await closeBrowser();
    writeResults('results_' + name + '_' + label + '.json');
    console.log('FAILS ' + fails);
    process.exitCode = fails ? 1 : 0;
  })().catch(async (e) => {
    console.log('FAIL exception ' + ((e && e.stack) || e));
    fails += 1;
    results.push({ name: (section ? section + ': ' : '') + 'exception', ok: false, extra: String((e && e.stack) || e) });
    try { await closeBrowser(); } catch (_e) { /* */ }
    try { writeResults('results_' + name + '_' + label + '.json'); } catch (_e) { /* */ }
    console.log('FAILS ' + fails);
    process.exit(1);
  });
}

module.exports = {
  HERE, REPO, OUT, check, info, setSection, fmt, parseNum, sameAtSf, openApp, waitBoot, closeBrowser, getBrowser,
  writeResults, runSection, results, FMEA_CSV, writeFmeaCsv, coreFile, parseExports, get fails() { return fails; },
};
