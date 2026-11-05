"""Fixtures of the F2A (CCF groups, alpha factor) acceptance tests.

Same pattern as the F2 folder: every product module is imported inside a fixture
or a test function, never at the top of a test module, so that an alpha part that
does not exist yet fails the tests that need it and does not stop pytest from
collecting the others.

The ``client`` fixture builds a bare Flask app from the blueprints, imported
through the ``fta_web`` package (``create_app()`` imports them by bare name and
would give them a second AppState).
"""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

#: <repo>/fta_web/tests/acceptance/ccf_alpha/conftest.py -> parents[4] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[4]


def _blueprints():
    from fta_web.routes.ai import ai_bp
    from fta_web.routes.analysis import analysis_bp
    from fta_web.routes.ccf import ccf_bp
    from fta_web.routes.files import files_bp
    from fta_web.routes.fmea import fmea_bp
    from fta_web.routes.render import render_bp
    from fta_web.routes.report import report_bp
    from fta_web.routes.tree import tree_bp
    from fta_web.routes.validate import validate_bp

    return [tree_bp, files_bp, render_bp, analysis_bp, validate_bp, report_bp, fmea_bp, ai_bp,
            ccf_bp]


class Api:
    """The Flask test client with JSON in and out, and a document opener."""

    def __init__(self, client, root):
        self.client = client
        self.root = Path(root)

    def call(self, method, url, **kwargs):
        response = self.client.open(url, method=method, **kwargs)
        raw = response.get_data()
        try:
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            body = None
        return response.status_code, body

    def get(self, url, **kwargs):
        return self.call("GET", url, **kwargs)

    def post(self, url, payload=None, **kwargs):
        if payload is not None:
            kwargs["json"] = payload
        return self.call("POST", url, **kwargs)

    def patch(self, url, payload=None, **kwargs):
        if payload is not None:
            kwargs["json"] = payload
        return self.call("PATCH", url, **kwargs)

    def delete(self, url, **kwargs):
        return self.call("DELETE", url, **kwargs)

    def raw(self, method, url, text):
        """A request whose body is the exact text ``text`` (NaN, -0, 1e999 ...)."""
        return self.call(method, url, data=text.encode("utf-8"), content_type="application/json")

    def open_doc(self, doc, name="doc.json"):
        """Write ``doc`` into the sandbox root and open it; the open response."""
        path = self.root / name
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        status, body = self.post("/api/file/open", {"path": str(path), "force": True})
        assert status == 200, body
        return body

    def groups(self):
        status, body = self.get("/api/ccf/groups")
        assert status == 200, (status, body)
        return body

    def binary(self, method, url, **kwargs):
        response = self.client.open(url, method=method, **kwargs)
        return response.status_code, response.get_data()


@pytest.fixture
def client(tmp_path):
    flask = pytest.importorskip("flask")
    from fta_web.state import get_state, reset_state

    reset_state()
    app = flask.Flask(__name__)
    for blueprint in _blueprints():
        app.register_blueprint(blueprint)
    app.config.update(TESTING=True)
    get_state().fs_root = tmp_path
    with app.test_client() as test_client:
        yield test_client
    reset_state()


@pytest.fixture
def api(client, tmp_path):
    return Api(client, tmp_path)


@pytest.fixture(autouse=True)
def _fresh_headline_cache():
    """The diagram remembers the headline of the last document it saw; a test
    that changes how the headline is computed must not meet an earlier one."""
    from fta_web import engine

    cache = getattr(engine, "_headline_cache", None)
    if cache is not None:
        cache[:] = []
    yield
    if cache is not None:
        cache[:] = []


@pytest.fixture
def cli_run(capsys):
    """``cli.main`` in this process: ``(exit code, stdout, stderr)``."""

    def run(*args):
        from fta_web import cli

        code = cli.main([str(a) for a in args])
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return run
