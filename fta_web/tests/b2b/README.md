# Back-to-back (B2B) numeric comparison corpus

The same input files go through every independent path of FTA Editor, and
the outputs are compared key by key. Every disagreement is either a bug (fixed,
with a test) or a documented, intended divergence (listed below).

| File | What it is |
|---|---|
| `*.json` | the corpus (49 trees), written by `make_corpus.py` |
| `expected.json` | hand-computed answers for the textbook trees (closed-form formulas in `make_corpus.py`, never the engine) |
| `make_corpus.py` | regenerates the corpus deterministically (`uv run --frozen python fta_web/tests/b2b/make_corpus.py`); `test_b2b.py` checks the committed files are its exact output |
| `b2b_lib.py` | the paths, normalisers, comparison, truth-table oracle and divergence attribution |
| `run_b2b.py` | runs everything and prints the matrix (below) |
| `../test_b2b.py` | the pytest module: fast paths by default, the rest with `FTA_B2B_FULL=1` |

## Running

```
PYTHONUTF8=1 uv run --frozen --extra all --extra test python -m pytest -q fta_web/tests/test_b2b.py
FTA_B2B_FULL=1 uv run --frozen --extra all python fta_web/tests/b2b/run_b2b.py
```

`FTA_B2B_FULL=1` adds the large random trees (`R*.json`) and, in pytest, the
real server and the packaged exe. The runner always runs every path it can
find; it exits 1 on any mismatch.

- **The packaged exe** is looked up at
  `%LOCALAPPDATA%\fta_build_170\dist\fta_editor\fta_editor.exe`
  (`FTA_B2B_EXE` overrides). It is the 1.7.0 release (`RELEASE_COMMIT` =
  `544492b`, `FTA_B2B_EXE_COMMIT` overrides), so the runner exports that
  commit's `fta_web/` with `git archive` and compares the exe with its own
  source.
- **A second Python build** (the exe is CPython 3.14; the default uv venv is
  3.10) is used when `.venv314` exists (`FTA_B2B_PY2` overrides):
  `UV_PROJECT_ENVIRONMENT=.venv314 uv run --frozen --python 3.14 --extra all python -V`.
- **node** is needed for the browser-formatter comparison (skipped without).

## Paths

| Path | What runs |
|---|---|
| `expected` | engine vs `expected.json` (rel 1e-10: the engine keeps 12 s.f.) |
| `oracle` | truth table over all 2^n event states (n ≤ 16; no PAND, no cycles), its own reading of the file and the model formulas: exact top event, minimal cut sets, repeated events, the MCUB from the minimal sets, tree walk = exact without repeated events, rare-event ≥ MCUB ≥ exact for coherent trees |
| `mc` | Monte Carlo: without uncertainty every statistic is the point estimate and std = 0; point = tree walk (method tree) or MCUB (method cutsets); lognormal means vs analytical (F12, n = 20000, 5 standard errors) |
| `engine` | derived q vs stored probability; summary vs cut sets |
| `api:client` | `create_app()` test client: `/api/file/open`, `/api/state`, `/api/nodes/<id>` (incl. `quantDerived`), `/api/analysis/summary`, `cutsets`, `importance`, `uncertainty` (seeded), `validate`, `/api/dot` labels at 6 s.f., `/api/export/xlsx` (Events and Analysis sheets), `/api/export/xml`, `/api/export/json` (reloaded), `/api/report/docx` at 6 s.f. (python-docx), save-as → reopen |
| `api:server` | the same over HTTP against a real `fta_web/run.py --root <copy> --no-browser` with the session token |
| `cli`, `cli:csv` | `run.py quantify|cutsets|importance|mc|validate --json` in one batch per command; `--csv` spot checks |
| `legacy_core` | `fta_web/core` FTACore (the 1.6 engine) on the legacy-only trees |
| `desktop` | the frozen `desktop/src/FTA_Editor_core.py` (imported under another module name); every difference attributed to a DIVERGENCE.md entry by switching the documented changes on one at a time in an independent re-implementation of the walk |
| `desktop_compat` | 1.7 files saved by the web app, read by the desktop core: the USER_GUIDE "Desktop app compatibility" claims (logicGate projection, derived `probability` for models/house/transfer, AND/OR-only trees equal up to D14, per-gate projection semantics, node keys kept and `analysis` dropped on a desktop save, reopen resets to defaults) |
| `roundtrip:engine` | load → save → load: identical values, keys, analysis; no load repair |
| `numfmt:js` | `static/js/numfmt.js` `formatProb` (node) vs `numfmt.format_prob` at 1–6 s.f. on every number the corpus produces |
| `cli:py2` | this branch's CLI under the second Python build |
| `release->branch` | the release's source CLI (same Python) vs this branch: only the branch's fixes may differ |
| `exe:cli==src`, `exe:server==src` | the exe vs its own source under the same Python version: bit-identical |
| `exe:cli`, `exe:server` | the exe vs this branch's engine (differences classified as LIBM or FIXED) |

