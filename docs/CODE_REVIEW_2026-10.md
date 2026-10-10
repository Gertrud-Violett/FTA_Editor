# Code review — October 2026

**Scope:** the whole repository at `main` = `b009027` (1.7.1 plus the GUI suite).
Eight parallel reviews: analysis engine, backend API/state/security,
I/O/CLI/exports, AI assistant, frontend core, analysis tabs and i18n, the
extended suites (full back-to-back matrix and real-browser GUI suite), and the
documentation. Repository infrastructure was reviewed alongside.

**Method:** every reported defect was reproduced before it was fixed: a
script against the code, the Flask test client, the CLI, or Chromium driving
the running app. Each fix has a regression test that failed before it, in
`fta_web/tests/test_review_2026_10_*.py`. The engine was cross-checked
against an independent truth-table oracle (exact top probability, minimal
cut sets, MCUB, Birnbaum) on about 5,000 random trees, including advanced
gates, house events, transfers and link cycles. The ID prefixes are E-
(engine), B- (backend), IO-, AI-, F- (frontend), T- (tabs), X- (extended
suites) and DOC-.

**Delivered in three merges to `main`:** sprint 1 (backend, CLI, exports,
AI), sprint 2 (frontend, tabs) and sprint 3 (documentation).
`CHANGELOG.md` → [Unreleased] lists every user-visible fix.

## Results

| Area | Fixed | Left open (see below) |
|---|---:|---|
| Engine and validation (E-) | 7 | E-7, E-8, E-10, E-12, two E-6 leftovers |
| Backend API, files, rendering (B-) | 18 (+3 fixed by other areas) | B-22, B-23 |
| I/O, CLI, Excel/DOCX/XML, FMEA import (IO-) | 24 | IO-20 (by design) |
| AI assistant, providers (AI-; D21–D26) | 17 | Azure reasoning models; AI-11 for non-Anthropic |
| Frontend core (F-) | 22 | ETA-mode aria labels |
| Analysis tabs and i18n (T-) | 15 (+1 fixed by F-20) | — |
| Extended suites (X-) | 3 | — |
| Documentation (DOC-) | 33 | DOC-33, DOC-35, DOC-36 (historical or unverifiable) |
| Infrastructure | 7 | test-state singletons, CI action versions |

**The most serious findings, all fixed:**

- **Security**
  - The SVG sanitiser could be bypassed, letting script run in the app
    origin and the session token go to another host (F-12).
  - Excel export stored `=…` text as live formulas (IO-1).
  - The browser CSV exports were open to formula injection (T-14).
- **Silently wrong numbers**
  - FMEA `"1,200"` and `"1.200,5"` were read 1000× low (IO-2, IO-19).
  - An `"eta"` file was computed as a fault tree (B-4, B-19).
  - Duplicate links were counted twice (B-18).
  - A legacy advanced gate name gave the tree walk one answer and the cut
    sets and validation another (E-1).
  - An invalid own T fell back to the mission time (E-2).
  - An out-of-range probability passed validation (E-6).
- **Lost or misapplied work**
  - An AI update was installed over a document edited, or replaced, while
    the model was working (AI-01), and proposals could be applied to another
    document (AI-02).
  - Load skipped the discard prompt mid-commit (F-13).
  - A Save As name was garbled under load (F-32).
  - IME Enter submitted mid-conversion (F-24).
  - An FMEA import wrote another document's occurrence table (T-1).
- **Broken features**
  - Anthropic replies failed on every thinking model, the default Claude
    models, while Test & Save passed (AI-07, D21).
  - The documented Azure endpoint always returned 404 (AI-08, D23).
  - No SDK timeouts, so a hung provider blocked the AI for up to 30 min, or
    until restart for Gemini (AI-09, D24).
  - Control characters and lone surrogates broke the XLSX, XML and DOCX
    exports, and Save (IO-3..5, B-16).
  - `install.py`'s uv path skipped the DOCX report extra and ran a foreign
    `pytest`.

## Verification

| Check | Baseline `b009027` | After the review |
|---|---|---|
| `pytest` (fta_web + desktop) | 2046 passed, 41 skipped | 2474 passed, 41 skipped |
| Full back-to-back matrix (`FTA_B2B_FULL=1`) | 0 mismatches | 0 mismatches (4374 rows) |
| Real-browser GUI suite | 716/716 | 716/716 |
| GitHub Actions `tests` (ubuntu 3.10/3.13, windows 3.13) | green | green |

Windows CI caught three test-only portability defects after sprint 1. Two
tests let subprocess decode node's UTF-8 output with cp1252, and one CLI test
ignored that Windows switches stdout to UTF-8 by design. All three were fixed
on `main`. CI now names failing tests in GitHub annotations (`conftest.py`),
because the job logs need a sign-in. The same decoding pattern in sprint 2's
tests was fixed before merge, using a Linux sitecustomize that applies
Windows' text-I/O defaults (cp1252, CRLF writes).

