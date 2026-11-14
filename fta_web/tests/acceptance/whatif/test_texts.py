"""F4 BRIEF criterion 9 (UI-18, FN-64) for the strings of the What-if tab, and the privacy rule.

* ``fta_web/static/js/i18n/whatif.js`` exists, has the 30 keys of DESIGN section 6 in en and ja
  with identical ``{placeholders}``, translated (no identical en/ja text), none of the keys the
  tab reuses from other catalogs;
* every one of the 30 en and 30 ja strings equals the text of DESIGN section 6 (revision 4),
  copied into ``EXPECTED`` (word for word, after the catalog's own ``\'`` escape rule); every
  ja string holds kana or kanji and no stray English word;
* the English strings SPEC quotes are exact: the banner "What-if values, not saved", "clamped
  to 1" and "cut sets from nominal values";
* ``main.js`` lists the catalog (the static tab button needs ``tab.whatif`` before the tab mounts);
* FN-64: no string holds comply, complies, compliant, compliance, conform, conforms, conformity,
  certified, certification (whole words, any case) in en, or 準拠, 適合, 認証 in ja, in the
  catalog and in the string literals of ``tabs/whatif.js``; a stem-based second pass is
  reported as a warning only;
* PRIVACY (public repo): no personal name, e-mail or user-folder path in a tracked or new file
  outside ``.division``.

The checks read the JS file as text (the same way ``test_catalog_parity.py`` does); until the
file exists each test fails on "does not exist".
"""
import re
import subprocess

import pytest

import whatif_support as W

REPO_ROOT = W.REPO_ROOT
STATIC = REPO_ROOT / "fta_web" / "static" / "js"
CATALOG = STATIC / "i18n" / "whatif.js"
MAIN_JS = STATIC / "main.js"

_ENTRY = re.compile(r"'([A-Za-z0-9_.]+)'\s*:\s*'((?:[^'\\]|\\.)*)'")
_PLACEHOLDER = re.compile(r"\{[A-Za-z0-9_]+\}")
FN64_EN = re.compile(r"\b(comply|complies|compliant|compliance|conform|conforms|conformity|"
                     r"certified|certification)\b", re.IGNORECASE)
FN64_JA = ("準拠", "適合", "認証")

#: DESIGN section 6 (revision 4): the 30 keys.
REQUIRED_KEYS = [
    "tab.whatif", "whatif.aria", "whatif.banner", "whatif.reset", "whatif.resetEvent",
    "whatif.resetAll", "whatif.resetAllTitle", "whatif.event", "whatif.factor",
    "whatif.factorTitle", "whatif.factorValue", "whatif.col.nominal", "whatif.col.whatif",
    "whatif.col.ratio", "whatif.ratioTitle", "whatif.row.paramQ", "whatif.baselineTitle",
    "whatif.ratioNone", "whatif.method.mcub", "whatif.method.treeWalk", "whatif.clamped",
    "whatif.group", "whatif.cutoffNote", "whatif.cutoffTitle", "whatif.incomplete",
    "whatif.notEvaluable", "whatif.loading", "whatif.empty", "whatif.stale", "whatif.failed",
]
#: Reused from other catalogs, not redefined (DESIGN section 6).
REUSED_KEYS = ["quant.lambda", "quant.q", "quant.invalidRange", "headline.label", "anl.eta",
               "tab.etaUnavailable"]
#: The placeholders the design gives to the keys that have any.
PLACEHOLDERS = {
    "whatif.resetEvent": ["{name}"],
    "whatif.factorValue": ["{f}"],
    "whatif.group": ["{group}", "{members}"],
    "whatif.notEvaluable": ["{name}"],
    "whatif.failed": ["{error}"],
}
#: The English strings SPEC (UI-15, FN-55, FN-56) quotes.
EXACT_EN = {
    "whatif.banner": "What-if values, not saved",
    "whatif.clamped": "clamped to 1",
    "whatif.cutoffNote": "cut sets from nominal values",
}

