# Real-browser GUI suite

A back-to-back check of the web GUI. Playwright drives a real browser with
real mouse and keyboard input, reads what the GUI shows (headline, Node
Details, every diagram label, every analysis tab, the downloaded reports) and
compares it with what the API computes for the same document. It has 716
checks in 14 sections and takes about 5 minutes.

It complements the numeric back-to-back suite in [`../b2b/`](../b2b/README.md),
which compares the engine, API, CLI and exe paths without a browser.

## What it checks

| Section | Checks | What |
|---|---:|---|
| `core` | 214 | Builds a tree entirely through the GUI: New, title and date, the Add dialog (button and Ctrl+A), Details edits committed with Enter / Tab / blur and reverted with Escape, gate select, undo / redo by keys and buttons, sig figs 1 to 6, switching to Advanced mid-edit, k-of-n, a link through the links editor, Save As / Ctrl+S / New / Open through the file dialog. After every step the headline, Details and every diagram label are compared with the API. It saves `b2b_core_<label>.json`, which most later sections open. |
| `fit` | 7 | Diagram auto-fit never enlarges past 100 %; zoom buttons, Ctrl+0, a 26-node tree still shrinks. |
| `treeclick` | 33 | The first real click on the bottom tree rows selects them, at three window sizes; the keyboard hint shows only for keyboard focus and never shifts rows. |
| `fixes` | 22 | The 1.7.1 frontend fixes: Alt+N and consequence-named confirmations, numeric fields that select on click, Escape in the Aa popover, formatted Validation messages, the FMEA λ unit warning, the live language switch of the AI panel and action bar. |
| `tabs` | 76 | Quantification (rate model through the form, derived q and formula), Cut Sets (rows, summary, highlight, sig figs), Importance (every measure, sort, FV overlay), Uncertainty (fixed seed against an API run with the same seed), Validation (list, chips, badge, after undo), tabs refreshed after an edit made while hidden, Traceability cell edits, ETA mode. |
| `files` | 19 | FMEA CSV import through the file dialog; the DOCX report, Excel and CSV exports, parsed back with `parse_exports.py` and compared with the API; the "Save … again" link. |
| `diagram` | 57 | compact / symbols × LR / TB show the API's numbers and each other's; a real-mouse click on every shape selects its node; zoom, Ctrl+wheel, pan, fit; dark theme. |
| `more` | 61 | Escape in the title, Hide Zero, λ units, the standby model, document defaults for cut sets and Monte Carlo, the truncation marker on the headline, RRW ∞, New with the FV overlay on. |
| `stale` | 51 | No stale values after undo / redo / delete: the Quantification form, Details, the title, the Validation list and badge. |
| `race` | 4 | An edit made while the first Cut Sets / Importance run is still in flight (responses delayed with `page.route`). |
| `view` | 131 | Every tab in en/light and ja/dark (screenshots), no raw i18n keys, tab-strip and tree keyboard navigation, F2 rename, drag and drop, the AI panel without credentials, four window sizes down to 420 px. |
| `big` | 14 | A 300-node tree: click to Details under 500 ms, no diagram re-layout on selection, the Add dialog under 3 s, five analysis tabs, the tree search. |
| `i18n` | 3 | After a live switch to Japanese no English UI text is left in any tab, and no Japanese after switching back. |
| `misc` | 24 | Save As without an extension, the splitter by keyboard, the sig-fig select by keyboard, basic mode showing an advanced gate read-only, the OS dark theme, a tab opened without a session token. |

Every section also fails on any console error or warning, page error, or
unexpected HTTP 4xx/5xx from `/api` in the page. The harness's own API calls
go from Node, not the page, so a deliberate 4xx never counts.

## Running it

