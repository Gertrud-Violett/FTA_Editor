"""
Flask application factory for the fta_web editor.

Wires together four things and nothing else:

  * the security layer (security.init_app) -- see security.py for the threat
    model; this module only decides *when* it is installed,
  * the API blueprints (tree, rendering),
  * one uniform JSON error envelope for every failure path, including the
    ones Flask would normally answer with an HTML page,
  * the single-worker guard.

The app is deliberately stateless at module level: everything lives on the
Flask instance returned by create_app, so tests can build as many isolated
apps as they like.
"""
import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

# Support being imported as a bare module (``import app``) no matter how the
# process was started. fta_web has no __init__.py on purpose -- the vendored
# core modules import each other by bare name (see config.py) -- so the
# package directory has to be importable directly.
_FTA_WEB_DIR = str(Path(__file__).resolve().parent)
if _FTA_WEB_DIR not in sys.path:
    sys.path.insert(0, _FTA_WEB_DIR)

from flask import Flask, jsonify, render_template, request  # noqa: E402
from werkzeug.exceptions import HTTPException  # noqa: E402

import config  # noqa: E402  (also puts fta_web/core on sys.path)
import errors  # noqa: E402
import security  # noqa: E402

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTTP-level error codes.
#
# errors.py owns the *domain* vocabulary (NODE_NOT_FOUND, CYCLE_REJECTED, ...).
# These four are transport-level and exist only so that a 404/405/413/500 comes
# back in the same envelope as everything else. If they ever need to be shared
# with route code, promote them into errors.py rather than re-declaring them.
# ---------------------------------------------------------------------------
NOT_FOUND = "NOT_FOUND"
METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
INTERNAL_ERROR = "INTERNAL_ERROR"

_MULTIWORKER_MESSAGE = (
    "fta_web must run as a single process.\n"
    "\n"
    "The whole editor state -- the loaded tree, the undo stack, the current\n"
    "file path -- lives in one in-process object. Under a pre-forking server\n"
    "each worker would get its own private copy, so consecutive requests from\n"
    "the same browser would land on different trees and silently lose edits.\n"
    "There is no shared session store and deliberately so: this is a\n"
    "single-user local tool.\n"
    "\n"
    "Detected: %s\n"
    "Start it with:  python3 fta_web/run.py"
)


def _detect_multiworker() -> Optional[str]:
    """Return a description of a multi-worker launch, or None if we are alone.

    Best-effort by design: it catches the ways this app would realistically be
    mis-deployed (someone reaching for gunicorn because it is a Flask app, or
    a PaaS honouring WEB_CONCURRENCY -- note this repo already carries a
    'Fix session state persistence for Render.com multi-worker environment'
    commit, so this failure mode has bitten the project before).
    """
    reasons = []

    if "gunicorn" in sys.modules or os.environ.get(
        "SERVER_SOFTWARE", ""
    ).lower().startswith("gunicorn"):
        reasons.append("gunicorn")
    if "uwsgi" in sys.modules:
        reasons.append("uWSGI")
    if "mod_wsgi" in sys.modules:
        reasons.append("mod_wsgi")

    raw = os.environ.get("WEB_CONCURRENCY", "").strip()
    if raw:
        try:
            if int(raw) > 1:
                reasons.append("WEB_CONCURRENCY=%s" % raw)
        except ValueError:
            pass

    cmd_args = os.environ.get("GUNICORN_CMD_ARGS", "")
    if "-w" in cmd_args.split() or "--workers" in cmd_args:
        reasons.append("GUNICORN_CMD_ARGS=%r" % cmd_args)

    return ", ".join(reasons) if reasons else None


def _assert_single_worker() -> None:
    """Refuse to start under a pre-forking server.

    Failing loudly at startup is the whole point: a multi-worker launch does
    not crash, it corrupts -- edits vanish into whichever worker answered the
    previous request. A confusing traceback now beats silent data loss later.
    """
    reason = _detect_multiworker()
    if reason is not None:
        raise RuntimeError(_MULTIWORKER_MESSAGE % reason)


def _json_http_error(code: str, message: str, status: int, **detail: Any):
    """Render an HTTP-level failure in the standard envelope."""
    err = errors.ApiError(code, message, status=status, detail=detail or None)
    return jsonify(err.to_payload()), status


