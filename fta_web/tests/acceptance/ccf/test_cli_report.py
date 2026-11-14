"""F2 BRIEF criteria 13, 14 and 15 (FN-25, FN-26, FN-67): the DOCX report and the CLI.

Criterion 13: the DOCX of the R1 file and of a file with one not-applied group
contains every item of FN-25 -- per group the name, model, parameters, testing
scheme, source, members and status; the formulas with their sources and pages;
the six assumptions of UI-7; the overlapping-events note; the FN-67 note;
``Not applied: <reason>. Results exclude this group.``; the headline line; the
CCF events in the cut-set and importance tables (en and ja).

Criterion 14: ``quantify``, ``cutsets``, ``importance`` and ``mc`` with ``--json``
give the API's numbers on the R1 file and add the ``ccf`` block; exit codes as
FN-26 (FTA and ETA mode); a file without groups gets no ``ccf`` block.

Criterion 15 (the report and CLI parts): the note of FN-67 is in the DOCX and
in ``ccf.note``.
"""
import json

import pytest

import _ccf_models as M

FOUR = ["quantify", "cutsets", "importance", "mc"]
MC_ARGS = ["--n", "1000", "--seed", "5", "--time-limit", "3600"]


def differing_tree(tag=""):
    """R1 with Pump B at 2e-3: the group (A, B) is not applied (CCF_MEMBERS_DIFFER)."""
    tree = M.r1_tree(tag)
    tree["children"][0]["children"][1]["probability"] = 2e-3
    return tree


def not_applied_doc(tag=""):
    return M.document(differing_tree(tag), [M.group()])


NOT_APPLIED_REASON = '"Pump B" differs from "Pump A"'
NOT_APPLIED_REASON_JA = "「Pump B」が「Pump A」と異なります"


@pytest.fixture
def summary_cap(monkeypatch):
    from fta_web import engine

    monkeypatch.setitem(engine.SUMMARY_LIMITS, "maxCount", 1)


def report(api, lang="en", **extra):
    status, blob = api.binary("POST", "/api/report/docx", json=dict({"lang": lang}, **extra))
    assert status == 200, blob[:300]
    return M.docx_text(blob)


def group_table(tables):
    found = [t for t in tables if t and "Testing scheme" in t[0]]
    assert len(found) == 1, "no per-group table with a Testing scheme column"
    return found[0]


# ---------------------------------------------------------------- criterion 13

CITATIONS = [
    "NUREG/CR-4780 Vol. 2", "Table C-1", "p. C-5", "Eq. C.10-C.13", "p. C-6",
    "NUREG/CR-5485", "Eq. 5.11-5.13", "p. 42", "NASA/SP-2011-3421", "p. D-20",
]


def test_docx_of_the_r1_file_has_every_fn_25_item(api):
    api.open_doc(M.document(M.r1_tree(), [M.group()]))
    text, cells, tables = report(api)

    assert "Common-cause failure (CCF) groups" in text
    table = group_table(tables)
    header = table[0]
    for column in ("Name", "Model", "Parameters", "Testing scheme", "Source", "Members", "Status"):
        assert column in header, header
    (row,) = table[1:]
    cell = dict(zip(header, row))
    assert cell["Name"] == "Feed pumps"
    assert "beta" in cell["Model"].lower()
    assert "0.1" in cell["Parameters"]
    assert cell["Testing scheme"] == "—"  # a beta group has none
    assert cell["Source"] == "test"
    assert "Pump A" in cell["Members"] and "Pump B" in cell["Members"]
    assert "Applied" in cell["Status"] and "Not applied" not in cell["Status"]

    for citation in CITATIONS:  # the formulas with their sources and pages
        assert citation in text, citation
    for sentence in M.ASSUMPTIONS_EN.values():  # the six sentences of UI-7
        assert sentence in text, sentence
    assert M.OVERLAP_EN in text
    assert M.NOTE_EN in text  # FN-67
    assert "includes CCF (1 group)" in text  # the headline line
    assert "incomplete, CCF not included" not in text
    assert "Not applied" not in text

    ccf_cells = [c for c in cells if "CCF: Feed pumps" in c]
    independent_cells = [c for c in cells if "Pump A (independent part)" in c]
    assert len(ccf_cells) >= 2  # the cut-set table and the importance table
    assert len(independent_cells) >= 2

    def tables_with(label):
        return [t for t in tables if any(label in cell for row in t for cell in row)]

    # Two different tables carry each label (the cut-set table and the importance table), not
    # two cells of one table.
    assert len(tables_with("CCF: Feed pumps")) >= 2
    assert len(tables_with("Pump A (independent part)")) >= 2


