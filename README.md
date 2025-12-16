# FTA/ETA Editor

A comprehensive Fault Tree Analysis (FTA) and Event Tree Analysis (ETA) editor with advanced probability calculations, visual tree editing, AI-powered analysis assistant, and export capabilities.

[![License: MIT](https://img.shields.io/badge/License-BSD2-yellow.svg)](https://opensource.org/license/bsd-2-clause)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-1.5.1-green.svg)](CHANGELOG.md)

## Features

- **Interactive Tree Editor** with live diagram preview
- **Dual Analysis Modes**: FTA (bottom-up) and ETA (top-down)  
- **AI-Powered Assistant**: Integrated chat interface for FTA analysis and suggestions
- **Accurate Probability Calculations** with AND/OR logic gates
- **International Support**: Japanese/Chinese/Korean fonts (Noto Sans CJK)
- **Visual Diagram Generation** with Graphviz - logic gates displayed in nodes
- **Multiple Export Formats** (JSON, XML, Excel with hierarchical structure)
- **Zero-Probability Node Highlighting** for quick issue identification
- **Secure Credential Storage**: API keys stored locally, never in repository

## Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/Gertrud-Violett/FTA_Editor.git
cd FTA_Editor

# Install dependencies
pip install -r requirements.txt

# Run the application
python src/FTA_Editor_UI.py
```

### Requirements

- Python 3.10+
- Graphviz (install from [graphviz.org](https://graphviz.org/download/))
- See `requirements.txt` for Python packages

## AI Assistant Setup

The FTA Editor includes an integrated AI assistant supporting OpenAI, Anthropic Claude, and Google Gemini.

**Quick Setup:**
1. Get API key from your provider:
   - Google Gemini: https://aistudio.google.com/apikey (free tier available)
   - OpenAI: https://platform.openai.com/api-keys
   - Anthropic Claude: https://console.anthropic.com/api-keys

2. Open FTA Editor → Click AI Settings (⚙)

3. Select provider, paste API key, click "Test & Save"

Your credentials are stored locally at `~/.fta_editor/ai_credentials.json` (never in repository or cloud).

For detailed setup instructions, see [docs/QUICK_AI_SETUP.md](docs/QUICK_AI_SETUP.md) and [docs/MULTI_PROVIDER_SETUP.md](docs/MULTI_PROVIDER_SETUP.md).

### Quick Actions
- **Analyze FTA**: Posts an assessment and suggestions to chat; does not modify your tree.
- **Update FTA**: AI generates a complete JSON update, verified for structure and safety, then replaces the current FTA. Existing nodes are preserved; only additions are applied. Detailed error logs are shown if the AI output is invalid.
- "What root causes might be missing from this failure mode?"
- "Can you review the probabilities in this tree?"
- "Suggest additional failure modes for the selected node"
- "What are common causes of pump failures I should consider?"

## Usage

### GUI Application

```bash
python src/FTA_Editor_UI.py
```

**Keyboard Shortcuts:**
- `Ctrl+N`: New analysis
- `Ctrl+A`: Add node
- `Ctrl+E`: Edit node
- `Ctrl+D`: Delete node
- `Ctrl+S`: Save
- `Ctrl+R`: Render diagram

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
│   ├── FTA_Editor_UI.py         # GUI application with AI chat
│   ├── FTA_Editor_core.py       # Core business logic
│   ├── AI_agent_handler.py      # AI agent and API handling
│   └── json_viewer.py           # Diagram renderer
├── tests/                        # Test suite
├── data/examples/               # Sample data
├── docs/                        # Documentation
└── requirements.txt             # Python dependencies
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

- [Quick Start Guide](QUICKSTART.md) - Get running in 3 steps
- [User Guide](docs/USER_GUIDE.md) - Complete manual
- [GitHub Copilot Setup](docs/GITHUB_COPILOT_SETUP.md) - Detailed Copilot configuration
- [ETA Mode](docs/ETA_MODE.md) - Event Tree Analysis
- [API Reference](docs/API_REFERENCE.md) - Programming interface

## Troubleshooting

### AI Assistant Issues

**"AI not configured" error:**
- Click the ⚙ button and enter your API credentials

**"Connection failed" during test:**
- Verify your API key is correct and active
- Check your internet connection
- Ensure the API endpoint URL is correct
- For Azure, verify your deployment name is correct

**Slow responses:**
- Consider using `gpt-4o-mini` for faster responses
- Check your API rate limits

### General Issues

**Graphviz not found:**
- Install Graphviz from [graphviz.org](https://graphviz.org/download/)
- Add Graphviz to your system PATH
- Restart the application

**Diagram not displaying:**
- Ensure Pillow is installed: `pip install Pillow`
- Verify Graphviz installation

## License

BSD-2 License - Copyright (c) makkiblog.com

## Support

- Issues: [GitHub Issues](https://github.com/Gertrud-Violett/FTA_editor/issues)
- Examples: [data/examples/](data/examples/)