def _register_error_handlers(app: Flask) -> None:
    """Make every failure path return ``{"ok": false, "error": {...}}``.

    Flask's defaults return HTML for 404/405/500. The frontend would then have
    to sniff the content type and parse two different shapes on every call, and
    would get it wrong exactly once, in the error path, where it matters most.
    One envelope everywhere is worth the handful of handlers.
    """

    @app.errorhandler(errors.ApiError)
    def _handle_api_error(err: errors.ApiError):
        return err.to_payload(), err.status

    @app.errorhandler(404)
    def _handle_404(err):
        return _json_http_error(
            NOT_FOUND, "No such endpoint.", 404, path=request.path
        )

    @app.errorhandler(405)
    def _handle_405(err):
        return _json_http_error(
            METHOD_NOT_ALLOWED,
            "Method not allowed for this endpoint.",
            405,
            path=request.path,
            method=request.method,
        )

    @app.errorhandler(413)
    def _handle_413(err):
        # The direct consequence of MAX_CONTENT_LENGTH below. Werkzeug would
        # answer with HTML, which would break the envelope contract on the one
        # path a user hits by accident (importing an oversized tree).
        return _json_http_error(
            PAYLOAD_TOO_LARGE,
            "Request body exceeds the %d byte limit."
            % config.MAX_UPLOAD_BYTES,
            413,
            limit_bytes=config.MAX_UPLOAD_BYTES,
        )

    @app.errorhandler(500)
    def _handle_500(err):
        # The message is deliberately generic. Detailed exception text goes to
        # the server log, not to the response body: even locally, a response
        # body can end up pasted into a bug report.
        log.exception("Unhandled error while serving %s", request.path)
        return _json_http_error(
            INTERNAL_ERROR, "Internal server error; see the server log.", 500
        )

    @app.errorhandler(HTTPException)
    def _handle_http_exception(err: HTTPException):
        # Catch-all for the statuses without a bespoke handler above (400, 411,
        # 501, ...) so none of them can slip through as HTML.
        return _json_http_error(
            err.name.upper().replace(" ", "_"),
            err.description or err.name,
            err.code or 500,
        )


def _register_index(app: Flask) -> None:
    """Serve the editor page.

    Placeholder until the frontend phase lands ``templates/index.html``; once
    that file exists this route renders it with no further change. Reachable
    without a token on purpose -- see the BOOTSTRAP note in security.py.
    """

    @app.route("/")
    def index():
        template = Path(app.template_folder) / "index.html"
        if template.is_file():
            return render_template("index.html")
        return (
            "<!doctype html><meta charset=utf-8>"
            "<title>FTA Editor</title>"
            "<h1>FTA Editor backend is running.</h1>"
            "<p>The frontend has not been installed yet "
            "(<code>fta_web/templates/index.html</code> is missing).</p>"
            "<p>The session token arrives in this URL as <code>?t=</code>; "
            "the page will store it in <code>sessionStorage</code> and send it "
            "as the <code>%s</code> header on every API call.</p>"
            % config.TOKEN_HEADER,
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )


def create_app(
    token: str = None,
    port: int = None,
    fs_root: Path = None,
) -> Flask:
    """Build the Flask application.

    Args:
        token: per-launch session token from ``security.generate_token()``.
            When given, the security layer is installed and ``port`` is
            required (Host/Origin cannot be pinned without it). When omitted,
            the app is UNAUTHENTICATED -- only ever do that in tests, never on
            a listening socket.
        port: the port the server will listen on, used to pin Host/Origin.
        fs_root: sandbox root for the filesystem endpoints; defaults to
            ``config.DEFAULT_FS_ROOT``.
    """
    _assert_single_worker()

    app = Flask(
        __name__,
        static_folder=str(config.STATIC_DIR),
        static_url_path="/static",
        template_folder=str(config.TEMPLATES_DIR),
    )

    # Cap request bodies. Without this a single oversized POST is an
    # out-of-memory DoS against a process that holds the user's unsaved work.
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_BYTES
    app.config["FTA_FS_ROOT"] = Path(fs_root) if fs_root else config.DEFAULT_FS_ROOT
    # Keep payload key order as written (Flask 3 API; the old JSON_SORT_KEYS
    # config key is a no-op there).
    if hasattr(app, "json"):
        app.json.sort_keys = False

    _register_error_handlers(app)
    _register_index(app)

    if token:
        security.init_app(app, token, port)
    else:
        log.warning(
            "create_app() called without a token: /api/* is UNAUTHENTICATED. "
            "This is a test-only configuration."
        )

    _register_blueprints(app)
    return app


#: (module, blueprint attribute, what it serves). Each is delivered by its own
#: phase, so each is optional in the same way -- see _register_blueprints.
_BLUEPRINTS = (
    ("routes.tree", "tree_bp", "the tree API"),
    ("routes.render", "render_bp", "the rendering API"),
    ("routes.files", "files_bp", "the file and export API"),
)


def _register_blueprints(app: Flask) -> None:
    """Attach the API blueprints.

    Each blueprint is delivered by a sibling phase. If one is not present yet
    the app still starts -- the security layer, the error envelope and the page
    bootstrap are independently useful and testable -- but that API is absent
    and that is said out loud rather than papered over with a stub. Only the
    specific "routes.<x> is missing" case is tolerated; a genuine import error
    inside a blueprint still propagates.
    """
    for module_name, attribute, description in _BLUEPRINTS:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if (exc.name or "").split(".")[0] != "routes":
                raise
            log.warning(
                "%s not found: %s is not registered. Expected at %s.",
                module_name,
                description,
                Path(_FTA_WEB_DIR) / Path(*module_name.split(".")).with_suffix(".py"),
            )
            continue
        app.register_blueprint(getattr(module, attribute))
