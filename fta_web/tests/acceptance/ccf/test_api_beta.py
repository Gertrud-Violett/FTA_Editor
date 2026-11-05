"""F2 BRIEF criteria 2 and 3 (FN-70 for ``beta``, SPEC 7.5): ``/api/ccf/groups``.

Criterion 2: POST and PATCH read the body with F0's ``read_strict_json`` and
check ``beta`` with ``validate_ccf_beta`` -- a number in [0, 1] is accepted;
``"0.1"``, the tokens NaN and Infinity, ``-0.1`` and ``1.5`` are refused with
the right code and field name; ``-0`` is stored as 0.

Criterion 3: GET, POST, PATCH and DELETE; every change is one undo step and
raises ``revision``.
"""
import json
import math

import pytest

import _ccf_models as M

GROUP_KEYS = {"id", "name", "model", "beta", "alpha", "testing", "members", "source"}
MUTATION_KEYS = {"tree", "zeroNodes", "dirty", "canUndo", "canRedo", "analysis",
                 "sessionWarnings", "revision", "documentSerial"}


def new_group(**over):
    body = {"name": "Feed pumps", "model": "beta", "beta": 0.1, "members": ["A", "B"],
            "source": "test"}
    body.update(over)
    return body


def raw_group(beta_text, **over):
    """The POST body as exact text, with ``beta`` written as ``beta_text``."""
    body = new_group(**over)
    body["beta"] = "@@BETA@@"
    return json.dumps(body).replace('"@@BETA@@"', beta_text)


@pytest.fixture
def plain(api):
    """R1 tree, no groups yet."""
    api.open_doc(M.document(M.r1_tree(), None))
    return api


@pytest.fixture
def one(api):
    """R1 tree with group g1 (A, B) already stored."""
    api.open_doc(M.document(M.r1_tree(), [M.group()]))
    return api


def revision(api):
    status, body = api.get("/api/revision")
    assert status == 200
    return body["revision"]


def stored(api):
    """The groups as stored (the eight keys), without the status."""
    return [{k: g[k] for k in GROUP_KEYS} for g in api.groups()["groups"]]


def error_of(body):
    assert isinstance(body, dict), "no JSON body (is the route missing?)"
    assert body["ok"] is False
    return body["error"]


# ---------------------------------------------------------------- criterion 2

VALID_BETAS = [0.1, 0, 1, 0.0, 1.0, 0.5, 1e-9, 0.999999]


@pytest.mark.parametrize("beta", VALID_BETAS)
def test_post_accepts_a_number_in_0_1(plain, beta):
    status, body = plain.post("/api/ccf/groups", new_group(beta=beta))
    assert status == 200, body
    assert body["group"]["beta"] == beta
    assert stored(plain)[0]["beta"] == beta


@pytest.mark.parametrize("beta", VALID_BETAS)
def test_patch_accepts_a_number_in_0_1(one, beta):
    status, body = one.patch("/api/ccf/groups/g1", {"beta": beta})
    assert status == 200, body
    assert stored(one)[0]["beta"] == beta


@pytest.mark.parametrize("text", ["-0", "-0.0"])
def test_minus_zero_is_stored_as_plain_zero(plain, text):
    status, body = plain.raw("POST", "/api/ccf/groups", raw_group(text))
    assert status == 200, body
    beta = stored(plain)[0]["beta"]
    assert beta == 0 and math.copysign(1.0, beta) == 1.0


def test_patch_stores_minus_zero_as_plain_zero(one):
    status, body = one.raw("PATCH", "/api/ccf/groups/g1", '{"beta": -0}')
    assert status == 200, body
    beta = stored(one)[0]["beta"]
    assert beta == 0 and math.copysign(1.0, beta) == 1.0


#: (JSON text for beta, expected error code)
REFUSED = [
    ('"0.1"', "INVALID_FIELD"),       # a string
    ("true", "INVALID_FIELD"),        # a boolean
    ("null", "INVALID_FIELD"),
    ("[0.1]", "INVALID_FIELD"),
    ("-0.1", "INVALID_FIELD"),        # below 0
    ("1.5", "INVALID_FIELD"),         # above 1
    ("101", "INVALID_FIELD"),
    ("1e999", "INVALID_FIELD"),       # a literal beyond the float range reads as infinity
    ("NaN", "INVALID_JSON"),          # the tokens JSON does not have
    ("Infinity", "INVALID_JSON"),
    ("-Infinity", "INVALID_JSON"),
]


@pytest.mark.parametrize("text, code", REFUSED)
def test_post_refuses_a_bad_beta_with_code_and_field(plain, text, code):
    status, body = plain.raw("POST", "/api/ccf/groups", raw_group(text))
    assert status == 400, body
    err = error_of(body)
    assert err["code"] == code
    if code == "INVALID_FIELD":
        assert err["detail"]["field"] == "beta"
        assert "beta" in err["message"]
    assert stored(plain) == []  # nothing was created


