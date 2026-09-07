"""
Configuration and path setup for the fta_web application.

Importing this module puts ``fta_web/core`` on ``sys.path`` so the vendored
modules import under their bare names (``FTA_Editor_core``, ``AI_agent_handler``,
``ai_providers``, ``json_viewer``).

Bare names are mandatory, not stylistic: ``fta_web/core/AI_agent_handler.py``
does ``from ai_providers import AIProviderFactory`` at module level, so
``fta_web.core.*`` package imports would break on that line. Keeping the vendored
files importable exactly as they were at baseline is what lets them stay
byte-identical to ``src/`` -- see fta_web/core/DIVERGENCE.md.
"""
import sys
from pathlib import Path

# fta_web/config.py -> parents[0]=fta_web, [1]=repo root
FTA_WEB_DIR = Path(__file__).resolve().parent
REPO_ROOT = FTA_WEB_DIR.parent
CORE_DIR = FTA_WEB_DIR / "core"
EXAMPLES_DIR = FTA_WEB_DIR / "examples"
STATIC_DIR = FTA_WEB_DIR / "static"
TEMPLATES_DIR = FTA_WEB_DIR / "templates"

if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

# ---- Network -------------------------------------------------------------
# Bound to loopback only, and deliberately not configurable. The filesystem
# endpoints make any other binding a remote-file-access hole.
HOST = "127.0.0.1"

# Header carrying the per-launch session token (see security.py).
TOKEN_HEADER = "X-FTA-Token"

# ---- Limits --------------------------------------------------------------
UNDO_DEPTH = 50
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
AI_TIMEOUT_SECONDS = 120
RENDER_DEBOUNCE_MS = 150

# ---- Filesystem sandbox --------------------------------------------------
DEFAULT_FS_ROOT = Path.home()
ALLOWED_WRITE_EXTENSIONS = {".json", ".xml", ".xlsx", ".png", ".svg"}
ALLOWED_OPEN_EXTENSIONS = {".json"}

# ---- i18n ----------------------------------------------------------------
DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "ja")