def test_docx_of_a_file_with_one_not_applied_group_has_the_not_applied_line(api):
    api.open_doc(not_applied_doc("report not applied"))
    text, cells, tables = report(api)
    assert "Common-cause failure (CCF) groups" in text
    (row,) = group_table(tables)[1:]
    assert "Not applied: %s" % NOT_APPLIED_REASON in row[-1]
    assert 'Not applied: %s. Results exclude this group.' % NOT_APPLIED_REASON in text
    for sentence in M.ASSUMPTIONS_EN.values():
        assert sentence in text
    for citation in CITATIONS:
        assert citation in text
    assert M.OVERLAP_EN in text and M.NOTE_EN in text
    assert "includes CCF" not in text  # nothing was applied: the 1.8.1 headline
    assert not [c for c in cells if "CCF: Feed pumps" in c]
    assert "(independent part)" not in text


def test_docx_headline_says_incomplete_with_the_reason_when_the_cut_sets_are_cut_short(
        api, summary_cap):
    api.open_doc(M.document(M.r1_tree("report incomplete"), [M.group()]))
    text, _cells, _tables = report(api)
    assert "incomplete, CCF not included" in text
    assert "tree walk, without CCF; cut sets cut short (summary cap)" in text
    assert "includes CCF (1 group)" not in text


def test_the_ccf_section_is_in_the_report_even_when_it_is_not_one_of_the_chosen_sections(api):
    api.open_doc(not_applied_doc("report one section"))
    text, _cells, _tables = report(api, sections=["headline"])
    assert 'Not applied: %s. Results exclude this group.' % NOT_APPLIED_REASON in text
    assert M.NOTE_EN in text


def test_the_monte_carlo_part_of_the_report_says_beta_and_alpha_are_not_sampled(api):
    api.open_doc(M.document(M.r11_tree(), [M.group()]))
    text, _cells, _tables = report(
        api, sections=["headline", "uncertainty"], runUncertainty=True, uncertaintyN=300)
    assert M.ASSUMPTIONS_EN["sampling"] in text
    assert "Monte Carlo" in text


def test_in_eta_mode_the_report_lists_the_groups_as_not_applied(api):
    api.open_doc(M.document(M.r1_tree(), [M.group()], mode="ETA"))
    text, _cells, tables = report(api)
    assert "Common-cause failure (CCF) groups" in text
    assert "Not applied: ETA mode" in text
    assert M.NOTE_EN in text


def test_docx_in_japanese_has_the_same_items(api):
    api.open_doc(M.document(M.r1_tree(), [M.group()]))
    text, cells, tables = report(api, "ja")
    assert "共通原因故障（CCF）グループ" in text
    assert "試験方式" in group_table_ja(tables)[0]
    for sentence in M.ASSUMPTIONS_JA.values():
        assert sentence in text, sentence
    assert M.OVERLAP_JA in text
    assert M.NOTE_JA in text
    assert "適用中" in text
    for citation in ("NUREG/CR-4780", "NUREG/CR-5485", "NASA/SP-2011-3421", "p. D-20"):
        assert citation in text
    assert any("CCF: Feed pumps" in c for c in cells)
    assert any("Pump A（独立部分）" in c for c in cells)


def group_table_ja(tables):
    found = [t for t in tables if t and "試験方式" in t[0]]
    assert len(found) == 1
    return found[0]


def test_docx_in_japanese_has_the_not_applied_line(api):
    api.open_doc(not_applied_doc("report not applied ja"))
    text, _cells, _tables = report(api, "ja")
    assert "未適用: %s。結果にはこのグループは含まれていません。" % NOT_APPLIED_REASON_JA in text


def test_a_report_of_a_file_without_groups_has_no_ccf_section(api):
    api.open_doc(M.document(M.r1_tree(), None))
    text, _cells, tables = report(api)
    assert "Common-cause failure" not in text
    assert M.NOTE_EN not in text
    assert not [t for t in tables if t and "Testing scheme" in t[0]]


# ---------------------------------------------------------------- criterion 14


def run_json(cli_run, command, path, *extra):
    code, out, err = cli_run(command, path, "--json", *extra)
    return code, (json.loads(out) if out.strip() else None), err


def r1_file(tmp_path, name="r1.json", **kwargs):
    return M.write_doc(tmp_path, M.document(M.r1_tree(), [M.group()], **kwargs), name)


