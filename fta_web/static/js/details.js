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
 * 1.7 (workstream B): the gate select offers every gate type when the Advanced
 * switch is on (AND/OR only when it is off) and PATCHes `gateType` for them;
 * KOFN reveals `k`, TRANSFER a target picker, a leaf an event-kind select and
 * a house event its ON/OFF state. In basic mode an advanced value is shown
 * read-only with an "advanced" chip and a hint -- never silently changed. A
 * probability derived from a non-fixed quantification model is read-only.
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
  fillGateOptions,
  formatProbability,
  injectStyles,
  isAdvancedMode,
  normalizeGate,
  parseProbability,
  sanitizeName,
  showError,
  t,
  uid,
  validateGate,
} from './dialogs.js';
import { BASIC_GATES, EVENT_KINDS, GATE_TYPES, isAdvancedNode } from './schema.js';

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
.fta-details-adv {
  margin: -0.2rem 0 0;
  font-size: 0.78rem;
  color: var(--fta-muted-fg);
  display: flex;
  gap: 0.4rem;
  align-items: baseline;
  flex-wrap: wrap;
}
.fta-details-chip {
  display: inline-block;
  padding: 0 0.4rem;
  border-radius: 999px;
  border: 1px solid var(--fta-accent, #14507d);
  color: var(--fta-accent, #14507d);
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.fta-details-extras { display: flex; flex-direction: column; gap: 0.5rem; }
.fta-details-note { margin: 0; font-size: 0.78rem; color: var(--fta-muted-fg); }
.fta-details input[readonly] { background: var(--fta-surface-2, #f4f6f8); color: var(--fta-muted-fg); }
`;

/** The editable fields, in the order the desktop dialog lists them. */
const FIELDS = [
  { key: 'name', label: 'details.name', kind: 'text' },
  { key: 'type', label: 'details.type', kind: 'text' },
  { key: 'probability', label: 'details.probabilityBase', kind: 'text' },
  { key: 'logicGate', label: 'details.logicGate', kind: 'gate' },
  { key: 'notes', label: 'details.notes', kind: 'textarea' },
];

/*
 * Every PATCH from this panel runs through one chain so a blur commit can
 * never overtake an earlier one, and `fta:flush` (Save, exports) can await the
 * tail. `sequence` numbers the requests so only the newest response is
 * applied: the server view is cumulative, so an older one is stale by then.
 */
let pending = Promise.resolve();
let sequence = 0;

/** The stored value of a field, as the form displays it. */
function displayValue(node, key) {
  switch (key) {
    case 'name':
      return String(node.name === undefined || node.name === null ? '' : node.name);
    case 'type':
      return String(node.type === undefined || node.type === null ? '' : node.type);
    case 'probability': {
      const value = Number(node.probability);
      if (!Number.isFinite(value)) return '';
      return derivedModel(node) ? formatProbability(value) : String(value);
    }
    case 'logicGate':
      return effectiveGate(node);
    case 'notes':
      return String(node.notes === undefined || node.notes === null ? '' : node.notes);
    default:
      return '';
  }
}

/** gateType when set (upper-cased), else the legacy logicGate. */
function effectiveGate(node) {
  const raw = node && node.gateType;
  if (raw !== undefined && raw !== null && String(raw).trim() !== '') return normalizeGate(raw);
  return normalizeGate(node ? node.logicGate : '');
}

/** The quant model name when it is not `fixed` (probability is derived), else null. */
function derivedModel(node) {
  const quant = node && node.quant;
  const model = quant && typeof quant === 'object' ? quant.model : null;
  if (model === undefined || model === null || model === '') return null;
  const name = String(model).toLowerCase();
  return name === 'fixed' ? null : name;
}

function eventKindOf(node) {
  const kind = node && node.eventKind;
  const name = kind === undefined || kind === null ? '' : String(kind).toLowerCase();
  return EVENT_KINDS.indexOf(name) === -1 ? 'basic' : name;
}

function childCount(node) {
  return Array.isArray(node && node.children) ? node.children.length : 0;
}

/** Ids of `node` and every descendant (a transfer must not point into itself). */
function subtreeIds(node) {
  const out = new Set();
  const stack = node ? [node] : [];
  while (stack.length) {
    const cur = stack.pop();
    if (!cur || typeof cur !== 'object') continue;
    out.add(String(cur.id));
    if (Array.isArray(cur.children)) stack.push(...cur.children);
  }
  return out;
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
  const advanced = isAdvancedMode();
  fillGateOptions(select, gate, advanced);
  // Basic mode with an advanced gate stored: read-only, never rewritten.
  select.disabled = !advanced && BASIC_GATES.indexOf(gate) === -1 && GATE_TYPES.indexOf(gate) !== -1;
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
    panel = el('section', { class: 'fta-details' });
    container.appendChild(panel);
  }

  /* ---- static structure, built once ---- */

  const idOut = el('code', { text: '—' });
  const calcOut = el('b', { text: '—' });
  const idLabel = document.createTextNode('');
  const calcLabel = document.createTextNode('');
  const zeroFlag = el('span', { class: 'fta-details-flag', hidden: true });
  const meta = el('div', { class: 'fta-details-meta' }, [
    el('span', {}, [idLabel, idOut]),
    el('span', {}, [calcLabel, calcOut]),
    zeroFlag,
  ]);

  const banner = el('p', { class: 'fta-details-banner', role: 'alert', hidden: true });
  const empty = el('p', { class: 'fta-details-empty' });

  const form = el('form', { class: 'fta-details-form', novalidate: true, hidden: true });
  form.addEventListener('submit', (event) => event.preventDefault());

  const fields = Object.create(null);
  for (const spec of FIELDS) {
    let control;
    if (spec.kind === 'textarea') control = el('textarea', { rows: '4' });
    else if (spec.kind === 'gate') control = createGateSelect({ value: 'OR', advanced: isAdvancedMode() });
    else control = el('input', { type: 'text' });

    const id = uid('fta-details');
    control.id = id;
    const label = el('label', { for: id });
    const error = el('p', { class: 'fta-field-error', id: id + '-error', hidden: true });
    control.setAttribute('aria-describedby', error.id);
    form.appendChild(el('div', { class: 'fta-field' }, [label, control, error]));
    // `baseline` is the value last written from the store; F-7 compares
    // against it to flag unsaved typing for main.js's beforeunload check.
    fields[spec.key] = { spec: spec, control: control, label: label, error: error, baseline: '' };
  }

  const linksEditor = createLinksEditor({
    selfId: null,
    links: [],
    onChange: (links) => send({ links: links }),
  });
  /* ---- 1.7 gate / event extras, placed right after the gate select ---- */

  const extras = buildExtras();
  const gateWrapper = fields.logicGate.control.parentNode;
  gateWrapper.parentNode.insertBefore(extras.root, gateWrapper.nextSibling);
  const probNote = el('p', { class: 'fta-details-note', hidden: true });
  fields.probability.control.parentNode.appendChild(probNote);

  function buildExtras() {
    const chipText = el('span', { class: 'fta-details-chip' });
    const hintText = el('span');
    const advBox = el('p', { class: 'fta-details-adv', hidden: true }, [chipText, hintText]);

    const kInput = el('input', { type: 'number', min: '1', step: '1', inputmode: 'numeric' });
    const kId = uid('fta-details-k');
    kInput.id = kId;
    const kLabel = el('label', { for: kId });
    const kError = el('p', { class: 'fta-field-error', id: kId + '-error', hidden: true });
    kInput.setAttribute('aria-describedby', kError.id);
    const kRow = el('div', { class: 'fta-field', hidden: true }, [kLabel, kInput, kError]);

    const transferSelect = el('select');
    const trId = uid('fta-details-transfer');
    transferSelect.id = trId;
    const trLabel = el('label', { for: trId });
    const trNote = el('p', { class: 'fta-details-note' });
    const trRow = el('div', { class: 'fta-field', hidden: true }, [trLabel, transferSelect, trNote]);

    const kindSelect = el('select');
    const kindId = uid('fta-details-kind');
    kindSelect.id = kindId;
    const kindLabel = el('label', { for: kindId });
    const kindRow = el('div', { class: 'fta-field', hidden: true }, [kindLabel, kindSelect]);

    const houseSelect = el('select');
    const houseId = uid('fta-details-house');
    houseSelect.id = houseId;
    const houseLabel = el('label', { for: houseId });
    const houseRow = el('div', { class: 'fta-field', hidden: true }, [houseLabel, houseSelect]);

    const root = el('div', { class: 'fta-details-extras' }, [advBox, kRow, trRow, kindRow, houseRow]);
    return {
      root, advBox, chipText, hintText,
      kRow, kInput, kLabel, kError,
      trRow, transferSelect, trLabel, trNote,
      kindRow, kindSelect, kindLabel,
      houseRow, houseSelect, houseLabel,
      kBaseline: '',
    };
  }

  function relabelExtras() {
    extras.chipText.textContent = t('gate.advancedChip');
    extras.hintText.textContent = t('gate.advancedHint');
    extras.kLabel.textContent = t('gate.k');
    extras.trLabel.textContent = t('gate.transferTo');
    extras.trNote.textContent = t('gate.transferNote');
    extras.kindLabel.textContent = t('event.kind');
    extras.houseLabel.textContent = t('event.houseState');
    const kindValue = extras.kindSelect.value;
    clear(extras.kindSelect);
    for (const kind of EVENT_KINDS) {
      extras.kindSelect.appendChild(el('option', { value: kind, text: t('event.' + kind) }));
    }
    if (kindValue) extras.kindSelect.value = kindValue;
    const houseValue = extras.houseSelect.value;
    clear(extras.houseSelect);
    extras.houseSelect.appendChild(el('option', { value: 'on', text: t('event.houseOn') }));
    extras.houseSelect.appendChild(el('option', { value: 'off', text: t('event.houseOff') }));
    if (houseValue) extras.houseSelect.value = houseValue;
  }

  /** Transfer targets: every node except this one and its own subtree. */
  function fillTransferOptions(node) {
    const select = extras.transferSelect;
    const excluded = subtreeIds(node);
    const wanted = node.transferTo === undefined || node.transferTo === null ? '' : String(node.transferTo);
    clear(select);
    select.appendChild(el('option', { value: '', text: t('gate.transferNone') }));
    let flat = [];
    try {
      flat = store.flat() || [];
    } catch (_err) {
      flat = [];
    }
    let found = wanted === '';
    for (const entry of flat) {
      const id = String(entry.id);
      if (excluded.has(id)) continue;
      if (id === wanted) found = true;
      select.appendChild(el('option', { value: id, text: String(entry.name) + ' (' + id + ')' }));
    }
    if (!found) {
      // A dangling or self-referencing target: shown as stored, not dropped.
      select.appendChild(el('option', { value: wanted, disabled: true, text: wanted + ' (?)' }));
    }
    select.value = wanted;
  }

  /** Show/hide and fill the extras for `node`; `force` repopulates the k box. */
  function updateExtras(node, force) {
    const advanced = isAdvancedMode();
    const gate = effectiveGate(node);
    const n = childCount(node);
    const kind = eventKindOf(node);
    const readOnly = !advanced;

    extras.advBox.hidden = advanced || !isAdvancedNode(node);

    extras.kRow.hidden = gate !== 'KOFN';
    extras.kInput.max = String(Math.max(1, n));
    extras.kInput.disabled = readOnly;
    const kText = node.k === undefined || node.k === null ? '' : String(node.k);
    if (force || document.activeElement !== extras.kInput) {
      extras.kInput.value = kText;
      extras.kBaseline = kText;
      delete extras.kInput.dataset.dirty;
      if (force) setKError('');
    }

    extras.trRow.hidden = gate !== 'TRANSFER';
    extras.transferSelect.disabled = readOnly;
    if (gate === 'TRANSFER') fillTransferOptions(node);

    const isLeaf = n === 0 && gate !== 'TRANSFER';
    extras.kindRow.hidden = !isLeaf || (!advanced && kind === 'basic');
    extras.kindSelect.disabled = readOnly;
    extras.kindSelect.value = kind;

    extras.houseRow.hidden = !isLeaf || kind !== 'house';
    extras.houseSelect.disabled = readOnly;
    extras.houseSelect.value = node.houseState === true ? 'on' : 'off';

    const model = derivedModel(node);
    const prob = fields.probability.control;
    prob.readOnly = !!model;
    probNote.hidden = !model;
    probNote.textContent = model ? t('event.derivedNote', { model: model }) : '';
  }

  function setKError(message) {
    extras.kError.textContent = message || '';
    extras.kError.hidden = !message;
    extras.kInput.setAttribute('aria-invalid', message ? 'true' : 'false');
  }

  function commitK() {
    const node = currentNode();
    if (!node || extras.kInput.disabled) return;
    const text = String(extras.kInput.value || '').trim();
    if (text === extras.kBaseline) {
      delete extras.kInput.dataset.dirty;
      return;
    }
    const n = childCount(node);
    const value = Number(text);
    if (n < 1) {
      setKError(t('gate.kNoChildren'));
      return;
    }
    if (!Number.isInteger(value) || value < 1 || value > n) {
      setKError(t('gate.kRange', { n: n }));
      return;
    }
    setKError('');
    const nodeId = String(node.id);
    send({ k: value }).then(
      () => {
        const now = currentNode();
        if (now && String(now.id) === nodeId) updateExtras(now, true);
      },
      () => {
        /* reported by send(); the typed value stays (and stays dirty) */
      }
    );
  }

  extras.kInput.addEventListener('input', () => {
    setKError('');
    if (extras.kInput.value !== extras.kBaseline) extras.kInput.dataset.dirty = 'true';
    else delete extras.kInput.dataset.dirty;
  });
  extras.kInput.addEventListener('blur', commitK);
  extras.kInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      extras.kInput.blur();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      const node = currentNode();
      if (node) updateExtras(node, true);
    }
  });
  const quiet = () => {
    /* reported by send() */
  };
  extras.transferSelect.addEventListener('change', () => {
    const value = extras.transferSelect.value;
    send({ transferTo: value === '' ? null : value }).catch(quiet);
  });
  extras.kindSelect.addEventListener('change', () => {
    const value = extras.kindSelect.value;
    send({ eventKind: value === 'basic' ? null : value }).catch(quiet);
  });
  extras.houseSelect.addEventListener('change', () => {
    send({ houseState: extras.houseSelect.value === 'on' }).catch(quiet);
  });

  const linksTitle = el('h3', { class: 'fta-details-links-title' });
  const linksSection = el('div', { hidden: true }, [linksTitle, linksEditor.element]);

  function relabel() {
    panel.setAttribute('aria-label', t('details.aria'));
    idLabel.data = t('details.nodeId') + ' ';
    calcLabel.data = t('details.calculated') + ' ';
    zeroFlag.textContent = t('details.zeroFlag');
    empty.textContent = t('details.empty');
    linksTitle.textContent = t('details.links');
    for (const key of Object.keys(fields)) {
      fields[key].label.textContent = t(fields[key].spec.label);
    }
    relabelExtras();
    const node = currentNode();
    if (node) {
      syncGateOptions(fields.logicGate.control, displayValue(node, 'logicGate'));
      updateExtras(node, false);
    }
    linksEditor.relabel();
  }

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

  /** Flag the control when its text differs from what the store last gave it. */
  function syncDirty(key) {
    const field = fields[key];
    if (field.control.value !== field.baseline) field.control.dataset.dirty = 'true';
    else delete field.control.dataset.dirty;
  }

  /** Write a store value into the control and reset the dirty baseline. */
  function populate(key, value) {
    const field = fields[key];
    if (field.spec.kind === 'gate') syncGateOptions(field.control, value);
    else if (field.control.value !== value) field.control.value = value;
    field.baseline = value;
    delete field.control.dataset.dirty;
  }

  function clearErrors() {
    setBanner('');
    for (const key of Object.keys(fields)) setFieldError(key, '');
    linksEditor.setStatus('', false);
  }

  /* ---- writing ---- */

  /**
   * PATCH one or more fields. The response is the full post-mutation view, so
   * the store is refreshed from it rather than from a follow-up GET. Queued
   * behind every earlier commit; see `pending` above.
   */
  function send(patch) {
    const id = currentId();
    if (!id) return Promise.resolve();
    setBanner('');
    sequence += 1;
    const seq = sequence;
    const request = pending.then(async () => {
      try {
        const result = await api.patch('/nodes/' + encodeURIComponent(id), patch);
        if (seq === sequence) store.applyMutation(result);
        return result;
      } catch (err) {
        const fallback = t('details.saveFailed');
        const message = errorMessage(err, fallback);
        setBanner(message);
        showError(err, fallback);
        const field = errorField(err);
        if (field && fields[field]) setFieldError(field, message);
        throw err;
      }
    });
    // The chain itself must never reject, or every later commit would be skipped.
    pending = request.then(
      () => undefined,
      () => undefined
    );
    return request;
  }

  /**
   * F-4: let Save/export wait for the queue. The focused field is committed
   * first so a value typed but not yet blurred is included in the flush.
   */
  function onFlush(event) {
    const detail = event && event.detail;
    if (!detail || !Array.isArray(detail.promises)) return;
    const active = document.activeElement;
    for (const key of Object.keys(fields)) {
      if (fields[key].control === active) commitField(key);
    }
    if (active === extras.kInput) commitK();
    detail.promises.push(pending);
  }

  /** Validate one field and return `{ok, value}` in the shape the API wants. */
  function validateField(key, raw) {
    switch (key) {
      case 'probability':
        return parseProbability(raw);
      case 'logicGate':
        return validateGate(raw, { advanced: isAdvancedMode() });
      case 'name': {
        const name = sanitizeName(raw);
        if (!name) return { ok: false, message: t('dialog.nameRequired') };
        return { ok: true, value: name };
      }
      case 'type': {
        const type = String(raw === null || raw === undefined ? '' : raw).trim();
        if (!type) return { ok: false, message: t('dialog.typeRequired') };
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
        // A derived value is read-only; its formatted text never "changes" it.
        return derivedModel(node) ? true : Number(node.probability) === value;
      case 'logicGate':
        return effectiveGate(node) === value;
      case 'name':
        return sanitizeName(node.name) === value;
      case 'type':
        return String(node.type === undefined || node.type === null ? '' : node.type).trim() === value;
      default:
        return displayValue(node, key) === value;
    }
  }

  /**
   * The PATCH for a gate change. A legacy node choosing AND/OR keeps writing
   * only `logicGate`; anything with (or getting) a `gateType` writes that and
   * the server projects `logicGate`. Leaving KOFN/TRANSFER drops the now
   * meaningless `k`/`transferTo`; entering KOFN seeds k = majority of n.
   */
  function gatePatch(node, gate) {
    const before = effectiveGate(node);
    const hasType = node.gateType !== undefined && node.gateType !== null && node.gateType !== '';
    const patch = {};
    if (BASIC_GATES.indexOf(gate) !== -1 && !hasType) patch.logicGate = gate;
    else patch.gateType = gate;
    if (before === 'KOFN' && gate !== 'KOFN' && node.k !== undefined && node.k !== null) patch.k = null;
    if (before === 'TRANSFER' && gate !== 'TRANSFER' && node.transferTo) patch.transferTo = null;
    if (gate === 'KOFN' && (node.k === undefined || node.k === null)) {
      const n = childCount(node);
      if (n > 0) patch.k = Math.floor(n / 2) + 1;
    }
    return patch;
  }

  function commitField(key) {
    const node = currentNode();
    const field = fields[key];
    if (!node || !field) return;

    const result = validateField(key, field.control.value);
    if (!result.ok) {
      setFieldError(key, result.message);
      syncDirty(key);
      return;
    }
    setFieldError(key, '');
    if (unchanged(node, key, result.value)) {
      // Re-normalise the box (whitespace collapsed, gate upper-cased) so what
      // is displayed is what is stored.
      populate(key, displayValue(node, key));
      return;
    }
    const patch = key === 'logicGate' ? gatePatch(node, result.value) : { [key]: result.value };
    const nodeId = String(node.id);
    send(patch).then(
      () => {
        // The store already holds the response, so the box is clean again
        // unless the user has since moved on to another node.
        const now = currentNode();
        if (now && String(now.id) === nodeId) populate(key, displayValue(now, key));
      },
      () => {
        /* reported by send(); the typed value stays (and stays dirty) so it can be corrected */
      }
    );
  }

  for (const key of Object.keys(fields)) {
    const field = fields[key];
    const control = field.control;

    if (field.spec.kind === 'gate') {
      control.addEventListener('change', () => {
        syncDirty(key);
        commitField(key);
      });
    } else {
      control.addEventListener('blur', () => commitField(key));
      control.addEventListener('input', () => {
        setFieldError(key, '');
        syncDirty(key);
      });
      control.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && field.spec.kind !== 'textarea') {
          event.preventDefault();
          control.blur();
        } else if (event.key === 'Escape') {
          // Escape here means "discard my typing", not "dismiss the toast".
          event.preventDefault();
          event.stopPropagation();
          const node = currentNode();
          if (node) populate(key, displayValue(node, key));
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
      const control = fields[key].control;
      // Never clobber the box the user is typing in.
      if (switched || document.activeElement !== control) populate(key, displayValue(node, key));
    }
    updateExtras(node, switched);

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

  relabel();
  const unsubscribe = store.subscribe(update);
  update();
  window.addEventListener('fta:language', relabel);
  window.addEventListener('fta:flush', onFlush);
  // Advanced switch: rebuild the gate list and the read-only state.
  const onAdvanced = () => {
    const node = currentNode();
    if (!node) return;
    populate('logicGate', displayValue(node, 'logicGate'));
    updateExtras(node, false);
  };
  window.addEventListener('fta:advanced', onAdvanced);

  return {
    refresh: update,
    destroy() {
      if (typeof unsubscribe === 'function') unsubscribe();
      window.removeEventListener('fta:language', relabel);
      window.removeEventListener('fta:flush', onFlush);
      window.removeEventListener('fta:advanced', onAdvanced);
      clear(panel);
      if (panel.parentNode === container) container.removeChild(panel);
    },
  };
}
