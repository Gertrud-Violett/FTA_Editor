# FTA/ETA Editor - User Guide

**Version**: 1.5.1 | **Updated**: December 16, 2025

Complete guide for using the Fault Tree Analysis and Event Tree Analysis Editor with AI Assistant.

## Table of Contents

- [Getting Started](#getting-started)
- [Understanding FTA vs ETA](#understanding-fta-vs-eta)
- [User Interface](#user-interface)
- [AI Assistant](#ai-assistant)
- [Working with Nodes](#working-with-nodes)
- [Probability Calculations](#probability-calculations)
- [Export Options](#export-options)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)

## Getting Started

### Installation

```bash
# Install dependencies -- uv (recommended) or plain pip
uv sync --extra desktop --extra excel --extra ai
# pip install -r requirements.txt

# Run the application
uv run python src/FTA_Editor_UI.py
# python src/FTA_Editor_UI.py
```

See the root [README](../README.md#quick-start) for the web app, which is the
recommended way to run the editor as of v1.6.

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

Shows selected node information:
- Name
- Type (Root, Event, Gate, etc.)
- Base Probability
- Calculated Probability
- Logic Gate (AND/OR)
- Notes
- Links to other nodes

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
Calculated = Base × Product(Child1, Child2, ...)
```

OR Gate:
```
Calculated = 1 - Product((1-Child1), (1-Child2), ...)
```

**With Links**:
1. Calculate from children (if any)
2. Apply AND links: multiply
3. Apply OR links: union formula

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

### XML Export

**File → Export XML**

Standard fault tree XML format, compatible with other FTA tools.

## Keyboard Shortcuts

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

The calculator detects circular references and uses base probability to break the cycle.

---

For more details, see:
- [ETA Mode Documentation](ETA_MODE.md)
- [Probability Validation](PROBABILITY_VALIDATION.md)
- [API Reference](API_REFERENCE.md)
