"""Test models, expected values and expected texts of the F2A (CCF alpha factor) tests.

Everything here is built from SPEC 7.1, 7.3, 7.4 and DESIGN sections 3, 4.2, 5, 6
and 8 of F2A, not from product code. No product module is imported at the top (a
helper that needs one imports it inside the function), so a missing alpha part
fails the test that needs it and nothing else.

The reference values R5 to R10h are COPIED from SPEC 7.4. The source errors of
SPEC 7.3 (S1 Eq. 5.10 Q3 = 3 alpha3 Q_t, the m = 4 rows of Tables 5-4 and 5-5,
the stray /4 of Table 5-5 "2 of 5") are not used anywhere: ``oracle_q`` derives
Q_k from S1 Eq. 5.6 and Eq. 5.7 only.

Names carry plain ASCII on purpose: a group name or a member name must be
findable in the English and in the Japanese text of a message.
"""
import copy
import io
import json
import math
import re
from itertools import combinations
from pathlib import Path

# --------------------------------------------------------------------------
# SPEC 7.4: the reference cases (Q_t = 1e-3), copied
# --------------------------------------------------------------------------

QT = 1e-3
#: S3 p. 7-16 alpha set of R7 to R10h.
ALPHA3 = (0.955, 0.034, 0.011)

REL12 = 1e-12   # "exact" rare-event values (SPEC 7.4)
REL9 = 1e-9     # MCUB and importance values (SPEC 7.4)

#: (value, absolute tolerance = half a unit of the last printed digit) for "rounded" values.
R5_Q1 = 9e-4
R5_Q2 = 1e-4                        # exact, equal to R1
R5_RARE = 1.0081e-4                 # R1 (SPEC 7.4): Q_1^2 + Q_2
R5_MCUB = 1.00809919e-4             # R1h
R6_Q2 = (9.5238095e-5, 5e-13)
R6H_Q1 = (9.0476190e-4, 5e-12)
R6H_RARE = (9.6056689e-5, 5e-13)
R6H_MCUB = (9.6056611e-5, 5e-13)
R7_CCF_PART = 6.2e-5                # 3 Q_2 + Q_3, exact
R7_Q1, R7_Q2, R7_Q3 = 9.55e-4, 1.7e-5, 1.1e-5   # DESIGN 3.2 reference table, SPEC 7.4 R7/R8 inputs
R8_CUTSETS = 7
R8_RARE = 6.4736075e-5              # 3 Q_1^2 + 3 Q_2 + Q_3, exact
R8H_MCUB = (6.47344749e-5, 5e-14)
R9_ALPHA_T = 1.056
R9_CCF_PART = (1.27841e-4, 5e-10)
R9_Q1 = (9.0435606e-4, 5e-12)       # DESIGN 3.2 reference table (rounded)
R9_Q2 = (3.2196970e-5, 5e-13)
R9_Q3 = (3.1250000e-5, 5e-13)
R9H_RARE = (1.302945e-4, 5e-11)
R9H_MCUB = (1.302880e-4, 5e-11)
R10_PUBLISHED = (1.10495760e-5, 5e-14)   # Q_1^3 + 3 Q_1 Q_2 + Q_3, overlapping events omitted
R10H_RARE = (1.10504430e-5, 5e-14)       # as the editor computes it: R10 + 3 Q_2^2


def near(value, expected, absolute):
    return abs(value - expected) <= absolute


def rel(expected, tol=REL12):
    """A purely relative comparison: ``pytest.approx(expected, rel=tol, abs=0.0)``.

    pytest's default is ``abs=1e-12`` and, when only ``rel=`` is given, the tolerance is
    ``max(rel * |expected|, 1e-12)``. The probabilities of this feature are 1e-5 to 1e-10, so
    that floor would make every "relative 1e-12" check about as loose as 1e-3 relative and
    would make a "differs at relative 1e-11" check impossible. Every approx call with ``rel=``
    in this folder therefore also sets ``abs=0.0`` (a self-guard test in ``test_alpha_text.py``
    fails otherwise). Half-unit ``near`` checks are absolute on purpose (SPEC 7.4 "rounded")."""
    import pytest

    return pytest.approx(expected, rel=tol, abs=0.0)


