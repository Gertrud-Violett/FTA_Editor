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


class ApiError(Exception):
    """Raised anywhere in a request to abort with a structured error.

    Registered as a Flask error handler in app.create_app, so route code can
    raise this instead of threading (payload, status) tuples through helpers.
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
