"""F4 BRIEF criterion 6 (FN-58): every factor returns to 1 when the document changes.

The factors live in the browser only (DESIGN D1); the server's part of FN-58 is the
revision check: every request carries ``{revision, documentSerial}`` and a request
for a document version that is no longer the live one answers ``409 STALE_REVISION``
with the current numbers (DESIGN 2.6 / 3.1). The browser resets on that, and on the
change of ``revision`` or ``documentSerial`` it sees in the store.

For every trigger of FN-58 -- New, Open, Import, an example, a mode switch, undo,
redo, a Details edit, a grid paste, and also an analysis-settings change and a CCF
group edit -- this file calls the real route and asserts:

1. the trigger changed ``revision`` or ``documentSerial``;
2. a request for the version before the trigger (also with only the revision or only
   the serial old) answers ``409 STALE_REVISION`` and ``detail`` holds the current numbers;
3. a request for the current version with no factor answers with ``whatIf`` equal (``==``,
   the same float) to ``baseline`` and to the headline of ``/api/analysis/summary``.

A Save is not a trigger (``state.revision_fields``): the saved document is the same one.
Until the route exists each test fails on the 404 of ``POST /api/whatif``.
"""
import io
import json

import pytest

import whatif_support as W

URL = W.URL


def _edit(api):
    api.edit("C", name="Sensor C edited")


def _edit_then_undo(api):
    _edit(api)
    status, body = api.post("/api/undo")
    assert status == 200, body


def t_new(api):
    status, body = api.post("/api/new", {"force": True})
    assert status == 200, body


def t_open_other(api):
    api.open_doc(W.models_doc(), name="other.json")


def t_open_same(api):
    api.open_doc(W.r1_doc())


def t_import(api):
    blob = json.dumps(W.models_doc(), ensure_ascii=False).encode("utf-8")
    response = api.client.post(
        "/api/import/json",
        data={"file": (io.BytesIO(blob), "imported.json"), "force": "true"},
        content_type="multipart/form-data")
    assert response.status_code == 200, response.get_data(as_text=True)[:300]


def t_example(api):
    status, body = api.get("/api/examples")
    assert status == 200 and body["examples"], body
    name = body["examples"][0]["name"]
    status, body = api.post("/api/examples/open", {"name": name, "force": True})
    assert status == 200, body


def t_undo(api):
    status, body = api.post("/api/undo")
    assert status == 200, body


def t_redo(api):
    status, body = api.post("/api/redo")
    assert status == 200, body


def t_details_edit(api):
    api.edit("C", name="Sensor C renamed")


def t_grid_paste(api):
    payload = dict(api.fields(), rows=[{"clipRow": 1, "nodeId": "C", "cells": {"q": 0.002}}])
    status, body = api.post("/api/grid/paste", payload)
    assert status == 200, body


def t_settings(api):
    status, body = api.post("/api/analysis/settings", {"missionTime": 100})
    assert status == 200, body


def t_ccf_group(api):
    status, body = api.patch("/api/ccf/groups/g1", {"beta": 0.2})
    assert status == 200, body


def t_title(api):
    status, body = api.post("/api/metadata", {"title": "Another title"})
    assert status == 200, body


