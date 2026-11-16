"""Feature FR, task X4: two fixes in the CCF part of the DOCX report (tests written first).

* The ``assume.alpha`` sentence (the alpha formulas with their sources and pages) is printed
  once for a document with alpha groups, however many groups it has. It used to be added
  under "Formulas" and again in the assumptions loop.
* ``report_docx._beta_text`` never raises: a stored beta such as ``10 ** 400`` (an int too big
  for a float) used to raise ``OverflowError`` in ``"%.3g" % beta`` and stopped the report.
  Only "no exception, a str" is pinned for such values; the output of ordinary betas stays as
  ``test_ccf_report_text.py`` has it.
"""
import io
import json

import pytest

docx = pytest.importorskip("docx")

from fta_web import ccf_text, engine, report_docx  # noqa: E402


def leaf(node_id):
    return {"id": node_id, "name": "Pump " + node_id, "type": "Event", "logicGate": "OR",
            "probability": 1e-3, "notes": "", "links": [], "children": [],
            "quant": {"model": "fixed"}}


def group(group_id, name, members, **over):
    stored = {"id": group_id, "name": name, "model": "alpha", "beta": None,
              "alpha": [0.9, 0.06, 0.04], "testing": "staggered", "members": list(members),
              "source": ""}
    stored.update(over)
    return stored


def document(groups, member_sets):
    gates = [{"id": "G%d" % i, "name": "Pumps %d" % i, "type": "Event", "logicGate": "AND",
              "probability": 1.0, "notes": "", "links": [],
              "children": [leaf(m) for m in members]}
             for i, members in enumerate(member_sets, 1)]
    tree = {"id": "root", "name": "Top", "type": "Root", "logicGate": "OR", "probability": 1.0,
            "notes": "", "links": [], "children": gates}
    return {"title": "t", "date": "2026-11-02", "mode": "FTA", "fileFormatVersion": 2,
            "tree": tree, "analysis": {"ccfGroups": groups}}


def report(tmp_path, doc, lang="en"):
    """``(paragraphs, cells)`` of the DOCX of ``doc``, built in process."""
    path = tmp_path / "doc.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    core = engine.WebCore()
    ok, error = core.load_from_json(str(path))
    assert ok, error
    options = report_docx.normalize_options({"lang": lang, "sections": ["headline", "cutsets"]})
    data = report_docx.collect_report_data(report_docx.DocSnapshot.of(core), [], options)
    document_ = docx.Document(io.BytesIO(report_docx.build_report(data, options)))
    cells = [c.text for table in document_.tables for row in table.rows for c in row.cells]
    return [p.text for p in document_.paragraphs], cells


ONE = (group("g1", "Valves", ["A", "B", "C"]),)
TWO = (group("g1", "Valves", ["A", "B", "C"]), group("g2", "Pumps", ["D", "E", "F"]))


# ---------------------------------------------------------------- assume.alpha, once


@pytest.mark.parametrize("lang", ["en", "ja"])
@pytest.mark.parametrize("groups", [ONE, TWO], ids=["one-alpha-group", "two-alpha-groups"])
def test_the_alpha_assumption_is_printed_exactly_once(tmp_path, lang, groups):
    member_sets = [g["members"] for g in groups]
    paragraphs, _cells = report(tmp_path, document(list(groups), member_sets), lang)
    sentence = ccf_text.text(lang, "assume.alpha")
    assert sentence in "\n".join(paragraphs)             # guard: the sentence is found at all
    assert paragraphs.count(sentence) == 1, paragraphs.count(sentence)


def test_the_alpha_assumption_is_still_in_the_report_after_the_assumptions_heading(tmp_path):
    """Whichever of the two places keeps it, the sentence is there with the formulas' sources."""
    paragraphs, _cells = report(tmp_path, document(list(ONE), [["A", "B", "C"]]))
    sentence = ccf_text.text("en", "assume.alpha")
    at = paragraphs.index(sentence)
    assert "NUREG/CR-5485 Eq. 5.6 p. 40" in paragraphs[at]
    assert "Formulas" in paragraphs[:at]                  # the CCF section's heading comes first


def test_a_document_with_a_beta_group_only_has_no_alpha_assumption(tmp_path):
    beta = group("g1", "Feed", ["A", "B"], model="beta", beta=0.1, alpha=None, testing=None)
    paragraphs, _cells = report(tmp_path, document([beta], [["A", "B"]]))
    assert ccf_text.text("en", "assume.alpha") not in paragraphs


def test_the_six_other_assumptions_are_still_printed_once_each(tmp_path):
    paragraphs, _cells = report(tmp_path, document(list(TWO), [g["members"] for g in TWO]))
    for key in ("assume.model", "assume.qt", "assume.beta", "assume.split", "assume.headline",
                "assume.sampling"):
        assert paragraphs.count(ccf_text.text("en", key)) == 1, key


# ---------------------------------------------------------------- _beta_text never raises

HUGE = [10 ** 400, -(10 ** 400), float("inf"), float("-inf"), float("nan"), -1e308, 1e308, 10 ** 25]


@pytest.mark.parametrize("beta", HUGE, ids=["big", "-big", "inf", "-inf", "nan", "-1e308", "1e308",
                                            "1e25"])
def test_beta_text_returns_a_str_and_does_not_raise(beta):
    assert isinstance(report_docx._beta_text(beta), str)


def test_beta_text_of_an_int_too_big_for_a_float_reads_in_three_significant_figures():
    assert report_docx._beta_text(10 ** 400) == "1.00e+400"
    assert report_docx._beta_text(-(10 ** 400)) == "-1.00e+400"


def test_beta_text_of_ordinary_values_is_unchanged():
    assert report_docx._beta_text(0.1) == "0.1"
    assert report_docx._beta_text(1 / 3) == "0.333"
    assert report_docx._beta_text(0) == "0"
    assert report_docx._beta_text(1) == "1"
    assert report_docx._beta_text("abc") == "abc"
    assert report_docx._beta_text(None) == "None"
    assert report_docx._beta_text(True) == "True"


@pytest.mark.parametrize("beta", [10 ** 400, -(10 ** 400), float("inf")], ids=["big", "-big", "inf"])
@pytest.mark.parametrize("lang", ["en", "ja"])
def test_a_report_with_an_absurd_stored_beta_is_built(tmp_path, beta, lang):
    stored = group("g1", "Feed", ["A", "B"], model="beta", beta=beta, alpha=None, testing=None)
    doc = document([stored], [["A", "B"]])
    paragraphs, cells = report(tmp_path, doc, lang)
    assert any("Feed" in c for c in cells)               # the group is listed
    assert any("β" in c for c in cells)                  # with a Parameters cell
