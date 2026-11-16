/**
 * i18n/imp.js -- strings for the Importance tab. The measure acronyms (FV,
 * RAW, RRW) are column headers written in the tab itself; their explanations
 * are here. Flat, single-quoted, one entry per line.
 */
export default {
  en: {
    'imp.colorFv': 'Colour diagram by FV',
    'imp.colorFvTitle': 'Tint every event in the tree and the diagram by its Fussell-Vesely importance',
    'imp.col.event': 'Event',
    'imp.col.cutSets': 'Cut sets',
    'imp.title.fv': 'Fussell-Vesely: the fraction of the top-event probability that involves this event',
    'imp.title.birnbaum': 'Birnbaum: Q with the event certain minus Q with the event impossible',
    'imp.title.raw': 'Risk achievement worth: Q with the event certain divided by Q',
    'imp.title.rrw': 'Risk reduction worth: Q divided by Q with the event impossible',
    'imp.title.q': 'The event probability',
    'imp.basis': 'Computed on the min-cut upper bound Q = {q} over {n} cut sets.',
    'imp.truncated': 'The cut sets were truncated, so the measures are approximate.',
    'imp.infiniteTitle': 'Infinite: the top event cannot occur without this event',
    'imp.none': 'No events: the top event has no cut sets.',
    'imp.notRun': 'Press Run to compute the importance measures.',
    'imp.hint': 'Click a column heading to sort, or a row to select the event.',
  },
  ja: {
    'imp.colorFv': 'FV で図を色分け',
    'imp.colorFvTitle': 'ツリーと図の各事象を Fussell-Vesely 重要度で色付けします',
    'imp.col.event': '事象',
    'imp.col.cutSets': 'カットセット数',
    'imp.title.fv': 'Fussell-Vesely: 頂上事象確率のうち、この事象が関わる割合',
    'imp.title.birnbaum': 'Birnbaum: 事象が確実に発生する場合の Q から、発生しない場合の Q を引いた値',
    'imp.title.raw': 'リスク増加価値: 事象が確実に発生する場合の Q を Q で割った値',
    'imp.title.rrw': 'リスク低減価値: Q を、事象が発生しない場合の Q で割った値',
    'imp.title.q': '事象の確率',
    'imp.basis': '{n} 件のカットセットによる最小カット上限 Q = {q} に基づいて計算しています。',
    'imp.truncated': 'カットセットが打ち切られているため、重要度は近似値です。',
    'imp.infiniteTitle': '無限大: この事象がなければ頂上事象は発生しません',
    'imp.none': '事象がありません。頂上事象にカットセットがありません。',
    'imp.notRun': '「実行」を押すと重要度を計算します。',
    'imp.hint': '列見出しをクリックすると並べ替え、行をクリックすると事象を選択します。',
  },
};
