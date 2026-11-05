"""F2A BRIEF criterion 5 (FN-70 for ``alpha``, SPEC 7.1, 7.5): ``/api/ccf/groups``.

POST and PATCH read the body with ``read_strict_json`` and check ``alpha`` with
``validate_ccf_alpha``: a list of JSON numbers each in [0, 1]. The FN-70 cases:

* a list of numbers (also ``[]``: length and sum are lint, not refusals) is accepted;
* ``"0.1"`` inside the list, a bool, null or a nested list is ``400 INVALID_FIELD`` naming
  ``alpha`` (``detail.index`` is the 0-based position of the first bad item);
* the tokens ``NaN`` and ``Infinity`` are ``400 INVALID_JSON`` (``read_strict_json``);
* ``-0.1``, ``1.5`` and ``1e999`` are ``400 INVALID_FIELD`` naming ``alpha``;
* ``alpha`` that is not a list (number, string, null, object) is ``400 INVALID_FIELD``.

Also ``testing`` (``staggered``, ``nonStaggered`` or null), the model switch, one undo step per
change, ``changed:false``, the file round trip of the SPEC 7.1 example, and the validators as
units.
"""
import json
import math

import pytest

import _alpha_models as M

GROUP_KEYS = {"id", "name", "model", "beta", "alpha", "testing", "members", "source"}
MUTATION_KEYS = {"tree", "zeroNodes", "dirty", "canUndo", "canRedo", "analysis",
                 "sessionWarnings", "revision", "documentSerial"}


def new_group(**over):
    body = {"name": M.GROUP_NAME, "model": "alpha", "alpha": [0.955, 0.034, 0.011],
            "testing": "staggered", "members": ["A", "B", "D"], "source": "test"}
    body.update(over)
    return body


def raw_group(alpha_text, **over):
    """The POST body as exact text with ``alpha`` written as ``alpha_text``."""
    body = new_group(**over)
    body["alpha"] = "@@ALPHA@@"
    return json.dumps(body).replace('"@@ALPHA@@"', alpha_text)


def stored(api):
    return [{k: g[k] for k in GROUP_KEYS} for g in api.groups()["groups"]]


def revision(api):
    status, body = api.get("/api/revision")
    assert status == 200
    return body["revision"]


def error_of(body):
    assert isinstance(body, dict), "no JSON body (is the route missing?)"
    assert body["ok"] is False
    return body["error"]


def tree():
    return M.top([M.gate("G1", "AND", [M.pump(i) for i in "ABCDE"], name="Pumps fail")])


@pytest.fixture
def plain(api):
    api.open_doc(M.document(tree(), None))
    return api


@pytest.fixture
def one(api):
    """A tree with the alpha group g1 (A, B, D) stored."""
    api.open_doc(M.document(tree(), [M.agroup(members=["A", "B", "D"], alpha=M.ALPHA3)]))
    return api


@pytest.fixture
def beta_one(api):
    api.open_doc(M.document(tree(), [M.bgroup(members=["A", "B"])]))
    return api


# ---------------------------------------------------------------- accepted lists

VALID_ALPHAS = [[0.9, 0.1], [0, 1], [1, 0], [0.0, 1.0], [0.955, 0.034, 0.011],
                [0.95, 0.03, 0.01, 0.01], [1e-9, 0.999999999], [0.5], [], [0.3, 0.3, 0.3]]


@pytest.mark.parametrize("alpha", VALID_ALPHAS)
def test_post_accepts_a_list_of_numbers_in_0_1(plain, alpha):
    status, body = plain.post("/api/ccf/groups", new_group(alpha=alpha))
    assert status == 200, body
    assert body["group"]["alpha"] == alpha
    assert body["group"]["beta"] is None
    assert stored(plain)[0]["alpha"] == alpha


@pytest.mark.parametrize("alpha", VALID_ALPHAS)
def test_patch_accepts_a_list_of_numbers_in_0_1(one, alpha):
    status, body = one.patch("/api/ccf/groups/g1", {"alpha": alpha})
    assert status == 200, body
    assert stored(one)[0]["alpha"] == alpha


