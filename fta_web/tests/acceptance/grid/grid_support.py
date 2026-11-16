"""Shared helpers of the F3 acceptance tests (``POST /api/grid/paste``).

Nothing here imports an F3 module at import time. The Flask app is a bare one
(the way ``test_analysis_routes.py`` builds it, so the blueprints share this
module's ``AppState``) with the tree and file blueprints and, when it exists,
``fta_web.routes.grid``. Until the grid blueprint exists the endpoint answers
404, and every test that posts a paste fails on that status and on nothing else.
"""
import copy
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"

PASTE_URL = "/api/grid/paste"


def make_app(sandbox):
    """A bare app: tree + file blueprints, the grid blueprint if it exists."""
    flask = pytest.importorskip("flask")
    from fta_web import errors
    from fta_web.routes.files import files_bp
    from fta_web.routes.tree import tree_bp
    from fta_web.state import get_state, reset_state

    reset_state()
    app = flask.Flask(__name__)

    @app.errorhandler(errors.ApiError)
    def _handle(err):  # the real app registers the same handler
        return errors.api_error_response(err)

    app.register_blueprint(tree_bp)
    app.register_blueprint(files_bp)
    try:
        from fta_web.routes.grid import grid_bp
    except ModuleNotFoundError as exc:
        # Only "the grid module is not there yet" is tolerated: the paste URL
        # then answers 404. Any other import error is a real failure.
        if exc.name != "fta_web.routes.grid":
            raise
    else:
        app.register_blueprint(grid_bp)
    app.config.update(TESTING=True)
    get_state().fs_root = Path(sandbox)
    return app


def body(response):
    return json.loads(response.get_data(as_text=True))


def state():
    from fta_web.state import get_state

    return get_state()


def add(client, parent="root", **fields):
    fields.setdefault("name", "Event")
    response = client.post("/api/nodes", json=dict(fields, parentId=parent))
    assert response.status_code == 200, body(response)
    return body(response)["nodeId"]


def stored(node_id):
    return state().core.find_node_by_id(node_id)


def quant_of(node_id):
    return stored(node_id).get("quant") or {}


def tree_copy():
    return copy.deepcopy(state().core.get_data())


def undo_depth():
    return len(state()._undo)


def fields_now(client):
    """``{revision, documentSerial}`` as the grid would have drawn them."""
    payload = body(client.get("/api/revision"))
    return {"revision": payload["revision"], "documentSerial": payload["documentSerial"]}


def build_document(client):
    """The small document most tests paste into. Returns the ids by role."""
    ids = {}
    ids["fixed"] = add(client, name="Alpha fixed", probability=0.1)
    ids["rate"] = add(client, name="Bravo rate", probability=0.5,
                      quant={"model": "rate", "lambda": 1e-4, "T": 100})
    ids["standby"] = add(client, name="Charlie standby", probability=0.5,
                         quant={"model": "standby", "lambda": 1e-4, "tau": 50})
    ids["repairable"] = add(client, name="Delta repairable", probability=0.5,
                            quant={"model": "repairable", "lambda": 1e-4, "mu": 0.5})
    ids["fixed2"] = add(client, name="Echo fixed", probability=0.2)
    ids["gate"] = add(client, name="Gate G", probability=1, logicGate="OR")
    ids["nested"] = add(client, parent=ids["gate"], name="Foxtrot nested", probability=0.3)
    ids["house"] = add(client, name="House H", probability=1, eventKind="house", houseState=True)
    return ids


def paste(client, rows, *, revision=None, serial=None, **extra):
    """POST a paste of ``rows`` with the revision fields of the current document."""
    current = fields_now(client)
    payload = {
        "revision": current["revision"] if revision is None else revision,
        "documentSerial": current["documentSerial"] if serial is None else serial,
        "rows": rows,
    }
    payload.update(extra)
    return client.post(PASTE_URL, json=payload)


def raw_paste(client, raw):
    """POST raw bytes (for the tokens JSON does not have)."""
    return client.post(PASTE_URL, data=raw, content_type="application/json")


def row(clip_row, node_id, **cells):
    return {"clipRow": clip_row, "nodeId": node_id, "cells": cells}


def assert_ok(response):
    assert response.status_code == 200, (response.status_code, response.get_data(as_text=True)[:300])
    payload = body(response)
    assert payload["ok"] is True
    return payload


def assert_error(response, status, code, field=None):
    text = response.get_data(as_text=True)[:300]
    assert response.status_code == status, (response.status_code, text)
    payload = body(response)
    assert payload["ok"] is False, payload
    error = payload["error"]
    assert error["code"] == code, error
    assert isinstance(error["message"], str) and error["message"]
    if field is not None:
        assert error["detail"]["field"] == field, error
    return error


def refusals(payload):
    """``{(clipRow, column): code}`` of a paste answer."""
    return {(item["clipRow"], item["column"]): item["code"] for item in payload["refused"]}