def test_cli_quantify_equals_the_api_summary_and_adds_the_ccf_block(api, cli_run, tmp_path):
    path = r1_file(tmp_path)
    api.open_doc(M.document(M.r1_tree(), [M.group()]), "api.json")
    status, summary = api.get("/api/analysis/summary")
    assert status == 200
    code, entry, _ = run_json(cli_run, "quantify", path)
    assert code == 0
    results = entry["results"]
    expected = M.strip_keys({k: v for k, v in summary.items() if k not in ("ok", "ccf")})
    assert M.strip_keys({k: v for k, v in results["summary"].items() if k != "ccf"}) == expected
    assert results["ccf"] == summary["ccf"]
    assert results["ccf"]["applied"][0]["id"] == "g1"
    assert results["ccf"]["notApplied"] == []
    assert results["ccf"]["note"] == M.NOTE_EN  # FN-67
    assert results["summary"]["headline"] == M.rel(1.00809919e-4, 1e-9)


def test_cli_cutsets_equals_the_api(api, cli_run, tmp_path):
    path = r1_file(tmp_path)
    api.open_doc(M.document(M.r1_tree(), [M.group()]), "api.json")
    status, body = api.post("/api/analysis/cutsets", {})
    assert status == 200
    code, entry, _ = run_json(cli_run, "cutsets", path)
    assert code == 0
    results = entry["results"]
    drop = {"ok", "returned", "elapsedMs"}
    assert M.strip_keys(results) == M.strip_keys({k: v for k, v in body.items() if k not in drop})
    assert results["ccf"] == body["ccf"] and results["ccf"]["note"] == M.NOTE_EN
    assert sorted(M.cut_set_ids(results)) == [["A", "B"], ["ccf:g1"]]


def test_cli_importance_equals_the_api(api, cli_run, tmp_path):
    path = r1_file(tmp_path)
    api.open_doc(M.document(M.r1_tree(), [M.group()]), "api.json")
    status, body = api.post("/api/analysis/importance", {})
    assert status == 200
    code, entry, _ = run_json(cli_run, "importance", path)
    assert code == 0
    results = entry["results"]
    key = lambda row: row["id"]  # noqa: E731
    assert sorted(results["measures"], key=key) == sorted(body["events"], key=key)
    assert results["ccf"] == body["ccf"]
    row = [m for m in results["measures"] if m["id"] == "ccf:g1"][0]
    assert row["birnbaum"] == M.rel(0.99999919, 1e-9)


def test_cli_mc_equals_the_api(api, cli_run, tmp_path):
    path = M.write_doc(tmp_path, M.document(M.r11_tree(), [M.group()]), "r11.json")
    api.open_doc(M.document(M.r11_tree(), [M.group()]), "api.json")
    status, body = api.post("/api/analysis/uncertainty", {"n": 1000, "seed": 5})
    assert status == 200
    code, entry, _ = run_json(cli_run, "mc", path, *MC_ARGS)
    assert code == 0
    results = entry["results"]
    for key in ("mean", "median", "p05", "p95", "std", "pointEstimate", "completed", "seed",
                "method", "uncertainEvents", "certainEvents", "ccfSampling"):
        assert results[key] == body[key], key
    assert results["ccf"] == body["ccf"]
    assert results["ccfSampling"]["note"] == "β and α are not sampled in Monte Carlo."


@pytest.mark.parametrize("command", FOUR)
def test_exit_code_0_when_every_group_is_applied(cli_run, tmp_path, command):
    extra = MC_ARGS if command == "mc" else []
    code, entry, _ = run_json(cli_run, command, r1_file(tmp_path), *extra)
    assert code == 0
    assert entry["results"]["ccf"]["notApplied"] == []


@pytest.mark.parametrize("command", FOUR)
def test_exit_code_1_when_a_group_is_not_applied(cli_run, tmp_path, command):
    path = M.write_doc(tmp_path, not_applied_doc("cli not applied"), "bad.json")
    extra = MC_ARGS if command == "mc" else []
    code, entry, _ = run_json(cli_run, command, path, *extra)
    assert code == 1
    block = entry["results"]["ccf"]
    assert block["applied"] == []
    assert block["notApplied"] == [{"id": "g1", "name": "Feed pumps",
                                    "code": "CCF_MEMBERS_DIFFER", "reason": NOT_APPLIED_REASON}]
    assert block["note"] == M.NOTE_EN


@pytest.mark.parametrize("command", FOUR)
def test_exit_code_1_when_the_headline_is_incomplete(cli_run, tmp_path, command, summary_cap):
    path = M.write_doc(tmp_path, M.document(M.r1_tree("cli incomplete"), [M.group()]), "cap.json")
    extra = MC_ARGS if command == "mc" else []
    code, entry, _ = run_json(cli_run, command, path, *extra)
    assert code == 1
    assert entry["results"]["ccf"]["notApplied"] == []  # all applied, yet the result is cut short
    if command == "quantify":
        assert entry["results"]["summary"]["headlineMethod"] == "incomplete"
        assert entry["results"]["summary"]["headline"] is None


