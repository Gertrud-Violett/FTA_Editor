"""F2 BRIEF criteria 25 and 26 (UI-18, FN-64, UI-7, FN-69) and the privacy rule.

* the new UI catalog ``fta_web/static/js/i18n/ccf.js`` exists and has en/ja
  parity with identical placeholders; the strings SPEC quotes are exact;
* ``fta_web/ccf_text.py`` (the server-side texts: lint, report, CLI) has en/ja
  key parity and placeholder parity;
* the six UI-7 assumptions and the FN-67 note are the same text in the catalog
  and in ``ccf_text.py``, in en and ja, and equal the SPEC / DESIGN wording;
* FN-64: no new en string holds comply, complies, compliant, compliance,
  conform, conforms, conformity, certified, certification (whole words, any
  case) and no new ja string holds 準拠, 適合 or 認証;
* FN-69: the CHANGELOG ``[Unreleased]`` section carries both sentences;
* PRIVACY (CEO rule, public repo): no personal name, e-mail or user-folder path
  in a tracked file outside ``.division``.
"""
import re
import subprocess
from pathlib import Path

import pytest

import _ccf_models as M

REPO_ROOT = Path(__file__).resolve().parents[4]
CATALOG = REPO_ROOT / "fta_web" / "static" / "js" / "i18n" / "ccf.js"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

_ENTRY = re.compile(r"'([A-Za-z0-9_.]+)'\s*:\s*'((?:[^'\\]|\\.)*)'")
_PLACEHOLDER = re.compile(r"\{[A-Za-z0-9_]+\}")
FN64_EN = re.compile(r"\b(comply|complies|compliant|compliance|conform|conforms|conformity|"
                     r"certified|certification)\b", re.IGNORECASE)
FN64_JA = ("準拠", "適合", "認証")

#: Strings that are the same in both languages by design (DESIGN 11.1).
#: "n/a (CCF)" is the same text in en and ja (R0 (d); the diagram, Excel and report show it as is).
IDENTICAL_OK = {"ccf.label.event", "details.ccfNa"}


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


def flatten(value, trail=""):
    """{path: string} of every string leaf of nested dicts / lists / tuples."""
    out = {}
    if isinstance(value, str):
        out[trail] = value
    elif isinstance(value, dict):
        for key, item in value.items():
            out.update(flatten(item, "%s/%s" % (trail, key)))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            out.update(flatten(item, "%s[%d]" % (trail, index)))
    return out


def ccf_text_module():
    from fta_web import ccf_text

    return ccf_text


def python_texts():
    """``({path: en string}, {path: ja string})`` of ``ccf_text.TEXT``."""
    table = ccf_text_module().TEXT
    assert set(table) >= {"en", "ja"}
    return flatten(table["en"]), flatten(table["ja"])


def all_python_strings():
    """Every string of every public table in ``ccf_text`` (TEXT and the lint tables)."""
    module = ccf_text_module()
    strings = []
    for name in dir(module):
        if name.startswith("_"):
            continue
        value = getattr(module, name)
        if isinstance(value, (dict, list, tuple)):
            strings.extend(flatten(value).values())
    return strings


# ------------------------------------------------------------ the JS catalog


REQUIRED_KEYS = [
    "tab.ccf", "tab.ccfEtaUnavailable", "ccf.new", "ccf.newTitle", "ccf.newNeedTwo",
    "ccf.addSelected", "ccf.col.name", "ccf.col.model", "ccf.col.params", "ccf.col.members",
    "ccf.col.source", "ccf.col.status", "ccf.model.beta", "ccf.status.applied",
    "ccf.status.notApplied", "ccf.status.warning", "ccf.memberMissing", "ccf.empty",
    "ccf.etaNote", "ccf.loading", "ccf.failed", "ccf.editor.new", "ccf.editor.edit",
    "ccf.field.name", "ccf.field.model", "ccf.field.beta", "ccf.field.source",
    "ccf.field.members", "ccf.betaHint", "ccf.err.beta", "ccf.err.name", "ccf.create",
    "ccf.cancel", "ccf.delete", "ccf.deleteTitle", "ccf.removeMember", "ccf.created",
    "ccf.deleted", "ccf.skippedNotBasic", "ccf.defaultName", "ccf.assumptions",
    "ccf.assume.model", "ccf.assume.qt", "ccf.assume.beta", "ccf.assume.split",
    "ccf.assume.headline", "ccf.assume.sampling", "ccf.note", "ccf.label.independent",
    "ccf.label.event", "ccf.badgeTitle", "ccf.badgeOff", "ccf.details.group", "ccf.details.qt",
    "ccf.details.independent", "ccf.details.event", "ccf.details.notApplied",
    "details.ccfMcub", "details.ccfNa", "headline.ccf.includes", "headline.ccf.includes1",
    "headline.ccf.incomplete", "headline.ccf.walk", "headline.ccf.reason.time",
    "headline.ccf.reason.error", "headline.ccf.reason.cap", "headline.ccf.notApplied",
    "headline.ccf.notApplied1", "headline.ccf.notAppliedTitle", "diagram.ccfGates",
    "val.ccfNeedsAdvanced", "val.jumpGroupTitle", "val.code.LOAD_REPAIR.newer_format",
    "val.code.LOAD_REPAIR.ccf_invalid", "history.ccf", "tree.ccfMcub",
]

