"""Unit tests of the CCF file format helpers and the beta validator (F2 T1).

The acceptance tests in ``acceptance/ccf`` judge the feature end to end; these
check the small pieces on their own, so a failure points at the piece.
"""
import math

import pytest

from fta_web import ccf
from fta_web.ccf_schema import validate_ccf_beta
from fta_web.errors import ApiError


@pytest.mark.parametrize("value", [0, 1, 0.0, 1.0, 0.1, 1e-9, 0.999999])
def test_validate_ccf_beta_accepts_numbers_in_0_1(value):
    assert validate_ccf_beta(value) == value


def test_validate_ccf_beta_turns_minus_zero_into_zero():
    result = validate_ccf_beta(-0.0)
    assert result == 0 and math.copysign(1.0, result) == 1.0


@pytest.mark.parametrize("value", ["0.1", True, None, [0.1], {}, -0.1, 1.5, 101,
                                   float("nan"), float("inf"), 10 ** 400])
def test_validate_ccf_beta_refuses_everything_else_naming_the_field(value):
    with pytest.raises(ApiError) as caught:
        validate_ccf_beta(value)
    assert caught.value.code == "INVALID_FIELD"
    assert caught.value.detail == {"field": "beta"}


def test_validate_ccf_beta_names_a_given_field():
    with pytest.raises(ApiError) as caught:
        validate_ccf_beta(2, "groups.beta")
    assert caught.value.detail == {"field": "groups.beta"}


def test_take_groups_leaves_the_argument_alone_and_returns_the_rest():
    raw = {"missionTime": 10, "ccfGroups": [5], "cutsets": {"maxOrder": 3}}
    rest, groups = ccf.take_groups(raw)
    assert rest == {"missionTime": 10, "cutsets": {"maxOrder": 3}}
    assert groups == [5]
    assert "ccfGroups" in raw


@pytest.mark.parametrize("raw", [None, 3, "x", [], {"missionTime": 1}])
def test_take_groups_without_the_key_returns_the_input(raw):
    rest, groups = ccf.take_groups(raw)
    assert rest is raw and groups is None


def test_load_groups_keeps_every_entry_verbatim_as_a_copy():
    entries = [5, None, {"id": "g1", "beta": "abc"}]
    groups, warnings = ccf.load_groups(entries)
    assert groups == entries and groups is not entries
    assert groups[2] is not entries[2]
    assert warnings == []


@pytest.mark.parametrize("raw", [None, []])
def test_load_groups_stores_nothing_for_none_or_an_empty_list(raw):
    assert ccf.load_groups(raw) == (None, [])


@pytest.mark.parametrize("raw", [{}, "x", 5, True])
def test_load_groups_ignores_a_value_that_is_not_a_list_with_one_warning(raw):
    groups, warnings = ccf.load_groups(raw)
    assert groups is None
    assert [w["kind"] for w in warnings] == ["ccf_invalid"]
    assert warnings[0]["message"] == ccf.NOT_A_LIST_MESSAGE


@pytest.mark.parametrize("version, warns", [(3, True), (2.5, True), (2, False), (1, False),
                                            (True, False), ("3", False), (None, False)])
def test_format_version_warning(version, warns):
    found = ccf.format_version_warnings({"fileFormatVersion": version})
    assert bool(found) is warns
    if warns:
        assert found[0]["message"] == "This file was saved by a newer FTA Editor; saving may lose data"


def test_format_version_warning_for_a_document_that_is_not_an_object():
    assert ccf.format_version_warnings(None) == []
    assert ccf.format_version_warnings([3]) == []


def test_export_document_without_a_group_only_appends_analysis():
    data = {"title": "t", "date": "d", "mode": "FTA", "tree": {}}
    out = ccf.export_document(dict(data), {"missionTime": 1, "ccfGroups": [], "_ccfRenamed": {}})
    assert list(out) == ["title", "date", "mode", "tree", "analysis"]
    assert out["analysis"] == {"missionTime": 1}


