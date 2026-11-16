"""
Tests for the fta_web security layer.

The guard is exercised on a bare ``Flask(__name__)`` with one trivial route
rather than on the real application. That keeps these genuine unit tests of
security.py: they cannot be broken (or accidentally satisfied) by whatever the
tree blueprint happens to do, and they run before the rest of the app exists.

Every request goes through ``base_url=BASE_URL`` so the test client sends a
``Host`` header the guard accepts. Werkzeug's default host is a bare
``localhost`` with no port, which the anti-rebinding check correctly rejects --
a silent reminder that the Host check is real.
"""
import sys
from pathlib import Path

import pytest
from flask import Flask, jsonify
from flask import request as flask_request

# fta_web/tests/test_security.py -> [0]=tests, [1]=fta_web
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as app_module  # noqa: E402
import config  # noqa: E402
import errors  # noqa: E402
import security  # noqa: E402

PORT = 8765
BASE_URL = "http://127.0.0.1:%d" % PORT
TOKEN = "test-token-0123456789-abcdefghijklmnopqrstuvwxyz"
HDR = config.TOKEN_HEADER


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def guarded():
    """A minimal app with the security layer installed."""
    flask_app = Flask(__name__)

    @flask_app.route("/api/ping")
    def ping():
        return jsonify({"ok": True, "pong": True})

    @flask_app.route("/api/echo", methods=["POST"])
    def echo():
        return jsonify({"ok": True})

    @flask_app.route("/")
    def index():
        return "<!doctype html><title>page</title>page"

    security.init_app(flask_app, TOKEN, PORT)
    return flask_app


@pytest.fixture
def client(guarded):
    return guarded.test_client()


def get(client, path, token=TOKEN, **kwargs):
    """GET with the session token attached unless told otherwise."""
    headers = dict(kwargs.pop("headers", {}))
    if token is not None:
        headers[HDR] = token
    return client.get(path, base_url=BASE_URL, headers=headers, **kwargs)


def assert_error_envelope(response, expected_code, expected_status):
    """The envelope contract from errors.py, asserted in full."""
    assert response.status_code == expected_status
    assert response.mimetype == "application/json", (
        "error responses must be JSON, got %r" % response.mimetype
    )
    body = response.get_json()
    assert body is not None, "response body was not valid JSON"
    assert body["ok"] is False
    assert set(body.keys()) == {"ok", "error"}
    error = body["error"]
    assert error["code"] == expected_code
    assert isinstance(error["message"], str) and error["message"]
    return body


# ---------------------------------------------------------------------------
# generate_token
# ---------------------------------------------------------------------------
def test_generate_token_is_unpredictable_and_url_safe():
    tokens = {security.generate_token() for _ in range(50)}
    assert len(tokens) == 50, "tokens must not repeat"
    for token in tokens:
        # token_urlsafe(32) -> 32 random bytes, ~43 base64url characters.
        assert len(token) >= 40
        assert all(c.isalnum() or c in "-_" for c in token), (
            "token must survive being placed in a URL query string"
        )


# ---------------------------------------------------------------------------
# token enforcement
# ---------------------------------------------------------------------------
def test_missing_token_is_forbidden_with_error_envelope(client):
    response = get(client, "/api/ping", token=None)
    body = assert_error_envelope(response, errors.FORBIDDEN, 403)
    assert body["error"]["detail"]["reason"] == security.REASON_NO_TOKEN
    assert TOKEN not in response.get_data(as_text=True), (
        "the rejection must never echo the expected token"
    )


def test_empty_token_header_is_forbidden(client):
    response = get(client, "/api/ping", token="")
    assert_error_envelope(response, errors.FORBIDDEN, 403)


def test_wrong_token_is_forbidden(client):
    response = get(client, "/api/ping", token="not-the-token")
    body = assert_error_envelope(response, errors.FORBIDDEN, 403)
    assert body["error"]["detail"]["reason"] == security.REASON_BAD_TOKEN


