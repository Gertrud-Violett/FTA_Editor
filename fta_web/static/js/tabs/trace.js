/**
 * tabs/trace.js -- the Traceability tab (1.7, workstream C).
 *
 * One table row per node (pre-order): id, name, and the six `trace` fields
 * (requirementId, testRef, owner, status, evidence, tags), edited in place.
 *
 * EDITING
 *   Cells are plain text until clicked (or Enter/F2 on a focused cell), so a
 *   tree of a thousand nodes costs a thousand rows of text, not seven
 *   thousand live inputs. Enter or leaving the cell commits, Escape reverts.
 *   A commit is `PATCH /api/nodes/<id> {trace: {field: value}}` -- a partial
 *   merge on the server (node_schema.merge_partial); an emptied cell sends
 *   null, which removes the key. Tags are typed comma-separated and sent as an
 *   array. PATCHes are chained so they reach the server in the order typed,
 *   and the chain is handed to the shell on `fta:flush` so Save waits for it.
 *
 * EVIDENCE
 *   Shown as a link only for http(s) URLs, opened in a new tab with
 *   rel="noopener noreferrer". Anything else (javascript:, file:, a note) is
 *   shown as text and never becomes an href.
 *
 * NAVIGATION
 *   Clicking an id or a name calls ctx.jumpTo(id): the tree reveals, scrolls
 *   to and focuses the node, and Details follows the selection.
 */
import { clear, el, injectStyles } from '../dialogs.js';
import { TRACE_STATUS } from '../schema.js';
import strings from '../i18n/trace.js';

export const id = 'trace';
export const advanced = true;

const FIELDS = Object.freeze(['requirementId', 'testRef', 'owner', 'status', 'evidence', 'tags']);
const COLUMNS = Object.freeze(['id', 'name', ...FIELDS]);
const SAFE_URL = /^https?:\/\/[^\s]+$/i;

const CSS = `
.trace-tab { display: flex; flex-direction: column; gap: 0.4rem; min-height: 0; height: 100%;
  font-size: 0.85rem; color: var(--fta-fg); }
.trace-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem 0.75rem; }
.trace-toolbar input[type="search"], .trace-toolbar select, .trace-cell-input, .trace-cell-select {
  font: inherit; color: var(--fta-fg); background: var(--fta-surface);
  border: 1px solid var(--fta-border); border-radius: var(--fta-radius); padding: 0.15rem 0.35rem; }
.trace-toolbar input[type="search"] { min-width: 14rem; flex: 1 1 14rem; max-width: 26rem; }
.trace-toolbar label { display: inline-flex; align-items: center; gap: 0.3rem; white-space: nowrap; }
.trace-toolbar button { font: inherit; cursor: pointer; color: var(--fta-fg); background: var(--fta-surface-2, var(--fta-surface));
  border: 1px solid var(--fta-border); border-radius: var(--fta-radius); padding: 0.2rem 0.6rem; }
.trace-toolbar button:hover { background: var(--fta-surface-hover, var(--fta-surface)); }
.trace-summary { color: var(--fta-muted-fg); font-size: 0.8rem; }
.trace-hint { margin: 0; color: var(--fta-muted-fg); font-size: 0.75rem; }
.trace-scroll { flex: 1 1 auto; min-height: 6rem; overflow: auto; border: 1px solid var(--fta-border);
  border-radius: var(--fta-radius); }
.trace-table { border-collapse: collapse; width: 100%; }
.trace-table th, .trace-table td { border-bottom: 1px solid var(--fta-border); padding: 0.2rem 0.4rem;
  text-align: left; vertical-align: middle; }
.trace-table th { position: sticky; top: 0; z-index: 1; background: var(--fta-surface-2, var(--fta-surface));
  font-weight: 600; white-space: nowrap; }
.trace-table tbody tr:hover td { background: var(--fta-surface-hover, transparent); }
.trace-table tr.is-selected td { background: var(--fta-tree-selected-tint, rgba(0,120,255,0.12)); }
.trace-table td.trace-id { font-family: ui-monospace, Consolas, monospace; font-size: 0.8rem; white-space: nowrap; }
.trace-table td.trace-id, .trace-table td.trace-name { cursor: pointer; color: var(--fta-accent); }
.trace-table td.trace-id:hover, .trace-table td.trace-name:hover { text-decoration: underline; }
.trace-table td.trace-name { max-width: 22rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.trace-table td.trace-edit { cursor: text; min-width: 6rem; }
.trace-table td.trace-edit:focus { outline: 2px solid var(--fta-focus-ring); outline-offset: -2px; }
.trace-table td.trace-edit.is-editing { padding: 0.05rem 0.15rem; }
.trace-table td.trace-edit.is-saving { opacity: 0.6; }
.trace-cell-input, .trace-cell-select { width: 100%; box-sizing: border-box; min-width: 6rem; }
.trace-chip { display: inline-block; margin: 0 0.2rem 0.1rem 0; padding: 0 0.4rem; border-radius: 999px;
  border: 1px solid var(--fta-border); background: var(--fta-surface-2, var(--fta-surface)); font-size: 0.75rem; }
.trace-status { display: inline-block; padding: 0 0.4rem; border-radius: 999px; font-size: 0.75rem;
  border: 1px solid var(--fta-border); }
.trace-status--approved { color: var(--fta-accent-fg, #fff); background: var(--fta-accent); border-color: var(--fta-accent); }
.trace-status--reviewed { border-color: var(--fta-accent); color: var(--fta-accent); }
.trace-status--draft { color: var(--fta-muted-fg); }
.trace-missing { color: var(--fta-muted-fg); }
.trace-empty { padding: 0.75rem; color: var(--fta-muted-fg); }
.trace-f-evidence a { color: var(--fta-accent); word-break: break-all; }
`;

