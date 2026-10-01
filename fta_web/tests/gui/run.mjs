#!/usr/bin/env node
// run.mjs -- run the real-browser GUI suite (see README.md).
//
//   node run.mjs                 every section, against a dev server this script starts
//   node run.mjs tabs view       only these sections (core is added when they need its file)
//   node run.mjs --list          list the sections in run order
//
// Environment:
//   FTA_GUI_CHANNEL=chrome       drive an installed Google Chrome (default: Playwright's
//                                bundled Chromium; "msedge" works too)
//   FTA_GUI_HEADFUL=1            show the browser window
//   FTA_GUI_URL=<token URL>      use an already-running server instead of starting one
//                                (its --root must be a scratch folder on this machine)
//   FTA_GUI_ROOT=<dir>           that server's sandbox root (default: asked from the server)
//   FTA_GUI_EXE=<path>           start this packaged fta_editor executable instead of the
//                                dev server (same isolation as the dev server)
//   FTA_GUI_SECTIONS="a b"       same as naming sections on the command line
//   FTA_GUI_LABEL=<name>         file-name label (default: dev / exe / url)
//   FTA_GUI_OUT=<dir>            screenshots, logs, results (default: out/<label>/)
//   FTA_GUI_TIMEOUT=<seconds>    per-section limit (default 1200)
//   FTA_GUI_KEEP=1               keep the temporary sandbox root and home afterwards
//
// The dev server is `uv run --frozen --extra all --extra test python fta_web/run.py
// --port <free> --no-browser --root <temp>/root`, with HOME and USERPROFILE pointed
// at an empty <temp>/home so no AI credentials (~/.fta_editor) are picked up.
// Exit code: 0 when every check passed, 1 otherwise. A server this script
// started is always stopped, also on Ctrl-C.
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..', '..');

// Run order. core builds a tree through the GUI and saves it as
// b2b_core_<label>.json in the sandbox root; the sections in NEEDS_CORE open it.
const SECTIONS = ['core', 'fit', 'treeclick', 'fixes', 'tabs', 'files', 'diagram', 'more',
  'stale', 'race', 'view', 'big', 'i18n', 'misc'];
const NEEDS_CORE = new Set(['tabs', 'files', 'diagram', 'more', 'stale', 'race', 'view', 'i18n', 'misc']);

const env = process.env;
const SECTION_TIMEOUT_MS = Number(env.FTA_GUI_TIMEOUT || 1200) * 1000;
const SERVER_START_TIMEOUT_MS = 300 * 1000; // a first `uv run` may have to build the venv

function die(msg) {
  console.error('run.mjs: ' + msg);
  process.exit(2);
}

// ---- arguments ----------------------------------------------------------------------
const argv = process.argv.slice(2);
if (argv.includes('--help') || argv.includes('-h')) {
  const text = fs.readFileSync(fileURLToPath(import.meta.url), 'utf8').split('\nimport ')[0];
  console.log(text.split('\n').filter((l) => l.startsWith('//')).map((l) => l.slice(3)).join('\n'));
  process.exit(0);
}
if (argv.includes('--list')) {
  for (const s of SECTIONS) console.log(s + (NEEDS_CORE.has(s) ? '   (opens the file core saves)' : ''));
  process.exit(0);
}
const asked = argv.filter((a) => !a.startsWith('-')).concat((env.FTA_GUI_SECTIONS || '').split(/[\s,]+/).filter(Boolean))
  .map((s) => s.replace(/^s_/, '').replace(/\.js$/, ''));
for (const s of asked) if (!SECTIONS.includes(s)) die(`unknown section "${s}" (known: ${SECTIONS.join(', ')})`);
const fullRun = asked.length === 0;

try {
  createRequire(path.join(HERE, 'lib.js')).resolve('playwright');
} catch (_e) {
  die('playwright is not installed here. Run: npm ci && npx playwright install chromium   (in ' + HERE + ')');
}

// ---- helpers ------------------------------------------------------------------------
function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitServing(origin, timeoutMs) {
  const t0 = Date.now();
  for (;;) {
    try {
      const r = await fetch(origin + '/', { signal: AbortSignal.timeout(2000) });
      await r.arrayBuffer();
      return;
    } catch (_e) { /* not up yet */ }
    if (Date.now() - t0 > timeoutMs) throw new Error('server at ' + origin + ' did not answer');
    await sleep(250);
  }
}

/** Kill a process and everything it started (uv -> python, node -> browser). */
function killTree(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
  } else {
    try { process.kill(-child.pid, 'SIGTERM'); } catch (_e) { try { child.kill('SIGTERM'); } catch (_e2) { /* gone */ } }
  }
}

async function stopTree(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  const exited = new Promise((r) => child.once('exit', r));
  killTree(child);
  const done = await Promise.race([exited.then(() => true), sleep(8000).then(() => false)]);
  if (!done && process.platform !== 'win32') {
    try { process.kill(-child.pid, 'SIGKILL'); } catch (_e) { /* gone */ }
    await Promise.race([exited, sleep(3000)]);
  }
}

