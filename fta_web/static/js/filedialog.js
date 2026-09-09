/**
 * filedialog.js -- the file browser modal.
 *
 * WHY A HAND-BUILT BROWSER AND NOT <input type="file">
 * ====================================================
 * The desktop editor calls `filedialog.askopenfilename` / `asksaveasfilename`
 * and gets back a real path, which `FTACore.save_to_json` then writes. This app
 * ships as an offline executable of that same editor, so "save" has to mean the
 * same thing: bytes at a path the user chose, re-openable next launch, editable
 * by the desktop build.
 *
 * A browser cannot offer that. `<input type="file">` hands over a File object
 * with no usable path, and a download lands wherever the browser is configured
 * to put things -- so a round trip through them would silently turn Save into
 * Save-a-copy-somewhere-else and Load into "upload a detached copy". Instead the
 * local server exposes a sandboxed view of the filesystem (`/api/fs/*`) and this
 * module draws a picker over it; the chosen path goes to the server, which does
 * the reading and writing exactly as the desktop app does.
 *
 * That means every path this dialog shows is a *server* path, and the server is
 * the authority on what may be read or written. `PATH_REJECTED` is therefore an
 * expected answer, not a malfunction: it is what a sandbox is for. It is shown
 * in the dialog's own message row, in the server's words, with the dialog left
 * open so the user can go somewhere else.
 *
 * CONTRACT
 * ========
 *   openFileDialog({mode, startDir?, filename?, extensions?, title?})
 *       mode        'open' | 'save'
 *       startDir    directory to open in; falls back to /api/fs/home
 *       filename    save mode: the name the box starts with
 *       extensions  ['.json'] by default; folders plus these are listed
 *       title       overrides the default heading
 *     -> Promise<string|null>   an absolute path, or null if cancelled.
 *
 * Nothing here talks to the store or writes a file. It answers one question --
 * "which path?" -- and the caller does the rest, so the same dialog serves
 * open, save-as and any later export-to-path.
 *
 * BACKEND SHAPES (fta_web/routes/files.py)
 *   GET /api/fs/home            -> {root, cwd}
 *   GET /api/fs/list?path=<abs> -> {path, parent, dirs:[{name,path}],
 *                                   files:[{name,path,size,modified}]}
 *                                  `parent` is null at the sandbox root.
 * (api.js strips the `ok` flag, so those are the fields as seen here.)
 *
 * KEYBOARD
 * --------
 * Escape cancels, Enter activates (descend into a folder, choose a file, or
 * confirm the typed name), Backspace goes up a level, arrows/Home/End move the
 * selection, and typing letters jumps to the next matching entry. Tab is trapped
 * inside the dialog and focus returns to whatever opened it -- the same rules
 * dialogs.js's modals follow, reimplemented here because createModal is private
 * to that module.
 */
import { api } from './api.js';
import { clear, confirmDialog, el, injectStyles } from './dialogs.js';

/* ------------------------------------------------------------- shell glue -- */

/**
 * Translate through the shell's table (main.js owns STRINGS and the EN/JA
 * toggle). No English literal belongs in this file: Japanese is a later phase
 * and a literal here would be work for it.
 */
function t(key, vars) {
  const shell = window.ftaShell;
  if (shell && typeof shell.t === 'function') {
    try {
      return shell.t(key, vars);
    } catch (_err) {
      /* fall through to the key, which is at least identifiable */
    }
  }
  return key;
}

/* ------------------------------------------------------------------ paths -- */

/**
 * Separator for `dir`. Guessed from the string rather than from navigator
 * platform: the server decides what a path looks like, and it is the only side
 * that knows. A POSIX path never contains a backslash, and a Windows path
 * always contains one or is a bare drive ("C:").
 */
function separatorFor(dir) {
  const text = String(dir || '');
  if (/^[A-Za-z]:$/.test(text) || /^[A-Za-z]:[\\/]/.test(text)) return '\\';
  if (text.indexOf('\\') !== -1 && text.indexOf('/') === -1) return '\\';
  return '/';
}

