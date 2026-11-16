/**
 * tabs/ccf.js -- the CCF groups tab (F2, F2A): common-cause failure groups with
 * the beta factor or, for 2 to 4 members, the alpha factors.
 *
 * Layout: a toolbar ("New group from selection", "Add selected events"), the
 * table of groups (name, model, parameters, members, source, status), an inline
 * editor for the selected group or for a new draft, and the Assumptions box
 * with the note that CCF results need a qualified engineer's check.
 *
 * Data: GET /api/ccf/groups on activate, on stale (debounced) and on a new
 * document; POST / PATCH / DELETE /api/ccf/groups[/id] for edits, each of them
 * one undo step. The status of a group (applied or not, the reason in both
 * languages, the warnings) is worked out by the server (fta_web/ccf.py): this
 * file only shows it.
 *
 * Commit conventions follow the other tabs: a text field commits on blur or
 * Enter, Escape restores the last saved value, an IME composition is left
 * alone. beta is read by numfmt.parseNumberText ("10%" is 0.1) and must be a
 * number from 0 to 1; anything else shows the message right under the field
 * and sends nothing. A new group starts as a draft with an EMPTY beta: there is
 * no default, so nobody ends up with an engineering assumption they did not
 * make.
 *
 * Alpha model (F2A): alpha1..alphaM (M = members) are read the same way and sent
 * together by "Save α values" (one request, one undo step); the testing scheme
 * has no preselected value. Choosing the other model in the selector of a saved
 * group only changes what the editor shows: the one PATCH that switches the
 * model goes out when the new model's values are committed, so a stray key on
 * the closed selector never nulls a stored value.
 */
import cat from '../i18n/ccf.js';
import { injectStyles } from '../dialogs.js';
import { parseNumberText } from '../numfmt.js';
import { groupName, membersOfGroup } from '../ccf_util.js';
import { clear, debounce, el, ensureStyles, isEta, reportError, translator } from './analysis_common.js';

window.ftaShell?.registerStrings?.(cat);

export const id = 'ccf';
export const advanced = true;

const SOURCE = 'ccf';
const STALE_DELAY_MS = 400;
const ASSUMPTIONS = ['model', 'qt', 'beta', 'split', 'headline', 'sampling'];
const COLUMNS = ['name', 'model', 'params', 'members', 'source', 'status'];
const ALPHA_FIELDS = 4; // an alpha group has 2 to 4 members (FN-43)
// The sum rule of fta_web/ccf.py (ALPHA_SUM_EXACT, ALPHA_SUM_TOLERANCE, ALPHA_SUM_SLACK).
const SUM_EXACT = 1e-9 + 1e-15;
const SUM_TOLERANCE = 1e-3 + 1e-15;
const SUM_KEYS = { none: 'ccf.alpha.sumNone', ok: 'ccf.alpha.sumOk', normalised: 'ccf.alpha.sumNormalised', bad: 'ccf.alpha.sumBad' };

const STYLES = `
.anl-ccf .ccf-toolbar-status { color: var(--text-dim); margin-left: auto; }
.anl-ccf .anl-table td.ccf-col-members { min-width: 14ch; }
.anl-ccf .ccf-status__warning { margin-top: 2px; color: var(--warn); font-size: var(--fs-xs, 11px); }
.anl-ccf .anl-badge[data-status="not-applied"] { white-space: normal; border-radius: var(--r-sm, 5px); line-height: 1.35; }
.anl-ccf .ccf-editor { display: flex; flex-direction: column; gap: 6px; }
.anl-ccf .ccf-editor__grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px 14px; align-items: start; }
.anl-ccf .ccf-field { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.anl-ccf .ccf-field > label { color: var(--text-dim); }
.anl-ccf .ccf-field input[type="text"], .anl-ccf .ccf-field select { width: 100%; box-sizing: border-box; }
.anl-ccf .ccf-error { margin: 0; color: var(--danger); font-size: var(--fs-xs, 11px); min-height: 0; }
.anl-ccf .ccf-error[hidden] { display: none; }
.anl-ccf .ccf-members { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 4px; }
.anl-ccf .ccf-chip { display: inline-flex; align-items: center; gap: 2px; padding: 0 2px 0 7px; border-radius: 999px;
  background: var(--accent-soft); color: var(--accent-hover); }
.anl-ccf .ccf-chip.is-missing { background: var(--warn-soft); color: var(--warn); }
.anl-ccf .ccf-chip button { border: 0; background: none; color: inherit; cursor: pointer; font: inherit; padding: 0 5px; border-radius: 999px; }
.anl-ccf .ccf-chip button:hover { background: var(--accent-hover); color: var(--surface); }
.anl-ccf .ccf-chip button:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
.anl-ccf .ccf-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.anl-ccf .ccf-actions .anl-grow { flex: 1 1 auto; }
.anl-ccf .ccf-alpha { display: flex; flex-direction: column; gap: 6px; margin: 0; min-width: 0;
  border: 1px solid var(--border); border-radius: var(--r-sm, 5px); padding: 6px 10px 8px; }
.anl-ccf .ccf-alpha > .btn { align-self: flex-start; }
.anl-ccf .ccf-alpha legend { padding: 0 4px; color: var(--text-dim); }
.anl-ccf .ccf-alpha__fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px 14px; align-items: start; }
.anl-ccf .ccf-help, .anl-ccf .ccf-sum, .anl-ccf .ccf-editor__status, .anl-ccf .ccf-alpha__size { margin: 0; }
.anl-ccf .ccf-alpha__size { color: var(--warn); }
.anl-ccf .ccf-help { color: var(--text-dim); font-size: var(--fs-xs, 11px); }
.anl-ccf .ccf-sum { color: var(--text-dim); }
.anl-ccf .ccf-sum--note { color: var(--warn); }
.anl-ccf .ccf-sum--bad { color: var(--danger); }
.anl-ccf .ccf-sum[hidden] { display: none; }
.anl-ccf .ccf-editor__status .ccf-status__warning { display: block; }
.anl-ccf .ccf-assumptions ul { margin: 0 0 6px; padding-left: 1.3em; }
.anl-ccf .ccf-assumptions li { margin: 2px 0; }
.anl-ccf .ccf-assumptions .anl-note { font-weight: 600; color: var(--text); }
`;

