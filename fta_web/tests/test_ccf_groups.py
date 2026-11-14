"""Unit tests of the CCF group assessment, membership helpers and the 1.8.1
save oracle (F2 T1 review item and T2).

The acceptance tests in ``acceptance/ccf`` judge the feature end to end; these
check the pieces on their own, so a failure points at the piece.
"""
import hashlib
from pathlib import Path

import pytest

from fta_web import ccf
from fta_web.engine import WebCore

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

#: SHA-256 of the bytes ``WebCore.save_to_json`` writes after opening each
#: example, taken from a save made by the 1.8.1 release commit
#: (c6d09f5b0d5363fc037f63d3ec7cf1c91186a798, detached worktree) and found equal
#: to the save of this branch on 2026-10-28. A document without a group must
#: save byte for byte as 1.8.1 did (FN-18, FN-28). If an example file is
#: edited on purpose, redo the hashes from a 1.8.1 worktree, never from this code.
#: The core writes in text mode, so Windows ends lines with CR LF and Linux with
#: LF. The hashes below are of the LF form: the test turns CR LF into LF before it
#: hashes (as acceptance/ccf/test_file_format.py does). They are the 1.8.1 CR LF
#: saves with each CR LF turned into LF; the examples themselves are checked out
#: as LF on every platform (.gitattributes, ``-text``).
SAVED_SHA256_1_8_1 = {
    "sampleFTA.json": "9c9bdc0fd194ee4d22026e3cf9e78641e04be976dd44fae6af6a7d330c20c1f9",
    "challenger_fta_en.json": "7feecaa621b8c85116eec1f096e82646942d1b34cd9c830dd417335106d08550",
    "tmi2_eta_en.json": "ea33db0931a84448dd9856d240db5a63739c1cb487016f8dfaecea9e86bd5f2b",
}


@pytest.mark.parametrize("name", sorted(SAVED_SHA256_1_8_1))
def test_a_file_without_groups_saves_the_bytes_1_8_1_saved(tmp_path, name):
    core = WebCore()
    ok, error = core.load_from_json(str(EXAMPLES / name))
    assert ok, error
    out = tmp_path / "saved.json"
    assert core.save_to_json(str(out)) == (True, None)
    # The core writes in text mode: Windows ends lines with CR LF, Linux with LF.
    written = out.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(written).hexdigest() == SAVED_SHA256_1_8_1[name]


# ---- tree and groups used below ----------------------------------------------------


def leaf(node_id, q=1e-3, **extra):
    node = {"id": node_id, "name": "Pump " + node_id, "type": "Event", "logicGate": "OR",
            "probability": q, "notes": "", "links": [], "children": []}
    node.update(extra)
    return node


def tree(*children):
    return {"id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "probability": 1.0,
            "notes": "", "links": [], "children": list(children)}


def group(gid="g1", members=("A", "B"), **over):
    out = ccf.make_group(gid, "Feed " + gid, 0.1, members, "src")
    out.update(over)
    return out


def codes(assessment):
    return [f.code for f in assessment.findings]


# ---- assess ------------------------------------------------------------------------


def test_a_fine_group_is_applied_with_no_finding():
    (a,) = ccf.assess([group()], tree(leaf("A"), leaf("B")), {})
    assert a.applied and a.primary is None and a.findings == []
    assert a.id == "g1" and a.members == ["A", "B"]


def test_the_first_error_in_the_documented_order_is_primary_and_all_are_listed():
    # a ghost member (NOT_BASIC) and a bad beta: NOT_BASIC comes first in the order
    (a,) = ccf.assess([group(members=["A", "ghost"], beta="abc")], tree(leaf("A")), {})
    assert not a.applied
    assert a.primary.code == "CCF_MEMBER_NOT_BASIC" and a.primary.kind == "missing"
    assert codes(a) == ["CCF_MEMBER_NOT_BASIC", "CCF_BAD_PARAMETER"]


def test_eta_mode_gives_one_status_and_nothing_else():
    (a,) = ccf.assess([group(beta="abc")], tree(leaf("A"), leaf("B")), {}, "ETA")
    assert codes(a) == ["CCF_ETA_MODE"] and a.primary.severity == "status" and not a.applied


@pytest.mark.parametrize("entry", [5, None, "text", [1]])
def test_an_entry_that_is_not_an_object_is_reported_not_raised(entry):
    (a,) = ccf.assess([entry], tree(leaf("A")), {})
    assert not a.applied
    assert "CCF_BAD_PARAMETER" in codes(a) and "CCF_TOO_FEW_MEMBERS" in codes(a)


