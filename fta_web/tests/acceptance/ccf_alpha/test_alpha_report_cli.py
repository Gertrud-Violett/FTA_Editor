"""F2A BRIEF criterion 8 (FN-25, FN-41, FN-42, SPEC 7.3): the alpha parts of the report and the CLI.

* the DOCX CCF section: Model cell, Parameters cell ``α = (...)`` (stored values), the Testing
  scheme column, the normalisation sum, the alpha formulas with source and page, the
  ``assume.alpha`` bullet (only with an alpha group), the overlap line for groups of 3 or 4
  members (not for 2), the subset labels ``CCF: <group> (<names>)`` in the cut-set table, the
  Not applied line; Japanese equivalents; an F2 beta-only report is unchanged;
* the CLI ``ccf`` block: ``alpha``, ``testing``, ``alphaSum``, ``alphaNormalised`` on applied
  alpha items, equal to the API's, exit 1 for a missing scheme, exit 0 for a normalised group;
* ``docs/CCF.md`` has the alpha formulas with pages, the source errors not to copy and R5 to
  R10h; the docstring of the alpha model cites source and page of every formula.
"""
import json
import re

import pytest

import _alpha_models as M

NAME = M.GROUP_NAME
NOTE_EN = "Check CCF results with a qualified engineer before use."
MC_ARGS = ["--n", "1000", "--seed", "5", "--time-limit", "3600"]
FOUR = ["quantify", "cutsets", "importance", "mc"]


def doc3(alpha=M.ALPHA3, testing="staggered"):
    return M.alpha_document(("A", "B", "C"), alpha, testing)


def doc4(testing="nonStaggered"):
    return M.alpha_document(("A", "B", "C", "D"), M.PERF_ALPHA, testing)


def doc2():
    return M.alpha_document(("A", "B"), (0.9, 0.1), "staggered")


def report(api, lang="en", **extra):
    status, blob = api.binary("POST", "/api/report/docx", json=dict({"lang": lang}, **extra))
    assert status == 200, blob[:300]
    return M.docx_text(blob)


def group_table(tables, marker):
    found = [t for t in tables if t and marker in t[0]]
    assert len(found) == 1, "no per-group table with the column %r" % marker
    return found[0]


def group_row(tables, marker="Testing scheme"):
    table = group_table(tables, marker)
    return dict(zip(table[0], table[1]))


# ---------------------------------------------------------------- the DOCX, English


def test_docx_group_row_of_a_staggered_alpha_group(api):
    api.open_doc(doc3())
    text, _cells, tables = report(api)
    cell = group_row(tables)
    assert cell["Name"] == NAME
    assert cell["Model"] == "Alpha factor"
    assert "α = (0.955, 0.034, 0.011)" in cell["Parameters"]
    assert "sum" not in cell["Parameters"]                      # not normalised
    assert cell["Testing scheme"] == "Staggered testing"
    assert "Pump A" in cell["Members"] and "Pump C" in cell["Members"]
    assert "Applied" in cell["Status"] and "Not applied" not in cell["Status"]
    assert "includes CCF (1 group)" in text


def test_docx_group_row_of_a_non_staggered_group(api):
    api.open_doc(doc4("nonStaggered"))
    cell = group_row(report(api)[2])
    assert cell["Testing scheme"] == "Non-staggered testing"
    assert "α = (0.95, 0.03, 0.01, 0.01)" in cell["Parameters"]


def test_docx_parameters_cell_shows_the_original_sum_when_normalised(api):
    api.open_doc(doc3(alpha=(0.9555, 0.034, 0.011)))
    cell = group_row(report(api)[2])
    assert "α = (0.9555, 0.034, 0.011)" in cell["Parameters"]
    assert M.report_text("report.alpha.sum", "en", sum="1.0005") in cell["Parameters"]
    # DESIGN 5: the separator is "; " (no space before the semicolon)
    assert ("α = (0.9555, 0.034, 0.011); "
            + M.report_text("report.alpha.sum", "en", sum="1.0005")) in cell["Parameters"]
    assert "Applied" in cell["Status"]


