"""F3 acceptance tests (T0): the vector file ``fixtures/number_inputs.json`` (FN-46).

* the file itself: at least 30 inputs, every column, every row of FN-46's second
  table with the result the specification states (written out here, from SPEC 4.4,
  so the file is checked against the text and not against itself);
* the file against the parsers that exist today, run under Node (the way the
  b2b ``numfmt:js`` row runs ``numfmt.js``): ``parseNumberText`` for beta, alpha_k
  and q, ``parseNumber`` (from its source text, the Quantification tab's reader) with
  the field ranges for lambda, T, tau, mu. These checks pass before and after F3: they keep
  the vectors true to what the fields do;
* the file against the server validators of ``/api/grid/paste``: a number the vectors accept
  is accepted, a plain number they refuse for its range is refused (answers 400, nothing applied).
  These fail until T1.

The GUI part (typing each input into the field, into the cell, pasting it) is ``s_grid.js``.
"""
import importlib.util
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_SUPPORT = Path(__file__).with_name("grid_support.py")
_spec = importlib.util.spec_from_file_location("fta_f3_grid_support_numbers", _SUPPORT)
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

FTA_WEB = Path(__file__).resolve().parents[3]
JS = FTA_WEB / "static" / "js"
COLUMNS = ["q", "lambda", "T", "tau", "mu", "beta", "alpha_k"]
SERVER_COLUMNS = ["q", "lambda", "T", "tau", "mu"]
ROLE = {"q": "fixed", "lambda": "rate", "T": "rate", "tau": "standby", "mu": "repairable"}

# SPEC 4.4 FN-46, "Inputs on which the two parsers disagree": None = refused, a number = accepted with that value.
SPEC_TABLE = {
    "1e-400": {"q": None, "beta": None, "alpha_k": None, "lambda": 0.0, "mu": 0.0, "T": None, "tau": None},
    "5%": {"q": 0.05, "beta": 0.05, "alpha_k": 0.05, "lambda": None, "mu": None, "T": None, "tau": None},
    "1/1000": {"q": 0.001, "beta": 0.001, "alpha_k": 0.001, "lambda": None, "mu": None, "T": None, "tau": None},
    "1,500E-06": {"q": None, "beta": None, "alpha_k": None, "lambda": 1.5e-6, "mu": 1.5e-6, "T": 1.5e-6, "tau": 1.5e-6},
    "1,5E-06": {"q": 1.5e-6, "beta": 1.5e-6, "alpha_k": 1.5e-6, "lambda": 1.5e-6, "mu": 1.5e-6, "T": 1.5e-6, "tau": 1.5e-6},
}

DECIMAL = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$", re.I | re.ASCII)


def vectors():
    path = S.FIXTURES / "number_inputs.json"
    assert path.is_file(), "missing %s" % path
    return json.loads(path.read_text(encoding="utf-8"))


def same(a, b):
    return a == b or (isinstance(a, float) and isinstance(b, (int, float)) and math.isclose(a, b, rel_tol=1e-12, abs_tol=0))


# ---------------------------------------------------------------------------
# the file
# ---------------------------------------------------------------------------


def test_the_file_has_at_least_30_inputs_and_every_column():
    data = vectors()
    assert data["schema"] == 1
    assert data["columns"] == COLUMNS
    assert len(data["inputs"]) >= 30
    texts = [item["text"] for item in data["inputs"]]
    assert len(set(texts)) == len(texts), "an input appears twice"
    for item in data["inputs"]:
        assert isinstance(item["text"], str)
        assert set(item["expect"]) == set(COLUMNS), item["text"]
        for column, result in item["expect"].items():
            assert result["ok"] in (True, False), (item["text"], column)
            if result["ok"]:
                assert result["value"] is None or isinstance(result["value"], (int, float)), (item["text"], column)
                assert result["value"] is None or math.isfinite(result["value"])
            else:
                assert "value" not in result


@pytest.mark.parametrize("text", list(SPEC_TABLE))
def test_every_row_of_the_second_table_of_fn46_is_there_with_the_stated_results(text):
    by_text = {item["text"]: item["expect"] for item in vectors()["inputs"]}
    assert text in by_text, "FN-46's second table needs %r" % text
    for column, want in SPEC_TABLE[text].items():
        got = by_text[text][column]
        if want is None:
            assert got == {"ok": False}, (text, column, got)
        else:
            assert got["ok"] is True and same(got["value"], want), (text, column, got)


