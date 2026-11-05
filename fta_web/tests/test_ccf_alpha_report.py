"""F2A T2 review round 1: the CCF section of the report for hand-written alpha groups.

The report must list a group that is not applied, whatever the file stored (FN-25), and
must print the alpha values with all the digits that were stored (a published 7-digit value
such as 0.9624707 must not read 0.962471). ``alphaSum`` is a float (DESIGN 2.3).
"""
import io
import json

import pytest

from fta_web import ccf, engine, report_docx


def leaf(node_id):
    return {"id": node_id, "name": "Pump " + node_id, "type": "Event", "logicGate": "OR",
            "probability": 1e-3, "notes": "", "links": [], "children": [],
            "quant": {"model": "fixed"}}


def document(group_over, members=("A", "B", "C")):
    group = {"id": "g1", "name": "Valves", "model": "alpha", "beta": None,
             "alpha": [0.9, 0.06, 0.04], "testing": "staggered", "members": list(members),
             "source": ""}
    group.update(group_over)
    tree = {"id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "probability": 1.0,
            "notes": "", "links": [],
            "children": [{"id": "G1", "name": "Pumps", "type": "Event", "logicGate": "AND",
                          "probability": 1.0, "notes": "", "links": [],
                          "children": [leaf(i) for i in members]}]}
    return {"title": "t", "date": "2026-11-02", "mode": "FTA", "fileFormatVersion": 2,
            "tree": tree, "analysis": {"ccfGroups": [group]}}


def report(tmp_path, doc, lang="en"):
    """``(text, cells)`` of the DOCX of ``doc``, built in process."""
    import docx

    path = tmp_path / "doc.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    core = engine.WebCore()
    ok, error = core.load_from_json(str(path))
    assert ok, error
    options = report_docx.normalize_options({"lang": lang, "sections": ["headline", "cutsets"]})
    data = report_docx.collect_report_data(report_docx.DocSnapshot.of(core), [], options)
    document_ = docx.Document(io.BytesIO(report_docx.build_report(data, options)))
    cells = [c.text for table in document_.tables for row in table.rows for c in row.cells]
    text = "\n".join([p.text for p in document_.paragraphs] + cells)
    return text, cells


@pytest.mark.parametrize("model", [["x"], {"a": 1}])
def test_a_stored_model_that_is_a_list_or_a_dict_does_not_stop_the_report(tmp_path, model):
    text, _cells = report(tmp_path, document({"model": model, "beta": 0.1, "alpha": None,
                                             "testing": None}))
    assert "Not applied:" in text and "Results exclude this group." in text


def test_a_huge_stored_alpha_does_not_stop_the_report_and_prints_as_json(tmp_path):
    text, cells = report(tmp_path, document({"alpha": [10 ** 400, 0, 0]}))
    assert "Not applied:" in text
    assert any(cell.startswith("[") and "0, 0]" in cell for cell in cells)


def test_alpha_values_outside_0_1_print_as_the_json_list(tmp_path):
    _text, cells = report(tmp_path, document({"alpha": [1.5, 0, 0]}))
    assert "[1.5, 0, 0]" in cells
    assert not any(cell.startswith("α = (") for cell in cells)


def test_a_seven_digit_alpha_keeps_its_digits_in_the_parameters_cell(tmp_path):
    alpha = [0.9624707, 0.0174, 0.013, 0.00708]
    members = ("A", "B", "C", "D")
    text, cells = report(tmp_path, document({"alpha": alpha}, members))
    cell = next(c for c in cells if c.startswith("α = ("))
    assert cell == "α = (0.9624707, 0.0174, 0.013, 0.00708); sum 0.9999507, each α divided by the sum"
    assert "Applied" in text


def test_the_overlap_line_is_for_applied_groups_only(tmp_path):
    line = "any cut sets with two CCF events of this group that share a member are kept"
    assert line in report(tmp_path, document({}))[0]
    assert line not in report(tmp_path, document({"testing": None}))[0]


def test_alpha_sum_is_a_float_for_an_all_integer_list():
    group = ccf.make_group("g1", "G", None, ["A", "B"], "", model="alpha", alpha=[1, 0],
                           testing="staggered")
    tree = {"id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "probability": 1.0,
            "notes": "", "links": [], "children": [leaf("A"), leaf("B")]}
    block = ccf.block(ccf.assess([group], tree, {"ccfGroups": [group]}, "FTA"))
    (item,) = block["applied"]
    assert item["alphaSum"] == 1.0 and isinstance(item["alphaSum"], float)
    assert item["alphaNormalised"] is False
