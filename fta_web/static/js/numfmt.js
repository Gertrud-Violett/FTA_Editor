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
 *   parseNumberText(raw)
 *       what people type for a number, read as the plain decimal the server
 *       takes: "5%", "0,05", "1/1000", "０．０５" -> {ok, value, text, changed}
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

/**
 * A plain decimal: digits, an optional fraction and exponent. Number() alone
 * also reads 0x1, 0b1 and 0o1 as 1 (and 0x0 as 0), which the server's float()
 * refuses and nobody means as a probability.
 */
export const DECIMAL_TEXT = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i;

/** Dashes an IME or a word processor puts where a minus sign was meant. */
const MINUS_LIKE = /[‐-―−ー－]/g;

/**
 * "0,05" with the comma as the decimal sign: one comma and no point. The
 * shape of a thousands group ("1,000", "12,500") is refused rather than
 * guessed, because it reads as a thousand to half the world and as one to the
 * other half. A leading zero ("0,005") cannot be a thousands group.
 */
function decimalComma(text) {
  const parts = text.split(',');
  if (parts.length !== 2 || text.indexOf('.') !== -1) return null;
  const whole = parts[0].replace(/^[+-]/, '');
  const fraction = parts[1].replace(/e[+-]?\d+$/i, '');
  if (/^[1-9]\d{0,2}$/.test(whole) && /^\d{3}$/.test(fraction)) return null;
  return parts[0] + '.' + parts[1];
}

/** A plain decimal divided by 100 exactly: the exponent moves, nothing is divided. */
function percentOf(text) {
  const match = /^(.*?)(?:e([+-]?\d+))?$/i.exec(text);
  return Number(match[1] + 'e' + (Number(match[2] || 0) - 2));
}

/**
 * Read a number the way people type one, and give back the plain decimal the
 * server accepts. The server's validator is not widened: the browser sends
 * the number, and shows `text` so the user sees what was understood.
 *
 * NFKC first, so full-width digits and signs (０．０５, ５％, １／１０) are
 * their ASCII selves. Then, in this order:
 *
 *   a trailing %          "5%"      -> 0.05
 *   a simple fraction     "1/1000"  -> 0.001
 *   a decimal comma       "0,05"    -> 0.05   (not "1,000": see decimalComma)
 *
 * @returns {{ok: boolean, value?: number, text?: string, changed?: boolean}}
 *   `changed` is true when `text` is not what was typed (apart from spaces
 *   around it).
 */
export function parseNumberText(raw) {
  const typed = String(raw === null || raw === undefined ? '' : raw).trim();
  let text = typed;
  try {
    text = text.normalize('NFKC');
  } catch (_err) {
    /* a lone surrogate: left as typed, and refused below */
  }
  text = text.replace(MINUS_LIKE, '-').trim();
  if (!text) return { ok: false };

  const plain = (part) => {
    const one = part.trim();
    if (DECIMAL_TEXT.test(one)) return one;
    const comma = decimalComma(one);
    return comma !== null && DECIMAL_TEXT.test(comma) ? comma : null;
  };

  let value;
  let shown;
  if (text.endsWith('%')) {
    const body = plain(text.slice(0, -1));
    if (body === null) return { ok: false };
    value = percentOf(body);
    shown = String(value);
  } else if (text.indexOf('/') !== -1) {
    const parts = text.split('/');
    if (parts.length !== 2) return { ok: false };
    const top = plain(parts[0]);
    const bottom = plain(parts[1]);
    if (top === null || bottom === null || Number(bottom) === 0) return { ok: false };
    value = Number(top) / Number(bottom);
    shown = String(value);
  } else {
    shown = plain(text);
    if (shown === null) return { ok: false };
    value = Number(shown);
  }
  if (!Number.isFinite(value)) return { ok: false };
  return { ok: true, value: value, text: shown, changed: shown !== typed };
}

export default formatProb;
