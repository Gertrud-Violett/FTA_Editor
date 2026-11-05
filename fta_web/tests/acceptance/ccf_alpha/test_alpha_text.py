"""F2A BRIEF criterion 9 (UI-18, FN-64), Python side: ``fta_web/ccf_text.py``.

* the exact English and Japanese reason, message and fix of the four alpha codes (DESIGN 4.2),
  as the API serves them (``GET /api/ccf/groups`` and ``GET /api/analysis/validate``), with every
  placeholder filled;
* the status line of a group without a scheme: ``Not applied: testing scheme missing`` and
  ``未適用: 試験方式が未指定``;
* the new report texts of DESIGN 5 (``report.alpha.*``, ``report.testing.*``, ``label.subset``,
  ``assume.alpha``): exact, in en/ja key and placeholder parity;
* FN-64: none of comply, complies, compliant, compliance, conform, conforms, conformity,
  certified, certification (whole words, any case) in an English string and none of 準拠, 適合,
  認証 in a Japanese one, over all new strings;
* the placeholder rule of DESIGN 6: ``{n}`` members, ``{count}`` stored alpha values, ``{k}``
  position, ``{sum}``; ``{m}`` is not used; Japanese term "アルファファクター" in the new strings
  (never "α ファクター" or "α モデル"); no English count text that reads "1 members".
"""
import re

import pytest

import _alpha_models as M

_PLACEHOLDER = re.compile(r"\{[A-Za-z0-9_]+\}")
fn64_hits = M.fn64_hits     # one copy of the FN-64 search, in _alpha_models
ALLOWED = {"group", "member", "n", "count", "k", "sum", "testing", "q"}
NEW_REPORT_KEYS = ["report.alpha.sum", "report.testing.staggered", "report.testing.nonStaggered",
                   "report.testing.none", "report.alpha.overlap", "label.subset", "assume.alpha"]
MEMBERS3 = "Pump A, Pump B, Pump D"


def ccf_text():
    from fta_web import ccf_text as module

    return module


def alpha_lint_entries():
    module = ccf_text()
    out = {}
    for code in ("CCF_ALPHA_SIZE", "CCF_ALPHA_SUM", "CCF_ALPHA_NORMALISED", "CCF_NO_TESTING"):
        assert code in module.LINT, code
        for kind, entry in module.LINT[code].items():
            out[(code, kind)] = entry
    return out


def doc_for(members, alpha, testing="staggered"):
    return M.document(M.and_tree(list(members)), [M.agroup(
        members=members, alpha=alpha, testing=testing)])


#: (code, kind, document, placeholder values). {member} is the comma list of member names.
SERVED = [
    ("CCF_ALPHA_SIZE", "", doc_for(list("ABCDE"), (0.9, 0.04, 0.03, 0.02, 0.01)),
     {"n": 5}),
    ("CCF_ALPHA_SUM", "length", doc_for(["A", "B", "D"], (0.9, 0.1)),
     {"n": 3, "count": 2, "member": MEMBERS3}),
    ("CCF_ALPHA_SUM", "range", doc_for(["A", "B", "D"], [0.6, -0.1, 0.5]),
     {"k": 2, "n": 3, "member": MEMBERS3}),
    ("CCF_ALPHA_SUM", "sum", doc_for(["A", "B", "D"], (0.9, 0.1, 0.1)),
     {"sum": "1.1", "n": 3, "member": MEMBERS3}),
    ("CCF_ALPHA_NORMALISED", "", doc_for(["A", "B", "D"], (0.9555, 0.034, 0.011)),
     {"sum": "1.0005"}),
    ("CCF_NO_TESTING", "missing", doc_for(["A", "B", "D"], M.ALPHA3, None),
     {"member": MEMBERS3}),
    ("CCF_NO_TESTING", "unknown", doc_for(["A", "B", "D"], M.ALPHA3, "non-staggered"),
     {"testing": "non-staggered", "member": MEMBERS3}),
]
SERVED_IDS = ["%s_%s" % (c, k or "base") for c, k, _d, _p in SERVED]


@pytest.mark.parametrize("code, kind, doc, params", SERVED, ids=SERVED_IDS)
def test_the_exact_texts_of_each_code_and_kind_as_the_api_serves_them(api, code, kind, doc, params):
    api.open_doc(doc)
    (group,) = api.groups()["groups"]
    fill = dict(params, group=M.GROUP_NAME)
    status = group["status"]
    if code == "CCF_ALPHA_NORMALISED":
        (item,) = [w for w in status["warnings"] if w["code"] == code]
    else:
        assert status["code"] == code
        item = status
    for lang in ("en", "ja"):
        assert item["reason"][lang] == M.text_of(code, kind, lang, "reason", **fill)
        assert item["message"][lang] == M.text_of(code, kind, lang, "message", **fill)
    # the fix, served with the Validation issue
    status_code, body = api.get("/api/analysis/validate")
    assert status_code == 200
    (issue,) = [i for i in body["issues"] if i["code"] == code]
    for lang in ("en", "ja"):
        assert issue["params"]["text"][lang]["reason"] == M.text_of(code, kind, lang, "reason", **fill)
        assert issue["params"]["text"][lang]["message"] == M.text_of(code, kind, lang, "message", **fill)
        assert issue["params"]["text"][lang]["fix"] == M.text_of(code, kind, lang, "fix", **fill)
    assert issue["message"] == M.text_of(code, kind, "en", "message", **fill)


