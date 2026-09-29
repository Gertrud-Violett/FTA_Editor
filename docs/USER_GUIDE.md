# FTA/ETA Editor - User Guide

**Version**: 1.7.0 | **Updated**: September 28, 2026

Complete guide for using the Fault Tree Analysis and Event Tree Analysis Editor with AI Assistant.

> **New in 1.7:** failure-rate models, standard gate types, minimal cut sets,
> importance measures, Monte Carlo uncertainty, validation, traceability, FMEA
> import, a DOCX report and a command-line interface. They are described in
> [Analysis features (1.7)](#analysis-features-17). Most of them are behind the
> **Advanced** switch in the top bar; see
> [Basic and Advanced mode](#basic-and-advanced-mode).

## Table of Contents

- [Getting Started](#getting-started)
- [Understanding FTA vs ETA](#understanding-fta-vs-eta)
- [User Interface](#user-interface)
- [AI Assistant](#ai-assistant)
- [Working with Nodes](#working-with-nodes)
- [Probability Calculations](#probability-calculations)
- [Analysis features (1.7)](#analysis-features-17)
  - [Basic and Advanced mode](#basic-and-advanced-mode)
  - [Significant figures](#significant-figures)
  - [The bottom tabs](#the-bottom-tabs)
  - [Quantification models](#quantification-models)
  - [Gate and event types](#gate-and-event-types)
  - [Top-event value: tree walk, MCUB and rare-event](#top-event-value-tree-walk-mcub-and-rare-event)
  - [Minimal cut sets](#minimal-cut-sets)
  - [Importance measures](#importance-measures)
  - [Uncertainty (Monte Carlo)](#uncertainty-monte-carlo)
  - [Validation](#validation)
  - [Traceability and tree search](#traceability-and-tree-search)
  - [FMEA import](#fmea-import)
  - [Report (DOCX) and Excel sheets](#report-docx-and-excel-sheets)
  - [Diagram styles and layout](#diagram-styles-and-layout)
- [Command-line interface](#command-line-interface)
- [Desktop app compatibility](#desktop-app-compatibility)
- [Export Options](#export-options)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)

## Getting Started

### Installation

The **web app is the primary way to run the editor**; see the root
[README](../README.md#quick-start):

```bash
uv sync --extra web --extra excel --extra ai --extra report
uv run python fta_web/run.py
```

`--extra report` installs `python-docx` for the DOCX report; `--extra all`
includes it. Without it everything else works and the report controls explain
what is missing.

The original Tkinter desktop app is kept in `desktop/` as a **legacy backup /
fallback**. It is frozen (no new features, no fixes) and needs Tk, Graphviz
and Pillow:

```bash
uv sync --extra desktop --extra excel --extra ai
# pip install -r requirements.txt

uv run python desktop/src/FTA_Editor_UI.py
# python desktop/src/FTA_Editor_UI.py
```

### First Launch

When you first launch the application, you'll see:
1. **Top Bar** - Mode selector, Title, and Date fields
2. **Tree View** - Left panel showing your analysis tree
3. **Diagram Preview** - Center panel with live visualization
4. **AI Assistant** - Right panel for AI-powered analysis
5. **Node Details** - Bottom panel showing selected node information
6. **Action Buttons** - Bottom toolbar for all operations

## Understanding FTA vs ETA

### FTA (Fault Tree Analysis) - Bottom-Up

**Purpose**: Analyze how component failures lead to system failure

**Calculation Direction**: Children → Parent

**Example Use Case**: "What causes the system to fail?"

```
System Failure (Parent calculated from children)
├─ Component A Fails (0.1)
├─ Component B Fails (0.2)  } → Parent probability calculated
└─ Component C Fails (0.15)     from these children
```

**When to Use FTA**:
- Reliability engineering
- Root cause analysis
- Failure mode analysis
- Quality control

### ETA (Event Tree Analysis) - Top-Down

**Purpose**: Analyze possible outcomes following an initiating event

**Calculation Direction**: Parent → Children

**Example Use Case**: "What happens if this event occurs?"

```
Initiating Event (0.001)
├─ Path A (0.9) → Calc: 0.001 × 0.9 = 0.0009
│  ├─ Outcome A1 (0.8) → Calc: 0.0009 × 0.8 = 0.00072
│  └─ Outcome A2 (0.2) → Calc: 0.0009 × 0.2 = 0.00018
└─ Path B (0.1) → Calc: 0.001 × 0.1 = 0.0001
```

**When to Use ETA**:
- Safety analysis
- Accident sequence analysis
- Risk assessment
- Consequence modeling

## User Interface

### Top Bar

```
┌──────────────────────────────────────────────────────────┐
│ Mode: [FTA ▼]  Title: [My Analysis]  Date: [2025-10-31] │
└──────────────────────────────────────────────────────────┘
```

**Mode Selector**:
- Switch between FTA and ETA modes
- Probabilities recalculate automatically
- Tree label updates accordingly

**Title Field**:
- Name your analysis
- Saved with JSON file
- Helps organize multiple analyses

**Date Field**:
- Document when analysis was performed
- Free-text format
- Saved with JSON file

### Tree View

- Hierarchical display of your analysis
- Color-coded by depth level
- Click to select nodes
- Shows node names
- Red asterisk (*) marks zero-probability nodes

### Diagram Preview

- Live visualization using Graphviz
- Pan: Click and drag
- Zoom: Ctrl + Mouse Wheel, or the **−** / **+** buttons (the percentage
  between them shows the current level)
- Updates automatically when tree changes

### Appearance (web UI)

These controls are in the browser version of the editor. Both remember your
choice in the browser, so they survive a reload without being saved into your
`.json` document — they are display preferences, not analysis data.

#### Dark Mode

The **◐** button in the top bar, next to the language switcher, cycles the
theme. It follows your operating system's light/dark setting until you press
it, after which your explicit choice wins.

The diagram follows the theme too: the background and the tree connector lines
switch with it. Two things deliberately stay the same in both themes —

- **Node boxes** keep their light background colours, because those colours
  carry meaning rather than styling (see the table below).
- **Link edges** stay blue, because colour is how a cross-tree link is told
  apart from a normal parent/child edge.

#### What the Node Colours Mean

A node box is shaded by its **calculated** probability (`P_calc`, the lower
line in the box), not the value you typed:

| Colour | Calculated probability | Reading |
|---|---|---|
| **Pink** | exactly `1.0` | Certain. Often a sign that an OR gate has saturated, or that a probability was entered as a percentage by mistake |
| **Light blue** | exactly `0.0` | Impossible, and contributes nothing to its parent. These are also the nodes the **Hide Zero** checkbox removes |
| **Light yellow** | `≥ 0.7` | High — worth attention when reading the tree |
| **White** | everything else | Nothing flagged |

The same colours are used in the browser, in a native Graphviz render, and in
exported PNG/SVG, so a diagram you send to someone else reads the same way it
does on screen.

#### Box Sizing (font detection and scale)

If text crowds or spills outside its node box, open the **Aa** popover on the
diagram panel's toolbar. (The popover can be dragged to a new position if it
covers something you need to see; it stays where you put it.)

**Why this exists:** the diagram is laid out by Graphviz, which sizes each box
from its *own* estimate of the named font's metrics, and then your browser
paints the text with whatever font it actually resolves that name to. If the
requested font is not installed, the browser silently substitutes one with
different glyph widths, and the text no longer fits the box that was measured
for the other font. This is most visible with Japanese text, where glyph widths
vary the most.

**Font**: leave it on **auto-detect** (the default) and the editor probes which
of its candidate fonts your system actually has — Meiryo first, then Yu Gothic,
Hiragino, Noto Sans CJK JP and others, ending in a generic fallback. Both sides
then agree on a font that really exists on your machine, which closes most of
the gap. You can also pick a specific font if you prefer one.

**Box scale**: the escape hatch for whatever mismatch is left. It accepts
**0–30** and defaults to **4**. Raising it inflates font size and padding
together, which is what grows the box — a box has no size of its own beyond
what its label needs. Raise it a step at a time until the text sits
comfortably.

> If the diagram looks right in the browser but wrong in an exported PNG, see
> [CJK_RENDERING.md](CJK_RENDERING.md): a native Graphviz install renders the
> export and may have a different set of fonts available than your browser
> does.

### Node Details Panel

In the web app the node details are the **Details** tab of the bottom panel.
They show the selected node's information:
- Name
- Type (Root, Event, Gate, etc.)
- Base Probability
- Calculated Probability
- Gate: AND/OR in basic mode. In advanced mode it also offers k-out-of-n,
  XOR, INHIBIT, Priority-AND and Transfer, and a leaf has an event kind (see
  [Gate and event types](#gate-and-event-types)).
- Notes
- Links to other nodes

Probabilities are shown with the chosen number of
[significant figures](#significant-figures). If a quantification model other
than *fixed* derives the probability, it is shown read-only; you edit the
model in the **Quantification** tab.

## AI Assistant

The AI Assistant provides intelligent analysis and suggestions for your fault trees using OpenAI-compatible APIs.

### Setup

1. Click the **⚙ (Settings)** button in the AI Assistant panel
2. Enter your API credentials:
   - **API Key**: Your OpenAI or compatible API key
   - **API Endpoint**: `https://api.openai.com/v1` (default) or your custom endpoint
   - **Model**: Select gpt-4o, gpt-4o-mini, or other models
3. Click **Test & Save** to verify and store credentials

> **Security**: Credentials are stored locally at `~/.fta_editor/ai_credentials.json`, never in the repository.

### Where Your API Key Is Stored

- **Location**: `~/.fta_editor/ai_credentials.json` -- that is, a folder named
  `.fta_editor` in your own user home directory (`C:\Users\<you>\.fta_editor\`
  on Windows, `/home/<you>/.fta_editor/` or `/Users/<you>/.fta_editor/` on
  Linux/macOS). This is the same file whether you run the desktop editor or
  the web UI (`fta_web`), so setting it up once covers both.
- **Format**: a plain JSON file containing the provider name, the API key,
  the endpoint and the selected model. It is **not encrypted** -- treat it
  like any other file that holds a secret, and rely on your OS user account
  and disk permissions to keep it private.
- **Scope**: local to this machine only. The key never leaves your computer
  except in the direct request the AI Assistant makes to the provider you
  configured (OpenAI, Anthropic or Google); it is never sent anywhere else,
  written into a saved `.json` analysis file, or committed to the
  repository.
- **Removing it**: click the **⚙ (Settings)** button in the AI Assistant
  panel and use **Clear** to delete the stored key (this removes the file).
  You can also delete `ai_credentials.json` by hand while the editor is
  closed.

### Features

**Quick Actions**:
- **Analyze FTA**: Posts analysis and suggestions to chat only (no changes applied).
- **Update FTA**: AI generates a complete updated JSON, validates it, and replaces the current tree. Existing nodes are preserved; only additions are applied. Detailed error logs are shown if the AI output is invalid.
- **Clear Chat**: Reset conversation history

**Free Chat**:
Type any question in the input box and press Enter. Examples:
- "What root causes might be missing from this failure mode?"
- "Can you review the probabilities in this tree?"
- "What are common causes of pump failures?"

### Applying Changes

- Use **Analyze FTA** for a safe review-only mode.
- Use **Update FTA** to apply all additions at once: the AI returns a full JSON which is verified before replacing your current tree. If the JSON is invalid, the update is rejected and the problematic section is shown in the chat and console.

### Status Indicator

- **● (Green)**: AI is configured and ready
- **○ (Gray)**: AI not configured - click ⚙ to set up

## Working with Nodes

### Adding a Node

1. Select parent node in tree
2. Click "Add Node" button (or press Ctrl+A)
3. Fill in node details:
   - **Name**: Descriptive name
   - **Type**: Event, Gate, etc.
   - **Probability**: Base probability (0.0-1.0)
   - **Logic Gate**: AND or OR (for nodes with children)
   - **Notes**: Optional description

### Editing a Node

1. Select node in tree
2. Click "Edit Node" button (or press Ctrl+E)
3. Modify any fields
4. Save changes

### Deleting a Node

1. Select node in tree
2. Click "Delete Node" button (or press Ctrl+D)
3. Confirm deletion
4. All children are also deleted

In the web app, links and transfer targets (`transferTo`) that pointed into
the deleted branch are removed as well and listed in the Validation tab
(`LINKS_REMOVED`); a transfer gate left without a target counts as 0. The
same happens when the AI assistant deletes nodes.

### Node Linking

**Create Link Between Nodes**:
1. Edit the node where link originates
2. Add link in the "Links" section
3. Select target node
4. Choose relationship: AND or OR

**Link Relationships**:
- **AND Link**: Both nodes must occur (multiply probabilities)
- **OR Link**: At least one occurs (union formula)

## Probability Calculations

### FTA Mode Calculations

**For Leaf Nodes** (no children):
```
Calculated Probability = Base Probability
```

**For Nodes with Children**:

AND Gate:
```
Calculated = Product(Child1, Child2, ...)
```

OR Gate:
```
Calculated = 1 - Product((1-Child1), (1-Child2), ...)
```

Once a node has children, its own (base) probability is **not used**. The
Validation tab reports a gate whose entered value differs from the calculated
one (`PARENT_PROBABILITY_IGNORED`).

**With Links**:
1. Calculate from children (if any)
2. Apply AND links: multiply
3. Apply OR links: union formula

Links are applied *after* the gate, in that fixed order. They are not extra
gate inputs.

The advanced gate types (k-out-of-n, XOR, INHIBIT, Priority-AND, Transfer) and
the failure-rate models are described in
[Gate and event types](#gate-and-event-types) and
[Quantification models](#quantification-models).

### ETA Mode Calculations

**For All Nodes**:
```
Child Calculated = Parent Calculated × Child Base
```

Flows top-down from root to leaves.

### Zero Probability Nodes

Nodes with zero probability are marked with red asterisk (*) in tree view.

**Common Causes**:
- Base probability set to 0.0
- In FTA: child with 0.0 probability in AND gate
- In ETA: parent has 0.0 calculated probability

## Analysis features (1.7)

Everything in this section is in the **web app** only. The legacy desktop app
is frozen and has none of it; see
[Desktop app compatibility](#desktop-app-compatibility) for what happens when
it opens a 1.7 file.

Most of the analysis features (all but validation) work on **fault trees**
(FTA mode). In ETA mode the analysis tabs show a notice, and the API returns
`409 MODE_UNSUPPORTED`.

### Basic and Advanced mode

The top bar has an **Advanced** switch. It is **off** by default, and the
choice is remembered per browser (`localStorage` key `fta.advanced`). It is
not saved in the document.

The switch only changes what the UI **shows**. The calculations, the files
and the API are identical in both modes, and switching never changes or
removes data.

| | Basic (switch off) | Advanced (switch on) |
|---|---|---|
| Bottom tabs | **Details** and **Validation** | all nine tabs |
| Gate selector | AND / OR | AND, OR, k-out-of-n, XOR, INHIBIT, Priority-AND, Transfer |
| Event kind (leaves) | hidden while it is *basic* | basic, house, undeveloped, conditioning |
| Probability entry | typed directly | typed directly, or derived from a model in the Quantification tab |
| Headline MCUB badge, FV overlay | hidden | shown |
| Report, FMEA import | hidden | available |

Basic mode is meant for junior engineers and quick edits. The Validation tab
stays visible in basic mode because it catches the most common mistakes.

**Advanced content in basic mode.** If a file already uses an advanced gate,
event kind or model, basic mode still shows it. The value appears read-only
with a small **advanced** chip and the hint "Switch on Advanced in the top bar
to edit it". Nothing is hidden silently, and saving in basic mode keeps every
advanced setting.

### Significant figures

The **Sig. figs** selector in the top bar sets how many significant figures
are used to display probabilities: 1 to 6, default 3. It is a per-browser
preference (`fta.sigFigs`) and is not saved in the document. It applies to the
node details, tree, diagram (`P:` / `P_calc:`), headline and every analysis
tab, and it is sent with the report and diagram requests.

The format follows JavaScript's `toPrecision`:

- Trailing zeros are kept, so 0.5 at 3 figures is `0.500`.
- Exponent form is used when the rounded magnitude is below 1e-3 or at least
  1e4: `1.00e-7`, `2.35e-4`.
- `0` is shown as `0`, and a missing value as `—`.

The CLI (`--sig-figs`), the DOCX report and the Excel number formats use the
same rules.

> **Fixed in 1.7:** before 1.7 the node details rounded to six decimals, so a
> realistic component probability such as 1e-7 was displayed as `0`. The
> stored value was always correct; only the display was wrong.

Stored values are never rounded to the display precision. The engine keeps
12 significant figures.

### The bottom tabs

The bottom panel is a tab strip. The last tab you used is remembered
(`fta.bottomTab`). A tab loads the first time it is shown, and it refreshes
when you return to it after the tree has changed.

| Tab | Mode | Purpose |
|---|---|---|
| **Details** | basic | The selected node: name, type, probability, gate, event kind, notes, links. |
| **Quantification** | advanced | The mission time, and the selected event's model (fixed / rate / standby / repairable), parameters, data source and uncertainty. Also a table of all basic events. |
| **Cut Sets** | advanced | Minimal cut sets ranked by probability, with their share, MCUB, rare-event and tree-walk values. Click a row to highlight its events. |
| **Importance** | advanced | Fussell-Vesely, Birnbaum, RAW and RRW per event. An optional FV colour overlay on the diagram. |
| **Uncertainty** | advanced | Monte Carlo on the lognormal parameter uncertainties: mean, median, 5th and 95th percentiles, standard deviation and a histogram. |
| **Validation** | basic | Issues found in the tree, each with a plain-language message and a one-line fix. Click an issue to jump to its node. |
| **Traceability** | advanced | A grid of requirement, test reference, owner, status, evidence and tags for every node, edited in place. |
| **FMEA** | advanced | Import failure modes from a CSV or XLSX sheet as basic events, with column mapping and an occurrence-rank table. |
| **Report** | advanced | Generate the DOCX report, export Excel (with the Events and Analysis sheets), or export an events CSV. |

**Quantification tab.**

1. *Document settings*: set the mission time and pick a display unit (hours,
   days or years). It is always stored in hours; the tab shows "stored as
   N h".
2. *Selected event*: select a basic event in the tree, then choose its model
   and enter its parameters. Choose the λ unit (/h, /y or FIT) from the
   selector next to λ; that choice is remembered per browser. T, τ and MTTR
   are entered in hours. The tab shows the derived probability, the formula
   used and any model warning.
3. *Basic events*: a table of every basic event with its model, uncertainty
   and probability. Click a row to select that event.

Gates, house events and transfers cannot be quantified here. The tab tells you
why.

**Cut Sets tab.** The tab runs when first shown, and again, after a short
delay, whenever the tree changes while it is visible. The limit fields (*Max
order*, *Max count*, *Cutoff*) start with the document settings; change them
to override the limits for one run (a blank field also uses the document
setting, shown as a hint). **Save as document defaults** stores the three
limits in the document (`analysis.cutsets`). That is what the Importance tab,
the headline, the Validation tab, the report and the CLI use. Saving marks the
document as modified and can be undone. *Show* limits how many rows are
listed; the totals always cover every cut set. **Copy CSV** copies the list to
the clipboard. Clicking a row outlines its events in the tree and the diagram;
leaving the tab clears the highlight. The badges above the table report
truncation, repeated events, non-coherence (XOR) and approximations. When the
tree has a Priority-AND gate, a badge says **PAND treated as AND in cut sets
(conservative)**.

**Importance tab.** A sortable table of FV, Birnbaum, RAW and RRW, together
with each event's q and the number of cut sets it appears in. **Colour diagram
by FV** shades the events in the diagram on a sequential scale and adds a
legend. While the overlay is on, each tree row also gets a small bar in the
same colour scale, so the ranking is visible in the tree as well. Click a row
to select the event.

**Uncertainty tab.** Enter the number of samples (up to 100,000), an optional
seed and a time limit (up to 60 s), then press **Run**. The samples and seed
start with the document settings (`analysis.mc`). **Save as document
defaults** stores them in the document (a blank seed means a random seed);
this can be undone. A run never starts by itself. An elapsed-time counter shows progress, and only one run can be in
progress at a time. See [Uncertainty (Monte Carlo)](#uncertainty-monte-carlo).

**Validation tab.** Issues are grouped by severity: error ✖, warning ⚠ and
info ℹ. Each shows the node, a message and a fix. The list refreshes when you
open the tab, when you press **Re-check**, and shortly after each edit.
**Dismiss session notices** hides the current load-repair and removed-link
notices; new ones still appear. See [Validation](#validation).

The **Validation** tab button carries a count badge, in basic mode too. It is
red with the number of errors when there are any, amber with the number of
warnings otherwise, and absent when the tree is clean. The badge refreshes
shortly after each change, so you see problems without opening the tab.

The toasts that report a load repair, or links removed by a delete (including
a multi-select delete), have a **Show in Validation** button that opens the
tab.

**Traceability, FMEA and Report tabs** are described in their own sections
below.

### Quantification models

Each basic event can carry a quantification model in its `quant` block. The
model **derives** the event's probability `q`. The derived value is written
back to the node's `probability`, so every other reader, including the legacy
desktop app, sees a meaningful number.

**Units.** λ (failure rate) and μ (repair rate) are always stored **per
hour**. T, τ and MTTR are stored in **hours**. The UI converts for display:

- 1 /y = 1/8760 /h
- 1 FIT = 1 failure per 10⁹ h = 1e-9 /h
- Mission time can be shown in days (24 h) or years (8760 h)

| Model | Inputs | q | Use it for |
|---|---|---|---|
| **fixed** | q | q as entered | Probabilities you already have (demand failure probabilities, human error, judgement) |
| **rate** | λ, T (default: mission time) | 1 − e^(−λT) | A non-repaired component that must survive a mission of length T |
| **standby** | λ, τ (test interval) | min(1, λτ/2) | A periodically proof-tested standby component: the time-average unavailability |
| **repairable** | λ, and μ or MTTR (μ = 1/MTTR) | λ/(λ+μ) | A revealed failure repaired on detection: the steady-state unavailability |

Notes for reliability engineers:

- **Mission time.** A rate event with no own T uses the document's mission
  time (default 8760 h, i.e. one year). Changing the mission time requantifies
  every such event and is one undo step.
- **Standby λτ/2** is the first-order approximation of the average
  unavailability of a periodically tested component. It assumes λτ ≪ 1. When
  **λτ > 0.2** the approximation is poor (the exact average is
  1 − (1 − e^(−λτ))/(λτ)), and the event is flagged `STANDBY_LARGE_LT`. The
  model also ignores test duration, test-caused failures and imperfect test
  coverage. Shorten τ, or model the event with the rate model over the
  interval, if that matters.
- **Repairable** gives the steady-state unavailability. It does not give the
  probability of failing *at least once* during the mission; for that, use the
  rate model. If both μ and MTTR are entered, μ wins.
- **Missing parameters.** If a model's parameters are missing or invalid, the
  event keeps its previous probability, and Validation reports
  `QUANT_PARAM_MISSING` as an error.
- **Data source.** The free-text *Data source* field (`quant.source`) keeps
  provenance, such as "OREDA 2015 p. 123" or "vendor data sheet", in the file.
  It is exported in the Excel **Events** sheet (`Source` column).

### Gate and event types

The gate is stored in `gateType`. The legacy `logicGate` field (AND/OR) is
always kept as the nearest AND/OR **projection** of it, so older readers still
get the closest coherent answer.

| Gate | Symbol (standards view) | Probability (inputs p₁…pₙ, independent) | `logicGate` projection | Notes |
|---|---|---|---|---|
| **AND** | flat-bottomed "D" | Πpᵢ | AND | |
| **OR** | curved shield | 1 − Π(1 − pᵢ) | OR | |
| **k-out-of-n** (`KOFN`) | OR shield with `k/n` | P(at least k of n) by exact Poisson-binomial sum | OR | Voting logic such as 2oo3 sensors. `k` must satisfy 1 ≤ k ≤ n. |
| **XOR** | OR shield with a second base line | p₁ + p₂ − 2p₁p₂ | OR | Exactly one of two. Makes the tree **non-coherent**. With more than 2 inputs it is evaluated as odd parity and flagged. |
| **INHIBIT** | hexagon | p(input) × p(condition) | AND | Exactly two inputs: one ordinary input and one child whose event kind is *conditioning*. Any other shape is still evaluated as AND and flagged `INHIBIT_ARITY`. |
| **Priority-AND** (`PAND`) | AND with an inner bar | Πpᵢ / n! (approximation) | AND | See below. Always flagged `PAND_APPROX`. |
| **Transfer** (`TRANSFER`) | triangle | the value of the `transferTo` node | OR | Same file only. Its own children are ignored. |

Event kinds (`eventKind`) apply to leaves:

| Kind | Symbol | Meaning |
|---|---|---|
| **basic** (default) | circle | A quantified basic event. |
| **undeveloped** | diamond | Not analysed further. It is quantified like a basic event and listed as info (`UNDEVELOPED_EVENT`), so an incomplete branch is visibly incomplete. |
| **house** | house (pentagon) | A switch that is either certain or impossible. Its probability is 1 when `houseState` is true (ON) and 0 when false (OFF). Use it to turn scenarios on and off without editing the tree. |
| **conditioning** | ellipse | The condition of an INHIBIT gate, for example "operator present" or "demand occurs while in maintenance". |

**Approximations, and when they matter:**

- **Priority-AND.** The exact probability that inputs fail *in a given
  order* depends on their failure times, which this tool does not model. For n
  inputs that are independent and identically distributed, all n! orders are
  equally likely, which gives Πp/n!. For inputs with very different rates, the
  true value can be far from that. The cut-set and importance analyses treat
  PAND as a plain **AND** (without the 1/n!), which is conservative. The
  headline shows the tree walk unless the tree has repeated events or XOR.
  When it shows the MCUB, the PAND reduction is therefore not in the headline
  either: the Cut Sets tab shows a *PAND treated as AND in cut sets
  (conservative)* badge, the MCUB badge's tooltip says so, and the cut-set
  and summary results list the approximation (`PAND_APPROX`).
- **XOR** is non-coherent: a component *not* failing can contribute to the top
  event. Cut sets read XOR as OR, so the cut-set results overstate XOR
  branches. The tree is flagged `NONCOHERENT_XOR`, and the headline uses the
  MCUB.
- **Transfer.** A transfer references a node in the same file by id and takes
  its value. The same event reached through a transfer and directly is one
  **repeated event**, so cut sets count it once. A transfer with no valid
  target counts as 0 (`TRANSFER_MISSING`). A transfer chain that loops back on
  itself counts as 0 (`TRANSFER_CYCLE`). References across files are not
  supported.
- **Links** keep their 1.6 meaning: the gate first, then the AND-links, then
  the OR-links.

### Top-event value: tree walk, MCUB and rare-event

Three numbers can describe the top event:

| Value | How it is computed | Exact when |
|---|---|---|
| **Tree walk** | bottom-up through the gates, treating every input as independent (the classic 1.6 number) | the tree is coherent and no event is reached along more than one path |
| **MCUB** (min-cut upper bound) | 1 − Π(1 − P(Cⱼ)) over the minimal cut sets | an upper bound on the exact value for a coherent tree; very close to exact when cut-set probabilities are small |
| **Rare-event** | ΣP(Cⱼ) | an upper bound, ≥ MCUB; useful only when every P(Cⱼ) ≪ 1; can exceed 1 |

**Repeated events.** An event is repeated when it is reached along several
paths: through a link, or through a transfer and its target. Node ids are
unique, so an ordinary child cannot be repeated. The tree walk then treats the
copies as independent events, and the result can be wrong in **either
direction**. For example, for A AND (A OR B) the tree walk gives
p_A·(p_A + p_B − p_A·p_B), but the correct answer is p_A. The cut sets handle
repeated events correctly because they are Boolean.

**The headline** in the top bar shows the top-event probability:

- It is the **MCUB** when the tree has repeated events or an XOR gate. In
  advanced mode a badge says **MCUB**. Its tooltip gives the reason (repeated
  events, XOR (non-coherent) gates, or both) and the tree-walk value, and
  notes when Priority-AND gates were treated as AND in the cut sets.
- Otherwise it is the **tree walk**.
- The headline is computed with cheaper limits (at most 2,000 cut sets and a
  2 s budget). If the cut sets cannot be computed at all, it falls back to
  the tree walk.
- In advanced mode a subtle **≈** marker after an MCUB headline says it was
  computed from fewer sets. Its tooltip says why: *Quick estimate (summary
  capped at 2000 cut sets / 2 s)* means only the headline's own limits cut
  the run short, so open the Cut Sets tab for the full result; *Cut sets
  truncated by the document limits* means the document's max order, max
  count or cutoff dropped sets, as the Cut Sets tab would also show.
- It refreshes from `GET /api/analysis/summary` about 400 ms after each edit
  to the tree, the analysis settings or the mode. A slower, outdated answer is
  discarded. If the request fails, the headline quietly shows the tree walk.
- In **ETA mode** the headline shows the root's calculated value and no
  badge.

**Truncation.** Cut sets are limited by *max order* (default 6), *max count*
(default 5,000) and *cutoff probability* (default 1e-15). Truncation only
drops sets, so a truncated MCUB or rare-event value **underestimates** the
exact value. Truncation by order or cutoff is usually negligible because the
dropped sets are the least probable ones. Truncation by count keeps the most
probable sets, but it is reported as an approximation. When a result is
truncated, the Cut Sets tab shows a *Truncated* badge, and the report and the
CLI show it too.

The document's defaults live in the `analysis.cutsets` block (see the API
reference). The Cut Sets tab can override them for one run, and its **Save as
document defaults** button changes them. The Validation tab and `validate`
expand the cut sets with the document's limits (2 s budget) and report
`CUTSETS_TRUNCATED` when they truncate. If that expansion runs out of time,
nothing is reported about truncation.

### Minimal cut sets

A **cut set** is a set of basic events whose joint occurrence causes the top
event. It is **minimal** when no event can be removed and still cause it. The
tool computes minimal cut sets with bottom-up MOCUS on a compiled Boolean graph
of the tree, including links, transfers, k-out-of-n and house events.

Each row shows the rank, the events, the **order** (number of events), the
probability P(C) = Πq, and the **share**, P(C)/ΣP.

How to read them:

- **Order-1 cut sets are single points of failure.** Any of them defeats
  every redundancy in the design.
- The **share** column tells you where the risk is. The top few rows often
  carry most of it. Design changes that remove or lower those cut sets pay
  off; changes elsewhere barely move the result.
- **Redundant trains** show up as order-2 or higher cut sets. If the trains
  share a cause (a common supply, maintenance crew or environment), model
  that cause explicitly as a shared (linked) event. Common-cause groups
  (β-factor) are not built in yet.
- A house event that is ON is the constant TRUE and disappears from the cut
  sets; one that is OFF removes every cut set it is in.
- A k-out-of-n gate whose expansion would exceed 20,000 combinations is
  refused (`422 ANALYSIS_TOO_LARGE`). So is an analysis that runs past its
  time budget (30 s for the tab).

### Importance measures

The measures are computed on the MCUB, Q, from the (possibly truncated) cut
sets. For each basic event i, Q(qᵢ = x) means the top value with that event's
probability set to x:

| Measure | Definition | Reading |
|---|---|---|
| **Fussell-Vesely (FV)** | (Q − Q(qᵢ=0)) / Q | The fraction of the top-event probability that involves event i. It lies between 0 and 1, and it ranks where risk comes from. |
| **Birnbaum** | Q(qᵢ=1) − Q(qᵢ=0) | The sensitivity ∂Q/∂qᵢ, i.e. how much Q changes per unit change of qᵢ. It is high for events whose failure alone nearly fails the system, whatever qᵢ is. |
| **RAW** (Risk Achievement Worth) | Q(qᵢ=1) / Q | The factor by which Q rises if event i is certain, for example if the component is out for maintenance. Use it to judge outages and to screen for defence-in-depth. |
| **RRW** (Risk Reduction Worth) | Q / Q(qᵢ=0) | The factor by which Q falls if event i is made perfect. Use it to find the best improvement. It is **∞** when every cut set contains the event (a pure single point). |

Practical guidance:

- Rank design effort by **FV** (or RRW). Rank maintenance and outage
  sensitivity by **RAW**.
- In PSA practice, events with FV > 0.005 or RAW > 2 are commonly called
  "risk significant". Treat those numbers as conventions, not as properties
  of this tool.
- An event with q = 0, or one whose cut sets were all truncated away, does
  not appear in the table.
- **Colour diagram by FV** turns the ranking into a picture: the darkest
  events carry the most risk.

### Uncertainty (Monte Carlo)

Give an event an uncertainty in the Quantification tab: choose *Lognormal*,
then enter an **error factor** EF (the 95th percentile divided by the median,
EF ≥ 1) and optionally a median or a mean.

- The uncertainty applies to the model's **main parameter**: q for *fixed*
  and λ for *rate*, *standby* and *repairable*. The other parameters (T, τ, μ)
  stay at their point values.
- σ = ln(EF)/1.645.
- If you enter a **mean**, it is converted to the median with
  median = mean·e^(−σ²/2).
- If you enter neither, the point value is taken as the **median**.
- Every sampled q is clamped to [0, 1].

Each run samples every uncertain parameter, recomputes q, and evaluates the top
event. It uses one of two methods, chosen automatically and shown in the
results:

- **tree**: the compiled tree with the engine's gate formulas. It is used when
  the tree is coherent and has no repeated events, and it then matches the tree
  walk sample for sample.
- **cutsets**: the MCUB over the most probable minimal cut sets that cover
  99.99 % of the rare-event sum, at most 2,000 of them. It is used otherwise. A
  warning says when sets were dropped (`MC_CUTSETS_TRUNCATED`).

The results are the **mean**, **median**, **5th** and **95th** percentiles
(linear interpolation), the **standard deviation**, the **point estimate**
(nominal values) and a 40-bin histogram. The histogram is log-spaced when the
values span more than two decades.

Settings and limits:

- **Samples**: default from the document (`analysis.mc.n`, 10,000). The
  Uncertainty tab and the API allow at most 100,000. The CLI takes the
  document value, up to 1,000,000.
- **Seed**: the same seed with the same tree gives identical results. If you
  leave it blank, a seed is drawn and **reported**, so any run can be
  repeated exactly.
- **Time limit**: default 30 s; at most 60 s in the tab and API. If the limit
  is hit, the samples completed so far are returned and the result is marked
  **partial**. Samples are processed in fixed chunks, so a partial result is
  still deterministic for its seed.
- Only one run can be in progress at a time. A second request gets
  `409 BUSY`.
- If no event has an uncertainty, the run reports `MC_NO_UNCERTAINTY`, and
  every sample equals the point estimate.

How to interpret the results:

- With skewed (lognormal) inputs, the **mean exceeds the median**, often by a
  lot for large EFs. Regulators and most PSA guidance compare the **mean** to
  targets.
- The **point estimate** uses the nominal values. When those are medians, the
  point estimate sits near the median, below the mean.
- The 5–95 % band is the usual way to state the result: "the top-event
  probability is between A and B with 90 % confidence, given the data
  uncertainty".
- The analysis treats every event's uncertainty as **independent**. Events that
  share a data source are really correlated (a "state-of-knowledge"
  dependence), which widens the true spread. This effect is not modelled.

### Validation

`GET /api/analysis/validate` runs the rules below. They run in the Validation
tab, the DOCX report and `cli validate`. Each code has a fixed severity.

| Code | Severity | Meaning | How to fix |
|---|---|---|---|
| `DANGLING_LINK` | error | A link points to a node id that does not exist. | Remove the link, or link it to an existing node. |
| `TRANSFER_MISSING` | error | A transfer gate has no valid target, so it counts as 0. | Pick a target node, or change the gate type. |
| `TRANSFER_CYCLE` | error | A transfer chain comes back on itself, so it counts as 0. | Point the transfer at a node outside its own branch. |
| `INHIBIT_ARITY` | error | An INHIBIT gate does not have exactly two children, one of them *conditioning*. The engine warning in the analysis tabs uses the same rule. | Keep one input, and one child marked as a conditioning event. |
| `KOFN_ARITY` | error | A k-out-of-n gate has k missing, k < 1 or k > n. | Set k between 1 and the number of inputs. |
| `XOR_ARITY` | error | An XOR gate does not have exactly 2 inputs. | Give it exactly two inputs, or use OR. |
| `QUANT_PARAM_MISSING` | error | A rate, standby or repairable model lacks a parameter; the previous probability is used. | Fill in the missing values, or switch to the fixed model. |
| `CYCLIC_LINK` | warning | A link closes a loop. The engine uses the target's value from its children only, so the result is approximate. | Remove the link, or link to a node that is not above this one. |
| `TRANSFER_HAS_CHILDREN` | warning | A transfer gate has children, which are ignored. | Move them under the transfer target, or delete them. |
| `HOUSE_HAS_CHILDREN` | warning | A house event has children, so its on/off state is ignored. | Make it a basic event, or move the children. |
| `SINGLE_INPUT_GATE` | warning | An AND, OR or PAND gate below the top event has one input and no links, so it does nothing. | Add an input, or remove the level. |
| `DEFAULT_PROBABILITY` | warning | A basic leaf is exactly 1.0 with no model, so it has probably never been quantified. | Enter the real probability. |
| `PARENT_PROBABILITY_IGNORED` | warning | A gate's own probability is neither 1.0 nor its calculated value, and it is ignored. | Clear it (set it to 1.0), or make the node a leaf. |
| `STANDBY_LARGE_LT` | warning | Standby λτ > 0.2, where λτ/2 is inaccurate. | Shorten τ, or use the rate model. |
| `NONCOHERENT_XOR` | warning | The tree has XOR gate(s), so cut-set results are approximate. | Use OR if both events can happen together. |
| `CUTSETS_TRUNCATED` | warning | The cut sets, expanded with the document's limits, were truncated, so the results may be underestimated. Shown in the Validation tab, `validate` and the DOCX report. | In the Cut Sets tab, raise the limits and click **Save as document defaults**. |
| `ETA_BRANCH_SUM` | warning | ETA only: the children's probabilities do not sum to 1 (±1e-6). | Adjust the branch probabilities. |
| `LOAD_REPAIR` | warning | The file was repaired on load (duplicate id renamed, top id changed, invalid analysis setting reset, stale gate type dropped), or an AI edit left a stale gate type that was dropped. | Check the node, and save to keep the repair. |
| `LINKS_REMOVED` | warning | Deleting a node (by hand or by the AI assistant) removed links or transfer targets (`transferTo`) that pointed to it. | Re-add the link or transfer target if the dependency still exists. |
| `UNDEVELOPED_EVENT` | info | The leaf is marked undeveloped. | Nothing needed, or develop it later. |
| `PAND_APPROX` | info | A Priority-AND gate is evaluated as AND × 1/n!. | Nothing needed; note the approximation in your report. |

The top event is never `SINGLE_INPUT_GATE`, because a top event that restates
its one cause is normal practice. An empty document is never
`DEFAULT_PROBABILITY`. In ETA mode only `ETA_BRANCH_SUM` and the session
notices are reported.

`LOAD_REPAIR` and `LINKS_REMOVED` are *session notices*. They are collected
while the document is open and are not saved in the file or undone. The one
exception is a stale gate type dropped after an AI edit (the notice says
*The AI assistant set this gate to …*): it belongs to that edit, so undoing
the AI update removes the notice and redo brings it back.

### Traceability and tree search

Every node can carry a `trace` block. You edit it in the **Traceability** tab,
where each row is a node in tree order:

| Field | Content |
|---|---|
| Requirement ID (`requirementId`) | The requirement or hazard this node traces to |
| Test ref (`testRef`) | The test, inspection or analysis that covers it |
| Owner (`owner`) | Who is responsible |
| Status (`status`) | `draft`, `reviewed` or `approved` |
| Evidence (`evidence`) | A reference or URL. Only `http(s)` URLs are shown as links, and they open in a new tab. |
| Tags (`tags`) | Comma-separated free tags, at most 64 |

To edit a cell, click it (or press Enter or F2). Enter or leaving the cell
commits the edit, and Escape reverts it. Emptying a cell removes the field.
Clicking an id or name jumps to the node.

**Tree search.** The search box above the tree matches names, and also the
requirement ID, owner, status, tags and FMEA id and item, case-insensitively.
Field prefixes narrow a search to one field. Terms combine with AND.

| Prefix | Matches | Example |
|---|---|---|
| `tag:` | a tag | `tag:hydraulic` |
| `owner:` | the owner | `owner:tanaka` |
| `status:` | the status | `status:draft` |
| `req:` | the requirement ID | `req:SR-12` |
| `fmea:` | the FMEA id | `fmea:P-07` |

Use quotes for values with spaces, for example `tag:"hot section"`. A prefix
with no value, such as `tag:`, matches every node that has that field. Matches
are shown with their ancestors, so the path to each match stays visible.

### FMEA import

The **FMEA** tab turns FMEA worksheet rows into basic events, and keeps the
FMEA row id on each node so the two analyses stay linked.

1. **File.** Click **Choose file…** to pick a `.csv` or `.xlsx` file with the
   editor's file browser, or type a path. For this dialog the browser lists
   `.csv` and `.xlsx` files instead of `.json`. The file must be within the
   browser's root and at most 10 MB, and the tool reads at most 20,000 rows
   and 200 columns. `.xlsx` needs `openpyxl`; otherwise save the sheet as CSV.
   The first non-empty row is the header. A preview shows the first 50 rows.
   For a workbook, pick the sheet.
2. **Columns.** Map each import field to a column: *id, item, mode, cause,
   severity, occurrence, detection, rpn, λ*. A mapping is suggested from
   English and Japanese header words.
3. **Target and values.**
   - *Parent*: the node the new events go under. It defaults to the selected
     node. If the parent is a leaf, it becomes an OR gate. It cannot be a
     transfer gate.
   - *λ unit*: `/h`, `/y` or `FIT`. It is suggested from the λ header, for
     example `λ (FIT)` or `故障率 [/年]`. λ is converted and stored per hour.
   - *Update existing rows*: see the rules below.
   - *Occurrence table*: the editable map from occurrence rank to
     probability.

Import rules:

- **Key.** Each row's key is the mapped id column. If no id column is mapped,
  the key is "item / mode". A row with neither is skipped.
- **Re-import updates in place.** With *update* on (the default), a row whose
  key equals an existing node's `fmea.id` anywhere in the tree updates that
  node: its name, its `fmea` block and, for a leaf, its numbers. With update
  off, such a row is skipped. A key repeated within the sheet is imported
  once.
- **New rows** become leaf events under the parent, named "item – mode".
- **Numbers.** The first rule that applies is used:
  1. A λ value gives the **rate** model with that λ.
  2. Otherwise, an **occurrence rank** gives a fixed probability from the
     occurrence table.
  3. Otherwise, a new event stays at 1.0 and is marked **undeveloped**, and an
     existing node's numbers are left alone.

  Re-importing merges into an existing `quant`, so your T and uncertainty
  survive.
- **Validation.** Ranks must be integers 1–10, RPN a non-negative integer, and
  λ a non-negative number. A bad row is skipped with its reason and sheet row
  number, and the rest is still imported. RPN is computed as S×O×D when it is
  not mapped.
- **Undo.** The whole import is **one undo step**, including any change to the
  occurrence table.

**Occurrence table.** The default maps AIAG PFMEA (4th edition) occurrence
ranks to a per-item probability, taking the lower edge of each band of
"failures per 1000 items":

| Rank | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Probability | 1e-7 | 1e-6 | 1e-5 | 1e-4 | 5e-4 | 2e-3 | 1e-2 | 2e-2 | 5e-2 | 1e-1 |

Rank 1 ("failure eliminated through prevention") has no band; 1e-7 is a
nominal value. Organisations calibrate their own tables, so the table is
editable in the FMEA tab and **saved in the document**
(`analysis.fmeaOccurrenceTable`). **Reset** restores the AIAG default.
Occurrence ranks are ordinal judgements, not measured probabilities. Prefer a
λ from field or handbook data where you have one.

After an import, the tab lists how many rows were created, updated, unchanged
and skipped (with reasons). It also highlights the imported nodes in the tree
and the diagram.

### Report (DOCX) and Excel sheets

The **Report** tab generates a Word document. This needs `python-docx`
(`uv sync --extra report`, which is included in `--extra all` and in the
standalone build). Without it, the tab shows the install command and the API
returns `503 EXPORT_UNAVAILABLE`.

Sections (tick the ones you want; the choice is remembered):

| Section | Contents |
|---|---|
| Metadata | Title, analysis date, mode, generation time, tool version |
| Headline | Top-event probability, the method (MCUB or tree walk) and the alternative value |
| Assumptions | Mission time, the models used (with formulas and counts), approximations, non-coherence, repeated events, cut-set limits |
| Diagram | The diagram image (see below) |
| Events | The basic-event table: id, name, kind, model, parameters (λ, T, τ, μ, MTTR), q, calculated value and source (data provenance) |
| Cut sets | The top 50 by default, with totals, MCUB, rare-event value and a truncation note |
| Importance | The top 30 by FV, by default |
| Uncertainty | **Off by default.** When selected, a Monte Carlo run of at most 5,000 samples (30 s) is made for the report. |
| Validation | Every issue, including `CUTSETS_TRUNCATED` |
| Traceability | Every node that has trace data |

Choose the language (English or Japanese). In Japanese, the report uses
Meiryo for East-Asian text.

**The report diagram** is the PNG of the diagram as your browser shows it, so
it has the true symbols in the symbols style. When no browser image is sent,
for example from the CLI, the diagram is rendered by a native Graphviz `dot`
in the compact style. When neither is available, the report says the diagram
is not available. ETA documents are accepted; the fault-tree-only sections
say they do not apply.

**Excel export** (`Export Excel` here, or the usual export menu) writes three
sheets:

- **FTA**: the 1.6 hierarchical sheet, unchanged.
- **Events**: one row per node in tree order. The columns are Id, Name, Parent
  Id, Depth, Node type, Gate type, k, Event kind, House state, Transfer to,
  Model, λ (/h), T (h), τ (h), μ (/h), MTTR (h), Base probability, Calculated
  probability, Source, Unc. dist, Unc. median, Unc. mean, Unc. EF, Requirement
  ID, Test ref, Owner, Status, Evidence, Tags, FMEA ID, FMEA item, FMEA mode,
  FMEA cause, S, O, D, RPN. Numbers are real numbers in scientific format
  with the significant figures chosen in the top bar, so you can sort, filter
  and pivot. The header row is frozen and auto-filtered.
- **Analysis**: the document settings (mission time, cut-set limits, Monte
  Carlo settings). In FTA mode it also has the headline, tree walk, MCUB,
  rare-event value, repeated-event count, non-coherence, the number of
  approximations and the truncation flag.

**Export events CSV** builds the same per-event table as a CSV in the browser.

### Diagram styles and layout

The **Aa** popover on the diagram toolbar has two display settings. They are
remembered per browser (`fta.diagram.settings`) and are not saved in the file.

- **Style**
  - **Compact boxes** (default): the 1.6 two-row boxes. The meta row reads
    `Gate: <gate> | P:<q> | P_calc:<Q>`. The 1.7 gates appear as `2/3`,
    `XOR`, `INHIBIT`, `PAND` or `TRANSFER→<target>`. A non-basic leaf shows
    `House: ON|OFF`, `Undeveloped` or `Conditioning`.
  - **Standard symbols**: a description rectangle for every node, with an
    IEC 61025 / NUREG-0492 gate or event symbol under it. A transfer gate's
    ignored children are drawn dotted. A conditioning event is drawn as an
    ellipse hanging off its INHIBIT gate. Clicking a gate symbol selects its
    node.
- **Layout**: *Left → right* (default, as in 1.6) or *Top → down*.

**Export limitation.** Graphviz itself has only polygons, so the DOT the
server produces uses *approximate* shapes:

| Symbol | Graphviz approximation |
|---|---|
| AND | `house` |
| PAND | `house` with a double outline |
| OR and k-out-of-n | `triangle` |
| XOR | `triangle` with a double outline |
| INHIBIT | `hexagon` |
| Transfer | a filled `triangle` |

In the browser, these shapes are replaced by the true symbol paths
(`static/js/fta_symbols.js`). As a result:

- **Browser export** (SVG, or PNG from the canvas) and the **report diagram**
  show the **true symbols**.
- A **native render** (the "render to file" export through a system Graphviz,
  `POST /api/render`) shows the **approximate** shapes.

For a document you send to a reviewer, export from the browser.

## Command-line interface

The same analyses can run without a browser. Nothing starts a server:

```
fta_editor.exe <command> FILE... [options]           # the standalone build
uv run python fta_web/run.py <command> FILE... [options]
```

| Command | Output |
|---|---|
| `quantify` | The headline (and its method), tree walk, MCUB and rare-event value, plus q and the calculated value per basic event |
| `cutsets` | The minimal cut sets, ranked |
| `importance` | FV, Birnbaum, RAW, RRW and the cut-set count per event, sorted by FV |
| `mc` | Monte Carlo: point estimate, mean, median, p05, p95, std, requested and completed samples, seed and method |
| `validate` | The Validation issues and their counts |
| `report` | The DOCX report (needs `python-docx`) |

Options:

| Option | Commands | Meaning |
|---|---|---|
| `--json` / `--csv` | all | Machine-readable output instead of a text table (mutually exclusive). With several files, `--json` gives a list. |
| `--out PATH` | all | Write to PATH instead of stdout. With several files, give a directory; each file then gets `<stem>.<command>.<ext>`. A path that exists as a directory or ends in `/` or `\` is a directory. `report` defaults to `<stem>_report.docx` beside the input; for `report`, any `--out` that does not end in `.docx` is a directory. |
| `--sig-figs N` | all | Significant figures in text tables, 1–6, default 3. JSON and CSV carry full precision. |
| `--mission-time H` | all | Override the document's mission time, in hours. |
| `--max-order N`, `--max-count N`, `--cutoff P` | cutsets, importance, report | Override the cut-set limits. |
| `--top N` | cutsets, importance | Show only the first N rows (N ≥ 1). |
| `--n N`, `--seed S` | mc, report | Monte Carlo samples and seed. |
| `--time-limit SEC` | mc, report | Monte Carlo time cap in seconds, > 0, default 30. For `report` it is capped at 60. |
| `--strict` | validate | Warnings also fail (exit 1). |
| `--sections LIST`, `--lang en\|ja`, `--uncertainty` | report | Comma-separated sections, the report language, and whether to run Monte Carlo (n ≤ 5,000) and include it. |

Wildcards are expanded by the tool itself, so `*.json` works in `cmd.exe` too.

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | OK |
| 1 | Validation errors (or warnings with `--strict`), or an analysis failed (for example an ETA file given to `cutsets`, or a voting gate that is too large) |
| 2 | Usage error (bad option or value) |
| 3 | An input file could not be read |

With several files, the highest code wins.

Examples:

```
fta_editor.exe validate *.json --json                 # CI gate: exit 1 on any error
fta_editor.exe validate plant.json --strict           # warnings fail too
fta_editor.exe quantify plant.json --mission-time 17520
fta_editor.exe cutsets plant.json --top 20 --csv --out cutsets.csv
fta_editor.exe importance plant.json --json --out results/
fta_editor.exe mc plant.json --n 50000 --seed 42
fta_editor.exe report plant.json --lang ja --uncertainty
```

`fta_editor.exe --version` prints the version. `fta_editor.exe help` prints
the command list.

## Desktop app compatibility

The 1.7 file format is **additive**. Every new key is optional, and a file
without them behaves exactly as in 1.6:

- node keys: `gateType`, `k`, `transferTo`, `eventKind`, `houseState`,
  `quant`, `trace`, `fmea`
- the top-level key: `analysis`

What the frozen legacy desktop app (`desktop/`) does with a 1.7 file:

- **It reads only `logicGate` and `probability`.** It computes AND/OR only,
  from each leaf's `probability`.
- **Advanced gates are projected to AND/OR** through `logicGate`:
  - INHIBIT and PAND → AND. PAND loses its 1/n!, so it is higher in the
    desktop app.
  - k-out-of-n, XOR and TRANSFER → OR. The desktop result is the plain OR of
    the children, i.e. "any 1 of n" for a vote and a + b − ab for XOR.
- **The derived probability is written into `probability`** for rate,
  standby and repairable models, for house events (1 when ON, 0 when OFF) and
  for transfer gates (the target's calculated value). So these leaves have
  meaningful values in the desktop app, frozen at the web app's last
  recalculation. Changing the mission time, a house state or a transfer
  target in the desktop app is not possible.
- **Transfer gates and house events are not understood** as such: the desktop
  app sees leaves carrying the derived `probability` above, so for AND/OR
  trees the top event matches the web app. A transfer gate **with children**
  is the exception: the web app ignores the children, while the desktop app
  computes the gate from them (`TRANSFER_HAS_CHILDREN` warns about it).

Saving from the desktop app:

- **Node keys are kept.** The desktop app loads a file by normalising only the
  keys it knows. Its node edit merges the changed fields into the existing
  node, and it saves a deep copy of the tree. So `gateType`, `quant`, `trace`,
  `fmea` and the other node keys survive a desktop open-edit-save round trip.
- **The `analysis` block is lost.** The desktop app writes only `title`,
  `date`, `mode` and `tree`. The mission time, cut-set limits, Monte Carlo
  settings and a custom FMEA occurrence table revert to their defaults the
  next time the web app opens the file.
- **A gate changed in the desktop app is kept.** The desktop app edits only
  `logicGate` and leaves a stale `gateType` behind. When the web app opens a
  file (or installs an AI update) where `gateType` no longer projects to
  `logicGate`, for example a k-out-of-n gate that the desktop user switched
  to AND, it trusts `logicGate`. The `gateType` is dropped together with its
  `k` or `transferTo`, and the Validation tab lists a load repair
  (`LOAD_REPAIR`, kind `gate_type_reset`). A change that keeps the projection
  cannot be detected: a PAND or INHIBIT gate whose `logicGate` is still AND
  keeps its `gateType`.
- **Probabilities typed in the desktop app are overruled** for an event with a
  rate, standby or repairable model (recomputed from the model), and for
  house events and transfer gates (recomputed from the state or the target).
- The desktop app's AI "Update FTA" replaces the tree with what the model
  returns, which usually drops the 1.7 node keys. The web app's AI update
  restores them by node id and reports how many (`mergedFields`).

**Recommendation.** Treat the web app as the owner of any file that uses 1.7
features. Use the desktop app only to view such a file, or for trees that use
AND/OR and fixed probabilities only.

## Export Options

### JSON Export

**File → Save JSON**

Saves complete analysis including:
- Metadata (title, date, mode)
- Full tree structure
- All probabilities
- Links and notes

**Format**:
```json
{
  "title": "Analysis Name",
  "date": "2025-10-31",
  "mode": "ETA",
  "tree": { ... }
}
```

### Excel Export

**File → Export Excel**

Hierarchical column structure:
- Column A: Root events
- Column B: Level 1 children
- Column C: Level 2 children
- Continues for all levels

**Features**:
- Color-coded by depth
- Auto-adjusted widths
- Wrapped text
- All node details in each cell

From 1.7 the web app's workbook also has a flat **Events** sheet (one row per
node, numbers as real numbers) and an **Analysis** sheet (settings and
headline figures). See [Report (DOCX) and Excel sheets](#report-docx-and-excel-sheets).

### DOCX Report (web app, 1.7)

**Report tab → Generate report**. See
[Report (DOCX) and Excel sheets](#report-docx-and-excel-sheets).

### XML Export

**File → Export XML**

Standard fault tree XML format, compatible with other FTA tools.

## Keyboard Shortcuts

### Web app (1.7.1)

| Shortcut | Action |
|----------|--------|
| `Alt+N` | New analysis (Chrome and Edge reserve `Ctrl+N` for a new browser window, so the page never receives it) |
| `Ctrl+A` | Add a child to the selected node |
| `Ctrl+E` | Edit the selected node (Details tab) |
| `Ctrl+D` / `Delete` | Delete the selected node (`Delete` only from the tree) |
| `Ctrl+S` | Save (also with the caret still in a field) |
| `Ctrl+Shift+S` | Save As |
| `Ctrl+Z` / `Ctrl+Y` (`Ctrl+Shift+Z`) | Undo / Redo |
| `Ctrl+F` | Search the tree |
| `Escape` | Discard what was typed in a field; close a dialog or the diagram's Aa popover; dismiss a toast |

Inside a text field `Ctrl+A` and `Ctrl+Z` keep their usual meaning (select
all, undo typing). In the tree: arrows move, `Enter` / `Space` select, `F2`
renames, `Ctrl+Shift+arrows` move the focused node. In the bottom tab strip:
`Left` / `Right` / `Home` / `End`. In the diagram: `Ctrl+=` / `Ctrl+-` zoom,
`Ctrl+0` fits (never above 100%).

### Desktop app

- `Ctrl+N` - New Analysis
- `Ctrl+A` - Add Node
- `Ctrl+E` - Edit Node
- `Ctrl+D` - Delete Node
- `Ctrl+S` - Save (overwrite)
- `Ctrl+Shift+S` - Save As
- `Ctrl+R` - Render Diagram

## Examples

### Example 1: Server Reliability (FTA)

**Scenario**: Analyze server downtime causes

1. Set Mode to "FTA"
2. Create root: "Server Unavailable"
3. Add children:
   - Hardware Failure (0.1)
   - Software Crash (0.15)
   - Network Issue (0.08)
4. Set root Logic Gate to "OR"
5. Result: Root calculated probability shows overall failure rate

### Example 2: Nuclear Safety (ETA)

**Scenario**: Analyze loss of coolant accident sequences

1. Set Mode to "ETA"
2. Create root: "Loss of Coolant" (0.001)
3. Add branches:
   - ECCS Activates (0.99)
     - Core Cooled (0.98)
     - Partial Cooling (0.02)
   - ECCS Fails (0.01)
     - Core Meltdown (1.0)
4. Calculated probabilities show each outcome likelihood

## Troubleshooting

**Q: Probabilities seem wrong after mode switch**
A: Different modes calculate differently - this is expected. FTA is bottom-up, ETA is top-down.

**Q: Can't see diagram preview**
A: Ensure Graphviz is installed and in your PATH.

**Q: Zero probability nodes everywhere**
A: Check that probabilities are set > 0. In FTA mode, check logic gates.

**Q: Excel export fails**
A: Ensure openpyxl is installed: `pip install openpyxl`

**Q: "Generate report" is disabled or says python-docx is missing**
A: Run `uv sync --extra report` (or `pip install python-docx`) and restart the editor.

**Q: I only see the Details and Validation tabs**
A: Switch on **Advanced** in the top bar. See [Basic and Advanced mode](#basic-and-advanced-mode).

**Q: The top-event value differs from the root node's calculated probability**
A: The headline uses the min-cut upper bound when the tree has repeated events
or XOR gates. See [Top-event value](#top-event-value-tree-walk-mcub-and-rare-event).

**Q: Opening a file says it is empty, not valid JSON, or that the root must be an object**
A: The web app says why a file could not be read: an empty file, a JSON
syntax error (with the line and column to look at), or a file whose top level
is not a JSON object. Fix the file in a text editor, or restore it from a
backup.

**Q: A path is refused with "outside" or "may not contain ':'"**
A: The web app only reads and writes inside its root folder. On Windows a
path on another drive, a network (UNC) path, or a drive letter created with
`subst` is refused even if it points at the same folder, and a `:` in a file
name (an NTFS alternate data stream) is refused. Relaunch with `--root` to
use another folder.

**Q: Legacy JSON files don't load properly**
A: Old format is supported, but defaults to FTA mode. Set mode manually after loading.

**Q: AI Assistant shows "not configured"**
A: Click the ⚙ button in the AI panel to enter your API credentials.

**Q: AI connection test fails**
A: Verify your API key is valid and has available credits. Check internet connection.

**Q: AI responses are slow**
A: Consider using a faster model like `gpt-4o-mini`. Check your API rate limits.

**Q: AI suggestions don't apply correctly**
A: Ensure you've reviewed and selected the changes in the confirmation dialog.

## Best Practices

1. **Use Descriptive Names**: Make nodes self-explanatory
2. **Document with Dates**: Always fill in the date field
3. **Add Notes**: Use notes field for important context
4. **Save Frequently**: Use Ctrl+S regularly
5. **Validate Results**: Check calculated probabilities make sense
6. **Export Regularly**: Keep Excel/XML exports for sharing

## Advanced Features

### Using Links

Links allow dependencies between non-parent/child nodes:

```
Node A (0.5)
  Link→ AND to Node B (0.8)
  Result: A's probability becomes 0.5 × 0.8 = 0.4
```

### Mixed AND/OR Gates

You can have different logic gates at different levels:
- Root: OR gate (any child causes failure)
- Children: AND gates (all sub-components must fail)

### Circular Reference Handling

The calculator detects circular references. A link that closes a loop uses
the target's value computed from its children only (its "gate-only" value),
instead of letting the loop saturate every node on it to 1.0. The Validation
tab lists such links as `CYCLIC_LINK`, because the result is then an
approximation. A leaf reached around a loop uses its base probability.

---

For more details, see:
- [ETA Mode Documentation](ETA_MODE.md)
- [Probability Validation](PROBABILITY_VALIDATION.md)
- [API Reference](API_REFERENCE.md)
