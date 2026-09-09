/**
 * main.js -- the application shell.
 *
 * Owns: boot sequence, the session gate, the metadata bar, the layout grid and
 * its splitters, theme + language, the button bar, keyboard shortcuts, and the
 * one place errors become visible (toast + status line).
 *
 * Does NOT own the tree, the details form or the dialogs. Those live in
 * tree.js / details.js / dialogs.js and are loaded here.
 *
 * BOOT
 * ----
 *   bootstrapToken() -> api.get('/state') -> store.setState() ->
 *   initTree(#tree-root) / initDetails(#details-root)
 *
 * The three sibling modules are pulled in with dynamic import() rather than a
 * static one. A static import that 404s or throws at parse time takes the whole
 * page down to a blank screen; this way a missing or broken panel degrades to a
 * visible message in that panel and the rest of the editor keeps working.
 *
 * HOW DIALOGS.JS IS CALLED
 * ------------------------
 * Two ways, tried in order, so the module can pick whichever it prefers:
 *
 *   1. A cancelable `fta:action` window event:
 *        detail = {action: 'new'|'add'|'edit'|'delete', nodeId?, parentId?}
 *      Call ev.preventDefault() to say "I have this" and the shell stands down.
 *
 *   2. A named export, first match wins:
 *        add    -> openAddDialog | openAddNodeDialog | addNode | showAddDialog
 *        edit   -> openEditDialog | openEditNodeDialog | editNode | showEditDialog
 *        delete -> openDeleteDialog | confirmDelete | deleteNode
 *        new    -> openNewDialog | confirmNew | newAnalysis
 *      Signature: fn(id) -- parentId for add, nodeId for edit/delete, nothing
 *      for new. A returned promise is awaited.
 *
 * If neither exists the shell falls back to its own minimal implementation and
 * says so out loud; nothing fails silently. Two of those fallbacks are the
 * expected steady state rather than a stopgap:
 *
 *   * delete/new confirmations go through dialogs.js `confirmDialog(message,
 *     options) -> Promise<boolean>` when it exists, and window.confirm when it
 *     does not;
 *   * "edit" has no dialog because details.js edits in place, so the shell
 *     focuses the details panel and says where to type.
 *
 * FILES AND EXPORTS (P3)
 * ----------------------
 * Load / Save / Save As go through filedialog.js, which returns a *server*
 * path; the server reads and writes it, exactly as the desktop editor does.
 * Save falls through to Save As on 409 NO_CURRENT_PATH, which is what Ctrl+S
 * means on a document that has never been saved.
 *
 * The three /api/export/* endpoints are GETs that return a file, and they are
 * inside the token-guarded /api/* prefix. A plain <a href> or window.open
 * cannot carry the X-FTA-Token header (a navigation carries no custom headers)
 * and would come back 403, so downloads are fetched with the header and handed
 * to the browser as a blob URL instead. See downloadExport().
 *
 * Two buttons are gated on /api/state's `capabilities` rather than on a phase
 * flag: Excel (openpyxl) and Render (a native Graphviz). A gated button stays
 * visible and focusable and says what is missing and how to install it --
 * disappearing would leave the user believing the build never had the feature.
 *
 * THE AI PANEL (P4)
 * -----------------
 * chat.js fills #ai-root and aisettings.js owns the setup dialog. The shell
 * only wires the gear in the panel head, and answers chat.js's cancelable
 * `fta:ai-settings` event by opening that dialog -- see actionAiSettings().
 * Both AI modules translate through window.ftaShell.t, so every string they
 * show is a key in the STRINGS table below.
 *
 * OTHER WINDOW EVENTS THE SHELL HANDLES
 * -------------------------------------
 *   fta:ai-settings (cancelable)  -> open the AI setup dialog
 *   fta:error  {message, code?}   -> red toast + status line
 *   fta:toast  {message, kind?}   -> toast ('info' | 'ok' | 'warn' | 'error')
 *   fta:escape (cancelable)       -> dispatched by the shell on Escape; a modal
 *                                    should preventDefault() and close itself
 *   fta:hide-zero {hidden}        -> dispatched by the shell when the checkbox
 *                                    flips (CSS already hides .is-zero rows)
 *   fta:language  {language}      -> dispatched when EN/JA is switched
 *   fta:session-invalid           -> from api.js; raises the blocking screen
 */

import {
  api,
  ApiError,
  bootstrapToken,
  clearToken,
  getToken,
  hasToken,
  SESSION_INVALID_EVENT,
  TOKEN_HEADER,
} from './api.js';
import { store } from './store.js';

// ---------------------------------------------------------------------------
// tiny helpers
// ---------------------------------------------------------------------------

const $ = (sel) => document.querySelector(sel);
const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));

function readLocal(key, fallback = null) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : raw;
  } catch (_err) {
    return fallback;
  }
}

function writeLocal(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch (_err) {
    /* private mode: preferences just do not persist */
  }
}

// ---------------------------------------------------------------------------
// i18n
//
// Shell strings only. There is no /api/language endpoint yet, so the choice is
// client-side and per-browser; state.language keeps reporting the server's
// default until a later phase adds the route.
// ---------------------------------------------------------------------------

