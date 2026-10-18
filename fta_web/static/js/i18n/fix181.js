/**
 * i18n/fix181.js -- strings for the fixes of the known issues of 1.8.0: Stop
 * in the assistant freeing the editor's AI slot, the recovery copy of unsaved
 * work offered at start-up, and choosing the allowed folder while the editor
 * runs.
 *
 * Catalog format (parsed by fta_web/tests/test_catalog_parity.py, so keep it
 * flat, single-quoted, one entry per line): `export default { en: {...},
 * ja: {...} };`. main.js registerStrings() merges it into STRINGS. Keys must
 * not collide with main.js or any other catalog; the parity test enforces it.
 */
export default {
  en: {
    'ai.msg.stopNotFreed': 'The editor could not be told to abandon that request. Until the provider answers, a new request may be refused as busy.',

    'file.changeRoot': 'Change folder…',
    'file.changeRootTitle': 'Choose another folder for the editor to read and write. The editor opens a folder chooser on this computer.',
    'file.changeRootWaiting': 'A folder chooser has opened on this computer. It may be behind the browser window. Choose the folder there, or close it to keep this one.',
    'file.changeRootUnavailable': 'A folder chooser cannot be opened on this computer. To work in another folder, close the editor and start it with: {command}',
    'file.changeRootBusy': 'A folder chooser is already open on this computer. Answer it first.',
    'file.changeRootCancelled': 'No folder was chosen. The editor still works in the same folder.',
    'file.changeRootDone': 'The editor now reads and writes in {root}.',
    'file.changeRootUntitled': 'The editor now reads and writes in {root}. The open analysis is outside that folder, so it is now untitled: use Save As to keep it. Nothing in it was changed.',
    'file.errOutsideRootChoose': 'That path is outside {root}, the only folder this editor may read or write. To work in another folder or on another drive, use "Change folder…".',

    'recovery.title': 'Unsaved work found',
    'recovery.offer': 'The editor was closed, or stopped, while an analysis had unsaved changes. A copy of it was kept.',
    'recovery.offerFile': 'The editor was closed, or stopped, while an analysis had unsaved changes. A copy of it was kept. It had been opened from {path}; restoring does not change that file.',
    'recovery.restore': 'Restore unsaved work from {date} ({title})',
    'recovery.discard': 'Discard it',
    'recovery.untitled': 'untitled',
    'recovery.restored': 'Restored "{title}" as an untitled copy. Use Save As to keep it.',
    'recovery.discardConfirm': 'Discard the unsaved work from {date} ({title})? The copy is deleted and cannot be brought back.',
    'recovery.discardOk': 'Discard the copy',
    'recovery.discarded': 'The recovery copy was deleted.',
  },
  ja: {
    'ai.msg.stopNotFreed': 'エディターにこの要求の破棄を伝えられませんでした。プロバイダーから回答が返るまで、新しい要求が処理中として拒否されることがあります。',

    'file.changeRoot': 'フォルダーを変更…',
    'file.changeRootTitle': 'エディターが読み書きするフォルダーを選び直します。このコンピューター上にフォルダー選択画面が開きます。',
    'file.changeRootWaiting': 'このコンピューター上にフォルダー選択画面を開きました。ブラウザーの後ろに隠れていることがあります。そこでフォルダーを選ぶか、閉じて今のフォルダーのままにしてください。',
    'file.changeRootUnavailable': 'このコンピューターではフォルダー選択画面を開けません。別のフォルダーで作業するには、エディターを終了し、次のコマンドで起動してください: {command}',
    'file.changeRootBusy': 'フォルダー選択画面がすでに開いています。先にそちらを操作してください。',
    'file.changeRootCancelled': 'フォルダーは選ばれませんでした。エディターは今のフォルダーのままです。',
    'file.changeRootDone': 'エディターが読み書きするフォルダーは {root} になりました。',
    'file.changeRootUntitled': 'エディターが読み書きするフォルダーは {root} になりました。開いている解析はそのフォルダーの外にあるため、無題になりました。残すには「名前を付けて保存」を使ってください。内容は変更されていません。',
    'file.errOutsideRootChoose': 'そのパスは {root} の外にあります。このエディターが読み書きできるのはこのフォルダーだけです。別のフォルダーやドライブで作業するには、「フォルダーを変更…」を使用してください。',

    'recovery.title': '保存されていない作業が見つかりました',
    'recovery.offer': '変更が保存されていない解析を開いたまま、エディターが閉じられたか停止しました。そのコピーが残っています。',
    'recovery.offerFile': '変更が保存されていない解析を開いたまま、エディターが閉じられたか停止しました。そのコピーが残っています。元のファイルは {path} です。復元してもそのファイルは変更されません。',
    'recovery.restore': '{date} の未保存の作業を復元（{title}）',
    'recovery.discard': '破棄する',
    'recovery.untitled': '無題',
    'recovery.restored': '「{title}」を無題のコピーとして復元しました。残すには「名前を付けて保存」を使ってください。',
    'recovery.discardConfirm': '{date} の未保存の作業（{title}）を破棄しますか？コピーは削除され、元に戻せません。',
    'recovery.discardOk': 'コピーを破棄',
    'recovery.discarded': '復元用のコピーを削除しました。',
  },
};
