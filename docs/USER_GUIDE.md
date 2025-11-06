# FTA/ETA Editor - User Guide

Complete guide for using the Fault Tree Analysis and Event Tree Analysis Editor.

## Table of Contents

- [Getting Started](#getting-started)
- [Understanding FTA vs ETA](#understanding-fta-vs-eta)
- [User Interface](#user-interface)
- [Working with Nodes](#working-with-nodes)
- [Probability Calculations](#probability-calculations)
- [Export Options](#export-options)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)

## Getting Started

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python src/FTA_Editor_UI.py
```

### First Launch

When you first launch the application, you'll see:
1. **Top Bar** - Mode selector, Title, and Date fields
2. **Tree View** - Left panel showing your analysis tree
3. **Diagram Preview** - Right panel with live visualization
4. **Node Details** - Bottom panel showing selected node information
5. **Action Buttons** - Bottom toolbar for all operations

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
- Zoom: Ctrl + Mouse Wheel
- Updates automatically when tree changes

### Node Details Panel

Shows selected node information:
- Name
- Type (Root, Event, Gate, etc.)
- Base Probability
- Calculated Probability
- Logic Gate (AND/OR)
- Notes
- Links to other nodes

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