let controlSeq = 0;
function controlId(prefix) {
  controlSeq += 1;
  return prefix + '-' + controlSeq;
}

function isLeaf(node) {
  return Boolean(node) && !(Array.isArray(node.children) && node.children.length);
}

/** Read a typed beta: {ok, value, text} with 0 <= value <= 1, or {ok: false}. */
export function readBeta(raw) {
  const read = parseNumberText(raw);
  if (!read.ok || !(read.value >= 0 && read.value <= 1)) return { ok: false };
  return { ok: true, value: read.value, text: read.text };
}

/** Read a typed alpha_k: the same rule as beta (FN-46, a number from 0 to 1). */
export const readAlpha = readBeta;

/**
 * The live sum of the alpha fields shown: {state, sum?, used?}. `state` is
 * none (a field is empty or invalid), ok, normalised (each alpha is divided by
 * the sum) or bad, by the rule of the server (fta_web/ccf.py).
 */
function alphaSum(texts, count) {
  const values = texts.slice(0, count).map(readAlpha);
  if (!count || values.some((v) => !v.ok)) return { state: 'none' };
  const sum = values.reduce((total, v) => total + v.value, 0);
  const off = Math.abs(sum - 1);
  const state = off <= SUM_EXACT ? 'ok' : off <= SUM_TOLERANCE ? 'normalised' : 'bad';
  const used = values.map((v) => String(Number((v.value / sum).toPrecision(6)))).join(', ');
  return { state, sum: String(Number(sum.toPrecision(12))), used };
}

/** The editor's texts for a saved group, as the server stores it (alpha padded to four fields). */
function storedForm(group, dataKey) {
  const stored = Array.isArray(group.alpha) ? group.alpha : [];
  return {
    gid: group.id,
    dataKey,
    model: group.model === 'alpha' ? 'alpha' : 'beta',
    beta: group.beta === null || group.beta === undefined ? '' : String(group.beta),
    alpha: Array.from({ length: ALPHA_FIELDS }, (_, i) => (stored[i] === undefined ? '' : String(stored[i]))),
    testing: group.testing === 'staggered' || group.testing === 'nonStaggered' ? group.testing : '',
  };
}

