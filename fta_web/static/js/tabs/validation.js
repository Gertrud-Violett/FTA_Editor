/**
 * tabs/validation.js -- the Validation tab (1.7 workstream E).
 *
 * Visible in basic and advanced mode: it is the junior engineer's safety net,
 * so every issue carries a plain-language message and a one-line "how to fix".
 *
 * Data: GET /api/analysis/validate -> {issues: [{severity, code, nodeId,
 * message, params}], counts, mode}. The rules and severities live in
 * fta_web/lint.py. Messages are localised through `val.code.<CODE>` (with
 * `{param}` interpolation, falling back to the server's English message) and
 * hints through `val.fix.<CODE>`; see i18n/val.js.
 *
 * Refresh: on activate, on the "Re-check" button, and 400 ms after the host
 * reports the tree/analysis changed (onStale). A newer request always wins.
 *
 * "Dismiss session notices" hides the LOAD_REPAIR / LINKS_REMOVED entries
 * present at that moment, client-side only; new notices still appear.
 */
import catalog from '../i18n/val.js';
import { injectStyles } from '../dialogs.js';

export const id = 'validation';
export const advanced = false;

const SEVERITIES = ['error', 'warning', 'info'];
const ICONS = { error: '✖', warning: '⚠', info: 'ℹ' };
const SESSION_CODES = new Set(['LOAD_REPAIR', 'LINKS_REMOVED']);
/** Codes whose fix needs a control that only exists with Advanced on. */
const ADVANCED_CODES = new Set([
  'TRANSFER_MISSING',
  'TRANSFER_CYCLE',
  'TRANSFER_HAS_CHILDREN',
  'HOUSE_HAS_CHILDREN',
  'INHIBIT_ARITY',
  'KOFN_ARITY',
  'XOR_ARITY',
  'QUANT_PARAM_MISSING',
  'STANDBY_LARGE_LT',
  'NONCOHERENT_XOR',
  'CUTSETS_TRUNCATED',
  'PAND_APPROX',
  'UNDEVELOPED_EVENT',
]);
const DEBOUNCE_MS = 400;
const HIGHLIGHT_SOURCE = 'validation';