const STRINGS = {
  en: {
    'a11y.skip': 'Skip to the fault tree',
    'a11y.splitTree': 'Resize the fault tree panel',
    'a11y.splitAi': 'Resize the AI assistant panel',
    'a11y.splitDetails': 'Resize the node details panel',

    'bar.mode': 'Mode',
    'bar.modeTitle': 'Switching mode recalculates every probability',
    'bar.title': 'Title',
    'bar.titlePlaceholder': 'Untitled Analysis',
    'bar.date': 'Date',
    'bar.hideZero': 'Hide Zero',
    'bar.hideZeroTitle': 'Hide nodes whose calculated probability is zero',

    'action.undo': 'Undo (Ctrl+Z)',
    'action.redo': 'Redo (Ctrl+Y)',
    'action.language': 'Switch language',
    'action.theme': 'Switch theme',
    'action.aiSettings': 'AI settings',

    'panel.tree': 'Fault Tree',
    'panel.diagram': 'Live Diagram Preview',
    'panel.details': 'Node Details',
    'panel.ai': 'AI Assistant',
    'placeholder.diagram': 'The rendered fault tree will appear here once the diagram phase lands.',
    'placeholder.ai': 'Chat, "Analyze FTA" and "Update FTA" arrive with the assistant phase.',

    'phase.p2': 'Coming in P2',
    'phase.p3': 'Coming in P3',
    'phase.p4': 'Coming in P4',

    'btn.new': 'New',
    'btn.add': 'Add',
    'btn.edit': 'Edit',
    'btn.delete': 'Delete',
    'btn.load': 'Load',
    'btn.save': 'Save',
    'btn.saveAs': 'Save As',
    'btn.json': 'JSON',
    'btn.xml': 'XML',
    'btn.excel': 'Excel',
    'btn.render': 'Render',
    'tip.new': 'New analysis (Ctrl+N)',
    'tip.add': 'Add a child node (Ctrl+A)',
    'tip.edit': 'Edit the selected node (Ctrl+E)',
    'tip.delete': 'Delete the selected node (Ctrl+D)',
    'tip.load': 'Open a saved analysis from disk',
    'tip.save': 'Save to the current file (Ctrl+S)',
    'tip.saveAs': 'Save to another file (Ctrl+Shift+S)',
    'tip.json': 'Download a copy as JSON',
    'tip.xml': 'Download a copy as XML',
    'tip.excel': 'Download a copy as an Excel workbook',
    'tip.render': 'Download the diagram as a PNG image',

    'status.saved': 'Saved',
    'status.unsaved': 'Unsaved changes',
    'status.noFile': 'No file',

    'theme.system': 'Theme: follow the system',
    'theme.light': 'Theme: light',
    'theme.dark': 'Theme: dark',

    'meta.node': '1 node',
    'meta.nodes': '{n} nodes',
    'meta.selected': 'Selected: {id}',
    'meta.noSelection': 'No selection',
    'meta.dotReady': 'Graphviz ready',
    'meta.dotMissing': 'Graphviz not found',

    'msg.selectFirst': 'Select a node first.',
    'msg.rootProtected': 'The root node cannot be deleted.',
    'msg.newCreated': 'Started a new analysis.',
    'msg.deleted': 'Deleted "{name}".',
    'msg.metadataSaved': 'Metadata updated.',
    'msg.editInDetails': 'Edit the selected node in the Node Details panel.',
    'msg.notAvailable': '"{label}" is not built yet - it arrives in {phase}.',
    'msg.moduleFailed': 'The {module} panel failed to load: {error}',
    'msg.noDialog': 'The node dialog module is unavailable, so this action cannot run.',
    'msg.noFileDialog':
      'The file browser module is unavailable, so files cannot be opened or saved.',
    'msg.opened': 'Opened {path}',
    'msg.savedTo': 'Saved to {path}',
    'msg.downloading': 'Preparing {name}...',
    'msg.downloaded': 'Downloaded {name}',
    'msg.excelUnavailable':
      'Excel export is off because the openpyxl package is not installed. '
      + 'Run "pip install openpyxl" and restart the editor to turn it back on.',
    'msg.renderUnavailable':
      'PNG export needs a system Graphviz, which was not found. Install Graphviz '
      + "(graphviz.org) and restart the editor; until then the diagram panel's "
      + 'PNG button renders in the browser instead.',

    'confirm.delete': 'Delete "{name}" and everything beneath it?',
    'confirm.discard': 'Discard the unsaved changes and start a new analysis?',
    'confirm.discardOpen': 'Discard the unsaved changes and open another file?',

    'file.openTitle': 'Open Analysis',
    'file.saveTitle': 'Save Analysis As',
    'file.up': 'Up one level',
    'file.parent': 'Parent folder',
    'file.location': 'Files in this folder',
    'file.name': 'File name',
    'file.open': 'Open',
    'file.save': 'Save',
    'file.cancel': 'Cancel',
    'file.loading': 'Reading the folder...',
    'file.filter': 'Showing folders and {ext} files.',
    'file.empty': 'This folder holds no {ext} files.',
    'file.emptyAll': 'This folder is empty.',
    'file.truncated':
      'This folder holds too many entries to list; some are not shown. '
      + 'Open a more specific folder to see the rest.',
    'file.kindFolder': 'folder',
    'file.kindFile': 'file',
    'file.errList': 'That folder could not be read.',
    'file.errPickFile': 'Select a file first.',
    'file.errNameRequired': 'Type a file name.',
    'file.errNameSeparator':
      'A file name cannot contain a folder path. Browse to the folder instead.',
    'file.errExtension': 'This dialog saves {ext} files. Change the extension, or leave it off.',
    'file.errIsFolder': '"{name}" is a folder here. Choose another name.',
    'file.confirmOverwrite': '"{name}" already exists in this folder. Replace it?',
    'file.overwriteTitle': 'Replace file',
    'file.overwrite': 'Replace',

    'session.title': 'This tab has no session',
    'session.body':
      'The editor hands each tab a one-time session key in the address it was ' +
      'launched with, and that key lives only in this tab. A tab opened by hand, ' +
      'restored by the browser, or left over from an earlier run has no key, so ' +
      'the server will refuse everything it asks for.',
    'session.hint':
      'Close this tab and open the address the launcher printed in your terminal. ' +
      'If the server is no longer running, start it again:',
    'boot.title': 'The editor could not start',
    'boot.body': 'The first request to the local server failed.',

    // --- P2/P3: capability disclosure (capabilities.js) and the diagram panel.
    // These live in the catalog rather than as inline literals so the deferred
    // Japanese phase is a data change, not a hunt through the modules.
    'cap.button': 'Feature availability',
    'cap.buttonHint': 'click for details',
    'cap.title': 'Feature availability',
    'cap.foot': 'Restart the editor after installing anything, so it can be detected.',
    'cap.unknown': 'Not known yet.',
    'cap.chip.ok': 'All features available',
    'cap.chip.graphviz': 'Diagram quality limited',
    'cap.chip.excel': 'Excel export unavailable',
    'cap.chip.several': '{n} features limited',
    'cap.chip.ai': 'Set up AI',
    'cap.chip.unknown': 'Checking availability',
    'cap.state.ok': 'Available',
    'cap.state.off': 'Unavailable',
    'cap.state.ready': 'Ready',
    'cap.state.optional': 'Optional',
    'cap.state.unknown': 'Unknown',
    'cap.dot.name': 'Diagram rendering',
    'cap.dot.okState': 'System Graphviz',
    'cap.dot.badState': 'Browser renderer',
    'cap.dot.ok': 'Diagrams are drawn by the Graphviz installed on this machine, with exact font metrics and native high-resolution PNG export.',
    'cap.dot.bad': 'Diagrams are drawn in the browser. Labels in Japanese, Chinese and Korean are sized from estimated metrics rather than the real font, so their boxes may sit a little loose or tight, and PNG export is rasterised here rather than natively at 300 dpi. Everything else is identical.',
    'cap.dot.fix': 'Install Graphviz from graphviz.org and restart; the editor will use it automatically.',
    'cap.excel.name': 'Excel export',
    'cap.excel.ok': 'Analyses can be exported as .xlsx.',
    'cap.excel.bad': 'Excel export is unavailable because the openpyxl package is not installed. JSON and XML export are unaffected.',
    'cap.excel.fix': 'Install openpyxl, then restart the editor:',
    'cap.excel.cmd': 'pip install openpyxl',
    'cap.ai.name': 'AI assistant',
    'cap.ai.ok': 'A provider is configured. Chat, Analyze and Update are available.',
    'cap.ai.bad': 'No provider is configured yet, so chat and the AI actions are off. This is optional -- every other feature works without it.',
    'cap.ai.fix': 'Add a provider and API key in AI settings.',
    'diagram.zoomIn': 'Zoom in',
    'diagram.zoomOut': 'Zoom out',
    'diagram.fit': 'Fit to window',
    'diagram.exportSvg': 'Export as SVG',
    'diagram.exportPng': 'Export as PNG',
    'diagram.rendererNative': 'Rendered by system Graphviz',
    'diagram.rendererWasm': 'Rendered in-browser (Graphviz WASM)',
    'diagram.error': 'Could not render the diagram: ',
    'diagram.nothingToExport': 'Nothing to export yet.',
    'diagram.pngFailed': 'Could not rasterise the diagram to PNG.',
    'diagram.nativeFellBack': 'System Graphviz unavailable; exported from the browser renderer instead.',

    // --- P4: the AI assistant panel (chat.js) and its setup dialog
    // (aisettings.js). Every string those two modules show is here, including
    // the ones inside their markup: a literal in a module is invisible to the
    // Japanese phase, and a missing key renders as "ai.something" on screen.
    'ai.settings.title': 'Set up the AI assistant',
    'ai.settings.intro':
      'Choose a provider, paste its API key, then press Test & Save. The key is '
      + 'tried against the provider before anything is stored, and it is kept on '
      + 'this machine.',
    'ai.settings.loading': 'Loading the provider list...',
    'ai.field.provider': 'Provider',
    'ai.field.key': 'API key',
    'ai.field.model': 'Model',
    'ai.field.endpoint': 'API endpoint',
    'ai.field.advanced': 'Advanced',
    'ai.provider.openai': 'OpenAI',
    'ai.provider.anthropic': 'Anthropic Claude',
    'ai.provider.google': 'Google Gemini',
    'ai.hint.openai': 'Paid account, billed per request.',
    'ai.hint.anthropic': 'Paid account, billed per request.',
    'ai.hint.google': 'Has a free tier, so it is the quickest way to try the assistant.',
    'ai.key.where': 'Get a key at',
    'ai.key.placeholder': 'Paste the API key',
    'ai.key.show': 'Show',
    'ai.key.hide': 'Hide',
    'ai.key.saved':
      'A key is already stored ({preview}). It cannot be read back, so leave this '
      + 'blank to keep it and only fill it in to replace it.',
    'ai.key.savedNoPreview':
      'A key is already stored. It cannot be read back, so leave this blank to keep '
      + 'it and only fill it in to replace it.',
    'ai.key.savedOther': 'The stored key belongs to {provider}. Saving here replaces it.',
    'ai.model.placeholder': 'Model name',
    'ai.model.hint': 'Pick one of the suggestions, or type any model name.',
    'ai.model.needKey':
      'These are the built-in default names. Save a key to load the live list -- '
      + 'and any model name can be typed here at any time.',
    'ai.model.live': 'Loaded from the provider.',
    'ai.model.loading': 'Loading the model list...',
    'ai.model.fallback': 'Built-in defaults, not the live list: {warning}',
    'ai.model.fallbackPlain': 'Built-in defaults, not the live list.',
    'ai.model.failed': 'The model list could not be loaded: {error}',
    'ai.model.refresh': 'Reload',
    'ai.model.refreshTitle': 'Ask the provider which models the key can use',
    'ai.model.unset': 'no model',
    'ai.btn.testSave': 'Test & Save',
    'ai.btn.cancel': 'Cancel',
    'ai.btn.clear': 'Clear',
    'ai.status.testing': 'Testing the connection to {provider}...',
    'ai.status.saved': 'Connected. The assistant is ready.',
    'ai.status.clearing': 'Removing the stored credentials...',
    'ai.status.cleared': 'The stored AI credentials were removed.',
    'ai.current': 'Currently set up: {provider}, {model}.',
    'ai.confirm.clear':
      'Remove the stored API key and provider settings? Every other feature is unaffected.',
    'ai.confirm.clearTitle': 'Clear AI credentials',
    'ai.err.provider': 'Choose a provider first.',
    'ai.err.key': 'Paste the API key.',
    'ai.err.keyAgain':
      'A stored key cannot be read back, so changing these settings means pasting '
      + 'the key again. Cancel to leave the current setup untouched.',
    'ai.err.endpoint':
      'The endpoint is empty. Choose the provider again to restore its default address.',
    'ai.err.model': 'Choose or type a model name.',
    'ai.err.providers': 'The provider list could not be loaded: {error}',
    'ai.err.noProviders': 'The server offered no AI providers, so there is nothing to set up.',
    'ai.err.noSettings': 'The AI settings dialog could not be loaded, so setup cannot run.',
    'ai.endpoint.hint':
      'Filled in from the provider. Change it only for a proxy or a compatible gateway.',

    'ai.invite.title': 'Set up the AI assistant',
    'ai.invite.body':
      'The assistant is optional -- every other feature works without it. Add a '
      + 'provider and an API key, and you can ask questions about this fault tree, '
      + 'request an analysis, or have changes proposed for you to review.',
    'ai.invite.free': 'Google Gemini has a free tier, which is the quickest way to try it.',
    'ai.invite.button': 'Set up AI',

    'ai.chat.log': 'Conversation with the AI assistant',
    'ai.chat.input': 'Message to the AI assistant',
    'ai.chat.placeholder': 'Ask about this fault tree. Enter sends, Shift+Enter adds a line.',
    'ai.chat.send': 'Send',
    'ai.chat.sendTitle': 'Send the message (Enter)',
    'ai.chat.analyze': 'Analyze FTA',
    'ai.chat.analyzeTitle': 'Ask for a review of this fault tree. Nothing is changed.',
    'ai.chat.update': 'Update FTA',
    'ai.chat.updateTitle':
      'Ask for an updated fault tree. It is verified before it replaces this one.',
    'ai.chat.clear': 'Clear Chat',
    'ai.chat.clearTitle': 'Forget this conversation, here and on the server.',

    'ai.role.user': 'You',
    'ai.role.assistant': 'Assistant',
    'ai.role.system': 'Editor',
    'ai.role.error': 'Error',

    'ai.msg.welcome':
      'Ask anything about this fault tree. "Analyze FTA" reviews it without '
      + 'changing anything; "Update FTA" proposes a full replacement, which is '
      + 'verified before it is applied.',
    'ai.msg.notConfigured':
      'No provider is set up yet, so there is nothing to send. "Set up AI" adds one.',
    'ai.msg.busy': 'The assistant is still working on the previous request.',
    'ai.msg.empty': 'Type a message first.',
    'ai.msg.emptyReply': 'The assistant replied with nothing.',
    'ai.msg.thinking': 'Waiting for the assistant...',
    'ai.msg.analyzing': 'Analyzing the fault tree...',
    'ai.msg.analyzePrompt': 'Analyze this FTA and provide suggestions.',
    'ai.msg.updating': 'Generating an updated fault tree...',
    'ai.msg.updatePrompt':
      'Update this FTA with your suggestions, preserving the original JSON structure.',
    'ai.msg.updated': 'The fault tree was replaced with the verified version.',
    'ai.msg.clearing': 'Clearing the conversation...',

    'ai.changes.title': 'Suggested changes',
    'ai.changes.hint': 'All of them are ticked. Untick anything you do not want, then apply.',
    'ai.changes.apply': 'Apply selected',
    'ai.changes.dismiss': 'Dismiss',
    'ai.changes.details': 'Change data',
    'ai.changes.target': 'Target: {id}',
    'ai.changes.untitled': 'Change {n}',
    'ai.changes.none': 'Nothing is ticked, so there is nothing to apply.',
    'ai.changes.applying': 'Applying the selected changes...',
    'ai.changes.applied': 'Applied {n} of {total} suggested changes.',
    'ai.changes.dismissed': 'These suggestions were dismissed.',
    'ai.changes.superseded': 'These suggestions were replaced by a newer set.',

    'ai.diag.excerpt': 'The first 500 characters of the AI output',
    'ai.diag.raw': 'The raw response',
    'ai.diag.section': 'The part that failed verification',
    'ai.diag.keys': 'Top-level keys',
  },

  ja: {
    'a11y.skip': 'フォルトツリーへ移動',
    'a11y.splitTree': 'フォルトツリーパネルの幅を変更',
    'a11y.splitAi': 'AIアシスタントパネルの幅を変更',
    'a11y.splitDetails': 'ノード詳細パネルの高さを変更',

    'bar.mode': 'モード',
    'bar.modeTitle': 'モードを変更すると確率が再計算されます',
    'bar.title': 'タイトル',
    'bar.titlePlaceholder': '無題の解析',
    'bar.date': '日付',
    'bar.hideZero': 'ゼロを非表示',
    'bar.hideZeroTitle': '計算確率がゼロのノードを非表示にします',

    'action.undo': '元に戻す (Ctrl+Z)',
    'action.redo': 'やり直す (Ctrl+Y)',
    'action.language': '言語を切り替える',
    'action.theme': 'テーマを切り替える',
    'action.aiSettings': 'AI設定',

    'panel.tree': 'フォルトツリー',
    'panel.diagram': '図プレビュー',
    'panel.details': 'ノード詳細',
    'panel.ai': 'AIアシスタント',
    'placeholder.diagram': '図の描画フェーズが実装されるとここに表示されます。',
    'placeholder.ai': 'チャットとFTA解析・更新はアシスタントフェーズで追加されます。',

    'phase.p2': 'P2で対応',
    'phase.p3': 'P3で対応',
    'phase.p4': 'P4で対応',

    'btn.new': '新規',
    'btn.add': '追加',
    'btn.edit': '編集',
    'btn.delete': '削除',
    'btn.load': '読込',
    'btn.save': '保存',
    'btn.saveAs': '名前を付けて保存',
    'btn.json': 'JSON',
    'btn.xml': 'XML',
    'btn.excel': 'Excel',
    'btn.render': '画像',
    'tip.new': '新規解析 (Ctrl+N)',
    'tip.add': '子ノードを追加 (Ctrl+A)',
    'tip.edit': '選択中のノードを編集 (Ctrl+E)',
    'tip.delete': '選択中のノードを削除 (Ctrl+D)',
    'tip.load': '保存済みの解析を開く',
    'tip.save': '現在のファイルに保存 (Ctrl+S)',
    'tip.saveAs': '別のファイルに保存 (Ctrl+Shift+S)',
    'tip.json': 'JSON形式でダウンロード',
    'tip.xml': 'XML形式でダウンロード',
    'tip.excel': 'Excelブックとしてダウンロード',
    'tip.render': '図をPNG画像としてダウンロード',

    'status.saved': '保存済み',
    'status.unsaved': '未保存の変更',
    'status.noFile': 'ファイルなし',

    'theme.system': 'テーマ: システムに従う',
    'theme.light': 'テーマ: ライト',
    'theme.dark': 'テーマ: ダーク',

    'meta.node': '1 ノード',
    'meta.nodes': '{n} ノード',
    'meta.selected': '選択中: {id}',
    'meta.noSelection': '未選択',
    'meta.dotReady': 'Graphviz 利用可能',
    'meta.dotMissing': 'Graphviz が見つかりません',

    'msg.selectFirst': '先にノードを選択してください。',
    'msg.rootProtected': 'ルートノードは削除できません。',
    'msg.newCreated': '新しい解析を開始しました。',
    'msg.deleted': '「{name}」を削除しました。',
    'msg.metadataSaved': 'メタデータを更新しました。',
    'msg.editInDetails': 'ノード詳細パネルで編集してください。',
    'msg.notAvailable': '「{label}」は未実装です（{phase}）。',
    'msg.moduleFailed': '{module} パネルの読み込みに失敗しました: {error}',
    'msg.noDialog': 'ダイアログモジュールが利用できないため実行できません。',
    'msg.noFileDialog':
      'ファイルブラウザモジュールが利用できないため、ファイルを開く・保存する操作は実行できません。',
    'msg.opened': '{path} を開きました',
    'msg.savedTo': '{path} に保存しました',
    'msg.downloading': '{name} を準備しています...',
    'msg.downloaded': '{name} をダウンロードしました',
    'msg.excelUnavailable':
      'openpyxl パッケージが見つからないため Excel 出力は無効です。'
      + '「pip install openpyxl」を実行してエディタを再起動すると有効になります。',
    'msg.renderUnavailable':
      'PNG 出力にはシステムの Graphviz が必要ですが、見つかりませんでした。'
      + 'Graphviz (graphviz.org) をインストールしてエディタを再起動してください。'
      + 'それまでは図パネルの PNG ボタンがブラウザ内で書き出します。',

    'confirm.delete': '「{name}」と配下のノードを削除しますか？',
    'confirm.discard': '未保存の変更を破棄して新規作成しますか？',
    'confirm.discardOpen': '未保存の変更を破棄して別のファイルを開きますか？',

    'file.openTitle': '解析を開く',
    'file.saveTitle': '名前を付けて保存',
    'file.up': '上の階層へ',
    'file.parent': '親フォルダー',
    'file.location': 'このフォルダー内のファイル',
    'file.name': 'ファイル名',
    'file.open': '開く',
    'file.save': '保存',
    'file.cancel': 'キャンセル',
    'file.loading': 'フォルダーを読み込んでいます...',
    'file.filter': 'フォルダーと {ext} ファイルを表示しています。',
    'file.empty': 'このフォルダーに {ext} ファイルはありません。',
    'file.emptyAll': 'このフォルダーは空です。',
    'file.truncated':
      'このフォルダーには項目が多すぎるため、一部は表示されていません。'
      + 'より下の階層のフォルダーを開いてください。',
    'file.kindFolder': 'フォルダー',
    'file.kindFile': 'ファイル',
    'file.errList': 'そのフォルダーを読み取れませんでした。',
    'file.errPickFile': '先にファイルを選択してください。',
    'file.errNameRequired': 'ファイル名を入力してください。',
    'file.errNameSeparator':
      'ファイル名にフォルダーのパスは含められません。フォルダーを移動してください。',
    'file.errExtension': 'このダイアログで保存できるのは {ext} ファイルです。拡張子を変更するか省略してください。',
    'file.errIsFolder': '「{name}」はこの場所にあるフォルダーです。別の名前を指定してください。',
    'file.confirmOverwrite': '「{name}」は既にこのフォルダーにあります。置き換えますか？',
    'file.overwriteTitle': 'ファイルを置き換える',
    'file.overwrite': '置き換える',

    'session.title': 'このタブにはセッションがありません',
    'session.body':
      'エディタは起動時のアドレスに含まれる一度きりのセッションキーを各タブに渡します。' +
      'キーはそのタブ内にのみ保存されるため、手動で開いたタブや復元されたタブにはキーがなく、' +
      'サーバーはすべての要求を拒否します。',
    'session.hint':
      'このタブを閉じ、ターミナルに表示されたアドレスを開いてください。' +
      'サーバーが停止している場合は再起動してください:',
    'boot.title': 'エディタを起動できませんでした',
    'boot.body': 'ローカルサーバーへの最初の要求が失敗しました。',
  },
};

