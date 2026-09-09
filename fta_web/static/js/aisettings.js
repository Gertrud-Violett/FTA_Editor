/**
 * aisettings.js -- "set up the AI assistant" in one dialog.
 *
 * WHAT THE FIRST RUN HAS TO FEEL LIKE
 * ===================================
 * Someone who has never used an API key must be able to finish this dialog.
 * Everything here follows from that:
 *
 *   * Provider first. Picking one fills in its endpoint and its model list, so
 *     nobody has to know that an endpoint URL exists. The endpoint is real and
 *     editable, but it lives under "Advanced" where it cannot intimidate.
 *   * Every provider says where its keys come from, as a plain link to that
 *     provider's own console. The link text is the URL itself: it navigates,
 *     nothing is loaded from it, and a user who cannot click it can still read
 *     and type it. Google's free tier is called out because it is the
 *     lowest-friction way to try the feature at all.
 *   * The model field is an editable combo, never a closed dropdown. The
 *     suggestions come from /api/ai/models, but a model released the week after
 *     this build shipped must still be typeable, and it is.
 *   * One primary action, "Test & Save", which calls the provider first and
 *     stores nothing unless that call succeeded. A key that is saved but broken
 *     turns every later feature into a mystery; a key that is refused here
 *     comes with the provider's own words about why.
 *
 * THE ALREADY-CONFIGURED CASE
 * ---------------------------
 * GET /api/ai/credentials never returns the key -- only a preview of it. So a
 * configured dialog opens with the key box EMPTY and the preview shown beside
 * it. That way an accidental "Test & Save" cannot overwrite a working key with
 * an empty string; instead the dialog says the stored key cannot be read back
 * and asks for it again, and Cancel leaves everything untouched.
 *
 * BACKEND (fta_web/routes/ai.py)
 *   GET    /api/ai/providers                     [{name, defaultEndpoint, defaultModels}]
 *   GET    /api/ai/models?provider=&endpoint=    live list, or the defaults plus
 *                                                {warning, source:"fallback"}
 *   GET    /api/ai/credentials                   {configured, provider, endpoint,
 *                                                 model, keyPreview}
 *   POST   /api/ai/credentials                   {provider, apiKey, endpoint, model}
 *   DELETE /api/ai/credentials                   forget them
 *
 * CONTRACT
 *   openAiSettings() -> Promise<{saved: boolean, cleared: boolean} | null>
 *                       null when the dialog was cancelled.
 *
 * Escape cancels, Enter submits, Tab is trapped inside the dialog and focus
 * returns to whatever opened it -- the rules dialogs.js's modals follow,
 * reimplemented here because createModal is private to that module.
 */
import { api, ApiError } from './api.js';
import { store } from './store.js';
import { clear, confirmDialog, el, uid } from './dialogs.js';

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

function toast(message, kind) {
  const shell = window.ftaShell;
  if (shell && typeof shell.toast === 'function') shell.toast(message, kind || 'info');
}

/* --------------------------------------------------------- provider facts -- */

/**
 * What this file knows about a provider that the server does not send: its
 * display name, where a human gets a key, and what that costs.
 *
 * `match` is checked against the lower-cased server name, so "openai",
 * "OpenAI", "anthropic", "Anthropic Claude", "google" and "Google Gemini" all
 * land on the right row. A provider the server offers and this table does not
 * know still works -- it simply shows its own name and no console link, which
 * is honest rather than wrong.
 */
const PROVIDER_META = [
  {
    match: ['anthropic', 'claude'],
    label: 'ai.provider.anthropic',
    hint: 'ai.hint.anthropic',
    url: 'https://console.anthropic.com/settings/keys',
  },
  {
    match: ['google', 'gemini', 'aistudio'],
    label: 'ai.provider.google',
    hint: 'ai.hint.google',
    url: 'https://aistudio.google.com/apikey',
  },
  {
    match: ['openai', 'gpt'],
    label: 'ai.provider.openai',
    hint: 'ai.hint.openai',
    url: 'https://platform.openai.com/api-keys',
  },
];