const CSS = `
.val { display: flex; flex-direction: column; gap: 8px; padding: 8px 10px;
  color: var(--fta-fg); background: var(--fta-surface); min-height: 100%;
  box-sizing: border-box; font-size: 13px; }
.val__bar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.val__mode { color: var(--fta-muted-fg); font-size: 12px; margin-right: 4px; }
.val__spacer { flex: 1 1 auto; }
.val__chip, .val__btn { font: inherit; font-size: 12px; cursor: pointer;
  border: 1px solid var(--fta-border); border-radius: 999px; padding: 2px 10px;
  background: var(--fta-surface-2); color: var(--fta-fg); }
.val__btn { border-radius: var(--fta-radius, 6px); }
.val__chip:hover, .val__btn:hover { background: var(--fta-surface-hover); }
.val__chip:focus-visible, .val__btn:focus-visible, .val-item__node:focus-visible {
  outline: 2px solid var(--fta-focus-ring); outline-offset: 1px; }
.val__chip[aria-pressed="false"] { opacity: 0.55; text-decoration: line-through; }
.val__chip--error { color: var(--fta-danger-fg); border-color: var(--fta-danger-border); }
.val__chip--warning { color: var(--fta-warn-fg); }
.val__chip--info { color: var(--fta-accent); }
.val__status { color: var(--fta-muted-fg); font-size: 12px; min-height: 1em; }
.val__status--error { color: var(--fta-danger-fg); }
.val__empty { padding: 16px 4px; text-align: center; }
.val__empty-title { font-size: 15px; margin: 0 0 4px; color: var(--fta-notice-fg); }
.val__empty-note { margin: 0; color: var(--fta-muted-fg); font-size: 12px; }
.val__group { margin: 0; }
.val__group-title { font-size: 12px; font-weight: 600; margin: 6px 0 4px;
  text-transform: uppercase; letter-spacing: 0.03em; }
.val__group-title--error { color: var(--fta-danger-fg); }
.val__group-title--warning { color: var(--fta-warn-fg); }
.val__group-title--info { color: var(--fta-accent); }
.val__list { list-style: none; margin: 0; padding: 0; display: flex;
  flex-direction: column; gap: 4px; }
.val-item { display: grid; grid-template-columns: 1.4em 1fr; column-gap: 6px;
  padding: 6px 8px; border: 1px solid var(--fta-border);
  border-radius: var(--fta-radius, 6px); background: var(--fta-surface-2); }
.val-item--error { border-left: 3px solid var(--fta-danger-fg); }
.val-item--warning { border-left: 3px solid var(--fta-warn-fg); }
.val-item--info { border-left: 3px solid var(--fta-accent); }
.val-item__icon { grid-row: 1 / span 4; font-size: 14px; line-height: 1.3; }
.val-item--error .val-item__icon { color: var(--fta-danger-fg); }
.val-item--warning .val-item__icon { color: var(--fta-warn-fg); }
.val-item--info .val-item__icon { color: var(--fta-accent); }
.val-item__head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; }
.val-item__node { font: inherit; font-weight: 600; padding: 0; border: 0;
  background: none; color: var(--fta-accent); cursor: pointer; text-align: left;
  text-decoration: underline; text-underline-offset: 2px; }
.val-item__node[disabled] { color: var(--fta-muted-fg); cursor: default; text-decoration: none; }
.val-item__code { font-family: ui-monospace, Consolas, monospace; font-size: 10.5px;
  color: var(--fta-muted-fg); }
.val-item__msg { margin: 2px 0 0; }
.val-item__fix { margin: 2px 0 0; color: var(--fta-muted-fg); font-size: 12px; }
.val-item__fix b { color: var(--fta-fg); font-weight: 600; }
.val-item__adv { margin: 2px 0 0; font-size: 11.5px; color: var(--fta-warn-fg); }
`;

function registerCatalog() {
  try {
    const shell = typeof window !== 'undefined' ? window.ftaShell : null;
    if (shell && typeof shell.registerStrings === 'function') shell.registerStrings(catalog);
  } catch (_err) {
    /* strings fall back to the catalog below */
  }
}

function interpolate(text, vars) {
  if (!vars) return text;
  return String(text).replace(/\{(\w+)\}/g, (whole, name) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : whole
  );
}

function signature(issue) {
  return [issue.code, issue.nodeId, issue.message].join('\u0001');
}

/**
 * @param {HTMLElement} panel
 * @param {object} ctx  see tabs/host.js
 */
