# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.0] - 2026-09-09

The editor now runs in a browser. Everything in this release is additive: the
Tkinter desktop app in `src/` is byte-for-byte unchanged and still the way to
run version 1.5.1.

### Added

- **Web application (`fta_web/`)** — the same editor as a local, single-user
  web app. `python3 fta_web/run.py` starts a loopback-only server and opens a
  browser on it.
  - **Tree editing**: add, edit, delete, reorder and move nodes; 50 levels of
    undo/redo; live probability recalculation with AND/OR gates; FTA and ETA
    modes; zero-probability nodes highlighted.
  - **Diagram rendering with no Graphviz installed.** The browser draws the
    diagram from `GET /api/dot` using a vendored WebAssembly build of Graphviz
    (`static/vendor/viz-js/viz.js`). A native `dot` binary, when present, is
    used only by `POST /api/render` to produce a file to save.
  - **Honest capability disclosure.** `GET /api/state` returns a
    `capabilities` object (`nativeDot`, `excelExport`, `aiConfigured`); the UI
    disables and *explains* a control whose optional dependency is missing
    instead of offering a button that fails when pressed.
  - **File I/O and exports**: open/save/save-as with a sandboxed file browser,
    plus JSON, XML, Excel, SVG and PNG export.
  - **AI assistant**: chat, "Analyze FTA" and "Update FTA", over OpenAI,
    Azure/Microsoft Copilot, Anthropic Claude and Google Gemini — the same
    providers and the same credential file (`~/.fta_editor/ai_credentials.json`)
    as the desktop app.
  - **Security model** for a tool that can read and write local files: bound to
    `127.0.0.1` only and not configurable; a per-launch token minted at startup,
    never persisted, required in the `X-FTA-Token` header on every `/api/*`
    call; Host/Origin pinned against DNS rebinding; the filesystem endpoints
    confined to a sandbox root (`--root`, default `$HOME`) with an extension
    allowlist; request bodies capped at 10 MB. A cookie session is deliberately
    *not* used — the browser would attach it to a forged cross-site request,
    which is the attack the header token prevents.
  - Refuses to start under gunicorn/uWSGI/mod_wsgi or with `WEB_CONCURRENCY>1`:
    the whole editor state is one in-process object, so a second worker would
    not crash, it would silently lose edits.

- **Standalone executable** (`build/fta_editor.spec`) — a PyInstaller *onedir*
  bundle of the web app that runs with **neither Python nor Graphviz
  installed**. Build with
  `python3 -m PyInstaller --clean --noconfirm --distpath build/dist --workpath build/build build/fta_editor.spec`;
  about 20 MB on Linux. Onefile is deliberately not used — it re-extracts the
  whole bundle to a temp directory on every launch and reliably trips antivirus
  heuristics. See [`build/README.md`](build/README.md) for the full rationale,
  per-OS notes and verification steps. Windows and macOS builds must be
  produced on those platforms; PyInstaller does not cross-compile.

- **`fta_web/runtime_paths.py`** — single place that resolves bundled data
  paths, through `sys._MEIPASS` when frozen and relative to `fta_web/` from a
  checkout.

### Changed

