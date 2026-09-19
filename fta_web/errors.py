"""
Uniform response envelopes for the fta_web API.

Every endpoint returns one of two shapes:

    {"ok": true,  ...payload}
    {"ok": false, "error": {"code": "...", "message": "...", "detail": {...}}}

``code`` is a stable machine-readable identifier the frontend can branch on;
``message`` is human-readable and localizable; ``detail`` carries structured
context (offending node id, failing path, validator output) and is omitted when
empty.
"""
from typing import Any, Dict, Optional, Tuple

from flask import jsonify

try:  # normal package import: ``import fta_web.errors``
    from . import i18n
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    import i18n  # type: ignore[no-redef]


class ApiError(Exception):
    """Raised anywhere in a request to abort with a structured error.

    Registered as a Flask error handler in app.create_app and on each
    blueprint, so route code can raise this instead of threading
    (payload, status) tuples through helpers. Every one of those handlers
    must return :func:`api_error_response` so the message is localized.
    """

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        detail: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.detail = detail or {}

    def to_payload(self) -> Dict[str, Any]:
        error: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.detail:
            error["detail"] = self.detail
        return {"ok": False, "error": error}


def api_error_response(exc: ApiError) -> Tuple[Dict[str, Any], int]:
    """The ``(payload, status)`` every ``ApiError`` handler returns.

    One function for the app-level and the blueprint-level handlers: a
    blueprint handler wins over the app's for errors raised in its views, so a
    blueprint that built the payload itself would silently skip localization.
    """
    return i18n.localize_error(exc.to_payload(), i18n.request_language()), exc.status


def error_response(
    code: str,
    message: str,
    status: int = 400,
    detail: Optional[Dict[str, Any]] = None,
) -> Tuple[Any, int]:
    """Build a Flask response for a failure."""
    return jsonify(ApiError(code, message, status, detail).to_payload()), status


def ok_response(**payload: Any) -> Any:
    """Build a Flask response for a success.

    Callers pass the payload as keyword arguments; ``ok: true`` is added here so
    no route has to remember it.
    """
    body: Dict[str, Any] = {"ok": True}
    body.update(payload)
    return jsonify(body)


# ---- Stable error codes --------------------------------------------------
# Kept together so the frontend and the tests share one vocabulary.
NODE_NOT_FOUND = "NODE_NOT_FOUND"
PARENT_NOT_FOUND = "PARENT_NOT_FOUND"
DUPLICATE_NODE_ID = "DUPLICATE_NODE_ID"
ROOT_PROTECTED = "ROOT_PROTECTED"
CYCLE_REJECTED = "CYCLE_REJECTED"
INVALID_FIELD = "INVALID_FIELD"
INVALID_JSON = "INVALID_JSON"
NOTHING_TO_UNDO = "NOTHING_TO_UNDO"
NOTHING_TO_REDO = "NOTHING_TO_REDO"
UNSAVED_CHANGES = "UNSAVED_CHANGES"
FORBIDDEN = "FORBIDDEN"
PATH_REJECTED = "PATH_REJECTED"
NO_CURRENT_PATH = "NO_CURRENT_PATH"
RENDERER_UNAVAILABLE = "RENDERER_UNAVAILABLE"
AI_NOT_CONFIGURED = "AI_NOT_CONFIGURED"
