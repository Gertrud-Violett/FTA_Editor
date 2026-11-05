# FTA/ETA Editor - User Guide

**Version**: 1.9.0 | **Updated**: November 5, 2026

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
  - [The What-if tab](#the-what-if-tab)
  - [Validation](#validation)
  - [Traceability and tree search](#traceability-and-tree-search)
  - [The Grid tab: every basic event, paste from Excel](#the-grid-tab-every-basic-event-paste-from-excel)
  - [FMEA import](#fmea-import)
  - [Report (DOCX) and Excel sheets](#report-docx-and-excel-sheets)
  - [The top box: headline and tree walk](#the-top-box-headline-and-tree-walk)
  - [Diagram styles and layout](#diagram-styles-and-layout)
  - [CCF groups (beta factor and alpha factor)](#ccf-groups-beta-factor-and-alpha-factor)
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

In the web app a new analysis shows a **Start here** hint in the tree panel,
with two buttons:

- **Name your top event** puts the caret in the top event's Name box, with
  the name selected. Type the failure you want to analyse and press Enter,
  then add its causes with **Add**.
- **Open an example** lists the analyses that come with the editor. See
  [Example files](#example-files).

The hint goes with the first edit, and the **×** in its corner closes it.

The **»** button in the AI Assistant's header folds that panel to a strip at
the right edge; **«** opens it again. The editor remembers the choice for the
next launch.

**The address is the same at every start.** The editor listens on
`127.0.0.1:8765` unless you start it with `--port`. A browser keeps what a
page stores per address, port included, so your display settings (Advanced,
the language, the theme, significant figures, the Formatted switch, the
diagram style) are there again at the next start. Up to 1.8.0 the port was a
new one each time and they were lost. If port 8765 is in use, for example
because a second copy of the editor is running, the editor starts on a free
port and its terminal window says so in a line beginning with `Note`; that
copy starts with the default settings. `--port 8800` chooses another fixed
port and `--port 0` any free one.

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

**Saved / Unsaved changes** (web app): the pill at the right end of the top
bar. The browser tab shows the same: its title is the file name (`Untitled`
before the first save), with a `●` in front while there are unsaved changes.
The status line at the bottom right shows the file name, then its folder;
hover over either for the full path.

**Opening a file by path** (web app): in the Load and Save As dialogs you can
type a path and press Enter. A bare name or a relative path is read against
the folder shown in the dialog, and `~` is your home folder. A path that does
not exist is reported as *Folder not found* or *File not found*.

**Where the dialog starts** (web app): in the folder of the open file. For an
analysis with no file yet (new, an example, a file from this computer) it
starts in the folder of the last file you opened or saved.

**Other places to open from** (web app): the Load dialog has two buttons at
the left of its footer.

- **Open an example…** lists the analyses that come with the editor.
- **A file on this computer…** opens the browser's own file picker, which can
  reach any folder. You can also drop a `.json` file on the tree panel.

Both open the analysis as an **untitled copy**: the status line says
*No file*, and **Save** asks where to put it. The file you chose is not
changed.

**Unsaved changes** (web app): New, Load, an example and a dropped file ask
first when the analysis has unsaved changes. **Save and continue** saves and
then goes on (an analysis with no file yet asks where to save; if you close
that dialog, nothing else happens). **Discard and …** goes on without
saving. **Cancel** does nothing.

**Two tabs** (web app): the editor holds one analysis, and each browser tab
shows a copy of it. A tab you come back to checks whether the analysis was
changed in another tab and shows the current version; a message says so. It
waits while a dialog is open or something you typed has not been entered.

**If the editor stops** (web app): when the editor has been closed, or the
computer slept and it is gone, a red banner appears at the top of the page
within a few seconds and stays until the editor answers again. The tree you
see is still in the tab. **Download a rescue copy (JSON)** saves it through
the browser, unsaved changes included, as a file named
`<name>-rescue-<date>-<time>.json`. Start the editor again and open that
file with **Load** (*A file on this computer…* if it is outside the root
folder). Text you were still typing in a field is not in the copy: press
Enter in the field first if the editor is still running.

A tab whose editor was closed and started again shows *This tab is not
connected to the editor* and the command that starts the editor. If that tab
still holds an analysis, the same **Download a rescue copy (JSON)** button is
on that screen.

### Tree View

- Hierarchical display of your analysis
- Color-coded by depth level
- Click to select nodes
- Shows node names
- A ✖ marker flags zero-probability nodes

In the web app:

- The top event is selected when the editor starts, and after New and Open.
- Double-click a name to rename it (or press F2). Double-click elsewhere on
  a row to open or close its branch.
- A node selected anywhere else (a click in the diagram, a row of a tab) is
  scrolled into view in the tree.
- Which branches are open is remembered per file. A new, unsaved document
  starts fully open.
- **Ctrl+Shift+Up / Down** move the focused node among its siblings,
  **Ctrl+Shift+Right / Left** indent and outdent it. Dragging a row does the
  same.

### Diagram Preview

- Live visualization using Graphviz
- Pan: Click and drag
- Zoom: the mouse wheel (with or without Ctrl; it zooms about the pointer),
  or the **−** / **+** buttons, which zoom about the selected node, or about
  the middle of the diagram when the selected node is not in view. The
  percentage between the buttons shows the current level.
- Updates automatically when tree changes
- Click a node to select it. A tab that jumps to a node moves the diagram
  only when that node is not already in view.

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
  apart from a normal parent/child edge. In dark mode they are a lighter blue
  (`#6cb6ff`), since pure blue is barely visible on the dark background.

#### What the Node Colours Mean

A node box is shaded by its **calculated** probability (`P_calc`, the lower
line in the box), not the value you typed. (The top box of a tree with
repeated events also shows the headline: see
[The top box](#the-top-box-headline-and-tree-walk).)

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

If text crowds or spills outside its node box, open **Settings** on the
diagram panel's toolbar (the **Diagram settings** popover; the button was
**Aa** up to 1.7.3). (The popover can be dragged to a new position if it
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

**Box padding (0-30)**: the escape hatch for whatever mismatch is left (it
was labelled **Box scale**). It accepts **0–30** and defaults to **4**. It is
blank space added around the text of every box, which is what grows the box —
a box has no size of its own beyond what its label needs. Raise it a step at
a time until the text sits comfortably.

#### Zoom, and finding a node

The wheel zooms about the cursor, **−** and **+** about the selected node,
**⤢** fits the whole diagram, **1:1** sets 100 %, and **◎** puts the selected
node in the middle of the panel at 100 % (or at the current zoom, if that is
larger). Selecting a node anywhere (a row of the tree, a row of an analysis
table) moves a zoomed diagram by the least that brings that node wholly into
view; the zoom is left alone.

#### Exporting the picture

**SVG** and **PNG** on the diagram toolbar, and **Render** in the action bar,
download the diagram under the document's name (`pump.json` gives
`pump.png`; an unsaved analysis uses its title), and a message says so.

- The file is always in the **light colours**, whatever theme the editor is
  in: a picture goes onto a white page.
- With **Colour diagram by FV** on (Importance tab), the file has the same
  colours and the legend under the diagram. The selection outline is never
  in the file.

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

In an FTA, a node with children is calculated from them, and its own
**Probability (base)** is not used. The box is then greyed, with a note; the
value stays in the file. When a node that has a probability of its own gets
its first child (Add, a move or a drag), a warning says so and links to the
**Validation** tab.

Enter in a field saves it and returns the focus to the node's row in the
tree. If the value is refused, the caret stays in the field. If you select
another node while a field still holds a refused value, a warning shows the
text that was dropped.

A probability can be typed as a decimal (`0.05`, `5e-2`), a percentage
(`5%`), a fraction (`1/20`), with a decimal comma (`0,05`) or in
full-width characters (`０．０５`). The field then shows the value as a plain
decimal. `1,000` is refused, because it could mean a thousand or one.

## AI Assistant

The AI Assistant provides intelligent analysis and suggestions for your fault trees. It works with OpenAI, Microsoft Copilot (Azure OpenAI), Anthropic Claude and Google Gemini.

### Setup

1. Click the **⚙ (Settings)** button in the AI Assistant panel
2. Choose a provider and enter your API credentials:
   - **Provider**: OpenAI, Microsoft Copilot, Anthropic Claude or Google Gemini
   - **API Key**: The provider's API key
   - **Model**: Pick one of the suggestions (for example gpt-4o) or type any model name. Once a key is saved, **Reload** asks the provider which models it can use (OpenAI, Anthropic and Gemini; Microsoft Copilot always shows the built-in list). OpenAI's reasoning models (o-series, GPT-5) work too.
   - **API Endpoint**: filled in from the provider, `https://api.openai.com/v1` for OpenAI. In the web app it sits under *Advanced*; change it only for a proxy or an OpenAI-compatible gateway such as [GitHub Models](MULTI_PROVIDER_SETUP.md#4-github-models-through-the-openai-provider). Microsoft Copilot is the exception: its endpoint is your own Azure resource, so the field is shown in the main form (see [Microsoft Copilot setup](MICROSOFT_COPILOT_SETUP.md)).
3. Click **Test & Save** to verify and store credentials. Saving a different provider or endpoint starts a new conversation, so the new one is never sent the old conversation; a new key for the same provider and endpoint keeps it.

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
  configured (OpenAI, Microsoft Azure, Anthropic or Google); it is never sent anywhere else,
  written into a saved `.json` analysis file, or committed to the
  repository.
- **Removing it**: click the **⚙ (Settings)** button in the AI Assistant
  panel and use **Clear** to delete the stored key (this removes the file and
  forgets the conversation).
  You can also delete `ai_credentials.json` by hand while the editor is
  closed.

### Features

**Formatted replies**: the assistant's replies are shown as formatted
Markdown: headings, lists, tables, code and bold. The **Formatted** button
(it was **MD**) beside
**Clear Chat** switches every reply between that view and the raw text the
model sent; use the raw text to copy a reply exactly. The choice is remembered
in this browser. Only the assistant's replies are formatted. HTML in a reply
is shown as text, and links are made for http, https and mailto only.

**Quick Actions**:
- **Analyze FTA**: Posts analysis and suggestions to chat only (no changes applied).
- **Update FTA**: The AI is asked to rewrite the whole tree, keeping the existing nodes and adding to them. In the web app the button asks first, because the tree is sent to the AI provider. The answer does not change anything: a card in the chat, **Proposed update (not applied yet)**, lists the nodes the rewrite would add, change and remove (the first twelve of each by name). **Apply update** replaces the tree with the AI's version in one step, and one Ctrl+Z undoes it. **Discard** drops it. If you edit the tree before you press Apply, the update is refused and nothing is changed: run Update FTA again. Detailed error logs are shown if the AI output is invalid. (The desktop app applies the update at once.)
- **Clear Chat**: Reset conversation history

**What the AI is told about the numbers**: with every request the AI gets the
tree (each node's base and calculated probability, gate and links) and, in
FTA mode, the editor's own results for it: the top-event probability shown in
the top bar and its method (MCUB or tree walk), the tree-walk value, the
repeated events, the ten most probable minimal cut sets with their share,
any approximation (Priority-AND, XOR) or truncation, and the mission time.
For a tree with repeated events it is told that the headline already counts
each of them once, so it does not report the tree walk's double counting as
a finding. In ETA mode, or when the cut sets cannot be computed within the
headline's 2 s budget, it gets the tree alone.

**Free Chat**:
Type any question in the input box and press Enter. Examples:
- "What root causes might be missing from this failure mode?"
- "Can you review the probabilities in this tree?"
- "What are common causes of pump failures?"

### Applying Changes

- Use **Analyze FTA** for a safe review-only mode.
- Use **Update FTA** to have the AI rewrite the tree in one step: the AI returns a full JSON which is verified before it replaces your current tree. If the JSON is invalid, the update is rejected and the problematic section is shown in the chat and console. If you edit, undo or open another file while the AI is writing, the update is not applied (nothing is changed); run it again. The 1.7 fields the AI is not shown (gate types, house events, quantification, traceability, FMEA links) are restored by node id.
- Changes the AI suggests in the chat are listed as **Suggested changes**, all ticked; untick what you do not want and click **Apply selected**. One Ctrl+Z undoes the whole batch. A suggestion that cannot be applied is listed with the reason, and the rest are applied. Among the reasons: a probability the editor computes cannot be set directly (a transfer gate takes its target's value, a house event is 1 or 0 from its state, and an event with a rate, standby or repairable model is computed from its parameters), and a suggestion made before New, Open or Import replaced the document is not applied to the new one.
- **Links in a suggestion.** A suggestion to add or edit a node can change that node's links. The links it gives are the node's complete new list, so the card says what approving it does: one line for each link it adds (*Adds link: OR → name (id)*) and each it removes (*Removes link: …*). A link must point at an existing node (one added by an earlier suggestion of the same set counts), not at the node itself, and appear once, with the relation AND or OR.
- **A suggestion is applied as a whole or not at all.** If any part of it is not valid, for example a link to a node that does not exist, that suggestion is not applied, neither its links nor its new name, and the chat says *Suggestion rejected* with the reason. It is never reported as applied with a part left out. The one exception is named in the chat as well: a suggestion cannot give an added node its children (each child is its own suggestion) or set the advanced fields (gate type, quantification model, and so on); if it carries those, it is applied and the chat lists them as *not changed by a suggestion*.
- Answers can take a while. The editor waits up to 120 seconds for the provider; after that the request fails with a timeout and nothing is changed. The assistant handles one request at a time, so a provider that has stopped answering keeps it busy until its call gives up: at most about four minutes (two for Google Gemini).

### Status Indicator

- **● (Green)**: AI is configured and ready
- **○ (Gray)**: AI not configured - click ⚙ to set up

## Working with Nodes

### Adding a Node

1. Select parent node in tree
2. Click the **Add** button (or press Ctrl+A). The dialog's title names the
   parent.
3. Fill in node details:
   - **Name**: Descriptive name
   - **Type**: Event, Gate, etc.
   - **Probability**: Base probability (0.0-1.0)
   - **Logic Gate**: AND or OR (for nodes with children)
   - **Notes**: Optional description

In the web app:

- **Probability** starts empty and has to be filled in. Enter in **Name**
  moves to it. For an event that will get children of its own the value is
  not used; enter 1.
- **OK** adds the node and closes the dialog. **OK and add another**
  (Ctrl+Enter) adds it and clears the dialog for the next node under the
  same parent; Type and Logic Gate are kept. Escape closes the dialog.
- The parent stays selected, so the next Add makes a sibling. The new node's
  row is shown in the tree and marked for a moment. To add beneath the new
  node, select it first.

### Editing a Node

1. Select node in tree
2. Click the **Edit** button (or press Ctrl+E)
3. Modify any fields
4. Save changes

In the web app, Edit opens the **Details** tab with the caret in **Name** and
the name selected. Each field is saved when you press Enter or leave it.

### Deleting a Node

1. Select node in tree
2. Click the **Delete** button (or press Ctrl+D)
3. Confirm deletion
4. All children are also deleted

In the web app the confirmation says how many nodes will be deleted, and it
opens with the focus on **Cancel**: press Tab and Enter, or click
**Delete**, to confirm.

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

In the web app an OR result below 1e-3 is computed in the mathematically
equal form `r ← r + Child × (1 − r)`, one input at a time, which keeps every
digit of very small values. (The product form cancels there: the legacy
desktop app, and the web app before 1.7.1, gave OR(1e-17, 1e-17) = 0 and
OR(1e-15, 1e-15) = 1.998e-15.) The MCUB is accumulated the same way.

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

Nodes with zero probability are marked with a ✖ in the tree view. In the
diagram, a calculated probability of exactly 0 is shaded light blue.

**Common Causes**:
- Base probability set to 0.0
- In FTA: child with 0.0 probability in AND gate
- In ETA: parent has 0.0 calculated probability

## Analysis features (1.7)

Everything in this section is in the **web app** only. The legacy desktop app
is frozen and has none of it; see
[Desktop app compatibility](#desktop-app-compatibility) for what happens when
it opens a 1.7 file.

Most of the analysis features (all but validation and the DOCX report) work
on **fault trees** (FTA mode). In ETA mode the analysis tabs show a notice,
and the API returns `409 MODE_UNSUPPORTED`.

### Basic and Advanced mode

The top bar has an **Advanced** switch. It is **off** by default, and the
choice is remembered per browser (`localStorage` key `fta.advanced`). It is
not saved in the document.

The switch only changes what the UI **shows**. The calculations, the files
and the API are identical in both modes, and switching never changes or
removes data.

| | Basic (switch off) | Advanced (switch on) |
|---|---|---|
| Bottom tabs | **Details** and **Validation** | all twelve tabs |
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
  1e4: `1.00e-7`, `2.35e-4`, `1.23e4`.
- A number with more integer digits than significant figures is rounded and
  written plain: 1234 at 3 figures is `1230` (importance measures such as
  RAW can be that large).
- An exact tie rounds up, as `toPrecision` does: 0.25 at 1 figure is `0.3`.
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
| **Grid** | advanced | One row per basic event with name, model, λ, T, τ, μ, q, source and tags in one table. Sort, filter, edit in place, and paste a block from Excel. |
| **Quantification** | advanced | The mission time, and the selected event's model (fixed / rate / standby / repairable), parameters, data source and uncertainty. Also a table of all basic events. |
| **CCF groups** | advanced | Common-cause failure groups with a beta factor or alpha factors: list, create from the selected basic events, edit, delete, status (`Applied` or `Not applied: <reason>`), the assumptions. See [CCF groups](#ccf-groups-beta-factor-and-alpha-factor). |
| **Cut Sets** | advanced | Minimal cut sets ranked by probability, with their share, MCUB, rare-event and tree-walk values. Click a row to highlight its events. |
| **Importance** | advanced | Fussell-Vesely, Birnbaum, RAW and RRW per event. An optional FV colour overlay on the diagram. |
| **Uncertainty** | advanced | Monte Carlo on the lognormal parameter uncertainties: mean, median, 5th and 95th percentiles, standard deviation and a histogram. |
| **What-if** | advanced | Multiply the main parameter of chosen basic events by a factor from 1/100 to 100 and see the nominal and what-if parameter, q, top event and their ratio. Nothing is saved or exported. See [The What-if tab](#the-what-if-tab). |
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
the clipboard (spreadsheet-safe, see [CSV from the browser](#csv-from-the-browser)).
Clicking a row outlines its events in the tree and the diagram;
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

**Grid, Traceability, FMEA and Report tabs** are described in their own
sections below.

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
  every such event and is one undo step. An own T that is not a valid number
  (text, negative or NaN, in a file edited by hand) does not fall back to the
  mission time: it counts as a missing parameter (see below).
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
- **Implausible rates.** A λ above 1e-2 /h (an MTBF under 100 h), or a rate
  event whose q reaches 0.999, is reported as `RATE_IMPLAUSIBLE`. It usually
  means FIT or per-year values were entered as per hour.
- **Data source.** The free-text *Data source* field (`quant.source`) keeps
  provenance, such as "OREDA 2015 p. 123" or "vendor data sheet", in the file.
  It is exported in the Excel **Events** sheet (`Source` column).

### Gate and event types

The gate is stored in `gateType`. The legacy `logicGate` field (AND/OR) is
always kept as the nearest AND/OR **projection** of it, so older readers still
get the closest coherent answer.

Without a `gateType`, `logicGate` is read as in 1.6: AND, and anything else
OR. One exception: a file that holds an advanced gate name in `logicGate`
(`KOFN`, `XOR`, `INHIBIT`, `PAND` or `TRANSFER`, written by hand or by another
program) is read as that gate. On load the name moves to `gateType`,
`logicGate` becomes its projection, and the Validation tab lists a load repair
(`LOAD_REPAIR`, kind `gate_type_promoted`).

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
- The **top event's node** shows the same number: the diagram's top box,
  Node Details for the root and the report's diagram give the MCUB, marked,
  with the root's tree-walk value beside it
  ([The top box](#the-top-box-headline-and-tree-walk)).
- It refreshes from `GET /api/analysis/summary` about 400 ms after each edit
  to the tree, the analysis settings or the mode. A slower, outdated answer is
  discarded. If the request fails, the headline quietly shows the tree walk.
- In **ETA mode** the headline shows the root's calculated value and no
  badge.

**Truncation.** Cut sets are limited by *max order* (default 6), *max count*
(default 5,000) and *cutoff probability* (default 1e-15). Truncation by
order or cutoff only drops sets, so a truncated MCUB or rare-event value reads
below the full analysis, though it can still be above the exact value. This is
usually negligible because the dropped sets are the least probable ones.
Truncation by count keeps the most probable sets at each gate and is an
approximation: it usually reads low too, but on a tree with repeated events, a
shared CCF event included, it can read high. When a result is
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

**Limits.** **Max order**, **Max count** and **Cutoff** start from the
limits saved in the document. A value you type applies to this tab's runs
only, and the tab marks it **This run only**: the headline, Importance and
the report go on using the document's limits. **Save as document defaults**
stores what you typed; **Reset** goes back to the document's limits and runs
again.

When the limits leave no cut set at all (Max order 1 on a tree whose
smallest cut set has two events), the tab says *No cut sets within these
limits* and names the limit. That is not a statement about the tree: the
top event can still occur. The min-cut upper bound and the rare-event sum
are not shown then, because with no cut sets both would read 0.

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
  warning says when sets were dropped (`MC_CUTSETS_TRUNCATED`). The sets are
  chosen by their point values, so an uncertain event in none of them (one
  whose point value is 0, say) is not sampled at all; a warning names such
  events (`MC_EVENT_NOT_SAMPLED`).

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

### The What-if tab

The **What-if** tab answers "what would the top event be if this valve failed
ten times as often?" without touching the document. You multiply the
parameter of one or more basic events by a factor and watch the top event
move. It works on a copy: nothing is written to the file, the undo history or
any export. The tab is in Advanced mode, after **Uncertainty**, and works on
fault trees only. In ETA mode its tab button is greyed and struck through and
opening it shows the same notice as the other analysis tabs; in Basic mode the
tab is hidden.

**Try a factor.**

1. Open the **What-if** tab and pick a basic event in the **Event** list. The
   list starts at the event selected in the tree, and selecting another basic
   event in the tree moves the list to it; choosing in the list never changes
   the tree selection.
2. Move the **Factor** slider, or type a number in the field beside it. The
   slider is logarithmic, from 1/100 to 100, with the factor 1 in the middle
   (exactly 1, with no rounding). Left and Right move it by a small step, Home
   and End go to the ends, and **PageUp** and **PageDown** move by one decade,
   so 0.1, 1, 10 and 100 are reached exactly; in between the factor has four
   significant figures (3.162, say). The field takes `10`, `1e1`, `0.1`, `.5`
   and `1,5` (a decimal comma, as 1.5). It refuses a number outside 0.01 to
   100, `0`, a blank field, text, and text that could be read two ways such as
   `1,500`; a message appears under the field and the factor stays as it was.
   The field commits when you press Enter or leave it, and **Esc** puts the
   current factor back.

**What the factor means.** The factor multiplies the event's **main
parameter**, as the Monte Carlo run does (see
[Uncertainty (Monte Carlo)](#uncertainty-monte-carlo)): λ for the models
*rate*, *standby* and *repairable*, and q for *fixed*. T, τ and μ are not
scaled. The event's probability q then follows from its model. A q above 1 is
set to 1 and **clamped to 1** is shown beside it. Several events can carry a
factor at the same time; each stays active when you pick another event, and the
top event reflects all of them.

**The seven numbers.** For the picked event the table shows, for the
**Nominal** value and the **What-if** value: the main parameter (λ in the unit
chosen in the Quantification tab, /h, /y or FIT, or q for the fixed model), the
probability q, and the **Top event**, and then the **Ratio** of the what-if top
event to the baseline top event. The **baseline** is the headline of the
document with no factor, the number in the top bar. The q cells, the top event
and the ratio use the significant-figures setting; the λ cells follow the λ
unit instead and are not rounded to the setting. The top event is worked out
with the headline's own method (see
[Top-event value](#top-event-value-tree-walk-mcub-and-rare-event)):

- **MCUB** over the document's cut sets with the changed probabilities. This
  is always the method when a CCF group is applied. The cut sets are those
  found with the nominal values. When the document's **cutoff** left out cut
  sets that have a probability above 0, the tab says **cut sets from nominal
  values**: a set that would pass the cutoff only after the factor is not in
  the what-if number.
- The **tree walk**, when that is the headline's method.
- **No number**, when the headline is incomplete. That happens when a CCF
  group is applied and the cut sets could not be completed (time, an error, or
  the headline's own cap of 2,000 sets). The tab then says so and shows the
  event's own numbers only.

The ratio shows a dash when the baseline is 0 and the what-if value is not.

**The banner and Reset.** While any factor is not 1, the banner **What-if
values, not saved** is shown above the controls. It lists one chip per changed
event (`name × factor`) with its own **Reset**, and a **Reset all** button. The
chip strip scrolls when many factors are active. Reset puts that event back to
1; Reset all puts every event back, and the what-if top event is then exactly
the baseline.

**CCF groups.** A factor on a member of an *applied*
[CCF group](#ccf-groups-beta-factor-and-alpha-factor) applies to **every member** of the group,
and the tab says so under the table ("This event is in the CCF group ... The
factor applies to every member: ..."). The sliders of all its members show the
same factor, and moving it on another member replaces it. The shared CCF event
and the independent parts are worked out with the group's own formula from the
new total probabilities. A group that is not applied is ignored: its members
are scaled one by one (with a caution).

**What is never changed.** The factors live in the browser only. They are not
saved in the file or the recovery copy, not in a CSV, Excel, DOCX or diagram
export, and not in what is sent to the assistant. A what-if makes no undo step
and does not mark the document modified; Save writes the nominal values even
while factors are active. To keep a value, type it into the document.

**When the factors go back to 1.** Every factor returns to 1 when the document
changes: New, Open, Import, an example, a mode switch, Undo, Redo, any edit (in
the Details, tree, Quantification, Grid, CCF groups or settings, or the
assistant's changes), and any change made in **another browser window** of the
same editor (noticed when you come back to this window, or at your next move of
the slider). When factors are dropped this way the tab says **The document
changed, so the factors were reset to 1.** until your next input, Reset or
picking another event. Save is not a change, and switching Advanced off and on
keeps the factors.

**Speed.** The first what-if after an edit has to build the baseline, which
means finding the cut sets (also when the headline is the tree walk), so the
tab shows "Computing the baseline…" for about as long as the headline takes.
The baseline is then kept for that version of the document, and the top event
follows the slider in a fraction of a second. On the 301-node test file (252
basic events, ten CCF groups) it took about 0.1 s or less after the slider
stopped. If the headline's own time budget (2 s) ran out, no baseline is kept:
every move then takes as long as the headline, about 2 s, because the baseline
is built again each time.

**The caution line.** While a factor is not 1, the tab can show a short
caution about the what-if values, in English or Japanese. A small **Caution**
badge appears in the empty top-left cell of the table (it takes no room and
moves nothing); the full line is under the table. Click the badge, or press
Enter or Space on it, to bring the line into view; hovering the badge shows
every caution. The line shows when, for the values with the factors applied:

- a member of a CCF group that is not applied at baseline, whatever the reason,
  has a factor other than 1; the what-if scales it alone, without the CCF
  event;
- a member of a CCF group that you scaled reaches a total probability of 1 or
  more. Typed into the document, the group would not be applied;
- a member of such a group has a total probability Q_t above 0.01, where the
  CCF model for small probabilities becomes rough;
- a scaled standby event has λ·τ above 0.2, where the λτ/2 formula is poor;
- the cut sets are limited by the document's **max order** or **max count**
  (or by the headline's own cap of 2,000 sets), so some may be missing from the
  what-if number. The cutoff alone is not this: it has its own note, **cut sets
  from nominal values**, above.

The line names the first caution and adds "(and N more)" when there are
several; the badge title lists them all. It is a hint, not a result and not the
list of warnings: type the value into the document to see the full Validation
message. Only events and groups you scaled count, and nothing shows while every
factor is 1 or after **Reset all**, even if the document's own values would
raise the same warnings.

**Limits of the what-if values.** Read these before you trust a what-if number
that is far from the baseline. They are the assumptions of the calculation, not
errors in it.

- *Warnings.* The document's own values raise warnings (in the Validation
  tab, and for groups also in the CCF groups tab). The tab shows a caution (see
  above) for `CCF_Q_ONE`, `CCF_HIGH_Q` and `STANDBY_LARGE_LT`, but not the
  full Validation message. `CCF_NOT_APPLIED` is not one of these warnings: it
  is a caution the tab adds for a group that is not applied at baseline.
  `RATE_IMPLAUSIBLE` is still not raised for what-if values: a λ above 1e-2 /h,
  or a *rate* event whose q is 0.999 or more (most likely a unit mix-up).

  To see the full warnings, type the value into the document. Undo takes it
  back. For a CCF group every member needs the value: typing it into one member
  makes the members differ and the group is then *Not applied*, so
  `CCF_HIGH_Q` does not appear. A Grid paste can put the value into all members
  in one undo step; otherwise it is one step per member.
- *A group that is not applied at baseline.* A group can be left out for a
  reason such as a member with Q_t = 1, or members that differ. The what-if
  does not switch it on: it scales the members alone and leaves the CCF event
  out, whatever the factors do. The tab shows a caution for it
  (`CCF_NOT_APPLIED`). The number can then be far **below** (or slightly above)
  the same document typed in by hand, where the group is applied. Examples, for
  an AND of two members of a beta-factor group with β = 0.1:
  - Members at q = 1 (group not applied, top event 1). A factor of 0.5 on both
    gives 0.25 in the what-if; typed into the document (q = 0.5 on both) the
    top event is 0.242375. A factor of 0.01 on both gives 1e-4 in the what-if
    and 0.001080919 typed (q = 0.01 on both), 10.8 times higher.
  - Members that differ, A at 1e-3 and B at 2e-3 (group not applied, top event
    2e-6). A factor of 2 on A gives 4e-6 in the what-if; typed into the
    document (A and B both 2e-3) the group is applied and the top event is
    2.03239352e-4, 50.8 times higher.
- *A factor that raises a member to 1.* In an applied group the q reaches 1
  (**clamped to 1** is shown when the value would pass 1), but the group stays
  applied and splits that value with its β, so each member fails through its
  independent part (0.9) and the shared CCF event (0.1) and not with
  certainty. Two members at q = 0.5 with β = 0.1 and a factor of 10 give q = 1
  for both and the top event 0.829 for the AND of the two. The tab shows the
  caution line for it (`CCF_Q_ONE`). Typing q = 1 into
  the document would leave the group not applied and the top
  event would be 1: the what-if is 17.1 % **lower**, so it is not a
  conservative figure.
- *Cut sets.* With an MCUB headline the cut sets come from the nominal
  values and the cutoff gets the note above. Cut sets can also be left
  out by the document's **order** limit, its **count** limit, or the headline's
  own cap of 2,000 sets. A factor on an event that is only in cut sets left out
  for any of these reasons changes nothing: the ratio stays 1, and the tab shows
  the caution line (not for the cutoff alone: that is the note above). The
  Cut Sets tab shows an order or count limit that left sets out, and the
  **≈** marker in the top bar (see
  [Top-event value](#top-event-value-tree-walk-mcub-and-rare-event)) shows the
  2,000-set cap. An order limit or the cutoff only drops sets, so that MCUB
  reads below the full MCUB, though it can still be above the exact value. A
  count limit or the 2,000-set cap usually reads low too, but it works inside
  each gate, so on a tree with repeated events it can also read high. A shared
  CCF event counts as a repeated event, so a count limit can do this with an
  applied group too. Treat the number as an estimate, not a bound, in the
  baseline and in the what-if alike. Example, with a count limit of 1: the top
  event is A OR (B AND C), with A = 1e-3 and B = C = 0.1, and B has an OR link
  to A, so A is a repeated event and the headline is the MCUB. The cut sets are
  {A} at 1e-3 and {B, C} at 0.01, and the limit keeps only {B, C}, so the
  baseline is 0.01. A factor of 100 on A leaves the top event at 0.01 (ratio
  1), while A typed into the document at 0.1 gives 0.1, ten times higher.
  Without the limit the baseline is 0.01099 and the factor gives 0.109. With an
  applied CCF group, the 2,000-set cap, a time-out or an error give no number
  at all. Without an applied group, when the time budget runs out or the cut
  sets fail there are no cut sets, and the headline and the what-if use the
  tree walk, which moves with the factor but, on a tree with repeated events,
  is the number the
  [Top-event value](#top-event-value-tree-walk-mcub-and-rare-event) section
  warns about.
- *The MCUB itself.* It is close to exact when the cut-set probabilities are
  small and loosens as they grow, in the baseline and in the what-if alike. For
  (A AND B) OR (A AND C) with every event at 0.5 the MCUB is 0.4375, where the
  exact value is 0.375.
- *Only what you move moves.* A factor changes the chosen event (and the other
  members of its applied group) and nothing else. Events stay independent of
  one another, so events that share a cause or a data source do not move
  together unless they are in an applied CCF group. The group's beta stays as
  stored, so a factor scales its independent and common parts together.
- *The factor field.* The field shows the factor with four significant digits.
  If you edit it, type the displayed text back and press Enter, the field
  commits that displayed (rounded) text as the new factor.

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
| `PROBABILITY_OUT_OF_RANGE` | error | FTA and ETA: a probability the engine uses is not a number from 0 to 1 (NaN, negative, above 1, non-numeric text or true/false, as a hand-edited or foreign file can hold). In FTA mode that is a basic leaf's own probability (not a house event's, nor one derived from a rate, standby or repairable model); in ETA mode every node's. Every result that uses it is wrong. | Enter a probability between 0 and 1 (for example 1e-4). |
| `CYCLIC_LINK` | warning | A link closes a loop (through children, links or a transfer). The engine uses the target's value from its children only, so the result is approximate. | Remove the link, or link to a node that is not above this one. |
| `TRANSFER_HAS_CHILDREN` | warning | A transfer gate has children, which are ignored. | Move them under the transfer target, or delete them. |
| `HOUSE_HAS_CHILDREN` | warning | A house event has children, so its on/off state is ignored. | Make it a basic event, or move the children. |
| `SINGLE_INPUT_GATE` | warning | An AND, OR or PAND gate below the top event has one input and no links, so it does nothing. | Add an input, or remove the level. |
| `DEFAULT_PROBABILITY` | warning | A basic leaf is exactly 1.0 with no model, so it has probably never been quantified. | Enter the real probability. |
| `PARENT_PROBABILITY_IGNORED` | warning | A gate's own probability is neither 1.0 nor its calculated value, and it is ignored. | Clear it (set it to 1.0), or make the node a leaf. |
| `STANDBY_LARGE_LT` | warning | Standby λτ > 0.2, where λτ/2 is inaccurate. | Shorten τ, or use the rate model. |
| `RATE_IMPLAUSIBLE` | warning | A rate, standby or repairable event has λ above 1e-2 /h (an MTBF under 100 h), or a rate event's q is 0.999 or more. This is almost always a unit mix-up, for example FIT or per-year values entered (or imported) as per hour. `params: {lambda, unit, q, model}`. | Check the unit: 1 FIT = 1e-9 /h, 1 /y = 1/8760 /h. Re-enter λ, or re-import with the right λ unit. |
| `NONCOHERENT_XOR` | warning | The tree has XOR gate(s), so cut-set results are approximate. | Use OR if both events can happen together. |
| `CUTSETS_TRUNCATED` | warning | The cut sets, expanded with the document's limits, were truncated, so values from the cut sets can read low or high. Shown in the Validation tab, `validate` and the DOCX report. | In the Cut Sets tab, raise the limits and click **Save as document defaults**. |
| `ETA_BRANCH_SUM` | warning | ETA only: the children's probabilities do not sum to 1 (±1e-6). | Adjust the branch probabilities. |
| `LOAD_REPAIR` | warning | The file was repaired on load: a duplicate id renamed, the top id changed, an invalid analysis setting reset, a stale gate type dropped, a repeated link dropped (it was counted twice), text that cannot be saved (an unpaired surrogate, half of an emoji) replaced with U+FFFD, or an advanced gate name written into the old AND/OR field promoted to that gate. Or an AI edit left a stale gate type that was dropped, or wrote an advanced gate name into the AND/OR field. | Check the node, and save to keep the repair. |
| `LINKS_REMOVED` | warning | Deleting a node (by hand or by the AI assistant) removed links or transfer targets (`transferTo`) that pointed to it. | Re-add the link or transfer target if the dependency still exists. |
| `UNDEVELOPED_EVENT` | info | The leaf is marked undeveloped. | Nothing needed, or develop it later. |
| `PAND_APPROX` | info | A Priority-AND gate is evaluated as AND × 1/n!. | Nothing needed; note the approximation in your report. |

The CCF groups (1.9) add the codes `CCF_MEMBER_NOT_BASIC`, `CCF_TOO_FEW_MEMBERS`,
`CCF_MEMBER_IN_TWO_GROUPS`, `CCF_MEMBERS_DIFFER`, `CCF_NO_PROBABILITY`,
`CCF_Q_ONE`, `CCF_BAD_PARAMETER` and `CCF_MEMBER_RENAMED` (errors: the group is
not applied), and `CCF_HIGH_Q`, `CCF_ZERO_Q` and `CCF_ORDERED_GATE` (warnings: the
group stays applied). The alpha-factor model adds `CCF_ALPHA_SIZE`,
`CCF_ALPHA_SUM` and `CCF_NO_TESTING` (errors) and `CCF_ALPHA_NORMALISED` (a
warning). Their texts name the group and the member in English and
Japanese; the table is in [CCF.md](CCF.md#applied-and-not-applied). Clicking
one opens the group in the CCF groups tab. They are not listed in ETA mode.

The top event is never `SINGLE_INPUT_GATE`, because a top event that restates
its one cause is normal practice. An empty document is never
`DEFAULT_PROBABILITY`. In ETA mode only `ETA_BRANCH_SUM`,
`PROBABILITY_OUT_OF_RANGE` and the session notices are reported.

`LOAD_REPAIR` and `LINKS_REMOVED` are *session notices*. They are collected
while the document is open and are not saved in the file. A load repair is
not undone. A notice raised by an edit belongs to that edit: `LINKS_REMOVED`
(from a delete, by hand or by the AI assistant), and a stale gate type
dropped or an advanced gate name promoted after an AI edit (the notice
names the AI assistant).
Undoing the edit removes its notice, and redo brings it back.

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
Press Enter in the search box to select the first match, Enter again for the
next and Shift+Enter for the one before; the caret stays in the box.

### The Grid tab: every basic event, paste from Excel

The **Grid** tab (Advanced mode) shows one row per basic event: a leaf that is
not the top event, a house event or a transfer. Use it to read and edit many
events at once, or to paste a block of values from a spreadsheet. It is not
available for an event tree (ETA mode); its tab is greyed and says so.

| Column | Content | Unit |
|---|---|---|
| ID | The node id. Read-only. | |
| Name | The event name. | |
| Model | The model name as in the Quantification tab (Fixed probability, Failure rate, ...). A paste also accepts `fixed`, `rate`, `standby` or `repairable` and the names in either language (see [Quantification models](#quantification-models)). | |
| λ | The failure rate. | /h, /y or FIT, as chosen in the unit picker in its header |
| T | The exposure time of the `rate` model (blank: the mission time). | h |
| τ | The test interval of the `standby` model. | h |
| μ | The repair rate of the `repairable` model. | /h |
| q | The probability. Editable only for the model `fixed`; on the other models it is computed from the model and read-only. Shown with your significant-figures setting. | none |
| Source | The data source. | |
| Tags | Free tags, shown and typed separated by `; `. A comma does not separate tags here (unlike the Traceability tab); use `;`. The full-width `；` and `、` also separate tags. | |

The headers name the units. Whatever unit the λ picker shows, the value is
stored per hour (8,760 h per year, 1 FIT = 1e-9 per hour); the picker is the
same setting as in the Quantification tab. A cell that the event's model does
not use is greyed out. A blank T falls back to the mission time. The
**Columns** button hides or shows columns; a paste fills only the visible
ones.

**Typing in a cell.** Click a cell and press Enter or F2 (or double-click it)
to edit it; Enter or leaving the cell saves, Escape cancels. A cell takes the same text as
the matching field elsewhere, and means the same number: for q, what the
Details tab takes; for λ, T, τ and μ, what the Quantification tab takes. A
value the field would refuse is refused here too, with the reason.

**Sort and filter.** Click a column header to sort by it (ascending first), and
again to reverse the order. Rows with an empty cell in that column come last.
The filter box keeps the rows that contain the text in any visible column;
the line above the table says how many of the events are shown.

**Paste from Excel.**

1. Copy the cells in Excel. Leave out the header row.
2. In the Grid, click the cell where the block should start, then press
   Ctrl+V.
3. The block fills from that cell to the right over the visible columns and
   downwards over the visible rows, **in the order the grid shows them**. Each
   value goes to the event of its row, so a sort or a filter does not send a
   value to the wrong event. Rows hidden by the filter receive nothing.
4. The paste is one step: **Undo** (Ctrl+Z) restores all of it.

An empty cell leaves that value unchanged. A line break at the end of the
clipboard is ignored, and Excel's quoting of cells with tabs or line breaks is
read (such a cell is kept in a text column and refused in a number column).
In the ID column a value equal to the row's id is ignored. In the q column of
a model other than `fixed`, a value equal to the shown q is ignored.

**The summary.** Beside the grid, **Last paste** gives the number of rows
applied and lists every refused row with its row number on the clipboard, the
column and the reason. One invalid cell refuses the whole row and nothing of
that row is applied; the other rows are applied. Typical reasons:

| Message | Meaning |
|---|---|
| id does not match this row | The pasted id differs from the id of the event in that row. |
| q is computed from the model | q was pasted onto an event whose model is not `fixed`, with a value other than the shown q. |
| *column* is not used by the model of this row | For example a λ for a `fixed` event. |
| A value the field does not accept | The same reason the field would give, for example a probability above 1. |
| Extra cells or rows | Cells right of the last visible column and rows below the last visible row are refused; no event is created. |

A clipboard with more than 2,000 rows is refused as a whole, with a message.

**If the analysis changed.** If the analysis changed between the moment the
grid was drawn and the paste (for example an edit, an undo or another
document), nothing is applied, the grid is redrawn, and the tab says "The
analysis changed; paste again". Paste again from the cell you want.

The same paste is available to scripts as `POST /api/grid/paste`; see the
[API reference](API_REFERENCE.md#grid-paste).

### FMEA import

The **FMEA** tab turns FMEA worksheet rows into basic events, and keeps the
FMEA row id on each node so the two analyses stay linked.

1. **File.** Click **Choose file…** to pick a `.csv` or `.xlsx` file with the
   editor's file browser, or type a path. For this dialog the browser lists
   `.csv` and `.xlsx` files instead of `.json`. The file must be within the
   browser's root and at most 10 MB, and the tool reads at most 20,000 rows
   and 200 columns. `.xlsx` needs `openpyxl`; otherwise save the sheet as CSV.
   The first non-empty row is the header. A preview shows the first 50 rows,
   as they will be imported. For a workbook, pick the sheet. A CSV is read as
   UTF-16 or UTF-32 when it starts with a byte-order mark, else as UTF-8 (with
   or without a BOM), else as Shift_JIS (cp932) when the text has kana, else as
   Windows-1252, else as cp932 (kanji-only text), and as Latin-1 as a last
   resort.
2. **Columns.** Map each import field to a column: *id, item, mode, cause,
   severity, occurrence, detection, rpn, λ*. A mapping is suggested from
   English and Japanese header words. An AIAG-VDA *AP* (action priority,
   H/M/L) column is not suggested for RPN.
3. **Target and values.**
   - *Parent*: the node the new events go under. It defaults to the selected
     node. If the parent is a leaf, it becomes an OR gate. It cannot be a
     transfer gate.
   - *λ unit*: `/h`, `/y` or `FIT`. It is suggested from the λ header, for
     example `λ (FIT)`, `故障率 [/年]` or `rate per hour`. When the header does
     not name a unit, it is suggested from the size of the values: a median
     of 1 or more suggests FIT, a median from 1e-3 up to 1 suggests `/y`,
     anything smaller `/h`. λ is converted and stored per hour. If FIT values
     are imported as `/h` anyway, Validation reports `RATE_IMPLAUSIBLE`.
   - *Update existing rows*: see the rules below.
   - *Occurrence table*: the editable map from occurrence rank to
     probability.

Import rules:

- **Key.** Each row's key is the mapped id column. If no id column is mapped,
  the key is "item / mode". A row with neither is skipped.
- **Blank items.** A row that has a failure mode but a blank item takes the
  item of the row above. The usual layout writes an item once over its failure
  modes, and merged cells read as blank below the first.
- **Re-import updates in place.** With *update* on (the default), a row whose
  key equals an existing node's `fmea.id` anywhere in the tree updates that
  node: its `fmea` block, its name and, for a leaf, its numbers. Only the
  fields whose columns are mapped change (a mapped column left blank empties
  its field), and the name is re-derived only when the item or mode column is
  mapped. With update off, such a row is skipped. A key repeated within the
  sheet is imported once.
- **Rows gone from the sheet.** Nodes from an earlier import of the same
  sheet whose key no row holds any more are kept, not deleted, and listed
  after the import.
- **New rows** become leaf events under the parent, named "item – mode".
- **Numbers.** The first rule that applies is used:
  1. A λ value gives the **rate** model with that λ.
  2. Otherwise, an **occurrence rank** gives a fixed probability from the
     occurrence table.
  3. Otherwise, a new event stays at 1.0 and is marked **undeveloped**, and an
     existing node's numbers are left alone.

  Re-importing merges into an existing `quant`, so your T and uncertainty
  survive.
- **Number formats.** A decimal comma (`1,5`) and European grouping
  (`1.200,5` is 1200.5) are read. In a comma-delimited CSV, where a comma
  cannot be the decimal mark of an unquoted number, `1,200` and `12,345.6` are
  thousands groupings (1200 and 12345.6), as Excel writes a `#,##0` column;
  elsewhere `1,200` is 1.2.
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
and skipped (with reasons), and the nodes of an earlier import whose rows are
no longer in the sheet. It also highlights the imported nodes in the tree and
the diagram.

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
| CCF groups | Written after Assumptions whenever the file has CCF groups; it has no tick box. Per group: name, model, parameters, testing scheme, source, members and status; the line `Not applied: <reason>. Results exclude this group.` for each group left out; the formulas with sources and pages, the assumptions and a note to check the results with a qualified engineer. Also written in ETA mode, where every group is not applied |
| Diagram | The diagram image (see below). When the top box shows the MCUB headline, a sentence under the picture says so and gives both values. With CCF groups applied, a sentence says that the gates above a member show their MCUB, or `n/a (CCF)` |
| Events | The basic-event table: id, name, kind, model, parameters (λ, T, τ, μ, MTTR), q, calculated value and source (data provenance) |
| Cut sets | The top 50 by default, with totals, MCUB, rare-event value and a truncation note |
| Importance | The top 30 by FV, by default |
| Uncertainty | **Off by default.** When selected, a Monte Carlo run of at most 5,000 samples (30 s) is made for the report. |
| Validation | Every issue, as the Validation tab lists them, including `CUTSETS_TRUNCATED` (judged with the document's cut-set limits, not the report's override; the report's own cut sets are reused when they use the document's limits, so a large tree that exceeds the tab's 2 s budget is still judged) |
| Traceability | Every node that has trace data |

Choose the language (English or Japanese). In Japanese, the report uses
Meiryo for East-Asian text.

**The report diagram** is the PNG of the diagram as your browser shows it, so
it has the true symbols in the symbols style. When no browser image is sent,
for example from the CLI, the diagram is rendered by a native Graphviz `dot`
in the compact style. When neither is available, the report says the diagram
is not available. ETA documents are accepted; the fault-tree-only sections
say they do not apply.

**Excel export** (**Export Excel** here, or **Excel** in the action bar) writes
three sheets:

- **FTA**: the 1.6 hierarchical sheet. With CCF groups applied, the `Calc:`
  text of a gate above a member reads `<value> (MCUB, CCF)` or `n/a (CCF)`,
  not its tree-walk value.
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
  approximations and the truncation flag. A file with CCF groups adds the rows
  *CCF groups applied* and *CCF groups not applied*: the number of groups, and
  in the note column their names, and for a group not applied its reason.

*Calculated probability* in the Events sheet is the tree-walk value of every
node, the top event included, so the column is one quantity (the CCF
exception below applies). When the headline is the MCUB, the top event's
cell has a comment that gives the headline and points to the Analysis sheet, and the *Tree walk* row there
notes that it is the value the Events sheet shows for the top event.

**CCF exception.** With CCF groups applied, a gate above a member of a group
shows its MCUB instead of its tree-walk value, because the tree walk cannot see
the shared CCF event. When the cut sets are incomplete, the cell reads
`n/a (CCF)` and has a comment that says why. A member itself keeps its `Q_t`.

**Export events CSV** builds the same per-event table as a CSV in the browser.

#### CSV from the browser

The browser's CSV output — **Export events CSV** here, and **Copy CSV** in the
Cut Sets and Traceability tabs — is meant to be opened in a spreadsheet, so a
text cell that a spreadsheet would run as a formula (one starting with `=`,
`+`, `-`, `@`, a tab or a carriage return, such as `+24V supply fails` or
`=HYPERLINK(…)`) gets a leading apostrophe. Numbers are never prefixed, so
probability and rate columns stay numeric. The CLI's `--csv` is the raw data
for scripts and is not changed this way.

### The top box: headline and tree walk

Every box in the diagram shows its node's calculated probability, which is
the tree-walk value (with one exception, see below). For most trees the top
box is then the headline. For a tree with repeated events (links, transfers)
or an XOR gate the headline is
the MCUB, and until 1.7.3 the top box showed the root's tree-walk value
instead, so the diagram disagreed with the top bar (0.0349 against 0.0684 in
the Challenger example).

When the headline is the MCUB, the top event shows it, marked, with its
tree-walk value beside it:

| Where | What the top event shows |
|---|---|
| Diagram, compact boxes | `P_calc:0.0684 (MCUB) \| tree walk 0.0349` |
| Diagram, standard symbols | `Q=0.0684 (MCUB)` and, on a smaller line, `tree walk 0.0349` |
| Node Details, root selected | **0.0684** (MCUB) · tree walk 0.0349 |
| DOCX report | The diagram as above, with a sentence under it |
| Excel | The Analysis sheet has both values; the root's cell in the Events sheet has a comment |

This holds in both layouts and both themes, in the SVG and PNG exports and in
`POST /api/render`. A line above the diagram says what the top box shows
while it shows the MCUB.

**Only the top event.** Every other box keeps its tree-walk value, with one
exception: with CCF groups applied, a gate above a member shows its MCUB, or
`n/a (CCF)` (see [CCF groups](#ccf-groups-beta-factor-and-alpha-factor)). A
cut-set value for each gate would need one cut-set expansion per gate, and it
would be a different quantity: the tree-walk values are the ones that combine
along the edges you see, child to parent.

**When the top box stays a tree-walk value:** when the headline is the tree
walk (no repeated events and no XOR), in ETA mode, and when the cut sets
could not be had in the headline's 2 s budget or were cut short by the
headline's own cap of 2,000 sets (the **≈** marker with *Quick estimate*).
In the last case the top bar shows an estimate from the sets the cap kept, and the box
does not repeat it.

### Diagram styles and layout

**Settings** on the diagram toolbar opens the **Diagram settings** popover,
which has two display settings. They are remembered per browser
(`fta.diagram.settings`) and are not saved in the file.

In **ETA mode** neither style draws a gate: an event tree has branch points,
not gates. The compact boxes leave out `Gate: ...`, and the symbols style
draws the description boxes only, joined directly, each with its own
probability and that of the path down to it (`q=<q> | Q=<Q>`).

- **Style**
  - **Compact boxes**: the 1.6 two-row boxes. The meta row reads
    `Gate: <gate> | P:<q> | P_calc:<Q>` for a gate and `P:<q> | P_calc:<Q>`
    for a basic event (1.6 also showed a meaningless `Gate: OR` there). The
    1.7 gates appear as `2/3`, `XOR`, `INHIBIT`, `PAND` or
    `TRANSFER→<target>`. A non-basic leaf shows `House: ON|OFF`,
    `Undeveloped` or `Conditioning` in front of the probabilities.
  - **Standard symbols** (default): a description rectangle for every node, with an
    IEC 61025 / NUREG-0492 gate or event symbol under it. Under the name,
    in bold, a gate shows `Q=<Q>` and an event `q=<q>`; an event whose
    calculated value differs from its own (it has links) shows
    `q=<q> | Q=<Q>`. A transfer gate's
    ignored children are drawn dotted. A conditioning event is drawn as an
    ellipse hanging off its INHIBIT gate. Clicking a gate symbol selects its
    node.
- **Layout**: *Left → right* (default, as in 1.6) or *Top → down*.

In the symbols style the lines are right-angled up to about 50 nodes. A larger
tree is drawn with straight-segment lines, because the in-browser Graphviz
cannot route right-angle lines for it.

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

### Working in the tree, the bottom panel and ETA mode (after 1.7.3)

**What a tree row shows.** At the right of the name, a node with inputs has
its gate (`AND`, `OR`, `2/3`, `XOR`, ...) and every row has a probability:
the calculated one for a gate, its own for an event. Hover either for what
it is. A row is bold red only for an **event** whose probability is exactly
1; a gate is never red for its unused base value.

**Several nodes at once.** Ctrl-click or Shift-click rows to select several.
The right end of the bottom panel's tab strip then says **N selected**
instead of naming one node. What acts on all of them, each as **one undo
step**:

| Action | Result |
|---|---|
| `Delete` / `Ctrl+D` / **Delete** | Deletes every selected node with what is beneath it, after one confirmation that gives the total. |
| Drag one of the selected rows | Moves them all: onto a node (they become its last children) or between two rows. |
| `Ctrl+Shift+Up` / `Down` | Moves the block past the next sibling. The nodes must share a parent. |
| `Ctrl+Shift+Right` / `Left` | Moves the block under the sibling above it, or out to follow its parent. |

A selected node inside another selected node goes with that node. The root
is never moved or deleted. Details still shows the node clicked last.

**The bottom panel's height.** Details keeps the height you give it. Every
other tab has a height of its own, about 45 % of the window until you drag
the splitter while one is shown (double-click the splitter to go back). The
**△** button at the right of the tab strip enlarges the panel to all the
height there is, leaving a strip of the diagram; **▽** puts it back.

**ETA mode.**

- The headline in the top bar reads **Initiating event** (in FTA: **Top
  event**).
- **Quantification**, **Cut Sets**, **Importance** and **Uncertainty** work
  on the gates of a fault tree. In ETA mode their tabs are greyed and struck
  through, and the tooltip says why; opening one shows the same notice. The
  **Grid** and **What-if** tabs are greyed the same way, with the same
  tooltip, and **CCF groups** is greyed with its own tooltip (the groups stay
  in the file but are not applied).
- The diagram draws no gate or event symbols, and the tree rows no gate.
- The assistant's buttons read **Analyze ETA** and **Update ETA**.
- Switching the mode says what it did (*Switched to ETA (event tree)...*).
  Changing the title or the date no longer shows *Metadata updated.*

**Importance: Copy CSV.** Copies the table as shown (its sort order, the
numbers in full) to the clipboard, as on the Cut Sets tab.

**Uncertainty for every event.** **Lognormal EF=3 for all events without
one** gives each basic event that has no uncertainty distribution a
lognormal one with error factor 3 around its own value, in one undo step.
Events that have one, house events, undeveloped and conditioning events are
left alone. When no event the top event depends on has a distribution, every
sample is the same value: the tab then says so and draws no chart.

**Rare-event.** The Cut Sets figure labelled *Rare-event* is the sum of the
cut-set probabilities: an upper bound, not a probability. Above 1 the tab
marks it as such.

**Report.** **Colour the diagram by Fussell-Vesely importance** puts the
coloured diagram and its legend into the Word report. Without it the
report's diagram is plain, whatever is on screen.

**Type.** The Type box of a node offers **Event**, **Gate** and
**Intermediate**; any other text is still accepted.

**Messages.** A notice no longer carries a code such as `ROOT_PROTECTED`
(an error still does), and messages appear beside the AI panel instead of
over its **Send** button.

### Keeping your work (after 1.8.0)

**A recovery copy.** While an analysis has unsaved changes, the editor keeps
a copy of it on disk. If the editor then ends without your saving (a crash,
a power cut, its terminal window closed), the next start shows **Unsaved
work found** above the tree:

- **Restore unsaved work from <date> (<title>)** opens the copy as an
  untitled analysis marked as modified. **Save** then asks where to put it.
  The file the work had been opened from is not changed; the message names
  it, so you can compare the two and decide which to keep.
- **Discard it** deletes the copy after asking once.

The offer stays until you choose one of the two. Details:

- The copies are in the `recovery` folder of the editor's per-user folder:
  `~/.fta_editor/recovery/`, which on Windows is
  `C:\Users\<you>\.fta_editor\recovery\`. This is the folder that also
  holds the AI settings. It does not depend on the folder the editor works
  in.
- A copy is written 2 seconds after you stop editing, and at the latest 30
  seconds after a change while you keep editing. At most that much work can
  be lost.
- The copy is the same JSON that **Save** writes, with a small file beside it
  that holds the title, the original file's path and the time. It contains
  no API key.
- The copy is deleted when you save, when you start a new analysis or load
  another one (after you chose to save or to discard), and when the editor
  is stopped with Ctrl-C. Stopping the editor with Ctrl-C while an analysis
  is unsaved therefore discards it, as closing a document without saving
  does.
- A second copy of the editor that is running at the same time keeps its own
  recovery copy; neither offers the other's.
- At most five copies of ended sessions are kept. Older ones are removed
  when the editor starts.
- The file dialog cannot open or save in the `recovery` folder. A copy is
  only reached through **Restore**.
- An analysis larger than 10 MB is not copied.

**Two tabs.** If the editor is open in two browser tabs and you load a file
in one while the other has unsaved changes, the editor now asks before it
replaces them, whichever tab the changes were made in.

**Changing the folder the editor works in.** The editor reads and writes
inside one folder (your home folder unless it was started with `--root`).
To work somewhere else you no longer have to restart it:

1. Open **Load** or **Save As** and press **Change folder…**. The same
   button appears under the message that refuses a path outside the folder.
2. The editor opens your operating system's folder chooser. It may open
   behind the browser window.
3. Pick the folder. The file dialog then shows it, and it stays the editor's
   folder until the editor is closed. Closing the chooser changes nothing.

If the analysis that is open was saved outside the folder you picked, it
becomes untitled: nothing in it changes, and **Save** asks where to put it.
The choice is not remembered for the next start; use `--root` for that.

The folder chooser belongs to the editor program, not to the browser page.
A page cannot choose the folder for you, which is what keeps the folder a
limit on what the page can reach. Where the editor cannot open a chooser
(a computer without a display, or the packaged app on Linux or macOS),
**Change folder…** shows the command that starts the editor on another
folder instead.

### The assistant (after 1.7.3)

- **What is sent.** The setup dialog says it in one line: the analysis open
  in the editor (the whole tree with its names, probabilities and notes) and
  what you type go to the provider you choose. Nothing is sent before you
  press Send, Analyze or Update.
- **First choice.** With nothing configured the dialog opens on **Google
  Gemini**, which has a free tier. A saved choice is never changed.
  **Microsoft Copilot** says what it needs: an Azure OpenAI resource of your
  own.
- **Stop.** While the assistant is working, **Stop** gives the panel back
  and tells the editor to abandon the request. You can send a new one at
  once. The request cannot be taken back from the provider, but its answer
  is ignored when it arrives: it is not shown, not added to the
  conversation and never applied. What you had typed returns to the box.
  (Up to 1.8.0 a new request was refused as busy until the provider had
  answered.)
- **A message that did not get through** (the request failed, or the
  provider reported an error) is put back in the box to send again. A reply
  that is the provider's error is drawn as an error.
- **After a reload** the conversation is shown again, with the suggestions
  and the Update preview that still wait for an answer. The editor keeps it
  while it is running; **Clear Chat** empties it.
- **Suggested changes** name the node as a link (click it to select the
  node), and list what would change in words: `probability: 0.05 → 0.5`.
  A card made for another analysis is switched off when you press New or
  open a file.

### CCF groups (beta factor and alpha factor)

Redundant components can fail together for one cause. A **CCF group** (common-cause
failure group) lists basic events that are identical redundant components, such as
two feed pumps, and gives one number, the **beta factor β**: the fraction of a
component's total failure probability `Q_t` that is common to the whole group. (For
groups of 2 to 4 members the **alpha-factor model** is the other choice; it is
described [below](#alpha-factor-groups).) With a
group applied, the top-event value, the cut sets, the importance, the Monte Carlo
run, the report and the command line all include a shared CCF event. The formulas,
their sources with pages, the assumptions and worked examples are in
[CCF.md](CCF.md).

**Check CCF results with a qualified engineer before use.** The editor does not
judge whether β suits your components or whether they are really identical.

**Two models are included**: the beta-factor model and the alpha-factor model. CCF
groups are available in the web app; the frozen desktop app does not know them.

**Create a group.** (This is the beta-factor model, the default of a new group; see
[Alpha-factor groups](#alpha-factor-groups) for the other.)

1. Switch **Advanced** on and select two or more basic events in the tree
   (Ctrl+click or Shift+click). Only basic events can be members, and an event
   can be in one group only.
2. Open the **CCF groups** tab and press **New group from selection**. The editor
   below the table opens with a name (**CCF group 1**, which you can change) and
   the selected events as members.
3. Enter **β (dimensionless, 0 to 1)**. There is no default: you must choose it.
   The field reads `0.1`, `1e-1`, `10%` (as 0.1) and a simple fraction like the
   other number fields; a value outside 0 to 1, or text, gives a message beside
   the field and nothing is created. Optionally enter the **Source** (the data
   handbook and page β came from).
4. Press **Create group**.

To change a group, select its row and edit the name, β, source or members (each
member has an **×** to remove it; **Add selected events** adds the events selected
in the tree). To remove a group press **Delete group**. Each create, change and
delete is one undo step, and Undo brings a deleted group back.

**The table.** One row per group: name, model, parameters (`β = 0.1`), member
names, source and **status**.

- **Applied**: the group is in every number.
- `Not applied: <reason>`: the group is kept in the file but left out of every
  result, and nothing in the results hides that. The reason names the member, for
  example *"Valve D" differs from "Valve C"*. Typical reasons: a member is not a
  basic event or is not in the tree; fewer than two members; an event is in two
  groups; the members differ in model, parameters, probability or uncertainty
  (more than 1e-6 relative); a member has no probability or a probability of 1; β
  from a file is not a number from 0 to 1; or the document is in ETA mode. The full
  list of 12 checks is in [CCF.md](CCF.md#applied-and-not-applied).
- An applied group can carry a **Warning** line: a member's probability above
  0.01 (NUREG/CR-5485 p. 44 lists an independent event unavailability of 10^-2
  or less among the conditions of the beta-factor approximation, so check the
  result),
  a probability of 0 (the group has no effect), or a member below a PAND or XOR
  gate.

In **ETA mode** the tab is greyed and every status reads *Not applied: ETA mode*;
you can still open it, edit the groups and save, and the groups stay in the file.

The box under the table, **Assumptions**, states the six assumptions of the model
(the formula with its source and page, what `Q_t` is, what the CCF event does, that
the split is applied to `Q_t`, that the headline is the min-cut upper bound, and that
β and α are not sampled in Monte Carlo), ending with the engineer note. A seventh
item, the alpha-factor formulas, is added while the document has an alpha group.

In **Basic mode** the tab is hidden, but badges, the headline and
the Validation issues still show.

**What you see elsewhere.**

- **Tree and diagram.** Each member shows a `CCF: <group name>` badge. A group that
  is not applied reads `CCF: <group name> (off)`. Diagram badges are drawn in
  fault-tree mode only, not in ETA mode. A tree label keeps its width before the
  badge; the badge is shortened with an ellipsis when the name is long, and the full
  text is in its tooltip.
- **Headline.** With a group applied the top-event value is the min-cut upper bound
  and reads **MCUB, includes CCF (n groups)** (one group: *1 group*). When the cut
  sets cannot be completed (time, an error, or the summary's own cap) it reads
  **incomplete, CCF not included** and shows no number; the tree-walk value, which
  has no CCF in it, appears only under the label *tree walk, without CCF; cut sets
  cut short (time)* (or *error*, *summary cap*). When a group is left out the note
  **n CCF groups not applied** appears beside it, in Basic and Advanced mode.
- **Details.** The Details panel of a member keeps showing `Q_t` as the probability.
  A block under the **Calculated probability** line adds **CCF group**, **Q_t
  (total)**, **Independent part** (`(1 − β)·Q_t`) and **CCF event** (`β·Q_t`). For a
  member of an alpha group it shows the independent part `Q_1` and one **CCF event
  (alpha factor)** line for each CCF event that contains the member, with that
  event's probability. For a member of a group that is not applied it shows the
  reason instead.
- **Gates above a member.** A gate whose subtree holds a member shows its MCUB from
  the cut sets, marked *(MCUB, includes CCF)*, or **n/a (CCF)** when the cut sets
  are incomplete (a dash while the value loads). It never shows its tree-walk
  value, which is far too low for such a gate. In the diagram, the box of a member
  shows its `Q_t` with the independent part beside it, `(indep. 9.00e-4)`, and a
  line explains the gate values.
- **Cut Sets and Importance.** The CCF event is listed as `CCF: <group name>`; the
  member's variable as `<name> (independent part)`. Clicking a CCF cut-set row
  highlights every member in the tree and the diagram. Importance has a row for the
  CCF event and rows for the independent parts, and no row for the component as a
  whole.
- **Validation.** Every error or warning of a group is an issue with the group and
  the member named, in English or Japanese. Clicking it opens the group in the CCF
  groups tab (in Basic mode a message asks you to switch Advanced on). In ETA mode no
  CCF issue is listed; the status and the headline note say it.
- **Uncertainty.** The Monte Carlo run draws one value per group per trial for the
  members' shared uncertainty, so the members move together, and states that **β and
  α are not sampled**.
- **Report and Excel.** The DOCX report has a CCF section (always written when the
  file has groups): per group the name, model, β, source, members and status, the
  formulas with sources and pages, the assumptions, the engineer note, and `Not applied: <reason>. Results exclude this group.` for each group
  left out. The Excel
  Analysis sheet has the rows *CCF groups applied* and *CCF groups not applied*, and
  gate values are the MCUB or `n/a (CCF)`.

**Saving.** A file with groups is saved with `"fileFormatVersion": 2` and the groups
under `analysis.ccfGroups`; a file without groups is saved exactly as before. **Do
not save a file that has CCF groups with FTA Editor 1.8.x or with the desktop app:**
1.8.x drops the groups (it warns *reset to their defaults: ccfGroups*), and the
desktop app drops every analysis setting, groups included. A file saved by a newer
version opens with the warning *This file was saved by a newer FTA Editor; saving
may lose data*.

**Command line.** For a file with groups, `quantify`, `cutsets`, `importance` and
`mc` add a `ccf` block to `--json` and print one line per group not applied. In
fault-tree mode they exit with **1** when a group is not applied or the headline is
incomplete, so a batch run cannot miss it. In ETA mode `quantify` lists every group
as not applied (`CCF_ETA_MODE`) and exits 0, and the other three keep their ETA
refusal.

**Limits.** The model is for small probabilities and identical members. Members
that differ are not averaged; the group is not applied. A member below a PAND or
XOR gate is read as AND or OR in the cut sets. The value of a gate is the MCUB of
the cut sets kept under the document's own order, count and cutoff limits. See
[CCF.md](CCF.md#assumptions-and-limits).

#### Alpha-factor groups

The alpha-factor model is for a group of **2 to 4** identical members and covers
partial common-cause failures (some members fail together, the others do not).
Instead of one β you enter **α1 … αm**: α_k is the fraction of the failure events
of the group in which exactly k of the m members fail. They are numbers from 0 to
1 that should add up to 1, and you choose how the data behind them were tested
(**staggered** or **non-staggered**). The formulas with their sources and pages
are in [CCF.md](CCF.md#the-alpha-factor-model).

**Create an alpha group.**

1. Select 2 to 4 basic events and press **New group from selection**, as above.
2. In the editor set **Model** to **Alpha factor**. The β field is replaced by
   one field per member, **α1 (dimensionless, 0 to 1)**, **α2 …**, and a
   **Testing scheme** selector appears. The fields read the same texts as β
   (`0.05`, `5%`, a fraction); a value outside 0 to 1, or text, gives a message
   under the field and nothing is created. Below the fields a line shows the
   **Sum of α**.
3. Enter the α values from your data source.
4. Choose the **Testing scheme**: **Staggered testing** (the components behind the
   α values were tested one after another at different times) or **Non-staggered
   testing** (they were all tested at the same time). **There is no default**: the
   selector starts at *Choose a testing scheme*, and the editor does not choose
   for you. Choose the scheme that matches the source of your α values; the
   result differs between the two. The help line under the selector names the
   sources (NUREG/CR-5485 p. 40; NASA/SP-2011-3421 pp. 7-9, 7-14).
5. Press **Create group**.

A group created without a scheme is kept, and its status reads **Not applied:
testing scheme missing** (in the table, in the editor and in the Validation tab)
until you choose one; it is left out of every result until then.

**The sum.** If the α values add up to 1 within 0.000000001 the sum line only shows
it. If the sum is off by up to 0.001 the group stays applied, each α is divided by
the sum, the line says so and lists the values used, and the group shows the
**Warning** *α values add up to …; divided by the sum* with the original sum.
Published α sets are rounded, so this is common. If the sum is further than 0.001
from 1 the sum line turns red and the group is not applied (*Not applied: α
values add up to …, not 1*).

**Change an alpha group.** Edit the α fields and press **Save α values** (or press
Enter in a field): one request and one undo step for the whole list; leaving a
field only checks it. Choose another scheme from the selector: one undo step. Undo
and Redo bring the editor back to the earlier values.

**Members and α.** Adding or removing a member does **not** change the stored α
values. If the number of α values then differs from the number of members, the
status reads *Not applied: α values: 3, members: 2* (for example), the editor shows
one field per member with a hint, and you check the fields and press **Save α
values**. A group with fewer than 2 or more than 4 members shows that the
alpha-factor model needs 2 to 4 members and is not applied.

**Switch between the models.** Choosing the other model in the selector changes
only what the editor shows; nothing is stored until you commit the new model's
values (**Save α values** for alpha, the β field for beta). The change is one
undo step, and the values of the old model are removed from the group; Undo brings
them back.

**What you see elsewhere.**

- **Cut Sets and Importance** list one CCF event for each subset of two or more
  members, named `CCF: <group name> (<member names joined by " + ">)`, for example
  `CCF: Relief valves (V1 + V2)`: 1 event for 2 members, 4 for 3, 11 for 4.
  Clicking a row highlights exactly the members of that event.
- **Assumptions** (CCF groups tab) gets a seventh item with the alpha formulas
  while the document has an alpha group.
- The **report** shows the α values and the testing scheme of each group, and the
  command line's `--json` output carries them in its `ccf` block. With 3 or 4
  members an applied group gets a line under the note on overlapping CCF events
  in the report (see [CCF.md](CCF.md#overlapping-ccf-events)). A group without a
  scheme is listed as not applied and the command line exits with 1.
- **Monte Carlo** does not sample α (nor β).
- **Ids with `+` or `:`.** CCF event ids join group and member ids with `+` and `:`.
  If ids that contain these characters would give the same event id twice, the
  groups concerned are not applied (`CCF_BAD_PARAMETER`); rename those ids.

The Validation tab lists four more codes for alpha groups: `CCF_ALPHA_SIZE`,
`CCF_ALPHA_SUM` and `CCF_NO_TESTING` (errors: the group is not applied) and
`CCF_ALPHA_NORMALISED` (a warning); see [CCF.md](CCF.md#alpha-lint-codes).

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
| `--json` / `--csv` | all | Machine-readable output instead of a text table (mutually exclusive). With several files, `--json` gives a list. `--json` is strict JSON: a value that is not a finite number (a NaN probability in the file, say) is written as `null`. `--csv` is the raw data for scripts: text is written exactly as it is, not guarded for spreadsheets, so a name such as `=HYPERLINK(…)` stays a formula if you open the file in Excel. |
| `--out PATH` | all | Write to PATH instead of stdout. With several files, give a directory; each file then gets `<stem>.<command>.<ext>`. A path that exists as a directory or ends in `/` or `\` is a directory. `report` defaults to `<stem>_report.docx` beside the input; for `report`, any `--out` that does not end in `.docx` is a directory. An output that would overwrite an input file, or that two inputs would both write, is a usage error (exit 2), and nothing is written. An output that cannot be written fails that file (exit 1). |
| `--sig-figs N` | all | Significant figures in text tables, 1–6, default 3. JSON and CSV carry full precision. |
| `--mission-time H` | all | Override the document's mission time, in hours. |
| `--max-order N`, `--max-count N`, `--cutoff P` | cutsets, importance, report | Override the cut-set limits. |
| `--top N` | cutsets, importance | Show only the first N rows (N ≥ 1). With `--json` the list is cut to N too; the totals, MCUB and truncation flags still cover every cut set. |
| `--n N`, `--seed S` | mc, report | Monte Carlo samples and seed. |
| `--time-limit SEC` | mc, report | Monte Carlo time cap in seconds, > 0, default 30. For `report` it is capped at 60. |
| `--strict` | validate | Warnings also fail (exit 1). |
| `--sections LIST`, `--lang en\|ja`, `--uncertainty` | report | Comma-separated sections, the report language, and whether to run Monte Carlo (n ≤ 5,000) and include it (also when `--sections` leaves it out). |

Wildcards are expanded by the tool itself, so `*.json` works in `cmd.exe` too.

**CCF groups.** For a file with CCF groups, `quantify`, `cutsets`, `importance` and
`mc` add a `ccf` block (`applied`, `notApplied` with `id`, `name`, `code`, `reason`,
and `note`) to `--json`, print one line `CCF group not applied: <name> (<id>): <reason>` per group
not applied, and print the engineer note. They exit with **1**
when the document is in fault-tree mode and a group is not applied or the headline
is `incomplete`. In ETA mode, `quantify` lists every group in `notApplied` with the
code `CCF_ETA_MODE` and exits 0; `cutsets`, `importance` and `mc` keep their ETA
refusal. A file without groups gets no `ccf` block and the output of 1.8.1. See
[CCF groups](#ccf-groups-beta-factor-and-alpha-factor).

Text tables show control characters from the input files (in names, titles
and messages) as `\xNN`, so a crafted file cannot send escape sequences to
the terminal; `--json` and `--csv` keep the text exactly. A character the
console's encoding cannot show is written as a backslash escape instead of
stopping the run (`--json` then escapes every non-ASCII character).

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | OK |
| 1 | Validation errors (or warnings with `--strict`), an analysis failed (for example an ETA file given to `cutsets`, or a voting gate that is too large), or an output file could not be written |
| 2 | Usage error (bad option or value, or `--out` would overwrite an input file or one output twice) |
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
- **CCF groups are lost** with the rest of the `analysis` block (they are stored
  in `analysis.ccfGroups`), and the desktop app does not apply them. Do not save a
  file with CCF groups there; FTA Editor 1.8.x also drops them. See
  [CCF groups](#ccf-groups-beta-factor-and-alpha-factor).
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

**Save** / **Save As** in the action bar (desktop app: **(S)ave JSON As**).

The buttons after **Export:** (**JSON**, **XML**, **Excel**, **Render**) are
downloads. Each hands a copy to the browser, which puts it in its own
download folder; the editor is not told where. The open file is not changed
and the analysis does not count as saved. Use **Save** for that.

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

**Excel** in the action bar (desktop app: **Export Excel**)

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
- Text stays text: in the web app's export a name that starts with `=`
  is never turned into a formula

From 1.7 the web app's workbook also has a flat **Events** sheet (one row per
node, numbers as real numbers) and an **Analysis** sheet (settings and
headline figures). See [Report (DOCX) and Excel sheets](#report-docx-and-excel-sheets).

### DOCX Report (web app, 1.7)

**Report tab → Generate report**. See
[Report (DOCX) and Excel sheets](#report-docx-and-excel-sheets).

### XML Export

**XML** in the action bar (desktop app: **Export XML**)

A `<FaultTree>` of nested `<Node>` elements carrying the name, type, base and
calculated probability, logic gate, notes and links. It is the editor's own
layout, not a standard exchange format, and it does not carry the 1.7 keys.

In the web app, the Excel, XML and DOCX exports leave out the characters XML
cannot hold, such as control characters pasted from PowerPoint or Word; the
whitespace-like ones (PowerPoint's soft line break) become a space. The
analysis itself is not changed.

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
| `Ctrl+Z` / `Ctrl+Y` (`Ctrl+Shift+Z`) | Undo / Redo. A message names the step (*Undid: deleting "Seal leak"*), and the node concerned is selected, or its former parent when it is gone. |
| `Ctrl+F` | Search the tree |
| `Escape` | Discard what was typed in a field; close a dialog or the Diagram settings popover; dismiss a toast |

Inside a text field `Ctrl+A` and `Ctrl+Z` keep their usual meaning (select
all, undo typing). With the focus on a dropdown, such as **Logic Gate**
after a change, `Ctrl+Z` and `Ctrl+Y` undo and redo in the document. In the
Add dialog `Ctrl+Enter` is **OK and add another**. In the tree: arrows move,
`Enter` / `Space` select, `F2` or a double-click on the name renames,
`Ctrl+Shift+arrows` move the focused node. In the search box: `Enter` and
`Shift+Enter` step through the matches. In the bottom tab strip:
`Left` / `Right` / `Home` / `End`. In the diagram: the mouse wheel or
`Ctrl+=` / `Ctrl+-` zoom, `Ctrl+0` fits (never above 100%).

### Desktop app

- `Ctrl+N` - New Analysis
- `Ctrl+A` - Add Node
- `Ctrl+E` - Edit Node
- `Ctrl+D` - Delete Node
- `Ctrl+S` - Save (overwrite)
- `Ctrl+Shift+S` - Save As
- `Ctrl+R` - Render Diagram

## Examples

### Example files

The editor ships with worked examples of two well-documented accidents, each
in English (`_en`) and in Japanese (`_ja`). The two languages are one
analysis: only the names, the notes and the title differ.

| File | Mode | Subject |
|---|---|---|
| `challenger_fta_en.json`, `challenger_fta_ja.json` | FTA | Loss of the Space Shuttle Challenger, STS 51-L, 28 January 1986 |
| `tmi2_eta_en.json`, `tmi2_eta_ja.json` | ETA | Accident at Three Mile Island Unit 2, 28 March 1979 |
| `sampleFTA.json` | FTA | The small AND/OR tree of the 1.x releases |

To open one in the web app, click **Open an example** in the hint of a new
analysis, or **Load** and then **Open an example…**, and pick it from the
list. It opens as an untitled copy: **Save** asks where to put your version,
and the example itself is never changed.

The files are in `fta_web/examples/` in a source checkout and in
`fta_editor\_internal\examples\` in the standalone build. The Load dialog's
file list can open them from there too, when that folder is inside the
editor's root folder (your home folder unless you started the editor with
`--root`). An example opened that way keeps its path, so **Save** writes back
to the file that came with the editor: use **Save As**, or open it from the
list instead.

Each node's notes (the **Details** tab) say what happened and cite the
accident report with the finding or page: the *Report of the Presidential
Commission on the Space Shuttle Challenger Accident* (the Rogers Commission,
1986) and the *Report of the President's Commission on the Accident at Three
Mile Island* (the Kemeny Commission, 1979). Quotations are word for word in
the English files; the Japanese files paraphrase them. **The probabilities are
illustrative values for learning the tool.** They are not from the reports,
and the files are not risk estimates.

**Challenger (fault tree).** The top gate is an AND of the two causes the
Commission reports: the joint that did not seal, and the launch that was not
stopped. The joint has two O-rings, a primary and a secondary, so "does not
seal" is an AND as well. Two events, the cold and the tight squeeze of the
O-rings, act on both rings: the secondary O-ring has a link to the node that
combines them. Things to look at, with **Advanced** on:

- The headline reads **0.0684** with the **MCUB** badge, and the diagram's
  top box reads `P_calc:0.0684 (MCUB) | tree walk 0.0349`. The second number
  is the root node's own calculated probability, the plain tree walk, which
  counts the cold and the squeeze once for each O-ring, as if each ring had
  its own. The first comes from the minimal cut sets and counts them once; it
  is an upper bound, and the exact value for these numbers is 0.0670.
  See [Top-event value](#top-event-value-tree-walk-mcub-and-rare-event).
- **Cut Sets** lists three sets. The first, the cold and the squeeze with the
  two decision events, is 0.0625, about 91 % of the total: two O-rings are no
  protection against a cause they share.
- **Importance**: the two decision events have a Fussell-Vesely of 1.00. They
  are in every cut set, because the top gate is an AND.
- Try it: set the probability of "Cold O-rings slow to recover" to 0.05, a
  warm day. The top event falls to about a fifth.

**Three Mile Island Unit 2 (event tree).** The root is the initiating event,
the loss of feedwater, with probability 1. Each level asks one question: does
the relief valve close again, do the operators close the block valve, is high
pressure injection left running, does the containment hold. The two answers
are branches whose probabilities add up to 1. Things to look at:

- A node's calculated probability is the product of the probabilities on the
  way down to it, so the five end states add up to 1: 0.98, 0.01, 0.005,
  0.00495 and 0.00005.
- The branches marked "(actual)" are the path the accident took.
- Try it: change one branch and not its sibling. The **Validation** tab then
  says that the branch probabilities under their parent no longer add up
  to 1.

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
A: The web app needs no Graphviz: the diagram is drawn in the browser, so check
the browser console (`/static/vendor/viz-js/viz.js` must load). The desktop app
needs Graphviz installed and in your PATH.

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
name (an NTFS alternate data stream) is refused. To open one file from
outside the root folder, use **Load** and then **A file on this computer…**:
it opens as an untitled copy. To work in another folder, press **Change
folder…** in the file dialog and pick it (see
[Keeping your work](#keeping-your-work-after-180)). Where that button cannot
open a folder chooser, close the editor and start it with `--root`; the
message gives the command for your installation
(`fta_editor.exe --root "<folder>"`, or
`uv run python fta_web/run.py --root "<folder>"` from source).

**Q: My settings (Advanced, language, theme) are gone after a restart**
A: The browser keeps them per address. The editor uses `127.0.0.1:8765`
unless that port is taken or you start it with `--port`. If its terminal
window shows a line beginning with `Note`, another program (often a second
copy of the editor) was using the port; close it and start the editor again.

**Q: The editor closed and I had not saved**
A: Start it again. If it had ended without a clean stop, **Unsaved work
found** appears above the tree. See
[Keeping your work](#keeping-your-work-after-180).

**Q: The page says "The editor is not answering"**
A: The editor (the program the page talks to) has been closed or has
stopped. Press **Download a rescue copy (JSON)** to keep the analysis in the
tab, then start the editor again and open that file with **Load**. See
[Top Bar](#top-bar), *If the editor stops*.

**Q: The page says "This tab is not connected to the editor"**
A: The editor only works in the tab it opens itself. A tab opened from a
bookmark or the history, or left over from an earlier run, cannot reach it.
Close the tab and use the one the editor opened, or start the editor again
with the command the screen shows.

**Q: The tree changed by itself and a message says "changed in another tab"**
A: The same editor is open in two tabs or windows, and the other one edited
the analysis. Both tabs show the same analysis; work in one of them.

**Q: Legacy JSON files don't load properly**
A: Old format is supported, but defaults to FTA mode. Set mode manually after loading.

**Q: AI Assistant shows "not configured"**
A: Click the ⚙ button in the AI panel to enter your API credentials.

**Q: AI connection test fails**
A: Verify your API key is valid and has available credits. Check internet connection.

**Q: AI responses are slow**
A: Consider using a faster model like `gpt-4o-mini`. Check your API rate limits.

**Q: AI suggestions don't apply correctly**
A: Ensure you've reviewed and ticked the changes in the *Suggested changes*
list before **Apply selected** (the desktop app: the confirmation dialog).
A suggestion the chat reports as *Suggestion rejected* was not applied at all; the
reason is beside it (see [Applying Changes](#applying-changes)).

**Q: The AI says my tree double-counts a shared event**
A: Until 1.7.3 the AI was shown only the tree-walk values, so for a tree with
repeated events it reported the double counting that the headline (MCUB)
already corrects. It is now given the headline and its method. Check the top
bar: with the **MCUB** badge, shared events are counted once.

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
- [API Reference](API_REFERENCE.md)