def test_ccf_text_lint_table_has_the_four_codes_with_the_kinds_of_the_design():
    entries = alpha_lint_entries()
    assert set(entries) >= {
        ("CCF_ALPHA_SIZE", ""), ("CCF_ALPHA_SUM", "length"), ("CCF_ALPHA_SUM", "range"),
        ("CCF_ALPHA_SUM", "sum"), ("CCF_ALPHA_NORMALISED", ""), ("CCF_NO_TESTING", "missing"),
        ("CCF_NO_TESTING", "unknown")}
    for key, expected in M.LINT_TEXTS.items():
        entry = entries[key]
        for field in ("reason", "message", "fix"):
            assert tuple(entry[field]) == tuple(expected[field]), (key, field)


def test_lint_text_function_fills_the_alpha_placeholders():
    module = ccf_text()
    out = module.lint_text("CCF_ALPHA_SUM", "length", {
        "group": "G", "member": "Pump A, Pump B", "n": 2, "count": 3})
    assert out["en"]["reason"] == "α values: 3, members: 2"
    assert out["ja"]["reason"] == "メンバー 2 件に対し α の値が 3 個"
    assert out["en"]["fix"] == "Enter α1 to α2 as numbers from 0 to 1 that add up to 1."
    assert "{" not in out["en"]["message"] and "{" not in out["ja"]["message"]


def test_placeholders_are_the_same_in_en_and_ja_and_only_the_documented_ones():
    for key, entry in alpha_lint_entries().items():
        for field in ("reason", "message", "fix"):
            en, ja = entry[field]
            found_en = sorted(_PLACEHOLDER.findall(en))
            found_ja = sorted(_PLACEHOLDER.findall(ja))
            assert found_en == found_ja, (key, field)
            assert {p.strip("{}") for p in found_en} <= ALLOWED, (key, field, found_en)
            assert "{m}" not in en + ja, (key, field)


def test_status_text_of_a_group_without_a_scheme():
    module = ccf_text()
    assert module.text("en", "notApplied", reason="testing scheme missing") == \
        "Not applied: testing scheme missing"
    assert module.text("ja", "notApplied", reason="試験方式が未指定") == "未適用: 試験方式が未指定"
    assert M.NO_SCHEME_STATUS_EN == "Not applied: testing scheme missing"
    assert M.NO_SCHEME_STATUS_JA == "未適用: 試験方式が未指定"


def test_high_q_has_an_alpha_kind_with_the_alpha_wording():
    module = ccf_text()
    out = module.lint_text("CCF_HIGH_Q", "alpha", {"group": "G", "member": "Pump A", "q": "0.02"})
    assert out["en"]["message"] == M.HIGH_Q_ALPHA_MESSAGE[0].format(group="G", member="Pump A", q="0.02")
    assert out["ja"]["message"] == M.HIGH_Q_ALPHA_MESSAGE[1].format(group="G", member="Pump A", q="0.02")
    beta = module.lint_text("CCF_HIGH_Q", "", {"group": "G", "member": "Pump A", "q": "0.02"})
    assert beta["en"]["reason"] == out["en"]["reason"]            # reason and fix as the beta kind
    assert beta["en"]["fix"] == out["en"]["fix"]
    assert beta["en"]["message"] != out["en"]["message"]


# ---------------------------------------------------------------- the report texts (DESIGN 5)


@pytest.mark.parametrize("key", NEW_REPORT_KEYS)
def test_the_new_report_texts_are_exact_in_both_languages(key):
    module = ccf_text()
    en, ja = M.REPORT_TEXT[key]
    assert module.TEXT["en"][key] == en
    assert module.TEXT["ja"][key] == ja
    assert module.text("en", key) == en and module.text("ja", key) == ja


def test_the_alpha_parameters_text_is_the_same_in_both_languages():
    module = ccf_text()
    assert module.TEXT["en"]["report.alpha.parameters"] == M.PARAMETERS_TEXT
    assert module.TEXT["ja"]["report.alpha.parameters"] == M.PARAMETERS_TEXT
    assert module.text("en", "report.alpha.parameters", values="0.9, 0.1") == "α = (0.9, 0.1)"


def test_ccf_text_key_and_placeholder_parity_covers_the_new_keys():
    module = ccf_text()
    en, ja = module.TEXT["en"], module.TEXT["ja"]
    assert set(en) == set(ja)
    for key in NEW_REPORT_KEYS + ["report.alpha.parameters"]:
        assert key in en and key in ja, key
        assert sorted(_PLACEHOLDER.findall(en[key])) == sorted(_PLACEHOLDER.findall(ja[key])), key
        assert "{m}" not in en[key] + ja[key], key
    for key in ("report.alpha.sum", "report.testing.staggered", "report.testing.nonStaggered",
                "report.testing.none", "report.alpha.overlap", "assume.alpha", "label.subset"):
        assert en[key] != ja[key], key


