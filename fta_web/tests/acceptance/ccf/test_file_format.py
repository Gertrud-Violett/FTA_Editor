"""F2 BRIEF criterion 1 (FN-18): the file format of CCF groups.

* groups live under ``analysis.ccfGroups`` and a file with a group also gets the
  top-level ``"fileFormatVersion": 2``; a no-group file is saved byte for byte as
  1.8.1 saves it;
* a dedicated loader keeps every group verbatim (a bad beta, a missing member)
  and takes ``ccfGroups`` out before ``engine.coerce_analysis`` sees it, so there
  is no ``analysis_invalid`` warning for it, while another invalid setting in
  the same file still gives exactly one, naming only that setting;
* ``fileFormatVersion`` above 2 opens with the newer-version warning.

``WebCore`` is the public loader/saver (the CLI and the routes use it).
"""
import json

import pytest

import _ccf_models as M

NEWER = M.NEWER_FORMAT_WARNING


def three_groups():
    """One valid group, one with ``"beta": "abc"``, one with a missing member."""
    return [
        M.group("g1", "Valid pair", ["A", "B"], source="handbook p. 1"),
        M.group("g2", "Bad beta", ["D", "E"], beta="abc"),
        M.group("g3", "Missing member", ["F", "nowhere"], beta=0.2, source=""),
    ]


def three_group_tree():
    return M.top([
        M.gate("G1", "AND", [M.pump("A"), M.pump("B")], name="Pumps fail"),
        M.gate("G2", "AND", [M.pump("D"), M.pump("E")], name="Valves fail"),
        M.pump("F"),
    ])


def load(path):
    from fta_web import engine

    core = engine.WebCore()
    ok, error = core.load_from_json(str(path))
    assert ok, error
    return core


def kinds(core, kind):
    return [w for w in core.last_load_warnings if w.get("kind") == kind]


def test_three_group_file_loads_verbatim_and_saves_the_same_groups(tmp_path):
    groups = three_groups()
    path = M.write_doc(tmp_path, M.document(three_group_tree(), groups), "three.json")
    core = load(path)

    assert core.analysis["ccfGroups"] == groups  # JSON objects equal, nothing coerced
    assert kinds(core, "analysis_invalid") == []
    assert not any("ccfGroups" in w.get("message", "") for w in core.last_load_warnings)

    out = tmp_path / "saved.json"
    ok, error = core.save_to_json(str(out))
    assert ok, error
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["analysis"]["ccfGroups"] == groups
    assert saved["fileFormatVersion"] == 2
    assert saved["tree"]["id"] == "root"


def test_three_group_file_opened_through_the_api_gives_no_analysis_invalid(api, tmp_path):
    groups = three_groups()
    body = api.open_doc(M.document(three_group_tree(), groups), "three.json")
    assert [w for w in body["warnings"] if w.get("kind") == "analysis_invalid"] == []
    assert body["analysis"]["ccfGroups"] == groups
    status, issues = api.get("/api/analysis/validate")
    assert status == 200
    assert not any("ccfGroups" in (i.get("message") or "") for i in issues["issues"])


def test_other_invalid_setting_still_warns_exactly_once_and_names_only_itself(tmp_path):
    groups = three_groups()
    doc = M.document(three_group_tree(), groups, analysis={"cutsets": {"maxOrder": 0}})
    core = load(M.write_doc(tmp_path, doc, "bad_setting.json"))

    warned = kinds(core, "analysis_invalid")
    assert len(warned) == 1
    assert warned[0]["fields"] == ["cutsets.maxOrder"]
    assert "cutsets.maxOrder" in warned[0]["message"]
    assert "ccfGroups" not in warned[0]["message"]
    assert core.analysis["ccfGroups"] == groups
    from fta_web import engine

    # reset to the default, as in 1.8.1
    assert core.analysis["cutsets"]["maxOrder"] == engine.DEFAULT_ANALYSIS["cutsets"]["maxOrder"]


def test_other_invalid_setting_via_the_api_warns_once(api):
    doc = M.document(three_group_tree(), three_groups(), analysis={"cutsets": {"maxOrder": 0}})
    body = api.open_doc(doc, "bad_setting.json")
    warned = [w for w in body["warnings"] if w.get("kind") == "analysis_invalid"]
    assert len(warned) == 1 and warned[0]["fields"] == ["cutsets.maxOrder"]


def test_entries_that_are_not_objects_are_kept_verbatim(tmp_path):
    entries = [5, "x", None, {"id": "g9"}, M.group("g1", "Valid pair", ["A", "B"])]
    core = load(M.write_doc(tmp_path, M.document(three_group_tree(), entries), "odd.json"))
    assert core.analysis["ccfGroups"] == entries
    assert kinds(core, "analysis_invalid") == []
    out = tmp_path / "odd_saved.json"
    assert core.save_to_json(str(out))[0]
    assert json.loads(out.read_text(encoding="utf-8"))["analysis"]["ccfGroups"] == entries