let language = readLocal('fta.language') === 'ja' ? 'ja' : 'en';

function t(key, vars) {
  const table = STRINGS[language] || STRINGS.en;
  let text = table[key];
  if (text === undefined) text = STRINGS.en[key];
  if (text === undefined) return key;
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (whole, name) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : whole
  );
}

function applyLanguage() {
  document.documentElement.lang = language;
  for (const el of document.querySelectorAll('[data-i18n]')) {
    el.textContent = t(el.dataset.i18n);
  }
  for (const el of document.querySelectorAll('[data-i18n-title]')) {
    el.title = t(el.dataset.i18nTitle);
  }
  for (const el of document.querySelectorAll('[data-i18n-aria]')) {
    el.setAttribute('aria-label', t(el.dataset.i18nAria));
  }
  for (const el of document.querySelectorAll('[data-i18n-placeholder]')) {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  }
  const code = $('#lang-code');
  if (code) code.textContent = language.toUpperCase();
  applyThemeLabel();
  if (store.state) renderShell(store.state);
}

function setLanguage(next) {
  language = next === 'ja' ? 'ja' : 'en';
  writeLocal('fta.language', language);
  applyLanguage();
  window.dispatchEvent(new CustomEvent('fta:language', { detail: { language } }));
}

// ---------------------------------------------------------------------------
// theme: system -> light -> dark -> system
// ---------------------------------------------------------------------------