# --------------------------------------------------------------------------
# S1 Table 6-9 p. 104 (DESIGN 8) and the perf set
# --------------------------------------------------------------------------

#: (name, alpha, sum of the printed values as text). S1 Table 6-9 prints NO sum: the text is our own
#: sum of the eight printed values (exact fractions, engineering review 2026-11-02), which the
#: normalisation note must show.
TABLE_6_9 = [
    ("generic", (0.9624707, 1.74e-2, 1.30e-2, 7.08e-3), "0.9999507"),
    ("plant-specific", (0.9668498, 1.47e-2, 1.16e-2, 6.86e-3), "1.0000098"),
]
#: DESIGN 8 oracles at Q_t = 1e-3: (set, scheme) -> (Q_1, Q_2, Q_3, Q_4), relative 1e-12.
TABLE_6_9_Q = {
    ("generic", "staggered"): (9.6251815214490073e-4, 5.8002859540975374e-6,
                               4.3335469771993091e-6, 7.080349061208718e-6),
    ("generic", "nonStaggered"): (9.0407581054390202e-4, 1.0896206401201889e-5,
                                  1.2211265794450392e-5, 2.6601772869141165e-5),
    ("plant-specific", "staggered"): (9.6684032496481532e-4, 4.8999519804705916e-6,
                                      3.8666287737046844e-6, 6.8599327726588282e-6),
    ("plant-specific", "nonStaggered"): (9.1342382326216082e-4, 9.2584737236013045e-6,
                                         1.0959009713650524e-5, 2.5923726426083653e-5),
}
#: the perf_alpha_301 set (DESIGN 8 (b))
PERF_ALPHA = (0.95, 0.03, 0.01, 0.01)
PERF_Q = {
    "staggered": (9.5e-4, 1.0e-5, 3.3333333333333333e-6, 1.0e-5),
    "nonStaggered": (8.7962962962962962e-4, 1.8518518518518518e-5,
                     9.2592592592592591e-6, 3.7037037037037037e-5),
}


def oracle_q(m, alpha, testing, qt=QT):
    """[Q_1 .. Q_m] from S1 Eq. 5.6 (staggered) and Eq. 5.7-5.9 (non-staggered),
    alpha divided by its sum first (SPEC FN-43). Written here, independent of the product."""
    total = math.fsum(alpha)
    a = [x / total for x in alpha]
    if testing == "staggered":
        return [a[k - 1] / math.comb(m - 1, k - 1) * qt for k in range(1, m + 1)]
    alpha_t = math.fsum(k * a[k - 1] for k in range(1, m + 1))
    return [k / math.comb(m - 1, k - 1) * (a[k - 1] / alpha_t) * qt for k in range(1, m + 1)]


def subsets(m):
    """Index tuples of the CCF events of an m-member group: size 2..m, group order."""
    return [idx for k in range(2, m + 1) for idx in combinations(range(m), k)]


def subset_id(gid, members, idxs):
    """``ccf:<groupId>:<m1>+<m2>...`` (SPEC 7.5, FN-41), members in group order."""
    return "ccf:%s:%s" % (gid, "+".join(members[i] for i in idxs))


# --------------------------------------------------------------------------
# tree builders
# --------------------------------------------------------------------------

GROUP_NAME = "Relief valves"
IDS = ["A", "B", "C", "D", "E"]


def leaf(node_id, q=QT, name=None, quant=None, **extra):
    node = {"id": node_id, "name": name or node_id, "type": "Event", "logicGate": "OR",
            "probability": q, "notes": "", "links": [], "children": [],
            "quant": copy.deepcopy(quant) if quant is not None else {"model": "fixed"}}
    node.update(extra)
    return node


