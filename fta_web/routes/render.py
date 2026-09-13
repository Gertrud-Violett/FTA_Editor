"""
Diagram endpoints -- ``GET /api/dot`` and ``POST /api/render``.

Two renderers, and the user is told which one they got
------------------------------------------------------
``GET /api/dot`` hands the browser DOT source to draw with its bundled
WebAssembly Graphviz. It always works, needs nothing installed, and is what
the live preview uses.

``POST /api/render`` produces a file to save, and needs a native ``dot``. When
there is none it fails **loudly** with 503 ``RENDERER_UNAVAILABLE`` and a
message naming Graphviz and how to install it. It never falls back to
returning the DOT source, or a lower-quality image, or a placeholder: a silent
downgrade is how a user ends up mailing a screenshot-quality PNG to a
regulator believing it came from Graphviz.

Both responses carry ``renderer``, probed at request time rather than read
from the startup capability flags in ``/api/state``. Those flags are a
snapshot: Graphviz can be installed -- or a PATH entry unmounted -- while the
editor sits open, and the field is only worth anything if it describes the
run that just happened.

Why the image comes back base64 in a JSON envelope
--------------------------------------------------
Returning ``image/png`` bytes directly would be leaner, but then ``renderer``
and the error envelope would have to live in headers, and the frontend would
need two response shapes for one endpoint -- differing exactly on the failure
path, where it matters most. One envelope, ``data`` always base64, and the
client builds ``data:<contentType>;base64,<data>`` for both formats.

Error codes
-----------
``errors.py`` owns the vocabulary and has one rendering code,
``RENDERER_UNAVAILABLE``. It covers both "no binary" and "the binary ran and
failed", which are the same thing from the client's point of view -- native
rendering cannot serve this request, use the browser renderer -- and
``detail.reason`` (``not_installed`` / ``render_failed`` / ``timeout``)
separates them for the message the user sees.
"""
from __future__ import annotations

import base64
from typing import Any, Dict

from flask import Blueprint, request

try:  # normal package import: ``import fta_web.routes.render``
    from ..errors import (
        INVALID_FIELD,
        INVALID_JSON,
        RENDERER_UNAVAILABLE,
        ApiError,
        ok_response,
    )
    from ..rendering import (
        RenderError,
        build_dot_text,
        content_type_for,
        describe_renderer,
        render_native,
    )
    from ..state import get_state
except ImportError:  # fallback: ``fta_web/`` itself is on sys.path
    from errors import (  # type: ignore[no-redef]
        INVALID_FIELD,
        INVALID_JSON,
        RENDERER_UNAVAILABLE,
        ApiError,
        ok_response,
    )
    from rendering import (  # type: ignore[no-redef]
        RenderError,
        build_dot_text,
        content_type_for,
        describe_renderer,
        render_native,
    )
    from state import get_state  # type: ignore[no-redef]

render_bp = Blueprint("render", __name__, url_prefix="/api")

VALID_FORMATS = ("svg", "png")

# Accepted spellings for a boolean query parameter. Anything else is a 400
# rather than a silent False: ``?hideZero=treu`` quietly rendering the zero
# nodes back in is precisely the kind of unannounced downgrade this blueprint
# exists to avoid.
_TRUE_STRINGS = frozenset({"1", "true", "yes", "on"})
_FALSE_STRINGS = frozenset({"0", "false", "no", "off", ""})


@render_bp.errorhandler(ApiError)
def _handle_api_error(exc: ApiError):
    # Registered on the blueprint as well as the app (see routes/tree.py) so
    # the blueprint returns the documented envelope wherever it is mounted.
    return exc.to_payload(), exc.status


# ---- request helpers -----------------------------------------------------


def _body() -> Dict[str, Any]:
    """The request's JSON object. An absent body is an empty object."""
    data = request.get_json(silent=True)
    if data is None:
        if not request.get_data():
            return {}
        raise ApiError(INVALID_JSON, "Request body must be a JSON object.", 400)
    if not isinstance(data, dict):
        raise ApiError(INVALID_JSON, "Request body must be a JSON object.", 400)
    return data


def _as_bool(value: Any, field: str, default: bool = False) -> bool:
    """A real boolean, or one of the accepted string spellings."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _TRUE_STRINGS:
            return True
        if text in _FALSE_STRINGS:
            return False
    raise ApiError(
        INVALID_FIELD,
        "'%s' must be a boolean (true/false)." % field,
        400,
        {"field": field, "value": value},
    )


def _validate_format(value: Any) -> str:
    """``svg`` or ``png``. Never interpolated into a command line unchecked."""
    if value is None:
        return "svg"
    if not isinstance(value, str):
        raise ApiError(
            INVALID_FIELD,
            "'format' must be 'svg' or 'png'.",
            400,
            {"field": "format", "value": value},
        )
    fmt = value.strip().lower()
    if fmt not in VALID_FORMATS:
        raise ApiError(
            INVALID_FIELD,
            "'format' must be 'svg' or 'png'.",
            400,
            {"field": "format", "value": value},
        )
    return fmt


def _dot_source(hide_zero: bool) -> str:
    """The current document as DOT, read under the state lock.

    The lock is held for the whole walk, not just for a ``get_data()`` call:
    ``gather_nodes`` traverses the live tree, so a concurrent mutation
    mid-traversal could produce a diagram that never existed.
    """
    state = get_state()
    with state.lock:
        return build_dot_text(state.core, hide_zero=hide_zero)


# ---- endpoints -----------------------------------------------------------


@render_bp.get("/dot")
def get_dot():
    """DOT source for the in-browser renderer.

    ``renderer`` names the best renderer available *right now* -- ``native``
    when a system ``dot`` exists (so ``POST /api/render`` will work), ``wasm``
    otherwise. The DOT returned here is identical either way; the field lets
    the page enable or disable its "export image" affordance without a second
    round trip, and keeps it honest as Graphviz comes and goes.
    """
    hide_zero = _as_bool(request.args.get("hideZero"), "hideZero")
    dot_text = _dot_source(hide_zero)
    renderer, _path = describe_renderer()
    return ok_response(dot=dot_text, renderer=renderer, hideZero=hide_zero)


@render_bp.post("/render")
def post_render():
    """Render the current document natively and return the image bytes.

    Body: ``{"format": "svg"|"png", "hideZero": bool, "highQuality": bool}``.
    All three are optional; the defaults are an SVG of the whole tree at
    normal quality.
    """
    payload = _body()
    fmt = _validate_format(payload.get("format"))
    hide_zero = _as_bool(payload.get("hideZero"), "hideZero")
    high_quality = _as_bool(payload.get("highQuality"), "highQuality")

    dot_text = _dot_source(hide_zero)

    try:
        image = render_native(dot_text, fmt, high_quality=high_quality)
    except RenderError as exc:
        # Covers a missing binary, a non-zero exit, and a timeout. 503 rather
        # than 500: the request is fine, this server just cannot serve it, and
        # the client has a working alternative in the browser renderer.
        detail: Dict[str, Any] = {"reason": exc.reason, "format": fmt, "renderer": "wasm"}
        if exc.stderr:
            # Graphviz' own diagnostic, truncated: it names the offending DOT
            # line, which is the only thing that makes a layout failure
            # actionable.
            detail["stderr"] = exc.stderr[:2000]
        raise ApiError(RENDERER_UNAVAILABLE, str(exc), 503, detail)

    return ok_response(
        format=fmt,
        renderer="native",
        contentType=content_type_for(fmt),
        encoding="base64",
        bytes=len(image),
        hideZero=hide_zero,
        highQuality=high_quality,
        data=base64.b64encode(image).decode("ascii"),
    )