const THEME_ORDER = ['system', 'light', 'dark'];
const THEME_GLYPH = { system: '◐', light: '☀', dark: '☾' };
let theme = ['light', 'dark'].includes(readLocal('fta.theme')) ? readLocal('fta.theme') : 'system';

function applyTheme() {
  if (theme === 'system') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', theme);
  writeLocal('fta.theme', theme);
  applyThemeLabel();
}

function applyThemeLabel() {
  const glyph = $('#theme-glyph');
  const button = $('#btn-theme');
  if (glyph) glyph.textContent = THEME_GLYPH[theme];
  if (button) {
    const label = t('theme.' + theme);
    button.setAttribute('aria-label', label);
    button.title = label;
  }
}

function cycleTheme() {
  theme = THEME_ORDER[(THEME_ORDER.indexOf(theme) + 1) % THEME_ORDER.length];
  applyTheme();
}

// ---------------------------------------------------------------------------
// layout: grid sizes persisted per browser
// ---------------------------------------------------------------------------

const LAYOUT_KEY = 'fta.layout';
const PANES = {
  tree: { cssVar: '--tree-w', def: 320, min: 200, max: 760, axis: 'x' },
  ai: { cssVar: '--ai-w', def: 340, min: 240, max: 760, axis: 'x' },
  details: { cssVar: '--details-h', def: 260, min: 140, max: 720, axis: 'y' },
};

let layout = { tree: PANES.tree.def, ai: PANES.ai.def, details: PANES.details.def };

function loadLayout() {
  const raw = readLocal(LAYOUT_KEY);
  if (!raw) return;
  try {
    const saved = JSON.parse(raw);
    for (const key of Object.keys(PANES)) {
      const value = Number(saved && saved[key]);
      if (Number.isFinite(value)) {
        layout[key] = clamp(Math.round(value), PANES[key].min, PANES[key].max);
      }
    }
  } catch (_err) {
    /* corrupt entry: keep the defaults */
  }
}

function applyLayout() {
  const workspace = $('#workspace');
  if (!workspace) return;
  for (const [key, pane] of Object.entries(PANES)) {
    workspace.style.setProperty(pane.cssVar, layout[key] + 'px');
  }
  for (const el of document.querySelectorAll('[data-splitter]')) {
    const pane = PANES[el.dataset.splitter];
    if (!pane) continue;
    el.setAttribute('aria-valuenow', String(layout[el.dataset.splitter]));
    el.setAttribute('aria-valuemin', String(pane.min));
    el.setAttribute('aria-valuemax', String(pane.max));
  }
}

function setPane(key, px) {
  const pane = PANES[key];
  if (!pane || !Number.isFinite(px)) return;
  layout[key] = clamp(Math.round(px), pane.min, pane.max);
  applyLayout();
  writeLocal(LAYOUT_KEY, JSON.stringify(layout));
}

function measurePane(key, event) {
  if (key === 'tree') {
    const rect = $('#tree-panel').getBoundingClientRect();
    return event.clientX - rect.left;
  }
  if (key === 'ai') {
    const rect = $('#ai-panel').getBoundingClientRect();
    return rect.right - event.clientX;
  }
  const rect = $('#details-panel').getBoundingClientRect();
  return rect.bottom - event.clientY;
}

function initSplitters() {
  for (const el of document.querySelectorAll('[data-splitter]')) {
    const key = el.dataset.splitter;
    const pane = PANES[key];
    if (!pane) continue;

    el.addEventListener('pointerdown', (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      const axisClass = pane.axis === 'x' ? 'is-resizing--v' : 'is-resizing--h';
      el.classList.add('is-dragging');
      document.body.classList.add('is-resizing', axisClass);
      try {
        el.setPointerCapture(event.pointerId);
      } catch (_err) {
        /* capture is an optimisation, not a requirement */
      }

      const onMove = (ev) => setPane(key, measurePane(key, ev));
      const onStop = () => {
        el.removeEventListener('pointermove', onMove);
        el.removeEventListener('pointerup', onStop);
        el.removeEventListener('pointercancel', onStop);
        el.classList.remove('is-dragging');
        document.body.classList.remove('is-resizing', axisClass);
      };
      el.addEventListener('pointermove', onMove);
      el.addEventListener('pointerup', onStop);
      el.addEventListener('pointercancel', onStop);
    });

    // Keyboard resizing: a splitter you can only drag is not usable without a
    // mouse, and role="separator" promises arrow-key behaviour.
    el.addEventListener('keydown', (event) => {
      const step = event.shiftKey ? 48 : 16;
      let delta = 0;
      if (pane.axis === 'x') {
        if (event.key === 'ArrowLeft') delta = key === 'ai' ? step : -step;
        else if (event.key === 'ArrowRight') delta = key === 'ai' ? -step : step;
      } else {
        if (event.key === 'ArrowUp') delta = step;
        else if (event.key === 'ArrowDown') delta = -step;
      }
      if (event.key === 'Home' || event.key === 'End') {
        event.preventDefault();
        setPane(key, event.key === 'Home' ? pane.min : pane.max);
        return;
      }
      if (!delta) return;
      event.preventDefault();
      setPane(key, layout[key] + delta);
    });

    el.addEventListener('dblclick', () => setPane(key, pane.def));
  }
}

// ---------------------------------------------------------------------------
// visible feedback: toasts + status line
// ---------------------------------------------------------------------------

const TOAST_MS = { info: 5000, ok: 4000, warn: 8000, error: 10000 };

function setStatus(message, kind = 'info') {
  const el = $('#statusline-msg');
  if (!el) return;
  el.textContent = message || '';
  el.dataset.kind = kind;
}

function toast(message, kind = 'info', code = null) {
  setStatus(message, kind);
  const host = $('#toasts');
  if (!host) return;

  const node = document.createElement('div');
  node.className = 'toast toast--' + kind;

  const body = document.createElement('div');
  body.className = 'toast__body';
  body.textContent = message;
  if (code) {
    const tag = document.createElement('span');
    tag.className = 'toast__code';
    tag.textContent = code;
    body.appendChild(document.createElement('br'));
    body.appendChild(tag);
  }

  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'toast__close';
  close.setAttribute('aria-label', 'Dismiss');
  close.textContent = '×';
  close.addEventListener('click', () => node.remove());

  node.append(body, close);
  host.appendChild(node);

  const timer = window.setTimeout(() => node.remove(), TOAST_MS[kind] || 6000);
  node.addEventListener('mouseenter', () => window.clearTimeout(timer));
  while (host.children.length > 4) host.firstElementChild.remove();
}

