# Specification: FTA Editor (division project `fta-editor`)

- Version: **v1.0**, 2026-10-22. Approved by the CEO on 2026-10-22 with every recommended answer in section 9 (requests/fta-editor-2.md); frozen. Work starts only on the CEO's call. Approval by the CEO freezes the UI, FN and PERF requirements (PERF bounds marked provisional may be adjusted once, section 4).
- Brief (CHARTER.md, verbatim): **"Release 1.8.1, then roadmap"**: "Ship the merged fixes as 1.8.1, then plan the next features from docs/ROADMAP_MECHANICAL_ENGINEERS.md".
- CEO answer to fta-editor-1 (decisions/20261022-roadmap-build-gate.md): "Build them after i give go ahead for all".
- Sources: `.division/research/R1-release-1.8.1.md`, `R2-roadmap.md`, `reviews/spec-critic-1.md`, `reviews/spec-analyst-1.md`, `reviews/spec-critic-2.md`, `docs/ROADMAP_MECHANICAL_ENGINEERS.md` ("roadmap x.y"), `CHANGELOG.md`, `.division/DOMAIN.md`.
- CCF sources, opened and checked by the analyst (pages are the printed page numbers):
  - **[S1]** NUREG/CR-5485 (1998), Mosleh, Rasmuson, Marshall, *Guidelines on Modeling Common-Cause Failures in PRA*. https://nrcoe.inl.gov/publicdocs/CCF/NUREGCR-5485_Guidelines%20on%20Modeling%20Common-Cause%20Failures%20in%20PRA.pdf
  - **[S2]** NUREG/CR-4780 Vol. 2 (1989), *Procedures for Treating Common Cause Failures in Safety and Reliability Studies*. https://www.osti.gov/servlets/purl/6564737
  - **[S3]** NASA/SP-2011-3421, 2nd ed., *Probabilistic Risk Assessment Procedures Guide*. https://ntrs.nasa.gov/api/citations/20120001369/downloads/20120001369.pdf

## 1. Summary

1. **Phase 1, starts when you approve this spec:** release `main` as **1.8.1** (recovery copy, Change folder, port 8765, `force`, server-side Stop). You merge the PR without squash; we build and test the exe from your merge commit, and tag and publish only after you approve.
2. **Phase 2 is specified here but built only after your go-ahead** (all of it or a part): F2 common-cause failure (CCF) groups, beta factor; F2A alpha factor (should, droppable); F3 grid with paste from Excel; F4 what-if sliders. Help and Tab-key editing (old F5) are cut.
3. Files without CCF groups give the same results as 1.8.1; the pinned core and `desktop/` are untouched; a CCF group that cannot be applied is kept, flagged and reported. Saving a CCF file in 1.8.x or the desktop app loses the groups (OQ-16).
4. Every CCF formula cites NUREG/CR-5485 or NUREG/CR-4780 Vol. 2 with page; no published numeric worked example exists (OQ-5). Speed limits are estimates until measured against 1.8.1 (OQ-17).
5. Your decisions: approve the spec and the recommendations in section 9, merge the 1.8.1 PR, run the 15-minute check, approve the release, give the Phase 2 go-ahead.

## 2. Goals and success measures

Every measure depends only on must items. G2, G4 and G5 can be measured only after the Phase 2 go-ahead.

| # | Goal | Measure (done when) | Must items |
|---|---|---|---|
| G1 | 1.8.1 is releasable with evidence | On the release commit (section 6): pytest 0 failures, GUI suite against the exe 0 FAIL, b2b against the exe 0 mismatches, manual check 3 of 3 passed, CI green; evidence under `.division/artifacts/release-1.8.1/` | FN-1, FN-3, FN-5, FN-10 to FN-13, FN-17, FN-68 |
| G2 | Redundant trains are no longer shown as more reliable than they are | Reference cases R1, R1h, R2, R2h, R3, R4 (section 7.4) reproduced to their stated tolerance; the CCF event appears in cut sets, importance, Monte Carlo, the report and the CLI; a group that is not applied is reported in the GUI, the report and the CLI (exit 1 in FTA mode) | FN-19, FN-21 to FN-26, FN-37 |
| G3 | Nothing changes for users who do not use CCF | FN-28 passes: corpus outputs equal to 1.8.1 after removing `elapsedMs`; no diff under `fta_web/core` or `desktop` | FN-28 |
| G4 | Data entry from spreadsheets | 500 rows × 3 columns pasted from Excel are applied within the PERF-6 bound (2.0 s, provisional) as one undo step, land on the intended events after any sort or filter, and every refused row is listed | PERF-6, FN-47, FN-50, UI-12 |
| G5 | What-if never changes the file or any output | With a factor active, every output path of FN-53 equals its nominal output; after any reset the what-if top event equals the headline exactly | FN-53, FN-58 |

## 3. Users and use cases

Users:
- **Reliability and safety engineers** (mechanical, machinery, process) running the Windows exe or `uv run`, with fault trees of up to a few hundred events (roadmap 3.2).
- **Reviewers** who read the DOCX report.
- **Batch users** of the CLI (`fta_editor quantify|cutsets|importance|mc|validate|report`).
- **Katey (CEO)**, who merges the PR from integration into `main` (without squash or rebase), runs the manual check, approves releases and gives the Phase 2 go-ahead.

Use cases:
- **U1** A user downloads 1.8.1, checks the SHA-256, and finds that language, theme and diagram style survive a restart and unsaved work survives a crash.
- **U2** An engineer models a 1oo2 pump train, groups the two pump failures with β = 0.1 from a cited data source, and sees the CCF cut set dominate the top event (roadmap 1.5).
- **U3** An engineer copies 200 failure rates from an FMEA spreadsheet and pastes them into the grid in one step (roadmap 3.3).
- **U4** A designer asks "what if this valve fails ten times as often?" and sees the top event move without changing the file (roadmap 1.7).

## 4. Requirements

Format: **ID** statement | why | test | priority. Retired IDs are listed at the end of each subsection and are never reused.
Reference cases R1 to R11 (section 7.4) are the numeric oracles; each is labelled "published formula" with its source page or "hand calculation".

**Measurement conditions for PERF items** (each item names one):
- **In-process:** `uv run --frozen pytest` on Katey's PC, the Python function called directly, one discarded warm-up call, then the median of 5 timed calls.
- **Browser:** the GUI suite harness, Chromium, dev server started with `uv run --frozen` on Katey's PC, app loaded and fixture opened before timing, median of 5.
- Fixtures are committed files (section 7.6). Medians and all 5 runs are written to `.division/artifacts/perf/<ID>.json`. CI runs the same tests with every bound multiplied by 3 as a smoke check.
- **Provisional bounds (PERF-2, PERF-5, PERF-6, PERF-7, PERF-8):** these bounds are estimates, not measurements. In task T0 the PM measures the 1.8.1 baseline of each (table below) under the item's conditions and writes it to `.division/artifacts/perf/baseline-1.8.1.json`. The Director may change each of these bounds **once**, without a change request, to a value no greater than 2× its measured baseline, recorded as a file in `.division/decisions/`. Any other change to a PERF bound is a change request. CEO consent: OQ-17.

  | Item | 1.8.1 baseline, measured on the 1.8.1 release commit |
  |---|---|
  | PERF-2 | in-process: `engine.summary` on `perf_ccf_301_nogroups.json` |
  | PERF-5 | in-process: `engine.summary` on `perf_alpha_301_nogroups.json` |
  | PERF-6 | browser: on `perf_grid_500.json`, the harness applies the 500 rows of `perf_grid_500_paste.tsv` through the existing node-update route, one request per node, until the headline is updated |
  | PERF-7 | browser: opening `perf_grid_500.json` until the tree panel and the headline are drawn |
  | PERF-8 | in-process: `engine.summary` on `perf_ccf_301_nogroups.json`; browser: one q edit in the Details panel on that file until the headline is updated |

- **T0** is the PM's first Phase 2 planning task. It adds no product code, so it may run before the Phase 2 go-ahead (section 6): it commits `make_perf_fixtures.py` and its outputs (section 7.6), derives the expected cut-set counts and `truncatedBy` of the CCF fixtures (for example from a hand-expanded copy of each tree run through 1.8.1 `cutsets.compute`) and records them in the generator, and measures the baselines above.

### 4.1 Phase 1: release 1.8.1 (F1)