function spawnGroup(cmd, args, opts) {
  // A process group of its own on POSIX, so the whole tree can be signalled.
  return spawn(cmd, args, Object.assign({ detached: process.platform !== 'win32', windowsHide: true }, opts));
}

/** Start the dev server (or FTA_GUI_EXE) with an isolated home; resolve its token URL. */
async function startServer(tmp, logFile) {
  const root = path.join(tmp, 'root');
  const home = path.join(tmp, 'home');
  fs.mkdirSync(root, { recursive: true });
  fs.mkdirSync(home, { recursive: true });
  const port = await freePort();
  const serverArgs = ['--port', String(port), '--no-browser', '--root', root];
  let cmd;
  let args;
  if (env.FTA_GUI_EXE) {
    cmd = path.resolve(env.FTA_GUI_EXE);
    if (!fs.existsSync(cmd)) die('FTA_GUI_EXE does not exist: ' + cmd);
    args = serverArgs;
  } else {
    cmd = 'uv';
    args = ['run', '--frozen', '--extra', 'all', '--extra', 'test', 'python', 'fta_web/run.py', ...serverArgs];
  }
  const serverEnv = Object.assign({}, env, { HOME: home, USERPROFILE: home, PYTHONUTF8: '1' });
  console.log(`starting ${path.basename(cmd)} ${args.join(' ')}`);
  const log = fs.createWriteStream(logFile);
  const child = spawnGroup(cmd, args, { cwd: REPO, env: serverEnv, stdio: ['ignore', 'pipe', 'pipe'] });
  let text = '';
  const url = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('no URL from the server within ' + SERVER_START_TIMEOUT_MS / 1000 + ' s')), SERVER_START_TIMEOUT_MS);
    const onData = (buf) => {
      log.write(buf);
      text += buf.toString('utf8');
      const m = /URL\s*:\s*(http:\/\/127\.0\.0\.1:\d+\/\?t=[A-Za-z0-9_-]+)/.exec(text);
      if (m) { clearTimeout(timer); resolve(m[1]); }
    };
    child.stdout.on('data', onData);
    child.stderr.on('data', (buf) => log.write(buf));
    child.on('error', (e) => { clearTimeout(timer); reject(e); });
    child.on('exit', (code) => { clearTimeout(timer); reject(new Error('server exited with ' + code + ' before printing its URL')); });
  }).catch((e) => {
    killTree(child);
    throw new Error(e.message + '\n--- server output ---\n' + text.slice(-3000));
  });
  // keep draining the pipes into the log for the whole run
  child.removeAllListeners('exit');
  child.stdout.removeAllListeners('data');
  child.stdout.on('data', (buf) => log.write(buf));
  await waitServing(new URL(url).origin, 30000);
  return { child, url, root, home, log };
}

/** The sandbox root of an already-running server (GET /api/fs/home). */
async function askRoot(url) {
  const u = new URL(url);
  const r = await fetch(u.origin + '/api/fs/home', { headers: { 'X-FTA-Token': u.searchParams.get('t') || '', Accept: 'application/json' } });
  const j = await r.json().catch(() => null);
  if (!r.ok || !j || !j.root) throw new Error('could not ask ' + u.origin + ' for its sandbox root (HTTP ' + r.status + '); set FTA_GUI_ROOT');
  return j.root;
}

function runSection(name, url, label, root, out) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    const logFile = fs.createWriteStream(path.join(out, name + '.log'));
    const child = spawnGroup(process.execPath, [path.join(HERE, 's_' + name + '.js'), url, label, root], {
      cwd: HERE,
      env: Object.assign({}, env, { FTA_GUI_OUT: out }),
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    current = child;
    const counts = { pass: 0, fail: 0, finished: false };
    let pending = '';
    const onText = (buf) => {
      logFile.write(buf);
      pending += buf.toString('utf8');
      const lines = pending.split(/\r?\n/);
      pending = lines.pop();
      for (const line of lines) {
        if (line.startsWith('PASS ')) counts.pass += 1;
        else if (line.startsWith('FAIL ')) counts.fail += 1;
        else if (/^FAILS \d+$/.test(line)) counts.finished = true;
        console.log(line);
      }
    };
    child.stdout.on('data', onText);
    child.stderr.on('data', onText);
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; killTree(child); }, SECTION_TIMEOUT_MS);
    child.on('close', (code) => {
      current = null;
      clearTimeout(timer);
      if (pending) onText('\n');
      logFile.end();
      if (timedOut) {
        counts.fail += 1;
        console.log(`FAIL ${name}: timed out after ${SECTION_TIMEOUT_MS / 1000} s`);
      } else if (!counts.finished || (code !== 0 && counts.fail === 0)) {
        counts.fail += 1;
        console.log(`FAIL ${name}: exited with ${code} without finishing`);
      }
      resolve(Object.assign(counts, { name, code, secs: (Date.now() - t0) / 1000 }));
    });
  });
}

