# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.2] - 2026-09-15

Fixes found by running the packaged build on Windows, and the CI that would
have caught most of them. Nothing here changes the desktop app (`src/`), which
remains frozen.

### Fixed

- **Every button in the web UI did nothing on some Windows machines.** Where
  the `.js` entry in `HKEY_CLASSES_ROOT` had been overridden to `text/plain`
  by other software, Flask's static handler — which asks the stdlib
  `mimetypes` module — served `main.js` as plain text. Browsers refuse to
  execute a `<script type="module">` that does not arrive as a JavaScript MIME
  type, so no frontend code ran at all and the whole editor looked dead. The
  server was healthy and its logs were clean, which is what made this hard to
  recognise. `fta_web/app.py` now pins the `.js` and `.css` types at import,
  overriding whatever the host claims.
- **Add Node created nothing.** The dialog collected its fields and never sent
  them to the server.
- **Render was unavailable without a native Graphviz**, even though the
  diagram panel's own PNG button already produced a file via the in-browser
  WebAssembly renderer in exactly that situation. Render now tries native
  first and falls back the same way.
- **Diagram labels could spill outside their node boxes.** Graphviz sized each
  box from its own estimate of the requested font's metrics, which does not
  match how the browser — or a different Graphviz build — actually renders
  that font, most visibly with Japanese text. Boxes are now sized by a trailing
  run of blank characters measured by the same engine, at the same size, as the
  visible text, so the box grows by whatever margin those characters genuinely
  need instead of by a guessed pixel value.
- **Dark mode did not reach the diagram.** The panel's chrome referenced CSS
  custom properties that were never defined and silently fell back to
  light-mode literals, and the rendered graph's background and connectors
  stayed light. Both now track the theme. Node fills are deliberately left
  alone — they encode calculated probability, not style — and link edges stay
  blue, since colour is what distinguishes a link from a tree edge.
- **The file dialog only accepted clicking through folders.** It now also takes
  a typed or pasted absolute path, resolving it as a folder to browse into or a
  file to open/save directly.
- **The FTA/ETA mode selector was clipped** by its own dropdown arrow.
- **Every SHA-256 pin failed on a Windows checkout.** Git for Windows defaults
  to `core.autocrlf=true` and rewrites LF to CRLF, and the pins in
  `fta_web/core/BASELINE.json` are a contract about *bytes*. A clean clone
  showed a dozen integrity failures with nothing edited — and, less visibly,
  the audit the PyInstaller bundle exists to support (hashing the shipped
  `fta_web/core/` against `BASELINE.json`) could never have passed on Windows.
  A new `.gitattributes` normalizes to LF and marks the pinned trees `-text`.
  A clone made before it exists needs `git rm --cached -r . && git reset --hard`
  once.

### Added

- **Continuous integration** (`.github/workflows/tests.yml`) — the full suite
  on Linux (Python 3.10 and 3.13, with Graphviz installed so the native render
  path is exercised) and on Windows. Previously nothing ran the tests unless a
  person remembered to, which is how a broken vendor pin reached `main`. The
  Windows job found two real problems on its first two runs.
- **Regression tests for the static asset MIME types**
  (`fta_web/tests/test_static_mime.py`). These reproduce the broken host — they
  poison `mimetypes` to report `text/plain` for `.js` first — because the
  obvious version of this test passes on Linux whether or not the fix exists,
  and would have pinned nothing.
- **A box-sizing control** on the diagram panel (the **Aa** popover): font
  auto-detection preferring Meiryo, a manual scale (0–30, default 4), and a
  draggable position.

### Changed

- **`docs/CHANGELOG.md` is now a pointer to this file** instead of a second
  copy. It had drifted — it stopped at 1.5.1 while this file went on to 1.6.x —
  and a changelog that is a year behind answers the question confidently and
  wrongly. Every entry it held is present here.
- **`docs/CONTRIBUTING.md` documents the frozen tree and the vendored fork.**
  The rule that `src/`, `tests/` and `data/` must not change, and that any edit
  to `fta_web/core/` needs a divergence entry plus a re-pin, previously existed
  only inside the file it governs and in a test's failure message.
- **`docs/USER_GUIDE.md`** documents dark mode, the box-sizing control, what
  the node colours mean, and where the AI Assistant's API key is stored.
- **Divergence D12** recorded in `fta_web/core/DIVERGENCE.md`: the diagram
  sizing and font/scale/dark parameters described above are a change to the
  vendored `json_viewer.py`. This is that file's first divergence and the last
  vendored module to leave byte-identity with its `src/` counterpart.

## [1.6.1] - 2026-09-13

