# Specification: FTA Editor (division project `fta-editor`)

- Version: **v0.1 draft**, 2026-10-22. Not approved. Approval by the CEO freezes the UI, FN and PERF requirements.
- Brief (CHARTER.md, verbatim): **"Release 1.8.1, then roadmap"**: "Ship the merged fixes as 1.8.1, then plan the next features from docs/ROADMAP_MECHANICAL_ENGINEERS.md".
- Sources: `.division/research/R1-release-1.8.1.md`, `.division/research/R2-roadmap.md`, `docs/ROADMAP_MECHANICAL_ENGINEERS.md` (cited as "roadmap x.y"), `CHANGELOG.md` [Unreleased] and [1.8.0], `.division/DOMAIN.md`.

## 1. Summary

1. Phase 1: release what is already on `main` as **1.8.1** (recovery copy, Change folder, port 8765, `force`, server-side Stop), with notes, SHA-256 and a checked exe.
2. Phase 2, in order: **F2** common-cause failure groups (beta factor, must; alpha factor, should), **F3** grid of basic events with paste from Excel, **F4** what-if sliders, **F5** semantics help and faster editing.
3. Without CCF groups every result stays exactly as today; the pinned core and `desktop/` are not touched.
4. Every CCF formula cites its source; tests reproduce a hand calculation and at least one published example. No claim of compliance with any standard.
5. Your decisions: approve this spec, run a 3-step manual check of the 1.8.1 exe (about 15 minutes, by `.bat`), release 1.8.1, and merge each PR.

## 2. Goals and success measures

| # | Goal | Measure (done when) |
|---|---|---|
| G1 | 1.8.1 is releasable with evidence | The release commit has: pytest 0 failures, GUI suite against the exe 0 FAIL, b2b against the exe 0 mismatches, manual check 3 of 3 passed, CI green. Evidence files under `.division/artifacts/release-1.8.1/`. |
| G2 | Redundant trains are no longer shown as more reliable than they are | A tree with a beta-factor group reproduces the hand check (1.0081e-4) and one published worked example to the tolerance stated in FN-19; the CCF event appears in cut sets, importance, Monte Carlo, report and CLI. |
| G3 | Nothing changes for users who do not use CCF | For every example file and reference model, CLI JSON output is byte-identical to 1.8.1; `test_vendor_integrity.py` passes; `git diff main -- fta_web/core desktop` is empty. |
| G4 | Data entry from spreadsheets | 500 rows pasted from Excel are applied in at most 2 s as one undo step, with every refused row listed. |
| G5 | What-if never changes the file | After any slider use and Reset all, Save writes a file byte-identical to the one saved before. |

## 3. Users and use cases

Users:
- **Reliability and safety engineers** (mechanical, machinery, process) running the Windows exe or `uv run`, building fault trees of up to a few hundred events (roadmap 3.2).
- **Reviewers** who read the DOCX report.
- **Batch users** of the CLI (`fta_editor quantify|cutsets|importance|mc|validate|report`).
- **Katey (CEO)**, who releases, runs the manual check and merges.

Use cases:
- **U1** A user downloads 1.8.1, checks the SHA-256, and finds that their language, theme and diagram style survive a restart, and that unsaved work survives a crash.
- **U2** An engineer models a 1oo2 pump train, groups the two pump failures in a CCF group with β = 0.1 from a cited data source, and sees the CCF cut set dominate the top event (roadmap 1.5).
- **U3** An engineer copies 200 failure rates from an FMEA spreadsheet and pastes them into the grid in one step (roadmap 3.3).
- **U4** A designer asks "what if this valve fails ten times as often?" and sees the top event move, without changing the file (roadmap 1.7).
- **U5** A new user reads in the app how links combine with gates, and builds a tree with the keyboard (roadmap 3.6, 3.7).

## 4. Requirements

Format: **ID** statement | why | test: how it is checked | priority.
"Hand calculation" marks a value derived by the division, not taken from a publication.
Measurement conditions for every PERF item, unless stated otherwise: Katey's Windows PC, the dev server started with `uv run --frozen`, Chromium through the GUI suite harness, median of 5 runs, timings written to `.division/artifacts/`.

### 4.1 Phase 1: release 1.8.1 (F1)