The vendored core changed only through documented divergences D21–D26 (AI
providers, re-pinned in `BASELINE.json`). `desktop/` source is untouched.

## Left open (deliberately)

| ID | Sev | What | Why open |
|---|---|---|---|
| E-7 | LOW | Order/cutoff truncation is reported even when every dropped set would have been absorbed | Conservative (says "≈" when exact); an exact check costs performance |
| E-8 | LOW | In link cycles, XOR/KOFN arity counts the inputs left after the cycle fallback | Rare; the cycle is already a CYCLIC_LINK warning |
| E-10 | LOW | numfmt.py vs numfmt.js differ on non-integer sig figs, ±inf and booleans | Outside the contract; every finite number agrees (12,058 × 6 checked) |
| E-12 | LOW | XOR tree-walk value ~1e-5 relative off for a parity input near 1 | D14's 12-significant-figure storage; XOR trees use the MCUB headline |
| E-6 | LOW | A non-boolean `houseState` (1, "true") reads as OFF; a string `k` gives an odd KOFN message | Only from hand-edited files; reported, not decided |
| B-22 | LOW | The pinned 1.6 DOT pipeline (`core/json_viewer.py`, desktop and parity tests) still has the digit-id and control-character defects | Pinned; the web app draws through `diagram_dot.py`, which is fixed |
| B-23 | LOW | A crafted id equal to another id's sanitised form merges two diagram boxes | Crafted input only |
| AI-11 | LOW | OpenAI/Gemini/Azure Update FTA still asks for 2000 tokens; trees over ~30–45 nodes may be cut off (a clear error) | A larger cap breaks older models with smaller output limits |
| — | LOW | Microsoft Copilot (Azure) still sends `max_tokens` and a temperature, which an o-series or GPT-5 deployment may refuse | D26 left Azure out on purpose; documented |
| IO-20 | — | The CLI's `--csv` is raw (not spreadsheet-escaped) | By design: it is the machine-readable contract; documented |
| — | LOW | In ETA mode the tree's aria label and search label still say "fault tree" | Screen-reader text only |
| — | MED (tests) | Several suites reset `fta_web.state`'s singleton, while `create_app` serves bare `routes.*` and its own `state`; they pass by test order | Test isolation; worth a follow-up |
| — | LOW (CI) | `actions/checkout@v4` and `astral-sh/setup-uv@v5` target the deprecated Node 20 | Bump when convenient |
| D-* | — | The frozen desktop app's own defects | Listed in `desktop/README.md` |

## Feature implementation status

These were checked against the code, not the docs. The list is
[`ROADMAP_MECHANICAL_ENGINEERS.md`](ROADMAP_MECHANICAL_ENGINEERS.md).

| Item | Status | Evidence / what is missing |
|---|---|---|
| 1.1 Minimal cut sets | Done | `cutsets.py` (MOCUS), `/api/analysis/cutsets`, Cut Sets tab, CLI, report |
| 1.2 Importance measures | Done | `importance.py` (FV, Birnbaum, RAW, RRW), FV overlay |
| 1.3 Failure-rate models | Partial | fixed / rate / standby / repairable with /h, /y, FIT; no dormant or coverage model |
| 1.4 Standard gates | Partial | KOFN, XOR, INHIBIT, PAND, transfer, house, undeveloped; no NOT gate, no cross-file transfer |
| 1.5 Common-cause failures | Not started | — |
| 1.6 Monte Carlo | Done | `uncertainty.py`, Uncertainty tab |
| 1.7 Sensitivity / scenario compare | Not started | — |
| 1.8 ETA consequences / bow-tie | Not started | only the ETA_BRANCH_SUM rule |
| 2.1 FMEA import | Done | `fmea_import.py`, FMEA tab, re-import in place |
| 2.2 Component library | Not started | — |
| 2.3 Traceability | Done | trace fields, Traceability tab, search prefixes |
| 2.4 Revisions / diff | Not started | 50-step undo only |
| 2.5 Report export | Partial | DOCX and Excel sheets; no PDF |
| 2.6 CLI | Done | `cli.py`: quantify, cutsets, importance, mc, validate, report |
| 3.1 Standard symbols | Done | `fta_symbols.js`, symbols style, top-down layout; no symbol legend |
| 3.2 Large-tree navigation | Not started | highlight and jump-to-node only |
| 3.3 Grid view | Not started | read-only table in the Quantification tab |
| 3.4 Significant figures | Done | `numfmt.js` / `numfmt.py` |
| 3.5 Validation panel | Done | 23 rules (`PROBABILITY_OUT_OF_RANGE` added) |
| 3.6 Editing ergonomics | Mostly not started | Japanese localisation done |
| 3.7 Semantics help | Partial | formulas and fix hints; no gate/link help |
| AI: grounded proposals, narratives, audit | Not started | — |