def gate(node_id, kind, children, name=None, type_="Event", **extra):
    """``kind`` is AND, OR or a gateType (KOFN, ...)."""
    node = {"id": node_id, "name": name or node_id, "type": type_, "probability": 1.0,
            "notes": "", "links": [], "children": children}
    if kind in ("AND", "OR"):
        node["logicGate"] = kind
    else:
        node["gateType"] = kind
        node["logicGate"] = "OR" if kind in ("KOFN", "XOR") else "AND"
    node.update(extra)
    return node


def pump(node_id, q=QT, **extra):
    return leaf(node_id, q, name="Pump %s" % node_id, **extra)


def top(children, **extra):
    return gate("root", "OR", children, name="Top event", type_="Root", **extra)


def and_tree(ids, q=QT):
    """Top event OR [ G1 AND [ pumps ] ]: the AND of the members (S1 Table 5-2 Case 1 for two,
    Case 3 for three: "1 out of 3")."""
    return top([gate("G1", "AND", [pump(i, q) for i in ids], name="Pumps fail")])


def or_tree(ids, q=QT):
    """Top event OR [ pumps ]: every member alone fails the top."""
    return top([pump(i, q) for i in ids])


def kofn_tree(ids, k, q=QT):
    """Top event OR [ k-of-n gate over the pumps ] (S1 Table 5-2 Case 4 for 2-of-3)."""
    return top([gate("V", "KOFN", [pump(i, q) for i in ids], name="Voting gate", k=k)])


def linked_tree(ids=("A", "B", "C")):
    """The members under G1 plus a leaf D that carries a link to the first member (FN-19)."""
    return top([
        gate("G1", "AND", [pump(i) for i in ids], name="Pumps fail"),
        gate("G2", "AND", [leaf("X"), leaf("D", QT, links=[
            {"target_id": ids[0], "relation": "OR"}])], name="Other"),
    ])


def agroup(gid="g1", name=GROUP_NAME, members=("A", "B"), alpha=(0.9, 0.1),
           testing="staggered", source="test", **over):
    """A stored alpha group: the eight keys of SPEC 7.1."""
    out = {"id": gid, "name": name, "model": "alpha", "beta": None,
           "alpha": None if alpha is None else list(alpha), "testing": testing,
           "members": None if members is None else list(members), "source": source}
    out.update(over)
    return out


def bgroup(gid="g1", name="Feed pumps", members=("A", "B"), beta=0.1, source="test", **over):
    """A stored beta group (F2)."""
    out = {"id": gid, "name": name, "model": "beta", "beta": beta, "alpha": None,
           "testing": None, "members": list(members), "source": source}
    out.update(over)
    return out


def document(tree, groups=None, mode="FTA", title="CCF alpha test", analysis=None):
    """A file as FTA Editor writes it. ``groups`` None writes no ``ccfGroups`` key."""
    doc = {"title": title, "date": "2026-10-28", "mode": mode}
    if groups:
        doc["fileFormatVersion"] = 2
    doc["tree"] = copy.deepcopy(tree)
    merged = dict(analysis or {})
    if groups is not None:
        merged["ccfGroups"] = copy.deepcopy(groups)
    if merged:
        doc["analysis"] = merged
    return doc


def alpha_document(ids=("A", "B", "C"), alpha=ALPHA3, testing="staggered", tree=None, **over):
    """One alpha group over ``ids`` in a tree (default: the AND of the members)."""
    tree = tree if tree is not None else and_tree(list(ids))
    return document(tree, [agroup(members=ids, alpha=alpha, testing=testing, **over)])


def write_doc(directory, doc, name="doc.json"):
    path = Path(directory) / name
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# readers
# --------------------------------------------------------------------------


def analysis_of(groups):
    return {"ccfGroups": groups}


LIMITS = {"timeBudgetS": 120}


def compute(tree, groups):
    from fta_web import cutsets

    return cutsets.compute(tree, analysis_of(groups), LIMITS)


def cut_set_ids(result):
    return [sorted(e["id"] for e in cs["events"]) for cs in result["cutSets"]]


def find_cut_set(result, ids):
    wanted = sorted(ids)
    for cs in result["cutSets"]:
        if sorted(e["id"] for e in cs["events"]) == wanted:
            return cs
    raise AssertionError("no cut set with events %s in %s" % (wanted, cut_set_ids(result)))