function metaFor(name) {
  const lower = String(name || '').toLowerCase();
  for (const meta of PROVIDER_META) {
    if (meta.match.some((needle) => lower.indexOf(needle) !== -1)) return meta;
  }
  return null;
}

function providerLabel(entry) {
  const meta = metaFor(entry.name);
  return meta ? t(meta.label) : String(entry.name);
}

/* ------------------------------------------------------------- payloads ---- */

/**
 * Pull a list out of a response without betting on one field name. api.js
 * rejects a bare JSON array, so the server has to wrap its list in an object;
 * this reads the documented key first and any array-valued field after, so a
 * rename on the backend degrades to "still works" rather than "silently empty".
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

/** Normalise one /api/ai/providers row. */
function readProvider(raw) {
  if (typeof raw === 'string') return { name: raw, endpoint: '', models: [] };
  if (!raw || typeof raw !== 'object') return null;
  const name = raw.name || raw.provider || raw.id || '';
  if (!name) return null;
  return {
    name: String(name),
    endpoint: String(raw.defaultEndpoint || raw.default_endpoint || raw.endpoint || ''),
    models: listFrom(raw, ['defaultModels', 'default_models', 'models']).map(String),
  };
}

function stringsFrom(list) {
  const out = [];
  for (const item of list) {
    if (typeof item === 'string' && item.trim()) out.push(item.trim());
    else if (item && typeof item === 'object') {
      const name = item.id || item.name || item.model;
      if (name) out.push(String(name));
    }
  }
  return out;
}

/* ----------------------------------------------------------------- modal ---- */

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  'summary',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

/**
 * Open the setup dialog.
 *
 * @returns {Promise<{saved: boolean, cleared: boolean}|null>}
 */
