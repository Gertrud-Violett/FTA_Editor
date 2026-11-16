/**
 * fta_symbols.js -- true IEC 61025 / NUREG-0492 fault-tree symbols for the
 * "Standard symbols" diagram style.
 *
 * Graphviz has no AND dome or OR shield, so the server (fta_web/diagram_dot.py)
 * draws the nearest polygon and tags each symbol node with a class:
 *
 *   <g class="node fta-gate fta-gate-and|or|kofn|xor|inhibit|pand|transfer">
 *   <g class="node fta-event fta-event-basic|house|undeveloped|conditioning">
 *
 * replaceGateShapes() swaps that polygon (or ellipse) for the real symbol,
 * fitted to the polygon's bounding box and oriented for the layout: symbols
 * point toward their parent, so with rankdir TB the output is at the top and
 * the inputs at the bottom, and with LR the output is on the left.
 *
 * Every shape is described once in a unit square (u across, v from the output
 * side at 0 to the input side at 1) as straight lines and Bezier curves only.
 * Mapping (u, v) -> (x, y) is affine, so the curves survive it exactly; LR is
 * the transpose, which for these left/right-symmetric shapes is the same as a
 * rotation. (SVG arcs would not survive a transpose -- the sweep flag flips --
 * which is why circles and ellipses are four cubic curves here.)
 *
 * Colours are copied from the Graphviz shape being replaced (the server set
 * them for the current theme), so the symbols follow light/dark mode and an
 * exported SVG/PNG needs no stylesheet.
 */

const K = 0.5522847498; // cubic Bezier circle constant

/** Ellipse inscribed in the unit square, as four cubic curves. */
function ellipseCmds() {
  const c = 0.5 * K;
  return [
    ['M', 0.5, 0],
    ['C', 0.5 + c, 0, 1, 0.5 - c, 1, 0.5],
    ['C', 1, 0.5 + c, 0.5 + c, 1, 0.5, 1],
    ['C', 0.5 - c, 1, 0, 0.5 + c, 0, 0.5],
    ['C', 0, 0.5 - c, 0.5 - c, 0, 0.5, 0],
    ['Z'],
  ];
}

const AND_BODY = [
  ['M', 0, 1],
  ['L', 0, 0.45],
  ['C', 0, 0.2, 0.22, 0, 0.5, 0],
  ['C', 0.78, 0, 1, 0.2, 1, 0.45],
  ['L', 1, 1],
  ['Z'],
];

/** OR shield with its concave input side ending at v = `bottom`. */
function orBody(bottom) {
  const dip = bottom - 0.28;
  const shoulder = bottom * 0.4;
  return [
    ['M', 0, bottom],
    ['Q', 0.5, dip, 1, bottom],
    ['Q', 0.92, shoulder, 0.5, 0],
    ['Q', 0.08, shoulder, 0, bottom],
    ['Z'],
  ];
}

/** Short input stub from the middle of the concave side to the box edge. */
function stubFrom(bottom) {
  const mid = 0.5 * bottom + 0.5 * (bottom - 0.28);
  return [['M', 0.5, mid], ['L', 0.5, 1]];
}

/**
 * Symbol name -> list of parts. `filled: false` parts are strokes only.
 * `keepText`: whether the Graphviz label stays on top (k/n, ON/OFF).
 * `exact`: fit the bounding box as is instead of a centred square.
 */
export const SYMBOLS = Object.freeze({
  'gate-and': { parts: [{ cmds: AND_BODY, filled: true }] },
  'gate-or': { parts: [{ cmds: orBody(1), filled: true }, { cmds: stubFrom(1), filled: false }] },
  'gate-xor': {
    parts: [
      { cmds: orBody(0.86), filled: true },
      { cmds: [['M', 0, 1], ['Q', 0.5, 0.72, 1, 1]], filled: false },
      { cmds: stubFrom(0.86), filled: false },
    ],
  },
  'gate-kofn': {
    parts: [{ cmds: orBody(1), filled: true }, { cmds: stubFrom(1), filled: false }],
    keepText: true,
  },
  'gate-pand': {
    parts: [{ cmds: AND_BODY, filled: true }, { cmds: [['M', 0, 0.8], ['L', 1, 0.8]], filled: false }],
  },
  'gate-inhibit': {
    parts: [{
      cmds: [['M', 0.5, 0], ['L', 1, 0.25], ['L', 1, 0.75], ['L', 0.5, 1], ['L', 0, 0.75], ['L', 0, 0.25], ['Z']],
      filled: true,
    }],
  },
  'gate-transfer': { parts: [{ cmds: [['M', 0.5, 0], ['L', 1, 1], ['L', 0, 1], ['Z']], filled: true }] },
  'event-basic': { parts: [{ cmds: ellipseCmds(), filled: true }] },
  'event-undeveloped': {
    parts: [{ cmds: [['M', 0.5, 0], ['L', 1, 0.5], ['L', 0.5, 1], ['L', 0, 0.5], ['Z']], filled: true }],
  },
  'event-house': {
    parts: [{ cmds: [['M', 0.5, 0], ['L', 1, 0.35], ['L', 1, 1], ['L', 0, 1], ['L', 0, 0.35], ['Z']], filled: true }],
    keepText: true,
  },
  'event-conditioning': { parts: [{ cmds: ellipseCmds(), filled: true }], keepText: true, exact: true },
});