export function mount(panel, ctx) {
  ensureStyles();
  injectStyles('fta-ccf-css', STYLES);
  const t = translator(ctx);
  const lang = () => (window.ftaShell && window.ftaShell.language === 'ja' ? 'ja' : 'en');

  // ---- state ---------------------------------------------------------------------
  let groups = [];
  let mode = 'FTA';
  let loaded = false;
  let failure = null;
  let loading = false;
  let selectedId = null;
  let draft = null; // {name, model, beta, alpha: [4 texts], testing, source, members}
  let local = null; // the texts of the saved group in the editor: storedForm() plus what was typed
  let shown = null; // what the editor on screen is about: {form, count (members), group}
  let seq = 0;
  let pending = Promise.resolve();
  let active = false;
  let disposed = false;
  let pendingSelect = null;
  let editorKey = '';

  const root = el('div', { class: 'anl anl-ccf', dataset: { tab: 'ccf' }, role: 'region' });
  panel.appendChild(root);

  // ---- skeleton ------------------------------------------------------------------
  const newBtn = el('button', { type: 'button', class: 'btn btn--primary', dataset: { role: 'new' } });
  const addBtn = el('button', { type: 'button', class: 'btn', dataset: { role: 'add-selected' } });
  const statusLine = el('span', { class: 'ccf-toolbar-status', role: 'status', 'aria-live': 'polite' });
  const toolbar = el('div', { class: 'anl-toolbar' }, [newBtn, addBtn, statusLine]);
  const etaNote = el('p', { class: 'anl-note', hidden: true, dataset: { role: 'eta-note' } });
  const message = el('p', { class: 'anl-empty', hidden: true });
  const tableWrap = el('div', { class: 'anl-tablewrap', hidden: true });
  const editorHost = el('div', { class: 'anl-section', hidden: true, dataset: { section: 'editor' } });
  const assumptions = el('section', { class: 'anl-section ccf-assumptions', dataset: { section: 'assumptions' } });
  root.append(toolbar, etaNote, message, tableWrap, editorHost, assumptions);

  // ---- helpers ---------------------------------------------------------------------
  const current = () => groups.find((g) => g.id === selectedId) || null;

  function selectedLeaves() {
    const ids = typeof ctx.selection === 'function' ? ctx.selection() : [];
    const seen = new Set();
    const leaves = [];
    let skipped = 0;
    for (const nodeId of ids) {
      const key = String(nodeId);
      if (seen.has(key)) continue;
      seen.add(key);
      if (isLeaf(ctx.store.findNode(key))) leaves.push(key);
      else skipped += 1;
    }
    return { leaves, skipped };
  }

  /** The focusable "disabled" pattern of app.css: aria-disabled, with the reason in the title. */
  function setDisabled(button, off, title) {
    button.setAttribute('aria-disabled', off ? 'true' : 'false');
    // White text on the disabled button's pale ground would vanish: the accent
    // colour is only for a button that can be pressed.
    if (button === newBtn) button.classList.toggle('btn--primary', !off);
    if (title !== undefined) button.title = title;
  }

  function nodeNameOf(memberId) {
    const node = ctx.store.findNode(memberId);
    return node && node.name ? String(node.name) : null;
  }

  function memberLabel(memberId, name) {
    const known = name || nodeNameOf(memberId);
    return known === null || known === undefined ? t('ccf.memberMissing', { id: memberId }) : String(known);
  }

  function defaultName() {
    const used = new Set(groups.map((g) => g.name));
    let n = 1;
    while (used.has(t('ccf.defaultName', { n }))) n += 1;
    return t('ccf.defaultName', { n });
  }

  /**
   * Mark the selected group's members in the tree and the diagram. Only while the tab is shown (an answer that
   * arrives after the tab was left paints nothing; deactivate has cleared the marks), and only when the member
   * list differs from the marks already shown: a rename or a beta edit must not make the tree reveal the members
   * again and reopen a branch the user closed. Undo and Redo change the list, so they still update the marks.
   */
  function highlightGroup() {
    if (!active) return;
    const group = current();
    if (group && Array.isArray(group.members) && group.members.length) {
      const ids = group.members.filter((m) => typeof m === 'string');
      const shown = ctx.store && ctx.store.highlight;
      if (shown && shown.source === SOURCE && shown.ids.length === ids.length && shown.ids.every((id, i) => id === ids[i])) return;
      ctx.highlight(ids, SOURCE);
    } else {
      ctx.clearHighlight(SOURCE);
    }
  }

  // ---- data ------------------------------------------------------------------------
  async function load() {
    if (disposed || !ctx.api) return;
    const mine = ++seq;
    loading = true;
    paintStatus();
    try {
      const res = await ctx.api.get('/ccf/groups');
      if (mine !== seq || disposed) return;
      groups = Array.isArray(res.groups) ? res.groups : [];
      mode = res.mode === 'ETA' ? 'ETA' : 'FTA';
      failure = null;
      loaded = true;
    } catch (err) {
      if (mine !== seq || disposed) return;
      failure = err;
    } finally {
      if (mine === seq) loading = false;
    }
    afterData();
  }

  const loadSoon = debounce(load, STALE_DELAY_MS);

  function afterData() {
    if (pendingSelect !== null && loaded) {
      if (groups.some((g) => g.id === pendingSelect)) {
        selectedId = pendingSelect;
        draft = null;
        highlightGroup();
      }
      pendingSelect = null;
    }
    if (selectedId !== null && !current()) {
      selectedId = null;
      highlightGroup();
    } else if (active && selectedId !== null) {
      // Undo, Redo and any other reload can change the member list of the selected group: the marks follow it
      highlightGroup();
    }
    paint();
  }

  /** One write at a time, in order. Resolves the response, or null after an error. */
  function send(task) {
    const request = pending.then(task);
    pending = request.then(() => undefined, () => undefined);
    return request;
  }

  function applyResponse(res) {
    if (res && Array.isArray(res.groups)) {
      groups = res.groups;
      loaded = true;
      failure = null;
    }
    if (res) ctx.store.applyMutation(res);
  }

  /** PATCH one group; the response repaints. `field` names the editor field an error belongs to. */
  function patchGroup(groupId, body, field) {
    return send(async () => {
      try {
        const res = await ctx.api.patch('/ccf/groups/' + encodeURIComponent(groupId), body);
        applyResponse(res);
        if (body && body.members && groupId === selectedId) highlightGroup(); // the marks follow the new member list
        afterData();
        return res;
      } catch (err) {
        editorKey = '';
        afterData();
        showFieldError(err, field);
        return null;
      }
    });
  }

  /** Show a refusal under the field it names (an alpha index marks that alpha field); else as a toast. */
  function showFieldError(err, field) {
    const detail = err && err.detail ? err.detail : {};
    let named = typeof detail.field === 'string' ? detail.field : field;
    if (named === 'alpha' && Number.isInteger(detail.index)) named = 'alpha' + (detail.index + 1);
    const slot = typeof named === 'string' ? editorHost.querySelector('p[data-error="' + CSS.escape(named) + '"]') : null;
    if (slot) {
      slot.textContent = named === 'testing' ? t('ccf.err.testing', { error: err.message || '' }) : err.message || '';
      slot.hidden = false;
      const input = editorHost.querySelector('input[data-field="' + CSS.escape(named) + '"]');
      if (input) {
        input.classList.add('anl-invalid');
        input.setAttribute('aria-invalid', 'true');
      }
      return;
    }
    reportError(ctx, err);
  }

  // ---- painting ----------------------------------------------------------------------
  function paintStatus() {
    if (failure) statusLine.textContent = t('ccf.failed', { error: failure.message || String(failure) });
    else if (loading && !loaded) statusLine.textContent = t('ccf.loading');
    else statusLine.textContent = '';
    statusLine.style.color = failure ? 'var(--danger)' : '';
  }

  function paintToolbar() {
    newBtn.textContent = t('ccf.new');
    addBtn.textContent = t('ccf.addSelected');
    const { leaves } = selectedLeaves();
    const canNew = leaves.length >= 2;
    setDisabled(newBtn, !canNew, canNew ? t('ccf.newTitle') : t('ccf.newNeedTwo'));
    const target = draft || current();
    const canAdd = Boolean(target) && leaves.length > 0;
    setDisabled(addBtn, !canAdd, target ? t('ccf.addSelected') : t('ccf.addNeedGroup'));
  }

  const reasonOf = (item) => (item && item.reason ? item.reason[lang()] || item.reason.en || '' : '');

  function warningLines(status, tag) {
    return (status.warnings || []).map((w) => el(tag, { class: 'ccf-status__warning', text: t('ccf.status.warning', { reason: reasonOf(w) }) }));
  }

  function statusCell(group) {
    const status = group.status || {};
    const td = el('td', { dataset: { col: 'status' } });
    if (status.applied) {
      td.appendChild(el('span', { class: 'anl-badge anl-badge--info', dataset: { status: 'applied' }, text: t('ccf.status.applied') }));
      td.append(...warningLines(status, 'div'));
      return td;
    }
    const reason = reasonOf(status);
    const template = t('ccf.status.notApplied', { reason: '\u0000' }).split('\u0000');
    td.appendChild(el('span', { class: 'anl-badge anl-badge--warn', dataset: { status: 'not-applied' } }, [
      document.createTextNode(template[0] || ''),
      el('span', { class: 'ccf-status__reason', text: reason }),
      document.createTextNode(template[1] || ''),
    ]));
    return td;
  }

  function modelCell(group) {
    if (group.model === 'beta') return t('ccf.model.beta');
    return group.model === 'alpha' ? t('ccf.model.alphaCell') : String(group.model);
  }

  /** `β = 0.1`, or `α = (0.955, 0.034, 0.011)` plus the testing scheme once it is chosen. */
  function paramsCell(group) {
    if (group.model !== 'alpha') return 'β = ' + (group.beta === null || group.beta === undefined ? '—' : String(group.beta));
    const alpha = group.alpha;
    let text = 'α = —';
    if (Array.isArray(alpha) && alpha.every((a) => typeof a === 'number')) text = 'α = (' + alpha.map(String).join(', ') + ')';
    else if (alpha !== null && alpha !== undefined) text = 'α = ' + JSON.stringify(alpha);
    return group.testing === 'staggered' || group.testing === 'nonStaggered' ? text + ', ' + t('ccf.testing.' + group.testing) : text;
  }

  function paintTable() {
    clear(tableWrap);
    tableWrap.hidden = groups.length === 0;
    if (!groups.length) return;
    const head = el('tr', null, COLUMNS.map((col) => el('th', { text: t('ccf.col.' + col) })));
    const body = el('tbody');
    for (const group of groups) {
      const names = Array.isArray(group.memberNames) ? group.memberNames : [];
      const members = (Array.isArray(group.members) ? group.members : []).map((m, i) => memberLabel(String(m), names[i]));
      const on = group.id === selectedId && !draft;
      body.appendChild(el('tr', {
        tabindex: '0',
        class: on ? 'is-selected' : null,
        'aria-selected': on ? 'true' : 'false',
        dataset: { id: group.id },
      }, [
        el('td', { dataset: { col: 'name' }, text: groupName(group) }),
        el('td', { dataset: { col: 'model' }, text: modelCell(group) }),
        el('td', { dataset: { col: 'params' }, text: paramsCell(group) }),
        el('td', { class: 'ccf-col-members', dataset: { col: 'members' }, text: members.join(', ') }),
        el('td', { dataset: { col: 'source' }, text: group.source ? String(group.source) : '—' }),
        statusCell(group),
      ]));
    }
    tableWrap.appendChild(el('table', { class: 'anl-table', 'aria-label': t('ccf.aria'), dataset: { role: 'groups' } }, [
      el('thead', null, [head]),
      body,
    ]));
  }

  function paintAssumptions() {
    clear(assumptions);
    const keys = groups.some((g) => g.model === 'alpha') ? ASSUMPTIONS.concat('alpha') : ASSUMPTIONS;
    assumptions.append(
      el('h3', { text: t('ccf.assumptions') }),
      el('ul', null, keys.map((key) => el('li', { dataset: { assumption: key }, text: t('ccf.assume.' + key) }))),
      el('p', { class: 'anl-note', dataset: { role: 'ccf-note' }, text: t('ccf.note') })
    );
  }

  // ---- the editor ------------------------------------------------------------------------
  /** Label + control + (optional) error paragraph; `help` is the id of a help paragraph that also describes the control. */
  function field(labelText, control, errorFor, help) {
    const wrap = el('div', { class: 'ccf-field' });
    const label = el('label', { text: labelText });
    if (!control.id) control.id = controlId('ccf-field');
    label.setAttribute('for', control.id);
    wrap.append(label, control);
    if (errorFor) {
      const error = el('p', { class: 'ccf-error', hidden: true, role: 'alert', id: control.id + '-error', dataset: { error: errorFor } });
      control.setAttribute('aria-describedby', help ? error.id + ' ' + help : error.id);
      wrap.appendChild(error);
    }
    return wrap;
  }

  function setInvalid(input, message) {
    const slot = input.parentNode && input.parentNode.querySelector('p.ccf-error');
    input.classList.toggle('anl-invalid', Boolean(message));
    if (message) input.setAttribute('aria-invalid', 'true');
    else input.removeAttribute('aria-invalid');
    if (slot) {
      slot.textContent = message || '';
      slot.hidden = !message;
    }
  }

  /**
   * A text input that commits on blur or Enter and reverts on Escape. `read(raw)`
   * returns {ok, value, text?, message?}; `commit(value)` stores it. `extra`:
   * `afterEnter()` runs once Enter has left (and so read) the field;
   * `keepBaseline` leaves the text Escape returns to at the saved one (a field
   * whose commit does not save, like the alpha fields).
   */
  function textInput(key, baseline, read, commit, attrs, extra) {
    const { afterEnter, keepBaseline } = extra || {};
    const input = el('input', Object.assign({ type: 'text', autocomplete: 'off', dataset: { field: key } }, attrs || {}));
    input.value = baseline;
    const state = { baseline, last: baseline }; // `last`: the text read most recently
    input.addEventListener('input', () => setInvalid(input, ''));
    const finish = () => {
      const raw = input.value;
      if (raw.trim() === String(state.last).trim()) {
        setInvalid(input, '');
        return;
      }
      const read1 = read(raw);
      if (!read1.ok) {
        setInvalid(input, read1.message);
        return;
      }
      setInvalid(input, '');
      if (read1.text !== undefined) input.value = read1.text;
      state.last = input.value;
      if (!keepBaseline) state.baseline = input.value;
      commit(read1.value);
    };
    input.addEventListener('blur', finish);
    input.addEventListener('keydown', (event) => {
      if (event.isComposing || event.keyCode === 229) return; // IME composition
      if (event.key === 'Enter') {
        event.preventDefault();
        input.blur();
        if (afterEnter) afterEnter();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        input.value = state.baseline;
        state.last = state.baseline;
        input.dispatchEvent(new Event('input')); // whoever mirrors the text (sum, buttons) follows at once
      }
    });
    return input;
  }

  const readName = (raw) => (raw.trim() ? { ok: true, value: raw.trim() } : { ok: false, message: t('ccf.err.name') });
  const readBetaField = (raw) => {
    const beta = readBeta(raw);
    return beta.ok ? beta : { ok: false, message: t('ccf.err.beta') };
  };

  function membersList(ids, names, onRemove) {
    const list = el('ul', { class: 'ccf-members', dataset: { role: 'members' } });
    ids.forEach((memberId, index) => {
      const label = memberLabel(memberId, names ? names[index] : undefined);
      const missing = (names ? names[index] : nodeNameOf(memberId)) === null && !nodeNameOf(memberId);
      const remove = el('button', {
        type: 'button',
        dataset: { role: 'remove-member' },
        'aria-label': t('ccf.removeMember', { name: label }),
        title: t('ccf.removeMember', { name: label }),
        text: '×',
      });
      remove.addEventListener('click', () => onRemove(memberId));
      list.appendChild(el('li', { class: 'ccf-chip' + (missing ? ' is-missing' : ''), dataset: { member: memberId } }, [
        el('span', { text: label }),
        remove,
      ]));
    });
    return list;
  }

  /** The selector of the editor control that has the focus (so a rebuild can give it back), or null. */
  function focusedSelector() {
    const focused = document.activeElement;
    if (!focused || !focused.dataset || !editorHost.contains(focused)) return null;
    if (focused.dataset.field) return '[data-field="' + focused.dataset.field + '"]';
    return focused.dataset.role === 'alpha-save' ? '[data-role="alpha-save"]' : null;
  }

  /** The model selector: a draft takes the model at once; a saved group only shows the other model's fields (nothing is sent). */
  function chooseModel(value) {
    if (draft) {
      draft.model = value;
    } else {
      const group = current();
      const stored = storedForm(group, local.dataKey);
      local = value === group.model ? stored : Object.assign(stored, { model: value, beta: '', alpha: Array(ALPHA_FIELDS).fill(''), testing: '' });
    }
    editorKey = '';
    paintEditor();
  }

  /**
   * One PATCH with the whole alpha list (plus the model switch and the scheme chosen so far, when the
   * model changes). Answers whether it was sent; the button keeps the focus either way.
   */
  function saveAlpha() {
    const save = editorHost.querySelector('[data-role="alpha-save"]');
    if (!shown || !shown.group || !save || save.getAttribute('aria-disabled') === 'true') return false;
    const { form, count, group } = shown;
    const body = { alpha: alphaValues(form.alpha, count) };
    if (form.model !== group.model) {
      body.model = 'alpha';
      if (form.testing) body.testing = form.testing;
    }
    save.focus();
    patchGroup(group.id, body, 'alpha');
    return true;
  }

  function alphaFieldset(form, count, group) {
    const box = el('fieldset', { class: 'ccf-alpha', dataset: { section: 'alpha' } }, [
      el('legend', { dataset: { role: 'alpha-legend' }, text: t('ccf.field.alphaGroup') }),
    ]);
    if (count < 2 || count > ALPHA_FIELDS) {
      box.appendChild(el('p', { class: 'ccf-alpha__size', dataset: { role: 'alpha-size' }, text: t('ccf.alpha.size', { n: count }) }));
      return box;
    }
    const help = el('p', { class: 'ccf-help', id: controlId('ccf-help'), dataset: { role: 'alpha-help' }, text: t('ccf.alpha.help', { n: count }) });
    const fields = el('div', { class: 'ccf-alpha__fields' });
    for (let k = 0; k < count; k += 1) {
      const message = t('ccf.err.alpha', { k: k + 1 });
      // Escape returns to the saved text: the one of the group, or nothing for a draft or a model switch.
      const saved = group && form.model === group.model && Array.isArray(group.alpha) && group.alpha[k] !== undefined ? String(group.alpha[k]) : '';
      const input = textInput('alpha' + (k + 1), saved, (raw) => {
        const read = readAlpha(raw);
        return read.ok ? read : { ok: false, message };
      }, () => {}, { inputmode: 'decimal', placeholder: t('ccf.alphaHint') }, {
        keepBaseline: true,
        afterEnter: () => { if (!saveAlpha()) input.focus(); },
      });
      input.value = form.alpha[k];
      const sync = () => {
        form.alpha[k] = input.value;
        refreshForm();
      };
      input.addEventListener('input', sync);
      input.addEventListener('blur', sync);
      fields.appendChild(field(t('ccf.field.alpha', { k: k + 1 }), input, 'alpha' + (k + 1), help.id));
    }
    box.append(
      help,
      fields,
      el('p', { class: 'ccf-error', hidden: true, role: 'alert', dataset: { error: 'alpha' } }),
      el('p', { class: 'ccf-sum', 'aria-live': 'polite', dataset: { role: 'alpha-sum' } }),
      el('p', { class: 'ccf-help', hidden: true, dataset: { role: 'alpha-used' } })
    );
    if (group) {
      const stored = Array.isArray(group.alpha) ? group.alpha.length : 0;
      if (form.model === group.model && stored !== count) {
        box.appendChild(el('p', { class: 'ccf-alpha__size', dataset: { role: 'alpha-resize' }, text: t('ccf.alpha.resize', { n: count, count: stored }) }));
      }
      // aria-disabled, not disabled: the button keeps the focus after the save it has just made.
      const save = el('button', { type: 'button', class: 'btn', dataset: { role: 'alpha-save' }, text: t('ccf.alpha.save') });
      save.addEventListener('click', saveAlpha);
      box.appendChild(save);
    }
    return box;
  }

  /** The scheme selector: the empty first option is a real choice, nothing else is preselected. */
  function testingField(form, group, switching) {
    const select = el('select', { dataset: { field: 'testing' } }, [
      el('option', { value: '', text: t('ccf.testing.placeholder') }),
      el('option', { value: 'staggered', text: t('ccf.testing.staggered') }),
      el('option', { value: 'nonStaggered', text: t('ccf.testing.nonStaggered') }),
    ]);
    select.value = form.testing;
    select.addEventListener('change', () => {
      setInvalid(select, '');
      form.testing = select.value;
      if (group && !switching) patchGroup(group.id, { testing: select.value || null }, 'testing');
    });
    const help = el('p', { class: 'ccf-help', id: controlId('ccf-help'), dataset: { role: 'testing-help' }, text: t('ccf.testing.help') });
    const wrap = field(t('ccf.field.testing'), select, 'testing', help.id);
    wrap.appendChild(help);
    return wrap;
  }

  function paintEditor() {
    const group = draft ? null : current();
    editorHost.hidden = !(draft || group);
    if (!draft && !group) {
      editorKey = '';
      shown = null;
      clear(editorHost);
      return;
    }
    const dataKey = draft
      ? 'draft'
      : JSON.stringify([group.id, group.name, group.model, group.beta, group.alpha, group.testing, group.source, group.members]);
    const key = draft ? 'draft' : dataKey + '|' + lang();
    if (key === editorKey) {
      if (shown && group) shown.group = group;
      refreshForm();
      return;
    }
    // Never rebuild the box the user is typing in; focusout tries again. The status line follows at once.
    if (!draft && editorHost.contains(document.activeElement) && document.activeElement.tagName === 'INPUT') {
      if (shown) shown.group = group;
      refreshForm();
      return;
    }
    const refocus = focusedSelector();
    editorKey = key;
    clear(editorHost);

    if (group) {
      // Typed alpha text survives a repaint that changes only the name, source or scheme.
      const localKey = JSON.stringify([group.id, group.model, group.beta, group.alpha, group.members]);
      if (!local || local.dataKey !== localKey) local = storedForm(group, localKey);
      else if (local.model === group.model) local.testing = storedForm(group, localKey).testing;
    }
    const form = draft || local;
    const ids = draft ? draft.members : (Array.isArray(group.members) ? group.members : []).map(String);
    const count = new Set(ids).size;
    const switching = Boolean(group) && form.model !== group.model;
    shown = { form, count, group };

    const heading = el('h3', { text: draft ? t('ccf.editor.new') : t('ccf.editor.edit') });
    const modelSelect = el('select', { dataset: { field: 'model' } }, [
      el('option', { value: 'beta', text: t('ccf.model.beta') }),
      el('option', { value: 'alpha', text: t('ccf.model.alpha') }),
    ]);
    modelSelect.value = form.model;
    modelSelect.addEventListener('change', () => chooseModel(modelSelect.value));
    modelSelect.addEventListener('keydown', (event) => {
      if (event.isComposing || event.keyCode === 229) return;
      if (event.key !== 'Escape' || !switching) return;
      event.preventDefault();
      event.stopPropagation();
      chooseModel(group.model);
    });

    let nameInput;
    let sourceInput;
    let membersEl;
    if (draft) {
      nameInput = textInput('name', draft.name, readName, () => {}, {});
      nameInput.addEventListener('input', () => { draft.name = nameInput.value; refreshForm(); });
      nameInput.addEventListener('blur', () => { draft.name = nameInput.value; refreshForm(); });
      sourceInput = textInput('source', draft.source, (raw) => ({ ok: true, value: raw }), () => {}, {});
      sourceInput.addEventListener('input', () => { draft.source = sourceInput.value; });
      sourceInput.addEventListener('blur', () => { draft.source = sourceInput.value; });
      membersEl = membersList(draft.members, null, (memberId) => {
        draft.members = draft.members.filter((m) => m !== memberId);
        editorKey = '';
        paintEditor();
        paintToolbar();
      });
    } else {
      const gid = group.id;
      nameInput = textInput('name', String(group.name === undefined || group.name === null ? '' : group.name), readName,
        (value) => patchGroup(gid, { name: value }, 'name'), {});
      sourceInput = textInput('source', group.source ? String(group.source) : '', (raw) => ({ ok: true, value: raw.trim() }),
        (value) => patchGroup(gid, { source: value }, 'source'), {});
      membersEl = membersList(ids, Array.isArray(group.memberNames) ? group.memberNames : null, (memberId) => {
        patchGroup(gid, { members: ids.filter((m) => m !== memberId) }, 'members');
      });
    }

    const alpha = form.model === 'alpha';
    const cells = [field(t('ccf.field.name'), nameInput, 'name'), field(t('ccf.field.model'), modelSelect)];
    if (!alpha) {
      const betaInput = textInput('beta', draft ? draft.beta : form.beta, readBetaField,
        draft ? () => {} : (value) => patchGroup(group.id, switching ? { model: 'beta', beta: value } : { beta: value }, 'beta'),
        { inputmode: 'decimal', placeholder: t('ccf.betaHint') });
      if (draft) {
        betaInput.addEventListener('input', () => { draft.beta = betaInput.value; refreshForm(); });
        betaInput.addEventListener('blur', () => { draft.beta = betaInput.value; refreshForm(); });
      }
      cells.push(field(t('ccf.field.beta'), betaInput, 'beta'));
    }
    cells.push(field(t('ccf.field.source'), sourceInput));
    const parts = [el('div', { class: 'ccf-editor__grid' }, cells)];
    if (alpha) parts.push(testingField(form, group, switching), alphaFieldset(form, count, group));
    parts.push(el('div', { class: 'ccf-field' }, [
      el('span', { class: 'ccf-field__label', text: t('ccf.field.members'), style: 'color:var(--text-dim)' }),
      membersEl,
    ]));

    const actions = el('div', { class: 'ccf-actions' });
    if (draft) {
      const create = el('button', { type: 'button', class: 'btn btn--primary', dataset: { role: 'create' }, text: t('ccf.create') });
      const cancel = el('button', { type: 'button', class: 'btn', dataset: { role: 'cancel' }, text: t('ccf.cancel') });
      create.addEventListener('click', () => createDraft());
      cancel.addEventListener('click', () => closeDraft());
      actions.append(create, cancel);
    } else {
      const del = el('button', { type: 'button', class: 'btn', dataset: { role: 'delete' }, text: t('ccf.delete'), title: t('ccf.deleteTitle') });
      del.addEventListener('click', () => deleteGroup(group));
      actions.append(del);
    }
    parts.push(actions);
    if (group) parts.push(el('p', { class: 'ccf-editor__status', 'aria-live': 'polite', dataset: { role: 'group-status' } }));
    editorHost.append(heading, el('div', { class: 'ccf-editor' }, parts));
    refreshForm();
    const back = refocus ? editorHost.querySelector(refocus) : null;
    if (back && !back.disabled) back.focus();
  }

  /** The values of the first `count` alpha texts, or null while one of them is invalid or `count` is not 2 to 4. */
  function alphaValues(texts, count) {
    if (count < 2 || count > ALPHA_FIELDS) return null;
    const reads = texts.slice(0, count).map(readAlpha);
    return reads.every((read) => read.ok) ? reads.map((read) => read.value) : null;
  }

  /** Bring the live parts of the editor in step with the texts and the group: sum, buttons, status line. */
  function refreshForm() {
    if (!shown) return;
    const { form, count, group } = shown;
    const find = (selector) => editorHost.querySelector(selector);
    let valid = readBeta(form.beta).ok;
    if (form.model === 'alpha') {
      const values = alphaValues(form.alpha, count);
      valid = values !== null;
      const info = alphaSum(form.alpha, count);
      const sum = find('p[data-role="alpha-sum"]');
      const used = find('p[data-role="alpha-used"]');
      if (sum && used) {
        sum.textContent = t(SUM_KEYS[info.state], { sum: info.sum });
        sum.className = 'ccf-sum' + (info.state === 'normalised' ? ' ccf-sum--note' : info.state === 'bad' ? ' ccf-sum--bad' : '');
        used.hidden = info.state !== 'normalised';
        used.textContent = used.hidden ? '' : t('ccf.alpha.used', { list: info.used });
      }
      const save = find('[data-role="alpha-save"]');
      if (save && group) {
        const stored = Array.isArray(group.alpha) ? group.alpha : [];
        setDisabled(save, !(valid && (form.model !== group.model || stored.length !== count || values.some((v, i) => v !== stored[i]))));
      }
    }
    const create = find('[data-role="create"]');
    if (create && draft) {
      create.disabled = !(draft.name.trim() && valid);
      create.classList.toggle('btn--primary', !create.disabled);
    }
    const line = find('p[data-role="group-status"]');
    if (line && group) {
      const status = group.status || {};
      const head = status.applied ? t('ccf.status.applied') : t('ccf.status.notApplied', { reason: reasonOf(status) });
      line.replaceChildren(document.createTextNode(head), ...(status.applied ? warningLines(status, 'span') : []));
    }
  }

  function paint() {
    if (disposed) return;
    root.setAttribute('aria-label', t('ccf.aria'));
    const eta = mode === 'ETA' || isEta(ctx);
    etaNote.hidden = !eta;
    etaNote.textContent = eta ? t('ccf.etaNote') : '';
    paintStatus();
    paintToolbar();
    if (!loaded) {
      message.hidden = !loading;
      message.textContent = loading ? t('ccf.loading') : '';
    } else if (!groups.length && !draft) {
      message.hidden = false;
      message.textContent = t('ccf.empty');
    } else {
      message.hidden = true;
      message.textContent = '';
    }
    paintTable();
    paintEditor();
    paintAssumptions();
  }

  // ---- actions ---------------------------------------------------------------------------
  function selectGroup(groupId) {
    if (selectedId === groupId && !draft) return;
    selectedId = groupId;
    draft = null;
    local = null;
    editorKey = '';
    highlightGroup();
    paint();
  }

  function openDraft() {
    const { leaves, skipped } = selectedLeaves();
    if (leaves.length < 2) return;
    if (skipped > 0) ctx.toast(t('ccf.skippedNotBasic', { n: skipped }), 'info');
    draft = {
      name: defaultName(), model: 'beta', beta: '', alpha: Array(ALPHA_FIELDS).fill(''), testing: '', source: '', members: leaves,
    };
    selectedId = null;
    ctx.clearHighlight(SOURCE);
    editorKey = '';
    paint();
    const input = editorHost.querySelector('input[data-field="beta"]');
    if (input) input.focus();
  }

  function closeDraft() {
    draft = null;
    editorKey = '';
    paint();
  }

  function createDraft() {
    if (!draft) return;
    const name = draft.name.trim();
    const body = { name, model: draft.model, members: draft.members.slice(), source: draft.source.trim() };
    if (draft.model === 'alpha') {
      const alpha = alphaValues(draft.alpha, draft.members.length);
      if (!alpha) return;
      body.alpha = alpha;
      if (draft.testing) body.testing = draft.testing;
    } else {
      const beta = readBeta(draft.beta);
      if (!beta.ok) return;
      body.beta = beta.value;
    }
    if (!name) return;
    send(async () => {
      try {
        const res = await ctx.api.post('/ccf/groups', body);
        draft = null;
        editorKey = '';
        applyResponse(res);
        selectedId = res.group ? res.group.id : null;
        highlightGroup();
        afterData();
        ctx.toast(t('ccf.created', { name: res.group ? res.group.name : name }), 'info');
      } catch (err) {
        showFieldError(err, 'name');
      }
    });
  }

  function deleteGroup(group) {
    send(async () => {
      try {
        const res = await ctx.api.del('/ccf/groups/' + encodeURIComponent(group.id));
        selectedId = null;
        editorKey = '';
        applyResponse(res);
        highlightGroup();
        afterData();
        ctx.toast(t('ccf.deleted', { name: group.name }), 'info');
      } catch (err) {
        reportError(ctx, err);
      }
    });
  }

  function addSelected() {
    const { leaves, skipped } = selectedLeaves();
    if (!leaves.length) return;
    if (skipped > 0) ctx.toast(t('ccf.skippedNotBasic', { n: skipped }), 'info');
    if (draft) {
      for (const leaf of leaves) if (!draft.members.includes(leaf)) draft.members.push(leaf);
      editorKey = '';
      paint();
      return;
    }
    const group = current();
    if (!group) return;
    const existing = (Array.isArray(group.members) ? group.members : []).map(String);
    const added = leaves.filter((leaf) => !existing.includes(leaf));
    if (!added.length) return;
    patchGroup(group.id, { members: existing.concat(added) }, 'members');
  }

  // ---- events ----------------------------------------------------------------------------
  const blockedClick = (button, handler) => (event) => {
    if (button.getAttribute('aria-disabled') === 'true') {
      event.preventDefault();
      return;
    }
    handler();
  };
  newBtn.addEventListener('click', blockedClick(newBtn, openDraft));
  addBtn.addEventListener('click', blockedClick(addBtn, addSelected));

  function rowFrom(event) {
    const tr = event.target instanceof Element ? event.target.closest('tr[data-id]') : null;
    return tr ? tr.dataset.id : null;
  }
  tableWrap.addEventListener('click', (event) => {
    const gid = rowFrom(event);
    if (gid !== null) selectGroup(gid);
  });
  tableWrap.addEventListener('keydown', (event) => {
    if (event.isComposing || event.keyCode === 229) return;
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const gid = rowFrom(event);
    if (gid === null) return;
    event.preventDefault();
    selectGroup(gid);
  });

  // A rebuild that waited for a text field to lose the focus is tried again here.
  editorHost.addEventListener('focusout', () => setTimeout(() => { if (!disposed) paintEditor(); }, 0));

  const onSelection = () => paintToolbar();
  const onLanguage = () => {
    editorKey = '';
    paint();
  };
  const onDocument = () => {
    loadSoon.cancel();
    seq += 1;
    groups = [];
    loaded = false;
    selectedId = null;
    draft = null;
    local = null;
    editorKey = '';
    ctx.clearHighlight(SOURCE);
    paint();
    if (active) load();
  };
  const takeRequest = () => {
    const request = typeof ctx.takeTabRequest === 'function' ? ctx.takeTabRequest('ccf') : null;
    if (request && request.groupId) {
      pendingSelect = String(request.groupId);
      if (loaded) afterData();
    }
  };
  const onTabRequest = (event) => {
    if (event && event.detail && event.detail.id === 'ccf') takeRequest();
  };
  window.addEventListener('fta:selection', onSelection);
  window.addEventListener('fta:language', onLanguage);
  window.addEventListener('fta:document', onDocument);
  window.addEventListener('fta:tab-request', onTabRequest);
  const unSig = typeof ctx.onAdvanced === 'function' ? ctx.onAdvanced(() => paint()) : null;

  paint();

  return {
    activate() {
      active = true;
      takeRequest();
      load();
      highlightGroup();
    },
    deactivate() {
      active = false;
      loadSoon.cancel();
      ctx.clearHighlight(SOURCE);
    },
    onStale() {
      loadSoon();
    },
    dispose() {
      disposed = true;
      loadSoon.cancel();
      window.removeEventListener('fta:selection', onSelection);
      window.removeEventListener('fta:language', onLanguage);
      window.removeEventListener('fta:document', onDocument);
      window.removeEventListener('fta:tab-request', onTabRequest);
      if (typeof unSig === 'function') unSig();
      ctx.clearHighlight(SOURCE);
      root.remove();
    },
    /** Test/integration seam: reload now. */
    refresh: load,
  };
}

export default mount;