@pytest.mark.parametrize("text, code", REFUSED)
def test_patch_refuses_a_bad_beta_with_code_and_field(one, text, code):
    before = stored(one)
    status, body = one.raw("PATCH", "/api/ccf/groups/g1", '{"beta": %s}' % text)
    assert status == 400, body
    err = error_of(body)
    assert err["code"] == code
    if code == "INVALID_FIELD":
        assert err["detail"]["field"] == "beta"
    assert stored(one) == before


@pytest.mark.parametrize("raw", ["[]", "[0.1]", '"text"', "not json", "", "{'a': 1}", "{"])
def test_a_body_that_is_not_a_json_object_is_invalid_json(one, raw):
    for method, url in (("POST", "/api/ccf/groups"), ("PATCH", "/api/ccf/groups/g1")):
        status, body = one.raw(method, url, raw)
        assert status == 400, (method, raw, body)
        assert error_of(body)["code"] == "INVALID_JSON"


def test_nan_inside_a_string_is_just_text(plain):
    status, body = plain.post("/api/ccf/groups", new_group(name="NaN Infinity pumps"))
    assert status == 200, body
    assert body["group"]["name"] == "NaN Infinity pumps"


# ---------------------------------------------------------------- criterion 3


def test_get_lists_the_stored_groups_with_name_of_members_and_status(one):
    body = one.groups()
    assert body["ok"] is True
    assert body["mode"] == "FTA"
    assert {"revision", "documentSerial"} <= set(body)
    (group,) = body["groups"]
    assert GROUP_KEYS <= set(group) and {"memberNames", "status"} <= set(group)
    assert {k: group[k] for k in GROUP_KEYS} == M.group()
    assert group["memberNames"] == ["Pump A", "Pump B"]
    status = group["status"]
    assert status["applied"] is True and status["code"] is None
    assert status["errors"] == [] and status["warnings"] == []
    block = body["ccf"]
    assert [g["id"] for g in block["applied"]] == ["g1"]
    assert block["notApplied"] == []
    assert block["note"] == M.NOTE_EN


def test_get_on_a_document_without_groups_is_empty(plain):
    assert plain.groups()["groups"] == []


def test_get_returns_a_stored_invalid_group_as_stored_plus_status(api):
    bad = M.group("g1", "Bad beta", ["A", "B"], beta="abc")
    api.open_doc(M.document(M.r1_tree(), [bad]))
    (group,) = api.groups()["groups"]
    assert {k: group[k] for k in GROUP_KEYS} == bad
    assert group["status"]["applied"] is False
    assert group["status"]["code"] == "CCF_BAD_PARAMETER"


def test_post_creates_a_group_and_returns_the_mutation_payload(plain):
    status, body = plain.post("/api/ccf/groups", new_group())
    assert status == 200, body
    assert MUTATION_KEYS <= set(body)
    assert body["group"]["id"] == "g1"
    assert {k: body["group"][k] for k in GROUP_KEYS} == M.group()
    assert [g["id"] for g in body["groups"]] == ["g1"]
    assert [g["id"] for g in body["ccf"]["applied"]] == ["g1"]
    assert body["canUndo"] is True and body["dirty"] is True
    assert body["analysis"]["ccfGroups"] == [M.group()]


def test_group_ids_are_the_smallest_unused_number(plain):
    ids = []
    for index in range(3):
        status, body = plain.post("/api/ccf/groups", new_group(name="Group %d" % index))
        assert status == 200, body
        ids.append(body["group"]["id"])
    assert ids == ["g1", "g2", "g3"]
    assert plain.delete("/api/ccf/groups/g2")[0] == 200
    status, body = plain.post("/api/ccf/groups", new_group(name="Again"))
    assert status == 200 and body["group"]["id"] == "g2"


def test_name_is_sanitized_like_a_node_name_and_source_defaults_to_empty(plain):
    status, body = plain.post("/api/ccf/groups", {
        "name": "  Feed \t  pumps ", "model": "beta", "beta": 0.1, "members": ["A", "B"]})
    assert status == 200, body
    assert body["group"]["name"] == "Feed pumps"
    assert body["group"]["source"] == ""
    status, body = plain.post("/api/ccf/groups", new_group(source=None))
    assert status == 200 and body["group"]["source"] == ""
    assert body["group"]["alpha"] is None and body["group"]["testing"] is None


