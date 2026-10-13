/**
 * i18n/ux3.js -- strings for the analysis, diagram and AI changes: the
 * diagram's settings button, 100% and zoom to the selection, the bottom
 * panel's enlarge button, ETA wording (headline, tabs, the assistant), the
 * gate and probability shown on tree rows, moving several nodes at once,
 * Copy CSV on the Importance tab, uncertainty for all events at once, the
 * rare-event note, the coloured diagram in the report, and the assistant's
 * Stop, reload, suggestion cards and setup dialog.
 *
 * Catalog format (parsed by fta_web/tests/test_catalog_parity.py, so keep it
 * flat, single-quoted, one entry per line): `export default { en: {...},
 * ja: {...} };`. main.js registerStrings() merges it into STRINGS. Keys must
 * not collide with main.js or any other catalog; the parity test enforces it.
 * A key ending in `.eta` is the ETA-mode wording of the key before it
 * (chat.js modeKey).
 */
export default {
  en: {
    'diagram3.settingsButton': 'Settings',
    'diagram3.actualSize': 'Actual size (100%)',
    'diagram3.toSelection': 'Show the selected node at a readable size',

    'bottom.maximise': 'Enlarge this panel (a strip of the diagram stays above it)',
    'bottom.restore': 'Back to the usual height',

    'headline.labelEta': 'Initiating event',
    'headline.titleEta': 'Probability of the initiating event (the root of the event tree)',
    'tab.etaUnavailable': 'Not available for an event tree (ETA mode): this analysis works on the gates of a fault tree. Switch Mode to FTA to use it.',
    'msg.modeEta': 'Switched to ETA (event tree). Each probability is now that of the path down to its node. Quantification, Cut Sets, Importance and Uncertainty apply to fault trees only.',
    'msg.modeFta': 'Switched to FTA (fault tree). Every probability was recalculated through the gates.',

    'meta.selectedName': 'Selected: {name}',
    'meta.selectedId': 'Node id: {id}',
    'meta.selectedMany': '{n} selected',
    'meta.selectedManyTitle': 'Several nodes are selected in the tree. Delete, a drag and Ctrl+Shift+arrow keys act on all of them. Details shows the one clicked last.',

    'tree.gateTitle': 'Gate: {gate}',
    'tree.probCalcTitle': 'Calculated probability: {value}',
    'tree.probOwnTitle': 'Probability: {value}',
    'tree.movedMany': 'Moved {n} nodes under "{parent}". One Undo takes them all back.',
    'tree.moveManyMixed': 'The selected nodes are under different parents, so the keyboard cannot move them together. Drag them, or select nodes under one parent.',

    'imp.copyCsv': 'Copy CSV',
    'imp.copyCsvTitle': 'Copy the table to the clipboard as CSV, in the order shown, with the numbers in full',
    'imp.copied': 'Copied {n} rows as CSV.',
    'imp.copyFailed': 'Could not copy to the clipboard.',

    'unc.applyAll': 'Lognormal EF={ef} for all events without one',
    'unc.applyAllTitle': 'Gives every basic event that has no uncertainty distribution a lognormal one with error factor {ef}, around its own value. {n} event(s) have none. One Undo takes it back.',
    'unc.appliedAll': 'Gave {n} basic event(s) a lognormal uncertainty with error factor {ef}. Press Run to see the spread.',
    'unc.appliedNone': 'Every basic event already has an uncertainty distribution.',
    'unc.noSpread': 'Every sample gave the same value, so there is no distribution to draw: no event the top event depends on has an uncertainty. Set one per event in the Quantification tab, or use "Lognormal EF={ef} for all events without one" above.',

    'cutsets.rareTitle': 'The sum of the cut-set probabilities (the rare-event approximation). It is an upper bound, not a probability, and can be greater than 1.',
    'cutsets.rareOver': '(a sum, not a probability: above 1 it says nothing; use the min-cut upper bound)',

    'report.fvDiagram': 'Colour the diagram by Fussell-Vesely importance',
    'report.fvUnavailable': 'The importance measures could not be computed, so the diagram in the report is not coloured.',

    'ai.chat.stop': 'Stop',
    'ai.chat.stopTitle': 'Stop waiting for this answer',
    'ai.msg.stopped': 'Stopped waiting. The request cannot be taken back from the provider: until it answers, a new request may be refused as busy.',
    'ai.msg.restored': 'Earlier in this conversation (the editor keeps it while it is running):',
    'ai.msg.restoredUpdate': 'The assistant answered with a rewritten tree.',
    'ai.changes.kind.add': 'Add',
    'ai.changes.kind.edit': 'Change',
    'ai.changes.kind.delete': 'Delete',
    'ai.changes.kind.move': 'Move',
    'ai.changes.node': 'Node:',
    'ai.changes.under': 'Under:',
    'ai.changes.selectTitle': 'Select this node in the tree and the diagram (id {id})',
    'ai.changes.empty': '(empty)',
    'ai.changes.otherDocument': 'These suggestions were made for another analysis, so they can no longer be applied.',

    'ai.chat.placeholder.eta': 'Ask about this event tree. Enter sends, Shift+Enter adds a line.',
    'ai.chat.analyze.eta': 'Analyze ETA',
    'ai.chat.analyzeTitle.eta': 'Ask for a review of this event tree. Nothing is changed.',
    'ai.chat.update.eta': 'Update ETA',
    'ai.chat.updateTitle.eta': 'Ask for an updated event tree. It is verified before it replaces this one.',
    'ai.msg.welcome.eta': 'Ask anything about this event tree. "Analyze ETA" reviews it without changing anything; "Update ETA" proposes a full replacement, which you see before it is applied.',
    'ai.msg.analyzing.eta': 'Analyzing the event tree...',
    'ai.msg.analyzePrompt.eta': 'Analyze this ETA and provide suggestions.',
    'ai.msg.updating.eta': 'Generating an updated event tree...',
    'ai.msg.updatePrompt.eta': 'Update this ETA with your suggestions, preserving the original JSON structure.',
    'ai.msg.updated.eta': 'The event tree was replaced with the verified version.',
    'ai.update.confirmTitle.eta': 'Update ETA',

    'ai.disclosure': 'When you use the assistant, the analysis open in the editor (the whole tree with its names, probabilities and notes) and what you type are sent to the provider you choose here. Nothing is sent until you press Send, Analyze or Update.',
    'ai.hint.azure': 'Needs an Azure OpenAI resource of your own: its endpoint, a deployment name as the model, and that resource key. A Microsoft 365 Copilot subscription does not include one.',
  },
  ja: {
    'diagram3.settingsButton': '設定',
    'diagram3.actualSize': '実寸 (100%)',
    'diagram3.toSelection': '選択中のノードを読める大きさで表示',

    'bottom.maximise': 'このパネルを広げる（上に図を少し残します）',
    'bottom.restore': '通常の高さに戻す',

    'headline.labelEta': '起因事象',
    'headline.titleEta': '起因事象（イベントツリーのルート）の確率',
    'tab.etaUnavailable': 'イベントツリー（ETA モード）では使用できません。この解析はフォールトツリーのゲートを対象とします。使用するにはモードを FTA に切り替えてください。',
    'msg.modeEta': 'ETA（イベントツリー）に切り替えました。各確率はそのノードまでの経路の確率になります。定量化、カットセット、重要度、不確かさはフォールトツリー専用です。',
    'msg.modeFta': 'FTA（フォールトツリー）に切り替えました。すべての確率をゲートに沿って再計算しました。',

    'meta.selectedName': '選択中: {name}',
    'meta.selectedId': 'ノード ID: {id}',
    'meta.selectedMany': '{n} 件を選択中',
    'meta.selectedManyTitle': 'ツリーで複数のノードを選択しています。削除、ドラッグ、Ctrl+Shift+矢印キーは選択したすべてに作用します。詳細には最後にクリックしたノードを表示します。',

    'tree.gateTitle': 'ゲート: {gate}',
    'tree.probCalcTitle': '計算された確率: {value}',
    'tree.probOwnTitle': '確率: {value}',
    'tree.movedMany': '{n} 件のノードを「{parent}」の配下に移動しました。元に戻す操作 1 回ですべて戻ります。',
    'tree.moveManyMixed': '選択したノードの親が異なるため、キーボードではまとめて移動できません。ドラッグするか、同じ親の配下のノードを選択してください。',

    'imp.copyCsv': 'CSV をコピー',
    'imp.copyCsvTitle': '表を表示順のまま、数値を省略せずに CSV としてクリップボードにコピーします',
    'imp.copied': '{n} 行を CSV としてコピーしました。',
    'imp.copyFailed': 'クリップボードにコピーできませんでした。',

    'unc.applyAll': '未設定の全事象に対数正規 EF={ef}',
    'unc.applyAllTitle': '不確かさ分布のないすべての基本事象に、その値を中心とする誤差係数 {ef} の対数正規分布を設定します。未設定の事象は {n} 件です。元に戻す操作 1 回で戻ります。',
    'unc.appliedAll': '{n} 件の基本事象に誤差係数 {ef} の対数正規分布を設定しました。実行を押すとばらつきを確認できます。',
    'unc.appliedNone': 'すべての基本事象に不確かさ分布が設定されています。',
    'unc.noSpread': 'すべてのサンプルが同じ値になったため、描く分布がありません。頂上事象に関わる事象に不確かさが設定されていません。定量化タブで事象ごとに設定するか、上の「未設定の全事象に対数正規 EF={ef}」を使ってください。',

    'cutsets.rareTitle': 'カットセット確率の合計（レアイベント近似）です。確率ではなく上限値で、1 を超えることがあります。',
    'cutsets.rareOver': '（合計であって確率ではありません。1 を超える場合は意味を持たないため、最小カット上限を使ってください）',

    'report.fvDiagram': '図を Fussell-Vesely 重要度で色分けする',
    'report.fvUnavailable': '重要度を計算できなかったため、レポートの図は色分けされていません。',

    'ai.chat.stop': '中止',
    'ai.chat.stopTitle': 'この回答を待つのをやめる',
    'ai.msg.stopped': '待機を中止しました。プロバイダーへの要求は取り消せないため、回答が返るまで新しい要求が処理中として拒否されることがあります。',
    'ai.msg.restored': 'これまでの会話（エディターの実行中は保持されます）:',
    'ai.msg.restoredUpdate': 'アシスタントは書き換えたツリーを返しました。',
    'ai.changes.kind.add': '追加',
    'ai.changes.kind.edit': '変更',
    'ai.changes.kind.delete': '削除',
    'ai.changes.kind.move': '移動',
    'ai.changes.node': 'ノード:',
    'ai.changes.under': '親ノード:',
    'ai.changes.selectTitle': 'ツリーと図でこのノードを選択します（ID {id}）',
    'ai.changes.empty': '（空）',
    'ai.changes.otherDocument': 'これらの提案は別の解析に対するものなので、適用できなくなりました。',

    'ai.chat.placeholder.eta': 'このイベントツリーについて質問してください。Enter で送信、Shift+Enter で改行します。',
    'ai.chat.analyze.eta': 'ETA解析',
    'ai.chat.analyzeTitle.eta': 'このイベントツリーのレビューを依頼します。内容は変更されません。',
    'ai.chat.update.eta': 'ETA更新',
    'ai.chat.updateTitle.eta': '更新版のイベントツリーを依頼します。置き換える前に検証されます。',
    'ai.msg.welcome.eta': 'このイベントツリーについて何でも質問してください。「ETA解析」は内容を変更せずにレビューし、「ETA更新」は全体の置き換え案を提示します。置き換え案は適用前に確認できます。',
    'ai.msg.analyzing.eta': 'イベントツリーを解析しています...',
    'ai.msg.analyzePrompt.eta': 'このETAを解析し、改善案を提示してください。',
    'ai.msg.updating.eta': '更新版のイベントツリーを生成しています...',
    'ai.msg.updatePrompt.eta': '元のJSON構造を保ったまま、提案内容でこのETAを更新してください。',
    'ai.msg.updated.eta': '検証済みの版でイベントツリーを置き換えました。',
    'ai.update.confirmTitle.eta': 'ETA更新',

    'ai.disclosure': 'アシスタントを使うと、エディターで開いている解析（ツリー全体と、その名前・確率・メモ）と入力した内容が、ここで選ぶプロバイダーに送信されます。送信、解析、更新を押すまでは何も送信されません。',
    'ai.hint.azure': 'ご自身の Azure OpenAI リソースが必要です。そのエンドポイント、モデルとしてのデプロイ名、そのリソースのキーを入力します。Microsoft 365 Copilot の契約には含まれません。',
  },
};