def event_q(tree, groups):
    """``{event id: q}`` of the compiled structure (every event of the tree and of the groups)."""
    from fta_web import logic

    s = logic.compile_tree(tree, analysis_of(groups))
    return {e["id"]: e["q"] for e in s.events}


def compiled(tree, groups):
    from fta_web import logic

    return logic.compile_tree(tree, analysis_of(groups))


def expansion(group, qt=QT):
    """``ccf.event_probabilities`` of a stored alpha group: (independent, {idxs: q})."""
    from fta_web import ccf

    m = len(group["members"])
    result = ccf.event_probabilities("alpha", group, [qt] * m)
    return tuple(result.independent), [(tuple(idx), q) for idx, q in result.events]


def docx_text(blob):
    """``(full_text, table_cell_texts, tables)`` of a DOCX held as bytes."""
    import docx

    document_ = docx.Document(io.BytesIO(blob))
    parts = [p.text for p in document_.paragraphs]
    cells = []
    tables = []
    for table in document_.tables:
        rows = []
        for row in table.rows:
            texts = [c.text for c in row.cells]
            rows.append(texts)
            cells.extend(texts)
            parts.append(" | ".join(texts))
        tables.append(rows)
    return "\n".join(parts), cells, tables


def strip_keys(value, keys=("elapsedMs",)):
    if isinstance(value, dict):
        return {k: strip_keys(v, keys) for k, v in value.items() if k not in keys}
    if isinstance(value, list):
        return [strip_keys(v, keys) for v in value]
    return value


# --------------------------------------------------------------------------
# the lint texts of DESIGN 4.2 (templates; {group} {member} {n} {count} {k} {sum} {testing} {q})
# --------------------------------------------------------------------------

_FIX_ENTER = ("Enter α1 to α{n} as numbers from 0 to 1 that add up to 1.",
              "α1 から α{n} までを、合計が 1 になる 0 から 1 までの数値で入力してください。")
_FIX_SCHEME = ("Choose staggered or non-staggered testing in the CCF groups tab.",
               "CCF グループタブで時間差試験か同時試験を選んでください。")