export function openAiSettings() {
  const trigger = document.activeElement;
  const titleId = uid('aiset-title');
  const keyId = uid('aiset-key');
  const modelId = uid('aiset-model');
  const modelListId = uid('aiset-models');
  const endpointId = uid('aiset-endpoint');
  const providerLabelId = uid('aiset-providers');
  const radioName = uid('aiset-provider');

  /* ---- fields ---- */

  const heading = el('h2', { class: 'fta-modal-title', id: titleId, text: t('ai.settings.title') });
  const intro = el('p', { class: 'aiset-intro', text: t('ai.settings.intro') });

  const providerList = el('div', {
    class: 'aiset-providers',
    role: 'radiogroup',
    'aria-labelledby': providerLabelId,
  });
  const providerBlock = el('div', { class: 'aiset-block' }, [
    el('p', { class: 'field-label', id: providerLabelId, text: t('ai.field.provider') }),
    providerList,
  ]);

  const keyInput = el('input', {
    type: 'password',
    class: 'aiset-key__input',
    id: keyId,
    autocomplete: 'off',
    autocapitalize: 'off',
    autocorrect: 'off',
    spellcheck: 'false',
    placeholder: t('ai.key.placeholder'),
  });
  const keyToggle = el('button', {
    type: 'button',
    class: 'btn aiset-key__toggle',
    text: t('ai.key.show'),
    'aria-pressed': 'false',
  });
  const keyNote = el('p', { class: 'aiset-note', hidden: true });
  const keyLink = el('p', { class: 'aiset-note aiset-note--link', hidden: true });
  const keyBlock = el('div', { class: 'aiset-block' }, [
    el('label', { class: 'field-label', for: keyId, text: t('ai.field.key') }),
    el('div', { class: 'aiset-key' }, [keyInput, keyToggle]),
    keyNote,
    keyLink,
  ]);

  const modelInput = el('input', {
    type: 'text',
    class: 'aiset-model__input',
    id: modelId,
    list: modelListId,
    autocomplete: 'off',
    spellcheck: 'false',
    placeholder: t('ai.model.placeholder'),
  });
  const modelOptions = el('datalist', { id: modelListId });
  const modelRefresh = el('button', {
    type: 'button',
    class: 'btn aiset-model__refresh',
    text: t('ai.model.refresh'),
    title: t('ai.model.refreshTitle'),
  });
  const modelNote = el('p', { class: 'aiset-note' });
  const modelBlock = el('div', { class: 'aiset-block' }, [
    el('label', { class: 'field-label', for: modelId, text: t('ai.field.model') }),
    el('div', { class: 'aiset-model' }, [modelInput, modelOptions, modelRefresh]),
    modelNote,
  ]);

  const endpointInput = el('input', {
    type: 'text',
    class: 'aiset-endpoint__input',
    id: endpointId,
    autocomplete: 'off',
    spellcheck: 'false',
  });
  const advanced = el('details', { class: 'aiset-advanced' }, [
    el('summary', { class: 'aiset-advanced__summary', text: t('ai.field.advanced') }),
    el('div', { class: 'aiset-block' }, [
      el('label', { class: 'field-label', for: endpointId, text: t('ai.field.endpoint') }),
      endpointInput,
      el('p', { class: 'aiset-note', text: t('ai.endpoint.hint') }),
    ]),
  ]);

  const status = el('p', {
    class: 'aiset-status',
    role: 'status',
    'aria-live': 'polite',
    dataset: { kind: 'idle' },
  });

  const form = el('div', { class: 'aiset-form', hidden: true }, [
    intro,
    providerBlock,
    keyBlock,
    modelBlock,
    advanced,
  ]);
  const loading = el('p', { class: 'aiset-loading', text: t('ai.settings.loading') });

  const body = el('div', { class: 'fta-modal-body aiset-body' }, [loading, form, status]);

  const clearButton = el('button', {
    type: 'button',
    class: 'btn btn--danger aiset-clear',
    text: t('ai.btn.clear'),
    hidden: true,
  });
  const cancelButton = el('button', { type: 'button', class: 'btn', text: t('ai.btn.cancel') });
  const saveButton = el('button', {
    type: 'button',
    class: 'btn btn--primary',
    text: t('ai.btn.testSave'),
    disabled: true,
  });
  const footer = el('div', { class: 'fta-modal-footer aiset-foot' }, [
    clearButton,
    cancelButton,
    saveButton,
  ]);

  const dialog = el(
    'div',
    {
      class: 'fta-modal aiset',
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
  const overlay = el('div', { class: 'fta-modal-overlay', dataset: { ftaModal: 'open' } }, [dialog]);

  /* ---- lifecycle ---- */

  let settle;
  const done = new Promise((resolve) => {
    settle = resolve;
  });
  let closed = false;
  let busy = false;
  let closeTimer = 0;

  function close(value) {
    if (closed) return;
    closed = true;
    if (closeTimer) window.clearTimeout(closeTimer);
    document.removeEventListener('keydown', onKeydown, true);
    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    if (trigger && typeof trigger.focus === 'function' && trigger.isConnected) trigger.focus();
    settle(value === undefined ? null : value);
  }

  /* ---- state ---- */

  let providers = [];
  let selected = null; // the provider row currently ticked
  let saved = { configured: false, provider: '', endpoint: '', model: '', keyPreview: '' };

  function setStatus(message, kind) {
    status.textContent = message || '';
    status.dataset.kind = message ? kind || 'info' : 'idle';
  }

  function setNote(target, message, kind) {
    target.textContent = message || '';
    target.hidden = !message;
    target.dataset.kind = kind || 'info';
  }

  function setBusy(next, message) {
    busy = Boolean(next);
    dialog.dataset.busy = busy ? 'true' : 'false';
    saveButton.disabled = busy || !selected;
    clearButton.disabled = busy;
    modelRefresh.disabled = busy;
    for (const input of [keyInput, modelInput, endpointInput]) input.readOnly = busy;
    if (message) setStatus(message, 'busy');
  }

  /* ---- providers ---- */

  function buildProviderCard(entry) {
    const meta = metaFor(entry.name);
    const radio = el('input', {
      type: 'radio',
      name: radioName,
      value: entry.name,
      class: 'aiset-provider__radio',
    });
    const card = el('div', { class: 'aiset-provider', dataset: { selected: 'false' } }, [
      el('label', { class: 'aiset-provider__pick' }, [
        radio,
        el('span', { class: 'aiset-provider__name', text: providerLabel(entry) }),
      ]),
    ]);
    if (meta) {
      card.appendChild(el('p', { class: 'aiset-provider__hint', text: t(meta.hint) }));
      // A plain hyperlink to the provider's own console: it navigates, it loads
      // nothing. The URL is its own link text so it can be read or typed.
      card.appendChild(
        el('p', { class: 'aiset-provider__where' }, [
          el('span', { text: t('ai.key.where') + ' ' }),
          el('a', {
            class: 'aiset-provider__link',
            href: meta.url,
            target: '_blank',
            rel: 'noopener noreferrer',
            text: meta.url,
          }),
        ])
      );
    }
    radio.addEventListener('change', () => {
      if (radio.checked) selectProvider(entry, { fromUser: true });
    });
    entry.card = card;
    entry.radio = radio;
    return card;
  }

  /**
   * Tick a provider and fill everything that depends on it.
   *
   * Endpoint and model are always rewritten from the provider's own defaults --
   * an endpoint left over from another provider is never valid -- except that
   * re-selecting the configured provider restores what was actually saved.
   */
  function selectProvider(entry, options) {
    selected = entry;
    for (const row of providers) {
      const on = row === entry;
      if (row.radio) row.radio.checked = on;
      if (row.card) row.card.dataset.selected = on ? 'true' : 'false';
    }

    const isSavedProvider =
      saved.configured && String(saved.provider || '').toLowerCase() === entry.name.toLowerCase();

    endpointInput.value = (isSavedProvider && saved.endpoint) || entry.endpoint || '';
    fillModels(entry.models, isSavedProvider ? saved.model : entry.models[0] || '');

    if (isSavedProvider) {
      setNote(modelNote, t('ai.model.hint'), 'info');
      // The live list needs the stored key, which only exists for this
      // provider, so this is the one case where fetching now can succeed.
      if (!options || options.fromUser !== false) refreshModels({ quiet: true });
    } else {
      setNote(modelNote, t('ai.model.needKey'), 'info');
    }

    saveButton.disabled = busy;
    updateKeyNote();
  }

  function fillModels(models, chosen) {
    clear(modelOptions);
    for (const model of models) modelOptions.appendChild(el('option', { value: model }));
    modelInput.value = chosen || models[0] || '';
  }

  function updateKeyNote() {
    if (!saved.configured) {
      setNote(keyNote, '');
      setNote(keyLink, '');
      return;
    }
    const sameProvider =
      selected && String(saved.provider || '').toLowerCase() === selected.name.toLowerCase();
    if (!sameProvider) {
      setNote(keyNote, t('ai.key.savedOther', { provider: saved.provider || '' }), 'info');
      return;
    }
    setNote(
      keyNote,
      saved.keyPreview
        ? t('ai.key.saved', { preview: saved.keyPreview })
        : t('ai.key.savedNoPreview'),
      'info'
    );
  }

  /* ---- models ---- */

  /**
   * Ask the server for the live list. It answers with the provider's real
   * models when it can and with this build's defaults plus a `warning` when it
   * cannot; a fallback list is labelled as one rather than presented as
   * authoritative, because the whole point of the editable field is that the
   * defaults go stale.
   */
  async function refreshModels(options) {
    if (!selected || busy) return;
    const quiet = Boolean(options && options.quiet);
    const provider = selected.name;
    const endpoint = endpointInput.value.trim();
    modelRefresh.disabled = true;
    if (!quiet) setNote(modelNote, t('ai.model.loading'), 'info');
    try {
      const payload = await api.get(
        '/ai/models?provider=' +
          encodeURIComponent(provider) +
          (endpoint ? '&endpoint=' + encodeURIComponent(endpoint) : '')
      );
      if (closed || !selected || selected.name !== provider) return;
      const models = stringsFrom(listFrom(payload, ['models', 'defaultModels', 'default_models']));
      if (models.length) fillModels(models, modelInput.value.trim() || models[0]);
      const warning = payload && payload.warning ? String(payload.warning) : '';
      const fallback = (payload && payload.source === 'fallback') || Boolean(warning);
      if (fallback) {
        setNote(
          modelNote,
          warning ? t('ai.model.fallback', { warning: warning }) : t('ai.model.fallbackPlain'),
          'warn'
        );
      } else {
        setNote(modelNote, t('ai.model.live'), 'ok');
      }
    } catch (err) {
      if (closed) return;
      if (err instanceof ApiError && err.code === 'AI_NOT_CONFIGURED') {
        setNote(modelNote, t('ai.model.needKey'), 'info');
        return;
      }
      setNote(modelNote, t('ai.model.failed', { error: errorText(err) }), 'warn');
    } finally {
      if (!closed) modelRefresh.disabled = busy;
    }
  }

  function errorText(err) {
    if (err && typeof err.message === 'string' && err.message) return err.message;
    return String(err);
  }

  /* ---- test & save ---- */

  async function testAndSave() {
    if (busy || closed) return;
    if (!selected) {
      setStatus(t('ai.err.provider'), 'error');
      return;
    }
    const key = keyInput.value.trim();
    const model = modelInput.value.trim();
    const endpoint = endpointInput.value.trim();

    if (!key) {
      // Never post an empty key: on a configured editor that would ask the
      // server to replace a working key with nothing.
      setStatus(saved.configured ? t('ai.err.keyAgain') : t('ai.err.key'), 'error');
      keyInput.focus();
      return;
    }
    if (!endpoint) {
      setStatus(t('ai.err.endpoint'), 'error');
      advanced.open = true;
      endpointInput.focus();
      return;
    }
    if (!model) {
      setStatus(t('ai.err.model'), 'error');
      modelInput.focus();
      return;
    }

    setBusy(true, t('ai.status.testing', { provider: providerLabel(selected) }));
    try {
      await api.post('/ai/credentials', {
        provider: selected.name,
        apiKey: key,
        endpoint: endpoint,
        model: model,
      });
      if (closed) return;
      setBusy(false);
      setStatus(t('ai.status.saved'), 'ok');
      keyInput.value = '';
      await refreshShell();
      toast(t('ai.status.saved'), 'ok');
      // Held open briefly so the success is read, not just flashed.
      closeTimer = window.setTimeout(() => close({ saved: true, cleared: false }), 900);
    } catch (err) {
      if (closed) return;
      setBusy(false);
      // The provider's own words. A wrong key, a wrong model name and a
      // firewalled endpoint fail differently, and only the server knows how.
      setStatus(errorText(err), 'error');
      keyInput.focus();
    }
  }

  async function clearCredentials() {
    if (busy || closed) return;
    const yes = await confirmDialog(t('ai.confirm.clear'), {
      title: t('ai.confirm.clearTitle'),
      confirmLabel: t('ai.btn.clear'),
      cancelLabel: t('ai.btn.cancel'),
    });
    if (!yes || closed) return;
    setBusy(true, t('ai.status.clearing'));
    try {
      await api.del('/ai/credentials');
      if (closed) return;
      setBusy(false);
      await refreshShell();
      toast(t('ai.status.cleared'), 'info');
      close({ saved: false, cleared: true });
    } catch (err) {
      if (closed) return;
      setBusy(false);
      setStatus(errorText(err), 'error');
    }
  }

  /**
   * Re-read /api/state so `aiConfigured` is current everywhere: the panel's
   * status dot, the capability chip and the chat panel all follow the store.
   */
  async function refreshShell() {
    const shell = window.ftaShell;
    try {
      if (shell && typeof shell.refresh === 'function') await shell.refresh();
      else store.setState(await api.get('/state'));
    } catch (_err) {
      /* The credentials did change; a stale indicator is not worth an alarm. */
    }
  }

  /* ---- keyboard ---- */

  function focusableIn(root) {
    return Array.from(root.querySelectorAll(FOCUSABLE)).filter(
      (node) => node.getClientRects().length > 0
    );
  }

  function isTopMost() {
    const overlays = document.querySelectorAll('.fta-modal-overlay');
    return !overlays.length || overlays[overlays.length - 1] === overlay;
  }

  function onKeydown(event) {
    // Only the top-most modal reacts, so the clear confirmation's Escape cannot
    // also close this dialog underneath it.
    if (!isTopMost()) return;

    if (!overlay.contains(event.target) && event.key !== 'Escape') {
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

    if (event.key === 'Enter') {
      const target = event.target;
      const tag = target && target.tagName ? target.tagName.toLowerCase() : '';
      // Buttons, links and the Advanced twisty keep Enter for themselves.
      if (tag === 'button' || tag === 'a' || tag === 'summary' || tag === 'textarea') return;
      event.preventDefault();
      testAndSave();
    }
  }

  /* ---- wiring ---- */

  keyToggle.addEventListener('click', () => {
    const show = keyInput.type === 'password';
    keyInput.type = show ? 'text' : 'password';
    keyToggle.textContent = show ? t('ai.key.hide') : t('ai.key.show');
    keyToggle.setAttribute('aria-pressed', show ? 'true' : 'false');
    keyInput.focus();
  });
  keyInput.addEventListener('input', () => {
    if (status.dataset.kind === 'error') setStatus('');
  });
  modelRefresh.addEventListener('click', () => refreshModels({ quiet: false }));
  saveButton.addEventListener('click', () => testAndSave());
  cancelButton.addEventListener('click', () => close(null));
  clearButton.addEventListener('click', () => clearCredentials());

  document.addEventListener('keydown', onKeydown, true);
  document.body.appendChild(overlay);
  dialog.focus();

  /* ---- load ---- */

  (async () => {
    const [providerResult, credentialResult] = await Promise.allSettled([
      api.get('/ai/providers'),
      api.get('/ai/credentials'),
    ]);
    if (closed) return;

    if (credentialResult.status === 'fulfilled') {
      const payload = credentialResult.value || {};
      saved = {
        configured: Boolean(payload.configured),
        provider: String(payload.provider || ''),
        endpoint: String(payload.endpoint || ''),
        model: String(payload.model || ''),
        keyPreview: String(payload.keyPreview || payload.key_preview || ''),
      };
    }

    if (providerResult.status !== 'fulfilled') {
      // Nothing sensible can be offered without the server's provider table:
      // the endpoints and the model defaults both live there. Say so, and let
      // the dialog be retried rather than inventing addresses here.
      loading.hidden = true;
      setStatus(t('ai.err.providers', { error: errorText(providerResult.reason) }), 'error');
      cancelButton.focus();
      return;
    }

    providers = listFrom(providerResult.value, ['providers', 'items'])
      .map(readProvider)
      .filter(Boolean);

    if (!providers.length) {
      loading.hidden = true;
      setStatus(t('ai.err.noProviders'), 'error');
      cancelButton.focus();
      return;
    }

    clear(providerList);
    for (const entry of providers) providerList.appendChild(buildProviderCard(entry));

    loading.hidden = true;
    form.hidden = false;
    clearButton.hidden = !saved.configured;

    const configured =
      saved.configured &&
      providers.find((row) => row.name.toLowerCase() === String(saved.provider).toLowerCase());
    selectProvider(configured || providers[0], { fromUser: false });
    saveButton.disabled = false;

    if (saved.configured) {
      setStatus(
        t('ai.current', {
          provider: configured ? providerLabel(configured) : saved.provider,
          model: saved.model || t('ai.model.unset'),
        }),
        'info'
      );
      // Already set up: the key box is the only thing that has to be re-typed.
      keyInput.focus();
      if (configured) refreshModels({ quiet: true });
    } else if (selected && selected.radio) {
      // First run: start on the provider choice, which is the first decision.
      selected.radio.focus();
    }
  })().catch((err) => {
    if (closed) return;
    loading.hidden = true;
    setStatus(errorText(err), 'error');
  });

  return done;
}

export default openAiSettings;