/** Join a directory and a bare file name with the directory's own separator. */
export function joinPath(dir, name) {
  const sep = separatorFor(dir);
  const base = String(dir || '').replace(/[\\/]+$/, '');
  return base === '' ? sep + name : base + sep + name;
}

/** The last segment of a path, for both separators. */
export function baseName(path) {
  const text = String(path == null ? '' : path);
  const parts = text.split(/[\\/]/);
  for (let i = parts.length - 1; i >= 0; i -= 1) {
    if (parts[i]) return parts[i];
  }
  return text;
}

/** Everything before the last segment, or null when there is nothing before it. */
export function dirName(path) {
  const text = String(path == null ? '' : path).replace(/[\\/]+$/, '');
  const cut = Math.max(text.lastIndexOf('/'), text.lastIndexOf('\\'));
  if (cut < 0) return null;
  if (cut === 0) return text.slice(0, 1); // "/file" -> "/"
  return text.slice(0, cut);
}

/* --------------------------------------------------------------- fomatting -- */

const UNITS = ['KB', 'MB', 'GB', 'TB'];

/** Human file size. Bytes below 1 KiB stay exact; the rest get one decimal. */
function formatSize(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n < 0) return '';
  if (n < 1024) return n + ' B';
  let value = n / 1024;
  let unit = 0;
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return (value < 10 ? value.toFixed(1) : String(Math.round(value))) + ' ' + UNITS[unit];
}

function pad2(n) {
  return (n < 10 ? '0' : '') + n;
}

/**
 * `modified` as YYYY-MM-DD HH:MM, in local time.
 *
 * The field's type is not pinned by the contract, so all three plausible
 * spellings are accepted: epoch seconds (what `Path.stat().st_mtime` gives),
 * epoch milliseconds, and an ISO string. Anything unrecognisable is shown
 * verbatim rather than as "Invalid Date" -- the file list is still usable
 * without a timestamp, and inventing one would be worse.
 */
function formatModified(value) {
  if (value === null || value === undefined || value === '') return '';
  let date = null;
  if (typeof value === 'number' && Number.isFinite(value)) {
    date = new Date(value > 1e12 ? value : value * 1000);
  } else if (typeof value === 'string') {
    const numeric = Number(value);
    if (value.trim() !== '' && Number.isFinite(numeric) && !/[^0-9.]/.test(value.trim())) {
      date = new Date(numeric > 1e12 ? numeric : numeric * 1000);
    } else {
      const parsed = new Date(value);
      date = Number.isNaN(parsed.getTime()) ? null : parsed;
    }
  }
  if (!date || Number.isNaN(date.getTime())) {
    return typeof value === 'string' ? value : '';
  }
  return (
    date.getFullYear() +
    '-' + pad2(date.getMonth() + 1) +
    '-' + pad2(date.getDate()) +
    ' ' + pad2(date.getHours()) +
    ':' + pad2(date.getMinutes())
  );
}

/* ------------------------------------------------------------------ errors -- */

/** The server's own words when there are any; otherwise something honest. */
function errorText(err, fallbackKey) {
  if (err && typeof err.message === 'string' && err.message) return err.message;
  return t(fallbackKey);
}

/** A dead session: the shell is already raising its blocking screen. */
function isSessionError(err) {
  return !!err && (err.code === 'NO_SESSION' || err.status === 403);
}

/* --------------------------------------------------------------- the modal -- */

const STYLE_ID = 'fta-filedialog-styles';

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

const GLYPH = { up: '↑', dir: '📁', file: '📄' };

const DEFAULT_EXTENSIONS = ['.json'];

let rowSeq = 0;

function normaliseExtensions(raw) {
  const list = Array.isArray(raw) ? raw : DEFAULT_EXTENSIONS;
  const out = [];
  for (const item of list) {
    const ext = String(item || '').trim().toLowerCase();
    if (!ext) continue;
    out.push(ext.charAt(0) === '.' ? ext : '.' + ext);
  }
  return out;
}

