"""Test models, expected texts and small readers of the F2 acceptance tests.

Everything here is built from SPEC 7.1, 7.4 and DESIGN section 14 and 13, not
from product code. The module imports no product module at the top (the
helpers that need one import it inside the function), so a missing F2 module
fails the test that needs it and nothing else.

Names carry plain ASCII on purpose: a group name or a member name must be
findable in the English and in the Japanese text of a message.
"""
import copy
import io
import json
from pathlib import Path

# --------------------------------------------------------------------------
# texts the tests expect (DESIGN section 13 and SPEC 4.2 / 4.7)
# --------------------------------------------------------------------------

NOTE_EN = "Check CCF results with a qualified engineer before use."
NOTE_JA = "CCF の結果は、使用前に有資格の技術者が確認してください。"

#: The six UI-7 sentences, en and ja (DESIGN 13.1, keys ccf.assume.*).
ASSUMPTIONS_EN = {
    "model": "Beta-factor model: Q_1 = (1 − β)·Q_t is the independent part of each member "
             "and Q_m = β·Q_t is one event failing all m members (NUREG/CR-4780 Vol. 2, "
             "Table C-1 p. C-5 and Eq. C.10-C.13 p. C-6; NUREG/CR-5485, Eq. 5.11-5.13 p. 42).",
    "qt": "A member's probability is its total failure probability Q_t at mission time.",
    "beta": "Beta factor: the CCF event fails all members together.",
    "split": "The split is applied to Q_t; splitting λ instead agrees only to first order "
             "in λT (NASA/SP-2011-3421, p. D-20).",
    "headline": "The headline is the min-cut upper bound; the formulas in the sources use "
                "the rare-event approximation.",
    "sampling": "β and α are not sampled in Monte Carlo.",
}
ASSUMPTIONS_JA = {
    "model": "ベータファクターモデル: Q_1 = (1 − β)·Q_t が各メンバーの独立部分、Q_m = β·Q_t が全 m "
             "メンバーを同時に故障させる 1 つの事象です（NUREG/CR-4780 Vol. 2 表 C-1 p. C-5、"
             "式 C.10-C.13 p. C-6、NUREG/CR-5485 式 5.11-5.13 p. 42）。",
    "qt": "メンバーの確率は、ミッション時間における全故障確率 Q_t です。",
    "beta": "ベータファクター: CCF 事象は全メンバーを同時に故障させます。",
    "split": "分割は Q_t に適用します。λ を分割した場合は、λT の一次の範囲でのみ一致します"
             "（NASA/SP-2011-3421 p. D-20）。",
    "headline": "頂上事象の値は最小カット上限（MCUB）です。出典の式はレアイベント近似を用いています。",
    "sampling": "モンテカルロでは β と α はサンプリングしません。",
}

