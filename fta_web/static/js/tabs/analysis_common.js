/**
 * tabs/analysis_common.js -- helpers shared by the four analysis tabs
 * (quant, cutsets, importance, uncertainty). Not a tab itself: host.js only
 * imports the nine ids it knows, so this file is never mounted.
 *
 * Registers all four analysis catalogs (each tab also registers its own, which
 * is harmless: registerStrings keeps the first, identical, definition) and
 * injects one stylesheet built only from theme tokens, so dark mode follows
 * theme.css automatically.
 */
import { el, clear, injectStyles } from '../dialogs.js';
import quantStrings from '../i18n/quant.js';
import cutsetsStrings from '../i18n/cutsets.js';
import impStrings from '../i18n/imp.js';
import uncStrings from '../i18n/unc.js';

for (const catalog of [quantStrings, cutsetsStrings, impStrings, uncStrings]) {
  window.ftaShell?.registerStrings?.(catalog);
}

export { el, clear };

const CSS = `
.anl { display: flex; flex-direction: column; gap: 8px; padding: 8px 10px;
  box-sizing: border-box; height: 100%; min-height: 0; overflow: auto;
  font-size: var(--fs-sm, 12.5px); color: var(--text); background: var(--panel); }
.anl-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; }
.anl-toolbar label, .anl-field { display: inline-flex; align-items: center; gap: 4px; color: var(--text-dim); }
.anl-toolbar input[type="text"], .anl-toolbar input[type="number"] { width: 9ch; }
.anl-toolbar .anl-grow { flex: 1 1 auto; }
.anl-summary { display: flex; flex-wrap: wrap; gap: 4px 16px; align-items: baseline; }
.anl-stat { color: var(--text-dim); white-space: nowrap; }
.anl-stat b { color: var(--text); font-variant-numeric: tabular-nums; font-weight: 600; }
.anl-badge { display: inline-block; padding: 0 7px; border-radius: 999px; font-size: var(--fs-xs, 11px);
  line-height: 18px; border: 1px solid var(--border); background: var(--surface); color: var(--text-dim); white-space: nowrap; }
.anl-badge--warn { background: var(--warn-soft); color: var(--warn); border-color: transparent; }
.anl-badge--info { background: var(--accent-soft); color: var(--accent-hover); border-color: transparent; }
.anl-tablewrap { flex: 1 1 auto; min-height: 90px; overflow: auto; border: 1px solid var(--border);
  border-radius: var(--r-sm, 5px); background: var(--surface); }
.anl-table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
.anl-table th, .anl-table td { padding: 3px 8px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
.anl-table th { position: sticky; top: 0; z-index: 1; background: var(--panel-header, var(--surface)); color: var(--text-dim);
  font-weight: 600; white-space: nowrap; }
.anl-table th.is-sortable { cursor: pointer; user-select: none; }
.anl-table th.is-sorted { color: var(--text); }
.anl-table .num { text-align: right; white-space: nowrap; }
.anl-table tbody tr { cursor: pointer; }
.anl-table tbody tr:hover { background: var(--surface-hover); }
.anl-table tbody tr.is-selected { background: var(--accent-soft); }
.anl-table tbody tr:focus-visible { outline: 2px solid var(--focus); outline-offset: -2px; }
.anl-bar { position: relative; min-width: 90px; }
.anl-bar__fill { position: absolute; left: 0; top: 3px; bottom: 3px; background: var(--accent); opacity: .28; border-radius: 2px; }
.anl-bar__text { position: relative; }
.anl-events { display: flex; flex-wrap: wrap; gap: 3px; }
.anl-event { padding: 0 5px; border-radius: 4px; background: var(--surface-hover); color: var(--text); white-space: nowrap; }
.anl-note { color: var(--text-dim); margin: 0; }
.anl-empty { color: var(--text-dim); padding: 10px 2px; margin: 0; }
.anl-error { color: var(--danger); margin: 0; }
.anl-warnings { margin: 0; padding-left: 1.3em; color: var(--warn); }
.anl-warnings li { margin: 1px 0; }
.anl-eta { color: var(--text-dim); padding: 16px 4px; }
.anl-section { border: 1px solid var(--border); border-radius: var(--r-md, 8px); padding: 8px 10px; background: var(--surface); }
.anl-section > h3 { margin: 0 0 6px; font-size: var(--fs-sm, 12.5px); color: var(--text-dim); font-weight: 600; }
.anl-grid { display: grid; grid-template-columns: max-content minmax(12ch, 32ch) max-content; gap: 5px 8px; align-items: center; }
.anl-grid > label { color: var(--text-dim); }
.anl-grid > input[type="text"], .anl-grid > select { width: 100%; box-sizing: border-box; }
.anl-grid > select:nth-child(3n) { width: auto; }
.anl-grid .anl-suffix { color: var(--text-dim); }
.anl-derived { font-variant-numeric: tabular-nums; }
.anl-derived b { font-size: var(--fs-md, 13.5px); }
.anl-mono { font-family: var(--font-mono, monospace); color: var(--text-dim); }
.anl-invalid { border-color: var(--danger) !important; }
.anl-cols { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-start; }
.anl-cols > .anl-section { flex: 1 1 300px; min-width: 260px; }
.anl-statgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 4px 12px; }
.anl-chart { width: 100%; max-width: 760px; height: auto; color: var(--text-dim); }
.anl-chart .bar { fill: var(--accent); opacity: .55; }
.anl-chart .axis { stroke: var(--border-strong, var(--border)); stroke-width: 1; }
.anl-chart .tick { fill: var(--text-dim); font-size: 11px; }
.anl-chart .marker { stroke: var(--danger); stroke-width: 1.5; stroke-dasharray: 4 3; }
.anl-chart .marker-label { fill: var(--danger); font-size: 11px; }
.anl-chart .pct { stroke: var(--text-faint); stroke-width: 1; stroke-dasharray: 2 3; }
`;

