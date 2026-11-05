"""The What-if caution line, texts (feature FR, task X3; FR DESIGN revision 2, section 4 and the X1 row of 8.1).

The seven strings live in a NEW catalog, ``fta_web/static/js/i18n/whatifcaution.js``, because the
protected ``acceptance/whatif/test_texts.py`` pins ``i18n/whatif.js`` to exactly its 30 keys
(Y3, CR-20261104, FR DESIGN 10.4 added ``ccfNotApplied``: 7 keys):

=================================  ======================================================
``whatif.caution.ccfNotApplied``   CCF_NOT_APPLIED (a factor on a member of a group not applied at baseline)
``whatif.caution.ccfOne``          CCF_Q_ONE
``whatif.caution.ccfHigh``         CCF_HIGH_Q, with ``{limit}``
``whatif.caution.standby``         STANDBY_LARGE_LT, with ``{limit}``
``whatif.caution.cutsets``         CUTSETS_TRUNCATED
``whatif.caution.more``            the suffix "(and {n} more)" of several cautions
``whatif.caution.badge``           the word on the badge in the corner of the values table ("Caution" / "注意")
=================================  ======================================================

What is checked: the keys exist in en and ja with equal ``{placeholders}``; both languages say
the exact text of DESIGN section 4 (copied into ``EXPECTED``, since DESIGN lives in ``.division``);
the ja strings are translated (kana or kanji, no stray English word); one line at the default
pane (length bounds); FN-64 (no compliance, conformity or certification wording) and no absolute
claim; no digit other than the placeholders, the 1 of "probability 1" and the 2 of "λτ/2"; the
keys are defined nowhere else; the shell and the tab register the catalog; the existing
catalog-parity tests keep passing (they read every file of ``i18n/`` and need no edit).

The files are read as text (the way ``test_catalog_parity.py`` reads them); until the catalog
exists each test fails on "does not exist".
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC = REPO_ROOT / "fta_web" / "static" / "js"
CATALOG = STATIC / "i18n" / "whatifcaution.js"
WHATIF_CATALOG = STATIC / "i18n" / "whatif.js"
MAIN_JS = STATIC / "main.js"
TAB_JS = STATIC / "tabs" / "whatif.js"

_ENTRY = re.compile(r"'([A-Za-z0-9_.]+)'\s*:\s*'((?:[^'\\]|\\.)*)'")
_PLACEHOLDER = re.compile(r"\{[A-Za-z0-9_]+\}")
FN64_EN = re.compile(r"\b(comply|complies|compliant|compliance|conform|conforms|conformity|"
                     r"certified|certification)\b", re.IGNORECASE)
FN64_JA = ("準拠", "適合", "認証")
ABSOLUTE_EN = re.compile(r"\b(will|always|never|must|guarantee[sd]?)\b", re.IGNORECASE)
KANA_KANJI = re.compile(r"[぀-ヿ一-鿿]")
#: Latin words that may stay in a Japanese string: the product word and the abbreviation.
JA_LATIN_OK = ("What-if", "CCF")

KEYS = ["whatif.caution.ccfOne", "whatif.caution.ccfHigh", "whatif.caution.standby",
        "whatif.caution.cutsets", "whatif.caution.more", "whatif.caution.badge",
        "whatif.caution.ccfNotApplied"]

#: FR DESIGN section 4 and 10.4 (the CR's English text), copied word for word: key -> (en, ja).
EXPECTED = {
    "whatif.caution.ccfNotApplied": (
        "CCF group not applied at baseline; CCF not included",
        "ベースラインで CCF グループが適用されていないため、CCF は含まれません。"),
    "whatif.caution.ccfOne": (
        "A CCF member is at probability 1. Typed into the document, the group would not be applied.",
        "CCF グループのメンバーの確率が 1 です。文書に入力するとグループは適用されなくなります。"),
    "whatif.caution.ccfHigh": (
        "A CCF member's probability is above {limit}. Check the CCF result.",
        "CCF グループのメンバーの確率が {limit} を超えています。CCF の結果を確認してください。"),
    "whatif.caution.standby": (
        "A scaled standby event has λτ above {limit}, where the λτ/2 approximation is poor.",
        "倍率をかけた待機系事象の λτ が {limit} を超えており、λτ/2 近似の精度が低下します。"),
    "whatif.caution.cutsets": (
        "Cut sets are limited by max order or max count; some may be missing from the what-if number.",
        "最大次数または最大件数でカットセットが制限されており、一部のカットセットが What-if 値に含まれない場合があります。"),
    "whatif.caution.more": ("(and {n} more)", "（ほか {n} 件）"),
    "whatif.caution.badge": ("Caution", "注意"),
}
PLACEHOLDERS = {
    "whatif.caution.ccfNotApplied": [],
    "whatif.caution.ccfOne": [],
    "whatif.caution.ccfHigh": ["{limit}"],
    "whatif.caution.standby": ["{limit}"],
    "whatif.caution.cutsets": [],
    "whatif.caution.more": ["{n}"],
    "whatif.caution.badge": [],
}
#: The digits a string may hold besides its placeholders: the 1 of "probability 1" and the 2 of "λτ/2".
DIGITS = {"whatif.caution.ccfOne": "1", "whatif.caution.standby": "2"}
#: One line at the default pane (about 738 px): characters per string (DESIGN section 4).
MAX_EN = 100
#: 56 for the first wording; the text lens made the subject of the cut-set sentence explicit (61 characters).
#: ``ccfNotApplied`` (36 characters) is inside the design's bound of 56 (DESIGN 10.4).
MAX_JA = 64
MAX_JA_NOT_APPLIED = 56
MAX_MORE = 16
#: The badge sits in the corner cell of the table (about 130 px at the narrowest): a word, not a sentence.
MAX_BADGE_EN = 12
MAX_BADGE_JA = 6


def unescape(value):
    return value.replace("\\'", "'").replace("\\\\", "\\")


def catalog():
    """``(en, ja)`` dicts from ``export default { en: {...}, ja: {...} };``."""
    assert CATALOG.is_file(), "fta_web/static/js/i18n/whatifcaution.js does not exist"
    src = CATALOG.read_text(encoding="utf-8")
    match = re.search(r"export default \{(.*?)\n\};", src, re.S)
    assert match, "whatifcaution.js: could not locate `export default { ... };`"
    block = match.group(1)
    assert "\n  en:" in block and "\n  ja:" in block, "whatifcaution.js needs an en: and a ja: section"
    en_block, ja_block = block.split("\n  ja:", 1)
    return ({k: unescape(v) for k, v in _ENTRY.findall(en_block)},
            {k: unescape(v) for k, v in _ENTRY.findall(ja_block)})


def other_catalog_keys():
    keys = {}
    sources = [MAIN_JS] + sorted((STATIC / "i18n").glob("*.js"))
    for path in sources:
        if path == CATALOG:
            continue
        for key, _ in _ENTRY.findall(path.read_text(encoding="utf-8")):
            keys.setdefault(key, path.name)
    return keys


def text_of(language, key):
    en, ja = catalog()
    return (en if language == "en" else ja)[key]


# ------------------------------------------------------------------- the catalog


def test_the_expected_table_is_the_seven_keys_of_the_design():
    assert len(KEYS) == 7 and len(set(KEYS)) == 7
    assert sorted(EXPECTED) == sorted(KEYS) == sorted(PLACEHOLDERS)
    for en, ja in EXPECTED.values():
        assert en and ja and en != ja
    assert EXPECTED["whatif.caution.ccfNotApplied"][0] == "CCF group not applied at baseline; CCF not included"


def test_the_catalog_has_exactly_the_seven_keys_in_both_languages():
    en, ja = catalog()
    assert len(en) == len(ja) == 7
    assert sorted(en) == sorted(KEYS)
    assert sorted(ja) == sorted(KEYS)


@pytest.mark.parametrize("key", KEYS)
def test_en_and_ja_have_the_same_placeholders_and_are_translated(key):
    en, ja = catalog()
    assert en[key].strip() and ja[key].strip()
    assert sorted(_PLACEHOLDER.findall(en[key])) == sorted(PLACEHOLDERS[key]), key
    assert sorted(_PLACEHOLDER.findall(ja[key])) == sorted(PLACEHOLDERS[key]), key
    assert en[key] != ja[key], "%s is not translated" % key


@pytest.mark.parametrize("language", ["en", "ja"])
@pytest.mark.parametrize("key", KEYS)
def test_each_string_is_the_designs(key, language):
    assert text_of(language, key) == EXPECTED[key][0 if language == "en" else 1]


def test_the_catalog_is_exactly_the_text_of_design_section_4():
    en, ja = catalog()
    assert en == {key: pair[0] for key, pair in EXPECTED.items()}
    assert ja == {key: pair[1] for key, pair in EXPECTED.items()}


@pytest.mark.parametrize("key", KEYS)
def test_every_japanese_string_has_kana_or_kanji_and_no_stray_english_word(key):
    text = text_of("ja", key)
    assert KANA_KANJI.search(text), "%s has no kana or kanji: %r" % (key, text)
    rest = _PLACEHOLDER.sub("", text)
    for word in JA_LATIN_OK:
        rest = rest.replace(word, "")
    assert not re.search(r"[A-Za-z]{2,}", rest), "%s has an English word: %r" % (key, text)


def test_the_japanese_texts_use_full_width_parentheses_and_keep_the_product_name():
    more = text_of("ja", "whatif.caution.more")
    assert more.startswith("（") and more.endswith("）")
    assert "(" not in more and ")" not in more
    assert "What-if" in text_of("ja", "whatif.caution.cutsets")
    assert "What-if" not in text_of("en", "whatif.caution.cutsets")    # the English text says what-if


# ------------------------------------------------------------------- one line, no figures


@pytest.mark.parametrize("key", [k for k in KEYS if not k.endswith((".more", ".badge"))])
def test_each_string_fits_one_line_at_the_default_pane(key):
    assert len(text_of("en", key)) <= MAX_EN, (key, len(text_of("en", key)))
    assert len(text_of("ja", key)) <= MAX_JA, (key, len(text_of("ja", key)))


def test_the_not_applied_text_is_inside_the_design_bounds():
    """DESIGN 10.4: en 51 characters (bound 100), ja 36 (bound 56); no placeholder, no digit."""
    en, ja = text_of("en", "whatif.caution.ccfNotApplied"), text_of("ja", "whatif.caution.ccfNotApplied")
    assert len(en) <= MAX_EN and len(ja) <= MAX_JA_NOT_APPLIED
    assert not _PLACEHOLDER.search(en) and not _PLACEHOLDER.search(ja)


def test_the_badge_word_is_one_short_word_in_each_language():
    en, ja = text_of("en", "whatif.caution.badge"), text_of("ja", "whatif.caution.badge")
    assert en == "Caution" and ja == "注意"
    assert len(en) <= MAX_BADGE_EN and len(ja) <= MAX_BADGE_JA
    assert " " not in en and " " not in ja


def test_the_more_suffix_is_short():
    assert len(text_of("en", "whatif.caution.more")) <= MAX_MORE
    assert len(text_of("ja", "whatif.caution.more")) <= MAX_MORE


@pytest.mark.parametrize("language", ["en", "ja"])
@pytest.mark.parametrize("key", KEYS)
def test_the_only_digits_are_the_ones_of_the_design(key, language):
    """No result figure and no value of the user's data: the placeholders ({limit}, {n}) are filled
    at run time; a text holds the 1 of "probability 1" and the 2 of "λτ/2" and nothing else."""
    text = _PLACEHOLDER.sub("", text_of(language, key))
    assert "".join(re.findall(r"[0-9]", text)) == DIGITS.get(key, ""), (key, text)


# ------------------------------------------------------------------- FN-64


def fn64_hits(strings_en, strings_ja):
    hits = []
    for text in strings_en:
        found = FN64_EN.search(text)
        if found:
            hits.append((found.group(0), text))
    for text in strings_ja:
        hits.extend((word, text) for word in FN64_JA if word in text)
    return hits


def test_no_caution_text_claims_compliance_or_an_absolute():
    en, ja = catalog()
    assert fn64_hits(en.values(), ja.values()) == []
    for text in en.values():
        assert not ABSOLUTE_EN.search(text), text


def test_the_fn64_search_itself_finds_what_it_should():
    """Guard the guard: the word list and the whole-word rule."""
    assert fn64_hits(["complies with a standard", "ISO Conformity", "Certification"], []) != []
    assert fn64_hits([], ["JIS に準拠", "適合性", "認証済み"]) != []
    assert fn64_hits(["a conformal layer", "certify"], []) == []


# ------------------------------------------------------------------- registration and neighbours


def test_no_key_is_defined_in_another_catalog():
    en, _ja = catalog()
    elsewhere = other_catalog_keys()
    assert {k: elsewhere[k] for k in en if k in elsewhere} == {}


def test_the_what_if_catalog_does_not_hold_the_caution_keys():
    """The 30 keys of i18n/whatif.js are pinned by the protected acceptance test: a caution key
    there would break it."""
    assert WHATIF_CATALOG.is_file()
    assert "whatif.caution" not in WHATIF_CATALOG.read_text(encoding="utf-8")


def test_the_shell_loads_the_catalog_after_the_what_if_one():
    source = MAIN_JS.read_text(encoding="utf-8")
    assert "'./i18n/whatifcaution.js'" in source
    assert source.index("'./i18n/whatif.js'") < source.index("'./i18n/whatifcaution.js'")


def test_the_tab_registers_the_catalog_itself():
    source = TAB_JS.read_text(encoding="utf-8")
    assert "i18n/whatifcaution.js" in source
    assert "registerStrings" in source[source.index("i18n/whatifcaution.js"):]


def test_apostrophes_are_escaped_so_the_file_parses_as_single_quoted_strings():
    assert CATALOG.is_file(), "fta_web/static/js/i18n/whatifcaution.js does not exist"
    lines = [ln for ln in CATALOG.read_text(encoding="utf-8").splitlines()
             if re.match(r"\s+'[A-Za-z0-9_.]+'\s*:", ln)]
    assert len(lines) == 2 * len(KEYS)
    for line in lines:
        assert _ENTRY.fullmatch(line.strip().rstrip(",")), "not one single-quoted entry: %r" % line


def test_the_catalog_file_has_the_shape_of_the_other_feature_catalogs():
    src = CATALOG.read_text(encoding="utf-8") if CATALOG.is_file() else ""
    assert src, "fta_web/static/js/i18n/whatifcaution.js does not exist"
    assert re.search(r"^export default \{\n  en: \{", src, re.M)
    assert re.search(r"^  \},\n  ja: \{", src, re.M)
    assert src.rstrip().endswith("};")