Monte Carlo runs everywhere with n = 2000, seed 20260928 (the report uses
the document's seed); same seed → identical numbers on every path of the
same build.

Tolerances: exact equality wherever a float is passed as a float (JSON,
CSV, XML carry `repr`); formatted outputs (DOT, DOCX) are compared as the
exact strings of the reference formatted with `numfmt.format_prob` at 6 s.f.;
XLSX at 16 significant digits (openpyxl writes `%.16g`).

## Corpus

| File | Covers |
|---|---|
| L01 | AND/OR, 3 levels, document format |
| L02 / L03 | the same tree as a bare tree / `{"FTA": tree}` (legacy formats) |
| L04 | AND- and OR-links to leaves and to a gate (repeated events) |
| L05 | link cycle G↔B plus a leaf self-link (D17) |
| L06 | 121-level AND/OR chain (recursion, order truncation) |
| L07 | ETA mode (D14: 3e-7 → 0 on the desktop) |
| L08 | probabilities 1e-12 … 0.999999 (D14 flush to zero; OR cancellation) |
| L09 | zeros and ones, string `"0.25"` and int `1` probabilities |
| L10 | duplicate ids (D15) |
| L11 | Unicode and `< > & " '` in names (DOT/DOCX escaping) |
| L12 | top id `TOP` (D16) |
| L13 | minified document (D8: the desktop loader cannot read it) |
| L14 | gate spellings `and` / `""` / `None` / missing / `NOT`, missing probability |
| L15 | dangling, empty and malformed links |
| L16 | tiny OR inputs (1e-17, 1e-15, AND of 1e-6 ×3): the OR cancellation bug |
| F01 | every quant model; λ in FIT stored per hour; T default (mission 4380 h) vs own T; μ vs MTTR; standby λτ > 0.2 |
| F02 | rate models with the default mission time (no `analysis` block) |
| F03 | KOFN 2oo3 (equal p), 1oo2, 3oo3 (k = n), 2oo4 unequal (k stored as `2.0`) |
| F04 | XOR two inputs and three (parity, flagged) |
| F05 | INHIBIT + conditioning, and a malformed INHIBIT (3 children) |
| F06 | PAND of 2 and 3 |
| F07 | TRANSFER to a gate, to a missing node, with ignored children, a cycle |
| F08 | house ON/OFF in AND/OR, house with children |
| F09 | undeveloped events |
| F10 | repeated event via a link: A AND (A OR B) |
| F11 | repeated event via a transfer: OR(AND(A,B), AND(C, →A)) |
| F12 | lognormal uncertainty (median, mean, nominal; EF 2–10) on fixed and rate models |
| F13 | trace and FMEA blocks, RPN computed and given, data source |
| F14 | a mixed plant: every gate and model, links, transfer, house, uncertainty |
| F15 | stale `gateType` (KOFN with `logicGate` AND): dropped on load |
| F16 | `analysis` block with truncating limits (order 2, cutoff 1e-10) and an invalid key |
| F17 | missing model parameters (previous probability kept) |
| T01–T06 | textbook trees with published answers (below) |
| O01–O06 | small random coherent trees (8–14 events, links, KOFN, quant models) for the oracle |
| R00 | 400-event random legacy tree with link cycles (desktop comparison) |
| R01–R03 | 300 / 800 / 2000-event random 1.7 trees (performance, count truncation, the summary's 2 s budget) |

## Hand-computed answers (`expected.json`)

| Tree | Answer |
|---|---|
| T01 2oo3, p = 0.1 | 3p² − 2p³ = 0.028; cut sets {A,B},{A,C},{B,C}; MCUB 1 − (1 − p²)³ = 0.029701; rare-event 3p² = 0.03 |
| T02 the same as AND/OR with shared events | exact 0.028 (oracle), tree walk = MCUB = 0.029701, headline MCUB |
| T03 standby λ = 1e-4/h, τ = 720 h; rate λ = 1e-5/h, T = 1000 h | λτ/2 = 0.036; 1 − e^−0.01 = 0.00995017; top = 1 − (1 − 0.036)(1 − 0.00995017) |
| T04 AND(OR(.1,.2), OR(.3,.4)) | 0.28 × 0.58 = 0.1624; cut sets {A,C},{A,D},{B,C},{B,D}; MCUB 0.194698; rare 0.21 |
| T05 repairable λ = 1e-3, MTTR 10 h / μ = 0.1 | λ/(λ+μ) = 1/101 each; top (1/101)² |
| T06 OR(A = 0.01, AND(B = 0.1, C = 0.2)) | Q = 0.0298; Birnbaum_A = 1 − q_Bq_C = 0.98; Birnbaum_B = q_C(1 − q_A) = 0.198; FV, RAW, RRW from Q(q=0/1) |
| F10 A AND (A OR B) | exact 0.1 (= p_A), cut set {A}, tree walk 0.1 × 0.28 = 0.028 |
| F11 | cut sets {A,B},{A,C}; exact p_A(p_B + p_C − p_Bp_C) = 0.044; tree walk = MCUB = 0.0494; rare 0.05 |
| F03 | 2oo3 0.028, 1oo2 0.44, 3oo3 0.06, 2oo4 1 − P(0) − P(1) |
| F04 | XOR 0.1 + 0.2 − 2·0.02 = 0.26; 3-input parity P(1) + P(3) = 0.404 |
| F01, F02, T03, F13 | the model formulas by hand (rate, standby, repairable, FIT) |
| F12 | lognormal mean = median·e^(σ²/2), σ = ln EF / 1.645; an entered mean is the mean; series E = Ea + Eb − EaEb, parallel E = EcEd |
| L01–L16, F05–F09, F15, F17 | gate-by-gate by hand (see `make_corpus.py`) |

## Bugs found and fixed on this branch

1. **OR gates flushed tiny probabilities to zero** (`engine.py`): `1 − Π(1 − p)`
   cancels; OR(1e-17, 1e-17) = 0, OR(1e-15, 1e-15) = 1.998e-15. Now
   `engine.or_probability` (log space below 1e-3). Found: oracle (L08).
2. **Monte Carlo without uncertainty** reported mean ≠ point estimate and std
   ≈ 1e-18 (`uncertainty.py`, `fsum/n`). Now pivoted. Found: `mc` checks.
3. **Server-side number formatting ≠ the browser's** (`numfmt.py`): integer
   digits beyond the sig figs kept, `e+`, round-half-even. Found: `numfmt:js`.

## Intended divergences

| Tag | Where | What |
|---|---|---|
| D8, D14, D15, D16, D17 | `desktop` | fta_web/core/DIVERGENCE.md (the frozen desktop core rounds to 6 decimals, aliases duplicate ids, keeps the top id, saturates link cycles, cannot read minified JSON). Attributed per tree by the model, never waved through. |
| OR-LOG | `legacy_core`, `desktop` | WebCore 1.7.1 computes an OR below 1e-3 in log space; the 1.6 cores keep the cancelling product (differs by the precision they lose: up to 100 % below 1e-16, 2.3e-10 relative at 8e-7). |
| LIBM | `cli:py2`, `exe:*` vs the 3.10 engine | Different Python builds link different libm: `math.expm1(-0.030149)` is `…917` on 3.14 and `…913` on 3.10. MCUB, importance, Monte Carlo and log-space ORs then differ by a few ulp (max seen 3e-15 relative). The same build is bit-identical (`exe:*==src`). |
| FIXED:* | `release->branch`, `exe:*` | the three fixes above, relative to the 1.7.0 release the exe was built from. |
| TIME | summary on large trees | the headline's own 2 s cut-set budget can stop at different points in different processes (reported as `capped`/`truncatedBy: time`). |
| XLSX 16 digits | `api:*` `xlsx.*` | openpyxl writes floats with `%.16g` (≤ 5e-16 relative). |
| _tidy | `engine` | `probability = _tidy(q)` keeps 12 s.f., so `quantDerived.q` (unrounded) and the stored probability differ below 1e-11 relative; the MC tree evaluator does not `_tidy`, so its point estimate matches the tree walk to 1e-10 relative. |
| FRONTEND BUG | `numfmt:js` | `numfmt.js` picks the plain/exponent form from the unrounded magnitude (0.00099996 at 3 s.f. → `1.00e-3`; 9999.7 → `10000`); the user guide and the server use the rounded one (`0.00100`, `1.00e4`). Reported to the frontend. |
