# Quick Start Guide

Get up and running with FTA/ETA Editor in 3 steps.

**Version**: 1.6.0 (Updated: September 9, 2026)

New in 1.6: the editor runs in your **browser**, with no Graphviz to install.
That is the recommended way to run it. The Tkinter desktop app is unchanged and
still supported — its instructions are below.

## 1. Install

**Prerequisites:** Python 3.10+ (that is all, for the web app)

```bash
git clone https://github.com/Gertrud-Violett/FTA_Editor.git
cd FTA_Editor
pip install -r requirements.txt -r fta_web/requirements.txt
```

## 2. Run

```bash
python3 fta_web/run.py
```

Your browser opens on the editor. The terminal prints the URL as well — it
carries a **one-time token for this launch**, so if the browser does not open
by itself, paste that whole URL in. `Ctrl-C` stops the server.

Useful flags: `--port 8765` for a fixed port, `--no-browser` to only print the
URL, `--root ~/trees` to confine the file browser to one directory.

<details>
<summary><b>Desktop app instead (Tkinter, v1.5.1 behaviour, unchanged)</b></summary>

**Extra prerequisites:** Tk and [Graphviz](https://graphviz.org/download/).

```bash
pip install -r requirements.txt
python src/FTA_Editor_UI.py
```

Or run `python install.py`, which checks the prerequisites for you.
</details>

<details>
<summary><b>No Python on the machine?</b></summary>

Build a standalone folder that contains its own Python **and** its own Graphviz:

```bash
pip install pyinstaller
python3 -m PyInstaller --clean --noconfirm \
    --distpath build/dist --workpath build/build \
    build/fta_editor.spec

./build/dist/fta_editor/fta_editor
```

Copy the whole `build/dist/fta_editor/` folder to the target machine — the
executable needs its `_internal/` sibling. Details in
[build/README.md](build/README.md).
</details>

## 3. Use

1. **Create nodes**: Select root, click "Add Node"
2. **Set probabilities**: Edit node, enter probability (0-1)
3. **Set logic gates**: Choose AND or OR for non-leaf nodes
4. **Choose mode**: FTA (failure analysis) or ETA (event sequences)  
5. **View diagram**: Logic gates displayed inside node boxes
6. **Export**: Save as JSON/Excel/XML or render diagram

### AI Quick Actions (optional)
- **Analyze FTA**: Reads the current tree and posts analysis/suggestions to chat only (no changes applied).
- **Update FTA**: Generates a complete, validated JSON from the AI and replaces the entire FTA in one step. Existing nodes are preserved; only additions are applied.

## AI Assistant Setup (Optional)

The AI assistant can analyze your FTA and suggest improvements.

1. **Get an API key** from [OpenAI Platform](https://platform.openai.com/)
2. **Click ⚙ (Settings)** in the AI Assistant panel
3. **Enter your API key** and click "Test & Save"
4. **Start chatting!** Ask questions or use quick actions

Your API key is stored locally at `~/.fta_editor/ai_credentials.json`, never in the repository.

See [README.md](README.md#ai-assistant-setup) for detailed setup instructions.

## What's New in v1.6.0

- ✅ **Runs in your browser**: `python3 fta_web/run.py`. Local, single-user, bound to `127.0.0.1` only.
- ✅ **No Graphviz needed**: the diagram is drawn in the browser by a bundled WebAssembly Graphviz. Install Graphviz only if you want the "render to file" export.
- ✅ **Nothing fails silently**: a missing optional dependency shows up as a disabled control with an explanation, not a button that errors when pressed.
- ✅ **Standalone executable**: a build that needs neither Python nor Graphviz on the target machine — see [build/README.md](build/README.md).
- ✅ **Five defect fixes** in the web app's copy of the core, each written up in [`fta_web/core/DIVERGENCE.md`](fta_web/core/DIVERGENCE.md) — notably `NOT` gates that were silently computed as `OR`, a move guard that permitted exactly the moves that corrupt the tree, and minified JSON files that failed to open with a misleading "encoding" error.
- ✅ **Desktop app unchanged** and still supported.

## Keyboard Shortcuts

Desktop app:

| Shortcut | Action |
|----------|--------|
| `Ctrl+N` | New analysis |
| `Ctrl+A` | Add node |
| `Ctrl+E` | Edit node |
| `Ctrl+D` | Delete node |
| `Ctrl+S` | Save |
| `Ctrl+R` | Render diagram |

## Need Help?

- Load example: `data/examples/sampleFTA.json` (the web app offers
  `fta_web/examples/sampleFTA.json`, the same tree)
- Documentation: `docs/USER_GUIDE.md`
- AI Setup: See [README.md](README.md#ai-assistant-setup)
- Building a standalone executable: [build/README.md](build/README.md)
- Test installation: `python -m pytest tests/ fta_web/tests/`