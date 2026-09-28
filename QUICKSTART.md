# Quick Start Guide

Get up and running with FTA/ETA Editor in 3 steps.

**Version**: 1.7.0 (Updated: September 28, 2026)

The editor runs in your **browser**, with no Graphviz to install — that is the
primary way to run it. The original Tkinter desktop app is kept in `desktop/`
as a frozen backup/fallback; its instructions are below.

## 1. Install

**Prerequisites:** Python 3.10+ (that is all, for the web app)

```bash
git clone https://github.com/Gertrud-Violett/FTA_Editor.git
cd FTA_Editor

# with uv (recommended -- faster, pins exact versions)
uv sync --extra web --extra excel --extra ai --extra report   # or: uv sync --extra all

# or with pip
pip install -r requirements.txt -r fta_web/requirements.txt
```

## 2. Run

```bash
uv run python fta_web/run.py     # if you used uv above
python3 fta_web/run.py           # if you used pip
```

Your browser opens on the editor. The terminal prints the URL as well — it
carries a **one-time token for this launch**, so if the browser does not open
by itself, paste that whole URL in. `Ctrl-C` stops the server.

Useful flags: `--port 8765` for a fixed port, `--no-browser` to only print the
URL, `--root ~/trees` to confine the file browser to one directory.

<details>
<summary><b>Legacy desktop app instead (Tkinter, v1.5.1 behaviour, frozen fallback)</b></summary>

**Extra prerequisites:** Tk and [Graphviz](https://graphviz.org/download/).

```bash
uv sync --extra desktop --extra excel --extra ai   # or: pip install -r requirements.txt
uv run python desktop/src/FTA_Editor_UI.py         # or: python desktop/src/FTA_Editor_UI.py
```

See [desktop/README.md](desktop/README.md) for the defects that are fixed in
the web app but not in this fallback.

Or run `python install.py`, which detects `uv` and uses it automatically,
falling back to pip if `uv` isn't on your PATH — either way it checks
prerequisites and offers to launch the app when it's done.
</details>

<details>
<summary><b>No Python on the machine?</b></summary>

Build a standalone folder that contains its own Python **and** its own Graphviz:

```bash
uv sync --extra all --extra build
uv run python -m PyInstaller --clean --noconfirm \
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
6. **Check**: the **Validation** tab lists mistakes, such as events left at
   1.0 or single-input gates, each with a one-line fix
7. **Export**: Save as JSON/Excel/XML or render diagram

### Advanced mode (1.7)

Switch on **Advanced** in the top bar to get:

- failure-rate models (λ with a mission time, standby, repairable)
- k-out-of-n, XOR, INHIBIT, Priority-AND and transfer gates
- house and undeveloped events
- the **Cut Sets**, **Importance**, **Uncertainty**, **Traceability**,
  **FMEA** and **Report** tabs

Nothing in the file or the results changes when you flip the switch. **Sig.
figs** in the top bar sets how many significant figures probabilities are
shown with.

### Command line (1.7)

```bash
uv run python fta_web/run.py validate my_tree.json         # exit 1 on errors
uv run python fta_web/run.py cutsets my_tree.json --top 10
fta_editor.exe validate *.json --json                      # the standalone build
```

See the [CLI reference](docs/USER_GUIDE.md#command-line-interface).

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

## What's New in v1.7.0

- ✅ **Analysis tabs**: Quantification, Cut Sets, Importance, Uncertainty,
  Validation, Traceability, FMEA and Report, in the bottom panel.
- ✅ **Failure-rate models** with a mission time, and λ in /h, /y or FIT.
- ✅ **Standard gates and symbols**: k-out-of-n, XOR, INHIBIT, Priority-AND,
  transfer, house and undeveloped events, a top-down layout and IEC 61025
  symbols.
- ✅ **Minimal cut sets, importance measures and Monte Carlo uncertainty.**
- ✅ **DOCX report** and flat Events/Analysis sheets in Excel.
- ✅ **FMEA import** (CSV/XLSX) and **traceability fields** with tree search.
- ✅ **Command-line batch mode** (`validate`, `quantify`, `cutsets`,
  `importance`, `mc`, `report`).
- ✅ **Basic/Advanced switch** and a **significant-figures** setting. Small
  probabilities such as 1e-7 no longer display as `0`.
- ✅ **Files stay compatible**: the new keys are optional. See
  [Desktop app compatibility](docs/USER_GUIDE.md#desktop-app-compatibility).

## What's New in v1.6.0

- ✅ **Runs in your browser**: `python3 fta_web/run.py`. Local, single-user, bound to `127.0.0.1` only.
- ✅ **No Graphviz needed**: the diagram is drawn in the browser by a bundled WebAssembly Graphviz. Install Graphviz only if you want the "render to file" export.
- ✅ **Nothing fails silently**: a missing optional dependency shows up as a disabled control with an explanation, not a button that errors when pressed.
- ✅ **Standalone executable**: a build that needs neither Python nor Graphviz on the target machine — see [build/README.md](build/README.md).
- ✅ **Five defect fixes** in the web app's copy of the core, each written up in [`fta_web/core/DIVERGENCE.md`](fta_web/core/DIVERGENCE.md) — notably `NOT` gates that were silently computed as `OR`, a move guard that permitted exactly the moves that corrupt the tree, and minified JSON files that failed to open with a misleading "encoding" error.
- ✅ **Desktop app unchanged** and still supported.
- ✅ **Installation via `pyproject.toml`**: `uv sync --extra <name>` is the
  recommended path (fast, exact versions pinned in `uv.lock`); plain
  `pip install -r requirements.txt` still works if you don't have uv.

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

- Load example: `fta_web/examples/sampleFTA.json` (the legacy desktop app
  has the same tree at `desktop/data/examples/sampleFTA.json`)
- Documentation: `docs/USER_GUIDE.md`
- AI Setup: See [README.md](README.md#ai-assistant-setup)
- Building a standalone executable: [build/README.md](build/README.md)
- Test installation: `python -m pytest` (runs `fta_web/tests/` and `desktop/tests/`)