- **FN-1** The version reads 1.8.1 in `pyproject.toml`, `uv.lock`, `report_docx.TOOL_VERSION`, the README badge, QUICKSTART (with the release date), `.github/copilot-instructions.md` and the `--version` example in `build/README.md` | one version wherever a user or a report sees it (R1) | test: a search for `1.8.0` in these seven files finds only history entries; the reviewer lists each hit | must
- **FN-3** `CHANGELOG.md` has `## [1.8.1] - <release date>` holding today's [Unreleased] text, with an empty `## [Unreleased]` above it; in the same commit `test_the_new_endpoints_are_in_the_api_reference_and_the_changelog` (`fta_web/tests/test_known_issues_1_8.py`, line 1880) is changed to slice the `## [1.8.1]` section | Keep a Changelog convention; the test would still pass on a slice from `[Unreleased]` to `[1.8.0]`, but it would then check a range that includes the empty [Unreleased] heading instead of the released section | test: the reviewer reads the diff (the [1.8.1] body equals the old [Unreleased] body; the test slices `## [1.8.1]` to `## [1.8.0]`); `uv run --frozen pytest` 0 failures on that commit | must
- **FN-5** The release notes pass this checklist: (1) the five behaviour changes: port 8765 with fallback and `--port 0`; `force` on `/api/file/open`, `/api/examples/open`, `/api/import/json` (`409 UNSAVED_CHANGES`); the recovery folder `C:\Users\<you>\.fta_editor\recovery\`; Change folder…; Stop that frees the editor (`/api/ai/cancel`); (2) a new Known issues list: 1.8.0 items fixed in 1.8.1 removed, "No autosave" reworded to describe the recovery copy, new items for a custom `--root` that contains the home folder (recovery-folder guard) and two copies started at once racing for port 8765; (3) the SHA-256 recorded by FN-10; (4) a "Not tested" list: the native folder dialog only by the manual check (FN-13), Ctrl-C cleanup, Firefox and WebKit only headless, the AI assistant only with a mock provider; (5) a Japanese section with items 1 and 2 | users and API clients learn of changed behaviour and honest limits (R1); en and ja (CHARTER) | test: the reviewer ticks items 1 to 5 in `.division/artifacts/release-1.8.1/notes-checklist.txt` | must
- **FN-10** The exe is built with PyInstaller (CPython 3.14) in a folder outside `K:\Dropbox`, from the release commit (the merge commit Katey creates on `main`, section 6), and launched once; `fta_editor.exe --version` prints `FTA Editor 1.8.1`; `fta_editor-1.8.1-windows.zip` is made from that build folder, and its SHA-256 is computed with `Get-FileHash -Algorithm SHA256` on the local zip before upload. Only after Katey approves the release does the division tag the release commit `v1.8.1` and publish the zip with the notes, as with v1.8.0 | the exe, the tag and the tested code must be one commit; Dropbox locks break the build | test: the build log in artifacts records the build path, the release-commit hash (`git rev-parse HEAD`), the `--version` output and the zip hash; `git rev-parse <release commit>^2` equals the tested integration commit of FN-17 (a merge without squash or rebase); `git rev-parse v1.8.1^{commit}` equals the recorded release-commit hash; the hash of the downloaded asset equals the recorded zip hash | must
- **FN-11** The full GUI suite, all 18 sections, runs against the built exe (`FTA_GUI_EXE=<path>`) with 0 FAIL | the exe is what users run (CHARTER) | test: `node run.mjs` with `FTA_GUI_EXE`; the summary table in artifacts shows FAIL = 0 | must
- **FN-12** The b2b suite runs against the new exe with `FTA_B2B_EXE` set to the exe of FN-10 and `FTA_B2B_EXE_COMMIT` set to the release-commit hash recorded by FN-10, with 0 mismatches | the defaults point at 1.7.0 (`544492b`, `fta_build_170`) (R1) | test: the `run_b2b.py` log shows both variables, the commit equal to the FN-10 hash, and 0 mismatches | must
- **FN-13** A person runs `manual-check-1.8.1.bat` on the built exe; it starts the exe, prints each step in English and writes pass or fail per step to `manual-check-1.8.1.txt`. Steps: (1) Change folder… opens the Windows folder chooser; a folder with a Japanese name, once picked, is listed by the file dialog; a file saved there reopens; a second Change folder… ended with Cancel leaves the allowed folder unchanged; (2) with unsaved edits, `taskkill /F /IM fta_editor.exe`, restart, **Unsaved work found** appears, and Restore brings back the edits as an untitled, modified analysis; (3) language, theme, significant figures and diagram style set in the exe are kept across two restarts | the native dialog and recovery after a real kill were never verified (R1); Katey runs Windows tasks from a `.bat` (global rule); see OQ-2 | test: the txt file shows 3 of 3 pass; the reviewer ran the `.bat` once on a dev build before handing it over | must
- **FN-17** CI (`tests.yml`, `extended.yml`) is green on the tested integration commit (the head of the PR from integration into `main`) and on the release commit | the merge gate, and proof that the merge commit is the tested code | test: GitHub checks page for both hashes | must
- **FN-68** A pytest added in F1 to the existing `fta_web/tests/test_known_issues_1_8.py` pins how 1.8.1 treats a file that has `analysis.ccfGroups` (shape of section 7.1): the file loads; its load warnings include one of kind `analysis_invalid` whose message contains `reset to their defaults: ccfGroups`; the file saved again has no `ccfGroups` | this warning is the only protection 1.8.x users get (K4, OQ-16); it must not change unnoticed | test: the pytest passes on the release commit; no product code changes for it | must
- **PERF-1** The batch move and delete of 4,800 nodes in a 4,860-node tree are measured and recorded (no pass threshold); if either median exceeds 1.0 s, the CHANGELOG phrase "well under a second" is corrected to the measured value | the CHANGELOG makes a claim the CI bound (3 s) does not prove | test: in-process, `test_3_a_batch_of_4800_nodes_moves_and_deletes_within_the_bound` timings in `artifacts/perf/PERF-1.json`; the reviewer compares them with the CHANGELOG text | should

Retired in 4.1: FN-2 (merged into FN-10), FN-4 (merged into FN-3), FN-6, FN-7, FN-8, FN-9 (merged into FN-5; the hash computation into FN-10), FN-14, FN-15, FN-16 (merged into FN-13).

### 4.2 Phase 2: common-cause failures, beta factor (F2)

- **UI-1** In Advanced mode a **CCF groups** tab lists every group with name, model, parameter values, member names, parameter source and status (`Applied`, or `Not applied: <reason>`); in ETA mode the tab is greyed with the reason in its tooltip, every group's status is `Not applied: ETA mode`, and the groups stay in the file | the user sees what is modelled and what is ignored (roadmap 1.5); matches how 1.8.0 greys other analysis tabs | test: GUI section `ccf` on a 2-group file (one not applied) checks columns and both statuses; switches to ETA and checks the greyed tab, that both statuses read `Not applied: ETA mode`, and that Save keeps both groups | must
- **UI-2** The tab creates a group from the basic events selected in the tree, edits a group's name, β, source and members, and deletes a group; each action is one undo step | groups must be editable without editing JSON | test: GUI section `ccf` creates, edits, deletes, and undoes each action | must
- **UI-5** Each member shows a `CCF: <group name>` badge in its tree row and diagram box; the cut-set table shows the CCF event as `CCF: <group name>`, and clicking that row highlights every member in the tree and the diagram | the grouping is visible where the tree is edited; the dominant cut set is often the CCF event | test: GUI section `ccf` counts badges and highlighted members; a screenshot is looked at by the reviewer | should
- **UI-7** The CCF tab shows an Assumptions box: the model and its formula with source and page (section 7.3); "a member's probability is its total failure probability Q_t at mission time"; "beta factor: the CCF event fails all members together"; "the split is applied to Q_t; splitting λ instead agrees only to first order in λT (S3 p. D-20)"; "the headline is the min-cut upper bound; the formulas in the sources use the rare-event approximation"; "β and α are not sampled in Monte Carlo" | results state their assumptions (DOMAIN) | test: the reviewer reads the box in en and ja against section 7.3 | must
- **FN-18** CCF groups are saved under `analysis.ccfGroups` (section 7.1), and a file with at least one group also gets the top-level key `"fileFormatVersion": 2`; files without groups are saved exactly as in 1.8.1. Groups are read by a dedicated CCF loader that takes `ccfGroups` out of the analysis before `engine.coerce_analysis` (which drops unknown keys and warns, engine.py 490-498) sees it, so loading a file with groups gives no `analysis_invalid` warning for `ccfGroups`; other invalid analysis settings in the same file are still warned about as today. A group with invalid values is kept verbatim and flagged not applied (FN-33), never dropped or coerced. A file whose `fileFormatVersion` is greater than 2 opens with the warning "This file was saved by a newer FTA Editor; saving may lose data" | engineers' modelling must never be lost on load or save (critic 8); a false "reset to defaults" warning would tell the user the groups were lost (critic 2-8) | test: pytest loads and saves a 3-group file (one valid, one with `"beta": "abc"`, one with a missing member) and compares the `ccfGroups` JSON objects equal, and asserts its load warnings contain no `analysis_invalid` entry; the same file with `"cutsets": {"maxOrder": 0}` added gets exactly one `analysis_invalid` entry, naming only `cutsets.maxOrder`; a no-group file saved by the new version equals its 1.8.1 save byte for byte; a `fileFormatVersion: 3` file shows the warning | must
- **FN-19** At compile time (`fta_web/logic.py` `compile_tree`, outside the pinned core), each member of an applied beta group has its variable replaced by OR(independent part, CCF event): the independent part keeps the member's event slot and id with q = (1 − β)·Q_t; the CCF event `ccf:<groupId>` has q = β·Q_t and is created once per group, so every reference to a member (links, transfers, repeated ids) reaches the same CCF event; the operator list stays in topological order (every operator refers only to earlier operators). Q_t is the member's q at mission time from its quantification model | roadmap 1.5; every analysis built on the compiled `Structure` sees the CCF event without a core change (analyst finding 6) | test: pytest reproduces R1, R1h (MCUB), R2, R2h, R3 and R4 to the tolerances in section 7.4; asserts topological order of the compiled operators; a member linked under two gates gives cut sets with exactly one `ccf:` id | must
- **FN-21** While at least one group is applied: `headlineMethod` is `mcub`, the headline includes the CCF events, the GUI headline reads "MCUB, includes CCF (n groups)", and `engine.may_need_cut_sets` (given the analysis) returns true. If the cut sets fail, time out, or are cut short by the summary's own caps (`capped`), the headline value is `null`, `headlineMethod` is `incomplete`, `ccfIncomplete` is true, and the GUI shows "incomplete, CCF not included" with the tree-walk value only under the label "tree walk, without CCF; cut sets cut short (<reason>)", where `<reason>` is `time`, `error` or `summary cap`; never a plain number | the tree walk cannot include a shared event, and today's fallback (engine.py 801-805) would show a CCF-free number as the headline (critic 4); the label says why the number is incomplete (critic 2-10) | test: pytest on the R1 file asserts method and value; with a 1 ms time budget asserts `incomplete`, `null` and the flag; GUI section `ccf` reads both headline texts and the label with reason `time` | must
- **FN-22** Cut sets list each CCF event with id `ccf:<groupId>`, label `CCF: <group name>` and its q; a member's variable appears under the member's id with the label `<name> (independent part)` and q = (1 − β)·Q_t; the member's Details panel and diagram box keep showing Q_t, with the independent part shown beside it | the user must know what each cut-set entry means after the expansion (critic 6, analyst) | test: pytest on the R1 file: cut sets {A, B} with q 8.1e-7 each labelled "(independent part)" (product of two 9e-4) and {ccf:g1} with q 1e-4; GUI reads the Details panel of A (Q_t 1e-3, independent part 9e-4) | must
- **FN-23** FV, Birnbaum, RAW and RRW (definitions in `fta_web/importance.py`) are computed on the expanded structure; the CCF event has its own row; member rows are the independent parts, labelled as in FN-22; no row reports a combined component value (independent part plus CCF) | importance must rank the CCF event; a component-level RAW would be a different quantity (analyst) | test: pytest on the R1 file reproduces the R1h importance values: FV 0.991965076374, Birnbaum 0.99999919, RAW 9919.6588, RRW 124.45669 for `ccf:g1` | must
- **FN-24** Monte Carlo samples the expanded structure: for each group, one draw per trial of the members' shared main parameter (members share model, parameters and uncertainty by FN-33) gives Q_t for that trial, and the independent parts and the CCF event follow as (1 − β)·Q_t and β·Q_t; the CCF event gets no uncertainty of its own (the members' `quant.unc` is not copied to it); β and α are fixed, and the Monte Carlo tab and the report say "β and α are not sampled" | uncertainty must include CCF without double sampling (analyst findings 2 and 7; closes OQ-10) | test: pytest (a) per trial, through the sampler's test hook: the CCF event q divided by the member Q_t equals β within relative 1e-12, and both members' independent parts are equal; (b) R11: n = 200,000, fixed seed, `--time-limit 3600`, the mean top event is within 3 of the run's own standard errors of 1.2696e-4 | must
- **FN-25** When the file has groups, the DOCX report has a CCF section: per group the name, model, parameters, testing scheme (alpha), source, members and status; the formulas with S1/S2 sources and pages; the Assumptions of UI-7; the note on overlapping CCF events (section 7.3); the note of FN-67; each not-applied group with the line "Not applied: <reason>. Results exclude this group."; the headline line says "includes CCF (n groups)" or "incomplete, CCF not included"; the CCF events appear in the cut-set and importance tables | the report is the deliverable (roadmap 2.5); a silent report would hide a not-applied group (critic 9) | test: pytest reads the DOCX text of the R1 file and of a file with one not-applied group and finds each item | must
- **FN-26** CLI `quantify`, `cutsets`, `importance` and `mc` with `--json` give the same numbers as the API for a file with groups and add a `ccf` block `{applied, notApplied: [{id, name, code, reason}], note}`; the text output prints one line per not-applied group. The exit code is 1 only when the document is in FTA mode, the command is one of these four, and a group is not applied or the headline is `incomplete`. In ETA mode: `quantify --json` adds the `ccf` block with every group in `notApplied` with code `CCF_ETA_MODE` and keeps exit code 0; `cutsets`, `importance` and `mc` keep their existing ETA refusal and its exit code; groups never change the exit code in ETA mode. Files without groups get no `ccf` block (FN-28) | batch users must not get a silent partial result (critic 9); ETA analyses never use groups, so they must not fail because of them (critic 2-11) | test: pytest compares CLI and API JSON on the R1 file; FTA-mode exit codes 0 (all applied), 1 (one not applied), 1 (incomplete headline); an ETA-mode file with one group: `quantify` exits 0 with `CCF_ETA_MODE` in `notApplied`, and `cutsets` exits with the same code as the same file without the group | must
- **FN-28** A document without CCF groups (no `ccfGroups` key or an empty list) gives the same results as 1.8.1, and no file under `fta_web/core/` or `desktop/` changes | engineers act on these numbers (Director); hash-pinned core and frozen desktop (CHARTER) | test: corpus = `fta_web/examples/*.json` and `fta_web/tests/b2b/*.json` except `expected.json`. For each file, CLI `quantify`, `cutsets`, `importance`, `validate` with `--json`, and `mc --json --n 2000 --seed 1 --time-limit 3600`, are compared with golden outputs produced on the 1.8.1 release commit (tag `v1.8.1`, FN-10) and committed under `fta_web/tests/golden_1_8_1/`. Comparison is parsed-JSON equality after removing the key `elapsedMs` at any depth (the only volatile key); both sides must have `truncatedByTime` false and no `"time"` in any `truncatedBy` (a file that times out at default limits is run with larger limits named per file in the test). b2b suite 0 mismatches. `git diff v1.8.1 -- fta_web/core desktop` is empty and `test_vendor_integrity.py` passes | must
- **FN-32** β is entered in a field labelled "β (dimensionless, 0 to 1)" and read as FN-46 states (`parseNumberText`, range [0, 1]); the GUI shows the message next to the field; the API checks β with `validate_ccf_beta` (FN-70). A β loaded from a file is handled by FN-18 and FN-33, not refused | units next to every value, errors next to the field, inputs validated (DOMAIN) | test: GUI section `ccf` enters `1.5` and `abc` and checks message position and text in en and ja, and enters `5%` and checks that β reads 0.05; API cases are those of FN-70 | must
- **FN-33** The CCF lint checks below run with every validation; an **error** makes the group not applied, a **warning** leaves it applied, a **status** makes it not applied without a Validation issue. Each code has en and ja text and names the group and member | the beta and alpha models assume identical basic-event components with small Q_t (S1 p. 40-42; analyst findings 3, 7, 9) | test: one pytest per row asserting code, severity and the applied flag; plus members with equal λ entered as /y and /h give no lint; members under INHIBIT or KOFN, and a member referenced twice, give no lint | must

  | Code | Condition | Severity |
  |---|---|---|
  | `CCF_MEMBER_NOT_BASIC` | member is a gate or has children, a house event, a conditioning event, a transfer, or an id not in the tree | error |
  | `CCF_TOO_FEW_MEMBERS` | fewer than 2 distinct members | error |
  | `CCF_MEMBER_IN_TWO_GROUPS` | an event belongs to two groups | error |
  | `CCF_MEMBERS_DIFFER` | members differ in quantification model, in any model parameter or Q_t by more than relative 1e-6, or in uncertainty (distribution, median or mean, error factor) | error |
  | `CCF_NO_PROBABILITY` | a member has no probability (q missing) | error |
  | `CCF_Q_ONE` | a member's Q_t is 1 (the split would lower a certain failure: AND of 2 gives 0.829 for β = 0.1) | error |
  | `CCF_BAD_PARAMETER` | β loaded from a file is not a finite number in [0, 1] | error |
  | `CCF_MEMBER_RENAMED` | a member id was renamed by the loader's duplicate-id repair | error |
  | `CCF_ETA_MODE` | the document is in ETA mode | status |
  | `CCF_HIGH_Q` | a member's Q_t is above 0.01 | warning |
  | `CCF_ZERO_Q` | the members' Q_t is 0 (the group has no effect) | warning |
  | `CCF_ORDERED_GATE` | a member sits below a PAND or XOR gate | warning |

- **FN-37** A group that is not applied is reported in the headline note ("n CCF groups not applied"), in its tab status, and in the Validation tab with click-to-jump to the group (report and CLI: FN-25, FN-26). In ETA mode only the headline note and the tab status apply; `CCF_ETA_MODE` is not a Validation issue | never silent (DOMAIN) | test: pytest asserts the note; GUI section `ccf` clicks the issue and lands on the group; in ETA mode the note reads "n CCF groups not applied" and the Validation tab lists no CCF issue | must
- **FN-38** Membership follows the tree: (a) every operation that removes a member node (tree delete, batch delete, AI update apply, FMEA re-import that replaces nodes, undo of the node's creation) removes it from its group in the same undo step, and undo restores both; (b) every operation that gives existing nodes new ids (import, duplicate-id repair on load) remaps members when the mapping is one to one, and otherwise flags the group `CCF_MEMBER_RENAMED`; (c) an operation that makes a member non-basic (adding a child, setting a gate) keeps the membership, and FN-33 flags the group | no dangling or wrong members (critic 8, 19) | test: pytest, one case per listed operation, checking the group's member list before, after and after undo | must
- **FN-40** Every CCF formula in code cites its source and page in the docstring; `docs/CCF.md` holds the formulas with sources and pages (section 7.3), the source errors not to copy, the reference cases of section 7.4 with their labels and derivations, the assumptions of UI-7 and the overlapping-CCF-events note | DOMAIN evidence rule | test: the analyst reviews before merge and records PASS in `.division/reviews/` | must
- **FN-66** A gate whose subtree contains a CCF member shows its min-cut upper bound from the cut-set expansion (`cutsets._Expander.memo`), labelled MCUB, in the diagram, Details, the report diagram and the Excel sheets; when no complete expansion is available it shows "n/a (CCF)" and no number; it never shows its tree-walk value | the tree-walk value of such a gate is about 100 times too low for R1 (analyst finding 4; closes OQ-11) | test: pytest on a tree root OR(G1 = AND(A, B), C) with A, B in a β = 0.1 group, Q_t = 1e-3, C q = 0: G1 shows 1.00809919e-4 (R1h, relative 1e-9); with a 1 ms time budget G1 shows "n/a (CCF)" | must
- **FN-67** The CCF tab, the report's CCF section and the CLI `ccf.note` carry the note "Check CCF results with a qualified engineer before use." (ja: 「CCF の結果は、使用前に有資格の技術者が確認してください。」) | DOMAIN: results carry the note unless the CEO decides otherwise; scope in OQ-15 | test: GUI section `ccf` reads the note in en and ja; pytest finds it in the DOCX text and the CLI JSON | must
- **FN-69** The CHANGELOG entry that introduces CCF groups, and the release notes of the version that ships them (1.9.0, OQ-8), carry this warning in en and ja: "Files with CCF groups lose the groups when saved by FTA Editor 1.8.x (it warns 'reset to their defaults: ccfGroups'), and lose all analysis settings when saved by the desktop app." (ja: 「CCF グループを含むファイルを FTA Editor 1.8.x で保存すると CCF グループが失われます（1.8.x は 'reset to their defaults: ccfGroups' と警告します）。デスクトップ版で保存すると解析設定がすべて失われます。」) | no key preservation is added to 1.8.x (OQ-16), so users must be told before they lose data (K4) | test: pytest finds both sentences in the CHANGELOG section that lists CCF groups; at the CCF release the reviewer ticks both in that release's notes checklist | must
- **PERF-2** In-process: `engine.summary` on `perf_ccf_301.json` (settings and group placement in section 7.6) takes at most 1.0 s (provisional) and returns `capped` false, `headlineMethod` `mcub`, and no `time`, `count`, `cutoff` or `error` in `truncatedBy`; the cut sets it used (`engine.summary_with_cut_sets`) contain each of the ten CCF events at least once, and their number and `truncatedBy` equal the values derived in T0 | the headline runs after every edit within a 2 s budget; at 1.0 s it stays clear of the cap that would make it `incomplete`; a fixture whose CCF cut sets were all dropped would time nothing useful (critic 2-3) | test: pytest timing to `artifacts/perf/PERF-2.json`, plus the content assertions | must
- **PERF-3** Browser: on `perf_ccf_301.json` the GUI `big` budgets hold: click to Details under 500 ms, Add dialog round trip under 3,000 ms | no slowdown in normal editing | test: GUI section `big` variant with the fixture, 0 FAIL | must
- **PERF-4** In-process: Monte Carlo with n = 10,000 on `perf_ccf_301.json` completes within the default 30 s limit (`truncatedByTime` false); the time is recorded | the run is time-capped, so a slowdown shows as fewer trials | test: pytest, result to `artifacts/perf/PERF-4.json` | should

Retired in 4.2: UI-3 (merged into FN-32), UI-4 (merged into FN-21), UI-6 (merged into UI-5), FN-20 (merged into FN-19), FN-27 (removed; see Non-goals), FN-29 (merged into FN-28), FN-30 and FN-31 (merged into FN-19 as R3, R4), FN-34, FN-35, FN-36 (merged into FN-33), FN-39 (merged into UI-1).

### 4.3 Phase 2: alpha factor for groups of 2 to 4 (F2A)

- **UI-8** For the alpha model the group editor shows fields α1 … αm "(dimensionless, 0 to 1)" for m members, read as FN-46 states, and a testing-scheme selector (staggered, non-staggered) with no preselected value | alpha needs one parameter per failure multiplicity; S1 p. 40 gives no default scheme | test: GUI section `ccf` on a 3-member group; the group shows `Not applied: testing scheme missing` until one is chosen | should
- **FN-41** The non-staggered alpha model uses Q_k = k / C(m−1, k−1) · (α_k / α_t) · Q_t with α_t = Σ k·α_k (S1 Eq. 5.7-5.9 p. 41; S2 Eq. C.23-C.24 pp. C-10/C-11), with one CCF event per member subset of size k ≥ 2 (q = Q_k, id `ccf:<groupId>:<m1>+<m2>…`), and each member = OR(independent part with Q_1, every CCF event that contains it) | roadmap 1.5 "MGL/α-factor" | test: pytest reproduces R6, R6h, R9, R9h; hypothesis property test Σ_k C(m−1, k−1)·Q_k = Q_t within relative 1e-12 for m = 2 to 4 | should
- **FN-42** The staggered alpha model uses Q_k = α_k / C(m−1, k−1) · Q_t (S1 Eq. 5.6 p. 40), with events as in FN-41 | same | test: pytest reproduces R5, R7, R8, R8h, R10h, and asserts R10h − R10 = 3·Q_2² within relative 1e-9; the property test of FN-41; for m = 2 with α = (1 − β, β) the cut-set probabilities equal the beta model within relative 1e-12 for β in {0, 0.05, 0.1, 1} (S1 p. E-2) | should
- **FN-43** Alpha lint, added to the FN-33 table: `CCF_ALPHA_SIZE` (error) for fewer than 2 or more than 4 members; `CCF_ALPHA_SUM` (error) when an α_k is not finite in [0, 1], the list length is not m, or |Σα − 1| > 1e-3; `CCF_ALPHA_NORMALISED` (warning) when 1e-9 < |Σα − 1| ≤ 1e-3, in which case each α_k is divided by Σα and the note shows the original sum; `CCF_NO_TESTING` (error) when the testing scheme is missing | at most 15 events per group; published α sets are rounded and do not sum to exactly 1 (S1 Table 6-9 p. 104, analyst finding 5) | test: pytest per code; an α set copied from S1 Table 6-9 p. 104 (chosen by the analyst) is applied | should
- **PERF-5** In-process: `engine.summary` on `perf_alpha_301.json` (5 staggered alpha groups of 4, settings and placement in section 7.6) takes at most 1.5 s (provisional) and returns `capped` false and no `time`, `count`, `cutoff` or `error` in `truncatedBy`; the cut sets it used contain each of the 55 CCF events at least once, and their number equals the value derived in T0 | 15 events per group multiply cut sets | test: pytest timing to `artifacts/perf/PERF-5.json`, plus the content assertions | should

Retired in 4.3: FN-44 (merged into FN-43), FN-45 (merged into FN-42).

### 4.4 Phase 2: grid of basic events with paste from Excel (F3)

- **UI-9** A **Grid** tab shows one row per basic event with columns id (read-only), name, model, λ, T, τ, μ, q, source, tags. Headers name units: λ in the unit picked in its header (/h, /y or FIT), T and τ in h, μ in /h, q dimensionless; q is editable only when the model is `fixed` and is shown with the significant-figures preference; tags are shown and entered separated by `; ` | engineers enter and check data in tables (roadmap 3.3); units explicit (DOMAIN) | test: GUI section `grid` reads the headers in en and ja and checks that q is read-only on a `rate` row | must
- **UI-10** The grid sorts by any column and filters by text | finding one row in 500 | test: GUI section `grid` | should
- **UI-12** After a paste, a summary beside the grid gives the number of rows applied and lists each refused row with its clipboard row number, column and message | bad rows are reported (R2, G4) | test: GUI section `grid` pastes 3 good and 2 bad rows and reads the summary | must
- **FN-46** One meaning per field: a cell typed or pasted into the grid means exactly what the same text means when typed into that field today, and no existing field changes how it reads numbers. Each field uses the function in the table below, called from its module (imported, not copied); the grid applies the same range as the existing field | the same text must never mean two things in one field depending on whether it was typed or pasted, and moving existing fields to another parser would change behaviour without a test (critic 11, critic 2-1) | test: the committed vector file `fta_web/tests/fixtures/number_inputs.json` holds at least 30 inputs with, per column (q, λ with header unit /h, T, τ, μ, β, α_k), the expected accept or refuse and value, including every row of the second table below; the GUI suite types each input into the existing field (Details panel for q, Quantification tab for λ, T, τ, μ, CCF tab for β, α_k) and into the grid cell, and pastes it into the grid, and all of them give the expected result; the reviewer confirms the grid module imports these functions and defines no number parser of its own | must

  | Field | Typed today in | Parser (unchanged) | Grid column |
  |---|---|---|---|
  | q (probability) | Add dialog, Details panel | `parseProbability` (`static/js/dialogs.js:716`), built on `parseNumberText` (`static/js/numfmt.js:137`); range [0, 1] | same function |
  | λ | Quantification tab | `parseNumber` (`static/js/tabs/analysis_common.js:171`) through `numberParser` (`static/js/tabs/quant.js:215`); ≥ 0, in the header unit | `parseNumber`, same range |
  | T, τ | Quantification tab | `parseNumber`; > 0 | `parseNumber`, same range |
  | μ | Quantification tab | `parseNumber`; ≥ 0 | `parseNumber`, same range |
  | β, α_k | CCF tab (new) | `parseNumberText`; range [0, 1] | not in the grid |
  | FMEA import cells | FMEA import | `cellNumber` (`static/js/tabs/fmea.js:111`) | unchanged, out of scope |

  Existing difference kept: the Quantification tab's own q field for the `fixed` model (`quant.js:371`) reads with `parseNumber`, so `5%` is refused there but read as 0.05 in the Details panel and the grid. Design may move `numberParser` to `analysis_common.js` and export it for the grid, with no change in behaviour.

  Inputs on which the two parsers disagree (expected results, all in `number_inputs.json`):

  | Input | q, β, α_k | λ (/h), μ | T, τ |
  |---|---|---|---|
  | `1e-400` | refused (too small for a double; not zero) | 0 | refused (0 is not > 0) |
  | `5%` | 0.05 | refused | refused |
  | `1/1000` | 0.001 | refused | refused |
  | `1,500E-06` | refused (thousands-group shape) | 1.5e-6 | 1.5e-6 |
  | `1,5E-06` | 1.5e-6 | 1.5e-6 | 1.5e-6 |

- **FN-47** Paste fills cells from the selected cell rightwards over the visible columns and downwards over the rows currently visible, in their displayed order. Each target cell is sent as (node id, column key) together with the `revision` and `documentSerial` the grid was drawn from; if either has changed, the server answers `409 STALE_REVISION`, applies nothing, and the grid redraws and says "The analysis changed; paste again". A whole paste is one undo step | row indexes land on the wrong events after sort or filter (critic 10); undo must not need 500 steps | test: pytest posts a paste with a stale revision and gets 409 with no change; GUI section `grid` sorts by name descending, filters, pastes a 3 × 3 block and checks the three intended node ids; one Ctrl+Z after a 50-row paste restores all 50 | must
- **FN-50** Paste cases behave as in this table | every case is defined before it is built (critic 10, 20) | test: one pytest or GUI check per row | must

  | Case | Behaviour |
  |---|---|
  | empty cell | leaves that cell unchanged |
  | row filtered out of view | receives nothing; the paste continues on the next visible row |
  | trailing newline at the end of the clipboard | ignored; no empty row |
  | quoted cell (Excel quoting, doubled quotes, embedded tab or newline) | unquoted; embedded tab or newline kept in text columns, refused in numeric columns |
  | more cells than visible columns to the right | the extra cells are refused, reported once per row |
  | more rows than visible rows below the anchor | the extra rows are refused and reported; no node is created |
  | more than 2,000 clipboard rows | the whole paste is refused with a message; nothing is applied |
  | id column | a value equal to the row's id is ignored; a different value refuses the row ("id does not match this row") |
  | q column on a non-fixed model | a value equal to the shown q is ignored; a different value refuses the row ("q is computed from the model") |
  | any invalid cell | the whole row is refused; valid rows are applied (OQ-13) |

- **FN-51** λ is read in the unit shown in its header and stored per hour (8,760 h per year, 1 FIT = 1e-9 /h); T and τ are hours; μ is per hour | units explicit end to end (DOMAIN) | test: pytest: 1 FIT is stored as 1e-9 /h; 8.76 /y as 1e-3 /h | must
- **PERF-6** Browser: pasting `perf_grid_500_paste.tsv` (500 rows × λ, T, source) into `perf_grid_500.json` is applied, and the paste summary and the headline are updated, within 2.0 s (provisional) of the paste event | G4 | test: GUI section `grid` timing to `artifacts/perf/PERF-6.json` | must
- **PERF-7** Browser: the Grid tab opens with the 500 rows of `perf_grid_500.json` drawn within 1.0 s (provisional) | G4 | test: GUI section `grid` timing | should

Retired in 4.4: UI-11 (merged into UI-9), UI-13 (removed; see Non-goals), FN-48 (merged into FN-47), FN-49 (merged into FN-50), FN-52 (replaced by the rule in FN-46).

### 4.5 Phase 2: what-if sliders (F4)

- **UI-14** A **What-if** tab lets the user pick basic events and set a factor for each with a slider from 1/100 to 100 on a log scale, showing the nominal and what-if main parameter, the nominal and what-if q, the baseline top event, the what-if top event and their ratio | roadmap 1.7 "slider or ±factor with the top event updating live" | test: GUI section `whatif` sets factor 10 on one event and reads the five values | must
- **UI-15** While any factor is not 1, a banner on the What-if tab says "What-if values, not saved", with Reset per event and Reset all | the user must not mistake what-if numbers for the analysis | test: GUI section `whatif` | must
- **FN-53** What-if works on a copy: the document, its undo history, the modified flag and `revision` are unchanged, and every output outside the What-if tab carries nominal values: Save, the recovery copy, the DOCX report, Excel and CSV export, diagram export, Copy CSV, and the AI context | what-if values must not leak into the analysis record (critic 12) | test: pytest and GUI with factor 10 active on one event: Save, recovery copy, CSV and Copy CSV are byte-identical to their output before the slider moved; DOCX text, Excel cell values and the exported diagram SVG are equal apart from creation timestamps; the AI context text is equal; `canUndo`, the modified flag and `revision` are unchanged | must
- **FN-55** A factor f multiplies the event's main parameter, as Monte Carlo does (`uncertainty._q_function`): λ for the `rate`, `standby` and `repairable` models, q for `fixed`; q then follows from the model. A q above 1 is set to 1 and "clamped to 1" is shown beside it. A factor on a CCF member applies to every member of its group, and the tab says so | scaling λ keeps the model's physics; scaling one member alone would break FN-33 (critic 13) | test: pytest: `rate` λ = 1e-5 /h, T = 1,000 h, f = 10 gives q = 1 − exp(−0.1) = 0.0951626 (hand calculation, relative 1e-6); `fixed` q = 0.5, f = 10 gives 1 with the clamp flag; f = 10 on member A of the R1 file scales both members | must
- **FN-56** The what-if top event uses the headline's method: when the headline is MCUB (always when a CCF group applies) it is the MCUB over the baseline's cut sets with the changed q values; when the headline is the tree walk it is the tree walk; when the headline is `incomplete` the what-if says so and shows no number. If the baseline cut sets were cut short by the document's cutoff, the tab notes "cut sets from nominal values" | like for like; reusing the baseline cut sets is what makes PERF-8 reachable | test: pytest on the R1 file: factor 1 gives the headline; factor 10 on A (q 1e-2 for both members) gives 1.080919e-3 (hand calculation: 8.1e-5 + 1e-3 − 8.1e-8, relative 1e-9) | must
- **FN-58** All factors return to 1 on Reset all, New, Open, Import, an example, a mode switch, undo or redo, and any document change made in this or another browser tab (seen as a change of `revision` or `documentSerial`); after any reset the what-if top event equals the headline exactly (the same float) | the baseline changed; Reset must truly reset | test: pytest per trigger; GUI section `whatif` with two tabs: an edit in tab 2 resets tab 1 | must
- **PERF-8** On `perf_ccf_301.json` with the baseline cut sets already computed: in-process, `POST /api/whatif` through the test client answers within 300 ms (provisional); browser, the what-if top event is shown within 500 ms (provisional) of the last slider movement. The first what-if after an edit may take up to the PERF-2 bound because it computes the baseline | "updating live"; resolves the v0.1 conflict between 300 ms, CCF (FN-56) and a 2.0 s headline | test: pytest and GUI section `whatif` timings to `artifacts/perf/PERF-8.json` | should

Retired in 4.5: FN-54 (merged into FN-58), FN-57 (merged into FN-55).

### 4.6 Phase 2: semantics help and editing (old F5)

Retired: UI-16, UI-17, FN-59, FN-60, FN-61, FN-62, FN-63 (F5 removed; see Non-goals and OQ-18).

### 4.7 All phases

- **UI-18** Every new user-visible text has an English and a Japanese string | CHARTER | test: `test_catalog_parity.py` and `test_i18n.py` pass with the new keys | must
- **FN-64** No new text claims compliance with a standard; standards appear only as sources | compliance claims are CEO-only (DOMAIN) | test: a case-insensitive whole-word search of new en strings for comply, complies, compliant, compliance, conform, conforms, conformity, certified, certification, and of new ja strings for 準拠, 適合, 認証, finds no hit outside source citations; the reviewer confirms | must
- **FN-70** The new endpoints (`/api/ccf/groups` and `/api/ccf/groups/<id>`, `/api/grid/paste`, `/api/whatif`) read the request body with a strict JSON reader that refuses the tokens `NaN`, `Infinity` and `-Infinity` with `400 INVALID_JSON`, and check every numeric field with the named validator in the table below. A validator accepts only a JSON number (not a string, boolean or null) that is finite and in range; otherwise it answers `400 INVALID_FIELD` naming the field and its range. `-0` is stored as 0. Existing routes and their validators (`node_schema.validate_quant`, `_validate_probability` in `routes/tree.py`) and the app-wide JSON provider are unchanged | the browser sends numbers already read by the field's parser (FN-46), so the server must not read text a second way; NaN and Infinity must never reach a calculation (critic 2-2) | test: pytest, per field, sends a valid number, a string (`"0.1"`), the token `NaN`, the token `Infinity`, a negative number (`-0.1`) and, for bounded fields, a value above the upper bound (`1.5`; `101` for f), and asserts acceptance or the code and the field name; `1e-400` is not used in API tests (the JSON reader turns it into 0 before any validator sees it) | must

  | Field | Endpoint | Validator (in a new module beside `node_schema.py`; names may change in design, one validator per field stays) | Accepted |
  |---|---|---|---|
  | `beta` | POST, PATCH `/api/ccf/groups` | `validate_ccf_beta` | [0, 1] |
  | `alpha` | POST, PATCH `/api/ccf/groups` | `validate_ccf_alpha` | a list of JSON numbers, each in [0, 1] (length and sum are lint, FN-43, not refusals) |
  | `q` | `/api/grid/paste` | `validate_grid_q` | [0, 1] |
  | `lambda` | `/api/grid/paste` | `validate_grid_lambda` | ≥ 0, per hour |
  | `T`, `tau` | `/api/grid/paste` | `validate_grid_duration` | > 0, hours |
  | `mu` | `/api/grid/paste` | `validate_grid_mu` | ≥ 0, per hour |
  | factor f | `/api/whatif` | `validate_whatif_factor` | [0.01, 100] |
  | `revision`, `documentSerial` | `/api/grid/paste`, `/api/whatif` | `validate_revision` | a non-negative integer |

Retired in 4.7: FN-65 (moved to section 6 as a constraint with the same check).

## 5. Non-goals

- **Semantics help, Tab / Shift-Tab editing, Duplicate subtree** (roadmap 3.6, 3.7; old F5): cut to fit the $300 budget; roadmap P2. The CEO confirms in OQ-18.
- **CCF groups on the Excel Analysis sheet and member marks on the Events sheet** (old FN-27). CCF events still appear wherever Excel shows cut sets, importance and gate values (FN-22, FN-23, FN-66).
- **Selecting a grid row selects the node** (old UI-13).
- **Changing how any existing field or the FMEA import reads numbers** (FN-46 keeps every existing parser).
- **Keeping `ccfGroups` when a file is saved by 1.8.x or `desktop/`** (OQ-16).
- **Sampling β or α in Monte Carlo**; CCF models other than beta and alpha (MGL, BFR).
- **NOT gate** (roadmap 1.4): rejected by DIVERGENCE D5 (OQ-3).
- **Component library** (2.2): needs cited reliability data the division cannot verify.
- **Revisions, review comments, diff and scenario compare** (2.4, second half of 1.7): needs a revision model in the file format.
- **Large-tree navigation** (3.2); **ETA normalisation, consequences, bow-tie** (1.8): the ETA walk is in the pinned core.
- **PDF report and diagram paging** (2.5): needs a PDF library, a licence choice that is the CEO's.
- **AI items** (section 4 of the roadmap): need a live provider with the CEO's key (OQ-6).
- **Dormant-with-coverage model, "cycles" unit** (1.3), **BDD backend** (1.1), copy and paste between files, inline editing in the diagram.
- **Writing what-if values into the document.**
- **Back-porting to `desktop/`**, a multi-user server, and any claim of compliance with a standard.

## 6. Constraints

- **Phase gate:** Phase 1 (F1) starts on spec approval. Phase 2 features (F2, F2A, F3, F4) are built only after a CEO go-ahead (CEO, 2026-10-22: "Build them after i give go ahead for all"); spec approval alone does not start them.
  - The go-ahead is recorded as a file `.division/decisions/<yyyymmdd>-phase2-go-ahead.md` that quotes the CEO's words and names the features covered, and as one line in `.division/STATUS.md` (date, features, file name).
  - The CEO may give it for a subset of F2, F2A, F3, F4 that respects the dependencies of section 10 (F4 and F2A need F2); the rest waits for a later go-ahead recorded the same way.
  - Before the go-ahead the PM may write `PLAN.md` and the Phase 2 feature briefs and run T0 (section 4); no Phase 2 feature branch starts and no product code is written.
- **Merging and the release commit:** feature teams work on feature branches; the PM merges feature branches into `division/fta-editor/integration`. The tested integration commit (CI green, FN-17) is opened as a PR to `main`; Katey merges it with a merge commit, without squash or rebase. That merge commit on `main` is the **release commit**. The division builds the exe from that exact commit, runs the release checks on it and records its hash (FN-10 to FN-13); after Katey approves the release, the division tags the release commit (`v1.8.1`) and publishes, as with v1.8.0. Nobody in the division pushes to `main` or merges into it.
- `fta_web/core/*.py` is hash-pinned (`fta_web/core/BASELINE.json`, `DIVERGENCE.md`) and `desktop/` is frozen; new behaviour goes in `fta_web/` beside the core (checked by FN-28).
- The server stays loopback-only with token, Origin and Host checks; the sandbox root stays a security boundary (Change folder only by the native chooser).
- Existing file keys and API responses for documents without CCF groups do not change; `analysis.ccfGroups` and `fileFormatVersion` are optional and written only when a group exists. Existing routes keep their validators (FN-70).
- 1.8.1 adds no feature. A defect found by the release checks is fixed only if it is in the merged 1.8.1 changes and is named in the CHANGELOG; anything else becomes a Known issue (OQ-14). The test of FN-68 changes no product code.
- No test calls a live AI provider; check: CI runs with no provider key set (from old FN-65).
- Windows PC in Dropbox: `uv run --frozen` always; build the exe outside Dropbox; Dropbox can lock git files.
- No new runtime dependency without the CEO (licences are CEO-only).
- Budget cap $300 (API-equivalent usage) for the whole project.

## 7. Interfaces and data

### 7.1 File format addition (JSON analysis file)

```json
{
  "fileFormatVersion": 2,
  "analysis": {
    "ccfGroups": [
      {"id": "g1", "name": "Feed pumps", "model": "beta", "beta": 0.1,
       "alpha": null, "testing": null,
       "members": ["n12", "n13"], "source": "free text, e.g. data handbook and page"},
      {"id": "g2", "name": "Relief valves", "model": "alpha", "beta": null,
       "alpha": [0.955, 0.034, 0.011], "testing": "staggered",
       "members": ["n20", "n21", "n22"], "source": "..."}
    ]
  }
}
```
`model` is `beta` or `alpha`. For `alpha`, `alpha` lists α1 … αm in member order and `testing` is `staggered` or `nonStaggered` (no default). Both keys are written only when at least one group exists.

Older programs (risk K4; no key preservation is added to them, OQ-16):
- **1.8.x** loads the file, drops `ccfGroups` with the load warning "Invalid analysis setting(s) were reset to their defaults: ccfGroups." (pinned by FN-68), ignores `fileFormatVersion`, and saves the file without `ccfGroups`.
- **`desktop/`** does not keep the `analysis` key: saving there drops all analysis settings, including `ccfGroups` (existing behaviour, unchanged).
- `fileFormatVersion` protects only against versions after the CCF release (FN-18).

### 7.2 Units

| Quantity | Unit | Range |
|---|---|---|
| q, Q_t, Q_k | dimensionless probability | [0, 1] |
| β, α_k | dimensionless fraction | [0, 1]; Σ α_k = 1 within 1e-3 (normalised) |
| λ | stored per hour; shown /h, /y (8,760 h) or FIT (1e-9 /h) | ≥ 0 |
| μ | per hour | ≥ 0 |
| T, τ | hours | > 0 |
| what-if factor f | dimensionless | [0.01, 100] |

### 7.3 Formulas and sources

| Formula | Source |
|---|---|
| Beta factor: Q_1 = (1 − β)·Q_t (independent part), Q_m = β·Q_t (one event failing all m members) | S2 Table C-1 p. C-5 and Eq. C.10-C.13 p. C-6; S1 Eq. 5.11-5.13 p. 42 |
| Alpha factor, non-staggered: Q_k = k / C(m−1, k−1) · (α_k / α_t) · Q_t, α_t = Σ k·α_k | S1 Eq. 5.7-5.9 p. 41; S2 Eq. C.23-C.24 pp. C-10/C-11 |
| Alpha factor, staggered: Q_k = α_k / C(m−1, k−1) · Q_t | S1 Eq. 5.6 p. 40 |
| Staggered alpha with m = 2, α2 = β equals the beta factor | S1 p. E-2 |
| Splitting Q_t versus splitting λ agree only to first order in λT | S3 p. D-20 |

Source errors not to copy (derive from S1 Eq. 5.6 and 5.7 instead): S1 p. 41 Eq. 5.10 prints Q3 = 3α3·Q_t (should be α3·Q_t); S1 Tables 5-4 and 5-5 have the m = 4 rows swapped; S1 Table 5-5 "2 of 5" has a stray /4.

Overlapping CCF events: with alpha groups of 3 or 4, MOCUS keeps cut sets with two CCF events of the same group (for example {C_AB, C_AC}); S1 Table E-2 p. E-4 omits them. The editor keeps them: Boolean-correct and conservative (for 1-of-3 the difference is 3·Q_2², R10 versus R10h). `docs/CCF.md` and the report state this.

Not cited: NUREG/CR-4780 Vol. 1 and NUREG/CR-6268 (not opened by the analyst).

### 7.4 Reference cases (acceptance oracles)

Q_t = 1e-3 unless stated. "Exact" values are compared with relative tolerance 1e-12 for rare-event sums and 1e-9 for MCUB and importance values (floating-point error of 1 − Π(1 − q)); "rounded" values to half a unit in the last digit shown.

| # | Case | Expected | Label | Kind |
|---|---|---|---|---|
| R1 | beta, AND of 2, β = 0.1 | rare-event 1.0081e-4 | published formula, S1 Table 5-2 p. 49 (Case 1); S3 Eq. 7-3 p. 7-5 | exact |
| R1h | same | MCUB 1.00809919e-4; for `ccf:g1`: FV 0.991965076374, Birnbaum 0.99999919, RAW 9919.6588, RRW 124.45669 | hand calculation | MCUB, Birnbaum exact; others rounded |
| R2 | beta, OR of 2, β = 0.1 | rare-event 2·Q_1 + Q_2 = 1.9e-3 | published formula, S1 Table 5-2 p. 49 (Case 2) | exact |
| R2h | same | MCUB 1.899010081e-3 | hand calculation | exact |
| R3 | R1 tree with β = 0 | MCUB 1e-6, equal to the tree without the group; cut sets equal after dropping zero-probability CCF sets | hand calculation | exact |
| R4 | R1 tree with β = 1 | top 1e-3 | hand calculation | exact |
| R5 | staggered, m = 2, α = (0.9, 0.1) | Q_2 = 1e-4, equal to R1 | published formula, S1 Table 5-4 p. 53 | exact |
| R6 | non-staggered, m = 2, α = (0.95, 0.05) | Q_2 = 9.5238095e-5 | published formula, S1 Table 5-5 p. 54 | rounded |
| R6h | same, AND of 2 | Q_1 = 9.0476190e-4; rare-event 9.6056689e-5; MCUB 9.6056611e-5 | hand calculation | rounded |
| R7 | staggered, m = 3, α = (0.955, 0.034, 0.011) (α from S3 p. 7-16) | CCF part 3·Q_2 + Q_3 = 6.2e-5 | published formula, S1 Table 5-4 p. 53 | exact |
| R8 | same, 2-of-3 | 7 cut sets; rare-event 3·Q_1² + 3·Q_2 + Q_3 = 6.4736075e-5 | published formula, S1 Table 5-2 p. 49 (Case 4); cut sets S1 Table E-2 p. E-4 | exact |
| R8h | same | MCUB 6.47344749e-5 | hand calculation | rounded |
| R9 | non-staggered, m = 3, same α (α_t = 1.056) | CCF part 1.27841e-4 | published formula, S1 Table 5-5 p. 54 | rounded |
| R9h | same, 2-of-3 | rare-event 1.302945e-4; MCUB 1.302880e-4 | hand calculation | rounded |
| R10 | staggered, m = 3, same α, 1-of-3 (all three must fail) | Q_1³ + 3·Q_1·Q_2 + Q_3 = 1.10495760e-5 (overlapping CCF events omitted) | published formula, S1 Table 5-2 p. 49 (Case 3) | rounded |
| R10h | same, as the editor computes it (overlapping CCF events kept) | rare-event 1.10504430e-5 = R10 + 3·Q_2² | hand calculation | rounded |
| R11 | Monte Carlo, AND of 2, β = 0.1, members lognormal with median 1e-3, error factor 3 | E[top] ≈ β·E[Q_t] + (1 − β)²·E[Q_t²] = 1.2696e-4 | hand calculation | within 3 standard errors of the run |

No published numeric worked example of a two- or three-train top event was found in S1, S2 or S3 (the S1 section 6 auxiliary feedwater example is asymmetric and time-dependent). See OQ-5.

### 7.5 API (proposed; names may change in design, behaviour may not)

- `GET /api/ccf/groups`, `POST /api/ccf/groups`, `PATCH /api/ccf/groups/<id>`, `DELETE /api/ccf/groups/<id>`: each change is one undo step and raises `revision`; `beta` and `alpha` are JSON numbers checked by FN-70.
- When the document has groups, analysis responses gain a `ccf` block `{applied: [...], notApplied: [{id, name, code, reason}], note}` and CCF event ids `ccf:<groupId>` (beta) or `ccf:<groupId>:<memberId>+<memberId>…` (alpha, members in group order). `headlineMethod` gains the value `incomplete` and the summary gains `ccfIncomplete` (FN-21). In ETA mode every group is in `notApplied` with code `CCF_ETA_MODE` (FN-26).
- `POST /api/grid/paste` `{revision, documentSerial, rows: [{clipRow, nodeId, cells: {columnKey: value}}]}` returns `{applied, refused: [{clipRow, column, message}]}`, or `409 STALE_REVISION` with nothing applied. Numeric values are JSON numbers in stored units, read in the browser by the field's parser (FN-46) and checked by FN-70.
- `POST /api/whatif` `{revision, factors: {nodeId: f}}` returns `{baseline, whatIf, ratio, method, events: [{id, nominalParam, param, nominalQ, q, clamped, groupId}], note}`; it never changes state; `409 STALE_REVISION` on a stale revision; each f is a JSON number checked by FN-70.
- The new endpoints read bodies with the strict JSON reader of FN-70 (`NaN`, `Infinity`, `-Infinity` give `400 INVALID_JSON`).
- New lint codes: those in FN-33 and FN-43, each with en and ja text.

### 7.6 Performance fixtures

Generated by the committed, deterministic `fta_web/tests/fixtures/make_perf_fixtures.py` (written in T0); the outputs are committed beside it.
- **`perf_ccf_301.json`**: the GUI `big` shape with fixed ids. Root `root` (OR); subsystems `S<i>`, i = 0..5 (AND if i is odd, else OR); modules `M<i>_<j>`, j = 0..6 (AND if i + j is odd, else OR); components `C<i>_<j>_<m>`, m = 0..5, model `fixed`, q = 1e-3·(m + 1). 301 nodes.
  - Analysis settings stored in the fixture: `analysis.cutsets` = `{"maxOrder": 6, "maxCount": 5000, "cutoff": 1e-30}`.
  - Ten beta groups, β = 0.1, all in AND modules under the OR subsystems S0, S2, S4: `G1`..`G9` have members `C<i>_<j>_0`, `C<i>_<j>_1`, `C<i>_<j>_2` of the modules (i, j) = (0,1), (0,3), (0,5), (2,1), (2,3), (2,5), (4,1), (4,3), (4,5) in that order; `G10` has members `C4_5_3`, `C4_5_4`, `C4_5_5`. Every member has q = 1e-3.
  - Why: each CCF event then appears in a minimal cut set of order at most 4 (for example {ccf:G1, C0_1_3, C0_1_4, C0_1_5}; {ccf:G9, ccf:G10}), within maxOrder and above the cutoff. The sets under the AND subsystems S1, S3, S5 have order 27 or more and are dropped by maxOrder by design, so an `order` entry in `truncatedBy` is expected.
  - Expected number of cut sets and `truncatedBy` under these settings: derived in T0 and recorded in the generator.
- **`perf_alpha_301.json`**: the same tree and analysis settings; five staggered alpha groups `A1`..`A5`, α = (0.95, 0.03, 0.01, 0.01), members `C<i>_<j>_0` to `C<i>_<j>_3` of the modules (0,1), (0,3), (0,5), (2,1), (2,3); those members have q = 1e-3. Each of the 11 CCF events of a group appears in a minimal cut set of order at most 6 (for example {ccf:A1:C0_1_0+C0_1_1, C0_1_2, C0_1_3, C0_1_4, C0_1_5}). Expected number of cut sets: derived in T0.
- **No-CCF variants** `perf_ccf_301_nogroups.json` and `perf_alpha_301_nogroups.json`: the two files above without `ccfGroups` and `fileFormatVersion`; used for the 1.8.1 baselines (section 4).
- **`perf_grid_500.json`**: root (OR); 25 OR gates `G00`..`G24`, each with 20 basic events `E<gg>_<nn>`, model `rate`, λ = 1e-6 /h, T = 8,760 h; 526 nodes, 500 basic events. **`perf_grid_500_paste.tsv`**: 500 rows of λ (in /y), T, source, in the grid's displayed order.

### 7.7 Release artifacts

`fta_editor-1.8.1-windows.zip` with its SHA-256; `.division/artifacts/release-1.8.1/` holds the GUI summary, the b2b log, the build log (path, release-commit hash, `--version`, zip hash), `notes-checklist.txt`, `manual-check-1.8.1.txt` and `perf/PERF-1.json`.

## 8. Risks and mitigations

| # | Risk | Mitigation |
|---|---|---|
| K1 | No published numeric worked example exists for the CCF formulas (DOMAIN asks for one) | Published-formula reference cases plus labelled hand calculations (section 7.4); the CEO decides (OQ-5) |
| K2 | The CCF expansion changes results of trees without groups | FN-28 golden comparison over the whole corpus, plus b2b |
| K3 | A change slips into the pinned core | FN-28 `git diff` check, `test_vendor_integrity.py` in CI |
| K4 | A file with groups saved in 1.8.x loses its groups; saved in `desktop/` it loses the whole `analysis` key | No key preservation in 1.8.x (would not trace to the brief); 1.8.x warns naming `ccfGroups`, pinned by FN-68; the CCF release notes warn (FN-69); the CEO accepts the residual risk (OQ-16); `fileFormatVersion` (FN-18) protects only later versions |
| K5 | Gate values below the top shown without CCF | FN-66 (MCUB from the expansion or no value) |
| K6 | Monte Carlo double-samples CCF members | FN-24 one draw per group, per-trial test |
| K7 | Recovery-folder guard with a custom `--root` containing home; two copies racing for 8765 | Known issues in the 1.8.1 notes (FN-5) |
| K8 | Five new endpoints in a patch release | OQ-1 |
| K9 | Dropbox locks files during the build | Build outside Dropbox (FN-10) |
| K10 | The manual check waits on Katey while travelling | 15-minute `.bat` (FN-13); the release is a CEO gate anyway |
| K11 | (removed with F5) | — |
| K12 | Budget ($300) runs out in Phase 2 | F5 cut; features ship in order F2, F3, F4, F2A as separate branches; F2A is should, last, and may be dropped (OQ-18); partial go-ahead (section 6) |
| K13 | Q_t near 1 makes the beta split lower a certain failure | `CCF_Q_ONE` error, `CCF_HIGH_Q` warning (FN-33) |
| K14 | Overlapping CCF events make results differ from S1 Table E-2 | Kept on purpose (conservative), stated in docs and report; R10/R10h test the difference |
| K15 | What-if values leak into saved or exported outputs | FN-53 checks every output path |
| K16 | Paste lands on the wrong events after sort or filter | FN-47 node-id addressing with revision check |
| K17 | The Phase 2 go-ahead comes late and the team context is lost | Phase 2 is fully specified now; `PLAN.md`, briefs and T0 may be done before the go-ahead (section 6) |
| K18 | PERF bounds are estimates and may be unreachable or too loose | Marked provisional; 1.8.1 baselines measured in T0; one Director adjustment to at most 2× baseline, recorded (section 4, OQ-17) |
| K19 | The released exe is built from a commit other than the tested one | Release commit defined in section 6; FN-10 checks the merge parents and the tag; FN-12 and FN-17 name the same hash |
| K20 | The same text means different numbers in different fields | FN-46 keeps each field's existing parser and tests the disagreeing inputs per column; FN-70 accepts only JSON numbers on new endpoints |

## 9. Open questions

Open, for the CEO (you can approve all recommendations in one reply):

| # | Question | Recommended answer |
|---|---|---|
| OQ-1 | 1.8.1 or 1.9.0? Five new endpoints suggest a minor version by semver | **1.8.1**, your wording; the notes list the API change |
| OQ-2 | Who runs the 15-minute manual check (FN-13)? | **Katey**, with `manual-check-1.8.1.bat` |
| OQ-3 | Add a NOT gate? | **No**, keep DIVERGENCE D5 |
| OQ-5 | Our rules ask every formula to be tested against a published worked example with numbers. The sources publish the CCF formulas, but none has a numeric example of a redundant train. Options: **A)** accept the published-formula cases plus labelled hand calculations (section 7.4) as the acceptance tests; **B)** require a published numeric example, and the CCF features wait until one is found | **A** |
| OQ-6 | Run a live AI test? | **Defer**; no AI item is in scope |
| OQ-8 | Which version ships Phase 2? | **1.9.0** (new file key, new tabs); releasing it is a later CEO gate |
| OQ-13 | Paste from Excel: apply the valid rows and refuse the bad ones, or all-or-nothing? | **Apply valid rows**, refuse whole bad rows (FN-50), one undo step |
| OQ-14 | A release check finds a defect: fix in 1.8.1 or list it as a known issue? | **Fix** if it is in the merged 1.8.1 changes; otherwise a Known issue |
| OQ-15 | Our domain rules say every result carries "check by a qualified engineer". The app has no such note today. Put it on every result, or on CCF results only (FN-67)? | **CCF results only** |
| OQ-16 | A file with CCF groups, opened and saved in 1.8.x, loses the groups (1.8.x shows a warning naming them); saved in the desktop app it loses all analysis settings. We do not add protection to 1.8.1. Accept this risk? | **Accept**; the 1.9.0 notes warn users (FN-69) |
| OQ-17 | Our speed limits (PERF-2, 5, 6, 7, 8) are estimates. May the Director adjust each once, to no more than twice what 1.8.1 measures on the same data, without asking you? | **Yes** |
| OQ-18 | Confirm that help and Tab-key editing (old F5) are cut, and that the alpha factor (F2A) may be dropped if the budget runs short? | **Yes** to both |

Closed in v0.2:
- OQ-4 (alpha in this project?): Director ruling, F2A stays as should and is built last.
- OQ-7 (build or plan?): answered by the CEO: Phase 2 is built after a separate go-ahead (section 6).
- OQ-9 (scope of the engineer note): replaced by FN-67 and OQ-15.
- OQ-10 (Monte Carlo sampling): settled by the analyst, now FN-24.
- OQ-11 (gate values below the top): Director ruling, now FN-66.
- OQ-12 (Tab / Shift-Tab mapping): retired with F5.

New in v0.3: OQ-16, OQ-17, OQ-18.

## 10. Proposed features

| Id | Title | Requirements covered | Depends on |
|---|---|---|---|
| F1 | Release 1.8.1 | FN-1, FN-3, FN-5, FN-10, FN-11, FN-12, FN-13, FN-17, FN-68, PERF-1 | spec approval |
| F2 | CCF groups, beta factor | UI-1, UI-2, UI-5, UI-7, FN-18, FN-19, FN-21 to FN-26, FN-28, FN-32, FN-33, FN-37, FN-38, FN-40, FN-66, FN-67, FN-69, FN-70 (`beta`), PERF-2 to PERF-4, UI-18, FN-64 | F1; T0; Phase 2 go-ahead covering F2 |
| F3 | Grid of basic events with paste from Excel | UI-9, UI-10, UI-12, FN-46, FN-47, FN-50, FN-51, FN-70 (grid fields), PERF-6, PERF-7, UI-18, FN-64 | F1; T0; Phase 2 go-ahead covering F3 |
| F4 | What-if sliders | UI-14, UI-15, FN-53, FN-55, FN-56, FN-58, FN-70 (factor), PERF-8, UI-18, FN-64 | F2; go-ahead covering F4 |
| F2A | CCF alpha factor (groups of 2 to 4) | UI-8, FN-41, FN-42, FN-43, FN-70 (`alpha`), PERF-5, UI-18, FN-64 | F2; go-ahead covering F2A; droppable on budget (OQ-18) |

Order: F1 on approval; T0 after the 1.8.1 release commit exists (allowed before the go-ahead); after the go-ahead, the covered features in the order F2, F3, F4, F2A. The analyst reviews F2, F2A, F4 and the final review. The PM merges each feature branch into `division/fta-editor/integration`; Katey merges the PR from integration into `main` without squash or rebase (section 6).

## 11. Revision history

| Version | Date | By | Change |
|---|---|---|---|
| v0.1 draft | 2026-10-22 | spec writer for the Director | First draft from CHARTER, DOMAIN, R1, R2, the roadmap and the Director's scope decisions. |
| v0.2 draft | 2026-10-22 | spec writer for the Director | Revision for critic round 1, analyst review 1, the CEO answer to fta-editor-1 and the Director's rulings. Details below. |
| v0.3 | 2026-10-22 | spec writer for the Director | Candidate for CEO approval. Critic round 2 (12 findings) applied by the Director's rulings. 55 to 58 requirements (47 must, 11 should). Details below. |

v0.3 changes, critic round 2 (`reviews/spec-critic-2.md`) under the Director's rulings:
- 2-1 [blocker] One parser: FN-46 retitled "one meaning per field". No existing field changes its parser: q uses `parseProbability`/`parseNumberText`; λ, T, τ, μ use `parseNumber`; β and α_k use `parseNumberText`; the grid calls the same functions (no copies); FMEA import unchanged and out of scope. Entry paths in a table; the five disagreeing inputs (`1e-400`, `5%`, `1/1000`, `1,500E-06`, `1,5E-06`) with expected results per column added to `number_inputs.json` as the test. Kept existing difference stated (Quantification tab q field). Non-goal added. UI-8 refers to FN-46. Server part moved to FN-70.
- 2-2 [blocker] Server: new FN-70: the new endpoints accept JSON numbers only, a named validator per field (table), a strict JSON reader refusing `NaN`/`Infinity`; tests send number, string, NaN, Infinity, negative, above range; `1e-400` dropped from API tests; existing routes unchanged. FN-32 and section 7.5 refer to FN-70. New K20.
- 2-3 [blocker] PERF-2 fixture: `perf_ccf_301.json` has its own `analysis.cutsets` (maxOrder 6, cutoff 1e-30); all ten groups moved into AND modules under the OR subsystems S0, S2, S4 so each CCF event is in a minimal cut set of order at most 4; the expected cut-set count and `truncatedBy` are "derived in T0". PERF-2 asserts `capped` false, no time/count/cutoff/error truncation and all ten CCF events present. The same placement rule applied to `perf_alpha_301.json` and PERF-5 (it had the same defect: two groups under S1).
- 2-4 [major] PERF bounds: PERF-2, 5, 6, 7, 8 marked provisional; T0 defined; 1.8.1 baselines named per item on no-CCF fixtures (new `*_nogroups.json`); one Director adjustment to at most 2× baseline, recorded as a decision; new OQ-17; new K18.
- 2-5 [major] K4: no key preservation in 1.8.1; new OQ-16 (CEO accepts the residual risk); new FN-68 in F1 pins the 1.8.1 warning text "reset to their defaults: ccfGroups" in the existing `test_known_issues_1_8.py`; new FN-69 in F2 puts the warning in the CHANGELOG and the 1.9.0 notes; K4 rewritten.
- 2-6 [major] Release commit defined in section 6 (tested integration commit → PR → Katey's merge without squash or rebase → build and checks on that merge commit, hash recorded → Katey approves → tag and publish, as with v1.8.0); applied to FN-10, FN-12, FN-17, FN-28, sections 1, 3, 7.7 and 10; new K19.
- 2-7 [major] Go-ahead gate: recorded as a decision file and a STATUS.md line; PLAN.md, briefs and T0 allowed before it; partial go-ahead respecting dependencies (section 6, section 10); new OQ-18 (F5 cut, F2A droppable); K12, K17 updated.
- 2-8 [major] FN-18: loading a file with groups gives no `analysis_invalid` warning for `ccfGroups`; other invalid settings still warned; tests added.
- 2-9 [minor] FN-3: line 1880.
- 2-10 [minor] FN-21: the tree-walk label carries the truncation reason.
- 2-11 [minor] ETA mode: groups kept, status `Not applied: ETA mode` (UI-1), new status code `CCF_ETA_MODE` (FN-33), FN-37 states what is shown, FN-26 states the CLI exactly (exit 1 only in FTA mode for quantify, cutsets, importance, mc; ETA `quantify` exits 0 with the `ccf` block), section 7.5.
- 2-12 [minor] Section 7.1 and K4 agree: `desktop/` drops the whole `analysis` key on save; 1.8.x drops `ccfGroups` with a warning.
- New IDs: FN-68, FN-69, FN-70. No ID renumbered or reused.

v0.2 changes, Director rulings:
- D1 Phase gate: OQ-7 removed (CEO answer); gate stated in sections 1, 6 and 10; Phase 1 starts on approval.
- D2 Citations: S1/S2/S3 with pages from the analyst; every "page to be verified" removed; NUREG/CR-4780 Vol. 1 and NUREG/CR-6268 dropped; reference cases R1 to R11 are the oracles, each labelled (section 7.4).
- D3 OQ-5 rewritten in plain words with options A (recommended) and B.
- D4 Overlapping same-group CCF events kept, with a note in docs and report (section 7.3, FN-25, FN-40; R10/R10h).
- D5 OQ-11: gate MCUB from the expansion, never the tree walk (new FN-66).
- D6 Headline fallback with groups: "incomplete, CCF not included", `may_need_cut_sets` true (FN-21).
- D7 Engineer note: new FN-67 on the CCF tab, report and CLI JSON; scope to the CEO as new OQ-15.
- D8 One number parser and node-id + column-key + revision paste addressing with 409; paste cases defined (FN-46, FN-47, FN-50).
- D9 What-if scales the main parameter; every output path nominal; reset on edits from any tab (FN-53, FN-55, FN-58).
- D10 Data safety: invalid groups kept and flagged; members remapped or flagged; `fileFormatVersion`; CLI exit 1 with the `ccf` block; DOCX "not applied" line (FN-18, FN-38, FN-26, FN-25).
- D11 PERF: committed fixtures with named member placement (7.6); in-process or browser conditions per item; PERF-1 a recorded measurement; PERF-8 versus FN-56 versus PERF-2 resolved by reusing the baseline cut sets.
- D12 Goals use only must items: F3 and F4 core items raised to must (the CEO's answer says build all of them); G2 extended to not-applied reporting.
- D13 Shrink: 91 to 55 requirements. Removed: FN-27, UI-13, FN-63, and all of F5 (UI-16, UI-17, FN-59 to FN-62) to Non-goals. F2A kept as should.
- D14 Merging roles stated in sections 1, 6 and 10.

v0.2 changes, critic round 1:
- C1 Build vs plan: see D1. C2 FN-28/G3: named volatile key `elapsedMs`, MC with fixed `--n`, `--seed`, `--time-limit 3600`, `truncatedByTime` false, corpus named, goldens from the 1.8.1 commit. C3: see D2, D3. C4: see D6.
- C5 FN-23 FV corrected to 0.991965076374 (code's definition). C6 Member meaning after expansion: FN-22 labels, FN-23 no component-level row. C7 FN-24 oracle and per-trial test replaced; OQ-10 closed. C8: see D10. C9: see D10.
- C10, C11: see D8. C12, C13: see D9. C14: see D11. C15: see D12. C16: see D7.
- C17 FN-3 (old FN-4) reason corrected: the test does not break; it is updated so it checks the released section. C18 Lint cases added: Q_t = 0, missing q, Q_t = 1, PAND/XOR warning, INHIBIT and KOFN allowed, differing error factor (FN-33). C19 FN-38 covers every membership change. C20 Grid read-only behaviour, units of T, τ, μ and the tags separator defined (UI-9, FN-50). C21 FN-10 builds the zip and hashes the local file. C22 PERF-1 recorded, merge roles stated. C23 FN-64 search narrowed to whole words. C24 Merges applied: release-notes checklist (FN-5), manual check (FN-13), lint table (FN-33), constraints (FN-65 to section 6, FN-29 into FN-28); cuts as in D13.

v0.2 changes, analyst review 1:
- A1 Citations replaced (D2); source errors not to copy listed (7.3). A2 FN-23 value (C5). A3 FN-24 oracle R11 and per-trial ratio test. A4 `CCF_MEMBERS_DIFFER` for model, parameters and uncertainty; "β and α are not sampled" in UI-7, FN-24, FN-25. A5 `CCF_HIGH_Q` warning, `CCF_Q_ONE` error, `CCF_ORDERED_GATE` warning. A6 Σα tolerance 1e-3 with normalisation note (FN-43). A7 No default testing scheme (UI-8, `CCF_NO_TESTING`). A8 Gate MCUB or no value (FN-66). A9 Compile-time expansion keeping topological order, with a test (FN-19). A10 Overlapping CCF events kept with a note (D4). A11 Member rows labelled "independent part", no component-level RAW (FN-22, FN-23). A12 OQ-5 to the CEO (D3). A13 Q_t versus λ splitting stated (UI-7, 7.3).

Retired and merged IDs (never reused): FN-2 → FN-10; FN-4 → FN-3; FN-6, FN-7, FN-8, FN-9 → FN-5 (hash computation → FN-10); FN-14, FN-15, FN-16 → FN-13; UI-3 → FN-32; UI-4 → FN-21; UI-6 → UI-5; FN-20, FN-30, FN-31 → FN-19; FN-29 → FN-28; FN-34, FN-35, FN-36 → FN-33; FN-39 → UI-1; FN-44 → FN-43; FN-45 → FN-42; UI-11 → UI-9; FN-48 → FN-47; FN-49 → FN-50; FN-52 → replaced by FN-46's rule; FN-54 → FN-58; FN-57 → FN-55; FN-65 → section 6. Removed: FN-27, UI-13, FN-63, UI-16, UI-17, FN-59, FN-60, FN-61, FN-62. New in v0.2: FN-66, FN-67. New in v0.3: FN-68, FN-69, FN-70. Removed open questions: OQ-7; closed: OQ-4, OQ-9, OQ-10, OQ-11, OQ-12; new in v0.2: OQ-15; new in v0.3: OQ-16, OQ-17, OQ-18.
- v1.0 (2026-10-22, Director): approved by the CEO ("I approve but wait my call to start work"); open questions closed with their recommended answers; text otherwise identical to v0.3.
