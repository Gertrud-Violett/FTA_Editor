# FTA/ETA Editor - AI Coding Agent Instructions

## Project Overview

This is a **Fault Tree Analysis (FTA) and Event Tree Analysis (ETA) editor** with dual interfaces (desktop GUI + web app) for reliability engineering and safety analysis. The core calculates failure/accident probabilities using logic gates (AND/OR) and link relationships.

**Version**: 1.7.1 | **License**: BSD-2-Clause | **Python**: 3.10+

## Architecture

### Three-Layer Design

> **Layout note (2026-09):** the web app in `fta_web/` is the primary path.
> The legacy Tkinter app and its tests/data moved to `desktop/` (`desktop/src/`,
> `desktop/tests/`, `desktop/data/`) and are frozen. An older `web_app/`
> Render.com deployment (filesystem sessions, gunicorn) no longer exists, and
> none of its patterns apply to `fta_web/` (see `docs/V1.6_WEB_SPEC.md`). The
> vendored core the web app actually runs is `fta_web/core/`.

1. **Core Logic** (`desktop/src/FTA_Editor_core.py`, vendored as `fta_web/core/FTA_Editor_core.py`): Stateful `FTACore` class managing:
   - Tree data structure (recursive dict with `id`, `name`, `probability`, `children`, `logicGate`, `links`)
   - Probability calculations (FTA=bottom-up, ETA=top-down)
   - Import/export (JSON with multiple encodings, XML, hierarchical Excel)
   - Both copies are hash-pinned (`fta_web/core/BASELINE.json`); read `fta_web/core/DIVERGENCE.md` before touching them. The 1.7 semantics (advanced gates, rate models, the `analysis` block) live in `fta_web/engine.py` (`WebCore(FTACore)`), with `cutsets.py`, `importance.py`, `uncertainty.py` and `lint.py` beside it.
   
2. **Desktop GUI** (`desktop/src/FTA_Editor_UI.py`, legacy fallback, frozen): Tkinter-based tree editor
   - Calls `FTACore` methods directly

3. **Web Application** (`fta_web/`, started only through `fta_web/run.py`): Flask app factory `fta_web/app.py` with the `/api` blueprints in `fta_web/routes/`:
   - **Single process, in-memory state**: one `AppState` (`fta_web/state.py`) holds the `WebCore`, the undo/redo stacks and the dirty flag, guarded by `state.lock`. No Flask sessions, no session store.
   - Refuses to start under gunicorn/uWSGI (each worker would hold its own copy of the document); binds to `127.0.0.1` only, with a per-launch token (`fta_web/security.py`).
   - Diagram: the server builds DOT (`fta_web/rendering.py`, `diagram_dot.py`, reusing `fta_web/core/json_viewer.py`) and the browser draws it with the vendored WebAssembly Graphviz (`static/vendor/viz-js/viz.js`). A native `dot` is used only for file exports.

### Critical Data Flow

```
User Action → /api endpoint → state.lock → push_undo() → WebCore method → recalculate → mark_dirty() → mutation payload
                                                                ↓
                              GET /api/dot → DOT text → browser viz.js (WASM) → SVG
```

## Key Technical Patterns

### 1. Probability Calculation Algorithm (Fixed in v1.3.0)

**CRITICAL**: v1.3.0 fixed AND gate bug. Do NOT use parent base probability when children exist.

```python
# FTA mode (bottom-up):
if not children:
    prob = base_probability
elif gate == "AND":
    prob = product(child_probs)  # NOT parent_prob × product!
else:  # OR
    prob = 1 - product(1 - p for p in child_probs)

# Then apply links: AND links multiply, OR links use union formula
```

**ETA mode** (top-down): Parent probability flows down, children multiply by their base probability.

### 2. State Management (web app)

The document lives in one in-process `AppState`. Every mutating endpoint
follows the contract at the top of `fta_web/routes/tree.py`:

```python
state = get_state()
with state.lock:                          # the whole read-modify-write
    state.push_undo()                     # before touching the tree
    ...                                   # mutate state.core
    state.core.recalculate_probabilities()
    state.mark_dirty()
    return ok_response(**_mutation_payload(state))  # tree, zeroNodes, dirty, canUndo, canRedo, ...
```

Do not add Flask sessions, a session store or a multi-worker server.

### 3. Node Structure

```python
{
    "id": "unique_id",
    "name": "Node Name",
    "type": "Root|Event|Outcome",
    "probability": 0.5,           # Base probability (leaf input)
    "calculatedProbability": 0.3,  # Computed from children/links
    "logicGate": "AND|OR|",        # Empty for leaves
    "children": [],
    "links": [                     # Cross-references outside tree
        {"target_id": "other_node", "relation": "AND|OR"}
    ],
    "notes": ""
}
```

### 4. Multi-Encoding File Loading

User base includes Japanese/Asian text. Use encoding fallback:

```python
encodings = ["utf-8-sig", "utf-8", "cp932", "shift_jis", "cp1252"]
for enc in encodings:
    try:
        with open(path, encoding=enc) as f:
            return json.load(f)
    except:
        continue
```

### 5. Graphviz Diagram Generation