def test_ccf_groups_that_is_not_a_list_is_ignored_with_a_load_warning(tmp_path):
    doc = M.document(three_group_tree(), None, analysis={"ccfGroups": {"g1": "oops"}})
    core = load(M.write_doc(tmp_path, doc, "not_a_list.json"))
    assert "ccfGroups" not in core.analysis
    assert kinds(core, "analysis_invalid") == []
    ignored = kinds(core, "ccf_invalid")
    assert len(ignored) == 1
    assert ignored[0]["message"] == "The ccfGroups entry in the file is not a list, so it was ignored."


def test_empty_list_stores_nothing_and_saves_nothing(tmp_path):
    doc = M.document(three_group_tree(), [])
    core = load(M.write_doc(tmp_path, doc, "empty.json"))
    assert "ccfGroups" not in core.analysis
    assert kinds(core, "analysis_invalid") == []
    out = tmp_path / "empty_saved.json"
    assert core.save_to_json(str(out))[0]
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert "ccfGroups" not in saved["analysis"]
    assert "fileFormatVersion" not in saved


@pytest.mark.parametrize("source", ["sampleFTA", "r1_without_groups"])
def test_a_file_without_groups_is_saved_byte_for_byte_as_1_8_1(tmp_path, repo_root, source):
    """1.8.1 wrote ``title, date, mode, tree, analysis`` (``WebCore.prepare_export_data``)
    with ``json.dump(indent=2, ensure_ascii=False)``; nothing is added."""
    from FTA_Editor_core import FTACore

    from fta_web import engine

    if source == "sampleFTA":
        path = repo_root / "fta_web" / "examples" / "sampleFTA.json"
    else:
        path = M.write_doc(tmp_path, M.document(M.r1_tree(), None), "r1_plain.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    core = load(path)
    out = tmp_path / "plain_saved.json"
    assert core.save_to_json(str(out))[0]

    expected = FTACore.prepare_export_data(core)  # title, date, mode, tree
    expected["analysis"] = engine.coerce_analysis(raw.get("analysis"))[0]
    # The core writes in text mode: Windows ends lines with CR LF, in 1.8.1 as now.
    written = out.read_bytes().replace(b"\r\n", b"\n")
    assert written == json.dumps(expected, indent=2, ensure_ascii=False).encode("utf-8")
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert list(saved) == ["title", "date", "mode", "tree", "analysis"]
    assert "fileFormatVersion" not in saved
    assert "ccfGroups" not in saved["analysis"]


def test_a_group_file_gets_version_2_and_keeps_the_groups_after_a_second_load(tmp_path):
    groups = [M.group()]
    core = load(M.write_doc(tmp_path, M.document(M.r1_tree(), groups, version=None), "a.json"))
    out = tmp_path / "b.json"
    assert core.save_to_json(str(out))[0]
    again = load(out)
    assert again.analysis["ccfGroups"] == groups
    assert json.loads(out.read_text(encoding="utf-8"))["fileFormatVersion"] == 2


@pytest.mark.parametrize("version", [3, 2.5, 99])
def test_a_newer_file_format_opens_with_the_warning_and_saves_as_version_2(tmp_path, version):
    doc = M.document(M.r1_tree(), [M.group()], version=version)
    core = load(M.write_doc(tmp_path, doc, "newer.json"))
    newer = kinds(core, "newer_format")
    assert len(newer) == 1
    assert newer[0]["message"] == NEWER  # exact, no final period
    assert newer[0]["old_id"] is None and newer[0]["new_id"] is None
    out = tmp_path / "newer_saved.json"
    assert core.save_to_json(str(out))[0]
    assert json.loads(out.read_text(encoding="utf-8"))["fileFormatVersion"] == 2


@pytest.mark.parametrize("version", [1, 2, True, "3", None])
def test_versions_up_to_2_or_not_numbers_give_no_newer_warning(tmp_path, version):
    doc = M.document(M.r1_tree(), [M.group()], version=version)
    if version is None:
        doc.pop("fileFormatVersion", None)
    core = load(M.write_doc(tmp_path, doc, "older.json"))
    assert kinds(core, "newer_format") == []


def test_the_newer_format_warning_reaches_the_open_response_and_the_validation_tab(api):
    body = api.open_doc(M.document(M.r1_tree(), [M.group()], version=3), "newer.json")
    assert any(w.get("message") == NEWER for w in body["warnings"])
    status, validate = api.get("/api/analysis/validate")
    assert status == 200
    repairs = [i for i in validate["issues"] if i["code"] == "LOAD_REPAIR" and i["message"] == NEWER]
    assert len(repairs) == 1
    assert repairs[0]["severity"] == "warning"
