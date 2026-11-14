"""F2A BRIEF criterion 4 (FN-43): the alpha lint.

One test per code and kind, on the two public surfaces F2 uses: ``GET /api/ccf/groups`` (the CCF
tab's status) and ``GET /api/analysis/validate`` (the Validation tab):

* ``CCF_ALPHA_SIZE`` (error): fewer than 2 or more than 4 members;
* ``CCF_ALPHA_SUM`` (error): an alpha_k not finite in [0, 1] (kind ``range``), the list length not
  m (``length``), |sum - 1| > 1e-3 (``sum``);
* ``CCF_ALPHA_NORMALISED`` (warning, group applied): 1e-9 < |sum - 1| <= 1e-3, each alpha divided
  by the sum, the note shows the original sum;
* ``CCF_NO_TESTING`` (error): the testing scheme is missing (``missing``: null, absent or the
  empty string) or not recognised (``unknown``, for example ``"non-staggered"``).

Boundaries: |sum - 1| <= 1e-3 is inside the normalisation band (0.9991, 1.0009, 0.99901, 1.00099);
outside are 0.99899, 1.00101, 0.9985 (1.5e-3 off) and 1.0015. An alpha set copied from S1 Table 6-9
p. 104 is applied (DESIGN 8).
"""
import pytest

import _alpha_models as M

IDS3 = ["A", "B", "D"]
MEMBERS3 = "Pump A, Pump B, Pump D"
ALPHA_OK = (0.955, 0.034, 0.011)


def doc_for(members=IDS3, alpha=ALPHA_OK, testing="staggered", mode="FTA", extra_ids=(), **over):
    ids = list(dict.fromkeys(list(members) + list(extra_ids)))
    tree = M.and_tree(ids)
    return M.document(tree, [M.agroup(members=members, alpha=alpha, testing=testing, **over)],
                      mode=mode)


def case(case_id, doc, code, kind, applied, errors, **params):
    return {"id": case_id, "doc": doc, "code": code, "kind": kind, "applied": applied,
            "errors": errors, "params": params}