def test_export_document_does_not_change_the_data_it_is_given():
    """R4 (code advice): the no-group branch used to set data["analysis"] on the caller's dict."""
    for analysis in ({"missionTime": 1, "ccfGroups": []},
                     {"ccfGroups": [ccf.make_group("g1", "Feed", 0.1, ["A", "B"])]}):
        data = {"title": "t", "date": "d", "mode": "FTA", "tree": {}}
        before = dict(data)
        out = ccf.export_document(data, analysis)
        assert data == before and list(data) == list(before) and "analysis" not in data
        assert out is not data and "analysis" in out
    # a document that already carries an analysis block keeps its key position in the copy
    data = {"title": "t", "analysis": {"old": 1}, "tree": {}}
    out = ccf.export_document(data, {"missionTime": 2})
    assert data["analysis"] == {"old": 1}
    assert list(out) == ["title", "analysis", "tree"] and out["analysis"] == {"missionTime": 2}


def test_export_document_with_a_group_adds_version_2_before_the_tree():
    data = {"title": "t", "date": "d", "mode": "FTA", "tree": {}}
    group = ccf.make_group("g1", "Feed", 0.1, ["A", "B"])
    out = ccf.export_document(dict(data), {"ccfGroups": [group], "_ccfRenamed": {"g1": ["A"]}})
    assert list(out) == ["title", "date", "mode", "fileFormatVersion", "tree", "analysis"]
    assert out["fileFormatVersion"] == 2
    assert out["analysis"] == {"ccfGroups": [group]}  # private keys are not written


def test_make_group_has_the_eight_keys_in_file_order():
    group = ccf.make_group("g1", "Feed", 0.1, ("A", "B"), "src")
    assert tuple(group) == ccf.GROUP_KEYS
    assert group["alpha"] is None and group["testing"] is None
    assert group["members"] == ["A", "B"] and group["model"] == "beta"


# ---- fileFormatVersion that is not an ordinary number (T1 review) ---------------------


def test_format_version_infinity_warns_and_nan_does_not():
    """Infinity is a number above 2, so it is a newer version; NaN is no version
    number at all (it compares false with everything), so it is ignored like a
    string. Neither may crash."""
    assert [w["kind"] for w in ccf.format_version_warnings(
        {"fileFormatVersion": float("inf")})] == ["newer_format"]
    assert ccf.format_version_warnings({"fileFormatVersion": float("nan")}) == []
    assert ccf.format_version_warnings({"fileFormatVersion": 10 ** 400}) != []  # beyond float range


@pytest.mark.parametrize("token, warns", [("NaN", False), ("Infinity", True), ("-Infinity", False)])
def test_a_file_with_a_bare_nan_or_infinity_version_opens_and_saves(tmp_path, token, warns):
    """Python's json reads the bare tokens; a hand-edited file with one opens
    without a crash and is saved without the odd version."""
    from fta_web.engine import WebCore

    source = tmp_path / "odd.json"
    source.write_text(
        '{"title": "t", "date": "2026-10-28", "mode": "FTA", "fileFormatVersion": %s,'
        ' "tree": {"id": "root", "name": "Top", "type": "Root", "probability": 0.5,'
        ' "logicGate": "OR", "notes": "", "links": [], "children": []},'
        ' "analysis": {"ccfGroups": [{"id": "g1", "name": "G", "model": "beta", "beta": 0.1,'
        ' "alpha": null, "testing": null, "members": ["a", "b"], "source": ""}]}}' % token,
        encoding="utf-8")
    core = WebCore()
    ok, error = core.load_from_json(str(source))
    assert ok, error
    kinds = [w["kind"] for w in core.last_load_warnings]
    assert ("newer_format" in kinds) is warns
    saved = tmp_path / "saved.json"
    assert core.save_to_json(str(saved)) == (True, None)
    text = saved.read_text(encoding="utf-8")
    assert '"fileFormatVersion": 2' in text and "NaN" not in text and "Infinity" not in text
