# Spec critic, round 1 (v0.1) — VERDICT: NOT READY

Blockers
1. Phase 2 build work traces to the brief only via OQ-7 ("plan the next features" ≠ build). CEO must answer OQ-7 before approval.
2. FN-28/G3 byte-identical CLI output cannot pass: `elapsedMs` (engine.py:830), MC time limit (cli.py:110, uncertainty.py:364/406). Compare without a named list of volatile keys; fixed --n, large --time-limit, assert truncatedByTime false; name the corpus (fta_web/examples + b2b corpus).
3. Formulas with "page to be verified" and FN-19(b) without a test; OQ-5 fallback waives DOMAIN's published-example rule, which only the CEO can do. Analyst verifies first; else ask for the waiver in plain words.
4. Headline fallback to the tree walk (engine.py:744, 801-805) would show a CCF-free number; `may_need_cut_sets` (engine.py:871) false for a CCF tree. Add an FN: incomplete runs shown as "CCF not included"; may_need_cut_sets true when a group applies.
Major
5. FN-23 expected FV wrong for the code's definition (importance.py:8,145): 0.9919651, not 0.9919659.
6. Member meaning after expansion (id, label, q shown, importance of component vs independent part) unspecified.
7. FN-24 MC test wrong (median vs mean; std 0 with no uncertainty); per-group draw is a new correlated sampler. Decide OQ-10 before freeze.
8. Data loss: coerce_analysis drops unknown keys (engine.py:230-261), so 1.8.x drops ccfGroups; bad β could drop a group; duplicate-id renames break members. Keep invalid groups flagged "not applied"; remap members; file-format version key.
9. Not-applied groups reported in GUI only: CLI exit 0, report silent. Add CLI block + exit 1 and a DOCX line.
10. Grid paste by row/column index lands on wrong events with sort/filter; many paste cases undefined. Address by node id + column key + revision (409).
11. Paste parser differs from the Add dialog parser. One parser everywhere; decide the comma rule once.
12. What-if leaks: report, Excel/CSV, diagram export, Copy CSV, recovery copy, AI context untested.
13. What-if factor should scale λ (main parameter), not q; define the clamp.
14. PERF numbers conflict (PERF-8 vs FN-56 vs PERF-2), conditions unclear, no committed fixture.
15. Goals G2, G4, G5 depend on "should" items.
16. "Check by a qualified engineer" note: DOMAIN wants it on every result; OQ-9 narrows it and no FN implements it.
Minor
17. FN-4 premise false (suite does not break); keep the edit, fix the reason.
18. Missing lint cases (Q_t=0, q None, members under XOR/PAND/INHIBIT, different EF).
19. FN-38 covers UI delete only; other membership changes (add child, AI update, FMEA re-import, batch delete).
20. Grid read-only column behaviour, units for T/τ/μ, tags separator unspecified.
21. No FN builds the zip; hash the local zip.
22. PERF-1 should be a recorded measurement; state who merges into integration.
23. FN-64 grep for "compl" too broad.
24. Size: merge to about 50 (list in the critic's reply: release notes checklist, manual check, lint table, constraints), cut FN-27, UI-13, FN-63 and F5; F2A candidate to defer.
