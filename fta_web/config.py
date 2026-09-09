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

Paths come from ``runtime_paths`` rather than from ``__file__`` so that a frozen
build resolves them against ``sys._MEIPASS`` instead of against a path inside
the archive. The names and their meanings are unchanged in a source checkout.
"""
import sys
from pathlib import Path

try:  # normal package import: ``import fta_web.config``
    from . import runtime_paths
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import runtime_paths  # type: ignore[no-redef]

# Source: the fta_web/ directory. Frozen: sys._MEIPASS, into which
# build/fta_editor.spec unpacks core/, examples/, static/ and templates/ under
# exactly these names.
FTA_WEB_DIR = runtime_paths.resource_root()
#: The checkout root, or -- frozen -- the directory holding the executable.
#: Diagnostics only; never join bundled data onto it.
REPO_ROOT = runtime_paths.app_root()
CORE_DIR = FTA_WEB_DIR / "core"
EXAMPLES_DIR = FTA_WEB_DIR / "examples"
STATIC_DIR = FTA_WEB_DIR / "static"
TEMPLATES_DIR = FTA_WEB_DIR / "templates"

# Frozen builds also compile the four vendored modules into the archive (see
# the hiddenimports in build/fta_editor.spec), so the bare names resolve even
# if this insert finds nothing. Kept unconditional: the shipped core/ directory
# is the source of truth an auditor can hash against BASELINE.json, and the two
# paths must not be allowed to diverge.
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
