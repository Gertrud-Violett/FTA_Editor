# FTA/ETA Editor

A comprehensive Fault Tree Analysis (FTA) and Event Tree Analysis (ETA) editor with advanced probability calculations, visual tree editing, and export capabilities.

[![License: MIT](https://img.shields.io/badge/License-BSD2-yellow.svg)](https://opensource.org/license/bsd-2-clause)
[![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-1.4.2-green.svg)](CHANGELOG.md)

## Features

- **Interactive Tree Editor** with live diagram preview
- **Dual Analysis Modes**: FTA (bottom-up) and ETA (top-down)  
- **Accurate Probability Calculations** with AND/OR logic gates
- **Web Application**: Browser-based interface with zoom/pan and resizable panels
- **Session Persistence**: Reliable state management for multi-user environments
- **International Support**: Japanese/Chinese/Korean fonts (Noto Sans CJK)
- **Visual Diagram Generation** with Graphviz - logic gates displayed in nodes
- **Multiple Export Formats** (JSON, XML, Excel with hierarchical structure)
- **Zero-Probability Node Highlighting** for quick issue identification
- **Docker Support** for easy deployment and cross-platform compatibility

## Quick Start

### Web Application (Online)

**Try it live**: [https://fta-editor.onrender.com](https://fta-editor.onrender.com)

*Note: First load may take 30-60 seconds as the server wakes up from sleep mode.*

### Local Installation

**Option 1: Direct Python**
```bash
pip install -r requirements.txt
python src/FTA_Editor_UI.py
```

**Option 2: Web Application (Local)**
```bash
pip install -r requirements.txt
python web_app/app.py
# Open browser to http://localhost:5000
```

**Option 3: Docker**
```bash
docker-compose up
```

### Requirements

- Python 3.14+
- Graphviz (install from [graphviz.org](https://graphviz.org/download/))
- See `requirements.txt` for Python packages

## Usage

### Web Application
Access the web interface at http://localhost:5000 (when running locally) or the deployed URL.

Features:
- Interactive tree editing
- Live diagram preview with zoom/pan
- Resizable panels
- Export to JSON, XML, Excel
- Import existing analyses

### GUI Application

```bash
python src/FTA_Editor_UI.py
```

### Programmatic API
```python
from src.FTA_Editor_core import FTACore

core = FTACore()
core.set_metadata(title="Analysis", mode="FTA")
core.load_from_json("data/examples/sampleFTA.json")
core.recalculate_probabilities()
core.export_to_excel("output.xlsx")
```

## Project Structure

```
FTA_Editor/
├── src/                          # Source code
│   ├── FTA_Editor_UI.py         # GUI application
│   ├── FTA_Editor_core.py       # Core business logic
│   └── json_viewer.py           # Diagram renderer
├── tests/                        # Test suite
├── data/examples/               # Sample data
├── docs/                        # Documentation
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Container image
└── docker-compose.yml          # Container orchestration
```

## Testing
```bash
python -m pytest tests/
```

## Analysis Modes

**FTA (Fault Tree Analysis)**: Bottom-up reliability analysis
- Root = System failure event
- Leaves = Component failure causes
- Calculates failure probability from component failures

**ETA (Event Tree Analysis)**: Top-down consequence analysis  
- Root = Initiating event
- Leaves = Final outcomes
- Calculates outcome probabilities from event sequences

## Export Formats

- **JSON**: Complete tree data with metadata
- **XML**: Standard fault tree format
- **Excel**: Hierarchical spreadsheet with color coding

## Documentation

- [Render.com Deployment](RENDER_DEPLOYMENT.md) - Free online hosting
- [User Guide](docs/USER_GUIDE.md) - Complete manual
- [ETA Mode](docs/ETA_MODE.md) - Event Tree Analysis
- [API Reference](docs/API_REFERENCE.md) - Programming interface
- [Docker Guide](docs/DOCKER.md) - Container deployment
- [Full Deployment Guide](DEPLOYMENT.md) - All deployment options

## License

MIT License - Copyright (c) makkiblog.com

## Support

- Issues: [GitHub Issues](https://github.com/Gertrud-Violett/FTA_editor/issues)
- Examples: [data/examples/](data/examples/)
