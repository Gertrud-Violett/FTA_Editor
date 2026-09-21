# Code review — critical bugs (2026-09-19, status updated 2026-09-20)

**Scope:** the whole repository as of `main` at `fd44067` (PR #8 merged), reviewed in
three independent passes — web backend (`fta_web/*.py`, `fta_web/routes/`,
`fta_web/core/`), web frontend (`fta_web/static/js/`, templates, CSS) and the legacy
desktop app (`desktop/src/`, `desktop/tests/`) — plus a repository/infrastructure pass
done while moving the desktop app into `desktop/`.

**Method:** whole-file reading with concrete inputs traced through the code. Items
marked **VERIFIED** were reproduced with a throwaway script against the checked-out code
(Python 3.14 venv, Flask, openpyxl, Pillow, Tk 8.6 and a native Graphviz on PATH) or by
driving the vendored `viz.js` from Node. Items marked PLAUSIBLE were not reproduced and
say what would confirm them.

**Companion:** [`ROADMAP_MECHANICAL_ENGINEERS.md`](ROADMAP_MECHANICAL_ENGINEERS.md)
references findings here by their IDs (B-n backend, F-n frontend, D-n desktop, R-n repo).

## Status (updated 2026-09-20)

Every web-app finding below — all B-*, F-*, R-* items and F-11 — is **fixed and merged
to `main`** via PR #11 (merge commit `6f93d61`, which also folds in the 1.6.2 release).
Released as **1.6.3**. See the `[1.6.3] → Fixed` entry in `CHANGELOG.md` and divergences D13–D20 in
`fta_web/core/DIVERGENCE.md`. The D-* items (legacy desktop app) are deliberately **not**
fixed: `desktop/src/` is hash-pinned and frozen, and `desktop/README.md` lists them for
anyone using the fallback.

**Latest test run — `main` at `6f93d61`:**

| Where | Result |
|---|---|
| Local, Windows 11 (Japanese locale), Python 3.14, `uv run --frozen … pytest` | **622 passed, 6 skipped, 0 failed** (12 s) |
| — of which `fta_web/tests/` | 587 passed, 6 skipped |
| — of which `desktop/tests/` (frozen suite, unchanged) | 35 passed |
| GitHub Actions `tests` workflow (ubuntu 3.10, ubuntu 3.13, windows 3.13) | **success** on `6f93d61` |

The 6 skips are the R-3 tests: five symlink tests (Windows needs
`SeCreateSymbolicLinkPrivilege` / Developer Mode) and one POSIX mode-bit test; they
run on the Linux CI jobs. The 4 warnings are `PytestReturnNotNoneWarning` from two
frozen desktop tests that `return True` instead of asserting — harmless and not fixable
without editing the pinned tree. Nothing failed, and no test was disabled to get there.

**Test status before the fixes (same machine):** 551 passed, 6 failed; all six
failures were environmental (R-3 below). Net change: +71 tests
(`test_core_fixes.py` 33, `test_backend_fixes.py` 23, MIME/appearance/render tests
from 1.6.2 and the review fixes).

**Still open after this round** (minor, listed in "Also noticed" below): the action
bar is clickable for ~1 s before the panel modules finish loading. Everything else
in the tables is closed or explicitly deferred to the desktop known-defect list.

---

## Summary table

| ID | Sev | Where | One line |
|---|---|---|---|
| B-1 / F-3 / D-H2 | CRITICAL | `fta_web/core/json_viewer.py` node_label, `desktop/src/json_viewer.py` | Node name containing `<`, `>` or `&` (e.g. `Pressure > 5 bar & T < 50`) breaks the DOT; **the whole diagram disappears**, native render 503s |
| B-2 / D-C1 | CRITICAL | `FTA_Editor_core.py:183,186,206,211,234` (both copies) | `round(…, 6)` at every gate: any probability below 5e-7 becomes exactly 0, is flagged "zero", hidden by Hide-Zero, and propagates 0 through AND gates |
| F-2 | CRITICAL | `diagram.js` + same root cause as B-1 | HTML-label injection through a node name yields a clickable `javascript:` link inside the app origin (session token in `sessionStorage`) |
| F-1 | CRITICAL | `chat.js:420-444,485` vs `routes/ai.py:452-482` | "Apply selected" sends card positions, server expects indices into an accumulating pending list → **applies a proposal the user never saw** |
| D-C2 | CRITICAL | `desktop/src/FTA_Editor_UI.py:988,1648` | Loaded file whose root id ≠ `"root"`: every node added afterwards is silently dropped from the data and not saved |
| D-C3 | CRITICAL | `desktop/src/FTA_Editor_UI.py:990-1002,1474` | Ctrl+D is `bind_all`: pressing it while typing in the chat/notes box deletes the selected subtree, no confirm, no undo |
| D-C4 | CRITICAL | `desktop/src/FTA_Editor_UI.py` | Closing the main window never prompts for unsaved changes |
| D-C5 | CRITICAL | `desktop/src/FTA_Editor_UI.py:1603-1609` | Duplicate ids in a file crash `load_json` half-way (`TclError`), leaving a partial UI over replaced data |
| D-C6 | CRITICAL | `desktop/src/FTA_Editor_UI.py:396,428,447,479` | AI settings dialog does blocking network calls on the Tk main thread, with no SDK timeouts; opening ⚙ with saved credentials fires a request before the dialog paints |
| B-3 | HIGH | `tree_ops.next_child_id`, `routes/tree.py:574-600` | Delete then Add reuses the id → a dangling link silently re-targets the new, unrelated node; saved file encodes the wrong relationship |
| B-4 | HIGH | `FTA_Editor_core.py:159-162,106-109`, `tree_ops.move_node` | Duplicate ids in a loaded file: wrong maths (memo returns the first), missing `calculatedProbability`, delete/move remove **both** |
| B-5 | HIGH | `FTA_Editor_core.py:163-167` | A link cycle through a gate node falls back to the gate's meaningless base 1.0 → everything saturates to 1.0; cycles are documented as legal |
| B-6 | HIGH | `routes/ai.py:614` | `/api/ai/update` installs un-normalised AI JSON; a string `"probability": "0.5"` then 500s every `/api/dot` and `/api/render` until undo |
| F-4 | HIGH | `main.js:1362-1368` flushPendingEdits, `details.js:358`, `tree.js:1551` | Ctrl+S / Save As / exports race the un-awaited details-panel PATCH; file on disk can lack the last edit while "Saved" is shown |
| F-5 | HIGH | `app.css:729`, `tree.js:772,955,640,1494` | Hide Zero hides only the row: children float headerless, hidden rows stay keyboard-reachable and multi-deletable; `is-full` beats `is-zero` |
| F-6 | HIGH | `details.js`, `dialogs.js` | Node Details panel, Add Node dialog and links editor are hard-coded English; JA leaves the editing surface untranslated. Delete confirm passes `okLabel` but the dialog reads `confirmLabel` → button says "OK" |
| D-H1 | HIGH | `FTA_Editor_core.py:70-74` (both copies) | `set_metadata(title=…)` / `(mode=…)` without `date` silently overwrites the date with today; desktop UI never refreshes `date_var` (web app works around it by always sending all three) |
| D-H3 | HIGH | `json_viewer.py:16-17` (both) | `sanitize_id` maps every non-ASCII/non-word char to `_`: ids `節点1`/`節点2` or `a-b`/`a_b` merge into one diagram node |
| D-H4 | HIGH | `desktop/src/FTA_Editor_UI.py:897` | "Update FTA" replaces the tree with shape-checked-only AI output; deletions not detected, no undo |
| D-H5 | HIGH | `desktop/src/FTA_Editor_UI.py:1157,1749,1761`, `json_viewer.py:230-240` | `dot` subprocesses without timeout; the one timeout kills only the Python child, orphaning `dot.exe` on Windows |
| R-1 | HIGH (fixed here) | `fta_web/core/BASELINE.json`, `DIVERGENCE.md` | PR #8 patched `fta_web/core/json_viewer.py` without recording a divergence or re-pinning → `test_vendor_integrity` failed on `main` |
| R-2 | MEDIUM (fixed here) | `fta_web/tests/test_vendor_integrity.py` | Hashes taken from LF bytes; a Windows checkout with `core.autocrlf=true` failed **every** pin, including untouched files |
| R-3 | MEDIUM | `fta_web/tests/test_api_files.py` (6 tests) | Symlink tests need `SeCreateSymbolicLinkPrivilege` (`WinError 1314`) and one asserts POSIX mode bits; they fail on every normal Windows account |
| R-4 | MEDIUM | `desktop/tests/run_all_tests.py`, `test_core_module.py` | Print `✓`/`❌`; on a cp932 console the runner crashes with `UnicodeEncodeError` *after* the tests pass, reporting failure |
| B-7 | MEDIUM | `routes/{tree,files,render,ai}.py` errorhandlers | Blueprint-level `ApiError` handlers bypass `app.py`'s i18n handler; `?lang=ja` errors come back in English |
| B-8 | MEDIUM | `FTA_Editor_core._normalize_node:362`, `routes/tree.py:583,617` | Root without an `id` becomes `root_0`; `ROOT_ID` guards compare against the literal `"root"`, so root can be "deleted" (no-op + undo entry) and every AI update is rejected |
| B-9 | MEDIUM | `routes/ai.py:519-535` | `changes/apply` pushes an undo entry before applying; an all-rejected batch still adds a no-op history step and clears redo |
| B-10 / D-M5 | MEDIUM | `AI_agent_handler.py:56` (both) | `~/.fta_editor/ai_credentials.json` written with default umask / ACLs, plain text |
| B-11 | MEDIUM | `state.py:300` | First `/api/state` imports all three AI SDKs while holding `state.lock` |
| F-7 | MEDIUM | `main.js:2240-2245` | `beforeunload` checks only `store.state.dirty`; typed-but-not-blurred field text is lost silently |
| F-8 | MEDIUM | `details.js:292-296`, `dialogs.js:393-437` | Details-panel errors use a second toast host with no timeout, not in the status line, not Escape-dismissable |
| F-9 | MEDIUM (PLAUSIBLE) | `details.js:284-290`, `tree.js:1041` | Two quick blurs → two PATCHes; reversed responses install the older full tree (display only; serialising commits also fixes F-4) |
| F-10 | MEDIUM | `details.js:376`, `dialogs.js:824`, `main.js:2169` | Escape in a field also dismisses the top toast; focus falls to `body` after Delete/Add because the trigger `<li>` was re-rendered; bare `Delete` fires from the diagram stage |
| D-M1…M7 | MEDIUM | `desktop/src/*` | Dirty flag on tab-through; CLI crashes on string probabilities / `null`; dangling links exported raw; non-atomic save; endpoint ignored by Anthropic/Gemini providers; unbounded chat history; `root.after()` from worker threads (PLAUSIBLE); `add_node` id clash raises `TclError` |

---

## Findings in detail

### Cross-cutting: the probability engine (`FTA_Editor_core.py`, both copies)

**B-2 / D-C1 — Rounding to 6 decimals at every level. VERIFIED.**
`_recalculate_fta_probabilities` rounds after the gate, after AND-links, after OR-links,
and ETA rounds after each multiplication. `AND(1e-3, 1e-4)` → 0.0 (expected 1e-7);
`OR(3e-7, 4e-7)` → 1e-6 (expected 7e-7); ETA `1e-3 × 1e-4` → 0.0. The node is then listed
in `zeroNodes`, painted as a zero node, dropped by Hide Zero together with its subtree,
and feeds 0 into any AND gate above it; XML/Excel export the 0. Component failure rates
of 1e-6…1e-9/h are the normal working range in reliability engineering, so this is wrong
maths in the common case, with no warning. `docs/V1.6_WEB_SPEC.md:344` records it as by
design, and `desktop/tests/test_probability_calculation.py:62-91` re-implements the same
rounding, so the suite cannot catch it.
*Fix:* remove rounding from the engine and round only for display (or round to
significant figures, `float(f"{x:.6g}")`). Requires a DIVERGENCE entry and a test update.

**B-5 — Link cycles saturate to 1.0. VERIFIED.** On re-entry via a link the engine
returns the node's *base* `probability`, which for a gate node is the ignored default
1.0. G (OR, one child 0.01) ↔ B (0.02) linked both ways → G = B = root = 1.0.
`routes/tree.py:25-28` documents cyclic links as legal. *Fix:* on re-entry return the
last computed value if present, else the children-only gate result; or reject cycles.

**B-4 — Duplicate ids. VERIFIED.** `load_from_json` never checks uniqueness. Two
children with `id: e1` (0.1 and 0.9): the memo returns the first for the second and
never writes its `calculatedProbability`; root = 0.19 instead of 0.91. `delete_node_from_data`
and `move_node` remove every node with that id. *Fix:* reject or auto-suffix duplicates
on load and report; key the memo by object identity.

**B-8 / D-C2 — Root id.** `_normalize_node` invents `root_0` for a root without an id;
the web `ROOT_ID` guards and the desktop Treeview both hard-code `"root"`. Web: root can
be "deleted" (no-op that still pushes undo and dirties) and every AI update is refused.
Desktop (VERIFIED): after loading a file whose root id is `TOP`/`1`/legacy, Add Node
inserts into the Treeview but `add_node_to_data('root', …)` finds nothing — the node is
never in the data and is not saved. *Fix:* force the top-level id to `"root"` on load,
remapping links, or compare against `get_data()["id"]`.

**D-H1 — `set_metadata` resets the date.** Any call without `date` sets it to today.
The web app deliberately sends all three fields on every change (`main.js`
`commitMetadata`); the desktop UI calls it on every Title focus-out and mode change and
never refreshes the date field, so the screen and the saved file disagree.

**Design notes engineers should know (by design, not bugs):** a node with children
ignores its own `probability`, which is nevertheless printed as `P:` in the diagram;
only AND/OR exist and an unrecognised gate string is silently treated as OR; links are a
*post-gate* stage (`OR(gate(children) × ∏ AND-links, OR-links)`), applied AND-first
regardless of list order — an AND-link on an OR node gives `(OR of children) AND target`;
dangling links are silently skipped; ETA does not normalise branch probabilities and the
root's own probability multiplies every path; undo leaves the document dirty even at the
saved state; `/api/ai/update` replaces the whole tree and validates shape only.

### Cross-cutting: DOT / diagram generation (`json_viewer.py`, both copies)

**B-1 / F-3 / D-H2 — Unescaped node names. VERIFIED (web with native `dot`, and with
`viz.js`; desktop).** `node_label` interpolates `name` (and the gate text) raw into a
Graphviz HTML-like label, which is XML. `Pressure > 5 bar & T < 50` produces a DOT that
both engines reject: web — every node vanishes, panel shows "Could not render", `/api/render`
returns 503 `render_failed`; desktop — the CLI prints "Rendering failed" but exits 0, so
the UI reports the misleading "Image loading failed". AI-added names take the same path.
`rendering.py` escapes the *title* but not names. *Fix:* `html.escape(name, quote=False)`
(and the meta row) in `node_label`; desktop CLI should `sys.exit(1)` on failure. New
DIVERGENCE entry for the web copy.

**F-2 — HTML injection → clickable script. VERIFIED with `viz.js`.** Because of the
above, a node named `x</FONT></TD></TR><TR><TD HREF="javascript:alert(1)"><FONT>y`
renders as `<a xlink:href="javascript:…">` inside the SVG that `diagram.js` `importNode`s
into the page unsanitised; the stage click handler does not `preventDefault`. A hostile
`.json` shared with an engineer runs script in the app origin, where the session token
lives in `sessionStorage` and `/api/fs`, `/api/file/save-as` are reachable. *Fix:* the
escaping above, plus defence in depth in `diagram.js` — strip `script`, `foreignObject`,
`on*` attributes and any `href`/`xlink:href` not starting with `#`/`http(s):`.

**D-H3 — `sanitize_id` collisions.** Every non-`[0-9A-Za-z_]` character becomes `_`, so
non-ASCII or punctuation-differing ids (only possible in hand-edited or externally
generated files) merge into one diagram node and edges cross-wire. *Fix:* quote the id
or append a short hash.

### Web backend (`fta_web/`)

**B-3 — Id reuse re-targets dangling links. VERIFIED.** Delete leaves links pointing at
the deleted id (documented desktop parity); `next_child_id` is max-of-current-children + 1,
so the next Add under the same parent gets the same id and the stale link now points at an
unrelated node. X `AND→root_1` (0.1): delete `root_1` → X = 0.5; add any child → it becomes
`root_1` → X = 0.45 against the wrong node, saved that way. *Fix:* strip links into the
deleted subtree on delete (report `removedLinks`), or never reuse ids (`_unused_id` already
scans the tree — call it unconditionally).

**B-6 — Un-normalised AI update. VERIFIED.** `routes/ai.py:614` `set_data(deepcopy(updated))`
skips `_normalize_node`; `verify_updated_fta_json` accepts anything `float()` accepts, so
`"probability": "0.5"` survives, and `node_label`'s `f"{p:.1E}"` raises → `/api/dot` and
`/api/render` 500 until undo or save+reload. *Fix:* normalise before `set_data`.

**B-7** blueprint `errorhandler(ApiError)` in all four route modules returns
`exc.to_payload()` directly, so `app.py`'s localising handler never runs; `i18n.py`'s
`ja` error strings are dead. **B-9** `changes/apply` pushes undo before validating.
**B-10** credentials file has default permissions (`os.open(…, 0o600)`, `mkdir(0o700)`).
**B-11** SDK probe runs under `state.lock` on first `/api/state` — seconds of blocking
for every concurrent request, once per process.

**Security review (no findings):** token compare is constant-time, Host pinned, Origin
`null` rejected, no CORS; `fsbrowser.resolve_in_root` resolves-then-contains and no Windows
escape (`C:foo`, `/foo`, `..\`, ADS `x.json:evil`) was found; Graphviz is invoked with an
argv list and a whitelisted format/font; download names sanitised; saves atomic; upload
size capped. F-2 is the one injection path, and it is through the diagram, not the API.

### Web frontend (`fta_web/static/js/`)

**F-1 — AI "Apply selected" index mismatch. VERIFIED by reading both sides.** `renderChanges`
uses the card's list position as `index`; the server indexes into `handler.pending_changes`,
which `extend`s across the conversation, and every change carries its real slot in
`change.index` — which `chat.js` never reads. Analyze FTA (3 proposals appended, cards
discarded) then a chat reply with 1 proposal at pending index 3: Apply sends `[0]` and the
server applies Analyze's first proposal. Undoable but silent. *Fix:* use `change.index`
(fall back to position only if absent), and clear or render pending after Analyze.

**F-4 — Save races the details PATCH.** `flushPendingEdits` blurs the field (which fires a
PATCH that is not awaited) and immediately POSTs `/file/save`; both contend for
`state.lock`. If save wins, the file lacks the edit, "Saved to …" is shown, and the dirty
badge flips back on. Same window for inline rename and for exports. *Fix:* expose the
in-flight commit promise (or a cancelable `fta:flush` event collecting promises) and await
it. Serialising commits through one chain also removes **F-9**.

**F-5 — Hide Zero.** CSS hides `.fta-tree-row.is-zero` but not the `<li>`/`<ul>`, so a
zero parent's non-zero children float headerless while the diagram drops the subtree;
hidden rows remain in `itemNodes()` so arrows/Home/End land on invisible rows and
Shift-ranges include them — a multi-delete then removes nodes the user cannot see.
`rowClass` gives `is-full` precedence over `is-zero`, so base 1.0 / calculated 0 is never
hidden.

**F-6 — i18n gaps.** `details.js` and `dialogs.js` (Add Node dialog, links editor,
confirm dialog, all validation messages) are literal English while every other module
routes through `ftaShell.t`; also `main.js` passes `okLabel` where `confirmDialog` reads
`confirmLabel`, so the delete confirmation button reads "OK".

**F-7, F-8, F-10** are usability defects around unsaved field text, a second toast
system that never auto-dismisses, and focus/Escape handling; see the table.

**Verified OK:** request/response shapes for PATCH/move/DELETE/undo/redo/file/render/dot/
credentials; `el()` never uses `innerHTML`; chat text rendered with `textContent`; modal
Escape/Tab trapping with stacked overlays; `busy` flags cleared in `finally`; multi-delete
prunes root and descendants; client `dropIsValid` mirrors the server cycle check; every
`t('…')` key used by tree/chat/aisettings/filedialog/capabilities/diagram exists in `STRINGS`.

### Legacy desktop app (`desktop/src/`) — what a fallback user will hit

Known and deliberately unpatched (see `fta_web/core/DIVERGENCE.md`): D1, **D5 NOT→OR**,
D7 move guard, **D8 minified JSON**, D9, D11. New, in addition to the shared items above:

**D-C3 — `bind_all` shortcuts. VERIFIED.** Ctrl+D/A/E/N are bound application-wide;
Tk's Text class binding for Ctrl+D is "delete character", so Ctrl+D while typing in the
AI chat box or a Notes field deletes the selected node's subtree with no confirmation,
and the app has no undo at all. Ctrl+A in the Name entry opens a second Add dialog.
*Fix:* bind on the tree widget, ignore when focus is an Entry/Text, confirm deletes.

**D-C4 — No `WM_DELETE_WINDOW` on the main window;** unsaved work is discarded on close.

**D-C5 — Duplicate ids crash `load_json`. VERIFIED.** The `_refresh_tree` fallback iid
`f"{parent_id}_{index(parent_id)}"` is constant per parent → `TclError: Item root_0 already
exists` half-way, after the core data was already replaced; it also rewrites `child["id"]`,
orphaning links.

**D-C6 — Blocking network on the Tk thread.** `get_available_models`/`test_connection` run
synchronously; `update_provider_options()` is called unconditionally when the dialog opens
with a stored key. No SDK timeouts are passed (OpenAI's default is 10 min with retries) —
PLAUSIBLE multi-minute freeze behind a proxy.

**D-H4, D-H5, D-M1…M7:** see the table. Of note for anyone shipping the fallback:
non-atomic save (a failure mid-write truncates the previous file — write to temp then
`os.replace`), no `dot` timeouts, and `json_viewer.py` CLI crashing on string or `null`
probabilities.

### Repository / infrastructure

**R-1 — Broken vendor pin on `main` (fixed in this branch).** PR #8 changed
`fta_web/core/json_viewer.py` (font, padding, dark theme) without a DIVERGENCE entry or
re-pin, so `test_vendor_integrity::test_vendored_matches_pin[json_viewer.py]` failed.
Added **D12** to `DIVERGENCE.md` and re-pinned `BASELINE.json`.

**R-2 — Line-ending-sensitive hashes (fixed in this branch).** The pins are sha256 of LF
bytes; with `core.autocrlf=true` every text file is CRLF on disk and every pin failed —
including files nobody touched — which made the guard useless on Windows. `_sha256` now
normalises CRLF→LF before hashing. Consider a `.gitattributes` with `* text=auto eol=lf`
as well (not done here: it renormalises the whole tree).

**R-3 — Six POSIX-only tests.** `test_api_files.py` symlink tests need
`SeCreateSymbolicLinkPrivilege` (`WinError 1314`) and `test_save_keeps_the_permissions…`
asserts `st_mode & 0o777 == 0o640`. Mark them `skipif` on Windows / when `os.symlink`
raises, so a red run on a Windows machine means something.

**R-4 — Frozen runner crashes on cp932.** `run_all_tests.py` and `test_core_module.py`
print `✓`/`❌` after the tests pass; on a Japanese Windows console this raises
`UnicodeEncodeError` and the suite reports failure. Workaround: `PYTHONUTF8=1`. (The files
are hash-pinned, so the fix is documentation — done in `desktop/README.md` — or a wrapper.)

**F-11 (found during integration, pre-existing, fixed here) — first click in the tree
selected the root.** `tree.js` shows the keyboard hint on `:focus-within`, and focus
arrives on mousedown; the hint was above the rows, so every row shifted ~56 px under the
pressed button, mouseup landed on a different row, and the browser retargeted the click
to the rows' common ancestor — the root item. Reproduced with real pointer events (DOM
`.click()` skips mousedown, which is why the frontend review did not see it). Fixed by
placing the hint below the list.

**Also noticed (open, minor):** the action bar is clickable before the dynamically
imported panel modules finish loading, so a very early click on **Add** (within ~1 s of
the page appearing) does nothing / reports "dialog module unavailable" once, and works on
the next click. Seen repeatedly in automated runs; a human rarely clicks that fast.
`main.js` could disable the bar until `loadPanels()` resolves.

**Also noticed:** `.github/copilot-instructions.md` described a `web_app/` Render.com
deployment that no longer exists (a note was added); `pyproject.toml`/`uv.lock` had
`pytest` added as a *runtime* dependency at some point on this machine — reverted before
PR #8, worth watching for.

---

## Fix order — as recommended, and what was done

| # | Items | Status | Where |
|---|---|---|---|
| 1 | **B-1/F-2/F-3** escape node names, sanitise imported SVG | ✅ done | D14 (`html.escape` in `node_label`), `diagram.js` `sanitizeSvg`, tests in `test_core_fixes.py` |
| 2 | **B-2** remove engine rounding | ✅ done | D15 `_tidy` (12 significant figures, display rounds), `test_core_fixes.py` |
| 3 | **F-1** use `change.index` | ✅ done | `chat.js`; pending list re-rendered after Analyze |
| 4 | **B-3, B-4, B-8** id hygiene | ✅ done | D16 `_dedupe_node_ids` + `last_load_warnings`, D17 `_canonicalize_root_id`/`ROOT_ID`, whole-tree `next_child_id`, `strip_links_to` → `removedLinks`; `warnings` returned by open |
| 5 | **B-6** normalise AI updates; **B-5** link cycles | ✅ done | `routes/ai.py` `_normalize_node` before `set_data`; D18 cycle fallback returns last computed / children-only value |
| 6 | **F-4/F-9** await details commits before save/export | ✅ done | `fta:flush` event collects promises; `flushPendingEdits` awaits them |
| 7 | **F-5…F-8, F-10** frontend; **B-7** i18n of errors | ✅ done | `is-zero` on `<li>`, hidden rows excluded from navigation; `t()` in `details.js`/`dialogs.js`; `confirmLabel||okLabel`; single toast host; `restoreFocus`; `api_error_response` localised |
| 8 | **R-3** skip POSIX-only tests on Windows | ✅ done | `requires_symlinks`, `posix_permissions` markers |
| — | **B-9, B-10, B-11, R-1, R-2, R-4, F-11** | ✅ done | undo pushed after apply; credentials 0o700/0o600 (D20); SDK probe outside lock; D12 + LF-normalised hashing; `PYTHONUTF8=1` documented; tree hint moved below rows |
| 9 | **D-C1…D-M7** desktop fallback | ⏸ deferred by policy | `desktop/src/` frozen; listed in `desktop/README.md` for fallback users |

---

## Recommended feature upgrades

These are the upgrades proposed for the web app now that the correctness items above
are closed. The full write-up — what each does today, what is missing, effort and the
standards they follow — is in
[`ROADMAP_MECHANICAL_ENGINEERS.md`](ROADMAP_MECHANICAL_ENGINEERS.md); this section is the
short list and its dependency on the review.

**Unblocked by this review.** Items that could not be built on the old engine and can
now: failure-rate inputs (needed B-2, done), cut sets (needed unique ids and cycle
handling, B-4/B-5, done), AI-grounded proposals (needed F-1, done), and any UI that
prints a probability (needed number formatting decoupled from the engine, done).

### P0 — do first

| Item | What it gives an engineer | Effort |
|---|---|---|
| **3.4 Number formatting** — scientific notation with user-chosen significant figures everywhere (details panel, diagram `P:`, tree, exports) | Values like 2.3E-7 readable and consistent; engine already stores full precision | S |
| **1.3 Failure-rate inputs with mission time** — per basic event choose fixed q, λ·T (1−e^−λT), periodically tested λτ/2, repairable λ/(λ+μ); document-level default mission time and unit; free-text *source* field | Enter the data engineers actually have (OREDA/NPRD/vendor λ), keep provenance in the file; `probability` stays derived for desktop compatibility | M |
| **1.1 Minimal cut sets** — MOCUS, ranked by probability with contribution, panel beside the diagram, click-to-highlight, Excel/JSON export | The primary FTA output (IEC 61025); also fixes over-counting of repeated (linked) events | M |
| **1.4 Standard gate types** — k-out-of-n, house, undeveloped first; XOR / INHIBIT / PAND / transfer next | Redundant trains (2oo3), scenario switches, visibly incomplete branches | M–L |
| **3.1 Standard FTA symbols + top-down layout** — event/gate/basic/undeveloped/house/transfer shapes, legend; keep today's table style as "compact" | Diagrams reviewers and regulators recognise | M |

### P1 — next

- **1.2 Importance measures** (Fussell–Vesely, Birnbaum, RAW, RRW) on top of cut sets; colour the tree by FV. (S after 1.1)
- **1.5 Common-cause failure groups** with β-factor / MGL. (M)
- **1.7 Sensitivity and scenario compare** — live ±factor on a basic event; diff of two files. (M)
- **1.8 ETA** — success/failure pivots summing to 1, consequence categories, end-state frequency table, bow-tie view. (M–L)
- **2.1 FMEA import/link** — CSV/XLSX rows become candidate basic events, row ID kept for traceability, re-import updates in place. (M)
- **2.3 Traceability fields** — requirement ID, test reference, owner, status, evidence link, tags; searchable. (S)
- **2.5 Report export** — PDF/DOCX with diagram, assumptions, event table, cut sets, importance; flat "event table" sheet in Excel. (M)
- **3.2 Large-tree navigation** — collapse in the diagram, focus mode, minimap, search highlight. (M)
- **3.3 Grid view** of basic events with paste-from-Excel. (M)
- **3.5 Lint panel** — single-input gates, events left at 1.0, undeveloped, dangling/cyclic links, duplicate ids (the load warnings from D16 are the first source), ETA branches not summing to 1, parent probability ignored. (S–M)

### P2 — when demanded

Uncertainty propagation (Monte Carlo, 1.6), component library (2.2), revisions and
review comments with diff (2.4), a headless CLI for batch re-quantification (2.6),
editing ergonomics and in-app help on the link/gate semantics (3.6, 3.7), and
completing the Japanese localisation of any new panels (F-6 closed the existing gap).

### AI assistant

Grounded proposals (rate range + source class on each proposed event), narratives built
from the cut-set and importance tables instead of the raw JSON, and an "audit this
tree" action that runs the lint rules and asks the model only about what rules cannot
decide. F-1 is fixed, so extending this area is safe now.

### Small items surfaced by the fixes themselves

- **Disable the action bar until `loadPanels()` resolves** (the open minor item above). S.
- **Surface `warnings` from open and `removedLinks` from delete more prominently** —
  they are toasts today; the lint panel (3.5) is their natural home.
- **Promote `last_load_warnings` (duplicate ids, root renamed) to a file-level notice**
  that is saved with the file, so a reviewer sees that the source was repaired.

### Suggested order

1. 3.4 + 1.3 together (formatting, rates, mission time) — the change existing users notice first.
2. 1.1 cut sets, then 1.2 importance.
3. 1.4 gates and 3.1 symbols together, since every new gate needs a symbol.
4. 3.5 lint panel, folding in the load/delete warnings.
5. 2.5 reporting once cut sets and importance exist.
6. The rest by demand. Nothing is back-ported to `desktop/`, which stays frozen.
