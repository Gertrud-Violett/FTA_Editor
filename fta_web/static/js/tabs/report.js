/**
 * tabs/report.js -- the Report tab (1.7, workstream D).
 *
 *   * "Generate report" POSTs /api/report/docx with the chosen sections, the
 *     top-N limits, the language and the diagram preview as a base64 PNG
 *     (ctx.diagramPng()); the .docx comes back as a download.
 *   * "Export Excel" is GET /api/export/xlsx (core sheet + Events + Analysis).
 *   * "Export events CSV" is built client-side from the store's tree.
 *
 * The section selection persists in localStorage `fta.report.sections`.
 * Tab contract: see tabs/host.js.
 */
import catalog from '../i18n/report.js';

export const id = 'report';
export const advanced = true;

try {
  window.ftaShell?.registerStrings?.(catalog);
} catch (_err) {
  /* the shell registers nothing before boot; keys then show as themselves */
}

export const SECTIONS = Object.freeze([
  'metadata', 'headline', 'assumptions', 'diagram', 'events',
  'cutsets', 'importance', 'uncertainty', 'validation', 'traceability',
]);
const DEFAULT_SECTIONS = SECTIONS.filter((s) => s !== 'uncertainty');
const STORAGE_KEY = 'fta.report.sections';
const INSTALL_CMD = 'uv sync --extra report';

function readSections() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [...DEFAULT_SECTIONS];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return SECTIONS.filter((s) => parsed.includes(s));
  } catch (_err) {
    /* private mode or junk: defaults */
  }
  return [...DEFAULT_SECTIONS];
}

function writeSections(list) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch (_err) {
    /* not persisted */
  }
}

/** Blob -> base64 (no data: prefix). */
export function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error || new Error('could not read the diagram image'));
    reader.onload = () => {
      const text = String(reader.result || '');
      resolve(text.slice(text.indexOf(',') + 1));
    };
    reader.readAsDataURL(blob);
  });
}

