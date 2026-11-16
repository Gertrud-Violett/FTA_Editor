"""
User-facing texts of the CCF groups feature, English and Japanese (DESIGN D5).

One Python table holds what the API sends in both languages (the browser
picks one at paint time): the lint texts of FN-33 (DESIGN section 9), the
status words and the FN-67 note. The table is keyed by lint code and kind::

    LINT[code][kind] = {"reason": (en, ja), "message": (en, ja), "fix": (en, ja) | None}

Placeholders: ``{group}``, ``{member}`` (for a group-level code a comma list of
member names, at most five and then ``, ...``), ``{reference}``, ``{other}``,
``{model}``, ``{q}`` (``%.3g``) and, for the alpha-factor model (F2A): ``{n}``
(members), ``{count}`` (stored α values), ``{k}`` (position of an α, 1-based),
``{sum}`` (the sum of the α values, ``%.12g``), ``{testing}``, ``{event}``.
Every text names the group and the member, so
an engineer reading one line knows where to look.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

LANGS = ("en", "ja")

#: FN-67 (SPEC 4.2): the note shown with every CCF result.
NOTE = (
    "Check CCF results with a qualified engineer before use.",
    "CCF の結果は、使用前に有資格の技術者が確認してください。",
)

#: Status words (DESIGN section 9, "Status words").
APPLIED = ("Applied", "適用中")
NOT_APPLIED = ("Not applied: {reason}", "未適用: {reason}")

_FIX_BASIC = ("Remove this member from the group, or make it a basic event again.",
              "このメンバーをグループから外すか、基本事象に戻してください。")
_FIX_DIFFER = ("Give all members the same model, parameters, probability and uncertainty "
               "(Quantification tab).",
               "すべてのメンバーに同じモデル・パラメータ・確率・不確かさを設定してください"
               "（定量化タブ）。")
_FIX_FEW = ("Add at least two redundant basic events to the group.",
            "冗長な基本事象を 2 つ以上グループに追加してください。")
_FIX_ALPHA = ("Enter α1 to α{n} as numbers from 0 to 1 that add up to 1.",
              "α1 から α{n} までを、合計が 1 になる 0 から 1 までの数値で入力してください。")
_FIX_SCHEME = ("Choose staggered or non-staggered testing in the CCF groups tab.",
               "CCF グループタブで時間差試験か同時試験を選んでください。")
_FIX_HIGH_Q = ("Check the probability or the mission time.",
               "確率またはミッション時間を確認してください。")
_BASIC_TAIL = (" The group is not applied.", "グループは適用されません。")
_DIFFER_TAIL = (" Members must be identical components, so the group is not applied.",
                "メンバーは同一の部品である必要があるため、グループは適用されません。")


def _basic(kind_en: str, kind_ja: str) -> Dict[str, Any]:
    return {
        "reason": ('"{member}" is not a basic event', "「{member}」は基本事象ではありません"),
        "message": (
            'CCF group "{group}": "{member}" ' + kind_en + _BASIC_TAIL[0],
            "CCF グループ「{group}」: 「{member}」は" + kind_ja + _BASIC_TAIL[1],
        ),
        "fix": _FIX_BASIC,
    }


def _differ(what_en: str, what_ja: str, rel: bool = False) -> Dict[str, Any]:
    """A CCF_MEMBERS_DIFFER entry; ``rel`` adds the 1e-6 relative tolerance note."""
    return {
        "reason": ('"{member}" differs from "{reference}"', "「{member}」が「{reference}」と異なります"),
        "message": (
            'CCF group "{group}": "{member}" ' + what_en + ' "{reference}"'
            + (" (more than 1e-6 relative)" if rel else "") + "." + _DIFFER_TAIL[0],
            "CCF グループ「{group}」: 「{member}」の" + what_ja + "が「{reference}」と異なります"
            + ("（相対差 1e-6 超）" if rel else "") + "。" + _DIFFER_TAIL[1],
        ),
        "fix": _FIX_DIFFER,
    }


_RESERVED_ID = {
    "reason": ('a node id starts with "ccf:"', 'ノード ID が "ccf:" で始まっています'),
    "message": (
        'CCF group "{group}" (members: {member}): the tree has a node whose id starts with '
        '"ccf:", which is reserved for CCF events, so the group is not applied.',
        'CCF グループ「{group}」（メンバー: {member}）: ツリーに "ccf:" で始まる ID のノードが'
        'あります。この ID は CCF 事象用に予約されているため、グループは適用されません。',
    ),
    "fix": ("Rename that node.", "そのノードの ID を変更してください。"),
}

LINT: Dict[str, Dict[str, Dict[str, Any]]] = {
    "CCF_ETA_MODE": {"": {
        "reason": ("ETA mode", "ETA モード"),
        "message": (
            'CCF group "{group}" (members: {member}) is not applied because the document is in '
            "ETA mode. The group stays in the file.",
            "CCF グループ「{group}」（メンバー: {member}）は、文書が ETA モードのため"
            "適用されません。グループはファイルに残ります。",
        ),
        "fix": None,
    }},
    "CCF_TOO_FEW_MEMBERS": {
        "one": {
            "reason": ("fewer than 2 members", "メンバーが 2 件未満"),
            "message": (
                'CCF group "{group}" has only one distinct member ("{member}"), so it is not '
                "applied.",
                "CCF グループ「{group}」には重複を除いてメンバーが 1 件（「{member}」）しか"
                "ないため、適用されません。",
            ),
            "fix": _FIX_FEW,
        },
        "none": {
            "reason": ("fewer than 2 members", "メンバーが 2 件未満"),
            "message": (
                'CCF group "{group}" has no members, so it is not applied.',
                "CCF グループ「{group}」にはメンバーがないため、適用されません。",
            ),
            "fix": _FIX_FEW,
        },
    },
    "CCF_MEMBER_NOT_BASIC": {
        "gate": _basic("has child events, so it is not a basic event.",
                       "子ノードを持つため基本事象ではありません。"),
        "house": _basic("is a house event, not a basic event.",
                        "家形事象であり、基本事象ではありません。"),
        "conditioning": _basic("is a conditioning event, not a basic event.",
                               "条件事象であり、基本事象ではありません。"),
        "transfer": _basic("is a transfer gate, not a basic event.",
                           "転送ゲートであり、基本事象ではありません。"),
        "missing": {
            "reason": ('"{member}" is not in the tree', "「{member}」がツリーにありません"),
            "message": (
                'CCF group "{group}": member "{member}" is not in the tree. The group is not '
                "applied.",
                "CCF グループ「{group}」: メンバー「{member}」がツリーにありません。"
                "グループは適用されません。",
            ),
            "fix": ("Remove this member from the group.",
                    "このメンバーをグループから外してください。"),
        },
    },
    "CCF_MEMBER_IN_TWO_GROUPS": {"": {
        "reason": ('"{member}" is in two groups', "「{member}」が 2 つのグループに属しています"),
        "message": (
            'CCF group "{group}": "{member}" also belongs to group "{other}". An event can be in '
            "one group only, so neither group is applied.",
            "CCF グループ「{group}」: 「{member}」はグループ「{other}」にも属しています。"
            "1 つの事象は 1 つのグループにしか入れられないため、どちらのグループも"
            "適用されません。",
        ),
        "fix": ("Keep each event in one group only.", "1 つの事象は 1 つのグループにだけ入れてください。"),
    }},
    "CCF_MEMBERS_DIFFER": {
        "model": _differ("uses a different quantification model than", "定量化モデル"),
        "parameter": _differ("has different model parameters than", "モデルパラメータ", rel=True),
        "qt": _differ("has a different probability Q_t than", "確率 Q_t ", rel=True),
        "uncertainty": _differ("has a different uncertainty (distribution, median or mean, "
                               "error factor) than", "不確かさ（分布、中央値または平均、エラーファクター）"),
    },
    "CCF_NO_PROBABILITY": {"": {
        "reason": ('"{member}" has no probability', "「{member}」に確率がありません"),
        "message": (
            'CCF group "{group}": "{member}" has no probability (its quantification model is '
            "missing a parameter), so the group is not applied.",
            "CCF グループ「{group}」: 「{member}」には確率がありません"
            "（定量化モデルのパラメータが不足しています）。グループは適用されません。",
        ),
        "fix": ("Complete the quantification model of this member (Quantification tab).",
                "このメンバーの定量化モデルを完成させてください（定量化タブ）。"),
    }},
    "CCF_Q_ONE": {"": {
        "reason": ('probability of "{member}" is 1', "「{member}」の確率が 1 です"),
        "message": (
            'CCF group "{group}": the probability of "{member}" is 1. Splitting a certain '
            "failure would lower its value, so the group is not applied.",
            "CCF グループ「{group}」: 「{member}」の確率は 1 です。確実な故障を分割すると"
            "値が下がってしまうため、グループは適用されません。",
        ),
        "fix": ("Check the probability of this member; a certain failure (1) cannot be split.",
                "このメンバーの確率を確認してください。確実な故障（1）は分割できません。"),
    }},
    "CCF_BAD_PARAMETER": {
        "beta": {
            "reason": ("β is not a number from 0 to 1", "β が 0 から 1 までの数値ではありません"),
            "message": (
                'CCF group "{group}" (members: {member}): β is not a number from 0 to 1, so the '
                "group is not applied.",
                "CCF グループ「{group}」（メンバー: {member}）: β が 0 から 1 までの数値では"
                "ないため、グループは適用されません。",
            ),
            "fix": ("Enter β as a number from 0 to 1 in the CCF groups tab.",
                    "CCF グループタブで β を 0 から 1 までの数値で入力してください。"),
        },
        "model": {
            "reason": ('model "{model}" is not available', "モデル「{model}」は利用できません"),
            "message": (
                'CCF group "{group}" (members: {member}): the model "{model}" is not available '
                "in this version, so the group is not applied.",
                "CCF グループ「{group}」（メンバー: {member}）: モデル「{model}」はこの版では"
                "利用できないため、グループは適用されません。",
            ),
            "fix": ("Use the beta-factor or alpha-factor model.",
                    "ベータファクターまたはアルファファクターモデルを使用してください。"),
        },
        "id": {
            "reason": ("group id missing or repeated", "グループ ID がないか重複しています"),
            "message": (
                'CCF group "{group}" (members: {member}): the group id is missing or used by '
                "another group, so the group is not applied.",
                "CCF グループ「{group}」（メンバー: {member}）: グループ ID がないか他の"
                "グループと重複しているため、グループは適用されません。",
            ),
            "fix": ("Delete this group and create it again.",
                    "このグループを削除して作り直してください。"),
        },
        "reserved": _RESERVED_ID,
        "event_id": {
            "reason": ('CCF event id "{event}" would be made twice',
                       "CCF 事象 ID「{event}」が重複します"),
            "message": (
                'CCF group "{group}" (members: {member}): the CCF event id "{event}" would be '
                "made more than once, which would merge two different events. Event ids join "
                'group and member ids with "+" and ":", so ids that contain these characters '
                "can clash. The group is not applied.",
                "CCF グループ「{group}」（メンバー: {member}）: CCF 事象 ID「{event}」が複数回作られ、"
                "異なる 2 つの事象が 1 つにまとめられてしまいます。事象 ID はグループ ID とメンバー ID を"
                "「+」と「:」でつないで作るため、これらの文字を含む ID は重複することがあります。"
                "グループは適用されません。",
            ),
            "fix": ('Rename the group or member ids that contain "+" or ":" so that the CCF '
                    "event ids differ.",
                    "「+」または「:」を含むグループ ID またはメンバー ID を変更して、CCF 事象 ID が"
                    "重複しないようにしてください。"),
        },
    },
    # F2A (DESIGN 4.2): alpha-factor model. {n} members, {count} stored alpha values,
    # {k} position of an alpha (1-based), {sum} the sum of the alphas. Count texts are
    # number-neutral ("number of members: {n}") so that 1 never reads "1 members".
    "CCF_ALPHA_SIZE": {"": {
        "reason": ("alpha-factor model needs 2 to 4 members",
                   "アルファファクターモデルにはメンバーが 2 件から 4 件必要"),
        "message": (
            'CCF group "{group}": number of members: {n}. The alpha-factor model handles groups '
            "of 2 to 4 members, so the group is not applied.",
            "CCF グループ「{group}」のメンバーは {n} 件です。アルファファクターモデルが扱えるのは "
            "2 件から 4 件のグループなので、グループは適用されません。",
        ),
        "fix": ("Use 2 to 4 members, or switch the group to the beta-factor model.",
                "メンバーを 2 件から 4 件にするか、グループをベータファクターモデルに切り替えてください。"),
    }},
    "CCF_ALPHA_SUM": {
        "length": {
            "reason": ("α values: {count}, members: {n}",
                       "メンバー {n} 件に対し α の値が {count} 個"),
            "message": (
                'CCF group "{group}" (members: {member}): the number of α values ({count}) '
                "differs from the number of members ({n}); α1 to α{n} are needed, so the group "
                "is not applied.",
                "CCF グループ「{group}」（メンバー: {member}）: メンバーは {n} 件ですが、α の値は "
                "{count} 個です（α1 から α{n} までが必要です）。グループは適用されません。",
            ),
            "fix": _FIX_ALPHA,
        },
        "range": {
            "reason": ("α{k} is not a number from 0 to 1",
                       "α{k} が 0 から 1 までの数値ではありません"),
            "message": (
                'CCF group "{group}" (members: {member}): α{k} is not a number from 0 to 1, so '
                "the group is not applied.",
                "CCF グループ「{group}」（メンバー: {member}）: α{k} が 0 から 1 までの数値では"
                "ないため、グループは適用されません。",
            ),
            "fix": _FIX_ALPHA,
        },
        "sum": {
            "reason": ("α values add up to {sum}, not 1", "α の合計が 1 ではなく {sum} です"),
            "message": (
                'CCF group "{group}" (members: {member}): the α values add up to {sum}. They '
                "must add up to 1 (a difference up to 0.001 is corrected), so the group is not "
                "applied.",
                "CCF グループ「{group}」（メンバー: {member}）: α の合計は {sum} です。合計は 1 で"
                "なければなりません（0.001 までの差は補正されます）。グループは適用されません。",
            ),
            "fix": _FIX_ALPHA,
        },
    },
    "CCF_ALPHA_NORMALISED": {"": {
        "reason": ("α values add up to {sum}; divided by the sum",
                   "α の合計が {sum} のため、合計で割って補正しました"),
        "message": (
            'CCF group "{group}": the α values add up to {sum}, not 1. Each α is divided by the '
            "sum before use (a difference up to 0.001 is accepted).",
            "CCF グループ「{group}」: α の合計は 1 ではなく {sum} です。使用前に各 α を合計で"
            "割っています（0.001 までの差は許容されます）。",
        ),
        "fix": ("Check the α values against their source; published sets are rounded.",
                "α の値を出典と照らして確認してください。公表されている値は丸められています。"),
    }},
    "CCF_NO_TESTING": {
        "missing": {
            "reason": ("testing scheme missing", "試験方式が未指定"),
            "message": (
                'CCF group "{group}" (members: {member}): no testing scheme is chosen. The '
                "alpha-factor model needs staggered or non-staggered testing, so the group is "
                "not applied.",
                "CCF グループ「{group}」（メンバー: {member}）: 試験方式が指定されていません。"
                "アルファファクターモデルには時間差試験か同時試験の指定が必要なため、グループは"
                "適用されません。",
            ),
            "fix": _FIX_SCHEME,
        },
        "unknown": {
            "reason": ('testing scheme "{testing}" is not recognised',
                       "試験方式「{testing}」は認識できません"),
            "message": (
                'CCF group "{group}" (members: {member}): the testing scheme "{testing}" is not '
                "recognised (allowed in the file: staggered, nonStaggered), so the group is not "
                "applied.",
                "CCF グループ「{group}」（メンバー: {member}）: 試験方式「{testing}」は認識できません"
                "（ファイルでは staggered または nonStaggered を指定します）。グループは適用されません。",
            ),
            "fix": _FIX_SCHEME,
        },
    },
    "CCF_MEMBER_RENAMED": {"": {
        "reason": ('"{member}" was renamed when the file was opened',
                   "「{member}」はファイルを開いたときに ID が付け替えられました"),
        "message": (
            'CCF group "{group}": member "{member}" was renamed when the file was opened '
            "(duplicate id repair), so it is not clear which event is meant. The group is not "
            "applied.",
            "CCF グループ「{group}」: メンバー「{member}」はファイルを開いたときに ID が"
            "付け替えられた（重複 ID の修復）ため、どの事象を指すか不明です。"
            "グループは適用されません。",
        ),
        "fix": ("Choose the members of the group again in the CCF groups tab.",
                "CCF グループタブでグループのメンバーを選び直してください。"),
    }},
    "CCF_HIGH_Q": {
        "": {
            "reason": ('probability of "{member}" is above 0.01',
                       "「{member}」の確率が 0.01 を超えています"),
            "message": (
                'CCF group "{group}": the probability of "{member}" is {q}, above 0.01. The '
                "beta-factor model keeps only the independent and global common-cause terms, "
                "a simplification; NUREG/CR-5485 p. 44 lists an independent event unavailability "
                "of 10^-2 or less among the conditions for it. Check the result.",
                "CCF グループ「{group}」: 「{member}」の確率は {q} で、0.01 を超えています。"
                "ベータファクターモデルは独立事象と、全メンバーを同時に故障させる CCF 事象の項のみを扱う単純化です。"
                "NUREG/CR-5485 p. 44 は、その条件の一つとして独立事象の不稼働率が 10^-2 以下で"
                "あることを挙げています。結果を確認してください。",
            ),
            "fix": _FIX_HIGH_Q,
        },
        # F2A (DESIGN 4.2): no page is cited for alpha (the beta text above cites p. 44);
        # S1 pp. 40-42 hold no such statement.
        "alpha": {
            "reason": ('probability of "{member}" is above 0.01',
                       "「{member}」の確率が 0.01 を超えています"),
            "message": (
                'CCF group "{group}": the probability of "{member}" is {q}, above 0.01. The '
                "alpha-factor model assumes small probabilities; check the result.",
                "CCF グループ「{group}」: 「{member}」の確率は {q} で、0.01 を超えています。"
                "アルファファクターモデルは小さな確率を前提としています。結果を確認してください。",
            ),
            "fix": _FIX_HIGH_Q,
        },
    },
    "CCF_ZERO_Q": {"": {
        "reason": ("probability is 0", "確率が 0 です"),
        "message": (
            'CCF group "{group}" (members: {member}): every member has probability 0, so the '
            "group has no effect.",
            "CCF グループ「{group}」（メンバー: {member}）: すべてのメンバーの確率が 0 のため、"
            "グループは結果に影響しません。",
        ),
        "fix": ("Check the probability of the members.", "メンバーの確率を確認してください。"),
    }},
    "CCF_ORDERED_GATE": {"": {
        "reason": ('"{member}" is below a PAND or XOR gate',
                   "「{member}」は PAND または XOR ゲートの下にあります"),
        "message": (
            'CCF group "{group}": "{member}" is below a PAND or XOR gate. The cut sets treat PAND '
            "as AND and XOR as OR, so the CCF event ignores the order logic; check the result.",
            "CCF グループ「{group}」: 「{member}」は PAND または XOR ゲートの下にあります。"
            "カットセットでは PAND を AND、XOR を OR として扱うため、CCF 事象は順序の条件を"
            "考慮しません。結果を確認してください。",
        ),
        "fix": ("Check that treating the gate as AND or OR is right for this group.",
                "このグループでゲートを AND または OR として扱ってよいか確認してください。"),
    }},
}


def _fill(pair: Tuple[str, str], index: int, params: Mapping[str, Any]) -> str:
    return pair[index].format(**params)


def lint_text(code: str, kind: Optional[str], params: Mapping[str, Any]) -> Dict[str, Dict[str, Optional[str]]]:
    """``{"en": {reason, message, fix}, "ja": {...}}`` for one finding.

    ``params`` holds ``group``, ``member`` and the extras the text uses
    (``reference``, ``other``, ``model``, ``q``); a placeholder the text does
    not use is ignored. ``fix`` is None for a status (``CCF_ETA_MODE``).
    """
    kinds = LINT[code]
    entry = kinds.get(kind or "", kinds.get("", None)) or next(iter(kinds.values()))
    fields = {"group": "", "member": "", "reference": "", "other": "", "model": "", "q": "",
              "n": "", "count": "", "k": "", "sum": "", "testing": "", "event": ""}
    fields.update({key: str(value) for key, value in params.items()})
    out: Dict[str, Dict[str, Optional[str]]] = {}
    for index, lang in enumerate(LANGS):
        out[lang] = {
            "reason": _fill(entry["reason"], index, fields),
            "message": _fill(entry["message"], index, fields),
            "fix": _fill(entry["fix"], index, fields) if entry["fix"] else None,
        }
    return out


def note(lang: str = "en") -> str:
    """The FN-67 note in ``lang`` (``en`` or ``ja``)."""
    return NOTE[1] if lang == "ja" else NOTE[0]


#: The flat text table of DESIGN D5: ``TEXT[lang][key]``. These are the
#: sentences the server writes itself (report section, CLI, API) and that the
#: browser catalog ``static/js/i18n/ccf.js`` repeats word for word: a pytest
#: compares the two. The lint texts are in ``LINT`` above.
TEXT: Dict[str, Dict[str, str]] = {
    "en": {
        "note": NOTE[0],
        "applied": APPLIED[0],
        "notApplied": NOT_APPLIED[0],
        # UI-7, the six assumptions (SPEC 7.3).
        "assume.model": (
            "Beta-factor model: Q_1 = (1 − β)·Q_t is the independent part of each member "
            "and Q_m = β·Q_t is one event failing all m members (NUREG/CR-4780 Vol. 2, "
            "Table C-1 p. C-5 and Eq. C.10-C.13 p. C-6; NUREG/CR-5485, Eq. 5.11-5.13 p. 42)."),
        "assume.qt": "A member's probability is its total failure probability Q_t at mission time.",
        "assume.beta": "Beta factor: the CCF event fails all members together.",
        "assume.split": (
            "The split is applied to Q_t; splitting λ instead agrees only to first order "
            "in λT (NASA/SP-2011-3421, p. D-20)."),
        "assume.headline": (
            "The headline is the min-cut upper bound; the formulas in the sources use "
            "the rare-event approximation."),
        "assume.sampling": "β and α are not sampled in Monte Carlo.",
        # FN-25, the report section.
        "report.heading": "Common-cause failure (CCF) groups",
        "report.testing": "Testing scheme",
        "report.formulas": "Formulas",
        "report.notApplied": "Not applied: {reason}. Results exclude this group.",
        "report.incomplete": "[incomplete, CCF not included]",
        # FN-25, FN-26, FN-66: the headline line, the CCF section's own wording, event names.
        "headline.includes": "includes CCF ({n} groups)",
        "headline.includes1": "includes CCF (1 group)",
        "headline.walk": "tree walk, without CCF; cut sets cut short ({reason})",
        "headline.reason.time": "time",
        "headline.reason.error": "error",
        "headline.reason.cap": "summary cap",
        "col.members": "Members",
        "model.beta": "Beta factor",
        "param.beta": "β = {beta}",
        # F2A (DESIGN 5): the alpha-factor model in the report.
        "model.alpha": "Alpha factor",
        "report.alpha.parameters": "α = ({values})",
        "report.alpha.sum": "sum {sum}, each α divided by the sum",
        "report.testing.staggered": "Staggered testing",
        "report.testing.nonStaggered": "Non-staggered testing",
        "report.testing.none": "not chosen",
        "report.alpha.overlap": (
            'Group "{group}" (alpha, {n} members): any cut sets with two CCF events of this '
            'group that share a member are kept; NUREG/CR-5485 disallows them (see the note '
            'above).'),
        "assume.alpha": (
            "Alpha-factor model: Q_k is the probability of each CCF event that fails exactly k "
            "of the group's members; staggered Q_k = α_k / C(m-1, k-1) · Q_t (NUREG/CR-5485 "
            "Eq. 5.6 p. 40); non-staggered Q_k = k / C(m-1, k-1) · (α_k / α_t) · Q_t with "
            "α_t = Σ k·α_k (Eq. 5.7-5.9 p. 41; NUREG/CR-4780 Vol. 2 Eq. C.23-C.24 "
            "pp. C-10/C-11)."),
        "event.independent": "{name} (independent part)",
        "event.ccf": "CCF: {name}",
        "label.subset": "CCF: {name} ({members})",
        "report.assumptions": "CCF assumptions",
        "report.etaHint": "Switch the document to fault-tree mode to apply the group.",
        "report.formula.independent": (
            "Independent part of each member: Q_1 = (1 − β)·Q_t (NUREG/CR-4780 Vol. 2, "
            "Table C-1 p. C-5 and Eq. C.10-C.13 p. C-6; NUREG/CR-5485, Eq. 5.11-5.13 p. 42)."),
        "report.formula.event": (
            "CCF event that fails all m members together: Q_m = β·Q_t (same sources; "
            "NASA/SP-2011-3421, Eq. 7-3 p. 7-5)."),
        "report.formula.check": (
            "Check: an AND of two members gives Q_1² + Q_m and an OR of two members gives "
            "2·Q_1 + Q_m (NUREG/CR-5485, Table 5-2 p. 49)."),
        "diagram.ccfGates": (
            "Boxes above or linking to a CCF member show the min-cut upper bound (MCUB) of the "
            "expanded tree, or n/a (CCF) when the cut sets are incomplete. Other boxes show "
            "tree-walk values. "
            "indep. = independent part."),
        "report.overlap": (
            "Overlapping CCF events: with alpha-factor groups of 3 or 4 members, this editor "
            "treats the CCF events of a group as independent basic events, so cut sets with two "
            "CCF events that share a member (for example {C_AB, C_AC}) are kept. NUREG/CR-5485 "
            "treats such events as mutually exclusive and disallows those cut sets (pp. 47-48; "
            "Table E-2 p. E-4). The kept cut sets raise the rare-event sum and the min-cut upper "
            "bound by a second-order amount. For all three members of a group of 3 failing, the "
            "amount is 3·Q_2²; at Q_t = 1e-3 that is 7.8e-5 relative for α = (0.955, 0.034, "
            "0.011) with staggered testing and 9.9e-5 non-staggered, and 6.0e-4 and 7.2e-4 for α "
            "= (0.9, 0.09, 0.01). The relative amount can be larger when α_m is very small "
            "compared with α_2. A beta-factor group has one CCF event, so this does not arise "
            "for it."),
    },
    "ja": {
        "note": NOTE[1],
        "applied": APPLIED[1],
        "notApplied": NOT_APPLIED[1],
        "assume.model": (
            "ベータファクターモデル: Q_1 = (1 − β)·Q_t が各メンバーの独立部分、Q_m = β·Q_t が全 m "
            "メンバーを同時に故障させる 1 つの事象です（NUREG/CR-4780 Vol. 2 表 C-1 p. C-5、"
            "式 C.10-C.13 p. C-6、NUREG/CR-5485 式 5.11-5.13 p. 42）。"),
        "assume.qt": "メンバーの確率は、ミッション時間における全故障確率 Q_t です。",
        "assume.beta": "ベータファクター: CCF 事象は全メンバーを同時に故障させます。",
        "assume.split": (
            "分割は Q_t に適用します。λ を分割した場合は、λT の一次の範囲でのみ一致します"
            "（NASA/SP-2011-3421 p. D-20）。"),
        "assume.headline": (
            "頂上事象の値は最小カット上限（MCUB）です。出典の式はレアイベント近似を用いています。"),
        "assume.sampling": "モンテカルロでは β と α はサンプリングしません。",
        "report.heading": "共通原因故障（CCF）グループ",
        "report.testing": "試験方式",
        "report.formulas": "計算式",
        "report.notApplied": "未適用: {reason}。結果にはこのグループは含まれていません。",
        "report.incomplete": "[不完全、CCF は含まれていません]",
        "headline.includes": "CCF を含む（{n} グループ）",
        "headline.includes1": "CCF を含む（1 グループ）",
        "headline.walk": "ツリー計算（CCF なし）、カットセットが途中で打ち切られました（{reason}）",
        "headline.reason.time": "時間",
        "headline.reason.error": "エラー",
        "headline.reason.cap": "サマリー上限",
        "col.members": "メンバー",
        "model.beta": "ベータファクター",
        "param.beta": "β = {beta}",
        "model.alpha": "アルファファクター",
        "report.alpha.parameters": "α = ({values})",
        "report.alpha.sum": "合計 {sum}、各 α を合計で割って使用",
        "report.testing.staggered": "時間差試験",
        "report.testing.nonStaggered": "同時試験",
        "report.testing.none": "未選択",
        "report.alpha.overlap": (
            "グループ「{group}」（α、メンバー {n} 件）: このグループの、メンバーを共有する 2 つの CCF "
            "事象を含むカットセットがあれば残します。NUREG/CR-5485 はこれらを除外しています（上の注記を参照）。"),
        "assume.alpha": (
            "アルファファクターモデル: Q_k は、与えられたメンバーのうちちょうど k 個を故障させる"
            "各 CCF 事象の確率です。時間差試験では Q_k = α_k / C(m-1, k-1) · Q_t"
            "（NUREG/CR-5485 式 5.6 p. 40）、同時試験では α_t = Σ k·α_k として "
            "Q_k = k / C(m-1, k-1) · (α_k / α_t) · Q_t（式 5.7-5.9 p. 41、NUREG/CR-4780 Vol. 2 "
            "式 C.23-C.24 pp. C-10/C-11）です。"),
        "event.independent": "{name}（独立部分）",
        "event.ccf": "CCF: {name}",
        "label.subset": "CCF: {name}（{members}）",
        "report.assumptions": "CCF の前提条件",
        "report.etaHint": "グループを適用するには、文書を故障の木モードにしてください。",
        "report.formula.independent": (
            "各メンバーの独立部分: Q_1 = (1 − β)·Q_t（NUREG/CR-4780 Vol. 2 表 C-1 p. C-5、"
            "式 C.10-C.13 p. C-6、NUREG/CR-5485 式 5.11-5.13 p. 42）。"),
        "report.formula.event": (
            "全 m メンバーを同時に故障させる CCF 事象: Q_m = β·Q_t（出典は同じ、"
            "NASA/SP-2011-3421 式 7-3 p. 7-5）。"),
        "report.formula.check": (
            "検算: 2 メンバーの AND は Q_1² + Q_m、2 メンバーの OR は 2·Q_1 + Q_m になります"
            "（NUREG/CR-5485 表 5-2 p. 49）。"),
        "diagram.ccfGates": (
            "CCF メンバーより上の箱、または CCF メンバーへのリンクを持つ箱には、展開したツリーの最小カット上限（MCUB）を表示し、"
            "カットセットが不完全な場合は n/a (CCF) と表示します。その他の箱はツリー計算値です。"
            "indep. は独立部分です。"),
        "report.overlap": (
            "重なり合う CCF 事象: メンバーが 3 または 4 件のアルファファクターのグループでは、このエディターは同じグループの CCF "
            "事象を互いに独立な基本事象として扱うため、メンバーを共有する 2 つの CCF 事象を含むカットセット（例: {C_AB, "
            "C_AC}）を残します。NUREG/CR-5485 はこのような事象を互いに排反として扱い、そのカットセットを除外しています（pp. 47-48、表 E-2 p. "
            "E-4）。残したカットセットは、レアイベント近似の合計と最小カット上限を二次のオーダーの量だけ大きくします。3 件のグループで 3 件すべてが故障する場合、その量は "
            "3·Q_2² で、Q_t = 1e-3 のとき相対値は α = (0.955, 0.034, 0.011) で時間差試験 7.8e-5、同時試験 9.9e-5、α = "
            "(0.9, 0.09, 0.01) でそれぞれ 6.0e-4、7.2e-4 です。α_2 に比べて α_m "
            "が非常に小さいと、相対値はさらに大きくなることがあります。ベータファクターのグループには CCF 事象が 1 つしかないため、該当しません。"),
    },
}


def text(lang: str, key: str, **params: Any) -> str:
    """``TEXT[lang][key]`` with ``{name}`` placeholders replaced by ``params``.

    ``lang`` other than ``ja`` reads English. Only the named placeholders are
    replaced (no ``str.format``), so a literal brace such as the
    ``{C_AB, C_AC}`` of the overlap note is left alone. An unknown ``key``
    raises ``KeyError``.
    """
    table = TEXT["ja" if lang == "ja" else "en"]
    out = table[key]
    for name, value in params.items():
        out = out.replace("{" + name + "}", str(value))
    return out