def test_correct_token_is_accepted(client):
    response = get(client, "/api/ping")
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "pong": True}


def test_token_prefix_is_forbidden(client):
    """A prefix of the real token must not pass.

    This is the test that fails if someone replaces compare_digest with
    ``startswith`` or a truncated comparison.
    """
    for length in (1, 8, len(TOKEN) - 1):
        response = get(client, "/api/ping", token=TOKEN[:length])
        assert response.status_code == 403, (
            "prefix of length %d was accepted" % length
        )


def test_token_with_extra_suffix_is_forbidden(client):
    assert get(client, "/api/ping", token=TOKEN + "x").status_code == 403


def test_non_ascii_token_is_rejected_not_crashed(client):
    """compare_digest raises TypeError on non-ASCII str; we must not 500."""
    response = get(client, "/api/ping", token="tökén-ÿ")
    assert_error_envelope(response, errors.FORBIDDEN, 403)


def test_token_in_query_string_is_not_accepted_for_api(client):
    """The token is a header, never a query parameter, on /api/*.

    A query parameter would be forgeable by any page that could guess or leak
    the URL, and would land in logs and history. Only the bootstrap navigation
    to ``/`` carries it in the URL.
    """
    response = client.get(
        "/api/ping?t=%s" % TOKEN, base_url=BASE_URL
    )
    assert_error_envelope(response, errors.FORBIDDEN, 403)


def test_token_check_applies_to_writes_too(client):
    response = client.post("/api/echo", base_url=BASE_URL)
    assert_error_envelope(response, errors.FORBIDDEN, 403)
    ok = client.post("/api/echo", base_url=BASE_URL, headers={HDR: TOKEN})
    assert ok.status_code == 200


# ---------------------------------------------------------------------------
# origin / host validation (anti-DNS-rebinding)
# ---------------------------------------------------------------------------
def test_foreign_origin_is_forbidden_even_with_valid_token(client):
    response = get(
        client, "/api/ping", headers={"Origin": "https://evil.example"}
    )
    body = assert_error_envelope(response, errors.FORBIDDEN, 403)
    assert body["error"]["detail"]["reason"] == security.REASON_BAD_ORIGIN


def test_null_origin_is_forbidden(client):
    """Sandboxed iframes and file:// pages send Origin: null."""
    response = get(client, "/api/ping", headers={"Origin": "null"})
    assert response.status_code == 403


def test_origin_on_a_different_port_is_forbidden(client):
    response = get(
        client,
        "/api/ping",
        headers={"Origin": "http://127.0.0.1:%d" % (PORT + 1)},
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "origin",
    ["http://127.0.0.1:%d" % PORT, "http://localhost:%d" % PORT],
)
def test_own_origins_are_accepted(client, origin):
    assert get(client, "/api/ping", headers={"Origin": origin}).status_code == 200


def test_absent_origin_is_accepted(client):
    """Browsers omit Origin on same-origin GETs; absence must not be fatal."""
    response = get(client, "/api/ping")
    assert "Origin" not in response.request.headers
    assert response.status_code == 200


def test_foreign_host_is_forbidden_even_with_valid_token(client):
    """The DNS-rebinding case: attacker hostname resolving to 127.0.0.1."""
    response = client.get(
        "/api/ping",
        base_url="http://evil.example:%d" % PORT,
        headers={HDR: TOKEN},
    )
    body = assert_error_envelope(response, errors.FORBIDDEN, 403)
    assert body["error"]["detail"]["reason"] == security.REASON_BAD_HOST


def test_host_on_a_different_port_is_forbidden(client):
    response = client.get(
        "/api/ping",
        base_url="http://127.0.0.1:%d" % (PORT + 1),
        headers={HDR: TOKEN},
    )
    assert response.status_code == 403


