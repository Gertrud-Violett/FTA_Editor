/**
 * tabs/quant.js -- the Quantification tab (1.7, workstream A).
 *
 * Three parts:
 *   1. Document settings: the mission time (shown in h / d / y, stored in
 *      hours) through POST /api/analysis/settings.
 *   2. The selected event's model: fixed / rate / standby / repairable, its
 *      parameters (λ entered per hour, per year or in FIT, always stored per
 *      hour), a data source and a lognormal uncertainty. Each field PATCHes
 *      /api/nodes/<id> {quant: {...partial}} (the fixed model's q is the
 *      node's `probability`). The derived q, the formula and the model
 *      warnings come from the node view's `quantDerived`.
 *   3. A compact table of every basic event; a row click selects it.
 *
 * Commit conventions follow details.js: a text field commits on blur or
 * Enter, Escape restores the last saved value, every write goes through one
 * serialised chain, and `fta:flush` (Save, exports) gets that chain's tail.
 */
import cat from '../i18n/quant.js';
import {
  clear,
  debounce,
  el,
  ensureStyles,
  etaNotice,
  formatPlain,
  isEta,
  parseNumber,
  renderWarnings,
  reportError,
  translator,
} from './analysis_common.js';

window.ftaShell?.registerStrings?.(cat);

export const id = 'quant';
export const advanced = true;

const MODELS = ['fixed', 'rate', 'standby', 'repairable'];
const TIME_FACTORS = { h: 1, d: 24, y: 8760 };
/** λ display units -> divide the shown value by this to get per hour (division keeps 2000 FIT = 2e-6 exact). */
const LAMBDA_UNITS = { h: 1, y: 8760, FIT: 1e9 };
const LAMBDA_LABELS = { h: '/h', y: '/y', FIT: 'FIT' };
const LAMBDA_UNIT_KEY = 'fta.lambdaUnit';

function readLambdaUnit() {
  try {
    const raw = window.localStorage.getItem(LAMBDA_UNIT_KEY);
    return Object.prototype.hasOwnProperty.call(LAMBDA_UNITS, raw) ? raw : 'h';
  } catch (_err) {
    return 'h';
  }
}

function writeLambdaUnit(unit) {
  try {
    window.localStorage.setItem(LAMBDA_UNIT_KEY, unit);
  } catch (_err) {
    /* not persisted */
  }
}

function isLeaf(node) {
  return !(node && Array.isArray(node.children) && node.children.length);
}

function nodeKind(node) {
  if (!node) return 'none';
  const gateType = String(node.gateType || '').toUpperCase();
  if (gateType === 'TRANSFER') return 'transfer';
  if (!isLeaf(node)) return 'gate';
  if (String(node.eventKind || '').toLowerCase() === 'house') return 'house';
  return 'event';
}

