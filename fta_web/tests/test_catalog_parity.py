"""
The English and Japanese UI catalogs must stay in lockstep.

`STRINGS.en` and `STRINGS.ja` live in `fta_web/static/js/main.js`. During
P2-P5 the English side grew by ~165 keys and the Japanese side did not, so
switching to Japanese produced a half-English UI and nobody noticed until P6.
This test is the guard that would have caught it at each phase.

It parses the catalog with a regex rather than executing JS -- good enough for
flat `'key': 'value'` entries, which is all the catalog uses.
"""
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_JS = REPO_ROOT / "fta_web" / "static" / "js" / "main.js"

_ENTRY = re.compile(r"'([A-Za-z0-9_.]+)'\s*:\s*'((?:[^'\\]|\\.)*)'")
_PLACEHOLDER = re.compile(r"\{[A-Za-z0-9_]+\}")

#: Values that are legitimately identical in both languages -- brand names,
#: shell commands, gate symbols. A key here may have en == ja without failing.
_IDENTICAL_OK = {
    "btn.excel",   # "Excel" is "Excel"
    "btn.json",    # file-format names, unchanged in Japanese engineering use
    "btn.xml",
    "cap.excel.cmd",  # a shell command; translating it would break it
    "ai.provider.openai",     # brand names
    "ai.provider.anthropic",
    "ai.provider.google",
}


def _catalogs():
    src = MAIN_JS.read_text(encoding="utf-8")
    m = re.search(r"const STRINGS = \{(.*?)\n\};", src, re.S)
    assert m, "could not locate `const STRINGS = { ... }` in main.js"
    block = m.group(1)
    assert "\n  ja:" in block, "catalog has no `ja:` section"
    en_block, ja_block = block.split("\n  ja:", 1)
    en = dict(_ENTRY.findall(en_block))
    ja = dict(_ENTRY.findall(ja_block))
    return en, ja


def test_every_english_key_has_a_japanese_entry():
    en, ja = _catalogs()
    missing = sorted(set(en) - set(ja))
    assert not missing, (
        "%d English keys have no Japanese translation:\n  %s"
        % (len(missing), "\n  ".join(missing))
    )


def test_no_orphan_japanese_keys():
    en, ja = _catalogs()
    orphans = sorted(set(ja) - set(en))
    assert not orphans, (
        "%d Japanese keys have no English counterpart (dead entries):\n  %s"
        % (len(orphans), "\n  ".join(orphans))
    )


def test_placeholders_match_between_languages():
    en, ja = _catalogs()
    mismatches = []
    for key in set(en) & set(ja):
        en_ph = set(_PLACEHOLDER.findall(en[key]))
        ja_ph = set(_PLACEHOLDER.findall(ja[key]))
        if en_ph != ja_ph:
            mismatches.append("%s: en=%s ja=%s" % (key, sorted(en_ph), sorted(ja_ph)))
    assert not mismatches, (
        "placeholder sets differ (a dropped {name} is a runtime bug):\n  %s"
        % "\n  ".join(mismatches)
    )


def test_japanese_values_are_actually_translated():
    """A ja entry equal to its en entry is a translation that never happened."""
    en, ja = _catalogs()
    untranslated = []
    for key in set(en) & set(ja):
        if en[key] != ja[key]:
            continue
        if key in _IDENTICAL_OK:
            continue
        # An entry with no letters (a symbol, a number) is fine identical.
        if not re.search(r"[A-Za-z]{2}", en[key]):
            continue
        untranslated.append("%s: %r" % (key, en[key]))
    assert not untranslated, (
        "%d keys have identical en/ja values and are not on the allow-list:\n  %s"
        % (len(untranslated), "\n  ".join(untranslated))
    )


@pytest.mark.parametrize("attr", ["data-i18n", "data-i18n-title", "data-i18n-aria", "data-i18n-placeholder"])
def test_template_i18n_attributes_reference_real_keys(attr):
    en, _ = _catalogs()
    index = (REPO_ROOT / "fta_web" / "templates" / "index.html").read_text(encoding="utf-8")
    referenced = set(re.findall(r'%s="([A-Za-z0-9_.]+)"' % re.escape(attr), index))
    missing = sorted(k for k in referenced if k not in en)
    assert not missing, "%s references keys absent from STRINGS.en: %s" % (attr, missing)
