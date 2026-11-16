"""Cross-feature checks of CCF groups (beta factor) and the Grid paste.

A grid paste is a normal node update, so the CCF lint judges its result the
same way as an edit in the Quantification tab: a paste of lambda on one member
of a beta group makes the members differ and the group is not applied; the
same paste on both members keeps it applied. A paste on a file with groups is
still one undo step and leaves the stored groups as they were.
"""
import json

import pytest


def _body(response):
    return json.loads(response.get_data(as_text=True))


@pytest.fixture()
def client(tmp_path):
    flask = pytest.importorskip("flask")
    from fta_web import errors
    from fta_web.routes.ccf import ccf_bp
    from fta_web.routes.files import files_bp
    from fta_web.routes.grid import grid_bp
    from fta_web.routes.tree import tree_bp
    from fta_web.state import get_state, reset_state

    reset_state()
    app = flask.Flask(__name__)

    @app.errorhandler(errors.ApiError)
    def _handle(err):
        return errors.api_error_response(err)

    for blueprint in (tree_bp, files_bp, grid_bp, ccf_bp):
        app.register_blueprint(blueprint)
    app.config.update(TESTING=True)
    get_state().fs_root = tmp_path
    with app.test_client() as test_client:
        yield test_client


def _add(client, **fields):
    response = client.post("/api/nodes", json=dict(fields, parentId="root"))
    assert response.status_code == 200, _body(response)
    return _body(response)["nodeId"]


def _pumps(client):
    """Two identical rate-model pumps under the root and a third event, plus a
    beta group over the two pumps."""
    quant = {"model": "rate", "lambda": 1e-5, "T": 100}
    a = _add(client, name="Pump A", probability=0.5, quant=dict(quant))
    b = _add(client, name="Pump B", probability=0.5, quant=dict(quant))
    c = _add(client, name="Valve C", probability=0.01)
    made = client.post("/api/ccf/groups", json={"name": "Feed pumps", "model": "beta", "beta": 0.1,
                                                "members": [a, b], "source": "test"})
    assert made.status_code == 200, _body(made)
    return a, b, c, _body(made)["group"]["id"]


def _paste(client, rows):
    revision = _body(client.get("/api/revision"))
    response = client.post("/api/grid/paste", json={
        "revision": revision["revision"], "documentSerial": revision["documentSerial"], "rows": rows})
    assert response.status_code == 200, _body(response)
    return _body(response)


def _row(clip_row, node_id, **cells):
    return {"clipRow": clip_row, "nodeId": node_id, "cells": cells}


def _status(client, group_id):
    listing = _body(client.get("/api/ccf/groups"))
    return next(g["status"] for g in listing["groups"] if g["id"] == group_id)


def _stored_groups():
    from fta_web.state import get_state

    return json.loads(json.dumps(get_state().core.analysis.get("ccfGroups")))


def test_a_grid_paste_of_lambda_on_one_member_makes_the_group_not_applied(client):
    a, _b, _c, group_id = _pumps(client)
    assert _status(client, group_id)["applied"] is True
    result = _paste(client, [_row(1, a, **{"lambda": 2e-5})])
    assert result["applied"] == 1 and result["refused"] == []
    status = _status(client, group_id)
    assert status["applied"] is False
    assert status["code"] == "CCF_MEMBERS_DIFFER"


def test_the_same_paste_on_both_members_keeps_the_group_applied(client):
    a, b, _c, group_id = _pumps(client)
    result = _paste(client, [_row(1, a, **{"lambda": 2e-5}), _row(2, b, **{"lambda": 2e-5})])
    assert result["applied"] == 2 and result["refused"] == []
    assert _status(client, group_id)["applied"] is True


def test_a_paste_on_a_file_with_groups_is_one_undo_step_and_keeps_the_groups(client):
    from fta_web.state import get_state

    a, b, c, group_id = _pumps(client)
    groups_before = _stored_groups()
    depth = len(get_state()._undo)
    result = _paste(client, [_row(1, a, **{"lambda": 3e-5}), _row(2, b, **{"lambda": 3e-5}),
                             _row(3, c, q=0.02)])
    assert result["applied"] == 3
    assert len(get_state()._undo) == depth + 1
    assert _stored_groups() == groups_before
    assert client.post("/api/undo").status_code == 200
    assert _stored_groups() == groups_before
    assert _status(client, group_id)["applied"] is True