/** Register this tab's strings once (see i18n/trace.js). */
function registerStrings() {
  const shell = window.ftaShell;
  if (shell && typeof shell.registerStrings === 'function') shell.registerStrings(strings);
}

function textOf(value) {
  return value === null || value === undefined ? '' : String(value);
}

/** The trace block of a node as a flat record for filtering and CSV. */
function recordOf(entry) {
  const node = entry.node || {};
  const trace = node.trace && typeof node.trace === 'object' ? node.trace : {};
  return {
    id: String(entry.id),
    name: textOf(node.name !== undefined ? node.name : entry.name),
    depth: entry.depth || 0,
    requirementId: textOf(trace.requirementId),
    testRef: textOf(trace.testRef),
    owner: textOf(trace.owner),
    status: textOf(trace.status),
    evidence: textOf(trace.evidence),
    tags: Array.isArray(trace.tags) ? trace.tags.map(String) : [],
  };
}

function csvCell(value) {
  const text = Array.isArray(value) ? value.join('; ') : textOf(value);
  return /[",\r\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
}

async function copyText(text) {
  if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_err) {
      /* fall back below */
    }
  }
  const area = document.createElement('textarea');
  area.value = text;
  area.setAttribute('readonly', '');
  area.style.position = 'fixed';
  area.style.left = '-9999px';
  document.body.appendChild(area);
  area.select();
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch (_err) {
    ok = false;
  }
  area.remove();
  return ok;
}

