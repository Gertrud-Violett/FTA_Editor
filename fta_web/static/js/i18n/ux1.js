/**
 * i18n/ux1.js -- strings for the editing-flow changes: adding several nodes
 * in a row, the first-child warning, delete confirmations that count, the
 * file name in the status line and the tab title, and the wording of a few
 * refusals.
 *
 * Catalog format (parsed by fta_web/tests/test_catalog_parity.py, so keep it
 * flat, single-quoted, one entry per line): `export default { en: {...},
 * ja: {...} };`. main.js registerStrings() merges it into STRINGS. Keys must
 * not collide with main.js or any other catalog; the parity test enforces it.
 */
export default {
  en: {
    'dialog.addAnother': 'OK and add another',
    'dialog.addAnotherTitle': 'Create this node and keep the dialog open for the next one (Ctrl+Enter)',
    'dialog.addedOne': 'Added "{name}". Type the next one, or press Escape to finish.',
    'dialog.probabilityRequired': 'Enter a probability from 0 to 1. For an event that will get children of its own the value is not used: enter 1.',
    'dialog.probabilityPlaceholder': '0 to 1, e.g. 1e-3, 0.5% or 1/1000',

    'msg.added': 'Added "{name}" under "{parent}".',
    'msg.firstChild': '"{name}" now has a child, so its own probability ({p}) is no longer used. It is calculated from its children.',

    'confirm.deleteLeaf': 'Delete "{name}"?',
    'confirm.deleteTree': 'Delete "{name}" and everything beneath it? That is {n} nodes.',
    'tree.confirmDeleteManyLeaves': 'Delete these {n} nodes?',
    'tree.confirmDeleteManyTree': 'Delete these {n} nodes and everything beneath them? That is {total} nodes.',

    'tree.moveNoRoomUp': 'It is already the first of its siblings.',
    'tree.moveNoRoomDown': 'It is already the last of its siblings.',

    'details.probabilityUnused': 'Not used in the calculation: this node has children, and its value comes from them.',
    'details.notSaved': '{field} of "{name}" was not saved: "{value}" is not a valid value.',

    'status.untitled': 'Untitled',

    'file.errFolderNotFound': 'Folder not found: {path}',
    'file.errFileNotFound': 'File not found: {path}',
  },
  ja: {
    'dialog.addAnother': '決定して続けて追加',
    'dialog.addAnotherTitle': 'このノードを作成し、ダイアログを開いたまま次のノードを入力します (Ctrl+Enter)',
    'dialog.addedOne': '「{name}」を追加しました。次のノードを入力するか、Esc キーで終了します。',
    'dialog.probabilityRequired': '確率を 0 から 1 の範囲で入力してください。あとで子ノードを追加する事象では値は使用されないため、1 を入力してください。',
    'dialog.probabilityPlaceholder': '0 から 1（例: 1e-3、0.5%、1/1000）',

    'msg.added': '「{name}」を「{parent}」の配下に追加しました。',
    'msg.firstChild': '「{name}」に子ノードができたため、このノード自身の確率（{p}）は使用されなくなりました。値は子ノードから計算されます。',

    'confirm.deleteLeaf': '「{name}」を削除しますか？',
    'confirm.deleteTree': '「{name}」と配下のノードを削除しますか？ 合計 {n} 件のノードが削除されます。',
    'tree.confirmDeleteManyLeaves': 'これら {n} 件のノードを削除しますか？',
    'tree.confirmDeleteManyTree': 'これら {n} 件のノードと配下のノードを削除しますか？ 合計 {total} 件のノードが削除されます。',

    'tree.moveNoRoomUp': '既に兄弟ノードの先頭にあります。',
    'tree.moveNoRoomDown': '既に兄弟ノードの末尾にあります。',

    'details.probabilityUnused': '計算には使用されません。このノードには子ノードがあり、値は子ノードから計算されます。',
    'details.notSaved': '「{name}」の{field}は保存されませんでした。「{value}」は有効な値ではありません。',

    'status.untitled': '無題',

    'file.errFolderNotFound': 'フォルダーが見つかりません: {path}',
    'file.errFileNotFound': 'ファイルが見つかりません: {path}',
  },
};
