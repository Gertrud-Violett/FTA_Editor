"""
Request authentication for the fta_web local server.

THREAT MODEL
============
This server binds to loopback, but "loopback only" is *not* a security
boundary in a browser. Any page on the internet, in any other tab, can issue
requests to ``http://127.0.0.1:<port>``. Since this app exposes filesystem
read/write endpoints, an unauthenticated local server is a remote
file-access hole reachable by a drive-by web page.

Three independent controls close it. All three are required; none of them is
redundant with the others.

1. Loopback binding (``config.HOST``, enforced in run.py)
   Keeps the socket off the LAN. It does NOT stop a browser on this machine
   from reaching us, so on its own it stops nothing that matters here.

2. Per-launch session token (this module)
   ``run.py`` mints ``secrets.token_urlsafe(32)`` per launch and hands it to
   the page in the bootstrap URL. The page echoes it back in the
   ``X-FTA-Token`` header on every ``/api/*`` call. A foreign page cannot
   read the token (it is never in a cookie, never in a DOM another origin can
   reach), so it cannot drive the editor. This is the control that actually
   stops cross-site request forgery against our API.

   The token is also why we need no CSRF token and no cookie session: nothing
   here is ambient authority. A cookie would be attached by the browser to a
   forged cross-site request; a custom header is not.

3. Origin / Host validation (this module)
   THIS IS THE ANTI-DNS-REBINDING CONTROL. DO NOT REMOVE IT AS REDUNDANT.
   An attacker can point a hostname they control (``evil.example``) at
   127.0.0.1 with a short TTL. The victim's browser then treats
   ``http://evil.example:<port>`` as the attacker's *own* origin while the
   packets land on our loopback socket. Loopback binding is defeated: the
   attacker's JavaScript is now same-origin with our server and the browser
   will happily let it read our responses.

   The token still blocks it (the attacker never saw the token), but we
   refuse to depend on a single control for filesystem access. Pinning the
   ``Host`` header to ``127.0.0.1:<port>`` / ``localhost:<port>`` rejects the
   rebound request outright, before any handler runs.

Defense in depth, for the record: a cross-origin ``fetch`` that tries to set
``X-FTA-Token`` triggers a CORS preflight. We serve no CORS headers at all,
so the browser blocks the request before it is ever sent. We still validate
on the server, because a non-browser client has no such scruples.

SCOPE
=====
Enforcement covers ``/api/*`` only. The page itself (``GET /``) and static
assets are reachable without the header, deliberately -- see "BOOTSTRAP".
Serving the page to an unauthenticated (or rebound) caller leaks nothing: the
page is inert HTML/JS until it is given a token, and every operation it can
perform goes through ``/api/*``, which is checked.
"""
import secrets
from typing import Any, Dict, FrozenSet, Optional, Tuple

from flask import Flask, jsonify, request

import config
import errors

# ---------------------------------------------------------------------------
# BOOTSTRAP -- how the token reaches the page, and why GET / is exempt
# ---------------------------------------------------------------------------
# The browser arrives by *navigation* to ``/?t=<token>``. A navigation cannot
# carry a custom header, so the very first request is necessarily
# unauthenticated. The page then copies ``?t=`` into ``sessionStorage`` and
# sends it as ``X-FTA-Token`` from JS afterwards.
#
# Consequences a reviewer should know about:
#
#  * ``GET /`` is NOT gated on the query token, on purpose. Gating it would
#    log the user out of their own app the moment the page strips the token
#    from the URL bar (which it should do, via history.replaceState, so the
#    token stays out of history and out of Referer headers). A reload would
#    then 403. The page is worthless without a token anyway.
#  * The token spends a moment in a URL. That is the weakest link in the
#    scheme: URLs reach browser history and can leak via Referer. We send
#    ``Referrer-Policy: no-referrer`` on every response to close the Referer
#    path; stripping the URL is the page's job.
#  * ``sessionStorage`` is per-tab. A second tab opened at ``/`` with no
#    ``?t=`` has no token and every API call from it will 403. That is
#    correct behaviour, not a bug -- but the frontend must render a clear
#    "relaunch the app" message rather than a wall of 403s.
API_PREFIX = "/api"

#: Reason strings placed in the error ``detail``. They tell an operator which
#: check fired without revealing anything an attacker does not already know
#: (never the expected token, never the expected host).
REASON_NO_TOKEN = "missing_token"
REASON_BAD_TOKEN = "invalid_token"
REASON_BAD_ORIGIN = "origin_not_allowed"
REASON_BAD_HOST = "host_not_allowed"


def generate_token() -> str:
    """Mint a fresh per-launch session token.

    32 bytes from the OS CSPRNG, URL-safe base64 (~43 characters). It lives
    only in this process and in the page's sessionStorage; it is never
    written to disk, so killing the server invalidates it.
    """
    return secrets.token_urlsafe(32)


def _allowed_origins(port: int) -> FrozenSet[str]:
    """Origins a legitimate page can be served from."""
    return frozenset(
        {
            "http://127.0.0.1:%d" % port,
            "http://localhost:%d" % port,
        }
    )