- **FN-1** The version reads 1.8.1 in `pyproject.toml`, `uv.lock`, `report_docx.TOOL_VERSION`, the README badge, QUICKSTART (with the release date), `.github/copilot-instructions.md` and the `--version` example in `build/README.md` | one version everywhere a user or a report sees it (R1) | test: a search for `1.8.0` in these seven files finds only history entries; reviewer lists each hit | must
- **FN-2** The built exe prints `FTA Editor 1.8.1` for `--version` | proves the exe is the release build | test: run `fta_editor.exe --version` on the built exe; output saved to artifacts | must
- **FN-3** `CHANGELOG.md` has `## [1.8.1] - <release date>` holding today's [Unreleased] text, with an empty `## [Unreleased]` above it | Keep a Changelog convention used by the repo | test: reviewer reads the diff; the [1.8.1] body equals the old [Unreleased] body | must
- **FN-4** `fta_web/tests/test_known_issues_1_8.py` (line 1883, which slices from `## [Unreleased]` to `## [1.8.0]`) is updated in the same commit as FN-3 to read the [1.8.1] section | otherwise the suite breaks on the version commit (R1 trap) | test: `uv run --frozen pytest` 0 failures on that commit; `git show --stat` of the commit lists both files | must
- **FN-5** The release notes name the five behaviour changes: port 8765 with fallback and `--port 0`; `force` on `/api/file/open`, `/api/examples/open`, `/api/import/json` (`409 UNSAVED_CHANGES`); the recovery folder `C:\Users\<you>\.fta_editor\recovery\`; Change folder…; Stop that frees the editor (`/api/ai/cancel`) | API clients and users must learn of changed behaviour (R1) | test: reviewer checklist of 5 items against the notes text | must
- **FN-6** The release notes carry a new Known issues list: 1.8.0 items fixed in 1.8.1 removed, "No autosave" reworded to describe the recovery copy, and new items added for a custom `--root` that contains the home folder (recovery-folder guard) and two copies started at once racing for port 8765 | users see current limits, not 1.8.0's (R1 risks) | test: reviewer compares the list with the 1.8.0 notes and R1 | must
- **FN-7** The release notes state the SHA-256 of the release zip | users can verify the download | test: `Get-FileHash -Algorithm SHA256` on the uploaded asset equals the stated value | must
- **FN-8** The release notes have a "Not tested" list: the native folder dialog only by the manual check (FN-12), Ctrl-C cleanup, Firefox and WebKit only headless, the AI assistant only with a mock provider | honest scope of evidence (R1 "never verified") | test: reviewer checklist of 4 items | must
- **FN-9** The release notes have a short Japanese section with the same five changes and the Known issues | en and ja for user-visible text (CHARTER) | test: reviewer reads it; the five items are present | should
- **FN-10** The exe is built with PyInstaller (CPython 3.14) in a folder outside Dropbox, from the release commit, and launched once before testing | Dropbox locks break the build (machine memory); the exe must match the commit | test: build log records the build path (not under `K:\Dropbox`) and `git rev-parse HEAD` | must
- **FN-11** The full GUI suite, all 18 sections, runs against the built exe (`FTA_GUI_EXE=<path>`) with 0 FAIL | the exe is what users run (CHARTER release rule) | test: `node run.mjs` with `FTA_GUI_EXE`; summary table saved to artifacts shows FAIL = 0 | must
- **FN-12** The b2b suite runs against the new exe with `FTA_B2B_EXE` and `FTA_B2B_EXE_COMMIT` set explicitly to the new exe and the release commit, with 0 mismatches | the defaults point at 1.7.0 (`544492b`, `fta_build_170`) and would test the wrong build (R1) | test: `run_b2b.py` log shows both variables and 0 mismatches | must
- **FN-13** Manual check 1, by a person on the exe: Change folder… opens the Windows folder chooser; picking a folder with a Japanese name makes the file dialog list it; a file saved there reopens; a second Change folder… ended with Cancel leaves the allowed folder unchanged | the native dialog was never opened by a person (STATUS top risk) | test: the person records pass or fail per step in `manual-check-1.8.1.txt` | must
- **FN-14** Manual check 2: with unsaved edits, the exe is killed (`taskkill /F /IM fta_editor.exe`), restarted, shows **Unsaved work found**, and Restore brings back the edits as an untitled, modified analysis | recovery after a real kill was never verified (R1) | test: as FN-13 | must
- **FN-15** Manual check 3: language, theme, significant figures and diagram style set in the exe are kept across two restarts | the port-8765 fix exists for this (CHANGELOG) | test: as FN-13 | must
- **FN-16** The manual check is delivered as `manual-check-1.8.1.bat` that starts the exe, prints each step in English, and writes the answers to `manual-check-1.8.1.txt` | Katey runs Windows tasks from a `.bat` (global rule); see OQ-2 | test: reviewer runs the `.bat` once on a dev build | should
- **FN-17** CI (`tests.yml`, `extended.yml`) is green on the head commit of the release PR | the merge gate | test: GitHub checks page | must
- **PERF-1** Moving and deleting 4,800 nodes of a 4,860-node tree each take under 1.0 s | the CHANGELOG claims "well under a second"; the CI bound is 3 s | test: `test_3_a_batch_of_4800_nodes_moves_and_deletes_within_the_bound` printout on Katey's PC, saved to artifacts | should

### 4.2 Phase 2: common-cause failures, beta factor (F2)

- **UI-1** In Advanced mode a **CCF groups** tab lists every group with name, model, parameter value, member names, parameter source and status (Applied, or Not applied: <reason>) | the user sees what is modelled and what is ignored (roadmap 1.5) | test: GUI suite section `ccf` checks the columns on a 2-group file | must
- **UI-2** The tab can create a group from the basic events selected in the tree, and edit a group's name, β, source and members, and delete it; each action is one undo step | groups must be editable without editing JSON | test: GUI suite creates, edits, deletes, and undoes each action | must
- **UI-3** The β field shows "β (dimensionless, 0 to 1)" and an invalid entry shows its message next to the field | units next to every value; errors next to the field (DOMAIN) | test: GUI suite enters 1.5 and checks the message location and text in en and ja | must
- **UI-4** While at least one group is applied, the headline reads as MCUB and says "includes CCF (n groups)" | the user must know the number is not the plain tree walk | test: GUI suite reads the headline on a 1-group file and on a no-group file | must
- **UI-5** The cut-set table shows a CCF event as "CCF: <group name>"; clicking it highlights every member in the tree and diagram | the dominant cut set is often the CCF event (roadmap 1.5) | test: GUI suite clicks the row and counts highlighted members | should
- **UI-6** Each member shows a CCF badge with its group name in its tree row and diagram box | the grouping is visible where the tree is edited | test: GUI suite screenshot looked at by the reviewer; DOM check for the badge | should
- **UI-7** The CCF tab shows an Assumptions box: the model, its formula, its source with page, "a member's probability is its total failure probability Q_t", "beta factor: the common cause fails all members together", and the rare-event approximation used | results state their assumptions (DOMAIN) | test: reviewer reads the box in en and ja against section 7.3 | must
- **FN-18** CCF groups are saved in the file under `analysis.ccfGroups` (section 7.1); save then load gives an identical object | groups are part of the analysis | test: pytest round trip on a 3-group file compares the JSON objects | must
- **FN-19** Before cut-set generation, each member's variable in the compiled `Structure` is replaced by OR(independent part with q = (1 − β)·Q_t, one shared CCF event with q = β·Q_t) per group (formula and source in 7.3) | roadmap 1.5; a pre-pass reaches every analysis without editing the core (Director) | test: (a) hand calculation: Q_t = 1e-3, β = 0.1, two members under AND gives cut sets {A_ind, B_ind} = 8.1e-7 and {CCF} = 1e-4, rare-event sum 1.0081e-4 (relative tolerance 1e-12), MCUB 1.00809919e-4 (relative tolerance 1e-9), shown as 1.0081e-4 at 5 significant figures; (b) the published worked example chosen in OQ-5, to the tolerance implied by the digits the source prints | must
- **FN-20** A member reached through links or transfers gets the same CCF event at every reference | the pre-pass acts on the compiled variable, so repeated references must not create several CCF events | test: pytest with a member linked under two gates; cut sets contain exactly one CCF event id | must
- **FN-21** While at least one group is applied, `headlineMethod` is `mcub` and the headline includes the CCF events | the CCF event is shared, so the plain tree walk would be wrong | test: pytest on the FN-19 tree asserts method and value | must
- **FN-22** Cut sets list each CCF event with id `ccf:<groupId>` and its probability | the primary FTA output must show the CCF contribution | test: pytest on the FN-19 tree | must
- **FN-23** FV, Birnbaum, RAW and RRW are computed on the expanded structure, and the CCF event has its own row | importance must rank the CCF event (roadmap 1.2 with 1.5) | test: pytest on the FN-19 tree; FV of the CCF event = 1e-4 / 1.00809919e-4 within relative 1e-9 (hand calculation) | must
- **FN-24** Monte Carlo samples the expanded structure, with the sampling rule decided in OQ-10 | uncertainty bounds must include CCF | test: pytest with a fixed seed and trial count; the mean is within 3 standard errors of the analytic MCUB for a tree with no uncertainty on β | must
- **FN-25** The DOCX report has a CCF section: each group's name, model, parameters, source, members, the formulas with their sources, and the CCF events in the cut-set and importance tables | the report is the deliverable (roadmap 2.5) | test: pytest reads the DOCX text of a 1-group file and finds each item | must
- **FN-26** The CLI commands `quantify`, `cutsets`, `importance` and `mc` with `--json` give the same numbers as the API for a file with groups | batch users get the same results (roadmap 2.6) | test: pytest compares CLI and API JSON on the FN-19 file | should
- **FN-27** The Excel export lists CCF groups on the Analysis sheet and marks members on the Events sheet | spreadsheet users see the grouping | test: pytest opens the workbook and reads the cells | could
- **FN-28** A tree without CCF groups gives results identical to 1.8.1 | engineers act on these numbers; nothing may move silently (Director) | test: for every file in `fta_web/examples/` and every reference model in `fta_web/tests/`, CLI `quantify`, `cutsets`, `importance`, `validate` with `--json`, and `mc` with a fixed seed and trial count, are byte-identical to the output of the 1.8.1 release commit; b2b suite 0 mismatches | must
- **FN-29** No file under `fta_web/core/` or `desktop/` changes, and the core hash check stays green | hash-pinned core and frozen desktop (CHARTER) | test: `git diff main -- fta_web/core desktop` is empty; `test_vendor_integrity.py` passes | must
- **FN-30** β = 0 gives the same top event (MCUB and rare-event) as the same tree without the group | edge case: no common cause | test: pytest, values equal to the last bit; cut sets equal after dropping zero-probability CCF sets | should
- **FN-31** β = 1 gives independent parts of probability 0 | edge case: only common cause | test: pytest, Q_t = 1e-3, two members under AND, top = 1e-3 (hand calculation, relative 1e-12) | should
- **FN-32** A β that is not a finite number in [0, 1] (including NaN, inf, `1e-400`, text) is refused with `400` and a message naming the field and the range; `-0` is read as 0 | inputs validated with helpful messages (DOMAIN) | test: pytest over these inputs | must
- **FN-33** A member that is not a basic event (gate, house event, transfer, missing id) raises lint error `CCF_MEMBER_NOT_BASIC` | the model applies to component failures only | test: pytest per kind | must
- **FN-34** Members whose probabilities Q_t differ by more than a relative 1e-6 raise lint error `CCF_UNEQUAL_Q` | the beta and alpha models assume identical components (R2) | test: pytest with 1e-3 and 1.1e-3; and with equal λ and T entered in different units (no error) | must
- **FN-35** A group with fewer than 2 members raises lint error `CCF_TOO_FEW_MEMBERS` | a common cause needs two components | test: pytest | must
- **FN-36** An event in two groups raises lint error `CCF_MEMBER_IN_TWO_GROUPS` | the expansion is defined for one group per event | test: pytest | must
- **FN-37** A group with any lint error is not applied, and this is said in the headline note, in the tab status and in the Validation tab with click-to-jump | never silent (DOMAIN) | test: pytest asserts the note; GUI suite clicks the issue | must
- **FN-38** Deleting a member node removes it from its group in the same undo step; undo restores both | no dangling members | test: pytest delete then undo | should
- **FN-39** In ETA mode the CCF tab is greyed with the reason in its tooltip, and groups stay in the file | matches how 1.8.0 greys the other analysis tabs | test: GUI suite | should
- **FN-40** Every CCF formula in code cites its source and page in the docstring, and `docs/CCF.md` holds the formulas, sources and the hand calculations | DOMAIN evidence rule | test: analyst review before merge | must
- **PERF-2** With 10 beta groups of 3 members each on the 300-node tree built by GUI section `big`, the headline after an edit takes at most 2.0 s and at most 1.5 times the same tree without groups | the headline runs after every edit | test: pytest timing, both numbers saved to artifacts | must
- **PERF-3** On the same tree with 10 groups, the GUI `big` budgets still hold: click to Details under 500 ms, the Add dialog under 3 s | no slowdown in normal editing | test: GUI section `big` variant with groups, 0 FAIL | must
- **PERF-4** Monte Carlo with a fixed 10,000 trials on the same tree with 10 groups takes at most 1.5 times the time without groups | the run is time-capped, so a slowdown shows as fewer trials | test: pytest timing saved to artifacts | should

### 4.3 Phase 2: alpha factor for groups of 2 to 4 (F2A)

- **UI-8** For the alpha model the group editor shows fields α1 … αm (dimensionless, 0 to 1) for m members and a testing scheme selector (staggered, non-staggered) | alpha needs one parameter per failure multiplicity | test: GUI suite on a 3-member group | should
- **FN-41** The alpha model with non-staggered testing uses Q_k = k / C(m−1, k−1) · (α_k / α_t) · Q_t with α_t = Σ k·α_k, and one CCF event per subset of size k ≥ 2 | roadmap 1.5 "MGL/α-factor" | test: property test (hypothesis) that Σ_k C(m−1, k−1)·Q_k = Q_t within relative 1e-12; published example per OQ-5 | should
- **FN-42** The alpha model with staggered testing uses Q_k = α_k / C(m−1, k−1) · Q_t | same | test: as FN-41 for the staggered form | should
- **FN-43** An alpha group outside 2 to 4 members raises lint error `CCF_ALPHA_SIZE` | 2^m − 1 events per group stay at most 15 | test: pytest with 5 members | should
- **FN-44** α values that are not finite in [0, 1] or whose sum differs from 1 by more than 1e-9 raise lint error `CCF_ALPHA_SUM` | the α_k are fractions of failures | test: pytest | should
- **FN-45** For m = 2, the staggered alpha model with α1 = 1 − β and α2 = β gives the same cut-set probabilities as the beta model with β (hand derivation from FN-42: Q_1 = α1·Q_t, Q_2 = α2·Q_t) | cross-check between the two models | test: pytest, equal within relative 1e-12 for β in {0, 0.05, 0.1, 1} | should
- **PERF-5** With 5 alpha groups of 4 members on the 300-node `big` tree, the headline takes at most 3.0 s | 15 events per group multiply cut sets | test: pytest timing saved to artifacts | should

### 4.4 Phase 2: grid of basic events with paste from Excel (F3)

- **UI-9** A **Grid** tab shows one row per basic event with columns id (read-only), name, model, λ, T, τ, μ, q, source, tags; every numeric column header names its unit | engineers enter and check data in tables (roadmap 3.3) | test: GUI suite reads the headers in en and ja | should
- **UI-10** The grid sorts by any column and filters by text | finding one row in 500 | test: GUI suite | should
- **UI-11** q is read-only when the model is not fixed and is shown with the significant-figures preference | q is derived from the model (roadmap 1.3) | test: GUI suite | should
- **UI-12** After a paste a summary beside the grid says how many rows were applied and lists each refused row with row number, column and message | bad rows are reported (R2) | test: GUI suite pastes 3 good and 2 bad rows | should
- **UI-13** Selecting a grid row selects the node in the tree and the diagram | the grid and the tree stay linked | test: GUI suite | could
- **FN-46** A cell edit goes through the same validator as the details panel (`node_schema.validate_quant`) and is one undo step | one validator (R2) | test: pytest sends the same bad values through both paths and compares the errors | should
- **FN-47** Paste takes tab-separated text from the clipboard and fills cells from the selected cell rightwards and downwards in the visible column order | how Excel copies | test: GUI suite pastes a 3 × 3 block | should
- **FN-48** A whole paste is one undo step | undo must not need 500 steps (R2) | test: GUI suite pastes 50 rows, one Ctrl+Z restores all | should
- **FN-49** A row with any invalid cell is not applied at all; the valid rows are | a half-applied row would mix old and new data | test: pytest | should
- **FN-50** Cells pasted into read-only columns or beyond the last row are reported and nothing is created | the tree is for structure (roadmap 3.3) | test: pytest | should
- **FN-51** λ is read in the unit shown in its header (/h, /y or FIT) and stored per hour | units explicit (DOMAIN) | test: pytest: 1 FIT is stored as 1e-9 /h; 8.76 /y as 1e-3 /h (8,760 h per year) | should
- **FN-52** A number with a decimal comma (`1,5E-06`) is refused with a message saying to use a decimal point | no guessing of locale | test: pytest | should
- **PERF-6** Pasting 500 rows × 3 columns into a tree with 500 basic events is applied and redrawn in at most 2.0 s | G4 | test: GUI suite timing | should
- **PERF-7** The grid opens with 500 rows in at most 1.0 s | G4 | test: GUI suite timing | should

### 4.5 Phase 2: what-if sliders (F4)

- **UI-14** A **What-if** tab lets the user pick basic events and set a factor for each with a slider from 1/100 to 100 on a log scale, showing nominal q, what-if q, baseline top event, what-if top event and their ratio | roadmap 1.7 "slider or ±factor with the top event updating live" | test: GUI suite sets factor 10 on one event | should
- **UI-15** While any factor is not 1, a banner says "What-if values, not saved", with Reset per event and Reset all | the user must not mistake what-if numbers for the analysis | test: GUI suite | should
- **FN-53** What-if works on a copy: the document, its undo history and its modified flag are unchanged | R2 "on a copy" | test: pytest: Save before and after slider use and Reset all writes byte-identical files; `canUndo` and the modified flag unchanged | should
- **FN-54** After Reset all the what-if top event equals the headline to the last bit | Reset must truly reset | test: pytest | should
- **FN-55** A factor that would push q above 1 clamps q to 1 and says so beside the value | probabilities stay in [0, 1] | test: pytest with q = 0.5, factor 10 | should
- **FN-56** The what-if top event uses the same method as the headline, including CCF groups | the comparison must be like for like | test: pytest on the FN-19 tree | should
- **FN-57** A factor on a CCF member scales Q_t of every member of its group | otherwise the group fails `CCF_UNEQUAL_Q` | test: pytest | should
- **FN-58** New, Load, a mode switch or any edit to the document resets all factors to 1 | the baseline changed | test: pytest | should
- **PERF-8** On the 300-node `big` tree the what-if top event is shown within 300 ms of the last slider movement | "updating live" | test: GUI suite timing | should

### 4.6 Phase 2: semantics help and editing (F5)

- **UI-16** A help button beside the gate selector explains in en and ja how a node combines its children, AND-links and OR-links (in a fixed order, not as gate inputs), and that a parent's own probability is ignored once it has children | every reviewer re-derived this (roadmap 3.7) | test: reviewer compares the text with `docs/USER_GUIDE.md` and `DIVERGENCE.md` | could
- **UI-17** A help button beside the links editor gives the same explanation for links, and in ETA mode how branch probabilities propagate | same | test: as UI-16 | could
- **FN-59** With focus on a tree row, Tab adds a child and starts its rename | roadmap 3.6; mapping per OQ-12 | test: GUI suite | could
- **FN-60** With focus on a tree row, Shift-Tab adds a sibling and starts its rename | roadmap 3.6; mapping per OQ-12 | test: GUI suite | could
- **FN-61** Tab and Shift-Tab anywhere else (fields, dialogs, buttons) keep the browser's focus movement | keyboard users must still be able to leave the tree | test: GUI suite tabs through the details panel | could
- **FN-62** **Duplicate subtree** copies the selected node and its descendants as the next sibling with new ids, maps links inside the subtree to the copies and keeps links to nodes outside; one undo step | roadmap 3.6 | test: pytest on a subtree with an inner and an outer link | could
- **FN-63** Duplicated basic events are not added to the originals' CCF groups, and a notice says so | membership is a modelling decision | test: pytest | could

### 4.7 All phases

- **UI-18** Every new user-visible text has an English and a Japanese string | CHARTER | test: `test_catalog_parity.py` and `test_i18n.py` pass with the new keys | must
- **FN-64** No new text claims compliance with a standard; standards appear only as sources | compliance claims are CEO-only (DOMAIN) | test: a search of new strings for "compl", "conform", "certif", "準拠", "適合" finds none outside source citations; reviewer confirms | must
- **FN-65** No test calls a live AI provider | CHARTER | test: CI runs without any provider key | must

## 5. Non-goals

- **NOT gate** (roadmap 1.4): rejected by DIVERGENCE D5; it makes the tree non-coherent and changes the meaning of cut sets and importance (OQ-3).
- **Component library** (2.2): needs cited reliability data the division cannot verify; deferred (R2).
- **Revisions, review comments, diff and scenario compare** (2.4, second half of 1.7): needs a revision model in the file format; deferred (R2).
- **Large-tree navigation** (3.2): the 300-node budgets hold today; a separate UI effort; deferred.
- **ETA normalisation, consequences, bow-tie** (1.8): the ETA walk is in the pinned core, so this is a new module and new semantics (M to L); next round.
- **PDF report and diagram paging** (2.5): needs a PDF library, a licence choice that is the CEO's; DOCX stays.
- **AI items** (section 4): testing them needs a live provider with the CEO's key and approval (OQ-6).
- **Dormant-with-coverage model, "cycles" unit** (1.3), **BDD backend** (1.1), copy and paste between files and inline editing in the diagram (rest of 3.6).
- **Writing what-if values into the document.**
- **Back-porting to `desktop/`**, a multi-user server, and any claim of compliance with a standard.

## 6. Constraints

- `fta_web/core/*.py` is hash-pinned (`fta_web/core/BASELINE.json`, `DIVERGENCE.md`) and `desktop/` is frozen; new behaviour goes in `fta_web/` beside the core.
- Server stays loopback-only with token, Origin and Host checks; the sandbox root stays a security boundary (Change folder only by the native chooser).
- Existing file keys and API responses for trees without CCF groups do not change; `analysis.ccfGroups` is optional.
- 1.8.1 adds no feature. A defect found by the release checks is fixed only if it is in the merged 1.8.1 changes, and is named in the CHANGELOG; anything else becomes a Known issue (OQ-14).
- Windows PC in Dropbox: `uv run --frozen` always; build the exe outside Dropbox; Dropbox can lock git files.
- No new runtime dependency without the CEO (licences are CEO-only).
- No live AI call in tests.
- Work on branches, PR into `division/fta-editor/integration`; the CEO merges into `main` and releases. Budget cap $300.

## 7. Interfaces and data

### 7.1 File format addition (JSON analysis file)

```json
"analysis": {
  "ccfGroups": [
    {"id": "g1", "name": "Feed pumps", "model": "beta", "beta": 0.1,
     "alpha": null, "testing": null,
     "members": ["n12", "n13"], "source": "free text, e.g. data handbook and page"}
  ]
}
```
`model` is `beta` or `alpha`; for `alpha`, `alpha` is a list α1 … αm and `testing` is `staggered` or `nonStaggered`. Older versions and `desktop/` ignore the key or drop it on save (risk K4).

### 7.2 Units

| Quantity | Unit | Range |
|---|---|---|
| q, Q_t, Q_k | dimensionless probability | [0, 1] |
| β, α_k | dimensionless fraction | [0, 1]; Σ α_k = 1 |
| λ | stored per hour; shown /h, /y (8,760 h) or FIT (1e-9 /h) | ≥ 0 |
| T, τ | hours; shown in h, d or y | > 0 |

### 7.3 Formulas and sources

Page numbers below are **to be verified by the analyst before freeze**; R2 could not open the NRC PDFs.

| Formula | Source |
|---|---|
| Beta factor: Q_ind = (1 − β)·Q_t, Q_CCF = β·Q_t; the CCF event fails all m members | NUREG/CR-4780 Vol. 1 (Mosleh et al.), beta-factor model, page to be verified; NUREG/CR-5485, page to be verified |
| Alpha factor, non-staggered: Q_k = k / C(m−1, k−1) · (α_k / α_t) · Q_t, α_t = Σ k·α_k | NUREG/CR-5485 (Mosleh, Rasmuson, Marshall), page to be verified |
| Alpha factor, staggered: Q_k = α_k / C(m−1, k−1) · Q_t | NUREG/CR-5485, page to be verified |
| Hand check: Q_t = 1e-3, β = 0.1, two members under AND: 8.1e-7 + 1e-4 = 1.0081e-4 (rare event), MCUB 1.00809919e-4 | **hand calculation**, derivation in `docs/CCF.md` |
| Published worked example | to be chosen (OQ-5) |

### 7.4 API (proposed; names may change in design, behaviour may not)

- `GET /api/ccf/groups`, `POST /api/ccf/groups`, `PATCH /api/ccf/groups/<id>`, `DELETE /api/ccf/groups/<id>`: each change is one undo step.
- Existing analysis responses gain a `ccf` block (groups applied, groups not applied with reason) and CCF event ids `ccf:<groupId>` (beta) or `ccf:<groupId>:<memberId>+<memberId>…` (alpha).
- `POST /api/grid/paste` `{rows: [...], startRow, startColumn}` returns `{applied, refused: [{row, column, message}]}`.
- `POST /api/whatif` `{factors: {nodeId: factor}}` returns `{baseline, whatIf, ratio, clamped}`; it never changes state.
- New lint codes: `CCF_MEMBER_NOT_BASIC`, `CCF_UNEQUAL_Q`, `CCF_TOO_FEW_MEMBERS`, `CCF_MEMBER_IN_TWO_GROUPS`, `CCF_ALPHA_SIZE`, `CCF_ALPHA_SUM`, each with en and ja text.

### 7.5 Release artifacts

`fta_editor-1.8.1-windows.zip` with its SHA-256; `.division/artifacts/release-1.8.1/` holds the GUI summary, the b2b log, the build log, `--version` output and `manual-check-1.8.1.txt`.

## 8. Risks and mitigations

| # | Risk | Mitigation |
|---|---|---|
| K1 | CCF page numbers and the published example cannot be verified (NRC fetch failed) | Analyst verifies before freeze; if no published example can be read, the CEO decides (OQ-5) |
| K2 | The pre-pass changes results of trees without groups | FN-28 byte-identical outputs over all examples and reference models, plus b2b |
| K3 | A change slips into the pinned core | FN-29, `test_vendor_integrity.py` in CI |
| K4 | A file with groups opened in 1.8.x or `desktop/` loses its groups on save | Test it, and say it in the release notes of the CCF release |
| K5 | Gate values below the top are shown without CCF and misread | OQ-11 |
| K6 | The Monte Carlo sampling rule for groups is a modelling choice | OQ-10, analyst review |
| K7 | Recovery-folder guard with a custom `--root` containing home; two copies racing for 8765 | Known issues in 1.8.1 notes (FN-6) |
| K8 | Five new endpoints in a patch release | OQ-1 |
| K9 | Dropbox locks files during the build | Build outside Dropbox (FN-10) |
| K10 | The manual check waits on Katey while travelling | `.bat` of about 15 minutes (FN-16); the release is a CEO gate anyway |
| K11 | Tab in the tree traps keyboard users | FN-61 |
| K12 | Budget ($300) runs out before F5 | Features ship in order as separate PRs; F5 is could |

## 9. Open questions

| # | Question | Recommended answer |
|---|---|---|
| OQ-1 | 1.8.1 or 1.9.0? Five new endpoints suggest a minor version by semver | **1.8.1**, the CEO's wording; the notes list the API change |
| OQ-2 | Who runs the manual check (FN-13 to FN-15)? | **Katey**, with `manual-check-1.8.1.bat` |
| OQ-3 | Add a NOT gate? | **No**, keep DIVERGENCE D5 |
| OQ-4 | Alpha factor in this project or later? | **In this project as should**, after beta is merged |
| OQ-5 | Which published CCF example becomes the acceptance test of FN-19 (and FN-41)? | The **NUREG/CR-5485 two-train example** if the analyst can read it; otherwise the CEO picks between another published case and hand calculations only |
| OQ-6 | Run a live AI test? | **Defer**; no AI item is in scope |
| OQ-7 | The brief says "plan the next features". Does that include building F2 to F5? | **Yes**: approving this spec starts F2; each feature is its own PR for CEO acceptance |
| OQ-8 | Which version ships Phase 2? | **1.9.0** (new file key, new tabs); releasing it is a later CEO gate, not part of this project's done |
| OQ-9 | DOMAIN asks for a "check by a qualified engineer" note on results; the app has none today | Add it **to the CCF tab and the report's CCF section only**; the CEO decides any wider use |
| OQ-10 | Monte Carlo with groups: how are members sampled? | One Q_t draw per group per trial (members are identical components), β and α fixed; members must share the error factor or get a lint warning. Analyst to confirm |
| OQ-11 | Gate values below the top with groups applied | Keep the tree-walk values and label them "without CCF", as 1.8.0 already marks MCUB vs tree walk |
| OQ-12 | Tab / Shift-Tab mapping: roadmap 3.6 says "sibling / child (as in mind-map tools)", but mind-map tools use Tab for a child | **Tab = child, Shift-Tab = sibling** (mind-map convention the roadmap cites) |
| OQ-13 | Paste from Excel: apply valid rows and refuse bad ones, or all-or-nothing? | **Apply valid rows**, refuse whole bad rows (FN-49), one undo step |
| OQ-14 | A release check finds a defect: fix in 1.8.1 or list as known issue? | **Fix** if it is in the merged 1.8.1 changes; otherwise a Known issue |

## 10. Proposed features

- **F1** Release 1.8.1 covers FN-1 to FN-17, PERF-1, FN-65 depends on none
- **F2** CCF groups, beta factor covers UI-1 to UI-7, FN-18 to FN-40, PERF-2 to PERF-4, UI-18, FN-64 depends on F1
- **F2A** CCF alpha factor (groups of 2 to 4) covers UI-8, FN-41 to FN-45, PERF-5 depends on F2
- **F3** Grid of basic events with paste from Excel covers UI-9 to UI-13, FN-46 to FN-52, PERF-6, PERF-7 depends on F1
- **F4** What-if sliders covers UI-14, UI-15, FN-53 to FN-58, PERF-8 depends on F2
- **F5** Semantics help and editing covers UI-16, UI-17, FN-59 to FN-63 depends on F1 (FN-63 needs F2)

Order: F1, F2, F2A, F3, F4, F5. The analyst reviews F2, F2A, F4 and the final review.

## 11. Revision history

| Version | Date | By | Change |
|---|---|---|---|
| v0.1 draft | 2026-10-22 | spec writer for the Director | First draft from CHARTER, DOMAIN, R1, R2, the roadmap and the Director's scope decisions. Not approved. |
