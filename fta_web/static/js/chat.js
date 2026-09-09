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
 *   * a reviewable list whenever the assistant proposes `changes`.
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
 *   POST   /api/ai/update          -> generate, verify, apply
 *   POST   /api/ai/changes/apply   {indices:[...]}
 *   DELETE /api/ai/conversation    clear the history
 * Any of them answers 400 AI_NOT_CONFIGURED while no key is stored.
 *
 * CONTRACT
 *   initChat(host) -> {refresh(), destroy()}
 */
import { api, ApiError } from './api.js';
import { store } from './store.js';
import { clear, el } from './dialogs.js';

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
  const busyBar = el('div', { class: 'chat__busy', role: 'status', 'aria-live': 'polite', hidden: true }, [
    el('span', { class: 'chat__spinner', 'aria-hidden': 'true' }),
    busyText,
  ]);

  const analyzeBtn = el('button', { type: 'button', class: 'btn chat__action', onclick: () => actionAnalyze() });
  const updateBtn = el('button', { type: 'button', class: 'btn chat__action', onclick: () => actionUpdate() });
  const clearBtn = el('button', {
    type: 'button',
    class: 'btn btn--danger chat__action chat__action--end',
    onclick: () => actionClear(),
  });
  const actions = el('div', { class: 'chat__actions' }, [analyzeBtn, updateBtn, clearBtn]);

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

  /* ---- labels (re-applied on every EN/JA switch) ---- */

  function applyLabels() {
    inviteTitle.textContent = t('ai.invite.title');
    inviteBody.textContent = t('ai.invite.body');
    inviteFree.textContent = t('ai.invite.free');
    inviteButton.textContent = t('ai.invite.button');

    log.setAttribute('aria-label', t('ai.chat.log'));

    analyzeBtn.textContent = t('ai.chat.analyze');
    analyzeBtn.title = t('ai.chat.analyzeTitle');
    updateBtn.textContent = t('ai.chat.update');
    updateBtn.title = t('ai.chat.updateTitle');
    clearBtn.textContent = t('ai.chat.clear');
    clearBtn.title = t('ai.chat.clearTitle');

    input.setAttribute('aria-label', t('ai.chat.input'));
    input.placeholder = t('ai.chat.placeholder');
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
  function addMessage(role, text) {
    const kind = ROLE_KEY[role] ? role : 'system';
    const body = el('div', { class: 'chat-msg__body' });
    body.textContent = String(text === null || text === undefined ? '' : text);
    const row = el('div', { class: 'chat-msg chat-msg--' + kind, dataset: { role: kind } }, [
      el('span', { class: 'chat-msg__role', text: t(ROLE_KEY[kind]) }),
      body,
    ]);
    log.appendChild(row);
    scrollToEnd();
    return row;
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
    if (!event.defaultPrevented) addMessage('error', t('ai.err.noSettings'));
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
  function ensureConfigured() {
    if (aiConfigured() === false) {
      showInvitation(true);
      addMessage('system', t('ai.msg.notConfigured'));
      return false;
    }
    return true;
  }

  function handleError(err) {
    if (err instanceof ApiError && err.code === 'AI_NOT_CONFIGURED') {
      showInvitation(true);
      addMessage('system', t('ai.msg.notConfigured'));
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

  function changeTitle(change, index) {
    const type = firstString(change, ['changeType', 'change_type', 'type', 'kind']);
    const description = firstString(change, ['description', 'summary', 'detail', 'text']);
    const head = type ? '[' + type.toUpperCase() + '] ' : '';
    return head + (description || t('ai.changes.untitled', { n: index + 1 }));
  }

  /**
   * The review list. Every box starts ticked, matching the desktop dialog
   * (src/FTA_Editor_UI.py:651) -- the assistant's whole set is the proposal, and
   * unticking is how a user disagrees with part of it.
   */
  function renderChanges(changes) {
    if (!Array.isArray(changes) || !changes.length) return;

    // Indices are positions in the server's newest suggestion list. An older
    // card's indices point into a list the server has since replaced, so
    // applying one would apply the wrong changes: retire it instead.
    if (openChanges) retireChanges(openChanges, t('ai.changes.superseded'));

    const rows = [];
    const list = el('ul', { class: 'chat-changes__list' });

    changes.forEach((change, index) => {
      const box = el('input', { type: 'checkbox', class: 'chat-changes__box', checked: true });
      box.checked = true;
      const label = el('label', { class: 'chat-changes__label' }, [
        box,
        el('span', { class: 'chat-changes__text', text: changeTitle(change, index) }),
      ]);
      const item = el('li', { class: 'chat-changes__item' }, [label]);

      const target = firstString(change, ['targetId', 'target_id', 'target', 'nodeId', 'node_id']);
      if (target) {
        item.appendChild(el('p', { class: 'chat-changes__target', text: t('ai.changes.target', { id: target }) }));
      }
      if (change && change.data !== null && change.data !== undefined && change.data !== '') {
        const pre = el('pre', { class: 'chat-block__pre' });
        pre.textContent = typeof change.data === 'string' ? change.data : safeJson(change.data);
        item.appendChild(
          el('details', { class: 'chat-block chat-block--inline' }, [
            el('summary', { class: 'chat-block__summary', text: t('ai.changes.details') }),
            pre,
          ])
        );
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
      const applied = Number.isFinite(Number(result && result.applied))
        ? Number(result.applied)
        : indices.length;
      await refreshDocument(result);
      retireChanges(handle, t('ai.changes.applied', { n: applied, total: total }));
      if (openChanges === handle) openChanges = null;
      addMessage('system', t('ai.changes.applied', { n: applied, total: total }));
    } catch (err) {
      if (destroyed) return;
      handle.status.textContent = '';
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
      addMessage('system', t('ai.msg.busy'));
      return true;
    }
    return !ensureConfigured();
  }

  /** The busy state and the single catch every request shares. */
  async function run(statusText, work) {
    setBusy(true, statusText);
    try {
      await work();
    } catch (err) {
      if (!destroyed) handleError(err);
    } finally {
      if (!destroyed) setBusy(false);
    }
  }

  function showReply(payload) {
    const reply = replyFrom(payload);
    addMessage('assistant', reply || t('ai.msg.emptyReply'));
  }

  function actionSend() {
    const text = input.value.trim();
    if (!text) {
      addMessage('system', t('ai.msg.empty'));
      input.focus();
      return;
    }
    if (blocked()) return;

    addMessage('user', text);
    input.value = '';
    run(t('ai.msg.thinking'), async () => {
      const result = await api.post('/ai/chat', { message: text });
      if (destroyed) return;
      showReply(result);
      renderChanges(listFrom(result, ['changes', 'suggestions']));
    });
  }

  /** Analyze is read-only by contract, so suggestions are not offered here. */
  function actionAnalyze() {
    if (blocked()) return;
    addMessage('user', t('ai.msg.analyzePrompt'));
    run(t('ai.msg.analyzing'), async () => {
      const result = await api.post('/ai/analyze', {});
      if (destroyed) return;
      showReply(result);
    });
  }

  function actionUpdate() {
    if (blocked()) return;
    addMessage('user', t('ai.msg.updatePrompt'));
    run(t('ai.msg.updating'), async () => {
      const result = await api.post('/ai/update', {});
      if (destroyed) return;
      const reply = replyFrom(result);
      if (reply) addMessage('assistant', reply);
      await refreshDocument(result);
      addMessage('system', t('ai.msg.updated'));
    });
  }

  /**
   * Clear the log here and the conversation on the server. A server that
   * refuses because nothing is configured has no history to forget, so the
   * local clear still happens -- the button must never look broken.
   */
  async function actionClear() {
    if (busy) {
      addMessage('system', t('ai.msg.busy'));
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
    welcomed = false;
    greet();
    if (failure) handleError(failure);
  }

  /* ---- first paint ---- */

  function greet() {
    if (welcomed) return;
    welcomed = true;
    addMessage('system', t('ai.msg.welcome'));
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

  const onLanguage = () => applyLabels();
  window.addEventListener('fta:language', onLanguage);

  applyLabels();
  const unsubscribe = store.subscribe(render);
  render();

  return {
    refresh: render,
    destroy() {
      destroyed = true;
      if (typeof unsubscribe === 'function') unsubscribe();
      window.removeEventListener('fta:language', onLanguage);
      clear(host);
    },
  };
}

export default initChat;