function fmt(n) {
  return String(Math.round(n * 100) / 100);
}

/**
 * The SVG path `d` for unit-square commands fitted to `box` ({x, y, w, h}),
 * output side toward the parent: top for TB, left for LR.
 */
export function symbolPath(cmds, box, rankdir) {
  const lr = String(rankdir || '').toUpperCase() === 'LR';
  const map = (u, v) => (lr
    ? [box.x + v * box.w, box.y + u * box.h]
    : [box.x + u * box.w, box.y + v * box.h]);
  const out = [];
  for (const cmd of cmds) {
    const op = cmd[0];
    if (op === 'Z') {
      out.push('Z');
      continue;
    }
    const pts = [];
    for (let i = 1; i < cmd.length; i += 2) {
      const [x, y] = map(cmd[i], cmd[i + 1]);
      pts.push(fmt(x) + ',' + fmt(y));
    }
    out.push(op + pts.join(' '));
  }
  return out.join(' ');
}

/** 'gate-and' etc. from a <g>'s class list, or null. */
export function symbolKey(g) {
  const cls = (g.getAttribute('class') || '').split(/\s+/);
  for (const token of cls) {
    const m = /^fta-(gate|event)-([a-z]+)$/.exec(token);
    if (m) {
      const key = m[1] + '-' + m[2];
      if (SYMBOLS[key]) return key;
    }
  }
  return null;
}

function num(value) {
  const n = Number.parseFloat(value);
  return Number.isFinite(n) ? n : 0;
}

/** Bounding box of a Graphviz polygon/ellipse, from its own attributes (no layout needed). */
function shapeBox(shape) {
  const tag = shape.localName || shape.nodeName;
  if (tag === 'ellipse') {
    const cx = num(shape.getAttribute('cx'));
    const cy = num(shape.getAttribute('cy'));
    const rx = num(shape.getAttribute('rx'));
    const ry = num(shape.getAttribute('ry'));
    return { x: cx - rx, y: cy - ry, w: 2 * rx, h: 2 * ry };
  }
  const nums = String(shape.getAttribute('points') || '')
    .trim()
    .split(/[\s,]+/)
    .map(Number)
    .filter(Number.isFinite);
  if (nums.length < 4) return null;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (let i = 0; i + 1 < nums.length; i += 2) {
    minX = Math.min(minX, nums[i]);
    maxX = Math.max(maxX, nums[i]);
    minY = Math.min(minY, nums[i + 1]);
    maxY = Math.max(maxY, nums[i + 1]);
  }
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
}

function union(a, b) {
  if (!a) return b;
  if (!b) return a;
  const x = Math.min(a.x, b.x);
  const y = Math.min(a.y, b.y);
  return {
    x,
    y,
    w: Math.max(a.x + a.w, b.x + b.w) - x,
    h: Math.max(a.y + a.h, b.y + b.h) - y,
  };
}

/**
 * Replace every tagged Graphviz shape under `svgEl` with its true symbol.
 * Idempotent (a group already converted has no polygon left to replace).
 * @returns {number} how many symbols were drawn.
 */
export function replaceGateShapes(svgEl, rankdir) {
  if (!svgEl || typeof svgEl.querySelectorAll !== 'function') return 0;
  const ns = 'http://www.w3.org/2000/svg';
  const doc = svgEl.ownerDocument;
  let count = 0;
  svgEl.querySelectorAll('g.node').forEach((g) => {
    const key = symbolKey(g);
    if (!key) return;
    const spec = SYMBOLS[key];
    const shapes = Array.from(g.children).filter((c) => {
      const tag = c.localName || c.nodeName;
      return tag === 'polygon' || tag === 'ellipse';
    });
    if (!shapes.length) return;
    let box = null;
    let stroke = null;
    let fill = null;
    let strokeWidth = null;
    for (const shape of shapes) {
      box = union(box, shapeBox(shape));
      if (!stroke) {
        const s = shape.getAttribute('stroke');
        if (s && s !== 'none') stroke = s;
      }
      if (!fill) {
        const f = shape.getAttribute('fill');
        if (f && f !== 'none') fill = f;
      }
      if (!strokeWidth && shape.getAttribute('stroke-width')) strokeWidth = shape.getAttribute('stroke-width');
    }
    if (!box || !(box.w > 0) || !(box.h > 0)) return;
    if (!spec.exact) {
      const side = Math.max(box.w, box.h);
      box = { x: box.x + (box.w - side) / 2, y: box.y + (box.h - side) / 2, w: side, h: side };
    }
    const anchor = shapes[0];
    for (const part of spec.parts) {
      const path = doc.createElementNS(ns, 'path');
      path.setAttribute('d', symbolPath(part.cmds, box, rankdir));
      path.setAttribute('class', part.filled ? 'fta-sym' : 'fta-sym fta-sym-line');
      path.setAttribute('fill', part.filled ? fill || 'none' : 'none');
      path.setAttribute('stroke', stroke || 'currentColor');
      path.setAttribute('stroke-width', strokeWidth || '1.2');
      path.setAttribute('stroke-linejoin', 'round');
      g.insertBefore(path, anchor);
    }
    for (const shape of shapes) shape.remove();
    if (!spec.keepText) g.querySelectorAll(':scope > text').forEach((node) => node.remove());
    g.classList.add('fta-sym-done');
    count += 1;
  });
  return count;
}

export default replaceGateShapes;