def test_the_new_japanese_strings_use_one_term_for_alpha_factor():
    module = ccf_text()
    new = [module.TEXT["ja"][k] for k in NEW_REPORT_KEYS if k != "report.alpha.overlap"]
    new += [e["reason"][1] for e in alpha_lint_entries().values()]
    new += [e["message"][1] for e in alpha_lint_entries().values()]
    new += [e["fix"][1] for e in alpha_lint_entries().values()]
    for text in new:
        assert "α ファクター" not in text and "α モデル" not in text, text
        assert "αファクター" not in text, text
    # the strings that name the model use the one term
    for key in ("assume.alpha",):
        assert "アルファファクターモデル" in module.TEXT["ja"][key]
    for key in (("CCF_ALPHA_SIZE", ""), ("CCF_NO_TESTING", "missing")):
        entry = alpha_lint_entries()[key]
        assert "アルファファクター" in entry["message"][1], key
    assert "アルファファクター" in alpha_lint_entries()[("CCF_ALPHA_SIZE", "")]["reason"][1]


def test_count_texts_are_number_neutral_in_english():
    """T6: "{n} members" / "{count} α values" would read "1 members" / "1 α values"."""
    for key, entry in alpha_lint_entries().items():
        for field in ("reason", "message", "fix"):
            en = entry[field][0]
            assert not re.search(r"\{(n|count)\} (members?|α values?)", en), (key, field, en)
    # the tab's resize hint can show a count of 1 (one stored value); the overlap line is only
    # printed for 3 or 4 members and may say "{n} members"
    assert not re.search(r"\{(n|count)\} (members?|α values?)",
                         M.CATALOG_EXACT["ccf.alpha.resize"][0])


# ---------------------------------------------------------------- tolerance self-guard


def test_every_relative_approx_in_this_folder_sets_abs_to_zero():
    """pytest's approx keeps a hidden absolute floor of 1e-12 when only ``rel=`` is given, which
    is as large as the probabilities under test (1e-5 to 1e-10): every relative tolerance would be
    far looser than stated (see ``_alpha_models.rel``). A call with ``rel=`` must also set
    ``abs=``."""
    from pathlib import Path

    needle = "pytest" + ".approx("
    offenders = []
    for path in sorted(Path(__file__).resolve().parent.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        start = source.find(needle)
        while start >= 0:
            depth, end = 1, start + len(needle)
            while depth and end < len(source):
                depth += {"(": 1, ")": -1}.get(source[end], 0)
                end += 1
            call = source[start:end]
            if "rel=" in call and "abs=" not in call:
                offenders.append((path.name, source.count("\n", 0, start) + 1))
            start = source.find(needle, end)
    assert offenders == []


# ---------------------------------------------------------------- FN-64


def new_strings():
    module = ccf_text()
    entries = alpha_lint_entries()
    en = [e[f][0] for e in entries.values() for f in ("reason", "message", "fix")]
    ja = [e[f][1] for e in entries.values() for f in ("reason", "message", "fix")]
    en += [module.TEXT["en"][k] for k in NEW_REPORT_KEYS + ["report.alpha.parameters"]]
    ja += [module.TEXT["ja"][k] for k in NEW_REPORT_KEYS + ["report.alpha.parameters"]]
    return en, ja


def test_no_new_python_text_claims_compliance():
    en, ja = new_strings()
    assert len(en) > 20
    assert fn64_hits(en, ja) == []


def test_the_fn64_search_itself_finds_what_it_should():
    assert fn64_hits(["complies with a standard", "ISO Conformity", "Certification"], []) != []
    assert fn64_hits(["a conformal layer", "certify"], []) == []
    assert fn64_hits([], ["JIS に準拠", "適合性", "認証済み"]) != []


def test_no_served_alpha_text_claims_compliance_and_every_placeholder_is_filled(api):
    seen = []
    codes = set()
    for _code, _kind, doc, _params in SERVED:
        api.open_doc(doc)
        (group,) = api.groups()["groups"]
        status = group["status"]
        for item in [status] + list(status["warnings"]) + list(status["errors"]):
            for field in ("reason", "message"):
                if isinstance(item.get(field), dict):
                    seen.extend(item[field][lang] for lang in ("en", "ja"))
        _s, issues = api.get("/api/analysis/validate")
        codes.update(i["code"] for i in issues["issues"])
        for issue in issues["issues"]:
            text = (issue.get("params") or {}).get("text")
            if str(issue["code"]).startswith("CCF_") and text:
                for lang in ("en", "ja"):
                    seen.extend(text[lang][f] for f in ("reason", "message", "fix"))
    assert {"CCF_ALPHA_SIZE", "CCF_ALPHA_SUM", "CCF_ALPHA_NORMALISED", "CCF_NO_TESTING"} <= codes
    assert len(seen) > 40
    assert fn64_hits(seen, seen) == []
    for text in seen:
        assert text.strip() and not _PLACEHOLDER.search(text), text