Needs Node 20 or newer, [uv](https://docs.astral.sh/uv/) with the project
environment (`uv sync --extra all --extra test`), and a Playwright browser.

```bash
cd fta_web/tests/gui
npm ci
npx playwright install chromium      # once: the bundled Chromium
node run.mjs                         # every section, ~5 minutes
```

`run.mjs` starts its own dev server,
`uv run --frozen --extra all --extra test python fta_web/run.py --port <free> --no-browser --root <temp>/root`,
with `HOME` and `USERPROFILE` pointed at an empty temporary folder so no AI
credentials are picked up. It runs the sections in order (`core` first),
prints a summary, exits 1 on any failure, and always stops the server it
started and removes the temporary folder.

Everything a run writes goes to `out/<label>/` (git-ignored): one log per
section, `results_<section>_<label>.json`, screenshots, the downloaded
DOCX / XLSX / CSV, `server.log` and `summary.txt`.

| Option | Meaning |
|---|---|
| `node run.mjs tabs view` | Only these sections. `core` is added first when a section opens its file (all but `fit`, `treeclick`, `fixes`, `big`). |
| `node run.mjs --list` | The sections in run order. |
| `FTA_GUI_CHANNEL=chrome` | Use the installed Google Chrome instead of the bundled Chromium (`msedge` works too). Playwright launches it with a fresh temporary profile, never your own. |
| `FTA_GUI_HEADFUL=1` | Show the browser window. |
| `FTA_GUI_EXE=<path>` | Start this packaged `fta_editor` executable instead of the dev server, with the same isolation (label `exe`). |
| `FTA_GUI_URL=<token URL>` | Use an already-running server (label `url`); see below. |
| `FTA_GUI_ROOT=<dir>` | That server's sandbox root, if it cannot be asked for. |
| `FTA_GUI_LABEL`, `FTA_GUI_OUT` | Override the label (file names) and the output folder. |
| `FTA_GUI_TIMEOUT=<s>` | Per-section limit, default 1200. |
| `FTA_GUI_KEEP=1` | Keep the temporary sandbox root and home. |

A single section can also be run by hand against any server:
`node s_tabs.js <url-with-token> <label> <sandbox-root>`.

### Against the packaged exe

The simplest way is to let the runner start it:

```bash
FTA_GUI_EXE=/path/to/dist/fta_editor/fta_editor.exe node run.mjs
```

To test an exe that is already running, start it yourself with a scratch
sandbox root and an empty home, then pass its URL (with the token):

```powershell
# a separate PowerShell window; the empty USERPROFILE keeps AI credentials out
$env:USERPROFILE = "$env:TEMP\fta-gui-home"
New-Item -ItemType Directory -Force $env:USERPROFILE, "$env:TEMP\fta-gui-root" | Out-Null
& "C:\path\to\fta_editor.exe" --port 8871 --no-browser --root "$env:TEMP\fta-gui-root"
```

```bash
FTA_GUI_URL='http://127.0.0.1:8871/?t=<token>' node run.mjs
```

The server must be on this machine (sections write input files into its
sandbox root, which the runner asks for with `GET /api/fs/home`), must not see
AI credentials (`view` checks `aiConfigured` is false), and nobody else may use
it during the run: every section drives the server's single document. The
runner refuses a sandbox root that is your home directory.

`files` reads the downloaded DOCX and XLSX with `parse_exports.py` through
`uv run`, so the project environment is needed in every mode.

To compare what two builds showed, run the suite against each and compare
the snapshots `core` records (headline, Details and diagram labels after
every step):

```bash
node compare_snaps.js out/dev/core_dev.json out/exe/core_exe.json
```

## Known blind spots

- **Browser-reserved shortcuts.** Keys are injected through the Chrome
  DevTools Protocol, below the browser's own UI, so the page receives
  shortcuts a real browser keeps for itself (Ctrl+N new window, Ctrl+T,
  Ctrl+W, Ctrl+Shift+N, …). That is how "New analysis" on Ctrl+N shipped
  unusable in Chrome and Edge until 1.7.1 (it is Alt+N now). The suite checks
  that the New button documents Alt+N; it cannot prove a shortcut reaches the
  page. Check new shortcuts by hand in a real window.
- **Native UI.** OS file dialogs, the browser's Save dialog, the OS clipboard,
  printing and window chrome are not exercised; downloads are captured by
  Playwright.
- **Rendering.** Fonts differ between machines and headless mode. Layout
  checks (no horizontal scroll, clicks on bottom tree rows at several window
  sizes) are geometric, and screenshots are for people to look at, not
  pixel-compared.
- **Timing.** The budgets in `big` (Details under 500 ms, Add under 3 s on
  300 nodes) depend on the machine.
- **AI assistant.** Only the no-credentials path; no provider is called.
- **macOS.** Not tried: the suite presses Ctrl-based shortcuts, which is what
  the app binds on Windows and Linux.
- **A transient module load failure** ("The … tab could not be loaded: Failed
  to fetch dynamically imported module") was seen once in `view` with Google
  Chrome on Windows against the Werkzeug dev server; the server logged no
  failed request and a re-run passed. Re-run the section before hunting a bug.

## How it is built

- `run.mjs` – the runner described above.
- `lib.js` – browser launch, the app handle (API client, GUI readers, real
  input helpers), `check()` / `runSection()`, and `fmt()`, a mirror of
  `static/js/numfmt.js` that must change when it does.
- `b2b.js` – `compareCore()`: headline, Details and every diagram label
  against the API, used after each step.
- `s_<section>.js` – one script per section, each runnable on its own.
- `parse_exports.py` – dumps the DOCX / XLSX numbers as JSON for `files`.
- `compare_snaps.js` – compares the `core` snapshots of two runs.

To add a section, write `s_<name>.js` ending in
`L.runSection('<name>', main)` and list it in `SECTIONS` in `run.mjs` (and in
`NEEDS_CORE` if it opens the file `core` saves).

One trap worth knowing: `page.waitForFunction` with an `async` predicate does
not wait, because the returned Promise is already truthy. Poll from Node
instead (see `app.waitSelectionChange` in `lib.js`); before that fix,
`addViaDialog` returned the previous selection whenever the server was slow.

In CI, [`.github/workflows/extended.yml`](../../../.github/workflows/extended.yml)
runs `node run.mjs` with the bundled Chromium on ubuntu-latest weekly, on
demand, and on pull requests that change this folder, and uploads `out/` as
the `gui-out` artifact.
