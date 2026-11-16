// fta_web/tests/perf/baseline_browser.js -- browser baselines of 1.8.1 (SPEC section 4).
//
//   PERF-6  on perf_grid_500.json, the 500 rows of perf_grid_500_paste.tsv are applied through
//           the existing node-update route (PATCH /api/nodes/<id>, one request per node, lambda
//           per year divided by 8760 into the stored per-hour value, T and source as given),
//           until the headline is updated. The clock starts before the first request and stops
//           when the top-bar headline shows the value the finished document has.
//   PERF-7  opening perf_grid_500.json (POST /api/file/open, the document installed in the
//           store as the Load action does) until the tree panel and the headline are drawn.
//   PERF-8  (browser part) one probability edit in the Details panel of perf_ccf_301_nogroups.json,
//           from the Enter key until the headline is updated.
//
// Condition (SPEC section 4, "Browser"): the GUI suite harness (fta_web/tests/gui/lib.js),
// Chromium, the dev server started with `uv run --frozen` (in the release worktree, port 8780),
// app loaded and fixture opened before timing, one discarded warm-up, then the median of 5.
// Every time is taken inside the page with performance.now(); the end of the clock is the first
// animation frame after the page shows the expected state.
//
//   node baseline_browser.js --repo <release worktree> --fixtures <fixtures dir> --out <result.json> [--port 8780]
//
// The fixtures are copied byte for byte into the server's sandbox root (its file API refuses
// paths outside the root); their SHA-256 is recorded. Nothing is asserted: it measures and records.
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const { spawn, spawnSync } = require('child_process');

const WARMUPS = 1;
const RUNS = 5;
const SIG_FIGS = 6;

function arg(name, dflt) {
  const i = process.argv.indexOf('--' + name);
  if (i === -1 || i + 1 >= process.argv.length) {
    if (dflt === undefined) { console.error('missing --' + name); process.exit(2); }
    return dflt;
  }
  return process.argv[i + 1];
}

const REPO = path.resolve(arg('repo'));
const FIXTURES = path.resolve(arg('fixtures'));
const OUT_FILE = path.resolve(arg('out'));
const PORT = Number(arg('port', '8780'));

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'fta_perf_'));
process.env.FTA_GUI_OUT = path.join(TMP, 'gui_out'); // lib.js makes its output folder at require time
const L = require(path.resolve(__dirname, '..', 'gui', 'lib.js'));

const median = (xs) => { const s = xs.slice().sort((a, b) => a - b); const n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; };
const sha256 = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---- server -------------------------------------------------------------------
function killTree(child) {
  if (!child || child.exitCode !== null) return;
  if (process.platform === 'win32') spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
  else { try { process.kill(-child.pid, 'SIGKILL'); } catch (_e) { child.kill('SIGKILL'); } }
}

async function startServer(root, home) {
  const args = ['run', '--frozen', '--extra', 'all', '--extra', 'test', 'python', 'fta_web/run.py',
    '--port', String(PORT), '--no-browser', '--root', root];
  const env = Object.assign({}, process.env, {
    HOME: home, USERPROFILE: home, PYTHONUTF8: '1', FTA_EDITOR_NO_FOLDER_PICKER: '1',
  });
  console.log('starting uv ' + args.join(' ') + '  (cwd ' + REPO + ')');
  const child = spawn('uv', args, { cwd: REPO, env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true, detached: process.platform !== 'win32' });
  let text = '';
  const url = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('no URL from the server within 120 s\n' + text.slice(-2000))), 120000);
    const onData = (buf) => {
      text += buf.toString('utf8');
      const m = /URL\s*:\s*(http:\/\/127\.0\.0\.1:\d+\/\?t=[A-Za-z0-9_-]+)/.exec(text);
      if (m) { clearTimeout(timer); resolve(m[1]); }
    };
    child.stdout.on('data', onData);
    child.stderr.on('data', onData);
    child.on('exit', (code) => { clearTimeout(timer); reject(new Error('server exited with ' + code + '\n' + text.slice(-2000))); });
  });
  child.stdout.removeAllListeners('data');
  child.stderr.removeAllListeners('data');
  child.stdout.resume();
  child.stderr.resume();
  child.removeAllListeners('exit');
  if (new URL(url).port !== String(PORT)) throw new Error('server did not take port ' + PORT + ': ' + url);
  return { child, url };
}