export function mount(panel, ctx) {
  registerStrings();
  injectStyles('fta-trace-css', CSS);
  const t = (key, vars) => (ctx && typeof ctx.t === 'function' ? ctx.t(key, vars) : key);
  const store = ctx.store;

  /* ---- chrome ---- */
  const filterInput = el('input', { type: 'search', autocomplete: 'off', spellcheck: 'false' });
  const statusSelect = el('select');
  const missingBox = el('input', { type: 'checkbox' });
  const missingText = el('span');
  const missingLabel = el('label', {}, [missingBox, missingText]);
  const copyButton = el('button', { type: 'button' });
  const summary = el('span', { class: 'trace-summary', role: 'status', 'aria-live': 'polite' });
  const shown = el('span', { class: 'trace-summary' });
  const toolbar = el('div', { class: 'trace-toolbar' }, [
    filterInput, statusSelect, missingLabel, copyButton, summary, shown,
  ]);
  const hint = el('p', { class: 'trace-hint' });
  const thead = el('thead');
  const tbody = el('tbody');
  const table = el('table', { class: 'trace-table' }, [thead, tbody]);
  const empty = el('div', { class: 'trace-empty', hidden: true });
  const scroll = el('div', { class: 'trace-scroll' }, [table, empty]);
  const root = el('div', { class: 'trace-tab' }, [toolbar, hint, scroll]);
  panel.appendChild(root);

  /* ---- state ---- */
  let records = [];
  let visible = [];
  const rowsById = new Map();
  let editor = null; // {td, id, field, original, input}
  let chain = Promise.resolve();
  let pendingCount = 0;
  let renderWanted = false;
  let active = false;

  function paintStrings() {
    filterInput.placeholder = t('trace.filterPlaceholder');
    filterInput.setAttribute('aria-label', t('trace.filterLabel'));
    statusSelect.setAttribute('aria-label', t('trace.statusFilter'));
    const chosen = statusSelect.value;
    clear(statusSelect);
    statusSelect.append(
      el('option', { value: '', text: t('trace.statusAll') }),
      ...TRACE_STATUS.map((s) => el('option', { value: s, text: t('trace.status.' + s) })),
      el('option', { value: '-', text: t('trace.statusNone') })
    );
    statusSelect.value = chosen || '';
    missingText.textContent = t('trace.onlyMissing');
    copyButton.textContent = t('trace.copyCsv');
    copyButton.title = t('trace.copyCsvTitle');
    hint.textContent = t('trace.editHint');
    table.setAttribute('aria-label', t('trace.tableLabel'));
    clear(thead);
    thead.appendChild(
      el('tr', {}, COLUMNS.map((c) => el('th', { scope: 'col', text: t('trace.col.' + c) })))
    );
  }

  /* ---- data ---- */
  function readRecords() {
    let flat = [];
    try {
      flat = store.flat() || [];
    } catch (_err) {
      flat = [];
    }
    records = flat.map(recordOf);
  }

  function passes(rec) {
    const status = statusSelect.value;
    if (status === '-' && rec.status) return false;
    if (status && status !== '-' && rec.status !== status) return false;
    if (missingBox.checked && rec.requirementId.trim()) return false;
    const needle = filterInput.value.trim().toLowerCase();
    if (!needle) return true;
    const hay = [rec.id, rec.name, rec.requirementId, rec.testRef, rec.owner, rec.status,
      rec.evidence, rec.tags.join(' ')].join('\u0001').toLowerCase();
    return hay.indexOf(needle) !== -1;
  }

  function paintSummary() {
    const total = records.length;
    const req = records.filter((r) => r.requirementId.trim()).length;
    const approved = records.filter((r) => r.status === 'approved').length;
    const share = total ? (req / total) * 100 : 0;
    // One decimal below 10 % so a single traced node in a big tree is not "0%".
    const pct = total ? (share > 0 && share < 10 ? share.toFixed(1) : String(Math.round(share))) + '%' : '—';
    summary.textContent = t('trace.coverage', { req, approved, total, pct });
    shown.textContent = t('trace.shown', { n: visible.length, total });
  }

  /* ---- cells ---- */
  function statusBadge(value) {
    if (!value) return el('span', { class: 'trace-missing', text: t('trace.status.unset') });
    return el('span', {
      class: 'trace-status trace-status--' + value,
      text: TRACE_STATUS.includes(value) ? t('trace.status.' + value) : value,
    });
  }

  function fillCell(td, rec, field) {
    clear(td);
    td.classList.remove('is-editing');
    const value = rec[field];
    if (field === 'status') {
      td.appendChild(statusBadge(value));
    } else if (field === 'tags') {
      for (const tag of value) td.appendChild(el('span', { class: 'trace-chip', text: tag }));
    } else if (field === 'evidence' && value && SAFE_URL.test(value.trim())) {
      // Only http(s) ever becomes an href; the check runs on the trimmed value
      // that is also what the href gets.
      td.appendChild(
        el('a', {
          href: value.trim(),
          target: '_blank',
          rel: 'noopener noreferrer',
          title: t('trace.openEvidence'),
          text: value,
        })
      );
    } else {
      td.textContent = value;
    }
  }

  function buildRow(rec) {
    const tr = el('tr', { dataset: { id: rec.id } });
    if (String(store.selectedId) === rec.id) tr.classList.add('is-selected');
    const idCell = el('td', { class: 'trace-id', text: rec.id, title: rec.id });
    const nameCell = el('td', { class: 'trace-name', text: rec.name, title: rec.name });
    nameCell.style.paddingLeft = 0.4 + Math.min(rec.depth, 12) * 0.8 + 'rem';
    tr.append(idCell, nameCell);
    for (const field of FIELDS) {
      const td = el('td', {
        class: 'trace-edit trace-f-' + field,
        tabindex: '0',
        dataset: { field },
        'aria-label': t('trace.editCell', { field: t('trace.col.' + field), name: rec.name || rec.id }),
      });
      fillCell(td, rec, field);
      tr.appendChild(td);
    }
    return tr;
  }

  function render() {
    if (editor) {
      // Rebuilding would throw away the cell being typed in; do it after.
      renderWanted = true;
      return;
    }
    renderWanted = false;
    readRecords();
    visible = records.filter(passes);
    rowsById.clear();
    const frag = document.createDocumentFragment();
    for (const rec of visible) {
      const tr = buildRow(rec);
      rowsById.set(rec.id, tr);
      frag.appendChild(tr);
    }
    clear(tbody);
    tbody.appendChild(frag);
    const noTree = !records.length;
    empty.hidden = visible.length > 0;
    empty.textContent = noTree ? t('trace.noTree') : t('trace.empty');
    table.hidden = !visible.length;
    paintSummary();
  }

  function recordById(nodeId) {
    return records.find((r) => r.id === nodeId) || null;
  }

  /* ---- editing ---- */
  function startEdit(td) {
    if (!td || editor) return;
    const tr = td.closest('tr');
    const nodeId = tr && tr.dataset.id;
    const field = td.dataset.field;
    const rec = nodeId && recordById(nodeId);
    if (!rec || !field) return;
    let input;
    let original;
    if (field === 'status') {
      original = rec.status;
      input = el('select', { class: 'trace-cell-select' }, [
        el('option', { value: '', text: t('trace.status.unset') }),
        ...TRACE_STATUS.map((s) => el('option', { value: s, text: t('trace.status.' + s) })),
      ]);
      input.value = original;
    } else {
      original = field === 'tags' ? rec.tags.join(', ') : rec[field];
      input = el('input', {
        type: 'text',
        class: 'trace-cell-input',
        autocomplete: 'off',
        spellcheck: 'false',
        placeholder: field === 'tags' ? t('trace.tagsPlaceholder') : null,
      });
      input.value = original;
    }
    input.setAttribute('aria-label', td.getAttribute('aria-label') || field);
    editor = { td, id: nodeId, field, original, input };
    clear(td);
    td.classList.add('is-editing');
    td.appendChild(input);
    input.addEventListener('keydown', onEditorKey);
    input.addEventListener('blur', () => finishEdit(true));
    if (field === 'status') input.addEventListener('change', () => finishEdit(true));
    input.focus();
    if (typeof input.select === 'function' && field !== 'status') input.select();
    if (store.selectedId !== nodeId) {
      try {
        store.select(nodeId);
      } catch (_err) {
        /* selection is a convenience here */
      }
    }
  }

  function onEditorKey(event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      finishEdit(true, true);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      finishEdit(false, true);
    }
  }

  function parseValue(field, raw) {
    if (field === 'tags') {
      const tags = [];
      for (const part of String(raw).split(/[,、，]/)) {
        const tag = part.trim();
        if (tag && !tags.includes(tag)) tags.push(tag);
      }
      return tags.length ? tags : null;
    }
    const text = String(raw).trim();
    return text ? text : null;
  }

  function finishEdit(commit, refocus) {
    if (!editor) return;
    const { td, id: nodeId, field, original, input } = editor;
    editor = null;
    const raw = input.value;
    const rec = recordById(nodeId);
    const changed = commit && String(raw).trim() !== String(original).trim();
    if (rec) {
      if (changed) {
        // Optimistic paint; the server's answer re-renders the row.
        const value = parseValue(field, raw);
        const shownRec = { ...rec, [field]: field === 'tags' ? value || [] : value || '' };
        fillCell(td, shownRec, field);
        td.classList.add('is-saving');
        send(nodeId, field, value);
      } else {
        fillCell(td, rec, field);
      }
    }
    if (refocus && td.isConnected) td.focus();
    if (renderWanted && !changed) render();
  }

  function send(nodeId, field, value) {
    pendingCount += 1;
    const body = { trace: { [field]: value } };
    chain = chain
      .catch(() => {})
      .then(() => ctx.api.patch('/nodes/' + encodeURIComponent(nodeId), body))
      .then((res) => {
        if (res) store.applyMutation(res);
      })
      .catch((err) => {
        ctx.showError(err);
      })
      .finally(() => {
        pendingCount -= 1;
        // The mutation notifies the host, which calls onStale -> render; make
        // sure a failed PATCH repaints the reverted value too.
        if (!pendingCount) render();
      });
    return chain;
  }

  /* ---- events ---- */
  function onTableClick(event) {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;
    if (target.closest('a')) return; // evidence link: let it open
    const td = target.closest('td');
    if (!td || !tbody.contains(td)) return;
    const tr = td.closest('tr');
    if (td.classList.contains('trace-id') || td.classList.contains('trace-name')) {
      ctx.jumpTo(tr.dataset.id);
      return;
    }
    if (td.classList.contains('trace-edit') && !td.classList.contains('is-editing')) startEdit(td);
  }

  function onTableKey(event) {
    const td = event.target instanceof Element ? event.target.closest('td.trace-edit') : null;
    if (!td || td.classList.contains('is-editing')) return;
    if (event.key === 'Enter' || event.key === 'F2') {
      event.preventDefault();
      startEdit(td);
    }
  }

  let filterTimer = 0;
  filterInput.addEventListener('input', () => {
    window.clearTimeout(filterTimer);
    filterTimer = window.setTimeout(render, 120);
  });
  statusSelect.addEventListener('change', render);
  missingBox.addEventListener('change', render);
  tbody.addEventListener('click', onTableClick);
  tbody.addEventListener('keydown', onTableKey);

  copyButton.addEventListener('click', async () => {
    // Headers are the stable field names (not the translated labels), so the
    // CSV reads the same whatever language the UI is in.
    const lines = [COLUMNS.join(',')];
    for (const rec of visible) lines.push(COLUMNS.map((c) => csvCell(rec[c])).join(','));
    const ok = await copyText(lines.join('\r\n') + '\r\n');
    if (ok) ctx.toast(t('trace.copied', { n: visible.length }), 'info');
    else ctx.toast(t('trace.copyFailed'), 'error');
  });

  function onFlush(event) {
    const detail = event && event.detail;
    if (!detail || !Array.isArray(detail.promises)) return;
    if (editor) finishEdit(true);
    if (pendingCount) detail.promises.push(chain);
  }

  function onLanguage() {
    paintStrings();
    render();
  }

  // Selection follows the store without a full rebuild.
  let lastSelected = null;
  const unsubscribe = store.subscribe(() => {
    const sel = store.selectedId === null || store.selectedId === undefined ? null : String(store.selectedId);
    if (sel === lastSelected) return;
    const before = lastSelected && rowsById.get(lastSelected);
    if (before) before.classList.remove('is-selected');
    const after = sel && rowsById.get(sel);
    if (after) after.classList.add('is-selected');
    lastSelected = sel;
  });

  window.addEventListener('fta:flush', onFlush);
  window.addEventListener('fta:language', onLanguage);

  paintStrings();
  render();

  return {
    activate() {
      active = true;
      if (renderWanted) render();
    },
    deactivate() {
      active = false;
      if (editor) finishEdit(true);
    },
    onStale() {
      render();
    },
    dispose() {
      window.removeEventListener('fta:flush', onFlush);
      window.removeEventListener('fta:language', onLanguage);
      if (typeof unsubscribe === 'function') unsubscribe();
      window.clearTimeout(filterTimer);
      root.remove();
    },
    /** Test seam. */
    get isActive() {
      return active;
    },
  };
}

export default mount;
