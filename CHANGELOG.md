# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Validation: `RATE_IMPLAUSIBLE`** (warning). A rate, standby or repairable
  event with λ above 1e-2 /h (an MTBF under 100 h), or a rate event whose q
  reaches 0.999, is flagged: almost always FIT or per-year values entered as
  per hour. Before this, importing an FMEA sheet whose λ column held FIT
  values (120, 45) with the default `/h` made both events certain (q = 1)
  and Validation said nothing.

### Changed

- **FMEA import: λ unit suggestion.** When the λ header does not name a unit,
  the suggestion now comes from the column's values: a median of 1 or more
  suggests FIT, 1e-3 up to 1 suggests `/y`. A unit in the header (`FIT`,
  `/y`, `per year`, `/h`, `per hour`, `年`, `時間`) still wins.

### Fixed

- **OR gates flushed very small probabilities to zero.** The OR formula
  `1 − Π(1 − p)` cancels for small inputs: OR(1e-17, 1e-17) was exactly 0
  (so OR(AND(1e-6 ×3), AND(1e-6 ×3)) made a tree-walk headline of 0 while
  the MCUB said 2e-18), OR(1e-15, 1e-15) was 1.998e-15 and OR(1e-12, 3e-12)
  4.00002e-12. An OR (gate or OR-links) whose result is below 1e-3 is now
  computed as `−expm1(Σ log1p(−p))` (`engine.or_probability`), in the tree
  walk and in the Monte Carlo tree evaluator alike. Results at or above
  1e-3 keep the 1.6 formula, so ordinary legacy trees give bit-identical
  numbers; the others differ from 1.6 only by the precision 1.6 lost. Found
  by a back-to-back comparison with a truth-table oracle.
- **Monte Carlo without uncertainty:** the reported mean could be one ulp
  off the point estimate, with a standard deviation of ~1e-18, although
  every sample equals the point estimate (`fsum(samples) / n` does not
  always return the sample value; about 1 run in 12). The mean is now
  pivoted on the first sample, so equal samples give exactly their value
  and a standard deviation of 0.
- **`LINKS_REMOVED` survived the undo that restored the link.** Deleting a
  node that another node linked to, then undoing, brought the node and the
  link back but kept "Link from … to deleted node … was removed" in
  `sessionWarnings` and the Validation tab. The notice now belongs to the
  delete (by hand or by the AI assistant): undo removes it, redo restores
  it, as for the AI gate-type notices.
- **Importance measures lost the digits of small contributions.** FV,
  Birnbaum and RRW took the difference of two separately rounded log sums,
  which cancels: in OR(A = 0.5, B = 1e-17) the FV of B was 0.0 (exactly
  1e-17), and on the B2B corpus FV was off by up to 1.8e-8 relative. The
  exponent difference is now summed directly from the changed terms; every
  measure agrees with exact rational arithmetic to 1e-12.
- **DOCX report, validation section:** `CUTSETS_TRUNCATED` did not match the
  Validation tab. Its `params.count` was always 0 (the whole cut-set result
  was handed to lint instead of the truncation signal); it followed the
  report's override limits instead of the document's; and a report without
  the cut-set section never reported truncation at all. It is now the
  Validation tab's signal, reusing the report's cut sets when they were
  expanded with the document's limits.
- **Number formatting, server side (CLI, DOCX report, diagram labels)** now
  reads the same as the browser. Found by a back-to-back comparison with
  `static/js/numfmt.js`: a number with more integer digits than significant
  figures kept all of them (RAW 9238.78 at 3 s.f. was `9239`, the browser
  showed `9240`); exponents were written `1.23e+4` (browser `1.23e4`); and
  exact ties rounded half-to-even (0.25 at 1 s.f. was `0.2`, the browser
  showed `0.3`).
- **Diagram, dark mode:** cross-link edges were pure blue on the dark
  background (about 2:1 contrast) and barely visible. They are now `#6cb6ff`
  in dark mode (8:1); light mode keeps the 1.6 blue. The transfer-gate fill
  and the dotted edges to a transfer's ignored children were raised to at
  least 3:1 against the background in both themes. `test_diagram_dot.py`
  checks the contrast of every colour the DOT emits.