// ---- main ---------------------------------------------------------------------------
let server = null;
let tmp = null;
let current = null; // the section process running now

async function cleanup() {
  if (current) await stopTree(current);
  if (server) {
    await stopTree(server.child);
    server.log.end();
    server = null;
  }
  if (tmp && env.FTA_GUI_KEEP !== '1') {
    try { fs.rmSync(tmp, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 }); } catch (e) {
      console.log('note: could not remove ' + tmp + ': ' + e.message);
    }
  } else if (tmp) {
    console.log('kept ' + tmp);
  }
  tmp = null;
}

for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) {
  process.on(sig, () => { cleanup().finally(() => process.exit(130)); });
}
process.on('exit', () => {
  if (current) killTree(current);
  if (server) killTree(server.child);
});

async function main() {
  const mode = env.FTA_GUI_URL ? 'url' : env.FTA_GUI_EXE ? 'exe' : 'dev';
  const label = env.FTA_GUI_LABEL || mode;
  if (!/^[A-Za-z0-9_-]+$/.test(label)) die('FTA_GUI_LABEL may only hold letters, digits, _ and -');
  const out = path.resolve(env.FTA_GUI_OUT || path.join(HERE, 'out', label));
  if (fullRun && !env.FTA_GUI_OUT) fs.rmSync(out, { recursive: true, force: true });
  fs.mkdirSync(out, { recursive: true });

  let url;
  let root;
  if (mode === 'url') {
    url = env.FTA_GUI_URL;
    if (!/[?&]t=/.test(url)) die('FTA_GUI_URL must be the full bootstrap URL with ?t=<token>');
    root = path.resolve(env.FTA_GUI_ROOT || await askRoot(url));
    if (!fs.existsSync(root)) die('sandbox root ' + root + ' is not a directory on this machine (set FTA_GUI_ROOT)');
    if (path.resolve(root) === path.resolve(os.homedir())) {
      die('the server\'s sandbox root is your home directory; the suite writes files there. '
        + 'Start the server with --root <an empty scratch folder>.');
    }
  } else {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'fta-gui-'));
    server = await startServer(tmp, path.join(out, 'server.log'));
    url = server.url;
    root = server.root;
  }
  const sample = path.join(root, 'sampleFTA.json');
  if (!fs.existsSync(sample)) fs.copyFileSync(path.join(REPO, 'fta_web', 'examples', 'sampleFTA.json'), sample);

  let run = fullRun ? SECTIONS.slice() : SECTIONS.filter((s) => asked.includes(s));
  const coreFile = path.join(root, 'b2b_core_' + label + '.json');
  if (!run.includes('core') && run.some((s) => NEEDS_CORE.has(s)) && !fs.existsSync(coreFile)) {
    console.log('adding core: ' + run.filter((s) => NEEDS_CORE.has(s)).join(', ') + ' open(s) the file it saves');
    run = ['core'].concat(run);
  }

  const browser = env.FTA_GUI_CHANNEL || 'chromium (bundled)';
  console.log(`GUI suite: ${run.length} section(s) against ${new URL(url).origin} (${mode}), browser ${browser}${env.FTA_GUI_HEADFUL === '1' ? ', headful' : ''}`);
  console.log(`sandbox root ${root}\noutput       ${out}`);

  const rows = [];
  let coreMissing = false;
  for (const name of run) {
    if (coreMissing && NEEDS_CORE.has(name)) {
      rows.push({ name, pass: 0, fail: 1, code: null, secs: 0, skipped: true });
      continue;
    }
    rows.push(await runSection(name, url, label, root, out));
    if (name === 'core' && !fs.existsSync(coreFile)) {
      coreMissing = true;
      console.log('FAIL core did not save ' + path.basename(coreFile) + '; the sections that open it are not run');
    }
  }

  const lines = [];
  lines.push('');
  lines.push(`GUI suite summary (${mode}, ${browser}, label ${label})`);
  for (const r of rows) {
    lines.push(`${r.name.padEnd(10)} PASS ${String(r.pass).padStart(4)}  FAIL ${String(r.fail).padStart(3)}  ${r.skipped ? 'not run' : r.secs.toFixed(0).padStart(4) + ' s'}`);
  }
  const pass = rows.reduce((a, r) => a + r.pass, 0);
  const fail = rows.reduce((a, r) => a + r.fail, 0);
  lines.push(`${'TOTAL'.padEnd(10)} PASS ${String(pass).padStart(4)}  FAIL ${String(fail).padStart(3)}`);
  lines.push(fail ? 'FAILED' : 'ALL CHECKS PASSED');
  console.log(lines.join('\n'));
  fs.writeFileSync(path.join(out, 'summary.txt'), lines.join('\n').trimStart() + '\n');
  return fail ? 1 : 0;
}

let code = 1;
try {
  code = await main();
} catch (e) {
  console.error('run.mjs: ' + ((e && e.stack) || e));
  code = 1;
} finally {
  await cleanup();
}
process.exit(code);
