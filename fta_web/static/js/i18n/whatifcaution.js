/**
 * i18n/whatifcaution.js -- strings for the caution line of the What-if tab (feature FR, task X3):
 * one short text per caution (a CCF group not applied at baseline, a CCF member at probability 1,
 * a CCF member above the high-q limit, a scaled standby event with a large lambda-tau, cut sets
 * limited by max order or max count), the suffix "(and N more)" and the word of the badge. The limit in the texts is filled
 * from the server's `cautions` entry. Kept apart from i18n/whatif.js, whose key set is pinned
 * by an acceptance test. Flat, single-quoted, one entry per line.
 */
export default {
  en: {
    'whatif.caution.ccfNotApplied': 'CCF group not applied at baseline; CCF not included',
    'whatif.caution.ccfOne': 'A CCF member is at probability 1. Typed into the document, the group would not be applied.',
    'whatif.caution.ccfHigh': 'A CCF member\'s probability is above {limit}. Check the CCF result.',
    'whatif.caution.standby': 'A scaled standby event has λτ above {limit}, where the λτ/2 approximation is poor.',
    'whatif.caution.cutsets': 'Cut sets are limited by max order or max count; some may be missing from the what-if number.',
    'whatif.caution.more': '(and {n} more)',
    'whatif.caution.badge': 'Caution',
  },
  ja: {
    'whatif.caution.ccfNotApplied': 'ベースラインで CCF グループが適用されていないため、CCF は含まれません。',
    'whatif.caution.ccfOne': 'CCF グループのメンバーの確率が 1 です。文書に入力するとグループは適用されなくなります。',
    'whatif.caution.ccfHigh': 'CCF グループのメンバーの確率が {limit} を超えています。CCF の結果を確認してください。',
    'whatif.caution.standby': '倍率をかけた待機系事象の λτ が {limit} を超えており、λτ/2 近似の精度が低下します。',
    'whatif.caution.cutsets': '最大次数または最大件数でカットセットが制限されており、一部のカットセットが What-if 値に含まれない場合があります。',
    'whatif.caution.more': '（ほか {n} 件）',
    'whatif.caution.badge': '注意',
  },
};