def test_localhost_host_is_accepted(client):
    response = client.get(
        "/api/ping",
        base_url="http://localhost:%d" % PORT,
        headers={HDR: TOKEN},
    )
    assert response.status_code == 200


def test_host_comparison_is_case_insensitive(client):
    """Host is case-insensitive per RFC 9110; a legitimate client may shout."""
    response = client.get(
        "/api/ping",
        base_url="http://LOCALHOST:%d" % PORT,
        headers={HDR: TOKEN},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# scope: the page bootstrap
# ---------------------------------------------------------------------------
def test_page_is_reachable_without_a_token(client):
    """GET / must work unauthenticated -- a navigation cannot set a header.

    This is the bootstrap: the token arrives as ?t= and the page moves it into
    sessionStorage.
    """
    response = client.get("/", base_url=BASE_URL)
    assert response.status_code == 200
    assert "page" in response.get_data(as_text=True)


def test_page_is_reachable_with_the_token_in_the_query_string(client):
    response = client.get("/?t=%s" % TOKEN, base_url=BASE_URL)
    assert response.status_code == 200


def test_api_prefix_without_trailing_slash_is_guarded(client):
    """``/api`` itself must not be an unguarded hole beside ``/api/``."""
    assert security._is_api_path("/api") is True
    assert security._is_api_path("/api/tree") is True
    assert security._is_api_path("//api/tree") is True, (
        "duplicated leading slashes must not bypass the guard"
    )
    assert security._is_api_path("/apifoo") is False
    assert security._is_api_path("/") is False


# ---------------------------------------------------------------------------
# response hardening
# ---------------------------------------------------------------------------
def test_security_headers_are_present(client):
    response = client.get("/", base_url=BASE_URL)
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_api_responses_are_not_cached(client):
    response = get(client, "/api/ping")
    assert response.headers["Cache-Control"] == "no-store"


def test_no_cors_headers_are_served(client):
    """Any Access-Control-Allow-* header would undo the origin check."""
    response = get(client, "/api/ping", headers={"Origin": BASE_URL})
    leaked = [h for h in response.headers.keys() if h.lower().startswith("access-control")]
    assert leaked == []


# ---------------------------------------------------------------------------
# init_app refuses to be configured into a fail-open state
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad_token", ["", None, 0])
def test_init_app_rejects_an_empty_token(bad_token):
    with pytest.raises(ValueError):
        security.init_app(Flask(__name__), bad_token, PORT)


@pytest.mark.parametrize("bad_port", [None, 0, -1, 70000, "8765"])
def test_init_app_rejects_a_bad_port(bad_port):
    with pytest.raises(ValueError):
        security.init_app(Flask(__name__), TOKEN, bad_port)


# ---------------------------------------------------------------------------
# create_app: the JSON envelope on Flask's own error paths
# ---------------------------------------------------------------------------
@pytest.fixture
def full_app():
    """The real application, unauthenticated, for the error-handler tests."""
    return app_module.create_app()


def test_unknown_path_returns_json_not_html(full_app):
    response = full_app.test_client().get("/definitely/not/a/route")
    assert_error_envelope(response, app_module.NOT_FOUND, 404)


def test_wrong_method_returns_json_not_html(full_app):
    @full_app.route("/__get_only")
    def _get_only():
        return "ok"

    response = full_app.test_client().post("/__get_only")
    body = assert_error_envelope(response, app_module.METHOD_NOT_ALLOWED, 405)
    assert body["error"]["detail"]["method"] == "POST"


def test_unhandled_exception_returns_json_not_html(full_app):
    @full_app.route("/__boom")
    def _boom():
        raise RuntimeError("kaboom")

    response = full_app.test_client().get("/__boom")
    body = assert_error_envelope(response, app_module.INTERNAL_ERROR, 500)
    assert "kaboom" not in response.get_data(as_text=True), (
        "internal exception text must stay in the log, not the response"
    )
    assert "detail" not in body["error"]


def test_api_error_is_rendered_in_the_envelope(full_app):
    @full_app.route("/__raises")
    def _raises():
        raise errors.ApiError(
            errors.NODE_NOT_FOUND, "no such node", status=404, detail={"id": "N1"}
        )

    response = full_app.test_client().get("/__raises")
    body = assert_error_envelope(response, errors.NODE_NOT_FOUND, 404)
    assert body["error"]["detail"] == {"id": "N1"}


def test_oversized_body_returns_json_not_html(full_app):
    full_app.config["MAX_CONTENT_LENGTH"] = 64

    @full_app.route("/__sink", methods=["POST"])
    def _sink():
        return jsonify({"ok": True, "size": len(flask_request.get_data())})

    response = full_app.test_client().post("/__sink", data=b"x" * 4096)
    assert_error_envelope(response, app_module.PAYLOAD_TOO_LARGE, 413)


# ---------------------------------------------------------------------------
# create_app: configuration invariants
# ---------------------------------------------------------------------------
def test_create_app_sets_the_upload_cap(full_app):
    assert full_app.config["MAX_CONTENT_LENGTH"] == config.MAX_UPLOAD_BYTES


def test_create_app_installs_the_guard_when_given_a_token():
    secured = app_module.create_app(token=TOKEN, port=PORT)
    assert secured.config["FTA_TOKEN"] == TOKEN
    assert secured.config["FTA_PORT"] == PORT
    response = secured.test_client().get("/api/anything", base_url=BASE_URL)
    # 403 (guard fired), never 404: the guard runs before routing decides
    # whether the endpoint exists, so it cannot be used to probe the API
    # surface without a token.
    assert response.status_code == 403


def test_create_app_without_a_token_leaves_the_api_unguarded(full_app):
    """Documents the test-only configuration, so nobody ships it by accident."""
    assert "FTA_TOKEN" not in full_app.config
    assert full_app.test_client().get("/api/nope").status_code == 404


def test_create_app_uses_the_given_fs_root(tmp_path):
    built = app_module.create_app(fs_root=tmp_path)
    assert built.config["FTA_FS_ROOT"] == tmp_path


def test_create_app_defaults_fs_root_to_config(full_app):
    assert full_app.config["FTA_FS_ROOT"] == config.DEFAULT_FS_ROOT


# ---------------------------------------------------------------------------
# single-worker guard
# ---------------------------------------------------------------------------
def test_create_app_refuses_a_multi_worker_launch(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    with pytest.raises(RuntimeError) as excinfo:
        app_module.create_app()
    message = str(excinfo.value)
    assert "single process" in message
    assert "WEB_CONCURRENCY=4" in message, "the message must name what it found"


def test_create_app_refuses_gunicorn(monkeypatch):
    monkeypatch.setenv("SERVER_SOFTWARE", "gunicorn/21.2.0")
    with pytest.raises(RuntimeError) as excinfo:
        app_module.create_app()
    assert "gunicorn" in str(excinfo.value)


def test_single_worker_guard_allows_one_worker(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    assert app_module._detect_multiworker() is None


def test_single_worker_guard_ignores_junk_concurrency(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "not-a-number")
    assert app_module._detect_multiworker() is None


# ---------------------------------------------------------------------------
# run.py wiring
# ---------------------------------------------------------------------------
def test_run_never_offers_a_host_flag():
    """The bind address is not configurable, by design."""
    import run

    args = run.parse_args(["--no-browser"])
    assert not hasattr(args, "host")
    assert args.port is None
    assert args.no_browser is True
    assert config.HOST == "127.0.0.1"


def test_run_picks_a_free_loopback_port():
    import run

    port = run._free_port()
    assert 1024 < port < 65536


def test_run_rejects_a_bad_root(tmp_path):
    import run

    with pytest.raises(SystemExit):
        run._resolve_root(str(tmp_path / "does-not-exist"))