- **Vendored core fork.** `fta_web/core/` holds copies of `AI_agent_handler.py`,
  `FTA_Editor_core.py`, `ai_providers.py` and `json_viewer.py` taken from `src/`
  at commit `e5f655f`. `src/`, `tests/` and `data/` are frozen for the 1.6 line
  and pinned by SHA-256 in `fta_web/core/BASELINE.json`; the fork is the copy
  1.6 is allowed to patch, and `fta_web/tests/test_vendor_integrity.py` fails
  the build if either side changes without the manifest and the divergence
  record being updated together.

  Five defects are fixed in the fork and **not** in `src/`. Full write-ups,
  including the evidence and the behaviour change for each, are in
  [`fta_web/core/DIVERGENCE.md`](fta_web/core/DIVERGENCE.md):

  - **D1** — `AIAgentHandler._get_client()` was dead code that could only ever
    raise `AttributeError` (`__init__` never assigned `self._client`). Deleted;
    the live path, `_get_provider()`, was already correct. No observable change.
  - **D5** — `logicGate: "NOT"` was accepted by validation but computed as
    **OR**: the probability engine branches on `AND` and falls through to the OR
    union formula for everything else, so a NOT gate produced a wrong number
    with no error and nothing in the UI to show the gate had been ignored. `NOT`
    is now rejected at all four acceptance sites with a message naming the
    offending node, and is no longer advertised to the model in the schema or
    the system prompt. Trees relying on the silent OR fallback now surface an
    error, which is the point. The probability engine itself is unchanged.
  - **D7** — the move guard asked its question backwards. It tested whether the
    node being moved was inside the target's subtree, rather than whether the
    new parent was a descendant of the node being moved, so it rejected every
    legal move (promoting a grandchild, reordering under the same parent) and
    permitted the corrupting ones (a node into its own child or grandchild).
    Argument order corrected; the function now returns a real `bool` instead of
    leaking a node dict.
  - **D8** — minified JSON was mangled and then blamed on the file's encoding.
    A double-wrap repair ran unconditionally *before* parsing, and its
    `endswith("}}")` test matches every minified document; stripping the brace
    turned a valid file into invalid JSON and the resulting error was reported
    as "Failed to read file with common encodings". The document is now parsed
    as written first, with the legacy repair as a fallback. Minified files open;
    nothing that loaded before stops loading.
  - **D9** — `AnthropicProvider.get_default_models()` still returned the Claude
    3 family. That list is the *fallback* used when the live model fetch fails,
    which is exactly when a stale entry does the most damage. Refreshed to the
    current family, most-capable first. The model field is an editable combo and
    the live fetch is preferred, so the list ageing again degrades gracefully.

  One reported defect, **D3** (Excel sibling rows overwriting each other), was
  investigated and **not** reproduced — the report misreads a `nonlocal`
  high-water mark as a per-level counter. Verified exhaustively against all 626
  rooted ordered tree shapes of 1–8 nodes. No patch was applied; regression
  tests pin the layout instead.

- `requirements.txt` is unchanged. The web app's one extra dependency, Flask,
  is in `fta_web/requirements.txt`; install both with
  `pip install -r requirements.txt -r fta_web/requirements.txt`.

- `README.md` and `QUICKSTART.md` now lead with the web app.

### Deprecated

- Nothing yet. The desktop application (`src/FTA_Editor_UI.py`) is **unchanged,
  supported and retained** in this release. It is expected to be marked
  deprecated after 1.6 has shipped and the web app has been exercised in
  practice; it will be kept available after that, not deleted. Until that
  announcement, both applications are current.

## [1.5.1] - 2025-12-16

### Added

- **Multi-Provider AI Support**: Support for multiple AI platforms
  - New `ai_providers.py` module with abstraction layer for AI providers
  - **Google Gemini** support (free tier + pay-per-use)
  - **Anthropic Claude** support (pay-per-use)
  - **OpenAI** support (existing, enhanced)
  - **GitHub Copilot** support (via OpenAI-compatible API)
  - **Azure OpenAI** support (via OpenAI-compatible API)

- **Provider Implementations**:
  - `OpenAIProvider`: OpenAI and compatible APIs
  - `AnthropicProvider`: Anthropic Claude API
  - `GeminiProvider`: Google Gemini API
  - `AIProviderFactory`: Factory pattern for provider selection

- **Enhanced AI Settings Dialog**:
  - Provider selection dropdown (auto-updates endpoint and models)
  - Dynamic model list based on selected provider
  - Automatic endpoint population per provider

- **Documentation**:
  - `docs/QUICK_AI_SETUP.md`: 5-minute quick start guide
  - `docs/MULTI_PROVIDER_SETUP.md`: Detailed setup and troubleshooting
  - Updated README/Quick Start with new "Analyze FTA" and "Update FTA" flows

- **Full-JSON Update Flow**:
  - New "Update FTA" button generates a complete JSON from the AI and replaces the in-memory tree after validation
  - Validator rejects malformed outputs and reports the exact failing section/node
  - Detailed error logging for invalid JSON (snippet printed to chat and stderr)

