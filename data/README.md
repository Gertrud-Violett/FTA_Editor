# Data Directory

This directory contains sample data and examples for FTA/ETA Editor.

## Structure

```
data/
├── examples/          # Example analysis files
│   └── sampleFTA.json # Sample fault tree
└── README.md          # This file
```

## Example Files

### sampleFTA.json

A complete example fault tree analysis with:
- Multiple levels of hierarchy
- AND/OR logic gates
- Node links
- Probability calculations

**Usage**:
```bash
python src/FTA_Editor_UI.py
# Click "Load JSON" → Select data/examples/sampleFTA.json
```

## Creating Your Own Data

### JSON Format

```json
{
  "title": "My Analysis",
  "date": "2025-10-31",
  "mode": "FTA",
  "tree": {
    "id": "root",
    "name": "Root Event",
    "type": "Root",
    "probability": 0.5,
    "logicGate": "OR",
    "notes": "Description here",
    "children": [
      {
        "id": "child1",
        "name": "Child Event",
        "type": "Event",
        "probability": 0.3,
        "logicGate": "OR",
        "children": [],
        "links": []
      }
    ],
    "links": []
  }
}
```

### Legacy Format (also supported)

```json
{
  "id": "root",
  "name": "Root Event",
  "type": "Root",
  "probability": 0.5,
  "children": [...]
}
```

## Adding Examples

To add your own example:

1. Create analysis in the application
2. Save as JSON
3. Copy to `data/examples/`
4. Add description here

## Sample Analyses

### Reliability Analysis (FTA)

Use FTA mode for:
- System reliability
- Component failure analysis
- Quality control
- Risk assessment

### Safety Analysis (ETA)

Use ETA mode for:
- Accident sequences
- Consequence modeling
- Safety system analysis
- Event progression

## Data Privacy

- Do not commit sensitive data
- Use sample/anonymized data for examples
- Add `.gitignore` entries for private files

## Need Help?

See [User Guide](../docs/USER_GUIDE.md) for more information on creating analyses.