def lint_cases():
    cases = []
    # CCF_ALPHA_SIZE
    five = ["A", "B", "C", "D", "E"]
    cases.append(case("SIZE_five", doc_for(five, (0.9, 0.04, 0.03, 0.02, 0.01)),
                      "CCF_ALPHA_SIZE", "", False, ["CCF_ALPHA_SIZE"], n=5))
    # one member: TOO_FEW_MEMBERS stays primary, SIZE is also listed
    cases.append(case("SIZE_one", doc_for(["A"], (1.0,), extra_ids=["B"]),
                      "CCF_TOO_FEW_MEMBERS", "one", False,
                      ["CCF_TOO_FEW_MEMBERS", "CCF_ALPHA_SIZE"], n=1))
    # CCF_ALPHA_SUM, kind length
    cases.append(case("SUM_length_short", doc_for(alpha=(0.9, 0.1)), "CCF_ALPHA_SUM", "length",
                      False, ["CCF_ALPHA_SUM"], n=3, count=2))
    cases.append(case("SUM_length_long", doc_for(["A", "B"], (0.5, 0.3, 0.2)), "CCF_ALPHA_SUM",
                      "length", False, ["CCF_ALPHA_SUM"], n=2, count=3))
    cases.append(case("SUM_length_null", doc_for(alpha=None), "CCF_ALPHA_SUM", "length", False,
                      ["CCF_ALPHA_SUM"], n=3, count=0))
    # kind range (first bad position k, 1-based)
    cases.append(case("SUM_range_string", doc_for(alpha=[0.5, "0.3", 0.2]), "CCF_ALPHA_SUM",
                      "range", False, ["CCF_ALPHA_SUM"], k=2))
    cases.append(case("SUM_range_negative", doc_for(alpha=[0.6, -0.1, 0.5]), "CCF_ALPHA_SUM",
                      "range", False, ["CCF_ALPHA_SUM"], k=2))
    cases.append(case("SUM_range_above_one", doc_for(alpha=[0.5, 0.5, 1.5]), "CCF_ALPHA_SUM",
                      "range", False, ["CCF_ALPHA_SUM"], k=3))
    cases.append(case("SUM_range_bool", doc_for(alpha=[0.5, True, 0.5]), "CCF_ALPHA_SUM",
                      "range", False, ["CCF_ALPHA_SUM"], k=2))
    cases.append(case("SUM_range_null", doc_for(alpha=[0.5, None, 0.5]), "CCF_ALPHA_SUM",
                      "range", False, ["CCF_ALPHA_SUM"], k=2))
    cases.append(case("SUM_range_nan", doc_for(alpha=[0.5, float("nan"), 0.5]), "CCF_ALPHA_SUM",
                      "range", False, ["CCF_ALPHA_SUM"], k=2))
    # kind sum (|sum - 1| > 1e-3)
    cases.append(case("SUM_sum_1p1", doc_for(alpha=(0.9, 0.1, 0.1)), "CCF_ALPHA_SUM", "sum",
                      False, ["CCF_ALPHA_SUM"], sum="1.1"))
    cases.append(case("SUM_sum_0p998", doc_for(alpha=(0.9, 0.05, 0.048)), "CCF_ALPHA_SUM", "sum",
                      False, ["CCF_ALPHA_SUM"], sum="0.998"))
    cases.append(case("SUM_sum_0p9985", doc_for(alpha=(0.9, 0.05, 0.0485)), "CCF_ALPHA_SUM",
                      "sum", False, ["CCF_ALPHA_SUM"], sum="0.9985"))
    cases.append(case("SUM_sum_1p0015", doc_for(alpha=(0.9, 0.05, 0.0515)), "CCF_ALPHA_SUM",
                      "sum", False, ["CCF_ALPHA_SUM"], sum="1.0015"))
    # CCF_ALPHA_NORMALISED (warning; the group stays applied)
    cases.append(case("NORMALISED_1p0005", doc_for(alpha=(0.9555, 0.034, 0.011)),
                      "CCF_ALPHA_NORMALISED", "", True, [], sum="1.0005"))
    cases.append(case("NORMALISED_0p9991", doc_for(alpha=(0.9, 0.05, 0.0491)),
                      "CCF_ALPHA_NORMALISED", "", True, [], sum="0.9991"))
    cases.append(case("NORMALISED_1p0009", doc_for(alpha=(0.9, 0.05, 0.0509)),
                      "CCF_ALPHA_NORMALISED", "", True, [], sum="1.0009"))
    cases.append(case("NORMALISED_2e-9", doc_for(alpha=(0.955, 0.034, 0.011 + 2e-9)),
                      "CCF_ALPHA_NORMALISED", "", True, [], sum="1.000000002"))
    # S1 Table 6-9 p. 104 (m = 4), both columns
    members4 = ["A", "B", "C", "D"]
    for name, alpha, values_sum in M.TABLE_6_9:
        for scheme in ("staggered", "nonStaggered"):
            cases.append(case("TABLE_6_9_%s_%s" % (name, scheme),
                              doc_for(members4, alpha, scheme),
                              "CCF_ALPHA_NORMALISED", "", True, [], sum=values_sum))
    # CCF_NO_TESTING
    cases.append(case("NO_TESTING_missing", doc_for(testing=None), "CCF_NO_TESTING", "missing",
                      False, ["CCF_NO_TESTING"]))
    cases.append(case("NO_TESTING_unknown_hyphen", doc_for(testing="non-staggered"),
                      "CCF_NO_TESTING", "unknown", False, ["CCF_NO_TESTING"],
                      testing="non-staggered"))
    # a stored group whose `testing` key is absent (an older or hand-made file): kind missing
    absent = doc_for()
    del absent["analysis"]["ccfGroups"][0]["testing"]
    assert "testing" not in absent["analysis"]["ccfGroups"][0]
    cases.append(case("NO_TESTING_absent", absent, "CCF_NO_TESTING", "missing", False,
                      ["CCF_NO_TESTING"]))
    # the empty string is "nothing chosen" (DESIGN 4.1), not an unknown scheme
    cases.append(case("NO_TESTING_empty_is_missing", doc_for(testing=""), "CCF_NO_TESTING",
                      "missing", False, ["CCF_NO_TESTING"]))
    # several errors: all listed, SUM before NO_TESTING
    cases.append(case("SUM_and_NO_TESTING", doc_for(alpha=(0.9, 0.1), testing=None),
                      "CCF_ALPHA_SUM", "length", False, ["CCF_ALPHA_SUM", "CCF_NO_TESTING"],
                      n=3, count=2))
    return cases