- **Diagram, standard-symbols style:** a gate or event symbol could sit off to
  the side of its own event box (near a neighbour's), making it ambiguous
  which gate belonged to which event. Each box and its symbol now share a
  Graphviz `group` and a heavy (`weight=100`) edge, so the symbol hangs
  straight under (top-down) or beside (left-right) its box. The compact
  style is unchanged.

## [1.7.0] - 2026-09-28

Analysis release for the web app. Engineers can now enter failure rates, use
the standard gate types, get minimal cut sets, importance and uncertainty,
validate a tree, trace nodes to requirements, import an FMEA, run batches from
the command line, and produce a report. Each feature has its own tab in a new
bottom panel. An **Advanced** switch keeps the basic UI simple.

**The vendored core is not edited.** `fta_web/core/` and `desktop/` keep their
pinned hashes, and no divergence was added. All new behaviour lives in
`fta_web/engine.py` as `WebCore(FTACore)` and in new sibling modules.

### Added

- **Engine (`engine.py`).** `WebCore` subclasses `FTACore` and overrides only
  three methods: the tree walk, `load_from_json` (to keep the `analysis`
  block) and `prepare_export_data`. It replaces `FTACore()` at every
  construction site. On legacy trees it reproduces the core exactly;
  `test_engine.py` proves this on a few hundred random trees with links and
  cycles.
- **New optional node keys** (`node_schema.py`, mirrored in
  `static/js/schema.js`): `gateType` (AND, OR, KOFN, XOR, INHIBIT, PAND,
  TRANSFER), `k`, `transferTo`, `eventKind` (basic, house, undeveloped,
  conditioning), `houseState`, and the objects `quant`, `trace` and `fmea`.
  `logicGate` stays AND/OR as the projection of `gateType`.
- **Document `analysis` block**: mission time, display time unit, cut-set
  limits, Monte Carlo n and seed, and the FMEA occurrence table. It is saved
  beside `tree`, is part of undo, and invalid values are reset on load with
  a notice.
- **Quantification models**: fixed q, rate 1−e^(−λT) with T defaulting to the
  mission time, standby min(1, λτ/2) (flagged above λτ = 0.2) and repairable
  λ/(λ+μ). λ is stored per hour; the UI accepts /h, /y and FIT. Each event
  has a data-source field and a lognormal uncertainty (median or mean, error
  factor). The derived value is written to `probability`.
- **Gate semantics**:
  - k-out-of-n by exact Poisson-binomial computation
  - XOR a+b−2ab (odd parity for n ≠ 2; flagged non-coherent)
  - INHIBIT with a conditioning event
  - PAND Πp/n! (flagged as an approximation)
  - same-file TRANSFER through the shared memo
  - house events 1/0
- **Minimal cut sets** (`logic.py`, `cutsets.py`): bottom-up MOCUS over a
  compiled Boolean graph, with integer-bitmask sets, repeated events counted
  once, and truncation by order, count and cutoff that is reported. Also the
  MCUB and rare-event values. A voting gate is refused above 20,000
  combinations.
- **Headline value** in the top bar: the MCUB when the tree has repeated
  events or XOR, the tree walk otherwise (`engine.summary`,
  `GET /api/analysis/summary`), with an MCUB badge in advanced mode. It is
  refreshed 400 ms after every change, and an outdated answer is dropped. ETA
  mode shows the root value without a badge.
- **Validation badge** on the Validation tab button: a red error count, or
  else an amber warning count. It is shown in basic mode too.
- **"Show in Validation"** button on the warning toasts for load repairs and
  removed links.
- **FV bar in the tree**: while the importance overlay is on, each tree row
  shows a small bar on the diagram's colour scale.
- **Importance measures** (`importance.py`): Fussell-Vesely, Birnbaum, RAW and
  RRW on the MCUB, computed in log space through an event-to-cut-set index,
  with an FV colour overlay on the diagram.
- **Monte Carlo uncertainty** (`uncertainty.py`): pure Python, seeded and
  deterministic, time-capped with partial results, and one run at a time. It
  evaluates the tree exactly when the tree is coherent with no repeated
  events, and otherwise uses the MCUB over the cut sets covering 99.99 % of
  the rare-event sum.
- **Validation** (`lint.py`): 21 codes with fixed severities, localised
  messages and one-line fixes. Load repairs and removed links are collected
  as session notices (`AppState.session_warnings`).
- **Bottom-panel tabs**: Details, Quantification, Cut Sets, Importance,
  Uncertainty, Validation, Traceability, FMEA and Report. They are
  lazy-loaded, the last-used tab is remembered, and they refresh when the tree
  changes. Each has English and Japanese catalogs.
- **Advanced switch** in the top bar (`fta.advanced`, off by default). Basic
  mode shows Details and Validation only, and AND/OR only. Advanced content
  in a file is shown read-only with an "advanced" chip, never hidden or
  lost. Calculations, files and the API are identical in both modes.
- **Significant-figures selector** (`fta.sigFigs`, 1–6, default 3). It is
  used by the UI (`numfmt.js`) and by the report, Excel and CLI
  (`numfmt.py`).
- **Traceability**: requirement ID, test reference, owner, status, evidence
  and tags per node, edited in a grid. Tree search understands `tag:`,
  `owner:`, `status:`, `req:` and `fmea:`, and highlights nodes from other
  tabs.
- **FMEA import** (`fmea_import.py`, `/api/fmea/preview`, `/api/fmea/import`):
  CSV or XLSX, a suggested column mapping (English and Japanese headers), λ
  unit conversion, and an editable AIAG occurrence-rank table saved in the
  document. Re-import updates in place by `fmea.id`, the whole import is one
  undo step, and bad rows are skipped with reasons.
- **DOCX report** (`report_docx.py`, `POST /api/report/docx`, new `report`
  extra = `python-docx`, included in `all` and `dev`). Sections: metadata,
  headline, assumptions, diagram (the browser PNG, falling back to native
  `dot`), events, cut sets, importance, uncertainty (optional), validation and
  traceability. English or Japanese.
- **Excel export**: new **Events** (flat, numeric, filterable) and
  **Analysis** sheets beside the unchanged hierarchical sheet
  (`excel_events.py`).
- **Diagram**:
  - a *Standard symbols* style, with IEC 61025 / NUREG-0492 paths in the
    browser (`fta_symbols.js`) and Graphviz approximations in native renders
  - a top-down layout
  - significant figures in labels
  - `idMap` in `GET /api/dot`, so clicking a gate symbol selects its node
- **CLI** (`cli.py`): `quantify`, `cutsets`, `importance`, `mc`, `validate`
  and `report`, with `--json`/`--csv`, `--out`, `--sig-figs`, limit and
  Monte Carlo options, and exit codes 0/1/2/3. It works as
  `fta_editor.exe <cmd>` and `python fta_web/run.py <cmd>`, and never starts
  the server.
- **API**:
  - new endpoints: `POST /api/analysis/settings`, `GET /api/analysis/summary`,
    `POST /api/analysis/{cutsets,importance,uncertainty}`,
    `GET /api/analysis/validate`, `POST /api/report/docx` and
    `POST /api/fmea/{preview,import}`
  - new error codes: `MODE_UNSUPPORTED` (409), `BUSY` (409),
    `ANALYSIS_TOO_LARGE` (422) and `EXPORT_UNAVAILABLE` for docx (503)
  - `capabilities.reportExport` and `capabilities.fmeaXlsx`
  - `analysis` and `sessionWarnings` in `/api/state` and in every mutation
    payload
- **Docs**: the User Guide gains "Analysis features (1.7)", a CLI reference
  and desktop compatibility notes. The API reference gains the 1.7 endpoints
  and modules. The roadmap and code review are marked with their 1.7.0
  status.

### Changed

- `PATCH /api/nodes/<id>`:
  - `quant`, `trace` and `fmea` merge partially, and `null` removes a key or
    sub-key.
  - Setting `gateType` rewrites `logicGate` to its projection.
  - Setting `logicGate` on a node with a `gateType` keeps the two in step.
- `POST /api/ai/update` restores the 1.7 node keys by node id that a
  full-tree AI rewrite dropped, and reports `mergedFields`.
- `GET /api/dot` and `POST /api/render` accept `style`, `rankdir` and
  `sigFigs`. The compact style's meta line uses significant figures instead
  of `%.1E`.
- `GET /api/fs/list` takes an optional `ext` filter, for example
  `?ext=.csv,.xlsx`. It is limited to `config.LISTABLE_EXTENSIONS`
  (`.json`, `.csv`, `.xlsx`); anything else is `400 INVALID_FIELD`, and the
  default is still `.json` only. The FMEA file dialog uses it.
- Error localisation now covers `BUSY` and `ANALYSIS_TOO_LARGE`, including
  per-reason texts for `kofn` and `time`. The DOCX-unavailable message gives
  `uv sync --extra report`, and FMEA `.xlsx` without openpyxl has its own
  message.
- The node details panel moved into the Details tab. Its gate selector
  offers the advanced gates when the Advanced switch is on.
- The frozen build bundles `python-docx`, with its templates, when it is
  installed. CLI subcommands work in the exe.
- **Document analysis defaults can be edited in the UI.** The Cut Sets tab
  (max order, max count, cutoff) and the Uncertainty tab (samples, seed)
  start from the document's `analysis` settings and have a **Save as document
  defaults** button (`POST /api/analysis/settings`: undoable, marks the
  document modified). The `CUTSETS_TRUNCATED` hint now points there.
- **The MCUB badge tooltip gives the reason**: repeated events, XOR
  (non-coherent) gates, or both. It used to say "repeated events" also for
  XOR trees.
- **Priority-AND in cut sets is now visible.** Cut sets expand PAND as plain
  AND (no 1/n!), which is conservative, so an MCUB headline drops the PAND
  reduction. The Cut Sets tab shows a *PAND treated as AND in cut sets
  (conservative)* badge and the MCUB tooltip says so.
- **`INHIBIT_ARITY` from the engine** now uses lint's rule: exactly two
  inputs, one of them conditioning. Before, the engine accepted three or more
  inputs while the Validation tab rejected them. Quantification is unchanged.
- The DOCX report's event table has a **Source** column (`quant.source`).
- `GET /api/export/xlsx` accepts `?sigFigs=N` (clamped to 1–6) for the number
  formats; the Excel buttons send the top bar's setting. It was always 3.
- **`GET /api/analysis/summary` separates its own caps from the document's
  limits.** It uses `min(maxCount, 2000)` sets; `capped: true` means only the
  summary's 2000-set / 2 s caps cut the run short, while `truncated` and the
  new `truncatedBy` mean the document's limits did. In advanced mode a subtle
  `≈` marker after an MCUB headline shows either case in its tooltip.
- **`POST /api/report/docx` reads only its documented keys.** `limits` is
  validated like `analysis.cutsets` (unknown keys, including `timeBudgetS`,
  are a 400), `uncertaintyN` must be an integer 1–5,000 and
  `uncertaintyTimeLimit` a number of seconds in (0, 60]; other top-level keys
  are ignored.

### Fixed

- **Diagram labels spilled past their boxes or sat off-centre.** Graphviz
  sizes and places label text with its own font metrics, which run 20–25%
  narrower than the fonts the page draws with. The preview now centres each
  label in its box and, only if it would still overflow, squeezes it to fit.
  Browser SVG/PNG exports use the same fitted labels. Server-side padding
  grows with the row's length and is split evenly around the text, so native
  Graphviz exports are centred too. Box scale 0 no longer spills.
- **The top-bar date field was clipped** (`2026-09-2`) by the new 1.7
  controls; it now always has room for a full date.
- **The node details showed small probabilities as `0`.**
  `dialogs.formatProbability` rounded to six decimals, so 1e-7 displayed as
  `0` even though the stored value was right. It now uses
  significant-figure formatting.
- **Boot gate**: the action bar and keyboard shortcuts were live for about a
  second before the panels finished loading (the last open item of the
  2026-09 code review). `<html data-booting>` now blocks them until
  `loadPanels()` settles.
- **Multi-select delete now reports removed links.** Deleting several nodes
  from the tree did not report the links that were stripped with them, as a
  single delete does. It now shows the count in a toast linked to the
  Validation tab.
- **`mc --csv` and the `mc` text table had an empty `n` column**: the CLI read
  a key `uncertainty.run` does not return. They now show `requested` and
  `completed`.
- **`CUTSETS_TRUNCATED` never appeared** in the Validation tab or
  `validate`, because they ran lint without a cut-set result. They now expand
  the cut sets with the document's limits (2 s budget, outside the lock;
  skipped silently on failure or timeout) and pass the truncation to lint.