def test_docx_names_the_missing_scheme_and_excludes_the_group(api):
    api.open_doc(doc3(testing=None))
    text, cells, tables = report(api)
    row = group_row(tables)
    assert row["Testing scheme"] == M.report_text("report.testing.none", "en") == "not chosen"
    assert "Not applied: testing scheme missing" in row["Status"]
    assert "Not applied: testing scheme missing. Results exclude this group." in text
    assert "includes CCF" not in text
    assert not [c for c in cells if "CCF: %s" % NAME in c]


def test_docx_has_the_alpha_formulas_with_source_and_page_and_the_assumption(api):
    api.open_doc(doc3())
    text, _cells, _tables = report(api)
    for citation in ("Eq. 5.6", "p. 40", "Eq. 5.7-5.9", "p. 41", "C.23-C.24", "pp. C-10/C-11",
                     "NUREG/CR-5485", "NUREG/CR-4780 Vol. 2"):
        assert citation in text, citation
    assert M.report_text("assume.alpha", "en") in text
    for beta_formula in ("Eq. 5.11-5.13", "Table C-1"):          # the beta formulas stay
        assert beta_formula in text
    assert M.OVERLAP_EN_F2 in text                                # F2's paragraph is unchanged
    assert NOTE_EN in text


def test_the_alpha_assumption_and_overlap_line_appear_only_with_an_alpha_group(api):
    beta_doc = M.document(M.and_tree(["A", "B"]), [M.bgroup()])
    api.open_doc(beta_doc)
    text, _cells, tables = report(api)
    assert "Alpha-factor model: Q_k" not in text
    assert "(alpha," not in text
    assert group_row(tables)["Testing scheme"] == "—"
    assert M.OVERLAP_EN_F2 in text                                # F2's always-printed paragraph


@pytest.mark.parametrize("make, members", [(doc3, 3), (doc4, 4)])
def test_the_overlap_line_is_printed_for_alpha_groups_of_three_and_four(api, make, members):
    api.open_doc(make())
    text, _cells, _tables = report(api)
    assert M.report_text("report.alpha.overlap", "en", group=NAME, n=members) in text


def test_no_overlap_line_for_an_alpha_group_of_two(api):
    api.open_doc(doc2())
    text, _cells, _tables = report(api)
    assert 'Group "%s" (alpha,' % NAME not in text
    assert M.report_text("assume.alpha", "en") in text            # still an alpha group
    assert M.OVERLAP_EN_F2 in text


def test_no_overlap_line_for_a_not_applied_group_of_three(api):
    # a group that is not applied has no CCF events, so no cut set of it "is kept"
    api.open_doc(doc3(testing=None))
    text, _cells, _tables = report(api)
    assert 'Group "%s" (alpha,' % NAME not in text
    assert M.OVERLAP_EN_F2 in text


def test_cut_set_and_importance_tables_use_the_subset_labels(api):
    api.open_doc(doc3())
    _text, cells, tables = report(api)
    pair = "CCF: %s (Pump A + Pump B)" % NAME
    triple = "CCF: %s (Pump A + Pump B + Pump C)" % NAME
    assert [c for c in cells if pair in c]
    assert [c for c in cells if triple in c]
    assert [c for c in cells if "Pump A (independent part)" in c]

    def tables_with(label):
        return [t for t in tables if any(label in cell for row in t for cell in row)]

    assert len(tables_with(pair)) >= 2          # the cut-set table and the importance table


# ---------------------------------------------------------------- the DOCX, Japanese


