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
const PAN_SLOP_PX = 4; // movement below this is a click, not a pan

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

// ---------------------------------------------------------------------------
// box sizing: font auto-detect + a manual scale override.
//
// The mismatch this exists to close: viz-js (WASM Graphviz) lays out each
// node's HTML label using its OWN estimate of the named font's metrics, then
// the browser paints the same text with whatever font it actually resolves
// "fontname" to. When those two disagree -- most commonly because the
// requested font is not installed and the browser silently substitutes one
// with different glyph widths -- the drawn text can crowd or cross the box
// border that was sized for the *other* font's metrics.
//
// Detecting which candidate fonts this browser/OS actually has narrows that
// gap (both sides now agree on a font that really exists here), and the
// manual scale is the escape hatch for whatever gap is left: it inflates
// font size and padding together, which is what grows the box, since a box
// has no size of its own beyond what its label needs.
// ---------------------------------------------------------------------------

/** Preference order: Meiryo first per spec, then other common CJK-capable
 * fonts, ending in a generic family that is always considered "available". */
const FONT_CANDIDATES = [
  'Meiryo',
  'Yu Gothic UI',
  'Yu Gothic',
  'Hiragino Sans',
  'Hiragino Kaku Gothic Pro',
  'Noto Sans CJK JP',
  'Noto Sans JP',
  'MS PGothic',
  'sans-serif',
];

const DIAGRAM_SETTINGS_KEY = 'fta.diagram.settings';
// "Scale" is a count of trailing blank characters appended to every node's
// text (json_viewer.node_label on the server): a computed pixel/point width
// was tried twice and still left text spilling past the border in some
// cases, because it depended on guessing the same unknowable thing -- how
// wide this exact text renders in whichever font actually gets used. Padding
// spaces are measured by that same (mis-)guess, so the box grows by exactly
// as much room as they need, no separate width arithmetic required.
const SCALE_MIN = 0;
const SCALE_MAX = 30;
const SCALE_DEFAULT = 4;

function readDiagramSettings() {
  let raw = null;
  try {
    raw = window.localStorage.getItem(DIAGRAM_SETTINGS_KEY);
  } catch (_err) {
    raw = null;
  }
  // fontChoice '' means "auto-detect"; popoverLeft/Top null means "not moved
  // yet, use the default lower-right pin".
  const out = { fontChoice: '', scale: SCALE_DEFAULT, popoverLeft: null, popoverTop: null };
  if (!raw) return out;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.fontChoice === 'string') out.fontChoice = parsed.fontChoice;
    const scale = Math.round(Number(parsed && parsed.scale));
    if (Number.isFinite(scale)) out.scale = Math.min(SCALE_MAX, Math.max(SCALE_MIN, scale));
    const left = Number(parsed && parsed.popoverLeft);
    const top = Number(parsed && parsed.popoverTop);
    if (Number.isFinite(left)) out.popoverLeft = left;
    if (Number.isFinite(top)) out.popoverTop = top;
  } catch (_err) {
    /* corrupt entry: keep the defaults */
  }
  return out;
}

function writeDiagramSettings(settings) {
  try {
    window.localStorage.setItem(DIAGRAM_SETTINGS_KEY, JSON.stringify(settings));
  } catch (_err) {
    /* private mode: the choice just does not persist across reloads */
  }
}

/**
 * True when the diagram should be drawn dark. Reads the same signal main.js
 * sets on `<html data-theme>` (main.js owns the theme cycle; this only reads
 * its result) -- 'system' leaves the attribute off, so that case falls
 * through to the OS/browser preference via `prefers-color-scheme`.
 */
function isDarkMode() {
  const attr = document.documentElement.getAttribute('data-theme');
  if (attr === 'dark') return true;
  if (attr === 'light') return false;
  try {
    return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  } catch (_err) {
    return false;
  }
}

/** First candidate this browser reports as available, cached for the page's
 * lifetime -- `document.fonts.check` is cheap but there is no reason to
 * repeat it on every render. */