#: (override of a valid POST body, the field the error names)
BAD_POSTS = [
    ({"name": ""}, "name"),
    ({"name": "   "}, "name"),
    ({"name": None}, "name"),
    ({"name": ["x"]}, "name"),
    ({"name": True}, "name"),
    ({"name": "x" * 4001}, "name"),
    ({"model": "gamma"}, "model"),
    ({"model": 5}, "model"),
    ({"members": "A"}, "members"),
    ({"members": ["A", "A"]}, "members"),
    ({"members": ["A", ""]}, "members"),
    ({"members": ["A", 7]}, "members"),
    ({"members": ["A", "ghost"]}, "members"),
    ({"source": 5}, "source"),
    ({"alpha": [0.9, 0.1]}, "alpha"),
    ({"testing": "staggered"}, "testing"),
    ({"colour": "red"}, "colour"),
    ({"id": "g9"}, "id"),
]


@pytest.mark.parametrize("override, field", BAD_POSTS)
def test_post_refuses_a_bad_field_naming_it(plain, override, field):
    status, body = plain.post("/api/ccf/groups", new_group(**override))
    assert status == 400, body
    err = error_of(body)
    assert err["code"] == "INVALID_FIELD"
    assert field in err["message"] or err.get("detail", {}).get("field") == field
    if field != "colour" and field != "id":
        assert err["detail"]["field"] == field
    assert stored(plain) == []


def test_post_names_the_unknown_member_ids(plain):
    status, body = plain.post("/api/ccf/groups", new_group(members=["A", "ghost", "phantom"]))
    assert status == 400
    detail = error_of(body)["detail"]
    assert detail["field"] == "members"
    assert detail["ids"] == ["ghost", "phantom"]


@pytest.mark.parametrize("key", ["name", "model", "beta", "members"])
def test_post_requires_name_model_beta_and_members(plain, key):
    body = new_group()
    del body[key]
    status, payload = plain.post("/api/ccf/groups", body)
    assert status == 400, payload
    assert error_of(payload)["code"] == "INVALID_FIELD"
    assert error_of(payload)["detail"]["field"] == key


def test_null_alpha_and_testing_are_accepted(plain):
    status, body = plain.post("/api/ccf/groups", new_group(alpha=None, testing=None))
    assert status == 200, body


def test_a_member_in_another_group_or_not_basic_is_accepted_and_flagged(one):
    # B is in g1 already; G1 is a gate. Both are accepted by the API and flagged by lint.
    status, body = one.post("/api/ccf/groups", new_group(name="Second", members=["B", "G1"]))
    assert status == 200, body
    by_id = {g["id"]: g["status"] for g in one.groups()["groups"]}
    assert by_id["g1"]["applied"] is False and by_id["g1"]["code"] == "CCF_MEMBER_IN_TWO_GROUPS"
    assert by_id["g2"]["applied"] is False and by_id["g2"]["code"] == "CCF_MEMBER_NOT_BASIC"


def test_groups_can_be_created_and_edited_in_eta_mode(plain):
    status, body = plain.post("/api/ccf/groups", new_group())
    assert status == 200
    status, body = plain.post("/api/metadata", {"mode": "ETA"})
    assert status == 200, body
    listing = plain.groups()
    assert listing["mode"] == "ETA"
    assert listing["groups"][0]["status"]["code"] == "CCF_ETA_MODE"
    assert [g["code"] for g in listing["ccf"]["notApplied"]] == ["CCF_ETA_MODE"]
    status, body = plain.post("/api/ccf/groups", new_group(name="Another"))
    assert status == 200, body
    assert plain.patch("/api/ccf/groups/g1", {"name": "Renamed"})[0] == 200
    assert plain.delete("/api/ccf/groups/g2")[0] == 200


# ------------------------------------------------ one undo step, revision + 1

ACTIONS = [
    ("post", "POST", "/api/ccf/groups", new_group(name="Second", members=["A", "B"])),
    ("patch_name", "PATCH", "/api/ccf/groups/g1", {"name": "Renamed"}),
    ("patch_beta", "PATCH", "/api/ccf/groups/g1", {"beta": 0.25}),
    ("patch_source", "PATCH", "/api/ccf/groups/g1", {"source": "handbook p. 5"}),
    ("patch_members", "PATCH", "/api/ccf/groups/g1", {"members": ["A", "B", "C"]}),
    ("patch_all", "PATCH", "/api/ccf/groups/g1",
     {"name": "All", "beta": 0.3, "source": "s", "members": ["B", "A"]}),
    ("delete", "DELETE", "/api/ccf/groups/g1", None),
]


