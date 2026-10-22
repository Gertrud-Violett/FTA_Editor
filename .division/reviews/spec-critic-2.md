# Spec critic, round 2 (v0.2) — VERDICT: NOT READY (2 blockers by count in reply: 3 marked blocker, 5 major, 4 minor)

Round 1: all resolved except 8 data loss (partly; K4), 11 one parser (not resolved), 14 PERF (partly). Analyst changes: all resolved; R1h, R2h, R6, R11, FN-55, FN-56 re-derived correct.

1. [blocker] FN-46 one parser is false: λ/T/τ/μ use parseNumber (analysis_common.js:171, quant.js:218), FMEA uses cellNumber (fmea.js:111); they disagree on 1e-400, 5%, 1/1000, 1,500E-06. Moving fields to one parser changes existing behaviour without a test. List every entry path; non-probability columns' rule stated; tests in number_inputs.json.
2. [blocker] FN-46/FN-32 server side untestable: validate_quant refuses strings, _validate_probability (routes/tree.py:182) uses float(text) ("0.0_1" → 0.01); Flask get_json reads 1e-400 as 0 and accepts NaN/Infinity. New endpoints: JSON numbers only, named validators, tests with number/string/NaN/Infinity/out of range; drop 1e-400 from API tests or strict parse_float.
3. [blocker] PERF-2 fixture perf_ccf_301.json: cut sets of order ≥19 exceed maxOrder 6 (engine.py:107), always truncated; groups under S1 never reach a cut set. Set fixture maxOrder/cutoff, re-derive, place groups so CCF events appear.
4. [major] PERF-2,5,6,7,8 unmeasured but frozen. Measure baselines before approval or mark provisional until a named spike with CEO consent.
5. [major] K4: fileFormatVersion does nothing for 1.8.x. Do not add key preservation to 1.8.1 (does not trace). New OQ: CEO accepts residual risk; pin the 1.8.1 warning text; 1.9.0 notes requirement as an FN.
6. [major] Release commit undefined: define tested integration commit → Katey's merge without rewriting → build and tag on that exact commit, hash recorded.
7. [major] Go-ahead gate: record format, Phase 2 PLAN.md allowed before go-ahead, partial go-ahead; OQ to confirm F5 cut and F2A droppable on budget.
8. [major] FN-18: loading a file with groups must give no analysis_invalid warning (coerce_analysis, engine.py:490-498).
9. [minor] FN-3 line 1880, not 1883.
10. [minor] FN-21 label must carry the truncation note.
11. [minor] FN-26/UI-1: CCF groups in ETA mode unspecified.
12. [minor] 7.1 vs K4 on desktop/ (desktop drops the whole analysis key on save).
Traceability: all trace, except FN-46's spill into existing fields.
