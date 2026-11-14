"""F2 BRIEF criteria 5 and 6 (FN-33, FN-37): the CCF lint.

Criterion 5: every row of the FN-33 table -- all twelve codes, every kind
DESIGN section 9 lists -- is one test that opens a document raising it and
asserts the code, the severity and the applied flag, on both public surfaces:

* ``GET /api/ccf/groups`` (the CCF tab's status: applied flag, primary code,
  severity ``error`` / ``status``, reason and message in en and ja, and the
  warnings of an applied group);
* ``GET /api/analysis/validate`` (the Validation tab: an issue per error and
  warning with ``nodeId`` None and the group in ``params``; the status code
  ``CCF_ETA_MODE`` is never an issue).

Also: equal lambda entered per year and per hour gives no lint; members under
INHIBIT or KOFN and a member referenced twice (a link, a transfer) give none;
each text names the group and the member in en and in ja.

Criterion 6 (API side): a not-applied group is in the ``ccf`` block of the
summary (the data of the headline note), in the group status and in the
Validation list with its jump target; in ETA mode only the note data and the
status exist.
"""
import pytest

import _ccf_models as M

CASES = M.lint_cases()
CASE_IDS = [c["id"] for c in CASES]

TWELVE_CODES = {
    "CCF_MEMBER_NOT_BASIC", "CCF_TOO_FEW_MEMBERS", "CCF_MEMBER_IN_TWO_GROUPS",
    "CCF_MEMBERS_DIFFER", "CCF_NO_PROBABILITY", "CCF_Q_ONE", "CCF_BAD_PARAMETER",
    "CCF_MEMBER_RENAMED", "CCF_ETA_MODE", "CCF_HIGH_Q", "CCF_ZERO_Q", "CCF_ORDERED_GATE",
}
SEVERITY_OF_ISSUE_CODES = {
    "CCF_MEMBER_NOT_BASIC": "error", "CCF_TOO_FEW_MEMBERS": "error",
    "CCF_MEMBER_IN_TWO_GROUPS": "error", "CCF_MEMBERS_DIFFER": "error",
    "CCF_NO_PROBABILITY": "error", "CCF_Q_ONE": "error", "CCF_BAD_PARAMETER": "error",
    "CCF_MEMBER_RENAMED": "error", "CCF_HIGH_Q": "warning", "CCF_ZERO_Q": "warning",
    "CCF_ORDERED_GATE": "warning",
}


def contains_all(text, names):
    for wanted in names:
        alternatives = wanted if isinstance(wanted, tuple) else (wanted,)
        assert any(a in text for a in alternatives), "%r not in %r" % (wanted, text)


def ccf_issues(api):
    status, body = api.get("/api/analysis/validate")
    assert status == 200, body
    return [i for i in body["issues"] if str(i["code"]).startswith("CCF_")]


def test_the_cases_cover_all_twelve_codes_of_fn_33():
    assert {c["code"] for c in CASES} == TWELVE_CODES
    assert {c["severity"] for c in CASES} == {"error", "warning", "status"}


