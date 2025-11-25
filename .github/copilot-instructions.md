# FTA/ETA Editor - AI Coding Agent Instructions

## Project Overview

This is a **Fault Tree Analysis (FTA) and Event Tree Analysis (ETA) editor** with dual interfaces (desktop GUI + web app) for reliability engineering and safety analysis. The core calculates failure/accident probabilities using logic gates (AND/OR) and link relationships.

**Version**: 1.4.2 | **License**: BSD-2 | **Python**: 3.14

## Architecture

### Three-Layer Design

1. **Core Logic** (`src/FTA_Editor_core.py`): Stateful `FTACore` class managing:
   - Tree data structure (recursive dict with `id`, `name`, `probability`, `children`, `logicGate`, `links`)
   - Probability calculations (FTA=bottom-up, ETA=top-down)
   - Import/export (JSON with multiple encodings, XML, hierarchical Excel)
   
2. **Desktop GUI** (`src/FTA_Editor_UI.py`): Tkinter-based tree editor
   - Single-threaded with X11 display for Docker
   - Calls `FTACore` methods directly

3. **Web Application** (`web_app/app.py`): Flask REST API with:
   - **Session-based state** using filesystem sessions (not in-memory!)
   - `get_core()` restores state from session, `save_core()` persists after EVERY modification
   - Gunicorn deployment for Render.com (2 workers, 120s timeout)
   - Diagram renderer (`src/json_viewer.py`) generates Graphviz PNG from tree data

### Critical Data Flow

```
User Action → API Endpoint → get_core() → FTACore method → save_core() → Response
                                          ↓
                              JSON tree → json_viewer.py → Graphviz → PNG
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

### 2. Session Management (Fixed in v1.4.2)

Web app had state inconsistency with Gunicorn workers. **Solution**:

```python
# ALWAYS use filesystem sessions, not dicts
def get_core():
    core = FTACore()
    if 'fta_data' in session:
        core.fta_data = session['fta_data']  # Restore
    return core

def save_core(core):
    session['fta_data'] = core.fta_data
    session.modified = True  # Mark for persistence
```

Call `save_core()` after ANY mutation (add/update/delete/calculate).

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

- Font: `"Noto Sans CJK JP"` (Docker: `fonts-noto-cjk` package)
- Color coding: Pink (prob=1.0), lightblue (prob=0.0), lightyellow (prob≥0.7)
- Gates displayed **inside** node boxes (not separate nodes)
- Hide zero-probability nodes via `hide_zero` parameter

## Development Workflows

### Local Development

```bash
# Setup
pip install -r requirements.txt
sudo apt install graphviz fonts-noto-cjk  # Linux
brew install graphviz                      # macOS

# Run GUI
python src/FTA_Editor_UI.py

# Run web app
python web_app/app.py  # http://localhost:5000

# Run tests
python -m pytest tests/
```

### Docker Deployment

```bash
# GUI (requires X11 forwarding)
xhost +local:docker
docker-compose up fta-editor

# Web app
docker-compose up fta-web
```

### Render.com Deployment

- Uses `Dockerfile.render` and `render.yaml`
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 web_app.app:app`
- Environment: `SECRET_KEY` auto-generated, `PORT=5000`
- Free tier sleeps after 15 min inactivity

## Testing Guidelines

### Critical Test Patterns

1. **Probability Validation** (`test_probability_calculation.py`):
   - AND gate: Check product of children (NOT parent × product)
   - OR gate: Check union formula `1 - Π(1-p)`
   - Links: AND multiplies, OR unions
   - Circular refs: Use memoization to detect

2. **Session Persistence** (web app):
   - Test state survives across requests
   - Verify `session.modified = True` is set

3. **Encoding Tests**:
   - Test Japanese/Chinese characters in node names
   - Verify UTF-8-sig, cp932, shift_jis handling

### Running Tests

```bash
python tests/run_all_tests.py  # All tests
python tests/test_probability_calculation.py  # Just probability
```

## Common Pitfalls

1. **AND Gate Bug**: Never multiply parent base probability when children exist (fixed v1.3.0)
2. **Session Loss**: Always call `save_core()` after modifications in web app
3. **Graphviz Missing**: System package, not Python—install via apt/brew
4. **Circular References**: Use `memo` and `visiting` sets in recursive calculations
5. **Font Issues**: Use Noto Sans CJK for Asian characters, not Times New Roman

## Code Conventions

- **Docstrings**: All public methods with Args/Returns
- **Line length**: 100 chars
- **Naming**: `snake_case` functions, `PascalCase` classes
- **Error handling**: Return `(success: bool, error: str)` tuples
- **Testing**: pytest with descriptive test names (`test_<feature>_<scenario>`)
- **Versioning**: Update `setup.py`, `CHANGELOG.md`, `Dockerfile` versions together

## Key Files Reference

- `src/FTA_Editor_core.py`: Business logic (594 lines, ~40 methods)
- `src/json_viewer.py`: Graphviz rendering (326 lines)
- `web_app/app.py`: Flask API (383 lines, 15 endpoints)
- `tests/test_probability_calculation.py`: 690 lines, covers all gate logic
- `data/examples/sampleFTA.json`: Example tree structure
- `CHANGELOG.md`: Version history (v1.4.2 = session fixes + CJK fonts)
- `DEPLOYMENT.md`: All deployment options (Render, Docker, local)

## External Dependencies

- **Graphviz**: System package for diagram generation (`apt-get install graphviz`)
- **openpyxl**: Excel export with hierarchical formatting
- **Pillow**: PNG rendering and display
- **Flask + gunicorn**: Web app server (production)
- **pytest**: Test framework

## When Making Changes

1. **Probability calculations**: Run `test_probability_calculation.py` first
2. **Web API changes**: Update `save_core()` calls, test session persistence
3. **Tree structure changes**: Update `json_viewer.py` rendering logic
4. **Version bumps**: Update setup.py, CHANGELOG.md, Dockerfile, docker-compose.yml
5. **Font/i18n**: Test with Japanese example data

## Quick Commands

```bash
# Test installation
python -m pytest tests/ -v

# Load example
python src/FTA_Editor_UI.py  # File → Open → data/examples/sampleFTA.json

# Generate diagram from JSON
python src/json_viewer.py data/examples/sampleFTA.json output.png

# Export formats
core.export_to_json("out.json")
core.export_to_xml("out.xml")
core.export_to_excel("out.xlsx")
```

---

**Last Updated**: November 2025 | **Questions?** See README.md, DEPLOYMENT.md, or GitHub issues