function matchesExtension(name, extensions) {
  if (!extensions.length) return true;
  const lower = String(name).toLowerCase();
  return extensions.some((ext) => lower.endsWith(ext));
}

/**
 * Browse the server's filesystem and resolve with the chosen absolute path.
 *
 * @param {{mode?: string, startDir?: string|null, filename?: string|null,
 *          extensions?: string[], title?: string}} [options]
 * @returns {Promise<string|null>}
 */
export function openFileDialog(options) {
  injectStyles(STYLE_ID, STYLES);

  const opts = options || {};
  const mode = opts.mode === 'save' ? 'save' : 'open';
  const extensions = normaliseExtensions(opts.extensions);
  const extensionLabel = extensions.join(', ');

  const trigger = document.activeElement;

  /* ---- state ---- */
  let cwd = '';
  let parent = null;
  let dirs = [];
  let files = [];
  let rows = []; // what the listbox is currently showing, in order
  let activeIndex = -1;
  let generation = 0;
  let busy = false;
  let closed = false;
  let typeBuffer = '';
  let typeTimer = 0;

  /* ---- chrome ---- */
  const titleId = 'fta-filedialog-title';
  const listId = 'fta-filedialog-list';

  const heading = el('h2', {
    class: 'fta-modal-title',
    id: titleId,
    text: opts.title || t(mode === 'save' ? 'file.saveTitle' : 'file.openTitle'),
  });

  const upButton = el('button', {
    type: 'button',
    class: 'fta-btn is-tiny',
    text: GLYPH.up + ' ' + t('file.up'),
    title: t('file.up'),
    onclick: () => goUp(),
  });

  const locationLine = el('p', { class: 'fdlg-location', 'aria-live': 'polite' });

  const list = el('div', {
    class: 'fdlg-list',
    id: listId,
    role: 'listbox',
    tabindex: '0',
    'aria-label': t('file.location'),
  });

  const hint = el('p', { class: 'fdlg-hint', text: t('file.filter', { ext: extensionLabel }) });

  const message = el('p', { class: 'fdlg-message', role: 'alert' });

  const nameInput = el('input', {
    type: 'text',
    class: 'fdlg-name',
    autocomplete: 'off',
    spellcheck: 'false',
    value: mode === 'save' ? String(opts.filename || '') : '',
  });
  const nameFieldId = 'fta-filedialog-name';
  nameInput.id = nameFieldId;
  const nameField = el('div', { class: 'fta-field fdlg-namefield' }, [
    el('label', { for: nameFieldId, text: t('file.name') }),
    nameInput,
  ]);

  const cancelButton = el('button', {
    type: 'button',
    class: 'fta-btn',
    text: t('file.cancel'),
    onclick: () => close(null),
  });
  const acceptButton = el('button', {
    type: 'button',
    class: 'fta-btn is-primary',
    text: t(mode === 'save' ? 'file.save' : 'file.open'),
    onclick: () => confirmChoice(),
  });

  const body = el('div', { class: 'fta-modal-body fdlg-body' }, [
    el('div', { class: 'fdlg-toolbar' }, [upButton, locationLine]),
    list,
    hint,
    mode === 'save' ? nameField : null,
    message,
  ]);

  const footer = el('div', { class: 'fta-modal-footer' }, [cancelButton, acceptButton]);

  const dialog = el(
    'div',
    {
      class: 'fta-modal fta-filedialog',
      role: 'dialog',
      'aria-modal': 'true',
      'aria-labelledby': titleId,
      tabindex: '-1',
    },
    [heading, body, footer]
  );

  // `.fta-modal-overlay` is what main.js looks for when deciding whether to
  // suppress its own shortcuts; `data-fta-modal` is the documented spelling in
  // app.css. Carrying both means neither has to know about this file.
  const overlay = el(
    'div',
    { class: 'fta-modal-overlay', dataset: { ftaModal: 'open' } },
    [dialog]
  );

  let settle;
  const done = new Promise((resolve) => {
    settle = resolve;
  });

  function close(value) {
    if (closed) return;
    closed = true;
    generation += 1; // orphan any in-flight listing
    document.removeEventListener('keydown', onKeydown, true);
    if (typeTimer) window.clearTimeout(typeTimer);
    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    if (trigger && typeof trigger.focus === 'function' && trigger.isConnected) {
      trigger.focus();
    }
    settle(value === undefined ? null : value);
  }

  /* ---- messages ---- */

  function setMessage(text, kind) {
    message.textContent = text || '';
    message.classList.toggle('is-error', kind === 'error');
    message.classList.toggle('is-warn', kind === 'warn');
    message.classList.toggle('is-busy', kind === 'busy');
  }

  function setBusy(next) {
    busy = next;
    list.setAttribute('aria-busy', next ? 'true' : 'false');
    acceptButton.disabled = next;
  }

  /* ---- listing ---- */

  function focusableIn(root) {
    return Array.from(root.querySelectorAll(FOCUSABLE)).filter(
      (node) => node.getClientRects().length > 0
    );
  }

  function buildRows() {
    const out = [];
    if (parent) {
      out.push({ kind: 'up', name: '..', path: parent, label: t('file.parent') });
    }
    for (const dir of dirs) {
      out.push({ kind: 'dir', name: dir.name, path: dir.path });
    }
    for (const file of files) {
      out.push({
        kind: 'file',
        name: file.name,
        path: file.path,
        size: formatSize(file.size),
        modified: formatModified(file.modified),
      });
    }
    return out;
  }

  function renderList() {
    rows = buildRows();
    clear(list);

    if (!rows.length || (rows.length === 1 && rows[0].kind === 'up')) {
      list.appendChild(
        el('p', {
          class: 'fdlg-empty',
          text: extensions.length
            ? t('file.empty', { ext: extensionLabel })
            : t('file.emptyAll'),
        })
      );
    }

    rows.forEach((row, index) => {
      rowSeq += 1;
      const id = 'fdlg-row-' + rowSeq;
      row.id = id;
      const label =
        row.kind === 'up'
          ? row.label
          : row.name + ', ' + t(row.kind === 'dir' ? 'file.kindFolder' : 'file.kindFile');
      const node = el(
        'div',
        {
          class: 'fdlg-row',
          id: id,
          role: 'option',
          'aria-selected': 'false',
          'aria-label': label,
          title: row.path,
          dataset: { kind: row.kind, index: String(index) },
        },
        [
          el('span', { class: 'fdlg-row__glyph', 'aria-hidden': 'true', text: GLYPH[row.kind] }),
          el('span', { class: 'fdlg-row__name', text: row.kind === 'up' ? row.label : row.name }),
          el('span', { class: 'fdlg-row__size', text: row.size || '' }),
          el('span', { class: 'fdlg-row__time', text: row.modified || '' }),
        ]
      );
      node.addEventListener('click', () => setActive(index));
      node.addEventListener('dblclick', () => {
        setActive(index);
        activate();
      });
      list.appendChild(node);
    });

    locationLine.textContent = cwd;
    locationLine.title = cwd;
    upButton.disabled = !parent;

    setActive(rows.length ? (rows[0].kind === 'up' && rows.length > 1 ? 1 : 0) : -1, true);
  }

  function setActive(index, silent) {
    const previous = list.querySelector('.fdlg-row.is-active');
    if (previous) {
      previous.classList.remove('is-active');
      previous.setAttribute('aria-selected', 'false');
    }
    activeIndex = index >= 0 && index < rows.length ? index : -1;
    if (activeIndex < 0) {
      list.removeAttribute('aria-activedescendant');
      return;
    }
    const row = rows[activeIndex];
    const node = document.getElementById(row.id);
    if (node) {
      node.classList.add('is-active');
      node.setAttribute('aria-selected', 'true');
      node.scrollIntoView({ block: 'nearest' });
      list.setAttribute('aria-activedescendant', row.id);
    }
    // Clicking a file in save mode fills the name box, so "replace that one"
    // takes one click rather than retyping a name that is already on screen.
    if (!silent && mode === 'save' && row.kind === 'file') {
      nameInput.value = row.name;
      setMessage('');
    }
  }

  /**
   * List `target`. Returns true when the listing rendered, false when it did
   * not -- the caller uses that to fall back to the next candidate directory.
   */
  async function navigate(target) {
    if (!target) return false;
    const mine = ++generation;
    setBusy(true);
    setMessage(t('file.loading'), 'busy');
    try {
      const res = await api.get('/fs/list?path=' + encodeURIComponent(target));
      if (mine !== generation || closed) return false;
      cwd = typeof res.path === 'string' && res.path ? res.path : String(target);
      parent = typeof res.parent === 'string' && res.parent ? res.parent : null;
      dirs = (Array.isArray(res.dirs) ? res.dirs : [])
        .filter((entry) => entry && entry.name && entry.path)
        .sort((a, b) => String(a.name).localeCompare(String(b.name)));
      files = (Array.isArray(res.files) ? res.files : [])
        .filter((entry) => entry && entry.name && entry.path)
        .filter((entry) => matchesExtension(entry.name, extensions))
        .sort((a, b) => String(a.name).localeCompare(String(b.name)));
      renderList();
      // fsbrowser caps a listing at MAX_LIST_ENTRIES and says so. A silently
      // half-listed folder is exactly how a user concludes their file is gone.
      setMessage(res.truncated ? t('file.truncated') : '', res.truncated ? 'warn' : null);
      return true;
    } catch (err) {
      if (mine !== generation || closed) return false;
      if (isSessionError(err)) {
        // The shell is already putting up its "relaunch the app" screen; a
        // dialog on top of it would just be in the way.
        close(null);
        return false;
      }
      // PATH_REJECTED lands here, and it is not a crash: the sandbox refused a
      // directory. Say what the server said and leave the dialog open.
      setMessage(errorText(err, 'file.errList'), 'error');
      return false;
    } finally {
      if (mine === generation) setBusy(false);
    }
  }

  function goUp() {
    if (parent) navigate(parent);
  }

  /** Enter / double-click on the highlighted row. */
  function activate() {
    if (busy) return;
    const row = rows[activeIndex];
    if (!row) return;
    if (row.kind === 'up' || row.kind === 'dir') {
      navigate(row.path);
      return;
    }
    if (mode === 'save') {
      nameInput.value = row.name;
    }
    confirmChoice();
  }

  /**
   * Add the default extension to a bare name.
   *
   * Returns null when the user typed a *different* extension. The dialog
   * advertises which types it saves, so it says no itself and stays open
   * rather than closing on a name the server will refuse with PATH_REJECTED --
   * which would cost the user their place in the folder tree to fix a typo.
   * The name is never silently rewritten: "report.txt" does not become
   * "report.txt.json" behind the user's back.
   */
  function withExtension(name) {
    if (!extensions.length) return name;
    if (matchesExtension(name, extensions)) return name;
    if (/\.[A-Za-z0-9]{1,8}$/.test(name)) return null;
    return name + extensions[0];
  }

  async function confirmChoice() {
    if (busy || closed) return;
    setMessage('');

    if (mode === 'open') {
      const row = rows[activeIndex];
      if (!row) {
        setMessage(t('file.errPickFile'), 'error');
        return;
      }
      if (row.kind !== 'file') {
        // Enter on a folder means "go in", which is what every other file
        // browser does; refusing here would be a dead end.
        navigate(row.path);
        return;
      }
      close(row.path);
      return;
    }

    const raw = String(nameInput.value || '').trim();
    if (!raw) {
      setMessage(t('file.errNameRequired'), 'error');
      nameInput.focus();
      return;
    }
    if (/[\\/]/.test(raw) || raw === '.' || raw === '..') {
      setMessage(t('file.errNameSeparator'), 'error');
      nameInput.focus();
      return;
    }

    const name = withExtension(raw);
    if (name === null) {
      setMessage(t('file.errExtension', { ext: extensionLabel }), 'error');
      nameInput.focus();
      return;
    }
    const lower = name.toLowerCase();

    if (dirs.some((dir) => String(dir.name).toLowerCase() === lower)) {
      setMessage(t('file.errIsFolder', { name: name }), 'error');
      nameInput.focus();
      return;
    }

    // Exact match wins and contributes its server-built path. A
    // case-insensitive match still prompts: on Windows and the default macOS
    // filesystem "Report.json" and "report.json" are one file, and overwriting
    // one believing it was the other is exactly the loss this prompt exists to
    // prevent.
    const exact = files.find((file) => file.name === name);
    const insensitive = exact || files.find((file) => String(file.name).toLowerCase() === lower);
    const target = exact ? exact.path : joinPath(cwd, name);

    if (insensitive) {
      const replace = await confirmDialog(t('file.confirmOverwrite', { name: insensitive.name }), {
        title: t('file.overwriteTitle'),
        confirmLabel: t('file.overwrite'),
        cancelLabel: t('file.cancel'),
      });
      if (closed) return;
      if (!replace) {
        nameInput.focus();
        nameInput.select();
        return;
      }
    }

    close(target);
  }

  /* ---- keyboard ---- */

  function isTopMost() {
    const overlays = document.querySelectorAll('.fta-modal-overlay');
    return !overlays.length || overlays[overlays.length - 1] === overlay;
  }

  function moveActive(delta) {
    if (!rows.length) return;
    const next = activeIndex < 0 ? 0 : activeIndex + delta;
    setActive(Math.min(rows.length - 1, Math.max(0, next)));
  }

  /** Jump to the next row whose name starts with what was just typed. */
  function typeAhead(char) {
    if (typeTimer) window.clearTimeout(typeTimer);
    typeBuffer += char.toLowerCase();
    typeTimer = window.setTimeout(() => {
      typeBuffer = '';
      typeTimer = 0;
    }, 700);

    const total = rows.length;
    for (let step = 1; step <= total; step += 1) {
      const index = ((activeIndex < 0 ? -1 : activeIndex) + step + total) % total;
      const row = rows[index];
      if (row.kind !== 'up' && String(row.name).toLowerCase().startsWith(typeBuffer)) {
        setActive(index);
        return;
      }
    }
  }

  function onKeydown(event) {
    // Only the top-most modal reacts, so the overwrite confirmation's Escape
    // cannot also close this dialog underneath it.
    if (!isTopMost()) return;

    if (!overlay.contains(event.target) && event.key !== 'Escape') {
      // Focus escaped (browser chrome, a stray programmatic focus): pull it
      // back rather than letting the page behind take the keystroke.
      const first = focusableIn(dialog)[0] || dialog;
      first.focus();
      event.preventDefault();
      return;
    }

    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      close(null);
      return;
    }

    if (event.key === 'Tab') {
      const items = focusableIn(dialog);
      if (!items.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      const outside = !dialog.contains(active);
      if (event.shiftKey && (outside || active === first)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (outside || active === last)) {
        event.preventDefault();
        first.focus();
      }
      return;
    }

    const inList = list === event.target || list.contains(event.target);
    const onButton = event.target && event.target.tagName === 'BUTTON';

    if (event.key === 'Enter') {
      if (onButton) return; // let the button take its own click
      event.preventDefault();
      if (inList) activate();
      else confirmChoice();
      return;
    }

    if (!inList) {
      // Backspace has to keep deleting characters in the name box.
      return;
    }

    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        moveActive(1);
        return;
      case 'ArrowUp':
        event.preventDefault();
        moveActive(-1);
        return;
      case 'PageDown':
        event.preventDefault();
        moveActive(10);
        return;
      case 'PageUp':
        event.preventDefault();
        moveActive(-10);
        return;
      case 'Home':
        event.preventDefault();
        setActive(0);
        return;
      case 'End':
        event.preventDefault();
        setActive(rows.length - 1);
        return;
      case 'Backspace':
        event.preventDefault();
        goUp();
        return;
      default:
        break;
    }

    if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      typeAhead(event.key);
    }
  }

  /* ---- open ---- */

  document.addEventListener('keydown', onKeydown, true);
  document.body.appendChild(overlay);

  (async () => {
    let home = null;
    let homeError = null;
    try {
      home = await api.get('/fs/home');
    } catch (err) {
      if (isSessionError(err)) {
        close(null);
        return;
      }
      homeError = err;
    }
    if (closed) return;

    const candidates = [];
    if (opts.startDir) candidates.push(opts.startDir);
    if (home && home.cwd) candidates.push(home.cwd);
    if (home && home.root) candidates.push(home.root);

    for (const candidate of candidates) {
      if (closed) return;
      if (await navigate(candidate)) {
        // Save mode starts in the name box with the stem selected, so typing
        // replaces the name and Enter saves; open mode starts in the list.
        if (mode === 'save') {
          nameInput.focus();
          const stem = nameInput.value.lastIndexOf('.');
          nameInput.setSelectionRange(0, stem > 0 ? stem : nameInput.value.length);
        } else {
          list.focus();
        }
        return;
      }
    }

    if (!closed && homeError) setMessage(errorText(homeError, 'file.errList'), 'error');
    if (!closed) cancelButton.focus();
  })();

  return done;
}