LINT_TEXTS = {
    ("CCF_ALPHA_SIZE", ""): {
        "reason": ("alpha-factor model needs 2 to 4 members",
                   "アルファファクターモデルにはメンバーが 2 件から 4 件必要"),
        # number-neutral English ("number of members: 1", never "has 1 members")
        "message": (
            'CCF group "{group}": number of members: {n}. The alpha-factor model handles groups '
            'of 2 to 4 members, so the group is not applied.',
            'CCF グループ「{group}」のメンバーは {n} 件です。アルファファクターモデルが扱えるのは '
            '2 件から 4 件のグループなので、グループは適用されません。'),
        "fix": ("Use 2 to 4 members, or switch the group to the beta-factor model.",
                "メンバーを 2 件から 4 件にするか、グループをベータファクターモデルに切り替えてください。"),
    },
    ("CCF_ALPHA_SUM", "length"): {
        "reason": ("α values: {count}, members: {n}", "メンバー {n} 件に対し α の値が {count} 個"),
        "message": (
            'CCF group "{group}" (members: {member}): the number of α values ({count}) differs '
            'from the number of members ({n}); α1 to α{n} are needed, so the group is not applied.',
            'CCF グループ「{group}」（メンバー: {member}）: メンバーは {n} 件ですが、α の値は {count} 個です'
            '（α1 から α{n} までが必要です）。グループは適用されません。'),
        "fix": _FIX_ENTER,
    },
    ("CCF_ALPHA_SUM", "range"): {
        "reason": ("α{k} is not a number from 0 to 1", "α{k} が 0 から 1 までの数値ではありません"),
        "message": (
            'CCF group "{group}" (members: {member}): α{k} is not a number from 0 to 1, so the '
            'group is not applied.',
            'CCF グループ「{group}」（メンバー: {member}）: α{k} が 0 から 1 までの数値ではないため、'
            'グループは適用されません。'),
        "fix": _FIX_ENTER,
    },
    ("CCF_ALPHA_SUM", "sum"): {
        "reason": ("α values add up to {sum}, not 1", "α の合計が 1 ではなく {sum} です"),
        "message": (
            'CCF group "{group}" (members: {member}): the α values add up to {sum}. They must add '
            'up to 1 (a difference up to 0.001 is corrected), so the group is not applied.',
            'CCF グループ「{group}」（メンバー: {member}）: α の合計は {sum} です。合計は 1 でなければなりません'
            '（0.001 までの差は補正されます）。グループは適用されません。'),
        "fix": _FIX_ENTER,
    },
    ("CCF_ALPHA_NORMALISED", ""): {
        "reason": ("α values add up to {sum}; divided by the sum",
                   "α の合計が {sum} のため、合計で割って補正しました"),
        "message": (
            'CCF group "{group}": the α values add up to {sum}, not 1. Each α is divided by the '
            'sum before use (a difference up to 0.001 is accepted).',
            'CCF グループ「{group}」: α の合計は 1 ではなく {sum} です。使用前に各 α を合計で割っています'
            '（0.001 までの差は許容されます）。'),
        "fix": ("Check the α values against their source; published sets are rounded.",
                "α の値を出典と照らして確認してください。公表されている値は丸められています。"),
    },
    ("CCF_NO_TESTING", "missing"): {
        "reason": ("testing scheme missing", "試験方式が未指定"),
        "message": (
            'CCF group "{group}" (members: {member}): no testing scheme is chosen. The '
            'alpha-factor model needs staggered or non-staggered testing, so the group is not '
            'applied.',
            'CCF グループ「{group}」（メンバー: {member}）: 試験方式が指定されていません。アルファファクターモデルには'
            '時間差試験か同時試験の指定が必要なため、グループは適用されません。'),
        "fix": _FIX_SCHEME,
    },
    ("CCF_NO_TESTING", "unknown"): {
        "reason": ('testing scheme "{testing}" is not recognised', '試験方式「{testing}」は認識できません'),
        "message": (
            'CCF group "{group}" (members: {member}): the testing scheme "{testing}" is not '
            'recognised (allowed in the file: staggered, nonStaggered), so the group is not '
            'applied.',
            'CCF グループ「{group}」（メンバー: {member}）: 試験方式「{testing}」は認識できません'
            '（ファイルでは staggered または nonStaggered を指定します）。グループは適用されません。'),
        "fix": _FIX_SCHEME,
    },
}

#: CCF_HIGH_Q for an alpha group (DESIGN 4.2, "Related adjustments"): reason and fix as beta.
HIGH_Q_ALPHA_MESSAGE = (
    'CCF group "{group}": the probability of "{member}" is {q}, above 0.01. The alpha-factor model '
    'assumes small probabilities; check the result.',
    'CCF グループ「{group}」: 「{member}」の確率は {q} で、0.01 を超えています。アルファファクターモデルは小さな確率を'
    '前提としています。結果を確認してください。')

#: Status words (F2 + DESIGN 4.2): the group without a scheme reads exactly this.
NO_SCHEME_STATUS_EN = "Not applied: testing scheme missing"
NO_SCHEME_STATUS_JA = "未適用: 試験方式が未指定"


def text_of(code, kind, lang, field, **params):
    """The expected ``reason`` / ``message`` / ``fix`` text of DESIGN 4.2 with placeholders filled."""
    pair = LINT_TEXTS[(code, kind)][field]
    template = pair[1] if lang == "ja" else pair[0]
    for key, value in params.items():
        template = template.replace("{%s}" % key, str(value))
    return template


# --------------------------------------------------------------------------
# DESIGN 5: report / CLI texts
# --------------------------------------------------------------------------

