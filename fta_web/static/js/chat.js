/**
 * chat.js -- the AI assistant panel.
 *
 * A port of the desktop editor's chat panel (src/FTA_Editor_UI.py:244-314 for
 * the layout, :783-921 for the two quick actions) onto the web shell:
 *
 *   * a message log with user / assistant / system / error styling,
 *   * an input where Enter sends and Shift+Enter starts a new line,
 *   * Analyze FTA (reply only, never mutates), Update FTA (generate -> verify
 *     -> apply) and Clear Chat,
 *   * a reviewable list whenever the assistant proposes `changes`,
 *   * an MD switch: the assistant's replies as formatted Markdown, or as the
 *     raw text the model sent (markdown.js; kept in `fta.aiMarkdown`).
 *
 * WHAT THIS PANEL LOOKS LIKE WITH NO PROVIDER CONFIGURED
 * ------------------------------------------------------
 * An invitation, never an error and never a warning. An unconfigured assistant
 * is the expected default -- it is optional by design and every other feature
 * works without it -- so the panel reads like an offer rather than a fault.
 * capabilities.js frames the same fact the same way; the two must not disagree.
 *
 * WHY FAILED UPDATES ARE LOUD
 * ---------------------------
 * `POST /api/ai/update` answers a bad generation with diagnostics: a 500-char
 * excerpt of what the model actually said, or the JSON of the node that failed
 * verification. That detail is the feature. A user who is told only "the update
 * failed" has no way to tell a bad prompt from a bad model from a bad key, so
 * every field of the error envelope's `detail` is rendered -- long ones inside a
 * collapsible, scrollable block so they inform without burying the conversation.
 *
 * BACKEND (fta_web/routes/ai.py)
 *   POST   /api/ai/chat            {message} -> {reply, changes:[...]}
 *   POST   /api/ai/analyze         -> {reply}          (never mutates)
 *   POST   /api/ai/update          -> generate and verify; with {preview:
 *                                     true} (what this panel sends) nothing
 *                                     is applied and the answer is a summary
 *   POST   /api/ai/update/apply    -> install the previewed rewrite
 *   POST   /api/ai/update/discard  -> drop it
 *   POST   /api/ai/changes/apply   {indices:[...]}
 *   GET    /api/ai/conversation    the chat so far (repainted after a reload)
 *   DELETE /api/ai/conversation    clear the history
 * Any of them but the GET answers 400 AI_NOT_CONFIGURED while no key is stored.
 *
 * CONTRACT
 *   initChat(host) -> {refresh(), destroy()}
 */
import { api, ApiError } from './api.js';
import { store } from './store.js';
import { choiceDialog, clear, el } from './dialogs.js';
import { renderMarkdown } from './markdown.js';

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

/**
 * true / false / null, where null means "the server did not say". Same
 * tri-state rule as capabilities.js, deliberately re-implemented in four lines
 * rather than imported: a broken capabilities.js should cost the top-bar chip,
 * not this panel as well.
 */
function aiConfigured() {
  const state = store.state;
  if (!state || typeof state !== 'object') return null;
  const caps = state.capabilities && typeof state.capabilities === 'object' ? state.capabilities : null;
  if (caps && typeof caps.aiConfigured === 'boolean') return caps.aiConfigured;
  if (typeof state.aiConfigured === 'boolean') return state.aiConfigured;
  return null;
}

/**
 * The MD switch is a per-browser preference like the theme. On unless it was
 * switched off; a browser without storage simply starts on every time.
 */
const MARKDOWN_PREF = 'fta.aiMarkdown';

function readMarkdownPref() {
  try {
    return window.localStorage.getItem(MARKDOWN_PREF) !== '0';
  } catch (_err) {
    return true;
  }
}

function writeMarkdownPref(on) {
  try {
    window.localStorage.setItem(MARKDOWN_PREF, on ? '1' : '0');
  } catch (_err) {
    /* private mode: the choice lasts until the page is closed */
  }
}

/** True when the open document is an event tree. */
function isEta() {
  try {
    return String(store.metadata().mode || '').toUpperCase() === 'ETA';
  } catch (_err) {
    return false;
  }
}

/**
 * The catalog key for the mode: `key + '.eta'` in ETA mode where the catalog
 * has one, else `key`. "Analyze FTA" and "this fault tree" on an event tree
 * were simply wrong.
 */
function modeKey(key) {
  if (!isEta()) return key;
  const eta = key + '.eta';
  return t(eta) === eta ? key : eta;
}

/** The start of a reply that is the provider's failure, reported in-band. */
const AI_ERROR_PREFIX = 'AI Error:';

/* ------------------------------------------------------------- payloads ---- */

/**
 * Pull a list out of a response without betting on one field name.
 *
 * The backend is being written in parallel against the same contract; a list
 * that arrives as `changes` in one revision and `suggestions` in the next would
 * otherwise silently render as "no suggestions", which is the one failure mode
 * a user cannot see. Named keys first, then any array-valued field.
 */
function listFrom(payload, names) {
  if (!payload || typeof payload !== 'object') return [];
  for (const name of names) {
    if (Array.isArray(payload[name])) return payload[name];
  }
  for (const value of Object.values(payload)) {
    if (Array.isArray(value)) return value;
  }
  return [];
}

/** The assistant's prose, whatever the field ended up being called. */
function replyFrom(payload) {
  if (!payload || typeof payload !== 'object') return '';
  for (const name of ['reply', 'response', 'message', 'text']) {
    if (typeof payload[name] === 'string' && payload[name].trim()) return payload[name];
  }
  return '';
}

function firstString(source, names) {
  for (const name of names) {
    const value = source && source[name];
    if (value !== null && value !== undefined && String(value).trim() !== '') {
      return String(value);
    }
  }
  return '';
}

/**
 * How many changes POST /api/ai/changes/apply applied. `applied` is the list
 * of applied records -- Number() of a one-record list is NaN, which once made
 * a batch with rejections read "Applied 3 of 3". A bare count is accepted
 * too; only a response with neither falls back to the number requested.
 */