- Font: `"Noto Sans CJK JP"` in the desktop app (`fonts-noto-cjk` on Linux); the web app auto-detects an installed CJK font (Meiryo, Yu Gothic, Hiragino, Noto Sans CJK JP, …)
- Color coding: Pink (prob=1.0), lightblue (prob=0.0), lightyellow (prob≥0.7)
- Gates displayed **inside** node boxes (not separate nodes) in the compact style; the web app's 1.7 *Standard symbols* style draws IEC 61025 gate symbols as separate nodes (`fta_web/diagram_dot.py`)
- Hide zero-probability nodes via `hide_zero` parameter

## Development Workflows

### Local Development

```bash
# Setup -- uv (recommended, see pyproject.toml) or pip
uv sync --extra dev
# pip install -r requirements.txt -r fta_web/requirements.txt
sudo apt install graphviz fonts-noto-cjk  # Linux, desktop app / native rendering only
brew install graphviz                      # macOS, desktop app / native rendering only

# Run the web app (primary): prints a URL with a per-launch token on 127.0.0.1
python fta_web/run.py

# Run the legacy desktop GUI (fallback)
python desktop/src/FTA_Editor_UI.py

# Run tests
python -m pytest fta_web/tests/ desktop/tests/
```

There is no Docker or hosted deployment: the web app is a local, single-user
tool, and the standalone build is described in `build/README.md`.

## Testing Guidelines

### Critical Test Patterns

1. **Probability Validation** (`test_probability_calculation.py`):
   - AND gate: Check product of children (NOT parent × product)
   - OR gate: Check union formula `1 - Π(1-p)`
   - Links: AND multiplies, OR unions
   - Circular refs: Use memoization to detect

2. **Web API** (`fta_web/tests/test_api_*.py`, `test_analysis_routes.py`):
   - Check the mutation payload of every changing endpoint
   - Check that undo/redo restore the previous state

3. **Encoding Tests**:
   - Test Japanese/Chinese characters in node names
   - Verify UTF-8-sig, cp932, shift_jis handling

### Running Tests

```bash
python -m pytest                        # All tests (fta_web/tests + desktop/tests)
python desktop/tests/run_all_tests.py   # Legacy desktop suite only
python desktop/tests/test_probability_calculation.py  # Just probability
```

## Common Pitfalls

1. **AND Gate Bug**: Never multiply parent base probability when children exist (fixed v1.3.0)
2. **Multi-worker servers**: The web app refuses gunicorn/uWSGI by design; run it only via `fta_web/run.py`
3. **Graphviz Missing**: System package, not Python—install via apt/brew
4. **Circular References**: Use `memo` and `visiting` sets in recursive calculations
5. **Font Issues**: Use Noto Sans CJK for Asian characters, not Times New Roman

## Code Conventions

- **Docstrings**: All public methods with Args/Returns
- **Line length**: 100 chars
- **Naming**: `snake_case` functions, `PascalCase` classes
- **Error handling**: Return `(success: bool, error: str)` tuples
- **Testing**: pytest with descriptive test names (`test_<feature>_<scenario>`)
- **Versioning**: Update `pyproject.toml` (the `version` field) and `CHANGELOG.md` together

## Key Files Reference

- `desktop/src/FTA_Editor_core.py`: Business logic (594 lines, ~40 methods)
- `desktop/src/json_viewer.py`: Graphviz rendering (326 lines)
- `fta_web/app.py`, `fta_web/routes/`: Flask app factory and the `/api` blueprints (endpoints in `docs/API_REFERENCE.md` and `docs/V1.6_WEB_SPEC.md` §5)
- `fta_web/engine.py`: `WebCore`, the 1.7 gates, rate models and `analysis` block
- `desktop/tests/test_probability_calculation.py`: 690 lines, covers all gate logic
- `fta_web/examples/sampleFTA.json` (and `desktop/data/examples/sampleFTA.json`): Example tree structure
- `CHANGELOG.md`: Version history
- `fta_web/core/DIVERGENCE.md`: Every patch of the vendored core

## External Dependencies

- **Graphviz**: System package for diagram generation (`apt-get install graphviz`); required by the desktop app, optional for the web app (native file exports)
- **openpyxl**: Excel export with hierarchical formatting
- **Pillow**: PNG rendering and display (desktop app only)
- **Flask**: Web app server (single process on 127.0.0.1; never gunicorn)
- **python-docx**: DOCX report (web app, optional)
- **pytest**: Test framework

## When Making Changes

1. **Probability calculations**: Run `test_probability_calculation.py` first
2. **Web API changes**: Keep every mutation undoable (`push_undo()` first), update `docs/API_REFERENCE.md` and the route tests
3. **Tree structure changes**: Update `json_viewer.py` rendering logic
4. **Version bumps**: Update `pyproject.toml`, `CHANGELOG.md` and `TOOL_VERSION` in `fta_web/report_docx.py` (`test_version_sync.py` checks them)
5. **Font/i18n**: Test with Japanese example data

## Quick Commands

```bash
# Test installation
python -m pytest -v

# Load example
python desktop/src/FTA_Editor_UI.py  # Load JSON → desktop/data/examples/sampleFTA.json

# Generate diagram from JSON
python desktop/src/json_viewer.py -i desktop/data/examples/sampleFTA.json -o output.png

# Export formats
core.save_to_json("out.json")
core.export_to_xml("out.xml")
core.export_to_excel("out.xlsx")
```

---

**Last Updated**: October 2026 | **Questions?** See README.md, docs/, or GitHub issues