def test_docx_in_japanese(api):
    api.open_doc(doc3(alpha=(0.9555, 0.034, 0.011)))
    text, cells, tables = report(api, "ja")
    row = group_row(tables, "試験方式")
    assert row["モデル"] == "アルファファクター"
    assert "α = (0.9555, 0.034, 0.011)" in row["パラメータ"]
    assert M.report_text("report.alpha.sum", "ja", sum="1.0005") in row["パラメータ"]
    assert ("α = (0.9555, 0.034, 0.011); "
            + M.report_text("report.alpha.sum", "ja", sum="1.0005")) in row["パラメータ"]
    assert row["試験方式"] == M.report_text("report.testing.staggered", "ja") == "時間差試験"
    assert M.report_text("assume.alpha", "ja") in text
    assert M.report_text("report.alpha.overlap", "ja", group=NAME, n=3) in text
    assert any("CCF: %s（Pump A + Pump B）" % NAME in c for c in cells)
    # DESIGN 6: one Japanese term, アルファファクター. (F2's pinned overlap paragraph uses it too,
    # so the term is not forbidden in the whole text; the wrong spellings are.)
    assert "α ファクター" not in text and "α モデル" not in text


def test_docx_in_japanese_names_the_missing_scheme(api):
    api.open_doc(doc3(testing=None))
    text, _cells, tables = report(api, "ja")
    assert group_row(tables, "試験方式")["試験方式"] == "未選択"
    assert "未適用: 試験方式が未指定。結果にはこのグループは含まれていません。" in text


def test_a_non_staggered_group_in_japanese_reads_同時試験(api):
    api.open_doc(doc4("nonStaggered"))
    row = group_row(report(api, "ja")[2], "試験方式")
    assert row["試験方式"] == "同時試験"


def test_the_alpha_report_text_has_no_fn64_word_in_either_language(api):
    """FN-64 over the whole DOCX text (alpha group with a normalisation note, en and ja) and over
    a report of a group without a scheme."""
    en_texts, ja_texts = [], []
    for doc in (doc3(alpha=(0.9555, 0.034, 0.011)), doc4("nonStaggered"), doc3(testing=None)):
        api.open_doc(doc)
        en_texts.append(report(api, "en")[0])
        ja_texts.append(report(api, "ja")[0])
    assert all(len(t) > 500 for t in en_texts + ja_texts)
    assert M.fn64_hits(en_texts, ja_texts) == []
    assert M.fn64_hits(["The report complies with"], []) != []        # the search itself


# ---------------------------------------------------------------- the CLI


def run_json(cli_run, command, path, *extra):
    code, out, err = cli_run(command, path, "--json", *extra)
    return code, (json.loads(out) if out.strip() else None), err


def cli_file(tmp_path, doc, name="alpha.json"):
    return M.write_doc(tmp_path, doc, name)


def test_cli_quantify_ccf_block_has_the_alpha_keys_and_equals_the_api(api, cli_run, tmp_path):
    doc = doc3(alpha=(0.9555, 0.034, 0.011))
    path = cli_file(tmp_path, doc)
    api.open_doc(doc, "api.json")
    status, summary = api.get("/api/analysis/summary")
    assert status == 200
    code, entry, _ = run_json(cli_run, "quantify", path)
    assert code == 0
    block = entry["results"]["ccf"]
    assert block == summary["ccf"]
    (item,) = block["applied"]
    assert item["id"] == "g1" and item["model"] == "alpha" and item["beta"] is None
    assert item["alpha"] == [0.9555, 0.034, 0.011]
    assert item["testing"] == "staggered"
    assert item["alphaSum"] == pytest.approx(1.0005, rel=1e-12, abs=0.0)
    assert item["alphaNormalised"] is True
    assert block["notApplied"] == [] and block["note"] == NOTE_EN


def test_cli_block_of_a_group_with_sum_one_is_not_normalised(cli_run, tmp_path):
    code, entry, _ = run_json(cli_run, "quantify", cli_file(tmp_path, doc3()))
    assert code == 0
    (item,) = entry["results"]["ccf"]["applied"]
    assert item["alphaNormalised"] is False
    assert item["alphaSum"] == pytest.approx(1.0, rel=1e-12, abs=0.0)


