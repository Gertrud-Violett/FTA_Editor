# Research R2: next roadmap features (spec researcher, 2026-10-22)

Status: the 1.8.0 round and the known-issue fixes closed no roadmap item. Open: 1.3 (dormant/coverage), 1.4 (transfers across files; NOT gate rejected by DIVERGENCE D5), 1.5 CCF (no code), 1.7 sensitivity (none; importance.py `with_value` re-evaluates MCUB on a changed q and can be reused), 1.8 ETA (no normalisation; ETA walk is in the pinned core, so a new module beside it), 2.2 library, 2.4 revisions (state.revision is a page counter only), 2.5 report (DOCX only), 3.2 large trees, 3.3 grid (copy CSV only, no editable grid or paste), 3.6 ergonomics (no Tab/Shift-Tab, duplicate subtree, copy/paste), 3.7 semantics help, 4 AI (unknown).

Recommended order: 1) 1.5 CCF, beta factor first, alpha for groups of 2-4 later (M); as a pre-pass on the compiled Structure before MOCUS so cut sets, MCUB, importance, Monte Carlo and the report all see it, no core edit. 2) 3.3 grid with paste from Excel (M), reusing the one probability validator, one undo step. 3) 1.7 sensitivity sliders on a copy (S-M); scenario compare deferred with 2.4. 4) 3.7 help + 3.6 Tab/Shift-Tab, duplicate subtree (S each). 5) 2.5 PDF or 1.8 ETA normalisation (M). Defer 2.4, 2.2, 3.2, 4.

Sources (page numbers NOT verified; the NRC PDF fetch failed): NUREG/CR-4780 vol. 1-2 (beta, BFR, MGL); NUREG/CR-5485 (alpha factor; appendix two-train example); NUREG/CR-6268 (data); NUREG-0492; IEC 61025; IEC 61508-6 Annex B (periodic test).
Beta: Q_ind = (1-β)Q_t, Q_ccf = βQ_t. Hand check (not published): Q_t=1e-3, β=0.1, two under AND: 8.1e-7 + 1e-4 ≈ 1.0081e-4.
Alpha, non-staggered: Q_k = k/C(m-1,k-1) · (α_k/α_t) · Q_t, α_t = Σ k·α_k; staggered: Q_k = α_k/C(m-1,k-1) · Q_t.

Candidate requirements: CCF groups (model, parameter source, test scheme) flowing through every analysis and the report; no core change and byte-identical results without groups; validation (β, α in [0,1], Σα=1, members are basic events with equal q, else lint error); results state assumptions, no compliance claim. Grid paste: one validator, one undo step, bad rows reported. What-if: on a copy, Reset leaves the file byte-identical.
Open: NOT gate (rec. no, keep D5); beta only first, alpha later (rec.), analyst to verify formulas and pages before freeze; live AI test (rec. defer).
