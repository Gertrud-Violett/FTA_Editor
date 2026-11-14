"""Feature FR, task X4: the final-review wording fixes (tests written first).

1. "lower bounds": a count or order limit that truncates the cut sets does not make a value
   from the cut sets a lower bound (the cut-set approximation can also read high). The four
   catalog strings, the USER_GUIDE row of ``CUTSETS_TRUNCATED`` and the comment of
   ``engine.root_headline`` say so (the analyst's wording). ``lint.py`` and the messages that
   the golden files pin stay as they are.
2. ``STALE_REVISION`` of the what-if: the Japanese answer of ``POST /api/whatif`` says to put the
   factors back to 1 and act again, not the Grid's "paste again". The Grid keeps its text and
   the English message stays. The tests ask the HTTP route only: how the server tells the two
   routes apart is left to the implementation (see the report of task X4 about ``detail``).

The catalogs are read as text, the way ``test_whatif_caution_texts.py`` reads them.
"""
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

STATIC = REPO_ROOT / "fta_web" / "static" / "js"
CUTSETS_JS = STATIC / "i18n" / "cutsets.js"
VAL_JS = STATIC / "i18n" / "val.js"
GRID_JS = STATIC / "i18n" / "grid.js"
USER_GUIDE = REPO_ROOT / "docs" / "USER_GUIDE.md"
ENGINE_PY = REPO_ROOT / "fta_web" / "engine.py"

_ENTRY = re.compile(r"'([A-Za-z0-9_.]+)'\s*:\s*'((?:[^'\\]|\\.)*)'")
_PLACEHOLDER = re.compile(r"\{[A-Za-z0-9_]+\}")


def unescape(value):
    return value.replace("\\'", "'").replace("\\\\", "\\")


def catalog(path):
    """``(en, ja)`` dicts of a ``export default { en: {...}, ja: {...} };`` catalog."""
    src = path.read_text(encoding="utf-8")
    head, ja_block = src.split("\n  ja: {", 1)
    en_block = head.split("\n  en: {", 1)[1]
    return ({k: unescape(v) for k, v in _ENTRY.findall(en_block)},
            {k: unescape(v) for k, v in _ENTRY.findall(ja_block)})


# ------------------------------------------------------------------- 1. the four strings

#: (file, key, en, ja): the new texts, exact.
CUTSETS_KEY = "anl.warn.CUTSETS_TRUNCATED"
VAL_KEY = "val.code.CUTSETS_TRUNCATED"
CUTSETS_EN = ("Cut sets were truncated by {by}. Values from the cut sets cover only the sets kept "
              "and can read low or high.")
CUTSETS_JA = ("カットセットは {by} で打ち切られています。カットセットから求めた値は残ったセットのみを対象としており、"
              "実際の値より低くなることも高くなることもあります。")
VAL_EN = "The cut-set list was cut short ({reason}). Values from the cut sets can read low or high."
VAL_JA = ("カットセットの一覧が途中で打ち切られました ({reason})。カットセットから求めた値は、"
          "実際の値より低くなることも高くなることもあります。")

CASES = [
    pytest.param(CUTSETS_JS, CUTSETS_KEY, 0, CUTSETS_EN, id="cutsets-en"),
    pytest.param(CUTSETS_JS, CUTSETS_KEY, 1, CUTSETS_JA, id="cutsets-ja"),
    pytest.param(VAL_JS, VAL_KEY, 0, VAL_EN, id="val-en"),
    pytest.param(VAL_JS, VAL_KEY, 1, VAL_JA, id="val-ja"),
]


@pytest.mark.parametrize("path, key, which, expected", CASES)
def test_the_truncation_warning_says_the_exact_new_text(path, key, which, expected):
    assert catalog(path)[which][key] == expected


@pytest.mark.parametrize("path, key, which, expected", CASES)
def test_the_truncation_warning_keeps_its_placeholder(path, key, which, expected):
    text = catalog(path)[which][key]
    wanted = ["{by}"] if key == CUTSETS_KEY else ["{reason}"]
    assert _PLACEHOLDER.findall(text) == wanted


@pytest.mark.parametrize("path, key, which, expected", CASES)
def test_the_truncation_warning_does_not_call_the_value_a_bound_or_too_low(path, key, which, expected):
    text = catalog(path)[which][key]
    for word in ("lower bound", "lower-bound", "下限", "too low", "小さめ", "underestimate"):
        assert word not in text.lower(), (word, text)


def test_the_new_texts_are_not_over_claiming():
    """The count limit can make a value read high as well as low: no absolute word."""
    for text in (CUTSETS_EN, VAL_EN):
        assert not re.search(r"\b(always|never|guarantee[sd]?|exact|exactly)\b", text, re.I)
        assert "low or high" in text
    for text in (CUTSETS_JA, VAL_JA):
        assert "低くなることも高くなることもあります" in text