let detectedFontCache = null;
function detectFont() {
  if (detectedFontCache) return detectedFontCache;
  let found = FONT_CANDIDATES[FONT_CANDIDATES.length - 1]; // 'sans-serif': always matches
  try {
    for (const name of FONT_CANDIDATES) {
      if (name === 'sans-serif') break;
      if (document.fonts && document.fonts.check(`14px "${name}"`)) {
        found = name;
        break;
      }
    }
  } catch (_err) {
    /* document.fonts unsupported (very old browser): fall back to generic */
  }
  detectedFontCache = found;
  return found;
}

/**
 * Synchronous SHA-1 (hex). The WebCrypto digest is async and the id map is
 * built inside a click handler, so a small in-line implementation is used;
 * inputs are node ids, never more than a few hundred bytes.
 */
function sha1Hex(text) {
  const bytes = new TextEncoder().encode(text);
  const ml = bytes.length;
  const wordCount = (((ml + 8) >> 6) << 4) + 16;
  const words = new Uint32Array(wordCount);
  for (let i = 0; i < ml; i += 1) words[i >> 2] |= bytes[i] << (24 - (i % 4) * 8);
  words[ml >> 2] |= 0x80 << (24 - (ml % 4) * 8);
  words[wordCount - 1] = ml * 8;

  let h0 = 0x67452301;
  let h1 = 0xefcdab89;
  let h2 = 0x98badcfe;
  let h3 = 0x10325476;
  let h4 = 0xc3d2e1f0;
  const w = new Uint32Array(80);
  for (let block = 0; block < wordCount; block += 16) {
    for (let i = 0; i < 16; i += 1) w[i] = words[block + i];
    for (let i = 16; i < 80; i += 1) {
      const x = w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16];
      w[i] = (x << 1) | (x >>> 31);
    }
    let a = h0;
    let b = h1;
    let c = h2;
    let d = h3;
    let e = h4;
    for (let i = 0; i < 80; i += 1) {
      let f;
      let k;
      if (i < 20) { f = (b & c) | (~b & d); k = 0x5a827999; }
      else if (i < 40) { f = b ^ c ^ d; k = 0x6ed9eba1; }
      else if (i < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8f1bbcdc; }
      else { f = b ^ c ^ d; k = 0xca62c1d6; }
      const next = (((a << 5) | (a >>> 27)) + f + e + k + w[i]) >>> 0;
      e = d;
      d = c;
      c = (b << 30) | (b >>> 2);
      b = a;
      a = next;
    }
    h0 = (h0 + a) >>> 0;
    h1 = (h1 + b) >>> 0;
    h2 = (h2 + c) >>> 0;
    h3 = (h3 + d) >>> 0;
    h4 = (h4 + e) >>> 0;
  }
  return [h0, h1, h2, h3, h4].map((v) => v.toString(16).padStart(8, '0')).join('');
}

/**
 * Mirror of `json_viewer.sanitize_id`: an id made only of [0-9A-Za-z_] is
 * kept; any other id is replaced character-for-character and suffixed with
 * the first 8 hex digits of its SHA-1, so "a.b" and "a b" no longer collide.
 * Graphviz writes the sanitized id into each node's <title>, which is what
 * click-to-select matches against.
 */
function sanitizeId(value) {
  const raw = String(value);
  const clean = raw.replace(/[^0-9A-Za-z_]/g, '_');
  if (clean === raw) return raw;
  return clean + '_' + sha1Hex(raw).slice(0, 8);
}