- **UI**:
  - Arbitrary tree depth coloring; nested additions render correctly

### Changed

- **Credential Storage**: Enhanced to store provider information
  - Now stores: `api_key`, `api_endpoint`, `model`, `provider`
  - Backward compatible with previous credential format

- **AIAgentHandler**: Refactored to use provider abstraction
  - Provider-agnostic message sending
  - `configure()` accepts provider parameter
  - Added `generate_full_fta_update()` and `verify_updated_fta_json()`

- **requirements.txt**: Added support for all AI providers
  - Added: `anthropic>=0.7.0`
  - Added: `google-generativeai>=0.3.0`
  - Kept: `openai>=1.0.0`

- **README.md**: Updated AI Assistant documentation with provider setup instructions
  - Added Quick Actions description (Analyze vs Update)

---

## [1.5.0] - 2025-12-16

### Added

- **AI Assistant Integration**: Integrated chat interface for AI-powered FTA analysis
  - Chat panel in main UI with message history
  - Quick action buttons: "Analyze FTA", "Suggest Root Causes", "Clear Chat"
  - Threaded API calls for responsive UI during AI processing
  - Color-coded messages (user/AI/system/error)

- **AI Agent Handler** (`src/AI_agent_handler.py`): New module for AI functionality
  - `AICredentialManager`: Secure local storage of API credentials
  - `FTAStructureAnalyzer`: Converts FTA data to AI-readable format
  - `AIProposedChange`: Data class for structured change proposals
  - `AIAgentHandler`: Main handler for OpenAI API interactions
  - System prompt optimized for FTA/ETA analysis

- **Change Confirmation Workflow**: User approval required for AI modifications
  - Confirmation dialog shows all proposed changes
  - Selectable list of changes to apply
  - Detailed view of change data (type, target, description)
  - Warning message before applying changes

- **Secure Credential Storage**: API keys stored outside repository
  - Credentials saved at `~/.fta_editor/ai_credentials.json`
  - Never uploaded or committed to version control
  - Settings dialog with show/hide API key toggle
  - Connection test before saving credentials

- **AI Settings Dialog**: Configure AI credentials in-app
  - API Key input with show/hide toggle
  - Customizable API endpoint (OpenAI, Azure, or compatible)
  - Model selection dropdown (gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo)
  - Test connection functionality
  - Clear credentials option

### Changed

- **UI Layout**: Added AI chat panel on right side of main window
  - Main content area now uses horizontal paned window
  - Chat panel is resizable and collapsible
  - Status indicator shows AI configuration state (●/○)

- **Dependencies**: Updated `requirements.txt`
  - Added `openai>=1.0.0` for AI API integration
  - Removed web application dependencies (Flask, gunicorn, etc.)
  - This version focuses on desktop application only

### Removed

- **Web Application**: Removed Flask-based web interface
  - `web_app/` directory no longer supported in this branch
  - Removed Flask, Flask-Session, gunicorn, requests dependencies
  - Docker deployment configurations removed
  - Render.com deployment no longer supported

### Migration Notes

- Existing FTA JSON files are fully compatible
- No changes to core FTA/ETA functionality
- AI features are optional - application works without API configuration
- Web application users should use v1.4.x branch

## [1.4.2] - 2025-11-25

### Added

- **Japanese Font Support**: Embedded Noto Sans CJK JP font for proper Japanese character rendering
  - Installed `fonts-noto-cjk` package in Docker containers
  - Updated Graphviz font settings to use "Noto Sans CJK JP"
  - Supports Japanese, Chinese, and Korean characters in node names and labels

### Fixed

- **Session State Persistence**: Fixed node replacement and deletion issues on Render.com
  - Replaced in-memory session dictionary with Flask filesystem session storage
  - Added `save_core()` function to persist state after every modification
  - Fixed state consistency across Gunicorn worker processes
  - Resolved issues where nodes were incorrectly replaced or deleted during editing