def test_post_stores_minus_zero_as_plain_zero_inside_the_list(plain):
    status, body = plain.raw("POST", "/api/ccf/groups", raw_group("[-0, 0.5, 0.5]"))
    assert status == 200, body
    first = stored(plain)[0]["alpha"][0]
    assert first == 0 and math.copysign(1.0, first) == 1.0


def test_patch_stores_minus_zero_as_plain_zero_inside_the_list(one):
    status, body = one.raw("PATCH", "/api/ccf/groups/g1", '{"alpha": [-0.0, 0.9, 0.1]}')
    assert status == 200, body
    first = stored(one)[0]["alpha"][0]
    assert first == 0 and math.copysign(1.0, first) == 1.0


# ---------------------------------------------------------------- refused lists

#: (JSON text of alpha, error code, 0-based index of the first bad item or None)
REFUSED = [
    ('["0.1", 0.9]', "INVALID_FIELD", 0),        # a numeric string inside the list
    ('[0.9, "0.1"]', "INVALID_FIELD", 1),
    ("[true, 0.5]", "INVALID_FIELD", 0),         # a bool is not a number
    ("[0.5, null, 0.5]", "INVALID_FIELD", 1),
    ("[[0.1], 0.9]", "INVALID_FIELD", 0),
    ("[-0.1, 1.1]", "INVALID_FIELD", 0),         # below 0
    ("[0.5, 1.5]", "INVALID_FIELD", 1),          # above 1
    ("[1.5, 0]", "INVALID_FIELD", 0),
    ("[0.5, 101, 0.1]", "INVALID_FIELD", 1),
    ("[0.1, 1e999]", "INVALID_FIELD", 1),        # a literal beyond the float range
    ("[NaN, 0.5]", "INVALID_JSON", None),        # the tokens JSON does not have
    ("[0.5, Infinity]", "INVALID_JSON", None),
    ("[-Infinity, 0]", "INVALID_JSON", None),
    ("0.5", "INVALID_FIELD", None),              # not a list
    ('"x"', "INVALID_FIELD", None),
    ('"[0.9, 0.1]"', "INVALID_FIELD", None),
    ("null", "INVALID_FIELD", None),
    ("{}", "INVALID_FIELD", None),
    ('{"0": 0.5}', "INVALID_FIELD", None),
    ("true", "INVALID_FIELD", None),
]


@pytest.mark.parametrize("text, code, index", REFUSED)
def test_post_refuses_a_bad_alpha_with_code_and_field(plain, text, code, index):
    status, body = plain.raw("POST", "/api/ccf/groups", raw_group(text))
    assert status == 400, body
    err = error_of(body)
    assert err["code"] == code
    if code == "INVALID_FIELD":
        assert err["detail"]["field"] == "alpha"
        assert "alpha" in err["message"]
        assert "Unsupported" not in err["message"]   # a value refusal, not "field not known"
        if index is not None:
            assert err["detail"]["index"] == index
            assert "[0, 1]" in err["message"]         # names the field and its range (FN-70)
    assert stored(plain) == []  # nothing was created


@pytest.mark.parametrize("text, code, index", REFUSED)
def test_patch_refuses_a_bad_alpha_with_code_and_field(one, text, code, index):
    before = stored(one)
    status, body = one.raw("PATCH", "/api/ccf/groups/g1", '{"alpha": %s}' % text)
    assert status == 400, body
    err = error_of(body)
    assert err["code"] == code
    if code == "INVALID_FIELD":
        assert err["detail"]["field"] == "alpha"
        assert "Unsupported" not in err["message"]   # a value refusal, not "field not known"
        assert "alpha" in err["message"]
        if index is not None:
            assert err["detail"]["index"] == index
            assert "[0, 1]" in err["message"]         # names the field and its range (FN-70)
    assert stored(one) == before


