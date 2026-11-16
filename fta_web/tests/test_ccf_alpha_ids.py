"""Unit tests of two assessment rules of the alpha-factor groups (F2A T1, FN-41, FN-43).

* CCF event ids join group and member ids with ``+`` and ``:``. When two events
  of the applied groups would get the same id, the structure would merge them,
  so every group that holds such an id is refused (``CCF_BAD_PARAMETER``, kind
  ``event_id``). Ordinary ids, and an id like ``x+y`` that clashes with nothing,
  are not affected.
* An alpha sum exactly 0.001 away from 1 in decimal is inside the tolerance of
  FN-43 although the float sum can land a few ulps beyond it.
"""
import pytest

from fta_web import ccf, logic


def leaf(node_id, q=1e-3):
    return {"id": node_id, "name": "Pump " + node_id, "type": "Event", "logicGate": "OR",
            "probability": q, "notes": "", "links": [], "children": []}


def top(ids):
    return {"id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "probability": 1.0,
            "notes": "", "links": [], "children": [leaf(i) for i in ids]}


ALPHAS = {2: (0.9, 0.1), 3: (0.9, 0.06, 0.04), 4: (0.7, 0.2, 0.06, 0.04)}   # each adds up to 1


def alpha_group(gid, members, alpha=None, testing="staggered"):
    group = ccf.make_group(gid, "Group " + gid, None, members, "", model="alpha")
    group.update(alpha=list(alpha or ALPHAS[len(members)]), testing=testing)
    return group


def beta_group(gid, members, beta=0.2):
    return ccf.make_group(gid, "Group " + gid, beta, members, "")


def assess(ids, groups):
    return ccf.assess(groups, top(ids), {"ccfGroups": groups}, "FTA")


def clash_event(assessment):
    """The ``event`` parameter of the ``event_id`` finding, or None."""
    for finding in assessment.findings:
        if finding.code == "CCF_BAD_PARAMETER" and finding.kind == "event_id":
            return finding.params["event"]
    return None


# ---- event id clashes ------------------------------------------------------------------


def test_two_subsets_of_one_group_with_the_same_id_are_refused():
    """Members a, b+c, a+b, c: the subsets {a, b+c} and {a+b, c} are both ccf:g:a+b+c."""
    groups = [alpha_group("g", ["a", "b+c", "a+b", "c"])]
    (result,) = assess(["a", "b+c", "a+b", "c"], groups)
    assert not result.applied
    assert result.primary.code == "CCF_BAD_PARAMETER" and result.primary.kind == "event_id"
    assert clash_event(result) == "ccf:g:a+b+c"


def test_an_alpha_event_and_a_beta_event_of_two_groups_with_the_same_id_are_refused():
    """Alpha group g on a, b makes ccf:g:a+b; beta group "g:a+b" makes ccf:g:a+b too."""
    groups = [alpha_group("g", ["a", "b"]), beta_group("g:a+b", ["p", "q"])]
    first, second = assess(["a", "b", "p", "q"], groups)
    assert not first.applied and not second.applied
    assert clash_event(first) == clash_event(second) == "ccf:g:a+b"


def test_the_refusal_texts_name_the_group_and_the_event_in_both_languages():
    groups = [alpha_group("g", ["a", "b"]), beta_group("g:a+b", ["p", "q"])]
    (first, _second) = assess(["a", "b", "p", "q"], groups)
    texts = first.primary.text()
    assert texts["en"]["reason"] == 'CCF event id "ccf:g:a+b" would be made twice'
    assert texts["ja"]["reason"] == "CCF 事象 ID「ccf:g:a+b」が重複します"
    for lang in ("en", "ja"):
        assert "Group g" in texts[lang]["message"] and "ccf:g:a+b" in texts[lang]["message"]
        assert texts[lang]["fix"]


def test_a_member_id_with_a_plus_that_clashes_with_nothing_stays_applied():
    members = ["x+y", "z", "w"]
    groups = [alpha_group("g1", members)]
    (result,) = assess(members, groups)
    assert result.applied and result.findings == []
    structure = logic.compile_tree(top(members), {"ccfGroups": groups})
    ids = [e["id"] for e in structure.events if e["id"].startswith("ccf:")]
    assert ids == ["ccf:g1:x+y+z", "ccf:g1:x+y+w", "ccf:g1:z+w", "ccf:g1:x+y+z+w"]
    expected = ccf.event_probabilities("alpha", groups[0], [1e-3] * 3)
    by_id = {e["id"]: e["q"] for e in structure.events}
    for event, (_subset, q) in zip(ids, expected.events):
        assert by_id[event] == q


def test_a_beta_group_id_with_a_colon_that_clashes_with_nothing_stays_applied():
    groups = [beta_group("g:a+b", ["p", "q"]), alpha_group("h", ["a", "b"])]
    first, second = assess(["a", "b", "p", "q"], groups)
    assert first.applied and second.applied


def test_a_group_that_is_refused_for_another_reason_still_counts_for_the_clash():
    """The check does not depend on the other findings: group g (alpha, no scheme) and the beta
    group "g:a+b" are both refused, the second one for the event id."""
    groups = [alpha_group("g", ["a", "b"], testing=None), beta_group("g:a+b", ["p", "q"])]
    first, second = assess(["a", "b", "p", "q"], groups)
    assert clash_event(first) == clash_event(second) == "ccf:g:a+b"


# ---- the FN-43 boundary ------------------------------------------------------------------


@pytest.mark.parametrize("alpha", [(0.899, 0.1), (0.9, 0.101), (0.5, 0.501), (0.4991, 0.5),
                                   (0.5, 0.50099)])
def test_a_sum_up_to_0_001_from_one_is_applied_with_the_normalised_warning(alpha):
    (result,) = assess(["A", "B"], [alpha_group("g", ["A", "B"], alpha)])
    assert result.applied
    assert [f.code for f in result.findings] == ["CCF_ALPHA_NORMALISED"]


@pytest.mark.parametrize("alpha", [(0.8989, 0.1), (0.9, 0.1011), (0.5, 0.50101), (0.5, 0.49899)])
def test_a_sum_more_than_0_001_from_one_is_refused(alpha):
    (result,) = assess(["A", "B"], [alpha_group("g", ["A", "B"], alpha)])
    assert not result.applied
    assert (result.primary.code, result.primary.kind) == ("CCF_ALPHA_SUM", "sum")