export function ensureStyles() {
  injectStyles('fta-analysis-tabs', CSS);
}

/** A translator bound to ctx with a key fallback. */
export function translator(ctx) {
  return (key, vars) => (ctx && typeof ctx.t === 'function' ? ctx.t(key, vars) : key);
}

/** True when the loaded document is an event tree. */
export function isEta(ctx) {
  try {
    return String(ctx.store.metadata().mode || '').toUpperCase() === 'ETA';
  } catch (_err) {
    return false;
  }
}

/** Display name of a node id (falls back to the id). */
export function nodeName(ctx, id) {
  if (id === null || id === undefined) return '';
  const node = ctx.store.findNode(id);
  return node && node.name ? String(node.name) : String(id);
}

/** The localized text of an analysis warning `{code, nodeId, params}`. */
export function warningText(ctx, warning) {
  const t = translator(ctx);
  const code = String((warning && warning.code) || '');
  const params = Object.assign({}, (warning && warning.params) || {});
  params.node = nodeName(ctx, warning && warning.nodeId);
  if (Array.isArray(params.by)) params.by = params.by.map((b) => t('anl.by.' + b)).join(', ');
  const key = 'anl.warn.' + code;
  const text = t(key, params);
  return text === key ? code : text;
}

/** Render a `<ul>` of warnings into `host` (cleared first). */
export function renderWarnings(ctx, host, warnings) {
  clear(host);
  const list = (warnings || []).filter(Boolean);
  host.hidden = list.length === 0;
  const seen = new Set();
  for (const w of list) {
    const text = warningText(ctx, w);
    if (seen.has(text)) continue;
    seen.add(text);
    host.appendChild(el('li', { text }));
  }
}

/** Trailing-edge debounce. `fn.cancel()` drops a pending call. */
export function debounce(fn, ms) {
  let timer = null;
  const wrapped = (...args) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      fn(...args);
    }, ms);
  };
  wrapped.cancel = () => {
    if (timer) clearTimeout(timer);
    timer = null;
  };
  return wrapped;
}

/**
 * Parse a user-typed number ("1e-6", "0.5", " 3 ", "1,5"). '' -> null, bad -> NaN.
 *
 * One comma is read as a decimal comma. A comma that could just as well be a
 * thousands separator ("1,500", "5,000", "1,000,000") is rejected rather than
 * guessed: reading "5,000" as 5 would silently change a limit by 1000x.
 */
export function parseNumber(raw) {
  const text = String(raw === null || raw === undefined ? '' : raw).trim();
  if (text === '') return null;
  let normal = text;
  if (text.includes(',')) {
    const ambiguous = /^[-+]?[1-9]\d{0,2},\d{3}$/.test(text);
    if (ambiguous || text.includes('.') || text.split(',').length > 2) return NaN;
    normal = text.replace(',', '.');
  }
  // Plain decimal / exponent notation only (Number() would also take "0x1f").
  if (!/^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$/i.test(normal)) return NaN;
  const value = Number(normal);
  return Number.isFinite(value) ? value : NaN;
}

/** Numbers that are not probabilities (hours, samples): plain but compact. */
export function formatPlain(value) {
  if (value === null || value === undefined || value === '') return '';
  const num = Number(value);
  if (!Number.isFinite(num)) return '';
  if (num !== 0 && (Math.abs(num) < 1e-3 || Math.abs(num) >= 1e7)) {
    return num.toExponential(6).replace(/\.?0+e/, 'e').replace('e+', 'e');
  }
  return String(Number(num.toPrecision(10)));
}

/** Copy text to the clipboard; resolves true on success. */
export async function copyText(text) {
  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (_err) {
    /* fall through to the textarea path */
  }
  try {
    const area = el('textarea', { style: 'position:fixed;left:-9999px;top:0' });
    area.value = text;
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand('copy');
    area.remove();
    return ok;
  } catch (_err) {
    return false;
  }
}

/** The ETA-mode notice element. */
export function etaNotice(ctx) {
  return el('p', { class: 'anl-eta', text: translator(ctx)('anl.eta') });
}

/** Show an analysis API error through the shell (409/422/501/503 included). */
export function reportError(ctx, err) {
  if (ctx && typeof ctx.showError === 'function') ctx.showError(err);
}
