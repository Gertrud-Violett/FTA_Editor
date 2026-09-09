/**
 * diagram.js -- the interactive diagram panel.
 *
 * The desktop app shells out to `json_viewer.py`, rasterises a PNG and shows it
 * in a Tk canvas (src/FTA_Editor_UI.py:1133-1198). v1.6 keeps the same DOT --
 * the server hands us `build_dot()` output verbatim -- but renders it to SVG in
 * the browser with a vendored Graphviz-on-WASM build.
 *
 * Doing it as SVG rather than PNG buys three things the desktop cannot do:
 * crisp zoom at any scale, selectable/searchable label text, and nodes that can
 * be clicked to drive the selection in the tree.
 *
 * Renderers
 * ---------
 * `GET /api/dot` reports which renderer the *server* would use. When a native
 * Graphviz is present the server can rasterise at 300 dpi for PNG export; when
 * it is not, everything happens here. The panel always states which engine
 * produced what is on screen, because a user comparing output against the
 * desktop app needs to know whether it is even the same engine (spec 6.8).
 */
import { api, ApiError } from './api.js';
import { store } from './store.js';
import { el, clear, injectStyles } from './dialogs.js';

const RENDER_DEBOUNCE_MS = 150; // config.RENDER_DEBOUNCE_MS
const ZOOM_MIN = 0.1;
const ZOOM_MAX = 8;
const ZOOM_STEP = 1.1;

/** Single WASM instance. It is ~1.1 MB -- never build one per render. */
let vizPromise = null;
function getViz() {
  if (!vizPromise) {
    vizPromise = import('../vendor/viz-js/viz.js')
      .then((mod) => mod.instance())
      .catch((err) => {
        vizPromise = null; // let a later attempt retry rather than latching the failure
        throw err;
      });
  }
  return vizPromise;
}

function t(key, fallback) {
  const fn = window.ftaShell && window.ftaShell.t;
  if (typeof fn !== 'function') return fallback;
  const out = fn(key);
  return out === key ? fallback : out;
}

/**
 * Mirror of `json_viewer.sanitize_id`:
 *     re.sub(r'[^0-9A-Za-z_]', '_', str(s))
 * Graphviz writes the sanitized id into each node's <title>, so a node whose
 * real id contains a dot or a space cannot be matched back by string equality.
 */
function sanitizeId(value) {
  return String(value).replace(/[^0-9A-Za-z_]/g, '_');
}

/**
 * sanitized -> real id. Sanitizing is lossy ("a.b" and "a b" collide), so a
 * collision is recorded and left unmapped rather than resolved arbitrarily:
 * selecting the wrong node is worse than selecting none.
 */
function buildIdMap(flat) {
  const map = new Map();
  const collided = new Set();
  for (const entry of flat) {
    const real = String(entry.id);
    const key = sanitizeId(real);
    if (map.has(key) && map.get(key) !== real) collided.add(key);
    else map.set(key, real);
  }
  for (const key of collided) map.delete(key);
  return map;
}