/* ------------------------------------------------------------------ styles -- */

const STYLES = `
.fta-filedialog { width: min(44rem, 100%); }
.fta-filedialog .fdlg-body { gap: 0.5rem; }

.fdlg-toolbar { display: flex; align-items: center; gap: 0.5rem; min-width: 0; }
.fdlg-location {
  margin: 0;
  flex: 1 1 auto;
  min-width: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.78rem;
  color: var(--fta-muted-fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fdlg-list {
  min-height: 12rem;
  max-height: min(50vh, 22rem);
  overflow: auto;
  border: 1px solid var(--fta-border);
  border-radius: var(--fta-radius);
  background: var(--fta-surface);
}
.fdlg-list:focus-visible { outline: 2px solid var(--fta-focus-ring); outline-offset: 1px; }
.fdlg-list[aria-busy="true"] { opacity: 0.6; }

.fdlg-row {
  display: grid;
  grid-template-columns: 1.4em minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.5rem;
  font-size: 0.85rem;
  cursor: default;
  user-select: none;
}
.fdlg-row:hover { background: var(--fta-tree-hover-tint); }
.fdlg-row.is-active {
  background: var(--fta-tree-selected-tint);
  box-shadow: inset 2px 0 0 var(--fta-tree-selected-outline);
}
.fdlg-row__glyph { font-size: 0.85rem; line-height: 1; }
.fdlg-row__name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fdlg-row__size,
.fdlg-row__time {
  font-size: 0.75rem;
  color: var(--fta-muted-fg);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.fdlg-row[data-kind="dir"] .fdlg-row__name,
.fdlg-row[data-kind="up"] .fdlg-row__name { font-weight: 600; }

.fdlg-empty {
  margin: 0;
  padding: 1.2rem 0.6rem;
  text-align: center;
  font-size: 0.85rem;
  color: var(--fta-muted-fg);
}

.fdlg-hint { margin: 0; font-size: 0.75rem; color: var(--fta-muted-fg); }
.fdlg-namefield { margin-top: 0.1rem; }
.fdlg-name { width: 100%; }

.fdlg-message {
  margin: 0;
  min-height: 1.2em;
  font-size: 0.8rem;
  color: var(--fta-muted-fg);
  overflow-wrap: anywhere;
}
.fdlg-message.is-error { color: var(--fta-danger-fg); }
/* --warn comes from theme.css, which is loaded in the same document; the
   dialogs.js token set has no amber and a truncated listing is not an error. */
.fdlg-message.is-warn { color: var(--warn, var(--fta-danger-fg)); font-weight: 600; }
`;

export default openFileDialog;