- **House events and transfer gates showed stale values in the desktop app.**
  The engine now writes their derived value into `probability` (1/0 for a
  house event, the target's value for a transfer), which is what the 1.6 app
  reads.
- **A gate changed in the desktop app was silently discarded.** The desktop
  app edits only `logicGate`, and the stale `gateType` won. On load and on an
  AI update, a `gateType` that does not project to `logicGate` is now dropped
  (with its `k`/`transferTo`) and reported as `LOAD_REPAIR`
  (`gate_type_reset`). An AI update also no longer restores a `transferTo`
  whose transfer gate it dropped.
- **The report's Monte Carlo section never said when a run was cut short**,
  and never showed the sample count: it read `completed` as a flag and a
  key `n` that `uncertainty.run` does not return. It now notes a time-capped
  run (`truncatedByTime`) and shows *completed / requested* samples.
- **The report's cut-set section lacked the MCUB and rare-event values** the
  User Guide lists; they are now shown. An infinite RRW is shown as `∞`
  rather than `—`.
- **`report --time-limit` was ignored** (the report always used 30 s). It is
  now honoured, capped at 60 s.
- **`report x.json --out reports`** wrote a file literally named `reports`
  when that folder did not exist yet. For `report`, an `--out` that does not
  end in `.docx` is now a folder.
- **`--top 0`** silently showed every row, and `--time-limit 0` was
  accepted; both are now usage errors (exit 2). A mistyped command
  (`fta_editor qunatify x.json`) now names the valid commands instead of
  argparse's "unrecognized arguments".
- **Excel export**: a NaN or infinite number in a hand-edited file was
  written as an empty numeric cell (malformed for Excel); it is now left
  blank. On the Analysis sheet only probabilities use the scientific format
  (mission time reads `8760`, not `8.76E+03`).
- **Deleting a node left transfers pointing at its id**, so the next node
  added there silently became the transfer's target. `DELETE /api/nodes`, an
  AI `delete` change and a full AI update now strip `transferTo` (and, on the
  AI paths, links) into removed ids, reported in `removedLinks` /
  `LINKS_REMOVED` with relation `TRANSFER`.
- **Applied AI gate edits were overruled by a stale `gateType`**;
  `POST /api/ai/changes/apply` now reconciles gate types like `/update`. A
  `gate_type_reset` notice from an AI edit carries `params.cause: "ai"`, says
  so in the Validation tab (English and Japanese), and is undone and redone
  with the edit.
- **NaN/Infinity in a response** (a loaded tree, an error's `detail.value`)
  made it unparseable for the browser; they are now sent as `null`.
  `POST /api/fmea/import` with a non-string `lambdaUnit` is a 400, not a 500.
- **Windows path hardening**: a `:` after the drive (an NTFS alternate data
  stream such as `notes.txt:x.json`) is refused, and a path on another drive
  or share (UNC, `\\?\`, a `subst` alias of the root) is refused before it
  is resolved, so no SMB connection is opened.
- **Load errors say what is wrong**: *empty*, *not valid JSON (line, column)*
  or *root must be an object*, instead of the core's encoding error.
- **Numerics**: a PAND gate with more than 170 inputs no longer overflows
  (log space); Monte Carlo with an extreme error factor no longer overflows;
  float sums use `math.fsum`, so Python 3.10/3.11 give the same results as
  3.12+; an empty cut-set list has MCUB `0.0`, not `-0.0`.
- **Web UI** (frontend pass):
  - the diagram keeps fitting while the tree grows until you zoom or pan, and
    on resize;
  - analysis tabs drop stale results and inputs after New / Open, and a tab
    that went stale in the background re-runs when shown;
  - number fields reject `5,000` (it was read as 5) and hex; cut-set limits
    are range-checked with localized messages; Escape reverts typing;
  - the Uncertainty tab no longer lowers a stored `mc.n` above 100,000 on
    Save;
  - Quantification labels are tied to their controls; diagram popovers, font
    options and aria-labels follow the language;
  - **Render** and PNG export honour the style, layout and significant
    figures; the symbols style is rasterised in the browser, never by native
    `dot`;
  - the capabilities chip and panel are styled (the panel floats instead of
    pushing the top bar down), and faint text, badges and unit suffixes meet
    WCAG AA contrast in both themes.

### Compatibility

- **The file format is additive.** Every new key is optional, and a 1.6 file
  opens and computes exactly as before. A 1.7 file without advanced features
  is a valid 1.6 file plus an `analysis` block.
- **The legacy desktop app** reads only `logicGate` and `probability`:
  - Advanced gates are projected to AND or OR. INHIBIT and PAND become AND;
    KOFN, XOR and TRANSFER become OR.
  - Model-derived probabilities, house states (1/0) and transfer values are
    written into `probability`, so its numbers stay meaningful. A transfer
    gate that has children is still computed from them there.
- **Saving from the desktop app** keeps the new node keys but drops the
  top-level `analysis` block, which then reverts to its defaults.
- **Desktop gate edits are kept.** When a file comes back from the desktop
  app with a `logicGate` that its `gateType` no longer projects to,
  `logicGate` wins and the stale `gateType` is dropped with a load notice. A
  rate model still recomputes `probability`.
- See [USER_GUIDE.md → Desktop app compatibility](docs/USER_GUIDE.md#desktop-app-compatibility).

## [1.6.4] - 2026-09-22

Single-defect release for the web app: **click-to-select in the diagram panel
was dead in every Chromium-based browser** -- Chrome, Edge, Brave and the
packaged build's default browser -- which is the one interaction spec 6.8 calls
"the main payoff of choosing SVG over PNG". Nothing else changed; the 1.6.3
bundle is otherwise byte-for-byte what this one freezes.

### Fixed

- **Clicking a node in the diagram now selects it in the tree and node details
  again.** The panel took pointer capture on `pointerdown` so it could pan on
  drag; Chromium-based browsers then retarget the follow-up `click` at the
  stage container, so `diagram.js` never found the `<g class="node">` that was
  pressed and the selection never moved (spec 6.8 "click a node in the diagram
  -> selects it in the tree"). Capture is now taken only once the pointer has
  moved past a 4 px slop, i.e. when the gesture really is a pan, and the node
  under `pointerdown` is remembered as the fallback answer to "which node?".
  A drag that pans still leaves the selection alone.
  Pinned by `fta_web/tests/test_diagram_click_select.py`.

## [1.6.3] - 2026-09-21

Correctness release for the web app, which is now the primary path. Every
web-app finding of the September 2026 code review is fixed; the legacy desktop
app moved to `desktop/` as a frozen fallback. Verified on the packaged Windows
build (`build/dist/fta_editor/fta_editor.exe`, PyInstaller 6.22.3): page, static
assets, token enforcement, DOT, Excel export and all three AI providers.

### Documentation

- `docs/CODE_REVIEW_2026-09.md` records the status of every finding, the latest
  test results (622 passed, 6 skipped; CI green on Linux and Windows) and a
  condensed list of recommended feature upgrades;
  `docs/ROADMAP_MECHANICAL_ENGINEERS.md` notes that all its blocking review
  items are closed.
- `build/README.md`: Windows build is verified, not "out of scope"; added a
  warning about building from a cloud-synced `.venv`.

### Fixed

Findings from the September 2026 code review (`docs/CODE_REVIEW_2026-09.md`), web
app only — the legacy desktop app in `desktop/` is frozen and keeps its defects,
which `desktop/README.md` lists.

- **Probability engine** (`fta_web/core/FTA_Editor_core.py`, divergences D14–D18):
  results are no longer rounded to six decimals at every gate, so probabilities
  below 5e-7 — the normal failure-rate range — are no longer zeroed, flagged as
  zero and hidden; duplicate node ids in a loaded file are renamed
  (`<id>_dup2`, …) and reported instead of silently aliasing each other's maths;
  the top-level node's id is forced to `root` on load with links remapped; a link
  cycle no longer saturates the tree to 1.0; `set_metadata()` no longer resets the
  date when called without it.
- **Diagram** (`fta_web/core/json_viewer.py`, D13, D19; `diagram.js`): node names
  containing `<`, `>` or `&` no longer break the DOT and blank the whole diagram;
  the SVG imported from the WASM renderer is sanitised (no scripts, event
  attributes or non-http links), closing an HTML-injection path via a shared
  `.json`; DOT ids for non-ASCII or punctuated node ids no longer collide.
- **API** (`fta_web/routes/`, `tree_ops.py`, `state.py`): deleting a node strips
  every link into the deleted subtree and reports them as `removedLinks`, and new
  ids never reuse an id present anywhere in the tree, so a stale link can no
  longer silently re-target an unrelated new node; `/api/file/open` and
  `/api/import/json` return `warnings` for ids renamed on load; `/api/ai/update`
  normalises the AI's JSON before installing it (a string probability no longer
  500s every diagram request); `/api/ai/changes/apply` no longer records an undo
  step for an all-rejected batch; API errors are localised on every blueprint
  (`?lang=ja` works for domain errors); the AI-SDK probe no longer runs under the
  state lock; root-protection guards use the actual top-level id.
- **Frontend**: AI "Apply selected" sends the server's pending-change indices
  rather than card positions, so it can no longer apply a proposal the user
  never saw, and "Analyze FTA" now shows its proposals; Save / Save As / exports
  wait for in-flight field commits (`fta:flush`) instead of racing them, and
  details-panel commits are serialised so out-of-order responses cannot install
  a stale tree; Hide Zero hides the whole item (children included) and keyboard
  navigation and range selection skip hidden rows; the Node Details panel, Add
  Node dialog and links editor are fully localised (48 new catalog keys) and
  the delete confirmation button reads "Delete"; details errors use the shell's
  toasts; `beforeunload` also protects typed-but-uncommitted text; Escape in a
  field no longer dismisses the top toast; focus returns to the tree after a
  dialog whose trigger row was re-rendered; the bare Delete key only acts from
  the tree; the diagram's settings popover no longer intercepts clicks while
  hidden; the first mouse click in the tree after loading no longer selects the
  root instead of the clicked row (the keyboard hint used to appear above the
  rows on focus and shift them under the pressed button — it now appears below
  the list).
- **Credentials**: `~/.fta_editor/ai_credentials.json` and its directory are now
  created with owner-only permissions (D20; best-effort on Windows).
- **Tests**: `test_vendor_integrity` hashes with line endings normalised, so it
  no longer fails every pin on a Windows `autocrlf` checkout; the six POSIX-only
  symlink/permission tests are skipped where symlinks or mode bits are
  unavailable. New suites: `fta_web/tests/test_core_fixes.py`,
  `fta_web/tests/test_backend_fixes.py`.

### Changed

- **The web app is now the primary path; the desktop app is a fallback.** The
  legacy Tkinter application and everything that belongs only to it moved from
  the repo root into `desktop/`: `src/` → `desktop/src/`, `tests/` →
  `desktop/tests/`, `data/` → `desktop/data/`. Contents are byte-for-byte
  unchanged and the frozen suite still passes from its new home (the tests
  resolve `src/` and `data/` relative to their own parent directory, so moving
  the three together needed no edits to them). `fta_web/core/BASELINE.json`
  and `fta_web/tests/test_vendor_integrity.py` now pin the new paths — same
  hashes. `pytest.ini`, `install.py`, `pyproject.toml`, the build spec and all
  docs point at `desktop/src/FTA_Editor_UI.py`; `desktop/README.md` records
  the fallback's status and the defects it does not fix.

## [1.6.2] - 2026-09-15

Fixes found by running the packaged build on Windows, and the CI that would
have caught most of them. Nothing here changes the desktop app (`src/`), which
remains frozen.

### Fixed

- **Every button in the web UI did nothing on some Windows machines.** Where
  the `.js` entry in `HKEY_CLASSES_ROOT` had been overridden to `text/plain`
  by other software, Flask's static handler — which asks the stdlib
  `mimetypes` module — served `main.js` as plain text. Browsers refuse to
  execute a `<script type="module">` that does not arrive as a JavaScript MIME
  type, so no frontend code ran at all and the whole editor looked dead. The
  server was healthy and its logs were clean, which is what made this hard to
  recognise. `fta_web/app.py` now pins the `.js` and `.css` types at import,
  overriding whatever the host claims.
- **Add Node created nothing.** The dialog collected its fields and never sent
  them to the server.
- **Render was unavailable without a native Graphviz**, even though the
  diagram panel's own PNG button already produced a file via the in-browser
  WebAssembly renderer in exactly that situation. Render now tries native
  first and falls back the same way.
- **Diagram labels could spill outside their node boxes.** Graphviz sized each
  box from its own estimate of the requested font's metrics, which does not
  match how the browser — or a different Graphviz build — actually renders
  that font, most visibly with Japanese text. Boxes are now sized by a trailing
  run of blank characters measured by the same engine, at the same size, as the
  visible text, so the box grows by whatever margin those characters genuinely
  need instead of by a guessed pixel value.
- **Dark mode did not reach the diagram.** The panel's chrome referenced CSS
  custom properties that were never defined and silently fell back to
  light-mode literals, and the rendered graph's background and connectors
  stayed light. Both now track the theme. Node fills are deliberately left
  alone — they encode calculated probability, not style — and link edges stay
  blue, since colour is what distinguishes a link from a tree edge.
- **The file dialog only accepted clicking through folders.** It now also takes
  a typed or pasted absolute path, resolving it as a folder to browse into or a
  file to open/save directly.
- **The FTA/ETA mode selector was clipped** by its own dropdown arrow.
- **Every SHA-256 pin failed on a Windows checkout.** Git for Windows defaults
  to `core.autocrlf=true` and rewrites LF to CRLF, and the pins in
  `fta_web/core/BASELINE.json` are a contract about *bytes*. A clean clone
  showed a dozen integrity failures with nothing edited — and, less visibly,
  the audit the PyInstaller bundle exists to support (hashing the shipped
  `fta_web/core/` against `BASELINE.json`) could never have passed on Windows.
  A new `.gitattributes` normalizes to LF and marks the pinned trees `-text`.
  A clone made before it exists needs `git rm --cached -r . && git reset --hard`
  once.

### Added

- **Continuous integration** (`.github/workflows/tests.yml`) — the full suite
  on Linux (Python 3.10 and 3.13, with Graphviz installed so the native render
  path is exercised) and on Windows. Previously nothing ran the tests unless a
  person remembered to, which is how a broken vendor pin reached `main`. The
  Windows job found two real problems on its first two runs.
- **Regression tests for the static asset MIME types**
  (`fta_web/tests/test_static_mime.py`). These reproduce the broken host — they
  poison `mimetypes` to report `text/plain` for `.js` first — because the
  obvious version of this test passes on Linux whether or not the fix exists,
  and would have pinned nothing.
- **A box-sizing control** on the diagram panel (the **Aa** popover): font
  auto-detection preferring Meiryo, a manual scale (0–30, default 4), and a
  draggable position.

### Changed

- **`docs/CHANGELOG.md` is now a pointer to this file** instead of a second
  copy. It had drifted — it stopped at 1.5.1 while this file went on to 1.6.x —
  and a changelog that is a year behind answers the question confidently and
  wrongly. Every entry it held is present here.
- **`docs/CONTRIBUTING.md` documents the frozen tree and the vendored fork.**
  The rule that `src/`, `tests/` and `data/` must not change, and that any edit
  to `fta_web/core/` needs a divergence entry plus a re-pin, previously existed
  only inside the file it governs and in a test's failure message.
- **`docs/USER_GUIDE.md`** documents dark mode, the box-sizing control, what
  the node colours mean, and where the AI Assistant's API key is stored.
- **Divergence D12** recorded in `fta_web/core/DIVERGENCE.md`: the diagram
  sizing and font/scale/dark parameters described above are a change to the
  vendored `json_viewer.py`. This is that file's first divergence and the last
  vendored module to leave byte-identity with its `src/` counterpart.

## [1.6.1] - 2026-09-13

Bug-fix release found by building and exercising the packaged executable from
[1.6.0](#160---2026-09-09) rather than only running from source.

### Fixed

- **Gemini in a frozen build.** The standalone executable's Google Gemini
  provider was non-functional (`"Google Generative AI package not installed"`
  regardless of key validity) while OpenAI and Anthropic worked correctly —
  caused by `google.generativeai` living under `google`, a PEP 420 namespace
  package that PyInstaller's plain `hiddenimports` silently fails to collect.
  Fixed by migrating `fta_web/core/ai_providers.py`'s `GeminiProvider` off the
  now end-of-life `google.generativeai` SDK onto its replacement,
  `google.genai` (divergence **D11** in `fta_web/core/DIVERGENCE.md`), and
  retargeting `build/fta_editor.spec`'s namespace-package `collect_all()`
  workaround at `google.genai` and `google.auth`. Verified against a rebuilt
  binary: all three providers now reach their real API with a deliberately
  invalid key and return the provider's own 4xx error. `pyproject.toml`'s `ai`
  extra now installs `google-genai`; the `desktop` extra gained
  `google-generativeai` explicitly, since the frozen `src/ai_providers.py`
  still needs the old package — the two apps now genuinely require different
  SDKs for the same provider. Bundle size: 80 MB with all three AI SDKs
  (down slightly from 1.6.0's 79 MB baseline despite adding a package, because
  `google.genai` itself needs none of the ~100 MB `google-api-python-client`
  chain the old SDK required — see `build/README.md`'s "Bundle size" section).

### Investigated, not a defect

- **Button clicks appearing to do nothing.** Reported after a packaged-build
  test: clicking any action-bar button seemed to not reach the server. Could
  not be reproduced — real, CDP-dispatched mouse clicks (not synthetic
  `.click()`) against a freshly built and launched binary correctly fire the
  expected `POST` request with no console errors, both before and after the
  Gemini fix above. If this recurs, the details that would narrow it down are
  the browser and OS used, whether the tab was freshly opened for that launch
  or reused from an earlier one (a stale per-launch auth token would fail
  every request), and anything shown in the browser's own developer console.

## [1.6.0] - 2026-09-09

The editor now runs in a browser. Everything in this release is additive: the
Tkinter desktop app in `src/` is byte-for-byte unchanged and still the way to
run version 1.5.1.

### Added

- **Web application (`fta_web/`)** — the same editor as a local, single-user
  web app. `python3 fta_web/run.py` starts a loopback-only server and opens a
  browser on it.
  - **Tree editing**: add, edit, delete, reorder and move nodes; 50 levels of
    undo/redo; live probability recalculation with AND/OR gates; FTA and ETA
    modes; zero-probability nodes highlighted.
  - **Diagram rendering with no Graphviz installed.** The browser draws the
    diagram from `GET /api/dot` using a vendored WebAssembly build of Graphviz
    (`static/vendor/viz-js/viz.js`). A native `dot` binary, when present, is
    used only by `POST /api/render` to produce a file to save.
  - **Honest capability disclosure.** `GET /api/state` returns a
    `capabilities` object (`nativeDot`, `excelExport`, `aiConfigured`); the UI
    disables and *explains* a control whose optional dependency is missing
    instead of offering a button that fails when pressed.
  - **File I/O and exports**: open/save/save-as with a sandboxed file browser,
    plus JSON, XML, Excel, SVG and PNG export.
  - **AI assistant**: chat, "Analyze FTA" and "Update FTA", over OpenAI,
    Azure/Microsoft Copilot, Anthropic Claude and Google Gemini — the same
    providers and the same credential file (`~/.fta_editor/ai_credentials.json`)
    as the desktop app.
  - **Security model** for a tool that can read and write local files: bound to
    `127.0.0.1` only and not configurable; a per-launch token minted at startup,
    never persisted, required in the `X-FTA-Token` header on every `/api/*`
    call; Host/Origin pinned against DNS rebinding; the filesystem endpoints
    confined to a sandbox root (`--root`, default `$HOME`) with an extension
    allowlist; request bodies capped at 10 MB. A cookie session is deliberately
    *not* used — the browser would attach it to a forged cross-site request,
    which is the attack the header token prevents.
  - Refuses to start under gunicorn/uWSGI/mod_wsgi or with `WEB_CONCURRENCY>1`:
    the whole editor state is one in-process object, so a second worker would
    not crash, it would silently lose edits.

- **Standalone executable** (`build/fta_editor.spec`) — a PyInstaller *onedir*
  bundle of the web app that runs with **neither Python nor Graphviz
  installed**. Build with
  `uv sync --extra all --extra build && uv run python -m PyInstaller --clean --noconfirm --distpath build/dist --workpath build/build build/fta_editor.spec`;
  about 20 MB on Linux with no AI providers bundled, up to ~79 MB with all
  three. Onefile is deliberately not used — it re-extracts the whole bundle to
  a temp directory on every launch and reliably trips antivirus heuristics.
  See [`build/README.md`](build/README.md) for the full rationale, per-OS
  notes and verification steps. Windows and macOS builds must be produced on
  those platforms; PyInstaller does not cross-compile.

- **`pyproject.toml`** — the source of truth for dependencies, for both apps.
  `[project.optional-dependencies]` splits them by what actually needs them:
  `web` (Flask), `desktop` (Pillow), `excel` (openpyxl, shared), `ai` (OpenAI +
  Anthropic + Gemini SDKs, shared), `test` (pytest) and `build` (PyInstaller);
  `all` bundles everything a user wants, `dev` adds `test` and `build` for
  contributors. Recommended install: `uv sync --extra <name>`, which also
  writes the committed `uv.lock` — exact resolved versions, so a `uv sync` run
  later reproduces the same environment. `pip install -r requirements.txt
  [-r fta_web/requirements.txt]` remains a supported fallback for anyone
  without [uv](https://docs.astral.sh/uv/); `install.py` now detects which
  tool is available and uses it, defaulting to uv.

  `[tool.uv] package = false`: this project is intentionally not built as an
  installable package. `src/` and `fta_web/` are flat module directories with
  no `__init__.py`, and `fta_web/core/` is imported by bare module name via a
  `sys.path` insertion — the layout that keeps it byte-identical to `src/` for
  the divergence pin (see `fta_web/core/DIVERGENCE.md`). Turning either tree
  into a real package would mean restructuring code a hash pin depends on
  staying untouched, so `pyproject.toml` declares dependencies without a
  `[build-system]` table, and `pip install .` is not a supported path — use
  `-r requirements.txt` instead. Both apps still run the ordinary way, e.g.
  `uv run python fta_web/run.py`.

- **`fta_web/runtime_paths.py`** — single place that resolves bundled data
  paths, through `sys._MEIPASS` when frozen and relative to `fta_web/` from a
  checkout.

### Changed

- **Vendored core fork.** `fta_web/core/` holds copies of `AI_agent_handler.py`,
  `FTA_Editor_core.py`, `ai_providers.py` and `json_viewer.py` taken from `src/`
  at commit `e5f655f`. `src/`, `tests/` and `data/` are frozen for the 1.6 line
  and pinned by SHA-256 in `fta_web/core/BASELINE.json`; the fork is the copy
  1.6 is allowed to patch, and `fta_web/tests/test_vendor_integrity.py` fails
  the build if either side changes without the manifest and the divergence
  record being updated together.

  Five defects are fixed in the fork and **not** in `src/`. Full write-ups,
  including the evidence and the behaviour change for each, are in
  [`fta_web/core/DIVERGENCE.md`](fta_web/core/DIVERGENCE.md):

  - **D1** — `AIAgentHandler._get_client()` was dead code that could only ever
    raise `AttributeError` (`__init__` never assigned `self._client`). Deleted;
    the live path, `_get_provider()`, was already correct. No observable change.
  - **D5** — `logicGate: "NOT"` was accepted by validation but computed as
    **OR**: the probability engine branches on `AND` and falls through to the OR
    union formula for everything else, so a NOT gate produced a wrong number
    with no error and nothing in the UI to show the gate had been ignored. `NOT`
    is now rejected at all four acceptance sites with a message naming the
    offending node, and is no longer advertised to the model in the schema or
    the system prompt. Trees relying on the silent OR fallback now surface an
    error, which is the point. The probability engine itself is unchanged.
  - **D7** — the move guard asked its question backwards. It tested whether the
    node being moved was inside the target's subtree, rather than whether the
    new parent was a descendant of the node being moved, so it rejected every
    legal move (promoting a grandchild, reordering under the same parent) and
    permitted the corrupting ones (a node into its own child or grandchild).
    Argument order corrected; the function now returns a real `bool` instead of
    leaking a node dict.
  - **D8** — minified JSON was mangled and then blamed on the file's encoding.
    A double-wrap repair ran unconditionally *before* parsing, and its
    `endswith("}}")` test matches every minified document; stripping the brace
    turned a valid file into invalid JSON and the resulting error was reported
    as "Failed to read file with common encodings". The document is now parsed
    as written first, with the legacy repair as a fallback. Minified files open;
    nothing that loaded before stops loading.
  - **D9** — `AnthropicProvider.get_default_models()` still returned the Claude
    3 family. That list is the *fallback* used when the live model fetch fails,
    which is exactly when a stale entry does the most damage. Refreshed to the
    current family, most-capable first. The model field is an editable combo and
    the live fetch is preferred, so the list ageing again degrades gracefully.

  One reported defect, **D3** (Excel sibling rows overwriting each other), was
  investigated and **not** reproduced — the report misreads a `nonlocal`
  high-water mark as a per-level counter. Verified exhaustively against all 626
  rooted ordered tree shapes of 1–8 nodes. No patch was applied; regression
  tests pin the layout instead.

- `requirements.txt` and `fta_web/requirements.txt` are unchanged in content —
  same packages, same versions — and remain the pip-fallback path. They are
  now secondary to `pyproject.toml`, described above, which is where a new
  dependency gets added first.

- **`setup.py` removed.** It declared `python_requires=">=3.14"` (the rest of
  the project has always targeted 3.10+) and packaged `src/` with
  `find_packages(where="src")`, which finds nothing — `src/` has no
  `__init__.py`, so `pip install .` against it silently produced an empty
  distribution. `pyproject.toml` is the replacement, and is explicit that this
  project is not meant to be built as a package at all (see above) rather than
  quietly failing to be one.

- `README.md` and `QUICKSTART.md` now lead with the web app, and their install
  instructions lead with `uv sync`.

### Deprecated

- Nothing yet. The desktop application (`src/FTA_Editor_UI.py`) is **unchanged,
  supported and retained** in this release. It is expected to be marked
  deprecated after 1.6 has shipped and the web app has been exercised in
  practice; it will be kept available after that, not deleted. Until that
  announcement, both applications are current.

## [1.5.1] - 2025-12-16

### Added

- **Multi-Provider AI Support**: Support for multiple AI platforms
  - New `ai_providers.py` module with abstraction layer for AI providers
  - **Google Gemini** support (free tier + pay-per-use)
  - **Anthropic Claude** support (pay-per-use)
  - **OpenAI** support (existing, enhanced)
  - **GitHub Copilot** support (via OpenAI-compatible API)
  - **Azure OpenAI** support (via OpenAI-compatible API)

- **Provider Implementations**:
  - `OpenAIProvider`: OpenAI and compatible APIs
  - `AnthropicProvider`: Anthropic Claude API
  - `GeminiProvider`: Google Gemini API
  - `AIProviderFactory`: Factory pattern for provider selection

- **Enhanced AI Settings Dialog**:
  - Provider selection dropdown (auto-updates endpoint and models)
  - Dynamic model list based on selected provider
  - Automatic endpoint population per provider

- **Documentation**:
  - `docs/QUICK_AI_SETUP.md`: 5-minute quick start guide
  - `docs/MULTI_PROVIDER_SETUP.md`: Detailed setup and troubleshooting
  - Updated README/Quick Start with new "Analyze FTA" and "Update FTA" flows

- **Full-JSON Update Flow**:
  - New "Update FTA" button generates a complete JSON from the AI and replaces the in-memory tree after validation
  - Validator rejects malformed outputs and reports the exact failing section/node
  - Detailed error logging for invalid JSON (snippet printed to chat and stderr)

- **UI**:
  - Arbitrary tree depth coloring; nested additions render correctly

### Changed

- **Credential Storage**: Enhanced to store provider information
  - Now stores: `api_key`, `api_endpoint`, `model`, `provider`
  - Backward compatible with previous credential format

- **AIAgentHandler**: Refactored to use provider abstraction
  - Provider-agnostic message sending
  - `configure()` accepts provider parameter
  - Added `generate_full_fta_update()` and `verify_updated_fta_json()`

- **requirements.txt**: Added support for all AI providers
  - Added: `anthropic>=0.7.0`
  - Added: `google-generativeai>=0.3.0`
  - Kept: `openai>=1.0.0`

- **README.md**: Updated AI Assistant documentation with provider setup instructions
  - Added Quick Actions description (Analyze vs Update)

---

## [1.5.0] - 2025-12-16

### Added

- **AI Assistant Integration**: Integrated chat interface for AI-powered FTA analysis
  - Chat panel in main UI with message history
  - Quick action buttons: "Analyze FTA", "Suggest Root Causes", "Clear Chat"
  - Threaded API calls for responsive UI during AI processing
  - Color-coded messages (user/AI/system/error)

- **AI Agent Handler** (`src/AI_agent_handler.py`): New module for AI functionality
  - `AICredentialManager`: Secure local storage of API credentials
  - `FTAStructureAnalyzer`: Converts FTA data to AI-readable format
  - `AIProposedChange`: Data class for structured change proposals
  - `AIAgentHandler`: Main handler for OpenAI API interactions
  - System prompt optimized for FTA/ETA analysis

- **Change Confirmation Workflow**: User approval required for AI modifications
  - Confirmation dialog shows all proposed changes
  - Selectable list of changes to apply
  - Detailed view of change data (type, target, description)
  - Warning message before applying changes

- **Secure Credential Storage**: API keys stored outside repository
  - Credentials saved at `~/.fta_editor/ai_credentials.json`
  - Never uploaded or committed to version control
  - Settings dialog with show/hide API key toggle
  - Connection test before saving credentials

- **AI Settings Dialog**: Configure AI credentials in-app
  - API Key input with show/hide toggle
  - Customizable API endpoint (OpenAI, Azure, or compatible)
  - Model selection dropdown (gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo)
  - Test connection functionality
  - Clear credentials option

### Changed

- **UI Layout**: Added AI chat panel on right side of main window
  - Main content area now uses horizontal paned window
  - Chat panel is resizable and collapsible
  - Status indicator shows AI configuration state (●/○)

- **Dependencies**: Updated `requirements.txt`
  - Added `openai>=1.0.0` for AI API integration
  - Removed web application dependencies (Flask, gunicorn, etc.)
  - This version focuses on desktop application only

### Removed

- **Web Application**: Removed Flask-based web interface
  - `web_app/` directory no longer supported in this branch
  - Removed Flask, Flask-Session, gunicorn, requests dependencies
  - Docker deployment configurations removed
  - Render.com deployment no longer supported

### Migration Notes

- Existing FTA JSON files are fully compatible
- No changes to core FTA/ETA functionality
- AI features are optional - application works without API configuration
- Web application users should use v1.4.x branch

## [1.4.2] - 2025-11-25

### Added

- **Japanese Font Support**: Embedded Noto Sans CJK JP font for proper Japanese character rendering
  - Installed `fonts-noto-cjk` package in Docker containers
  - Updated Graphviz font settings to use "Noto Sans CJK JP"
  - Supports Japanese, Chinese, and Korean characters in node names and labels

### Fixed

- **Session State Persistence**: Fixed node replacement and deletion issues on Render.com
  - Replaced in-memory session dictionary with Flask filesystem session storage
  - Added `save_core()` function to persist state after every modification
  - Fixed state consistency across Gunicorn worker processes
  - Resolved issues where nodes were incorrectly replaced or deleted during editing
- **Diagram Auto-Refresh**: Fixed automatic diagram updates in web interface
  - Removed incompatible timestamp query parameter from base64 data URIs
  - Added proper error logging for diagram loading failures
  - Made async refresh calls properly awaited in all tree mutation operations

### Changed

- **Docker Configuration**: Updated all Docker files to version 1.4.2
- **Font System**: Changed from Times New Roman to Noto Sans CJK JP for international character support

## [1.4.1] - 2025-11-21

### Added

- **Web Application**: Flask-based web interface for browser-based FTA/ETA editing
  - Interactive tree editing with live diagram preview
  - Zoom and pan functionality for diagram viewing (mouse wheel + click-drag)
  - Resizable panels (fault tree and node details) with drag handles
  - Real-time diagram rendering without page refresh
  - Session-based multi-user support
  - Export/import functionality (JSON, XML, Excel)
  - Node CRUD operations via REST API
  - Responsive UI with Font Awesome icons
- **Render.com Deployment Support**: Free cloud hosting configuration
  - `render.yaml` for automatic deployment
  - Gunicorn production server setup
  - Environment-based configuration
  - Auto-deploy from GitHub integration
- **Deployment Documentation**: Complete guides for cloud hosting
  - `RENDER_DEPLOYMENT.md`: Quick-start guide for Render.com
  - Enhanced `DEPLOYMENT.md` with Render.com as Option 1
  - Cost comparison and scaling information

### Changed
- **Session Management**: Dedicated session directory to prevent conflicts with system temp files
  - Fixed OSError warnings from cachelib accessing incompatible temp files
  - Isolated Flask sessions in dedicated directory
- **Security**: Environment-based SECRET_KEY for production deployment
- **Requirements**: Added Flask, Flask-Session, and gunicorn dependencies

### Fixed
- **Cache File Warnings**: Eliminated OSError warnings from Arduino IDE and other temp files
- **Production Configuration**: Disabled debug mode and dynamic port binding for cloud deployment

## [1.3.1] - 2025-11-06

### Changed
- **UI Improvements**: Updated `json_viewer.py` and `FTA_Editor_UI.py` with minor visual enhancements
  - Probabilities now display side by side (Gate:  |  P_base: X.X | P_calc: X.X) to save space
  - Added proper cell height to prevent text cutoff in node labels
  - Applied Times New Roman font consistently across the entire diagram
  - Improved node name and probability text visibility
  - Added checkbox to hide nodes with zero probability.
  - Improved Preview UI resolution.
  - Added "New Analysis" button to create new FTA.
  - Fixed graph UI bug. Now the same order is preserved for FTA tree and graph view.

## [1.3.0] - 2025-11-01

### Fixed
- **CRITICAL: AND Gate Probability Calculation**: Fixed incorrect calculation that was multiplying parent's base probability with children probabilities
  - **Before**: `parent_base_prob × ∏(child_probabilities)` - incorrectly included parent's base probability
  - **After**: `∏(child_probabilities)` - correctly calculates as product of children only
  - **Impact**: AND gates now follow standard Fault Tree Analysis principles
  - **Note**: Existing FTA diagrams with AND gates may show different (but correct) probabilities if parent nodes had base probabilities ≠ 1.0
- Updated test suite to reflect correct AND gate behavior (all 13 tests pass)
- Updated documentation to clarify that parent base probability is ignored when logic gates are applied with children

### Changed
- `_recalculate_fta_probabilities()` method now correctly ignores parent base probability for AND gates
- Test expectations updated in `test_probability_calculation.py`
- Documentation updated in `PROBABILITY_VALIDATION.md`

## [1.2.0] - 2025-10-31

### Added
- **ETA (Event Tree Analysis) Mode**: Top-down probability calculation for accident sequence analysis
- **Metadata Support**: Title, date, and mode fields saved with analyses
- **Top Bar UI**: Mode selector dropdown, title field, and date field
- **Hierarchical Excel Export**: Tree structure exported with nested columns
- **Dynamic Tree Labels**: Changes between "Fault Tree" and "Event Tree" based on mode
- **Comprehensive Documentation**: User guide, API reference, ETA documentation
- **Docker Support**: Dockerfile and docker-compose.yml for containerization
- **Test Suite**: Complete test coverage for ETA mode and core functionality

### Changed
- **JSON Format**: Now includes metadata (backward compatible with legacy format)
- **Excel Export**: Hierarchical columns instead of flat rows
- **Calculation Engine**: Supports both FTA (bottom-up) and ETA (top-down) modes

### Fixed
- Probability calculation edge cases
- Circular reference handling
- Zero probability node detection

## [1.1.1] - 2025-10-30

### Added
- Excel export with hierarchical column structure
- Color-coding by depth level in Excel
- Auto-adjusted column widths
- Wrapped text for better readability

### Changed
- Excel export format from flat to hierarchical

## [1.1.0] - 2025-10-29

### Added
- Code refactoring: Split into UI and Core modules
- `FTA_Editor_core.py`: Core business logic
- `FTA_Editor_UI.py`: User interface layer
- Comprehensive test suite (19 tests)
- API for programmatic usage

### Changed
- Project structure: Separation of concerns
- Improved maintainability and testability

### Deprecated
- None (original FTA_Editor.py preserved for backward compatibility)

## [1.0.0] - 2025-10-01

### Added
- Initial FTA Editor release
- Fault tree creation and editing
- Probability calculations with AND/OR gates
- Node linking system
- JSON export/import
- XML export
- Graphviz diagram visualization
- Live preview with zoom/pan

---

## Release Notes

### Version 2.0.0 - Web Application and Cloud Deployment

This major release introduces a browser-based web application alongside the existing desktop GUI, plus free cloud hosting support.

**Key Highlights**:
- Full-featured web interface accessible from any browser
- Interactive diagram viewing with zoom/pan controls
- Resizable UI panels for customized workspace
- One-click deployment to Render.com (free tier)
- Multi-user session support
- REST API for programmatic access
- No installation required for web version

**Web Application Features**:
- Interactive tree editing with real-time updates
- Live diagram preview with mouse wheel zoom and drag-to-pan
- Resizable fault tree and node details panels
- Export to JSON, XML, and Excel formats
- Import existing FTA/ETA analyses
- Session-based data isolation for multiple users

**Deployment Options**:
- **Web (Render.com)**: Free cloud hosting with auto-deploy from GitHub
- **Local Web**: Run Flask app locally at http://localhost:5000
- **Desktop GUI**: Traditional tkinter application (unchanged)
- **Docker**: Containerized deployment for both GUI and web app

**Quick Start (Web)**:
```bash
pip install -r requirements.txt
python web_app/app.py
# Open http://localhost:5000 in browser
```

**Deploy to Render.com**:
```bash
git push origin main
# Connect repository at render.com
# Auto-deploys with render.yaml configuration
```

**Technical Improvements**:
- Fixed session cache conflicts with system temp files
- Environment-based configuration for production
- Gunicorn production server integration
- Dedicated session directory to prevent cache errors

**Migration Note**:
- Desktop GUI remains unchanged and fully functional
- Web application is an additional interface option
- All existing JSON files work with both interfaces
- No breaking changes to existing workflows

See [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md) for cloud hosting guide.

### Version 1.3.1 - UI Improvements and Bug Fixes

This major release adds Event Tree Analysis (ETA) capability alongside the existing Fault Tree Analysis (FTA), making the tool suitable for both reliability analysis and accident sequence modeling.

**Key Highlights**:
- Dual-mode analysis (FTA/ETA) with easy switching
- Complete metadata support for better documentation
- Improved Excel export with visual hierarchy
- Production-ready with Docker support
- Comprehensive documentation for public use

**Migration Guide**:
- Legacy JSON files load automatically (default to FTA mode)
- No breaking changes to existing workflows
- New JSON format is recommended for new projects

**Docker Deployment**:
```bash
docker-compose up
```

**Programmatic Usage**:
```python
from src.FTA_Editor_core import FTACore
core = FTACore()
core.set_metadata(mode="ETA", title="Analysis")
```

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for complete documentation.