def test_the_file_covers_the_kinds_of_input_the_brief_names():
    texts = {item["text"] for item in vectors()["inputs"]}
    need = {"0", "-0", "-0.1", "1.5", "0.25", "0,25", "", "NaN", "Infinity", "abc"}
    assert need <= texts, need - texts
    assert any(re.search(r"[０-９]", t) for t in texts), "full-width digits"
    assert any(re.fullmatch(r"[+-]?\d+(\.\d+)?[eE][+-]?\d+", t) for t in texts), "exponent form"
    assert any(re.fullmatch(r"\d{1,3}(,\d{3})+", t) for t in texts), "thousands form"
    assert any(t.strip() == "" and t != "" for t in texts), "spaces only"


def test_blank_text_clears_the_number_fields_and_is_refused_for_probabilities():
    for item in vectors()["inputs"]:
        if item["text"].strip() != "":
            continue
        for column in ("lambda", "T", "tau", "mu"):
            assert item["expect"][column] == {"ok": True, "value": None}, (item["text"], column)
        for column in ("q", "beta", "alpha_k"):
            assert item["expect"][column] == {"ok": False}, (item["text"], column)


def test_lambda_unit_examples_follow_fn51():
    data = vectors()
    assert data["lambda_units"] == {"h": 1, "y": 8760, "FIT": 1e9}
    for example in data["lambda_unit_examples"]:
        assert same(float(example["text"]) / data["lambda_units"][example["unit"]], example["perHour"])
    assert {(e["text"], e["unit"]): e["perHour"] for e in data["lambda_unit_examples"]}[("1", "FIT")] == 1e-9


# ---------------------------------------------------------------------------
# the vectors against the parsers that exist today (Node)
# ---------------------------------------------------------------------------


def _function_source(source, name):
    start = re.search(r"(?:export )?function %s\(" % re.escape(name), source)
    assert start, "function %s not found" % name
    open_at = source.index("{", source.index(")", start.start()))
    depth = 0
    for j in range(open_at, len(source)):
        depth += source[j] == "{"
        depth -= source[j] == "}"
        if depth == 0:
            return source[start.start():j + 1].replace("export ", "", 1)
    raise AssertionError("unbalanced braces in %s" % name)