function appliedCount(result, requested) {
  const applied = result && typeof result === 'object' ? result.applied : undefined;
  if (Array.isArray(applied)) return applied.length;
  if (typeof applied === 'number' && Number.isFinite(applied)) return applied;
  return requested;
}

/** An update summary names at most this many nodes, each at most this long. */
const SUMMARY_NAMES = 5;
const SUMMARY_NAME_CHARS = 40;

/** "A, B, C, D, E, …" from a list of {id, name}. Names are data, not UI text. */
function summaryNames(list) {
  const names = (Array.isArray(list) ? list : [])
    .map((entry) => String((entry && (entry.name || entry.id)) || '').trim())
    .filter(Boolean)
    .map((name) => (name.length > SUMMARY_NAME_CHARS ? name.slice(0, SUMMARY_NAME_CHARS - 1) + '…' : name));
  if (names.length > SUMMARY_NAMES) return names.slice(0, SUMMARY_NAMES).join(', ') + ', …';
  return names.join(', ');
}

/**
 * POST /api/ai/update's `updateSummary` as one chat line: a catalog key and
 * its vars, so a language switch re-translates it. Counts what the rewrite
 * added, changed and removed, and names the changed and removed nodes -- the
 * model is asked to keep every existing node, but nothing makes it.
 */
function updateSummaryMessage(summary) {
  if (!summary || typeof summary !== 'object') return null;
  const count = (list) => (Array.isArray(list) ? list.length : 0);
  const vars = {
    added: count(summary.added),
    changed: count(summary.changed),
    removed: count(summary.removed),
    removedNames: summaryNames(summary.removed),
    changedNames: summaryNames(summary.changed),
  };
  let key = 'ai.update.summary';
  if (vars.removedNames && vars.changedNames) key = 'ai.update.summaryBoth';
  else if (vars.removedNames) key = 'ai.update.summaryRemoved';
  else if (vars.changedNames) key = 'ai.update.summaryChanged';
  return { key, vars };
}

/** A preview names at most this many nodes per line, then says how many more. */
const PREVIEW_NAMES = 12;

/** "A, B, C … and 4 more" from a list of {id, name}, for the preview card. */
function previewNames(list) {
  const names = (Array.isArray(list) ? list : [])
    .map((entry) => String((entry && (entry.name || entry.id)) || '').trim())
    .filter(Boolean)
    .map((name) => (name.length > SUMMARY_NAME_CHARS ? name.slice(0, SUMMARY_NAME_CHARS - 1) + '…' : name));
  if (names.length <= PREVIEW_NAMES) return names.join(', ');
  return names.slice(0, PREVIEW_NAMES).join(', ') + ' ' + t('ai.update.more', { n: names.length - PREVIEW_NAMES });
}

/* ------------------------------------------------------------ the panel ---- */

const ROLE_KEY = {
  user: 'ai.role.user',
  assistant: 'ai.role.assistant',
  system: 'ai.role.system',
  error: 'ai.role.error',
};

/**
 * Error-envelope `detail` keys we can name in the user's language. Anything
 * else is shown under its raw key: that is server data, not UI copy, and a
 * field the backend added after this build is still worth reading.
 */
const DIAGNOSTIC_KEY = {
  excerpt: 'ai.diag.excerpt',
  outputExcerpt: 'ai.diag.excerpt',
  output: 'ai.diag.excerpt',
  raw: 'ai.diag.raw',
  rawOutput: 'ai.diag.raw',
  response: 'ai.diag.raw',
  section: 'ai.diag.section',
  node: 'ai.diag.section',
  nodeJson: 'ai.diag.section',
  problemNode: 'ai.diag.section',
  topLevelKeys: 'ai.diag.keys',
  keys: 'ai.diag.keys',
};

