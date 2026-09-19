# Feature and UI proposals — making the editor useful to mechanical / reliability engineers

**Date:** 2026-09-19  ·  **Scope:** the web app (`fta_web/`), which is the primary path.
Companion document: [`CODE_REVIEW_2026-09.md`](CODE_REVIEW_2026-09.md) (defects found in
the same review; several of them block items below and are marked as such).

The proposals are grouped by what an engineer is trying to do, ranked within each
group, and summarised in a priority table at the end. Each item says what the tool
does today, what is missing, and roughly what it would take.

---

## 1. Quantification — the numbers engineers actually need

### 1.1 Minimal cut sets  (P0)

**Today:** the engine computes a single top-event probability by walking the tree
bottom-up. Nothing tells the user *which combinations of basic events* cause the top
event, which is the primary output of an FTA in practice (IEC 61025 §7, NUREG-0492 ch.
VII).

**Proposal:** compute minimal cut sets (MOCUS for trees of this size; a BDD backend
later for large ones), list them ranked by probability with each set's contribution to
the top event, show the top-N in a panel beside the diagram, and export them to the
Excel/JSON output. Clicking a cut set highlights its basic events in the tree and
diagram.

**Why this matters beyond reporting:** the current tree walk is only exact when every
basic event appears once. A basic event referenced from two places (today: a *link*
to the same node from two parents) is treated as two independent events, so the
top-event probability is over-counted. Cut-set quantification (with the rare-event or
min-cut-upper-bound approximation, user-selectable) handles repeated events correctly
and is the normal way tools solve this.

### 1.2 Importance measures  (P1)

Fussell–Vesely, Birnbaum, Risk Achievement Worth and Risk Reduction Worth per basic
event, derived from the cut sets (1.1). Colour the tree/diagram by FV importance so the
"where should I spend the next design hour" question is answered visually. Export as
a table.

### 1.3 Failure-rate inputs with mission time, not bare probabilities  (P0)

**Today:** every event carries one number, `probability ∈ [0,1]`, defaulting to 1.0.
Engineers mostly have a failure *rate* λ (per hour, from OREDA / NPRD / vendor data /
field returns) and a mission time or proof-test interval, not a probability.

**Proposal:** per basic event choose a quantification model and enter its parameters;
the engine derives the probability and shows the formula used:

| Model | Inputs | Probability used |
|---|---|---|
| Fixed probability (today) | q | q |
| Constant rate, mission time | λ, T | 1 − e^(−λT) |
| Periodically tested (standby) | λ, τ (test interval) | λτ/2 (average unavailability) |
| Repairable | λ, μ (or MTTR) | λ/(λ+μ) |
| Dormant with detection | λ, τ, coverage | as above with coverage factor |

Add a document-level default mission time, unit selection (h / y / cycles), and a
"source" free-text field per event so the data provenance is in the file. Store the
inputs; `probability` becomes derived (kept in the file for compatibility with the
legacy desktop app, which will keep reading it).

**Blocked by** the 6-decimal rounding defect (review item B-2): with rates around
1e-6/h, derived probabilities routinely fall below 5e-7 and are currently rounded to
zero at every gate.

### 1.4 Standard gate types  (P0)

**Today:** AND and OR only. NOT is rejected (correctly — see DIVERGENCE D5). A link's
AND/OR relation is a *post-gate* stage, which surprises people who expect a link to be
another gate input.

**Proposal:** add the gates the standards define and engineers reach for:

- **k-out-of-n (voting)** — essential for redundant trains (2oo3 sensors, 1oo2 pumps).
- **XOR** and **INHIBIT** (conditioning event) — common in safety cases.
- **Priority-AND** — sequence-dependent failures; can be quantified approximately.
- **NOT / complement** with an explicit "non-coherent tree" warning, since cut-set
  algorithms and importance measures change meaning.
- **Transfer-in / transfer-out** — split a large tree across pages/files and reference a
  sub-tree by ID instead of duplicating it. This is also the clean replacement for
  today's cross-links.
- **House events** (fixed true/false) to switch scenarios on and off without editing
  the tree, and **undeveloped events** (diamond) so an incomplete branch is visibly
  incomplete rather than silently quantified at 1.0.

Each of these needs an engine rule, a validation rule, a symbol (see 3.1) and an
export mapping; k-of-n and house events give the most value for the least work.

### 1.5 Common-cause failures  (P1)

Group basic events into a CCF group with a β-factor (or MGL/α-factor) model; the engine
adds the implied common-cause event to every cut set that contains members of the
group. Without this, redundant trains look far more reliable than they are, which is
the classic FTA mistake the standards warn about.