export function initDiagram(container) {
  if (!container) throw new Error('initDiagram(container): container is required');

  injectStyles('fta-diagram-styles', STYLES);
  clear(container);

  const status = el('div', { class: 'diagram__status', role: 'status', 'aria-live': 'polite' });
  const stage = el('div', { class: 'diagram__stage', tabindex: '0' });
  const canvas = el('div', { class: 'diagram__canvas' });
  stage.appendChild(canvas);

  const zoomLabel = el('span', { class: 'diagram__zoom' }, '100%');
  const btn = (label, key, fallback, onClick) => {
    const b = el('button', { type: 'button', class: 'diagram__btn', onclick: onClick }, label);
    b.dataset.i18nTitle = key;      // so retitleToolbar() and a language switch can find it
    b._fallback = fallback;
    return b;
  };

  const toolbar = el('div', { class: 'diagram__toolbar' }, [
    btn('−', 'diagram.zoomOut', 'Zoom out', () => zoomBy(1 / ZOOM_STEP)),
    zoomLabel,
    btn('+', 'diagram.zoomIn', 'Zoom in', () => zoomBy(ZOOM_STEP)),
    btn('⤢', 'diagram.fit', 'Fit to window', () => fit()),
    el('span', { class: 'diagram__spacer' }),
    btn('SVG', 'diagram.exportSvg', 'Export as SVG', () => exportSvg()),
    btn('PNG', 'diagram.exportPng', 'Export as PNG', () => exportPng()),
  ]);

  function retitleToolbar() {
    for (const b of toolbar.querySelectorAll('button[data-i18n-title]')) {
      const label = t(b.dataset.i18nTitle, b._fallback);
      b.title = label;
      b.setAttribute('aria-label', label);
    }
  }
  retitleToolbar();

  container.appendChild(toolbar);
  container.appendChild(stage);
  container.appendChild(status);

  let scale = 1;
  let tx = 0;
  let ty = 0;
  let svgEl = null;
  let lastSvgText = '';
  let renderer = 'wasm';
  let timer = null;
  let generation = 0;
  let destroyed = false;

  const metaHost = document.getElementById('diagram-meta');

  function applyTransform() {
    canvas.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
    zoomLabel.textContent = `${Math.round(scale * 100)}%`;
  }

  function zoomBy(factor, originX, originY) {
    const next = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, scale * factor));
    if (next === scale) return;
    // Keep the point under the cursor fixed while zooming.
    if (typeof originX === 'number') {
      const rect = stage.getBoundingClientRect();
      const px = originX - rect.left;
      const py = originY - rect.top;
      tx = px - ((px - tx) * next) / scale;
      ty = py - ((py - ty) * next) / scale;
    }
    scale = next;
    applyTransform();
  }

  function fit() {
    if (!svgEl) return;
    const rect = stage.getBoundingClientRect();
    const w = svgEl.viewBox && svgEl.viewBox.baseVal && svgEl.viewBox.baseVal.width
      ? svgEl.viewBox.baseVal.width
      : svgEl.getBoundingClientRect().width / (scale || 1);
    const h = svgEl.viewBox && svgEl.viewBox.baseVal && svgEl.viewBox.baseVal.height
      ? svgEl.viewBox.baseVal.height
      : svgEl.getBoundingClientRect().height / (scale || 1);
    if (!w || !h) return;
    scale = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.min((rect.width - 24) / w, (rect.height - 24) / h)));
    tx = (rect.width - w * scale) / 2;
    ty = 12;
    applyTransform();
  }

  // ---- pan ---------------------------------------------------------------
  let dragging = false;
  let dragX = 0;
  let dragY = 0;
  stage.addEventListener('pointerdown', (ev) => {
    if (ev.button !== 0) return;
    dragging = true;
    dragX = ev.clientX - tx;
    dragY = ev.clientY - ty;
    stage.setPointerCapture(ev.pointerId);
    stage.classList.add('is-panning');
  });
  stage.addEventListener('pointermove', (ev) => {
    if (!dragging) return;
    tx = ev.clientX - dragX;
    ty = ev.clientY - dragY;
    applyTransform();
  });
  const endPan = (ev) => {
    if (!dragging) return;
    dragging = false;
    try { stage.releasePointerCapture(ev.pointerId); } catch (_) { /* already released */ }
    stage.classList.remove('is-panning');
  };
  stage.addEventListener('pointerup', endPan);
  stage.addEventListener('pointercancel', endPan);

  stage.addEventListener('wheel', (ev) => {
    if (!ev.ctrlKey && !ev.metaKey) return; // plain wheel scrolls the panel
    ev.preventDefault();
    zoomBy(ev.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP, ev.clientX, ev.clientY);
  }, { passive: false });

  stage.addEventListener('keydown', (ev) => {
    if (!ev.ctrlKey && !ev.metaKey) return;
    if (ev.key === '+' || ev.key === '=') { ev.preventDefault(); zoomBy(ZOOM_STEP); }
    else if (ev.key === '-') { ev.preventDefault(); zoomBy(1 / ZOOM_STEP); }
    else if (ev.key === '0') { ev.preventDefault(); fit(); }
  });

  // ---- click a node -> select it in the tree ------------------------------
  stage.addEventListener('click', (ev) => {
    if (!svgEl) return;
    const g = ev.target.closest && ev.target.closest('g.node');
    if (!g) return;
    const title = g.querySelector('title');
    if (!title) return;
    const map = buildIdMap(store.flat ? store.flat() : []);
    const real = map.get(title.textContent.trim());
    if (real) store.select(real);
  });

  function markSelection() {
    if (!svgEl) return;
    const selected = store.selectedId ? sanitizeId(store.selectedId) : null;
    svgEl.querySelectorAll('g.node').forEach((g) => {
      const title = g.querySelector('title');
      const isSel = !!(title && selected && title.textContent.trim() === selected);
      g.classList.toggle('is-selected', isSel);
    });
  }

  function setStatusMessage(text, kind) {
    status.textContent = text || '';
    status.className = 'diagram__status' + (kind ? ` diagram__status--${kind}` : '');
  }

  function setMeta(text) {
    if (metaHost) metaHost.textContent = text;
  }

  async function render() {
    const mine = ++generation;
    try {
      const hideZero = !!(window.ftaShell && window.ftaShell.hideZero);
      const payload = await api.get(`/dot?hideZero=${hideZero ? 'true' : 'false'}`);
      if (mine !== generation || destroyed) return; // a newer render superseded this one
      renderer = payload.renderer || 'wasm';

      const viz = await getViz();
      if (mine !== generation || destroyed) return;

      const svgText = viz.renderString(payload.dot, { format: 'svg' });
      lastSvgText = svgText;

      clear(canvas);
      const doc = new DOMParser().parseFromString(svgText, 'image/svg+xml');
      const parsed = doc.documentElement;
      if (!parsed || parsed.nodeName === 'parsererror') throw new Error('Graphviz returned invalid SVG.');
      svgEl = document.importNode(parsed, true);
      svgEl.removeAttribute('width');
      svgEl.removeAttribute('height');
      canvas.appendChild(svgEl);

      markSelection();
      if (scale === 1 && tx === 0 && ty === 0) fit();
      setStatusMessage('');
      setMeta(
        renderer === 'native'
          ? t('diagram.rendererNative', 'Rendered by system Graphviz')
          : t('diagram.rendererWasm', 'Rendered in-browser (Graphviz WASM)')
      );
    } catch (err) {
      if (mine !== generation || destroyed) return;
      svgEl = null;
      clear(canvas);
      const msg = err instanceof ApiError ? err.message : String((err && err.message) || err);
      setStatusMessage(t('diagram.error', 'Could not render the diagram: ') + msg, 'error');
      setMeta('');
    }
  }

  function schedule() {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => { timer = null; render(); }, RENDER_DEBOUNCE_MS);
  }

  // ---- export ------------------------------------------------------------
  function download(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = el('a', { href: url, download: filename });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function exportSvg() {
    if (!lastSvgText) {
      setStatusMessage(t('diagram.nothingToExport', 'Nothing to export yet.'), 'error');
      return;
    }
    download(new Blob([lastSvgText], { type: 'image/svg+xml;charset=utf-8' }), 'fta_diagram.svg');
  }

  async function exportPng() {
    if (!lastSvgText) {
      setStatusMessage(t('diagram.nothingToExport', 'Nothing to export yet.'), 'error');
      return;
    }
    const caps = (store.state && store.state.capabilities) || {};
    if (caps.nativeDot) {
      // A real `dot` rasterises at 300 dpi; prefer it over a canvas upscale.
      try {
        const res = await api.post('/render', { format: 'png', hideZero: !!(window.ftaShell && window.ftaShell.hideZero), highQuality: true });
        const bin = atob(res.data);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
        download(new Blob([bytes], { type: res.contentType || 'image/png' }), 'fta_diagram.png');
        return;
      } catch (err) {
        // 503 here means `dot` vanished since startup; fall through to canvas.
        setStatusMessage(t('diagram.nativeFellBack', 'System Graphviz unavailable; exported from the browser renderer instead.'), 'warn');
      }
    }
    await exportPngViaCanvas();
  }

  function exportPngViaCanvas() {
    return new Promise((resolve) => {
      const scaleUp = 2;
      const box = svgEl ? svgEl.viewBox.baseVal : null;
      const w = (box && box.width) || 1200;
      const h = (box && box.height) || 800;
      const img = new Image();
      const svgBlob = new Blob([lastSvgText], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(svgBlob);
      img.onload = () => {
        const c = document.createElement('canvas');
        c.width = Math.round(w * scaleUp);
        c.height = Math.round(h * scaleUp);
        const ctx = c.getContext('2d');
        ctx.fillStyle = '#ffffff'; // PNG has no page behind it; transparent reads as black in many viewers
        ctx.fillRect(0, 0, c.width, c.height);
        ctx.drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        c.toBlob((blob) => {
          if (blob) download(blob, 'fta_diagram.png');
          resolve();
        }, 'image/png');
      };
      img.onerror = () => {
        URL.revokeObjectURL(url);
        setStatusMessage(t('diagram.pngFailed', 'Could not rasterise the diagram to PNG.'), 'error');
        resolve();
      };
      img.src = url;
    });
  }

  // ---- wiring ------------------------------------------------------------
  const unsubscribe = store.subscribe(() => { markSelection(); schedule(); });
  const onHideZero = () => schedule();
  window.addEventListener('fta:hide-zero', onHideZero);
  // The toolbar buttons carry glyphs, not words, so a sighted user sees nothing
  // stale on a language switch -- but the title/aria-label do change, and a
  // screen-reader user switching mid-session would otherwise hear the old
  // language. Re-render on the next diagram update picks up the meta line for
  // free; the toolbar needs this.
  const onLanguage = () => { retitleToolbar(); schedule(); };
  window.addEventListener('fta:language', onLanguage);

  applyTransform();
  schedule();

  return {
    refresh: schedule,
    destroy() {
      destroyed = true;
      if (timer) clearTimeout(timer);
      window.removeEventListener('fta:hide-zero', onHideZero);
      window.removeEventListener('fta:language', onLanguage);
      if (typeof unsubscribe === 'function') unsubscribe();
      clear(container);
    },
  };
}

const STYLES = `
.diagram__toolbar { display:flex; align-items:center; gap:4px; padding:4px 8px;
  border-bottom:1px solid var(--fta-border, #d7dde5); flex:0 0 auto; }
.diagram__spacer { flex:1 1 auto; }
.diagram__zoom { font-variant-numeric: tabular-nums; font-size:12px; min-width:44px;
  text-align:center; color: var(--fta-muted, #5d6a78); }
.diagram__btn { font:inherit; font-size:12px; line-height:1; padding:4px 8px; cursor:pointer;
  background: var(--fta-surface, #fff); color: var(--fta-text, #10151c);
  border:1px solid var(--fta-border, #d7dde5); border-radius:4px; }
.diagram__btn:hover { background: var(--fta-surface-hover, #eef2f6); }
.diagram__btn:focus-visible { outline:2px solid var(--fta-accent, #14507d); outline-offset:1px; }
.diagram__stage { position:relative; overflow:hidden; flex:1 1 auto; min-height:0;
  background: var(--fta-canvas, #fff); cursor:grab; }
.diagram__stage.is-panning { cursor:grabbing; }
.diagram__stage:focus-visible { outline:2px solid var(--fta-accent, #14507d); outline-offset:-2px; }
.diagram__canvas { position:absolute; top:0; left:0; transform-origin:0 0; will-change:transform; }
.diagram__canvas g.node { cursor:pointer; }
.diagram__canvas g.node.is-selected > polygon,
.diagram__canvas g.node.is-selected > path,
.diagram__canvas g.node.is-selected > ellipse {
  stroke: var(--fta-accent, #14507d); stroke-width:2.5px; }
.diagram__status { flex:0 0 auto; padding:4px 8px; font-size:12px; min-height:0; }
.diagram__status--error { color: var(--fta-danger, #a8321c); }
.diagram__status--warn { color: var(--fta-warn, #a85b00); }
`;

export default initDiagram;
