"""F2 T5 follow-up (text review): the wording of the CCF part of the DOCX report and
of the CLI text output.

* beta in the Parameters cell is printed with three significant figures (1/3 reads
  0.333, 0.1 reads 0.1);
* the Japanese headline bracket joins "MCUB" and "CCF を含む" with "、", the English one
  keeps ", ";
* a group that is not applied gets the lint fix after the fixed FN-25 sentence, and an
  ETA document gets the switch-mode hint;
* the CLI ``mc`` text output says that beta and alpha are not sampled, and the text output
  of ``cutsets`` / ``importance`` / ``mc`` says "CCF: incomplete, CCF not included" when the
  headline is incomplete.
"""
import copy
import io

import pytest

docx = pytest.importorskip("docx")

NOTE_SAMPLING = "β and α are not sampled in Monte Carlo."


def _leaf(node_id, q=1e-3):
    return {"id": node_id, "name": "Pump %s" % node_id, "type": "Event", "logicGate": "OR",
            "probability": q, "notes": "", "links": [], "children": [],
            "quant": {"model": "fixed"}}


def _tree(q_b=1e-3):
    return {"id": "root", "name": "Top event %s" % q_b, "type": "Root", "logicGate": "AND",
            "probability": 1.0, "notes": "", "links": [],
            "children": [_leaf("A"), _leaf("B", q_b)]}


def _group(beta=0.1):
    return {"id": "g1", "name": "Feed pumps", "model": "beta", "beta": beta, "alpha": None,
            "testing": None, "members": ["A", "B"], "source": "test"}


def _report(tree, beta=0.1, lang="en", mode="FTA"):
    from fta_web import report_docx

    snapshot = report_docx.DocSnapshot(
        copy.deepcopy(tree), {"ccfGroups": [_group(beta)]},
        {"title": "T", "date": "", "mode": mode})
    options = report_docx.normalize_options({"lang": lang, "sections": ["headline"]})
    data = report_docx.collect_report_data(snapshot, [], options)
    blob = report_docx.build_report(data, options)
    document = docx.Document(io.BytesIO(blob))
    paragraphs = [p.text for p in document.paragraphs]
    tables = [[[c.text for c in row.cells] for row in table.rows] for table in document.tables]
    return paragraphs, tables


def _parameters_cell(tables):
    (table,) = [t for t in tables if t and ("Parameters" in t[0] or "パラメータ" in t[0])]
    return table[1][2]


def test_beta_in_the_parameters_cell_has_three_significant_figures():
    _paragraphs, tables = _report(_tree(), beta=1 / 3)
    assert _parameters_cell(tables) == "β = 0.333"
    _paragraphs, tables = _report(_tree(), beta=0.1)
    assert _parameters_cell(tables) == "β = 0.1"


def test_a_beta_that_is_not_a_number_is_printed_as_stored():
    from fta_web import report_docx

    assert report_docx._beta_text("abc") == "abc"
    assert report_docx._beta_text(None) == "None"
    assert report_docx._beta_text(True) == "True"


def test_the_headline_bracket_uses_the_language_separator():
    en, _ = _report(_tree(), lang="en")
    ja, _ = _report(_tree(), lang="ja")
    assert any("[MCUB (min-cut upper bound), includes CCF (1 group)]" in p for p in en)
    assert any("、CCF を含む（1 グループ）]" in p for p in ja)
    assert not any("), CCF を含む" in p for p in ja)


def test_a_group_that_is_not_applied_gets_its_fix_after_the_fixed_sentence():
    from fta_web import ccf

    tree = _tree(q_b=2e-3)  # Pump B differs from Pump A: CCF_MEMBERS_DIFFER
    (assessment,) = ccf.assess([_group()], tree, {}, "FTA")
    for lang in ("en", "ja"):
        paragraphs, _tables = _report(tree, lang=lang)
        fix = assessment.primary.text()[lang]["fix"]
        (line,) = [p for p in paragraphs if p.startswith("Feed pumps: ")]
        # the fixed sentence is followed by the lint fix of the code
        assert fix and line.endswith(("" if lang == "ja" else " ") + fix), line


def test_the_fixed_fn_25_sentence_is_unchanged_with_the_fix_appended():
    paragraphs, _tables = _report(_tree(q_b=2e-3))
    (line,) = [p for p in paragraphs if p.startswith("Feed pumps: ")]
    assert 'Not applied: "Pump B" differs from "Pump A". Results exclude this group.' in line