/**
 * The single funnel for anything that went wrong. Every catch block in this
 * file ends here; nothing is logged and left invisible.
 */
function showError(err) {
  // eslint-disable-next-line no-console
  console.error('[fta]', err);
  if (err instanceof ApiError) {
    toast(err.message, 'error', err.code);
    return;
  }
  toast(err && err.message ? err.message : String(err), 'error');
}

function dismissTopToast() {
  const host = $('#toasts');
  const last = host && host.lastElementChild;
  if (last) last.remove();
}

// ---------------------------------------------------------------------------
// the blocking screen (bootstrap problem #2)
// ---------------------------------------------------------------------------

let sessionLost = false;

function showBlockingScreen(title, body, hint) {
  const overlay = $('#blocking-overlay');
  if (!overlay) return;
  if (title) $('#overlay-title').textContent = title;
  if (body) {
    const el = overlay.querySelector('#overlay-body p');
    if (el) el.textContent = body;
  }
  if (hint) {
    const paras = overlay.querySelectorAll('#overlay-body p');
    if (paras[1]) paras[1].textContent = hint;
  }
  overlay.hidden = false;
  const card = overlay.querySelector('.overlay__card');
  if (card) {
    card.tabIndex = -1;
    card.focus();
  }
}

/**
 * A tab with no token, or a 403 from a token the server no longer accepts.
 * One screen, once -- not a wall of failed requests.
 */
function onSessionInvalid() {
  if (sessionLost) return;
  sessionLost = true;
  showBlockingScreen(t('session.title'), t('session.body'), t('session.hint'));
}

// ---------------------------------------------------------------------------
// sibling modules
// ---------------------------------------------------------------------------

const modules = { tree: null, details: null, dialogs: null, filedialog: null, aisettings: null };

function renderModuleFallback(host, name, err) {
  if (!host) return;
  host.innerHTML = '';
  const box = document.createElement('div');
  box.className = 'placeholder';
  const glyph = document.createElement('span');
  glyph.className = 'placeholder__glyph';
  glyph.setAttribute('aria-hidden', 'true');
  glyph.textContent = '⚠';
  const title = document.createElement('p');
  title.className = 'placeholder__title';
  title.textContent = name;
  const note = document.createElement('p');
  note.className = 'placeholder__note';
  note.textContent = t('msg.moduleFailed', {
    module: name,
    error: err && err.message ? err.message : String(err),
  });
  box.append(glyph, title, note);
  host.appendChild(box);
}

async function loadPanels() {
  const specs = [
    ['tree', './tree.js'],
    ['details', './details.js'],
    ['dialogs', './dialogs.js'],
    ['filedialog', './filedialog.js'],
    ['diagram', './diagram.js'],
    ['capabilities', './capabilities.js'],
    ['chat', './chat.js'],
    ['aisettings', './aisettings.js'],
  ];
  await Promise.all(
    specs.map(async ([name, spec]) => {
      try {
        modules[name] = await import(spec);
      } catch (err) {
        modules[name] = null;
        // dialogs.js and filedialog.js have no panel of their own; their
        // absence shows up when an action needs them, so do not shout here.
        if (name === 'tree') renderModuleFallback($('#tree-root'), t('panel.tree'), err);
        if (name === 'details') renderModuleFallback($('#details-root'), t('panel.details'), err);
        if (name === 'diagram') renderModuleFallback($('#diagram-root'), t('panel.diagram'), err);
        if (name === 'chat') renderModuleFallback($('#ai-root'), t('panel.ai'), err);
        // eslint-disable-next-line no-console
        console.error('[fta] could not load ' + spec, err);
      }
    })
  );

  callInit(modules.tree, ['initTree', 'init', 'default'], $('#tree-root'), t('panel.tree'));
  callInit(modules.details, ['initDetails', 'init', 'default'], $('#details-root'), t('panel.details'));
  callInit(modules.diagram, ['initDiagram', 'init', 'default'], $('#diagram-root'), t('panel.diagram'));
  callInit(modules.capabilities, ['initCapabilities', 'init', 'default'], $('#capabilities-host'), 'capabilities', true);
  callInit(modules.chat, ['initChat', 'init', 'default'], $('#ai-root'), t('panel.ai'));
  // aisettings.js has no panel of its own; like dialogs.js and filedialog.js
  // its absence shows up when the gear is pressed, so nothing is said here.
  if (modules.dialogs) {
    callInit(modules.dialogs, ['initDialogs', 'init'], document.body, 'dialogs', true);
  }
}

function callInit(module, names, host, label, optional = false) {
  if (!module) return;
  for (const name of names) {
    if (typeof module[name] === 'function') {
      try {
        module[name](host);
      } catch (err) {
        if (optional) showError(err);
        else renderModuleFallback(host, label, err);
      }
      return;
    }
  }
  if (!optional) {
    renderModuleFallback(host, label, new Error('no init export found'));
  }
}

const DIALOG_ENTRY_POINTS = {
  add: ['openAddDialog', 'openAddNodeDialog', 'addNode', 'showAddDialog'],
  edit: ['openEditDialog', 'openEditNodeDialog', 'editNode', 'showEditDialog'],
  delete: ['openDeleteDialog', 'confirmDelete', 'deleteNode'],
  new: ['openNewDialog', 'confirmNew', 'newAnalysis'],
};

function dialogFn(kind) {
  const module = modules.dialogs;
  if (!module) return null;
  for (const name of DIALOG_ENTRY_POINTS[kind] || []) {
    if (typeof module[name] === 'function') return module[name];
  }
  return null;
}

/** @returns {boolean} true when another module claimed the action. */
function dispatchAction(action, detail = {}) {
  const event = new CustomEvent('fta:action', {
    detail: { action, ...detail },
    cancelable: true,
  });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}

// ---------------------------------------------------------------------------
// metadata bar
// ---------------------------------------------------------------------------

function metadataFromInputs() {
  return {
    title: $('#title-input').value,
    date: $('#date-input').value.trim(),
    mode: $('#mode-select').value,
  };
}

function syncMetadataInputs(force = false) {
  const meta = store.metadata();
  const fields = [
    ['#title-input', meta.title == null ? '' : String(meta.title)],
    ['#date-input', meta.date == null ? '' : String(meta.date)],
    ['#mode-select', meta.mode === 'ETA' ? 'ETA' : 'FTA'],
  ];
  for (const [sel, value] of fields) {
    const el = $(sel);
    if (!el) continue;
    // Never yank a field out from under someone who is typing in it.
    if (!force && el === document.activeElement) continue;
    if (el.value !== value) el.value = value;
  }
}

function metadataChanged() {
  const meta = store.metadata();
  const now = metadataFromInputs();
  return (
    String(meta.title == null ? '' : meta.title) !== now.title ||
    String(meta.date == null ? '' : meta.date) !== now.date ||
    String(meta.mode || 'FTA') !== now.mode
  );
}

/**
 * All three fields go on every call, always.
 *
 * FTACore.set_metadata() rewrites `date` to today whenever it is handed None
 * alongside another field (desktop behaviour, kept deliberately in the
 * backend). Posting {"mode": "ETA"} on its own would therefore silently
 * overwrite the document's date. Sending the current title and date back with
 * every change makes that impossible.
 */
async function commitMetadata() {
  if (!store.state || sessionLost) return;
  if (!metadataChanged()) return;
  try {
    const result = await api.post('/metadata', metadataFromInputs());
    store.applyMutation(result);
    syncMetadataInputs(true); // the server sanitizes the title; show the truth
    toast(t('msg.metadataSaved'), 'ok');
  } catch (err) {
    showError(err);
    syncMetadataInputs(true); // roll the inputs back to the server's version
  }
}

/**
 * The metadata POST currently in flight, so a save can wait for it.
 * commitMetadata() handles its own errors and never rejects, so nothing here
 * needs a catch.
 */
let metadataPending = null;

function queueMetadata() {
  metadataPending = commitMetadata();
  return metadataPending;
}

/**
 * Push whatever the user is typing to the server before writing a file.
 *
 * Ctrl+S with the caret still in the Title box must save the title that is on
 * screen. Blurring fires the field's own `change` handler -- commitMetadata
 * here, and details.js's PATCH for a node field -- and then we wait for the
 * metadata round trip. details.js's own commit is not awaitable from here, so a
 * node edit saved in the same keystroke can land just after the write; that
 * shows up honestly as the dirty badge coming back, never as a silent loss.
 */
async function flushPendingEdits() {
  const active = document.activeElement;
  if (active && isTextEntry(active) && typeof active.blur === 'function') {
    active.blur();
  }
  if (metadataPending) await metadataPending;
}

// ---------------------------------------------------------------------------
// actions
// ---------------------------------------------------------------------------