@pytest.mark.parametrize("name, method, url, payload", ACTIONS, ids=[a[0] for a in ACTIONS])
def test_each_change_is_one_undo_step_and_raises_the_revision(one, name, method, url, payload):
    before_groups = stored(one)
    before_revision = revision(one)
    status, body = one.call(method, url, **({"json": payload} if payload is not None else {}))
    assert status == 200, body
    after_groups = stored(one)
    assert after_groups != before_groups
    assert revision(one) == before_revision + 1
    assert body["revision"] == before_revision + 1
    assert body["canUndo"] is True and body["dirty"] is True

    status, undone = one.post("/api/undo")  # one step restores the whole previous state
    assert status == 200, undone
    assert stored(one) == before_groups
    assert undone["analysis"].get("ccfGroups") == before_groups
    status, redone = one.post("/api/redo")
    assert status == 200, redone
    assert stored(one) == after_groups
    assert redone["analysis"].get("ccfGroups", []) == after_groups


def test_patch_changes_only_the_fields_sent(one):
    status, body = one.patch("/api/ccf/groups/g1", {"beta": 0.25})
    assert status == 200, body
    group = body["group"]
    assert group["beta"] == 0.25
    assert {k: group[k] for k in GROUP_KEYS - {"beta"}} == {
        k: v for k, v in M.group().items() if k != "beta"}


def test_a_patch_that_changes_nothing_is_not_an_undo_step(plain):
    assert plain.post("/api/ccf/groups", new_group())[0] == 200
    r1 = revision(plain)
    status, body = plain.patch("/api/ccf/groups/g1", {"name": "Feed pumps", "beta": 0.1})
    assert status == 200, body
    assert body["changed"] is False
    assert revision(plain) == r1
    # The only step on the stack is the creation: one undo removes the group.
    assert plain.post("/api/undo")[0] == 200
    assert stored(plain) == []
    assert plain.post("/api/undo")[0] == 400  # nothing left to undo


def test_a_real_patch_reports_changed_true(one):
    status, body = one.patch("/api/ccf/groups/g1", {"beta": 0.4})
    assert status == 200 and body["changed"] is True


def test_patch_with_no_fields_is_invalid(one):
    status, body = one.patch("/api/ccf/groups/g1", {})
    assert status == 400
    err = error_of(body)
    assert err["code"] == "INVALID_FIELD"
    assert err["message"] == "No group fields to update."


def test_patch_refuses_an_unknown_key_or_id_change(one):
    for payload in ({"colour": "red"}, {"id": "g7"}):
        status, body = one.patch("/api/ccf/groups/g1", payload)
        assert status == 400, payload
        assert error_of(body)["code"] == "INVALID_FIELD"
    assert stored(one) == [M.group()]


@pytest.mark.parametrize("model", ["gamma", 5])
def test_patch_refuses_an_unknown_model_naming_it(one, model):
    status, body = one.patch("/api/ccf/groups/g1", {"model": model})
    assert status == 400
    err = error_of(body)
    assert err["code"] == "INVALID_FIELD"
    assert err["detail"]["field"] == "model"
    assert stored(one) == [M.group()]


def test_patch_and_delete_of_an_unknown_group_are_404(one):
    for status, body in (one.patch("/api/ccf/groups/g9", {"name": "x"}),
                         one.delete("/api/ccf/groups/g9")):
        assert status == 404, body
        assert error_of(body)["code"] == "GROUP_NOT_FOUND"
    assert stored(one) == [M.group()]


def test_delete_returns_the_id_and_the_rest_and_the_last_one_removes_the_key(plain):
    plain.post("/api/ccf/groups", new_group(name="One"))
    plain.post("/api/ccf/groups", new_group(name="Two", members=["B", "C"]))
    status, body = plain.delete("/api/ccf/groups/g1")
    assert status == 200, body
    assert body["deletedId"] == "g1"
    assert [g["id"] for g in body["groups"]] == ["g2"]
    assert MUTATION_KEYS <= set(body)
    status, body = plain.delete("/api/ccf/groups/g2")
    assert status == 200
    assert body["groups"] == []
    assert "ccfGroups" not in body["analysis"]  # an empty list is never stored
    assert plain.post("/api/undo")[0] == 200
    assert [g["id"] for g in plain.groups()["groups"]] == ["g2"]


def test_groups_survive_a_change_of_analysis_settings_and_undo(one):
    status, body = one.post("/api/analysis/settings", {"missionTime": 100})
    assert status == 200, body
    assert body["analysis"]["ccfGroups"] == [M.group()]
    assert stored(one) == [M.group()]
    assert one.post("/api/undo")[0] == 200
    assert stored(one) == [M.group()]


def test_the_settings_endpoint_still_refuses_ccf_groups(one):
    status, body = one.post("/api/analysis/settings", {"ccfGroups": []})
    assert status == 400, body
    err = error_of(body)
    assert err["code"] == "INVALID_FIELD"
    assert "Unsupported analysis setting" in err["message"]
    assert stored(one) == [M.group()]


def test_a_new_document_forgets_the_groups(one):
    assert one.post("/api/new", {"force": True})[0] == 200
    assert one.groups()["groups"] == []