def _node(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    proc = subprocess.run([node, "--input-type=module"], input=script.encode("utf-8"),
                          capture_output=True, timeout=120)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return json.loads(proc.stdout.decode("utf-8"))


def _read_all(texts):
    """What today's readers make of each text: {column: [ {ok, value}, ... ]}."""
    common = (JS / "tabs" / "analysis_common.js").read_text(encoding="utf-8")
    module = (JS / "numfmt.js").as_uri()
    script = (
        "import { parseNumberText } from %s;\n"
        "const texts = %s;\n"
        "%s\n"
        "const unit = (r, lo, hi, openLo) => r.ok && r.value >= lo && r.value <= hi && !(openLo && r.value === lo)"
        " ? { ok: true, value: Object.is(r.value, -0) ? 0 : r.value } : { ok: false };\n"
        "const probability = (text) => { const r = parseNumberText(text); return unit(r, 0, 1, false); };\n"
        "const number = (min, exclusive) => (text) => {\n"
        "  const v = parseNumber(text);\n"
        "  if (v === null) return { ok: true, value: null };\n"
        "  if (Number.isNaN(v) || v < min || (exclusive && v === min)) return { ok: false };\n"
        "  return { ok: true, value: Object.is(v, -0) ? 0 : v };\n"
        "};\n"
        "const readers = { q: probability, beta: probability, alpha_k: probability, lambda: number(0, false),\n"
        "  mu: number(0, false), T: number(0, true), tau: number(0, true) };\n"
        "const out = {};\n"
        "for (const [k, f] of Object.entries(readers)) out[k] = texts.map(f);\n"
        "process.stdout.write(JSON.stringify(out));\n"
        % (json.dumps(module), json.dumps(texts), _function_source(common, "parseNumber")))
    return _node(script)


@pytest.fixture(scope="module")
def parsed():
    data = vectors()
    texts = [item["text"] for item in data["inputs"]]
    return data, _read_all(texts)


@pytest.mark.parametrize("column", ["beta", "alpha_k"])
def test_beta_and_alpha_k_columns_equal_parse_number_text_with_range_0_to_1(parsed, column):
    """The CCF fields read with parseNumberText (SPEC FN-46 table); the GUI check in the CCF tab
    is added when F2 / F2A are merged, until then this is the check (BRIEF Interfaces)."""
    data, now = parsed
    bad = []
    for item, got in zip(data["inputs"], now[column]):
        want = item["expect"][column]
        if want["ok"] != got["ok"] or (want["ok"] and not same(got["value"], want["value"])):
            bad.append((item["text"], want, got))
    assert not bad, bad


@pytest.mark.parametrize("column", ["q", "lambda", "T", "tau", "mu"])
def test_the_other_columns_equal_what_the_existing_readers_do_today(parsed, column):
    data, now = parsed
    bad = []
    for item, got in zip(data["inputs"], now[column]):
        want = item["expect"][column]
        if want["ok"] != got["ok"] or (want["ok"] and not same(got["value"], want["value"])):
            bad.append((item["text"], want, got))
    assert not bad, bad


# ---------------------------------------------------------------------------
# the vectors against the server validators (/api/grid/paste): fail until T1
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    app = S.make_app(tmp_path)
    with app.test_client() as test_client:
        yield test_client
    from fta_web.state import reset_state

    reset_state()


@pytest.fixture
def doc(client):
    return S.build_document(client)


def _post_number(client, doc, column, value):
    return S.paste(client, [S.row(1, doc[ROLE[column]], **{column: value})])


def _server_cases():
    """(text, column, number, accepted) for every number the server is sent.

    The browser reads the text; the server only ever sees the number. So: a vector the
    fields accept is sent with its value and must be accepted; a vector refused only for its
    range (a plain decimal text) is sent as that number and must be refused.
    """
    cases = []
    for item in vectors()["inputs"]:
        for column in SERVER_COLUMNS:
            want = item["expect"][column]
            if want["ok"] and want["value"] is not None:
                cases.append((item["text"], column, want["value"], True))
            elif not want["ok"] and DECIMAL.match(item["text"].strip()):
                number = float(item["text"].strip())
                if number == 0 and re.search("[1-9]", item["text"]):
                    continue  # "1e-400": too small for a double; the refusal is the browser's
                if math.isfinite(number):
                    cases.append((item["text"], column, number, False))
    return cases


def test_the_vectors_yield_server_cases_of_both_kinds():
    cases = _server_cases()
    assert sum(1 for c in cases if c[3]) >= 100
    assert sum(1 for c in cases if not c[3]) >= 20


@pytest.mark.parametrize("column", SERVER_COLUMNS)
def test_a_number_the_vectors_accept_is_accepted_by_the_server_and_a_range_error_is_refused(client, doc, column):
    for text, col, number, accepted in _server_cases():
        if col != column:
            continue
        before_revision = S.fields_now(client)["revision"]
        response = _post_number(client, doc, column, number)
        if accepted:
            payload = S.assert_ok(response)
            assert payload["applied"] == 1 and payload["refused"] == [], (text, column, number)
        else:
            S.assert_error(response, 400, "INVALID_FIELD", column)
            assert S.fields_now(client)["revision"] == before_revision, (text, column, number)


@pytest.mark.parametrize("column, validator", [
    ("q", "validate_grid_q"), ("lambda", "validate_grid_lambda"), ("T", "validate_grid_duration"),
    ("tau", "validate_grid_duration"), ("mu", "validate_grid_mu")])
def test_validator_agrees_with_the_vectors(column, validator):
    import inspect

    from fta_web import grid_schema
    from fta_web.errors import ApiError

    function = getattr(grid_schema, validator)
    required = [p for p in inspect.signature(function).parameters.values()
                if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) and p.default is p.empty]
    call = (lambda v: function(v, column)) if len(required) >= 2 else function
    for text, col, number, accepted in _server_cases():
        if col != column:
            continue
        if accepted:
            assert call(number) == number, (text, column, number)  # number_field returns the value itself (-0 comes back as 0.0)
        else:
            with pytest.raises(ApiError) as caught:
                call(number)
            assert caught.value.code == "INVALID_FIELD" and caught.value.detail.get("field") == column
