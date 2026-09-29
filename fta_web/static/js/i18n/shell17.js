/**
 * i18n/shell17.js -- strings for the 1.7 shell: the bottom tab strip, the
 * Advanced switch, the significant-figure selector and the headline.
 *
 * Catalog format (parsed by fta_web/tests/test_catalog_parity.py, so keep it
 * flat, single-quoted, one entry per line): `export default { en: {...},
 * ja: {...} };`. main.js registerStrings() merges it into STRINGS. Keys must
 * not collide with main.js or any other catalog; the parity test enforces it.
 */
export default {
  en: {
    'panel.bottom': 'Details and analysis',
    'tabs.aria': 'Details and analysis tabs',

    'tab.details': 'Details',
    'tab.quant': 'Quantification',
    'tab.cutsets': 'Cut Sets',
    'tab.importance': 'Importance',
    'tab.uncertainty': 'Uncertainty',
    'tab.validation': 'Validation',
    'tab.trace': 'Traceability',
    'tab.fmea': 'FMEA',
    'tab.report': 'Report',

    'tab.comingSoon': 'Coming soon',
    'tab.comingSoonNote': 'The {tab} tab is being built for 1.7.',
    'tab.loadFailed': 'The {tab} tab could not be loaded: {error}',
    'tab.hiddenInBasic': 'The {tab} tab is an advanced feature. Switch on Advanced in the top bar to use it.',

    'bar.advanced': 'Advanced',
    'bar.advancedTitle': 'Show advanced gates, models and analysis tabs. Calculations and files are the same either way.',
    'bar.sigFigs': 'Sig. figs',
    'bar.sigFigsTitle': 'Significant figures used to display probabilities',

    'headline.label': 'Top event',
    'headline.title': 'Top-event probability',
    'headline.mcub': 'MCUB',
    'headline.mcubTitle': 'Min-cut upper bound, used because {reason}. Tree walk: {alt}',
    'headline.reason.repeated': 'the tree has repeated events',
    'headline.reason.nonCoherent': 'the tree has XOR (non-coherent) gates',
    'headline.reason.both': 'the tree has repeated events and XOR (non-coherent) gates',
    'headline.reason.other': 'the tree walk is not exact for this tree',
    'headline.pandNote': 'PAND treated as AND in cut sets (conservative).',
    'headline.cappedNote': 'Quick estimate (summary capped at 2000 cut sets / 2 s) — open the Cut Sets tab for the full result',
    'headline.truncatedNote': 'Cut sets truncated by the document limits',

    'boot.busy': 'Loading the editor panels…',

    'tab.badgeErrors': '{tab}, {n} error(s)',
    'tab.badgeWarnings': '{tab}, {n} warning(s)',
    'toast.showValidation': 'Show in Validation',
    'toast.dismiss': 'Dismiss',
  },
  ja: {
    'panel.bottom': '詳細と解析',
    'tabs.aria': '詳細と解析のタブ',

    'tab.details': '詳細',
    'tab.quant': '定量化',
    'tab.cutsets': 'カットセット',
    'tab.importance': '重要度',
    'tab.uncertainty': '不確かさ',
    'tab.validation': '検証',
    'tab.trace': 'トレーサビリティ',
    'tab.fmea': 'FMEA',
    'tab.report': 'レポート',

    'tab.comingSoon': '近日対応',
    'tab.comingSoonNote': '{tab} タブは 1.7 に向けて作成中です。',
    'tab.loadFailed': '{tab} タブを読み込めませんでした: {error}',
    'tab.hiddenInBasic': '{tab} タブは詳細機能です。上部バーの「詳細機能」をオンにすると使用できます。',

    'bar.advanced': '詳細機能',
    'bar.advancedTitle': '高度なゲート、モデル、解析タブを表示します。計算結果とファイルはどちらでも同じです。',
    'bar.sigFigs': '有効桁',
    'bar.sigFigsTitle': '確率の表示に使う有効桁数',

    'headline.label': '頂上事象',
    'headline.title': '頂上事象の確率',
    'headline.mcub': 'MCUB',
    'headline.mcubTitle': '{reason}ため、最小カット上限を使用しています。ツリー計算値: {alt}',
    'headline.reason.repeated': '重複事象がある',
    'headline.reason.nonCoherent': 'XOR(非コヒーレント)ゲートがある',
    'headline.reason.both': '重複事象と XOR(非コヒーレント)ゲートがある',
    'headline.reason.other': 'このツリーではツリー計算が厳密でない',
    'headline.pandNote': 'カットセットでは PAND を AND として扱っています(保守側)。',
    'headline.cappedNote': '簡易見積もりです(サマリーはカットセット 2000 件 / 2 秒で打ち切り)— 完全な結果はカットセットタブで確認してください',
    'headline.truncatedNote': 'ドキュメントの制限によりカットセットが打ち切られています',

    'boot.busy': 'エディターのパネルを読み込んでいます…',

    'tab.badgeErrors': '{tab}、エラー {n} 件',
    'tab.badgeWarnings': '{tab}、警告 {n} 件',
    'toast.showValidation': '検証タブで表示',
    'toast.dismiss': '閉じる',
  },
};