def test_the_other_cutsets_catalog_entries_are_untouched_in_this_task():
    en, ja = catalog(CUTSETS_JS)
    assert en["anl.warn.MC_CUTSETS_TRUNCATED"] == "Sampling uses the {used} most probable of {total} cut sets."
    assert ja["anl.warn.MC_CUTSETS_TRUNCATED"].startswith("{total} 件のカットセットのうち")


# ------------------------------------------------------------------- the guide and the comment


def _guide_row():
    rows = [ln for ln in USER_GUIDE.read_text(encoding="utf-8").splitlines()
            if ln.startswith("| `CUTSETS_TRUNCATED` |")]
    assert len(rows) == 1, rows
    return rows[0]


def test_the_user_guide_row_of_cutsets_truncated_says_low_or_high():
    row = _guide_row()
    assert "so values from the cut sets can read low or high" in row
    assert "so the results may be underestimated" not in row
    assert "underestimated" not in row
    # the rest of the row is unchanged
    assert "The cut sets, expanded with the document's limits, were truncated," in row
    assert "Shown in the Validation tab, `validate` and the DOCX report." in row


def test_the_old_underestimated_sentence_is_gone_from_the_guide():
    text = USER_GUIDE.read_text(encoding="utf-8")
    assert text.count("so the results may be underestimated") == 0


def test_the_engine_comment_does_not_call_the_capped_number_a_bound():
    src = ENGINE_PY.read_text(encoding="utf-8")
    start = src.index("def root_headline(")
    doc = src[start:start + 1200]
    assert "a bound from the first 2000 sets" not in " ".join(doc.split())
    assert "an estimate from the sets the cap kept" in " ".join(doc.split())


# ------------------------------------------------------------------- 2. STALE_REVISION of the what-if

WHATIF_JA = "解析が変更されました。倍率を 1 に戻して、もう一度操作してください"
WHATIF_EN = "The document changed; start again from factor 1"


def _grid_text(lang):
    return catalog(GRID_JS)[0 if lang == "en" else 1]["grid.summary.stale"]


@pytest.fixture()
def client():
    pytest.importorskip("flask")
    from fta_web.app import create_app
    from fta_web.state import reset_state

    reset_state()
    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


def _stale_whatif(client, **kwargs):
    now = client.get("/api/revision").get_json()
    body = {"revision": now["revision"] + 1, "documentSerial": now["documentSerial"],
            "factors": {}}
    return now, client.post("/api/whatif", json=body, **kwargs)


def test_the_what_if_409_answers_in_japanese_with_its_own_text(client):
    now, via_header = _stale_whatif(client, headers={"Accept-Language": "ja"})
    via_param = client.post("/api/whatif?lang=ja", json={
        "revision": now["revision"] + 1, "documentSerial": now["documentSerial"], "factors": {}})
    for response in (via_header, via_param):
        assert response.status_code == 409
        error = response.get_json()["error"]
        assert error["code"] == "STALE_REVISION"
        assert error["message"] == WHATIF_JA
        assert "貼り付け" not in error["message"]


def test_the_what_if_409_keeps_the_numbers_in_detail(client):
    now, response = _stale_whatif(client, headers={"Accept-Language": "ja"})
    detail = response.get_json()["error"]["detail"]
    assert detail["revision"] == now["revision"]
    assert detail["documentSerial"] == now["documentSerial"]


def test_the_what_if_409_message_in_english_is_unchanged(client):
    for kwargs in ({}, {"headers": {"Accept-Language": "en"}}):
        _now, response = _stale_whatif(client, **kwargs)
        error = response.get_json()["error"]
        assert response.status_code == 409 and error["code"] == "STALE_REVISION"
        assert error["message"] == WHATIF_EN


def test_the_grid_409_keeps_the_grid_text_in_japanese_and_english(client):
    now = client.get("/api/revision").get_json()
    body = {"revision": now["revision"] + 1, "documentSerial": now["documentSerial"], "rows": []}
    ja = client.post("/api/grid/paste", json=body, headers={"Accept-Language": "ja"})
    en = client.post("/api/grid/paste", json=body)
    assert ja.status_code == en.status_code == 409
    assert ja.get_json()["error"]["message"] == _grid_text("ja")
    assert "貼り付け" in ja.get_json()["error"]["message"]
    assert en.get_json()["error"]["message"] == _grid_text("en")


def test_the_japanese_what_if_text_is_not_the_grid_text():
    assert WHATIF_JA != _grid_text("ja")
