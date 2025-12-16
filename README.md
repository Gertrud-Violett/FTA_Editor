# FTA/ETA Editor

A comprehensive Fault Tree Analysis (FTA) and Event Tree Analysis (ETA) editor with advanced probability calculations, visual tree editing, AI-powered analysis assistant, and export capabilities.

[![License: MIT](https://img.shields.io/badge/License-BSD2-yellow.svg)](https://opensource.org/license/bsd-2-clause)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-1.5.0-green.svg)](CHANGELOG.md)

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

The FTA Editor includes an integrated AI assistant that can analyze your fault trees, suggest improvements, and help identify missing root causes. The AI uses OpenAI-compatible APIs (OpenAI, Azure OpenAI, GitHub Copilot, or other compatible endpoints).

### Step 1: Obtain an API Key

Choose one of the following options:

#### Option A: GitHub Copilot / GitHub Models (Recommended)

If you have a **GitHub Copilot subscription**, you can use GitHub Models API at no extra cost!

**Requirements**:
- Active GitHub Copilot subscription ($10-19/month)
- GitHub Personal Access Token

**Quick Setup**:
1. Go to [github.com/settings/tokens](https://github.com/settings/tokens)
2. Click **"Generate new token (classic)"**
3. Set scopes: ✅ `read:user`
4. Copy the token (starts with `ghp_...`)
5. Use in FTA Editor:
   - **API Endpoint**: `https://models.github.ai`
   - **API Key**: Your Personal Access Token
   - **Model**: `gpt-4o` or `gpt-4o-mini`

📖 **Detailed guide**: [GitHub Copilot Setup](docs/GITHUB_COPILOT_SETUP.md)

---

#### Option B: OpenAI API (Pay-as-you-go)
1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Sign up or log in to your account
3. Navigate to **API Keys** in your account settings
4. Click **Create new secret key**
5. Copy and save the key securely (it won't be shown again)
6. **Add credits or enable billing** to use the API:
   - Go to **Settings** → **Billing** → **Add payment method**
   - Add at least $5-10 in credits to get started
   - GPT-4o costs: ~$0.005 per 1K tokens (very affordable for FTA analysis)

**Cost Estimation for FTA Editor**:
- Quick FTA analysis: ~1,000-2,000 tokens ≈ $0.01-0.02
- Root cause suggestions: ~800-1,500 tokens ≈ $0.005-0.015
- Monthly usage (heavy): ~$2-5
- Pay-as-you-go, no subscription required

---

#### Option C: Azure OpenAI
1. Create an Azure OpenAI resource in [Azure Portal](https://portal.azure.com/)
2. Deploy a model (e.g., gpt-4o, gpt-4-turbo)
3. Get your endpoint URL and API key from the resource
4. For enterprises already using Azure

---

#### Option D: Other OpenAI-Compatible APIs
Any API that follows the OpenAI API format can be used:
- Local LLM servers (Ollama, LLaMA.cpp, etc.)
- Other cloud providers
- Custom/private AI servers

### Step 2: Configure in FTA Editor

1. Launch the FTA Editor: `python src/FTA_Editor_UI.py`
2. Look for the **AI Assistant** panel on the right side
3. Click the **⚙ (Settings)** button
4. Enter your credentials:
   - **API Key**: Your API key/token from Step 1
   - **API Endpoint**: 
     - **GitHub Models**: `https://models.github.ai`
     - **OpenAI**: `https://api.openai.com/v1` (default)
     - **Azure**: `https://your-resource.openai.azure.com/openai/deployments/your-deployment`
     - **Other**: Your provider's endpoint URL
   - **Model**: Select from dropdown or enter custom model name
     - `gpt-4o` (recommended, fastest)
     - `gpt-4o-mini` (faster, lower cost)
     - `gpt-4-turbo`
     - `gpt-3.5-turbo`
5. Click **Test & Save** to verify the connection

### Step 3: Credential Storage

Your API credentials are stored **locally on your computer** at:

| Operating System | Location |
|-----------------|----------|
| Windows | `C:\Users\<username>\.fta_editor\ai_credentials.json` |
| macOS | `/Users/<username>/.fta_editor/ai_credentials.json` |
| Linux | `/home/<username>/.fta_editor/ai_credentials.json` |

**Security Notes:**
- Credentials are **never** stored in the repository
- Credentials are **never** uploaded or transmitted except to the configured API endpoint
- You can delete credentials anytime via the Settings dialog or by deleting the file
- The `.fta_editor` folder is in your home directory, outside any git repository

### Using the AI Assistant

Once configured, you can:

1. **Quick Analysis**: Click "Analyze FTA" to get an overview and suggestions
2. **Root Cause Suggestions**: Select a node and click "Suggest Root Causes"
3. **Free Chat**: Type any question in the input box and press Enter
4. **Apply Suggestions**: When AI proposes changes, a confirmation dialog appears where you can review and selectively apply them

**Example prompts:**
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