def test_a_repeated_group_id_marks_both_groups():
    two = [group("g1", ["A", "B"]), group("g1", ["C", "D"])]
    found = ccf.assess(two, tree(*[leaf(i) for i in "ABCD"]), {})
    assert [a.primary.kind for a in found] == ["id", "id"]


def test_a_node_id_starting_with_ccf_colon_blocks_every_group():
    (a,) = ccf.assess([group()], tree(leaf("A"), leaf("B"), leaf("ccf:g1")), {})
    assert a.primary.code == "CCF_BAD_PARAMETER" and a.primary.kind == "id"
    assert 'starts with "ccf:"' in a.primary.text()["en"]["message"]


def test_members_are_judged_on_the_recalculated_value_not_a_stale_probability():
    rate = {"model": "rate", "lambda": 1e-7}
    (a,) = ccf.assess([group()], tree(leaf("A", 0.5, quant=rate), leaf("B", 0.5, quant=rate)),
                      {"missionTime": 1000.0})
    assert a.applied  # equal models and parameters; the stored 0.5 is not what counts


def test_beta_is_valid_only_for_a_number_from_0_to_1():
    assert all(ccf.beta_is_valid(v) for v in (0, 1, 0.0, 0.5, 1.0))
    assert not any(ccf.beta_is_valid(v) for v in
                   (True, "0.1", None, -0.1, 1.5, float("nan"), float("inf"), 10 ** 400, [0.1]))


def test_text_of_a_finding_has_both_languages_and_names_group_and_member():
    (a,) = ccf.assess([group(members=["A", "ghost"])], tree(leaf("A")), {})
    texts = a.primary.text()
    for lang in ("en", "ja"):
        assert "Feed g1" in texts[lang]["message"] and "ghost" in texts[lang]["message"]
    assert texts["en"]["reason"] == '"ghost" is not in the tree'


def test_listing_returns_stored_values_names_and_status():
    analysis = {"ccfGroups": [group(beta="abc"), group("g2", ["A", "ghost"])]}
    items, block = ccf.listing(tree(leaf("A"), leaf("B")), analysis, "FTA")
    assert items[0]["beta"] == "abc" and items[0]["memberNames"] == ["Pump A", "Pump B"]
    assert items[1]["memberNames"] == ["Pump A", None]
    assert [n["id"] for n in block["notApplied"]] == ["g1", "g2"] and block["applied"] == []


# ---- membership (FN-38) ------------------------------------------------------------


class _Core:
    def __init__(self, analysis):
        self.analysis = analysis


def test_remove_members_keeps_the_group_and_clears_the_rename_flag():
    analysis = {"ccfGroups": [group(members=["A", "B", "C"])],
                ccf.RENAMED_KEY: {"g1": ["A"]}}
    core = _Core(analysis)
    assert ccf.remove_members(core, {"A", "C"}) is True
    assert analysis["ccfGroups"][0]["members"] == ["B"]  # one left: still stored
    assert ccf.RENAMED_KEY not in analysis
    assert ccf.remove_members(core, {"zzz"}) is False


def test_remove_members_tolerates_odd_stored_values():
    analysis = {"ccfGroups": [5, {"members": None}, {"members": [1, {"x": 1}, "A"]}]}
    assert ccf.remove_members(_Core(analysis), ["A"]) is True
    assert analysis["ccfGroups"][2]["members"] == [1, {"x": 1}]


def test_remap_follows_the_top_id_and_flags_a_repeated_id():
    groups = [group("g1", ["TOP", "A"]), group("g2", ["B", "C"])]
    warnings = [{"kind": "root_id", "old_id": "TOP", "new_id": "root"},
                {"kind": "duplicate_id", "old_id": "B", "new_id": "B_dup2"}]
    flagged = ccf.remap_loaded_members(groups, warnings, {"root", "A", "B", "B_dup2", "C"})
    assert groups[0]["members"] == ["root", "A"]
    assert groups[1]["members"] == ["B", "C"]
    assert flagged == {"g2": ["B"]}


def test_remap_flags_an_old_top_id_that_another_node_still_carries():
    groups = [group("g1", ["A", "B"])]
    warnings = [{"kind": "root_id", "old_id": "A", "new_id": "root"}]
    flagged = ccf.remap_loaded_members(groups, warnings, {"root", "A", "B"})
    assert groups[0]["members"] == ["A", "B"] and flagged == {"g1": ["A"]}