Bug-fix release found by building and exercising the packaged executable from
[1.6.0](#160---2026-09-09) rather than only running from source.

### Fixed

- **Gemini in a frozen build.** The standalone executable's Google Gemini
  provider was non-functional (`"Google Generative AI package not installed"`
  regardless of key validity) while OpenAI and Anthropic worked correctly —
  caused by `google.generativeai` living under `google`, a PEP 420 namespace
  package that PyInstaller's plain `hiddenimports` silently fails to collect.
  Fixed by migrating `fta_web/core/ai_providers.py`'s `GeminiProvider` off the
  now end-of-life `google.generativeai` SDK onto its replacement,
  `google.genai` (divergence **D11** in `fta_web/core/DIVERGENCE.md`), and
  retargeting `build/fta_editor.spec`'s namespace-package `collect_all()`
  workaround at `google.genai` and `google.auth`. Verified against a rebuilt
  binary: all three providers now reach their real API with a deliberately
  invalid key and return the provider's own 4xx error. `pyproject.toml`'s `ai`
  extra now installs `google-genai`; the `desktop` extra gained
  `google-generativeai` explicitly, since the frozen `src/ai_providers.py`
  still needs the old package — the two apps now genuinely require different
  SDKs for the same provider. Bundle size: 80 MB with all three AI SDKs
  (down slightly from 1.6.0's 79 MB baseline despite adding a package, because
  `google.genai` itself needs none of the ~100 MB `google-api-python-client`
  chain the old SDK required — see `build/README.md`'s "Bundle size" section).

### Investigated, not a defect

- **Button clicks appearing to do nothing.** Reported after a packaged-build
  test: clicking any action-bar button seemed to not reach the server. Could
  not be reproduced — real, CDP-dispatched mouse clicks (not synthetic
  `.click()`) against a freshly built and launched binary correctly fire the
  expected `POST` request with no console errors, both before and after the
  Gemini fix above. If this recurs, the details that would narrow it down are
  the browser and OS used, whether the tab was freshly opened for that launch
  or reused from an earlier one (a stale per-launch auth token would fail
  every request), and anything shown in the browser's own developer console.

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
  `uv sync --extra all --extra build && uv run python -m PyInstaller --clean --noconfirm --distpath build/dist --workpath build/build build/fta_editor.spec`;
  about 20 MB on Linux with no AI providers bundled, up to ~79 MB with all
  three. Onefile is deliberately not used — it re-extracts the whole bundle to
  a temp directory on every launch and reliably trips antivirus heuristics.
  See [`build/README.md`](build/README.md) for the full rationale, per-OS
  notes and verification steps. Windows and macOS builds must be produced on
  those platforms; PyInstaller does not cross-compile.

- **`pyproject.toml`** — the source of truth for dependencies, for both apps.
  `[project.optional-dependencies]` splits them by what actually needs them:
  `web` (Flask), `desktop` (Pillow), `excel` (openpyxl, shared), `ai` (OpenAI +
  Anthropic + Gemini SDKs, shared), `test` (pytest) and `build` (PyInstaller);
  `all` bundles everything a user wants, `dev` adds `test` and `build` for
  contributors. Recommended install: `uv sync --extra <name>`, which also
  writes the committed `uv.lock` — exact resolved versions, so a `uv sync` run
  later reproduces the same environment. `pip install -r requirements.txt
  [-r fta_web/requirements.txt]` remains a supported fallback for anyone
  without [uv](https://docs.astral.sh/uv/); `install.py` now detects which
  tool is available and uses it, defaulting to uv.

  `[tool.uv] package = false`: this project is intentionally not built as an
  installable package. `src/` and `fta_web/` are flat module directories with
  no `__init__.py`, and `fta_web/core/` is imported by bare module name via a
  `sys.path` insertion — the layout that keeps it byte-identical to `src/` for
  the divergence pin (see `fta_web/core/DIVERGENCE.md`). Turning either tree
  into a real package would mean restructuring code a hash pin depends on
  staying untouched, so `pyproject.toml` declares dependencies without a
  `[build-system]` table, and `pip install .` is not a supported path — use
  `-r requirements.txt` instead. Both apps still run the ordinary way, e.g.
  `uv run python fta_web/run.py`.

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

- `requirements.txt` and `fta_web/requirements.txt` are unchanged in content —
  same packages, same versions — and remain the pip-fallback path. They are
  now secondary to `pyproject.toml`, described above, which is where a new
  dependency gets added first.

- **`setup.py` removed.** It declared `python_requires=">=3.14"` (the rest of
  the project has always targeted 3.10+) and packaged `src/` with
  `find_packages(where="src")`, which finds nothing — `src/` has no
  `__init__.py`, so `pip install .` against it silently produced an empty
  distribution. `pyproject.toml` is the replacement, and is explicit that this
  project is not meant to be built as a package at all (see above) rather than
  quietly failing to be one.

- `README.md` and `QUICKSTART.md` now lead with the web app, and their install
  instructions lead with `uv sync`.

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
