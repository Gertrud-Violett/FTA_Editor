/**
 * numfmt.js -- probability formatting with a per-user significant-figure
 * preference. Mirrors fta_web/numfmt.py.
 *
 * CONTRACT
 * ========
 *   formatProb(v, sf = getSigFigs())
 *       0            -> "0"
 *       non-finite   -> "—" (also null / undefined / "")
 *       |v| < 1e-3 or |v| >= 1e4  -> exponent form, e.g. 1e-7 -> "1.00e-7"
 *       otherwise    -> toPrecision(sf), e.g. 0.5 -> "0.500"
 *   getSigFigs()     localStorage `fta.sigFigs`, default 3, clamped to 1..6
 *   setSigFigs(n)    persist + dispatch `fta:sigfigs` {sigFigs} on window
 *
 * Pure except for the localStorage/window access in the two preference
 * helpers, both wrapped so a private-mode browser or Node import still works.
 */

export const SIG_FIGS_KEY = 'fta.sigFigs';
export const SIG_FIGS_DEFAULT = 3;
export const SIG_FIGS_MIN = 1;
export const SIG_FIGS_MAX = 6;
export const SIG_FIGS_EVENT = 'fta:sigfigs';

function clampSigFigs(n) {
  const value = Math.round(Number(n));
  if (!Number.isFinite(value)) return SIG_FIGS_DEFAULT;
  return Math.min(SIG_FIGS_MAX, Math.max(SIG_FIGS_MIN, value));
}

/** The user's significant-figure preference (1..6, default 3). */
export function getSigFigs() {
  try {
    const raw = window.localStorage.getItem(SIG_FIGS_KEY);
    if (raw === null || raw === '') return SIG_FIGS_DEFAULT;
    return clampSigFigs(raw);
  } catch (_err) {
    return SIG_FIGS_DEFAULT;
  }
}

/** Persist a new preference and tell every listener. Returns the stored value. */
export function setSigFigs(n) {
  const value = clampSigFigs(n);
  try {
    window.localStorage.setItem(SIG_FIGS_KEY, String(value));
  } catch (_err) {
    /* private mode: the preference just does not persist */
  }
  try {
    window.dispatchEvent(new CustomEvent(SIG_FIGS_EVENT, { detail: { sigFigs: value } }));
  } catch (_err) {
    /* no window (tests) */
  }
  return value;
}

/** toExponential without the redundant plus: "1.00e4", not "1.00e+4". */
function exponent(num, sf) {
  return num.toExponential(sf - 1).replace('e+', 'e');
}

/**
 * Format a probability (or any magnitude) to `sf` significant figures.
 * @param {number|string} v
 * @param {number} [sf]
 * @returns {string}
 */
export function formatProb(v, sf) {
  if (v === null || v === undefined || v === '') return '—';
  const num = Number(v);
  if (!Number.isFinite(num)) return '—';
  if (num === 0) return '0';
  const digits = clampSigFigs(sf === undefined || sf === null ? getSigFigs() : sf);
  // Decide plain vs exponent form from the ROUNDED magnitude, exactly like the
  // server (numfmt.py): 0.00099996 at 3 s.f. rounds to 0.00100 (plain), and
  // 9999.7 rounds to 1.00e4 (exponent). Deciding on the raw value made the
  // browser and the DOCX/CLI print the same number differently.
  const mag = Math.abs(Number(num.toExponential(digits - 1)));
  if (mag < 1e-3 || mag >= 1e4) return exponent(num, digits);
  const text = num.toPrecision(digits);
  // toPrecision itself switches to exponent form when the integer part has
  // more digits than `sf` (e.g. 1234 at 2 sf); keep that plain in this range.
  return text.indexOf('e') === -1 ? text : String(Number(text));
}

export default formatProb;