function rootId() {
  const root = store.tree();
  return root ? String(root.id) : 'root';
}

/**
 * Yes/no, through dialogs.js when it offers `confirmDialog(message, options)`
 * (documented there as resolving true/false) and through window.confirm when
 * it does not.
 */
async function askConfirm(message, options) {
  const dialogs = modules.dialogs;
  if (dialogs && typeof dialogs.confirmDialog === 'function') {
    try {
      return Boolean(await dialogs.confirmDialog(message, options));
    } catch (err) {
      showError(err);
      return false;
    }
  }
  return window.confirm(message);
}

function confirmDiscard(message) {
  const fn = dialogFn('new');
  if (fn) return fn();
  return askConfirm(message || t('confirm.discard'));
}

async function actionNew() {
  if (dispatchAction('new')) return;
  try {
    const result = await api.post('/new', {});
    store.applyMutation(result);
    store.select(rootId());
    toast(t('msg.newCreated'), 'ok');
  } catch (err) {
    if (err instanceof ApiError && err.code === 'UNSAVED_CHANGES') {
      // The backend refuses to discard unsaved work unless forced (409).
      const proceed = await confirmDiscard(t('confirm.discard'));
      if (!proceed) return;
      try {
        const forced = await api.post('/new', { force: true });
        store.applyMutation(forced);
        store.select(rootId());
        toast(t('msg.newCreated'), 'ok');
      } catch (retryErr) {
        showError(retryErr);
      }
      return;
    }
    showError(err);
  }
}

async function actionAdd() {
  const parentId = store.selectedId || rootId();
  if (dispatchAction('add', { parentId })) return;
  const fn = dialogFn('add');
  if (fn) {
    try {
      await fn(parentId);
    } catch (err) {
      showError(err);
    }
    return;
  }
  toast(t('msg.noDialog'), 'error', 'NO_DIALOG');
}

async function actionEdit() {
  const nodeId = store.selectedId;
  if (!nodeId) {
    toast(t('msg.selectFirst'), 'warn');
    return;
  }
  if (dispatchAction('edit', { nodeId })) return;
  const fn = dialogFn('edit');
  if (fn) {
    try {
      await fn(nodeId);
    } catch (err) {
      showError(err);
    }
    return;
  }
  // details.js edits in place, so this is a pointer rather than a failure.
  const host = $('#details-root');
  if (host) {
    host.focus();
    host.scrollIntoView({ block: 'nearest' });
  }
  toast(t('msg.editInDetails'), 'info');
}

async function actionDelete() {
  const nodeId = store.selectedId;
  if (!nodeId) {
    toast(t('msg.selectFirst'), 'warn');
    return;
  }
  if (nodeId === rootId()) {
    toast(t('msg.rootProtected'), 'warn', 'ROOT_PROTECTED');
    return;
  }
  if (dispatchAction('delete', { nodeId })) return;

  const fn = dialogFn('delete');
  if (fn) {
    try {
      await fn(nodeId);
    } catch (err) {
      showError(err);
    }
    return;
  }

  const node = store.findNode(nodeId);
  const name = (node && node.name) || nodeId;
  const proceed = await askConfirm(t('confirm.delete', { name }), {
    title: t('btn.delete'),
    okLabel: t('btn.delete'),
    danger: true,
  });
  if (!proceed) return;

  const parentId = store.parentIdOf(nodeId) || rootId();
  try {
    const result = await api.del('/nodes/' + encodeURIComponent(nodeId));
    store.applyMutation(result);
    store.select(parentId);
    toast(t('msg.deleted', { name }), 'ok');
  } catch (err) {
    showError(err);
  }
}

async function actionHistory(kind) {
  try {
    const result = await api.post('/' + kind, {});
    store.applyMutation(result);
    syncMetadataInputs(true); // undo/redo can move the title, date and mode
  } catch (err) {
    // "nothing to undo" is a fact about the document, not a malfunction.
    if (err instanceof ApiError && (err.code === 'NOTHING_TO_UNDO' || err.code === 'NOTHING_TO_REDO')) {
      toast(err.message, 'info', err.code);
      return;
    }
    showError(err);
  }
}

// ---------------------------------------------------------------------------
// files and exports
//
// Paths here are always SERVER paths: filedialog.js browses /api/fs/* and hands
// back an absolute path, and the server does the reading and writing. Nothing
// in this section touches the user's disk from the browser.
// ---------------------------------------------------------------------------

/**
 * Path helpers, deliberately duplicated from filedialog.js rather than
 * imported: a static import of that module would take the whole shell down with
 * it if it ever failed to parse, which is the exact failure the dynamic import
 * in loadPanels() exists to contain.
 */
function pathBaseName(path) {
  const parts = String(path == null ? '' : path).split(/[\\/]/).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : '';
}

function pathDirName(path) {
  const text = String(path == null ? '' : path).replace(/[\\/]+$/, '');
  const cut = Math.max(text.lastIndexOf('/'), text.lastIndexOf('\\'));
  if (cut < 0) return null;
  return cut === 0 ? text.slice(0, 1) : text.slice(0, cut);
}

/**
 * A file-name stem for a download: the open file's name when there is one, the
 * document title otherwise. Characters Windows forbids in a name are replaced
 * rather than dropped, so two distinct titles cannot collapse into one name.
 */
function documentStem() {
  const current = store.state && store.state.currentPath;
  if (current) {
    const name = pathBaseName(current);
    const dot = name.lastIndexOf('.');
    return dot > 0 ? name.slice(0, dot) : name;
  }
  const title = String(store.metadata().title || '').trim();
  const stem = title
    .replace(/[<>:"/\\|?*\x00-\x1f]/g, '_')
    .replace(/\s+/g, ' ')
    .trim();
  return stem || 'fta_analysis';
}

function exportFilename(extension) {
  return documentStem() + '.' + extension;
}

/** Ask filedialog.js for a path. Resolves null when cancelled or unavailable. */
async function pickPath(mode) {
  const module = modules.filedialog;
  const open = module && (module.openFileDialog || module.default);
  if (typeof open !== 'function') {
    toast(t('msg.noFileDialog'), 'error', 'NO_FILE_DIALOG');
    return null;
  }
  const current = (store.state && store.state.currentPath) || '';
  try {
    const chosen = await open({
      mode,
      startDir: current ? pathDirName(current) : null,
      filename:
        mode === 'save'
          ? current
            ? pathBaseName(current)
            : exportFilename('json')
          : null,
      extensions: ['.json'],
    });
    return chosen || null;
  } catch (err) {
    showError(err);
    return null;
  }
}

/**
 * Install the payload from POST /api/file/open (or a later /api/import/json).
 *
 * That payload is the *document* view -- tree, metadata, zeroNodes,
 * currentPath, dirty, canUndo, canRedo (routes/files.py::_document_payload) --
 * and deliberately not the per-launch session facts /api/state also carries
 * (capabilities, language, nativeDot, aiConfigured). Those cannot change by
 * opening a file, so it is merged over the state already held rather than
 * replacing it: a plain setState would blank `capabilities` and take the Excel
 * button's explanation with it.
 *
 * If a document key is missing the merge would keep the *previous* document's
 * value for it -- a stale dirty badge, or an undo button that lies -- so that
 * case takes one extra /api/state read instead of guessing.
 */
const DOCUMENT_KEYS = ['tree', 'metadata', 'zeroNodes', 'currentPath', 'dirty', 'canUndo', 'canRedo'];

async function adoptDocument(payload) {
  const complete =
    Boolean(payload) &&
    DOCUMENT_KEYS.every((key) => Object.prototype.hasOwnProperty.call(payload, key));

  store.setState({ ...(store.state || {}), ...(payload || {}) });
  store.select(rootId());
  syncMetadataInputs(true);
  if (complete) return;

  try {
    store.setState(await api.get('/state'));
    store.select(rootId());
    syncMetadataInputs(true);
  } catch (err) {
    showError(err);
  }
}

async function actionLoad() {
  // The backend has no unsaved-changes guard on open (only /new has one), so
  // the guard lives here -- ask before the picker, not after, so a user who
  // meant to save first has not already picked a file.
  if (store.state && store.state.dirty) {
    const proceed = await askConfirm(t('confirm.discardOpen'), {
      title: t('btn.load'),
      confirmLabel: t('btn.load'),
    });
    if (!proceed) return;
  }

  const path = await pickPath('open');
  if (!path) return;

  try {
    const payload = await api.post('/file/open', { path });
    await adoptDocument(payload);
    toast(t('msg.opened', { path: (store.state && store.state.currentPath) || path }), 'ok');
  } catch (err) {
    showError(err);
  }
}

async function actionSave() {
  await flushPendingEdits();
  try {
    const result = await api.post('/file/save', {});
    store.applyMutation(result);
    const path = result.currentPath || (store.state && store.state.currentPath) || '';
    toast(t('msg.savedTo', { path }), 'ok');
  } catch (err) {
    // 409 NO_CURRENT_PATH is not a failure: this document has never been
    // written, so Save means Save As. That is the desktop's Ctrl+S.
    if (err instanceof ApiError && err.code === 'NO_CURRENT_PATH') {
      await actionSaveAs();
      return;
    }
    showError(err);
  }
}

async function actionSaveAs() {
  await flushPendingEdits();
  const path = await pickPath('save');
  if (!path) return;
  try {
    const result = await api.post('/file/save-as', { path });
    store.applyMutation(result);
    toast(t('msg.savedTo', { path: result.currentPath || path }), 'ok');
  } catch (err) {
    showError(err);
  }
}

// ---- downloads ------------------------------------------------------------

const EXPORTS = {
  json: { url: '/api/export/json', extension: 'json' },
  xml: { url: '/api/export/xml', extension: 'xml' },
  xlsx: { url: '/api/export/xlsx', extension: 'xlsx' },
};

/** The name the server suggested, if any. Never a path -- see the strip below. */
function filenameFromDisposition(header) {
  if (!header) return null;
  const encoded = /filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i.exec(header);
  if (encoded) {
    try {
      return pathBaseName(decodeURIComponent(encoded[1].trim().replace(/^"|"$/g, '')));
    } catch (_err) {
      /* fall through to the plain form */
    }
  }
  const plain = /filename\s*=\s*"?([^";]+)"?/i.exec(header);
  // pathBaseName strips any directory the header tried to smuggle in: the
  // download name must never be able to steer where the browser writes.
  return plain ? pathBaseName(plain[1].trim()) : null;
}

