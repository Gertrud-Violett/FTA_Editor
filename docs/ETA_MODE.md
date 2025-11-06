# ETA (Event Tree Analysis) Mode Documentation

## Overview

The FTA Editor now supports both **FTA (Fault Tree Analysis)** and **ETA (Event Tree Analysis)** modes.

## Mode Differences

### FTA (Fault Tree Analysis) - Bottom-Up
- **Direction:** Children → Parent
- **Purpose:** Analyze how component failures lead to system failure
- **Calculation:** Parent probability is calculated from children probabilities
- **Use case:** Reliability analysis, failure mode analysis

**Example:**
```
System Failure (calculated from children)
  ├─ Component A Fails (0.1)
  ├─ Component B Fails (0.2)
  └─ Component C Fails (0.15)
```

### ETA (Event Tree Analysis) - Top-Down
- **Direction:** Parent → Children
- **Purpose:** Analyze possible outcomes following an initiating event
- **Calculation:** Children probabilities are cumulative product from root down
- **Use case:** Accident sequence analysis, consequence modeling

**Example:**
```
Initiating Event (0.5)
  ├─ Branch 1 Success (0.8) → Calc: 0.5 × 0.8 = 0.4
  │   ├─ Outcome A (0.9) → Calc: 0.4 × 0.9 = 0.36
  │   └─ Outcome B (0.7) → Calc: 0.4 × 0.7 = 0.28
  └─ Branch 2 Failure (0.6) → Calc: 0.5 × 0.6 = 0.3
```

## UI Features

### Top Bar Controls

The application now includes a top bar with three fields:

1. **Mode Selector** - Switch between FTA and ETA modes
2. **Title Field** - Name your analysis
3. **Date Field** - Document when the analysis was performed

### Mode Selector
- Dropdown menu with options: FTA, ETA
- Changing mode immediately recalculates all probabilities
- Tree label updates to reflect current mode ("Fault Tree" or "Event Tree")

### Title and Date Fields
- Free-text entry fields
- Automatically saved with the JSON file
- Retained when loading files

## JSON File Format

### New Format (with Metadata)
```json
{
  "title": "Nuclear Plant Safety Analysis",
  "date": "2025-10-31",
  "mode": "ETA",
  "tree": {
    "id": "root",
    "name": "Initiating Event",
    "type": "Root",
    "probability": 0.5,
    "logicGate": "OR",
    "children": [...]
  }
}
```

### Legacy Format Support
The application still supports loading old-format JSON files (without metadata):
```json
{
  "id": "root",
  "name": "RootEvent",
  ...
}
```

When loading legacy files:
- Title defaults to "Untitled Analysis"
- Date defaults to empty string
- Mode defaults to "FTA"

## ETA Calculation Algorithm

In ETA mode, calculated probabilities flow top-down:

```python
def calculate_eta(node, parent_calc_prob=1.0):
    # Child's calculated probability = parent's calc prob × child's base prob
    child.calculatedProbability = parent_calc_prob × child.probability
    
    # Recursively apply to all children
    for each child:
        calculate_eta(child, child.calculatedProbability)
```

### Example Calculation

```
Initiating Event (base: 0.5)
  calc = 0.5

  ├─ Success Branch (base: 0.8)
  │   calc = 0.5 × 0.8 = 0.4
  │
  │   ├─ Good Outcome (base: 0.9)
  │   │   calc = 0.4 × 0.9 = 0.36
  │   │
  │   └─ Degraded Outcome (base: 0.7)
  │       calc = 0.4 × 0.7 = 0.28
  │
  └─ Failure Branch (base: 0.6)
      calc = 0.5 × 0.6 = 0.3
```

## Usage Examples

### Creating an ETA Analysis

1. Open FTA Editor UI: `python FTA_Editor_UI.py`
2. Set Mode to "ETA" in the top bar
3. Enter Title: "Reactor Scram Analysis"
4. Enter Date: "2025-10-31"
5. Build your event tree:
   - Root = Initiating event (e.g., "Loss of Coolant")
   - Children = Possible branches (e.g., "ECCS Success", "ECCS Failure")
   - Grand-children = Final outcomes

### Converting FTA to ETA

1. Load an existing FTA file
2. Change Mode from "FTA" to "ETA"
3. Probabilities recalculate automatically in ETA mode
4. Save as new file to preserve original

## Programmatic Usage

```python
from FTA_Editor_core import FTACore

# Create ETA analysis
core = FTACore()
core.set_metadata(
    title="Safety Analysis",
    date="2025-10-31",
    mode="ETA"
)

# Build tree structure
core.set_data({
    "id": "root",
    "name": "Initiating Event",
    "probability": 0.5,
    "children": [...]
})

# Calculate probabilities in ETA mode
core.recalculate_probabilities()

# Save with metadata
core.save_to_json("safety_analysis.json")
```

## Comparison Table

| Feature | FTA Mode | ETA Mode |
|---------|----------|----------|
| Direction | Bottom-Up | Top-Down |
| Parent Calc | From children | From base prob |
| Child Calc | From base prob | From parent calc |
| Logic Gates | AND, OR gates apply | Cumulative only |
| Use Case | System reliability | Accident sequences |
| Root Meaning | System failure | Initiating event |
| Leaf Meaning | Component failure | Final outcome |

## Testing

Run the ETA test suite:
```bash
python test_eta_mode.py
```

Expected output:
```
✅ All ETA calculations correct!
✅ All tests passed!
```

## Notes

- Mode can be switched at any time
- Switching modes recalculates all probabilities
- Both modes save/load properly with metadata
- Legacy files default to FTA mode
- Excel export works in both modes
- Zero-probability marking works in both modes

## Future Enhancements

Potential improvements for ETA mode:
- Success/Failure branch labeling
- Conditional probability support
- Automatic outcome categorization
- ETA-specific visualization