// ---- in-page helpers ----------------------------------------------------------
/** Wait until the headline text has not changed for `quietMs`; return it. */
async function settledHeadline(page, quietMs) {
  let last = null;
  let since = Date.now();
  for (;;) {
    const now = await page.evaluate(() => document.getElementById('headline-value').textContent.trim());
    if (now !== last) { last = now; since = Date.now(); }
    if (Date.now() - since >= (quietMs || 1500) && now !== '' && now !== '—') return now;
    await sleep(100);
  }
}

async function treeRows(page) {
  return page.evaluate(() => document.querySelectorAll('#tree-root li.fta-tree-item').length);
}

/**
 * Open a file in the page the way the Load action does (POST /api/file/open, then the document
 * payload merged into the store). With `expect` = {rows, headline} the call is timed and returns the
 * ms from just before the request to the first frame that shows both; without it, it returns at once.
 */
async function openInPage(page, file, expect) {
  return page.evaluate(async ([p, exp]) => {
    const token = sessionStorage.getItem('fta.session.token');
    const { store } = await import('/static/js/store.js');
    let timed = null;
    if (exp) {
      timed = new Promise((resolve) => {
        let waiting = false;
        const check = () => {
          if (waiting) return;
          const rows = document.querySelectorAll('#tree-root li.fta-tree-item').length;
          const head = document.getElementById('headline-value').textContent.trim();
          if (rows === exp.rows && head === exp.headline) {
            waiting = true;
            requestAnimationFrame(() => { observer.disconnect(); resolve(performance.now()); });
          }
        };
        const observer = new MutationObserver(check);
        observer.observe(document.body, { childList: true, subtree: true, characterData: true });
      });
    }
    const t0 = performance.now();
    const r = await fetch('/api/file/open', {
      method: 'POST',
      headers: { 'X-FTA-Token': token, 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ path: p, force: true }),
    });
    const payload = await r.json();
    if (!r.ok || payload.ok === false) throw new Error('open failed: ' + JSON.stringify(payload).slice(0, 300));
    delete payload.ok;
    store.setState({ ...(store.state || {}), ...payload });
    window.dispatchEvent(new CustomEvent('fta:document'));
    store.select(store.state.tree.id);
    if (!timed) return null;
    return (await timed) - t0;
  }, [file, expect || null]);
}