#: DESIGN section 6 (revision 4), copied verbatim: key -> (en, ja). DESIGN lives in .division and
#: is not pushed, so the table has to be here. The strings are design-locked on purpose; the GUI
#: section (s_whatif.js, ``T``) keeps its own copy as an independent oracle, and the two must say
#: the same. A catalog written with \uXXXX escapes is compared after ``unescape`` and the
#: ``\'`` rule, as the catalog-parity test reads it.
EXPECTED = {
    "tab.whatif": ("What-if", "What-if 分析"),
    "whatif.aria": ("What-if analysis", "What-if 分析"),
    "whatif.banner": ("What-if values, not saved", "What-if の値（保存されません）"),
    "whatif.reset": ("Reset", "リセット"),
    "whatif.resetEvent": ("Reset the factor of {name} to 1", "{name} の倍率を 1 に戻す"),
    "whatif.resetAll": ("Reset all", "すべてリセット"),
    "whatif.resetAllTitle": ("Set every factor back to 1", "すべての倍率を 1 に戻します"),
    "whatif.event": ("Event", "事象"),
    "whatif.factor": ("Factor", "倍率"),
    "whatif.factorTitle": (
        "Factor on the main parameter, from 1/100 to 100 (logarithmic scale)",
        "主パラメータにかける倍率（1/100 から 100、対数目盛）"),
    "whatif.factorValue": ("factor {f}", "倍率 {f}"),
    "whatif.col.nominal": ("Nominal", "公称値"),
    "whatif.col.whatif": ("What-if", "What-if 値"),
    "whatif.col.ratio": ("Ratio", "比"),
    "whatif.ratioTitle": (
        "What-if top event divided by the baseline top event",
        "What-if の頂上事象をベースラインの頂上事象で割った値"),
    "whatif.row.paramQ": ("Main parameter q", "主パラメータ q"),
    "whatif.baselineTitle": (
        "Baseline: the top event of the document with no factor",
        "ベースライン: 倍率をかけない文書の頂上事象"),
    "whatif.ratioNone": ("No ratio: the baseline is 0.", "ベースラインが 0 のため、比は求められません。"),
    "whatif.method.mcub": ("Method: min-cut upper bound (MCUB)", "手法: 最小カット上限（MCUB）"),
    "whatif.method.treeWalk": ("Method: tree walk", "手法: ツリー計算"),
    "whatif.clamped": ("clamped to 1", "1 に制限"),
    "whatif.group": (
        'This event is in the CCF group "{group}". The factor applies to every member: {members}.',
        "この事象は CCF グループ「{group}」のメンバーです。倍率は全メンバー（{members}）にかかります。"),
    "whatif.cutoffNote": ("cut sets from nominal values", "カットセットは公称値から求めています"),
    "whatif.cutoffTitle": (
        "The cut sets were found with the nominal probabilities and the cutoff of this document. "
        "Sets below the cutoff are not part of the what-if number.",
        "カットセットは公称値の確率とこの文書のカットオフで求めています。"
        "カットオフ未満のカットセットは What-if 値に含まれません。"),
    "whatif.incomplete": (
        "The top event is incomplete (the cut sets could not be finished), so there is no what-if top event.",
        "頂上事象が不完全なため（カットセットを最後まで求められませんでした）、What-if の頂上事象はありません。"),
    "whatif.notEvaluable": (
        "{name} has a missing parameter, so its factor cannot be applied.",
        "{name} はパラメータが不足しているため、倍率をかけられません。"),
    "whatif.loading": ("Computing the baseline…", "ベースラインを計算中…"),
    "whatif.empty": (
        "The tree has no basic events yet. Add some to try factors.",
        "ツリーに基本事象がありません。基本事象を追加すると倍率を試せます。"),
    "whatif.stale": (
        "The document changed, so the factors were reset to 1.",
        "文書が変更されたため、倍率を 1 に戻しました。"),
    "whatif.failed": ("The what-if could not be computed: {error}", "What-if を計算できませんでした: {error}"),
}
#: Latin words that may stay in a Japanese string: the product word and two abbreviations.
JA_LATIN_OK = ("What-if", "CCF", "MCUB")
KANA_KANJI = re.compile(r"[぀-ヿ一-鿿]")


def unescape(value):
    return value.replace("\\'", "'").replace("\\\\", "\\")


def catalog():
    """``(en, ja)`` dicts from ``export default { en: {...}, ja: {...} };``."""
    assert CATALOG.is_file(), "fta_web/static/js/i18n/whatif.js does not exist"
    src = CATALOG.read_text(encoding="utf-8")
    match = re.search(r"export default \{(.*?)\n\};", src, re.S)
    assert match, "whatif.js: could not locate `export default { ... };`"
    block = match.group(1)
    assert "\n  en:" in block and "\n  ja:" in block, "whatif.js needs an en: and a ja: section"
    en_block, ja_block = block.split("\n  ja:", 1)
    en = {k: unescape(v) for k, v in _ENTRY.findall(en_block)}
    ja = {k: unescape(v) for k, v in _ENTRY.findall(ja_block)}
    return en, ja


def other_catalog_keys():
    keys = {}
    for path in sorted((STATIC / "i18n").glob("*.js")):
        if path == CATALOG:
            continue
        for key, _ in _ENTRY.findall(path.read_text(encoding="utf-8")):
            keys.setdefault(key, path.name)
    return keys


def fn64_hits(strings_en, strings_ja):
    hits = []
    for text in strings_en:
        found = FN64_EN.search(text)
        if found:
            hits.append((found.group(0), text))
    for text in strings_ja:
        for word in FN64_JA:
            if word in text:
                hits.append((word, text))
    return hits