def test_the_alpha_patch_of_null_is_refused_to_clear_switch_the_model(one):
    status, body = one.patch("/api/ccf/groups/g1", {"alpha": None})
    assert status == 400
    assert error_of(body)["detail"]["field"] == "alpha"
    assert "Unsupported" not in error_of(body)["message"]
    assert stored(one)[0]["alpha"] == list(M.ALPHA3)


def test_length_and_sum_are_lint_not_refusals(plain):
    status, body = plain.post("/api/ccf/groups", new_group(alpha=[0.9, 0.9]))   # 2 values, 3 members
    assert status == 200, body
    (group,) = plain.groups()["groups"]
    assert group["status"]["applied"] is False and group["status"]["code"] == "CCF_ALPHA_SUM"
    status, body = plain.patch("/api/ccf/groups/g1", {"alpha": [0.5, 0.2, 0.1]})   # sum 0.8
    assert status == 200, body
    assert plain.groups()["groups"][0]["status"]["code"] == "CCF_ALPHA_SUM"


# ---------------------------------------------------------------- validator units


def test_validate_ccf_alpha_as_a_unit():
    from fta_web import ccf_schema
    from fta_web.errors import ApiError

    assert ccf_schema.validate_ccf_alpha([0.9, 0.1]) == [0.9, 0.1]
    assert ccf_schema.validate_ccf_alpha([0, 1]) == [0.0, 1.0]
    assert ccf_schema.validate_ccf_alpha([]) == []
    out = ccf_schema.validate_ccf_alpha([-0.0, 0.5])
    assert out[0] == 0 and math.copysign(1.0, out[0]) == 1.0
    for bad in (["0.1"], [True], [None], [[0.1]], [-0.1], [1.5], [float("inf")], [float("nan")],
                0.5, "x", None, {}, (0.5,)):
        with pytest.raises(ApiError) as caught:
            ccf_schema.validate_ccf_alpha(bad)
        assert caught.value.detail["field"] == "alpha", bad
        assert caught.value.code == "INVALID_FIELD"
    with pytest.raises(ApiError) as caught:
        ccf_schema.validate_ccf_alpha([0.5, "x"], field="alpha2")
    assert caught.value.detail["field"] == "alpha2"


def test_validate_ccf_testing_as_a_unit():
    from fta_web import ccf_schema
    from fta_web.errors import ApiError

    assert ccf_schema.validate_ccf_testing(None) is None
    assert ccf_schema.validate_ccf_testing("staggered") == "staggered"
    assert ccf_schema.validate_ccf_testing("nonStaggered") == "nonStaggered"
    for bad in ("non-staggered", "", "Staggered", "weekly", 1, True, [], {}):
        with pytest.raises(ApiError) as caught:
            ccf_schema.validate_ccf_testing(bad)
        assert caught.value.detail["field"] == "testing", bad
        assert "staggered" in caught.value.message


def test_patch_fields_include_alpha_testing_and_model():
    from fta_web import ccf_schema

    assert {"name", "model", "beta", "alpha", "testing", "source", "members"} <= set(
        ccf_schema.PATCH_FIELDS)


# ---------------------------------------------------------------- testing

@pytest.mark.parametrize("testing", ["staggered", "nonStaggered"])
def test_post_accepts_both_schemes(plain, testing):
    status, body = plain.post("/api/ccf/groups", new_group(testing=testing))
    assert status == 200, body
    assert body["group"]["testing"] == testing


def test_post_without_a_scheme_stores_null_and_the_group_is_not_applied(plain):
    body = new_group()
    del body["testing"]
    status, payload = plain.post("/api/ccf/groups", body)
    assert status == 200, payload
    assert payload["group"]["testing"] is None
    assert payload["group"]["status"]["reason"]["en"] == "testing scheme missing"
    (entry,) = payload["ccf"]["notApplied"]
    assert entry["code"] == "CCF_NO_TESTING"
    status, payload = plain.post("/api/ccf/groups", new_group(name="Explicit null", testing=None))
    assert status == 200 and payload["group"]["testing"] is None