function csvCell(value) {
  if (value === null || value === undefined) return '';
  const text = Array.isArray(value) ? value.join('; ') : String(value);
  return /[",\r\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
}

const CSV_COLUMNS = [
  'id', 'name', 'parentId', 'depth', 'nodeType', 'gateType', 'k', 'eventKind', 'model',
  'lambda', 'T', 'tau', 'mu', 'mttr', 'probability', 'calculatedProbability',
  'requirementId', 'testRef', 'owner', 'status', 'tags', 'fmeaId', 'rpn',
];

/** The tree as CSV text (one row per node, pre-order). */
export function eventsCsv(tree) {
  const lines = [CSV_COLUMNS.join(',')];
  const stack = tree ? [[tree, '', 0]] : [];
  while (stack.length) {
    const [node, parentId, depth] = stack.pop();
    const children = Array.isArray(node.children) ? node.children : [];
    const quant = node.quant && typeof node.quant === 'object' ? node.quant : {};
    const trace = node.trace && typeof node.trace === 'object' ? node.trace : {};
    const fmea = node.fmea && typeof node.fmea === 'object' ? node.fmea : {};
    const isGate = children.length > 0 || String(node.gateType || '').toUpperCase() === 'TRANSFER';
    const row = {
      id: node.id,
      name: node.name,
      parentId,
      depth,
      nodeType: isGate ? 'gate' : 'event',
      gateType: isGate ? String(node.gateType || node.logicGate || 'OR').toUpperCase() : '',
      k: node.k,
      eventKind: node.eventKind || (isGate ? '' : 'basic'),
      model: quant.model || (isGate ? '' : 'fixed'),
      lambda: quant.lambda,
      T: quant.T,
      tau: quant.tau,
      mu: quant.mu,
      mttr: quant.mttr,
      probability: node.probability,
      calculatedProbability: node.calculatedProbability,
      requirementId: trace.requirementId,
      testRef: trace.testRef,
      owner: trace.owner,
      status: trace.status,
      tags: trace.tags,
      fmeaId: fmea.id,
      rpn: fmea.rpn,
    };
    lines.push(CSV_COLUMNS.map((c) => csvCell(row[c])).join(','));
    for (let i = children.length - 1; i >= 0; i -= 1) {
      if (children[i] && typeof children[i] === 'object') stack.push([children[i], node.id, depth + 1]);
    }
  }
  return lines.join('\r\n') + '\r\n';
}

function safeStem(text) {
  const stem = String(text || '').replace(/[\\/:*?"<>|\u0000-\u001f]+/g, '_').trim();
  return stem || 'fta';
}

const STYLE_ID = 'report-tab-style';
const CSS = `
.report-tab { display: flex; flex-direction: column; gap: 12px; padding: 4px 2px; max-width: 760px; }
.report-tab h3 { margin: 0; font-size: 1em; }
.report-tab p { margin: 0; }
.report-tab__hint { font-size: .9em; opacity: .8; }
.report-tab__warn { color: var(--danger, #b00); font-size: .9em; }
.report-tab__sections { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 4px 12px; border: 0; margin: 0; padding: 0; }
.report-tab__sections label, .report-tab__row label { display: flex; align-items: center; gap: 6px; }
.report-tab__row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; }
.report-tab__row input[type=number] { width: 6em; }
.report-tab__actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
`;

function ensureStyle() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = CSS;
  document.head.appendChild(style);
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) node.append(child);
  return node;
}

export function mount(panel, ctx) {
  ensureStyle();
  const t = (key, vars) => (ctx && typeof ctx.t === 'function' ? ctx.t(key, vars) : key);
  const root = el('div', { class: 'report-tab', 'data-report-tab': '' });
  const labels = []; // [element, key, vars?] repainted on language change
  const label = (node, key, vars) => {
    labels.push([node, key, vars]);
    node.textContent = t(key, vars);
    return node;
  };

  // ---- Word report ----
  const heading = label(el('h3'), 'report.heading');
  const intro = label(el('p', { class: 'report-tab__hint' }), 'report.intro');
  const missing = el('p', { class: 'report-tab__warn', 'data-report-missing': '', hidden: '' });
  const etaNote = label(el('p', { class: 'report-tab__hint', hidden: '' }), 'report.etaNote');

  const chosen = new Set(readSections());
  const fieldset = el('fieldset', { class: 'report-tab__sections' });
  const legend = label(el('legend'), 'report.sections');
  fieldset.append(legend);
  const boxes = {};
  for (const section of SECTIONS) {
    const box = el('input', { type: 'checkbox', 'data-section': section });
    box.checked = chosen.has(section);
    box.addEventListener('change', () => {
      if (box.checked) chosen.add(section);
      else chosen.delete(section);
      writeSections(SECTIONS.filter((s) => chosen.has(s)));
      if (section === 'uncertainty' && box.checked && !mcBox.checked) mcBox.checked = true;
    });
    boxes[section] = box;
    const text = label(el('span'), 'report.section.' + section);
    fieldset.append(el('label', {}, [box, text]));
  }

  const topCut = el('input', { type: 'number', min: '1', max: '10000', value: '50', 'data-top': 'cutsets' });
  const topImp = el('input', { type: 'number', min: '1', max: '10000', value: '30', 'data-top': 'importance' });
  const limits = el('div', { class: 'report-tab__row' }, [
    el('label', {}, [label(el('span'), 'report.topCutsets'), topCut]),
    el('label', {}, [label(el('span'), 'report.topImportance'), topImp]),
  ]);

  const mcBox = el('input', { type: 'checkbox', 'data-run-uncertainty': '' });
  mcBox.checked = chosen.has('uncertainty');
  mcBox.addEventListener('change', () => {
    if (mcBox.checked && !boxes.uncertainty.checked) {
      boxes.uncertainty.checked = true;
      boxes.uncertainty.dispatchEvent(new Event('change'));
    }
  });
  const langSelect = el('select', { 'data-report-lang': '' });
  const langEn = el('option', { value: 'en' });
  const langJa = el('option', { value: 'ja' });
  label(langEn, 'report.lang.en');
  label(langJa, 'report.lang.ja');
  langSelect.append(langEn, langJa);
  langSelect.value = window.ftaShell?.language === 'ja' ? 'ja' : 'en';
  let langTouched = false;
  langSelect.addEventListener('change', () => { langTouched = true; });
  const options = el('div', { class: 'report-tab__row' }, [
    el('label', {}, [mcBox, label(el('span'), 'report.runUncertainty')]),
    el('label', {}, [label(el('span'), 'report.language'), langSelect]),
  ]);

  const generate = el('button', { type: 'button', class: 'btn btn--primary', 'data-report-generate': '' });
  label(generate, 'report.generate');
  const saveAgain = el('a', { class: 'btn', hidden: '', 'data-report-link': '' });
  const actions = el('div', { class: 'report-tab__actions' }, [generate, saveAgain]);

  // ---- other exports ----
  const otherHeading = label(el('h3'), 'report.otherExports');
  const xlsxBtn = el('button', { type: 'button', class: 'btn', 'data-report-xlsx': '' });
  label(xlsxBtn, 'report.exportXlsx');
  const csvBtn = el('button', { type: 'button', class: 'btn', 'data-report-csv': '' });
  label(csvBtn, 'report.exportCsv');
  const other = el('div', { class: 'report-tab__actions' }, [xlsxBtn, csvBtn]);

  root.append(heading, intro, missing, etaNote, fieldset, limits, options, actions, otherHeading, other);
  panel.appendChild(root);

  let lastUrl = null;
  const offer = (blob, name) => {
    if (lastUrl) URL.revokeObjectURL(lastUrl);
    lastUrl = URL.createObjectURL(blob);
    const link = el('a', { href: lastUrl, download: name });
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    link.remove();
    return lastUrl;
  };

  function applyCapabilities() {
    const caps = (ctx && typeof ctx.capabilities === 'function' && ctx.capabilities()) || {};
    const noDocx = caps.reportExport === false;
    generate.disabled = noDocx;
    missing.hidden = !noDocx;
    missing.textContent = noDocx ? t('report.unavailable', { cmd: INSTALL_CMD }) : '';
    const noXlsx = caps.excelExport === false;
    xlsxBtn.disabled = noXlsx;
    xlsxBtn.title = noXlsx ? t('report.exportXlsxUnavailable') : '';
    const mode = ctx?.store?.metadata?.().mode;
    etaNote.hidden = mode !== 'ETA';
  }

  let busy = false;
  generate.addEventListener('click', async () => {
    if (busy) return;
    const sections = SECTIONS.filter((s) => chosen.has(s));
    if (!sections.length) {
      ctx.toast(t('report.noSections'), 'notice');
      return;
    }
    busy = true;
    generate.disabled = true;
    generate.setAttribute('aria-busy', 'true');
    ctx.toast(t('report.generating'), 'info');
    try {
      const body = {
        sections,
        sigFigs: ctx.fmt?.sigFigs?.() || 3,
        lang: langSelect.value,
        topN: { cutsets: Number(topCut.value) || 50, importance: Number(topImp.value) || 30 },
        runUncertainty: Boolean(mcBox.checked && chosen.has('uncertainty')),
      };
      if (sections.includes('diagram') && typeof ctx.diagramPng === 'function') {
        const png = await ctx.diagramPng();
        if (png) body.diagramPng = await blobToBase64(png);
      }
      const { blob, filename } = await ctx.api.download('POST', '/report/docx', body);
      const name = filename || safeStem(ctx.store?.metadata?.().title) + '_report.docx';
      saveAgain.href = offer(blob, name);
      saveAgain.setAttribute('download', name);
      saveAgain.hidden = false;
      labels.push([saveAgain, 'report.saveAgain', { name }]);
      saveAgain.textContent = t('report.saveAgain', { name });
      ctx.toast(t('report.done', { name }), 'ok');
    } catch (err) {
      ctx.showError(err);
    } finally {
      busy = false;
      generate.removeAttribute('aria-busy');
      applyCapabilities();
    }
  });

  xlsxBtn.addEventListener('click', async () => {
    xlsxBtn.disabled = true;
    try {
      const { blob, filename } = await ctx.api.download(
        'GET',
        '/export/xlsx?sigFigs=' + encodeURIComponent(ctx.fmt?.sigFigs?.() || 3)
      );
      const name = filename || safeStem(ctx.store?.metadata?.().title) + '.xlsx';
      offer(blob, name);
      ctx.toast(t('report.saved', { name }), 'ok');
    } catch (err) {
      ctx.showError(err);
    } finally {
      applyCapabilities();
    }
  });

  csvBtn.addEventListener('click', () => {
    const tree = ctx.store?.tree?.();
    if (!tree) {
      ctx.toast(t('report.csvEmpty'), 'notice');
      return;
    }
    // BOM so Excel opens Japanese names as UTF-8.
    const blob = new Blob(['﻿' + eventsCsv(tree)], { type: 'text/csv;charset=utf-8' });
    const name = safeStem(ctx.store?.metadata?.().title) + '_events.csv';
    offer(blob, name);
    ctx.toast(t('report.saved', { name }), 'ok');
  });

  const repaint = () => {
    for (const [node, key, vars] of labels) node.textContent = t(key, vars);
    if (!langTouched) langSelect.value = window.ftaShell?.language === 'ja' ? 'ja' : 'en';
    applyCapabilities();
  };
  window.addEventListener('fta:language', repaint);
  const unsubscribe = ctx?.store?.subscribe ? ctx.store.subscribe(() => applyCapabilities()) : null;
  applyCapabilities();

  return {
    activate() { applyCapabilities(); },
    deactivate() {},
    onStale() { applyCapabilities(); },
    dispose() {
      window.removeEventListener('fta:language', repaint);
      if (typeof unsubscribe === 'function') unsubscribe();
      if (lastUrl) URL.revokeObjectURL(lastUrl);
      root.remove();
    },
  };
}

export default mount;