/**
 * GET an /api/* URL that answers with a file rather than JSON.
 *
 * api.js cannot be used: it parses every response as JSON, which would corrupt
 * an .xlsx. And a plain <a href> / window.open cannot be used either, because a
 * navigation carries no custom headers and the export endpoints sit behind the
 * X-FTA-Token guard -- the link would 403 and the browser would save the error
 * page. So the request is a fetch with the header, and the bytes are handed to
 * the browser as a blob.
 */
async function fetchDownload(url) {
  const token = getToken();
  if (!token) {
    onSessionInvalid();
    throw new ApiError('NO_SESSION', t('session.title'), { reason: 'no_token' });
  }

  const headers = {};
  headers[TOKEN_HEADER] = token;

  let response;
  try {
    response = await fetch(url, {
      method: 'GET',
      headers,
      cache: 'no-store',
      credentials: 'same-origin',
      redirect: 'follow',
    });
  } catch (cause) {
    throw new ApiError(
      'NETWORK_ERROR',
      'Could not reach the editor server. It may have been stopped in the terminal.',
      { url, cause: String((cause && cause.message) || cause) }
    );
  }

  const contentType = (response.headers.get('Content-Type') || '').toLowerCase();
  const isJson = contentType.indexOf('json') !== -1;

  // A failure comes back as the standard envelope; so, in principle, could a
  // 200 carrying {"ok": false}. Both are checked, because writing an error
  // envelope to disk under the name "analysis.xlsx" is the worst outcome here.
  if (!response.ok || isJson) {
    const text = await response.text().catch(() => '');
    let payload = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch (_err) {
        payload = null;
      }
    }
    const failed =
      !response.ok || (payload && typeof payload === 'object' && payload.ok === false);
    if (failed) {
      const envelope =
        payload && payload.error && typeof payload.error === 'object' ? payload.error : {};
      if (response.status === 403) {
        clearToken();
        window.dispatchEvent(
          new CustomEvent(SESSION_INVALID_EVENT, {
            detail: { reason: (envelope.detail && envelope.detail.reason) || 'forbidden' },
          })
        );
      }
      throw new ApiError(
        envelope.code || 'HTTP_' + response.status,
        envelope.message || 'The export failed (HTTP ' + response.status + ').',
        envelope.detail || null,
        response.status
      );
    }
    // A successful JSON body is the JSON export itself. Rebuild the blob from
    // the text already read rather than re-reading a consumed body.
    return {
      blob: new Blob([text], { type: contentType || 'application/json' }),
      filename: filenameFromDisposition(response.headers.get('Content-Disposition')),
    };
  }

  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get('Content-Disposition')),
  };
}

/** Hand a blob to the browser as a download. */
function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.rel = 'noopener';
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Revoked late: Firefox cancels an in-flight download when the object URL
  // goes away in the same tick as the click.
  window.setTimeout(() => URL.revokeObjectURL(url), 10000);
}

async function actionExport(kind) {
  const spec = EXPORTS[kind];
  if (!spec) return;
  // Export what is on screen: a title still sitting uncommitted in its input
  // would otherwise be missing from the file.
  await flushPendingEdits();

  const fallbackName = exportFilename(spec.extension);
  setStatus(t('msg.downloading', { name: fallbackName }), 'info');
  try {
    const result = await fetchDownload(spec.url);
    const name = result.filename || fallbackName;
    saveBlob(result.blob, name);
    toast(t('msg.downloaded', { name }), 'ok');
  } catch (err) {
    showError(err);
  }
}

/** base64 -> bytes, for the image POST /api/render answers with. */
function base64ToBytes(data) {
  const binary = atob(String(data || ''));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/**
 * Render the diagram to a PNG file, the desktop editor's "Render" button.
 *
 * This is the native-Graphviz path (300 dpi). Without a system `dot` the button
 * is gated off by applyCapabilityGates() and the message points at the diagram
 * panel's own PNG button, which rasterises what the in-browser renderer drew --
 * a different engine, so it is named rather than silently substituted.
 */
async function actionRenderImage() {
  const name = exportFilename('png');
  setStatus(t('msg.downloading', { name }), 'info');
  try {
    const result = await api.post('/render', {
      format: 'png',
      hideZero: document.documentElement.dataset.hideZero === '1',
      highQuality: true,
    });
    saveBlob(
      new Blob([base64ToBytes(result.data)], { type: result.contentType || 'image/png' }),
      name
    );
    toast(t('msg.downloaded', { name }), 'ok');
  } catch (err) {
    if (err instanceof ApiError && err.code === 'RENDERER_UNAVAILABLE') {
      toast(t('msg.renderUnavailable'), 'warn', err.code);
      return;
    }
    showError(err);
  }
}

// ---------------------------------------------------------------------------
// the AI assistant
//
// The gear in the AI panel head and the "Set up AI" button inside chat.js open
// the same dialog. chat.js asks for it with a cancelable `fta:ai-settings`
// event rather than importing aisettings.js, so a broken settings module costs
// one visible message instead of taking the whole chat panel down with it --
// the same reason the panels themselves are loaded with dynamic import().
//
// Nothing is done with the result here: saving or clearing re-reads /api/state
// from inside the dialog, and the store notifies the panel, the status dot and
// the capability chip together.
// ---------------------------------------------------------------------------

async function actionAiSettings() {
  const module = modules.aisettings;
  const open = module && (module.openAiSettings || module.default);
  if (typeof open !== 'function') {
    toast(t('ai.err.noSettings'), 'error', 'NO_AI_SETTINGS');
    return;
  }
  try {
    await open();
  } catch (err) {
    showError(err);
  }
}

// ---------------------------------------------------------------------------
// capability gating (spec 6.8)
// ---------------------------------------------------------------------------

/**
 * true / false / null, where null means "the server did not say". Mirrors
 * capabilities.js: an unreported capability is never folded into false, because
 * accusing a build of a limitation nobody measured is its own kind of lie.
 */
function capability(name) {
  const state = store.state;
  const caps =
    state && state.capabilities && typeof state.capabilities === 'object'
      ? state.capabilities
      : null;
  if (caps && typeof caps[name] === 'boolean') return caps[name];
  if (state && typeof state[name] === 'boolean') return state[name];
  return null;
}

/** Buttons whose availability depends on an optional dependency. */
const CAPABILITY_GATES = [
  { action: 'excel', capability: 'excelExport', message: 'msg.excelUnavailable' },
  { action: 'render', capability: 'nativeDot', message: 'msg.renderUnavailable' },
];

/**
 * Disable-with-an-explanation, never hide. A vanished button reads as "this
 * build never had the feature"; a dimmed one that says openpyxl is missing and
 * how to install it is a bug report the user can fix themselves.
 */
function applyCapabilityGates() {
  for (const gate of CAPABILITY_GATES) {
    const button = $('[data-action="' + gate.action + '"]');
    if (!button) continue;
    const off = capability(gate.capability) === false;
    button.setAttribute('aria-disabled', off ? 'true' : 'false');
    if (off) {
      button.dataset.capability = gate.capability;
      button.title = t(gate.message);
    } else {
      delete button.dataset.capability;
      if (button.dataset.i18nTitle) button.title = t(button.dataset.i18nTitle);
    }
  }
}

function explainUnbuilt(button) {
  const phase = button.dataset.phase || 'a later phase';
  const label = button.getAttribute('aria-label') || button.textContent.trim();
  toast(t('msg.notAvailable', { label, phase }), 'info');
}

/** Why this button did nothing: a missing dependency, or an unbuilt phase. */
function explainDisabled(button) {
  const gate = CAPABILITY_GATES.find((entry) => entry.capability === button.dataset.capability);
  if (gate) {
    toast(t(gate.message), 'warn', 'CAPABILITY_UNAVAILABLE');
    return;
  }
  explainUnbuilt(button);
}

const ACTIONS = {
  new: actionNew,
  add: actionAdd,
  edit: actionEdit,
  delete: actionDelete,
  load: actionLoad,
  save: actionSave,
  'save-as': actionSaveAs,
  json: () => actionExport('json'),
  xml: () => actionExport('xml'),
  excel: () => actionExport('xlsx'),
  render: actionRenderImage,
};

function wireActionBar() {
  for (const button of document.querySelectorAll('[data-action]')) {
    button.addEventListener('click', () => {
      if (button.getAttribute('aria-disabled') === 'true') {
        explainDisabled(button);
        return;
      }
      const handler = ACTIONS[button.dataset.action];
      if (handler) handler();
    });
  }
  $('#btn-ai-settings').addEventListener('click', (event) => {
    event.preventDefault();
    actionAiSettings();
  });
  $('#btn-undo').addEventListener('click', () => actionHistory('undo'));
  $('#btn-redo').addEventListener('click', () => actionHistory('redo'));
}

// ---------------------------------------------------------------------------
// top bar wiring
// ---------------------------------------------------------------------------

function setHideZero(on) {
  document.documentElement.dataset.hideZero = on ? '1' : '0';
  writeLocal('fta.hideZero', on ? '1' : '0');
  window.dispatchEvent(new CustomEvent('fta:hide-zero', { detail: { hidden: on } }));
}

function wireTopbar() {
  $('#mode-select').addEventListener('change', queueMetadata);
  for (const sel of ['#title-input', '#date-input']) {
    const el = $(sel);
    el.addEventListener('change', queueMetadata);
    el.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') el.blur();
    });
  }

  const hideZero = $('#hide-zero');
  hideZero.checked = readLocal('fta.hideZero') === '1';
  setHideZero(hideZero.checked);
  hideZero.addEventListener('change', () => setHideZero(hideZero.checked));

  $('#btn-theme').addEventListener('click', cycleTheme);
  $('#btn-lang').addEventListener('click', () => setLanguage(language === 'en' ? 'ja' : 'en'));
}