@pytest.mark.parametrize("bad", ['"non-staggered"', '""', '"Staggered"', "1", "true", "[]", '"x"'])
def test_post_and_patch_refuse_an_unknown_scheme_naming_testing(plain, bad):
    body = new_group()
    body["testing"] = "@@T@@"
    text = json.dumps(body).replace('"@@T@@"', bad)
    status, payload = plain.raw("POST", "/api/ccf/groups", text)
    assert status == 400, payload
    assert error_of(payload)["code"] == "INVALID_FIELD"
    assert error_of(payload)["detail"]["field"] == "testing"
    assert stored(plain) == []
    assert plain.post("/api/ccf/groups", new_group())[0] == 200
    status, payload = plain.raw("PATCH", "/api/ccf/groups/g1", '{"testing": %s}' % bad)
    assert status == 400, payload
    assert error_of(payload)["detail"]["field"] == "testing"
    assert stored(plain)[0]["testing"] == "staggered"


def test_patch_sets_and_clears_the_scheme(one):
    assert one.patch("/api/ccf/groups/g1", {"testing": "staggered"})[0] == 200
    assert stored(one)[0]["testing"] == "staggered"
    assert one.patch("/api/ccf/groups/g1", {"testing": "nonStaggered"})[0] == 200
    assert stored(one)[0]["testing"] == "nonStaggered"
    assert one.patch("/api/ccf/groups/g1", {"testing": None})[0] == 200
    group = one.groups()["groups"][0]
    assert group["testing"] is None and group["status"]["code"] == "CCF_NO_TESTING"


# ---------------------------------------------------------------- model rules

def test_post_alpha_requires_alpha_and_refuses_beta(plain):
    body = new_group()
    del body["alpha"]
    status, payload = plain.post("/api/ccf/groups", body)
    assert status == 400 and error_of(payload)["detail"]["field"] == "alpha"
    status, payload = plain.post("/api/ccf/groups", new_group(beta=0.1))
    assert status == 400 and error_of(payload)["detail"]["field"] == "beta"
    status, payload = plain.post("/api/ccf/groups", new_group(beta=None))
    assert status == 200, payload
    assert payload["group"]["beta"] is None


def test_post_beta_refuses_alpha_and_testing(plain):
    beta_body = {"name": "Feed pumps", "model": "beta", "beta": 0.1, "members": ["A", "B"]}
    for key, value in (("alpha", [0.9, 0.1]), ("testing", "staggered")):
        status, payload = plain.post("/api/ccf/groups", dict(beta_body, **{key: value}))
        assert status == 400, key
        assert error_of(payload)["detail"]["field"] == key
    status, payload = plain.post("/api/ccf/groups", dict(beta_body, alpha=None, testing=None))
    assert status == 200, payload


def test_post_refuses_an_unknown_model(plain):
    for model in ("gamma", 5, "Alpha", None):
        status, payload = plain.post("/api/ccf/groups", new_group(model=model))
        assert status == 400, model
        assert error_of(payload)["detail"]["field"] == "model"


def test_patch_alpha_on_a_beta_group_without_the_model_is_refused(beta_one):
    status, body = beta_one.patch("/api/ccf/groups/g1", {"alpha": [0.9, 0.1]})
    assert status == 400
    assert error_of(body)["detail"]["field"] == "alpha"
    status, body = beta_one.patch("/api/ccf/groups/g1", {"testing": "staggered"})
    assert status == 400
    assert error_of(body)["detail"]["field"] == "testing"
    assert stored(beta_one) == [M.bgroup(members=["A", "B"])]


def test_patch_beta_on_an_alpha_group_without_the_model_is_refused(one):
    status, body = one.patch("/api/ccf/groups/g1", {"beta": 0.1})
    assert status == 400
    assert error_of(body)["detail"]["field"] == "beta"