export function initChat(host) {
  if (!host) throw new Error('initChat(host): host is required');

  clear(host);

  /* ---- structure ---- */

  const inviteTitle = el('p', { class: 'chat-invite__title' });
  const inviteBody = el('p', { class: 'chat-invite__body' });
  const inviteFree = el('p', { class: 'chat-invite__free' });
  const inviteButton = el('button', {
    type: 'button',
    class: 'btn btn--primary chat-invite__btn',
    onclick: () => openSettings(),
  });
  const invite = el('div', { class: 'chat__invite', hidden: true }, [
    inviteTitle,
    inviteBody,
    inviteFree,
    inviteButton,
  ]);

  const log = el('div', {
    class: 'chat__log',
    role: 'log',
    'aria-live': 'polite',
    'aria-relevant': 'additions',
    tabindex: '0',
  });

  const busyText = el('span', { class: 'chat__busy-text' });
  // Stop gives the panel back while the provider is still thinking. It was
  // wait-or-reload: up to two minutes with every button disabled.
  const stopBtn = el('button', {
    type: 'button',
    class: 'btn chat__stop',
    dataset: { role: 'stop' },
    hidden: true,
    onclick: () => actionStop(),
  });
  const busyBar = el('div', { class: 'chat__busy', role: 'status', 'aria-live': 'polite', hidden: true }, [
    el('span', { class: 'chat__spinner', 'aria-hidden': 'true' }),
    busyText,
    stopBtn,
  ]);

  const analyzeBtn = el('button', { type: 'button', class: 'btn chat__action', onclick: () => actionAnalyze() });
  const updateBtn = el('button', { type: 'button', class: 'btn chat__action', onclick: () => actionUpdate() });
  const clearBtn = el('button', {
    type: 'button',
    class: 'btn btn--danger chat__action',
    onclick: () => actionClear(),
  });
  const markdownBtn = el('button', {
    type: 'button',
    class: 'btn chat__action chat__action--end chat__md',
    onclick: () => setMarkdown(!markdownOn),
  });
  const actions = el('div', { class: 'chat__actions' }, [analyzeBtn, updateBtn, markdownBtn, clearBtn]);

  const input = el('textarea', { class: 'chat__input', rows: '3', spellcheck: 'true' });
  const sendBtn = el('button', { type: 'submit', class: 'btn btn--primary chat__send' });
  const composer = el('form', { class: 'chat__composer' }, [input, sendBtn]);

  const root = el('div', { class: 'chat', dataset: { busy: 'false' } }, [
    invite,
    log,
    busyBar,
    actions,
    composer,
  ]);
  host.appendChild(root);

  /* ---- state ---- */

  let busy = false;
  let destroyed = false;
  let welcomed = false;
  let lastConfigured = undefined;
  let openChanges = null; // the newest, still-applicable suggestion card
  let openUpdate = null; // the Update FTA preview still waiting for Apply or Discard
  let markdownOn = readMarkdownPref();
  let current = null; // the request to the provider now on the wire (see run())
  let lastMode = isEta();
  let notConfiguredRow = null; // the one "no provider yet" line in the log
  let welcomeRow = null;

  /* ---- labels (re-applied on every EN/JA switch) ---- */

  function applyLabels() {
    inviteTitle.textContent = t('ai.invite.title');
    inviteBody.textContent = t('ai.invite.body');
    inviteFree.textContent = t('ai.invite.free');
    inviteButton.textContent = t('ai.invite.button');

    log.setAttribute('aria-label', t('ai.chat.log'));

    analyzeBtn.textContent = t(modeKey('ai.chat.analyze'));
    analyzeBtn.title = t(modeKey('ai.chat.analyzeTitle'));
    updateBtn.textContent = t(modeKey('ai.chat.update'));
    updateBtn.title = t(modeKey('ai.chat.updateTitle'));
    stopBtn.textContent = t('ai.chat.stop');
    stopBtn.title = t('ai.chat.stopTitle');
    clearBtn.textContent = t('ai.chat.clear');
    clearBtn.title = t('ai.chat.clearTitle');
    markdownBtn.textContent = t('ai.chat.markdown');
    markdownBtn.title = t(markdownOn ? 'ai.chat.markdownOnTitle' : 'ai.chat.markdownOffTitle');
    markdownBtn.setAttribute('aria-label', t('ai.chat.markdownLabel'));
    markdownBtn.setAttribute('aria-pressed', markdownOn ? 'true' : 'false');

    input.setAttribute('aria-label', t('ai.chat.input'));
    input.placeholder = t(modeKey('ai.chat.placeholder'));
    sendBtn.textContent = t('ai.chat.send');
    sendBtn.title = t('ai.chat.sendTitle');
  }

  /* ---- the log ---- */

  function scrollToEnd() {
    log.scrollTop = log.scrollHeight;
  }

  /**
   * One message. `role` picks the styling and the speaker label; the text is
   * always written with textContent, because a model's reply is untrusted input
   * exactly like a node name is.
   */
  /**
   * Messages written from a catalog key remember it (key -> {key, vars}), so a
   * live language switch re-translates them along with every role label.
   * Text typed by the user or returned by the AI is never touched.
   */
  const keyed = new WeakMap();

  /**
   * The model's own replies (row -> the text as sent). Only these are ever
   * drawn as Markdown: what the user typed and what the editor says stay
   * plain. The raw text is kept so the MD switch can redraw either way.
   */
  const replies = new WeakMap();

  /**
   * Draw a reply as Markdown or as its raw text. markdown.js builds elements
   * and text nodes only, never HTML, so the reply stays as untrusted as it is
   * under textContent. If it throws, the raw text is shown: a reply is never
   * lost to its formatting.
   */
  function fillReply(body, text) {
    clear(body);
    body.classList.toggle('chat-msg__body--md', markdownOn);
    if (markdownOn) {
      try {
        body.appendChild(renderMarkdown(text, document));
        return;
      } catch (_err) {
        clear(body);
        body.classList.remove('chat-msg__body--md');
      }
    }
    body.textContent = text;
  }

  function setMarkdown(on) {
    markdownOn = Boolean(on);
    writeMarkdownPref(markdownOn);
    applyLabels();
    for (const row of log.querySelectorAll('.chat-msg')) {
      const body = row.querySelector('.chat-msg__body');
      if (body && replies.has(row)) fillReply(body, replies.get(row));
    }
  }

  function addMessage(role, text, options) {
    const kind = ROLE_KEY[role] ? role : 'system';
    const body = el('div', { class: 'chat-msg__body' });
    const raw = String(text === null || text === undefined ? '' : text);
    const reply = Boolean(options && options.reply);
    if (reply) fillReply(body, raw);
    else body.textContent = raw;
    const row = el('div', { class: 'chat-msg chat-msg--' + kind, dataset: { role: kind } }, [
      el('span', { class: 'chat-msg__role', text: t(ROLE_KEY[kind]) }),
      body,
    ]);
    if (reply) replies.set(row, raw);
    log.appendChild(row);
    scrollToEnd();
    return row;
  }

  /** addMessage for a catalog string: re-translated on a language switch. */
  function say(role, key, vars) {
    const row = addMessage(role, t(key, vars));
    keyed.set(row, { key, vars });
    return row;
  }

  /** Re-translate the role labels and every catalog-keyed message in the log. */
  function relabelLog() {
    for (const row of log.querySelectorAll('.chat-msg')) {
      const role = row.querySelector('.chat-msg__role');
      if (role && ROLE_KEY[row.dataset.role]) role.textContent = t(ROLE_KEY[row.dataset.role]);
      const entry = keyed.get(row);
      const body = row.querySelector('.chat-msg__body');
      if (entry && body) body.textContent = t(entry.key, entry.vars);
    }
  }

  /** A long block (an AI output excerpt, a rejected node) kept readable. */
  function addBlock(label, text, open) {
    const pre = el('pre', { class: 'chat-block__pre' });
    pre.textContent = String(text);
    const block = el('details', { class: 'chat-block' }, [
      el('summary', { class: 'chat-block__summary', text: label }),
      pre,
    ]);
    if (open) block.open = true;
    log.appendChild(block);
    scrollToEnd();
    return block;
  }

  function diagnosticLabel(key) {
    const mapped = DIAGNOSTIC_KEY[key];
    return mapped ? t(mapped) : key;
  }

  /**
   * Render everything the server attached to a failure. Short scalars read
   * better as a line of text; anything long or structured goes into a
   * collapsible block, the first one already open so the detail is seen without
   * a click.
   */
  function showDiagnostics(detail) {
    if (!detail || typeof detail !== 'object') return;
    let opened = false;
    for (const [key, value] of Object.entries(detail)) {
      if (value === null || value === undefined || value === '') continue;
      const text = typeof value === 'string' ? value : safeJson(value);
      if (!text) continue;
      if (typeof value === 'string' && text.length <= 80 && text.indexOf('\n') === -1) {
        addMessage('system', diagnosticLabel(key) + ': ' + text);
      } else {
        addBlock(diagnosticLabel(key), text, !opened);
        opened = true;
      }
    }
  }

  function safeJson(value) {
    try {
      return JSON.stringify(value, null, 2);
    } catch (_err) {
      return String(value);
    }
  }

  /* ---- busy ---- */

  /**
   * One request at a time. Overlapping calls would interleave two replies in
   * one log and could apply a change set generated against a tree that the
   * other call had already replaced.
   */
  function setBusy(next, message) {
    busy = Boolean(next);
    root.dataset.busy = busy ? 'true' : 'false';
    busyBar.hidden = !busy;
    // Only a request to the provider can be stopped; applying is short and
    // must run to its end.
    stopBtn.hidden = !(busy && current);
    busyText.textContent = busy ? message || t('ai.msg.thinking') : '';
    log.setAttribute('aria-busy', busy ? 'true' : 'false');
    for (const button of [analyzeBtn, updateBtn, clearBtn, sendBtn]) {
      button.disabled = busy;
    }
    input.readOnly = busy;
  }

  /* ---- configuration ---- */

  function openSettings() {
    // main.js owns the dialog module (it is loaded with the other panels), so
    // the panel asks rather than importing: a broken aisettings.js then costs
    // one visible message instead of taking this panel down with it.
    const event = new CustomEvent('fta:ai-settings', {
      detail: { source: 'chat' },
      cancelable: true,
    });
    window.dispatchEvent(event);
    if (!event.defaultPrevented) say('error', 'ai.err.noSettings');
  }

  function showInvitation(on) {
    invite.hidden = !on;
    root.dataset.configured = on ? 'false' : 'true';
    for (const button of [analyzeBtn, updateBtn, sendBtn]) {
      button.setAttribute('aria-disabled', on ? 'true' : 'false');
    }
  }

  /**
   * @returns {boolean} false when the request must not be sent. Nothing here
   * shouts: not being set up is a state, not a mistake.
   */
  /**
   * "No provider is set up yet", once. Each press of a button added the line
   * again, so three presses left three of them; now the one line is moved to
   * the end of the log instead.
   */
  function sayNotConfigured() {
    if (notConfiguredRow && notConfiguredRow.isConnected) {
      log.appendChild(notConfiguredRow);
      scrollToEnd();
      return;
    }
    notConfiguredRow = say('system', 'ai.msg.notConfigured');
    notConfiguredRow.dataset.kind = 'not-configured';
  }

  function ensureConfigured() {
    if (aiConfigured() === false) {
      showInvitation(true);
      sayNotConfigured();
      return false;
    }
    return true;
  }

  function handleError(err) {
    if (err instanceof ApiError && err.code === 'AI_NOT_CONFIGURED') {
      showInvitation(true);
      sayNotConfigured();
      return;
    }
    addMessage('error', err && err.message ? err.message : String(err));
    if (err instanceof ApiError) showDiagnostics(err.detail);
  }

  /* ---- the document, after the assistant has touched it ---- */

  /**
   * Put the tree and the diagram back in step with the server.
   *
   * A response that already carries a tree is merged directly; anything else
   * costs one /api/state read rather than a guess. Both paths notify the store,
   * which is what makes tree.js and diagram.js redraw.
   */
  async function refreshDocument(payload) {
    if (payload && typeof payload === 'object' && payload.tree) {
      store.applyMutation(payload);
      return;
    }
    const shell = window.ftaShell;
    if (shell && typeof shell.refresh === 'function') {
      await shell.refresh();
      return;
    }
    store.setState(await api.get('/state'));
  }

  /* ---- suggested changes ---- */

  /** "Add", "Change", "Delete", "Move" for a change type; the raw type if unknown. */
  function changeKind(change) {
    const type = firstString(change, ['changeType', 'change_type', 'type', 'kind']);
    if (!type) return '';
    const key = 'ai.changes.kind.' + type.toLowerCase();
    const label = t(key);
    return label === key ? type.toUpperCase() : label;
  }

  function changeTitle(change, index) {
    const kind = changeKind(change);
    const description = firstString(change, ['description', 'summary', 'detail', 'text']);
    return (kind ? kind + ': ' : '') + (description || t('ai.changes.untitled', { n: index + 1 }));
  }

  /**
   * A node by name, as a button that selects it (and brings it into view in
   * the tree and the diagram). A card said "Target: root_1_0" and left the
   * user to find out which node that was. An id that names no node of this
   * tree (a node the change would add) is shown as plain text.
   */
  function nodeLink(id) {
    const node = store.findNode(id);
    if (!node) return el('span', { class: 'chat-changes__id', text: String(id) });
    const name = node.name === undefined || node.name === null || String(node.name).trim() === '' ? String(id) : String(node.name);
    return el('button', {
      type: 'button',
      class: 'chat-link',
      dataset: { node: String(id) },
      title: t('ai.changes.selectTitle', { id: String(id) }),
      text: name,
      onclick: () => {
        if (store.findNode(id)) store.jumpTo(String(id));
      },
    });
  }

  /** Keys of a change's data that hold a node id (shown by name). */
  const ID_FIELDS = new Set(['parentId', 'parent_id', 'newParentId', 'new_parent_id', 'new_parent', 'parent']);
  /** Keys never listed: the id is the server's business, links have their own lines. */
  const SKIP_FIELDS = new Set(['id', 'links', 'children']);

  function fieldLabel(key) {
    const known = 'history.field.' + key;
    const label = t(known);
    return label === known ? key : label;
  }

  function fieldText(value) {
    if (value === null || value === undefined || value === '') return t('ai.changes.empty');
    if (typeof value === 'object') {
      const text = safeJson(value).replace(/\s+/g, ' ');
      return text.length > 120 ? text.slice(0, 119) + '…' : text;
    }
    return String(value);
  }

  /**
   * A change's data as lines a person can read: "probability: 0.01 → 0.05"
   * for a field of an existing node, "name: Pump fails" for a new one. The
   * card used to offer the raw JSON and nothing else.
   */
  function fieldLines(change, target) {
    const data = change && change.data;
    if (!data || typeof data !== 'object' || Array.isArray(data)) return [];
    const type = firstString(change, ['changeType', 'change_type', 'type', 'kind']).toLowerCase();
    const existing = type === 'edit' && target ? store.findNode(target) : null;
    const lines = [];
    for (const [key, value] of Object.entries(data)) {
      if (SKIP_FIELDS.has(key)) continue;
      const line = el('li', { class: 'chat-changes__field', dataset: { field: key } });
      line.append(fieldLabel(key) + ': ');
      if (ID_FIELDS.has(key) && value !== null && value !== undefined && value !== '') {
        line.appendChild(nodeLink(value));
      } else if (existing && Object.prototype.hasOwnProperty.call(existing, key) && fieldText(existing[key]) !== fieldText(value)) {
        line.append(
          el('span', { class: 'chat-changes__old', text: fieldText(existing[key]) }),
          ' → ',
          el('span', { class: 'chat-changes__new', text: fieldText(value) })
        );
      } else {
        line.appendChild(el('span', { class: 'chat-changes__new', text: fieldText(value) }));
      }
      lines.push(line);
    }
    return lines;
  }

  /** `Name (id)` for a link target; the id alone when the name is unknown. */
  function linkTarget(entry) {
    const id = firstString(entry, ['targetId', 'target_id']);
    const name = firstString(entry, ['targetName', 'name']);
    return name && name !== id ? name + ' (' + id + ')' : id;
  }

  /**
   * A change's `linkChanges` ({added, removed, problem}, from the server) as
   * lines for the card: `{kind: 'add'|'remove'|'none'|'problem', text}`.
   * Empty when the change does not touch links.
   */
  function linkLines(change) {
    const preview = change && change.linkChanges;
    if (!preview || typeof preview !== 'object') return [];
    const lines = [];
    for (const entry of Array.isArray(preview.added) ? preview.added : []) {
      lines.push({ kind: 'add', text: t('ai.changes.linkAdd', { relation: entry.relation, name: linkTarget(entry) }) });
    }
    for (const entry of Array.isArray(preview.removed) ? preview.removed : []) {
      lines.push({ kind: 'remove', text: t('ai.changes.linkRemove', { relation: entry.relation, name: linkTarget(entry) }) });
    }
    if (!lines.length && !preview.problem) lines.push({ kind: 'none', text: t('ai.changes.linkNone') });
    if (preview.problem) {
      lines.push({ kind: 'problem', text: t('ai.changes.linkProblem', { reason: String(preview.problem) }) });
    }
    return lines;
  }

  /**
   * The review list. Every box starts ticked, matching the desktop dialog
   * (src/FTA_Editor_UI.py:651) -- the assistant's whole set is the proposal, and
   * unticking is how a user disagrees with part of it.
   */
  function renderChanges(changes) {
    if (!Array.isArray(changes) || !changes.length) return;

    // The server keeps one pending list for the whole conversation and clears
    // it on apply, so an older card's slots are stale once a newer card exists:
    // retire it instead of letting it apply the wrong changes.
    if (openChanges) retireChanges(openChanges, t('ai.changes.superseded'));

    const rows = [];
    const list = el('ul', { class: 'chat-changes__list' });
    // pending_changes accumulates across the conversation, so the card's list
    // position is not the server slot; `change.index` is. Without it the card
    // cannot be applied safely.
    let indexed = true;

    changes.forEach((change, position) => {
      const index = change && Number.isInteger(change.index) ? change.index : position;
      if (!(change && Number.isInteger(change.index))) indexed = false;
      const box = el('input', { type: 'checkbox', class: 'chat-changes__box', checked: true });
      box.checked = true;
      const label = el('label', { class: 'chat-changes__label' }, [
        box,
        el('span', { class: 'chat-changes__text', text: changeTitle(change, position) }),
      ]);
      const item = el('li', { class: 'chat-changes__item' }, [label]);

      const target = firstString(change, ['targetId', 'target_id', 'target', 'nodeId', 'node_id']);
      if (target) {
        const type = firstString(change, ['changeType', 'change_type', 'type', 'kind']).toLowerCase();
        const line = el('p', { class: 'chat-changes__target', dataset: { target: target } });
        line.append(t(type === 'add' ? 'ai.changes.under' : 'ai.changes.node') + ' ', nodeLink(target));
        item.appendChild(line);
      }
      const fields = fieldLines(change, target);
      if (fields.length) item.appendChild(el('ul', { class: 'chat-changes__fields' }, fields));
      // What approving this does to the node's links, in words: the links in
      // a suggestion replace the node's whole list, so a removal is as much
      // part of it as an addition, and neither is visible in a title.
      const links = linkLines(change);
      if (links.length) {
        const box = el('ul', { class: 'chat-changes__links' });
        for (const line of links) {
          box.appendChild(
            el('li', { class: 'chat-changes__link chat-changes__link--' + line.kind, dataset: { kind: line.kind }, text: line.text })
          );
        }
        item.appendChild(box);
      }
      if (change && typeof change.data === 'string' && change.data !== '') {
        // Data that is not an object cannot be read field by field.
        item.appendChild(el('p', { class: 'chat-changes__target', text: change.data }));
      }

      rows.push({ index, box });
      list.appendChild(item);
    });

    const status = el('p', { class: 'chat-changes__status', role: 'status', 'aria-live': 'polite' });
    const applyBtn = el('button', { type: 'button', class: 'btn btn--primary', text: t('ai.changes.apply') });
    const dismissBtn = el('button', { type: 'button', class: 'btn', text: t('ai.changes.dismiss') });

    const card = el('section', { class: 'chat-changes' }, [
      el('h3', { class: 'chat-changes__title', text: t('ai.changes.title') }),
      el('p', { class: 'chat-changes__hint', text: t('ai.changes.hint') }),
      list,
      el('div', { class: 'chat-changes__foot' }, [applyBtn, dismissBtn]),
      status,
    ]);

    const handle = { card: card, rows: rows, status: status, buttons: [applyBtn, dismissBtn] };
    if (!indexed) {
      applyBtn.disabled = true;
      applyBtn.title = t('ai.changes.unindexed');
      status.textContent = t('ai.changes.unindexed');
    }
    applyBtn.addEventListener('click', () => applyChanges(handle, changes.length));
    dismissBtn.addEventListener('click', () => {
      retireChanges(handle, t('ai.changes.dismissed'));
      if (openChanges === handle) openChanges = null;
    });

    openChanges = handle;
    log.appendChild(card);
    scrollToEnd();
  }

  /** Freeze a card so it can no longer be applied, and say why. */
  function retireChanges(handle, message) {
    handle.card.dataset.retired = 'true';
    for (const row of handle.rows) row.box.disabled = true;
    for (const button of handle.buttons) button.disabled = true;
    handle.status.textContent = message;
  }

  /** One line per rejected suggestion: which one, and the server's reason. */
  function showRejected(rejected) {
    for (const record of rejected) {
      if (!record || typeof record !== 'object') continue;
      const row = say('error', 'ai.changes.rejectedOne', {
        title: changeTitle(record, 0),
        reason: firstString(record, ['message', 'reason']) || '—',
      });
      row.dataset.rejected = 'true';
    }
  }

  async function applyChanges(handle, total) {
    if (busy) {
      handle.status.textContent = t('ai.msg.busy');
      return;
    }
    const indices = handle.rows.filter((row) => row.box.checked).map((row) => row.index);
    if (!indices.length) {
      handle.status.textContent = t('ai.changes.none');
      return;
    }
    if (!ensureConfigured()) return;

    setBusy(true, t('ai.changes.applying'));
    handle.status.textContent = t('ai.changes.applying');
    try {
      const result = await api.post('/ai/changes/apply', { indices: indices });
      if (destroyed) return;
      const applied = appliedCount(result, indices.length);
      await refreshDocument(result);
      retireChanges(handle, t('ai.changes.applied', { n: applied, total: total }));
      if (openChanges === handle) openChanges = null;
      say('system', 'ai.changes.applied', { n: applied, total: total });
      // "Applied" must not claim more than was done. A suggestion is applied
      // whole or not at all: each rejected one is named with the server's
      // reason, and an applied one names the fields a suggestion never
      // changes (children, 1.7 keys) if it carried any.
      for (const record of result && Array.isArray(result.applied) ? result.applied : []) {
        if (record && Array.isArray(record.ignored) && record.ignored.length) {
          say('system', 'ai.changes.ignoredOne', { title: changeTitle(record, 0), fields: record.ignored.join(', ') });
        }
      }
      // One line each, with the server's reason (showRejected). The same
      // records used to follow as a block of raw JSON.
      if (result && Array.isArray(result.rejected) && result.rejected.length) {
        showRejected(result.rejected);
      }
    } catch (err) {
      if (destroyed) return;
      handle.status.textContent = '';
      if (err instanceof ApiError && err.detail && Array.isArray(err.detail.rejected)) {
        // Named one by one; the rest of the detail, if any, as usual.
        showRejected(err.detail.rejected);
        addMessage('error', err.message || String(err));
        const rest = Object.assign({}, err.detail);
        delete rest.rejected;
        showDiagnostics(rest);
      } else {
        handleError(err);
      }
    } finally {
      if (!destroyed) setBusy(false);
    }
  }

  /* ---- Update FTA: what it would do, then Apply or Discard ---- */

  /** Freeze a preview card so it can no longer be applied, and say why. */
  function retireUpdate(handle, message) {
    handle.card.dataset.retired = 'true';
    for (const button of handle.buttons) button.disabled = true;
    handle.status.textContent = message;
    if (openUpdate === handle) openUpdate = null;
  }

  /** Tell the server to forget a preview. Nothing depends on the answer. */
  function forgetUpdate(handle) {
    api.post('/ai/update/discard', { id: handle.id }).catch(() => {});
  }

  /**
   * The answer to a preview request: what the rewrite adds, changes and
   * removes, by name, with Apply and Discard. The tree is untouched until
   * Apply. One click on Update FTA used to replace the whole tree, and the
   * summary came after the fact.
   */
  function renderUpdatePreview(result) {
    const summary = (result && result.updateSummary) || {};
    const lines = [
      ['added', 'ai.update.lineAdded'],
      ['changed', 'ai.update.lineChanged'],
      ['removed', 'ai.update.lineRemoved'],
    ].filter(([key]) => Array.isArray(summary[key]) && summary[key].length);
    const id = result && typeof result.updateId === 'string' ? result.updateId : null;

    if (openUpdate) retireUpdate(openUpdate, t('ai.update.superseded'));
    if (!lines.length || !id) {
      // The model handed the tree back as it was: nothing to decide.
      if (id) api.post('/ai/update/discard', { id }).catch(() => {});
      say('system', 'ai.update.nothing');
      return;
    }

    const list = el('ul', { class: 'chat-changes__list' });
    for (const [key, label] of lines) {
      list.appendChild(el('li', {
        class: 'chat-changes__item chat-update__line',
        dataset: { kind: key },
        text: t(label, { n: summary[key].length, names: previewNames(summary[key]) }),
      }));
    }
    const status = el('p', { class: 'chat-changes__status', role: 'status', 'aria-live': 'polite' });
    const applyBtn = el('button', {
      type: 'button', class: 'btn btn--primary', dataset: { role: 'apply-update' }, text: t('ai.update.apply'),
    });
    const discardBtn = el('button', {
      type: 'button', class: 'btn', dataset: { role: 'discard-update' }, text: t('ai.update.discard'),
    });
    const card = el('section', { class: 'chat-changes chat-update' }, [
      el('h3', { class: 'chat-changes__title', text: t('ai.update.previewTitle') }),
      el('p', { class: 'chat-changes__hint', text: t('ai.update.previewHint') }),
      list,
      el('div', { class: 'chat-changes__foot' }, [applyBtn, discardBtn]),
      status,
    ]);
    const handle = { id, card, status, buttons: [applyBtn, discardBtn] };
    applyBtn.addEventListener('click', () => applyUpdate(handle));
    discardBtn.addEventListener('click', () => {
      forgetUpdate(handle);
      retireUpdate(handle, t('ai.update.discardedStatus'));
      say('system', 'ai.update.discarded');
    });
    openUpdate = handle;
    log.appendChild(card);
    scrollToEnd();
  }

  async function applyUpdate(handle) {
    if (busy) {
      handle.status.textContent = t('ai.msg.busy');
      return;
    }
    setBusy(true, t('ai.update.applying'));
    handle.status.textContent = t('ai.update.applying');
    try {
      const result = await api.post('/ai/update/apply', { id: handle.id });
      if (destroyed) return;
      await refreshDocument(result);
      retireUpdate(handle, t('ai.update.appliedStatus'));
      const summary = updateSummaryMessage(result && result.updateSummary);
      if (summary) say('system', summary.key, summary.vars);
      else say('system', 'ai.msg.updated');
    } catch (err) {
      if (destroyed) return;
      // Refused (the tree was edited since the preview, or the preview is
      // gone): the server has dropped it, so the card cannot be tried again.
      retireUpdate(handle, t('ai.update.notApplied'));
      handleError(err);
    } finally {
      if (!destroyed) setBusy(false);
    }
  }

  /* ---- the four actions ---- */

  /**
   * The two reasons a request must not start, each with the message that
   * explains it: a request already in flight, or nothing configured yet.
   */
  function blocked() {
    if (busy) {
      say('system', 'ai.msg.busy');
      return true;
    }
    return !ensureConfigured();
  }

  /**
   * The busy state and the single catch every request to the provider
   * shares. `work(job)` checks `job.stopped` after each await: Stop cannot
   * call the provider back, so an answer that arrives after it is dropped
   * here. `hooks.onFail` runs when the request failed or was stopped (the
   * typed message goes back into the box), `hooks.late(result)` when an
   * answer arrived after Stop.
   */
  async function run(statusText, work, hooks) {
    const job = { stopped: false, hooks: hooks || {} };
    current = job;
    setBusy(true, statusText);
    try {
      await work(job);
    } catch (err) {
      if (!destroyed && !job.stopped) {
        handleError(err);
        if (job.hooks.onFail) job.hooks.onFail();
      }
    } finally {
      if (!destroyed && current === job) {
        current = null;
        setBusy(false);
      }
    }
  }

  /**
   * Stop waiting. The request cannot be withdrawn from the provider, and the
   * editor's one AI slot stays taken until it answers, so the message says
   * that a new request may be refused for a moment.
   */
  function actionStop() {
    const job = current;
    if (!job) return;
    job.stopped = true;
    current = null;
    setBusy(false);
    if (job.hooks.onFail) job.hooks.onFail();
    say('system', 'ai.msg.stopped');
    input.focus();
  }

  /**
   * @returns {boolean} false when the "reply" is the provider's failure,
   * which the server passes on in-band as text starting "AI Error:". It is
   * shown as an error, not as something the assistant said.
   */
  function showReply(payload) {
    const reply = replyFrom(payload);
    if (reply && reply.trim().indexOf(AI_ERROR_PREFIX) === 0) {
      const row = addMessage('error', reply.trim().slice(AI_ERROR_PREFIX.length).trim() || reply);
      row.dataset.kind = 'ai-error';
      return false;
    }
    if (reply) addMessage('assistant', reply, { reply: true });
    else say('assistant', 'ai.msg.emptyReply');
    return true;
  }

  function actionSend() {
    const text = input.value.trim();
    if (!text) {
      say('system', 'ai.msg.empty');
      input.focus();
      return;
    }
    if (blocked()) return;

    const typed = input.value;
    const row = addMessage('user', text);
    input.value = '';
    // A message that did not get through is not lost: it goes back into the
    // box (unless something else was typed there meanwhile) to send again.
    const giveBack = () => {
      if (input.value.trim() === '') input.value = typed;
      row.dataset.failed = 'true';
    };
    run(t('ai.msg.thinking'), async (job) => {
      const result = await api.post('/ai/chat', { message: text });
      if (destroyed || job.stopped) return;
      if (!showReply(result)) giveBack();
      renderChanges(listFrom(result, ['changes', 'suggestions']));
    }, { onFail: giveBack });
  }

  /**
   * Analyze does not change the document itself, but the server still parses
   * and queues any proposals in the reply; showing the card is what lets the
   * user see (and apply or dismiss) what is now pending.
   */
  function actionAnalyze() {
    if (blocked()) return;
    say('user', modeKey('ai.msg.analyzePrompt'));
    run(t(modeKey('ai.msg.analyzing')), async (job) => {
      const result = await api.post('/ai/analyze', {});
      if (destroyed || job.stopped) return;
      showReply(result);
      renderChanges(listFrom(result, ['changes', 'suggestions']));
    });
  }

  /**
   * Asked first, then previewed. The request sends the whole tree to the AI
   * provider and can take a minute, so one stray click should not start it;
   * and its answer is shown as a summary to accept or refuse (see
   * renderUpdatePreview), not installed.
   */
  function actionUpdate() {
    if (blocked()) return;
    choiceDialog(t('ai.update.confirm'), {
      title: t(modeKey('ai.update.confirmTitle')),
      cancelValue: false,
      buttons: [{ value: true, role: 'ask', label: t('ai.update.confirmOk'), primary: true, focus: true }],
    }).then((go) => {
      if (!go || destroyed || blocked()) return;
      say('user', modeKey('ai.msg.updatePrompt'));
      run(t(modeKey('ai.msg.updating')), async (job) => {
        const result = await api.post('/ai/update', { preview: true });
        if (destroyed) return;
        if (job.stopped) {
          // The preview nobody is waiting for must not stay on the server.
          if (result && typeof result.updateId === 'string') {
            api.post('/ai/update/discard', { id: result.updateId }).catch(() => {});
          }
          return;
        }
        const reply = replyFrom(result);
        if (reply) addMessage('assistant', reply, { reply: true });
        if (result && result.preview) {
          renderUpdatePreview(result);
          return;
        }
        // A server that applied at once (one older than the preview flag).
        await refreshDocument(result);
        const summary = updateSummaryMessage(result && result.updateSummary);
        if (summary) say('system', summary.key, summary.vars);
        else say('system', modeKey('ai.msg.updated'));
      });
    });
  }

  /**
   * Clear the log here and the conversation on the server. A server that
   * refuses because nothing is configured has no history to forget, so the
   * local clear still happens -- the button must never look broken.
   */
  async function actionClear() {
    if (busy) {
      say('system', 'ai.msg.busy');
      return;
    }
    setBusy(true, t('ai.msg.clearing'));
    let failure = null;
    try {
      await api.del('/ai/conversation');
    } catch (err) {
      if (!(err instanceof ApiError && err.code === 'AI_NOT_CONFIGURED')) failure = err;
    } finally {
      if (!destroyed) setBusy(false);
    }
    if (destroyed) return;
    clear(log);
    openChanges = null;
    openUpdate = null; // DELETE /api/ai/conversation dropped it on the server
    notConfiguredRow = null;
    welcomed = false;
    greet();
    if (failure) handleError(failure);
  }

  /* ---- first paint ---- */

  function greet() {
    if (welcomed) return;
    welcomed = true;
    welcomeRow = say('system', modeKey('ai.msg.welcome'));
  }

  /**
   * After a reload: the conversation the server still holds, painted again,
   * with the suggestions and the Update FTA preview that still wait for an
   * answer. The log lived only in the page, so F5 emptied it while the
   * assistant went on remembering every turn.
   */
  async function restore() {
    let saved;
    try {
      saved = await api.get('/ai/conversation');
    } catch (_err) {
      return; // an older server, or no session: the empty log is the truth
    }
    if (destroyed || !saved || typeof saved !== 'object') return;
    // Not over something the user has already started in this page.
    if (busy || log.querySelector('.chat-msg--user, .chat-changes')) return;
    const messages = Array.isArray(saved.messages) ? saved.messages : [];
    const changes = Array.isArray(saved.changes) ? saved.changes : [];
    const update = saved.pendingUpdate && typeof saved.pendingUpdate === 'object' ? saved.pendingUpdate : null;
    if (!messages.length && !changes.length && !update) return;

    const note = say('system', 'ai.msg.restored');
    note.dataset.kind = 'restored';
    for (const message of messages) {
      if (!message || typeof message !== 'object') continue;
      const user = message.role === 'user';
      const text = typeof message.content === 'string' ? message.content : '';
      let row = null;
      if (message.kind === 'analyze' && user) row = say('user', modeKey('ai.msg.analyzePrompt'));
      else if (message.kind === 'update') row = user ? say('user', modeKey('ai.msg.updatePrompt')) : say('system', 'ai.msg.restoredUpdate');
      else if (user) row = addMessage('user', text);
      else if (text) row = addMessage('assistant', text, { reply: true });
      if (row) row.dataset.restored = 'true';
    }
    if (changes.length) renderChanges(changes);
    if (update) renderUpdatePreview({ preview: true, updateId: update.updateId, updateSummary: update.updateSummary });
  }

  /**
   * Configured -> the composer. Not configured -> the invitation above it.
   * Unknown (the server did not report the capability) is treated as usable:
   * accusing a working build of being unconfigured is worse than letting the
   * first request come back with AI_NOT_CONFIGURED, which is handled.
   */
  function render() {
    const configured = aiConfigured();
    if (configured !== lastConfigured) {
      lastConfigured = configured;
      showInvitation(configured === false);
      // Set up since: the "no provider yet" line no longer applies.
      if (configured !== false && notConfiguredRow) {
        notConfiguredRow.remove();
        notConfiguredRow = null;
      }
    }
    // FTA <-> ETA: the buttons and the placeholder name the kind of tree.
    const eta = isEta();
    if (eta !== lastMode) {
      lastMode = eta;
      applyLabels();
      // The welcome line names the buttons, so it follows them.
      if (welcomeRow && welcomeRow.isConnected) {
        const key = modeKey('ai.msg.welcome');
        keyed.set(welcomeRow, { key, vars: undefined });
        const body = welcomeRow.querySelector('.chat-msg__body');
        if (body) body.textContent = t(key);
      }
    }
    greet();
  }

  /* ---- events ---- */

  function onKeydown(event) {
    if (event.key !== 'Enter' || event.shiftKey) return;
    // Enter sends, Shift+Enter starts a new line -- the desktop binding
    // (src/FTA_Editor_UI.py:305-306). IME composition must not be interrupted.
    if (event.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    actionSend();
  }

  input.addEventListener('keydown', onKeydown);
  composer.addEventListener('submit', (event) => {
    event.preventDefault();
    actionSend();
  });

  const onLanguage = () => {
    applyLabels();
    relabelLog();
  };
  window.addEventListener('fta:language', onLanguage);

  // New / Open: a preview made for the previous document cannot be applied
  // to this one (the server would refuse it), so the card says so now.
  const onDocument = () => {
    // Suggestions too: they name nodes of the document that was open, and
    // ids such as root_0 recur from file to file. The card stayed live after
    // New or Load and offered to apply them to the new tree.
    if (openChanges) {
      retireChanges(openChanges, t('ai.changes.otherDocument'));
      openChanges = null;
    }
    if (!openUpdate) return;
    forgetUpdate(openUpdate);
    retireUpdate(openUpdate, t('ai.update.otherDocument'));
  };
  window.addEventListener('fta:document', onDocument);

  applyLabels();
  const unsubscribe = store.subscribe(render);
  render();
  restore();

  return {
    refresh: render,
    destroy() {
      destroyed = true;
      if (typeof unsubscribe === 'function') unsubscribe();
      window.removeEventListener('fta:language', onLanguage);
      window.removeEventListener('fta:document', onDocument);
      clear(host);
    },
  };
}

export default initChat;