#: The strings SPEC / DESIGN 13.1 spell out (en, ja).
EXACT = {
    "tab.ccf": ("CCF groups", "CCF グループ"),
    "ccf.field.beta": ("β (dimensionless, 0 to 1)", "β（無次元、0 から 1）"),
    "ccf.status.applied": ("Applied", "適用中"),
    "ccf.status.notApplied": ("Not applied: {reason}", "未適用: {reason}"),
    "ccf.note": (M.NOTE_EN, M.NOTE_JA),
    "ccf.label.independent": ("{name} (independent part)", "{name}（独立部分）"),
    "details.ccfNa": ("n/a (CCF)", "n/a (CCF)"),  # same in both languages (R0 (d); text review)
    "headline.ccf.includes": ("MCUB, includes CCF ({n} groups)", "MCUB、CCF を含む（{n} グループ）"),
    "headline.ccf.includes1": ("MCUB, includes CCF (1 group)", "MCUB、CCF を含む（1 グループ）"),
    "headline.ccf.incomplete": ("incomplete, CCF not included", "不完全、CCF は含まれていません"),
    "headline.ccf.walk": ("tree walk, without CCF; cut sets cut short ({reason})",
                          "ツリー計算（CCF なし）、カットセットが途中で打ち切られました（{reason}）"),
    "headline.ccf.notApplied": ("{n} CCF groups not applied", "CCF グループ {n} 件が未適用"),
    "headline.ccf.notApplied1": ("1 CCF group not applied", "CCF グループ 1 件が未適用"),
}
for _id in M.ASSUMPTIONS_EN:
    EXACT["ccf.assume." + _id] = (M.ASSUMPTIONS_EN[_id], M.ASSUMPTIONS_JA[_id])


def test_the_ccf_catalog_has_every_key_of_the_design_in_both_languages():
    en, ja = catalog()
    missing = [k for k in REQUIRED_KEYS if k not in en or k not in ja]
    assert not missing, missing


def test_the_ccf_catalog_is_in_en_ja_parity_with_the_same_placeholders():
    en, ja = catalog()
    assert en and set(en) == set(ja)
    for key in en:
        assert en[key].strip() and ja[key].strip(), key
        assert sorted(_PLACEHOLDER.findall(en[key])) == sorted(_PLACEHOLDER.findall(ja[key])), key
        if key not in IDENTICAL_OK:
            assert en[key] != ja[key], "%s is not translated" % key


@pytest.mark.parametrize("key", sorted(EXACT))
def test_the_strings_quoted_by_the_spec_are_exact_in_the_catalog(key):
    en, ja = catalog()
    assert (en[key], ja[key]) == EXACT[key]


# ------------------------------------------------------- the Python text table


def test_ccf_text_has_en_ja_key_and_placeholder_parity():
    en, ja = python_texts()
    assert en and set(en) == set(ja), sorted(set(en) ^ set(ja))
    for path in en:
        assert en[path].strip() and ja[path].strip(), path
        assert sorted(_PLACEHOLDER.findall(en[path])) == sorted(_PLACEHOLDER.findall(ja[path])), path


def test_ccf_text_exposes_the_text_function_for_both_languages():
    module = ccf_text_module()
    assert callable(module.text)
    en, ja = python_texts()
    flat = sorted(k for k in en if k.count("/") == 1 and "{" not in en[k] and "}" not in en[k])
    assert flat, "ccf_text.TEXT has no flat key to look up with text(lang, key)"
    leaf = flat[0].split("/")[-1]
    assert module.text("en", leaf) == en[flat[0]]
    assert module.text("ja", leaf) == ja[flat[0]]