def test_cli_cutsets_lists_the_subset_events(cli_run, tmp_path):
    code, entry, _ = run_json(cli_run, "cutsets", cli_file(tmp_path, doc3()))
    assert code == 0
    ids = {e["id"] for cs in entry["results"]["cutSets"] for e in cs["events"]}
    assert {"ccf:g1:A+B", "ccf:g1:A+C", "ccf:g1:B+C", "ccf:g1:A+B+C"} <= ids


@pytest.mark.parametrize("command", FOUR)
def test_exit_code_1_for_a_missing_scheme(cli_run, tmp_path, command):
    path = cli_file(tmp_path, doc3(testing=None), "noscheme.json")
    extra = MC_ARGS if command == "mc" else []
    code, entry, _ = run_json(cli_run, command, path, *extra)
    assert code == 1
    block = entry["results"]["ccf"]
    assert block["applied"] == []
    assert block["notApplied"] == [{"id": "g1", "name": NAME, "code": "CCF_NO_TESTING",
                                    "reason": "testing scheme missing"}]


@pytest.mark.parametrize("command", FOUR)
def test_exit_code_0_for_a_normalised_group(cli_run, tmp_path, command):
    path = cli_file(tmp_path, doc3(alpha=(0.9555, 0.034, 0.011)), "norm.json")
    extra = MC_ARGS if command == "mc" else []
    code, entry, _ = run_json(cli_run, command, path, *extra)
    assert code == 0
    (item,) = entry["results"]["ccf"]["applied"]
    assert item["alphaNormalised"] is True
    assert [w["code"] for w in item["warnings"]] == ["CCF_ALPHA_NORMALISED"]


def test_text_output_for_a_group_without_a_scheme(cli_run, tmp_path):
    path = cli_file(tmp_path, doc3(testing=None), "noscheme.json")
    code, out, _err = cli_run("quantify", path)
    assert code == 1
    lines = out.splitlines()
    assert "CCF group not applied: %s (g1): testing scheme missing" % NAME in lines
    assert "Note: %s" % NOTE_EN in lines


def test_mc_samples_neither_beta_nor_alpha(cli_run, tmp_path):
    path = cli_file(tmp_path, M.alpha_document(("A", "B"), (0.9, 0.1), "staggered"), "mc.json")
    code, entry, _ = run_json(cli_run, "mc", path, *MC_ARGS)
    assert code == 0
    assert entry["results"]["ccfSampling"]["note"] == "β and α are not sampled in Monte Carlo."


# ---------------------------------------------------------------- docs/CCF.md and the code docs


def test_docs_ccf_has_the_alpha_formulas_pages_errors_and_reference_cases(repo_root):
    text = (repo_root / "docs" / "CCF.md").read_text(encoding="utf-8")
    assert "Not in this version: the alpha-factor model" not in text
    for needle in ("Eq. 5.6", "p. 40", "Eq. 5.7", "p. 41", "C.23", "C-10", "C-11",
                   "Eq. 5.10", "Table 5-4", "Table 5-5", "Table E-2", "p. E-4",
                   "staggered", "non-staggered", "CCF_ALPHA_SIZE", "CCF_ALPHA_SUM",
                   "CCF_ALPHA_NORMALISED", "CCF_NO_TESTING"):
        assert needle in text, needle
    for label in ("R5", "R6", "R6h", "R7", "R8", "R8h", "R9", "R9h", "R10", "R10h"):
        assert re.search(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % label, text), label
    # the source errors are named as errors not to copy
    assert re.search(r"(?i)not to copy|do not copy|not copied", text)
    assert "3α3" in text or "3 α3" in text or "3*alpha3" in text.replace(" ", "") or "3·α3" in text


def test_every_alpha_formula_cites_source_and_page(repo_root):
    from fta_web import ccf

    doc = ccf.MODELS["alpha"].__doc__ or ""
    for needle in ("Eq. 5.6", "p. 40", "Eq. 5.7", "p. 41", "C.23", "C-10", "C-11"):
        assert needle in doc, needle
    source = (repo_root / "fta_web" / "ccf.py").read_text(encoding="utf-8")
    assert "Eq. 5.10" in source   # the source error that is not copied is named in the code