def test_an_eta_document_gets_the_switch_mode_hint():
    paragraphs, _tables = _report(_tree(), mode="ETA")
    assert any(p.endswith("Not applied: ETA mode. Results exclude this group. "
                          "Switch the document to fault-tree mode to apply the group.")
               for p in paragraphs)
    paragraphs, _tables = _report(_tree(), mode="ETA", lang="ja")
    assert any(p.endswith("グループを適用するには、文書を故障の木モードにしてください。")
               for p in paragraphs)


# ---------------------------------------------------------------- CLI text


def _write(tmp_path, tree):
    import json

    doc = {"title": "CLI", "date": "2026-10-28", "mode": "FTA", "fileFormatVersion": 2,
           "tree": tree, "analysis": {"ccfGroups": [_group()]}}
    path = tmp_path / "doc.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_cli_mc_text_says_beta_and_alpha_are_not_sampled(capsys, tmp_path):
    from fta_web import cli

    tree = _tree()
    for leaf in tree["children"]:
        leaf["quant"] = {"model": "fixed", "unc": {"dist": "lognormal", "median": 1e-3, "ef": 3}}
    code = cli.main(["mc", _write(tmp_path, tree), "--n", "300", "--seed", "3",
                     "--time-limit", "3600"])
    out = capsys.readouterr().out.splitlines()
    assert code == 0
    assert NOTE_SAMPLING in out
    code = cli.main(["mc", _write(tmp_path, tree), "--json", "--n", "300", "--seed", "3",
                     "--time-limit", "3600"])
    assert "Note" not in capsys.readouterr().out  # --json is unchanged data


@pytest.mark.parametrize("command", ["cutsets", "importance", "mc"])
def test_cli_text_of_an_incomplete_headline_says_so(capsys, tmp_path, monkeypatch, command):
    from fta_web import cli, engine

    monkeypatch.setitem(engine.SUMMARY_LIMITS, "maxCount", 1)
    extra = ["--n", "200", "--seed", "1", "--time-limit", "3600"] if command == "mc" else []
    code = cli.main([command, _write(tmp_path, _tree()), *extra])
    captured = capsys.readouterr()
    assert code == 1
    assert "CCF: incomplete, CCF not included" in captured.out.splitlines()
    assert "incomplete" in captured.err


@pytest.mark.parametrize("command", ["cutsets", "importance", "mc"])
def test_cli_text_of_an_incomplete_headline_names_the_summary_limit(capsys, tmp_path, monkeypatch, command):
    """R4 (engineering concern C2): the line says the headline comes from the quick
    summary and its limits, not from the command's own run; exit code 1 and --json unchanged."""
    import json

    from fta_web import cli, engine

    monkeypatch.setitem(engine.SUMMARY_LIMITS, "maxCount", 1)
    extra = ["--n", "200", "--seed", "1", "--time-limit", "3600"] if command == "mc" else []
    path = _write(tmp_path, _tree())
    code = cli.main([command, path, *extra])
    captured = capsys.readouterr()
    assert code == 1
    lines = captured.out.splitlines()
    at = lines.index("CCF: incomplete, CCF not included")
    assert lines[at + 1] == cli.SUMMARY_LIMIT_NOTE
    assert "not from this command's run" in cli.SUMMARY_LIMIT_NOTE
    assert cli.SUMMARY_LIMIT_NOTE in captured.err
    # --json carries the data only, no sentence, and the exit code is the same
    code_json = cli.main([command, path, "--json", *extra])
    out = capsys.readouterr().out
    assert code_json == 1
    assert json.loads(out)  # still plain JSON
    assert cli.SUMMARY_LIMIT_NOTE not in out


def test_the_summary_limit_note_names_the_real_limits():
    from fta_web import cli, engine

    assert engine.SUMMARY_LIMITS["timeBudgetS"] == 2.0 and "2 s" in cli.SUMMARY_LIMIT_NOTE
    assert engine.SUMMARY_LIMITS["maxCount"] == 2000 and "2000 cut sets" in cli.SUMMARY_LIMIT_NOTE


@pytest.mark.parametrize("command", ["cutsets", "importance", "mc"])
def test_cli_text_of_a_complete_result_has_no_incomplete_line(capsys, tmp_path, command):
    from fta_web import cli

    extra = ["--n", "200", "--seed", "1", "--time-limit", "3600"] if command == "mc" else []
    code = cli.main([command, _write(tmp_path, _tree()), *extra])
    out = capsys.readouterr().out
    assert code == 0
    assert "incomplete" not in out