def test_switching_a_beta_group_to_alpha_nulls_beta_and_takes_the_new_fields(beta_one):
    status, body = beta_one.patch("/api/ccf/groups/g1", {
        "model": "alpha", "alpha": [0.9, 0.1], "testing": "staggered"})
    assert status == 200, body
    group = stored(beta_one)[0]
    assert group["model"] == "alpha" and group["beta"] is None
    assert group["alpha"] == [0.9, 0.1] and group["testing"] == "staggered"
    assert beta_one.groups()["groups"][0]["status"]["applied"] is True


def test_switching_to_alpha_without_values_leaves_the_group_not_applied(beta_one):
    status, body = beta_one.patch("/api/ccf/groups/g1", {"model": "alpha"})
    assert status == 200, body
    group = stored(beta_one)[0]
    assert group["model"] == "alpha" and group["beta"] is None
    assert group["alpha"] is None and group["testing"] is None
    assert beta_one.groups()["groups"][0]["status"]["applied"] is False


def test_switching_an_alpha_group_to_beta_nulls_alpha_and_testing(one):
    status, body = one.patch("/api/ccf/groups/g1", {"model": "beta", "beta": 0.1})
    assert status == 200, body
    group = stored(one)[0]
    assert group["model"] == "beta" and group["beta"] == 0.1
    assert group["alpha"] is None and group["testing"] is None
    assert one.groups()["groups"][0]["status"]["applied"] is True


def test_a_model_switch_is_one_undo_step_and_undo_restores_every_field(one):
    before = stored(one)
    r0 = revision(one)
    assert one.patch("/api/ccf/groups/g1", {"model": "beta", "beta": 0.2})[0] == 200
    assert revision(one) == r0 + 1
    assert one.post("/api/undo")[0] == 200
    assert stored(one) == before
    assert one.post("/api/redo")[0] == 200
    assert stored(one)[0]["model"] == "beta" and stored(one)[0]["alpha"] is None


def test_patch_with_the_model_it_already_has_is_not_a_switch(one):
    status, body = one.patch("/api/ccf/groups/g1", {"model": "alpha", "alpha": [0.9, 0.05, 0.05]})
    assert status == 200, body
    group = stored(one)[0]
    assert group["alpha"] == [0.9, 0.05, 0.05] and group["testing"] == "staggered"


# ---------------------------------------------------------------- members leave alpha alone (A2)


def test_a_members_patch_never_edits_alpha_and_lint_says_the_length_is_wrong(one):
    before = stored(one)[0]["alpha"]
    status, body = one.patch("/api/ccf/groups/g1", {"members": ["A", "B"]})
    assert status == 200, body
    group = one.groups()["groups"][0]
    assert group["alpha"] == before == list(M.ALPHA3)
    assert group["members"] == ["A", "B"]
    assert group["status"]["applied"] is False and group["status"]["code"] == "CCF_ALPHA_SUM"
    assert group["status"]["reason"]["en"] == M.text_of(
        "CCF_ALPHA_SUM", "length", "en", "reason", n=2, count=3)       # α values: 3, members: 2
    # saving the two values for two members applies it again
    assert one.patch("/api/ccf/groups/g1", {"alpha": [0.9, 0.1]})[0] == 200
    assert one.groups()["groups"][0]["status"]["applied"] is True


def test_five_members_are_accepted_and_flagged_by_lint(one):
    status, body = one.patch("/api/ccf/groups/g1", {"members": ["A", "B", "C", "D", "E"]})
    assert status == 200, body
    assert one.groups()["groups"][0]["status"]["code"] == "CCF_ALPHA_SIZE"


# ---------------------------------------------------------------- GET / POST / PATCH / DELETE shapes


def test_get_lists_an_alpha_group_with_its_eight_keys_names_and_status(one):
    body = one.groups()
    (group,) = body["groups"]
    assert GROUP_KEYS <= set(group) and {"memberNames", "status"} <= set(group)
    assert {k: group[k] for k in GROUP_KEYS} == M.agroup(members=["A", "B", "D"], alpha=M.ALPHA3)
    assert group["memberNames"] == ["Pump A", "Pump B", "Pump D"]
    assert group["status"]["applied"] is True and group["status"]["warnings"] == []
    assert [g["id"] for g in body["ccf"]["applied"]] == ["g1"]


