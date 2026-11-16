/**
 * overlay_scale.js -- the colour scale of the node overlay (store.onOverlay,
 * e.g. {kind: 'fv', values}), shared by diagram.js (event fills) and tree.js
 * (the small bar on each row), so the two panels read the same.
 *
 * Light -> strong orange; black label text stays readable at both ends.
 */

export const SCALE_LOW = Object.freeze([255, 244, 229]);
export const SCALE_HIGH = Object.freeze([230, 85, 13]);

/** fraction in [0, 1] -> 'rgb(r, g, b)'. Out-of-range and NaN are clamped. */
export function scaleColor(fraction) {
  const f = Math.min(1, Math.max(0, Number(fraction) || 0));
  const c = SCALE_LOW.map((lo, i) => Math.round(lo + (SCALE_HIGH[i] - lo) * f));
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
}

/** The largest finite value in an overlay's `values` map (0 when none). */
export function overlayMax(values) {
  let max = 0;
  if (!values || typeof values !== 'object') return max;
  for (const key of Object.keys(values)) {
    const v = Number(values[key]);
    if (Number.isFinite(v) && v > max) max = v;
  }
  return max;
}

export default scaleColor;