# ------------------------------------------------------------------- the catalog


def test_there_are_thirty_required_keys_in_this_test():
    assert len(REQUIRED_KEYS) == 30 and len(set(REQUIRED_KEYS)) == 30


def test_the_catalog_has_every_key_of_the_design_in_both_languages():
    en, ja = catalog()
    missing = [k for k in REQUIRED_KEYS if k not in en or k not in ja]
    assert not missing, missing


def test_the_catalog_is_in_en_ja_parity_with_the_same_placeholders_and_is_translated():
    en, ja = catalog()
    assert en and set(en) == set(ja), sorted(set(en) ^ set(ja))
    for key in en:
        assert en[key].strip() and ja[key].strip(), key
        assert sorted(_PLACEHOLDER.findall(en[key])) == sorted(_PLACEHOLDER.findall(ja[key])), key
        assert en[key] != ja[key], "%s is not translated" % key


@pytest.mark.parametrize("key, placeholders", sorted(PLACEHOLDERS.items()))
def test_the_placeholders_are_the_ones_the_design_names(key, placeholders):
    en, ja = catalog()
    assert sorted(_PLACEHOLDER.findall(en[key])) == sorted(placeholders)
    assert sorted(_PLACEHOLDER.findall(ja[key])) == sorted(placeholders)


def test_keys_without_a_placeholder_have_none():
    en, ja = catalog()
    for key in REQUIRED_KEYS:
        if key not in PLACEHOLDERS:
            assert not _PLACEHOLDER.search(en[key]) and not _PLACEHOLDER.search(ja[key]), key


@pytest.mark.parametrize("key", sorted(EXACT_EN))
def test_the_english_strings_the_spec_quotes_are_exact(key):
    en, _ja = catalog()
    assert en[key] == EXACT_EN[key]


def test_the_japanese_banner_is_not_the_english_one_and_keeps_the_what_if_name():
    en, ja = catalog()
    assert ja["whatif.banner"] != en["whatif.banner"]
    assert "What-if" in ja["whatif.banner"]
    assert re.search(r"[぀-ヿ一-鿿]", ja["whatif.banner"])  # real Japanese text


def test_the_expected_table_has_exactly_the_thirty_keys():
    assert sorted(EXPECTED) == sorted(REQUIRED_KEYS)
    for key, (en, ja) in EXPECTED.items():
        assert en and ja and en != ja, key


def test_the_catalog_is_exactly_the_text_of_design_section_6():
    """Every one of the 30 en and 30 ja strings, word for word (the other tests check shape)."""
    en, ja = catalog()
    assert en == {key: pair[0] for key, pair in EXPECTED.items()}
    assert ja == {key: pair[1] for key, pair in EXPECTED.items()}


@pytest.mark.parametrize("language", ["en", "ja"])
@pytest.mark.parametrize("key", sorted(EXPECTED))
def test_each_string_of_the_catalog_is_the_designs(key, language):
    """The same comparison one string at a time, so that a failure names the key."""
    en, ja = catalog()
    got = (en if language == "en" else ja)[key]
    assert got == EXPECTED[key][0 if language == "en" else 1]


def test_every_japanese_string_has_kana_or_kanji_and_no_stray_english_word():
    """A ja value of "xx" or an untranslated English sentence must not pass. Latin letters may
    stay only as the product word What-if, CCF, MCUB, placeholders and the one-letter q."""
    _en, ja = catalog()
    for key in REQUIRED_KEYS:
        text = ja[key]
        assert KANA_KANJI.search(text), "%s has no kana or kanji: %r" % (key, text)
        rest = _PLACEHOLDER.sub("", text)
        for word in JA_LATIN_OK:
            rest = rest.replace(word, "")
        assert not re.search(r"[A-Za-z]{2,}", rest), "%s has an English word: %r" % (key, text)


def test_no_key_is_defined_in_another_catalog_and_the_reused_ones_are_not_redefined():
    en, _ja = catalog()
    elsewhere = other_catalog_keys()
    clashes = {k: elsewhere[k] for k in en if k in elsewhere}
    assert not clashes, clashes
    for key in REUSED_KEYS:
        assert key not in en, "%s is reused, not redefined" % key
        assert key in elsewhere, "%s (reused by the tab) is not in any catalog" % key


def test_the_catalog_is_registered_in_the_shell():
    source = MAIN_JS.read_text(encoding="utf-8")
    assert "'./i18n/whatif.js'" in source