def test_get_shows_the_normalisation_warning_in_the_status(api):
    api.open_doc(M.document(tree(), [M.agroup(members=["A", "B", "D"], alpha=[0.9555, 0.034, 0.011])]))
    (group,) = api.groups()["groups"]
    (warning,) = group["status"]["warnings"]
    assert warning["code"] == "CCF_ALPHA_NORMALISED" and warning["severity"] == "warning"
    assert set(warning["reason"]) == {"en", "ja"} and set(warning["message"]) == {"en", "ja"}
    assert group["status"]["applied"] is True


def test_post_creates_an_alpha_group_and_returns_the_mutation_payload(plain):
    status, body = plain.post("/api/ccf/groups", new_group())
    assert status == 200, body
    assert MUTATION_KEYS <= set(body)
    assert body["group"]["id"] == "g1"
    assert {k: body["group"][k] for k in GROUP_KEYS} == M.agroup(
        members=["A", "B", "D"], alpha=M.ALPHA3)
    assert [g["id"] for g in body["groups"]] == ["g1"]
    assert body["analysis"]["ccfGroups"] == [M.agroup(members=["A", "B", "D"], alpha=M.ALPHA3)]
    assert body["canUndo"] is True and body["dirty"] is True


def test_the_analysis_block_of_an_alpha_group_carries_alpha_testing_and_sum(api):
    api.open_doc(M.document(tree(), [M.agroup(members=["A", "B", "D"], alpha=[0.9555, 0.034, 0.011])]))
    status, summary = api.get("/api/analysis/summary")
    assert status == 200, summary
    (item,) = summary["ccf"]["applied"]
    assert item["id"] == "g1" and item["model"] == "alpha"
    assert item["alpha"] == [0.9555, 0.034, 0.011] and item["testing"] == "staggered"
    assert item["alphaSum"] == pytest.approx(1.0005, rel=1e-12, abs=0.0)
    assert item["alphaNormalised"] is True
    assert item["beta"] is None


ACTIONS = [
    ("post", "POST", "/api/ccf/groups", new_group(name="Second", members=["A", "B"],
                                                   alpha=[0.9, 0.1])),
    ("patch_alpha", "PATCH", "/api/ccf/groups/g1", {"alpha": [0.9, 0.05, 0.05]}),
    ("patch_testing", "PATCH", "/api/ccf/groups/g1", {"testing": "nonStaggered"}),
    ("patch_testing_null", "PATCH", "/api/ccf/groups/g1", {"testing": None}),
    ("patch_name", "PATCH", "/api/ccf/groups/g1", {"name": "Renamed"}),
    ("patch_members", "PATCH", "/api/ccf/groups/g1", {"members": ["A", "B", "E"]}),
    ("patch_all", "PATCH", "/api/ccf/groups/g1",
     {"name": "All", "alpha": [0.8, 0.1, 0.1], "testing": "nonStaggered", "source": "s"}),
    ("delete", "DELETE", "/api/ccf/groups/g1", None),
]


@pytest.mark.parametrize("name, method, url, payload", ACTIONS, ids=[a[0] for a in ACTIONS])
def test_each_change_is_one_undo_step_and_raises_the_revision(one, name, method, url, payload):
    before = stored(one)
    r0 = revision(one)
    status, body = one.call(method, url, **({"json": payload} if payload is not None else {}))
    assert status == 200, body
    after = stored(one)
    assert after != before
    assert revision(one) == r0 + 1 and body["revision"] == r0 + 1
    assert one.post("/api/undo")[0] == 200
    assert stored(one) == before
    assert one.post("/api/redo")[0] == 200
    assert stored(one) == after