CASES = lint_cases()
IDS = [c["id"] for c in CASES]


def ccf_issues(api):
    status, body = api.get("/api/analysis/validate")
    assert status == 200, body
    return [i for i in body["issues"] if str(i["code"]).startswith("CCF_")]


@pytest.mark.parametrize("code, severity", [
    ("CCF_ALPHA_SIZE", "error"), ("CCF_ALPHA_SUM", "error"),
    ("CCF_ALPHA_NORMALISED", "warning"), ("CCF_NO_TESTING", "error")])
def test_lint_knows_the_severity_of_each_alpha_code(code, severity):
    from fta_web import lint

    assert lint.SEVERITY[code] == severity


def test_the_cases_cover_every_code_and_kind_of_fn_43():
    seen = {(c["code"], c["kind"]) for c in CASES}
    for pair in [("CCF_ALPHA_SIZE", ""), ("CCF_ALPHA_SUM", "length"), ("CCF_ALPHA_SUM", "range"),
                 ("CCF_ALPHA_SUM", "sum"), ("CCF_ALPHA_NORMALISED", ""),
                 ("CCF_NO_TESTING", "missing"), ("CCF_NO_TESTING", "unknown")]:
        assert pair in seen, pair


@pytest.mark.parametrize("c", CASES, ids=IDS)
def test_status_of_each_alpha_finding(api, c):
    api.open_doc(c["doc"])
    listing = api.groups()
    (group,) = listing["groups"]
    status = group["status"]
    assert status["applied"] is c["applied"]
    if c["applied"]:
        assert status["code"] is None and status["errors"] == []
        (warning,) = [w for w in status["warnings"] if w["code"] == c["code"]]
        assert warning["severity"] == "warning"
        assert c["params"]["sum"] in warning["reason"]["en"]      # the note shows the original sum
        assert c["params"]["sum"] in warning["message"]["en"]
        assert c["params"]["sum"] in warning["reason"]["ja"]
        assert [g["id"] for g in listing["ccf"]["applied"]] == ["g1"]
        assert listing["ccf"]["notApplied"] == []
    else:
        assert status["code"] == c["code"] and status["severity"] == "error"
        assert [e["code"] for e in status["errors"]] == c["errors"]
        (entry,) = listing["ccf"]["notApplied"]
        assert entry["id"] == "g1" and entry["code"] == c["code"]
        assert entry["reason"] == status["reason"]["en"]
        assert status["reason"]["en"] != status["reason"]["ja"]


@pytest.mark.parametrize("c", CASES, ids=IDS)
def test_validation_issue_of_each_alpha_finding(api, c):
    api.open_doc(c["doc"])
    issues = ccf_issues(api)
    found = [i for i in issues if i["code"] == c["code"]]
    assert len(found) == 1, issues
    issue = found[0]
    assert issue["severity"] == ("warning" if c["applied"] else "error")
    assert issue["nodeId"] is None
    assert issue["params"]["groupId"] == "g1" and issue["params"]["group"] == M.GROUP_NAME
    text = issue["params"]["text"]
    for lang in ("en", "ja"):
        assert text[lang]["reason"] and text[lang]["message"] and text[lang]["fix"]
    assert M.GROUP_NAME in issue["message"]
    if c["applied"]:
        assert c["params"]["sum"] in text["en"]["message"]
    for error_code in c["errors"]:
        assert error_code in {i["code"] for i in issues}


@pytest.mark.parametrize("c", CASES, ids=IDS)
def test_lint_run_issue_of_each_alpha_finding_carries_the_hint_key(c):
    """``GET /api/analysis/validate`` keeps the frozen five keys; ``lint.run`` (report, CLI) adds
    ``hintKey`` = ``val.fix.<CODE>`` (as F2's test for CCF_MEMBERS_DIFFER)."""
    from fta_web import lint

    doc = c["doc"]
    issues = [i for i in lint.run(doc["tree"], doc["analysis"], [], mode="FTA")
              if i["code"] == c["code"]]
    assert len(issues) == 1, issues
    assert issues[0]["hintKey"] == "val.fix." + c["code"]
    assert issues[0]["severity"] == ("warning" if c["applied"] else "error")


