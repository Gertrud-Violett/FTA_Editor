"""F2A BRIEF criterion 9 (UI-18, FN-64), browser catalog side: ``static/js/i18n/ccf.js``.

The alpha keys of DESIGN 6 exist in en and ja with the same placeholders, differ between the
languages, read exactly as the design says, carry none of the FN-64 words, use ``{n}``,
``{count}``, ``{k}``, ``{sum}`` (never ``{m}``) and the Japanese term "アルファファクター". The two
sentences that the report repeats (``ccf.assume.alpha``, ``ccf.label.subset``) are the same text
in ``ccf_text.py``.
"""
import re
from pathlib import Path

import pytest

import _alpha_models as M

REPO_ROOT = Path(__file__).resolve().parents[4]
CATALOG = REPO_ROOT / "fta_web" / "static" / "js" / "i18n" / "ccf.js"
_ENTRY = re.compile(r"'([A-Za-z0-9_.]+)'\s*:\s*'((?:[^'\\]|\\.)*)'")
_PLACEHOLDER = re.compile(r"\{[A-Za-z0-9_]+\}")
ALLOWED = {"k", "n", "count", "sum", "list", "error", "name", "members"}


def unescape(value):
    return value.replace("\\'", "'").replace("\\\\", "\\")


def catalog():
    """``(en, ja)`` dicts from ``export default { en: {...}, ja: {...} };``."""
    assert CATALOG.is_file(), "fta_web/static/js/i18n/ccf.js does not exist"
    src = CATALOG.read_text(encoding="utf-8")
    match = re.search(r"export default \{(.*?)\n\};", src, re.S)
    assert match, "ccf.js: could not locate `export default { ... };`"
    block = match.group(1)
    assert "\n  en:" in block and "\n  ja:" in block, "ccf.js needs an en: and a ja: section"
    en_block, ja_block = block.split("\n  ja:", 1)
    en = {k: unescape(v) for k, v in _ENTRY.findall(en_block)}
    ja = {k: unescape(v) for k, v in _ENTRY.findall(ja_block)}
    return en, ja


def test_every_alpha_key_of_the_design_is_in_both_languages():
    en, ja = catalog()
    missing = [k for k in M.CATALOG_EXACT if k not in en or k not in ja]
    assert not missing, missing


@pytest.mark.parametrize("key", sorted(M.CATALOG_EXACT))
def test_the_alpha_strings_read_as_the_design_says(key):
    en, ja = catalog()
    assert (en[key], ja[key]) == M.CATALOG_EXACT[key]


def test_alpha_keys_are_translated_and_have_the_same_placeholders():
    en, ja = catalog()
    assert set(en) == set(ja)
    for key in M.CATALOG_EXACT:
        assert en[key].strip() and ja[key].strip(), key
        assert en[key] != ja[key], "%s is not translated" % key
        assert sorted(_PLACEHOLDER.findall(en[key])) == sorted(_PLACEHOLDER.findall(ja[key])), key
        found = {p.strip("{}") for p in _PLACEHOLDER.findall(en[key])}
        assert found <= ALLOWED, (key, found)
        assert "{m}" not in en[key] + ja[key], key


def test_the_placeholders_of_the_count_texts_are_n_count_k_and_sum():
    en, _ja = catalog()
    assert "{k}" in en["ccf.field.alpha"] and "{k}" in en["ccf.err.alpha"]
    assert "{n}" in en["ccf.alpha.help"]
    assert "{n}" in en["ccf.alpha.size"]
    assert "{n}" in en["ccf.alpha.resize"] and "{count}" in en["ccf.alpha.resize"]
    for key in ("ccf.alpha.sumOk", "ccf.alpha.sumNormalised", "ccf.alpha.sumBad"):
        assert "{sum}" in en[key], key


def test_one_japanese_term_alpha_factor_in_the_new_strings():
    """O9, text reviewer 2026-11-02: "アルファファクター" (parallel to F2's "ベータファクター"),
    never "α ファクター" or "α モデル"."""
    _en, ja = catalog()
    for key in M.CATALOG_EXACT:
        assert "α ファクター" not in ja[key] and "αファクター" not in ja[key], key
        assert "α モデル" not in ja[key], key
    assert ja["ccf.model.alpha"] == "アルファファクター"
    assert ja["ccf.model.alphaCell"] == "アルファファクター"
    assert "アルファファクターモデル" in ja["ccf.alpha.size"]
    assert "アルファファクターモデル" in ja["ccf.assume.alpha"]


def test_the_testing_selector_has_no_default_wording():
    en, ja = catalog()
    for key in ("ccf.testing.staggered", "ccf.testing.nonStaggered", "ccf.testing.placeholder"):
        assert "default" not in en[key].lower() and "デフォルト" not in ja[key]
    assert en["ccf.testing.placeholder"] == "Choose a testing scheme"


def test_the_catalog_and_ccf_text_repeat_the_same_sentences():
    from fta_web import ccf_text

    en, ja = catalog()
    assert en["ccf.assume.alpha"] == ccf_text.TEXT["en"]["assume.alpha"]
    assert ja["ccf.assume.alpha"] == ccf_text.TEXT["ja"]["assume.alpha"]
    assert en["ccf.label.subset"] == ccf_text.TEXT["en"]["label.subset"]
    assert ja["ccf.label.subset"] == ccf_text.TEXT["ja"]["label.subset"]
    assert en["ccf.label.subset"] != ja["ccf.label.subset"]


def test_no_alpha_catalog_string_claims_compliance():
    en, ja = catalog()
    keys = sorted(M.CATALOG_EXACT)
    assert M.fn64_hits([en[k] for k in keys], [ja[k] for k in keys]) == []
    # the search itself (shared copy in _alpha_models) finds what it should
    assert M.fn64_hits(["complies with a standard", "Certification"], []) != []
    assert M.fn64_hits([], ["JIS に準拠", "適合性", "認証済み"]) != []


def test_the_whole_catalog_keeps_en_ja_parity():
    en, ja = catalog()
    assert en and set(en) == set(ja), sorted(set(en) ^ set(ja))
    for key in en:
        assert sorted(_PLACEHOLDER.findall(en[key])) == sorted(_PLACEHOLDER.findall(ja[key])), key