def test_a_patch_that_changes_nothing_is_not_an_undo_step(one):
    r0 = revision(one)
    status, body = one.patch("/api/ccf/groups/g1", {"alpha": list(M.ALPHA3), "testing": "staggered"})
    assert status == 200, body
    assert body["changed"] is False
    assert revision(one) == r0
    status, body = one.patch("/api/ccf/groups/g1", {"alpha": [0.9, 0.05, 0.05]})
    assert status == 200 and body["changed"] is True


def test_delete_of_an_alpha_group_and_the_last_one_removes_the_key(one):
    status, body = one.delete("/api/ccf/groups/g1")
    assert status == 200 and body["deletedId"] == "g1"
    assert "ccfGroups" not in body["analysis"]
    assert one.post("/api/undo")[0] == 200
    assert stored(one)[0]["alpha"] == list(M.ALPHA3)


def test_patch_of_an_unknown_group_is_404(one):
    status, body = one.patch("/api/ccf/groups/g9", {"alpha": [0.9, 0.1]})
    assert status == 404 and error_of(body)["code"] == "GROUP_NOT_FOUND"


def test_a_stored_invalid_alpha_group_is_returned_as_stored(api):
    bad = M.agroup(members=["A", "B", "D"], alpha=[0.5, "0.3", 0.2], testing="weekly")
    api.open_doc(M.document(tree(), [bad]))
    (group,) = api.groups()["groups"]
    assert {k: group[k] for k in GROUP_KEYS} == bad
    assert group["status"]["applied"] is False


# ---------------------------------------------------------------- the file (SPEC 7.1)


def spec_7_1_groups():
    return [
        {"id": "g1", "name": "Feed pumps", "model": "beta", "beta": 0.1, "alpha": None,
         "testing": None, "members": ["A", "B"], "source": "free text, e.g. data handbook and page"},
        {"id": "g2", "name": "Relief valves", "model": "alpha", "beta": None,
         "alpha": [0.955, 0.034, 0.011], "testing": "staggered",
         "members": ["C", "D", "E"], "source": "..."},
    ]


def test_the_spec_7_1_example_loads_saves_and_round_trips_equal(tmp_path):
    from fta_web import engine

    groups = spec_7_1_groups()
    doc = M.document(M.top([M.pump(i) for i in "ABCDE"]),
                     groups)
    path = M.write_doc(tmp_path, doc, "spec71.json")
    core = engine.WebCore()
    ok, error = core.load_from_json(str(path))
    assert ok, error
    assert core.analysis["ccfGroups"] == groups          # verbatim, nothing coerced
    assert not [w for w in core.last_load_warnings if w.get("kind") == "analysis_invalid"]
    out = tmp_path / "saved.json"
    ok, error = core.save_to_json(str(out))
    assert ok, error
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["analysis"]["ccfGroups"] == groups
    assert saved["fileFormatVersion"] == 2
    # a second round gives the same bytes of the groups
    again = engine.WebCore()
    assert again.load_from_json(str(out))[0]
    assert again.analysis["ccfGroups"] == groups


def test_an_alpha_group_of_a_file_is_kept_verbatim_with_an_unknown_scheme_and_a_stray_beta(api):
    stray = M.agroup(members=["A", "B", "D"], alpha=[0.9, 0.05, 0.05], testing="non-staggered",
                     beta=0.3)
    body = api.open_doc(M.document(tree(), [stray]))
    assert body["analysis"]["ccfGroups"] == [stray]
    (group,) = api.groups()["groups"]
    assert {k: group[k] for k in GROUP_KEYS} == stray
    assert group["status"]["code"] == "CCF_NO_TESTING"


def test_a_beta_group_with_stray_alpha_values_is_kept_and_they_are_ignored(api):
    stray = M.bgroup(members=["A", "B"], alpha=[0.5, 0.5], testing="staggered")
    api.open_doc(M.document(tree(), [stray]))
    (group,) = api.groups()["groups"]
    assert {k: group[k] for k in GROUP_KEYS} == stray
    assert group["status"]["applied"] is True and group["status"]["warnings"] == []