// ---------------------------------------------------------------------------
// shell rendering (everything outside tree.js / details.js)
// ---------------------------------------------------------------------------

function renderShell(state) {
  if (!state) return;

  syncMetadataInputs();

  const dirty = Boolean(state.dirty);
  const badge = $('#dirty');
  badge.dataset.dirty = String(dirty);
  $('#dirty-text').textContent = dirty ? t('status.unsaved') : t('status.saved');

  $('#btn-undo').disabled = !state.canUndo;
  $('#btn-redo').disabled = !state.canRedo;

  const nodeCount = store.flat().length;
  $('#tree-count').textContent =
    nodeCount === 1 ? t('meta.node') : t('meta.nodes', { n: nodeCount });
  $('#details-meta').textContent = store.selectedId
    ? t('meta.selected', { id: store.selectedId })
    : t('meta.noSelection');
  $('#diagram-meta').textContent = state.nativeDot ? t('meta.dotReady') : t('meta.dotMissing');

  const aiDot = $('#ai-status');
  aiDot.dataset.on = String(Boolean(state.aiConfigured));

  const path = $('#statusline-path');
  path.textContent = state.currentPath || t('status.noFile');
  path.title = state.currentPath || '';

  // Runs on every state change, so a capability that only arrives with the
  // first /api/state is applied the moment it does.
  applyCapabilityGates();
}

// ---------------------------------------------------------------------------
// keyboard shortcuts
// ---------------------------------------------------------------------------

const NON_TEXT_INPUTS = new Set([
  'checkbox', 'radio', 'button', 'submit', 'reset', 'file', 'range', 'color', 'image',
]);

function isTextEntry(el) {
  if (!el) return false;
  if (el.isContentEditable) return true;
  const tag = el.tagName;
  if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (tag === 'INPUT') return !NON_TEXT_INPUTS.has((el.type || 'text').toLowerCase());
  return false;
}

function modalOpen() {
  // The first two are the documented convention; .fta-modal-overlay is what
  // dialogs.js actually puts on its backdrop, so a modal there suppresses the
  // shell's shortcuts without that module having to opt in.
  return Boolean(
    document.querySelector('[data-fta-modal="open"], dialog[open], .fta-modal-overlay')
  );
}

function onKeyDown(event) {
  // Escape first: it has to work from inside a modal's own text fields.
  if (event.key === 'Escape') {
    const escape = new CustomEvent('fta:escape', { cancelable: true });
    window.dispatchEvent(escape);
    if (!escape.defaultPrevented) dismissTopToast();
    return;
  }

  if (sessionLost) return;
  if (modalOpen()) return;

  const ctrl = event.ctrlKey || event.metaKey;
  const key = (event.key || '').toLowerCase();

  // Ctrl+S is checked before the text-entry guard below: saving has to work
  // with the caret still in the Title box, and actionSave flushes that field
  // before it writes. Ctrl+Shift+S is Save As, as on the desktop.
  if (ctrl && !event.altKey && key === 's') {
    event.preventDefault();
    if (event.shiftKey) actionSaveAs();
    else actionSave();
    return;
  }

  // Typing must never trigger an action, and Ctrl+A/Ctrl+Z inside a field must
  // keep meaning select-all and undo-my-typing.
  if (isTextEntry(event.target)) return;

  if (!ctrl) {
    if (event.key === 'Delete' || event.key === 'Del') {
      event.preventDefault();
      actionDelete();
    }
    return;
  }
  if (event.altKey) return;

  // preventDefault on every one of these: Ctrl+A selects the page, Ctrl+D
  // bookmarks it, Ctrl+E focuses a search bar. (Ctrl+N is reserved by most
  // browsers and cannot be intercepted at all -- the button bar is the
  // reliable path for New.)
  switch (key) {
    case 'n':
      event.preventDefault();
      actionNew();
      break;
    case 'a':
      event.preventDefault();
      actionAdd();
      break;
    case 'e':
      event.preventDefault();
      actionEdit();
      break;
    case 'd':
      event.preventDefault();
      actionDelete();
      break;
    case 'z':
      event.preventDefault();
      actionHistory(event.shiftKey ? 'redo' : 'undo');
      break;
    case 'y':
      event.preventDefault();
      actionHistory('redo');
      break;
    default:
      break;
  }
}

// ---------------------------------------------------------------------------
// boot
// ---------------------------------------------------------------------------

async function boot() {
  loadLayout();
  applyLayout();
  applyTheme();
  applyLanguage();
  initSplitters();
  wireTopbar();
  wireActionBar();

  window.addEventListener('keydown', onKeyDown);
  window.addEventListener(SESSION_INVALID_EVENT, onSessionInvalid);
  window.addEventListener('fta:error', (event) => {
    const detail = (event && event.detail) || {};
    toast(detail.message || 'Something went wrong.', 'error', detail.code || null);
  });
  window.addEventListener('fta:toast', (event) => {
    const detail = (event && event.detail) || {};
    toast(detail.message || '', detail.kind || 'info', detail.code || null);
  });
  window.addEventListener('fta:ai-settings', (event) => {
    // preventDefault is how the asker (chat.js) learns the shell has this; an
    // unclaimed event means the dialog module never loaded.
    if (event.cancelable) event.preventDefault();
    actionAiSettings();
  });
  window.addEventListener('beforeunload', (event) => {
    if (store.state && store.state.dirty) {
      event.preventDefault();
      event.returnValue = '';
    }
  });

  // Bootstrap problem #1: take the token out of the URL before anything else
  // can read or record it.
  bootstrapToken();

  // Bootstrap problem #2: no token in this tab means every call would 403.
  // Say so once, clearly, instead of firing requests that cannot succeed.
  if (!hasToken()) {
    onSessionInvalid();
    return;
  }

  let state;
  try {
    state = await api.get('/state');
  } catch (err) {
    if (err instanceof ApiError && (err.status === 403 || err.code === 'NO_SESSION')) {
      onSessionInvalid(); // api.js already dispatched the event; idempotent
      return;
    }
    showError(err);
    showBlockingScreen(
      t('boot.title'),
      t('boot.body') + ' ' + (err && err.message ? err.message : ''),
      t('session.hint')
    );
    return;
  }

  store.setState(state);

  // Subscribing after setState is safe: store.subscribe fires immediately with
  // the current state, so the shell paints once here and on every change after.
  // Done before the panels load so the top bar is correct while they arrive.
  store.subscribe(renderShell);

  await loadPanels();
}

/**
 * A small, documented surface for the sibling modules -- toasts, translation
 * and a state refresh -- so they never have to import main.js (which would be
 * a cycle) or reach into the DOM for the status line.
 */
window.ftaShell = {
  t,
  toast,
  showError,
  setStatus,
  get language() {
    return language;
  },
  get hideZero() {
    return document.documentElement.dataset.hideZero === '1';
  },
  async refresh() {
    const state = await api.get('/state');
    store.setState(state);
    return state;
  },
};

boot().catch((err) => {
  showError(err);
  showBlockingScreen(t('boot.title'), String(err && err.message ? err.message : err), null);
});
