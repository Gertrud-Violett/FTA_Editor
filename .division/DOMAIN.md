# Domain profile: mechanical engineering tools

Calculators, analysis and editing tools for engineers: beam, shaft and bolt calculations,
tolerance stack-ups, fault-tree and FMEA editors, unit-aware data tools, report generators.
Engineers act on these numbers, so a wrong result is worse than a missing feature.

## Specialist
`division-analyst` (opus, high): checks equations against their sources, units and
dimensions, edge cases, numerical stability, and that the tool states its assumptions. The
Director adds it to every feature that computes something, and to the final review.

## What counts as evidence
- Every formula cites its source (standard and clause, handbook and page, or a derivation in
  `docs/`). Tests reproduce at least one published worked example per formula, to stated tolerance.
- Units are explicit end to end (for Python, `pint` or a units layer); a dimensional-analysis
  test fails on mixed units. Inputs are validated with ranges and helpful messages.
- Edge cases: zero, negative, very large and very small values, singular geometry, empty
  models, NaN and inf never reach the UI silently.
- Numerical work: convergence criteria stated and tested; results stable under small input
  changes; float tolerances justified.
- Fault-tree, FMEA and reliability tools: reference models with known results (minimal cut
  sets, top-event probability) are regression tests; import and export round-trips are lossless.
- Performance requirements are measured on the stated model size, never estimated.

## Typical requirements
- UI: units shown next to every value; input errors next to the field; results exportable
  (CSV, PDF report with inputs, assumptions, sources, version and date).
- FN: each calculation with its standard; save, load and versioned file format; undo.
- PERF: solve time and memory at the largest model size the CEO cares about.

## CEO-only
Releasing a version to users, any claim of compliance with a standard, licence choices, and
removing a safety factor or warning. Results carry a "check by a qualified engineer" note
unless the CEO decides otherwise.

## Tools
Python: pytest, hypothesis for property tests, pint, numpy and scipy, matplotlib for plots
saved as test artifacts. Streamlit apps: `streamlit.testing.v1.AppTest` drives the UI headless
in pytest; add Playwright screenshots for layout checks. Desktop UI: whatever the repo uses;
screenshots saved under `.division/artifacts/` and looked at by the reviewer.
