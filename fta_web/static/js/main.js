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
 * OTHER WINDOW EVENTS THE SHELL HANDLES
 * -------------------------------------
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
  hasToken,
  SESSION_INVALID_EVENT,
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
    'btn.xml': 'XML',
    'btn.excel': 'Excel',
    'btn.render': 'Render',
    'tip.new': 'New analysis (Ctrl+N)',
    'tip.add': 'Add a child node (Ctrl+A)',
    'tip.edit': 'Edit the selected node (Ctrl+E)',
    'tip.delete': 'Delete the selected node (Ctrl+D)',

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

    'confirm.delete': 'Delete "{name}" and everything beneath it?',
    'confirm.discard': 'Discard the unsaved changes and start a new analysis?',

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
    'btn.xml': 'XML',
    'btn.excel': 'Excel',
    'btn.render': '画像',
    'tip.new': '新規解析 (Ctrl+N)',
    'tip.add': '子ノードを追加 (Ctrl+A)',
    'tip.edit': '選択中のノードを編集 (Ctrl+E)',
    'tip.delete': '選択中のノードを削除 (Ctrl+D)',

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

    'confirm.delete': '「{name}」と配下のノードを削除しますか？',
    'confirm.discard': '未保存の変更を破棄して新規作成しますか？',

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

const modules = { tree: null, details: null, dialogs: null };

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
    ['diagram', './diagram.js'],
    ['capabilities', './capabilities.js'],
  ];
  await Promise.all(
    specs.map(async ([name, spec]) => {
      try {
        modules[name] = await import(spec);
      } catch (err) {
        modules[name] = null;
        // dialogs.js has no panel of its own; its absence shows up when an
        // action needs it, so do not shout about it here.
        if (name === 'tree') renderModuleFallback($('#tree-root'), t('panel.tree'), err);
        if (name === 'details') renderModuleFallback($('#details-root'), t('panel.details'), err);
        if (name === 'diagram') renderModuleFallback($('#diagram-root'), t('panel.diagram'), err);
        // eslint-disable-next-line no-console
        console.error('[fta] could not load ' + spec, err);
      }
    })
  );

  callInit(modules.tree, ['initTree', 'init', 'default'], $('#tree-root'), t('panel.tree'));
  callInit(modules.details, ['initDetails', 'init', 'default'], $('#details-root'), t('panel.details'));
  callInit(modules.diagram, ['initDiagram', 'init', 'default'], $('#diagram-root'), t('panel.diagram'));
  callInit(modules.capabilities, ['initCapabilities', 'init', 'default'], $('#capabilities-host'), 'capabilities', true);
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

function explainUnbuilt(button) {
  const phase = button.dataset.phase || 'a later phase';
  const label = button.getAttribute('aria-label') || button.textContent.trim();
  toast(t('msg.notAvailable', { label, phase }), 'info');
}

const ACTIONS = {
  new: actionNew,
  add: actionAdd,
  edit: actionEdit,
  delete: actionDelete,
};

function wireActionBar() {
  for (const button of document.querySelectorAll('[data-action]')) {
    button.addEventListener('click', () => {
      if (button.getAttribute('aria-disabled') === 'true') {
        explainUnbuilt(button);
        return;
      }
      const handler = ACTIONS[button.dataset.action];
      if (handler) handler();
    });
  }
  $('#btn-ai-settings').addEventListener('click', (event) => {
    event.preventDefault();
    explainUnbuilt($('#btn-ai-settings'));
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
  $('#mode-select').addEventListener('change', commitMetadata);
  for (const sel of ['#title-input', '#date-input']) {
    const el = $(sel);
    el.addEventListener('change', commitMetadata);
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
  // Typing must never trigger an action, and Ctrl+A/Ctrl+Z inside a field must
  // keep meaning select-all and undo-my-typing.
  if (isTextEntry(event.target) || modalOpen()) return;

  const ctrl = event.ctrlKey || event.metaKey;
  const key = (event.key || '').toLowerCase();

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