### 1.6 Uncertainty propagation  (P2)

Per basic event: a distribution (lognormal with error factor is the convention) instead
of a point value. Monte Carlo through the cut sets gives mean / median / 5–95 % bounds
on the top event. Display as a small histogram beside the top-event number.

### 1.7 Sensitivity and what-if  (P1)

- A slider or ±factor on any basic event with the top event updating live.
- "Scenario compare": open two saved files (or two revisions, see 2.4) side by side
  with a diff of structure and numbers, and a table of which basic events moved the
  result.

### 1.8 ETA improvements  (P1)

**Today:** ETA multiplies each branch's own probability by its ancestors', with no
normalisation and no notion of success/failure branches or consequences.

**Proposal:** model each pivot as a safety function with a failure probability p (often
imported from an FTA's top event) and success 1 − p, so branch probabilities under a
node sum to 1 by construction; attach a consequence category and, optionally, a
consequence value to each end state; produce the end-state frequency table and a
frequency × consequence risk matrix; and offer a **bow-tie view** that joins an FTA
(causes) to an ETA (consequences) through the shared top event. This is how most
process-safety and machinery-safety analyses are actually presented.

---

## 2. Data, workflow and reporting

### 2.1 FMEA / FMECA import and linking  (P1)

Most fault trees start from an FMEA worksheet. Import a CSV/XLSX of failure modes
(item, mode, cause, λ or occurrence, detection, RPN) as candidate basic events;
keep the FMEA row ID on the node so the two analyses stay traceable; re-import updates
numbers in place instead of creating duplicates.

### 2.2 Component library / templates with cited data  (P2)

Reusable sub-trees (pump train, PLC I/O channel, relief valve, sensor with 2oo3
voting) that drop in with default rates and a source citation, editable per project.
A per-project library file that ships alongside the analysis JSON keeps the data
provenance inside the repository the engineer actually controls.

### 2.3 Traceability fields on every node  (P1)

Requirement ID, test/inspection reference, owner, status (draft / reviewed /
approved), evidence link, and free tags. Filter and search by any of them in the tree
panel. This is what turns a diagram into a deliverable that survives an audit.

### 2.4 Revisions and reviews  (P2)

Revision number and history in the file's metadata; per-node review comments with
author and date; a diff view between two files (structure, numbers, gates) that can be
exported with the report. The existing 50-step undo is not a substitute for knowing
what changed between issue A and issue B of a safety case.

### 2.5 Report export  (P1)

One-click PDF/DOCX containing: diagram (paged for large trees), assumptions and
mission time, basic-event table with rates and sources, top-event result, cut sets
with contributions, importance table, revision history. The current Excel export is
a hierarchical sheet meant for reading; add a flat "event table" sheet (one row per
event: ID, name, gate, λ, T, q, calculated, source, tags) that engineers can pivot and
re-import.

### 2.6 Headless / batch use  (P2)

The web app already has a JSON API. Add a small CLI (`fta quantify tree.json`) that
prints or writes the top event, cut sets and importance for a file, so re-quantifying
fifty trees after a data update is a script, not fifty sessions.

---

## 3. Diagram and UI

### 3.1 Standard FTA symbols  (P0)

**Today:** every node is a two-row table box; the gate is a text line inside it. That
is readable but it is not what an engineer, reviewer or regulator expects to see.

**Proposal:** render each node as the standard symbol set — event rectangle above a
gate symbol (AND/OR/k-of-n/XOR/INHIBIT/PAND shapes), circle for basic events, diamond
for undeveloped, house for house events, triangle for transfer — with a legend, and a
**top-down** layout option in addition to the current left-to-right. Keep today's
table style as the "compact" alternative. Graphviz can draw all of these; the work is
in `json_viewer.build_dot` and the symbol glyphs (SVG images are simplest and
theme-able).

### 3.2 Working with large trees  (P1)

Collapse/expand a subtree in the diagram (not only in the tree panel); a focus mode
that shows the selected node with its ancestors and descendants; a minimap; search
that highlights matches in the diagram; and page-break hints for printing. Trees with
a few hundred events are normal in this field.

### 3.3 Table (grid) view of basic events  (P1)

A spreadsheet-like grid beside the tree — one row per basic event, editable cells for
name, λ/T/q, source, tags, with sort/filter and paste-from-Excel. Engineers enter and
check data in tables; the tree is for structure.

### 3.4 Number formatting and units  (P0)

Scientific notation with a user-chosen number of significant figures everywhere the UI
shows a probability (today: 6 fixed decimals in the engine, `%.1E` in the diagram,
raw floats in the details panel). Tied to review item B-2.

### 3.5 Validation ("lint") panel  (P1)

Continuously listed warnings: gate with a single input; basic event still at the
default 1.0; unquantified/undeveloped events; dangling or cyclic links; duplicate IDs;
a node whose own probability is ignored because it has children (today this is silent
and the value is still printed on the diagram); ETA branches not summing to 1. Click a
warning to jump to the node.

### 3.6 Editing ergonomics  (P2)

Tab / Shift-Tab to add a sibling / child (as in mind-map tools), Enter to rename,
duplicate-subtree, copy/paste between files, and inline editing of probability
directly in the diagram. Finish the Japanese localisation of the details panel and
dialogs (review item F-6) so the whole editing surface switches language together.

### 3.7 Help where the semantics are non-obvious  (P2)

An in-app explanation, next to the gate selector and the links editor, of exactly how
the engine combines children, AND-links and OR-links (they are applied in a fixed
order, not as gate inputs), why a parent's own probability is ignored once it has
children, and how ETA propagates. Today this is documented only in code comments and
`DIVERGENCE.md`, and every reviewer of this codebase re-derived it.

---

## 4. AI assistant

- **Grounded proposals:** when the assistant proposes basic events, ask it for a
  failure-rate range and a source class (handbook / vendor / field data / engineering
  judgement) and put them in the node's source field; keep the existing verify-before-
  apply flow.
- **Narrative from the numbers, not from the JSON:** "explain the dominant cut sets
  and what design change would reduce them most" is the question engineers actually
  ask; feed the assistant the cut-set and importance tables (1.1, 1.2) rather than the
  raw tree so its answers are about the analysis, not about JSON structure.
- **Review-mode checklist:** an "audit this tree" action that runs the lint rules
  (3.5) and asks the assistant only about the items the rules cannot decide (missing
  failure modes, implausible rates).

Fix review item F-1 (the Apply-selected index mismatch) before extending this area;
it can currently apply a proposal the user never saw.

---

## 5. Priority summary

| Priority | Item | Value | Effort |
|---|---|---|---|
| **P0** | 3.4 Number formatting / significant figures (with review B-2 rounding fix) | correctness | S |
| **P0** | 1.3 Failure-rate inputs with mission time | correctness, adoption | M |
| **P0** | 1.1 Minimal cut sets | core FTA output; fixes repeated-event over-count | M |
| **P0** | 1.4 Gate types: k-of-n, house, undeveloped, transfer (XOR/INHIBIT/PAND next) | modelling power | M–L |
| **P0** | 3.1 Standard FTA symbols + top-down layout | credibility with reviewers | M |
| P1 | 1.2 Importance measures | design decisions | S (after 1.1) |
| P1 | 1.5 Common-cause failure groups | correctness for redundancy | M |
| P1 | 1.7 Sensitivity / scenario compare | design decisions | M |
| P1 | 1.8 ETA normalisation, consequences, bow-tie | process/machinery safety | M–L |
| P1 | 2.1 FMEA import/link | workflow | M |
| P1 | 2.3 Traceability fields | audits | S |
| P1 | 2.5 Report export + flat event table | deliverables | M |
| P1 | 3.2 Large-tree navigation | usability | M |
| P1 | 3.3 Grid view of basic events | data entry | M |
| P1 | 3.5 Lint panel | error prevention | S–M |
| P2 | 1.6 Uncertainty (Monte Carlo) | rigour | M |
| P2 | 2.2 Component library | speed | M |
| P2 | 2.4 Revisions / review comments / diff | governance | M |
| P2 | 2.6 CLI / batch | automation | S |
| P2 | 3.6 Editing ergonomics, 3.7 in-app semantics help, JA completion | polish | S–M |

Effort: S ≈ days, M ≈ 1–3 weeks, L ≈ more, for one developer familiar with the code.

### Suggested order

1. Land the correctness fixes from the code review (rounding, HTML escaping, ID reuse,
   AI apply indices) — they undermine everything else.
2. 1.3 + 3.4 together (rates, mission time, formatting) — this is the change existing
   users will notice first.
3. 1.1 cut sets, then 1.2 importance on top of it.
4. 1.4 gates and 3.1 symbols together, since each new gate needs a symbol.
5. 2.5 reporting once there are cut sets and importance to report.
6. The rest by demand.

### What this does *not* propose

- Back-porting any of it to the legacy desktop app in `desktop/`, which is frozen.
- A multi-user server. The single-process, loopback-only design is a deliberate
  security choice; collaboration should happen through files and revisions (2.4), not
  shared sessions.