@pytest.mark.parametrize("code, severity", sorted(SEVERITY_OF_ISSUE_CODES.items()))
def test_lint_knows_the_severity_of_each_issue_code(code, severity):
    from fta_web import lint

    assert lint.SEVERITY[code] == severity
    assert "CCF_ETA_MODE" not in lint.SEVERITY  # a status, never a Validation issue


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_status_of_each_code(api, case):
    api.open_doc(case["doc"])
    listing = api.groups()
    for index in case["gi"]:
        group = listing["groups"][index]
        status = group["status"]
        if case["applied"]:
            assert status["applied"] is True
            assert status["code"] is None and status["severity"] is None
            assert status["errors"] == []
            (warning,) = [w for w in status["warnings"] if w["code"] == case["code"]]
            assert warning["severity"] == "warning"
            reason, message = warning["reason"], warning["message"]
        else:
            assert status["applied"] is False
            assert status["code"] == case["code"]
            assert status["severity"] == case["severity"]
            assert case["code"] in [e["code"] for e in status["errors"]] or case["severity"] == "status"
            reason, message = status["reason"], status["message"]
        pairs = case["reasons"]
        assert (reason["en"], reason["ja"]) in pairs, (reason, pairs)
        contains_all(message["en"], case["names"])
        contains_all(message["ja"], case["names"])
        contains_all(message["en"], case["msg_en"])
        assert message["en"] != message["ja"]
        # the group is not applied exactly when the block says so
        block = listing["ccf"]
        listed_ids = [g["id"] for g in block["notApplied"]]
        if case["applied"]:
            assert group["id"] in [g["id"] for g in block["applied"]]
        elif group["id"] is not None:
            assert group["id"] in listed_ids
            entry = [g for g in block["notApplied"] if g["id"] == group["id"]][0]
            assert entry["code"] == case["code"] and entry["name"] == group["name"]
            assert entry["reason"] in [p[0] for p in pairs]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_validation_issue_of_each_code(api, case):
    api.open_doc(case["doc"])
    listing = api.groups()
    issues = ccf_issues(api)
    if case["severity"] == "status":
        # CCF_ETA_MODE: only a status. The document is in ETA mode and no CCF issue exists.
        assert issues == []
        return
    found = [i for i in issues if i["code"] == case["code"]]
    assert len(found) >= len(case["gi"]), issues
    for index in case["gi"]:
        group = listing["groups"][index]
        mine = [i for i in found if i["params"].get("groupId") == group["id"]]
        assert len(mine) >= 1, (group["id"], found)
        issue = mine[0]
        assert issue["severity"] == case["severity"]
        assert issue["nodeId"] is None  # a group, not a node
        assert group["name"] in issue["message"]  # English default names the group
        text = issue["params"]["text"]
        pairs = case["reasons"]
        assert (text["en"]["reason"], text["ja"]["reason"]) in pairs
        for lang in ("en", "ja"):
            assert text[lang]["message"] and text[lang]["fix"]
            contains_all(text[lang]["message"], case["names"])
        assert text["en"]["fix"] != text["ja"]["fix"]
        assert issue["params"]["group"] == group["name"]