# --------------------------------------------------------------- one test per code


def test_alpha_size_for_five_members(api):
    api.open_doc(doc_for(["A", "B", "C", "D", "E"], (0.9, 0.04, 0.03, 0.02, 0.01)))
    (group,) = api.groups()["groups"]
    assert group["status"]["code"] == "CCF_ALPHA_SIZE"
    assert [e["code"] for e in group["status"]["errors"]] == ["CCF_ALPHA_SIZE"]  # SUM not evaluated
    assert group["status"]["applied"] is False


def test_alpha_size_for_one_member_also_lists_too_few_members_first(api):
    api.open_doc(doc_for(["A"], (1.0,), extra_ids=["B"]))
    (group,) = api.groups()["groups"]
    assert group["status"]["code"] == "CCF_TOO_FEW_MEMBERS"
    assert [e["code"] for e in group["status"]["errors"]] == [
        "CCF_TOO_FEW_MEMBERS", "CCF_ALPHA_SIZE"]


def test_alpha_size_also_fires_for_a_group_without_members(api):
    api.open_doc(M.document(M.and_tree(["A", "B"]), [M.agroup(members=[], alpha=[])]))
    (group,) = api.groups()["groups"]
    codes = [e["code"] for e in group["status"]["errors"]]
    assert "CCF_ALPHA_SIZE" in codes and codes[0] == "CCF_TOO_FEW_MEMBERS"


@pytest.mark.parametrize("members, alpha", [
    (["A", "B"], (0.9, 0.1)), (["A", "B", "D"], ALPHA_OK),
    (["A", "B", "C", "D"], (0.95, 0.03, 0.01, 0.01))])
@pytest.mark.parametrize("testing", ["staggered", "nonStaggered"])
def test_a_group_of_two_to_four_with_a_good_set_raises_nothing(api, members, alpha, testing):
    api.open_doc(doc_for(members, alpha, testing))
    (group,) = api.groups()["groups"]
    assert group["status"]["applied"] is True
    assert group["status"]["errors"] == [] and group["status"]["warnings"] == []
    assert ccf_issues(api) == []
    assert [g["id"] for g in api.groups()["ccf"]["applied"]] == ["g1"]


def test_alpha_sum_boundary_inside_is_a_warning_outside_is_an_error(api):
    # the 1e-3 threshold pinned from both sides (FN-43: |sum - 1| <= 1e-3 is a warning)
    for alpha, code in [((0.9, 0.05, 0.0491), "CCF_ALPHA_NORMALISED"),    # 0.9991
                        ((0.9, 0.05, 0.0509), "CCF_ALPHA_NORMALISED"),    # 1.0009
                        ((0.9, 0.05, 0.04901), "CCF_ALPHA_NORMALISED"),   # 0.99901
                        ((0.9, 0.05, 0.05099), "CCF_ALPHA_NORMALISED"),   # 1.00099
                        ((0.9, 0.05, 0.04899), "CCF_ALPHA_SUM"),          # 0.99899
                        ((0.9, 0.05, 0.05101), "CCF_ALPHA_SUM"),          # 1.00101
                        ((0.9, 0.05, 0.0485), "CCF_ALPHA_SUM"),           # 0.9985
                        ((0.9, 0.05, 0.0515), "CCF_ALPHA_SUM")]:          # 1.0015
        api.open_doc(doc_for(alpha=alpha))
        (group,) = api.groups()["groups"]
        codes = [w["code"] for w in group["status"]["warnings"]] + [
            e["code"] for e in group["status"]["errors"]]
        assert codes == [code], (alpha, codes)
        assert group["status"]["applied"] is (code == "CCF_ALPHA_NORMALISED")


def test_no_normalisation_warning_for_a_sum_within_1e_9(api):
    for extra in (0.0, 1e-10, -1e-10, 9e-10):
        api.open_doc(doc_for(alpha=(0.955, 0.034, 0.011 + extra)))
        (group,) = api.groups()["groups"]
        assert group["status"]["applied"] is True
        assert group["status"]["warnings"] == [], extra
        assert ccf_issues(api) == []