export function mount(panel, ctx) {
  ensureStyles();
  const t = translator(ctx);
  const fmt = (v) => ctx.fmt.prob(v);

  let active = false;
  let derivedBox = null;
  let derivedWarnings = null;
  let lambdaUnit = readLambdaUnit();
  let view = null; // GET /api/nodes/<id> node view of the selected event
  let viewId = null;
  let formSignature = '';
  let fetchSeq = 0;
  let pending = Promise.resolve();
  const fields = new Map(); // key -> {input, baseline, commit(value)}

  const root = el('div', { class: 'anl anl-quant', dataset: { tab: 'quant' } });
  panel.appendChild(root);

  // ---- writing ------------------------------------------------------------------

  function queue(task) {
    const request = pending.then(task);
    pending = request.then(
      () => undefined,
      () => undefined
    );
    return request;
  }

  function patchNode(nodeId, patch) {
    return queue(async () => {
      try {
        const res = await ctx.api.patch('/nodes/' + encodeURIComponent(nodeId), patch);
        ctx.store.applyMutation(res);
        if (res && res.node && String(res.node.id) === viewId) {
          view = res.node;
          paintSelected();
        }
        return res;
      } catch (err) {
        reportError(ctx, err);
        if (viewId === nodeId) paintSelected(true);
        throw err;
      }
    });
  }

  function postSettings(partial) {
    return queue(async () => {
      try {
        const res = await ctx.api.post('/analysis/settings', partial);
        ctx.store.applyMutation(res);
        return res;
      } catch (err) {
        reportError(ctx, err);
        paintDoc(true);
        throw err;
      }
    });
  }

  function onFlush(event) {
    const detail = event && event.detail;
    if (!detail || !Array.isArray(detail.promises)) return;
    const focused = document.activeElement;
    for (const field of fields.values()) {
      if (field.input === focused) commitField(field);
    }
    detail.promises.push(pending);
  }

  // ---- text-field plumbing --------------------------------------------------------

  /**
   * A committing text input. `parse(raw)` returns {ok, value} (value null =
   * remove); `commit(value)` sends it. Blur/Enter commit, Escape reverts.
   */
  function textField(key, baseline, parse, commit, attrs) {
    const input = el('input', Object.assign({ type: 'text', dataset: { field: key } }, attrs || {}));
    input.value = baseline;
    const field = { key, input, baseline, parse, commit };
    fields.set(key, field);
    input.addEventListener('blur', () => commitField(field));
    input.addEventListener('input', () => input.classList.remove('anl-invalid'));
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        input.blur();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        input.value = field.baseline;
        input.classList.remove('anl-invalid');
      }
    });
    return input;
  }

  function commitField(field) {
    const raw = field.input.value;
    if (raw.trim() === String(field.baseline).trim()) return;
    const parsed = field.parse(raw);
    if (!parsed.ok) {
      field.input.classList.add('anl-invalid');
      field.input.title = parsed.message || '';
      return;
    }
    field.input.classList.remove('anl-invalid');
    field.input.title = '';
    field.baseline = raw;
    field.commit(parsed.value);
  }

  function numberParser(min, { exclusive = false, max = Infinity, allowBlank = true } = {}) {
    return (raw) => {
      const value = parseNumber(raw);
      if (value === null) {
        return allowBlank ? { ok: true, value: null } : { ok: false, message: t('quant.invalid', { min }) };
      }
      if (Number.isNaN(value) || value < min || (exclusive && value === min) || value > max) {
        return { ok: false, message: t('quant.invalid', { min }) };
      }
      return { ok: true, value };
    };
  }

  // ---- document settings ----------------------------------------------------------

  const docSection = el('section', { class: 'anl-section', dataset: { section: 'doc' } });
  const selSection = el('section', { class: 'anl-section', dataset: { section: 'selected' } });
  const tableSection = el('section', { class: 'anl-section', dataset: { section: 'events' } });
  const cols = el('div', { class: 'anl-cols' }, [docSection, selSection]);

  function analysis() {
    return (ctx.store.state && ctx.store.state.analysis) || {};
  }

  function paintDoc(force) {
    const a = analysis();
    const unit = TIME_FACTORS[a.timeUnit] ? a.timeUnit : 'h';
    const hours = Number(a.missionTime) || 8760;
    const shown = formatPlain(hours / TIME_FACTORS[unit]);
    const existing = fields.get('missionTime');
    if (existing && document.activeElement === existing.input && !force) return;
    clear(docSection);
    const input = textField('missionTime', shown, numberParser(0, { exclusive: true, allowBlank: false }),
      (value) => postSettings({ missionTime: value * TIME_FACTORS[unit] }), { inputmode: 'decimal', title: t('quant.missionTitle') });
    const unitSelect = el('select', { dataset: { field: 'timeUnit' } },
      Object.keys(TIME_FACTORS).map((u) => el('option', { value: u, text: t('quant.unit.' + u) })));
    unitSelect.value = unit;
    unitSelect.addEventListener('change', () => postSettings({ timeUnit: unitSelect.value }));
    docSection.append(
      el('h3', { text: t('quant.doc') }),
      el('div', { class: 'anl-grid' }, [
        el('label', { text: t('quant.mission'), title: t('quant.missionTitle') }),
        input,
        unitSelect,
        el('span'),
        el('span', { class: 'anl-note', text: t('quant.stored', { hours: formatPlain(hours) }) }),
        el('span'),
      ])
    );
  }

  // ---- the selected event --------------------------------------------------------------

  const refetchSoon = debounce(() => fetchView(), 150);

  async function fetchView() {
    const nodeId = ctx.store.selectedId;
    const node = ctx.store.findNode(nodeId);
    if (!node || nodeKind(node) !== 'event') {
      view = null;
      viewId = nodeId;
      paintSelected();
      return;
    }
    const mine = ++fetchSeq;
    try {
      const res = await ctx.api.get('/nodes/' + encodeURIComponent(nodeId));
      if (mine !== fetchSeq) return;
      view = res.node;
      viewId = String(nodeId);
      paintSelected();
    } catch (err) {
      if (mine !== fetchSeq) return;
      view = null;
      viewId = null;
      paintSelected();
      reportError(ctx, err);
    }
  }

  function lambdaShown(perHour) {
    if (perHour === null || perHour === undefined) return '';
    return formatPlain(perHour * LAMBDA_UNITS[lambdaUnit]);
  }

  function row(labelText, control, suffix, title) {
    return [
      el('label', { text: labelText, title: title || null }),
      control,
      suffix instanceof Node ? suffix : el('span', { class: 'anl-suffix', text: suffix || '' }),
    ];
  }

  function paintSelected(force) {
    const nodeId = ctx.store.selectedId;
    const node = ctx.store.findNode(nodeId);
    const kind = nodeKind(node);
    const quant = (view && view.quant) || {};
    const model = MODELS.includes(quant.model) ? quant.model : 'fixed';
    const unc = quant.unc || {};
    const dist = unc.dist === 'lognormal' ? 'lognormal' : 'none';
    const center = unc.mean !== undefined && unc.mean !== null && (unc.median === undefined || unc.median === null)
      ? 'mean' : 'median';
    const signature = [viewId, kind, model, dist, center, lambdaUnit].join('|');
    const focusedKey = [...fields.entries()].find(([, f]) => f.input === document.activeElement);

    if (!force && signature === formSignature && view && viewId === String(nodeId)) {
      // Same form: refresh values of the fields the user is not typing in.
      refreshValues(focusedKey ? focusedKey[0] : null);
      paintDerived();
      return;
    }
    formSignature = signature;
    for (const key of [...fields.keys()]) if (key !== 'missionTime') fields.delete(key);
    clear(selSection);
    selSection.appendChild(el('h3', { text: t('quant.selected') + (node ? ' — ' + (node.name || node.id) : '') }));

    if (!node) {
      selSection.appendChild(el('p', { class: 'anl-empty', text: t('quant.noSelection') }));
      return;
    }
    if (kind !== 'event') {
      const key = kind === 'gate' ? 'quant.isGate' : kind === 'house' ? 'quant.isHouse' : 'quant.isTransfer';
      selSection.appendChild(el('p', { class: 'anl-note', text: t(key, { name: node.name || node.id }) }));
      return;
    }
    if (!view || viewId !== String(nodeId)) {
      selSection.appendChild(el('p', { class: 'anl-note', text: t('anl.running') }));
      return;
    }
    const target = String(nodeId);
    const setQuant = (partial) => patchNode(target, { quant: partial });

    const modelSelect = el('select', { dataset: { field: 'model' } },
      MODELS.map((m) => el('option', { value: m, text: t('quant.model.' + m) })));
    modelSelect.value = model;
    modelSelect.addEventListener('change', () => setQuant({ model: modelSelect.value }));

    const grid = el('div', { class: 'anl-grid' });
    grid.append(...row(t('quant.model'), modelSelect, ''));

    const lambdaSelect = el('select', { title: t('quant.lambdaUnitTitle'), dataset: { field: 'lambdaUnit' } },
      Object.keys(LAMBDA_UNITS).map((u) => el('option', { value: u, text: LAMBDA_LABELS[u] })));
    lambdaSelect.value = lambdaUnit;
    lambdaSelect.addEventListener('change', () => {
      lambdaUnit = lambdaSelect.value;
      writeLambdaUnit(lambdaUnit);
      paintSelected(true);
      paintTable();
    });
    const toHour = (v) => (v === null ? null : v / LAMBDA_UNITS[lambdaUnit]);

    if (model === 'fixed') {
      grid.append(...row(t('quant.q'), textField('probability', formatPlain(view.probability),
        numberParser(0, { max: 1, allowBlank: false }), (v) => patchNode(target, { probability: v }),
        { inputmode: 'decimal' }), ''));
    } else {
      grid.append(...row(t('quant.lambda'), textField('lambda', lambdaShown(quant.lambda), numberParser(0),
        (v) => setQuant({ lambda: toHour(v) }), { inputmode: 'decimal' }), lambdaSelect));
    }
    if (model === 'rate') {
      const mission = formatPlain(analysis().missionTime);
      grid.append(...row(t('quant.T'), textField('T', formatPlain(quant.T), numberParser(0, { exclusive: true }),
        (v) => setQuant({ T: v }), { inputmode: 'decimal', placeholder: t('quant.TPlaceholder') + ' (' + mission + ')' }), 'h'));
    } else if (model === 'standby') {
      grid.append(...row(t('quant.tau'), textField('tau', formatPlain(quant.tau), numberParser(0, { exclusive: true }),
        (v) => setQuant({ tau: v }), { inputmode: 'decimal' }), 'h'));
    } else if (model === 'repairable') {
      grid.append(...row(t('quant.mu'), textField('mu', formatPlain(quant.mu), numberParser(0),
        (v) => setQuant({ mu: v }), { inputmode: 'decimal' }), '/h'));
      grid.append(...row(t('quant.mttr'), textField('mttr', formatPlain(quant.mttr), numberParser(0, { exclusive: true }),
        (v) => setQuant({ mttr: v }), { inputmode: 'decimal', title: t('quant.mttrNote') }), 'h', t('quant.mttrNote')));
    }
    grid.append(...row(t('quant.source'), textField('source', quant.source || '',
      (raw) => ({ ok: true, value: raw.trim() === '' ? null : raw }), (v) => setQuant({ source: v })), ''));

    // Uncertainty.
    const distSelect = el('select', { dataset: { field: 'uncDist' } }, [
      el('option', { value: 'none', text: t('quant.unc.none') }),
      el('option', { value: 'lognormal', text: t('quant.unc.lognormal') }),
    ]);
    distSelect.value = dist;
    distSelect.addEventListener('change', () => {
      if (distSelect.value === 'none') setQuant({ unc: null });
      else setQuant({ unc: { dist: 'lognormal', ef: unc.ef || 3 } });
    });
    const param = model === 'fixed' ? 'q' : 'λ';
    grid.append(...row(t('quant.unc'), distSelect, t('quant.unc.of', { param })));
    if (dist === 'lognormal') {
      const centerSelect = el('select', { dataset: { field: 'uncCenter' } }, [
        el('option', { value: 'median', text: t('quant.unc.median') }),
        el('option', { value: 'mean', text: t('quant.unc.mean') }),
      ]);
      centerSelect.value = center;
      const scale = model === 'fixed' ? 1 : LAMBDA_UNITS[lambdaUnit];
      const current = center === 'mean' ? unc.mean : unc.median;
      centerSelect.title = t('quant.unc.value');
      centerSelect.addEventListener('change', () => {
        // Move the value to the other key; with none yet, the point value
        // marks the choice so it sticks.
        let value = center === 'mean' ? unc.mean : unc.median;
        if (value === undefined || value === null) value = model === 'fixed' ? view.probability : quant.lambda;
        const partial = { median: null, mean: null };
        if (value > 0) partial[centerSelect.value] = value;
        setQuant({ unc: partial });
      });
      const valueInput = textField('uncValue',
        current === undefined || current === null ? '' : formatPlain(current * scale),
        numberParser(0, { exclusive: true }),
        (v) => setQuant({ unc: center === 'mean'
          ? { mean: v === null ? null : v / scale, median: null }
          : { median: v === null ? null : v / scale, mean: null } }),
        { inputmode: 'decimal', placeholder: t('quant.unc.valueNote') });
      grid.append(centerSelect, valueInput,
        el('span', { class: 'anl-suffix', text: model === 'fixed' ? '' : LAMBDA_LABELS[lambdaUnit] }));
      grid.append(...row(t('quant.unc.ef'), textField('uncEf', formatPlain(unc.ef), numberParser(1, { allowBlank: false }),
        (v) => setQuant({ unc: { ef: v } }), { inputmode: 'decimal' }), t('quant.unc.efNote')));
    }
    selSection.appendChild(grid);
    derivedBox = el('div', { class: 'anl-derived', 'aria-live': 'polite' });
    derivedWarnings = el('ul', { class: 'anl-warnings' });
    selSection.append(derivedBox, derivedWarnings);
    paintDerived();
  }

  function refreshValues(skipKey) {
    if (!view) return;
    const quant = view.quant || {};
    const unc = quant.unc || {};
    const model = quant.model || 'fixed';
    const scale = model === 'fixed' ? 1 : LAMBDA_UNITS[lambdaUnit];
    const values = {
      probability: formatPlain(view.probability),
      lambda: lambdaShown(quant.lambda),
      T: formatPlain(quant.T),
      tau: formatPlain(quant.tau),
      mu: formatPlain(quant.mu),
      mttr: formatPlain(quant.mttr),
      source: quant.source || '',
      uncValue: (() => {
        const v = unc.median !== undefined && unc.median !== null ? unc.median : unc.mean;
        return v === undefined || v === null ? '' : formatPlain(v * scale);
      })(),
      uncEf: formatPlain(unc.ef),
    };
    for (const [key, field] of fields) {
      if (key === skipKey || !(key in values)) continue;
      field.baseline = values[key];
      field.input.value = values[key];
      field.input.classList.remove('anl-invalid');
    }
  }

  function paintDerived() {
    if (!derivedBox || !view) return;
    const derived = view.quantDerived || {};
    clear(derivedBox);
    derivedBox.append(
      el('span', { class: 'anl-stat' }, [t('quant.derived') + ' ', el('b', { text: fmt(derived.q) })]),
      el('span', { text: '  ' }),
      el('span', { class: 'anl-stat' }, [t('quant.formula') + ' ', el('span', { class: 'anl-mono', text: derived.formula || '' })])
    );
    renderWarnings(ctx, derivedWarnings, derived.warnings || []);
  }

  // ---- the basic-event table -------------------------------------------------------------

  function basicEvents() {
    const out = [];
    const tree = ctx.store.tree();
    if (!tree) return out;
    const stack = [tree];
    const seen = new Set();
    while (stack.length) {
      const node = stack.pop();
      if (!node || typeof node !== 'object') continue;
      const children = Array.isArray(node.children) ? node.children : [];
      if (node !== tree && nodeKind(node) === 'event' && !seen.has(String(node.id))) {
        seen.add(String(node.id));
        out.push(node);
      }
      for (let i = children.length - 1; i >= 0; i -= 1) stack.push(children[i]);
    }
    return out;
  }

  function paintTable() {
    clear(tableSection);
    tableSection.appendChild(el('h3', { text: t('quant.table') }));
    const events = basicEvents();
    if (!events.length) {
      tableSection.appendChild(el('p', { class: 'anl-empty', text: t('quant.tableEmpty') }));
      return;
    }
    const table = el('table', { class: 'anl-table' });
    table.appendChild(el('thead', null, [el('tr', null, [
      el('th', { text: t('quant.col.event') }),
      el('th', { text: t('quant.col.model') }),
      el('th', { class: 'num', text: 'λ (' + LAMBDA_LABELS[lambdaUnit] + ')' }),
      el('th', { class: 'num', text: 'T / τ (h)' }),
      el('th', { text: t('quant.col.unc') }),
      el('th', { class: 'num', text: t('quant.col.q') }),
    ])]));
    const tbody = el('tbody');
    const selected = ctx.store.selectedId;
    const mission = analysis().missionTime;
    for (const node of events) {
      const quant = node.quant && typeof node.quant === 'object' ? node.quant : {};
      const model = MODELS.includes(quant.model) ? quant.model : 'fixed';
      let time = '';
      if (model === 'rate') time = quant.T ? formatPlain(quant.T) : '(' + formatPlain(mission) + ')';
      else if (model === 'standby') time = formatPlain(quant.tau);
      const unc = quant.unc && quant.unc.dist === 'lognormal'
        ? t('quant.unc.lognormal') + (quant.unc.ef ? ' EF ' + formatPlain(quant.unc.ef) : '') : '';
      tbody.appendChild(el('tr', {
        tabindex: '0',
        dataset: { id: String(node.id) },
        class: String(node.id) === String(selected) ? 'is-selected' : null,
      }, [
        el('td', { text: node.name || node.id, title: String(node.id) }),
        el('td', { text: t('quant.model.' + model).split(':')[0] }),
        el('td', { class: 'num', text: model === 'fixed' ? '' : lambdaShown(quant.lambda) }),
        el('td', { class: 'num', text: time }),
        el('td', { text: unc }),
        el('td', { class: 'num', text: fmt(node.probability) }),
      ]));
    }
    table.appendChild(tbody);
    tableSection.append(el('div', { class: 'anl-tablewrap', style: 'max-height:260px' }, [table]),
      el('p', { class: 'anl-note', text: t('quant.tableHint') }));
  }

  function onTableActivate(event) {
    const tr = event.target instanceof Element ? event.target.closest('tr[data-id]') : null;
    if (!tr) return;
    if (event.type === 'keydown') {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
    }
    ctx.jumpTo(tr.dataset.id);
  }
  tableSection.addEventListener('click', onTableActivate);
  tableSection.addEventListener('keydown', onTableActivate);

  // ---- orchestration -------------------------------------------------------------------

  function paintAll() {
    clear(root);
    if (isEta(ctx)) {
      root.appendChild(etaNotice(ctx));
      return;
    }
    root.append(cols, tableSection);
    paintDoc(true);
    paintSelected(true);
    paintTable();
  }

  let seenTree = null;
  let seenAnalysis = null;
  let seenSelected;
  const unsubscribe = ctx.store.subscribe((state) => {
    if (!active) return;
    const tree = state ? state.tree : null;
    const a = state ? state.analysis : null;
    const selected = ctx.store.selectedId;
    const treeChanged = tree !== seenTree;
    const analysisChanged = a !== seenAnalysis;
    const selectionChanged = selected !== seenSelected;
    seenTree = tree;
    seenAnalysis = a;
    seenSelected = selected;
    if (isEta(ctx)) {
      paintAll();
      return;
    }
    if (!root.contains(cols)) paintAll();
    if (analysisChanged) paintDoc();
    if (selectionChanged) {
      view = null;
      viewId = null;
      paintSelected();
      fetchView();
    } else if (treeChanged || analysisChanged) {
      refetchSoon();
    }
    if (treeChanged || selectionChanged || analysisChanged) paintTable();
  });

  const repaint = () => {
    if (active) paintAll();
  };
  window.addEventListener('fta:language', repaint);
  window.addEventListener('fta:flush', onFlush);
  const unSig = ctx.onSigFigs(() => {
    if (!active) return;
    paintDerived();
    paintTable();
  });

  return {
    activate() {
      active = true;
      seenTree = ctx.store.state ? ctx.store.state.tree : null;
      seenAnalysis = ctx.store.state ? ctx.store.state.analysis : null;
      seenSelected = ctx.store.selectedId;
      paintAll();
      fetchView();
    },
    deactivate() {
      // Commit whatever is being typed before the panel is hidden.
      const focused = document.activeElement;
      for (const field of fields.values()) if (field.input === focused) commitField(field);
      active = false;
      refetchSoon.cancel();
    },
    onStale() {
      if (!active) return;
      paintDoc();
      paintTable();
      refetchSoon();
    },
    dispose() {
      refetchSoon.cancel();
      if (typeof unsubscribe === 'function') unsubscribe();
      if (typeof unSig === 'function') unSig();
      window.removeEventListener('fta:language', repaint);
      window.removeEventListener('fta:flush', onFlush);
      root.remove();
    },
  };
}

export default mount;
