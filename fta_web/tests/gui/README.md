# Real-browser GUI suite

A back-to-back check of the web GUI. Playwright drives a real browser with
real mouse and keyboard input, reads what the GUI shows (headline, Node
Details, every diagram label, every analysis tab, the downloaded reports) and
compares it with what the API computes for the same document. It has 1073
checks in 17 sections and takes about 7 minutes.

It complements the numeric back-to-back suite in [`../b2b/`](../b2b/README.md),
which compares the engine, API, CLI and exe paths without a browser.

## What it checks

| Section | Checks | What |
|---|---:|---|
| `core` | 258 | Builds a tree entirely through the GUI: New, title and date, the Add dialog (button and Ctrl+A), Details edits committed with Enter / Tab / blur and reverted with Escape, gate select, undo / redo by keys and buttons, sig figs 1 to 6, switching to Advanced mid-edit, k-of-n, a link through the links editor, Save As / Ctrl+S / New / Open through the file dialog. After every step the headline, Details and every diagram label are compared with the API. It saves `b2b_core_<label>.json`, which most later sections open. |
| `fit` | 7 | Diagram auto-fit never enlarges past 100 %; zoom buttons, Ctrl+0, a 26-node tree still shrinks. |
| `treeclick` | 33 | The first real click on the bottom tree rows selects them, at three window sizes; the keyboard hint shows only for keyboard focus and never shifts rows. |
| `fixes` | 22 | The 1.7.1 frontend fixes: Alt+N and consequence-named confirmations, numeric fields that select on click, Escape in the Aa popover, formatted Validation messages, the FMEA λ unit warning, the live language switch of the AI panel and action bar. |
| `ux1` | 63 | The editing flow: the top event selected at start-up; the Add dialog (probability required, Enter moving from Name to it, `5%` / full-width digits / `1/1000` / `0,25`, **OK and add another** with Ctrl+Enter, four siblings from four Adds); the top bar keeping its height on the first edit and the tab title; the first-child warning after Add and after a keyboard move, with **Show in Validation**; first / last sibling messages; double-click to rename and to collapse; Ctrl+Z from the gate dropdown; Edit; Enter in a Details field; the warning for a dropped invalid entry; delete confirmations (count, focus on Cancel); Enter in the search box; the tree's open / closed state per file; a diagram click scrolling the tree; jumps, the + and − buttons and the plain wheel; the bold number row; *Folder not found* in the Open dialog. |
| `ux2` | 72 | Protecting work: the first-run hint and its two buttons; the AI panel folded and remembered by the server across a reload; **Open an example** (the list, an untitled copy, Save going to Save As, the bundled files byte-identical afterwards); the Load dialog's two other sources and its wording for a path outside the root; the unsaved-changes prompt (three buttons, focus on **Save and continue**, a cancelled save stopping the action); the remembered folder; a file from this computer through the picker and by drop on the tree panel, and a drop elsewhere doing nothing; export wording and the **Export:** group; undo / redo toasts and selection; a tab behind another tab (reload on focus, not under an open dialog, a save elsewhere, another document, no false notice for its own edits); the Cut Sets wording when a limit leaves nothing, **This run only** and **Reset**; the Update FTA confirmation, preview card, Discard and Apply (the three routes are answered by the script: no provider is called); the server-stopped banner, the rescue copy and its round trip through the import endpoint; the "not connected" screen and its rescue offer; the Japanese strings. |
| `ux3` | 79 | Analysis, diagram and AI: the gate and probability on tree rows, and red only for a certain event; a multi-selection (the header count, Ctrl+Shift+Down, a drag, Delete, each one undo step); a notice without a raw code, placed beside the AI panel; the **Settings** button and the **Diagram settings** popover; a selected node brought into view in a zoomed diagram, **1:1** and **◎**; the bottom panel's height per tab and its enlarge button; **Copy CSV** on Importance; the exports (the document's name, the toast, the importance colours and legend in the SVG, Render's name, a white PNG from the dark theme); the report's coloured diagram (the request is answered by the script); the rare-event note; uncertainty for all events and the chart only with a spread; ETA mode (headline, greyed tabs, no gate symbols, the assistant's wording); the assistant not set up (the line said once) and the setup dialog (Gemini ticked, the disclosure, the Copilot hint); **Stop**, a failed message given back, an error reply, a suggestion card with names, links and readable changes, the conversation after a reload, a card retired by New (every `/api/ai/*` request is answered by the script: no provider is called); the Japanese strings. |
| `tabs` | 84 | Quantification (rate model through the form, derived q and formula), Cut Sets (rows, summary, highlight, sig figs), Importance (every measure, sort, FV overlay), Uncertainty (fixed seed against an API run with the same seed), Validation (list, chips, badge, after undo), tabs refreshed after an edit made while hidden, Traceability cell edits, ETA mode. |
| `files` | 21 | FMEA CSV import through the file dialog; the DOCX report, Excel and CSV exports, parsed back with `parse_exports.py` and compared with the API; the "Save … again" link; a path entered in the file dialog while its first listing is held back. |
| `diagram` | 85 | compact / symbols × LR / TB show the API's numbers and each other's; with the root selected, its box, Node Details and the caption give the MCUB headline and the root's tree-walk value; a real-mouse click on every shape selects its node; zoom, Ctrl+wheel, pan, fit; dark theme. |
| `more` | 79 | Escape in the title, Hide Zero, λ units, the standby model, document defaults for cut sets and Monte Carlo, the truncation marker on the headline, RRW ∞, New with the FV overlay on. |
| `stale` | 59 | No stale values after undo / redo / delete: the Quantification form, Details, the title, the Validation list and badge. |
| `race` | 4 | An edit made while the first Cut Sets / Importance run is still in flight (responses delayed with `page.route`). |
| `view` | 150 | Every tab in en/light and ja/dark (screenshots), no raw i18n keys, tab-strip and tree keyboard navigation, F2 rename, drag and drop, the AI panel without credentials, four window sizes down to 420 px, and Japanese event names in a 420 px window (the Importance and Quantification tables keep six characters a line). |
| `big` | 16 | A 300-node tree: click to Details under 500 ms, no diagram re-layout on selection, the Add dialog under 3 s, five analysis tabs, the tree search. |
| `i18n` | 3 | After a live switch to Japanese no English UI text is left in any tab, and no Japanese after switching back. |
| `misc` | 38 | Save As without an extension, the splitter by keyboard, the sig-fig select by keyboard, basic mode showing an advanced gate read-only, the OS dark theme, a tab opened without a session token. |

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
| `node run.mjs tabs view` | Only these sections. `core` is added first when a section opens its file (all but `fit`, `treeclick`, `fixes`, `ux1`, `ux2`, `ux3`, `big`). |
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
  against the API, used after each step. Every node's label is compared
  with its `calculatedProbability`; the root's is compared with the
  headline, and its tree-walk value, when the headline is the MCUB
  (`rootShowsHeadline()`).
- `s_<section>.js` – one script per section, each runnable on its own.
- `parse_exports.py` – dumps the DOCX / XLSX numbers as JSON for `files`.
- `compare_snaps.js` – compares the `core` snapshots of two runs.

To add a section, write `s_<name>.js` ending in
`L.runSection('<name>', main)` and list it in `SECTIONS` in `run.mjs` (and in
`NEEDS_CORE` if it opens the file `core` saves).

One trap worth knowing: `page.waitForFunction` with an `async` predicate does
not wait, because the returned Promise is already truthy. Poll from Node
instead (see `app.addViaDialog` and `app.waitSelectionChange` in `lib.js`).

`addViaDialog` returns the id of the node it made, found as the id the
page's store did not have before. The selection stays on the parent after an
Add, so a flow that wants the next node beneath the new one selects it first.
Several checks run only when a node is selected (Details against the API,
the diagram's selection); since the top event is selected at start-up they
run in more places, which is where the higher counts of `diagram`, `more`
and `misc` come from.

In CI, [`.github/workflows/extended.yml`](../../../.github/workflows/extended.yml)
runs `node run.mjs` with the bundled Chromium on ubuntu-latest weekly, on
demand, and on pull requests that change this folder, and uploads `out/` as
the `gui-out` artifact.