def test_eta_mode_quantify_lists_every_group_as_eta_mode_and_exits_0(cli_run, tmp_path):
    path = M.write_doc(tmp_path, M.document(M.r1_tree(), [M.group(), M.group(
        "g2", "Second", ["A", "B"])], mode="ETA"), "eta.json")
    code, entry, _ = run_json(cli_run, "quantify", path)
    assert code == 0
    block = entry["results"]["ccf"]
    assert block["applied"] == []
    assert [(g["id"], g["code"], g["reason"]) for g in block["notApplied"]] == [
        ("g1", "CCF_ETA_MODE", "ETA mode"), ("g2", "CCF_ETA_MODE", "ETA mode")]
    assert block["note"] == M.NOTE_EN


@pytest.mark.parametrize("command", ["cutsets", "importance", "mc"])
def test_eta_mode_refusal_has_the_same_exit_code_with_or_without_the_group(
        cli_run, tmp_path, command):
    with_group = M.write_doc(tmp_path, M.document(M.r1_tree(), [M.group()], mode="ETA"), "g.json")
    plain = M.write_doc(tmp_path, M.document(M.r1_tree(), None, mode="ETA"), "p.json")
    extra = MC_ARGS if command == "mc" else []
    code_with = cli_run(command, with_group, "--json", *extra)[0]
    code_plain = cli_run(command, plain, "--json", *extra)[0]
    assert code_with == code_plain == 1  # the existing refusal, groups never change it


@pytest.mark.parametrize("command", FOUR + ["validate"])
@pytest.mark.parametrize("mode", ["FTA", "ETA"])
def test_a_file_without_groups_gets_no_ccf_block(cli_run, tmp_path, command, mode):
    path = M.write_doc(tmp_path, M.document(M.r1_tree(), None, mode=mode, title="Plain"), "plain.json")
    extra = MC_ARGS if command == "mc" else []
    code, entry, _ = run_json(cli_run, command, path, *extra)
    assert "ccf" not in json.dumps(entry).lower()  # no ccf key, no ccf text anywhere
    assert "ccf" not in (entry.get("results") or {})


@pytest.mark.parametrize("command", FOUR)
def test_text_output_prints_a_line_per_not_applied_group_and_the_note(cli_run, tmp_path, command):
    path = M.write_doc(tmp_path, not_applied_doc("cli text"), "bad.json")
    extra = MC_ARGS if command == "mc" else []
    code, out, _err = cli_run(command, path, *extra)
    assert code == 1
    lines = out.splitlines()
    assert ('CCF group not applied: Feed pumps (g1): %s' % NOT_APPLIED_REASON) in lines
    assert "Note: %s" % M.NOTE_EN in lines


@pytest.mark.parametrize("command", FOUR)
def test_text_output_of_applied_groups_has_the_note_and_no_not_applied_line(
        cli_run, tmp_path, command):
    extra = MC_ARGS if command == "mc" else []
    code, out, _err = cli_run(command, r1_file(tmp_path), *extra)
    assert code == 0
    assert "Note: %s" % M.NOTE_EN in out.splitlines()
    assert "CCF group not applied" not in out


def test_text_output_of_an_incomplete_headline_says_so(cli_run, tmp_path, summary_cap):
    path = M.write_doc(tmp_path, M.document(M.r1_tree("cli text incomplete"), [M.group()]), "cap.json")
    code, out, _err = cli_run("quantify", path)
    assert code == 1
    lines = out.splitlines()
    assert "Top event: —  (incomplete)" in lines
    assert "CCF: incomplete, CCF not included" in lines


def test_a_file_without_groups_prints_no_ccf_line(cli_run, tmp_path):
    path = M.write_doc(tmp_path, M.document(M.r1_tree(), None, title="Plain"), "plain.json")
    code, out, _err = cli_run("quantify", path)
    assert code == 0
    assert "CCF" not in out and "Note:" not in out


def test_the_subprocess_entry_point_gives_the_same_exit_codes(tmp_path, repo_root):
    """The real entry point (``fta_web/run.py``) and not only ``cli.main``."""
    import os
    import subprocess
    import sys

    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    run = repo_root / "fta_web" / "run.py"
    good = r1_file(tmp_path, "good.json")
    bad = M.write_doc(tmp_path, not_applied_doc("subprocess"), "bad.json")
    codes = []
    for path in (good, bad):
        proc = subprocess.run([sys.executable, str(run), "cutsets", str(path), "--json"],
                              capture_output=True, text=True, encoding="utf-8", cwd=str(repo_root),
                              env=env, timeout=120)
        codes.append(proc.returncode)
        assert json.loads(proc.stdout)["results"]["ccf"]["note"] == M.NOTE_EN
    assert codes == [0, 1]
