/**
 * details.js -- the node details panel.
 *
 * The desktop editor shows a read-only text summary
 * (src/FTA_Editor_UI.py:1525-1553) and edits through a modal
 * (:1231-1399). v1.6 replaces both with one live form: each field commits on
 * blur via `PATCH /api/nodes/<id>`, and the response -- which carries the whole
 * post-mutation view -- goes straight into `store.applyMutation`.
 *
 * Validation runs before the request so a bad value is reported instantly
 * rather than after a round trip. The rules mirror `routes/tree.py`:
 *
 *   * `probability` is a real number in [0.0, 1.0],
 *   * `logicGate` is AND or OR. NOT is never offered and is refused if a
 *     hand-edited file supplies it: the engine branches on `gate == "AND"` and
 *     scores everything else as OR, so a NOT gate is a silently wrong number.
 *     See divergence D5 in fta_web/core/DIVERGENCE.md.
 *   * `type` is a non-empty string.
 *
 * The only client-side rule the server does not have is a non-empty `name`;
 * the server would accept "" (sanitize_name of anything blank), but an unnamed
 * row is unusable in the tree, so the form refuses to send one.
 */
import { api } from './api.js';
import { store } from './store.js';
import {
  clear,
  createGateSelect,
  createLinksEditor,
  el,
  ensureBaseStyles,
  errorField,
  errorMessage,
  formatProbability,
  injectStyles,
  normalizeGate,
  parseProbability,
  sanitizeName,
  showError,
  uid,
  validateGate,
} from './dialogs.js';

const DETAILS_CSS = `
.fta-details {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  padding: 0.6rem;
  color: var(--fta-fg);
  font-size: 0.9rem;
}
.fta-details-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem 0.9rem;
  font-size: 0.78rem;
  color: var(--fta-muted-fg);
}
.fta-details-meta b { font-weight: 600; color: var(--fta-fg); }
.fta-details-meta code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--fta-fg);
}
.fta-details-flag { color: var(--fta-tree-zero-fg); font-weight: 600; }
.fta-details-banner {
  margin: 0;
  padding: 0.45rem 0.55rem;
  border: 1px solid var(--fta-danger-border);
  border-radius: var(--fta-radius);
  background: var(--fta-danger-bg);
  color: var(--fta-danger-fg);
  font-size: 0.82rem;
  overflow-wrap: anywhere;
}
.fta-details-banner[hidden] { display: none; }
.fta-details-empty { margin: 0; padding: 0.6rem; color: var(--fta-muted-fg); }
.fta-details-form { display: flex; flex-direction: column; gap: 0.5rem; }
.fta-details-links-title {
  margin: 0.2rem 0 0;
  font-size: 0.8rem;
  color: var(--fta-muted-fg);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.fta-details [hidden] { display: none; }
`;

/** The editable fields, in the order the desktop dialog lists them. */
const FIELDS = [
  { key: 'name', label: 'Name', kind: 'text' },
  { key: 'type', label: 'Type', kind: 'text' },
  { key: 'probability', label: 'Probability (base)', kind: 'text' },
  { key: 'logicGate', label: 'Logic Gate', kind: 'gate' },
  { key: 'notes', label: 'Notes', kind: 'textarea' },
];

/** The stored value of a field, as the form displays it. */
function displayValue(node, key) {
  switch (key) {
    case 'name':
      return String(node.name === undefined || node.name === null ? '' : node.name);
    case 'type':
      return String(node.type === undefined || node.type === null ? '' : node.type);
    case 'probability': {
      const value = Number(node.probability);
      return Number.isFinite(value) ? String(value) : '';
    }
    case 'logicGate':
      return normalizeGate(node.logicGate);
    case 'notes':
      return String(node.notes === undefined || node.notes === null ? '' : node.notes);
    default:
      return '';
  }
}

/** Stable key for a links array, so equal link sets compare equal. */
function linksKey(links) {
  if (!Array.isArray(links)) return '';
  return links
    .map((link) => {
      if (!link) return '';
      const target = link.target_id !== undefined ? link.target_id : link.targetId;
      return normalizeGate(link.relation) + ':' + String(target === undefined ? '' : target);
    })
    .join('|');
}

/** id+name signature of the whole tree; changes invalidate the link picker. */
function nodeListSignature() {
  let flat = [];
  try {
    flat = store.flat() || [];
  } catch (err) {
    flat = [];
  }
  return flat
    .map((entry) => (entry ? String(entry.id) + '\x00' + String(entry.name) : ''))
    .join('\x01');
}

