# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