REPORT_TEXT = {
    "report.alpha.sum": ("sum {sum}, each α divided by the sum", "合計 {sum}、各 α を合計で割って使用"),
    "report.testing.staggered": ("Staggered testing", "時間差試験"),
    "report.testing.nonStaggered": ("Non-staggered testing", "同時試験"),
    "report.testing.none": ("not chosen", "未選択"),
    "report.alpha.overlap": (
        'Group "{group}" (alpha, {n} members): any cut sets with two CCF events of this group that '
        'share a member are kept; NUREG/CR-5485 disallows them (see the note above).',
        'グループ「{group}」（α、メンバー {n} 件）: このグループの、メンバーを共有する 2 つの CCF 事象を含むカットセットが'
        'あれば残します。NUREG/CR-5485 はこれらを除外しています（上の注記を参照）。'),
    "label.subset": ("CCF: {name} ({members})", "CCF: {name}（{members}）"),
    "assume.alpha": (
        "Alpha-factor model: Q_k is the probability of each CCF event that fails exactly k of the "
        "group's members; staggered Q_k = α_k / C(m-1, k-1) · Q_t (NUREG/CR-5485 Eq. 5.6 p. 40); "
        "non-staggered Q_k = k / C(m-1, k-1) · (α_k / α_t) · Q_t with α_t = Σ k·α_k (Eq. 5.7-5.9 "
        "p. 41; NUREG/CR-4780 Vol. 2 Eq. C.23-C.24 pp. C-10/C-11).",
        "アルファファクターモデル: Q_k は、与えられたメンバーのうちちょうど k 個を故障させる各 CCF 事象の確率です。"
        "時間差試験では Q_k = α_k / C(m-1, k-1) · Q_t（NUREG/CR-5485 式 5.6 p. 40）、同時試験では "
        "α_t = Σ k·α_k として Q_k = k / C(m-1, k-1) · (α_k / α_t) · Q_t（式 5.7-5.9 p. 41、NUREG/CR-4780 "
        "Vol. 2 式 C.23-C.24 pp. C-10/C-11）です。"),
}
#: ``report.alpha.parameters`` is ``α = ({values})`` in both languages.
PARAMETERS_TEXT = "α = ({values})"

#: The F2 overlap paragraph (pinned by an F2 test) must stay in the report.
OVERLAP_EN_F2 = (
    "Overlapping CCF events: with alpha-factor groups of 3 or 4 members, this editor treats "
    "the CCF events of a group as independent basic events, so cut sets with two CCF events "
    "that share a member (for example {C_AB, C_AC}) are kept. NUREG/CR-5485 treats such events "
    "as mutually exclusive and disallows those cut sets (pp. 47-48; Table E-2 p. E-4). The "
    "kept cut sets raise the rare-event sum and the min-cut upper bound by a second-order "
    "amount. For all three members of a group of 3 failing, the amount is 3·Q_2²; at "
    "Q_t = 1e-3 that is 7.8e-5 relative for α = (0.955, 0.034, 0.011) with staggered testing "
    "and 9.9e-5 non-staggered, and 6.0e-4 and 7.2e-4 for α = (0.9, 0.09, 0.01). The relative "
    "amount can be larger when α_m is very small compared with α_2. A beta-factor group has "
    "one CCF event, so this does not arise for it."
)


# --------------------------------------------------------------------------
# FN-64: whole-word search (one copy for the text, catalog and report tests)
# --------------------------------------------------------------------------

FN64_EN = re.compile(r"\b(comply|complies|compliant|compliance|conform|conforms|conformity|"
                     r"certified|certification)\b", re.IGNORECASE)
FN64_JA = ("準拠", "適合", "認証")


def fn64_hits(strings_en, strings_ja):
    """``[(word, text)]`` for every English string with a FN-64 word and every Japanese string
    with one of its words. Empty means clean."""
    hits = []
    for text in strings_en:
        found = FN64_EN.search(text)
        if found:
            hits.append((found.group(0), text))
    for text in strings_ja:
        hits.extend((word, text) for word in FN64_JA if word in text)
    return hits


def report_text(key, lang, **params):
    pair = REPORT_TEXT[key]
    template = pair[1] if lang == "ja" else pair[0]
    for name, value in params.items():
        template = template.replace("{%s}" % name, str(value))
    return template


# --------------------------------------------------------------------------
# DESIGN 6: the JS catalog of the tab (en, ja)
# --------------------------------------------------------------------------