def test_normalised_group_is_applied_and_its_events_reach_the_cut_sets():
    result = M.compute(M.or_tree(IDS3), [M.agroup(
        members=IDS3, alpha=(0.9555, 0.034, 0.011), testing="staggered")])
    assert result["total"] == 7
    assert "ccf:g1:A+B+D" in {e["id"] for cs in result["cutSets"] for e in cs["events"]}


def test_a_table_6_9_set_is_applied_and_the_note_shows_the_sum_of_the_printed_values(api):
    """S1 Table 6-9 prints no sum; the note shows the sum of the eight printed values."""
    for name, alpha, values_sum in M.TABLE_6_9:
        api.open_doc(doc_for(["A", "B", "C", "D"], alpha, "staggered"))
        (group,) = api.groups()["groups"]
        assert group["status"]["applied"] is True, name
        (warning,) = group["status"]["warnings"]
        assert warning["code"] == "CCF_ALPHA_NORMALISED"
        assert values_sum in warning["message"]["en"] and values_sum in warning["message"]["ja"]
        block = api.groups()["ccf"]
        assert [g["id"] for g in block["applied"]] == ["g1"] and block["notApplied"] == []


def test_a_group_without_a_scheme_reads_not_applied_testing_scheme_missing(api):
    from fta_web import ccf_text

    api.open_doc(doc_for(testing=None))
    (group,) = api.groups()["groups"]
    status = group["status"]
    assert status["applied"] is False and status["code"] == "CCF_NO_TESTING"
    assert ccf_text.text("en", "notApplied", reason=status["reason"]["en"]) == M.NO_SCHEME_STATUS_EN
    assert ccf_text.text("ja", "notApplied", reason=status["reason"]["ja"]) == M.NO_SCHEME_STATUS_JA
    assert M.NO_SCHEME_STATUS_EN == "Not applied: testing scheme missing"
    (entry,) = api.groups()["ccf"]["notApplied"]
    assert entry == {"id": "g1", "name": M.GROUP_NAME, "code": "CCF_NO_TESTING",
                     "reason": "testing scheme missing"}


def test_a_group_with_a_scheme_chosen_through_the_api_becomes_applied(api):
    api.open_doc(doc_for(testing=None))
    status, body = api.patch("/api/ccf/groups/g1", {"testing": "nonStaggered"})
    assert status == 200, body
    (group,) = api.groups()["groups"]
    assert group["status"]["applied"] is True and group["testing"] == "nonStaggered"


def test_eta_mode_gives_only_the_eta_status_even_for_a_broken_alpha_group(api):
    api.open_doc(doc_for(alpha=(0.9, 0.5), testing=None, mode="ETA"))
    (group,) = api.groups()["groups"]
    assert group["status"]["code"] == "CCF_ETA_MODE" and group["status"]["severity"] == "status"
    assert group["status"]["errors"] == [] and group["status"]["warnings"] == []
    assert ccf_issues(api) == []


def test_ccf_assess_lists_every_error_in_the_documented_order():
    from fta_web import ccf

    doc = doc_for(["A", "B", "C", "D", "E"], (0.9, 0.5), testing=None)
    (assessment,) = ccf.assess(doc["analysis"]["ccfGroups"], doc["tree"], doc["analysis"], "FTA")
    assert assessment.applied is False
    assert assessment.primary.code == "CCF_ALPHA_SIZE"
    codes = [f.code for f in assessment.findings if f.severity == "error"]
    assert codes == ["CCF_ALPHA_SIZE", "CCF_NO_TESTING"]  # SUM is not evaluated after SIZE


def test_high_q_warning_for_an_alpha_group_uses_the_alpha_wording(api):
    tree = M.and_tree(IDS3, q=0.02)
    api.open_doc(M.document(tree, [M.agroup(members=IDS3, alpha=ALPHA_OK, testing="staggered")]))
    (group,) = api.groups()["groups"]
    assert group["status"]["applied"] is True
    (warning,) = [w for w in group["status"]["warnings"] if w["code"] == "CCF_HIGH_Q"]
    assert warning["message"]["en"] == M.HIGH_Q_ALPHA_MESSAGE[0].format(
        group=M.GROUP_NAME, member="Pump A", q="0.02")
    assert warning["message"]["ja"] == M.HIGH_Q_ALPHA_MESSAGE[1].format(
        group=M.GROUP_NAME, member="Pump A", q="0.02")