/**
 * Keep the gate `<select>` honest about what is stored. AND and OR are the only
 * choosable values; an unsupported gate from a hand-edited file is shown as a
 * disabled option instead of being silently rewritten.
 */
function syncGateOptions(select, gate) {
  const existing = select.querySelector('option[data-unsupported]');
  const unsupported = gate !== 'AND' && gate !== 'OR';
  if (existing && (!unsupported || existing.value !== gate)) existing.remove();
  if (unsupported && (!existing || existing.value !== gate)) {
    const option = el('option', {
      value: gate,
      disabled: true,
      text: gate + ' (unsupported)',
      dataset: { unsupported: 'true' },
    });
    select.insertBefore(option, select.firstChild);
  }
  select.value = gate;
}

/**
 * Mount the details form inside `container`.
 *
 * Non-destructive: the panel is appended, or reused if this is a re-init, so an
 * existing heading in the container survives.
 */
export function initDetails(container) {
  if (!container) throw new Error('initDetails(container): container is required');
  ensureBaseStyles();
  injectStyles('fta-details-css', DETAILS_CSS);

  let panel = container.querySelector(':scope > .fta-details');
  if (panel) clear(panel);
  else {
    panel = el('section', { class: 'fta-details', 'aria-label': 'Node details' });
    container.appendChild(panel);
  }

  /* ---- static structure, built once ---- */

  const idOut = el('code', { text: '—' });
  const calcOut = el('b', { text: '—' });
  const zeroFlag = el('span', { class: 'fta-details-flag', text: '✖ zero probability', hidden: true });
  const meta = el('div', { class: 'fta-details-meta' }, [
    el('span', {}, ['Node ID ', idOut]),
    el('span', {}, ['Calculated probability ', calcOut]),
    zeroFlag,
  ]);

  const banner = el('p', { class: 'fta-details-banner', role: 'alert', hidden: true });
  const empty = el('p', {
    class: 'fta-details-empty',
    text: 'Select a node in the tree to edit it.',
  });

  const form = el('form', { class: 'fta-details-form', novalidate: true, hidden: true });
  form.addEventListener('submit', (event) => event.preventDefault());

  const fields = Object.create(null);
  for (const spec of FIELDS) {
    let control;
    if (spec.kind === 'textarea') control = el('textarea', { rows: '4' });
    else if (spec.kind === 'gate') control = createGateSelect('OR');
    else control = el('input', { type: 'text' });

    const id = uid('fta-details');
    control.id = id;
    const error = el('p', { class: 'fta-field-error', id: id + '-error', hidden: true });
    control.setAttribute('aria-describedby', error.id);
    form.appendChild(
      el('div', { class: 'fta-field' }, [
        el('label', { for: id, text: spec.label }),
        control,
        error,
      ])
    );
    fields[spec.key] = { spec: spec, control: control, error: error };
  }

  const linksEditor = createLinksEditor({
    selfId: null,
    links: [],
    onChange: (links) => send({ links: links }),
  });
  const linksSection = el('div', { hidden: true }, [
    el('h3', { class: 'fta-details-links-title', text: 'Links' }),
    linksEditor.element,
  ]);

  panel.appendChild(meta);
  panel.appendChild(banner);
  panel.appendChild(empty);
  panel.appendChild(form);
  panel.appendChild(linksSection);

  /* ---- state ---- */

  let renderedId = null;
  let listSignature = null;

  function currentId() {
    const id = store.selectedId;
    return id === null || id === undefined ? null : String(id);
  }

  function currentNode() {
    const id = currentId();
    if (!id) return null;
    try {
      return store.findNode(id) || null;
    } catch (err) {
      return null;
    }
  }

  function setBanner(message) {
    banner.textContent = message || '';
    banner.hidden = !message;
  }

  function setFieldError(key, message) {
    const field = fields[key];
    if (!field) return;
    field.error.textContent = message || '';
    field.error.hidden = !message;
    field.control.setAttribute('aria-invalid', message ? 'true' : 'false');
  }

  function clearErrors() {
    setBanner('');
    for (const key of Object.keys(fields)) setFieldError(key, '');
    linksEditor.setStatus('', false);
  }

  /* ---- writing ---- */

  /**
   * PATCH one or more fields. The response is the full post-mutation view, so
   * the store is refreshed from it rather than from a follow-up GET.
   */
  async function send(patch) {
    const id = currentId();
    if (!id) return;
    setBanner('');
    try {
      const result = await api.patch('/nodes/' + encodeURIComponent(id), patch);
      store.applyMutation(result);
    } catch (err) {
      const message = errorMessage(err, 'Could not save the change.');
      setBanner(message);
      showError(err, 'Could not save the change.');
      const field = errorField(err);
      if (field && fields[field]) setFieldError(field, message);
      throw err;
    }
  }

  /** Validate one field and return `{ok, value}` in the shape the API wants. */
  function validateField(key, raw) {
    switch (key) {
      case 'probability':
        return parseProbability(raw);
      case 'logicGate':
        return validateGate(raw);
      case 'name': {
        const name = sanitizeName(raw);
        if (!name) return { ok: false, message: 'Name is required.' };
        return { ok: true, value: name };
      }
      case 'type': {
        const type = String(raw === null || raw === undefined ? '' : raw).trim();
        if (!type) return { ok: false, message: "'type' must be a non-empty string." };
        return { ok: true, value: type };
      }
      default:
        return { ok: true, value: String(raw === null || raw === undefined ? '' : raw) };
    }
  }

  /** True when the validated value is already what the node holds. */
  function unchanged(node, key, value) {
    switch (key) {
      case 'probability':
        return Number(node.probability) === value;
      case 'logicGate':
        return normalizeGate(node.logicGate) === value;
      case 'name':
        return sanitizeName(node.name) === value;
      case 'type':
        return String(node.type === undefined || node.type === null ? '' : node.type).trim() === value;
      default:
        return displayValue(node, key) === value;
    }
  }

  function commitField(key) {
    const node = currentNode();
    const field = fields[key];
    if (!node || !field) return;

    const result = validateField(key, field.control.value);
    if (!result.ok) {
      setFieldError(key, result.message);
      return;
    }
    setFieldError(key, '');
    if (unchanged(node, key, result.value)) {
      // Re-normalise the box (whitespace collapsed, gate upper-cased) so what
      // is displayed is what is stored.
      field.control.value = displayValue(node, key);
      return;
    }
    const patch = {};
    patch[key] = result.value;
    send(patch).catch(() => {
      /* reported by send(); the typed value stays so it can be corrected */
    });
  }

  for (const key of Object.keys(fields)) {
    const field = fields[key];
    const control = field.control;

    if (field.spec.kind === 'gate') {
      control.addEventListener('change', () => commitField(key));
    } else {
      control.addEventListener('blur', () => commitField(key));
      control.addEventListener('input', () => setFieldError(key, ''));
      control.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && field.spec.kind !== 'textarea') {
          event.preventDefault();
          control.blur();
        } else if (event.key === 'Escape') {
          event.preventDefault();
          const node = currentNode();
          if (node) control.value = displayValue(node, key);
          setFieldError(key, '');
        }
      });
    }
  }

  /* ---- reading ---- */

  function update() {
    const id = currentId();
    const node = currentNode();
    const switched = id !== renderedId;

    if (!node) {
      renderedId = null;
      empty.hidden = false;
      form.hidden = true;
      linksSection.hidden = true;
      idOut.textContent = '—';
      calcOut.textContent = '—';
      zeroFlag.hidden = true;
      if (switched) clearErrors();
      return;
    }

    empty.hidden = true;
    form.hidden = false;
    linksSection.hidden = false;
    if (switched) clearErrors();

    idOut.textContent = String(node.id);
    const calculated =
      node.calculatedProbability === undefined || node.calculatedProbability === null
        ? node.probability
        : node.calculatedProbability;
    calcOut.textContent = formatProbability(calculated);

    const zeroNodes = (store.state && store.state.zeroNodes) || [];
    zeroFlag.hidden = !(Array.isArray(zeroNodes) && zeroNodes.map(String).indexOf(String(node.id)) !== -1);

    for (const key of Object.keys(fields)) {
      const field = fields[key];
      const control = field.control;
      const value = displayValue(node, key);
      if (field.spec.kind === 'gate') {
        if (switched || document.activeElement !== control) syncGateOptions(control, value);
        continue;
      }
      // Never clobber the box the user is typing in.
      if (switched || (document.activeElement !== control && control.value !== value)) {
        control.value = value;
      }
    }

    if (switched) linksEditor.setSelfId(node.id);
    if (switched || linksKey(node.links) !== linksKey(linksEditor.getLinks())) {
      linksEditor.setLinks(node.links);
    }

    const signature = nodeListSignature();
    if (switched || signature !== listSignature) {
      listSignature = signature;
      linksEditor.reload();
    }

    renderedId = id;
  }

  const unsubscribe = store.subscribe(update);
  update();

  return {
    refresh: update,
    destroy() {
      if (typeof unsubscribe === 'function') unsubscribe();
      clear(panel);
      if (panel.parentNode === container) container.removeChild(panel);
    },
  };
}