- **Diagram Auto-Refresh**: Fixed automatic diagram updates in web interface
  - Removed incompatible timestamp query parameter from base64 data URIs
  - Added proper error logging for diagram loading failures
  - Made async refresh calls properly awaited in all tree mutation operations

### Changed

- **Docker Configuration**: Updated all Docker files to version 1.4.2
- **Font System**: Changed from Times New Roman to Noto Sans CJK JP for international character support

## [1.4.1] - 2025-11-21

### Added

- **Web Application**: Flask-based web interface for browser-based FTA/ETA editing
  - Interactive tree editing with live diagram preview
  - Zoom and pan functionality for diagram viewing (mouse wheel + click-drag)
  - Resizable panels (fault tree and node details) with drag handles
  - Real-time diagram rendering without page refresh
  - Session-based multi-user support
  - Export/import functionality (JSON, XML, Excel)
  - Node CRUD operations via REST API
  - Responsive UI with Font Awesome icons
- **Render.com Deployment Support**: Free cloud hosting configuration
  - `render.yaml` for automatic deployment
  - Gunicorn production server setup
  - Environment-based configuration
  - Auto-deploy from GitHub integration
- **Deployment Documentation**: Complete guides for cloud hosting
  - `RENDER_DEPLOYMENT.md`: Quick-start guide for Render.com
  - Enhanced `DEPLOYMENT.md` with Render.com as Option 1
  - Cost comparison and scaling information

### Changed
- **Session Management**: Dedicated session directory to prevent conflicts with system temp files
  - Fixed OSError warnings from cachelib accessing incompatible temp files
  - Isolated Flask sessions in dedicated directory
- **Security**: Environment-based SECRET_KEY for production deployment
- **Requirements**: Added Flask, Flask-Session, and gunicorn dependencies

### Fixed
- **Cache File Warnings**: Eliminated OSError warnings from Arduino IDE and other temp files
- **Production Configuration**: Disabled debug mode and dynamic port binding for cloud deployment

## [1.3.1] - 2025-11-06

### Changed
- **UI Improvements**: Updated `json_viewer.py` and `FTA_Editor_UI.py` with minor visual enhancements
  - Probabilities now display side by side (Gate:  |  P_base: X.X | P_calc: X.X) to save space
  - Added proper cell height to prevent text cutoff in node labels
  - Applied Times New Roman font consistently across the entire diagram
  - Improved node name and probability text visibility
  - Added checkbox to hide nodes with zero probability.
  - Improved Preview UI resolution.
  - Added "New Analysis" button to create new FTA.
  - Fixed graph UI bug. Now the same order is preserved for FTA tree and graph view.

## [1.3.0] - 2025-11-01

### Fixed
- **CRITICAL: AND Gate Probability Calculation**: Fixed incorrect calculation that was multiplying parent's base probability with children probabilities
  - **Before**: `parent_base_prob × ∏(child_probabilities)` - incorrectly included parent's base probability
  - **After**: `∏(child_probabilities)` - correctly calculates as product of children only
  - **Impact**: AND gates now follow standard Fault Tree Analysis principles
  - **Note**: Existing FTA diagrams with AND gates may show different (but correct) probabilities if parent nodes had base probabilities ≠ 1.0
- Updated test suite to reflect correct AND gate behavior (all 13 tests pass)
- Updated documentation to clarify that parent base probability is ignored when logic gates are applied with children

### Changed
- `_recalculate_fta_probabilities()` method now correctly ignores parent base probability for AND gates
- Test expectations updated in `test_probability_calculation.py`
- Documentation updated in `PROBABILITY_VALIDATION.md`

## [1.2.0] - 2025-10-31

### Added
- **ETA (Event Tree Analysis) Mode**: Top-down probability calculation for accident sequence analysis
- **Metadata Support**: Title, date, and mode fields saved with analyses
- **Top Bar UI**: Mode selector dropdown, title field, and date field
- **Hierarchical Excel Export**: Tree structure exported with nested columns
- **Dynamic Tree Labels**: Changes between "Fault Tree" and "Event Tree" based on mode
- **Comprehensive Documentation**: User guide, API reference, ETA documentation
- **Docker Support**: Dockerfile and docker-compose.yml for containerization
- **Test Suite**: Complete test coverage for ETA mode and core functionality