def _allowed_hosts(port: int) -> FrozenSet[str]:
    """``Host`` header values a legitimate request can carry.

    Only these two. Anything else means the request reached us under a name
    we did not publish -- i.e. DNS rebinding.
    """
    return frozenset(
        {
            "127.0.0.1:%d" % port,
            "localhost:%d" % port,
        }
    )


def _is_api_path(path: str) -> bool:
    """True if ``path`` addresses the guarded API surface.

    Leading slashes are collapsed first so ``//api/open`` cannot slip past a
    naive ``startswith`` check. (Werkzeug would answer that with a 308 to the
    canonical path, which is then checked properly, but the guard should not
    depend on routing behaviour to be correct.)
    """
    normalized = "/" + (path or "").lstrip("/")
    return normalized == API_PREFIX or normalized.startswith(API_PREFIX + "/")


def _tokens_match(supplied: str, expected: str) -> bool:
    """Constant-time token comparison.

    ``==`` on strings short-circuits at the first differing byte, which leaks
    the length of the matching prefix to anyone who can time us. Locally that
    is a real oracle, so use ``compare_digest``.

    Compared as UTF-8 bytes rather than str: ``compare_digest`` raises
    TypeError on non-ASCII str, and header values decoded from the wire can
    legitimately contain non-ASCII. Byte comparison makes hostile input a
    plain mismatch instead of a 500.
    """
    return secrets.compare_digest(
        supplied.encode("utf-8", "surrogateescape"),
        expected.encode("utf-8"),
    )


def _forbidden(message: str, reason: str) -> Tuple[Any, int]:
    """Build the standard 403 using the shared envelope from errors.py."""
    err = errors.ApiError(
        errors.FORBIDDEN, message, status=403, detail={"reason": reason}
    )
    return jsonify(err.to_payload()), err.status


def check_request(
    supplied_token: Optional[str],
    origin: Optional[str],
    host: Optional[str],
    expected_token: str,
    port: int,
) -> Optional[Tuple[str, str]]:
    """Pure validation core: return ``(message, reason)`` on rejection, else None.

    Kept free of Flask globals so it can be reasoned about -- and tested --
    on its own.
    """
    # --- Control 3a: Origin -------------------------------------------------
    # Absent Origin is allowed: browsers omit it on same-origin GETs, and
    # non-browser clients (curl) never send it. It is checked when present
    # because a *cross-origin* request always carries it, and "null" (from a
    # sandboxed iframe or a file:// page) is likewise not in the allow-list.
    if origin is not None and origin.strip().lower() not in _allowed_origins(port):
        return ("Request origin is not allowed.", REASON_BAD_ORIGIN)

    # --- Control 3b: Host ---------------------------------------------------
    # Anti-DNS-rebinding. Unlike Origin this is mandatory: every HTTP/1.1
    # request has a Host, so there is no legitimate way to be missing one.
    if not host or host.strip().lower() not in _allowed_hosts(port):
        return ("Request host is not allowed.", REASON_BAD_HOST)

    # --- Control 2: session token ------------------------------------------
    if not supplied_token:
        return ("Missing session token.", REASON_NO_TOKEN)
    if not _tokens_match(supplied_token, expected_token):
        return ("Invalid session token.", REASON_BAD_TOKEN)

    return None


def init_app(app: Flask, token: str, port: int) -> None:
    """Install the token / origin / host guard on ``app``.

    Guards ``/api/*`` only; see the SCOPE and BOOTSTRAP notes above.
    """
    if not isinstance(token, str) or not token:
        # An empty token would make compare_digest("", "") true and open the
        # API to everyone. Refuse loudly instead of failing open.
        raise ValueError("security.init_app requires a non-empty session token")
    if not isinstance(port, int) or not (0 < port < 65536):
        # Without the real port we cannot pin Host/Origin, and a guess would
        # silently disable the anti-rebinding check.
        raise ValueError("security.init_app requires the port the server listens on")

    app.config["FTA_TOKEN"] = token
    app.config["FTA_PORT"] = port

    @app.before_request
    def _guard_api():
        if not _is_api_path(request.path):
            return None  # page + static assets: see BOOTSTRAP
        failure = check_request(
            supplied_token=request.headers.get(config.TOKEN_HEADER),
            origin=request.headers.get("Origin"),
            host=request.host,
            expected_token=token,
            port=port,
        )
        if failure is None:
            return None
        message, reason = failure
        return _forbidden(message, reason)

    @app.after_request
    def _security_headers(response):
        # No referrer anywhere: the bootstrap URL carries the token in its
        # query string, and a Referer header would hand it to any host the
        # page later talks to.
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # We serve JSON and a local page; never let a browser sniff a
        # response into something executable.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        # A hostile page must not be able to frame the editor and drive it by
        # clickjacking. frame-ancestors is the modern spelling; X-Frame-
        # Options covers older engines.
        response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if _is_api_path(request.path):
            # API answers describe live in-memory state and may contain file
            # contents. Keep them out of any cache.
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def describe(port: int) -> Dict[str, Any]:
    """Human-readable summary of the active policy (for logs and diagnostics)."""
    return {
        "host": config.HOST,
        "port": port,
        "token_header": config.TOKEN_HEADER,
        "guarded_prefix": API_PREFIX + "/*",
        "allowed_origins": sorted(_allowed_origins(port)),
        "allowed_hosts": sorted(_allowed_hosts(port)),
    }