def test_apostrophes_are_escaped_so_the_file_parses_as_single_quoted_strings():
    src = CATALOG.read_text(encoding="utf-8") if CATALOG.is_file() else ""
    assert src, "fta_web/static/js/i18n/whatif.js does not exist"
    lines = [ln for ln in src.splitlines() if re.match(r"\s+'[A-Za-z0-9_.]+'\s*:", ln)]
    assert len(lines) >= 2 * len(REQUIRED_KEYS)
    for line in lines:
        assert _ENTRY.fullmatch(line.strip().rstrip(",")), "not one single-quoted entry: %r" % line


# ------------------------------------------------------------------ FN-64


def test_no_string_of_the_catalog_claims_compliance():
    en, ja = catalog()
    assert fn64_hits(en.values(), ja.values()) == []


def test_the_fn64_search_itself_finds_what_it_should():
    """Guard the guard: the word list and the whole-word rule."""
    assert fn64_hits(["complies with a standard", "ISO Conformity", "Certification"], []) != []
    assert fn64_hits(["a compliant design"], []) != []
    assert fn64_hits(["a conformal layer", "certify"], []) == []
    assert fn64_hits([], ["JIS に準拠", "適合性", "認証済み"]) != []


def string_literals(source):
    """The text of every string literal ('...', "..." and `...`) of a JavaScript source,
    comments left out (an apostrophe in a comment must not open a string)."""
    out = []
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        if source.startswith("//", i):
            end = source.find("\n", i)
            i = n if end < 0 else end
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = n if end < 0 else end + 2
        elif ch in "'\"`":
            j = i + 1
            while j < n and source[j] != ch:
                j += 2 if source[j] == "\\" else 1
            out.append(source[i + 1:j])
            i = j + 1
        else:
            i += 1
    return out


def test_the_string_literal_reader_finds_strings_and_skips_comments():
    sample = (
        "// don't 'confuse' me\n"
        "const a = 'it\\'s compliant', b = \"x\" + `y ${z}`; /* 'certified' */ const c = 1;\n"
        "// 'conform'\n")
    assert string_literals(sample) == ["it\\'s compliant", "x", "y ${z}"]


WHATIF_JS = STATIC / "tabs" / "whatif.js"


def test_no_string_literal_of_the_tab_code_claims_compliance():
    """SPEC says "new strings": text written in code (the chip text, tick labels, the unit and
    the multiplication sign) is not in the catalog, so the word search also runs over every
    string literal of ``tabs/whatif.js``. Until the file exists this fails on "does not exist"."""
    assert WHATIF_JS.is_file(), "fta_web/static/js/tabs/whatif.js does not exist"
    literals = string_literals(WHATIF_JS.read_text(encoding="utf-8"))
    assert literals, "no string literal found: the reader is broken"
    assert fn64_hits(literals, literals) == []


#: Advisory second pass (not part of SPEC's list): word stems, and two more Japanese words.
FN64_STEMS_EN = re.compile(r"\b(compl(y|ie[sd]|iant|iance|ying)|conform\w*|certif\w*)", re.IGNORECASE)
FN64_STEMS_JA = FN64_JA + ("認定", "規格")


def test_stem_based_second_pass_over_the_strings_is_reported_not_enforced():
    """Reports (as a warning, never a failure) any string with a compliance-like stem that SPEC's
    word list does not cover: "conformance", "complying", "certify", "認定", "規格"."""
    import warnings

    en, ja = catalog()
    texts = list(en.values()) + list(ja.values())
    if WHATIF_JS.is_file():
        texts += string_literals(WHATIF_JS.read_text(encoding="utf-8"))
    found = sorted({t for t in texts
                    if FN64_STEMS_EN.search(t) or any(word in t for word in FN64_STEMS_JA)})
    if found:
        warnings.warn("FN-64 advisory: compliance-like stem in %d string(s): %s" % (
            len(found), "; ".join(found[:5])), stacklevel=1)


# -------------------------------------------------------------------- PRIVACY


def forbidden_pattern():
    # Stored as hex so that neither this file nor its compiled copy holds the words.
    hexed = ("6e65726761", "6b61746579", "6e657267616c6865617679")
    return "|".join(bytes.fromhex(h).decode("ascii") for h in hexed)


def test_no_personal_name_email_or_user_folder_in_a_tracked_file():
    proc = subprocess.run(
        ["git", "grep", "-i", "-n", "-E", forbidden_pattern(), "--", ".", ":!.division"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert proc.returncode == 1, "git grep found a personal string:\n%s" % proc.stdout[:2000]


def test_no_personal_name_email_or_user_folder_in_a_new_untracked_file():
    listing = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"],
                             cwd=str(REPO_ROOT), capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    assert listing.returncode == 0
    pattern = re.compile(forbidden_pattern(), re.IGNORECASE)
    offenders = []
    for rel in listing.stdout.splitlines():
        if rel.startswith(".division/"):
            continue
        try:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if pattern.search(text):
            offenders.append(rel)
    assert offenders == []