def test_the_six_assumptions_and_the_note_are_the_same_text_in_python_and_in_the_catalog():
    cat_en, cat_ja = catalog()
    py_en, py_ja = python_texts()
    py_en_values, py_ja_values = set(py_en.values()), set(py_ja.values())
    for ident in M.ASSUMPTIONS_EN:
        key = "ccf.assume." + ident
        assert cat_en[key] == M.ASSUMPTIONS_EN[ident], key  # SPEC UI-7 / DESIGN 13.1
        assert cat_ja[key] == M.ASSUMPTIONS_JA[ident], key
        assert cat_en[key] in py_en_values, "ccf_text.py (en) lacks %s" % key
        assert cat_ja[key] in py_ja_values, "ccf_text.py (ja) lacks %s" % key
    assert cat_en["ccf.note"] == M.NOTE_EN and cat_ja["ccf.note"] == M.NOTE_JA
    assert M.NOTE_EN in py_en_values and M.NOTE_JA in py_ja_values


def test_ccf_text_holds_the_report_only_strings_of_the_design():
    py_en, py_ja = python_texts()
    en_values, ja_values = set(py_en.values()), set(py_ja.values())
    for en_text, ja_text in (
        ("Common-cause failure (CCF) groups", "共通原因故障（CCF）グループ"),
        ("Testing scheme", "試験方式"),
        ("Formulas", "計算式"),
        ("Not applied: {reason}. Results exclude this group.",
         "未適用: {reason}。結果にはこのグループは含まれていません。"),
        ("[incomplete, CCF not included]", None),
        (M.OVERLAP_EN, M.OVERLAP_JA),
        ("Applied", "適用中"),
        ("Not applied: {reason}", "未適用: {reason}"),
    ):
        assert en_text in en_values, en_text
        if ja_text is not None:
            assert ja_text in ja_values, ja_text


# ------------------------------------------------------------- FN-64, UI-18


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


def test_no_new_catalog_string_claims_compliance():
    en, ja = catalog()
    assert fn64_hits(en.values(), ja.values()) == []


def test_no_new_python_text_claims_compliance():
    strings = all_python_strings()
    assert strings
    assert fn64_hits(strings, strings) == []


def test_the_fn64_search_itself_finds_what_it_should():
    """Guard the guard: the word list and the whole-word rule."""
    assert fn64_hits(["complies with a standard", "ISO Conformity", "Certification"], []) != []
    assert fn64_hits(["a compliant design"], []) != []
    assert fn64_hits(["a conformal layer", "certify"], []) == []  # not whole words of the list
    assert fn64_hits([], ["JIS に準拠", "適合性", "認証済み"]) != []


def test_no_lint_text_claims_compliance_and_every_placeholder_is_filled(api):
    """The lint texts as the API serves them (en and ja, reason / message / fix)."""
    seen = []
    for case in M.lint_cases():
        api.open_doc(case["doc"])
        listing = api.groups()
        for group in listing["groups"]:
            status = group["status"]
            for item in [status] + list(status["warnings"]) + list(status["errors"]):
                for field in ("reason", "message"):
                    if isinstance(item.get(field), dict):
                        seen.extend((case["id"], lang, item[field][lang]) for lang in ("en", "ja"))
        status_code, issues = api.get("/api/analysis/validate")
        for issue in issues["issues"]:
            text = (issue.get("params") or {}).get("text")
            if str(issue["code"]).startswith("CCF_") and text:
                for lang in ("en", "ja"):
                    seen.extend((case["id"], lang, text[lang][f]) for f in ("reason", "message", "fix"))
    assert len(seen) > 100
    en = [t for _id, lang, t in seen if lang == "en"]
    ja = [t for _id, lang, t in seen if lang == "ja"]
    assert fn64_hits(en, ja) == []
    for case_id, lang, text in seen:
        assert not _PLACEHOLDER.search(text), (case_id, lang, text)  # no {group} left unformatted
        assert text.strip()


# --------------------------------------------------------------- FN-69


def unreleased_section():
    text = CHANGELOG.read_text(encoding="utf-8")
    start = text.index("## [1.9.0]")
    end = text.find("\n## [", start + 1)
    return text[start:end if end != -1 else len(text)]


def squeeze(text):
    return re.sub(r"\s+", "", text)  # a sentence may be wrapped across lines


def test_the_changelog_unreleased_section_carries_both_fn_69_sentences():
    section = unreleased_section()
    assert "CCF" in section
    squeezed = squeeze(section)
    assert squeeze(M.FN69_EN) in squeezed, "the English FN-69 sentence is missing"
    assert squeeze(M.FN69_JA) in squeezed, "the Japanese FN-69 sentence is missing"


# -------------------------------------------------------------- PRIVACY


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
        path = REPO_ROOT / rel
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if pattern.search(text):
            offenders.append(rel)
    assert offenders == []
