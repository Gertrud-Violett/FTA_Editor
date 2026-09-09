# FTA/ETA Editor

A comprehensive Fault Tree Analysis (FTA) and Event Tree Analysis (ETA) editor with advanced probability calculations, visual tree editing, AI-powered analysis assistant, and export capabilities.

[![License: MIT](https://img.shields.io/badge/License-BSD2-yellow.svg)](https://opensource.org/license/bsd-2-clause)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-1.6.0-green.svg)](CHANGELOG.md)

There are two ways to run it, and both are supported:

| | Runs in | Needs | Use it when |
|---|---|---|---|
| **Web app** (recommended, new in 1.6) | your browser, served from `127.0.0.1` | Python 3.10+ and Flask — **no Graphviz** | almost always |
| **Desktop app** (1.5.1, unchanged) | a Tkinter window | Python 3.10+, Tk, **Graphviz**, Pillow | you want the original GUI, or a scripted Tk workflow |

Both edit the same files, keep AI credentials in the same place, and produce the
same diagrams. The web app is the one under active development; the desktop app
is unchanged in this release and remains supported.

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

```bash
# Clone repository
git clone https://github.com/Gertrud-Violett/FTA_Editor.git
cd FTA_Editor
```

### Web app (recommended)

```bash
pip install -r requirements.txt -r fta_web/requirements.txt
python3 fta_web/run.py
```

That starts a server on `127.0.0.1` and opens your browser on it. The terminal
prints the URL, which carries a **one-time session token** for this launch —
if the browser does not open by itself, paste that URL in. Press `Ctrl-C` to
stop; quitting the server invalidates the token and every page holding it.

```bash
python3 fta_web/run.py --port 8765     # fixed port instead of a free one
python3 fta_web/run.py --no-browser    # just print the URL
python3 fta_web/run.py --root ~/trees  # restrict the file browser to a directory
```

The server binds to loopback only and is not configurable to do otherwise: it
can read and write files on your machine, so it is deliberately unreachable
from the network. It is a single-user tool and runs as a single process — do
not put it behind gunicorn or uWSGI, which it refuses to start under.

**No Graphviz needed.** The diagram is rendered in your browser by a bundled
WebAssembly build of Graphviz. If you *do* have Graphviz installed, the extra
"render to file" export is enabled as well. Anything unavailable — Graphviz,
`openpyxl` for Excel, an AI provider SDK — shows up as a disabled control with
an explanation, never as a button that fails when you press it.

### Standalone executable (no Python required)

For machines without a Python installation, the web app can be frozen into a
single folder containing everything, Graphviz included:

```bash
pip install pyinstaller
python3 -m PyInstaller --clean --noconfirm \
    --distpath build/dist --workpath build/build \
    build/fta_editor.spec

./build/dist/fta_editor/fta_editor
```

Ship the whole `build/dist/fta_editor/` folder — the executable needs its
`_internal/` sibling. See [build/README.md](build/README.md) for prerequisites,
per-OS notes and how to verify a build.

### Desktop app

The original Tkinter application, unchanged in 1.6:

```bash
pip install -r requirements.txt
python src/FTA_Editor_UI.py
```

### Requirements

- Python 3.10+
- Flask (web app) — `fta_web/requirements.txt`
- Graphviz — **required by the desktop app**, optional for the web app
  ([graphviz.org](https://graphviz.org/download/))
- Tk and Pillow — desktop app only
- See `requirements.txt` for the rest

## AI Assistant Setup

The FTA Editor includes an integrated AI assistant supporting multiple providers: **OpenAI**, **Microsoft Copilot**, **Anthropic Claude**, and **Google Gemini**.

**Quick Setup:**
1. Get API key from your provider:
   - **Google Gemini**: https://aistudio.google.com/apikey (free tier available)
   - **OpenAI**: https://platform.openai.com/api-keys
   - **Microsoft Copilot**: https://portal.azure.com (Azure OpenAI service)
   - **Anthropic Claude**: https://console.anthropic.com/api-keys

2. Open FTA Editor → Click AI Settings (⚙)

3. Select provider, paste API key, configure endpoint, click "Test & Save"

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

### Web application

```bash
python3 fta_web/run.py
```

Open the printed URL. The left panel is the tree, the middle the node details,
the right the live diagram; the AI assistant is in its own panel. Everything is
in one page — there is nothing to install in the browser.

### GUI Application (desktop)

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
├── src/                          # Desktop application (frozen for the 1.6 line)
│   ├── FTA_Editor_UI.py         # GUI application with AI chat
│   ├── FTA_Editor_core.py       # Core business logic
│   ├── AI_agent_handler.py      # AI agent and API handling
│   └── json_viewer.py           # Diagram renderer
├── fta_web/                      # Web application
│   ├── run.py                   # Launcher -- the only supported entry point
│   ├── app.py                   # Flask app factory
│   ├── security.py              # Session token, Host/Origin pinning
│   ├── routes/                  # /api blueprints: tree, render, files, ai
│   ├── core/                    # Vendored fork of src/ -- see DIVERGENCE.md
│   ├── static/, templates/      # Frontend, incl. WebAssembly Graphviz
│   └── tests/                   # Web app test suite
├── build/                        # PyInstaller spec for the standalone build
├── tests/                        # Desktop test suite
├── data/examples/               # Sample data
├── docs/                        # Documentation
└── requirements.txt             # Python dependencies
```

`fta_web/core/` is a **vendored fork** of four modules from `src/`, taken at a
pinned commit and patched for five defects that are documented one by one in
[`fta_web/core/DIVERGENCE.md`](fta_web/core/DIVERGENCE.md). `src/`, `tests/` and
`data/` are frozen for the 1.6 line and pinned by hash;
`fta_web/tests/test_vendor_integrity.py` fails if either side moves without the
record being updated.

## Testing

```bash
python -m pytest tests/        # desktop
python -m pytest fta_web/tests/  # web app, vendored core, and the freeze guard
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
- [Build Guide](build/README.md) - Packaging the web app as a standalone executable
- [User Guide](docs/USER_GUIDE.md) - Complete manual
- **AI Provider Setup Guides:**
  - [Microsoft Copilot Setup](docs/MICROSOFT_COPILOT_SETUP.md) - Azure OpenAI configuration
  - [GitHub Copilot Setup](docs/GITHUB_COPILOT_SETUP.md) - GitHub Models configuration
  - [Multi-Provider Setup](docs/MULTI_PROVIDER_SETUP.md) - OpenAI, Claude, Gemini
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
- *Web app*: the diagram still renders — it is drawn in your browser by a
  bundled WebAssembly Graphviz. Only "render to file" needs the native binary,
  and the app tells you so rather than failing silently.
- *Desktop app*: install Graphviz from
  [graphviz.org](https://graphviz.org/download/), add it to your `PATH`, and
  restart the application.

**Diagram not displaying:**
- *Web app*: check the browser console; `/static/vendor/viz-js/viz.js` must load.
- *Desktop app*: ensure Pillow is installed (`pip install Pillow`) and verify
  your Graphviz installation.

### Web App Issues

**"Forbidden" / 403 on every action:**
- The page was opened without this launch's session token. Use the URL the
  terminal printed, including its `?t=` part. A token is minted per launch, so
  a URL from a previous run will not work.

**The browser did not open:**
- Copy the URL from the terminal. Or start with `--no-browser`, which only
  prints it.

**"Excel export unavailable":**
- `pip install openpyxl`, then restart the server.

## License

BSD-2 License - Copyright (c) makkiblog.com

## Support

- Issues: [GitHub Issues](https://github.com/Gertrud-Violett/FTA_editor/issues)
- Examples: [data/examples/](data/examples/)