export function mount(panel, ctx) {
  registerCatalog();
  injectStyles('fta-validation-css', CSS);

  const lang = () => {
    const shell = typeof window !== 'undefined' ? window.ftaShell : null;
    return shell && shell.language === 'ja' ? 'ja' : 'en';
  };
  /** Translate; null when neither the shell nor the catalog knows the key. */
  const lookup = (key, vars) => {
    if (ctx && typeof ctx.t === 'function') {
      const text = ctx.t(key, vars);
      if (text !== key) return text;
    }
    const table = catalog[lang()] || catalog.en;
    const raw = table[key] !== undefined ? table[key] : catalog.en[key];
    return raw === undefined ? null : interpolate(raw, vars);
  };
  const t = (key, vars) => {
    const text = lookup(key, vars);
    return text === null ? key : text;
  };
  const fmtProb = (v) => {
    try {
      return ctx && ctx.fmt && typeof ctx.fmt.prob === 'function' ? ctx.fmt.prob(v) : String(v);
    } catch (_err) {
      return String(v);
    }
  };
  const isAdvanced = () => Boolean(ctx && typeof ctx.advanced === 'function' && ctx.advanced());

  // ---- state ---------------------------------------------------------------
  let issues = [];
  let mode = 'FTA';
  let loading = false;
  let failure = null;
  let loadedOnce = false;
  let seq = 0;
  let timer = null;
  let disposed = false;
  let activatedAt = 0;
  const filters = { error: true, warning: true, info: true };
  const dismissed = new Set();

  // ---- skeleton ------------------------------------------------------------
  const root = document.createElement('div');
  root.className = 'val';
  root.setAttribute('role', 'region');

  const bar = document.createElement('div');
  bar.className = 'val__bar';
  const modeLabel = document.createElement('span');
  modeLabel.className = 'val__mode';
  bar.appendChild(modeLabel);
  const chips = {};
  for (const sev of SEVERITIES) {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'val__chip val__chip--' + sev;
    chip.dataset.severity = sev;
    chip.setAttribute('aria-pressed', 'true');
    chip.addEventListener('click', () => {
      filters[sev] = !filters[sev];
      render();
    });
    chips[sev] = chip;
    bar.appendChild(chip);
  }
  const spacer = document.createElement('span');
  spacer.className = 'val__spacer';
  const dismissBtn = document.createElement('button');
  dismissBtn.type = 'button';
  dismissBtn.className = 'val__btn val__dismiss';
  dismissBtn.addEventListener('click', () => {
    for (const issue of issues) if (SESSION_CODES.has(issue.code)) dismissed.add(signature(issue));
    render();
  });
  const recheckBtn = document.createElement('button');
  recheckBtn.type = 'button';
  recheckBtn.className = 'val__btn val__recheck';
  recheckBtn.addEventListener('click', () => refresh());
  bar.append(spacer, dismissBtn, recheckBtn);

  const status = document.createElement('div');
  status.className = 'val__status';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  const body = document.createElement('div');
  body.className = 'val__body';
  root.append(bar, status, body);
  panel.appendChild(root);

  // ---- data ----------------------------------------------------------------
  async function refresh() {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    if (disposed || !ctx || !ctx.api) return;
    const mine = ++seq;
    loading = true;
    paintStatus();
    try {
      const res = await ctx.api.get('/analysis/validate');
      if (disposed || mine !== seq) return;
      issues = Array.isArray(res && res.issues) ? res.issues : [];
      mode = res && res.mode === 'ETA' ? 'ETA' : 'FTA';
      failure = null;
      loadedOnce = true;
    } catch (err) {
      if (disposed || mine !== seq) return;
      failure = err;
    } finally {
      if (mine === seq) loading = false;
    }
    render();
  }

  function schedule() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      refresh();
    }, DEBOUNCE_MS);
  }

  // ---- rendering -------------------------------------------------------------
  function displayParams(issue) {
    const out = {};
    const params = issue.params && typeof issue.params === 'object' ? issue.params : {};
    for (const [key, value] of Object.entries(params)) {
      if (typeof value === 'number') {
        out[key] = Number.isInteger(value) ? String(value) : fmtProb(value);
      } else if (Array.isArray(value)) {
        out[key] = value.join(', ');
      } else if (value === null || value === undefined) {
        out[key] = '-';
      } else if (typeof value === 'object') {
        continue;
      } else {
        out[key] = String(value);
      }
    }
    if (out.targetId !== undefined && out.targetName === undefined && ctx && ctx.store) {
      const target = ctx.store.findNode(out.targetId);
      out.targetName = target && target.name ? String(target.name) : out.targetId;
    }
    return out;
  }

  function messageFor(issue) {
    const vars = displayParams(issue);
    const kind = issue.params && typeof issue.params.kind === 'string' ? issue.params.kind : null;
    if (kind) {
      // A cause-specific variant first (params.cause 'ai': the AI assistant
      // made the edit, not the desktop editor), then the kind's own text.
      const cause = typeof issue.params.cause === 'string' ? issue.params.cause : null;
      if (cause) {
        const byCause = lookup('val.code.' + issue.code + '.' + kind + '.' + cause, vars);
        if (byCause !== null) return byCause;
      }
      const specific = lookup('val.code.' + issue.code + '.' + kind, vars);
      if (specific !== null) return specific;
    }
    // Session notices carry a message written for their specific case; the
    // generic LOAD_REPAIR text would lose that detail, so prefer the server's
    // own words only when no kind-specific text exists and it is English.
    const generic = lookup('val.code.' + issue.code, vars);
    if (generic !== null && !(issue.code === 'LOAD_REPAIR' && lang() === 'en' && issue.message)) {
      return generic;
    }
    return issue.message || generic || issue.code;
  }

  function nodeLabel(issue) {
    if (issue.nodeId === null || issue.nodeId === undefined) return null;
    const node = ctx && ctx.store ? ctx.store.findNode(issue.nodeId) : null;
    if (!node) return { text: t('val.nodeGone', { id: issue.nodeId }), exists: false };
    const name = node.name === undefined || node.name === null || node.name === '' ? String(node.id) : String(node.name);
    return { text: name, exists: true };
  }

  function select(nodeId) {
    if (!ctx) return;
    try {
      if (typeof ctx.jumpTo === 'function') ctx.jumpTo(nodeId);
      if (typeof ctx.highlight === 'function') ctx.highlight([nodeId], HIGHLIGHT_SOURCE);
    } catch (err) {
      if (typeof ctx.showError === 'function') ctx.showError(err);
    }
  }

  function renderItem(issue) {
    const li = document.createElement('li');
    const sev = SEVERITIES.includes(issue.severity) ? issue.severity : 'warning';
    li.className = 'val-item val-item--' + sev;
    li.dataset.code = issue.code;
    if (issue.nodeId !== null && issue.nodeId !== undefined) li.dataset.nodeId = issue.nodeId;

    const icon = document.createElement('span');
    icon.className = 'val-item__icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = ICONS[sev];

    const head = document.createElement('div');
    head.className = 'val-item__head';
    const label = nodeLabel(issue);
    const nodeBtn = document.createElement('button');
    nodeBtn.type = 'button';
    nodeBtn.className = 'val-item__node';
    if (label) {
      nodeBtn.textContent = label.text;
      if (label.exists) {
        nodeBtn.title = t('val.jumpTitle');
        nodeBtn.addEventListener('click', () => select(issue.nodeId));
      } else {
        nodeBtn.disabled = true;
      }
    } else {
      nodeBtn.textContent = t('val.wholeTree');
      nodeBtn.disabled = true;
    }
    const code = document.createElement('span');
    code.className = 'val-item__code';
    code.textContent = issue.code;
    head.append(nodeBtn, code);

    const msg = document.createElement('p');
    msg.className = 'val-item__msg';
    msg.textContent = messageFor(issue);

    li.append(icon, head, msg);

    const fix = lookup('val.fix.' + issue.code);
    if (fix) {
      const fixEl = document.createElement('p');
      fixEl.className = 'val-item__fix';
      const b = document.createElement('b');
      b.textContent = t('val.fixLabel') + ' ';
      fixEl.append(b, document.createTextNode(fix));
      li.appendChild(fixEl);
    }
    if (ADVANCED_CODES.has(issue.code) && !isAdvanced()) {
      const adv = document.createElement('p');
      adv.className = 'val-item__adv';
      adv.textContent = t('val.advancedHint');
      li.appendChild(adv);
    }
    return li;
  }

  function paintStatus() {
    status.classList.toggle('val__status--error', Boolean(failure));
    if (failure) {
      status.textContent = t('val.failed', {
        error: failure && failure.message ? failure.message : String(failure),
      });
    } else {
      status.textContent = loading ? t('val.checking') : '';
    }
    recheckBtn.disabled = loading;
  }

  function render() {
    if (disposed) return;
    root.setAttribute('aria-label', t('val.aria'));
    modeLabel.textContent = mode === 'ETA' ? t('val.modeEta') : t('val.modeFta');
    recheckBtn.textContent = t('val.recheck');
    recheckBtn.title = t('val.recheckTitle');
    dismissBtn.textContent = t('val.dismiss');
    dismissBtn.title = t('val.dismissTitle');

    const shown = issues.filter((i) => !dismissed.has(signature(i)));
    const counts = { error: 0, warning: 0, info: 0 };
    for (const issue of shown) {
      const sev = SEVERITIES.includes(issue.severity) ? issue.severity : 'warning';
      counts[sev] += 1;
    }
    for (const sev of SEVERITIES) {
      chips[sev].textContent = ICONS[sev] + ' ' + t('val.sev.' + sev) + ' ' + counts[sev];
      chips[sev].title = t('val.chipTitle');
      chips[sev].setAttribute('aria-pressed', filters[sev] ? 'true' : 'false');
    }
    dismissBtn.hidden = !shown.some((i) => SESSION_CODES.has(i.code));
    paintStatus();

    body.textContent = '';
    if (!loadedOnce) return;
    if (!shown.length) {
      const empty = document.createElement('div');
      empty.className = 'val__empty';
      const title = document.createElement('p');
      title.className = 'val__empty-title';
      title.textContent = t('val.empty');
      const note = document.createElement('p');
      note.className = 'val__empty-note';
      note.textContent = t('val.emptyNote');
      empty.append(title, note);
      body.appendChild(empty);
      return;
    }
    let any = false;
    for (const sev of SEVERITIES) {
      if (!filters[sev]) continue;
      const group = shown.filter((i) => (SEVERITIES.includes(i.severity) ? i.severity : 'warning') === sev);
      if (!group.length) continue;
      any = true;
      const section = document.createElement('section');
      section.className = 'val__group val__group--' + sev;
      section.dataset.severity = sev;
      const heading = document.createElement('h3');
      heading.className = 'val__group-title val__group-title--' + sev;
      heading.textContent = t('val.sev.' + sev) + ' (' + group.length + ')';
      const list = document.createElement('ul');
      list.className = 'val__list';
      for (const issue of group) list.appendChild(renderItem(issue));
      section.append(heading, list);
      body.appendChild(section);
    }
    if (!any) {
      const note = document.createElement('p');
      note.className = 'val__empty-note';
      note.textContent = t('val.allFiltered');
      body.appendChild(note);
    }
  }

  // ---- wiring ----------------------------------------------------------------
  const onLanguage = () => render();
  window.addEventListener('fta:language', onLanguage);
  // New / Open: dismissals belonged to the old document's session.
  const onDocument = () => {
    dismissed.clear();
    render();
  };
  window.addEventListener('fta:document', onDocument);
  const unSig = ctx && typeof ctx.onSigFigs === 'function' ? ctx.onSigFigs(() => render()) : null;
  const unAdv = ctx && typeof ctx.onAdvanced === 'function' ? ctx.onAdvanced(() => render()) : null;

  render();

  return {
    activate() {
      activatedAt = Date.now();
      refresh();
    },
    deactivate() {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      if (ctx && typeof ctx.clearHighlight === 'function') ctx.clearHighlight(HIGHLIGHT_SOURCE);
    },
    onStale() {
      // The host calls onStale right after activate for a background tab;
      // the request activate just started already sees the change.
      if (Date.now() - activatedAt < 50) return;
      schedule();
    },
    dispose() {
      disposed = true;
      if (timer) clearTimeout(timer);
      window.removeEventListener('fta:language', onLanguage);
      window.removeEventListener('fta:document', onDocument);
      if (typeof unSig === 'function') unSig();
      if (typeof unAdv === 'function') unAdv();
      if (ctx && typeof ctx.clearHighlight === 'function') ctx.clearHighlight(HIGHLIGHT_SOURCE);
      root.remove();
    },
    /** Test/integration seam: re-check now. */
    refresh,
  };
}

export default mount;