def test_an_issue_from_lint_run_carries_the_hint_key_and_both_texts():
    from fta_web import lint

    case = [c for c in CASES if c["id"] == "DIFFER_parameter"][0]
    doc = case["doc"]
    issues = [i for i in lint.run(doc["tree"], doc["analysis"], [], mode="FTA")
              if i["code"] == "CCF_MEMBERS_DIFFER"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue["severity"] == "error"
    assert issue["hintKey"] == "val.fix.CCF_MEMBERS_DIFFER"
    assert issue["nodeId"] is None and issue["nodeName"] is None
    assert issue["params"]["groupId"] == "g1"
    assert issue["params"]["memberId"] == "B"
    assert {"en", "ja"} <= set(issue["params"]["text"])


def test_a_ccf_issue_is_not_merged_with_another_of_the_same_code():
    """Two groups with the same error give two issues (no node id to dedupe on)."""
    from fta_web import lint

    tree = M.top([M.gate("G1", "AND", [M.pump("A"), M.pump("B"), M.pump("C"), M.pump("D")])])
    groups = [M.group("g1", "One", ["A", "B"], beta="abc"),
              M.group("g2", "Two", ["C", "D"], beta="abc")]
    issues = [i for i in lint.run(tree, {"ccfGroups": groups}, [], mode="FTA")
              if i["code"] == "CCF_BAD_PARAMETER"]
    assert sorted(i["params"]["groupId"] for i in issues) == ["g1", "g2"]


def test_eta_mode_is_a_status_only_and_lint_run_in_eta_mode_has_no_ccf_issue():
    from fta_web import ccf, lint

    doc = M.r1_document(mode="ETA")
    (assessment,) = ccf.assess(doc["analysis"]["ccfGroups"], doc["tree"], doc["analysis"], "ETA")
    assert assessment.applied is False
    assert assessment.primary.code == "CCF_ETA_MODE" and assessment.primary.severity == "status"
    assert [i for i in lint.run(doc["tree"], doc["analysis"], [], mode="ETA")
            if str(i["code"]).startswith("CCF_")] == []
    assert [i for i in lint.run(doc["tree"], doc["analysis"], [], mode="FTA")
            if str(i["code"]).startswith("CCF_")] == []  # a fine group: nothing either


# ---------------------------------------------------------------- no lint


@pytest.mark.parametrize("name, doc", M.no_lint_cases(), ids=[n for n, _ in M.no_lint_cases()])
def test_no_lint_for_these_documents(api, name, doc):
    """Equal lambda typed per year or per hour; members under INHIBIT or KOFN; a
    member reached twice by a link or a transfer: the group is applied, no finding."""
    api.open_doc(doc)
    (group,) = api.groups()["groups"]
    status = group["status"]
    assert status["applied"] is True and status["code"] is None
    assert status["errors"] == [] and status["warnings"] == []
    assert ccf_issues(api) == []


def test_a_broken_group_does_not_disturb_a_fine_one(api):
    tree = M.top([M.gate("G1", "AND", [M.pump("A"), M.pump("B"), M.pump("C"), M.pump("D")])])
    groups = [M.group("g1", "Fine", ["A", "B"]),
              M.group("g2", "Broken", ["C", "D"], beta="abc")]
    api.open_doc(M.document(tree, groups))
    by_id = {g["id"]: g["status"] for g in api.groups()["groups"]}
    assert by_id["g1"]["applied"] is True
    assert by_id["g2"]["applied"] is False and by_id["g2"]["code"] == "CCF_BAD_PARAMETER"


# ----------------------------------------------- criterion 6, the API side


def two_groups_one_fine_one_differing():
    tree = M.top([M.gate("G1", "AND", [M.pump("A"), M.pump("B"), M.pump("C"),
                                       M.pump("D", 2e-3)], name="Pumps fail")])
    return M.document(tree, [M.group("g1", "Fine", ["A", "B"]),
                             M.group("g2", "Differs", ["C", "D"])])


def test_the_summary_carries_the_not_applied_note_data(api):
    api.open_doc(two_groups_one_fine_one_differing())
    status, summary = api.get("/api/analysis/summary")
    assert status == 200, summary
    block = summary["ccf"]
    assert [g["id"] for g in block["applied"]] == ["g1"]
    assert block["notApplied"] == [{
        "id": "g2", "name": "Differs", "code": "CCF_MEMBERS_DIFFER",
        "reason": '"Pump D" differs from "Pump C"'}]
    assert block["note"] == M.NOTE_EN
    assert summary["ccfIncomplete"] is False
    assert len(block["notApplied"]) == 1  # "1 CCF group not applied"


def test_a_validation_issue_per_not_applied_group_names_the_group_to_jump_to(api):
    api.open_doc(two_groups_one_fine_one_differing())
    (issue,) = ccf_issues(api)
    assert issue["code"] == "CCF_MEMBERS_DIFFER" and issue["severity"] == "error"
    assert issue["nodeId"] is None
    assert issue["params"]["groupId"] == "g2"  # the jump target of the Validation tab
    assert issue["params"]["group"] == "Differs"
    assert "Differs" in issue["message"]


def test_eta_mode_has_the_note_data_and_the_status_but_no_validation_issue(api):
    tree = M.top([M.gate("G1", "AND", [M.pump("A"), M.pump("B"), M.pump("C"), M.pump("D")])])
    doc = M.document(tree, [M.group("g1", "First", ["A", "B"]),
                            M.group("g2", "Second", ["C", "D"])], mode="ETA")
    api.open_doc(doc)
    listing = api.groups()
    assert [g["code"] for g in listing["ccf"]["notApplied"]] == ["CCF_ETA_MODE", "CCF_ETA_MODE"]
    assert [g["reason"] for g in listing["ccf"]["notApplied"]] == ["ETA mode", "ETA mode"]
    assert listing["ccf"]["applied"] == []
    assert listing["ccf"]["note"] == M.NOTE_EN
    for group in listing["groups"]:
        assert group["status"]["applied"] is False
        assert group["status"]["severity"] == "status"
        assert group["status"]["reason"] == {"en": "ETA mode", "ja": "ETA モード"}
    assert ccf_issues(api) == []
    status, body = api.get("/api/analysis/summary")  # an event tree has no fault-tree summary
    assert status == 409


def test_a_group_that_is_not_applied_changes_no_number(api):
    """FN-28 spirit: the same tree with the broken group and without it give one result."""
    broken = M.document(M.r1_tree(), [M.group(beta="abc")])
    api.open_doc(broken)
    status, with_group = api.get("/api/analysis/summary")
    assert status == 200
    api.open_doc(M.tree_without_groups(broken), "plain.json")
    status, without = api.get("/api/analysis/summary")
    for key in ("treeWalk", "mcub", "rareEvent", "headline", "headlineMethod",
                "truncated", "truncatedBy", "capped"):
        assert with_group[key] == without[key], key
    assert "ccfGates" not in with_group
    assert with_group["ccfIncomplete"] is False