#: name -> (what to do before the version is recorded, the trigger)
CASES = {
    "new": (None, t_new),
    "open_another_file": (None, t_open_other),
    "open_the_same_file_again": (None, t_open_same),
    "import": (None, t_import),
    "example": (None, t_example),
    "undo": (_edit, t_undo),
    "redo": (_edit_then_undo, t_redo),
    "details_edit": (None, t_details_edit),
    "grid_paste": (None, t_grid_paste),
    "analysis_settings": (None, t_settings),
    "ccf_group_edit": (None, t_ccf_group),
    "title_change": (None, t_title),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_a_trigger_makes_the_old_version_stale_and_the_new_one_start_at_the_baseline(api, name):
    prepare, trigger = CASES[name]
    api.open_doc(W.r1_doc())
    if prepare is not None:
        prepare(api)
    before = api.fields()

    # a factor is active on the version before the trigger
    active = api.whatif_ok({"A": 10})
    assert active["whatIf"] != active["baseline"]
    assert active["revision"] == before["revision"]

    trigger(api)

    now = api.fields()
    assert now != before, "the trigger changed neither revision nor documentSerial"

    # (2) the old version, whole or in either half, is stale; detail names the current one
    stale_bodies = [dict(before, factors={"A": 10})]
    if now["revision"] != before["revision"]:
        stale_bodies.append(dict(now, revision=before["revision"], factors={"A": 10}))
    if now["documentSerial"] != before["documentSerial"]:
        stale_bodies.append(dict(now, documentSerial=before["documentSerial"], factors={"A": 10}))
    for body in stale_bodies:
        err = W.assert_error(api.post(URL, body), 409, "STALE_REVISION")
        assert err["detail"]["revision"] == now["revision"]
        assert err["detail"]["documentSerial"] == now["documentSerial"]

    # (3) the current version with no factor: the what-if is the headline, the same float
    fresh = api.whatif_ok({})
    assert fresh["revision"] == now["revision"] and fresh["documentSerial"] == now["documentSerial"]
    assert fresh["events"] == []
    assert fresh["whatIf"] == fresh["baseline"]
    assert fresh["whatIf"] == api.headline()


def test_a_mode_switch_is_a_trigger_and_eta_answers_mode_unsupported_first(api):
    """FTA -> ETA -> FTA. In ETA the endpoint says MODE_UNSUPPORTED (the check comes before the
    stale check, DESIGN 3.1), also for the old version; back in FTA the old version is stale and
    the new one starts at the baseline."""
    api.open_doc(W.r1_doc())
    before = api.fields()
    assert api.whatif_ok({"A": 10})["whatIf"] != api.whatif_ok({})["baseline"]

    status, body = api.post("/api/metadata", {"mode": "ETA"})
    assert status == 200, body
    in_eta = api.fields()
    assert in_eta["revision"] > before["revision"]
    for fields in (before, in_eta):
        err = W.assert_error(api.post(URL, dict(fields, factors={"A": 10})), 409, "MODE_UNSUPPORTED")
        assert err["detail"]["mode"] == "ETA"

    status, body = api.post("/api/metadata", {"mode": "FTA"})
    assert status == 200, body
    back = api.fields()
    assert back["revision"] > in_eta["revision"]
    for fields in (before, in_eta):
        W.assert_error(api.post(URL, dict(fields, factors={"A": 10})), 409, "STALE_REVISION")
    fresh = api.whatif_ok({})
    assert fresh["whatIf"] == fresh["baseline"] == api.headline()


def test_a_save_is_not_a_trigger_the_same_version_still_answers(api):
    """Saving does not raise the revision (state.revision_fields): factors survive a Save,
    and FN-53 proves the saved file is nominal."""
    api.open_doc(W.r1_doc())
    before = api.fields()
    first = api.whatif_ok({"A": 10})
    status, body = api.post("/api/file/save-as", {"path": str(api.root / "saved.json")})
    assert status == 200, body
    assert api.fields() == before
    second = api.whatif_ok({"A": 10})
    assert second["whatIf"] == first["whatIf"]
    assert second["revision"] == before["revision"]


def test_asking_does_not_change_the_version(r1):
    before = r1.fields()
    for _ in range(3):
        r1.whatif_ok({"A": 10})
    assert r1.fields() == before


def test_a_no_op_edit_that_changes_nothing_keeps_the_version(r1):
    """A metadata call that changes nothing is not an undo step and raises no revision, so the
    factors need not reset (the tab compares the numbers, not the calls)."""
    before = r1.fields()
    title = r1.get("/api/state")[1]["metadata"]["title"]
    status, body = r1.post("/api/metadata", {"title": title})
    assert status == 200, body
    assert r1.fields() == before
    assert r1.whatif_ok({"A": 10})["revision"] == before["revision"]


def test_the_version_after_a_trigger_gives_the_documented_answer_for_the_new_document(api):
    """After New the tree is empty: the new version answers 200 with no events and its own
    baseline; the ids of the old document are unknown."""
    api.open_doc(W.r1_doc())
    assert api.post("/api/new", {"force": True})[0] == 200
    body = api.whatif_ok({})
    assert body["events"] == [] and body["groups"] == []
    W.assert_error(api.whatif({"A": 10}), 400, "INVALID_FIELD", field="factors",
                   reason="unknown_event", id="A")