### Changed
- **JSON Format**: Now includes metadata (backward compatible with legacy format)
- **Excel Export**: Hierarchical columns instead of flat rows
- **Calculation Engine**: Supports both FTA (bottom-up) and ETA (top-down) modes

### Fixed
- Probability calculation edge cases
- Circular reference handling
- Zero probability node detection

## [1.1.1] - 2025-10-30

### Added
- Excel export with hierarchical column structure
- Color-coding by depth level in Excel
- Auto-adjusted column widths
- Wrapped text for better readability

### Changed
- Excel export format from flat to hierarchical

## [1.1.0] - 2025-10-29

### Added
- Code refactoring: Split into UI and Core modules
- `FTA_Editor_core.py`: Core business logic
- `FTA_Editor_UI.py`: User interface layer
- Comprehensive test suite (19 tests)
- API for programmatic usage

### Changed
- Project structure: Separation of concerns
- Improved maintainability and testability

### Deprecated
- None (original FTA_Editor.py preserved for backward compatibility)

## [1.0.0] - 2025-10-01

### Added
- Initial FTA Editor release
- Fault tree creation and editing
- Probability calculations with AND/OR gates
- Node linking system
- JSON export/import
- XML export
- Graphviz diagram visualization
- Live preview with zoom/pan

---

## Release Notes

### Version 2.0.0 - Web Application and Cloud Deployment

This major release introduces a browser-based web application alongside the existing desktop GUI, plus free cloud hosting support.

**Key Highlights**:
- Full-featured web interface accessible from any browser
- Interactive diagram viewing with zoom/pan controls
- Resizable UI panels for customized workspace
- One-click deployment to Render.com (free tier)
- Multi-user session support
- REST API for programmatic access
- No installation required for web version

**Web Application Features**:
- Interactive tree editing with real-time updates
- Live diagram preview with mouse wheel zoom and drag-to-pan
- Resizable fault tree and node details panels
- Export to JSON, XML, and Excel formats
- Import existing FTA/ETA analyses
- Session-based data isolation for multiple users

**Deployment Options**:
- **Web (Render.com)**: Free cloud hosting with auto-deploy from GitHub
- **Local Web**: Run Flask app locally at http://localhost:5000
- **Desktop GUI**: Traditional tkinter application (unchanged)
- **Docker**: Containerized deployment for both GUI and web app

**Quick Start (Web)**:
```bash
pip install -r requirements.txt
python web_app/app.py
# Open http://localhost:5000 in browser
```

**Deploy to Render.com**:
```bash
git push origin main
# Connect repository at render.com
# Auto-deploys with render.yaml configuration
```

**Technical Improvements**:
- Fixed session cache conflicts with system temp files
- Environment-based configuration for production
- Gunicorn production server integration
- Dedicated session directory to prevent cache errors

**Migration Note**:
- Desktop GUI remains unchanged and fully functional
- Web application is an additional interface option
- All existing JSON files work with both interfaces
- No breaking changes to existing workflows

See [RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md) for cloud hosting guide.

### Version 1.3.1 - UI Improvements and Bug Fixes

This major release adds Event Tree Analysis (ETA) capability alongside the existing Fault Tree Analysis (FTA), making the tool suitable for both reliability analysis and accident sequence modeling.

**Key Highlights**:
- Dual-mode analysis (FTA/ETA) with easy switching
- Complete metadata support for better documentation
- Improved Excel export with visual hierarchy
- Production-ready with Docker support
- Comprehensive documentation for public use

**Migration Guide**:
- Legacy JSON files load automatically (default to FTA mode)
- No breaking changes to existing workflows
- New JSON format is recommended for new projects

**Docker Deployment**:
```bash
docker-compose up
```

**Programmatic Usage**:
```python
from src.FTA_Editor_core import FTACore
core = FTACore()
core.set_metadata(mode="ETA", title="Analysis")
```

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for complete documentation.