// ---- measurements -------------------------------------------------------------
async function perf6(page, root, rows) {
  const gridFile = path.join(root, 'perf_grid_500.json');
  await openInPage(page, gridFile);
  const original = await settledHeadline(page, 1500);
  const patches = rows.map((r) => ({ id: r.id, body: { quant: { lambda: r.lambdaPerHour, T: r.T, source: r.source } } }));

  async function apply(expectHeadline) {
    return page.evaluate(async ([list, exp]) => {
      const token = sessionStorage.getItem('fta.session.token');
      const el = document.getElementById('headline-value');
      let done = null;
      if (exp) {
        done = new Promise((resolve) => {
          let waiting = false;
          const check = () => {
            if (waiting || el.textContent.trim() !== exp) return;
            waiting = true;
            requestAnimationFrame(() => { observer.disconnect(); resolve(performance.now()); });
          };
          const observer = new MutationObserver(check);
          observer.observe(el, { childList: true, subtree: true, characterData: true });
        });
      }
      const t0 = performance.now();
      for (const p of list) {
        const r = await fetch('/api/nodes/' + encodeURIComponent(p.id), {
          method: 'PATCH',
          headers: { 'X-FTA-Token': token, 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify(p.body),
        });
        if (!r.ok) throw new Error('PATCH ' + p.id + ' -> ' + r.status + ' ' + (await r.text()).slice(0, 200));
      }
      const t1 = performance.now();
      await window.ftaShell.refresh();
      return { patchMs: t1 - t0, done: done ? (await done) - t0 : null };
    }, [patches, expectHeadline || null]);
  }

  // Warm-up (discarded): learn the headline the finished document shows.
  await apply(null);
  const finished = await settledHeadline(page, 1500);
  if (finished === original) throw new Error('PERF-6: the headline did not change (' + original + '); the rows are no change');
  const runs = [];
  const patchPhase = [];
  for (let i = 0; i < RUNS; i += 1) {
    await openInPage(page, gridFile);
    const back = await settledHeadline(page, 1500);
    if (back !== original) throw new Error('PERF-6: reopening gave headline ' + back + ', not ' + original);
    const res = await apply(finished);
    runs.push(res.done);
    patchPhase.push(res.patchMs);
    console.log('PERF-6 run ' + (i + 1) + ': ' + res.done.toFixed(1) + ' ms (requests ' + res.patchMs.toFixed(1) + ' ms)');
  }
  return {
    condition: 'browser', fixture: 'perf_grid_500.json', paste: 'perf_grid_500_paste.tsv',
    action: '500 x PATCH /api/nodes/<id> {quant:{lambda,T,source}} one request per node, then the page re-reads the document; stop when the headline shows the new value',
    requests: rows.length, warmups: WARMUPS, runs_ms: runs, median_ms: median(runs),
    requests_phase_ms: patchPhase, headline_before: original, headline_after: finished, sigFigs: SIG_FIGS,
  };
}

async function perf7(page, root) {
  const grid = path.join(root, 'perf_grid_500.json');
  const other = path.join(root, 'perf_ccf_301_nogroups.json');
  // Warm-up (discarded) and the target state: what the page shows once the grid is open.
  await openInPage(page, grid);
  const headline = await settledHeadline(page, 1500);
  const rows = await treeRows(page);
  const runs = [];
  for (let i = 0; i < RUNS; i += 1) {
    await openInPage(page, other); // a different document first, so the open has something to replace
    const otherHeadline = await settledHeadline(page, 1500);
    if (otherHeadline === headline) throw new Error('PERF-7: the two documents show the same headline');
    const ms = await openInPage(page, grid, { rows, headline });
    runs.push(ms);
    console.log('PERF-7 run ' + (i + 1) + ': ' + ms.toFixed(1) + ' ms');
  }
  return {
    condition: 'browser', fixture: 'perf_grid_500.json',
    action: 'POST /api/file/open and install the document in the store; stop at the first frame showing the settled tree rows and headline',
    treeRows: rows, headline, warmups: WARMUPS, runs_ms: runs, median_ms: median(runs), sigFigs: SIG_FIGS,
  };
}

async function perf8(app, root) {
  const { page } = app;
  const file = path.join(root, 'perf_ccf_301_nogroups.json');
  await openInPage(page, file);
  await settledHeadline(page, 1500);
  const target = 'C0_0_0';
  await page.evaluate(async (id) => { const { store } = await import('/static/js/store.js'); store.jumpTo(id); }, target);
  await page.waitForFunction((id) => {
    const code = document.querySelector('#details-root .fta-details-meta code');
    return code && code.textContent === id;
  }, target, { timeout: 15000 });
  const field = page.locator('#details-root .fta-details-form .fta-field')
    .filter({ has: page.locator('label', { hasText: 'Probability (base)' }) }).first()
    .locator('input,textarea').first();

  async function edit(value) {
    const before = await page.evaluate(() => document.getElementById('headline-value').textContent.trim());
    await page.evaluate((b) => {
      const el = document.getElementById('headline-value');
      window.__perf8 = { t0: null, t1: null };
      const state = window.__perf8;
      state.keydown = (e) => { if (e.key === 'Enter' && state.t0 === null) state.t0 = performance.now(); };
      document.addEventListener('keydown', state.keydown, true);
      state.done = new Promise((resolve) => {
        let waiting = false;
        const check = () => {
          if (waiting || state.t0 === null || el.textContent.trim() === b) return;
          waiting = true;
          requestAnimationFrame(() => { state.t1 = performance.now(); observer.disconnect(); resolve(); });
        };
        const observer = new MutationObserver(check);
        observer.observe(el, { childList: true, subtree: true, characterData: true });
      });
    }, before);
    await field.click();
    await page.keyboard.press('Control+A');
    await page.keyboard.type(String(value), { delay: 3 });
    await page.keyboard.press('Enter');
    const ms = await page.evaluate(async () => {
      await window.__perf8.done;
      document.removeEventListener('keydown', window.__perf8.keydown, true);
      return window.__perf8.t1 - window.__perf8.t0;
    });
    const after = await settledHeadline(page, 1000);
    return { ms, before, after };
  }

  await edit(0.002); // warm-up (discarded)
  const runs = [];
  const texts = [];
  for (let i = 0; i < RUNS; i += 1) {
    const r = await edit(0.003 + 0.001 * i);
    runs.push(r.ms);
    texts.push({ before: r.before, after: r.after });
    console.log('PERF-8 browser run ' + (i + 1) + ': ' + r.ms.toFixed(1) + ' ms');
  }
  // The headline on screen equals what the server computes for the edited document.
  const token = await page.evaluate(() => sessionStorage.getItem('fta.session.token'));
  const res = await fetch(new URL(app.page.url()).origin + '/api/analysis/summary', { headers: { 'X-FTA-Token': token, Accept: 'application/json' } });
  const summary = await res.json();
  const shown = await page.evaluate(() => document.getElementById('headline-value').textContent.trim());
  return {
    condition: 'browser', fixture: 'perf_ccf_301_nogroups.json', node: target,
    action: 'one probability edit in the Details panel (Probability (base)), from the Enter key until the headline shows the new value',
    warmups: WARMUPS, runs_ms: runs, median_ms: median(runs), headlines: texts,
    final_headline_shown: shown, final_headline_server: L.fmt(summary.headline, SIG_FIGS),
    sigFigs: SIG_FIGS,
  };
}

// ---- main ---------------------------------------------------------------------
function parsePaste(file, ids) {
  const lines = fs.readFileSync(file, 'utf8').split('\n').filter((l) => l.length > 0);
  if (lines.length !== ids.length) throw new Error('paste rows ' + lines.length + ' != events ' + ids.length);
  return lines.map((line, i) => {
    const [lambdaYear, t, source] = line.split('\t');
    return { id: ids[i], lambdaPerHour: Number(lambdaYear) / 8760, T: Number(t), source };
  });
}

function leafIds(node, out) {
  if (!node.children || node.children.length === 0) out.push(node.id);
  else node.children.forEach((c) => leafIds(c, out));
  return out;
}

async function main() {
  const names = ['perf_grid_500.json', 'perf_grid_500_paste.tsv', 'perf_ccf_301_nogroups.json'];
  const root = path.join(TMP, 'root');
  const home = path.join(TMP, 'home');
  fs.mkdirSync(root, { recursive: true });
  fs.mkdirSync(home, { recursive: true });
  const hashes = {};
  for (const n of names) {
    fs.copyFileSync(path.join(FIXTURES, n), path.join(root, n));
    hashes[n] = sha256(path.join(FIXTURES, n));
    if (sha256(path.join(root, n)) !== hashes[n]) throw new Error('copy of ' + n + ' differs');
  }
  const grid = JSON.parse(fs.readFileSync(path.join(FIXTURES, 'perf_grid_500.json'), 'utf8'));
  const rows = parsePaste(path.join(FIXTURES, 'perf_grid_500_paste.tsv'), leafIds(grid.tree, []));

  const server = await startServer(root, home);
  let result;
  try {
    const app = await L.openApp(server.url, {
      prefs: { 'fta.advanced': '1', 'fta.sigFigs': String(SIG_FIGS) },
      viewport: { width: 1600, height: 1000 },
    });
    const browserVersion = app.context.browser().version();
    const p6 = await perf6(app.page, root, rows);
    const p7 = await perf7(app.page, root);
    const p8 = await perf8(app, root);
    const errs = app.errors.filter((e) => e.type === 'pageerror' || e.type === 'http');
    await app.context.close();
    result = {
      PERF_6: p6, PERF_7: p7, PERF_8_browser: p8,
      pageErrors: errs.slice(0, 20),
      machine: {
        platform: os.platform() + ' ' + os.release(), cpu: os.cpus()[0].model, logicalCpus: os.cpus().length,
        memoryGB: Math.round(os.totalmem() / 1e9 * 10) / 10, node: process.version, chromium: browserVersion,
      },
      fixtureSha256: hashes,
    };
  } finally {
    killTree(server.child);
    await L.closeBrowser();
  }
  fs.writeFileSync(OUT_FILE, JSON.stringify(result, null, 2) + '\n');
  console.log('written ' + OUT_FILE);
  console.log('PERF-6 median ' + result.PERF_6.median_ms.toFixed(1) + ' ms; PERF-7 median ' + result.PERF_7.median_ms.toFixed(1)
    + ' ms; PERF-8 browser median ' + result.PERF_8_browser.median_ms.toFixed(1) + ' ms');
}

main().then(() => process.exit(0), (e) => { console.error(e && e.stack || e); process.exit(1); });