CATALOG_EXACT = {
    # the text of the alpha option of the model select; the table Model cell and the report use
    # ccf.model.alphaCell. Japanese term rule of DESIGN 6 (text reviewer, O9):
    # "アルファファクター" everywhere, parallel to F2's "ベータファクター".
    "ccf.model.alpha": ("Alpha factor", "アルファファクター"),
    "ccf.model.alphaCell": ("Alpha factor", "アルファファクター"),
    "ccf.field.alphaGroup": ("α values", "α の値"),
    "ccf.field.alpha": ("α{k} (dimensionless, 0 to 1)", "α{k}（無次元、0 から 1）"),
    "ccf.alphaHint": ("e.g. 0.05 or 5%", "例: 0.05 または 5%"),
    "ccf.err.alpha": (
        "α{k} must be a number from 0 to 1 (for example 0.05 or 5%).",
        "α{k} は 0 から 1 までの数値で入力してください（例: 0.05 または 5%）。"),
    "ccf.alpha.help": (
        "α_k is the fraction of failure events in which exactly k members fail. Enter α1 to "
        "α{n}; they should add up to 1 (NUREG/CR-5485 p. 40).",
        "α_k は、ちょうど k 個のメンバーが故障する事象の割合です。α1 から α{n} までを入力します。"
        "合計は 1 になるはずです（NUREG/CR-5485 p. 40）。"),
    "ccf.alpha.sumNone": ("Sum of α: —", "α の合計: —"),
    "ccf.alpha.sumOk": ("Sum of α: {sum}", "α の合計: {sum}"),
    "ccf.alpha.sumNormalised": ("Sum of α: {sum}. Each α is divided by the sum.",
                                "α の合計: {sum}。各 α を合計で割って使用します。"),
    "ccf.alpha.sumBad": ("Sum of α: {sum}. It must be 1 (a difference up to 0.001 is corrected).",
                         "α の合計: {sum}。1 でなければなりません（0.001 までの差は補正されます）。"),
    "ccf.alpha.used": ("Values used: {list}", "使用する値: {list}"),
    "ccf.alpha.size": (
        "The alpha-factor model needs 2 to 4 members; this group has {n}.",
        "アルファファクターモデルにはメンバーが 2 件から 4 件必要です。このグループは {n} 件です。"),
    "ccf.alpha.resize": (
        "Members: {n}, α values stored: {count}. Check the fields and save the α values.",
        "メンバーは {n} 件ですが、保存されている α の値は {count} 個です。入力欄を確認して α の値を保存してください。"),
    "ccf.alpha.save": ("Save α values", "α の値を保存"),
    "ccf.field.testing": ("Testing scheme", "試験方式"),
    "ccf.testing.placeholder": ("Choose a testing scheme", "試験方式を選んでください"),
    "ccf.testing.staggered": ("Staggered testing", "時間差試験"),
    "ccf.testing.nonStaggered": ("Non-staggered testing", "同時試験"),
    "ccf.testing.help": (
        # RC4: the scheme describes how the components behind the alpha values were tested
        # (S1 p. 40: "the way systems in the database are tested"; S3 pp. 7-9, 7-14), not the user's plant.
        "Staggered: the components behind the α values were tested one after another at "
        "different times. Non-staggered: they were all tested at the same time. Choose the "
        "scheme that matches the source of your α values (NUREG/CR-5485 p. 40; "
        "NASA/SP-2011-3421 pp. 7-9, 7-14).",
        "時間差試験: α の値の元になったデータで、部品を時間をずらして順に試験した場合。"
        "同時試験: すべての部品を同時に試験した場合。α の値の出典に合う方式を選んでください"
        "（NUREG/CR-5485 p. 40、NASA/SP-2011-3421 pp. 7-9, 7-14）。"),
    "ccf.err.testing": ("The testing scheme could not be saved: {error}",
                        "試験方式を保存できませんでした: {error}"),
    "ccf.assume.alpha": REPORT_TEXT["assume.alpha"],
    "ccf.label.subset": REPORT_TEXT["label.subset"],
}