const SAFE_HREF = /^(#|https?:\/\/)/i;

/**
 * Defence in depth on the Graphviz output: node names are escaped on the
 * server, but the SVG is still imported into the live document, so anything
 * that could run script is stripped here regardless.
 */
function sanitizeSvg(root) {
  root.querySelectorAll('script, foreignObject').forEach((node) => node.remove());
  const doc = root.ownerDocument;
  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
  const nodes = [root];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    for (const attr of Array.from(node.attributes)) {
      const name = attr.name.toLowerCase();
      const local = (attr.localName || name).toLowerCase();
      if (name.startsWith('on')) node.removeAttributeNode(attr);
      else if (local === 'href' && !SAFE_HREF.test(attr.value.trim())) node.removeAttributeNode(attr);
    }
  }
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

  // ---- box-sizing popover (font auto-detect + manual scale) --------------
  const boxSettings = readDiagramSettings();

  const fontSelect = el('select', { 'aria-label': 'Diagram font' }, [
    el('option', { value: '', text: 'Auto-detect' }),
    ...FONT_CANDIDATES.filter((n) => n !== 'sans-serif').map((n) => el('option', { value: n, text: n })),
    el('option', { value: 'sans-serif', text: 'System default' }),
  ]);
  fontSelect.value = boxSettings.fontChoice;

  const scaleInput = el('input', {
    type: 'number',
    min: String(SCALE_MIN),
    max: String(SCALE_MAX),
    step: '1',
    'aria-label': 'Diagram box scale',
    value: String(boxSettings.scale),
  });

  const fontDetectedNote = el('span', { class: 'diagram__fontnote' });

  function refreshFontNote() {
    const active = boxSettings.fontChoice ? boxSettings.fontChoice : detectFont();
    fontDetectedNote.textContent = boxSettings.fontChoice
      ? ''
      : t('diagram.fontAutoUsing', 'Detected: ') + active;
  }

  const popoverCloseBtn = el('button', {
    type: 'button',
    class: 'diagram__popoverHead__close',
    'aria-label': t('diagram.fontSettingsClose', 'Close'),
    text: '×',
    onclick: () => closePopover(),
  });
  const popoverHead = el('div', { class: 'diagram__popoverHead' }, [
    el('span', { text: t('diagram.fontSettings', 'Font & box size') }),
    popoverCloseBtn,
  ]);

  const popover = el(
    'div',
    { class: 'diagram__popover', hidden: true },
    [
      popoverHead,
      el('label', { class: 'diagram__popoverRow' }, [
        el('span', { text: t('diagram.fontLabel', 'Font') }),
        fontSelect,
      ]),
      fontDetectedNote,
      el('label', { class: 'diagram__popoverRow' }, [
        el('span', { text: t('diagram.scaleLabel', 'Box scale') }),
        scaleInput,
      ]),
      el('p', { class: 'diagram__popoverHint' }, [
        t(
          'diagram.scaleHint',
          'If text still spills out of the boxes after auto-detect, raise the scale.'
        ),
      ]),
    ]
  );

  const aaBtn = btn('Aa', 'diagram.fontSettings', 'Font & box size', () => {
    if (popover.hidden) openPopover();
    else closePopover();
  });

  const POPOVER_MARGIN = 8;

  function clampPopoverPosition(left, top, width, height) {
    const maxLeft = Math.max(POPOVER_MARGIN, window.innerWidth - width - POPOVER_MARGIN);
    const maxTop = Math.max(POPOVER_MARGIN, window.innerHeight - height - POPOVER_MARGIN);
    return {
      left: Math.max(POPOVER_MARGIN, Math.min(left, maxLeft)),
      top: Math.max(POPOVER_MARGIN, Math.min(top, maxTop)),
    };
  }

  function placePopover(left, top) {
    const width = popover.offsetWidth;
    const height = popover.offsetHeight;
    const pos = clampPopoverPosition(left, top, width, height);
    popover.style.left = `${pos.left}px`;
    popover.style.top = `${pos.top}px`;
    return pos;
  }

  /**
   * Positioned as `position: fixed` and appended straight to `document.body`
   * (see below), not inside the toolbar: the toolbar lives inside
   * `#diagram-root`, which -- like every `.panel` -- has `overflow: hidden`
   * so a long diagram or a wide SVG cannot blow out the surrounding layout.
   * A merely `position: absolute` popover would be clipped by that the
   * moment the diagram panel is narrower than the popover, which is exactly
   * what made this menu vanish or run off-screen before. Anchoring by
   * `getBoundingClientRect()` and clamping to the viewport keeps it fully
   * visible regardless of panel width.
   *
   * Default position is the diagram panel's lower-right corner (pinned
   * there, as requested); once the user drags it, that spot is remembered
   * (in localStorage) and used instead until they drag it again.
   */
  function openPopover() {
    popover.hidden = false;
    if (boxSettings.popoverLeft !== null && boxSettings.popoverTop !== null) {
      placePopover(boxSettings.popoverLeft, boxSettings.popoverTop);
      return;
    }
    const stageRect = stage.getBoundingClientRect();
    const width = popover.offsetWidth;
    const height = popover.offsetHeight;
    placePopover(
      stageRect.right - width - POPOVER_MARGIN,
      stageRect.bottom - height - POPOVER_MARGIN
    );
  }

  function closePopover() {
    popover.hidden = true;
  }

  // ---- dragging: pointerdown on the header moves the whole popover -------
  let dragOffsetX = 0;
  let dragOffsetY = 0;
  let draggingPopover = false;
  popoverHead.addEventListener('pointerdown', (ev) => {
    if (ev.target === popoverCloseBtn || ev.button !== 0) return;
    draggingPopover = true;
    const rect = popover.getBoundingClientRect();
    dragOffsetX = ev.clientX - rect.left;
    dragOffsetY = ev.clientY - rect.top;
    popoverHead.setPointerCapture(ev.pointerId);
    ev.preventDefault();
  });
  popoverHead.addEventListener('pointermove', (ev) => {
    if (!draggingPopover) return;
    const pos = placePopover(ev.clientX - dragOffsetX, ev.clientY - dragOffsetY);
    boxSettings.popoverLeft = pos.left;
    boxSettings.popoverTop = pos.top;
  });
  const endPopoverDrag = (ev) => {
    if (!draggingPopover) return;
    draggingPopover = false;
    try { popoverHead.releasePointerCapture(ev.pointerId); } catch (_err) { /* already released */ }
    writeDiagramSettings(boxSettings);
  };
  popoverHead.addEventListener('pointerup', endPopoverDrag);
  popoverHead.addEventListener('pointercancel', endPopoverDrag);

  fontSelect.addEventListener('change', () => {
    boxSettings.fontChoice = fontSelect.value;
    writeDiagramSettings(boxSettings);
    refreshFontNote();
    schedule();
  });
  scaleInput.addEventListener('change', () => {
    const value = Math.round(Number(scaleInput.value));
    boxSettings.scale = Number.isFinite(value)
      ? Math.min(SCALE_MAX, Math.max(SCALE_MIN, value))
      : SCALE_DEFAULT;
    scaleInput.value = String(boxSettings.scale);
    writeDiagramSettings(boxSettings);
    schedule();
  });
  const onDocClickClosePopover = (ev) => {
    if (popover.hidden) return;
    if (popover.contains(ev.target) || aaBtn.contains(ev.target)) return;
    closePopover();
  };
  document.addEventListener('click', onDocClickClosePopover);
  // A resize can invalidate the position this was last opened at (or the
  // panel it belongs to may no longer even be on screen); closing rather
  // than repositioning avoids a popover stranded over the wrong panel.
  const onWindowResizeClosePopover = () => closePopover();
  window.addEventListener('resize', onWindowResizeClosePopover);
  refreshFontNote();
  // Appended to <body>, not the toolbar -- see openPopover()'s comment.
  document.body.appendChild(popover);

  const toolbar = el('div', { class: 'diagram__toolbar' }, [
    btn('−', 'diagram.zoomOut', 'Zoom out', () => zoomBy(1 / ZOOM_STEP)),
    zoomLabel,
    btn('+', 'diagram.zoomIn', 'Zoom in', () => zoomBy(ZOOM_STEP)),
    btn('⤢', 'diagram.fit', 'Fit to window', () => fit()),
    el('span', { class: 'diagram__spacer' }),
    aaBtn,
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

  /** The font/scale to actually send with this render -- the single place
   * both /api/dot and /api/render's native path read from, so the on-screen
   * preview and any exported file always agree on box sizing. */
  function effectiveBoxSettings() {
    return {
      font: boxSettings.fontChoice || detectFont(),
      scale: boxSettings.scale,
      dark: isDarkMode(),
    };
  }

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
  // Pointer capture is taken only once the pointer has actually MOVED past
  // PAN_SLOP_PX. Capturing on pointerdown -- which is what this did until
  // 1.6.4 -- retargets the compatibility mouse events, so the `click` that
  // follows is dispatched at the stage <div> instead of the <g class="node">
  // that was pressed, and click-to-select below could never find a node.
  let pressing = false;   // left button is down inside the stage
  let dragging = false;   // ...and it has moved far enough to be a pan
  let dragX = 0;
  let dragY = 0;
  let pressX = 0;
  let pressY = 0;
  let pressNode = null;   // the <g class="node"> under pointerdown, if any
  stage.addEventListener('pointerdown', (ev) => {
    if (ev.button !== 0) return;
    pressing = true;
    dragging = false;
    pressX = ev.clientX;
    pressY = ev.clientY;
    dragX = ev.clientX - tx;
    dragY = ev.clientY - ty;
    // Remembered here because the click event may be retargeted (a capture
    // taken mid-gesture, or a press on a node that scrolls out from under the
    // pointer); the press target is the honest answer to "which node?".
    pressNode = (ev.target.closest && ev.target.closest('g.node')) || null;
  });
  stage.addEventListener('pointermove', (ev) => {
    if (!pressing) return;
    if (!dragging) {
      if (Math.abs(ev.clientX - pressX) < PAN_SLOP_PX
        && Math.abs(ev.clientY - pressY) < PAN_SLOP_PX) return;
      dragging = true;
      pressNode = null; // a drag is a pan, never a selection
      try { stage.setPointerCapture(ev.pointerId); } catch (_) { /* not capturable */ }
      stage.classList.add('is-panning');
    }
    tx = ev.clientX - dragX;
    ty = ev.clientY - dragY;
    applyTransform();
  });
  const endPan = (ev) => {
    if (!pressing) return;
    pressing = false;
    if (!dragging) return;
    dragging = false;
    try { stage.releasePointerCapture(ev.pointerId); } catch (_) { /* already released */ }
    stage.classList.remove('is-panning');
  };
  stage.addEventListener('pointerup', endPan);
  stage.addEventListener('pointercancel', (ev) => {
    pressNode = null;
    endPan(ev);
  });

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
    // Any <a> left in the SVG has had its href vetted, but navigation away
    // from the editor is never what a click on the diagram means.
    const anchor = ev.target.closest && ev.target.closest('a');
    if (anchor && stage.contains(anchor)) ev.preventDefault();
    const g = (ev.target.closest && ev.target.closest('g.node')) || pressNode;
    pressNode = null;
    if (!svgEl) return;
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
      const box = effectiveBoxSettings();
      const payload = await api.get(
        `/dot?hideZero=${hideZero ? 'true' : 'false'}&font=${encodeURIComponent(box.font)}` +
        `&scale=${box.scale}&dark=${box.dark ? 'true' : 'false'}`
      );
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
      sanitizeSvg(parsed);
      svgEl = document.importNode(parsed, true);
      // Give the SVG real intrinsic pixel size from its own viewBox rather
      // than stripping width/height outright. .diagram__canvas is
      // position:absolute with no explicit size (it shrink-wraps its child so
      // the zoom transform below has something concrete to scale), and a
      // naked <svg> with only a viewBox inside such a parent has nothing to
      // lay out against -- Chromium collapses it to 0x0 instead of falling
      // back to a UA default, so the rendered diagram becomes invisible while
      // still being fully present in the DOM (every existing check --
      // "does a <svg> exist", "does it contain this text" -- passes anyway).
      // Zoom still comes entirely from .diagram__canvas's own
      // `transform: scale()` in applyTransform(), which multiplies this
      // intrinsic size, so fixing the collapse does not fight zoom.
      const vb = svgEl.viewBox && svgEl.viewBox.baseVal;
      if (vb && vb.width > 0 && vb.height > 0) {
        svgEl.setAttribute('width', String(vb.width));
        svgEl.setAttribute('height', String(vb.height));
      } else {
        svgEl.removeAttribute('width');
        svgEl.removeAttribute('height');
      }
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
        const box = effectiveBoxSettings();
        const res = await api.post('/render', {
          format: 'png',
          hideZero: !!(window.ftaShell && window.ftaShell.hideZero),
          highQuality: true,
          font: box.font,
          scale: box.scale,
          dark: box.dark,
        });
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
  const onLanguage = () => { retitleToolbar(); refreshFontNote(); schedule(); };
  window.addEventListener('fta:language', onLanguage);

  // Explicit light/dark from the theme toggle...
  const onThemeChange = () => schedule();
  window.addEventListener('fta:theme', onThemeChange);
  // ...and the OS-level preference, for when the toggle is left on 'system'
  // (isDarkMode() falls through to this same media query at render time).
  let darkMediaQuery = null;
  try {
    darkMediaQuery = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
    if (darkMediaQuery) darkMediaQuery.addEventListener('change', onThemeChange);
  } catch (_err) {
    darkMediaQuery = null;
  }

  applyTransform();
  schedule();

  return {
    refresh: schedule,
    exportSvg,
    exportPng,
    getBoxSettings: effectiveBoxSettings,
    destroy() {
      destroyed = true;
      if (timer) clearTimeout(timer);
      window.removeEventListener('fta:hide-zero', onHideZero);
      window.removeEventListener('fta:language', onLanguage);
      window.removeEventListener('fta:theme', onThemeChange);
      if (darkMediaQuery) darkMediaQuery.removeEventListener('change', onThemeChange);
      window.removeEventListener('resize', onWindowResizeClosePopover);
      document.removeEventListener('click', onDocClickClosePopover);
      if (popover.parentNode) popover.parentNode.removeChild(popover);
      if (typeof unsubscribe === 'function') unsubscribe();
      clear(container);
    },
  };
}

const STYLES = `
.diagram__toolbar { display:flex; flex-wrap:wrap; align-items:center; gap:4px; padding:4px 8px;
  border-bottom:1px solid var(--fta-border, #d7dde5); flex:0 0 auto; }
.diagram__spacer { flex:1 1 auto; }
.diagram__zoom { font-variant-numeric: tabular-nums; font-size:12px; min-width:44px;
  text-align:center; color: var(--fta-muted-fg, #5d6a78); }
.diagram__btn { font:inherit; font-size:12px; line-height:1; padding:4px 8px; cursor:pointer;
  background: var(--fta-surface, #fff); color: var(--fta-fg, #10151c);
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
.diagram__status { flex:0 0 auto; padding:4px 8px; font-size:12px; min-height:0;
  color: var(--fta-fg, #10151c); }
.diagram__status--error { color: var(--fta-danger-fg, #a8321c); }
.diagram__status--warn { color: var(--fta-warn-fg, #a85b00); }
.diagram__popover {
  /* Fixed and appended to <body> (see openPopover() in the JS): a diagram
     panel is a .panel with overflow: hidden, which would otherwise clip
     this the moment the panel is narrower than the popover. Position
     defaults to the diagram's lower-right corner and is user-draggable
     (see the pointerdown wiring on .diagram__popoverHead below); both are
     computed/clamped to the viewport in JS. */
  position:fixed; z-index:1000;
  display:flex; flex-direction:column; gap:6px; width:15rem; max-width:calc(100vw - 8px);
  padding:10px;
  background: var(--fta-surface, #fff); color: var(--fta-fg, #10151c);
  border:1px solid var(--fta-border, #d7dde5); border-radius:6px;
  box-shadow: 0 8px 24px rgba(16,20,24,0.20); font-size:12px;
}
/* The explicit display:flex above outranks the UA's [hidden] rule, so a
   closed popover kept its box and swallowed clicks on whatever it overlapped. */
.diagram__popover[hidden] {
  display:none;
}
.diagram__popover[hidden] { display:none; }
.diagram__popoverHead {
  display:flex; align-items:center; justify-content:space-between; gap:8px;
  margin:-10px -10px 0; padding:6px 8px;
  border-bottom:1px solid var(--fta-border, #d7dde5);
  background: var(--fta-surface-2, #f4f6f8);
  border-radius:6px 6px 0 0;
  cursor:move; touch-action:none; user-select:none;
  font-weight:600;
}
.diagram__popoverHead__close { font:inherit; font-size:14px; line-height:1; padding:0 4px;
  cursor:pointer; background:transparent; color:inherit; border:0; }
.diagram__popoverRow { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.diagram__popoverRow select,
.diagram__popoverRow input { font:inherit; font-size:12px; padding:2px 4px;
  border:1px solid var(--fta-border, #d7dde5); border-radius:4px;
  background: var(--fta-surface, #fff); color: inherit; }
.diagram__popoverRow input[type="number"] { width:4.5rem; }
.diagram__fontnote { color: var(--fta-muted-fg, #5d6a78); font-size:11px; min-height:1.2em; overflow-wrap:anywhere; }
.diagram__popoverHint { margin:0; color: var(--fta-muted-fg, #5d6a78); font-size:11px; line-height:1.4; }
`;

export default initDiagram;
