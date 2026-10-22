# Analyst, spec v0.1 (F2/F2A) — VERDICT: FAIL (formulas correct; oracles and guards wrong)

Sources opened: [S1] NUREG/CR-5485 (1998) https://nrcoe.inl.gov/publicdocs/CCF/NUREGCR-5485_Guidelines%20on%20Modeling%20Common-Cause%20Failures%20in%20PRA.pdf ; [S2] NUREG/CR-4780 Vol. 2 (1989) https://www.osti.gov/servlets/purl/6564737 ; [S3] NASA/SP-2011-3421 2nd ed. https://ntrs.nasa.gov/api/citations/20120001369/downloads/20120001369.pdf . Not opened: NUREG/CR-4780 Vol. 1, NUREG/CR-6268 (do not cite with pages).

Formulas: beta S2 Table C-1 p. C-5, Eq. C.10-C.13 p. C-6; S1 Eq. 5.11-5.13 p. 42. Alpha non-staggered S1 Eq. 5.7-5.9 p. 41, S2 Eq. C.23-C.24 pp. C-10/11. Alpha staggered S1 Eq. 5.6 p. 40. FN-45 correct (staggered, m=2, α2=β; S1 p. E-2). Source errors not to copy: S1 p. 41 Eq. 5.10 Q3=3α3Qt (should be α3Qt); S1 Tables 5-4/5-5 m=4 rows swapped, Table 5-5 "2 of 5" stray /4. Derive from Eq. 5.6/5.7.

Findings: (1) FN-23 FV(CCF) must be 0.991965076374. (2) FN-24 MC oracle wrong: E[top] ≈ β·E[Qt] + (1-β)²·E[Qt²] (1.2696e-4 for median 1e-3, EF 3, β 0.1). (3) Qt near 1 lowers a certain failure (Qt=1, β=0.1: AND of 2 gives 0.829); add guards. (4) OQ-11 tree-walk gate value is ~100x non-conservative; show gate MCUB from cutsets._Expander.memo or no value. (5) Σα tolerance 1e-9 refuses published α sets (S1 Table 6-9 p. 104); accept |Σα-1| ≤ 1e-3 and normalise with a note. (6) Pre-pass must keep topological order (logic.py:138-143); build the OR in Structure.var at compile time, independent part keeps the member's slot. (7) MC: one draw per group; do not copy quant.unc onto the new events (uncertainty.py:263-273); β/α not sampled, say so; members need same model, parameters, uncertainty. (8) Overlapping same-group CCF pairs in 1-of-3: MOCUS keeps {C_AB, C_AC}; S1 Table E-2 p. E-4 lists 5 sets; difference 3Q2²; recommend keep (conservative) with a note. (9) Member under PAND/XOR: warning. (10) Fine: repeated members, groups across AND/OR, k-of-n, β=0/1, Qt=1e-12, unequal q refused. (11) Splitting Qt vs splitting λ (S3 p. D-20) agree only to first order in λT; state it.

No published numeric two/three-train top-event example found (S1 §6 AFW example is asymmetric and time-dependent). OQ-5 goes to the CEO.

Reference cases:
- AND of 2, Qt=1e-3, β=0.1: rare-event 1.0081e-4 (S1 Table 5-2 Case 1 p. 49; S3 Eq. 7-3 p. 7-5). Hand: MCUB 1.00809919e-4, FV(CCF) 0.991965076374, RAW(CCF) 9919.6588, RRW(CCF) 124.45669.
- OR of 2, same: 2Q1+Q2 = 1.9e-3 (S1 Table 5-2 Case 2 p. 49). Hand: MCUB 1.899010081e-3.
- Staggered m=2 α=(0.9,0.1), Qt=1e-3: CCF 1e-4 (S1 Table 5-4 p. 53) = beta case.
- Non-staggered m=2 α=(0.95,0.05): CCF 9.5238095e-5 (S1 Table 5-5 p. 54). Hand: Q1 9.0476190e-4, rare-event 9.6056689e-5, MCUB 9.6056611e-5.
- 2-of-3, α=(0.955,0.034,0.011) (S3 p. 7-16), Qt=1e-3, staggered: CCF part 6.2e-5 (S1 Table 5-4 p. 53); 7 cut sets (S1 Table E-2 p. E-4); 3Q1²+3Q2+Q3 = 6.4736075e-5 (S1 Table 5-2 Case 4 p. 49). Hand: MCUB 6.47344749e-5.
- Same non-staggered (αt=1.056): CCF part 1.27841e-4 (S1 Table 5-5 p. 54). Hand: rare-event 1.302945e-4, MCUB 1.302880e-4.
- 1-of-3 staggered: Q1³+3Q1Q2+Q3 = 1.10495760e-5 (S1 Table 5-2 Case 3 p. 49). Hand with overlapping pairs kept: 1.10504430e-5.
- MC hand only: median Qt 1e-3, EF 3, β 0.1, AND of 2: E[top] ≈ 1.2696e-4.

Required changes: citations above replace "to be verified"; FN-23 value; FN-24 oracle + per-trial ratio test; lint for differing model/parameters/uncertainty (not applied) and note β/α not sampled; lint Qt>0.01 warning, Qt=1 error, member under PAND/XOR warning; Σα tolerance 1e-3 normalised; no default testing scheme (S1 p. 40); OQ-11 gate MCUB or no value; compile-time expansion keeping order with a test; decide overlapping pairs (keep, with note); label member rows "independent part" and no component-level RAW; OQ-5 to the CEO.