OVERLAP_EN = (
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
OVERLAP_JA = (
    "重なり合う CCF 事象: メンバーが 3 または 4 件のアルファファクターのグループでは、このエディターは同じグループの "
    "CCF 事象を互いに独立な基本事象として扱うため、メンバーを共有する 2 つの CCF 事象を含むカットセット"
    "（例: {C_AB, C_AC}）を残します。NUREG/CR-5485 はこのような事象を互いに排反として扱い、そのカットセットを"
    "除外しています（pp. 47-48、表 E-2 p. E-4）。残したカットセットは、レアイベント近似の合計と最小カット上限を"
    "二次のオーダーの量だけ大きくします。3 件のグループで 3 件すべてが故障する場合、その量は 3·Q_2² で、"
    "Q_t = 1e-3 のとき相対値は α = (0.955, 0.034, 0.011) で時間差試験 7.8e-5、同時試験 9.9e-5、"
    "α = (0.9, 0.09, 0.01) でそれぞれ 6.0e-4、7.2e-4 です。α_2 に比べて α_m が非常に小さいと、相対値はさらに"
    "大きくなることがあります。ベータファクターのグループには CCF 事象が 1 つしかないため、該当しません。"
)

#: SPEC FN-69 (the CHANGELOG sentences, en and ja).
FN69_EN = ("Files with CCF groups lose the groups when saved by FTA Editor 1.8.x (it warns "
           "'reset to their defaults: ccfGroups'), and lose all analysis settings when saved "
           "by the desktop app.")
FN69_JA = ("CCF グループを含むファイルを FTA Editor 1.8.x で保存すると CCF グループが失われます"
           "（1.8.x は 'reset to their defaults: ccfGroups' と警告します）。"
           "デスクトップ版で保存すると解析設定がすべて失われます。")

NEWER_FORMAT_WARNING = "This file was saved by a newer FTA Editor; saving may lose data"

# --------------------------------------------------------------------------
# tree builders
# --------------------------------------------------------------------------

GROUP_NAME = "Feed pumps"
BETA = 0.1


def rel(expected, tol):
    """A purely relative comparison: ``pytest.approx(expected, rel=tol, abs=0.0)``.

    With only ``rel=`` pytest keeps an absolute floor of 1e-12, as large as the probabilities
    under test, so the stated relative tolerance would be looser than it says. Every relative
    approx in this folder goes through here (or sets ``abs=`` itself)."""
    import pytest

    return pytest.approx(expected, rel=tol, abs=0.0)


def leaf(node_id, q=1e-3, name=None, quant=None, **extra):
    node = {"id": node_id, "name": name or node_id, "type": "Event", "logicGate": "OR",
            "probability": q, "notes": "", "links": [], "children": [],
            "quant": copy.deepcopy(quant) if quant is not None else {"model": "fixed"}}
    node.update(extra)
    return node


def gate(node_id, kind, children, name=None, type_="Event", **extra):
    """``kind`` is AND, OR or a gateType (KOFN, XOR, PAND, INHIBIT, TRANSFER)."""
    node = {"id": node_id, "name": name or node_id, "type": type_, "probability": 1.0,
            "notes": "", "links": [], "children": children}
    if kind in ("AND", "OR"):
        node["logicGate"] = kind
    else:
        node["gateType"] = kind
        node["logicGate"] = "OR" if kind in ("KOFN", "XOR") else "AND"
    node.update(extra)
    return node


def pump(node_id, q=1e-3, **extra):
    return leaf(node_id, q, name="Pump %s" % node_id, **extra)


def top(children, **extra):
    return gate("root", "OR", children, name="Top event", type_="Root", **extra)


def group(gid="g1", name=GROUP_NAME, members=("A", "B"), beta=BETA, source="test", **over):
    """A stored beta group: exactly the eight keys of SPEC 7.1."""
    out = {"id": gid, "name": name, "model": "beta", "beta": beta, "alpha": None,
           "testing": None, "members": None if members is None else list(members),
           "source": source}
    out.update(over)
    return out


def r1_tree(tag=""):
    """R1: root OR [ G1 AND [A, B], C ], A and B 1e-3, C 0 (the top is G1).

    ``tag`` renames the top event, so that a test that changes how the
    headline is computed uses a document no earlier test used (the diagram
    remembers the last headline of an identical document).
    """
    tree = top([gate("G1", "AND", [pump("A"), pump("B")], name="Pumps fail"),
                leaf("C", 0.0, name="Sensor C")])
    if tag:
        tree["name"] = "Top event %s" % tag
    return tree


def r2_tree():
    """R2: root OR [ A, B ]."""
    return top([pump("A"), pump("B")])


def r11_tree():
    """R11: root AND [ A, B ] with a lognormal uncertainty on both members."""
    quant = {"model": "fixed", "unc": {"dist": "lognormal", "median": 1e-3, "ef": 3}}
    return gate("root", "AND", [pump("A", 1e-3, quant=quant), pump("B", 1e-3, quant=quant)],
                name="Top event", type_="Root")


def document(tree, groups=None, mode="FTA", title="CCF test", version=None, analysis=None):
    """A file as FTA Editor writes it. ``groups`` None writes no ``ccfGroups`` key."""
    doc = {"title": title, "date": "2026-10-26", "mode": mode}
    if version is not None:
        doc["fileFormatVersion"] = version
    elif groups:
        doc["fileFormatVersion"] = 2
    doc["tree"] = copy.deepcopy(tree)
    merged = dict(analysis or {})
    if groups is not None:
        merged["ccfGroups"] = copy.deepcopy(groups)
    if merged:
        doc["analysis"] = merged
    return doc


def r1_document(groups=None, tag="", **kw):
    return document(r1_tree(tag), [group()] if groups is None else groups, **kw)


def write_doc(directory, doc, name="doc.json"):
    path = Path(directory) / name
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def tree_without_groups(doc):
    out = copy.deepcopy(doc)
    out.pop("fileFormatVersion", None)
    if isinstance(out.get("analysis"), dict):
        out["analysis"].pop("ccfGroups", None)
        if not out["analysis"]:
            out.pop("analysis")
    return out


# --------------------------------------------------------------------------
# readers
# --------------------------------------------------------------------------


def fmt(value, sig_figs=3):
    """The diagram's number format (existing ``numfmt.format_prob``)."""
    from fta_web import numfmt

    return numfmt.format_prob(value, sig_figs)


def docx_text(blob):
    """``(full_text, table_cell_texts)`` of a DOCX held as bytes."""
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


def xlsx_cells(blob):
    """``[(sheet, row, column, value)]`` for every non-empty cell."""
    import openpyxl

    book = openpyxl.load_workbook(io.BytesIO(blob))
    out = []
    for sheet in book.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if cell.value is not None:
                    out.append((sheet.title, cell.row, cell.column, cell.value))
    return out


def strip_keys(value, keys=("elapsedMs",)):
    """``value`` without ``keys`` at any depth."""
    if isinstance(value, dict):
        return {k: strip_keys(v, keys) for k, v in value.items() if k not in keys}
    if isinstance(value, list):
        return [strip_keys(v, keys) for v in value]
    return value


def cut_set_ids(result):
    return [sorted(e["id"] for e in cs["events"]) for cs in result["cutSets"]]


def find_cut_set(result, ids):
    wanted = sorted(ids)
    for cs in result["cutSets"]:
        if sorted(e["id"] for e in cs["events"]) == wanted:
            return cs
    raise AssertionError("no cut set with events %s in %s" % (wanted, cut_set_ids(result)))


# --------------------------------------------------------------------------
# the lint cases (SPEC FN-33: one document per code and kind)
# --------------------------------------------------------------------------


def _rate(lam, **extra):
    quant = {"model": "rate", "lambda": lam}
    quant.update(extra)
    return quant


def _case(case_id, doc, code, severity, applied, reasons, names, gi=(0,), msg_en=(), warning=False):
    # ``reasons``: one (en, ja) pair, or a list of pairs when the member named in the
    # reason may be any of several members with equal Q_t.
    pairs = [reasons] if isinstance(reasons[0], str) else list(reasons)
    return {"id": case_id, "doc": doc, "code": code, "severity": severity, "applied": applied,
            "reasons": pairs, "names": list(names), "gi": tuple(gi), "msg_en": list(msg_en),
            "warning": warning}


def lint_cases():
    """The twelve FN-33 codes (every kind), each with the document that raises it.

    ``reasons`` is the (en, ja) reason of DESIGN section 9; ``names`` are the
    strings the English and the Japanese message must both contain (an item
    that is a tuple means any one of them). ``gi`` are the indexes of the
    groups the finding is reported for.
    """
    cases = []
    gp = GROUP_NAME

    # CCF_ETA_MODE (status)
    cases.append(_case(
        "ETA_MODE", r1_document(mode="ETA"), "CCF_ETA_MODE", "status", False,
        ("ETA mode", "ETA モード"), [gp, "Pump A", "Pump B"]))

    # CCF_TOO_FEW_MEMBERS
    few = ("fewer than 2 members", "メンバーが 2 件未満")
    cases.append(_case(
        "TOO_FEW_one", document(r2_tree(), [group(members=["A", "A"])]),
        "CCF_TOO_FEW_MEMBERS", "error", False, few, [gp, "Pump A"],
        msg_en=["only one distinct member"]))
    cases.append(_case(
        "TOO_FEW_none", document(r2_tree(), [group(members=[])]),
        "CCF_TOO_FEW_MEMBERS", "error", False, few, [gp], msg_en=["no members"]))
    cases.append(_case(
        "TOO_FEW_not_a_list", document(r2_tree(), [group(members=None)]),
        "CCF_TOO_FEW_MEMBERS", "error", False, few, [gp], msg_en=["no members"]))

    # CCF_MEMBER_NOT_BASIC: gate, house, conditioning, transfer, missing
    def basic_reason(name):
        return ('"%s" is not a basic event' % name, "「%s」は基本事象ではありません" % name)

    gate_tree = top([gate("G1", "AND", [pump("A"), gate(
        "GG", "AND", [leaf("C"), leaf("D")], name="Valve train")], name="Pumps fail")])
    cases.append(_case(
        "NOT_BASIC_gate", document(gate_tree, [group(members=["A", "GG"])]),
        "CCF_MEMBER_NOT_BASIC", "error", False, basic_reason("Valve train"),
        [gp, "Valve train"], msg_en=["has child events"]))
    house_tree = top([gate("G1", "AND", [pump("A"), leaf(
        "H", 1.0, name="Mode switch", eventKind="house", houseState=True)], name="Pumps fail")])
    cases.append(_case(
        "NOT_BASIC_house", document(house_tree, [group(members=["A", "H"])]),
        "CCF_MEMBER_NOT_BASIC", "error", False, basic_reason("Mode switch"),
        [gp, "Mode switch"], msg_en=["house event"]))
    cond_tree = top([gate("INH", "INHIBIT", [pump("A"), leaf(
        "COND", 0.5, name="Enabling condition", eventKind="conditioning")], name="Inhibit gate"),
        pump("B")])
    cases.append(_case(
        "NOT_BASIC_conditioning", document(cond_tree, [group(members=["A", "COND"])]),
        "CCF_MEMBER_NOT_BASIC", "error", False, basic_reason("Enabling condition"),
        [gp, "Enabling condition"], msg_en=["conditioning event"]))
    xfer_tree = top([
        gate("SUB", "AND", [leaf("C"), leaf("D")], name="Sub tree"),
        leaf("XF", 1.0, name="Transfer to sub", gateType="TRANSFER", transferTo="SUB"),
        pump("A")])
    cases.append(_case(
        "NOT_BASIC_transfer", document(xfer_tree, [group(members=["A", "XF"])]),
        "CCF_MEMBER_NOT_BASIC", "error", False, basic_reason("Transfer to sub"),
        [gp, "Transfer to sub"], msg_en=["transfer gate"]))
    cases.append(_case(
        "NOT_BASIC_missing", document(r2_tree(), [group(members=["A", "ghost"])]),
        "CCF_MEMBER_NOT_BASIC", "error", False,
        ('"ghost" is not in the tree', "「ghost」がツリーにありません"), [gp, "ghost"],
        msg_en=["is not in the tree"]))

    # CCF_MEMBER_IN_TWO_GROUPS (both groups)
    two_tree = top([gate("G1", "AND", [pump("A"), pump("B"), pump("C")], name="Pumps fail")])
    cases.append(_case(
        "IN_TWO_GROUPS",
        document(two_tree, [group(members=["A", "B"]),
                            group("g2", "Valve group", members=["B", "C"])]),
        "CCF_MEMBER_IN_TWO_GROUPS", "error", False,
        ('"Pump B" is in two groups', "「Pump B」が 2 つのグループに属しています"),
        [gp, "Pump B"], gi=(0, 1), msg_en=["Valve group"]))

    # CCF_MEMBERS_DIFFER: model, parameter, qt, uncertainty
    def differ(member, reference):
        return ('"%s" differs from "%s"' % (member, reference),
                "「%s」が「%s」と異なります" % (member, reference))

    cases.append(_case(
        "DIFFER_model",
        document(r2_tree_with(pump("A", 1e-3), pump("B", 1e-3, quant=_rate(1e-7))),
                 [group()]),
        "CCF_MEMBERS_DIFFER", "error", False, differ("Pump B", "Pump A"),
        [gp, "Pump A", "Pump B"], msg_en=["different quantification model"]))
    cases.append(_case(
        "DIFFER_parameter",
        document(r2_tree_with(pump("A", quant=_rate(1e-6)), pump("B", quant=_rate(2e-6))),
                 [group()]),
        "CCF_MEMBERS_DIFFER", "error", False, differ("Pump B", "Pump A"),
        [gp, "Pump A", "Pump B"], msg_en=["different model parameters"]))
    # Every parameter within the relative 1e-6 of FN-33, yet Q_t = lambda / (lambda + mu)
    # differs by 1.64e-6 relative: the Q_t kind.
    eps = 0.9e-6
    cases.append(_case(
        "DIFFER_qt",
        document(r2_tree_with(
            pump("A", quant={"model": "repairable", "lambda": 1e-3, "mu": 1e-2}),
            pump("B", quant={"model": "repairable", "lambda": 1e-3 * (1 + eps),
                             "mu": 1e-2 * (1 - eps)})), [group()]),
        "CCF_MEMBERS_DIFFER", "error", False, differ("Pump B", "Pump A"),
        [gp, "Pump A", "Pump B"], msg_en=["different probability Q_t"]))
    unc3 = {"dist": "lognormal", "median": 1e-3, "ef": 3}
    # FN-33 / DESIGN 9: the compared parameter is equal when math.isclose(a, b, rel_tol=1e-6).
    # 1.5e-6 apart is over the edge (|a - b| = 1.5e-9 > 1e-6 * 1e-3 = 1e-9), 0.5e-6 is inside
    # (no_lint_cases). For the fixed model the compared parameter is q itself; for the rate
    # model it is lambda (the mission time is the same for both members).
    over = 1.5e-6
    cases.append(_case(
        "DIFFER_parameter_fixed_q_1p5e6",
        document(r2_tree_with(pump("A", 1e-3), pump("B", 1e-3 * (1 + over))), [group()]),
        "CCF_MEMBERS_DIFFER", "error", False, differ("Pump B", "Pump A"),
        [gp, "Pump A", "Pump B"], msg_en=["different model parameters"]))
    cases.append(_case(
        "DIFFER_parameter_rate_lambda_1p5e6",
        document(r2_tree_with(pump("A", quant=_rate(1e-7)),
                              pump("B", quant=_rate(1e-7 * (1 + over)))), [group()]),
        "CCF_MEMBERS_DIFFER", "error", False, differ("Pump B", "Pump A"),
        [gp, "Pump A", "Pump B"], msg_en=["different model parameters"]))
    cases.append(_case(
        "DIFFER_uncertainty_absent",
        document(r2_tree_with(pump("A", quant={"model": "fixed", "unc": unc3}), pump("B")),
                 [group()]),
        "CCF_MEMBERS_DIFFER", "error", False, differ("Pump B", "Pump A"),
        [gp, "Pump A", "Pump B"], msg_en=["different uncertainty"]))
    cases.append(_case(
        "DIFFER_uncertainty_ef",
        document(r2_tree_with(
            pump("A", quant={"model": "fixed", "unc": unc3}),
            pump("B", quant={"model": "fixed", "unc": dict(unc3, ef=5)})), [group()]),
        "CCF_MEMBERS_DIFFER", "error", False, differ("Pump B", "Pump A"),
        [gp, "Pump A", "Pump B"], msg_en=["different uncertainty"]))

    # CCF_NO_PROBABILITY
    cases.append(_case(
        "NO_PROBABILITY",
        document(r2_tree_with(pump("A", quant=_rate(1e-6)), pump("B", quant={"model": "rate"})),
                 [group()]),
        "CCF_NO_PROBABILITY", "error", False,
        ('"Pump B" has no probability', "「Pump B」に確率がありません"),
        [gp, "Pump B"], msg_en=["has no probability"]))

    # CCF_Q_ONE
    cases.append(_case(
        "Q_ONE", document(r2_tree_with(pump("A", 1.0), pump("B", 1.0)), [group()]),
        "CCF_Q_ONE", "error", False,
        [('probability of "Pump A" is 1', "「Pump A」の確率が 1 です"),
         ('probability of "Pump B" is 1', "「Pump B」の確率が 1 です")],
        [gp, ("Pump A", "Pump B")], msg_en=["certain failure"]))

    # CCF_BAD_PARAMETER: beta (several bad values), model, id
    beta_reason = ("β is not a number from 0 to 1", "β が 0 から 1 までの数値ではありません")
    for label, bad in (("string", "abc"), ("above_one", 1.5), ("negative", -0.1),
                       ("null", None), ("bool", True), ("nan", float("nan"))):
        cases.append(_case(
            "BAD_PARAMETER_beta_%s" % label,
            document(r2_tree(), [group(beta=bad)]),
            "CCF_BAD_PARAMETER", "error", False, beta_reason, [gp, "Pump A", "Pump B"]))
    missing_beta = group()
    del missing_beta["beta"]
    cases.append(_case(
        "BAD_PARAMETER_beta_missing", document(r2_tree(), [missing_beta]),
        "CCF_BAD_PARAMETER", "error", False, beta_reason, [gp, "Pump A", "Pump B"]))
    cases.append(_case(
        "BAD_PARAMETER_model",
        document(r2_tree(), [group(model="gamma")]),
        "CCF_BAD_PARAMETER", "error", False,
        ('model "gamma" is not available', "モデル「gamma」は利用できません"),
        [gp, "Pump A", "Pump B", "gamma"]))
    no_id = group()
    del no_id["id"]
    cases.append(_case(
        "BAD_PARAMETER_id_missing", document(r2_tree(), [no_id]),
        "CCF_BAD_PARAMETER", "error", False,
        ("group id missing or repeated", "グループ ID がないか重複しています"),
        [gp, "Pump A", "Pump B"]))

    # CCF_MEMBER_RENAMED: the loader gave a repeated id a new one
    dup_tree = top([
        gate("G1", "AND", [pump("A"), pump("B")], name="Pumps fail"),
        gate("G2", "AND", [leaf("A", 1e-3, name="Pump A twin"), leaf("D")], name="Other")])
    cases.append(_case(
        "RENAMED", document(dup_tree, [group()]),
        "CCF_MEMBER_RENAMED", "error", False,
        ('"Pump A" was renamed when the file was opened',
         "「Pump A」はファイルを開いたときに ID が付け替えられました"),
        [gp, "Pump A"], msg_en=["duplicate id repair"]))

    # warnings: the group stays applied
    cases.append(_case(
        "HIGH_Q", document(r2_tree_with(pump("A", 0.02), pump("B", 0.02)), [group()]),
        "CCF_HIGH_Q", "warning", True,
        [('probability of "Pump A" is above 0.01', "「Pump A」の確率が 0.01 を超えています"),
         ('probability of "Pump B" is above 0.01', "「Pump B」の確率が 0.01 を超えています")],
        [gp, ("Pump A", "Pump B")], msg_en=["0.02", "above 0.01"], warning=True))
    # FN-33: HIGH_Q is Q_t > 0.01 (strictly): 0.0101 raises it, exactly 0.01 does not
    # (no_lint_cases "qt_at_0p01").
    cases.append(_case(
        "HIGH_Q_just_above", document(r2_tree_with(pump("A", 0.0101), pump("B", 0.0101)), [group()]),
        "CCF_HIGH_Q", "warning", True,
        [('probability of "Pump A" is above 0.01', "「Pump A」の確率が 0.01 を超えています"),
         ('probability of "Pump B" is above 0.01', "「Pump B」の確率が 0.01 を超えています")],
        [gp, ("Pump A", "Pump B")], msg_en=["above 0.01"], warning=True))
    cases.append(_case(
        "ZERO_Q", document(r2_tree_with(pump("A", 0.0), pump("B", 0.0)), [group()]),
        "CCF_ZERO_Q", "warning", True,
        ("probability is 0", "確率が 0 です"), [gp, ("Pump A", "Pump B")],
        msg_en=["has no effect"], warning=True))
    for kind in ("PAND", "XOR"):
        # Only Pump A sits below the ordered gate (one finding); Pump B is elsewhere.
        tree = top([gate("OG", kind, [pump("A"), leaf("C")], name="Ordered gate"), pump("B")])
        cases.append(_case(
            "ORDERED_GATE_%s" % kind, document(tree, [group()]),
            "CCF_ORDERED_GATE", "warning", True,
            ('"Pump A" is below a PAND or XOR gate', "「Pump A」は PAND または XOR ゲートの下にあります"),
            [gp, "Pump A"], msg_en=["PAND or XOR"], warning=True))
    return cases


def r2_tree_with(a, b):
    """root OR [ a, b ]: two members (any shape) under the top event."""
    return top([a, b])


def no_lint_cases():
    """Documents with an applied group that must raise no CCF lint at all."""
    cases = []
    # Equal lambda: one typed per hour, one typed per year (stored per hour in both).
    lam_h = 1e-7
    lam_y = 8.76e-4  # 1e-7 /h * 8760 h
    cases.append(("lambda_h_vs_y", document(
        r2_tree_with(pump("A", quant=_rate(lam_h)), pump("B", quant=_rate(lam_y / 8760.0))),
        [group()])))
    # FN-33 thresholds: Q_t exactly 0.01 is not "above 0.01" (CCF_HIGH_Q needs Q_t > 0.01);
    # parameters 0.5e-6 apart are equal under isclose(rel_tol=1e-6) (1.5e-6 apart: lint_cases).
    cases.append(("qt_at_0p01", document(
        r2_tree_with(pump("A", 0.01), pump("B", 0.01)), [group()])))
    cases.append(("fixed_q_0p5e6_apart", document(
        r2_tree_with(pump("A", 1e-3), pump("B", 1e-3 * (1 + 0.5e-6))), [group()])))
    cases.append(("rate_lambda_0p5e6_apart", document(
        r2_tree_with(pump("A", quant=_rate(1e-7)),
                     pump("B", quant=_rate(1e-7 * (1 + 0.5e-6)))), [group()])))
    # Members under INHIBIT and under a voting gate.
    inh = top([gate("INH", "INHIBIT", [pump("A"), leaf(
        "COND", 0.5, name="Enabling condition", eventKind="conditioning")], name="Inhibit gate"),
        pump("B")])
    cases.append(("under_inhibit", document(inh, [group()])))
    kofn = top([gate("V", "KOFN", [pump("A"), pump("B"), pump("C")], name="Vote", k=2)])
    cases.append(("under_kofn", document(kofn, [group()])))
    # A member reached twice: by a link and by a transfer.
    linked = top([gate("G1", "AND", [pump("A"), pump("B")], name="Pumps fail"),
                  gate("G2", "AND", [leaf("C"), leaf("D", 1e-3, links=[
                      {"target_id": "A", "relation": "OR"}])], name="Other")])
    cases.append(("referenced_by_link", document(linked, [group()])))
    transferred = top([
        gate("SUB", "AND", [pump("A"), pump("B")], name="Sub tree"),
        gate("G2", "AND", [leaf("C"), leaf("XF", 1.0, name="Transfer to sub",
                                           gateType="TRANSFER", transferTo="SUB")],
             name="Other")])
    cases.append(("referenced_by_transfer", document(transferred, [group()])))
    return cases
